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
    """Traza la directriz como haría un TRADER: uniendo los DOS SWINGS RECIENTES del tipo
    pedido (no los extremos globales, que cruzaban todo el gráfico). want='resistencia'
    une máximos recientes; 'soporte' une mínimos recientes. Devuelve dos puntos o None.

    Elige entre los últimos ~4 pivotes el par (reciente) que forma la recta con MÁS toques
    (pivotes que la línea roza) — una directriz con varios apoyos es más fiable que una
    que solo une dos puntos al azar. Solo mira estructura RECIENTE, no todo el histórico."""
    if len(idxs) < 2:
        return None
    tol = (max(prices) - min(prices)) * 0.02 or 1e-9
    # Solo pivotes de las ÚLTIMAS ~45 velas → directriz LOCAL reciente (no una diagonal
    # que cruza todo el histórico). Si hay muchos, nos quedamos con los últimos.
    last_i = len(prices) - 1
    recent = [i for i in idxs if i >= last_i - 45][-5:]
    if len(recent) < 2:
        recent = idxs[-3:]  # respaldo si no hay pivotes recientes suficientes
    best = None
    for a in range(len(recent)):
        for b in range(a + 1, len(recent)):
            i1, i2 = recent[a], recent[b]
            if i2 - i1 < 3:  # demasiado juntos → pendiente poco fiable
                continue
            p1, p2 = prices[i1], prices[i2]
            slope = (p2 - p1) / (i2 - i1)
            # Cuenta cuántos pivotes recientes ROZA la línea (apoyos) sin que la crucen mucho.
            touches = 0
            for k in recent:
                diff = prices[k] - (p1 + slope * (k - i1))
                if abs(diff) <= tol:
                    touches += 1
            # Preferimos: más toques y, a igualdad, la más RECIENTE (i2 mayor).
            score = (touches, i2)
            if best is None or score > best["score"]:
                best = {"score": score, "i1": i1, "p1": p1, "slope": slope}
    if not best:
        return None
    # Proyecta hasta la ÚLTIMA vela para ver dónde está el soporte/resistencia HOY.
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


def _lsq_slope(ys):
    """Pendiente por mínimos cuadrados de una serie (x = 0,1,2,...). Puro Python."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def _quad_curvature(ys):
    """Ajuste de parábola y = a·x² + b·x + c por mínimos cuadrados (ecuaciones normales,
    sin numpy). Devuelve 'a': si a > 0 la curva abre hacia ARRIBA => forma de 'U' (taza);
    si a <= 0 es plana o en 'V'/domo. Sirve para exigir un fondo cóncavo redondeado."""
    n = len(ys)
    if n < 3:
        return 0.0
    xs = list(range(n))
    Sx = sum(xs); Sx2 = sum(x * x for x in xs)
    Sx3 = sum(x ** 3 for x in xs); Sx4 = sum(x ** 4 for x in xs)
    Sy = sum(ys); Sxy = sum(x * y for x, y in zip(xs, ys))
    Sx2y = sum(x * x * y for x, y in zip(xs, ys))
    # Sistema 3x3 [a,b,c] resuelto por eliminación de Gauss.
    A = [[Sx4, Sx3, Sx2, Sx2y],
         [Sx3, Sx2, Sx,  Sxy],
         [Sx2, Sx,  n,   Sy]]
    for i in range(3):
        piv = A[i][i]
        if abs(piv) < 1e-12:
            return 0.0
        for j in range(i, 4):
            A[i][j] /= piv
        for k in range(3):
            if k != i:
                f = A[k][i]
                for j in range(i, 4):
                    A[k][j] -= f * A[i][j]
    return A[0][3]  # coeficiente 'a' (curvatura)


def _detect_cup_handle(closes, highs=None, lows=None, volumes=None):
    """Taza con asa (cup & handle, O'Neil) — detector RIGUROSO sobre highs/lows/closes.

    Ancla 5 pivotes: P0 borde izq., P1 fondo, P2 borde der., P3 techo del asa, P4 mínimo
    del asa. Aplica los umbrales O'Neil/Bulkowski y RECHAZA los falsos positivos:
      • V puntiaguda  -> exige fondo redondeado (>=5 velas en el tercio inferior, >=20%
                         del ancho) y curvatura de parábola a>0.
      • Doble suelo (W)-> descarta si dentro del basin del fondo hay un repunte por encima
                         de la mitad de la taza (dos valles con pico intermedio).
      • Sin asa       -> si tras P2 no hay consolidación válida (P3/P4), devuelve None.
      • 2ª pierna bajista -> 'halfway rule': P4 debe quedar en la MITAD SUPERIOR de la taza.
      • Cuña/canal    -> el asa debe ser corta (<=30 velas), estrecha (<=~15%) y de deriva
                         plana o bajista (sus máximos no ascienden).
    Devuelve dict con tipo/nombre/sentido/descripcion + 'puntos' (5 pivotes) y 'lineas'
    (arco, buy line, mitad de taza, canal del asa, objetivo), todo en index/price.
    """
    n = len(closes)
    if highs is None:
        highs = closes
    if lows is None:
        lows = closes
    if n < 45:                       # sin histórico mínimo no hay taza fiable
        return None

    # La taza dura 30..325 velas; basta con mirar las últimas ~360.
    W = min(n, 360)
    off = n - W
    H = highs[off:]; L = lows[off:]
    V = volumes[off:] if volumes else None
    m = len(H)

    hi = _pivots(H, "high", 3, 3)    # candidatos a bordes/techo (P0, P2, P3)
    if len(hi) < 2:
        return None

    best = None
    # P2 = borde derecho: debe dejar hueco para el asa (5..30 velas = 1..6 semanas) delante.
    for p2 in hi:
        after = m - 1 - p2
        if after < 5 or after > 30:              # duración del asa fuera de rango
            continue
        for p0 in hi:                            # P0 = borde izquierdo
            width = p2 - p0
            if width < 30 or width > 325:        # ancho de la taza (7..65 semanas)
                continue
            rim = max(H[p0], H[p2])
            # --- simetría de bordes ---
            if abs(H[p0] - H[p2]) / H[p0] > 0.05:            # bordes a nivel similar
                continue
            if H[p2] > H[p0] * 1.05 or H[p2] < H[p0] * 0.90:  # der. no supera >5% ni cae >10%
                continue
            # --- fondo P1 (mínimo absoluto de lows entre P0 y P2) ---
            seg = L[p0:p2 + 1]
            p1low = min(seg)
            p1 = p0 + seg.index(p1low)
            depth_abs = rim - p1low
            if depth_abs <= 0:
                continue
            depth = depth_abs / rim
            if not (0.12 <= depth <= 0.50):       # rechaza taza plana (<12%) o abismal (>50%)
                continue
            wide_base = depth > 0.33              # base ancha/laxa (solo mercados bajistas)
            # fondo centrado (no pegado a un borde) -> U, no medio-tazón
            if not (0.20 <= (p1 - p0) / width <= 0.80):
                continue
            # --- forma 'U' NO 'V': suelo redondeado ---
            lower_third = p1low + 0.33 * depth_abs
            nb = [i for i in range(p0, p2 + 1) if L[i] <= lower_third]
            if len(nb) < 5:                       # una V toca fondo en 1-2 velas
                continue
            if (nb[-1] - nb[0]) < 0.20 * width:   # el fondo debe abarcar >=20% del ancho
                continue
            midcup = p1low + 0.50 * depth_abs
            # DESCARTA doble suelo (W): un repunte por encima de la mitad DENTRO del basin
            # implica dos valles con pico intermedio, no un único fondo redondeado.
            if max(H[nb[0]:nb[-1] + 1]) > midcup:
                continue
            # curvatura: la parábola de los lows debe abrir hacia arriba (cóncava = U).
            if _quad_curvature(seg) <= 0:
                continue
            # --- ASA: desde justo tras P2 hasta el final de la ventana ---
            hstart = p2 + 1
            hh = H[hstart:]; hl = L[hstart:]
            if len(hl) < 3:                       # sin consolidación -> 'cup without handle'
                continue
            p3high = max(H[p2], max(hh))          # techo del asa ~ borde derecho (buy line)
            p3 = p2 if H[p2] >= max(hh) else hstart + hh.index(max(hh))
            p4low = min(hl)
            p4 = hstart + hl.index(p4low)
            # REGLA CLAVE 'halfway' (O'Neil/Bulkowski): P4 en la MITAD SUPERIOR de la taza.
            if p4low <= midcup:                   # si cae bajo la mitad -> reanudación bajista
                continue
            # profundidad del asa 5..15% (tol. 3..18%) y retroceso < 1/3 de la taza.
            hdepth = (p3high - p4low) / p3high
            if not (0.03 <= hdepth <= 0.18):
                continue
            if (p3high - p4low) >= (depth_abs / 3.0):
                continue
            # deriva del asa: sus máximos NO deben ascender (plana o ligeramente bajista).
            if _lsq_slope(hh) > rim * 0.002:      # tolerancia ~0.2%/vela; una cuña sube fuerte
                continue
            # --- tendencia previa alcista >=30% que desemboca en P0 (si hay histórico) ---
            gi = p0 + off
            if gi >= 20:
                prev = lows[max(0, gi - 60):gi]
                if prev:
                    base = min(prev)
                    if base > 0 and (H[p0] - base) / base < 0.30:
                        continue
            # --- volumen (opcional): seco en el asa; si sube más que en la taza, sospechoso ---
            if V:
                cv = V[p0:p2 + 1]; hv = V[hstart:]
                if cv and hv and (sum(hv) / len(hv)) > (sum(cv) / len(cv)):
                    continue
            # puntuación: preferimos taza en el centro del rango O'Neil (~22%) y más ancha.
            score = (1.0 - abs(depth - 0.22), width)
            if best is None or score > best[0]:
                best = (score, dict(p0=p0, p1=p1, p2=p2, p3=p3, p4=p4, rim=rim,
                                    p1low=p1low, p3high=p3high, p4low=p4low, midcup=midcup,
                                    depth=depth, depth_abs=depth_abs, hdepth=hdepth,
                                    wide=wide_base))
    if best is None:
        return None

    b = best[1]
    last = n - 1
    def gi(i):        # índice ventana -> índice del array completo
        return int(i + off)
    def pt(i, price):
        return {"index": gi(i), "price": round(float(price), 2)}

    pivote = max(b["rim"], b["p3high"])           # buy point = techo asa / borde derecho
    objetivo = pivote + b["depth_abs"]            # measure rule (Bulkowski): pivote + altura

    puntos = [
        {"label": "P0", "index": gi(b["p0"]), "price": round(float(H[b["p0"]]), 2)},  # borde izq.
        {"label": "P1", "index": gi(b["p1"]), "price": round(float(b["p1low"]), 2)},  # fondo
        {"label": "P2", "index": gi(b["p2"]), "price": round(float(H[b["p2"]]), 2)},  # borde der.
        {"label": "P3", "index": gi(b["p3"]), "price": round(float(b["p3high"]), 2)}, # techo asa
        {"label": "P4", "index": gi(b["p4"]), "price": round(float(b["p4low"]), 2)},  # min asa
    ]
    lineas = [
        # (1) arco inferior de la taza sobre los lows P0 -> P1 -> P2.
        {"tipo": "arco_taza", "points": [pt(b["p0"], b["rim"]), pt(b["p1"], b["p1low"]),
                                         pt(b["p2"], b["rim"])]},
        # (2) buy line / resistencia horizontal (pivote de ruptura).
        {"tipo": "resistencia", "kind": "buy_line",
         "points": [pt(b["p0"], pivote), pt(last, pivote)]},
        # (3) canal del asa: techo P3 -> mínimo P4 (deriva plana/bajista).
        {"tipo": "asa", "points": [{"index": gi(b["p3"]), "price": round(float(b["p3high"]), 2)},
                                   {"index": gi(b["p4"]), "price": round(float(b["p4low"]), 2)}]},
        # (4) línea de mitad de taza (guía de validez del asa: P4 debe quedar por encima).
        {"tipo": "mitad_taza", "points": [pt(b["p0"], b["midcup"]), pt(last, b["midcup"])]},
        # (5) objetivo (proyección): pivote + altura de la taza.
        {"tipo": "objetivo", "points": [pt(b["p2"], objetivo), pt(last, objetivo)]},
    ]

    nota = " Base ancha/laxa (profundidad >33%, típica de mercado bajista)." if b["wide"] else ""
    return {
        "tipo": "taza_asa", "nombre": "Taza con asa", "sentido": "alcista",
        "descripcion": (
            "Fondo redondeado en 'U' (taza) seguido de una pequeña consolidación de deriva "
            "plana/bajista en la mitad superior (asa). Patrón alcista de continuación (O'Neil). "
            "Compra en la ruptura del pivote %.2f con volumen >=1.4x la media de 50; objetivo "
            "%.2f (pivote + altura de la taza); stop bajo el mínimo del asa %.2f." % (
                round(pivote, 2), round(objetivo, 2), round(b["p4low"], 2)) + nota),
        "pivote": round(float(pivote), 2),
        "objetivo": round(float(objetivo), 2),
        "profundidad_taza": round(float(b["depth"]), 3),
        "profundidad_asa": round(float(b["hdepth"]), 3),
        "puntos": puntos,
        "lineas": lineas,
    }


def _detect_flat_base(closes):
    """Base plana / Caja de Darvas: consolidación estrecha y horizontal cerca de máximos
    tras una subida. Alcista en la ruptura del techo."""
    n = len(closes)
    if n < 25:
        return None
    base = closes[-15:]
    avg = sum(base) / len(base)
    rng = (max(base) - min(base)) / avg if avg else 1
    recent_high = max(closes[-60:]) if n >= 60 else max(closes)
    near_high = closes[-1] >= recent_high * 0.92
    prior = closes[-30:-15] if n >= 30 else []
    subio = bool(prior and (base[0] - prior[0]) / prior[0] > 0.05)
    if rng < 0.08 and near_high and subio:
        return {"tipo": "base_plana", "nombre": "Base plana / Caja de Darvas", "sentido": "alcista",
                "descripcion": "Consolidación estrecha y horizontal cerca de máximos tras una subida "
                "(caja de Darvas). Se compra en la ruptura del techo de la caja con volumen."}
    return None


def _detect_broadening(highs, lows):
    """Megáfono (ensanchamiento): máximos crecientes + mínimos decrecientes = volatilidad
    en expansión. Patrón a EVITAR (inestabilidad/distribución)."""
    hp = _pivots(highs, "high")
    lp = _pivots(lows, "low")
    if len(hp) >= 2 and len(lp) >= 2:
        if highs[hp[-1]] > highs[hp[-2]] and lows[lp[-1]] < lows[lp[-2]]:
            return {"tipo": "megafono", "nombre": "Megáfono (ensanchamiento)", "sentido": "bajista",
                    "descripcion": "Máximos crecientes y mínimos decrecientes: volatilidad en expansión "
                    "e indecisión. Patrón a EVITAR — suele indicar distribución/inestabilidad."}
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
        # Cuñas: ambas directrices en la MISMA dirección pero convergiendo.
        if sr > flat_th and ss > flat_th and ss > sr:  # ambas suben, soporte más empinado → converge
            return {"tipo": "cuna_ascendente", "nombre": "Cuña ascendente", "sentido": "bajista",
                    "descripcion": "Ambas directrices suben pero convergen: pese a las subidas, el impulso "
                    "se agota. Sesgo BAJISTA — suele romper a la baja."}
        if sr < -flat_th and ss < -flat_th and sr > ss:  # ambas bajan, resistencia más empinada → converge
            return {"tipo": "cuna_descendente", "nombre": "Cuña descendente", "sentido": "alcista",
                    "descripcion": "Ambas directrices bajan pero convergen: la caída pierde fuerza. "
                    "Sesgo ALCISTA — suele romper al alza."}
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
    # BANDERA / BANDERÍN: impulso fuerte reciente + consolidación breve y estrecha después.
    # Es una PAUSA en la tendencia (patrón de continuación), no una reversión.
    if pattern is None and len(closes) >= 25:
        pole = closes[-25:-8]          # el "mástil" (impulso)
        flag = closes[-8:]             # la consolidación reciente
        if pole and flag:
            pole_move = (pole[-1] - pole[0]) / pole[0] if pole[0] else 0
            flag_rng = (max(flag) - min(flag)) / (sum(flag) / len(flag)) if flag else 1
            if abs(pole_move) > 0.08 and flag_rng < 0.04:   # impulso >8% + consolidación <4%
                if pole_move > 0:
                    pattern = {"tipo": "bandera_alcista", "nombre": "Bandera alcista", "sentido": "alcista",
                               "descripcion": "Impulso alcista fuerte seguido de una pausa de consolidación. "
                               "Patrón de continuación: se espera ruptura al alza que reanude la subida."}
                else:
                    pattern = {"tipo": "bandera_bajista", "nombre": "Bandera bajista", "sentido": "bajista",
                               "descripcion": "Caída fuerte seguida de una pausa de consolidación. Patrón de "
                               "continuación: se espera ruptura a la baja que reanude el descenso."}

    # Taza con asa y base plana (favoritos de ruptura de máximos): prioridad alta.
    if pattern is None:
        pattern = _detect_cup_handle(closes, highs, lows)
    if pattern is None:
        pattern = _detect_flat_base(closes)
    # Cabeza y hombros tiene prioridad sobre los patrones de directriz.
    if pattern is None:
        pattern = _detect_head_shoulders(highs, lows, price_range)
    # Si no hay doble suelo/techo ni H-C-H, prueba patrones de directrices.
    if pattern is None:
        pattern = _detect_pattern(trendlines, levels, closes, current_price)
    # Megáfono (a evitar): último recurso, solo si no hay nada mejor.
    if pattern is None:
        pattern = _detect_broadening(highs, lows)

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
