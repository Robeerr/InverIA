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
    """Lógica pura del resultado de una señal de compra.

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
            "tp1": res.get("take_profit_1"), "sl": res.get("stop_loss"),
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
            señales.append({
                "symbol": sym, "fecha": s["created"].date().isoformat(),
                "entrada": round(s["entry"], 2), "resultado": resultado, "retorno": retorno,
            })

    señales.sort(key=lambda x: x["fecha"], reverse=True)
    cerradas = [s for s in señales if s["resultado"] in ("tp1", "stop")]
    aciertos = [s for s in cerradas if s["resultado"] == "tp1"]
    con_ret = [s["retorno"] for s in señales if s["retorno"] is not None]
    return {
        "total": len(señales),
        "aciertos": len(aciertos),
        "fallos": len(cerradas) - len(aciertos),
        "abiertas": len(señales) - len(cerradas),
        "win_rate": round(len(aciertos) / len(cerradas) * 100, 1) if cerradas else None,
        "retorno_medio": round(sum(con_ret) / len(con_ret), 1) if con_ret else None,
        "señales": señales[:50],
        "dias": days,
        "generado": now.isoformat(),
    }
