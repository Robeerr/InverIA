"""Market data service.

Resiliente para entornos cloud (Render). Estrategia:
- Quotes: Finnhub PRIMARIO (no IP-blocked, API key del usuario), yfinance fallback.
- Historical OHLC: yfinance con curl_cffi (impersona Chrome) PRIMARIO,
  Stooq fallback (gratis, sin API key, sin rate limit).
- Caché en memoria para historial (reduce drásticamente llamadas externas).
- Rate limiter global para Finnhub (60 calls/min free tier).
"""
import asyncio
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

# Silence yfinance noisy 401 errors (we fall back to other sources anyway)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# curl_cffi impersonates a real browser to bypass Yahoo Finance anti-bot on cloud providers
try:
    from curl_cffi import requests as cffi_requests
    _yf_session = cffi_requests.Session(impersonate="chrome124")
except Exception:
    _yf_session = None


# ---------- Finnhub rate limiter ----------
# Free tier = 60 calls/minute. We stay safely below that.
class _FinnhubLimiter:
    def __init__(self, max_per_min: int = 50):
        self.max_per_min = max_per_min
        self.calls = []
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < 60]
            if len(self.calls) >= self.max_per_min:
                sleep_for = 60 - (now - self.calls[0]) + 0.05
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.time()
                self.calls = [t for t in self.calls if now - t < 60]
            self.calls.append(now)


_finnhub_limiter = _FinnhubLimiter(max_per_min=50)


def _ticker(symbol: str):
    """Return a yfinance Ticker using the browser-impersonating session when available."""
    if _yf_session is not None:
        try:
            return yf.Ticker(symbol, session=_yf_session)
        except Exception:
            pass
    return yf.Ticker(symbol)


PERIOD_MAP = {
    "5M": ("5d", "5m"),
    "15M": ("1mo", "15m"),
    "1H": ("3mo", "1h"),
    "1D": ("5d", "5m"),
    "1W": ("1mo", "30m"),
    "1M": ("3mo", "1d"),
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


def _cache_get(key: str):
    with _history_lock:
        entry = _history_cache.get(key)
        if entry and (time.time() - entry["ts"]) < _HISTORY_TTL_SECONDS:
            return entry["df"]
    return None


def _cache_set(key: str, df):
    with _history_lock:
        _history_cache[key] = {"df": df, "ts": time.time()}


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
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
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
        r = _yf_session.get(url, params=params, timeout=10)
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
    cache_key = f"hist:{ticker.upper()}:{timeframe}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Try yfinance high-level API first
    df = None
    try:
        t = _ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=False)
        if df is not None and not df.empty:
            df = df.reset_index()
            date_col = "Date" if "Date" in df.columns else "Datetime"
            df = df.rename(columns={date_col: "Date"})
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        else:
            df = None
    except Exception:
        df = None

    # Fallback 1: direct Yahoo chart API (survives some IP blocks via curl_cffi)
    if df is None or df.empty:
        df = _fetch_yahoo_chart(ticker, interval, period)

    # Fallback 2: Stooq (only daily-or-larger — no intraday support on free tier)
    if df is None or df.empty:
        stooq_interval = _STOOQ_INTERVALS.get(interval, "d")
        df = _fetch_stooq_history(ticker, stooq_interval)
        if df is not None:
            df = _filter_period(df, period)

    if df is None or df.empty:
        return None

    _cache_set(cache_key, df)
    return df


def get_full_indicator_history(ticker: str):
    """Fetch 2y daily data used for computing indicators reliably."""
    cache_key = f"ind:{ticker.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    df = None
    try:
        t = _ticker(ticker)
        df = t.history(period="2y", interval="1d", auto_adjust=False)
        if df is not None and not df.empty:
            df = df.reset_index()
            date_col = "Date" if "Date" in df.columns else "Datetime"
            df = df.rename(columns={date_col: "Date"})
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        else:
            df = None
    except Exception:
        df = None

    # Fallback 1: Yahoo direct chart API
    if df is None or df.empty:
        df = _fetch_yahoo_chart(ticker, "1d", "2y")

    # Fallback 2: Stooq
    if df is None or df.empty:
        df = _fetch_stooq_history(ticker, "d")
        if df is not None:
            df = _filter_period(df, "2y")

    if df is None or df.empty:
        return None

    _cache_set(cache_key, df)
    return df


def get_quote(ticker: str) -> Optional[dict]:
    """Fast quote. Finnhub PRIMARIO (reliable, no IP-block, has API key), yfinance fallback."""
    finnhub_data = _try_finnhub_quote(ticker)

    # Si Finnhub funciona, devolvemos un quote rápido sin esperar a yfinance.
    # Intentamos enriquecer con fundamentales/info pero con timeout corto.
    info: dict = {}
    fast: dict = {}
    if finnhub_data:
        # Best-effort fundamentals from yfinance (puede fallar en cloud, no es bloqueante)
        try:
            t = _ticker(ticker)
            try:
                fast = t.fast_info  # type: ignore[assignment]
            except Exception:
                fast = {}
            try:
                info = t.info or {}
            except Exception:
                info = {}
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
            try:
                info = t.info or {}
            except Exception:
                info = {}
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


def _try_finnhub_quote(ticker: str):
    """Get a quote from Finnhub. Thread-safe rate-limited."""
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return None
    _finnhub_limiter.acquire()
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker.upper(), "token": key},
            timeout=8,
        )
        if r.status_code == 429:
            # Esperamos 5 segundos y reintentamos una vez
            time.sleep(5)
            r = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": ticker.upper(), "token": key},
                timeout=8,
            )
        if r.status_code != 200:
            return None
        d = r.json() or {}
        if not d.get("c"):
            return None
        return {
            "current": d.get("c"),
            "high": d.get("h"),
            "low": d.get("l"),
            "open": d.get("o"),
            "previous_close": d.get("pc"),
        }
    except Exception:
        return None


def get_news(ticker: str, limit: int = 8):
    t = _ticker(ticker)
    try:
        items = t.news or []
    except Exception:
        return []
    out = []
    for n in items[:limit]:
        content = n.get("content") or n
        title = content.get("title") or n.get("title")
        url = (content.get("canonicalUrl") or {}).get("url") or n.get("link") or content.get("clickThroughUrl", {}).get("url")
        publisher = content.get("provider", {}).get("displayName") if isinstance(content.get("provider"), dict) else n.get("publisher")
        pub_date = content.get("pubDate") or n.get("providerPublishTime")
        if not title:
            continue
        out.append({
            "title": title,
            "url": url,
            "publisher": publisher,
            "published": pub_date,
        })
    return out


def df_to_candles(df: pd.DataFrame):
    """Convert OHLC dataframe to list of dicts for the frontend chart."""
    if df is None or df.empty:
        return []
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "date": r["Date"].isoformat(),
            "open": round(float(r["Open"]), 2),
            "high": round(float(r["High"]), 2),
            "low": round(float(r["Low"]), 2),
            "close": round(float(r["Close"]), 2),
            "volume": int(r["Volume"]) if not pd.isna(r["Volume"]) else 0,
        })
    return rows


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
