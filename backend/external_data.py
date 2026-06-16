"""Finnhub & Alpha Vantage helpers — analyst recommendations, price targets, sentiment news."""
import os
import time
from typing import Optional

import market_data as _md

FINNHUB_BASE = "https://finnhub.io/api/v1"
ALPHA_BASE = "https://www.alphavantage.co/query"


def _finnhub_key():
    return os.environ.get("FINNHUB_API_KEY")


def _finnhub_get(path: str, params: dict, timeout: int = 10):
    """Wrapper that respects the shared Finnhub rate limiter (60/min free tier)."""
    http = _md.get_http_session()
    _md.get_finnhub_limiter().acquire()
    r = http.get(f"{FINNHUB_BASE}{path}", params=params, timeout=timeout)
    if r.status_code == 429:
        time.sleep(5)
        _md.get_finnhub_limiter().acquire()
        r = http.get(f"{FINNHUB_BASE}{path}", params=params, timeout=timeout)
    return r


def _alpha_key():
    return os.environ.get("ALPHA_VANTAGE_API_KEY")


def finnhub_recommendation_trends(symbol: str):
    """Aggregated analyst recs by month (last 4 months)."""
    key = _finnhub_key()
    if not key:
        return None
    try:
        r = _finnhub_get("/stock/recommendation", {"symbol": symbol.upper(), "token": key})
        if r.status_code != 200:
            return None
        data = r.json() or []
        return data[:4]  # last 4 months
    except Exception:
        return None


def finnhub_price_target(symbol: str):
    """Analyst consensus price targets."""
    key = _finnhub_key()
    if not key:
        return None
    try:
        r = _finnhub_get("/stock/price-target", {"symbol": symbol.upper(), "token": key})
        if r.status_code != 200:
            return None
        d = r.json() or {}
        if not d.get("targetMean"):
            return None
        return {
            "target_mean": d.get("targetMean"),
            "target_high": d.get("targetHigh"),
            "target_low": d.get("targetLow"),
            "target_median": d.get("targetMedian"),
            "analysts_count": d.get("numberOfAnalysts"),
            "last_updated": d.get("lastUpdated"),
        }
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
        }
        return {k: v for k, v in out.items() if v is not None}
    except Exception:
        return None


def finnhub_quote(symbol: str):
    """Real-time quote from Finnhub (current, prev close, day high/low, %)."""
    key = _finnhub_key()
    if not key:
        return None
    try:
        r = _finnhub_get("/quote", {"symbol": symbol.upper(), "token": key}, timeout=8)
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
            "change": d.get("d"),
            "change_percent": d.get("dp"),
        }
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
    When symbols list provided, fetches per-symbol to bypass free-tier pagination limit."""
    from datetime import datetime, timedelta
    from concurrent.futures import ThreadPoolExecutor, as_completed
    key = _finnhub_key()
    if not key:
        return None
    today = datetime.utcnow().date()
    to = today + timedelta(days=days)
    from_str, to_str = today.isoformat(), to.isoformat()

    if symbols:
        # Per-symbol requests in parallel — avoids free-tier result cap on bulk queries
        out = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(_fetch_earnings_for_symbol, sym, from_str, to_str, key): sym for sym in symbols}
            for future in as_completed(futures):
                out.extend(future.result())
        out.sort(key=lambda x: x.get("date") or "")
        return {"items": out, "from": from_str, "to": to_str}

    # No symbol filter — bulk request (may be capped by Finnhub free tier)
    try:
        r = _finnhub_get("/calendar/earnings", {"from": from_str, "to": to_str, "token": key}, timeout=15)
        if r.status_code != 200:
            return None
        items = r.json().get("earningsCalendar") or []
        out = [
            {
                "symbol": (it.get("symbol") or "").upper(),
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
        out.sort(key=lambda x: x.get("date") or "")
        return {"items": out, "from": from_str, "to": to_str}
    except Exception:
        return None


def alpha_sentiment_news(symbol: str, limit: int = 6):
    """Alpha Vantage news sentiment."""
    key = _alpha_key()
    if not key:
        return None
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
        # Alpha Vantage may return rate-limit "Information" key with no feed
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
        return out
    except Exception:
        return None
