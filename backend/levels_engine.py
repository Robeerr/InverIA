"""Motor de confluencia de niveles de compra/venta.

En vez de pedirle a la IA que "adivine" los niveles, aquí se CALCULAN de forma
determinista: se reúnen candidatos de múltiples métodos independientes, se agrupan
en zonas y se puntúa por CONFLUENCIA. Cuantas más fuentes caen en la misma zona,
más fuerte es el nivel.

La IA recibe estas zonas ya rankeadas y solo las explica/afina.
"""
from __future__ import annotations

import math
from typing import List, Dict, Optional, Tuple


# ── Peso base por fuente ─────────────────────────────────────────────────────
# Basado en evidencia empírica y uso profesional:
# • Volume Profile (POC/VAL/HVN) — el nivel donde más dinero se intercambió;
#   instituciones defienden estos niveles activamente.
# • VWAP anclado — precio medio ponderado por volumen desde el swing bajo;
#   las mesas institucionales usan esto como "fair value" dinámico.
# • Fibonacci golden ratio (61.8%) — ratio más observado en retrocesos.
# • SMA200 — el filtro de régimen más citado en la literatura (Faber 2007).
# Weights calibrated empirically from walk-forward universe backtest (641 touches, 30 stocks).
# Values proportional to clean_hold_rate (% where level was never broken by close in 60d window),
# normalized so top source ≈ 3.0. Sources ranked worst→best: low_52w(30%) < poc(30.4%) <
# fib_0.618(31.5%) < camarilla_s3(32.4%) < hvn(33.6%) < weekly_pivot(34.5%) < fib_0.5(36.7%) <
# floor_s1(37.6%) < round(38.3%) < val(39.1%) < pivot(39.4%) < camarilla_s4(39.7%) <
# sma50(40.2%) < sma200(40.7%) < floor_s2(41.8%) < fib_0.236(44.3%) < fib_0.786(44.7%) <
# vwap_anchored(44.7%) < fib_0.382(50.7%).
#
# NOTA (probado y descartado): ensanchar el rango a 0.5–3.0 vía
# peso = k·max(rate−25,0) NO mejoró la discriminación del bucket de fuerza
# (en backtest dio media > fuerte) y daba pesos extremos a fuentes con muestra
# pequeña (fib_0.618 n=52, low_52w n=30) = sobreajuste de ruido. El bucket de
# fuerza está limitado por ruido (SE≈3.5pts con n≈190): fuerte≈media≈débil en
# durabilidad porque los niveles ultra-obvios concentran stops. La señal REAL y
# estable es el ranking por fuente, que estos pesos moderados ya capturan.
_SOURCE_WEIGHTS = {
    "fib_0.382":    3.0,   # best empirical edge: 50.7% clean hold
    "vwap_anchored": 2.6,  # 44.7% clean hold
    "fib_0.786":    2.6,   # 44.7% clean hold
    "fib_0.236":    2.6,   # 44.3% clean hold
    "floor_s2":     2.5,   # 41.8% clean hold
    "sma200":       2.4,   # 40.7% clean hold
    "sma50":        2.4,   # 40.2% clean hold
    "camarilla_s4": 2.3,   # 39.7% clean hold (stronger than S3)
    "pivot":        2.3,   # 39.4% clean hold
    "val":          2.3,   # 39.1% clean hold
    "round":        2.2,   # 38.3% clean hold (underestimated before)
    "floor_s1":     2.2,   # 37.6% clean hold
    "fib_0.5":      2.1,   # 36.7% clean hold
    "weekly_pivot": 2.0,   # 34.5% clean hold
    "hvn":          1.9,   # 33.6% clean hold
    "camarilla_s3": 1.8,   # 32.4% clean hold (weaker than S4)
    "fib_0.618":    1.8,   # 31.5% clean hold (overrated before)
    "poc":          1.7,   # 30.4% clean hold (overrated before at 3.0)
    "low_52w":      1.7,   # 30.0% clean hold
}

_SOURCE_LABELS = {
    "poc":           "POC (precio más negociado)",
    "val":           "Value Area Low",
    "hvn":           "Zona de alto volumen (HVN)",
    "vwap_anchored": "VWAP anclado (soporte institucional dinámico)",
    "fib_0.618":     "Fibonacci 61.8% (golden ratio)",
    "fib_0.5":       "Fibonacci 50%",
    "fib_0.786":     "Fibonacci 78.6%",
    "fib_0.382":     "Fibonacci 38.2%",
    "fib_0.236":     "Fibonacci 23.6%",
    "camarilla_s3":  "Camarilla S3 (soporte intraday fiable)",
    "camarilla_s4":  "Camarilla S4 (soporte ruptura)",
    "floor_s1":      "Floor Pivot S1",
    "floor_s2":      "Floor Pivot S2",
    "sma200":        "Media móvil SMA200",
    "sma50":         "Media móvil SMA50",
    "weekly_pivot":  "Soporte semanal (timeframe alto)",
    "pivot":         "Soporte histórico (swing low)",
    "low_52w":       "Mínimo de 52 semanas",
    "round":         "Número redondo psicológico",
}

_STRENGTH_DIVISOR = 12.0

# Familia metodológica de cada fuente. La confluencia REAL es que metodologías
# DISTINTAS coincidan (volumen + fibonacci + media + pivote), no que 3 variantes
# de la misma idea (POC+VAL+HVN = todas "volumen") sumen como si fueran 3 pruebas
# independientes. Al puntuar se toma el mejor peso POR FAMILIA, no por fuente.
_SOURCE_FAMILY = {
    "poc": "volumen", "val": "volumen", "hvn": "volumen",
    "vwap_anchored": "vwap",
    "fib_0.236": "fibonacci", "fib_0.382": "fibonacci", "fib_0.5": "fibonacci",
    "fib_0.618": "fibonacci", "fib_0.786": "fibonacci",
    "camarilla_s3": "pivot_points", "camarilla_s4": "pivot_points",
    "floor_s1": "pivot_points", "floor_s2": "pivot_points",
    "pivot": "swing", "weekly_pivot": "swing", "low_52w": "swing",
    "sma200": "media", "sma50": "media",
    "round": "round",
}


# ── Camarilla Pivots ─────────────────────────────────────────────────────────
def _camarilla_pivots(high: float, low: float, close: float) -> dict:
    """Camarilla pivot points from the previous day/period OHLC.
    S3 = close - (high - low) * 1.1/4  — the most-traded intraday support level.
    S4 = close - (high - low) * 1.1/2  — breakout support (strong floor).
    Used by professional day traders and algorithms worldwide."""
    rng = high - low
    return {
        "s3": round(close - rng * 1.1 / 4, 2),
        "s4": round(close - rng * 1.1 / 2, 2),
        "r3": round(close + rng * 1.1 / 4, 2),
        "r4": round(close + rng * 1.1 / 2, 2),
    }


def _floor_pivots(high: float, low: float, close: float) -> dict:
    """Classic floor/pit trader pivot points.
    PP = (H + L + C) / 3
    S1 = 2*PP - H    S2 = PP - (H - L)"""
    pp = (high + low + close) / 3
    return {
        "pp":  round(pp, 2),
        "s1":  round(2 * pp - high, 2),
        "s2":  round(pp - (high - low), 2),
        "r1":  round(2 * pp - low, 2),
        "r2":  round(pp + (high - low), 2),
    }


# ── Touch counting with recency decay ────────────────────────────────────────
def _count_touches_weighted(df, level: float, tol_pct: float = 1.0) -> float:
    """Count how many candles touched this level weighted by recency.
    Recent touches are worth more than old touches. Returns a float weight
    that is added as extra score to the pivot source."""
    if level <= 0 or df is None or df.empty:
        return 0.0
    lows = df["Low"].astype(float)
    band = level * tol_pct / 100.0
    n = len(lows)
    total = 0.0
    for i, (idx, low_val) in enumerate(lows.items()):
        if abs(low_val - level) <= band:
            # Recency weight: bars closer to the end get more weight (1.0 at last, 0.3 at oldest)
            recency = 0.3 + 0.7 * (i / max(n - 1, 1))
            total += recency
    # Cap moderado: los toques refuerzan, pero no deben dominar la confluencia.
    return round(min(1.2, total * 0.3), 2)


# ── Multi-timeframe: weekly swing lows ───────────────────────────────────────
def _weekly_pivots(df, current_price: float) -> List[float]:
    """Higher-timeframe (weekly) swing lows. Un soporte que aguanta en el gráfico
    SEMANAL es mucho más significativo que un mínimo diario aislado — es el filtro
    multi-timeframe que usa todo profesional para separar niveles reales del ruido.
    Se construye agregando las velas diarias en velas ~semanales (5 sesiones)."""
    if df is None or len(df) < 30:
        return []
    lows = df["Low"].astype(float).tolist()
    n = len(lows)
    # Agregar mínimos diarios en cubos semanales (5 sesiones de bolsa por semana)
    weekly_lows = [min(lows[i:i + 5]) for i in range(0, n, 5)]
    m = len(weekly_lows)
    out: List[float] = []
    seen: List[float] = []
    # Swing low SEMANAL SIGNIFICATIVO = el mínimo de una ventana de ±2 velas
    # semanales (un suelo que aguantó ~5 semanas). Filtra el ruido y deja solo los
    # soportes estructurales reales del timeframe alto, sin duplicados cercanos.
    for j in range(2, m - 2):
        if weekly_lows[j] == min(weekly_lows[j - 2:j + 3]):
            p = round(float(weekly_lows[j]), 2)
            if 0 < p < current_price and all(abs(p - s) / p > 0.015 for s in seen):
                out.append(p)
                seen.append(p)
    return out


# ── Round levels ─────────────────────────────────────────────────────────────
def _round_levels_near(values: List[float]) -> List[float]:
    out = set()
    for v in values:
        if v <= 0:
            continue
        for step in (10, 5):
            nearest = round(v / step) * step
            if nearest > 0 and abs(nearest - v) / v <= 0.02:
                out.add(float(nearest))
    return sorted(out)


# ── Fibonacci retracements ────────────────────────────────────────────────────
def _swing_fibonacci(df, current: float) -> Dict[str, float]:
    recent = df.tail(252) if len(df) > 252 else df
    if recent.empty:
        return {}
    swing_high = float(recent["High"].max())
    swing_low = float(recent["Low"].min())
    rng = swing_high - swing_low
    if rng <= 0:
        return {}
    levels = {}
    for ratio in (0.236, 0.382, 0.5, 0.618, 0.786):
        price = swing_high - rng * ratio
        if 0 < price < current:
            levels[f"fib_{ratio}"] = round(price, 2)
    return levels


# ── ATR-based cluster tolerance ───────────────────────────────────────────────
def _cluster_tol(current_price: float, atr_val: Optional[float]) -> float:
    """ATR-relative tolerance for clustering nearby levels.
    Fixed % tolerances are arbitrary; ATR-scaled tolerances adapt to volatility.
    A zone within 1.0×ATR of another is likely the same structural level."""
    if atr_val and atr_val > 0 and current_price > 0:
        atr_pct = atr_val / current_price * 100
        # Cap: very low-vol stocks → 1.0%, very high-vol → 3.5%
        return max(1.0, min(3.5, atr_pct * 1.2))
    return 1.8  # fallback fixed %


# ── Regime scoring modifier ───────────────────────────────────────────────────
def _regime_modifier(src: str, regime: Optional[dict]) -> float:
    """In a strong trend, mean-reversion levels are less reliable; in a range,
    Value Area edges are more reliable. Adjust source weights accordingly."""
    if not regime:
        return 1.0
    trending = regime.get("trending", False)
    ranging = regime.get("ranging", False)
    direction = regime.get("direction", "lateral")

    if trending:
        # Trend mode: dynamic levels (SMA200, VWAP) more reliable; static pivots less
        if src in ("sma200", "sma50", "vwap_anchored"):
            return 1.3
        if src in ("poc", "val", "fib_0.618", "fib_0.5", "weekly_pivot"):
            return 1.1
        if src in ("camarilla_s3", "camarilla_s4", "floor_s1", "floor_s2"):
            return 0.8  # intraday levels less meaningful in strong trends
    if ranging:
        # Range mode: Value Area edges and round numbers more reliable
        if src in ("val", "poc", "hvn", "round", "camarilla_s3"):
            return 1.3
        if src in ("sma200", "sma50"):
            return 0.9  # MAs less meaningful in ranging market
    return 1.0


# ── Main engine ───────────────────────────────────────────────────────────────
def compute_buy_levels(
    df,
    volume_profile: Optional[dict],
    current_price: float,
    sma: Optional[dict] = None,
    max_levels: int = 4,
    atr_val: Optional[float] = None,
    regime: Optional[dict] = None,
    vwap_anchored: Optional[float] = None,
) -> List[dict]:
    """Compute ranked buy zones by confluence.

    Returns a list (closest to deepest) of dicts:
      {price, zone_low, zone_high, strength, label, distance_pct, reasons, sources}
    """
    if not current_price or current_price <= 0 or df is None or df.empty:
        return []

    tol_pct = _cluster_tol(current_price, atr_val)

    # ── 1) Gather candidates from all methods ─────────────────────────────
    candidates: List[tuple] = []  # (price, source_key, extra_weight)

    # Volume Profile
    vp = volume_profile or {}
    for key in ("poc", "val"):
        v = vp.get(key)
        if isinstance(v, (int, float)) and 0 < v < current_price:
            candidates.append((float(v), key, 0.0))
    for h in (vp.get("hvn") or []):
        if isinstance(h, (int, float)) and 0 < h < current_price:
            candidates.append((float(h), "hvn", 0.0))

    # Anchored VWAP — institutional dynamic support
    if isinstance(vwap_anchored, (int, float)) and 0 < vwap_anchored < current_price:
        candidates.append((float(vwap_anchored), "vwap_anchored", 0.0))

    # Fibonacci retracements from 52-week swing
    for src, price in _swing_fibonacci(df, current_price).items():
        candidates.append((price, src, 0.0))

    # SMAs
    sma = sma or {}
    for key, src in (("200", "sma200"), ("50", "sma50")):
        v = sma.get(key)
        if isinstance(v, (int, float)) and 0 < v < current_price:
            candidates.append((float(v), src, 0.0))

    # Camarilla Pivots — from last 20 bars (use recent typical range)
    try:
        recent = df.tail(20)
        cam_high = float(recent["High"].max())
        cam_low = float(recent["Low"].min())
        cam_close = float(df["Close"].iloc[-1])
        cam = _camarilla_pivots(cam_high, cam_low, cam_close)
        for src_key, cam_key in (("camarilla_s3", "s3"), ("camarilla_s4", "s4")):
            v = cam.get(cam_key)
            if isinstance(v, float) and 0 < v < current_price:
                candidates.append((v, src_key, 0.0))
        # Floor pivots
        fp = _floor_pivots(cam_high, cam_low, cam_close)
        for src_key, fp_key in (("floor_s1", "s1"), ("floor_s2", "s2")):
            v = fp.get(fp_key)
            if isinstance(v, float) and 0 < v < current_price:
                candidates.append((v, src_key, 0.0))
    except Exception:
        pass

    # Swing low pivots with recency-weighted touch count
    lows = df["Low"].astype(float)
    w = 11
    local_min = lows.rolling(w, center=True).min()
    pivots = lows[lows == local_min]
    seen_pivots: set = set()
    for p in pivots:
        p = round(float(p), 2)
        if not (0 < p < current_price) or p in seen_pivots:
            continue
        seen_pivots.add(p)
        extra = _count_touches_weighted(df, p)
        candidates.append((p, "pivot", extra))

    # Multi-timeframe: weekly swing lows (timeframe alto = soporte más fiable).
    # Cuando coinciden con un nivel diario, refuerzan la confluencia; cuando no,
    # añaden zonas estructurales profundas que el gráfico diario por sí solo pierde.
    # Sin extra por toques: ya pesa alto y los toques se cuentan en el pivote diario.
    for wp in _weekly_pivots(df, current_price):
        candidates.append((wp, "weekly_pivot", 0.0))

    # 52-week low
    low_52w = float(df["Low"].tail(252).min()) if len(df) else None
    if low_52w and 0 < low_52w < current_price:
        candidates.append((low_52w, "low_52w", 0.0))

    # Round numbers near existing candidates
    for rp in _round_levels_near([c[0] for c in candidates]):
        if 0 < rp < current_price:
            candidates.append((rp, "round", 0.0))

    if not candidates:
        return []

    # ── 2) Cluster nearby candidates ─────────────────────────────────────
    candidates.sort(key=lambda c: c[0], reverse=True)
    clusters: List[List[tuple]] = []
    for cand in candidates:
        price = cand[0]
        placed = False
        for cl in clusters:
            center = sum(c[0] for c in cl) / len(cl)
            if abs(price - center) / center * 100 <= tol_pct:
                cl.append(cand)
                placed = True
                break
        if not placed:
            clusters.append([cand])

    # ── 3) Score each zone by confluence (regime-adjusted) ────────────────
    zones = []
    for cl in clusters:
        best_by_source: Dict[str, float] = {}
        for price, src, extra in cl:
            base_weight = _SOURCE_WEIGHTS.get(src, 0.5)
            regime_adj = _regime_modifier(src, regime)
            weight = (base_weight * regime_adj) + extra
            if weight > best_by_source.get(src, 0):
                best_by_source[src] = weight
        # Puntuar por FAMILIA, no por fuente: se toma el mejor peso de cada familia
        # metodológica presente en la zona. Así POC+VAL+HVN cuenta como una prueba
        # de "volumen" fuerte, y la nota alta exige metodologías DISTINTAS.
        best_by_family: Dict[str, float] = {}
        for src, wt in best_by_source.items():
            fam = _SOURCE_FAMILY.get(src, "otro")
            if wt > best_by_family.get(fam, 0):
                best_by_family[fam] = wt
        raw = sum(best_by_family.values())
        # Bonus por nº de familias DISTINTAS que coinciden (la esencia de la confluencia).
        n_families = len([f for f in best_by_family if f != "round"])
        if n_families >= 2:
            raw += (n_families - 1) * 0.6
        strength = int(min(100, round(raw / _STRENGTH_DIVISOR * 100)))

        prices_in_cl = [c[0] for c in cl]
        zone_low = round(min(prices_in_cl), 2)
        zone_high = round(max(prices_in_cl), 2)
        wsum = sum(_SOURCE_WEIGHTS.get(s, 0.5) for _, s, _ in cl) or 1
        center = round(sum(p * _SOURCE_WEIGHTS.get(s, 0.5) for p, s, _ in cl) / wsum, 2)

        reasons = [_SOURCE_LABELS.get(s, s) for s in sorted(best_by_source, key=best_by_source.get, reverse=True)]
        zones.append({
            "price": center,
            "zone_low": zone_low,
            "zone_high": zone_high,
            "strength": strength,
            "distance_pct": round((center - current_price) / current_price * 100, 2),
            "reasons": reasons,
            "sources": list(best_by_source.keys()),
        })

    # ── 4) Select the strongest structural zones as the ladder backbone ───
    zones.sort(key=lambda z: z["strength"], reverse=True)
    backbone = zones[:max_levels]
    leftover = zones[max_levels:]
    backbone.sort(key=lambda z: z["price"], reverse=True)

    # ── 4b) Hybrid tactical gap-fill (ATR-based) ──────────────────────────
    # Los acumuladores profesionales (scaling-in institucional, pirámide de
    # O'Neil) evitan dejar huecos mayores de ~1×ATR entre peldaños. Cuando un
    # hueco supera ese umbral insertamos UN relleno táctico: anclado al mejor
    # soporte estructural sobrante DENTRO del hueco si existe, o a un número
    # redondo cerca del punto medio si no hay estructura. Los rellenos llevan
    # flag `tactical` y fuerza reducida — sirven para suavizar el drawdown y
    # subir la tasa de llenado, NO para mejorar el retorno (evidencia: el CAGR
    # apenas cambia pero el drawdown baja). Núcleo fuerte + relleno oportunista.
    gap_threshold = (atr_val * 1.0) if (atr_val and atr_val > 0) else current_price * 0.04
    boundaries = [current_price] + [z["price"] for z in backbone]
    gaps = []  # (gap_size, hi, lo)
    for i in range(len(boundaries) - 1):
        hi, lo = boundaries[i], boundaries[i + 1]
        if hi - lo > gap_threshold:
            gaps.append((hi - lo, hi, lo))
    gaps.sort(reverse=True)  # rellena primero los huecos más grandes

    fillers: List[dict] = []
    for _, hi, lo in gaps[:2]:  # como mucho 2 rellenos tácticos
        inside = [z for z in leftover if lo < z["price"] < hi and not z.get("_used")]
        if inside:
            best = max(inside, key=lambda z: z["strength"])
            best["_used"] = True
            best["tactical"] = True
            if "Entrada táctica" not in best["reasons"]:
                best["reasons"] = ["Entrada táctica"] + best["reasons"]
            fillers.append(best)
            continue
        # Sin estructura sobrante: número redondo cerca del punto medio.
        mid = (hi + lo) / 2.0
        rp = None
        for step in (5, 10):
            cand = round(mid / step) * step
            if lo < cand < hi:
                rp = float(cand)
                break
        if rp is None:
            rp = round(mid, 2)
        fillers.append({
            "price": rp,
            "zone_low": rp,
            "zone_high": rp,
            "strength": 20,
            "distance_pct": round((rp - current_price) / current_price * 100, 2),
            "reasons": ["Entrada táctica (rellena hueco)"],
            "sources": ["tactical"],
            "tactical": True,
        })

    # ── 4c) Merge backbone + tactical fillers, re-label closest-to-deepest ─
    combined = backbone + fillers
    combined.sort(key=lambda z: z["price"], reverse=True)
    for i, z in enumerate(combined, 1):
        z["label"] = f"NIVEL {i}"
        z.setdefault("tactical", False)
        z.pop("_used", None)
    return combined


# ─────────────────────────────────────────────────────────────────────────────
# QUÉ ZONAS ENTRAN EN EL PLAN ESCALONADO
#
# Vive aquí, y no en server.py, por dos razones:
#
#   1. Es UNA sola implementación. `_deterministic_levels` la usa para construir el
#      plan y el ensamblado del dashboard la usa para marcar `en_plan`. Si estuvieran
#      separadas, la pantalla podría agrupar de una forma y el plan operar de otra —
#      exactamente el desajuste que este campo viene a cerrar.
#   2. Este módulo es puro (solo math y typing), así que los tests pueden importarlo
#      sin arrastrar FastAPI ni Mongo. La versión anterior de estos tests tenía que
#      REPLICAR el filtro para poder probarlo, y una réplica siempre acaba divergiendo.
#
# El umbral llega como parámetro a propósito: `MAX_PLAN_DEPTH` es configurable por
# entorno y su sitio es server.py. Escribirlo aquí sería la misma duplicación con otro
# disfraz.
# ─────────────────────────────────────────────────────────────────────────────

MAX_ESCALONES = 3      # el plan reparte la compra en 3 tramos como mucho
VENTANA = 6            # solo se miran las 6 zonas más cercanas al precio


def _precio(z) -> Optional[float]:
    try:
        v = float((z or {}).get("price"))
    except (TypeError, ValueError, AttributeError):
        return None
    return v


def indices_del_plan(current_price, buy_levels, max_depth: float) -> List[int]:
    """Índices de `buy_levels` que forman el plan escalonado, de cerca a lejos.

    Fachada de `indices_del_plan_detallado`, que es donde vive la regla. Conserva firma y
    comportamiento porque la mayoría de los llamadores solo necesitan los índices y no les
    importa por qué camino salieron.

    La regla, tal cual la aplicaba `_deterministic_levels`:

      - se miran las `VENTANA` primeras zonas (la lista viene ordenada de cerca a lejos);
      - se descarta la que esté por debajo del suelo, `precio × (1 − max_depth)`. El stop
        va por debajo de TODAS las entradas del plan, así que meter una zona a −46%
        arrastraba el stop hasta ahí y eso no es un stop, es perder media posición;
      - se cogen las `MAX_ESCALONES` primeras que sobrevivan.

    El límite es INCLUSIVO: una zona exactamente en el suelo entra.

    Respaldo: si no sobrevive ninguna —la acción ha subido tanto que no hay soporte
    cerca— se devuelve la menos profunda de toda la lista. Es preferible a quedarse sin
    plan, porque sin plan los números los inventa la IA.
    """
    return indices_del_plan_detallado(current_price, buy_levels, max_depth)[0]


def indices_del_plan_detallado(current_price, buy_levels,
                               max_depth: float) -> Tuple[List[int], bool]:
    """Lo mismo, más SI el plan devuelto es el rescate y no una selección.

    POR QUÉ HACE FALTA SABERLO

    El respaldo devuelve la zona menos profunda AUNQUE quede por debajo del suelo. Quien
    redacta la nota del plan no podía distinguir ese caso de uno normal, así que escribía
    siempre la misma frase —«deja fuera las que están a más de un 30% bajo el precio»—
    mientras la única zona que el plan usaba estaba, ella también, por debajo de ese 30%.
    La nota contradecía al plan que acompañaba.

    Y hay una variante peor: con UNA sola zona bajo el suelo no sobraba ninguna, así que
    la nota ni siquiera salía. El usuario recibía un plan con el stop a -38% y ningún
    aviso.

    SE DEVUELVE, NO SE DEDUCE

    El dato se conoce exactamente aquí, en la rama que lo decide. Dejar que el llamador lo
    infiera comparando la zona elegida contra `precio × (1 − max_depth)` sería reimplantar
    el suelo fuera de su dueño, que es la clase de duplicación que este módulo existe para
    evitar.

    `indices_del_plan` sigue siendo la puerta de entrada normal: mantiene su firma para
    que ni `marcar_en_plan` ni los tests que fijan la selección tengan que cambiar.
    """
    zonas = buy_levels or []
    try:
        precio = float(current_price)
    except (TypeError, ValueError):
        return [], False
    if precio <= 0:
        return [], False

    suelo = precio * (1 - max_depth)

    elegidos: List[int] = []
    for i, z in enumerate(zonas[:VENTANA]):
        if len(elegidos) >= MAX_ESCALONES:
            break
        p = _precio(z)
        if p is None or p < suelo:
            continue
        elegidos.append(i)

    if elegidos:
        return elegidos, False

    for i, z in enumerate(zonas):
        if _precio(z) is not None:
            return [i], True
    # Sin ninguna zona con precio no hay plan NI rescate: no se ha salvado nada.
    return [], False


def marcar_en_plan(buy_levels, current_price, max_depth: float):
    """Añade `en_plan` a cada zona. ADITIVO: no toca ningún otro campo ni el orden.

    Se llama en los dos sitios donde se producen zonas —el ensamblado del dashboard y
    `/analyze`— para que la respuesta que parchea la IA no llegue sin el campo y la
    pantalla pierda la agrupación justo al pulsar el botón.
    """
    dentro = set(indices_del_plan(current_price, buy_levels, max_depth))
    for i, z in enumerate(buy_levels or []):
        if isinstance(z, dict):
            z["en_plan"] = i in dentro
    return buy_levels
