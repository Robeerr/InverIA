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


def true_range(df: pd.DataFrame) -> pd.Series:
    """True Range: max(H-L, |H-prevC|, |L-prevC|). Base for ATR/ADX."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    prev_close = df["Close"].astype(float).shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder's smoothing). The professional unit for
    measuring volatility — used to size stops, targets and zone tolerance."""
    tr = true_range(df)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14):
    """Average Directional Index (Wilder). Measures TREND STRENGTH (not direction):
    ADX > 25 = trending, < 20 = ranging. Returns (adx, plus_di, minus_di).
    Gates whether trend-following or mean-reversion level logic applies."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)
    tr = true_range(df)
    atr_s = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_s.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_s = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return adx_s, plus_di, minus_di


def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume: cumulative volume signed by close direction. Rising OBV
    confirms accumulation behind a price level; falling OBV warns of distribution."""
    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float) if "Volume" in df else pd.Series(0.0, index=df.index)
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * vol).cumsum()


def anchored_vwap(df: pd.DataFrame, anchor_idx: int) -> pd.Series:
    """Volume-Weighted Average Price anchored at a specific bar (typically a major
    swing low/high or an event). The institutional 'fair value since X' line —
    a dynamic support/resistance that pros defend. Uses typical price (H+L+C)/3."""
    sub = df.iloc[anchor_idx:]
    if sub.empty or "Volume" not in df:
        return pd.Series(dtype=float)
    tp = (sub["High"].astype(float) + sub["Low"].astype(float) + sub["Close"].astype(float)) / 3
    vol = sub["Volume"].astype(float)
    cum_vol = vol.cumsum().replace(0, np.nan)
    return (tp * vol).cumsum() / cum_vol


def market_regime(df: pd.DataFrame):
    """Classify the current regime so level logic can adapt. Returns a dict with
    trend strength (ADX), direction (vs SMA200 + SMA50 slope) and volatility band.
    In a strong trend, mean-reversion-to-support is less reliable; in a range,
    Value-Area edges bounce more. The best traders condition on this."""
    if df is None or len(df) < 60:
        return {"regime": "indeterminado", "adx": None, "trending": False, "direction": "lateral"}
    close = df["Close"].astype(float)
    adx_s, plus_di, minus_di = adx(df)
    adx_val = _safe(adx_s.iloc[-1])
    sma50 = sma(close, 50)
    sma200 = sma(close, 200) if len(close) >= 200 else None
    price = float(close.iloc[-1])

    trending = adx_val is not None and adx_val >= 25
    ranging = adx_val is not None and adx_val < 20

    # Direction: price vs SMA200 + recent SMA50 slope.
    direction = "lateral"
    sma50_now = sma50.iloc[-1]
    sma50_prev = sma50.iloc[-11] if len(sma50.dropna()) > 11 else sma50_now
    slope_up = pd.notna(sma50_now) and pd.notna(sma50_prev) and sma50_now > sma50_prev
    above_200 = sma200 is not None and pd.notna(sma200.iloc[-1]) and price > sma200.iloc[-1]
    if above_200 and slope_up:
        direction = "alcista"
    elif (sma200 is not None and pd.notna(sma200.iloc[-1]) and price < sma200.iloc[-1]) and not slope_up:
        direction = "bajista"

    if trending:
        regime = f"tendencia_{direction}"
    elif ranging:
        regime = "rango"
    else:
        regime = "transicion"

    return {
        "regime": regime,
        "adx": adx_val,
        "plus_di": _safe(plus_di.iloc[-1]),
        "minus_di": _safe(minus_di.iloc[-1]),
        "trending": bool(trending),
        "ranging": bool(ranging),
        "direction": direction,
    }


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
    """Find local minima (support) and maxima (resistance) pivots.

    Vectorizado con rolling centrado: un pivote es el valor que coincide con el
    mín (soporte) / máx (resistencia) de su ventana de tamaño 2*window+1.
    rolling con min_periods completo deja NaN en los extremos, que quedan excluidos
    igual que en la versión por loop original."""
    highs = df["High"]
    lows = df["Low"]
    w = 2 * window + 1
    local_min = lows.rolling(w, center=True).min()
    local_max = highs.rolling(w, center=True).max()
    supports = lows[lows == local_min]
    resistances = highs[highs == local_max]

    current = float(df["Close"].iloc[-1])
    # Closest supports below current, resistances above current
    supports_below = sorted({round(float(s), 2) for s in supports if s < current}, reverse=True)[:n_levels]
    resistances_above = sorted({round(float(r), 2) for r in resistances if r > current})[:n_levels]

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

    # Volatility (ATR) — the professional unit for stops/targets/zone width.
    atr_series = atr(df)
    atr_val = _safe(atr_series.iloc[last])
    atr_pct = round(atr_val / current_price * 100, 2) if atr_val and current_price else None

    # Regime (ADX-based) so downstream logic can adapt level reliability.
    regime = market_regime(df)

    # Anchored VWAP from the most significant swing low of the last year — the
    # institutional "fair value since the bottom" dynamic support.
    avwap_val = None
    try:
        window = df.tail(252)
        if not window.empty and "Volume" in df:
            anchor_pos = df.index.get_loc(window["Low"].astype(float).idxmin())
            av = anchored_vwap(df, anchor_pos)
            if not av.empty:
                avwap_val = _safe(av.iloc[-1])
    except Exception:
        avwap_val = None

    # OBV trend (accumulation vs distribution behind the price).
    obv_trend = None
    try:
        obv_series = obv(df)
        if len(obv_series) >= 20:
            obv_now = obv_series.iloc[-1]
            obv_then = obv_series.iloc[-20]
            obv_trend = "acumulacion" if obv_now > obv_then else "distribucion"
    except Exception:
        obv_trend = None

    # --- Salida por media de 10 semanas (= SMA 50 días): el método de "dejar correr los
    # ganadores y vender cuando el precio pierde la media de 10 semanas". ---
    salida_10w = None
    if len(close) >= 50:
        s50 = sma(close, 50)
        sma50_val = s50.iloc[last]
        if pd.notna(sma50_val) and sma50_val:
            por_encima = current_price >= sma50_val
            dist = (current_price - sma50_val) / sma50_val * 100
            recien = False
            if len(close) >= 56:
                seq = [current_price >= s50.iloc[i] if i == last else close.iloc[i] >= s50.iloc[i]
                       for i in range(last - 5, last + 1) if pd.notna(s50.iloc[i])]
                if len(seq) >= 2 and seq[0] and not seq[-1]:
                    recien = True  # estaba por encima y ha perdido la media en los últimos días
            salida_10w = {
                "sma": round(float(sma50_val), 2),
                "por_encima": bool(por_encima),
                "distancia_pct": round(float(dist), 2),
                "senal": "mantener" if por_encima else "salida",
                "recien_perdida": recien,
            }

    return {
        "price": round(current_price, 2),
        "salida_10w": salida_10w,
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
        "atr": atr_val,
        "atr_pct": atr_pct,
        "adx": regime.get("adx"),
        "regime": regime,
        "vwap_anchored": avwap_val,
        "obv_trend": obv_trend,
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
