"""Vigía del RSI del S&P 500: avisa cuando el índice entra en sobreventa.

Por qué el ÍNDICE y no una acción: un RSI bajo en una acción suelta suele significar que esa
empresa tiene un problema, y el precio puede seguir cayendo indefinidamente. En el índice
completo mide miedo generalizado, que históricamente se ha revertido con más frecuencia. No
es lo mismo y por eso este vigía solo mira el S&P 500.

IMPORTANTE — el aviso NO afirma que "siempre sube". Calcula el historial REAL en el momento
de dispararse (cuántas veces ocurrió, cuántas veces subió después, y sobre todo CUÁL FUE EL
PEOR CASO) y lo manda con el mensaje. Si esta vez toca un 2008, el propio aviso lo dirá.
"""
import logging
import os
from datetime import datetime, timezone

import pandas as pd

import indicators as ind
import market_data
import telegram_notifier

logger = logging.getLogger(__name__)

#: Umbral de sobreventa. 30 es la convención clásica.
RSI_ENTRADA = float(os.environ.get("SP500_RSI_ENTRADA", 30))
#: Por encima de este valor se considera terminado el episodio y se rearma el aviso. La
#: histéresis evita el spam: sin ella, un RSI oscilando en 29,9/30,1 dispararía cada ciclo.
RSI_REARME = float(os.environ.get("SP500_RSI_REARME", 40))
#: Símbolo del índice. SPY es el ETF; sigue al S&P 500 y tiene histórico largo y limpio.
SIMBOLO = os.environ.get("SP500_RSI_SIMBOLO", "SPY")
#: Horizontes que se analizan tras cada episodio de sobreventa, en sesiones.
_HORIZONTES = (("1 mes", 21), ("3 meses", 63), ("6 meses", 126))
#: Segundos para bajar el histórico largo del estudio. Ver _historico_largo.
_TIMEOUT_HISTORICO = float(os.environ.get("SP500_RSI_TIMEOUT_HIST", 30))


def _regimen(df: pd.DataFrame):
    """¿Está el índice por encima o por debajo de su media de 200 sesiones?

    NO es un adorno: medido sobre el S&P 500 diario de 1950 a 2018 (212 episodios de
    sobreventa), el resultado a 3 meses cambia radicalmente según el régimen —
    subió el 77% de las veces por ENCIMA de la SMA200 y solo el 57% por debajo.
    Es la diferencia entre un susto en una tendencia sana y un mercado bajista de verdad.
    """
    try:
        c = df["Close"].astype(float)
        if len(c) < 200:
            return None
        sma = float(c.rolling(200).mean().iloc[-1])
        precio = float(c.iloc[-1])
        if pd.isna(sma):
            return None
        return {"sobre_sma200": precio > sma, "sma200": round(sma, 2),
                "dist_pct": round((precio / sma - 1) * 100, 1)}
    except Exception:
        return None


def _historial_sobreventa(df: pd.DataFrame, umbral: float, sobre_sma200: bool = None):
    """Qué pasó las OTRAS veces que el índice entró en sobreventa.

    sobre_sma200: si se indica, solo cuenta los episodios que ocurrieron en el MISMO régimen
    de tendencia que el de hoy (ver _regimen: el resultado cambia mucho según cuál sea).

    Cuenta episodios, no días: una sobreventa que dura dos semanas es UN evento, no diez.
    Contarlos por separado inflaría la muestra y haría parecer la señal más fiable de lo que
    es (los días de un mismo episodio no son observaciones independientes).

    Devuelve None si no hay histórico suficiente.
    """
    try:
        if df is None or df.empty or len(df) < 300:
            return None
        cierre = df["Close"].astype(float).reset_index(drop=True)
        rsi = ind.rsi(cierre)
        bajo = rsi < umbral
        # Inicio de episodio: hoy por debajo y ayer por encima.
        entradas = [i for i in range(1, len(bajo)) if bool(bajo.iloc[i]) and not bool(bajo.iloc[i - 1])]
        if not entradas:
            return None

        # Si se pide, quedarse SOLO con los episodios del mismo régimen que el de hoy. Es la
        # comparación que de verdad informa: "las otras veces que estuvimos sobrevendidos Y
        # por debajo de la SMA200", no un promedio que mezcla sustos con mercados bajistas.
        if sobre_sma200 is not None:
            sma = cierre.rolling(200).mean()
            entradas = [i for i in entradas
                        if not pd.isna(sma.iloc[i])
                        and (cierre.iloc[i] > sma.iloc[i]) == sobre_sma200]
            if not entradas:
                return None

        fechas = pd.to_datetime(df["Date"]).reset_index(drop=True)
        resultados = {}
        for etiqueta, sesiones in _HORIZONTES:
            rends = [
                (float(cierre.iloc[i + sesiones]) / float(cierre.iloc[i]) - 1) * 100
                for i in entradas if i + sesiones < len(cierre)
            ]
            if not rends:
                continue
            resultados[etiqueta] = {
                "n": len(rends),
                "subieron": sum(1 for r in rends if r > 0),
                "media": round(sum(rends) / len(rends), 1),
                "peor": round(min(rends), 1),
                "mejor": round(max(rends), 1),
            }
        if not resultados:
            return None
        return {
            "episodios": len(entradas),
            "desde": fechas.iloc[0].strftime("%Y"),
            "ultimo": fechas.iloc[entradas[-1]].strftime("%d/%m/%Y"),
            "horizontes": resultados,
        }
    except Exception as e:
        logger.warning("Historial de sobreventa falló: %s", str(e)[:120])
        return None


def estudio_completo(umbral: float = None):
    """Ejecuta el estudio entero sobre datos FRESCOS y devuelve la tabla.

    Existe porque el análisis que se hizo al diseñar esto usó un dataset público que acaba
    en 2018: no incluía el COVID, 2022 ni nada posterior. Desde el servidor sí hay acceso a
    Yahoo, así que se puede repetir con datos hasta hoy cuando se quiera.

    Incluye la comparación con un día CUALQUIERA, que es la referencia que hay que batir: si
    el índice sube el 70% de las veces a 6 meses de todas formas, un 70% tras la sobreventa
    no demuestra nada.
    """
    umbral = RSI_ENTRADA if umbral is None else float(umbral)
    df = _historico_largo()
    if df is None or df.empty:
        return {"error": "No se pudo descargar el histórico."}
    c = df["Close"].astype(float).reset_index(drop=True)
    fechas = pd.to_datetime(df["Date"]).reset_index(drop=True)
    rsi = ind.rsi(c)
    sma200 = c.rolling(200).mean()
    bajo = rsi < umbral
    ent = [i for i in range(1, len(bajo))
           if bool(bajo.iloc[i]) and not bool(bajo.iloc[i - 1]) and not pd.isna(sma200.iloc[i])]

    def _stats(idxs):
        out = {}
        for et, k in _HORIZONTES + (("1 año", 252),):
            r = [(float(c.iloc[i + k]) / float(c.iloc[i]) - 1) * 100 for i in idxs if i + k < len(c)]
            if r:
                out[et] = {"n": len(r), "subio_pct": round(sum(1 for x in r if x > 0) / len(r) * 100),
                           "media": round(sum(r) / len(r), 1),
                           "peor": round(min(r), 1), "mejor": round(max(r), 1)}
        return out

    def _base():
        out = {}
        for et, k in _HORIZONTES + (("1 año", 252),):
            r = [(float(c.iloc[i + k]) / float(c.iloc[i]) - 1) * 100 for i in range(len(c) - k)]
            if r:
                out[et] = {"subio_pct": round(sum(1 for x in r if x > 0) / len(r) * 100),
                           "media": round(sum(r) / len(r), 1)}
        return out

    # Solape: los episodios se agrupan, así que n NO son n observaciones independientes.
    huecos = [ent[i] - ent[i - 1] for i in range(1, len(ent))]
    return {
        "simbolo": SIMBOLO, "umbral": umbral,
        "desde": fechas.iloc[0].strftime("%d/%m/%Y"), "hasta": fechas.iloc[-1].strftime("%d/%m/%Y"),
        "sesiones": int(len(c)),
        "episodios": len(ent),
        "dias_en_sobreventa_pct": round(float(bajo.sum()) / len(c) * 100, 1),
        "tras_sobreventa": _stats(ent),
        "dia_cualquiera": _base(),
        "sobre_sma200": _stats([i for i in ent if c.iloc[i] > sma200.iloc[i]]),
        "bajo_sma200": _stats([i for i in ent if c.iloc[i] <= sma200.iloc[i]]),
        "aviso_independencia": (
            f"{sum(1 for g in huecos if g < 63)} de {len(huecos)} episodios ocurrieron a menos "
            "de 63 sesiones del anterior: las ventanas se SOLAPAN, así que el margen de error "
            "real es mayor que el que sugiere el nº de episodios."
        ) if huecos else None,
    }


def _historico_largo():
    """Histórico lo más largo posible para que el historial tenga sentido. La sobreventa del
    índice es RARA (unas pocas veces por década), así que con 2 años no habría muestra."""
    try:
        t = market_data._ticker(SIMBOLO)
        # Tope propio y GENEROSO: _HISTORY_FETCH_TIMEOUT son 2s, pensados para el camino
        # rápido de una carga de página, donde caer al respaldo enseguida es lo correcto.
        # Aquí se bajan 25 años (~6.300 velas) y con 2s no llegaría NUNCA: el historial
        # saldría siempre vacío y el aviso perdería justo lo que lo hace útil. Esto corre
        # unas pocas veces al año y en segundo plano, así que puede esperar.
        df = market_data._call_with_timeout(
            lambda: t.history(period="25y", interval="1d", auto_adjust=False),
            _TIMEOUT_HISTORICO, None,
        )
        if df is None or df.empty:
            return None
        df = df.reset_index()
        col = "Date" if "Date" in df.columns else "Datetime"
        df = df.rename(columns={col: "Date"})
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        return df
    except Exception as e:
        logger.warning("Histórico largo de %s falló: %s", SIMBOLO, str(e)[:120])
        return None


def _formatear(rsi_actual: float, precio, hist, reg=None) -> str:
    """Mensaje deliberadamente distinto a todos los demás del bot: bloque de emojis arriba y
    abajo para que destaque de un vistazo entre las alertas de niveles."""
    borde = "🟥" * 12
    L = [
        borde,
        "🚨  *S&P 500 EN SOBREVENTA*  🚨",
        borde,
        "",
        f"📉  RSI del índice: *{rsi_actual:.1f}*  (umbral {RSI_ENTRADA:.0f})",
    ]
    if precio:
        L.append(f"💲  {SIMBOLO}: {precio:.2f}")

    # El régimen es lo que más cambia el pronóstico, así que va ARRIBA y con su aviso.
    if reg:
        if reg["sobre_sma200"]:
            L.append(f"✅  Sobre la SMA200 ({reg['dist_pct']:+.1f}%) — *tendencia de fondo sana*")
            L.append("     Es el escenario bueno: un susto dentro de una tendencia alcista.")
        else:
            L.append(f"🔻  BAJO la SMA200 ({reg['dist_pct']:+.1f}%) — *tendencia de fondo rota*")
            L.append("     OJO: aquí la sobreventa acierta MUCHO menos. No es lo mismo.")
    L.append("")

    if hist and hist.get("horizontes"):
        ambito = ""
        if reg is not None:
            ambito = " en tendencia alcista" if reg["sobre_sma200"] else " con la tendencia rota"
        L.append(f"📊  *Qué pasó las {hist['episodios']} veces anteriores{ambito}* (desde {hist['desde']}):")
        for etiqueta, d in hist["horizontes"].items():
            pct_ok = round(d["subieron"] / d["n"] * 100)
            L.append(f"   • A {etiqueta}: subió {d['subieron']} de {d['n']} veces ({pct_ok}%)")
            L.append(f"     media {d['media']:+.1f}%  ·  peor caso *{d['peor']:+.1f}%*")
        L.append("")
        L.append(f"🕐  Sobreventa anterior: {hist['ultimo']}")
        L.append("")
        peor = min(d["peor"] for d in hist["horizontes"].values())
        if peor < -10:
            L.append(f"⚠️  OJO: en el peor episodio el índice aún cayó un *{peor:.1f}%* más "
                     "después de esta señal. Sobreventa NO significa suelo.")
    else:
        L.append("📊  No se pudo calcular el historial esta vez (sin datos suficientes).")

    L += [
        "",
        "👉  *Revisa el gráfico antes de comprar.*",
        "_Escalona la entrada: la sobreventa puede prolongarse._",
        borde,
    ]
    return "\n".join(L)


async def comprobar(db) -> bool:
    """Una comprobación. Devuelve True si se envió aviso. Público para poder probarlo a mano.

    El estado vive en Mongo (no en memoria) para que un redespliegue de Render no reenvíe el
    aviso: es el mismo bug que ya se corrigió en el resumen diario.
    """
    df = market_data.get_full_indicator_history(SIMBOLO)
    if df is None or getattr(df, "empty", True) or len(df) < 30:
        return False

    serie = ind.rsi(df["Close"].astype(float).reset_index(drop=True))
    rsi_actual = serie.dropna()
    if rsi_actual.empty:
        return False
    rsi_actual = float(rsi_actual.iloc[-1])
    precio = float(df["Close"].iloc[-1])

    doc = await db.market_rsi_state.find_one({"_id": SIMBOLO}) or {}
    avisado = bool(doc.get("avisado"))

    # Rearme: el episodio ha terminado, el próximo volverá a avisar.
    if avisado and rsi_actual > RSI_REARME:
        await db.market_rsi_state.update_one(
            {"_id": SIMBOLO},
            {"$set": {"avisado": False, "rearmado_en": datetime.now(timezone.utc).isoformat(),
                      "rsi": round(rsi_actual, 2)}},
            upsert=True)
        logger.info("Vigía RSI: rearmado (RSI %.1f > %.0f)", rsi_actual, RSI_REARME)
        return False

    if rsi_actual >= RSI_ENTRADA or avisado:
        return False

    # Reclama el envío de forma ATÓMICA antes de mandar nada: si hay dos instancias o un
    # redespliegue justo en este momento, solo una consigue modified_count>0 y avisa.
    res = await db.market_rsi_state.update_one(
        {"_id": SIMBOLO, "avisado": {"$ne": True}},
        {"$set": {"avisado": True, "avisado_en": datetime.now(timezone.utc).isoformat(),
                  "rsi": round(rsi_actual, 2)}},
        upsert=True)
    if not (res.modified_count or res.upserted_id):
        return False

    reg = _regimen(df)
    hist = _historial_sobreventa(
        _historico_largo(), RSI_ENTRADA,
        sobre_sma200=(reg["sobre_sma200"] if reg else None))
    ok, err = await telegram_notifier.send_message(
        _formatear(rsi_actual, precio, hist, reg), parse_mode="Markdown")
    if not ok:
        # Devolver el estado para reintentar en el siguiente ciclo: si se queda "avisado"
        # y el envío falló, el aviso se pierde para siempre. Mismo fallo que tenía el
        # vigilante del Chartista.
        await db.market_rsi_state.update_one({"_id": SIMBOLO}, {"$set": {"avisado": False}})
        logger.warning("Vigía RSI: Telegram falló (%s); reintentaré", str(err)[:120])
        return False
    logger.info("Vigía RSI: aviso enviado (RSI %.1f)", rsi_actual)
    return True


async def worker_loop(db, intervalo: int = 3600):
    """Comprueba una vez por hora. El RSI se calcula sobre velas DIARIAS: dentro de la misma
    sesión apenas se mueve, así que mirarlo más a menudo solo gastaría cuota."""
    import asyncio
    logger.info("Vigía del RSI del S&P 500 arrancado (entrada<%.0f, rearme>%.0f)",
                RSI_ENTRADA, RSI_REARME)
    while True:
        try:
            await comprobar(db)
        except Exception as e:
            logger.warning("Vigía RSI falló: %s", str(e)[:150])
        await asyncio.sleep(intervalo)
