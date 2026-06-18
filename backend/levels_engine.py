"""Motor de confluencia de niveles de compra.

En vez de pedirle a la IA que "adivine" los niveles, aquí se CALCULAN de forma
determinista: se reúnen todos los soportes por debajo del precio actual desde
métodos independientes (Volume Profile, Fibonacci sobre el swing real, pivotes
de mínimos ponderados por toques, medias móviles, mínimo de 52s y números
redondos), se agrupan los cercanos en zonas y se puntúa cada zona por
CONFLUENCIA (cuántos métodos distintos coinciden). Cuantas más fuentes caen en
la misma zona, más fuerte es el nivel.

La IA recibe estas zonas ya rankeadas y solo las explica/afina.
"""
from __future__ import annotations

from typing import List, Dict, Optional


# Peso de cada fuente: cuánto "vale" que un método sitúe un soporte aquí.
# El Volume Profile y el Fibonacci de la golden ratio pesan más porque son las
# señales más fiables para zonas de acumulación.
_SOURCE_WEIGHTS = {
    "poc": 3.0,        # Point of Control — precio más negociado, soporte más fuerte
    "val": 3.0,        # Value Area Low — borde inferior del 70% del volumen
    "hvn": 2.0,        # High Volume Node — zona donde el precio rebota
    "fib_0.618": 2.5,  # golden ratio
    "fib_0.5": 2.0,
    "fib_0.786": 2.0,
    "fib_0.382": 1.5,
    "fib_0.236": 1.0,
    "sma200": 2.0,     # soporte dinámico de largo plazo
    "sma50": 1.5,
    "pivot": 1.0,      # mínimo local (se suma un extra por nº de toques)
    "low_52w": 1.5,
    "round": 0.5,      # número psicológico redondo
}

# Etiqueta legible para el usuario por cada fuente.
_SOURCE_LABELS = {
    "poc": "POC (precio más negociado)",
    "val": "Value Area Low",
    "hvn": "Zona de alto volumen (HVN)",
    "fib_0.618": "Fibonacci 61.8% (golden ratio)",
    "fib_0.5": "Fibonacci 50%",
    "fib_0.786": "Fibonacci 78.6%",
    "fib_0.382": "Fibonacci 38.2%",
    "fib_0.236": "Fibonacci 23.6%",
    "sma200": "Media móvil SMA200",
    "sma50": "Media móvil SMA50",
    "pivot": "Soporte histórico",
    "low_52w": "Mínimo de 52 semanas",
    "round": "Número redondo psicológico",
}

# Tolerancia para agrupar candidatos en una misma zona (% del precio).
_CLUSTER_TOL_PCT = 1.8
# Divisor de normalización: con este peso acumulado se considera fuerza ~máxima.
# Calibrado para que una zona de 1 sola fuente quede floja (~30-40), 2-3 fuentes
# medio-fuerte (~60-80) y 4+ fuentes en confluencia llegue cerca de 100.
_STRENGTH_DIVISOR = 9.5


def _round_levels_near(values: List[float]) -> List[float]:
    """Devuelve números redondos (decenas / múltiplos de 5) cercanos a los
    candidatos existentes — solo cuentan si refuerzan una zona ya presente."""
    out = set()
    for v in values:
        if v <= 0:
            continue
        # múltiplo de 10 y de 5 más cercanos
        for step in (10, 5):
            nearest = round(v / step) * step
            if nearest > 0 and abs(nearest - v) / v <= 0.02:
                out.add(float(nearest))
    return sorted(out)


def _count_touches(df, level: float, tol_pct: float = 1.0) -> int:
    """Cuántas velas tienen su mínimo a menos de tol_pct del nivel — un soporte
    tocado muchas veces es más fiable que uno tocado una sola."""
    if level <= 0 or df is None or df.empty:
        return 0
    lows = df["Low"].astype(float)
    band = level * tol_pct / 100.0
    return int(((lows - level).abs() <= band).sum())


def _swing_fibonacci(df, current: float) -> Dict[str, float]:
    """Retrocesos Fibonacci sobre el swing relevante reciente (último ~año),
    no sobre un rango arbitrario. Solo se devuelven los que caen por debajo del
    precio actual (zonas de compra)."""
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
        if 0 < price < current:  # solo soportes por debajo del precio
            levels[f"fib_{ratio}"] = round(price, 2)
    return levels


def compute_buy_levels(
    df,
    volume_profile: Optional[dict],
    current_price: float,
    sma: Optional[dict] = None,
    max_levels: int = 4,
) -> List[dict]:
    """Calcula zonas de compra rankeadas por confluencia.

    Devuelve una lista (de más cercana a más profunda) de dicts:
      {price, zone_low, zone_high, strength, label, distance_pct, reasons, sources}
    """
    if not current_price or current_price <= 0 or df is None or df.empty:
        return []

    # ---- 1) Reunir candidatos (price, source) de cada método, por debajo del precio ----
    candidates: List[tuple] = []  # (price, source_key, extra_weight)

    vp = volume_profile or {}
    for key in ("poc", "val"):
        v = vp.get(key)
        if isinstance(v, (int, float)) and 0 < v < current_price:
            candidates.append((float(v), key, 0.0))
    for h in (vp.get("hvn") or []):
        if isinstance(h, (int, float)) and 0 < h < current_price:
            candidates.append((float(h), "hvn", 0.0))

    for src, price in _swing_fibonacci(df, current_price).items():
        candidates.append((price, src, 0.0))

    sma = sma or {}
    for key, src in (("200", "sma200"), ("50", "sma50")):
        v = sma.get(key)
        if isinstance(v, (int, float)) and 0 < v < current_price:
            candidates.append((float(v), src, 0.0))

    # Pivotes de mínimos locales, ponderados por nº de toques.
    lows = df["Low"].astype(float)
    w = 11
    local_min = lows.rolling(w, center=True).min()
    pivots = lows[lows == local_min]
    seen_pivots = set()
    for p in pivots:
        p = round(float(p), 2)
        if not (0 < p < current_price) or p in seen_pivots:
            continue
        seen_pivots.add(p)
        touches = _count_touches(df, p)
        extra = min(1.5, max(0, touches - 1) * 0.3)  # más toques → más peso (cap)
        candidates.append((p, "pivot", extra))

    low_52w = float(df["Low"].tail(252).min()) if len(df) else None
    if low_52w and 0 < low_52w < current_price:
        candidates.append((low_52w, "low_52w", 0.0))

    # Números redondos cercanos a candidatos ya presentes (solo refuerzan).
    for rp in _round_levels_near([c[0] for c in candidates]):
        if 0 < rp < current_price:
            candidates.append((rp, "round", 0.0))

    if not candidates:
        return []

    # ---- 2) Agrupar candidatos cercanos en zonas ----
    candidates.sort(key=lambda c: c[0], reverse=True)  # de más cerca a más lejos del precio
    clusters: List[List[tuple]] = []
    for cand in candidates:
        price = cand[0]
        placed = False
        for cl in clusters:
            center = sum(c[0] for c in cl) / len(cl)
            if abs(price - center) / center * 100 <= _CLUSTER_TOL_PCT:
                cl.append(cand)
                placed = True
                break
        if not placed:
            clusters.append([cand])

    # ---- 3) Puntuar cada zona por confluencia ----
    zones = []
    for cl in clusters:
        # Una misma fuente (p.ej. dos HVN) no debe inflar la nota: se queda el
        # mayor peso por tipo de fuente, y se suman tipos DISTINTOS (confluencia).
        best_by_source: Dict[str, float] = {}
        for price, src, extra in cl:
            weight = _SOURCE_WEIGHTS.get(src, 0.5) + extra
            if weight > best_by_source.get(src, 0):
                best_by_source[src] = weight
        raw = sum(best_by_source.values())
        # Bonus por nº de tipos distintos FUERTES que coinciden (la esencia de la
        # confluencia). Los números redondos no cuentan como confluencia real.
        distinct = len([s for s in best_by_source if s != "round"])
        if distinct >= 2:
            raw += (distinct - 1) * 0.4
        strength = int(min(100, round(raw / _STRENGTH_DIVISOR * 100)))

        prices = [c[0] for c in cl]
        zone_low = round(min(prices), 2)
        zone_high = round(max(prices), 2)
        # Centro ponderado por peso de fuente.
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

    # ---- 4) Quedarnos con las mejores zonas, ordenadas de más cerca a más profunda ----
    zones.sort(key=lambda z: z["strength"], reverse=True)
    top = zones[:max_levels]
    top.sort(key=lambda z: z["price"], reverse=True)
    for i, z in enumerate(top, 1):
        z["label"] = f"NIVEL {i}"
    return top
