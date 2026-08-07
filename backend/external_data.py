"""Finnhub & Alpha Vantage helpers — analyst recommendations, price targets, sentiment news."""
import logging
import os
import threading
import time
from typing import Optional

import requests as _requests

import market_data as _md

_log = logging.getLogger("inveria.external_data")

FINNHUB_BASE = "https://finnhub.io/api/v1"
ALPHA_BASE = "https://www.alphavantage.co/query"
FMP_BASE = "https://financialmodelingprep.com"

# Caché en módulo para datos que cambian pocas veces al día. Compartido entre todas
# las llamadas (dashboard, opportunities scanner, analyze) → drástica reducción de
# llamadas Finnhub repetidas para el mismo símbolo.
_ext_cache: dict = {}
_ext_lock = threading.Lock()


def _ext_cache_get(key: str, ttl: int):
    with _ext_lock:
        e = _ext_cache.get(key)
        if e and (time.time() - e["ts"]) < ttl:
            return e["val"], True
    return None, False


def _ext_cache_set(key: str, val):
    with _ext_lock:
        _ext_cache[key] = {"val": val, "ts": time.time()}
        # Bound memory: evict oldest entries (FIFO) past the cap on the free tier.
        while len(_ext_cache) > 500:
            _ext_cache.pop(next(iter(_ext_cache)), None)


# Caché de FALLOS. Sin esto, un símbolo que Finnhub no cubre (o que devuelve 429) paga la
# latencia completa —limitador + red— en CADA carga, para siempre, y encima gasta cuota que
# le hace falta a los símbolos que sí funcionan. 5 minutos: corto para que un fallo pasajero
# se reintente pronto, largo para que no duela en un rato de navegación.
_TTL_FALLO = 300


def _marcar_fallo(key: str):
    _ext_cache_set(f"neg:{key}", True)


def _fallo_reciente(key: str) -> bool:
    _, hit = _ext_cache_get(f"neg:{key}", _TTL_FALLO)
    return hit


def _finnhub_key():
    return os.environ.get("FINNHUB_API_KEY")


#: Espera máxima por un hueco del limitador. Sin tope, acquire() puede bloquear hasta 60s
#: dentro de una petición del usuario.
_ESPERA_LIMITADOR = float(os.environ.get("FINNHUB_WAIT", 2.5))


def _finnhub_get(path: str, params: dict, timeout: int = 10):
    """Wrapper que respeta el limitador compartido de Finnhub.

    Dos cosas aprendidas midiendo (ver market_data._try_finnhub_quote, mismo caso):

    1. La espera por el limitador va ACOTADA. Sin tope bloquea hasta 60s dentro de una
       petición que alguien está esperando en pantalla.
    2. Ante un 429 NO se duerme ni se reintenta. Aquí había un `time.sleep(5)`, que es lo
       que hacía que la cotización tardara 6,6 s en fallar. Dormir en el camino de una
       petición bloquea un hilo y retrasa la pantalla, y el reintento gasta OTRA llamada de
       la cuota que acaba de agotarse. Se devuelve la respuesta 429 tal cual y cada llamador
       decide (todos degradan a "sin datos", que es lo correcto).
    """
    http = _md.get_http_session()
    if not _md.get_finnhub_limiter().acquire(max_wait=_ESPERA_LIMITADOR):
        # Sin hueco: devolvemos una respuesta sintética de "demasiadas peticiones" para que
        # el llamador degrade igual que ante un 429 real, sin tener que distinguir el caso.
        r = _requests.Response()
        r.status_code = 429
        return r
    r = http.get(f"{FINNHUB_BASE}{path}", params=params, timeout=timeout)
    if r.status_code == 429:
        _log.warning("Finnhub 429 en %s — se degrada sin esperar", path)
    return r


def _alpha_key():
    return os.environ.get("ALPHA_VANTAGE_API_KEY")


def finnhub_recommendation_trends(symbol: str):
    """Aggregated analyst recs by month (last 4 months). Cached 4h."""
    sym = symbol.upper()
    cached, hit = _ext_cache_get(f"trends:{sym}", 14400)
    if hit:
        return cached
    if _fallo_reciente(f"trends:{sym}"):
        return None
    key = _finnhub_key()
    if not key:
        return None
    try:
        r = _finnhub_get("/stock/recommendation", {"symbol": sym, "token": key})
        if r.status_code != 200:
            _marcar_fallo(f"trends:{sym}")
            return None
        data = (r.json() or [])[:4]
        _ext_cache_set(f"trends:{sym}", data)
        return data
    except Exception:
        return None


def finnhub_company_news(symbol: str, days: int = 7, limit: int = 10):
    """Company-SPECIFIC news (last `days` days) from Finnhub's /company-news.
    Mucho mejor que yfinance para capturar catalizadores propios de la empresa
    (fichajes/salidas, lanzamientos, demandas, guidance) que mueven el precio sin
    ser ruido macro. Cacheado 30 min. Devuelve [] si no hay clave o falla."""
    from datetime import datetime, timedelta
    sym = symbol.upper()
    cached, hit = _ext_cache_get(f"company_news:{sym}", 1800)
    if hit:
        return cached
    key = _finnhub_key()
    if not key:
        return []
    try:
        today = datetime.utcnow().date()
        frm = (today - timedelta(days=days)).isoformat()
        r = _finnhub_get("/company-news", {
            "symbol": sym, "from": frm, "to": today.isoformat(), "token": key,
        })
        if r.status_code != 200:
            return []
        items = r.json() or []
        out = []
        for n in items[:limit]:
            title = n.get("headline")
            if not title:
                continue
            out.append({
                "title": title,
                # El resumen suele nombrar el catalizador concreto (p. ej. "John Jumper
                # deja DeepMind por Anthropic") que el titular generaliza ("AI talent
                # exodus"). Lo pasamos al modelo para que cite el hecho exacto, no algo vago.
                "summary": n.get("summary"),
                "url": n.get("url"),
                "publisher": n.get("source"),
                "published": n.get("datetime"),  # epoch seconds
            })
        _ext_cache_set(f"company_news:{sym}", out)
        return out
    except Exception:
        return []


def finnhub_general_news(limit: int = 25):
    """Noticias GENERALES de mercado (Finnhub /news?category=general). Para alimentar
    el cerebro/Radar con catalizadores del día. Cacheado 30 min. [] si no hay clave."""
    cached, hit = _ext_cache_get("general_news", 1800)
    if hit:
        return cached
    key = _finnhub_key()
    if not key:
        return []
    try:
        r = _finnhub_get("/news", {"category": "general", "token": key})
        if r.status_code != 200:
            return []
        out = []
        for n in (r.json() or [])[:limit]:
            title = n.get("headline")
            if not title:
                continue
            out.append({
                "title": title, "summary": n.get("summary"),
                "url": n.get("url"), "publisher": n.get("source"),
                "published": n.get("datetime"),
            })
        _ext_cache_set("general_news", out)
        return out
    except Exception:
        return []


def _fmp_key():
    return os.environ.get("FMP_API_KEY")


def fmp_stock_screener(
    market_cap_more_than: int = 2_000_000_000,
    price_more_than: float = 9,
    volume_more_than: int = 300_000,
    limit: int = 250,
    exchanges: str = "NASDAQ,NYSE",
):
    """Candidatos de TODO el mercado US vía el stock-screener de FMP, pre-filtrados por
    fundamentales BARATOS en UNA sola llamada (market cap, precio, volumen, exchange).
    Es la fuente de descubrimiento: en vez de una lista fija, deja que cualquier empresa
    del mercado entre si cumple el mínimo de calidad. El cribado fino (crecimiento,
    valoración, técnico) lo hace después el motor de scoring sobre estos finalistas.
    Cacheado 6h (el universo cambia poco intradía). Devuelve [] si no hay clave o falla."""
    cached, hit = _ext_cache_get("fmp_screener_universe", 21600)
    if hit:
        return cached
    key = _fmp_key()
    if not key:
        return []
    try:
        http = _md.get_http_session()
        r = http.get(
            f"{FMP_BASE}/api/v3/stock-screener",
            params={
                "marketCapMoreThan": market_cap_more_than,
                "priceMoreThan": price_more_than,
                "volumeMoreThan": volume_more_than,
                "isActivelyTrading": "true",
                "isEtf": "false",
                "isFund": "false",
                "exchange": exchanges,
                "limit": limit,
                "apikey": key,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return []
        items = r.json() or []
        out = []
        for n in items:
            sym = n.get("symbol")
            if not sym or "." in sym or "-" in sym:  # descarta clases raras / preferentes
                continue
            out.append(sym.upper())
        _ext_cache_set("fmp_screener_universe", out)
        return out
    except Exception:
        return []


def fmp_market_movers(kind: str = "actives", limit: int = 30):
    """Movimientos del día (kind: 'actives' | 'gainers' | 'losers') vía FMP. Capturan
    empresas que se mueven HOY y que quizá no estén en ninguna lista curada — justo el
    tipo de descubrimiento oportuno para el corto plazo. Cacheado 15 min. [] si falla."""
    endpoint = {
        "actives": "/api/v3/stock_market/actives",
        "gainers": "/api/v3/stock_market/gainers",
        "losers": "/api/v3/stock_market/losers",
    }.get(kind, "/api/v3/stock_market/actives")
    cached, hit = _ext_cache_get(f"fmp_movers:{kind}", 900)
    if hit:
        return cached
    key = _fmp_key()
    if not key:
        return []
    try:
        http = _md.get_http_session()
        r = http.get(f"{FMP_BASE}{endpoint}", params={"apikey": key}, timeout=8)
        if r.status_code != 200:
            return []
        items = r.json() or []
        out = []
        for n in items[:limit]:
            sym = n.get("symbol")
            if not sym or "." in sym or "-" in sym:
                continue
            out.append(sym.upper())
        _ext_cache_set(f"fmp_movers:{kind}", out)
        return out
    except Exception:
        return []


def fmp_company_profile(symbol: str):
    """Perfil de la empresa vía FMP: descripción del negocio, sector, industria, CEO,
    país, web. Sirve para que el análisis explique QUÉ HACE la empresa y QUÉ PRODUCTO
    ofrece con datos reales (no alucinados). Cacheado 24h (casi nunca cambia). None si falla."""
    sym = symbol.upper()
    cached, hit = _ext_cache_get(f"fmp_profile:{sym}", 86400)
    if hit:
        return cached
    key = _fmp_key()
    if not key:
        return None
    try:
        http = _md.get_http_session()
        r = http.get(f"{FMP_BASE}/api/v3/profile/{sym}", params={"apikey": key}, timeout=8)
        if r.status_code != 200:
            return None
        items = r.json() or []
        if not items:
            return None
        p = items[0]
        out = {
            "descripcion": p.get("description"),
            "sector": p.get("sector"),
            "industria": p.get("industry"),
            "ceo": p.get("ceo"),
            "pais": p.get("country"),
            "web": p.get("website"),
            "empleados": p.get("fullTimeEmployees"),
        }
        _ext_cache_set(f"fmp_profile:{sym}", out)
        return out
    except Exception:
        return None


def fmp_company_news(symbol: str, limit: int = 15):
    """Company-SPECIFIC news from Financial Modeling Prep (stock_news endpoint).
    Complementa a Finnhub: FMP suele traer un campo `text` con el cuerpo del
    artículo, donde aparece el catalizador concreto (persona, cifra, producto)
    que el titular generaliza. Cacheado 30 min. Devuelve [] si no hay clave o falla."""
    from datetime import datetime, timezone
    sym = symbol.upper()
    cached, hit = _ext_cache_get(f"fmp_news:{sym}", 1800)
    if hit:
        return cached
    key = _fmp_key()
    if not key:
        return []
    try:
        http = _md.get_http_session()
        r = http.get(
            f"{FMP_BASE}/api/v3/stock_news",
            params={"tickers": sym, "limit": limit, "apikey": key},
            timeout=4,
        )
        if r.status_code != 200:
            return []
        items = r.json() or []
        out = []
        for n in items[:limit]:
            title = n.get("title")
            if not title:
                continue
            # FMP da fecha ISO "YYYY-MM-DD HH:MM:SS" (UTC); la pasamos a epoch.
            published = None
            raw = n.get("publishedDate")
            if raw:
                try:
                    published = datetime.fromisoformat(
                        str(raw).replace("Z", "+00:00")
                    ).replace(tzinfo=timezone.utc).timestamp()
                except Exception:
                    published = None
            out.append({
                "title": title,
                "summary": n.get("text"),
                "url": n.get("url"),
                "publisher": n.get("site"),
                "published": published,
            })
        _ext_cache_set(f"fmp_news:{sym}", out)
        return out
    except Exception:
        return []


def finnhub_price_target(symbol: str):
    """Analyst consensus price targets. Cached 4h."""
    sym = symbol.upper()
    cached, hit = _ext_cache_get(f"price_target:{sym}", 14400)
    if hit:
        return cached
    if _fallo_reciente(f"price_target:{sym}"):
        return None
    key = _finnhub_key()
    if not key:
        return None
    try:
        r = _finnhub_get("/stock/price-target", {"symbol": symbol.upper(), "token": key})
        if r.status_code != 200:
            _marcar_fallo(f"price_target:{sym}")
            return None
        d = r.json() or {}
        if not d.get("targetMean"):
            _marcar_fallo(f"price_target:{sym}")
            return None
        result = {
            "target_mean": d.get("targetMean"),
            "target_high": d.get("targetHigh"),
            "target_low": d.get("targetLow"),
            "target_median": d.get("targetMedian"),
            "analysts_count": d.get("numberOfAnalysts"),
            "last_updated": d.get("lastUpdated"),
        }
        _ext_cache_set(f"price_target:{sym}", result)
        return result
    except Exception:
        return None


def finnhub_insider_transactions(symbol: str, months: int = 6):
    """Recent insider (officer/director) buy/sell transactions.
    A net-buying pattern by executives is one of the strongest bullish signals.
    Returns None if unavailable on the current plan."""
    from datetime import datetime, timedelta
    key = _finnhub_key()
    if not key:
        return None
    try:
        frm = (datetime.utcnow().date() - timedelta(days=months * 30)).isoformat()
        to = datetime.utcnow().date().isoformat()
        r = _finnhub_get(
            "/stock/insider-transactions",
            {"symbol": symbol.upper(), "from": frm, "to": to, "token": key},
        )
        if r.status_code != 200:
            return None
        rows = (r.json() or {}).get("data") or []
        if not rows:
            return None
        # change > 0 = buy (acquisition), change < 0 = sell (disposal)
        buys = sum(1 for x in rows if (x.get("change") or 0) > 0)
        sells = sum(1 for x in rows if (x.get("change") or 0) < 0)
        net_shares = sum((x.get("change") or 0) for x in rows)
        recent = sorted(rows, key=lambda x: x.get("transactionDate") or "", reverse=True)[:8]
        return {
            "buy_transactions": buys,
            "sell_transactions": sells,
            "net_shares": net_shares,
            "signal": (
                "COMPRA NETA (alcista)" if net_shares > 0
                else "VENTA NETA (bajista)" if net_shares < 0
                else "NEUTRAL"
            ),
            "recent": [
                {
                    "name": x.get("name"),
                    "date": x.get("transactionDate"),
                    "shares": x.get("change"),
                    "price": x.get("transactionPrice"),
                }
                for x in recent
            ],
        }
    except Exception:
        return None


def finnhub_earnings_surprises(symbol: str, quarters: int = 4):
    """Historical EPS actual vs estimate — shows if the company tends to beat/miss.
    Returns None if unavailable on the current plan."""
    key = _finnhub_key()
    if not key:
        return None
    try:
        r = _finnhub_get(
            "/stock/earnings",
            {"symbol": symbol.upper(), "limit": quarters, "token": key},
        )
        if r.status_code != 200:
            return None
        rows = r.json() or []
        if not rows or not isinstance(rows, list):
            return None
        out = []
        beats = 0
        for x in rows[:quarters]:
            actual = x.get("actual")
            estimate = x.get("estimate")
            surprise_pct = x.get("surprisePercent")
            if actual is not None and estimate is not None and actual >= estimate:
                beats += 1
            out.append({
                "period": x.get("period"),
                "actual": actual,
                "estimate": estimate,
                "surprise_percent": surprise_pct,
            })
        return {
            "quarters": out,
            "beats": beats,
            "total": len(out),
            "beat_rate": round(beats / len(out) * 100, 0) if out else 0,
        }
    except Exception:
        return None


def finnhub_basic_financials(symbol: str):
    """Fundamental metrics (P/E, EPS, beta, 52w range, dividend yield, avg volume) from
    Finnhub — used as a fallback when yfinance .info returns an incomplete quote.
    Returns a dict with only the fields that are available, or None."""
    key = _finnhub_key()
    if not key:
        return None
    try:
        r = _finnhub_get("/stock/metric", {"symbol": symbol.upper(), "metric": "all", "token": key})
        if r.status_code != 200:
            return None
        m = (r.json() or {}).get("metric") or {}
        if not m:
            return None
        dy = m.get("dividendYieldIndicatedAnnual") or m.get("currentDividendYieldTTM")
        avg_vol = m.get("3MonthAverageTradingVolume") or m.get("10DayAverageTradingVolume")
        out = {
            "pe_ratio": m.get("peTTM"),
            "eps": m.get("epsTTM") or m.get("epsInclExtraItemsTTM"),
            "beta": m.get("beta"),
            "high_52w": m.get("52WeekHigh"),
            "low_52w": m.get("52WeekLow"),
            # Finnhub gives yield as a percent (e.g. 1.09); store as decimal for the frontend
            "dividend_yield": round(dy / 100, 4) if dy else None,
            # Finnhub reports average volume in millions of shares
            "avg_volume": int(avg_vol * 1_000_000) if avg_vol else None,
            # Growth metrics (already in percent, e.g. 23.4 = 23.4%) — used by the screener.
            # Fall back across the fields Finnhub may populate on the free tier.
            "revenue_growth": (
                m.get("revenueGrowthTTMYoy")
                if m.get("revenueGrowthTTMYoy") is not None
                else m.get("revenueGrowthQuarterlyYoy")
                if m.get("revenueGrowthQuarterlyYoy") is not None
                else m.get("revenueGrowth3Y")
            ),
            "eps_growth": (
                m.get("epsGrowthTTMYoy")
                if m.get("epsGrowthTTMYoy") is not None
                else m.get("epsGrowthQuarterlyYoy")
                if m.get("epsGrowthQuarterlyYoy") is not None
                else m.get("epsGrowth3Y")
            ),
            # Momentum / tendencia (retorno de precio, ya en %) — para detectar "sectores
            # muertos" / value traps: una empresa que crece pero cuya acción lleva meses
            # cayendo NO es buena idea a corto/medio plazo.
            "return_13w": m.get("13WeekPriceReturnDaily"),
            "return_26w": m.get("26WeekPriceReturnDaily"),
            "return_52w": m.get("52WeekPriceReturnDaily"),
            # Fuerza relativa vs S&P500 a 52s: >0 bate al mercado, <0 lo hace peor
            # (síntoma de sector rezagado). Finnhub la reporta en %.
            "rel_strength_52w": m.get("priceRelativeToS&P50052Week"),
            # CALIDAD (factor con prima demostrada: empresas rentables y poco endeudadas
            # baten +2-3% anual). Margen neto (%), ROE (%) y deuda/patrimonio.
            "net_margin": m.get("netProfitMarginTTM") or m.get("netProfitMarginAnnual"),
            "roe": m.get("roeTTM") or m.get("roeRfy"),
            "debt_to_equity": m.get("totalDebt/totalEquityQuarterly") or m.get("totalDebt/totalEquityAnnual"),
        }
        return {k: v for k, v in out.items() if v is not None}
    except Exception:
        return None



def aggregate_recommendation(trends):
    """Aggregate finnhub trends into a single sentiment."""
    if not trends:
        return None
    latest = trends[0]
    total = sum([
        latest.get("strongBuy", 0),
        latest.get("buy", 0),
        latest.get("hold", 0),
        latest.get("sell", 0),
        latest.get("strongSell", 0),
    ])
    if total == 0:
        return None
    # weighted score 0-100
    score = (
        latest.get("strongBuy", 0) * 100
        + latest.get("buy", 0) * 75
        + latest.get("hold", 0) * 50
        + latest.get("sell", 0) * 25
        + latest.get("strongSell", 0) * 0
    ) / total
    if score >= 70:
        consensus = "COMPRAR"
    elif score >= 55:
        consensus = "COMPRAR MODERADO"
    elif score >= 45:
        consensus = "MANTENER"
    elif score >= 30:
        consensus = "VENDER MODERADO"
    else:
        consensus = "VENDER"
    return {
        "consensus": consensus,
        "score": round(score, 1),
        "period": latest.get("period"),
        "total_analysts": total,
        "breakdown": {
            "strong_buy": latest.get("strongBuy", 0),
            "buy": latest.get("buy", 0),
            "hold": latest.get("hold", 0),
            "sell": latest.get("sell", 0),
            "strong_sell": latest.get("strongSell", 0),
        },
        "trend_history": trends,
    }


def _fetch_earnings_for_symbol(sym: str, from_date: str, to_date: str, key: str):
    """Fetch earnings for a single symbol from Finnhub."""
    try:
        r = _finnhub_get(
            "/calendar/earnings",
            {"symbol": sym, "from": from_date, "to": to_date, "token": key},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        items = r.json().get("earningsCalendar") or []
        return [
            {
                "symbol": (it.get("symbol") or sym).upper(),
                "date": it.get("date"),
                "hour": it.get("hour"),
                "eps_estimate": it.get("epsEstimate"),
                "eps_actual": it.get("epsActual"),
                "revenue_estimate": it.get("revenueEstimate"),
                "revenue_actual": it.get("revenueActual"),
                "quarter": it.get("quarter"),
                "year": it.get("year"),
            }
            for it in items
        ]
    except Exception:
        return []


def finnhub_earnings_calendar(days: int = 14, symbols=None):
    """Upcoming earnings from Finnhub for next `days` days.

    Uses a SINGLE bulk Finnhub call (1 API slot) and filters client-side.
    Previously made 50 per-symbol calls that saturated the rate limiter.
    Falls back to per-symbol only if bulk returns nothing useful.
    """
    from datetime import datetime, timedelta
    from concurrent.futures import ThreadPoolExecutor, as_completed
    key = _finnhub_key()
    if not key:
        return None
    today = datetime.utcnow().date()
    to = today + timedelta(days=days)
    from_str, to_str = today.isoformat(), to.isoformat()

    sym_set = set(symbols) if symbols else None

    # Bulk call: 1 Finnhub API slot instead of N per-symbol calls.
    # Finnhub free tier returns all events in the range (up to a few hundred).
    try:
        r = _finnhub_get("/calendar/earnings", {"from": from_str, "to": to_str, "token": key}, timeout=15)
        if r.status_code != 200:
            return None
        items = r.json().get("earningsCalendar") or []
        out = []
        for it in items:
            sym = (it.get("symbol") or "").upper()
            if sym_set and sym not in sym_set:
                continue
            out.append({
                "symbol": sym,
                "date": it.get("date"),
                "hour": it.get("hour"),
                "eps_estimate": it.get("epsEstimate"),
                "eps_actual": it.get("epsActual"),
                "revenue_estimate": it.get("revenueEstimate"),
                "revenue_actual": it.get("revenueActual"),
                "quarter": it.get("quarter"),
                "year": it.get("year"),
            })
        out.sort(key=lambda x: x.get("date") or "")

        # Relleno por-símbolo de los que FALTEN en el lote (el masivo de Finnhub free se
        # trunca y deja fuera acciones como NFLX). Antes solo se rellenaba si no había
        # NINGUNA → las que faltaban no aparecían nunca. Ahora cada símbolo pedido que no
        # esté en el resultado se busca individualmente.
        if sym_set:
            encontrados = {x["symbol"] for x in out}
            faltan = [s for s in sym_set if s not in encontrados][:25]
            if faltan:
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = [ex.submit(_fetch_earnings_for_symbol, s, from_str, to_str, key)
                            for s in faltan]
                    for f in as_completed(futs):
                        try:
                            out.extend(f.result() or [])
                        except Exception:
                            pass
                out.sort(key=lambda x: x.get("date") or "")

        return {"items": out, "from": from_str, "to": to_str}
    except Exception:
        return None


_ALPHA_SENTIMENT_TTL = 6 * 3600  # 6h — Alpha Vantage free tier allows only 25 calls/day


def alpha_sentiment_news(symbol: str, limit: int = 6):
    """Alpha Vantage news sentiment. Cached 6h because the free tier only allows
    25 requests/day — without caching a handful of tickers exhausts the quota."""
    key = _alpha_key()
    if not key:
        return None
    cache_key = ("alpha_sentiment", symbol.upper(), limit)
    cached, hit = _ext_cache_get(cache_key, _ALPHA_SENTIMENT_TTL)
    if hit:
        return cached
    try:
        r = _md.get_http_session().get(
            ALPHA_BASE,
            params={
                "function": "NEWS_SENTIMENT",
                "tickers": symbol.upper(),
                "limit": limit,
                "apikey": key,
            },
            timeout=15,
        )
        if r.status_code != 200:
            return None
        d = r.json() or {}
        # Alpha Vantage may return rate-limit "Information" key with no feed.
        # Don't cache rate-limit responses — retry next time rather than caching empty.
        if d.get("Information") or d.get("Note"):
            return None
        feed = d.get("feed") or []
        out = []
        for item in feed[:limit]:
            ticker_sentiments = item.get("ticker_sentiment", [])
            ts = next(
                (t for t in ticker_sentiments if t.get("ticker") == symbol.upper()),
                None,
            )
            out.append({
                "title": item.get("title"),
                "url": item.get("url"),
                "source": item.get("source"),
                "time_published": item.get("time_published"),
                "summary": (item.get("summary") or "")[:240],
                "overall_sentiment": item.get("overall_sentiment_label"),
                "ticker_sentiment_score": float(ts.get("ticker_sentiment_score")) if ts and ts.get("ticker_sentiment_score") else None,
                "ticker_sentiment_label": ts.get("ticker_sentiment_label") if ts else None,
            })
        _ext_cache_set(cache_key, out)
        return out
    except Exception:
        return None
