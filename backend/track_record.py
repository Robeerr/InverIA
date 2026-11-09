"""Track record del sistema — el auto-examen honesto de InverIA.

Coge las recomendaciones de COMPRA que el motor dio en el pasado (guardadas en
db.analyses) y mira qué hizo el precio DESPUÉS: ¿tocó antes el take-profit (acierto)
o el stop (fallo)? Devuelve estadísticas agregadas (aciertos, fallos, abiertas,
% de acierto, retorno medio) para que sepas si fiarte del motor — sin autoengaño.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger("inveria.trackrecord")


def _iso_to_dt(s):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None


def _num(x):
    try:
        v = float(x)
        return v if v == v else None  # descarta NaN
    except (TypeError, ValueError):
        return None


def evaluate_signal(entry, tp1, sl, future):
    """Lógica pura del resultado de una señal de compra (evaluada contra TP1).

    `future` = lista de velas posteriores a la señal, cada una (high, low, close),
    en orden cronológico. Determina qué se tocó ANTES: el stop (fallo) o el TP1
    (acierto). Si no se toca ninguno, queda 'abierta'. Devuelve (resultado, retorno_%).
    El retorno es el del punto de cierre (TP/stop) o el actual si sigue abierta.
    """
    ev = evaluar_con_cierre(entry, tp1, sl, future, etiqueta="tp1")
    return ev[:2] if ev else None


def evaluar_con_cierre(entry, objetivo, sl, future, etiqueta="tp1"):
    """Como evaluate_signal, pero dice además EN QUÉ VELA se cerró la señal.

    Devuelve (resultado, retorno_%, índice_de_cierre) — el índice es None si sigue
    abierta. Hace falta para comparar con el índice en la misma ventana que la señal:
    una operación cerrada en tres días no puede medirse contra lo que hizo el S&P en tres
    meses.
    """
    entry = _num(entry)
    if not entry:
        return None
    objetivo, sl = _num(objetivo), _num(sl)
    if not future:
        return None
    for i, (hi, lo, _close) in enumerate(future):
        hi, lo = _num(hi), _num(lo)
        # El stop se comprueba primero (criterio conservador: ante la duda, cuenta el peor caso).
        if sl and lo is not None and lo <= sl:
            return ("stop", round((sl - entry) / entry * 100, 1), i)
        if objetivo and hi is not None and hi >= objetivo:
            return (etiqueta, round((objetivo - entry) / entry * 100, 1), i)
    last_close = _num(future[-1][2])
    cur = round((last_close - entry) / entry * 100, 1) if last_close else None
    return ("abierta", cur, None)


def evaluate_signal_tp2(entry, tp2, sl, future):
    """Igual que evaluate_signal pero contra el SEGUNDO objetivo (TP2): refleja el
    resultado si aguantas la posición hasta el objetivo mayor en vez de cerrar en TP1.
    Devuelve (resultado, retorno_%) con resultado en {'tp2','stop','abierta'}."""
    ev = evaluar_con_cierre(entry, tp2, sl, future, etiqueta="tp2")
    return ev[:2] if ev else None


#: Tamaño de operación con el que se calculan los costes. El Track record no sabe cuánto
#: habrías metido en cada señal, y los 2 € fijos de DEGIRO pesan muy distinto en 300 € que
#: en 3.000 €. Se fija uno explícito, y se enseña en pantalla, en vez de ignorar los costes.
IMPORTE_REFERENCIA_EUR = 1000.0


def coste_ida_vuelta_pct(importe_eur: float = IMPORTE_REFERENCIA_EUR) -> float:
    """Lo que cuesta comprar Y vender una acción de EE.UU. en DEGIRO, en % del importe.

    Dos órdenes (2 € cada una) más la conversión AutoFX al comprar y al vender. Usa las
    mismas constantes que comisiones.py para que una tarifa nueva cambie las dos cosas.
    """
    import comisiones
    importe = max(float(importe_eur or 0), 1.0)
    fijo = 2 * comisiones.COMISION_FIJA_EUR / importe * 100
    divisa = 2 * comisiones.FX_AUTO_PCT * 100
    return round(fijo + divisa, 2)


def deduplicar_senales(sigs):
    """Una señal por símbolo, día y precio de entrada.

    Regenerar el análisis el mismo día guardaba otra recomendación idéntica, y el Track
    record la contaba dos veces: inflaba la muestra y duplicaba cada acierto o fallo. Se
    conserva la versión más reciente del día, que es la que viste por última vez. Un
    análisis con el precio ya movido es otra decisión y se mantiene.
    """
    elegidas = {}
    for s in sigs:
        clave = (s["created"].date(), round(float(s["entry"]), 2))
        actual = elegidas.get(clave)
        if actual is None or s["created"] > actual["created"]:
            elegidas[clave] = s
    return sorted(elegidas.values(), key=lambda s: s["created"], reverse=True)


def retorno_indice_en_ventana(fechas, cierres, desde, hasta=None):
    """Retorno % del índice desde el último cierre anterior a `desde` hasta `hasta`.

    La señal entra al precio del momento del análisis y su vela siguiente ya cuenta para
    el resultado, así que el índice tiene que empezar ANTES de esa vela: en el último
    cierre conocido cuando se hizo el análisis. Empezar en el cierre de la vela siguiente
    se comía justo el movimiento de ese día, y una señal cerrada en ella se comparaba
    siempre con un 0 %. `hasta` es la fecha de cierre de la señal; None si sigue abierta
    (se mide hasta hoy). Devuelve None si no hay datos: un hueco no se rellena con un
    número inventado.
    """
    if not fechas:
        return None
    siguiente = next((i for i in range(len(fechas)) if fechas[i] > desde), None)
    if siguiente is None:
        return None
    idx = max(siguiente - 1, 0)
    fin = len(fechas) - 1
    if hasta is not None:
        fin = max((i for i in range(len(fechas)) if fechas[i] <= hasta), default=None)
        if fin is None or fin < idx:
            return None
    base, last = _num(cierres[idx]), _num(cierres[fin])
    if not base or not last:
        return None
    return round((last - base) / base * 100, 1)


def _neto(retorno, coste_pct):
    return round(retorno - coste_pct, 1) if retorno is not None else None


def veredicto_benchmark(sistema_medio, spy_medio):
    """Qué se le puede decir al usuario sin engañarle.

    Batir al índice y ganar dinero son dos cosas distintas: si el mercado cae un 2,5 % y
    el motor un 0,7 %, el motor "bate" al índice pero tú has perdido dinero. La pantalla
    lo presentaba como "aporta valor"; este veredicto separa los cuatro casos.
    """
    if sistema_medio is None or spy_medio is None:
        return None
    gana = sistema_medio > 0
    bate = sistema_medio > spy_medio
    if gana and bate:
        return "gana_y_bate"
    if gana:
        return "gana_sin_batir"
    if bate:
        return "pierde_menos_que_indice"
    return "pierde_y_no_bate"


def construir_fila(sym, s, velas, spy_fechas, spy_closes, coste_pct):
    """Resultado de UNA señal, ya con costes, y el índice medido en su misma ventana.

    `velas` trae las listas fechas/highs/lows/closes del símbolo. `retorno` es neto de
    costes; `retorno_bruto` queda al lado para poder comprobar la resta. El índice lleva
    los mismos costes: comprar SPY tampoco es gratis, y compararlo sin ellos inflaría la
    ventaja del índice en vez de medirla.
    """
    fechas, highs, lows, closes = velas["fechas"], velas["highs"], velas["lows"], velas["closes"]
    created = s["created"].replace(tzinfo=None)
    inicio = next((i for i in range(len(fechas)) if fechas[i] > created), len(fechas))
    future = [(highs[i], lows[i], closes[i]) for i in range(inicio, len(fechas))]
    if future:
        ev = evaluar_con_cierre(s["entry"], s.get("tp1"), s.get("sl"), future)
    else:
        # Señal recién creada (sin velas posteriores aún): aparece ya como 'abierta' a
        # precio ~actual, para que veas al instante que se guardó.
        last = _num(closes[-1]) if closes else None
        ret = round((last - s["entry"]) / s["entry"] * 100, 1) if last else 0.0
        ev = ("abierta", ret, None)
    if not ev:
        return None
    resultado, retorno, i_cierre = ev
    fecha_cierre = fechas[inicio + i_cierre] if i_cierre is not None else None
    spy = retorno_indice_en_ventana(spy_fechas, spy_closes, created, fecha_cierre)
    fila = {
        "symbol": sym, "fecha": s["created"].date().isoformat(),
        "entrada": round(s["entry"], 2), "resultado": resultado,
        "retorno": _neto(retorno, coste_pct), "retorno_bruto": retorno,
        "spy_retorno": _neto(spy, coste_pct),
    }
    # Resultado alternativo aguantando hasta TP2 (si el análisis lo definió).
    ev2 = evaluate_signal_tp2(s["entry"], s.get("tp2"), s.get("sl"), future) if s.get("tp2") else None
    if ev2:
        fila["resultado_tp2"] = ev2[0]
        fila["retorno_tp2"] = _neto(ev2[1], coste_pct)
    return fila


async def compute_track_record(db, days: int = 180, min_age_days: int = 0) -> dict:
    """Evalúa las señales de COMPRA de los últimos `days` días (con al menos
    `min_age_days` de antigüedad para que haya recorrido). Agrupa por símbolo para
    traer el histórico de cada uno una sola vez."""
    import asyncio
    import market_data

    docs = await db.analyses.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    now = datetime.now(timezone.utc)
    by_symbol = defaultdict(list)
    for d in docs:
        res = d.get("result") or {}
        if (res.get("recommendation") or "").upper() != "COMPRAR":
            continue
        created = _iso_to_dt(d.get("created_at"))
        if not created:
            continue
        age = (now - created).days
        if age < min_age_days or age > days:
            continue
        entry = _num((d.get("quote_snapshot") or {}).get("price"))
        if not entry:
            continue
        by_symbol[d["symbol"]].append({
            "created": created, "entry": entry,
            "tp1": res.get("take_profit_1"), "tp2": res.get("take_profit_2"),
            "sl": res.get("stop_loss"),
        })

    # Índice de referencia (SPY): para cada señal, cuánto habría hecho el S&P 500 en la
    # MISMA ventana que la señal (de su fecha a su cierre, o a hoy si sigue abierta).
    try:
        spy_df = await asyncio.to_thread(market_data.get_full_indicator_history, "SPY")
        spy_fechas = spy_df["Date"].tolist()
        spy_closes = spy_df["Close"].tolist()
    except Exception:
        spy_fechas, spy_closes = [], []

    coste = coste_ida_vuelta_pct()
    señales = []
    duplicadas = 0
    for sym, sigs in by_symbol.items():
        try:
            df = await asyncio.to_thread(market_data.get_full_indicator_history, sym)
        except Exception:
            df = None
        if df is None or getattr(df, "empty", True):
            continue
        velas = {"fechas": df["Date"].tolist(), "highs": df["High"].tolist(),
                 "lows": df["Low"].tolist(), "closes": df["Close"].tolist()}
        unicas = deduplicar_senales(sigs)
        duplicadas += len(sigs) - len(unicas)
        for s in unicas:
            fila = construir_fila(sym, s, velas, spy_fechas, spy_closes, coste)
            if fila:
                señales.append(fila)

    señales.sort(key=lambda x: x["fecha"], reverse=True)
    cerradas = [s for s in señales if s["resultado"] in ("tp1", "stop")]
    abiertas = [s for s in señales if s["resultado"] == "abierta"]
    aciertos = [s for s in cerradas if s["resultado"] == "tp1"]
    fallos = [s for s in cerradas if s["resultado"] == "stop"]

    def _media(rows):
        vals = [r["retorno"] for r in rows if r["retorno"] is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def _tp2media(rows):
        vals = [r["retorno_tp2"] for r in rows if r.get("retorno_tp2") is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    win_rate = round(len(aciertos) / len(cerradas) * 100, 1) if cerradas else None
    ganancia_media = _media(aciertos)   # cuánto ganas cuando aciertas
    perdida_media = _media(fallos)      # cuánto pierdes cuando fallas
    # Esperanza matemática por operación: lo que ganas de media por señal cerrada,
    # ponderando aciertos y fallos. Es EL número que dice si el motor gana dinero.
    esperanza = None
    if win_rate is not None and ganancia_media is not None and perdida_media is not None:
        p = win_rate / 100
        esperanza = round(p * ganancia_media + (1 - p) * perdida_media, 1)
    # Ratio riesgo/recompensa real: ganancia media / pérdida media (en valor absoluto).
    rr = None
    if ganancia_media and perdida_media:
        rr = round(ganancia_media / abs(perdida_media), 2) if perdida_media else None

    # --- Escenario TP2: qué pasaría aguantando hasta el objetivo mayor ---
    tp2_rows = [s for s in señales if s.get("resultado_tp2")]
    tp2 = None
    if tp2_rows:
        cerr2 = [s for s in tp2_rows if s["resultado_tp2"] in ("tp2", "stop")]
        win2 = [s for s in cerr2 if s["resultado_tp2"] == "tp2"]
        loss2 = [s for s in cerr2 if s["resultado_tp2"] == "stop"]
        g2 = _tp2media(win2)
        p2 = _tp2media(loss2)
        wr2 = round(len(win2) / len(cerr2) * 100, 1) if cerr2 else None
        esp2 = None
        if wr2 is not None and g2 is not None and p2 is not None:
            pr = wr2 / 100
            esp2 = round(pr * g2 + (1 - pr) * p2, 1)
        rr2 = round(g2 / abs(p2), 2) if (g2 and p2) else None
        tp2 = {
            "win_rate": wr2, "ganancia_media": g2, "perdida_media": p2,
            "ratio_rr": rr2, "esperanza": esp2,
            "aciertos": len(win2), "fallos": len(loss2),
            "abiertas": len(tp2_rows) - len(cerr2),
        }

    # --- Benchmark vs índice (SPY) ---
    # Compara el retorno gestionado del motor (con TP/stop) contra lo que habría hecho
    # SPY en la misma ventana de cada señal. alpha = cuánto de más (o de menos) aporta.
    pares = [(s["retorno"], s["spy_retorno"]) for s in señales
             if s.get("retorno") is not None and s.get("spy_retorno") is not None]
    benchmark = None
    if pares:
        sis = round(sum(a for a, _ in pares) / len(pares), 1)
        spy = round(sum(b for _, b in pares) / len(pares), 1)
        baten = sum(1 for a, b in pares if a > b)
        benchmark = {
            "sistema_medio": sis,
            "spy_medio": spy,
            "alpha": round(sis - spy, 1),          # cuánto bate (o no) al índice
            "baten_spy_pct": round(baten / len(pares) * 100, 1),
            "muestra": len(pares),
            "veredicto": veredicto_benchmark(sis, spy),
        }

    return {
        "total": len(señales),
        "benchmark": benchmark,
        # Supuestos con los que se ha calculado todo lo de arriba, para enseñarlos.
        "costes": {"pct_ida_vuelta": coste, "importe_referencia_eur": IMPORTE_REFERENCIA_EUR},
        "duplicadas_descartadas": duplicadas,
        "aciertos": len(aciertos),
        "fallos": len(fallos),
        "abiertas": len(abiertas),
        "win_rate": win_rate,
        "retorno_medio_cerradas": _media(cerradas),   # resultado real de lo ya cerrado
        "ganancia_media": ganancia_media,
        "perdida_media": perdida_media,
        "ratio_rr": rr,
        "esperanza": esperanza,
        "pl_abiertas": _media(abiertas),              # P&L medio de lo que sigue en curso
        "tp2": tp2,                                   # mismo análisis aguantando hasta TP2
        "señales": señales[:50],
        "dias": days,
        "generado": now.isoformat(),
    }
