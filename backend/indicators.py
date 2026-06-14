"""Technical indicator calculations using pandas/numpy."""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return upper, sma, lower


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def fibonacci_levels(high: float, low: float):
    diff = high - low
    return {
        "0.0": round(low, 2),
        "23.6": round(low + 0.236 * diff, 2),
        "38.2": round(low + 0.382 * diff, 2),
        "50.0": round(low + 0.5 * diff, 2),
        "61.8": round(low + 0.618 * diff, 2),
        "78.6": round(low + 0.786 * diff, 2),
        "100.0": round(high, 2),
    }


def support_resistance(df: pd.DataFrame, window: int = 5, n_levels: int = 3):
    """Find local minima (support) and maxima (resistance) pivots."""
    highs = df["High"]
    lows = df["Low"]
    supports = []
    resistances = []

    for i in range(window, len(df) - window):
        local_lows = lows.iloc[i - window : i + window + 1]
        local_highs = highs.iloc[i - window : i + window + 1]
        if lows.iloc[i] == local_lows.min():
            supports.append(float(lows.iloc[i]))
        if highs.iloc[i] == local_highs.max():
            resistances.append(float(highs.iloc[i]))

    current = float(df["Close"].iloc[-1])
    # Closest supports below current, resistances above current
    supports_below = sorted({round(s, 2) for s in supports if s < current}, reverse=True)[:n_levels]
    resistances_above = sorted({round(r, 2) for r in resistances if r > current})[:n_levels]

    return {
        "supports": supports_below,
        "resistances": resistances_above,
    }


def detect_patterns(df: pd.DataFrame):
    """Simple chart pattern detection."""
    patterns = []
    close = df["Close"]
    if len(close) < 50:
        return patterns

    last_50 = close.tail(50)
    last_20 = close.tail(20)
    sma_20 = sma(close, 20).iloc[-1]
    sma_50 = sma(close, 50).iloc[-1] if len(close) >= 50 else None
    sma_200 = sma(close, 200).iloc[-1] if len(close) >= 200 else None

    current = float(close.iloc[-1])
    prev = float(close.iloc[-10]) if len(close) >= 10 else current

    # Golden / Death cross
    if sma_50 is not None and sma_200 is not None:
        if sma_50 > sma_200 and current > sma_50:
            patterns.append("Golden Cross (alcista)")
        elif sma_50 < sma_200:
            patterns.append("Death Cross (bajista)")

    # Trend
    trend_change = (current - prev) / prev * 100
    if trend_change > 5:
        patterns.append(f"Tendencia alcista fuerte (+{trend_change:.1f}%)")
    elif trend_change < -5:
        patterns.append(f"Tendencia bajista fuerte ({trend_change:.1f}%)")

    # Higher highs / lower lows
    highs = df["High"].tail(20).values
    lows = df["Low"].tail(20).values
    if all(highs[i] <= highs[i + 5] for i in range(0, len(highs) - 5, 5)):
        patterns.append("Máximos crecientes (HH)")
    if all(lows[i] >= lows[i + 5] for i in range(0, len(lows) - 5, 5)):
        patterns.append("Mínimos decrecientes (LL)")

    # Consolidation
    volatility = last_20.std() / last_20.mean() * 100
    if volatility < 2:
        patterns.append("Consolidación (rango estrecho)")

    return patterns


def compute_all(df: pd.DataFrame):
    """Compute all indicators and return a structured dict."""
    close = df["Close"]
    rsi_series = rsi(close)
    macd_line, signal_line, hist = macd(close)
    bb_upper, bb_mid, bb_lower = bollinger(close)

    high_52w = float(df["High"].tail(252).max()) if len(df) > 0 else 0.0
    low_52w = float(df["Low"].tail(252).min()) if len(df) > 0 else 0.0

    sr = support_resistance(df, n_levels=5)
    fib = fibonacci_levels(high_52w, low_52w)
    patterns = detect_patterns(df)

    last = -1
    current_price = float(close.iloc[last])

    return {
        "price": round(current_price, 2),
        "rsi": _safe(rsi_series.iloc[last]),
        "macd": {
            "macd": _safe(macd_line.iloc[last]),
            "signal": _safe(signal_line.iloc[last]),
            "histogram": _safe(hist.iloc[last]),
        },
        "bollinger": {
            "upper": _safe(bb_upper.iloc[last]),
            "middle": _safe(bb_mid.iloc[last]),
            "lower": _safe(bb_lower.iloc[last]),
        },
        "sma": {
            "20": _safe(sma(close, 20).iloc[last]),
            "50": _safe(sma(close, 50).iloc[last]) if len(close) >= 50 else None,
            "200": _safe(sma(close, 200).iloc[last]) if len(close) >= 200 else None,
        },
        "ema": {
            "12": _safe(ema(close, 12).iloc[last]),
            "26": _safe(ema(close, 26).iloc[last]),
        },
        "fibonacci": fib,
        "support_resistance": sr,
        "patterns": patterns,
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
    }


def _safe(val):
    try:
        if val is None or pd.isna(val):
            return None
        return round(float(val), 2)
    except Exception:
        return None
