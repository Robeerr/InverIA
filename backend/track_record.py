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
    entry = _num(entry)
    if not entry:
        return None
    tp1, sl = _num(tp1), _num(sl)
    if not future:
        return None
    for hi, lo, _close in future:
        hi, lo = _num(hi), _num(lo)
        # El stop se comprueba primero (criterio conservador: ante la duda, cuenta el peor caso).
        if sl and lo is not None and lo <= sl:
            return ("stop", round((sl - entry) / entry * 100, 1))
        if tp1 and hi is not None and hi >= tp1:
            return ("tp1", round((tp1 - entry) / entry * 100, 1))
    last_close = _num(future[-1][2])
    cur = round((last_close - entry) / entry * 100, 1) if last_close else None
    return ("abierta", cur)


def evaluate_signal_tp2(entry, tp2, sl, future):
    """Igual que evaluate_signal pero contra el SEGUNDO objetivo (TP2): refleja el
    resultado si aguantas la posición hasta el objetivo mayor en vez de cerrar en TP1.
    Devuelve (resultado, retorno_%) con resultado en {'tp2','stop','abierta'}."""
    entry = _num(entry)
    if not entry:
        return None
    tp2, sl = _num(tp2), _num(sl)
    if not future:
        return None
    for hi, lo, _close in future:
        hi, lo = _num(hi), _num(lo)
        if sl and lo is not None and lo <= sl:
            return ("stop", round((sl - entry) / entry * 100, 1))
        if tp2 and hi is not None and hi >= tp2:
            return ("tp2", round((tp2 - entry) / entry * 100, 1))
    last_close = _num(future[-1][2])
    cur = round((last_close - entry) / entry * 100, 1) if last_close else None
    return ("abierta", cur)


async def compute_track_record(db, days: int = 180, min_age_days: int = 3) -> dict:
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

    señales = []
    for sym, sigs in by_symbol.items():
        try:
            df = await asyncio.to_thread(market_data.get_full_indicator_history, sym)
        except Exception:
            df = None
        if df is None or getattr(df, "empty", True):
            continue
        fechas = df["Date"].tolist()
        highs, lows, closes = df["High"].tolist(), df["Low"].tolist(), df["Close"].tolist()
        for s in sigs:
            created = s["created"].replace(tzinfo=None)
            future = [(highs[i], lows[i], closes[i])
                      for i in range(len(fechas)) if fechas[i] > created]
            ev = evaluate_signal(s["entry"], s["tp1"], s["sl"], future)
            if not ev:
                continue
            resultado, retorno = ev
            fila = {
                "symbol": sym, "fecha": s["created"].date().isoformat(),
                "entrada": round(s["entry"], 2), "resultado": resultado, "retorno": retorno,
            }
            # Resultado alternativo aguantando hasta TP2 (si el análisis lo definió).
            ev2 = evaluate_signal_tp2(s["entry"], s["tp2"], s["sl"], future) if s.get("tp2") else None
            if ev2:
                fila["resultado_tp2"], fila["retorno_tp2"] = ev2
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

    return {
        "total": len(señales),
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
