"""Daily opportunities scanner — analyzes a universe of stocks and detects buy signals."""
import asyncio
from datetime import datetime, timezone, timedelta
import market_data
import indicators as ind
import external_data


UNIVERSE = [
    # Mega caps
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    # Large caps tech / growth
    "AMD", "AVGO", "ORCL", "CRM", "ADBE", "NFLX", "INTC", "QCOM",
    # Finance
    "JPM", "V", "MA",
    # Consumer
    "WMT", "COST", "MCD", "KO", "NKE", "DIS",
    # Health
    "JNJ", "UNH", "LLY",
    # ETFs
    "SPY", "QQQ", "IWM",
]


_cache = {"data": None, "ts": None}
_CACHE_TTL = timedelta(minutes=60)
_scan_lock = asyncio.Lock()


async def _analyze_one(symbol: str):
    try:
        quote = await asyncio.to_thread(market_data.get_quote, symbol)
        if not quote:
            return None
        df = await asyncio.to_thread(market_data.get_full_indicator_history, symbol)
        if df is None or df.empty:
            return None
        indicators_data = ind.compute_all(df)
        consensus_raw = await asyncio.to_thread(external_data.finnhub_recommendation_trends, symbol)
        consensus = external_data.aggregate_recommendation(consensus_raw)

        # Signals scoring
        signals = []
        score = 0
        rsi_val = indicators_data.get("rsi")
        change_pct = quote.get("change_percent") or 0
        macd = indicators_data.get("macd") or {}
        sma20 = (indicators_data.get("sma") or {}).get("20")
        sma50 = (indicators_data.get("sma") or {}).get("50")
        price = quote.get("price")
        low_52w = quote.get("low_52w")
        high_52w = quote.get("high_52w")

        category = None

        # 1) Oversold (RSI < 30)
        if rsi_val is not None and rsi_val < 32:
            signals.append(f"RSI sobrevendido ({rsi_val})")
            score += 30
            category = "OVERSOLD"

        # 2) Big intraday drop (potential dip-buy)
        if change_pct <= -3:
            signals.append(f"Caída fuerte hoy ({change_pct:.2f}%)")
            score += 25
            if not category:
                category = "DIP"

        # 3) Strong momentum (RSI > 60 with price above MA20)
        if rsi_val is not None and 55 <= rsi_val <= 70 and sma20 and price and price > sma20:
            signals.append("Momentum alcista sano")
            score += 15
            if not category:
                category = "MOMENTUM"

        # 4) Golden cross / above MA50
        if sma20 and sma50 and sma20 > sma50 and price and price > sma50:
            signals.append("Tendencia alcista (SMA20 > SMA50)")
            score += 10

        # 5) Near 52w low (potential reversal)
        if low_52w and price and low_52w > 0:
            ratio = (price - low_52w) / low_52w
            if ratio < 0.10:
                signals.append(f"Cerca de mínimo 52w (+{ratio*100:.1f}%)")
                score += 20
                if not category:
                    category = "VALUE"

        # 6) MACD histogram positive turn
        if macd.get("histogram") is not None and macd.get("histogram") > 0 and macd.get("macd") and macd.get("macd") > macd.get("signal", 0):
            signals.append("MACD bullish")
            score += 10

        # 7) Analyst consensus
        if consensus and consensus.get("score", 0) >= 65:
            signals.append(f"Consenso analistas: {consensus['consensus']} ({consensus['total_analysts']} analistas)")
            score += 15

        # 8) New 52w high (breakout)
        if high_52w and price and price >= high_52w * 0.98:
            signals.append("Cerca de máximos 52w (breakout)")
            score += 12
            if not category:
                category = "BREAKOUT"

        if score < 20:
            return None

        # Find nearest support and resistance for quick levels
        sr = indicators_data.get("support_resistance") or {}
        supports = sr.get("supports") or []
        resistances = sr.get("resistances") or []

        return {
            "symbol": symbol,
            "name": quote.get("name"),
            "price": quote.get("price"),
            "change_percent": quote.get("change_percent"),
            "rsi": rsi_val,
            "category": category or "GENERAL",
            "score": score,
            "signals": signals,
            "suggested_entry": price,
            "nearest_support": supports[0] if supports else None,
            "nearest_resistance": resistances[0] if resistances else None,
            "analyst_consensus": consensus["consensus"] if consensus else None,
            "analysts_count": consensus["total_analysts"] if consensus else None,
            "market_cap": quote.get("market_cap"),
            "sector": quote.get("sector"),
        }
    except Exception:
        return None


async def scan_daily_opportunities(force_refresh: bool = False):
    now = datetime.now(timezone.utc)
    if not force_refresh and _cache["data"] and _cache["ts"] and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["data"]

    # If a scan is already running, return the previous (possibly stale) cache
    # instead of queueing — keeps the HTTP request fast and avoids proxy timeouts.
    if _scan_lock.locked():
        if _cache["data"]:
            return _cache["data"]
        # No cache yet — return a "warming" placeholder so the client can retry.
        return {
            "generated_at": now.isoformat(),
            "universe_size": len(UNIVERSE),
            "opportunities_found": 0,
            "top": [],
            "by_category": {},
            "status": "warming",
        }

    async with _scan_lock:
        # Re-check after acquiring lock (another coroutine may have just finished)
        now = datetime.now(timezone.utc)
        if not force_refresh and _cache["data"] and _cache["ts"] and (now - _cache["ts"]) < _CACHE_TTL:
            return _cache["data"]

        # Run analyses with limited concurrency to respect Finnhub's 60 calls/min free tier.
        # Each symbol does ~2 Finnhub calls (quote + recommendation), so sem=3 keeps us
        # comfortably under the limit and the shared rate-limiter handles bursts.
        sem = asyncio.Semaphore(3)

        async def bounded(s):
            async with sem:
                return await _analyze_one(s)

        results = await asyncio.gather(*[bounded(s) for s in UNIVERSE])
        items = [r for r in results if r is not None]
        items.sort(key=lambda x: x["score"], reverse=True)

        # Group by category
        by_category = {}
        for it in items:
            by_category.setdefault(it["category"], []).append(it)

        data = {
            "generated_at": now.isoformat(),
            "universe_size": len(UNIVERSE),
            "opportunities_found": len(items),
            "top": items[:15],
            "by_category": by_category,
        }
        _cache["data"] = data
        _cache["ts"] = now
        return data
