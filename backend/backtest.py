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


def _walk_forward_records(
    df: pd.DataFrame,
    *,
    forward_window: int,
    anchor_step: int,
    touch_tol_atr: float,
    bounce_atr: float,
    break_atr: float,
) -> Optional[List[dict]]:
    """Core walk-forward loop. Returns the raw per-touch records, or None if the
    history is too short. Shared by single-symbol and universe backtests so the
    aggregation is identical and lossless."""
    if df is None or df.empty or len(df) < WARMUP_BARS + forward_window + 5:
        return None

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
                continue

            held = None
            for t in range(touch_at, len(fwd_low)):
                if fwd_close[t] <= L - break_amt:
                    held = False
                    break
                if fwd_high[t] >= L + bounce_amt:
                    held = True
                    break
            if held is None:
                continue

            # Magnitud y durabilidad del rebote (aquí es donde la confluencia
            # debería pagar, aunque la tasa de rebote sea parecida):
            #  • bounce_atr_real = máximo recorrido favorable tras el toque, en ATR
            #  • clean = el nivel NUNCA se rompió por cierre en toda la ventana
            post_high = fwd_high[touch_at:]
            mfe = (float(post_high.max()) - L) if len(post_high) else 0.0
            bounce_real = round(mfe / atr_val, 3) if atr_val else 0.0
            broke_ever = bool((fwd_close[touch_at:] <= (L - break_amt)).any())

            records.append({
                "strength": int(z.get("strength", 0)),
                "bucket": _bucket(int(z.get("strength", 0))),
                "tactical": bool(z.get("tactical", False)),
                "held": held,
                "bounce_atr": bounce_real,
                "clean": (not broke_ever),
                "sources": list(z.get("sources") or []),
            })

        i += anchor_step

    return records


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
    records = _walk_forward_records(
        df,
        forward_window=forward_window,
        anchor_step=anchor_step,
        touch_tol_atr=touch_tol_atr,
        bounce_atr=bounce_atr,
        break_atr=break_atr,
    )
    if records is None:
        return {"error": "insufficient_history", "bars": 0 if df is None else len(df)}
    return _aggregate(records, forward_window)


def _aggregate(records: List[dict], forward_window: int) -> dict:
    def rate(rs):
        resolved = [r for r in rs if r["held"] is not None]
        if not resolved:
            return {"n": 0, "hold_rate": None}
        held = sum(1 for r in resolved if r["held"])
        bounces = [r["bounce_atr"] for r in resolved if r.get("bounce_atr") is not None]
        cleans = [r for r in resolved if r.get("clean") is not None]
        n_clean = sum(1 for r in cleans if r.get("clean"))
        avg_bounce = round(sum(bounces) / len(bounces), 2) if bounces else None
        med_bounce = round(sorted(bounces)[len(bounces) // 2], 2) if bounces else None
        return {
            "n": len(resolved),
            "hold_rate": round(held / len(resolved) * 100, 1),
            "clean_hold_rate": round(n_clean / len(cleans) * 100, 1) if cleans else None,
            "avg_bounce_atr": avg_bounce,
            "median_bounce_atr": med_bounce,
        }

    by_bucket = {b: rate([r for r in records if r["bucket"] == b]) for b in ("fuerte", "media", "debil")}
    by_kind = {
        "estructural": rate([r for r in records if not r["tactical"]]),
        "tactico": rate([r for r in records if r["tactical"]]),
    }

    # Desglose por FUENTE: para cada metodología, mide su edge real cuando está
    # presente en un nivel tocado. Un nivel puede tener varias fuentes, así que
    # un toque cuenta para todas las que lo componen. Esto es lo que permite
    # recalibrar los pesos del score con datos en vez de a ojo.
    all_sources = set()
    for r in records:
        all_sources.update(r.get("sources") or [])
    by_source = {}
    for src in all_sources:
        st = rate([r for r in records if src in (r.get("sources") or [])])
        if st["n"] >= 8:  # ignora fuentes con muestra ridícula
            by_source[src] = st
    # ordena por durabilidad (clean) desc — el ranking empírico de fiabilidad
    by_source = dict(sorted(
        by_source.items(),
        key=lambda kv: (kv[1].get("clean_hold_rate") or 0),
        reverse=True,
    ))

    return {
        "overall": rate(records),
        "by_strength": by_bucket,
        "by_kind": by_kind,
        "by_source": by_source,
        "forward_window_days": forward_window,
        "samples": len(records),
    }


def backtest_universe(load_history, symbols: List[str], **kwargs) -> dict:
    """Aggregate the backtest across many symbols for statistical power. A single
    symbol gives only ~10-35 touches (too few, and uptrend names inflate to 100%);
    pooling the raw per-touch records across the universe yields hundreds.

    `load_history(sym)` must return a price DataFrame (Open/High/Low/Close/Volume).
    Runs sequentially to keep the memory footprint low (one DataFrame at a time)."""
    fw = kwargs.get("forward_window", FORWARD_WINDOW)
    all_records: List[dict] = []
    per_symbol: Dict[str, dict] = {}
    for sym in symbols:
        try:
            df = load_history(sym)
        except Exception:
            continue
        recs = _walk_forward_records(
            df,
            forward_window=fw,
            anchor_step=kwargs.get("anchor_step", ANCHOR_STEP),
            touch_tol_atr=kwargs.get("touch_tol_atr", 0.5),
            bounce_atr=kwargs.get("bounce_atr", 1.0),
            break_atr=kwargs.get("break_atr", 1.0),
        )
        if recs:
            all_records.extend(recs)
            per_symbol[sym] = _aggregate(recs, fw)["overall"]
    agg = _aggregate(all_records, fw)
    agg["per_symbol"] = per_symbol
    agg["symbols_tested"] = len(per_symbol)
    return agg
