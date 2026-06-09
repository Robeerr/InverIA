"""Finnhub & Alpha Vantage helpers — analyst recommendations, price targets, sentiment news."""
import os
import time
import requests
from typing import Optional

import market_data as _md

FINNHUB_BASE = "https://finnhub.io/api/v1"
ALPHA_BASE = "https://www.alphavantage.co/query"


def _finnhub_key():
    return os.environ.get("FINNHUB_API_KEY")


def _finnhub_get(path: str, params: dict, timeout: int = 10):
    """Wrapper that respects the shared Finnhub rate limiter (60/min free tier)."""
    _md.get_finnhub_limiter().acquire()
    r = requests.get(f"{FINNHUB_BASE}{path}", params=params, timeout=timeout)
    if r.status_code == 429:
        time.sleep(5)
        _md.get_finnhub_limiter().acquire()
        r = requests.get(f"{FINNHUB_BASE}{path}", params=params, timeout=timeout)
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
        r = requests.get(
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
