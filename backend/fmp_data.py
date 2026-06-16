"""Financial Modeling Prep integration — market movers (free tier, /stable API)."""
import os
import logging

import market_data as _md

logger = logging.getLogger("fmp_data")
BASE = "https://financialmodelingprep.com/stable"


def _key():
    return os.environ.get("FMP_API_KEY")


def _fetch(path: str):
    key = _key()
    if not key:
        return []
    try:
        r = _md.get_http_session().get(f"{BASE}/{path}", params={"apikey": key}, timeout=12)
        if r.status_code != 200:
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"FMP {path} error: {e}")
        return []


def _clean(rows, limit: int = 20, min_price: float = 5.0):
    """Normalize FMP mover rows, dropping penny/OTC names for relevance."""
    out = []
    for x in rows:
        try:
            price = float(x.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if price < min_price:
            continue
        ex = (x.get("exchange") or "").upper()
        # keep major US exchanges (or rows with no exchange info); drop OTC/PINK
        if ex and not any(m in ex for m in ("NASDAQ", "NYSE", "AMEX", "NMS", "NYQ")):
            continue
        out.append({
            "symbol": x.get("symbol"),
            "name": x.get("name"),
            "price": round(price, 2),
            "change": x.get("change"),
            "change_percent": x.get("changesPercentage"),
            "exchange": x.get("exchange"),
        })
        if len(out) >= limit:
            break
    return out


def get_market_movers():
    """Top gainers / losers / most-active US stocks. Empty if FMP_API_KEY missing."""
    return {
        "gainers": _clean(_fetch("biggest-gainers")),
        "losers": _clean(_fetch("biggest-losers")),
        "actives": _clean(_fetch("most-actives")),
    }
