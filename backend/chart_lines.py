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
    # Tres soldados blancos / tres cuervos negros: 3 velas del mismo color con cierres
    # progresivos y apertura dentro del cuerpo previo (impulso sostenido).
    up3 = (cl_(c2) > o(c2) and cl_(c1) > o(c1) and cl_(c0) > o(c0)
           and cl_(c0) > cl_(c1) > cl_(c2)
           and o(c1) <= cl_(c2) and o(c0) <= cl_(c1) and o(c1) >= o(c2) and o(c0) >= o(c1))
    if up3 and b1 > 0 and b2 > 0:
        return {"tipo": "tres_soldados", "nombre": "Tres soldados blancos", "sentido": "alcista",
                "descripcion": "Tres velas verdes consecutivas con cierres crecientes: impulso comprador sostenido, reversión/continuación alcista."}
    dn3 = (cl_(c2) < o(c2) and cl_(c1) < o(c1) and cl_(c0) < o(c0)
           and cl_(c0) < cl_(c1) < cl_(c2)
           and o(c1) >= cl_(c2) and o(c0) >= cl_(c1) and o(c1) <= o(c2) and o(c0) <= o(c1))
    if dn3 and b1 > 0 and b2 > 0:
        return {"tipo": "tres_cuervos", "nombre": "Tres cuervos negros", "sentido": "bajista",
                "descripcion": "Tres velas rojas consecutivas con cierres decrecientes: presión vendedora sostenida, reversión/continuación bajista."}

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
    # Harami: cuerpo pequeño CONTENIDO dentro del cuerpo grande anterior (color opuesto) →
    # pérdida de impulso, posible reversión (confirmar con la vela siguiente).
    if b1 > 0 and body <= b1 * 0.5 and max(o(c0), cl_(c0)) <= max(o(c1), cl_(c1)) and min(o(c0), cl_(c0)) >= min(o(c1), cl_(c1)):
        if cl_(c1) < o(c1) and cl_(c0) > o(c0) and prev_trend_dn:
            return {"tipo": "harami_alcista", "nombre": "Harami alcista", "sentido": "alcista",
                    "descripcion": "Vela verde pequeña contenida dentro de una roja grande tras una caída: se frena la presión vendedora, posible giro alcista."}
        if cl_(c1) > o(c1) and cl_(c0) < o(c0) and prev_trend_up:
            return {"tipo": "harami_bajista", "nombre": "Harami bajista", "sentido": "bajista",
                    "descripcion": "Vela roja pequeña contenida dentro de una verde grande tras una subida: se frena la presión compradora, posible giro bajista."}

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


def _eval_hch(sign, peak_vals, valley_vals, closes, atr, price_range):
    """Evalúa Cabeza y Hombros en un SENTIDO. Con sign=+1 busca el TECHO (HI/C/HD son
    máximos de `peak_vals`=highs, axilas mínimos de `valley_vals`=lows); con sign=-1 busca el
    SUELO/invertido (HI/C/HD mínimos de lows, axilas máximos de highs). Trabajando en el
    "espacio transformado" t = sign*precio, la geometría del invertido queda idéntica a la
    del techo (más extremo = mayor t), así una sola rutina sirve para ambos.
    Devuelve el dict de dibujo (pivotes/neckline/objetivo) o None."""
    n = len(peak_vals)
    if n < 30 or price_range <= 0:
        return None
    # Pivotes: para el techo picos=máximos, axilas=mínimos; invertido al revés.
    peaks = _pivots(peak_vals, "high" if sign > 0 else "low")
    valleys = _pivots(valley_vals, "low" if sign > 0 else "high")
    if len(peaks) < 3 or len(valleys) < 2:
        return None
    peaks = peaks[-9:]  # solo estructura RECIENTE (acota el bucle y prioriza lo relevante)

    def t(v):            # espacio transformado: cabeza = valor máximo
        return sign * v

    best = None
    best_key = None

    # Recorre triples de picos (HI, C, HD); C debe ser el pico más extremo de los tres.
    for ia in range(len(peaks) - 2):
        for ib in range(ia + 1, len(peaks) - 1):
            for ic in range(ib + 1, len(peaks)):
                HI, C, HD = peaks[ia], peaks[ib], peaks[ic]
                # (0) separación mínima temporal → evita picos pegados (poco fiables).
                if (C - HI) < 3 or (HD - C) < 3:
                    continue
                pHI, pC, pHD = peak_vals[HI], peak_vals[C], peak_vals[HD]
                tHI, tC, tHD = t(pHI), t(pC), t(pHD)
                # (1) La CABEZA debe ser el pico más extremo (estrictamente).
                if not (tC > tHI and tC > tHD):
                    continue
                # Axilas: pivote-valle más extremo (más profundo) a cada lado de la Cabeza.
                left = [v for v in valleys if HI < v < C]
                right = [v for v in valleys if C < v < HD]
                if not left or not right:
                    continue
                A1 = min(left, key=lambda v: t(valley_vals[v]))
                A2 = min(right, key=lambda v: t(valley_vals[v]))
                pA1, pA2 = valley_vals[A1], valley_vals[A2]

                # --- CRITERIO 1: prominencia de la Cabeza (>=3% sobre el hombro más alto).
                higher_t = max(tHI, tHD)
                ref_price = pHI if tHI >= tHD else pHD   # hombro de referencia (el más "difícil")
                prom = tC - higher_t                     # prominencia en magnitud de precio (>0)
                if prom < 0.03 * abs(ref_price):
                    continue  # <3% → es Triple Techo/Suelo, no Cabeza y Hombros

                # --- CRITERIO 2: simetría de altura de hombros (<5% del nivel de la Cabeza).
                if abs(pHI - pHD) / abs(pC) >= 0.05:
                    continue
                # equivalente estricto: diferencia de hombros < 1/3 de la prominencia.
                if abs(pHI - pHD) >= prom / 3.0:
                    continue

                # --- CRITERIO 3: simetría temporal (ratio HI->C / C->HD en 0.80-1.20).
                ratio_t = (C - HI) / (HD - C)
                if not (0.80 <= ratio_t <= 1.20):
                    continue

                # --- Neckline y altura del patrón (proyección vertical de C a la clavicular).
                def nl_at(x):
                    if A2 == A1:
                        return pA1
                    return pA1 + (pA2 - pA1) / (A2 - A1) * (x - A1)

                altura = abs(pC - nl_at(C))
                if altura <= 0:
                    continue

                # --- CRITERIO 5a: amplitud significativa (>= 2*ATR14) para descartar ruido.
                if atr > 0 and altura < 2.0 * atr:
                    continue

                # --- CRITERIO 4: axilas cercanas / neckline poco inclinada (<30% de la altura).
                if abs(pA1 - pA2) >= 0.30 * altura:
                    continue

                # Ambos hombros por encima (techo) / por debajo (invertido) de la neckline.
                if sign * (pHI - nl_at(HI)) <= 0 or sign * (pHD - nl_at(HD)) <= 0:
                    continue

                # --- CRITERIO 5b: valles REALES → cada axila retrocede >=30% de la altura
                # respecto al pico adyacente (descarta techo/suelo REDONDEADO sin axilas).
                if (min(tHI, tC) - t(pA1)) < 0.30 * altura:
                    continue
                if (min(tHD, tC) - t(pA2)) < 0.30 * altura:
                    continue

                # --- DISCRIMINADOR de tendencia previa: el techo exige tendencia ALCISTA hacia
                # HI/C; el invertido, BAJISTA. (Umbral 7% relajado.)
                lb = 20
                pre = [t(closes[k]) for k in range(max(0, HI - lb), HI)]
                if not pre:
                    continue
                pre_start = min(pre)  # arranque de la tendencia en espacio transformado
                if (t(closes[HI]) - pre_start) < 0.07 * abs(pre_start):
                    continue

                # --- CRITERIO 7: confirmación por RUPTURA de la neckline tras el HD, con filtro
                # anti-latigazo (penetración > 0.5-1.0% del precio o > 0.5*ATR).
                brk = None
                for k in range(HD + 1, len(closes)):
                    filt = max(0.005 * closes[k], 0.5 * atr)
                    if sign * (nl_at(k) - closes[k]) > filt:  # cierre más allá de la clavicular
                        brk = k
                        break
                confirmado = brk is not None

                # Puntuación: preferimos patrón CONFIRMADO, luego el más RECIENTE, luego el más
                # simétrico (ratio~1 y hombros a la misma altura).
                sym = abs(1.0 - ratio_t) + abs(pHI - pHD) / abs(pC)
                key = (1 if confirmado else 0, HD, -sym)
                if best_key is None or key > best_key:
                    best_key = key
                    best = {
                        "HI": HI, "A1": A1, "C": C, "A2": A2, "HD": HD,
                        "pHI": pHI, "pA1": pA1, "pC": pC, "pA2": pA2, "pHD": pHD,
                        "altura": altura, "brk": brk, "confirmado": confirmado,
                        "nl_at": nl_at,
                    }

    if best is None:
        return None

    # VIGENCIA: un H&S de techo cuyo precio ha recuperado SOBRE la clavicular (o un invertido
    # que ha vuelto por DEBAJO) está invalidado — el precio anuló la tesis. Descartar.
    nl_last = best["nl_at"](len(closes) - 1)
    cur = closes[-1]
    if sign > 0 and cur > nl_last:      # techo (bajista) pero precio de nuevo sobre la neckline
        return None
    if sign < 0 and cur < nl_last:      # invertido (alcista) pero precio de nuevo bajo la neckline
        return None

    nl_at = best["nl_at"]
    HI, A1, C, A2, HD = best["HI"], best["A1"], best["C"], best["A2"], best["HD"]
    altura = best["altura"]
    brk = best["brk"]

    # ----- PUNTOS DE DIBUJO -----
    pivotes = [
        {"label": "HI", "index": int(HI), "price": round(float(best["pHI"]), 2)},
        {"label": "A1", "index": int(A1), "price": round(float(best["pA1"]), 2)},
        {"label": "C",  "index": int(C),  "price": round(float(best["pC"]), 2)},
        {"label": "A2", "index": int(A2), "price": round(float(best["pA2"]), 2)},
        {"label": "HD", "index": int(HD), "price": round(float(best["pHD"]), 2)},
    ]
    x_end = brk if brk is not None else len(closes) - 1
    neckline = [
        {"index": int(A1), "price": round(float(best["pA1"]), 2)},
        {"index": int(x_end), "price": round(float(nl_at(x_end)), 2)},
    ]
    objetivo = None
    if brk is not None:
        target_price = nl_at(brk) - sign * altura   # techo: restar h; invertido: sumar h
        objetivo = {
            "ruptura": {"index": int(brk), "price": round(float(closes[brk]), 2)},
            "target":  {"index": int(brk), "price": round(float(target_price), 2)},
            "altura":  round(float(altura), 2),
        }

    return {
        "confirmado": best["confirmado"],
        "puntos": {"pivotes": pivotes, "neckline": neckline, "objetivo": objetivo},
    }


def _detect_head_shoulders(highs, lows, closes, price_range):
    """Cabeza y Hombros (techo, bajista) e invertido (suelo, alcista). Detector de REVERSIÓN
    de 5 pivotes alternos (HI, A1, C, A2, HD) con validación geométrica completa (Bulkowski):
    prominencia de la Cabeza >=3%, hombros simétricos (<5%), simetría temporal (0.8-1.2),
    axilas reales (>=30% de la altura) con neckline poco inclinada, altura >=2*ATR, tendencia
    previa coherente y, si existe, ruptura confirmada de la clavicular con objetivo. Rechaza
    triple techo/suelo, redondeado, doble techo/suelo, canales/cuñas y 3 picos aleatorios."""
    if price_range <= 0 or len(closes) < 30:
        return None
    atr = _atr(highs, lows, closes, 14)

    variantes = (
        (1,  highs, lows, "cabeza_hombros", "Cabeza y hombros", "bajista",
         "Tres máximos con la Cabeza claramente por encima de los dos hombros (simétricos) "
         "tras una tendencia alcista: reversión BAJISTA."),
        (-1, lows, highs, "hch_invertido", "Hombro-cabeza-hombro invertido", "alcista",
         "Tres mínimos con la Cabeza claramente por debajo de los dos hombros (simétricos) "
         "tras una tendencia bajista: reversión ALCISTA."),
    )
    for sign, pv, vv, tipo, nombre, sentido, base_desc in variantes:
        res = _eval_hch(sign, pv, vv, closes, atr, price_range)
        if not res:
            continue
        if res["confirmado"]:
            confirm = (" La clavicular ya se ha PERDIDO: patrón confirmado; objetivo = precio "
                       "de ruptura −/+ la altura del patrón.")
        else:
            confirm = (" Formación aún NO confirmada: espera el cierre más allá de la línea "
                       "clavicular (con filtro > 0.5% o 0.5·ATR) para validarla.")
        return {
            "tipo": tipo, "nombre": nombre, "sentido": sentido,
            "descripcion": base_desc + confirm,
            "confirmado": res["confirmado"],
            "puntos": res["puntos"],
        }
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


def _linreg_slope(ys):
    """Pendiente de regresión lineal (mínimos cuadrados) de `ys` sobre x=0..n-1."""
    n = len(ys)
    if n < 2:
        return 0.0
    xm = (n - 1) / 2.0
    ym = sum(ys) / n
    num = sum((i - xm) * (ys[i] - ym) for i in range(n))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den if den else 0.0


def _validar_caja_darvas(t, techo, closes, highs, lows, volumes, n):
    """Valida una caja de Darvas cuyo TECHO arranca en la vela `t` (high[t]) y devuelve el
    patrón + puntos de dibujo, o None si incumple algún criterio. Umbrales O'Neil/Darvas."""
    BUF = 0.0015     # 0.15%: margen de ruptura "decisiva"
    TOL = 0.015      # 1.5%: tolerancia de "toque" a techo/suelo
    WICK = 0.02      # 2%: mecha máxima tolerada por encima del techo

    brk = None
    e = n - 1
    for j in range(t + 1, n):
        if closes[j] > techo * (1 + BUF):
            brk = j
            e = j - 1
            break
    right = brk if brk is not None else n - 1
    if right < n - 6:                       # el patrón debe ser ACTUAL
        return None

    N = e - t + 1
    if N < 15 or N > 55:
        return None

    box_h = highs[t:e + 1]
    box_l = lows[t:e + 1]
    box_c = closes[t:e + 1]
    if max(box_h) > techo * (1 + WICK):
        return None

    # Regla Darvas del suelo (4 velas): low[b] mínimo seguido de 3 mínimos crecientes.
    suelo = None
    b = None
    for k in range(t + 1, e - 2):
        lo = lows[k]
        if k + 3 <= e and lows[k + 1] > lo and lows[k + 2] > lo and lows[k + 3] > lo:
            if suelo is None or lo < suelo:
                suelo = lo
                b = k
    if b is None or suelo >= techo:
        return None

    depth = (techo - suelo) / techo
    if depth > 0.15:
        return None

    prior = closes[max(0, t - 60):t]
    if len(prior) < 20:
        return None
    if closes[t] < min(prior) * 1.20:
        return None
    if _linreg_slope(prior) <= 0:
        return None

    if abs(_linreg_slope(box_h)) / techo >= 0.003:   # techo inclinado -> bandera
        return None
    if abs(_linreg_slope(box_l)) / suelo >= 0.003:   # suelo no plano -> taza
        return None

    q = max(2, len(box_h) // 4)
    if abs(max(box_h[:q]) - max(box_h[-q:])) / techo >= 0.05:
        return None
    if abs(min(box_l[:q]) - min(box_l[-q:])) / suelo >= 0.05:
        return None

    ancho_ini = max(box_h[:q]) - min(box_l[:q])
    ancho_fin = max(box_h[-q:]) - min(box_l[-q:])
    if ancho_ini > 0:
        if ancho_fin < 0.6 * ancho_ini:                     # se estrecha -> triángulo/cuña
            return None
        if abs(ancho_fin - ancho_ini) / ancho_ini > 0.30:   # no paralelas
            return None

    toques_techo = [i for i in range(t, e + 1) if highs[i] >= techo * (1 - TOL)]
    toques_suelo = [i for i in range(t, e + 1) if lows[i] <= suelo * (1 + TOL)]
    if len(toques_techo) < 2 or len(toques_suelo) < 2:
        return None
    for c in box_c:
        if c > techo * 1.005 or c < suelo * 0.995:
            return None

    vol_note = ""
    if volumes and len(volumes) == n:
        box_vol = volumes[t:e + 1]
        prev_vol = volumes[max(0, t - 60):t]
        if prev_vol and box_vol:
            if sum(box_vol) / len(box_vol) >= 0.9 * (sum(prev_vol) / len(prev_vol)):
                return None    # sin 'dry-up' de volumen no es base plana O'Neil
        if brk is not None:
            m50 = volumes[max(0, brk - 50):brk]
            if m50 and volumes[brk] < 1.4 * (sum(m50) / len(m50)):
                vol_note = " Aviso: la ruptura NO va con expansión de volumen (posible falsa ruptura)."

    if brk is not None:
        estado = ("Ruptura confirmada: cierre %.2f sobre el techo %.2f." % (closes[brk], techo))
        if closes[brk] > techo * 1.05:
            estado += " Precio ya >5%% sobre el pivote: entrada descartada por 'chasing'."
    else:
        estado = "Caja en formación; gatillo de compra en cierre > %.2f (pivote), stop bajo %.2f." % (techo, suelo)

    puntos = {
        "techo": [{"index": int(t), "price": round(float(techo), 2)},
                  {"index": int(right), "price": round(float(techo), 2)}],
        "suelo": [{"index": int(b), "price": round(float(suelo), 2)},
                  {"index": int(right), "price": round(float(suelo), 2)}],
        "toques_techo": [{"index": int(i), "price": round(float(highs[i]), 2)} for i in toques_techo],
        "toques_suelo": [{"index": int(i), "price": round(float(lows[i]), 2)} for i in toques_suelo],
        "pivote_compra": round(float(techo), 2),
        "stop": round(float(suelo), 2),
        "ruptura": ({"index": int(brk), "price": round(float(closes[brk]), 2)} if brk is not None else None),
    }

    return {
        "tipo": "base_plana",
        "nombre": "Base plana / Caja de Darvas",
        "sentido": "alcista",
        "descripcion": ("Rectángulo horizontal de consolidación (caja de Darvas) tras un avance alcista: "
                        "techo y suelo planos y paralelos, profundidad %.0f%%, %d velas. Patrón de "
                        "CONTINUACIÓN alcista; se compra en la ruptura del techo con volumen. %s%s"
                        % (depth * 100, N, estado, vol_note)),
        "puntos": puntos,
    }


def _detect_flat_base(closes, highs=None, lows=None, volumes=None):
    """Base plana / Caja de Darvas: rectángulo estrecho y horizontal cerca de máximos tras
    una subida (CONTINUACIÓN alcista). Aplica la regla Darvas de 4 velas al techo y al suelo
    y valida contexto/planitud/profundidad/volumen; rechaza taza, V, bandera, triángulo/cuña,
    base profunda y distribución. Devuelve dict (con puntos de dibujo) o None."""
    n = len(closes)
    if n < 25:
        return None
    if highs is None:
        highs = closes
    if lows is None:
        lows = closes

    look = min(n, 60)
    seg_start = n - look
    hist_high = max(highs[max(0, n - 200):])

    for t in range(seg_start, n - 3):
        hi = highs[t]
        if hi < hist_high * 0.94:
            continue
        prev = highs[max(0, t - 5):t]
        if prev and hi < max(prev):
            continue
        if not (highs[t + 1] < hi and highs[t + 2] < hi and highs[t + 3] < hi):
            continue
        res = _validar_caja_darvas(t, hi, closes, highs, lows, volumes, n)
        if res:
            return res
    return None


def _alternating_swings(highs, lows, left: int = 3, right: int = 3):
    """Secuencia ALTERNANTE de pivotes H-L-H-L... (colapsa consecutivos del mismo tipo al más
    extremo). Devuelve tuplas (index, 'H'/'L', price)."""
    hp = [(i, "H", highs[i]) for i in _pivots(highs, "high", left, right)]
    lp = [(i, "L", lows[i]) for i in _pivots(lows, "low", left, right)]
    piv = sorted(hp + lp, key=lambda t: t[0])
    seq = []
    for p in piv:
        if not seq:
            seq.append(p)
        elif p[1] == seq[-1][1]:
            if (p[1] == "H" and p[2] > seq[-1][2]) or (p[1] == "L" and p[2] < seq[-1][2]):
                seq[-1] = p
        else:
            seq.append(p)
    return seq


def _monotonic(prices, direction: str, margin: float) -> bool:
    """HH crecientes ('up') o LL decrecientes ('down') con margen mínimo. Tolera 1 violación."""
    if direction == "up":
        if prices[-1] - prices[0] < margin:
            return False
        bad = sum(1 for k in range(1, len(prices)) if prices[k] < prices[k - 1] - 0.5 * margin)
    else:
        if prices[0] - prices[-1] < margin:
            return False
        bad = sum(1 for k in range(1, len(prices)) if prices[k] > prices[k - 1] + 0.5 * margin)
    return bad <= 1


def _detect_broadening(highs, lows, closes=None, recent: int = 140):
    """Megáfono / ensanchamiento (broadening) y variantes. Volatilidad CRECIENTE: dos rectas
    DIVERGENTES (cono abierto a la derecha, apex a la izquierda). Rechaza triángulo (convergen),
    canal/bandera (paralelas), cuña clásica y ruido (<5 pivotes, R²<0.85, no monótonos)."""
    n = len(highs)
    if n < 15:
        return None
    if closes is None:
        closes = [(highs[i] + lows[i]) / 2 for i in range(n)]

    off = max(0, n - recent)
    H, L, C = highs[off:], lows[off:], closes[off:]
    m = len(H)
    if m < 15:
        return None

    seq = _alternating_swings(H, L)
    if len(seq) < 5:
        return None
    seq = seq[-9:]
    if len(seq) < 5:
        return None
    hi_piv = [(i, pr) for (i, _t, pr) in seq if _t == "H"]
    lo_piv = [(i, pr) for (i, _t, pr) in seq if _t == "L"]
    if len(hi_piv) < 2 or len(lo_piv) < 2:
        return None
    if len(hi_piv) + len(lo_piv) < 5:
        return None
    if max(len(hi_piv), len(lo_piv)) < 3:
        return None

    price = sum(C) / m
    atr = _atr(H, L, C, 14) or (price * 0.01)
    margin = max(0.005 * price, 0.3 * atr)

    hh = [pr for _i, pr in hi_piv]
    ll = [pr for _i, pr in lo_piv]
    if not _monotonic(hh, "up", margin):
        return None
    if not _monotonic(ll, "down", margin):
        return None

    xs_h = [i for i, _pr in hi_piv]; ys_h = [pr for _i, pr in hi_piv]
    xs_l = [i for i, _pr in lo_piv]; ys_l = [pr for _i, pr in lo_piv]
    b_s, a_s, r2_s = _linreg(xs_h, ys_h)
    b_i, a_i, r2_i = _linreg(xs_l, ys_l)

    if len(hi_piv) >= 3 and r2_s < 0.85:
        return None
    if len(lo_piv) >= 3 and r2_i < 0.85:
        return None

    def sup_y(x): return a_s + b_s * x
    def inf_y(x): return a_i + b_i * x

    x_first = min(xs_h + xs_l)
    x_last = max(xs_h + xs_l)
    if x_last - x_first < 15:
        return None

    w_first = sup_y(x_first) - inf_y(x_first)
    w_last = sup_y(x_last) - inf_y(x_last)
    if w_first <= 0 or w_last <= 0:
        return None
    ratio = w_last / w_first
    if ratio < 1.3:
        return None

    xs_all = sorted(set(xs_h + xs_l))
    if len(xs_all) >= 2:
        x_pen = xs_all[-2]
        w_pen = sup_y(x_pen) - inf_y(x_pen)
        if not (w_pen > w_first * 1.15):
            return None

    denom = b_s - b_i
    if denom == 0:
        return None
    x_apex = (a_i - a_s) / denom
    if x_apex >= x_first:
        return None

    tol_line = max(0.02 * price, 1.0 * atr)
    pen_tol = 0.5 * atr
    for i, pr in hi_piv:
        if abs(pr - sup_y(i)) > tol_line:
            return None
        if pr < inf_y(i) - pen_tol:
            return None
    for i, pr in lo_piv:
        if abs(pr - inf_y(i)) > tol_line:
            return None
        if pr > sup_y(i) + pen_tol:
            return None

    def near_flat(a, b):
        return abs(a) < 0.1 * abs(b) if b != 0 else False

    if b_s > 0 and b_i < 0:
        if near_flat(b_s, b_i):
            variante = "angulo_recto_desc"
        elif near_flat(b_i, b_s):
            variante = "angulo_recto_asc"
        else:
            ratio_sl = abs(b_s) / abs(b_i) if b_i != 0 else 999
            variante = "simetrico" if 0.5 <= ratio_sl <= 2.0 else "asimetrico"
    elif b_s > 0 and b_i > 0:
        variante = "cuna_ensanchada_asc"
    elif b_s < 0 and b_i < 0:
        variante = "cuna_ensanchada_desc"
    else:
        return None

    pre = C[:x_first] if x_first > 0 else []
    prev_up = bool(pre) and (C[x_first] - pre[0]) / (abs(pre[0]) or 1) > 0.10
    prev_dn = bool(pre) and (C[x_first] - pre[0]) / (abs(pre[0]) or 1) < -0.10

    if variante == "cuna_ensanchada_asc":
        sentido = "bajista"
        desc = ("Cuña ENSANCHADA ascendente: ambas directrices suben y DIVERGEN. Pese a la apariencia "
                "alcista, sesgo BAJISTA — suele resolverse a la baja.")
        nombre = "Cuña ensanchada ascendente"
    elif variante == "cuna_ensanchada_desc":
        sentido = "alcista"
        desc = ("Cuña ENSANCHADA descendente: ambas directrices bajan y DIVERGEN. Sesgo ALCISTA — suele "
                "resolverse al alza.")
        nombre = "Cuña ensanchada descendente"
    elif variante in ("angulo_recto_asc", "angulo_recto_desc"):
        sentido = "bajista" if prev_up else ("alcista" if prev_dn else "bilateral")
        nombre = "Ensanchamiento de ángulo recto"
        desc = ("Megáfono de ángulo recto: una directriz casi horizontal y la otra inclinada; volatilidad "
                "creciente. Bilateral: la dirección la confirma el cierre de ruptura.")
    else:
        if prev_up:
            sentido = "bajista"
            desc = ("Megáfono (BROADENING TOP): máximos crecientes y mínimos decrecientes tras una subida; "
                    "volatilidad en expansión y distribución. Reversal con ligero sesgo BAJISTA.")
        elif prev_dn:
            sentido = "alcista"
            desc = ("Megáfono (BROADENING BOTTOM): oscilaciones cada vez más amplias tras una caída. Sesgo "
                    "ALCISTA.")
        else:
            sentido = "bilateral"
            desc = ("Megáfono simétrico: dos directrices divergentes (volatilidad creciente). BILATERAL casi "
                    "neutro; la ruptura confirma el lado. A EVITAR sin confirmación.")
        nombre = "Megáfono simétrico" if variante == "simetrico" else "Megáfono asimétrico"

    def _line(kind, slope, yfun):
        return {
            "type": "trendline", "kind": kind,
            "points": [
                {"index": int(x_first + off), "price": round(float(yfun(x_first)), 2)},
                {"index": int(n - 1),         "price": round(float(yfun(m - 1)), 2)},
            ],
            "direction": "alcista" if slope > 0 else "bajista",
        }

    trendlines = [_line("resistencia", b_s, sup_y), _line("soporte", b_i, inf_y)]
    seg = range(x_first, x_last + 1)
    altura = max(H[i] for i in seg) - min(L[i] for i in seg)

    return {
        "tipo": "megafono", "nombre": nombre + " (ensanchamiento)", "sentido": sentido,
        "descripcion": desc, "trendlines": trendlines,
        "meta": {"variante": variante, "ratio_divergencia": round(ratio, 2),
                 "altura": round(float(altura), 2), "span": int(x_last - x_first)},
    }


def _alternating_pivots(highs, lows, left: int = 3, right: int = 3):
    """Como _alternating_swings pero devuelve etiquetas 'high'/'low' (para el detector triple)."""
    hi = [(i, "high", highs[i]) for i in _pivots(highs, "high", left, right)]
    lo = [(i, "low", lows[i]) for i in _pivots(lows, "low", left, right)]
    piv = sorted(hi + lo, key=lambda p: p[0])
    seq = []
    for p in piv:
        if seq and seq[-1][1] == p[1]:
            prev = seq[-1]
            mejor = (p[2] >= prev[2]) if p[1] == "high" else (p[2] <= prev[2])
            if mejor:
                seq[-1] = p
        else:
            seq.append(p)
    return seq


def _validar_triple(seq, start, lado, highs, lows, closes,
                    tol_ig=0.03, tol_nk=0.05, retro_min=0.03, retro_max=0.33,
                    alt_min=0.03, tend_min=0.15, ancho_min=15):
    """Valida 5 pivotes A-B-A-B-A como triple techo/suelo. Rechaza HCH, doble, rectángulo,
    triángulo/cuña, V y ruido. Devuelve el dict del patrón (con puntos de dibujo) o None."""
    win = seq[start:start + 5]
    (i1, _, e1), (j1, _, c1), (i2, _, e2), (j2, _, c2), (i3, _, e3) = win
    extremos = [e1, e2, e3]
    contras = [c1, c2]
    if min(extremos) <= 0 or min(contras) <= 0:
        return None

    if max(extremos) / min(extremos) - 1 > tol_ig:
        return None
    ext_media = sum(extremos) / 3.0
    con_media = sum(contras) / 2.0

    lat = (e1 + e3) / 2.0
    if lado == "techo":
        if (e2 - lat) / lat > 0.03:
            return None
    else:
        if (lat - e2) / lat > 0.03:
            return None

    if abs(c1 - c2) / con_media > tol_nk:
        return None
    pend = (c2 - c1) / max(j2 - j1, 1)
    if abs(pend) / con_media > 0.005:
        return None

    for c in contras:
        retro = (ext_media - c) / ext_media if lado == "techo" else (c - ext_media) / ext_media
        if retro < retro_min or retro > retro_max:
            return None

    if i3 - i1 < ancho_min:
        return None
    d1, d2 = i2 - i1, i3 - i2
    if d1 <= 0 or d2 <= 0 or not (1.0 / 3.0 <= d2 / d1 <= 3.0):
        return None

    H = abs(ext_media - con_media)
    if H / ext_media < alt_min:
        return None

    ini = max(0, i1 - 120)
    if i1 - ini < 10:
        return None
    if lado == "techo":
        base = min(lows[ini:i1])
        if base <= 0 or (e1 - base) / base < tend_min:
            return None
    else:
        base = max(highs[ini:i1])
        if base <= 0 or (base - e1) / base < tend_min:
            return None

    mismo = "high" if lado == "techo" else "low"
    for pos in (start - 1, start + 5):
        if 0 <= pos < len(seq):
            v = seq[pos]
            if v[1] == mismo and abs(v[2] - ext_media) / ext_media <= tol_ig:
                return None

    neckline = min(contras) if lado == "techo" else max(contras)
    margen = neckline * 0.005
    ruptura = None
    for k in range(i3 + 1, len(closes)):
        if lado == "techo" and closes[k] < neckline - margen:
            ruptura = {"index": int(k), "price": round(float(closes[k]), 2)}
            break
        if lado == "suelo" and closes[k] > neckline + margen:
            ruptura = {"index": int(k), "price": round(float(closes[k]), 2)}
            break
    confirmado = ruptura is not None
    if not confirmado:                       # solo triples CONFIRMADOS (evita 'pendientes' prematuros)
        return None
    cur = closes[-1]                         # y aún VIGENTES: el precio no ha vuelto al otro lado
    if lado == "techo" and cur > neckline:   # techo: si recupera sobre la neckline, invalidado
        return None
    if lado == "suelo" and cur < neckline:   # suelo: si pierde la neckline, invalidado
        return None
    objetivo = round(float(neckline - H if lado == "techo" else neckline + H), 2)

    tags = ["P1", "V1", "P2", "V2", "P3"] if lado == "techo" else ["V1", "P1", "V2", "P2", "V3"]
    pivotes = [{"index": int(p[0]), "price": round(float(p[2]), 2), "punto": t}
               for p, t in zip(win, tags)]
    nivel_ext = round(float(ext_media), 2)
    linea_extremos = {"type": "trendline", "kind": "resistencia" if lado == "techo" else "soporte",
                      "points": [{"index": int(i1), "price": nivel_ext}, {"index": int(i3), "price": nivel_ext}]}
    fin_nk = ruptura["index"] if ruptura else len(closes) - 1
    linea_neckline = {"type": "trendline", "kind": "neckline",
                      "points": [{"index": int(j1), "price": round(float(neckline), 2)},
                                 {"index": int(fin_nk), "price": round(float(neckline), 2)}]}

    if lado == "techo":
        tipo, nombre, sentido = "triple_techo", "Triple techo", "bajista"
        desc = ("Tres máximos al mismo nivel separados por dos mínimos: rechazado tres veces en la "
                "resistencia. Reversión BAJISTA que se confirma al cerrar bajo la neckline. Objetivo = "
                "neckline - altura.")
    else:
        tipo, nombre, sentido = "triple_suelo", "Triple suelo", "alcista"
        desc = ("Tres mínimos al mismo nivel separados por dos máximos: rebotó tres veces en el soporte. "
                "Reversión ALCISTA que se confirma al cerrar sobre la neckline. Objetivo = neckline + altura.")
    if not confirmado:
        desc += " Patrón aún PENDIENTE: falta el cierre de ruptura para confirmar."

    return {
        "tipo": tipo, "nombre": nombre, "sentido": sentido, "descripcion": desc,
        "confirmado": confirmado, "pivotes": pivotes,
        "lineas": [linea_extremos, linea_neckline], "ruptura": ruptura,
        "objetivo": objetivo, "altura": round(float(H), 2),
    }


def _detect_triple_top_bottom(highs, lows, closes):
    """TRIPLE TECHO / TRIPLE SUELO (espejo). Busca la ventana más reciente de 5 pivotes
    alternados A-B-A-B-A y la valida. Devuelve el dict con puntos de dibujo o None."""
    n = len(closes)
    if n < 30:
        return None
    seq = _alternating_pivots(highs, lows)
    if len(seq) < 5:
        return None
    for start in range(len(seq) - 5, -1, -1):
        win = seq[start:start + 5]
        if win[-1][0] < n - 70:              # el 3er extremo debe ser RECIENTE (patrón vigente)
            continue
        tipos = [p[1] for p in win]
        lado = None
        if tipos == ["high", "low", "high", "low", "high"]:
            lado = "techo"
        elif tipos == ["low", "high", "low", "high", "low"]:
            lado = "suelo"
        if lado:
            r = _validar_triple(seq, start, lado, highs, lows, closes)
            if r:
                return r
    return None


def _linreg_ab(xs, ys):
    """Regresión lineal mínima → (pendiente, intercepto). (2 valores; no confundir con _linreg)."""
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0)
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0, my
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / den
    return slope, my - slope * mx


def _spread(idxs, gap: int = 3):
    """Filtra índices para que estén separados >= `gap` velas (evita contar toques contiguos)."""
    kept = []
    for i in sorted(idxs):
        if not kept or i - kept[-1] >= gap:
            kept.append(i)
    return kept


def _cluster_by_price(idxs, prices, tol):
    """Agrupa pivotes por NIVEL de precio cercano (<= tol)."""
    clusters = []
    for i in sorted(idxs, key=lambda k: prices[k]):
        p = prices[i]
        placed = False
        for cl in clusters:
            avg = sum(prices[j] for j in cl) / len(cl)
            if abs(p - avg) <= tol:
                cl.append(i)
                placed = True
                break
        if not placed:
            clusters.append([i])
    return clusters


def _detect_rectangle(highs, lows, closes, volumes=None):
    """Rectángulo / rango lateral de acumulación-distribución. Canal HORIZONTAL: resistencia y
    soporte planos, paralelos y equidistantes; el precio oscila de lado a lado. Neutral/bilateral.
    Rechaza triángulo, cuña, canal inclinado, bandera, doble techo/suelo, megáfono y ruido."""
    n = len(closes)
    if n < 20:
        return None

    look = min(n, 90)
    off = n - look
    H_, L_, C_ = highs[off:], lows[off:], closes[off:]
    V_ = volumes[off:] if volumes else None
    m = len(C_)
    atr = _atr(highs, lows, closes)

    ph = _pivots(H_, "high", 2, 2)
    pl = _pivots(L_, "low", 2, 2)
    if len(ph) < 2 or len(pl) < 2:
        return None

    mean_p = sum(C_) / m
    tol0 = max(0.5 * atr, 0.012 * mean_p)
    if tol0 <= 0:
        return None

    res_cl = [cl for cl in _cluster_by_price(ph, H_, tol0) if len(_spread(cl)) >= 2]
    sup_cl = [cl for cl in _cluster_by_price(pl, L_, tol0) if len(_spread(cl)) >= 2]
    if not res_cl or not sup_cl:
        return None
    res_cluster = max(res_cl, key=lambda cl: sum(H_[j] for j in cl) / len(cl))
    sup_cluster = min(sup_cl, key=lambda cl: sum(L_[j] for j in cl) / len(cl))

    r_prices = sorted(H_[j] for j in res_cluster)
    s_prices = sorted(L_[j] for j in sup_cluster)
    R = r_prices[len(r_prices) // 2]
    S = s_prices[len(s_prices) // 2]
    H = R - S
    if H <= 0:
        return None

    if H < max(0.03 * mean_p, 1.5 * atr):
        return None
    if H / mean_p > 0.30:
        return None

    tol_touch = max(0.5 * atr, 0.15 * H)
    res_touch = _spread([off + j for j in ph if abs(H_[j] - R) <= tol_touch], 3)
    sup_touch = _spread([off + j for j in pl if abs(L_[j] - S) <= tol_touch], 3)
    if len(res_touch) < 2 or len(sup_touch) < 2:
        return None

    start = min(res_touch[0], sup_touch[0])
    end = max(res_touch[-1], sup_touch[-1])
    width = end - start
    if width < 15:
        return None

    if (max(r_prices) - min(r_prices)) / H > 0.2 or (max(r_prices) - min(r_prices)) / R > 0.03:
        return None
    if (max(s_prices) - min(s_prices)) / H > 0.2 or (max(s_prices) - min(s_prices)) / S > 0.03:
        return None

    sl_r, ic_r = _linreg_ab([float(i) for i in res_touch], [closes[i] for i in res_touch])
    sl_s, ic_s = _linreg_ab([float(i) for i in sup_touch], [closes[i] for i in sup_touch])
    if abs(sl_r * width) / H > 0.15 or abs(sl_s * width) / H > 0.15:
        return None

    r_ini, r_fin = ic_r + sl_r * start, ic_r + sl_r * end
    s_ini, s_fin = ic_s + sl_s * start, ic_s + sl_s * end
    H_ini, H_fin = r_ini - s_ini, r_fin - s_fin
    if H_ini <= 0 or H_fin <= 0 or not (0.8 <= H_fin / H_ini <= 1.25):
        return None

    region = closes[start:end + 1]
    tol_c = max(0.5 * atr, 0.10 * H)
    inside = sum(1 for c in region if S - tol_c <= c <= R + tol_c)
    if inside / len(region) < 0.90:
        return None

    up_band, lo_band = R - H / 3.0, S + H / 3.0
    frac_up = sum(1 for c in region if c >= up_band) / len(region)
    frac_lo = sum(1 for c in region if c <= lo_band) / len(region)
    if frac_up > 0.70 or frac_lo > 0.70:
        return None
    zone, transits = None, 0
    for c in region:
        z = "U" if c >= up_band else ("L" if c <= lo_band else None)
        if z is None:
            continue
        if zone and z != zone:
            transits += 1
        zone = z
    if transits < 3:
        return None

    margin = max(0.5 * atr, 0.005 * mean_p)
    ruptura = None
    for k in range(end + 1, n):
        if closes[k] > R + margin:
            ruptura = {"index": int(k), "price": round(float(closes[k]), 2), "direccion": "alcista"}
            break
        if closes[k] < S - margin:
            ruptura = {"index": int(k), "price": round(float(closes[k]), 2), "direccion": "bajista"}
            break

    if ruptura and ruptura["direccion"] == "alcista":
        sentido = "alcista"; objetivo = round(float(R + H), 2)
        desc_rup = "Ruptura ALCISTA confirmada (cierre sobre resistencia)."
    elif ruptura and ruptura["direccion"] == "bajista":
        sentido = "bajista"; objetivo = round(float(S - H), 2)
        desc_rup = "Ruptura BAJISTA confirmada (cierre bajo soporte)."
    else:
        sentido = "neutral"; objetivo = None
        desc_rup = "Sin ruptura aún: rango en curso (acumulación/distribución)."

    fin = ruptura["index"] if ruptura else (n - 1)
    linea_resistencia = {"type": "trendline", "kind": "resistencia", "points": [
        {"index": int(start), "price": round(float(R), 2)}, {"index": int(fin), "price": round(float(R), 2)}]}
    linea_soporte = {"type": "trendline", "kind": "soporte", "points": [
        {"index": int(start), "price": round(float(S), 2)}, {"index": int(fin), "price": round(float(S), 2)}]}

    desc = ("Canal HORIZONTAL: el precio oscila lateralmente entre una resistencia y un soporte planos "
            "y paralelos (equilibrio). Patrón neutral/bilateral: la ruptura con volumen define el sesgo; "
            "objetivo = altura del rango proyectada. " + desc_rup)

    return {
        "tipo": "rectangulo",
        "nombre": "Rectángulo (rango lateral)", "sentido": sentido, "descripcion": desc,
        "resistencia": round(float(R), 2), "soporte": round(float(S), 2),
        "altura_H": round(float(H), 2), "objetivo": objetivo, "ruptura": ruptura,
        "lineas": [linea_resistencia, linea_soporte],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Detectores RIGUROSOS de triángulos y cuñas (regresión de directrices + apex),
# generados a partir de la investigación (Bulkowski/StockCharts). Sustituyen a la
# lógica laxa de _detect_pattern para estas dos familias.
# ─────────────────────────────────────────────────────────────────────────────

def _lstsq_line(xs, ys):
    """Ajuste por mínimos cuadrados de la recta price = a*index + b sobre los pivotes.
    Devuelve (a, b, r2) o None. a = pendiente en precio/vela."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    a = sxy / sxx
    b = my - a * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a * x + b)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return a, b, r2


def _atr(highs, lows, closes, period: int = 14):
    """ATR simple (media de True Range) sobre las últimas `period` velas."""
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if not trs:
        return 0.0
    p = min(period, len(trs))
    return sum(trs[-p:]) / p


def _detect_triangles(highs, lows, closes, volumes=None, k: int = 3):
    """Detecta TRIÁNGULO ascendente / descendente / simétrico según la especificación
    (Bulkowski/StockCharts) con umbrales concretos y RECHAZA los falsos positivos:
    cuña, rectángulo/canal, megáfono, banderín y rupturas fallidas.

    Opera sobre listas highs/lows/closes (y volumes opcional). Devuelve un dict con
    tipo/nombre/sentido/descripcion + 'puntos' (rectas, apex, base y objetivo) para
    dibujar, o None si no hay triángulo válido. Los índices de 'puntos' están en
    coordenadas del array COMPLETO (ya se les suma el offset de la ventana)."""
    n = len(closes)
    if n < 20:
        return None

    # --- Ventana reciente (patrón local, no toda la historia) ---
    look = min(n, 120)
    off = n - look
    H = highs[off:]
    L = lows[off:]
    C = closes[off:]
    V = volumes[off:] if volumes else None
    price = C[-1] or (sum(C) / len(C))
    if not price:
        return None

    # --- 1) Pivotes por fractales (ventana +/-k) ---
    sh = _pivots(H, "high", k, k)   # swing highs → recta superior
    sl = _pivots(L, "low", k, k)    # swing lows  → recta inferior
    if len(sh) < 2 or len(sl) < 2:
        return None

    # --- 2) Ajuste inicial de ambas rectas por mínimos cuadrados ---
    fit_sup = _lstsq_line(sh, [H[i] for i in sh])
    fit_inf = _lstsq_line(sl, [L[i] for i in sl])
    if not fit_sup or not fit_inf:
        return None
    a_sup, b_sup, _ = fit_sup
    a_inf, b_inf, _ = fit_inf

    def ysup(x):
        return a_sup * x + b_sup

    def yinf(x):
        return a_inf * x + b_inf

    i_start = min(sh[0], sl[0])
    i_end = max(sh[-1], sl[-1])

    # Refinado: descartar pivotes que no rozan su recta (tolerancia) y reajustar 1 vez.
    H0_ini = ysup(i_start) - yinf(i_start)
    tol = max(0.01 * price, 0.15 * H0_ini) if H0_ini > 0 else 0.01 * price
    sh2 = [i for i in sh if abs(H[i] - ysup(i)) <= tol]
    sl2 = [i for i in sl if abs(L[i] - yinf(i)) <= tol]
    if len(sh2) >= 2 and len(sl2) >= 2:
        f1 = _lstsq_line(sh2, [H[i] for i in sh2])
        f2 = _lstsq_line(sl2, [L[i] for i in sl2])
        if f1 and f2:
            a_sup, b_sup, r2_sup = f1
            a_inf, b_inf, r2_inf = f2
            sh, sl = sh2, sl2
            i_start = min(sh[0], sl[0])
            i_end = max(sh[-1], sl[-1])
    else:
        r2_sup = fit_sup[2]
        r2_inf = fit_inf[2]

    # --- 3) Duración N (primer→último pivote) ---
    N = i_end - i_start
    if N < 15:          # <3 semanas en diario → banderín/pennant, NO triángulo
        return None
    if N > 120:         # base/rango largo, no triángulo
        return None

    # --- 4) Pendientes normalizadas (% por vela) y cambio total de cada recta ---
    s_sup = a_sup / price          # fracción/vela
    s_inf = a_inf / price
    top_change = abs(a_sup * N) / price   # cambio total recta superior (fracción)
    bot_change = abs(a_inf * N) / price
    FLAT = 0.001    # |s| < 0.1%/vela  → horizontal
    INCL = 0.0015   # |s| >= 0.15%/vela → inclinada relevante

    # DISCRIMINADOR cuña: mismo signo de pendiente en ambas y ambas inclinadas → cuña.
    if (s_sup > INCL and s_inf > INCL) or (s_sup < -INCL and s_inf < -INCL):
        return None

    # --- 5) Altura de la base H0 (parte más ancha, en el primer pivote) ---
    H0 = ysup(i_start) - yinf(i_start)
    if H0 <= 0:
        return None
    h0_pct = H0 / price
    if not (0.03 <= h0_pct <= 0.40):   # <3% ruido, >40% demasiado volátil
        return None

    # --- 6) Convergencia real (el ancho debe estrecharse >=35%) ---
    W_ini = H0
    W_fin = ysup(i_end) - yinf(i_end)
    if W_fin <= 0:            # el apex cae DENTRO del patrón → agotado
        return None
    r = W_fin / W_ini
    if r > 0.65:             # DISCRIMINADOR rectángulo/canal/megáfono (sin convergencia)
        return None

    # --- 7) Clasificación de la variante ---
    tipo = None
    lvl_sup = sum(H[i] for i in sh) / len(sh)   # nivel medio SH (para forzar horizontal)
    lvl_inf = sum(L[i] for i in sl) / len(sl)

    # Banda de la recta plana: todos sus toques dentro de 1.5% entre sí.
    band_sup_ok = (max(H[i] for i in sh) - min(H[i] for i in sh)) / price <= 0.015
    band_inf_ok = (max(L[i] for i in sl) - min(L[i] for i in sl)) / price <= 0.015

    if top_change <= 0.015 and band_sup_ok and s_inf > 0 and bot_change >= 0.03:
        tipo = "ascendente"
    elif bot_change <= 0.015 and band_inf_ok and s_sup < 0 and top_change >= 0.03:
        tipo = "descendente"
    elif s_sup < -FLAT and s_inf > FLAT and top_change >= 0.03 and bot_change >= 0.03:
        ratio = abs(a_sup) / abs(a_inf) if a_inf else 999
        if 0.5 <= ratio <= 2.0:   # simetría de pendientes
            tipo = "simetrico"
    if tipo is None:
        return None

    # --- 8) Fijar rectas de DIBUJO (forzar horizontal en asc/desc) y recalcular apex ---
    if tipo == "ascendente":
        a_sup, b_sup = 0.0, lvl_sup
    elif tipo == "descendente":
        a_inf, b_inf = 0.0, lvl_inf

    def ysup(x):
        return a_sup * x + b_sup

    def yinf(x):
        return a_inf * x + b_inf

    H0 = ysup(i_start) - yinf(i_start)
    if H0 <= 0:
        return None
    if a_sup == a_inf:
        return None
    x_apex = (b_inf - b_sup) / (a_sup - a_inf)
    D = x_apex - i_start
    if D <= 0:
        return None

    # --- 9) Toques mínimos (>=2 por recta, >=4 total) y reparto temporal ---
    tol = max(0.01 * price, 0.15 * H0)   # residuo máximo pivote→recta
    sup_t = [i for i in sh if abs(H[i] - ysup(i)) <= tol]
    inf_t = [i for i in sl if abs(L[i] - yinf(i)) <= tol]
    if len(sup_t) < 2 or len(inf_t) < 2 or (len(sup_t) + len(inf_t)) < 4:
        return None
    all_t = sorted(sup_t + inf_t)
    if (all_t[0] - i_start) > 0.25 * N:   # primer toque en el 25% inicial
        return None
    if (i_end - all_t[-1]) > 0.40 * N:    # último toque en el 40% final
        return None

    # Calidad de ajuste: R^2>=0.90 en la(s) recta(s) INCLINADA(s) (la plana tiene R^2 bajo
    # por construcción, así que a esa se le aplica la banda ya comprobada).
    if tipo in ("ascendente", "simetrico") and r2_inf < 0.90:
        return None
    if tipo in ("descendente", "simetrico") and r2_sup < 0.90:
        return None

    # --- 10) Ruptura / invalidación ---
    atr = _atr(H, L, C, 14)
    buffer = max(0.5 * atr, 0.01 * price)
    cur = look - 1
    brk = None                      # (direccion, indice_en_ventana)
    for i in range(i_end, look):
        c = C[i]
        if c > ysup(i) + buffer:
            brk = ("alcista", i)
            break
        if c < yinf(i) - buffer:
            brk = ("bajista", i)
            break

    # DISCRIMINADOR apex agotado: precio en zona del apex (>0.90*D) sin romper → nulo.
    if brk is None and (cur - i_start) > 0.90 * D:
        return None
    # Ruptura demasiado cerca del apex (>0.90*D) → sin recorrido, descartar.
    if brk and (brk[1] - i_start) > 0.90 * D:
        return None
    # DISCRIMINADOR ruptura fallida (busted): tras romper el cierre vuelve a entrar.
    if brk:
        _, bi = brk
        for j in range(bi + 1, look):
            if yinf(j) < C[j] < ysup(j):
                brk = None          # ruptura anulada → tratamos el patrón como en formación
                break

    # Volumen (criterio blando, no invalida): pendiente decreciente en el patrón.
    vol_decreasing = None
    if V:
        seg = V[i_start:i_end + 1]
        if len(seg) >= 4:
            fv = _lstsq_line(list(range(len(seg))), seg)
            vol_decreasing = bool(fv and fv[0] < 0)

    # --- 11) Sentido y objetivo (measure rule T = ruptura +/- H0, ajuste 0.63-0.70) ---
    sentido_map = {"ascendente": "alcista", "descendente": "bajista", "simetrico": "neutral"}
    sentido = sentido_map[tipo]
    ruptura_pt = None
    objetivo = None
    if brk:
        dir_, bi = brk
        sentido = dir_
        p_brk = C[bi]
        signo = 1 if dir_ == "alcista" else -1
        objetivo = round(p_brk + signo * 0.65 * H0, 2)   # objetivo probabilístico
        ruptura_pt = {"index": int(bi + off), "price": round(float(p_brk), 2)}

    # --- 12) Puntos de dibujo (índices en array completo) ---
    x1 = min(sup_t[0], inf_t[0])
    x2 = i_end
    puntos = {
        "superior": [
            {"index": int(x1 + off), "price": round(float(ysup(x1)), 2)},
            {"index": int(x2 + off), "price": round(float(ysup(x2)), 2)},
        ],
        "inferior": [
            {"index": int(x1 + off), "price": round(float(yinf(x1)), 2)},
            {"index": int(x2 + off), "price": round(float(yinf(x2)), 2)},
        ],
        "apex": {"index": int(round(x_apex) + off), "price": round(float(ysup(x_apex)), 2)},
        "base": [   # segmento vertical H0 en el primer pivote
            {"index": int(i_start + off), "price": round(float(ysup(i_start)), 2)},
            {"index": int(i_start + off), "price": round(float(yinf(i_start)), 2)},
        ],
        "ruptura": ruptura_pt,
        "objetivo": objetivo,
    }

    nombres = {
        "ascendente": "Triángulo ascendente",
        "descendente": "Triángulo descendente",
        "simetrico": "Triángulo simétrico",
    }
    desc = {
        "ascendente": ("Resistencia horizontal con mínimos crecientes que convergen. Sesgo alcista de "
                       "continuación: se compra en el cierre por encima de la resistencia (buffer "
                       "0.5*ATR/1%). Objetivo = ruptura + altura de la base (H0)."),
        "descendente": ("Soporte horizontal con máximos decrecientes que convergen. Sesgo bajista: se "
                        "vende en el cierre por debajo del soporte. Objetivo = ruptura - H0."),
        "simetrico": ("Máximos decrecientes y mínimos crecientes convergen hacia el apex. Neutro/"
                      "continuación: la dirección de la ruptura (cierre + buffer) marca el movimiento; "
                      "objetivo = ruptura +/- H0."),
    }[tipo]

    return {
        "tipo": "triangulo_" + tipo,
        "nombre": nombres[tipo],
        "sentido": sentido,
        "descripcion": desc,
        "puntos": puntos,
        "meta": {
            "N": int(N),
            "H0_pct": round(h0_pct, 4),
            "convergencia_r": round(r, 3),
            "toques": {"superior": len(sup_t), "inferior": len(inf_t)},
            "r2_sup": round(r2_sup, 3),
            "r2_inf": round(r2_inf, 3),
            "apex_index": int(round(x_apex) + off),
            "D": round(D, 1),
            "volumen_decreciente": vol_decreasing,
            "ruptura_confirmada": brk is not None,
        },
    }


def _linreg(xs, ys):
    """Regresión lineal simple. Devuelve (pendiente, ordenada, R^2)."""
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0), 0.0
    sx = sum(xs); sy = sum(ys)
    sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0, sy / n, 0.0
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    mean = sy / n
    ss_tot = sum((y - mean) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, intercept, r2


def _atr14(highs, lows, closes):
    """ATR de 14 sobre las últimas velas (escala de tolerancia de 'toque')."""
    n = len(closes)
    if n < 2:
        return 0.0
    trs = []
    for i in range(max(1, n - 14), n):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.0


def _detect_wedge(highs, lows, closes, volumes=None):
    """Cuña ascendente (rising, BAJISTA) y descendente (falling, ALCISTA).

    Dos directrices con pendientes del MISMO signo que CONVERGEN hacia un vértice (apex).
    Rechaza triángulos (signos opuestos / una línea plana), canales y banderas (paralelas)
    y megáfonos (divergen). Requiere >=3 toques por línea, R^2>=0.85, contracción de
    amplitud >=34% y convergencia real (apex cercano). Devuelve dict con la detección y
    los puntos de dibujo (dos líneas + segmento de base) o None."""
    n = len(closes)
    if n < 15:
        return None

    P = closes[-1] or (sum(closes) / n)  # precio de referencia
    if P <= 0:
        return None

    # --- Paso 1: pivotes por ventana fractal (k=3, con respaldo k=2). Solo estructura
    # RECIENTE: últimas 10-60 velas (mínimo operable ~15) para una cuña local, no global.
    look = min(n, 60)
    off = n - look
    hi_slice, lo_slice = highs[off:], lows[off:]
    h_idx = l_idx = []
    for k in (3, 2):
        h_idx = [i + off for i in _pivots(hi_slice, "high", k, k)]
        l_idx = [i + off for i in _pivots(lo_slice, "low", k, k)]
        if len(h_idx) >= 3 and len(l_idx) >= 3:
            break
    # Criterio nº1: >=3 pivotes en cada línea (con 2 no hay cuña confirmada → falso pivote).
    if len(h_idx) < 3 or len(l_idx) < 3:
        return None

    # --- Paso 2 y 3: regresión de la línea de MÁXIMOS (resistencia) y de MÍNIMOS (soporte).
    a_h, b_h, r2_h = _linreg(h_idx, [highs[i] for i in h_idx])
    a_l, b_l, r2_l = _linreg(l_idx, [lows[i] for i in l_idx])

    # Criterio nº2 (ajuste): R^2 >= 0.85 en ambas líneas.
    if r2_h < 0.85 or r2_l < 0.85:
        return None

    t_ini = min(h_idx[0], l_idx[0])
    t_fin = max(h_idx[-1], l_idx[-1])
    L = t_fin - t_ini
    if L < 8:  # figura demasiado corta para ser cuña
        return None

    def recta_max(t): return a_h * t + b_h
    def recta_min(t): return a_l * t + b_l

    # --- Discriminador CUÑA vs TRIÁNGULO SIMÉTRICO: pendientes del MISMO signo (obligatorio).
    if not (a_h > 0 and a_l > 0) and not (a_h < 0 and a_l < 0):
        return None

    # --- Discriminador CUÑA vs TRIÁNGULO asc/desc: ninguna línea casi horizontal.
    if abs(a_h * L) < 0.01 * P or abs(a_l * L) < 0.01 * P:
        return None

    # --- Discriminador CUÑA vs CANAL/BANDERA: separación de pendientes suficiente.
    if abs(a_l - a_h) < 0.15 * max(abs(a_h), abs(a_l)):
        return None

    # --- Convergencia (nº4) + discriminador vs MEGÁFONO: la amplitud DECRECE.
    w_ini = recta_max(t_ini) - recta_min(t_ini)   # base (parte ancha, izquierda)
    w_fin = recta_max(t_fin) - recta_min(t_fin)
    if w_ini <= 0 or w_fin <= 0:                  # deben mantener techo>suelo (aún no cruzan)
        return None
    if w_fin / w_ini > 0.66:                       # exigir contracción >= 34%
        return None

    # Apex = intersección. Debe estar POR DELANTE y CERCA (a <= 3*L velas desde el inicio).
    if a_h == a_l:
        return None
    t_apex = (b_l - b_h) / (a_h - a_l)
    if t_apex <= t_fin or (t_apex - t_ini) > 3 * L:
        return None

    # Invalidación por expiración: si ya recorrimos >90% hacia el apex sin ruptura, expira.
    progreso = (t_fin - t_ini) / (t_apex - t_ini) if (t_apex - t_ini) else 1.0
    if progreso > 0.90:
        return None

    # --- Criterio nº5: dirección relativa de pendientes → tipo de cuña.
    if a_h > 0 and a_l > 0 and a_l > a_h:
        tipo, nombre, sentido = "cuna_ascendente", "Cuña ascendente", "bajista"
    elif a_h < 0 and a_l < 0 and a_h < a_l:
        tipo, nombre, sentido = "cuna_descendente", "Cuña descendente", "alcista"
    else:
        return None  # mismo signo pero mal ordenadas (no es cuña válida)

    # --- Criterio nº2 (contención): ningún High supera recta_max ni ningún Low perfora recta_min.
    tol = max(0.6 * _atr14(highs, lows, closes), 0.008 * P)
    for i in range(t_ini, t_fin + 1):
        if highs[i] - recta_max(i) > tol:  # High rompe el techo → no es canal contenedor
            return None
        if recta_min(i) - lows[i] > tol:   # Low perfora el suelo
            return None

    # --- Criterio nº6 (volumen): DECRECIENTE dentro de la cuña. Opcional.
    if volumes is not None and len(volumes) >= t_fin + 1:
        seg = volumes[t_ini:t_fin + 1]
        tercio = max(1, len(seg) // 3)
        vol_ini = sum(seg[:tercio]) / tercio
        vol_fin = sum(seg[-tercio:]) / tercio
        if vol_ini > 0 and vol_fin >= 0.80 * vol_ini:  # el último tercio debe caer <80% del primero
            return None

    # --- Ruptura/objetivo (measure rule): altura = base w(t_ini).
    if tipo == "cuna_ascendente":
        objetivo = round(P - w_ini, 2)  # rompe a la BAJA
        gatillo = "cierre por DEBAJO del soporte"
    else:
        objetivo = round(P + w_ini, 2)  # rompe al ALZA
        gatillo = "cierre por ENCIMA de la resistencia con volumen >=1.5x media20"

    descripcion = (
        f"Dos directrices que {'suben' if sentido == 'bajista' else 'bajan'} convergiendo "
        f"(amplitud -{round((1 - w_fin / w_ini) * 100)}%). "
        + ("La subida pierde impulso: sesgo BAJISTA, suele romper a la baja. "
           if sentido == "bajista" else
           "La caída pierde fuerza: sesgo ALCISTA, suele romper al alza. ")
        + f"Gatillo: {gatillo}. Objetivo (altura de la base) ~ {objetivo}."
    )

    line_res = {
        "type": "trendline", "kind": "resistencia",
        "points": [
            {"index": int(t_ini), "price": round(float(recta_max(t_ini)), 2)},
            {"index": int(t_fin), "price": round(float(recta_max(t_fin)), 2)},
        ],
    }
    line_sup = {
        "type": "trendline", "kind": "soporte",
        "points": [
            {"index": int(t_ini), "price": round(float(recta_min(t_ini)), 2)},
            {"index": int(t_fin), "price": round(float(recta_min(t_fin)), 2)},
        ],
    }
    base_seg = {
        "type": "segment", "kind": "base",
        "points": [
            {"index": int(t_ini), "price": round(float(recta_max(t_ini)), 2)},
            {"index": int(t_ini), "price": round(float(recta_min(t_ini)), 2)},
        ],
    }

    return {
        "tipo": tipo, "nombre": nombre, "sentido": sentido,
        "descripcion": descripcion,
        "objetivo": objetivo,
        "apex_index": int(round(t_apex)),
        "puntos": [line_res, line_sup, base_seg],
    }


def _argmax(seq):
    """Índice del máximo (sin numpy; el módulo trabaja sobre listas)."""
    best, bi = seq[0], 0
    for i, v in enumerate(seq):
        if v > best:
            best, bi = v, i
    return bi


def _argmin(seq):
    """Índice del mínimo."""
    best, bi = seq[0], 0
    for i, v in enumerate(seq):
        if v < best:
            best, bi = v, i
    return bi


def _detect_double(highs, lows, closes):
    """Doble suelo (W, reversión ALCISTA) y Doble techo (M, reversión BAJISTA).

    Motor riguroso: exige tendencia previa contraria, dos extremos ~iguales (A,C),
    un retroceso intermedio B significativo (el cuello) y separación/simetría temporal.
    Rechaza los falsos positivos clásicos: V-bottom, redondeado, cabeza-hombros,
    triple suelo/techo, rango lateral, patrón sesgado y fakeout. Devuelve el dict del
    patrón + `puntos` (A,B,C,D) y `lineas` de dibujo, o None."""
    n = len(closes)
    if n < 30:                      # hace falta histórico para la tendencia previa + el patrón
        return None
    if max(highs) - min(lows) <= 0:
        return None

    EQ_MAX     = 0.02   # |A-C| máx entre extremos: 2% (apretado para reducir falsos positivos)
    DEPTH_MIN  = 0.10   # retroceso intermedio B mínimo = altura del patrón (10% Bulkowski)
    DEPTH_MAX  = 0.45   # rebote intermedio MÁXIMO: un W real rebota 10-40%, no más. Un pico
                        # gigante entre dos mínimos lejanos NO es un doble suelo (era el bug).
    TREND_MIN  = 0.10   # tendencia previa contraria mínima hacia A (>=10%)
    SEP_MIN    = 10     # velas mínimas entre A y C (~2-3 semanas)
    SEP_MAX    = 250    # velas máximas (~1 año)
    SYM_LO     = 0.33   # simetría temporal t(A->B)/t(B->C) mínima
    SYM_HI     = 3.0    #   ... máxima
    PEN_STRONG = 0.05   # penetración fuerte del cuello (filtro anti-fakeout 5%)
    W          = 5      # ventana de pivote local (+/-5 velas)

    return (_scan_double(highs, lows, closes, n, "suelo",
                         EQ_MAX, DEPTH_MIN, TREND_MIN, SEP_MIN, SEP_MAX, SYM_LO, SYM_HI, PEN_STRONG, W, DEPTH_MAX)
            or _scan_double(highs, lows, closes, n, "techo",
                            EQ_MAX, DEPTH_MIN, TREND_MIN, SEP_MIN, SEP_MAX, SYM_LO, SYM_HI, PEN_STRONG, W, DEPTH_MAX))


def _scan_double(highs, lows, closes, n, variante,
                 EQ_MAX, DEPTH_MIN, TREND_MIN, SEP_MIN, SEP_MAX, SYM_LO, SYM_HI, PEN_STRONG, W, DEPTH_MAX=0.45):
    """Escanea una variante ('suelo' o 'techo'). Comparte toda la lógica numérica; solo
    cambia el signo: en el suelo los extremos son mínimos y el cuello un máximo intermedio."""
    es_suelo = variante == "suelo"
    ext = lows if es_suelo else highs                     # serie de los dos extremos A y C
    mid = highs if es_suelo else lows                     # serie del retroceso intermedio B
    ext_piv = _pivots(ext, "low" if es_suelo else "high", W, W)
    if len(ext_piv) < 2:
        return None

    mejor = None
    for ia in range(len(ext_piv)):
        for ic in range(ia + 1, len(ext_piv)):
            i_a, i_c = ext_piv[ia], ext_piv[ic]
            pa, pc = ext[i_a], ext[i_c]
            if pa <= 0 or pc <= 0:
                continue

            sep = i_c - i_a
            if not (SEP_MIN <= sep <= SEP_MAX):
                continue
            if abs(pa - pc) / min(pa, pc) > EQ_MAX:
                continue

            base = min(pa, pc) if es_suelo else max(pa, pc)   # extremo del patrón (invalidación)

            seg = mid[i_a + 1:i_c]
            if not seg:
                continue
            if es_suelo:
                pb = max(seg); i_b = i_a + 1 + seg.index(pb)
                depth = (pb - base) / base
            else:
                pb = min(seg); i_b = i_a + 1 + seg.index(pb)
                depth = (base - pb) / pb
            if depth < DEPTH_MIN:            # sin pico intermedio >=10% es V o redondeado, NO doble
                continue
            if depth > DEPTH_MAX:            # rebote >45% => no son dos suelos gemelos de un W,
                continue                     # sino dos mínimos lejanos alrededor de un pico grande

            t1, t2 = i_b - i_a, i_c - i_b
            if t1 <= 0 or t2 <= 0:
                continue
            ratio = t1 / t2
            if not (SYM_LO <= ratio <= SYM_HI):   # muy asimétrico => probable H&S
                continue

            tol = base * EQ_MAX
            cerca = [p for p in ext_piv if i_a - 2 <= p <= i_c + 2 and abs(ext[p] - base) <= tol]
            if len(cerca) > 2:                    # >2 extremos al mismo nivel => triple/rango
                continue

            es_hch = False
            for p in ext_piv:
                if i_a < p < i_c:
                    if es_suelo and ext[p] < base * (1 - EQ_MAX):
                        es_hch = True; break
                    if not es_suelo and ext[p] > base * (1 + EQ_MAX):
                        es_hch = True; break
            if es_hch:
                continue

            lo0 = max(0, i_a - 60)
            if i_a - lo0 < 10:
                continue
            if es_suelo:
                i_p0 = lo0 + int(_argmax(highs[lo0:i_a]))
                p0 = highs[i_p0]
                trend_prev = (p0 - pa) / p0 if p0 else 0
            else:
                i_p0 = lo0 + int(_argmin(lows[lo0:i_a]))
                p0 = lows[i_p0]
                trend_prev = (pa - p0) / pa if pa else 0
            if trend_prev < TREND_MIN:
                continue

            neck = pb
            i_d, confirmado, penetracion_fuerte, invalidado = None, False, False, False
            for j in range(i_c + 1, n):
                if es_suelo:
                    if closes[j] > neck:
                        i_d = j; confirmado = True
                        penetracion_fuerte = closes[j] >= neck * (1 + PEN_STRONG)
                        break
                    if closes[j] < base:
                        invalidado = True; break
                else:
                    if closes[j] < neck:
                        i_d = j; confirmado = True
                        penetracion_fuerte = closes[j] <= neck * (1 - PEN_STRONG)
                        break
                    if closes[j] > base:
                        invalidado = True; break
            if invalidado:
                continue
            if not confirmado:                # SOLO mostramos el doble si ya rompió el cuello
                continue                      # (evita ruido: un W sin confirmar sale demasiado)
            if i_d is not None and i_d < n - 60:   # y solo si la ruptura es RECIENTE (patrón vigente,
                continue                           # no un W de hace 200 velas ya irrelevante)
            cur = closes[-1]                       # y VIGENTE: el precio no ha recaído al otro lado
            if es_suelo and cur < neck:            # doble suelo: recayó bajo el cuello -> invalidado
                continue
            if (not es_suelo) and cur > neck:       # doble techo: recuperó sobre el cuello -> invalidado
                continue

            cand = {
                "i_a": i_a, "i_b": i_b, "i_c": i_c, "i_d": i_d, "i_p0": i_p0,
                "pa": pa, "pb": pb, "pc": pc, "base": base, "neck": neck,
                "depth": depth, "trend_prev": trend_prev,
                "confirmado": confirmado, "penetracion_fuerte": penetracion_fuerte,
            }
            clave = (i_c, 1 if confirmado else 0)
            if mejor is None or clave > mejor["_clave"]:
                cand["_clave"] = clave
                mejor = cand

    if mejor is None:
        return None
    return _build_double(highs, lows, closes, n, es_suelo, mejor)


def _build_double(highs, lows, closes, n, es_suelo, m):
    """Empaqueta el patrón: dict estándar + `puntos` (P0,A,B,C,D) y `lineas` (cuello, base,
    objetivo, invalidación), en coordenadas de índice/precio como el resto del módulo."""
    base, neck = m["base"], m["neck"]
    H = abs(neck - base)                                   # altura del patrón (regla de medida)
    if es_suelo:
        objetivo = round(neck + H, 2)
        objetivo_cons = round(neck + 0.7 * H, 2)
    else:
        objetivo = round(neck - H, 2)
        objetivo_cons = round(neck - 0.7 * H, 2)

    r = lambda x: round(float(x), 2)
    puntos = [
        {"index": int(m["i_p0"]), "price": r(highs[m["i_p0"]] if es_suelo else lows[m["i_p0"]]),
         "etiqueta": "P0", "rol": "inicio_tendencia"},
        {"index": int(m["i_a"]), "price": r(m["pa"]), "etiqueta": "A", "rol": "primer_extremo"},
        {"index": int(m["i_b"]), "price": r(m["pb"]), "etiqueta": "B", "rol": "cuello"},
        {"index": int(m["i_c"]), "price": r(m["pc"]), "etiqueta": "C", "rol": "segundo_extremo"},
    ]
    if m["i_d"] is not None:
        puntos.append({"index": int(m["i_d"]), "price": r(closes[m["i_d"]]),
                       "etiqueta": "D", "rol": "ruptura"})

    x_fin = n - 1
    x_rup = m["i_d"] if m["i_d"] is not None else x_fin
    lineas = [
        {"tipo": "cuello", "kind": "neckline",
         "points": [{"index": int(m["i_b"]), "price": r(neck)}, {"index": int(x_fin), "price": r(neck)}]},
        {"tipo": "base", "kind": "base", "estilo": "punteada",
         "points": [{"index": int(m["i_a"]), "price": r(base)}, {"index": int(m["i_c"]), "price": r(base)}]},
        {"tipo": "objetivo", "kind": "target",
         "points": [{"index": int(x_rup), "price": r(neck)}, {"index": int(x_rup), "price": objetivo}],
         "objetivo": objetivo, "objetivo_conservador": objetivo_cons},
        {"tipo": "invalidacion", "kind": "invalidation", "color": "rojo",
         "points": [{"index": int(m["i_a"]), "price": r(base)}, {"index": int(x_fin), "price": r(base)}]},
    ]

    estado = "confirmado" if m["confirmado"] else "potencial (sin romper el cuello)"
    if es_suelo:
        desc = ("Doble suelo (W): dos mínimos ~iguales tras una caída previa del "
                f"{m['trend_prev']*100:.0f}%, separados por un rebote intermedio del "
                f"{m['depth']*100:.0f}% (cuello en {r(neck)}). Reversión ALCISTA {estado}. "
                f"Gatillo: cierre por encima del cuello (penetración >=5%). Objetivo {objetivo} "
                f"(conservador {objetivo_cons}); invalida si cierra bajo {r(base)}.")
        return {"tipo": "doble_suelo", "nombre": "Doble suelo", "sentido": "alcista",
                "descripcion": desc, "confirmado": m["confirmado"],
                "penetracion_fuerte": m["penetracion_fuerte"],
                "puntos": puntos, "lineas": lineas}
    desc = ("Doble techo (M): dos máximos ~iguales tras una subida previa del "
            f"{m['trend_prev']*100:.0f}%, separados por un valle intermedio del "
            f"{m['depth']*100:.0f}% (cuello en {r(neck)}). Reversión BAJISTA {estado}. "
            f"Gatillo: cierre por debajo del cuello (penetración >=5%). Objetivo {objetivo} "
            f"(conservador {objetivo_cons}); invalida si cierra sobre {r(base)}.")
    return {"tipo": "doble_techo", "nombre": "Doble techo", "sentido": "bajista",
            "descripcion": desc, "confirmado": m["confirmado"],
            "penetracion_fuerte": m["penetracion_fuerte"],
            "puntos": puntos, "lineas": lineas}


def _lsq(xs, ys):
    """Regresión lineal por mínimos cuadrados. Devuelve (pendiente, intercepto, R²)."""
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0), 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return 0.0, my, 0.0
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return slope, intercept, r2


def _detect_channel(highs, lows, closes, atr14=None):
    """Canal ASCENDENTE (alcista) o DESCENDENTE (bajista): dos directrices SENSIBLEMENTE
    PARALELAS (misma pendiente, ancho constante) entre las que oscila el precio. RECHAZA
    cuña, triángulo, megáfono, bandera, rectángulo y trendline suelta. Devuelve dict con los
    puntos de dibujo de ambas rectas, o None."""
    n = len(closes)
    if n < 15:
        return None
    if atr14 is None:
        atr14 = _atr14(highs, lows, closes)
    price = closes[-1] or (sum(closes) / n)
    eps = 1e-9

    look = min(n, 120)
    off = n - look
    h_all = [i + off for i in _pivots(highs[off:], "high")]
    l_all = [i + off for i in _pivots(lows[off:], "low")]
    h_piv = h_all[-6:]
    l_piv = l_all[-6:]
    if len(h_piv) < 2 or len(l_piv) < 2:
        return None

    m_sup, b_sup, r2_sup = _lsq(h_piv, [highs[i] for i in h_piv])
    m_inf, b_inf, r2_inf = _lsq(l_piv, [lows[i] for i in l_piv])
    if r2_sup < 0.90 or r2_inf < 0.90:
        return None

    x_start = min(h_piv[0], l_piv[0])
    x_end = max(h_piv[-1], l_piv[-1])
    span = x_end - x_start
    if span < 15:
        return None

    ws = []
    for x in range(x_start, x_end + 1):
        ws.append((m_sup * x + b_sup) - (m_inf * x + b_inf))
    if min(ws) <= 0:
        return None
    mean_w = sum(ws) / len(ws)
    std_w = (sum((w - mean_w) ** 2 for w in ws) / len(ws)) ** 0.5

    if mean_w < max(3 * atr14, 0.05 * price):
        return None
    if std_w > 0.15 * mean_w:
        return None
    ratio = ws[-1] / ws[0] if ws[0] > 0 else 0.0
    if not (0.75 <= ratio <= 1.25):          # <0.75 = cuña; >1.25 = megáfono
        return None

    mean_slope = (m_sup + m_inf) / 2.0
    if abs(m_sup - m_inf) / max(abs(mean_slope), eps) > 0.20:   # paralelismo
        return None

    run = abs(mean_slope) * span
    if run < 0.5 * mean_w:                   # sin inclinación -> rectángulo, no canal
        return None
    ascendente = mean_slope > 0

    tol_step = 0.03 * mean_w

    def _seq_ok(idxs, vals, up):
        viol = 0
        for k in range(1, len(idxs)):
            d = vals[idxs[k]] - vals[idxs[k - 1]]
            if up and d < -tol_step:
                viol += 1
            elif (not up) and d > tol_step:
                viol += 1
        return viol <= 1

    if not (_seq_ok(h_piv, highs, ascendente) and _seq_ok(l_piv, lows, ascendente)):
        return None

    tol_touch = max(0.10 * mean_w, atr14)
    sup_touch = [i for i in h_piv if abs(highs[i] - (m_sup * i + b_sup)) <= tol_touch]
    inf_touch = [i for i in l_piv if abs(lows[i] - (m_inf * i + b_inf)) <= tol_touch]
    if len(sup_touch) < 2 or len(inf_touch) < 2:
        return None
    seq = sorted([(i, "S") for i in sup_touch] + [(i, "I") for i in inf_touch])
    tags = [t for _, t in seq]
    run_same, max_same, changes = 1, 1, 0
    for k in range(1, len(tags)):
        if tags[k] == tags[k - 1]:
            run_same += 1
            max_same = max(max_same, run_same)
        else:
            run_same = 1
            changes += 1
    if max_same > 2 or changes < 2:
        return None

    over = 0.10 * mean_w
    inside = total = 0
    for x in range(x_start, x_end + 1):
        y_sup = m_sup * x + b_sup + over
        y_inf = m_inf * x + b_inf - over
        total += 1
        if y_inf <= closes[x] <= y_sup:
            inside += 1
    if total == 0 or inside / total < 0.90:
        return None

    x_draw_end = n - 1
    puntos_sup = [
        {"index": int(x_start), "price": round(float(m_sup * x_start + b_sup), 2)},
        {"index": int(x_draw_end), "price": round(float(m_sup * x_draw_end + b_sup), 2)},
    ]
    puntos_inf = [
        {"index": int(x_start), "price": round(float(m_inf * x_start + b_inf), 2)},
        {"index": int(x_draw_end), "price": round(float(m_inf * x_draw_end + b_inf), 2)},
    ]

    if ascendente:
        tipo, nombre, sentido = "canal_alcista", "Canal alcista", "alcista"
        desc = ("Precio en tendencia alcista contenido entre dos directrices paralelas (misma "
                "pendiente y ancho constante), con máximos y mínimos crecientes. Comprar en rebotes "
                "sobre el SOPORTE con stop bajo la línea; objetivo la resistencia. El cierre por debajo "
                "del soporte avisa de giro bajista.")
    else:
        tipo, nombre, sentido = "canal_bajista", "Canal bajista", "bajista"
        desc = ("Precio en tendencia bajista contenido entre dos directrices paralelas, con máximos y "
                "mínimos decrecientes. Vender en rechazos de la RESISTENCIA; los rebotes no son compras. "
                "El cierre por encima de la resistencia avisa de giro alcista.")

    return {
        "tipo": tipo, "nombre": nombre, "sentido": sentido, "descripcion": desc,
        "ancho": round(float(mean_w), 2),
        "puntos_dibujo": {"resistencia": puntos_sup, "soporte": puntos_inf},
    }


def _true_range(highs, lows, closes, i):
    """True Range de la vela i (contempla el gap con el cierre previo)."""
    if i <= 0:
        return highs[i] - lows[i]
    return max(highs[i] - lows[i],
               abs(highs[i] - closes[i - 1]),
               abs(lows[i] - closes[i - 1]))


def _linreg_seq(ys):
    """Regresión lineal de ys sobre x=0..n-1. Devuelve (pendiente, intercepto, R^2).
    (Versión de UNA serie; distinta de _linreg(xs, ys), no confundir.)"""
    n = len(ys)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0), 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = (1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    return slope, intercept, r2


def _eval_flag(highs, lows, closes, volumes, Bidx, cons, direction, atr, eps):
    """Evalúa UNA hipótesis: consolidación de `cons` velas colgando del tip Bidx, en el
    sentido `direction` ('bull'/'bear'). Devuelve un candidato con score y puntos de dibujo."""
    n = len(closes)
    bull = direction == "bull"

    win_lo = max(0, Bidx - 20)
    seg = closes[win_lo:Bidx + 1]
    if len(seg) < 4:
        return None
    Arel = (min(range(len(seg)), key=lambda k: seg[k]) if bull
            else max(range(len(seg)), key=lambda k: seg[k]))
    Aidx = win_lo + Arel
    pl = Bidx - Aidx
    if not (3 <= pl <= 20):
        return None

    pole_closes = closes[Aidx:Bidx + 1]
    P_A = lows[Aidx] if bull else highs[Aidx]
    P_B = highs[Bidx] if bull else lows[Bidx]
    pole_h = (P_B - P_A) if bull else (P_A - P_B)
    if pole_h <= 0:
        return None
    if (bull and P_B <= P_A) or (not bull and P_B >= P_A):
        return None

    move = pole_h / P_A if P_A else 0.0
    if move < 0.08:
        return None
    if pole_h / pl < atr * 0.6:
        return None
    steps = [pole_closes[i + 1] - pole_closes[i] for i in range(len(pole_closes) - 1)]
    same = sum(1 for s in steps if (s > 0) == bull)
    if steps and same / len(steps) < 0.6:
        return None
    pr_hi, pr_lo = max(pole_closes), min(pole_closes)
    pr_rng = (pr_hi - pr_lo) or 1e-9
    pos = (closes[Bidx] - pr_lo) / pr_rng
    if (bull and pos < 0.80) or (not bull and pos > 0.20):
        return None

    _, _, pole_r2 = _linreg_seq(pole_closes)
    if pole_r2 < 0.85:
        return None
    max_pull, run_ext = 0.0, pole_closes[0]
    for v in pole_closes:
        if bull:
            run_ext = max(run_ext, v); max_pull = max(max_pull, run_ext - v)
        else:
            run_ext = min(run_ext, v); max_pull = max(max_pull, v - run_ext)
    if max_pull > 0.20 * pole_h:
        return None

    body_hi = highs[Bidx:n - 1]
    body_lo = lows[Bidx:n - 1]
    body_cl = closes[Bidx:n - 1]
    Lb = len(body_hi)
    if Lb < 4:
        return None
    top, bot = max(body_hi), min(body_lo)
    cons_h = top - bot

    retro = (P_B - bot) / pole_h if bull else (top - P_B) / pole_h
    if retro >= 0.50:
        return None

    if cons_h > 0.40 * pole_h:
        return None
    flag_tr = sum(_true_range(highs, lows, closes, i)
                  for i in range(Bidx + 1, n - 1)) / max(1, (n - 1) - (Bidx + 1))
    pole_tr = sum(_true_range(highs, lows, closes, i)
                  for i in range(Aidx + 1, Bidx + 1)) / max(1, Bidx - Aidx)
    if pole_tr > 0 and flag_tr > 0.60 * pole_tr:
        return None

    m_sup, b_sup, _ = _linreg_seq(body_hi)
    m_inf, b_inf, _ = _linreg_seq(body_lo)
    m_mid, _, _ = _linreg_seq(body_cl)

    conv = (m_sup < -eps and m_inf > eps)

    if bull and m_mid > eps and conv:
        return None
    if not bull and m_mid < -eps and conv:
        return None

    diff = abs(m_sup - m_inf) / max(abs(m_sup), abs(m_inf), eps)
    if conv:
        variante = "banderin"
    elif diff < 0.30:
        variante = "bandera"
    else:
        return None

    running = (bull and m_mid > eps) or (not bull and m_mid < -eps)

    thr = max(0.5 * atr, 0.003 * closes[-1])
    x_break = Lb
    sup_proj = m_sup * x_break + b_sup
    inf_proj = m_inf * x_break + b_inf
    if bull:
        confirmada = closes[-1] > sup_proj + thr
    else:
        confirmada = closes[-1] < inf_proj - thr

    vol_bonus = 0.0
    if volumes and len(volumes) >= n:
        prior = volumes[max(0, Aidx - 30):Aidx]
        pole_v = volumes[Aidx:Bidx + 1]
        body_v = volumes[Bidx:n - 1]
        if prior and pole_v and sum(pole_v) / len(pole_v) >= 1.5 * (sum(prior) / len(prior)):
            vol_bonus += 0.15
        if len(body_v) >= 3 and _linreg_seq(body_v)[0] < 0:
            vol_bonus += 0.15

    def _line_val(m, b, idx):
        return m * (idx - Bidx) + b
    C_idx = n - 2
    if confirmada:
        D_idx, D_price = n - 1, closes[-1]
    else:
        D_idx = n - 2
        D_price = _line_val(m_sup, b_sup, n - 2) if bull else _line_val(m_inf, b_inf, n - 2)
    tgt_price = D_price + pole_h if bull else D_price - pole_h
    tgt_idx = (n - 1) + max(3, pl)

    def _pt(idx, price):
        return {"index": int(idx), "price": round(float(price), 2)}

    puntos = [
        {"label": "A", **_pt(Aidx, P_A)},
        {"label": "B", **_pt(Bidx, P_B)},
        {"label": "C", **_pt(C_idx, closes[C_idx])},
        {"label": "D", **_pt(D_idx, D_price)},
        {"label": "objetivo", **_pt(tgt_idx, tgt_price)},
    ]
    lineas = [
        {"kind": "mastil",   "points": [_pt(Aidx, P_A), _pt(Bidx, P_B)]},
        {"kind": "superior", "points": [_pt(Bidx, _line_val(m_sup, b_sup, Bidx)),
                                        _pt(n - 2, _line_val(m_sup, b_sup, n - 2))]},
        {"kind": "inferior", "points": [_pt(Bidx, _line_val(m_inf, b_inf, Bidx)),
                                        _pt(n - 2, _line_val(m_inf, b_inf, n - 2))]},
        {"kind": "objetivo", "points": [_pt(D_idx, D_price), _pt(tgt_idx, tgt_price)]},
    ]

    score = (pole_r2 + min(move, 0.5) + (0.5 - min(retro, 0.5))
             + (0.2 if confirmada else 0.0) + vol_bonus)

    return {
        "_score": score, "variante": variante, "bull": bull,
        "confirmada": confirmada, "running": running, "retro": retro,
        "puntos": puntos, "lineas": lineas,
    }


def _detect_flag_pennant(highs, lows, closes, volumes=None):
    """BANDERA / BANDERÍN (flag / pennant): CONTINUACIÓN = mástil impulsivo casi rectilíneo +
    consolidación breve, estrecha e inclinada EN CONTRA del mástil. Bandera = rectas casi
    paralelas; banderín = rectas convergentes. Rechaza canal/rectángulo, triángulo grande,
    cuña de reversión, retroceso profundo y mástil ruidoso."""
    n = len(closes)
    if n < 18:
        return None
    atr = _atr(highs, lows, closes) or (sum(closes) / n) * 0.01
    avg = sum(closes[-40:]) / len(closes[-40:])
    eps = max(atr * 0.05, avg * 0.0003)

    best = None
    for cons in range(5, 21):
        Bidx = n - 1 - cons
        if Bidx < 4:
            break
        for direction in ("bull", "bear"):
            cand = _eval_flag(highs, lows, closes, volumes, Bidx, cons, direction, atr, eps)
            if cand and (best is None or cand["_score"] > best["_score"]):
                best = cand
    if best is None:
        return None

    bull = best["bull"]
    sentido = "alcista" if bull else "bajista"
    if best["variante"] == "bandera":
        tipo = "bandera_alcista" if bull else "bandera_bajista"
        nombre = "Bandera " + sentido
        geo = ("una consolidación breve y estrecha entre dos rectas casi paralelas "
               "que derivan " + ("ligeramente a la baja" if bull else "ligeramente al alza"))
    else:
        tipo = "banderin_alcista" if bull else "banderin_bajista"
        nombre = "Banderín " + sentido
        geo = "una pequeña consolidación entre dos rectas convergentes (triángulo)"

    accion = ("ruptura al alza de la recta superior reanuda la subida"
              if bull else "ruptura a la baja de la recta inferior reanuda el descenso")
    desc = ("Mástil " + sentido + " casi rectilíneo seguido de " + geo + ". "
            "Patrón de CONTINUACIÓN: la " + accion + "; objetivo = altura del mástil "
            "proyectada desde la ruptura (measure rule).")
    if best["running"]:
        desc += " Nota: la consolidación se inclina a favor de la tendencia (running flag), válida pero menos fiable."
    if best["confirmada"]:
        desc += " Ruptura ya CONFIRMADA por cierre."
    else:
        desc += " Aún sin confirmar: esperar cierre más allá de la recta (>=0.5xATR)."

    return {
        "tipo": tipo, "nombre": nombre, "sentido": sentido, "descripcion": desc,
        "confirmada": best["confirmada"], "retroceso": round(best["retro"], 2),
        "puntos": best["puntos"], "lineas": best["lineas"],
    }


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


# ═════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 de detectores (escritos desde la investigación): suelo/techo redondeado,
# isla de vuelta, diamante, hueco, pipe, tres valles/picos, taza sin asa.
# ═════════════════════════════════════════════════════════════════════════════

def _parabola_fit(ys):
    """Ajusta y = a·x² + b·x + c por MCO y devuelve (a, b, c, r2). Python puro."""
    n = len(ys)
    if n < 3:
        return 0.0, 0.0, (ys[0] if ys else 0.0), 0.0
    xs = list(range(n))
    Sx = sum(xs); Sx2 = sum(x * x for x in xs)
    Sx3 = sum(x ** 3 for x in xs); Sx4 = sum(x ** 4 for x in xs)
    Sy = sum(ys); Sxy = sum(x * y for x, y in zip(xs, ys))
    Sx2y = sum(x * x * y for x, y in zip(xs, ys))
    A = [[Sx4, Sx3, Sx2, Sx2y], [Sx3, Sx2, Sx, Sxy], [Sx2, Sx, n, Sy]]
    for i in range(3):
        piv = A[i][i]
        if abs(piv) < 1e-12:
            return 0.0, 0.0, Sy / n, 0.0
        for j in range(i, 4):
            A[i][j] /= piv
        for k in range(3):
            if k != i:
                f = A[k][i]
                for j in range(i, 4):
                    A[k][j] -= f * A[i][j]
    a, b, c = A[0][3], A[1][3], A[2][3]
    my = Sy / n
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((ys[x] - (a * x * x + b * x + c)) ** 2 for x in xs)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return a, b, c, r2


def _detect_rounding(highs, lows, closes):
    """Suelo redondeado (U, alcista) / techo redondeado (domo, bajista): giro suave en arco
    parabólico. Exige ajuste de parábola R²>=0.85, vértice centrado (30-70%) y tendencia
    previa contraria. Devuelve dict con arco de dibujo o None."""
    n = len(closes)
    if n < 30:
        return None
    look = min(n, 160)
    off = n - look
    C = closes[off:]
    m = len(C)
    a, b, c, r2 = _parabola_fit(C)
    if r2 < 0.85 or a == 0:
        return None
    vx = -b / (2 * a)
    if not (0.30 * m <= vx <= 0.70 * m):          # vértice en la franja central (simetría)
        return None
    price = sum(C) / m
    depth = (max(C) - min(C))
    if depth / price < 0.06:                        # demasiado plano = ruido
        return None
    # curvatura mínima: la parábola debe explicar buena parte de la profundidad.
    if abs(a) * m * m < 0.5 * depth:
        return None
    suelo = a > 0                                   # a>0 => cóncava hacia arriba => U (suelo)
    # tendencia previa CONTRARIA (hacia el primer borde de la ventana).
    pre = closes[max(0, off - 40):off]
    if pre:
        drift = (C[0] - pre[0]) / (abs(pre[0]) or 1)
        if suelo and drift > -0.05:                 # suelo redondeado exige bajada previa
            return None
        if not suelo and drift < 0.05:              # techo exige subida previa
            return None
    vi = int(round(vx))
    r = lambda x: round(float(x), 2)
    arco = {"tipo": "arco", "points": [
        {"index": int(off), "price": r(C[0])},
        {"index": int(off + vi), "price": r(min(C) if suelo else max(C))},
        {"index": int(n - 1), "price": r(C[-1])}]}
    if suelo:
        return {"tipo": "suelo_redondeado", "nombre": "Suelo redondeado", "sentido": "alcista",
                "descripcion": ("Giro suave en 'U' ancha (platillo): reversión ALCISTA de largo plazo. "
                                "Se compra en la ruptura del nivel del borde con volumen creciente."),
                "puntos": [arco]}
    return {"tipo": "techo_redondeado", "nombre": "Techo redondeado", "sentido": "bajista",
            "descripcion": ("Giro suave en domo ('n'): reversión BAJISTA de largo plazo. Se vende al "
                            "perder el nivel del borde."),
            "puntos": [arco]}


def _detect_island(highs, lows, closes, atr):
    """Isla de vuelta: grupo compacto de K velas aislado por DOS huecos opuestos al mismo
    nivel. Techo (tras subida) o suelo (tras bajada). Devuelve dict o None."""
    n = len(closes)
    if n < 25:
        return None
    gmin = max(0.3 * atr, 0.005 * closes[-1])
    # buscamos el hueco-2 (ruptura) reciente y su hueco-1 (agotamiento) unas K velas antes.
    for last in range(n - 1, n - 12, -1):
        if last < 6:
            break
        # hueco2 entre (last-1) e (last)?
        gap2_baj = highs[last] < lows[last - 1] - gmin      # isla de TECHO cierra con hueco bajista
        gap2_alc = lows[last] > highs[last - 1] + gmin      # isla de SUELO cierra con hueco alcista
        if not (gap2_baj or gap2_alc):
            continue
        techo = gap2_baj
        # la isla = [first..last-1]; buscamos hueco1 al inicio (mismo nivel, sentido opuesto).
        for first in range(last - 1, max(0, last - 9), -1):
            if first < 1:
                break
            if techo:
                gap1 = lows[first] > highs[first - 1] + gmin    # hueco alcista de agotamiento
                mismo_nivel = abs(highs[last] - highs[first - 1]) < 3 * atr
            else:
                gap1 = highs[first] < lows[first - 1] - gmin    # hueco bajista de agotamiento
                mismo_nivel = abs(lows[last] - lows[first - 1]) < 3 * atr
            if not (gap1 and mismo_nivel):
                continue
            # tendencia previa (10-30 velas antes de first-1) en el sentido a revertir.
            pre = closes[max(0, first - 25):first]
            if len(pre) < 8:
                continue
            trend = (closes[first - 1] - pre[0]) / (abs(pre[0]) or 1)
            if techo and trend < 0.08:
                continue
            if not techo and trend > -0.08:
                continue
            r = lambda x: round(float(x), 2)
            isla = [{"index": int(i), "price": r(closes[i])} for i in range(first, last)]
            if techo:
                return {"tipo": "isla_techo", "nombre": "Isla de vuelta (techo)", "sentido": "bajista",
                        "descripcion": ("Grupo de velas aislado por dos huecos opuestos tras una subida: "
                                        "reversión BAJISTA potente. Confirma el hueco de ruptura a la baja."),
                        "puntos": isla}
            return {"tipo": "isla_suelo", "nombre": "Isla de vuelta (suelo)", "sentido": "alcista",
                    "descripcion": ("Grupo de velas aislado por dos huecos opuestos tras una caída: "
                                    "reversión ALCISTA potente. Confirma el hueco de ruptura al alza."),
                    "puntos": isla}
    return None


def _detect_three_rising(highs, lows, closes):
    """Tres valles ascendentes (alcista) / tres picos descendentes (bajista). Tres swings del
    mismo tipo monótonos (>=1% cada paso), homogéneos, sin violación estructural."""
    n = len(closes)
    if n < 25:
        return None
    lo = _pivots(lows, "low", 3, 3)
    hi = _pivots(highs, "high", 3, 3)
    # 3 valles ascendentes
    if len(lo) >= 3:
        v1, v2, v3 = lo[-3], lo[-2], lo[-1]
        l1, l2, l3 = lows[v1], lows[v2], lows[v3]
        if l1 > 0 and (l2 - l1) / l1 >= 0.01 and (l3 - l2) / l2 >= 0.01:
            # sin violación: entre v2 y v3 ningún cierre bajo l2
            if min(closes[v2:v3 + 1]) >= l2 * 0.995 and (v3 - v1) >= 12:
                r = lambda x: round(float(x), 2)
                pts = [{"index": int(v), "price": r(lows[v]), "punto": f"V{k+1}"} for k, v in enumerate((v1, v2, v3))]
                return {"tipo": "tres_valles", "nombre": "Tres valles ascendentes", "sentido": "alcista",
                        "descripcion": ("Tres mínimos consecutivos cada vez más altos: la presión compradora "
                                        "gana terreno. Sesgo ALCISTA; ruptura del último pico lo confirma."),
                        "puntos": pts,
                        "lineas": [{"tipo": "soporte_asc", "points": [pts[0], pts[2]]}]}
    # 3 picos descendentes
    if len(hi) >= 3:
        p1, p2, p3 = hi[-3], hi[-2], hi[-1]
        h1, h2, h3 = highs[p1], highs[p2], highs[p3]
        if h1 > 0 and (h1 - h2) / h1 >= 0.01 and (h2 - h3) / h2 >= 0.01:
            if max(closes[p2:p3 + 1]) <= h2 * 1.005 and (p3 - p1) >= 12:
                r = lambda x: round(float(x), 2)
                pts = [{"index": int(p), "price": r(highs[p]), "punto": f"P{k+1}"} for k, p in enumerate((p1, p2, p3))]
                return {"tipo": "tres_picos", "nombre": "Tres picos descendentes", "sentido": "bajista",
                        "descripcion": ("Tres máximos consecutivos cada vez más bajos: la presión vendedora "
                                        "domina. Sesgo BAJISTA; pérdida del último valle lo confirma."),
                        "puntos": pts,
                        "lineas": [{"tipo": "resistencia_desc", "points": [pts[0], pts[2]]}]}
    return None


def _detect_pipe(highs, lows, closes, lookback: int = 52):
    """Pipe bottom/top (Bulkowski): dos velas ADYACENTES con picos gemelos muy largos (>=2x el
    rango medio previo) y gran solapamiento (>=50%). Suelo (tras bajada) / techo (tras subida)."""
    n = len(closes)
    if n < 20:
        return None
    i = n - 2                                        # las dos últimas velas
    j = n - 1
    rng_i = highs[i] - lows[i]
    rng_j = highs[j] - lows[j]
    if rng_i <= 0 or rng_j <= 0:
        return None
    prev = [highs[k] - lows[k] for k in range(max(0, i - lookback), i)]
    if len(prev) < 10:
        return None
    avg = sum(prev) / len(prev)
    if rng_i < 2.0 * avg or rng_j < 2.0 * avg:       # picos mucho más largos que la media
        return None
    overlap = min(highs[i], highs[j]) - max(lows[i], lows[j])
    if overlap / min(rng_i, rng_j) < 0.50:           # gran solapamiento vertical
        return None
    pre = closes[max(0, i - 20):i]
    if len(pre) < 8:
        return None
    trend = (closes[i] - pre[0]) / (abs(pre[0]) or 1)
    r = lambda x: round(float(x), 2)
    pts = [{"index": int(i), "price": r(lows[i])}, {"index": int(j), "price": r(lows[j])}]
    if trend < -0.08:                                # bajada previa → pipe bottom (alcista)
        return {"tipo": "pipe_bottom", "nombre": "Pipe bottom (suelo en tubo)", "sentido": "alcista",
                "descripcion": ("Dos velas gemelas de rango muy largo tras una caída: suelo de reversión "
                                "ALCISTA (Bulkowski). Compra sobre el máximo de las dos velas."),
                "puntos": pts}
    if trend > 0.08:                                 # subida previa → pipe top (bajista)
        return {"tipo": "pipe_top", "nombre": "Pipe top (techo en tubo)", "sentido": "bajista",
                "descripcion": ("Dos velas gemelas de rango muy largo tras una subida: techo de reversión "
                                "BAJISTA (Bulkowski). Vende bajo el mínimo de las dos velas."),
                "puntos": [{"index": int(i), "price": r(highs[i])}, {"index": int(j), "price": r(highs[j])}]}
    return None


def _detect_diamond(highs, lows, closes):
    """Diamante (top/bottom): ensanchamiento (izquierda diverge) seguido de contracción
    (derecha converge). Rombo de 4 vértices. Requiere >=5 pivotes alternos."""
    n = len(closes)
    if n < 30:
        return None
    look = min(n, 140)
    off = n - look
    seq = _alternating_swings(highs[off:], lows[off:])
    if len(seq) < 6:
        return None
    seq = seq[-9:]
    # centro = pivote de mayor amplitud (donde el rombo es más ancho). Partimos la serie.
    idxs = [p[0] for p in seq]
    mid = len(seq) // 2
    left = seq[:mid + 1]
    right = seq[mid:]
    if len(left) < 3 or len(right) < 3:
        return None
    hL = [p[2] for p in left if p[1] == "H"]; lL = [p[2] for p in left if p[1] == "L"]
    hR = [p[2] for p in right if p[1] == "H"]; lR = [p[2] for p in right if p[1] == "L"]
    if len(hL) < 2 or len(lL) < 2 or len(hR) < 2 or len(lR) < 2:
        return None
    # Fase 1: máximos crecientes + mínimos decrecientes (diverge).
    if not (hL[-1] > hL[0] and lL[-1] < lL[0]):
        return None
    # Fase 2: máximos decrecientes + mínimos crecientes (converge).
    if not (hR[-1] < hR[0] and lR[-1] > lR[0]):
        return None
    spread_c = max(hL[-1], hR[0]) - min(lL[-1], lR[0])
    spread_L = hL[0] - lL[0]
    spread_R = hR[-1] - lR[-1]
    if spread_L <= 0 or spread_R <= 0 or spread_c <= 0:
        return None
    if spread_c / spread_L < 1.3 or spread_c / spread_R < 1.3:   # ensancha y luego contrae
        return None
    price = sum(closes[off:]) / look
    prev = closes[max(0, off - 30):off]
    up = bool(prev) and (closes[off] - prev[0]) / (abs(prev[0]) or 1) > 0.08
    r = lambda x: round(float(x), 2)
    T = max(seq, key=lambda p: p[2]); B = min(seq, key=lambda p: p[2])
    vertices = [{"index": int(idxs[0] + off), "price": r(seq[0][2]), "punto": "L"},
                {"index": int(T[0] + off), "price": r(T[2]), "punto": "T"},
                {"index": int(B[0] + off), "price": r(B[2]), "punto": "B"},
                {"index": int(idxs[-1] + off), "price": r(seq[-1][2]), "punto": "R"}]
    sentido = "bajista" if up else "alcista"
    return {"tipo": "diamante", "nombre": "Diamante " + ("de techo" if up else "de suelo"),
            "sentido": sentido,
            "descripcion": ("Rombo: primero la volatilidad se ensancha (diverge) y luego se contrae "
                            "(converge). Reversión " + ("BAJISTA tras subida" if up else "ALCISTA tras caída") +
                            "; la ruptura de la directriz de la fase de contracción confirma."),
            "puntos": vertices}


def _detect_cup_no_handle(closes, highs=None, lows=None):
    """Taza SIN asa (cup without handle): U redondeada con bordes ~iguales y subida previa, que
    rompe la resistencia SIN consolidación (asa). Reutiliza la geometría de la taza."""
    n = len(closes)
    if highs is None:
        highs = closes
    if lows is None:
        lows = closes
    if n < 40:
        return None
    W = min(n, 300)
    off = n - W
    H = highs[off:]; L = lows[off:]
    m = len(H)
    hi = _pivots(H, "high", 3, 3)
    if len(hi) < 2:
        return None
    best = None
    for p2 in hi:
        if m - 1 - p2 > 5:                 # borde derecho debe estar CERCA del final (sin asa larga)
            continue
        for p0 in hi:
            width = p2 - p0
            if width < 25 or width > 300:
                continue
            rim = max(H[p0], H[p2])
            if abs(H[p0] - H[p2]) / H[p0] > 0.05:
                continue
            seg = L[p0:p2 + 1]
            lo = min(seg); p1 = p0 + seg.index(lo)
            depth_abs = rim - lo
            if depth_abs <= 0:
                continue
            depth = depth_abs / rim
            if not (0.12 <= depth <= 0.50):
                continue
            if not (0.30 <= (p1 - p0) / width <= 0.70):     # fondo centrado
                continue
            lower_third = lo + 0.33 * depth_abs
            nb = [k for k in range(p0, p2 + 1) if L[k] <= lower_third]
            if len(nb) < 5 or (nb[-1] - nb[0]) < 0.20 * width:
                continue
            if _quad_curvature(seg) <= 0:                    # U, no V
                continue
            gi = p0 + off
            if gi >= 20:
                prev = lows[max(0, gi - 60):gi]
                if prev and (H[p0] - min(prev)) / min(prev) < 0.30:   # subida previa >=30%
                    continue
            score = (1.0 - abs(depth - 0.22), width)
            if best is None or score > best[0]:
                best = (score, p0, p1, p2, rim, lo, depth_abs)
    if best is None:
        return None
    _, p0, p1, p2, rim, lo, depth_abs = best
    r = lambda x: round(float(x), 2)
    gi = lambda k: int(k + off)
    pivote = rim
    objetivo = pivote + depth_abs
    return {"tipo": "taza_sin_asa", "nombre": "Taza sin asa", "sentido": "alcista",
            "descripcion": ("Fondo redondeado en 'U' con bordes al mismo nivel tras una subida previa, que "
                            "rompe la resistencia %.2f SIN consolidación (asa). Continuación alcista; objetivo "
                            "%.2f (pivote + profundidad)." % (round(pivote, 2), round(objetivo, 2))),
            "pivote": round(float(pivote), 2), "objetivo": round(float(objetivo), 2),
            "puntos": [{"index": gi(p0), "price": r(H[p0]), "punto": "P1"},
                       {"index": gi(p1), "price": r(lo), "punto": "P2"},
                       {"index": gi(p2), "price": r(H[p2]), "punto": "P3"}],
            "lineas": [{"tipo": "arco_taza", "points": [{"index": gi(p0), "price": r(rim)},
                                                        {"index": gi(p1), "price": r(lo)},
                                                        {"index": gi(p2), "price": r(rim)}]},
                       {"tipo": "resistencia", "points": [{"index": gi(p0), "price": r(pivote)},
                                                          {"index": int(n - 1), "price": r(pivote)}]}]}


def _detect_gap(highs, lows, closes, volumes, atr):
    """Hueco (gap) reciente significativo: banda de precio sin solape entre dos velas. Clasifica
    breakaway/runaway/agotamiento por volumen si está disponible. Informativo (baja prioridad)."""
    n = len(closes)
    if n < 5:
        return None
    gmin = max(0.01 * closes[-1], 0.5 * atr)
    for i in range(n - 1, max(0, n - 6), -1):
        alc = lows[i] > highs[i - 1] + gmin
        baj = highs[i] < lows[i - 1] - gmin
        if not (alc or baj):
            continue
        size = (lows[i] - highs[i - 1]) if alc else (lows[i - 1] - highs[i])
        clase = "hueco"
        if volumes and len(volumes) >= n:
            sma = sum(volumes[max(0, i - 20):i]) / max(1, len(volumes[max(0, i - 20):i]))
            if sma:
                ratio = volumes[i] / sma
                post = volumes[i + 1:i + 4]
                colapso = post and (sum(post) / len(post)) < 0.8 * sma
                if ratio >= 2 and colapso:
                    clase = "hueco de agotamiento"
                elif ratio >= 1.5 and not colapso:
                    clase = "hueco de ruptura/continuación"
        sentido = "alcista" if alc else "bajista"
        lo_b = highs[i - 1] if alc else highs[i]
        hi_b = lows[i] if alc else lows[i - 1]
        r = lambda x: round(float(x), 2)
        return {"tipo": "hueco", "nombre": clase.capitalize() + (" alcista" if alc else " bajista"),
                "sentido": sentido,
                "descripcion": ("Hueco %s del %.1f%%: el precio salta sin negociar entre %.2f y %.2f. Suele "
                                "actuar como soporte/resistencia; muchos se rellenan." %
                                (sentido, 100 * size / closes[i - 1], round(lo_b, 2), round(hi_b, 2))),
                "puntos": [{"tipo": "banda_hueco",
                            "points": [{"index": int(i - 1), "price": r(lo_b)}, {"index": int(n - 1), "price": r(lo_b)},
                                       {"index": int(i - 1), "price": r(hi_b)}, {"index": int(n - 1), "price": r(hi_b)}]}]}
    return None


_LINE_KEYS = {"superior", "inferior", "base", "neckline", "cuello", "soporte", "resistencia",
              "arco", "arco_taza", "mitad_taza", "asa", "objetivo", "soporte_asc",
              "resistencia_desc", "banda_hueco", "buy_line"}


def _pattern_drawables(pattern):
    """Normaliza la geometría heterogénea de cualquier patrón (lineas/puntos/trendlines/
    pivotes/neckline) a un formato ÚNICO para el frontend:
        {"lines": [{"tipo", "points":[{index,price}...]}], "markers": [{index,price,tipo}]}
    Así el gráfico Pro dibuja cualquier patrón sin conocer su estructura interna."""
    if not pattern:
        return None
    lines, markers = [], []

    def is_point(d):
        return isinstance(d, dict) and "index" in d and "price" in d and "points" not in d

    def label_of(d):
        return d.get("label") or d.get("etiqueta") or d.get("punto") or ""

    def add_marker(q, key):
        markers.append({"index": q["index"], "price": q["price"], "tipo": key, "label": label_of(q)})

    def add_line(pts, tipo):
        p = [{"index": q["index"], "price": q["price"]} for q in pts
             if isinstance(q, dict) and q.get("index") is not None and q.get("price") is not None]
        if len(p) >= 2:
            lines.append({"tipo": tipo, "points": p})
        elif len(p) == 1:
            markers.append({**p[0], "tipo": tipo, "label": ""})

    def walk(obj, key=""):
        if isinstance(obj, dict):
            if isinstance(obj.get("points"), list):
                add_line(obj["points"], obj.get("tipo") or obj.get("kind") or key)
                return
            if is_point(obj):
                add_marker(obj, key)
                return
            for k, v in obj.items():
                walk(v, k)
        elif isinstance(obj, list):
            if obj and is_point(obj[0]):
                if key in _LINE_KEYS:
                    add_line(obj, key)
                else:
                    for q in obj:
                        if is_point(q):
                            add_marker(q, key)
            else:
                for v in obj:
                    walk(v, key)

    for key in ("lineas", "trendlines", "puntos", "pivotes", "neckline"):
        if key in pattern:
            walk(pattern[key], key)
    if not lines and not markers:
        return None
    return {"lines": lines, "markers": markers,
            "nombre": pattern.get("nombre"), "sentido": pattern.get("sentido")}


def detect_lines(candles: List[Dict], current_price: float = None) -> Dict:
    """Punto de entrada. `candles` = lista de dicts con high/low/close (y opcionalmente
    fecha). Devuelve líneas de tendencia + niveles horizontales, en coordenadas de índice
    de vela (el frontend las mapea a la escala temporal del gráfico)."""
    if not candles or len(candles) < 15:
        return {"trendlines": [], "levels": [], "pattern": None, "candlestick": None, "zones": []}
    highs = [float(c.get("high") or c.get("h") or c.get("close") or 0) for c in candles]
    lows = [float(c.get("low") or c.get("l") or c.get("close") or 0) for c in candles]
    closes = [float(c.get("close") or c.get("c") or 0) for c in candles]
    _vol = [float(c.get("volume") or c.get("v") or 0) for c in candles]
    volumes = _vol if any(_vol) else None
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

    # Doble suelo (W) / doble techo (M) — detector RIGUROSO (extremos ~iguales, cuello,
    # tendencia previa, simetría; rechaza V, redondeado, triple, H&S y fakeout).
    price_range = max(highs) - min(lows) if highs else 0
    _atr14v = _atr(highs, lows, closes, 14)
    pattern = _detect_double(highs, lows, closes)
    # Triple techo / triple suelo (reversión mayor de 5 pivotes): prioridad alta.
    if pattern is None:
        pattern = _detect_triple_top_bottom(highs, lows, closes)
    # Isla de vuelta y pipe (reversiones potentes por huecos / velas gemelas): prioridad alta.
    if pattern is None:
        pattern = _detect_island(highs, lows, closes, _atr14v)
    if pattern is None:
        pattern = _detect_pipe(highs, lows, closes)
    # BANDERA / BANDERÍN RIGUROSO (mástil impulsivo + consolidación breve contra-tendencia).
    if pattern is None:
        pattern = _detect_flag_pennant(highs, lows, closes, volumes)

    # Taza con asa y base plana (favoritos de ruptura de máximos): prioridad alta.
    if pattern is None:
        pattern = _detect_cup_handle(closes, highs, lows, volumes)
    if pattern is None:
        pattern = _detect_cup_no_handle(closes, highs, lows)
    if pattern is None:
        pattern = _detect_flat_base(closes, highs, lows, volumes)
    # Cabeza y hombros y diamante (reversión) antes de los patrones de directriz.
    if pattern is None:
        pattern = _detect_head_shoulders(highs, lows, closes, price_range)
    if pattern is None:
        pattern = _detect_diamond(highs, lows, closes)
    # Suelo/techo redondeado y tres valles/picos.
    if pattern is None:
        pattern = _detect_rounding(highs, lows, closes)
    if pattern is None:
        pattern = _detect_three_rising(highs, lows, closes)
    # Triángulos y cuñas RIGUROSOS (regresión + apex + toques): tienen prioridad sobre la
    # lógica laxa de _detect_pattern. Cuña primero (más restrictiva), luego triángulo.
    if pattern is None:
        pattern = _detect_wedge(highs, lows, closes)
    if pattern is None:
        pattern = _detect_triangles(highs, lows, closes)
    # Canal ASC/DESC (rectas paralelas): antes de la lógica laxa de directrices.
    if pattern is None:
        pattern = _detect_channel(highs, lows, closes)
    # Rectángulo / rango lateral horizontal.
    if pattern is None:
        pattern = _detect_rectangle(highs, lows, closes, volumes)
    # Si nada de lo anterior, prueba la lógica laxa de directrices (canal/consolidación).
    if pattern is None:
        pattern = _detect_pattern(trendlines, levels, closes, current_price)
    # Megáfono (a evitar): último recurso, solo si no hay nada mejor. Dibuja sus dos rectas.
    if pattern is None:
        pattern = _detect_broadening(highs, lows, closes)
        if pattern:
            trendlines.extend(pattern.pop("trendlines", []))
    # Hueco reciente significativo: informativo, solo si no hay estructura mayor.
    if pattern is None:
        pattern = _detect_gap(highs, lows, closes, volumes, _atr14v)

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
            "candlestick": candlestick, "zones": zones,
            "pattern_draw": _pattern_drawables(pattern)}
