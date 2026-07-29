"""Market data service.

Resiliente para entornos cloud (Render). Estrategia:
- Quotes: Finnhub PRIMARIO (no IP-blocked, API key del usuario), yfinance fallback.
- Historical OHLC: yfinance con curl_cffi (impersona Chrome) PRIMARIO,
  Stooq fallback (gratis, sin API key, sin rate limit).
- Caché en memoria para historial (reduce drásticamente llamadas externas).
- Rate limiter global para Finnhub (60 calls/min free tier).
"""
import asyncio
import concurrent.futures
import contextvars
import io
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

_log = logging.getLogger("inveria.market_data")
# Silence yfinance noisy 401 errors (we fall back to other sources anyway)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# curl_cffi impersonates a real browser to bypass Yahoo Finance anti-bot on cloud providers
try:
    from curl_cffi import requests as cffi_requests
    _yf_session = cffi_requests.Session(impersonate="chrome124")
except Exception:
    _yf_session = None

# Sesión HTTP global con connection pooling + keep-alive. Evita el handshake TLS
# en cada llamada a Finnhub/Stooq (cientos por ciclo del worker / screener).
_http = requests.Session()
_http.headers.update({"User-Agent": "Mozilla/5.0"})
_http_adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
_http.mount("https://", _http_adapter)
_http.mount("http://", _http_adapter)


# ---------- Finnhub rate limiter ----------
# Free tier = 60 calls/minute. We stay safely below that.
#
# Prioridad: las llamadas marcadas como "background" (el screener, que escanea 120
# símbolos) solo usan hasta `bg_cap`, dejando margen reservado para las llamadas de
# usuario (dashboard). Así un escaneo en segundo plano no atasca la cuota durante ~50s.
_finnhub_bg_ctx = contextvars.ContextVar("finnhub_background", default=False)


def enter_finnhub_background():
    """Marca el contexto actual (y sus hijos vía to_thread) como background. Devuelve token."""
    return _finnhub_bg_ctx.set(True)


def reset_finnhub_background(token):
    try:
        _finnhub_bg_ctx.reset(token)
    except Exception:
        pass


class _FinnhubLimiter:
    def __init__(self, max_per_min: int = 50, bg_reserve: int = 15):
        self.max_per_min = max_per_min
        self.bg_cap = max(1, max_per_min - bg_reserve)  # tope para llamadas de fondo
        self.calls = []
        self.lock = threading.Lock()

    def acquire(self, max_wait: float = None) -> bool:
        """Reserva un hueco. Devuelve True si lo consigue.

        max_wait acota la espera: si no hay hueco en ese tiempo, devuelve False en vez de
        seguir bloqueando. Es lo que necesitan las llamadas que sirven una petición del
        usuario — antes esperaban hasta 60s, el endpoint las cortaba a los 8 y la página
        acababa diciendo "no se encontró el símbolo" cuando el símbolo existía de sobra:
        lo que faltaba era cuota. Con un tope corto se cae al proveedor alternativo, que
        no pasa por este limitador, y la página responde igual.
        """
        is_bg = _finnhub_bg_ctx.get()
        cap = self.bg_cap if is_bg else self.max_per_min
        t_start = time.time()
        while True:
            with self.lock:
                now = time.time()
                self.calls = [t for t in self.calls if now - t < 60]
                if len(self.calls) < cap:
                    self.calls.append(now)
                    waited = now - t_start
                    if waited > 2.0:
                        _log.warning("Finnhub limiter blocked %.1fs [bg=%s window=%d cap=%d]",
                                     waited, is_bg, len(self.calls), cap)
                    return True
                sleep_for = 60 - (now - self.calls[0]) + 0.05
            if max_wait is not None:
                restante = max_wait - (time.time() - t_start)
                if restante <= 0:
                    _log.warning("Finnhub limiter: sin hueco en %.1fs [bg=%s cap=%d] — "
                                 "se usará el proveedor alternativo", max_wait, is_bg, cap)
                    return False
                sleep_for = min(sleep_for, restante)
            # Dormimos FUERA del lock para no serializar al resto de callers.
            time.sleep(min(max(sleep_for, 0.05), 1.0))


# bg_reserve = cuota que las tareas de FONDO no pueden tocar, o sea la reservada a lo que
# pide el usuario. Estaba en 10: el fondo podía comerse 40 de las 50 y dejaba 10/min para
# navegar. Como abrir una acción gasta entre 2 y 5 llamadas, eso daba para 2-3 cambios de
# ticker por minuto antes de quedarse sin cuota — justo el síntoma de "cambio entre acciones
# de la watchlist y acaba petando".
# Ahora se reparte a la mitad. El vigilante de la Cartera tardará algo más en completar sus
# vueltas, que da igual: comprobar niveles a los 60s en vez de a los 45s no cambia nada,
# quedarse sin poder abrir una acción sí.
_finnhub_limiter = _FinnhubLimiter(
    max_per_min=int(os.environ.get("FINNHUB_MAX_PER_MIN", 50)),
    bg_reserve=int(os.environ.get("FINNHUB_FOREGROUND_RESERVE", 25)),
)


def _ticker(symbol: str):
    """Return a yfinance Ticker using the browser-impersonating session when available."""
    if _yf_session is not None:
        try:
            return yf.Ticker(symbol, session=_yf_session)
        except Exception:
            pass
    return yf.Ticker(symbol)


# Cada etiqueta = TAMAÑO DE VELA real (lo que espera un trader). El periodo es cuánto
# histórico se carga. El 4H se construye remuestreando velas de 1h (Yahoo no lo da nativo).
PERIOD_MAP = {
    "15M": ("1mo", "15m"),   # velas de 15 min
    "1H": ("2mo", "1h"),     # velas de 1 hora
    "4H": ("1y", "1h"),      # velas de 4 horas (remuestreadas desde 1h)
    "1D": ("2y", "1d"),      # velas DIARIAS
    "1W": ("5y", "1wk"),     # velas SEMANALES
    "1M": ("10y", "1mo"),    # velas MENSUALES
    # Compatibilidad con enlaces antiguos:
    "5M": ("5d", "5m"),
    "3M": ("6mo", "1d"),
    "1Y": ("2y", "1d"),
    "5Y": ("5y", "1wk"),
}

# Stooq interval mapping: d=daily, w=weekly, m=monthly. No intraday for free.
_STOOQ_INTERVALS = {"1d": "d", "1wk": "w", "1mo": "m"}

# Yahoo direct chart API range/interval mapping
_YAHOO_INTERVAL_MAP = {
    "5m": ("5m", "5d"),
    "15m": ("15m", "1mo"),
    "1h": ("60m", "3mo"),
    "30m": ("30m", "1mo"),
    "1d": ("1d", "2y"),
    "1wk": ("1wk", "5y"),
}


# ---------- History cache ----------
_history_cache: dict = {}
_history_lock = threading.Lock()
_HISTORY_TTL_SECONDS = 900  # 15 min — indicadores no necesitan precisión segundo a segundo
# Cada entrada es un DataFrame de hasta 2 años (cientos de KB). Acotamos el número
# de símbolos cacheados para que la RAM no crezca sin límite en el free tier.
_HISTORY_MAXSIZE = 120


def _evict_bounded(store: dict, maxsize: int, ts_key: str = "ts"):
    """Purga expirados-o-no y evita crecer sin límite: si se supera maxsize, elimina
    las entradas más antiguas (FIFO por orden de inserción de dict)."""
    while len(store) > maxsize:
        store.pop(next(iter(store)), None)


def _cache_get(key: str):
    with _history_lock:
        entry = _history_cache.get(key)
        if entry and (time.time() - entry["ts"]) < _HISTORY_TTL_SECONDS:
            return entry["df"]
        if entry:
            _history_cache.pop(key, None)
    return None


def _cache_set(key: str, df):
    with _history_lock:
        _history_cache[key] = {"df": df, "ts": time.time()}
        _evict_bounded(_history_cache, _HISTORY_MAXSIZE)


# ---------- Fundamentals (.info) cache ----------
# yfinance `.info` es la operación más cara (descarga/parsea el blob completo de
# fundamentales, ~1-3s). Los fundamentales no cambian intradía, así que cacheamos 1h.
_info_cache: dict = {}
_info_lock = threading.Lock()
_INFO_TTL_SECONDS = 3600

# yfinance `.info`/`.news` no aceptan timeout y en Render (Yahoo bloquea cloud) pueden
# COLGARSE muchos segundos, bloqueando el dashboard. Los ejecutamos en un pool con un
# tope duro: si Yahoo no responde a tiempo, seguimos con lo que tengamos (precio Finnhub).
_yf_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="yf")
_INFO_FETCH_TIMEOUT = 3.0      # seg máx esperando a .info
_NEWS_FETCH_TIMEOUT = 3.0      # seg máx esperando a .news
_HISTORY_FETCH_TIMEOUT = 2.0   # seg máx esperando a .history antes de caer al fallback


def _call_with_timeout(fn, timeout, default):
    """Ejecuta fn() con un tope de tiempo. Si excede (o falla), devuelve default.
    El hilo colgado sigue en background pero ya no bloquea al caller."""
    try:
        return _yf_pool.submit(fn).result(timeout=timeout)
    except Exception:
        return default


def _get_info_cached(ticker: str, t) -> dict:
    key = ticker.upper()
    with _info_lock:
        entry = _info_cache.get(key)
        if entry and (time.time() - entry["ts"]) < _INFO_TTL_SECONDS:
            return entry["info"]
    info = _call_with_timeout(lambda: t.info or {}, _INFO_FETCH_TIMEOUT, {})
    if info:
        with _info_lock:
            _info_cache[key] = {"info": info, "ts": time.time()}
            _evict_bounded(_info_cache, 300)
    return info


# ---------- Stooq fallback (free, no API key, no rate limit) ----------
def _stooq_symbol(ticker: str) -> str:
    """Stooq uses lowercase + .us suffix for US stocks. ETFs same. Crypto/FX different."""
    t = ticker.lower()
    # ETFs and US stocks use .us suffix in Stooq
    if "." not in t and "-" not in t:
        return f"{t}.us"
    return t


def _fetch_stooq_history(ticker: str, interval: str = "d") -> Optional[pd.DataFrame]:
    """Daily/Weekly/Monthly OHLC from Stooq. Free, no auth."""
    try:
        sym = _stooq_symbol(ticker)
        url = f"https://stooq.com/q/d/l/?s={sym}&i={interval}"
        r = _http.get(url, timeout=5)
        if r.status_code != 200 or not r.text or "apikey" in r.text.lower() or "No data" in r.text:
            return None
        df = pd.read_csv(io.StringIO(r.text))
        if df.empty or "Date" not in df.columns:
            return None
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        if "Volume" not in df.columns:
            df["Volume"] = 0
        df = df.sort_values("Date").reset_index(drop=True)
        return df
    except Exception:
        return None


# ---------- Yahoo direct chart API fallback ----------
# Calls the same backend yfinance uses, but with curl_cffi Chrome impersonation —
# survives some IP blocks better than the high-level yfinance Ticker.history flow.
def _fetch_yahoo_chart(ticker: str, interval: str, period: str) -> Optional[pd.DataFrame]:
    if _yf_session is None:
        return None
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}"
        params = {
            "range": period,
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits",
        }
        r = _yf_session.get(url, params=params, timeout=3)
        if r.status_code != 200:
            return None
        data = r.json() or {}
        chart = (data.get("chart") or {})
        results = chart.get("result")
        if not results:
            return None
        result = results[0]
        ts = result.get("timestamp") or []
        quote = (result.get("indicators") or {}).get("quote", [{}])[0]
        if not ts or not quote:
            return None
        df = pd.DataFrame({
            "Date": pd.to_datetime(ts, unit="s"),
            "Open": quote.get("open") or [],
            "High": quote.get("high") or [],
            "Low": quote.get("low") or [],
            "Close": quote.get("close") or [],
            "Volume": quote.get("volume") or [],
        })
        df["Date"] = df["Date"].dt.tz_localize(None)
        df = df.dropna(subset=["Close"]).reset_index(drop=True)
        if df.empty:
            return None
        return df
    except Exception:
        return None


def _filter_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Trim a daily df to a given lookback period."""
    if df is None or df.empty:
        return df
    days_map = {"5d": 7, "1mo": 35, "3mo": 95, "6mo": 190, "1y": 370, "2y": 740, "5y": 1830}
    days = days_map.get(period, 740)
    cutoff = datetime.now() - timedelta(days=days)
    return df[df["Date"] >= cutoff].reset_index(drop=True)


def get_stock_data(ticker: str, timeframe: str = "1Y"):
    """Fetch historical OHLC data for the chart and indicator computation.

    Tries yfinance (with browser session) first; falls back to Stooq for daily-or-larger
    timeframes. Caches results for 15 min to reduce external load.
    """
    period, interval = PERIOD_MAP.get(timeframe, PERIOD_MAP["1Y"])
    # "1Y" y "1D" resuelven a ("2y","1d"), que es EXACTAMENTE lo que pide
    # get_full_indicator_history: misma llamada a yfinance, mismo procesado, mismos
    # respaldos. Solo cambiaba la clave de caché, así que el dashboard descargaba dos veces
    # el mismo histórico —y es de las llamadas más lentas de la carga—. Delegamos para que
    # compartan una sola descarga y una sola entrada en caché.
    if (period, interval) == ("2y", "1d"):
        return get_full_indicator_history(ticker)

    cache_key = f"hist:{ticker.upper()}:{timeframe}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Try yfinance high-level API first (con tope de tiempo: en cloud puede colgarse)
    df = None
    source = None
    try:
        t = _ticker(ticker)
        df = _call_with_timeout(
            lambda: t.history(period=period, interval=interval, auto_adjust=False),
            _HISTORY_FETCH_TIMEOUT, None,
        )
        if df is not None and not df.empty:
            df = df.reset_index()
            date_col = "Date" if "Date" in df.columns else "Datetime"
            df = df.rename(columns={date_col: "Date"})
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
            source = "yfinance"
        else:
            df = None
    except Exception:
        df = None

    # Fallback 1: direct Yahoo chart API (survives some IP blocks via curl_cffi)
    if df is None or df.empty:
        df = _fetch_yahoo_chart(ticker, interval, period)
        if df is not None and not df.empty:
            source = "yahoo_chart"

    # Fallback 2: Stooq (only daily-or-larger — no intraday support on free tier)
    if df is None or df.empty:
        stooq_interval = _STOOQ_INTERVALS.get(interval, "d")
        df = _fetch_stooq_history(ticker, stooq_interval)
        if df is not None:
            df = _filter_period(df, period)
            source = "stooq"

    if df is None or df.empty:
        return None

    # 4H: Yahoo no da velas de 4h nativas → las construimos agrupando las de 1h.
    if timeframe == "4H":
        try:
            r = df.set_index(pd.to_datetime(df["Date"])).resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
            }).dropna(subset=["Open", "Close"]).reset_index()
            if not r.empty:
                df = r
        except Exception:
            pass

    _stamp_source(df, source)
    _cache_set(cache_key, df)
    return df


def get_full_indicator_history(ticker: str):
    """Fetch 2y daily data used for computing indicators reliably."""
    cache_key = f"ind:{ticker.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    df = None
    source = None
    try:
        t = _ticker(ticker)
        df = _call_with_timeout(
            lambda: t.history(period="2y", interval="1d", auto_adjust=False),
            _HISTORY_FETCH_TIMEOUT, None,
        )
        if df is not None and not df.empty:
            df = df.reset_index()
            date_col = "Date" if "Date" in df.columns else "Datetime"
            df = df.rename(columns={date_col: "Date"})
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
            source = "yfinance"
        else:
            df = None
    except Exception:
        df = None

    # Fallback 1: Yahoo direct chart API
    if df is None or df.empty:
        df = _fetch_yahoo_chart(ticker, "1d", "2y")
        if df is not None and not df.empty:
            source = "yahoo_chart"

    # Fallback 2: Stooq
    if df is None or df.empty:
        df = _fetch_stooq_history(ticker, "d")
        if df is not None:
            df = _filter_period(df, "2y")
            source = "stooq"

    if df is None or df.empty:
        return None

    _stamp_source(df, source)
    _cache_set(cache_key, df)
    return df


def _stamp_source(df, source):
    """Marca en df.attrs la FUENTE que sirvió los datos y la fecha del último dato, para
    poder avisar al usuario de fallbacks silenciosos (#7). No invasivo: quien no lo mire,
    lo ignora."""
    if df is None or getattr(df, "empty", True):
        return df
    try:
        df.attrs["source"] = source or "desconocida"
        df.attrs["as_of"] = pd.to_datetime(df["Date"].iloc[-1]).isoformat()
    except Exception:
        pass
    return df


def data_health(df) -> Optional[dict]:
    """Salud de los datos de un DataFrame de mercado: {source, as_of, degraded, note}.
    Marca 'degraded' cuando la fuente es de RESPALDO (Stooq: diario, sin volumen, ajuste
    distinto) o cuando el último dato es demasiado viejo (fallback silencioso o mercado
    caído). Sirve para avisar de forma discreta en la UI y modular la confianza del análisis."""
    if df is None or getattr(df, "empty", True):
        return {"source": None, "as_of": None, "degraded": True, "note": "sin datos"}
    attrs = getattr(df, "attrs", {}) or {}
    src = attrs.get("source")
    as_of = attrs.get("as_of")
    degraded = False
    notes = []
    if src == "stooq":
        degraded = True
        notes.append("fuente de respaldo (Stooq): diario, sin volumen y ajuste distinto")
    try:
        last = pd.to_datetime(df["Date"].iloc[-1])
        age = (datetime.now() - last.to_pydatetime()).days
        if age is not None and age > 4:  # > fin de semana largo → datos con retraso
            degraded = True
            notes.append(f"último dato de hace {age} días")
    except Exception:
        pass
    return {"source": src, "as_of": as_of, "degraded": degraded, "note": " · ".join(notes) or None}


def get_quote_fast(ticker: str) -> Optional[dict]:
    """Precio SOLO de Finnhub, sin tocar yfinance `.info` (lo más lento).

    Para listados (watchlist, populares, screener), el worker de señales y el
    websocket — todos solo necesitan el precio en vivo, no los fundamentales.
    Devuelve None si Finnhub no responde (el caller puede caer a get_quote)."""
    d = _try_finnhub_quote(ticker)
    if not d or d.get("current") is None:
        return None
    last_price = d.get("current")
    prev_close = d.get("previous_close")
    change = change_pct = None
    if prev_close:
        change = float(last_price) - float(prev_close)
        change_pct = (change / float(prev_close)) * 100
    return {
        "symbol": ticker.upper(),
        "name": ticker.upper(),
        "price": round(float(last_price), 2),
        "previous_close": _r(prev_close),
        "open": _r(d.get("open")),
        "day_high": _r(d.get("high")),
        "day_low": _r(d.get("low")),
        "change": _r(change),
        "change_percent": _r(change_pct),
    }


def get_quote(ticker: str) -> Optional[dict]:
    """Fast quote. Finnhub PRIMARIO (reliable, no IP-block, has API key), yfinance fallback."""
    finnhub_data = _try_finnhub_quote(ticker)

    # Si Finnhub funciona, devolvemos un quote rápido sin esperar a yfinance.
    # Intentamos enriquecer con fundamentales/info pero con timeout corto.
    info: dict = {}
    fast: dict = {}
    if finnhub_data:
        # Best-effort fundamentals from yfinance (puede fallar en cloud, no es bloqueante).
        # .info va cacheado 1h (es lo más caro de yfinance).
        try:
            t = _ticker(ticker)
            try:
                fast = t.fast_info  # type: ignore[assignment]
            except Exception:
                fast = {}
            info = _get_info_cached(ticker, t)
        except Exception:
            info = {}
            fast = {}

        last_price = finnhub_data.get("current")
        prev_close = finnhub_data.get("previous_close")
        open_price = finnhub_data.get("open")
        day_high = finnhub_data.get("high")
        day_low = finnhub_data.get("low")
        volume = _g(fast, "last_volume") or info.get("volume")
        market_cap = _g(fast, "market_cap") or info.get("marketCap")
    else:
        # Fallback completo a yfinance
        try:
            t = _ticker(ticker)
            try:
                fast = t.fast_info  # type: ignore[assignment]
            except Exception:
                fast = {}
            info = _get_info_cached(ticker, t)
        except Exception:
            return None

        last_price = _g(fast, "last_price") or info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = _g(fast, "previous_close") or info.get("previousClose")
        open_price = _g(fast, "open") or info.get("open")
        day_high = _g(fast, "day_high") or info.get("dayHigh")
        day_low = _g(fast, "day_low") or info.get("dayLow")
        volume = _g(fast, "last_volume") or info.get("volume")
        market_cap = _g(fast, "market_cap") or info.get("marketCap")

    if last_price is None:
        return None

    change = None
    change_pct = None
    if prev_close:
        change = float(last_price) - float(prev_close)
        change_pct = (change / float(prev_close)) * 100

    # Dividend yield: yfinance is inconsistent (decimal 0.0109 vs percent 1.09 across
    # versions). Prefer dividendRate/price (unambiguous); else normalize to a decimal.
    raw_dy = info.get("dividendYield")
    div_rate = info.get("dividendRate")
    if div_rate and last_price:
        dividend_yield = round(div_rate / float(last_price), 4)
    elif raw_dy is not None:
        dividend_yield = round(raw_dy / 100, 4) if raw_dy > 1 else round(raw_dy, 4)
    else:
        dividend_yield = None

    return {
        "symbol": ticker.upper(),
        "name": info.get("longName") or info.get("shortName") or ticker.upper(),
        "price": round(float(last_price), 2),
        "previous_close": _r(prev_close),
        "open": _r(open_price),
        "day_high": _r(day_high),
        "day_low": _r(day_low),
        "volume": int(volume) if volume else None,
        "change": _r(change),
        "change_percent": _r(change_pct),
        "market_cap": int(market_cap) if market_cap else None,
        "currency": _g(fast, "currency") or info.get("currency") or "USD",
        "exchange": info.get("exchange"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "pe_ratio": _r(info.get("trailingPE")),
        "forward_pe": _r(info.get("forwardPE")),
        "eps": _r(info.get("trailingEps")),
        "dividend_yield": dividend_yield,
        "beta": _r(info.get("beta")),
        "high_52w": _r(info.get("fiftyTwoWeekHigh")),
        "low_52w": _r(info.get("fiftyTwoWeekLow")),
        "avg_volume": info.get("averageVolume"),
        "description": (info.get("longBusinessSummary") or "")[:600],
    }


def get_index_quote(symbol: str):
    """Lightweight quote for indices/futures (e.g. ES=F) via yfinance fast_info —
    bypasses the Finnhub path, which doesn't cover futures. Futures trade ~24h, so
    this works before the equity pre-market opens."""
    try:
        t = _ticker(symbol)
        try:
            fast = t.fast_info
        except Exception:
            fast = {}
        last = _g(fast, "last_price")
        prev = _g(fast, "previous_close")
        if last is None:
            try:
                info = t.info or {}
            except Exception:
                info = {}
            last = info.get("regularMarketPrice")
            prev = prev or info.get("previousClose")
        if last is None:
            return None
        change_pct = None
        if prev:
            change_pct = (float(last) - float(prev)) / float(prev) * 100
        return {
            "price": round(float(last), 2),
            "change_percent": round(change_pct, 2) if change_pct is not None else None,
        }
    except Exception:
        return None


def get_extended_quote(symbol: str):
    """Pre-market / after-hours quote using prepost 1-minute candles (yfinance .info
    no longer exposes preMarketPrice/marketState reliably). Returns
    {market_state, extended_price, regular_close} or None."""
    from datetime import time as _t
    try:
        t = _ticker(symbol)
        # yfinance .history NO respeta timeouts y en cloud (Yahoo bloquea) puede colgarse
        # indefinidamente, congelando el worker de señales. Tope duro vía el pool.
        df = _call_with_timeout(
            lambda: t.history(period="2d", interval="1m", prepost=True),
            _HISTORY_FETCH_TIMEOUT,
            None,
        )
        if df is None or df.empty:
            return None
        try:
            if df.index.tz is None:
                df = df.tz_localize("UTC").tz_convert("America/New_York")
            else:
                df = df.tz_convert("America/New_York")
        except Exception:
            pass
        last_price = float(df["Close"].iloc[-1])
        last_time = df.index[-1].time()
        if _t(4, 0) <= last_time < _t(9, 30):
            state = "PRE"
        elif _t(9, 30) <= last_time < _t(16, 0):
            state = "REGULAR"
        elif _t(16, 0) <= last_time < _t(20, 0):
            state = "POST"
        else:
            state = "CLOSED"
        regular_close = None
        try:
            reg = df.between_time("09:30", "16:00")
            if not reg.empty:
                regular_close = round(float(reg["Close"].iloc[-1]), 2)
        except Exception:
            pass
        return {
            "market_state": state,
            "extended_price": round(last_price, 2),
            "regular_close": regular_close,
        }
    except Exception:
        return None


# Cache para quotes de Finnhub: TTL corto para alertas rápidas.
# Con TTL=8s y bg_cap=40 calls/min el rate limiter cadencia ~1.5s/símbolo;
# precios nunca tienen más de 8s de antigüedad → alertas en 1-2 ciclos (~20-40s).
_fh_quote_cache: dict = {}
_fh_quote_lock = threading.Lock()
_FH_QUOTE_TTL = 8  # segundos


def _try_finnhub_quote(ticker: str):
    """Get a quote from Finnhub. Thread-safe rate-limited, cached 60s."""
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return None
    sym = ticker.upper()
    with _fh_quote_lock:
        entry = _fh_quote_cache.get(sym)
        if entry and (time.time() - entry["ts"]) < _FH_QUOTE_TTL:
            return entry["data"]
    # Espera acotada: si el limitador está saturado (normalmente por el vigilante de la
    # Cartera consumiendo el cupo de fondo), no bloqueamos. Devolvemos None y get_quote cae
    # a yfinance, que no pasa por este limitador. Antes esto se comía los 8s de margen del
    # dashboard y la página decía que el símbolo no existía.
    _espera = 8.0 if _finnhub_bg_ctx.get() else 2.5
    if not _finnhub_limiter.acquire(max_wait=_espera):
        return None
    try:
        r = _http.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker.upper(), "token": key},
            timeout=8,
        )
        if r.status_code == 429:
            # Esperamos 5 segundos y reintentamos una vez
            time.sleep(5)
            r = _http.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": ticker.upper(), "token": key},
                timeout=8,
            )
        if r.status_code != 200:
            return None
        d = r.json() or {}
        if not d.get("c"):
            return None
        result = {
            "current": d.get("c"),
            "high": d.get("h"),
            "low": d.get("l"),
            "open": d.get("o"),
            "previous_close": d.get("pc"),
        }
        with _fh_quote_lock:
            _fh_quote_cache[sym] = {"data": result, "ts": time.time()}
            _evict_bounded(_fh_quote_cache, 500)
        return result
    except Exception:
        return None


def get_news(ticker: str, limit: int = 8):
    # 1) Noticias ESPECÍFICAS de la empresa vía Finnhub (capturan catalizadores
    #    propios —fichajes, salidas, demandas, lanzamientos— que yfinance suele
    #    perder y que son justo los que explican movimientos sin causa macro).
    #    Import perezoso para evitar el ciclo external_data ↔ market_data.
    # Las tres fuentes son independientes → se lanzan EN PARALELO para no sumar
    # latencias en serie (antes Finnhub + FMP + yfinance se encadenaban y hacían
    # lenta la carga al cambiar de ticker, cuando no hay caché todavía).
    def _finnhub_news():
        try:
            import external_data
            return external_data.finnhub_company_news(ticker) or []
        except Exception:
            return []

    def _fmp_news():
        try:
            import external_data
            # FMP complementa a Finnhub: suele traer el cuerpo del artículo (campo `text`)
            # con el catalizador concreto que el titular generaliza.
            return external_data.fmp_company_news(ticker) or []
        except Exception:
            return []

    t = _ticker(ticker)
    def _yf_news():
        return _call_with_timeout(lambda: t.news or [], _NEWS_FETCH_TIMEOUT, [])

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_company = ex.submit(_finnhub_news)
        f_fmp = ex.submit(_fmp_news)
        f_yf = ex.submit(_yf_news)
        company = f_company.result()
        fmp = f_fmp.result()
        items = f_yf.result()

    yf_out = []
    for n in (items or []):
        content = n.get("content") or n
        title = content.get("title") or n.get("title")
        url = (content.get("canonicalUrl") or {}).get("url") or n.get("link") or content.get("clickThroughUrl", {}).get("url")
        publisher = content.get("provider", {}).get("displayName") if isinstance(content.get("provider"), dict) else n.get("publisher")
        pub_date = content.get("pubDate") or n.get("providerPublishTime")
        if not title:
            continue
        yf_out.append({
            "title": title,
            "url": url,
            "publisher": publisher,
            "published": pub_date,
        })

    # Mezcla deduplicando por título normalizado. Etiquetamos la fuente: Finnhub y FMP
    # son ESPECÍFICAS de empresa (capturan el catalizador real —una salida, una demanda);
    # yfinance suele traer macro/sector. Marcamos cada origen para poder priorizar.
    seen = set()
    merged = []
    for src, lst in (("company", company), ("company", fmp), ("macro", yf_out)):
        for n in lst:
            key = (n.get("title") or "").strip().lower()[:80]
            if not key or key in seen:
                continue
            seen.add(key)
            n = {**n, "_src": src}
            merged.append(n)

    def _epoch(n):
        p = n.get("published")
        if p is None:
            return 0
        if isinstance(p, (int, float)):
            return float(p)
        try:
            from datetime import datetime
            return datetime.fromisoformat(str(p).replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0

    # Orden compuesto: las noticias de EMPRESA van primero (su catalizador explica el
    # movimiento mucho mejor que una macro genérica), y dentro de cada grupo, lo más
    # reciente arriba. Así una salida/fichaje de ayer NO queda sepultado bajo titulares
    # macro de hoy — que era justo por lo que el modelo generalizaba ("éxodo de talento"
    # en vez de nombrar el hecho concreto).
    merged.sort(key=lambda n: (0 if n.get("_src") == "company" else 1, -_epoch(n)))
    return merged[:limit]


def df_to_candles(df: pd.DataFrame):
    """Convert OHLC dataframe to list of dicts for the frontend chart.

    Vectorizado con zip sobre arrays de columna (mucho más rápido que iterrows,
    que crea una Series por fila)."""
    if df is None or df.empty:
        return []
    dates = df["Date"]
    o = df["Open"].astype(float).round(2)
    h = df["High"].astype(float).round(2)
    low = df["Low"].astype(float).round(2)
    c = df["Close"].astype(float).round(2)
    v = df["Volume"].fillna(0).astype("int64")
    return [
        {
            "date": dt.isoformat(),
            "open": oo,
            "high": hh,
            "low": ll,
            "close": cc,
            "volume": int(vv),
        }
        for dt, oo, hh, ll, cc, vv in zip(dates, o, h, low, c, v)
    ]


def _g(obj, key):
    try:
        return obj[key]
    except Exception:
        try:
            return getattr(obj, key)
        except Exception:
            return None


def _r(v):
    try:
        if v is None:
            return None
        return round(float(v), 2)
    except Exception:
        return None


# Expose limiter to other modules (external_data.py) so they share quota
def get_finnhub_limiter():
    return _finnhub_limiter


# Expose the pooled HTTP session so other modules reuse connections (keep-alive)
def get_http_session():
    return _http
