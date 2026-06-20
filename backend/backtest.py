"""Walk-forward backtesting of the confluence buy-levels engine.

For each anchor date in the past we compute the support levels using ONLY the
data available up to that date (no lookahead), then look forward a fixed window
and measure whether price actually reached each level and whether it *held*
(bounced) or *broke*. Aggregating thousands of these point-in-time tests tells us,
empirically, how trustworthy each strength bucket is — turning "these levels look
good" into "levels with strength >=75 held 78% of the time".
"""
import logging
from typing import Optional, List, Dict

import pandas as pd

import indicators as ind
import levels_engine
import polygon_data

_log = logging.getLogger("inveria.backtest")

# ── Tunables (ATR-relative where possible, pct fallback) ──────────────────────
WARMUP_BARS = 260          # need ~252 for fib/52w + weekly pivots
ANCHOR_STEP = 21           # re-evaluate roughly monthly
FORWARD_WINDOW = 60        # trading days to judge whether a level held (~3 months)
VP_LOOKBACK = 252          # bars used to build the point-in-time volume profile


def _df_slice_to_bars(df_slice: pd.DataFrame) -> list:
    """Convert a price DataFrame slice to the bar dicts the VP builder expects."""
    tail = df_slice.tail(VP_LOOKBACK)
    bars = []
    for _, row in tail.iterrows():
        bars.append({
            "h": float(row["High"]),
            "l": float(row["Low"]),
            "c": float(row["Close"]),
            "v": float(row.get("Volume", 0) or 0),
        })
    return bars


def _bucket(strength: int) -> str:
    if strength >= 75:
        return "fuerte"
    if strength >= 50:
        return "media"
    return "debil"


def backtest_symbol(
    df: pd.DataFrame,
    *,
    forward_window: int = FORWARD_WINDOW,
    anchor_step: int = ANCHOR_STEP,
    touch_tol_atr: float = 0.5,
    bounce_atr: float = 1.0,
    break_atr: float = 1.0,
) -> dict:
    """Run the walk-forward backtest over a single symbol's price history.

    A level (a support BELOW the anchor price) is:
      • *touched* if, within the forward window, the Low reaches within
        touch_tol_atr*ATR of the level;
      • *held* if, after the first touch, price rebounds by >= bounce_atr*ATR
        BEFORE a daily Close breaks break_atr*ATR below the level;
      • *broken* if it touches but a Close breaks below before bouncing.
    Untouched levels are ignored (we can't judge them).
    """
    if df is None or df.empty or len(df) < WARMUP_BARS + forward_window + 5:
        return {"error": "insufficient_history", "bars": 0 if df is None else len(df)}

    df = df.copy()
    for col in ("High", "Low", "Close"):
        df[col] = df[col].astype(float)

    n = len(df)
    records: List[dict] = []

    i = WARMUP_BARS
    while i < n - forward_window - 1:
        sliced = df.iloc[: i + 1]
        current_price = float(df["Close"].iloc[i])
        if current_price <= 0:
            i += anchor_step
            continue

        try:
            indicators = ind.compute_all(sliced)
        except Exception:
            i += anchor_step
            continue

        atr_val = indicators.get("atr")
        if not atr_val or atr_val <= 0:
            i += anchor_step
            continue

        try:
            vp = polygon_data.compute_volume_profile(_df_slice_to_bars(sliced))
        except Exception:
            vp = {}

        try:
            levels = levels_engine.compute_buy_levels(
                sliced, vp, current_price,
                indicators.get("sma"),
                atr_val=atr_val,
                regime=indicators.get("regime"),
                vwap_anchored=indicators.get("vwap_anchored"),
            )
        except Exception:
            i += anchor_step
            continue

        fwd = df.iloc[i + 1 : i + 1 + forward_window]
        fwd_low = fwd["Low"].values
        fwd_high = fwd["High"].values
        fwd_close = fwd["Close"].values

        touch_tol = touch_tol_atr * atr_val
        bounce_amt = bounce_atr * atr_val
        break_amt = break_atr * atr_val

        for z in levels:
            L = float(z["price"])
            if not (0 < L < current_price):
                continue
            touch_at = None
            for t in range(len(fwd_low)):
                if fwd_low[t] <= L + touch_tol:
                    touch_at = t
                    break
            if touch_at is None:
                continue  # never reached — can't judge

            held = None  # True=bounced, False=broke
            for t in range(touch_at, len(fwd_low)):
                if fwd_close[t] <= L - break_amt:
                    held = False
                    break
                if fwd_high[t] >= L + bounce_amt:
                    held = True
                    break
            if held is None:
                # touched but neither bounced nor broke within window → unresolved
                continue

            records.append({
                "strength": int(z.get("strength", 0)),
                "bucket": _bucket(int(z.get("strength", 0))),
                "tactical": bool(z.get("tactical", False)),
                "held": held,
            })

        i += anchor_step

    return _aggregate(records, forward_window)


def _aggregate(records: List[dict], forward_window: int) -> dict:
    def rate(rs):
        resolved = [r for r in rs if r["held"] is not None]
        if not resolved:
            return {"n": 0, "hold_rate": None}
        held = sum(1 for r in resolved if r["held"])
        return {"n": len(resolved), "hold_rate": round(held / len(resolved) * 100, 1)}

    by_bucket = {b: rate([r for r in records if r["bucket"] == b]) for b in ("fuerte", "media", "debil")}
    by_kind = {
        "estructural": rate([r for r in records if not r["tactical"]]),
        "tactico": rate([r for r in records if r["tactical"]]),
    }
    return {
        "overall": rate(records),
        "by_strength": by_bucket,
        "by_kind": by_kind,
        "forward_window_days": forward_window,
        "samples": len(records),
    }


def backtest_universe(load_history, symbols: List[str], **kwargs) -> dict:
    """Aggregate the backtest across many symbols. `load_history(sym)` must return
    a price DataFrame (Open/High/Low/Close/Volume). Runs sequentially to keep the
    memory footprint low (one 2-3yr DataFrame at a time)."""
    all_records: List[dict] = []
    per_symbol: Dict[str, dict] = {}
    for sym in symbols:
        try:
            df = load_history(sym)
        except Exception:
            continue
        res = backtest_symbol(df, **kwargs)
        if res.get("samples"):
            per_symbol[sym] = res["overall"]
            # rebuild records weighted by reported counts is lossy; instead re-run
            # is wasteful — so we re-derive from buckets below using counts.
            for bucket, st in res["by_strength"].items():
                if st["n"] and st["hold_rate"] is not None:
                    held = round(st["n"] * st["hold_rate"] / 100)
                    all_records += [{"bucket": bucket, "tactical": False, "held": True}] * held
                    all_records += [{"bucket": bucket, "tactical": False, "held": False}] * (st["n"] - held)
    agg = _aggregate(all_records, kwargs.get("forward_window", FORWARD_WINDOW))
    agg["per_symbol"] = per_symbol
    agg["symbols_tested"] = len(per_symbol)
    return agg
