"""Polygon.io integration — Volume Profile analysis for key support/resistance levels."""
import os
import logging
import math
from datetime import date, timedelta
from typing import Optional

import market_data as _md

logger = logging.getLogger("polygon_data")

BASE_URL = "https://api.polygon.io"


def _api_key() -> Optional[str]:
    return os.environ.get("POLYGON_API_KEY")


def get_aggregate_bars(symbol: str, days: int = 365, timespan: str = "day") -> list[dict]:
    """Fetch OHLCV aggregate bars from Polygon.io."""
    key = _api_key()
    if not key:
        return []

    end = date.today()
    start = end - timedelta(days=days)

    url = f"{BASE_URL}/v2/aggs/ticker/{symbol}/range/1/{timespan}/{start}/{end}"
    try:
        resp = _md.get_http_session().get(url, params={"apiKey": key, "limit": 5000, "adjusted": "true"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results") or []
    except Exception as e:
        logger.warning(f"Polygon bars error for {symbol}: {e}")
        return []


def compute_volume_profile(bars: list[dict], bins: int = 40) -> dict:
    """
    Build a price-volume histogram and identify key levels:
    - POC  (Point of Control): price with highest traded volume
    - VAH  (Value Area High): upper bound of 70% volume zone
    - VAL  (Value Area Low): lower bound of 70% volume zone
    - HVN  (High Volume Nodes): strong support/resistance zones
    - LVN  (Low Volume Nodes): price passes through quickly (weak levels)
    """
    if not bars:
        return {}

    # Use typical price (H+L+C)/3 weighted by volume for each bar
    prices = [(b["h"] + b["l"] + b["c"]) / 3 for b in bars]
    volumes = [b.get("v", 0) for b in bars]

    low = min(b["l"] for b in bars)
    high = max(b["h"] for b in bars)
    if high <= low:
        return {}

    bin_size = (high - low) / bins
    histogram = [0.0] * bins

    for price, vol in zip(prices, volumes):
        idx = min(int((price - low) / bin_size), bins - 1)
        histogram[idx] += vol

    total_vol = sum(histogram)
    if total_vol == 0:
        return {}

    # POC — bin with max volume
    poc_idx = histogram.index(max(histogram))
    poc_price = round(low + (poc_idx + 0.5) * bin_size, 2)

    # Value Area — 70% of total volume centered around POC
    target = total_vol * 0.70
    accumulated = histogram[poc_idx]
    lo_idx = poc_idx
    hi_idx = poc_idx

    while accumulated < target and (lo_idx > 0 or hi_idx < bins - 1):
        can_go_lo = lo_idx > 0
        can_go_hi = hi_idx < bins - 1
        if can_go_lo and can_go_hi:
            if histogram[lo_idx - 1] >= histogram[hi_idx + 1]:
                lo_idx -= 1
                accumulated += histogram[lo_idx]
            else:
                hi_idx += 1
                accumulated += histogram[hi_idx]
        elif can_go_lo:
            lo_idx -= 1
            accumulated += histogram[lo_idx]
        else:
            hi_idx += 1
            accumulated += histogram[hi_idx]

    val = round(low + lo_idx * bin_size, 2)
    vah = round(low + (hi_idx + 1) * bin_size, 2)

    # High Volume Nodes — top 20% by volume (strong levels)
    threshold_hvn = sorted(histogram, reverse=True)[max(1, bins // 5)]
    hvn_prices = []
    for i, vol in enumerate(histogram):
        if vol >= threshold_hvn:
            hvn_prices.append(round(low + (i + 0.5) * bin_size, 2))

    # Low Volume Nodes — bottom 20% by volume (weak, price passes quickly)
    threshold_lvn = sorted(histogram)[max(1, bins // 5)]
    lvn_prices = []
    for i, vol in enumerate(histogram):
        if vol <= threshold_lvn and vol > 0:
            lvn_prices.append(round(low + (i + 0.5) * bin_size, 2))

    return {
        "poc": poc_price,
        "vah": vah,
        "val": val,
        "hvn": sorted(hvn_prices),
        "lvn": sorted(lvn_prices),
        "range": {"low": round(low, 2), "high": round(high, 2)},
        "bars_analyzed": len(bars),
    }


def get_volume_profile(symbol: str, days: int = 365) -> dict:
    """Main entry point: fetch bars and return volume profile."""
    bars = get_aggregate_bars(symbol, days=days)
    if not bars:
        return {}
    return compute_volume_profile(bars)
