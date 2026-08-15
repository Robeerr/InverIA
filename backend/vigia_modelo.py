"""Avisa cuando Google publica un Gemini más nuevo que el que estás usando.

AVISA. No cambia nada. La diferencia es deliberada y es el motivo de que este módulo
exista en vez de dos líneas que resuelvan el modelo al arrancar:

  · los prompts están afinados contra un modelo y el backend parsea JSON de la respuesta;
    un modelo nuevo puede cambiar el formato y romper el análisis sin previo aviso
  · el precio se mueve entre versiones (3.7 Flash entró a mitad de precio, pero de forma
    introductoria); enterarse por la factura no es enterarse
  · esto produce razonamiento de compra y de venta. Que el modelo cambie solo un martes
    por la mañana, sin dejar rastro, mientras se lee una recomendación y se decide con
    ella, es exactamente lo que no se quiere. Si un día el Chartista dice algo raro, hay
    que poder saber con qué modelo lo dijo.

El alias oficial `gemini-flash-latest` tampoco vale como atajo: va por detrás. En agosto
de 2026 apuntaba a 3.5 Flash con 3.6 en producción y 3.7 ya publicado, así que ponerlo
habría sido retroceder dos versiones creyendo que se avanzaba.

Cambiar de modelo es poner GEMINI_MODEL en el entorno y reiniciar: no hace falta
desplegar, y se deshace igual de rápido si el nuevo no convence.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone

import ai_analysis
import telegram_notifier

logger = logging.getLogger("vigia_modelo")

# Una vez por semana. Los modelos salen cada varios meses; mirarlo más a menudo no
# adelantaría nada y solo añadiría una llamada más que puede fallar.
INTERVALO = 7 * 24 * 3600

# `gemini-3.7-flash` → familia "flash", versión (3, 7).
#
# La familia se compara en crudo a propósito: "flash" y "flash-lite" son productos
# distintos con precios distintos, y proponer un salto de uno a otro sería proponer otra
# cosa, no una actualización. Lo mismo con "pro".
_MODELO = re.compile(r"^(?:models/)?gemini-(\d+)\.(\d+)-([a-z][a-z-]*)$")

# Nombres que NO son un modelo estable: previews, experimentales y fechados. Un aviso que
# empujara a un preview sería un aviso para pisar producción con algo que Google puede
# retirar sin avisar.
_INESTABLE = re.compile(r"preview|exp|latest|\d{4}", re.IGNORECASE)


def descomponer(model_id: str):
    """(familia, (mayor, menor)) de un id de modelo, o None si no es uno estable."""
    m = _MODELO.match((model_id or "").strip())
    if not m:
        return None
    mayor, menor, familia = m.group(1), m.group(2), m.group(3)
    if _INESTABLE.search(familia):
        return None
    return familia, (int(mayor), int(menor))


def mas_nuevo(actual: str, disponibles) -> str:
    """El modelo más nuevo de la MISMA familia que `actual`, o "" si no hay ninguno.

    Misma familia y no "el mejor que haya": si estás en flash, un aviso que te empuje a
    pro te está proponiendo multiplicar la factura, y uno que te empuje a flash-lite, bajar
    de calidad. Ninguna de las dos es la pregunta que este vigía contesta.
    """
    yo = descomponer(actual)
    if yo is None:
        return ""
    familia, version = yo
    mejor, mejor_id = version, ""
    for cand in disponibles or []:
        d = descomponer(cand)
        if d is None or d[0] != familia:
            continue
        if d[1] > mejor:
            mejor, mejor_id = d[1], (cand or "").replace("models/", "")
    return mejor_id


def _texto(actual: str, nuevo: str) -> str:
    """El aviso dice qué hacer. Un "hay algo nuevo" sin el paso siguiente obliga a ir a
    buscar cómo se cambiaba, y entonces el aviso se pospone y no se cambia nunca."""
    return (
        f"🤖 Hay un Gemini más nuevo: {nuevo}\n"
        f"El tuyo es {actual}.\n\n"
        f"Para cambiarlo: pon GEMINI_MODEL={nuevo} en las variables de entorno y "
        f"reinicia el servicio. No hace falta desplegar, y se deshace igual de rápido.\n\n"
        f"Comprueba antes el precio: las versiones nuevas no siempre entran más baratas."
    )


async def _listar_modelos() -> list:
    """Ids de modelo que ofrece Google para tu key. Lista vacía si no se puede saber."""
    if not ai_analysis.GEMINI_AVAILABLE:
        return []
    keys = ai_analysis._gemini_keys()
    if not keys:
        return []
    cliente = ai_analysis._genai_client(keys[0])
    modelos = await asyncio.to_thread(lambda: list(cliente.models.list()))
    return [getattr(m, "name", "") or "" for m in modelos]


async def comprobar(db) -> dict:
    """Mira si hay un Gemini más nuevo y avisa por Telegram UNA vez por modelo.

    Una vez por modelo y no una vez por semana: repetir el mismo aviso siete veces no
    informa de nada nuevo y enseña a ignorar los avisos de este bot, que también manda
    las alertas de nivel.
    """
    actual = (ai_analysis.GEMINI_MODEL or "").strip()
    try:
        disponibles = await _listar_modelos()
    except Exception as exc:
        logger.warning("No se pudo consultar el catálogo de modelos: %s", str(exc)[:150])
        return {"actual": actual, "nuevo": "", "avisado": False,
                "error": "No se pudo consultar el catálogo de modelos de Google."}

    nuevo = mas_nuevo(actual, disponibles)
    if not nuevo:
        return {"actual": actual, "nuevo": "", "avisado": False}

    ya = await db.avisos_modelo.find_one({"modelo": nuevo}, {"_id": 0})
    if ya:
        return {"actual": actual, "nuevo": nuevo, "avisado": False, "ya_avisado": True}

    ok, err = await telegram_notifier.send_message(_texto(actual, nuevo), parse_mode="")
    if not ok:
        # Sin marcar: si el aviso no salió, la semana que viene se vuelve a intentar. Marcar
        # un aviso que nadie recibió sería perderlo para siempre.
        logger.warning("Aviso de modelo nuevo no enviado: %s", err)
        return {"actual": actual, "nuevo": nuevo, "avisado": False, "error": err}

    await db.avisos_modelo.insert_one({
        "modelo": nuevo, "desde": actual,
        "avisado_en": datetime.now(timezone.utc).isoformat(),
    })
    return {"actual": actual, "nuevo": nuevo, "avisado": True}


async def worker_loop(db, intervalo: int = INTERVALO):
    logger.info("Vigía de modelos arrancado (cada %d h)", intervalo // 3600)
    while True:
        try:
            await comprobar(db)
        except Exception as exc:
            logger.warning("Vigía de modelos falló: %s", str(exc)[:150])
        await asyncio.sleep(intervalo)
