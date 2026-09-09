"""El bucle que vigila las fuentes. Un `asyncio.create_task` más, como los otros quince.

POR QUÉ NO HAY COLA NI INFRAESTRUCTURA NUEVA

Este proyecto ya resuelve el trabajo de fondo con bucles asíncronos y Mongo, y lo hace
en quince sitios. Meter Redis o una cola de mensajes para una petición cada cinco
minutos sería añadir una pieza que hay que desplegar, vigilar y pagar, para un
problema que no tenemos.

LO QUE ESTE MÓDULO SÍ HACE, Y LO QUE DELEGA

Aquí vive lo que necesita base de datos: leer el cursor, saber tu universo, escribir
eventos y llevar la cuenta de fallos. Todo lo que se puede decidir sin red —qué es un
duplicado, qué te toca, qué relevancia tiene— está en `intel_pipeline`, que se prueba
en memoria. Esa frontera es la que permite tener 42 tests del pipeline sin abrir una
sola conexión.

REINICIOS

Render duerme los servicios inactivos y los reinicia. El worker tiene que poder morir
en cualquier punto sin dejar nada a medias:

  · el cursor son los ids YA ESCRITOS, no los que se van a escribir;
  · los eventos se escriben con `upsert` por un id determinista;
  · la cuenta de fallos vive en Mongo, no en memoria.

Consecuencia: reprocesar el mismo feed tras un reinicio no crea nada. Es lo que hace
que «un evento no genere dos señales» sea cierto también cuando el proceso se cae a
mitad de ciclo.

NO SE FABRICAN EVENTOS

Si la fuente no está configurada, no se toca la red. Si falla, se anota el fallo y se
espera. En ninguno de los dos casos se escribe un evento: el radar solo puede pintar
lo que de verdad ha entrado.
"""
import asyncio
import logging
from datetime import datetime, timezone

import intel_pipeline as pl
import intel_sec as sec

logger = logging.getLogger("inveria.intel")

# La espera, con nombre propio en este módulo. Los tests la sustituyen aquí en vez de
# parchear `asyncio.sleep` global, que rompe el propio bucle de eventos que los ejecuta.
dormir = asyncio.sleep

COL_EVENTOS = "intel_eventos"
COL_SALUD = "intel_salud"

# Cuántos ids recientes se recuerdan para deduplicar. El feed devuelve 40 por vuelta;
# 500 cubre de sobra varias horas y evita releer la colección entera cada ciclo.
IDS_RECORDADOS = 500


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _universo(db) -> tuple:
    """Tus símbolos: watchlist + cartera activa, y cuáles llevas de verdad.

    Se lee en cada vuelta y no se cachea: añades una acción a la watchlist y el
    siguiente ciclo ya la vigila, sin reiniciar nada.
    """
    watchlist, cartera = set(), set()
    try:
        for it in await db.watchlist.find({}, {"_id": 0, "symbol": 1}).to_list(500):
            if it.get("symbol"):
                watchlist.add(it["symbol"].upper())
    except Exception as e:
        logger.warning("intel: no se pudo leer la watchlist: %s", str(e)[:120])
    try:
        for it in await db.signal_entries.find({"active": True},
                                               {"_id": 0, "symbol": 1, "acciones": 1}).to_list(500):
            s = (it.get("symbol") or "").upper()
            if not s:
                continue
            watchlist.add(s)
            # «En cartera» es tener acciones, no tener la fila. Una acción con niveles
            # puestos pero sin comprar todavía no expone dinero, y la relevancia
            # depende de eso.
            try:
                if float(it.get("acciones") or 0) > 0:
                    cartera.add(s)
            except (TypeError, ValueError):
                pass
    except Exception as e:
        logger.warning("intel: no se pudo leer la Cartera: %s", str(e)[:120])
    return watchlist | cartera, cartera, watchlist


async def _ids_recientes(db, fuente: str) -> set:
    """Los ids ya escritos de esta fuente. El cursor de deduplicación.

    Son los que están EN LA BASE DE DATOS, no los que se pretendía escribir: si el
    proceso murió antes del `upsert`, ese evento vuelve a entrar y se escribe. Es el
    lado correcto en el que equivocarse — reprocesar es gratis, perder no.
    """
    try:
        docs = await db[COL_EVENTOS].find(
            {"fuente": fuente}, {"_id": 0, "id": 1}
        ).sort("recibido_en", -1).to_list(IDS_RECORDADOS)
        return {d["id"] for d in docs if d.get("id")}
    except Exception as e:
        logger.warning("intel: no se pudo leer el cursor: %s", str(e)[:120])
        # Ante la duda, conjunto vacío: se reprocesa y el `upsert` evita duplicados.
        return set()


async def _guardar(db, eventos: list) -> int:
    """Escribe cada evento por su id determinista. Idempotente por construcción.

    `upsert` y no `insert`: dos vueltas sobre el mismo filing reescriben el mismo
    documento. Y `$setOnInsert` para `recibido_en`, porque la primera vez que lo
    vimos no cambia porque lo hayamos vuelto a leer.
    """
    escritos = 0
    for e in eventos or []:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        doc = dict(e)
        recibido = doc.pop("recibido_en", _ahora())
        try:
            await db[COL_EVENTOS].update_one(
                {"id": doc["id"]},
                {"$set": doc, "$setOnInsert": {"recibido_en": recibido}},
                upsert=True)
            escritos += 1
        except Exception as ex:
            logger.warning("intel: no se pudo guardar %s: %s", doc["id"], str(ex)[:120])
    return escritos


async def _anotar_salud(db, fuente: str, **campos) -> None:
    """La salud vive en Mongo y no en memoria: un reinicio no puede borrar que la
    fuente lleva media hora fallando."""
    try:
        await db[COL_SALUD].update_one(
            {"fuente": fuente},
            {"$set": {"fuente": fuente, "actualizado_en": _ahora(), **campos}},
            upsert=True)
    except Exception as e:
        logger.warning("intel: no se pudo anotar la salud: %s", str(e)[:120])


async def _salud(db, fuente: str) -> dict:
    try:
        return await db[COL_SALUD].find_one({"fuente": fuente}, {"_id": 0}) or {}
    except Exception:
        return {}


async def ciclo_sec(db) -> dict:
    """Una vuelta de SEC. Devuelve lo que ha pasado, para el log y el diagnóstico."""
    if not sec.configurado():
        # NO se toca la red y NO se escribe ningún evento. La fuente se anota como
        # no configurada, que es lo que la pantalla pintará: apagada, no rota.
        await _anotar_salud(db, sec.FUENTE, estado=sec.NO_CONFIGURADA,
                            error="Falta SEC_USER_AGENT", fallos=0)
        return {"estado": sec.NO_CONFIGURADA, "nuevos": 0}

    salud = await _salud(db, sec.FUENTE)
    fallos = int(salud.get("fallos") or 0)

    crudos = []
    try:
        # Los dos formularios en la misma vuelta. Son dos peticiones cada cinco
        # minutos: muy por debajo de las 10/segundo que pide la SEC.
        for formulario in sec.FORMULARIOS:
            crudos.extend(await sec.descargar(formulario))
            await dormir(1)             # cortesía entre peticiones
    except Exception as e:
        fallos += 1
        msg = str(e)[:200]
        await _anotar_salud(db, sec.FUENTE,
                            estado=sec.estado_salud(msg, fallos),
                            error=msg, fallos=fallos,
                            espera_s=sec.espera_tras_fallo(fallos))
        logger.warning("intel/sec: fallo %d — %s", fallos, msg)
        return {"estado": "error", "error": msg, "fallos": fallos, "nuevos": 0}

    universo, cartera, watchlist = await _universo(db)
    conocidos = await _ids_recientes(db, sec.FUENTE)
    r = pl.procesar(crudos, universo=universo, ids_conocidos=conocidos,
                    cartera=cartera, watchlist=watchlist)
    escritos = await _guardar(db, r["guardar"])

    await _anotar_salud(db, sec.FUENTE, estado=sec.ONLINE, error=None, fallos=0,
                        espera_s=0, ultimo_ciclo={
                            "recibidos": r["recibidos"], "nuevos": r["nuevos"],
                            "significativos": len(r["significativos"]),
                            "descartados": r["descartados"],
                            "por_motivo": r["por_motivo"]})
    if r["nuevos"]:
        logger.info("intel/sec: %d recibidos → %d nuevos → %d significativos",
                    r["recibidos"], r["nuevos"], len(r["significativos"]))
    return {"estado": sec.ONLINE, "escritos": escritos, **r}


async def worker_loop(db, intervalo: int = None, retraso_inicial: int = 120):
    """El bucle. Mismo contrato que `news_ingest.news_worker_loop`.

    El retraso inicial deja que el arranque respire: al levantar, el servicio tiene
    quince workers más pidiendo cosas.
    """
    intervalo = intervalo or sec.INTERVALO
    await dormir(retraso_inicial)
    while True:
        espera = intervalo
        try:
            r = await ciclo_sec(db)
            # Tras un fallo se espera MÁS que el intervalo normal. Sin esto, un 403
            # por identificación mal puesta se reintentaría cada cinco minutos
            # indefinidamente contra una puerta que no se va a abrir sola.
            if r.get("estado") == "error":
                espera = max(intervalo, sec.espera_tras_fallo(r.get("fallos", 1)))
        except Exception:
            logger.exception("intel: el ciclo falló entero")
        await dormir(espera)
