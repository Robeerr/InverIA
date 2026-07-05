"""Detección ALGORÍTMICA de líneas de gráfico (sin IA de visión, puro cálculo).

Genera, a partir de las velas OHLC:
  • Líneas de TENDENCIA diagonales (uniendo pivotes máximos o mínimos relevantes).
  • Niveles horizontales de SOPORTE/RESISTENCIA (clustering de precios donde más ha
    rebotado el precio).

Ligero (numpy), corre en el servidor de 512MB sin problema y sin coste de IA. El frontend
recibe las coordenadas y las dibuja sobre el gráfico interactivo.
"""
from __future__ import annotations

from typing import List, Dict


def _pivots(values, kind: str, left: int = 3, right: int = 3):
    """Índices de pivotes locales. kind='high' → máximos locales; 'low' → mínimos.
    Un pivote alto es una vela cuyo valor es >= que las `left` anteriores y `right` posteriores."""
    n = len(values)
    out = []
    for i in range(left, n - right):
        v = values[i]
        window = values[i - left:i + right + 1]
        if kind == "high" and v >= max(window):
            out.append(i)
        elif kind == "low" and v <= min(window):
            out.append(i)
    return out


def _fit_trendline(idxs, prices, want: str):
    """Ajusta la mejor recta a los pivotes. want='resistencia' usa máximos (línea por
    encima), 'soporte' usa mínimos. Devuelve dos puntos {index, price} o None.

    Estrategia sencilla y robusta: toma los 2 pivotes más separados en el tiempo cuyo
    trazo deja al resto de pivotes del lado correcto (una directriz "limpia")."""
    if len(idxs) < 2:
        return None
    best = None
    for a in range(len(idxs)):
        for b in range(a + 1, len(idxs)):
            i1, i2 = idxs[a], idxs[b]
            if i2 == i1:
                continue
            p1, p2 = prices[i1], prices[i2]
            slope = (p2 - p1) / (i2 - i1)
            # Comprueba que la recta deja los pivotes del lado correcto (tolerancia pequeña).
            tol = (max(prices) - min(prices)) * 0.01
            ok = True
            for k in idxs:
                line_val = p1 + slope * (k - i1)
                if want == "resistencia" and prices[k] > line_val + tol:
                    ok = False; break
                if want == "soporte" and prices[k] < line_val - tol:
                    ok = False; break
            if not ok:
                continue
            span = i2 - i1
            if best is None or span > best["span"]:
                best = {"span": span, "i1": i1, "p1": p1, "i2": i2, "p2": p2, "slope": slope}
    if not best:
        return None
    return {
        "type": "trendline",
        "kind": want,
        "points": [
            {"index": int(best["i1"]), "price": round(float(best["p1"]), 2)},
            {"index": int(best["i2"]), "price": round(float(best["p2"]), 2)},
        ],
        "direction": "alcista" if best["slope"] > 0 else "bajista",
    }


def _horizontal_levels(highs, lows, closes, current_price, max_levels: int = 4):
    """Niveles horizontales por DENSIDAD: agrupa pivotes (altos y bajos) en clusters de
    precio cercanos; los clusters con más toques son soportes/resistencias fuertes."""
    hi_idx = _pivots(highs, "high")
    lo_idx = _pivots(lows, "low")
    pts = [highs[i] for i in hi_idx] + [lows[i] for i in lo_idx]
    if not pts:
        return []
    price_range = max(highs) - min(lows)
    if price_range <= 0:
        return []
    tol = price_range * 0.015  # 1.5% del rango = mismo nivel
    clusters: List[List[float]] = []
    for p in sorted(pts):
        placed = False
        for cl in clusters:
            if abs(p - (sum(cl) / len(cl))) <= tol:
                cl.append(p); placed = True; break
        if not placed:
            clusters.append([p])
    levels = []
    for cl in clusters:
        if len(cl) < 2:  # al menos 2 toques para ser un nivel relevante
            continue
        price = round(sum(cl) / len(cl), 2)
        levels.append({
            "type": "level",
            "price": price,
            "touches": len(cl),
            "role": "resistencia" if current_price and price > current_price else "soporte",
        })
    levels.sort(key=lambda x: x["touches"], reverse=True)
    return levels[:max_levels]


def detect_lines(candles: List[Dict], current_price: float = None) -> Dict:
    """Punto de entrada. `candles` = lista de dicts con high/low/close (y opcionalmente
    fecha). Devuelve líneas de tendencia + niveles horizontales, en coordenadas de índice
    de vela (el frontend las mapea a la escala temporal del gráfico)."""
    if not candles or len(candles) < 15:
        return {"trendlines": [], "levels": []}
    highs = [float(c.get("high") or c.get("h") or c.get("close") or 0) for c in candles]
    lows = [float(c.get("low") or c.get("l") or c.get("close") or 0) for c in candles]
    closes = [float(c.get("close") or c.get("c") or 0) for c in candles]
    if current_price is None:
        current_price = closes[-1] if closes else None

    trendlines = []
    # Solo miramos la parte reciente para líneas relevantes (últimas ~120 velas).
    look = min(len(candles), 120)
    off = len(candles) - look
    h_idx = _pivots(highs[off:], "high")
    l_idx = _pivots(lows[off:], "low")
    res = _fit_trendline([i for i in h_idx], highs[off:], "resistencia")
    sup = _fit_trendline([i for i in l_idx], lows[off:], "soporte")
    for line in (res, sup):
        if line:
            # Reajusta los índices al array completo.
            for pt in line["points"]:
                pt["index"] += off
            trendlines.append(line)

    levels = _horizontal_levels(highs, lows, closes, current_price)
    return {"trendlines": trendlines, "levels": levels}
