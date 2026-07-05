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
    # Proyecta la directriz hasta la ÚLTIMA vela (el "ahora"), para que la línea llegue al
    # borde derecho y el usuario vea dónde está el soporte/resistencia HOY, no dónde acabó
    # el último pivote.
    last = len(prices) - 1
    end_price = best["p1"] + best["slope"] * (last - best["i1"])
    return {
        "type": "trendline",
        "kind": want,
        "points": [
            {"index": int(best["i1"]), "price": round(float(best["p1"]), 2)},
            {"index": int(last), "price": round(float(end_price), 2)},
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


def _detect_candlesticks(candles):
    """Patrones de VELAS japonesas sobre las últimas velas (los más fiables: mates puras
    sobre OHLC). Devuelve el más reciente/relevante o None. Prioriza patrones de 2-3 velas."""
    if len(candles) < 3:
        return None

    def o(c): return float(c.get("open") or c.get("close") or 0)
    def h(c): return float(c.get("high") or c.get("close") or 0)
    def l(c): return float(c.get("low") or c.get("close") or 0)
    def cl_(c): return float(c.get("close") or 0)

    c2, c1, c0 = candles[-3], candles[-2], candles[-1]  # antepenúltima, penúltima, última
    body = abs(cl_(c0) - o(c0))
    rng = h(c0) - l(c0)
    if rng <= 0:
        return None
    upper = h(c0) - max(cl_(c0), o(c0))
    lower = min(cl_(c0), o(c0)) - l(c0)
    prev_trend_up = cl_(c1) > cl_(c2)     # contexto: veníamos subiendo
    prev_trend_dn = cl_(c1) < cl_(c2)

    # --- Patrones de 3 velas ---
    b1 = abs(cl_(c1) - o(c1)); b2 = abs(cl_(c2) - o(c2))
    if b2 > 0 and cl_(c2) < o(c2) and b1 < b2 * 0.5 and cl_(c0) > o(c0) and cl_(c0) > (o(c2) + cl_(c2)) / 2:
        return {"tipo": "estrella_amanecer", "nombre": "Estrella del amanecer", "sentido": "alcista",
                "descripcion": "Patrón alcista de 3 velas que confirma el fin de una tendencia bajista."}
    if b2 > 0 and cl_(c2) > o(c2) and b1 < b2 * 0.5 and cl_(c0) < o(c0) and cl_(c0) < (o(c2) + cl_(c2)) / 2:
        return {"tipo": "estrella_anochecer", "nombre": "Estrella del anochecer", "sentido": "bajista",
                "descripcion": "Patrón bajista de 3 velas que confirma el fin de una tendencia alcista."}

    # --- Patrones de 2 velas ---
    if cl_(c1) < o(c1) and cl_(c0) > o(c0) and cl_(c0) >= o(c1) and o(c0) <= cl_(c1):
        return {"tipo": "envolvente_alcista", "nombre": "Envolvente alcista", "sentido": "alcista",
                "descripcion": "Una vela verde grande envuelve por completo la roja anterior: cambio a alcista."}
    if cl_(c1) > o(c1) and cl_(c0) < o(c0) and o(c0) >= cl_(c1) and cl_(c0) <= o(c1):
        return {"tipo": "envolvente_bajista", "nombre": "Envolvente bajista", "sentido": "bajista",
                "descripcion": "Una vela roja grande envuelve por completo la verde anterior: cambio a bajista."}
    if cl_(c1) > o(c1) and cl_(c0) < o(c0) and o(c0) > h(c1) and cl_(c0) < (o(c1) + cl_(c1)) / 2:
        return {"tipo": "nube_oscura", "nombre": "Cubierta de nube oscura", "sentido": "bajista",
                "descripcion": "Vela bajista que abre por encima y cierra bajo la mitad de la verde previa: señal bajista."}

    # --- Patrones de 1 vela (martillo/estrella ANTES que doji: son más específicos) ---
    if body > 0 and lower >= body * 2 and upper <= body * 0.6 and prev_trend_dn:
        return {"tipo": "martillo", "nombre": "Martillo", "sentido": "alcista",
                "descripcion": "Cuerpo pequeño arriba con larga sombra inferior tras una caída: posible reversión alcista."}
    if body > 0 and upper >= body * 2 and lower <= body * 0.6 and prev_trend_up:
        return {"tipo": "estrella_fugaz", "nombre": "Estrella fugaz", "sentido": "bajista",
                "descripcion": "Cuerpo pequeño abajo con larga sombra superior tras una subida: posible reversión bajista."}
    if body >= rng * 0.9:
        alcista = cl_(c0) > o(c0)
        return {"tipo": "marubozu", "nombre": "Marubozu " + ("verde" if alcista else "rojo"),
                "sentido": "alcista" if alcista else "bajista",
                "descripcion": "Vela de cuerpo largo sin sombras: dominio total de " + ("compradores." if alcista else "vendedores.")}
    if body <= rng * 0.1:
        return {"tipo": "doji", "nombre": "Doji", "sentido": "indecision",
                "descripcion": "Apertura y cierre casi idénticos: indecisión entre compradores y vendedores."}
    return None


def _detect_head_shoulders(highs, lows, price_range):
    """Cabeza y Hombros (bajista) e invertido (alcista). 3 picos donde el central destaca
    y los hombros están a nivel similar. Devuelve dict o None."""
    if price_range <= 0:
        return None
    hi = _pivots(highs, "high")
    if len(hi) >= 3:
        a, b, c = hi[-3], hi[-2], hi[-1]
        ha, hb, hc = highs[a], highs[b], highs[c]
        if hb > ha and hb > hc and abs(ha - hc) / price_range < 0.05 and (hb - max(ha, hc)) / price_range > 0.03:
            return {"tipo": "cabeza_hombros", "nombre": "Cabeza y hombros", "sentido": "bajista",
                    "descripcion": "Tres picos con el central más alto: patrón clásico de reversión bajista. "
                    "La pérdida de la línea clavicular confirma la caída."}
    lo = _pivots(lows, "low")
    if len(lo) >= 3:
        a, b, c = lo[-3], lo[-2], lo[-1]
        la, lb, lc = lows[a], lows[b], lows[c]
        if lb < la and lb < lc and abs(la - lc) / price_range < 0.05 and (min(la, lc) - lb) / price_range > 0.03:
            return {"tipo": "hch_invertido", "nombre": "Hombro-cabeza-hombro invertido", "sentido": "alcista",
                    "descripcion": "Tres valles con el central más bajo: reversión alcista. La ruptura de la "
                    "clavicular confirma la subida."}
    return None


def _detect_pattern(trendlines, levels, closes, current_price):
    """Reconoce patrones sencillos a partir de las directrices y niveles ya detectados.
    Devuelve dict {nombre, descripcion, tipo} o None. Reglas geométricas, sin IA."""
    res = next((t for t in trendlines if t["kind"] == "resistencia"), None)
    sup = next((t for t in trendlines if t["kind"] == "soporte"), None)

    def slope(tl):
        p = tl["points"]
        dx = p[1]["index"] - p[0]["index"]
        return (p[1]["price"] - p[0]["price"]) / dx if dx else 0

    n = len(closes)
    recent = closes[-min(n, 40):]
    rng = (max(recent) - min(recent)) if recent else 0
    avg = sum(recent) / len(recent) if recent else 0
    flat_th = (avg * 0.0008) if avg else 0  # umbral de "casi horizontal"

    if res and sup:
        sr, ss = slope(res), slope(sup)
        conv = (sr < -flat_th and ss > flat_th)   # convergen
        # Triángulos
        if conv:
            return {"tipo": "triangulo", "nombre": "Triángulo simétrico",
                    "descripcion": "Máximos decrecientes y mínimos crecientes convergen. "
                    "Ruptura inminente; la dirección de la ruptura marca el siguiente movimiento."}
        if abs(sr) <= flat_th and ss > flat_th:
            return {"tipo": "triangulo_asc", "nombre": "Triángulo ascendente",
                    "descripcion": "Resistencia horizontal con mínimos crecientes. Sesgo alcista: "
                    "la ruptura de la resistencia suele impulsar al alza."}
        if abs(ss) <= flat_th and sr < -flat_th:
            return {"tipo": "triangulo_desc", "nombre": "Triángulo descendente",
                    "descripcion": "Soporte horizontal con máximos decrecientes. Sesgo bajista: "
                    "la pérdida del soporte suele acelerar la caída."}
        # Canales (paralelos)
        if sr > flat_th and ss > flat_th:
            return {"tipo": "canal_alcista", "nombre": "Canal alcista",
                    "descripcion": "Precio en tendencia alcista entre dos directrices paralelas. "
                    "Comprar cerca del soporte del canal, vender cerca de la resistencia."}
        if sr < -flat_th and ss < -flat_th:
            return {"tipo": "canal_bajista", "nombre": "Canal bajista",
                    "descripcion": "Tendencia bajista entre directrices paralelas. Rebotes hacia "
                    "la resistencia del canal suelen ser oportunidades de venta, no de compra."}
    # Consolidación lateral: rango estrecho reciente.
    if avg and rng / avg < 0.04:
        return {"tipo": "consolidacion", "nombre": "Consolidación lateral",
                "descripcion": "El precio se mueve en un rango estrecho (acumulación/distribución). "
                "Espera la ruptura del rango para confirmar dirección."}
    return None


def detect_lines(candles: List[Dict], current_price: float = None) -> Dict:
    """Punto de entrada. `candles` = lista de dicts con high/low/close (y opcionalmente
    fecha). Devuelve líneas de tendencia + niveles horizontales, en coordenadas de índice
    de vela (el frontend las mapea a la escala temporal del gráfico)."""
    if not candles or len(candles) < 15:
        return {"trendlines": [], "levels": [], "pattern": None, "candlestick": None, "zones": []}
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

    # Doble suelo / doble techo (dos pivotes al mismo nivel) — patrón de reversión clásico.
    pattern = None
    lo_all = _pivots(lows, "low")
    hi_all = _pivots(highs, "high")
    price_range = max(highs) - min(lows) if highs else 0
    if price_range > 0 and len(lo_all) >= 2:
        a, b = lo_all[-2], lo_all[-1]
        if abs(lows[a] - lows[b]) / price_range < 0.02 and (b - a) >= 5:
            pattern = {"tipo": "doble_suelo", "nombre": "Doble suelo",
                       "descripcion": "Dos mínimos al mismo nivel: el precio ha rebotado dos veces en "
                       "ese soporte. Patrón alcista de reversión si rompe el máximo intermedio."}
    if pattern is None and price_range > 0 and len(hi_all) >= 2:
        a, b = hi_all[-2], hi_all[-1]
        if abs(highs[a] - highs[b]) / price_range < 0.02 and (b - a) >= 5:
            pattern = {"tipo": "doble_techo", "nombre": "Doble techo",
                       "descripcion": "Dos máximos al mismo nivel: el precio ha sido rechazado dos "
                       "veces en esa resistencia. Patrón bajista si pierde el mínimo intermedio."}
    # Cabeza y hombros tiene prioridad sobre los patrones de directriz.
    if pattern is None:
        pattern = _detect_head_shoulders(highs, lows, price_range)
    # Si no hay doble suelo/techo ni H-C-H, prueba patrones de directrices.
    if pattern is None:
        pattern = _detect_pattern(trendlines, levels, closes, current_price)

    # Patrón de VELAS reciente (independiente del patrón chartista de estructura).
    candlestick = _detect_candlesticks(candles)

    # ZONAS de demanda/oferta: banda alrededor del soporte/resistencia horizontal más fuerte.
    zones = []
    band = price_range * 0.01 if price_range else 0
    for lv in levels[:2]:
        zones.append({
            "type": "zone",
            "role": "demanda" if lv["role"] == "soporte" else "oferta",
            "low": round(lv["price"] - band, 2),
            "high": round(lv["price"] + band, 2),
        })

    return {"trendlines": trendlines, "levels": levels, "pattern": pattern,
            "candlestick": candlestick, "zones": zones}
