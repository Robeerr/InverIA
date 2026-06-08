"""Backtesting engine for AI-suggested levels."""
import pandas as pd
from typing import Optional
import market_data


def backtest_levels(
    symbol: str,
    entry_min: float,
    entry_max: float,
    stop_loss: float,
    take_profit_1: float,
    take_profit_2: Optional[float] = None,
    direction: str = "long",  # "long" or "short"
    lookback_days: int = 252,
):
    """Simulate trades using historical bars and the suggested levels.

    For each historical day, if price enters the entry zone, open a trade.
    Close at TP or SL (whichever hits first using high/low of subsequent bars).
    """
    df = market_data.get_full_indicator_history(symbol)
    if df is None or df.empty:
        return None
    df = df.tail(lookback_days).reset_index(drop=True)

    trades = []
    i = 0
    while i < len(df) - 1:
        row = df.iloc[i]
        low, high = float(row["Low"]), float(row["High"])
        entered = False
        if direction == "long":
            # Entry triggers if the bar touched the entry zone
            if low <= entry_max and high >= entry_min:
                entry_price = max(entry_min, low)  # approximate fill
                entered = True
        else:  # short
            if low <= entry_max and high >= entry_min:
                entry_price = min(entry_max, high)
                entered = True

        if entered:
            outcome = None
            for j in range(i + 1, len(df)):
                bar = df.iloc[j]
                bh, bl = float(bar["High"]), float(bar["Low"])
                if direction == "long":
                    hit_tp1 = bh >= take_profit_1
                    hit_sl = bl <= stop_loss
                    if hit_sl and hit_tp1:
                        # Conservative: assume SL hit first
                        outcome = ("LOSS", stop_loss, j)
                        break
                    if hit_tp1:
                        outcome = ("WIN", take_profit_1, j)
                        break
                    if hit_sl:
                        outcome = ("LOSS", stop_loss, j)
                        break
                else:
                    hit_tp1 = bl <= take_profit_1
                    hit_sl = bh >= stop_loss
                    if hit_sl and hit_tp1:
                        outcome = ("LOSS", stop_loss, j)
                        break
                    if hit_tp1:
                        outcome = ("WIN", take_profit_1, j)
                        break
                    if hit_sl:
                        outcome = ("LOSS", stop_loss, j)
                        break
            if outcome:
                result, exit_price, exit_idx = outcome
                ret_pct = ((exit_price - entry_price) / entry_price * 100) if direction == "long" else ((entry_price - exit_price) / entry_price * 100)
                trades.append({
                    "entry_date": df.iloc[i]["Date"].isoformat(),
                    "entry_price": round(entry_price, 2),
                    "exit_date": df.iloc[exit_idx]["Date"].isoformat(),
                    "exit_price": round(exit_price, 2),
                    "result": result,
                    "return_pct": round(ret_pct, 2),
                    "bars_held": exit_idx - i,
                })
                i = exit_idx + 1
                continue
        i += 1

    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    total_return = sum(t["return_pct"] for t in trades)
    win_rate = (len(wins) / len(trades) * 100) if trades else 0

    return {
        "symbol": symbol.upper(),
        "direction": direction,
        "params": {
            "entry_zone": [entry_min, entry_max],
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
        },
        "lookback_days": lookback_days,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_return_pct": round(total_return, 2),
        "avg_return_pct": round(total_return / len(trades), 2) if trades else 0,
        "avg_bars_held": round(sum(t["bars_held"] for t in trades) / len(trades), 1) if trades else 0,
        "trades": trades[-20:],  # last 20 trades to keep payload small
    }
