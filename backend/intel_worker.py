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

import intel_earnings as earnings
import intel_eventos as ev
import intel_pipeline as pl
import intel_sec as sec

# Las fuentes que existen. Añadir una es añadirla aquí y en `lifespan`: el bucle no sabe
# de cuál se trata, solo le pide `recolectar(contexto)` y trata a todas igual.
FUENTES = (sec, earnings)

logger = logging.getLogger("inveria.intel")

# La espera, con nombre propio en este módulo. Los tests la sustituyen aquí en vez de
# parchear `asyncio.sleep` global, que rompe el propio bucle de eventos que los ejecuta.
dormir = asyncio.sleep

COL_EVENTOS = "intel_eventos"
COL_SALUD = "intel_salud"
#: Un documento por CIK: hasta dónde llegamos la última vez. Es lo que impide releer años
#: de historia en cada vuelta, y lo que hace que una empresa que sale y vuelve al universo
#: no reprocese nada.
COL_CURSORES = "intel_cursores"

# Cuántos ids recientes se recuerdan para deduplicar. El feed devuelve 40 por vuelta;
# 500 cubre de sobra varias horas y evita releer la colección entera cada ciclo.
IDS_RECORDADOS = 500

# Versión de los contadores acumulados. Se sube cuando cambia lo que SIGNIFICA un contador.
#
# La v1 sumaba los repetidos dentro de `descartados`. Al separarlos, los números guardados
# antes del cambio y los de después miden cosas distintas, y sumarlos daría una cifra que
# no es ninguna de las dos. Cuando la versión guardada no coincide, los acumuladores se
# ponen a cero UNA vez y se anota desde cuándo cuentan.
#
# Se prefiere perder el histórico a servir un número mezclado: un contador que nadie sabe
# interpretar es peor que un contador que empieza de nuevo y se entiende.
CONTADORES_V = 2


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


async def _anotar_salud(db, fuente: str, sumar: dict = None, **campos) -> None:
    """La salud vive en Mongo y no en memoria: un reinicio no puede borrar que la
    fuente lleva media hora fallando.

    `sumar` son los contadores ACUMULADOS, que se incrementan con `$inc` en vez de
    reescribirse. La diferencia importa: el último ciclo dice cómo fue una vuelta, y el
    acumulado dice cómo va el periodo de prueba. Con solo lo primero, un despliegue a
    media tarde borraría toda la evidencia de que el sistema llevaba días funcionando.
    """
    try:
        cambios = {"$set": {"fuente": fuente, "actualizado_en": _ahora(), **campos},
                   "$setOnInsert": {"vigilando_desde": _ahora()}}
        if sumar:
            cambios["$inc"] = sumar
        await db[COL_SALUD].update_one({"fuente": fuente}, cambios, upsert=True)
    except Exception as e:
        logger.warning("intel: no se pudo anotar la salud: %s", str(e)[:120])


async def _salud(db, fuente: str) -> dict:
    try:
        return await db[COL_SALUD].find_one({"fuente": fuente}, {"_id": 0}) or {}
    except Exception:
        return {}


async def _cursores(db) -> dict:
    """`{"1652044": {...}}` — hasta dónde llegamos con cada empresa.

    Se leen todos y no solo los del universo actual: si una acción salió de la cartera y
    vuelve, su cursor sigue ahí y no se reprocesa su historia. Guardar unos cientos de
    documentos diminutos para evitar eso es un cambio barato por un problema caro.
    """
    try:
        docs = await db[COL_CURSORES].find({}, {"_id": 0}).to_list(2000)
        return {str(d["cik"]): d for d in docs if d.get("cik") is not None}
    except Exception as e:
        logger.warning("intel: no se pudieron leer los cursores: %s", str(e)[:120])
        # Sin cursores se reprocesa, y el `upsert` por id determinista evita duplicados.
        # Es el lado correcto en el que equivocarse.
        return {}


async def _guardar_cursores(db, cursores: dict) -> int:
    """Un documento por CIK, reescrito. No hay histórico que conservar aquí: lo único que
    importa es hasta dónde se llegó la última vez."""
    guardados = 0
    for cik, c in (cursores or {}).items():
        try:
            await db[COL_CURSORES].update_one(
                {"cik": int(cik)},
                {"$set": {**c, "cik": int(cik), "actualizado_en": _ahora()},
                 "$setOnInsert": {"primera_vez": _ahora()}},
                upsert=True)
            guardados += 1
        except Exception as e:
            logger.warning("intel: no se pudo guardar el cursor de %s: %s", cik, str(e)[:120])
    return guardados


def _avance_de_vuelta(mod) -> dict:
    """El turno de rotación avanza en la MISMA escritura que la salud.

    Se hizo aparte al principio y estaba mal: en el primer ciclo el documento de salud
    todavía no existe, así que un `$inc` suelto sin upsert no hacía nada y la rotación no
    arrancaba nunca. Yendo en el mismo `update_one` que ya crea el documento, el problema
    no puede volver.

    Solo SEC rota: es la única fuente con carriles.
    """
    return {"vuelta": 1} if mod is sec else {}


def _cobertura(salida: dict, universo) -> dict:
    """Cuántos de tus valores se vigilan de verdad, y cuántos no.

    Con el mecanismo anterior esto no se podía decir: se miraba el mercado entero y la
    cobertura era una probabilidad. Ahora se pregunta por empresas concretas, así que la
    cifra es exacta — y los que quedan fuera se nombran, porque un valor sin vigilar que
    nadie menciona es indistinguible de uno vigilado del que no pasa nada.
    """
    salida = salida or {}
    sin_cik = salida.get("sin_cik") or []
    total = len(universo or ())
    return {"valores_en_universo": total,
            "empresas_vigiladas": salida.get("objetivos_totales", 0),
            "consultadas_esta_vuelta": salida.get("consultados", 0),
            "sin_cik_en_la_sec": sin_cik,
            "cubiertos": max(0, total - len(sin_cik))}


def _telemetria(salida: dict) -> dict:
    """Lo que el connector dejó en el canal de vuelta, con nombres para la pantalla."""
    salida = salida or {}
    return {"consultados": salida.get("consultados", 0),
            "objetivos_totales": salida.get("objetivos_totales", 0),
            "fallos_por_objetivo": salida.get("fallos") or [],
            "sin_cik": salida.get("sin_cik") or []}


# ── Migración de identificadores ─────────────────────────────────────────────

#: Versión del identificador de los eventos de SEC. La v1 sacaba el número de registro de
#: la URL del feed Atom; la v2 lo canoniza a solo dígitos, que es la forma que produce
#: también el JSON de submissions. Sin esto, el mismo documento leído por los dos
#: mecanismos tendría dos ids y entraría dos veces.
SEC_ID_V = 2


async def migrar_ids_sec(db, limite: int = 5000) -> dict:
    """Canoniza el número de registro de los eventos ya guardados. Idempotente.

    NO BORRA NI DUPLICA NADA

    Si el id canónico coincide con el que ya tenía —que es lo esperable, porque el feed
    Atom daba la forma sin guiones— solo se sella la versión. Si difiere, se reescribe el
    id, salvo que ya exista otro documento con ese id: en ese caso se deja como está y se
    anota, porque fusionar dos documentos automáticamente es más peligroso que tener uno
    de más y verlo en el diagnóstico.

    Se cura sola: cada evento lleva su `sec_id_v`, así que un proceso que muera a mitad
    deja el resto para la vuelta siguiente.
    """
    try:
        pendientes = await db[COL_EVENTOS].find(
            {"fuente": sec.FUENTE, "sec_id_v": {"$ne": SEC_ID_V}}, {"_id": 0}
        ).to_list(limite)
    except Exception as e:
        logger.warning("intel: no se pudo leer lo pendiente de migrar: %s", str(e)[:120])
        return {"revisados": 0, "renombrados": 0, "conflictos": 0}

    revisados = renombrados = conflictos = 0
    for doc in pendientes:
        revisados += 1
        externo = str(doc.get("externo_id") or "")
        # `8-K:000104581026000042` — la forma se conserva tal cual y solo se canoniza el
        # número, que es la parte que venía en dos formatos.
        forma, _, acc = externo.partition(":")
        nuevo_externo = f"{forma}:{sec.canonizar_accession(acc)}" if acc else externo
        nuevo_id = f"{sec.FUENTE}:{nuevo_externo}"
        cambios = {"sec_id_v": SEC_ID_V}
        if nuevo_id != doc.get("id"):
            try:
                if await db[COL_EVENTOS].find_one({"id": nuevo_id}, {"_id": 0, "id": 1}):
                    conflictos += 1
                    logger.warning("intel: %s ya existe como %s; no se toca",
                                   doc.get("id"), nuevo_id)
                    cambios["id_conflicto"] = nuevo_id
                else:
                    cambios.update(id=nuevo_id, externo_id=nuevo_externo)
                    renombrados += 1
            except Exception as e:
                logger.warning("intel: no se pudo comprobar %s: %s", nuevo_id, str(e)[:120])
                continue
        try:
            await db[COL_EVENTOS].update_one({"id": doc["id"]}, {"$set": cambios})
        except Exception as e:
            logger.warning("intel: no se pudo migrar %s: %s", doc.get("id"), str(e)[:120])
    if revisados:
        logger.info("intel/sec: %d ids revisados, %d renombrados, %d conflictos",
                    revisados, renombrados, conflictos)
    return {"revisados": revisados, "renombrados": renombrados, "conflictos": conflictos}


async def _reiniciar_contadores(db, fuente: str) -> None:
    """Pone los acumuladores a cero tras un cambio de significado. Solo los contadores.

    NO se toca ningún evento: los documentos guardados siguen siendo válidos y el radar
    sigue enseñando lo mismo. Lo único que se descarta es una estadística que ya no se
    puede interpretar.
    """
    ceros = {c: 0 for c in ("acum_ciclos", "acum_fallos", "acum_recibidos",
                            "acum_repetidos", "acum_nuevos", "acum_descartados",
                            "acum_significativos", "acum_guardados")}
    try:
        await db[COL_SALUD].update_one(
            {"fuente": fuente},
            {"$set": {**ceros, "acum_motivos": {}, "contadores_v": CONTADORES_V,
                      "vigilando_desde": _ahora()}})
        logger.info("intel/%s: contadores reiniciados (v%d)", fuente, CONTADORES_V)
    except Exception as e:
        logger.warning("intel: no se pudieron reiniciar los contadores: %s", str(e)[:120])


async def _fechas_conocidas(db) -> dict:
    """`{AAPL:2026Q3: "2026-10-28"}` — la última fecha vista para cada trimestre.

    Es lo que permite que el connector de resultados diga «antes era el 28» sin consultar
    la base de datos él mismo. La misma frontera que en SEC: el módulo puro recibe el
    estado, no va a buscarlo.

    Se toma la fecha del evento MÁS RECIENTE de cada trimestre, que es la vigente. Si el
    calendario ha bailado dos veces, lo que importa comparar es contra la última.
    """
    fechas = {}
    try:
        docs = await db[COL_EVENTOS].find(
            {"fuente": earnings.FUENTE}, {"_id": 0, "crudo": 1, "symbol": 1}
        ).sort("recibido_en", 1).to_list(IDS_RECORDADOS)
        for d in docs:
            crudo = d.get("crudo") or {}
            trimestre, fecha = crudo.get("trimestre"), crudo.get("fecha")
            # El evento de publicación no fija fecha de calendario: su `fecha` es cuándo
            # se publicó, y usarla como «fecha prevista» inventaría un cambio al trimestre
            # siguiente.
            if not trimestre or not fecha or crudo.get("suceso") == earnings.PUBLICADO:
                continue
            if d.get("symbol"):
                fechas[f"{d['symbol']}:{trimestre}"] = fecha
    except Exception as e:
        logger.warning("intel: no se pudieron leer las fechas conocidas: %s", str(e)[:120])
    return fechas


async def ciclo(db, mod) -> dict:
    """Una vuelta de UNA fuente. Idéntica para todas: el bucle no sabe de cuál se trata.

    Que sea genérica es lo que hace que añadir una fuente no toque el worker. Lo único que
    un connector tiene que ofrecer es `configurado()`, `recolectar(contexto)`,
    `estado_salud()` y `espera_tras_fallo()`.
    """
    if not mod.configurado():
        # NO se toca la red y NO se escribe ningún evento. La fuente se anota como
        # no configurada, que es lo que la pantalla pintará: apagada, no rota.
        await _anotar_salud(db, mod.FUENTE, estado=mod.NO_CONFIGURADA,
                            error="Falta su variable de entorno", fallos=0)
        return {"fuente": mod.FUENTE, "estado": mod.NO_CONFIGURADA, "nuevos": 0}

    salud = await _salud(db, mod.FUENTE)
    fallos = int(salud.get("fallos") or 0)
    if salud and int(salud.get("contadores_v") or 1) != CONTADORES_V:
        await _reiniciar_contadores(db, mod.FUENTE)
        salud = await _salud(db, mod.FUENTE)

    # El universo se lee ANTES de salir a la red: hay fuentes —resultados— que lo
    # necesitan para no pedir el calendario del mercado entero.
    universo, cartera, watchlist = await _universo(db)
    # `salida` es el canal de vuelta del connector: ahí deja lo que el worker tiene que
    # persistir —cursores, recuentos, fallos— sin que este bucle sepa qué es un CIK ni un
    # trimestre. Es lo que permite cambiar entero el mecanismo de descubrimiento de una
    # fuente sin tocar el worker.
    salida = {}
    contexto = {"universo": universo, "cartera": cartera, "watchlist": watchlist,
                "salida": salida}
    if mod is earnings:
        contexto["fechas_conocidas"] = await _fechas_conocidas(db)
    if mod is sec:
        contexto["cursores"] = await _cursores(db)
        # La vuelta persiste: si se reiniciara a cero en cada arranque, el turno 0 del
        # seguimiento se miraría siempre y los demás nunca.
        contexto["vuelta"] = int(salud.get("vuelta") or 0)

    try:
        crudos = await mod.recolectar(contexto)
    except Exception as e:
        fallos += 1
        msg = str(e)[:200]
        await _anotar_salud(db, mod.FUENTE,
                            sumar={"acum_ciclos": 1, "acum_fallos": 1,
                                   **_avance_de_vuelta(mod)},
                            estado=mod.estado_salud(msg, fallos),
                            error=msg, fallos=fallos,
                            espera_s=mod.espera_tras_fallo(fallos))
        # Los cursores de las empresas que SÍ contestaron antes del corte se guardan
        # igual: no volver a leerlas es correcto, y perderlos obligaría a recorrer otra
        # vez lo mismo en la vuelta siguiente.
        await _guardar_cursores(db, salida.get("cursores"))
        logger.warning("intel/%s: fallo %d — %s", mod.FUENTE, fallos, msg)
        return {"fuente": mod.FUENTE, "estado": "error", "error": msg,
                "fallos": fallos, "nuevos": 0, **_telemetria(salida)}

    conocidos = await _ids_recientes(db, mod.FUENTE)
    r = pl.procesar(crudos, universo=universo, ids_conocidos=conocidos,
                    cartera=cartera, watchlist=watchlist)
    escritos = await _guardar(db, r["guardar"])
    # Los cursores DESPUÉS de escribir los eventos. Si se guardaran antes y la escritura
    # fallara, la vuelta siguiente daría esos registros por vistos y se perderían.
    await _guardar_cursores(db, salida.get("cursores"))

    # Los cuatro números que responden «¿esto está funcionando?»: cuántos se leyeron,
    # cuántos eran nuevos, cuántos se descartaron y cuántos se guardaron de verdad. El
    # último es el que cierra la cadena: sin él, «se procesaron 40» podría convivir con
    # una base de datos vacía y nadie lo notaría.
    resumen = {"recibidos": r["recibidos"], "repetidos": r["repetidos"],
               "nuevos": r["nuevos"], "descartados": r["descartados"],
               "significativos": len(r["significativos"]), "guardados": escritos,
               "por_motivo": r["por_motivo"], "cuando": _ahora()}
    acumulado = {"acum_ciclos": 1, "acum_recibidos": r["recibidos"],
                 "acum_repetidos": r["repetidos"],
                 "acum_nuevos": r["nuevos"], "acum_guardados": escritos,
                 "acum_descartados": r["descartados"],
                 "acum_significativos": len(r["significativos"])}
    for motivo, n in (r["por_motivo"] or {}).items():
        acumulado[f"acum_motivos.{motivo}"] = n
    acumulado.update(_avance_de_vuelta(mod))
    await _anotar_salud(db, mod.FUENTE, sumar=acumulado, contadores_v=CONTADORES_V,
                        estado=mod.ONLINE, error=None, fallos=0,
                        espera_s=0, ultimo_ciclo=resumen,
                        cobertura=_cobertura(salida, universo))
    if r["nuevos"]:
        logger.info("intel/%s: %d recibidos → %d nuevos → %d significativos",
                    mod.FUENTE, r["recibidos"], r["nuevos"], len(r["significativos"]))
    return {"fuente": mod.FUENTE, "estado": mod.ONLINE, "escritos": escritos,
            **_telemetria(salida), **r}


async def comprobar_ahora(db, fuentes=None) -> dict:
    """Una vuelta forzada de cada fuente, con el desglose entero. La prueba de vida.

    POR QUÉ EXISTE, HABIENDO YA UN BUCLE

    Porque «espera y mira si algo ha cambiado» no es una verificación: si al volver no hay
    nada, no sabes si la fuente falló, si el filtro se lo comió o si simplemente no había
    novedades. Esto ejecuta el ciclo AHORA y devuelve por dónde ha ido cada evento, que es
    lo único que distingue esas tres cosas.

    POR FUENTE Y NO EN GLOBAL

    Sumar los números de todas las fuentes escondería justo lo que hace falta ver: con SEC
    leyendo cada cinco minutos y resultados cada seis horas, un total conjunto estaría
    dominado por la primera y una caída de la segunda pasaría desapercibida.

    NO ES UN ATAJO NI UNA VÍA PARALELA

    Llama al mismo `ciclo` que el bucle. Si hiciera su propia versión «de prueba», estaría
    verificando un código que en producción no se ejecuta — la forma clásica de tener una
    comprobación en verde sobre un sistema roto.
    """
    salida = []
    for mod in (fuentes or FUENTES):
        r = await ciclo(db, mod)
        salida.append({
            "fuente": mod.FUENTE,
            "nombre": mod.NOMBRE,
            "estado": r.get("estado"),
            "error": r.get("error"),
            # La cadena entera, paso a paso, en el orden en que ocurre.
            "cadena": {
                "leidos_de_la_fuente": r.get("recibidos", 0),
                # «Ya conocido» no es un descarte: es la deduplicación haciendo su
                # trabajo. Con un feed que devuelve los mismos registros cada pocos
                # minutos, este número ALTO es señal de que va bien.
                "ya_conocidos": r.get("repetidos", 0),
                "nuevos_tras_deduplicar": r.get("nuevos", 0),
                "descartados_al_filtrar": r.get("descartados", 0),
                "significativos": len(r.get("significativos") or []),
                "escritos_en_esta_vuelta": r.get("escritos", 0),
            },
            "por_motivo": r.get("por_motivo") or {},
            # Lo que hay en la base de datos DESPUÉS, leído de vuelta. Que el ciclo diga
            # que guardó tres cosas y que la colección tenga tres cosas son dos
            # afirmaciones distintas, y solo la segunda cierra la cadena.
            "guardados_unicos": await db[COL_EVENTOS].count_documents(
                {"fuente": mod.FUENTE}),
            "acumulado": _acumulado(await _salud(db, mod.FUENTE)),
        })
    return {"fuentes": salida}


def _acumulado(salud: dict) -> dict:
    """Los contadores del periodo de prueba, con nombres legibles.

    `escrituras` y no «guardados»: cuenta operaciones de escritura, y una vuelta que
    reprocesa algo ya escrito vuelve a contar. Los guardados ÚNICOS se cuentan aparte
    contando documentos en la colección, que es la única cifra que no puede inflarse.
    """
    salud = salud or {}
    return {
        "desde": salud.get("vigilando_desde"),
        "ciclos": salud.get("acum_ciclos") or 0,
        "fallos": salud.get("acum_fallos") or 0,
        "recibidos": salud.get("acum_recibidos") or 0,
        # Ya conocidos: leídos otra vez del feed y reconocidos. NO son descartes.
        "repetidos": salud.get("acum_repetidos") or 0,
        "nuevos": salud.get("acum_nuevos") or 0,
        "descartados": salud.get("acum_descartados") or 0,
        "significativos": salud.get("acum_significativos") or 0,
        "escrituras": salud.get("acum_guardados") or 0,
        "por_motivo": salud.get("acum_motivos") or {},
    }


async def repuntuar_pendientes(db, limite: int = 2000) -> dict:
    """Repasa los eventos que llevan una nota de una fórmula anterior.

    POR QUÉ HACE FALTA

    Cambiar los pesos no reescribe lo ya guardado. Sin este repaso, la lista mezclaría
    notas calculadas con dos reglas distintas —un 95 de la v1 junto a un 80 de la v2— y
    nadie podría saberlo mirándolas. Es el mismo problema que tuvieron los contadores, y
    se resuelve igual: marcando la versión y arreglando lo que no coincide.

    ES IDEMPOTENTE Y SE CURA SOLO

    Cada evento lleva su `relevancia_v`. Se repasan solo los que no están en la actual, y
    al repasarlos quedan marcados. Ejecutarlo dos veces no hace nada la segunda; si el
    proceso muere a mitad, la siguiente vuelta termina lo que faltaba.

    QUÉ NO TOCA

    Los descartados. `descartado` es terminal a propósito —es la puerta que impide que
    algo ya rechazado vuelva a entrar por otro camino— y además su motivo no depende de la
    nota: quien no está en tu universo sigue sin estarlo con cualquier fórmula.
    """
    universo, cartera, watchlist = await _universo(db)
    try:
        pendientes = await db[COL_EVENTOS].find(
            {"etapa": {"$in": [ev.FILTRADO, ev.SIGNIFICATIVO, ev.ALERTADO]},
             "relevancia_v": {"$ne": pl.RELEVANCIA_V}},
            {"_id": 0}).to_list(limite)
    except Exception as e:
        logger.warning("intel: no se pudo leer lo pendiente de repuntuar: %s", str(e)[:120])
        return {"revisados": 0, "cambiados": 0}

    revisados = cambiados = 0
    for viejo in pendientes:
        revisados += 1
        nuevo = pl.puntuar(viejo, cartera=cartera, watchlist=watchlist)
        # `puntuar` puede subir de `filtrado` a `significativo`, pero nunca baja: las
        # transiciones son una lista blanca y no hay marcha atrás. Si con la fórmula nueva
        # el evento ya no llega al umbral, se le devuelve a `filtrado` AQUÍ, dejándolo
        # anotado como recalibración.
        #
        # Es la única marcha atrás del sistema y por eso está escrita a mano, en una
        # función que se llama una vez por cambio de fórmula, y no dentro del pipeline:
        # un retroceso que ocurriera en el camino normal sí sería el fallo que las
        # transiciones existen para impedir.
        if (nuevo["relevancia"] < pl.UMBRAL_SIGNIFICATIVO
                and nuevo.get("etapa") == ev.SIGNIFICATIVO):
            nuevo["etapa"] = ev.FILTRADO
            nuevo["historial"] = list(nuevo.get("historial") or []) + [
                {"etapa": ev.FILTRADO, "cuando": _ahora(), "motivo": "recalibrado"}]
        if (nuevo.get("relevancia") != viejo.get("relevancia")
                or nuevo.get("etapa") != viejo.get("etapa")):
            cambiados += 1
        # Se escribe igualmente aunque la nota no cambie: hay que sellar la versión, o
        # este evento se releería en cada arranque para siempre.
        try:
            await db[COL_EVENTOS].update_one(
                {"id": nuevo["id"]},
                {"$set": {"relevancia": nuevo["relevancia"],
                          "relevancia_v": pl.RELEVANCIA_V,
                          "nivel_alerta": nuevo["nivel_alerta"],
                          "afecta_cartera": nuevo["afecta_cartera"],
                          "afecta_watchlist": nuevo["afecta_watchlist"],
                          "afecta_tesis": nuevo["afecta_tesis"],
                          "etapa": nuevo["etapa"],
                          "historial": nuevo.get("historial") or []}})
        except Exception as e:
            logger.warning("intel: no se pudo repuntuar %s: %s", nuevo.get("id"), str(e)[:120])
    if revisados:
        logger.info("intel: %d eventos repuntuados a la fórmula v%d (%d cambiaron de nota)",
                    revisados, pl.RELEVANCIA_V, cambiados)
    return {"revisados": revisados, "cambiados": cambiados}


async def worker_loop(db, mod=None, intervalo: int = None, retraso_inicial: int = 120):
    """El bucle de UNA fuente. Mismo contrato que `news_ingest.news_worker_loop`.

    UN BUCLE POR FUENTE, NO UNO COMPARTIDO

    Cada fuente tiene su ritmo —la SEC cada cinco minutos, los resultados cada seis
    horas— y sobre todo su propio backoff. Con un bucle único, una fuente caída
    arrastraría a la sana: o se espera la hora de castigo de la que falla, o se machaca a
    la que va bien. Son dos tareas y cada una duerme lo suyo.

    El retraso inicial deja que el arranque respire: al levantar, el servicio tiene quince
    workers más pidiendo cosas.
    """
    mod = mod or sec
    intervalo = intervalo or mod.INTERVALO
    await dormir(retraso_inicial)
    # El repaso de fórmula lo lanza UNA sola fuente, la primera. Si lo hicieran todas,
    # dos workers se pisarían escribiendo los mismos documentos en el mismo instante.
    if mod is FUENTES[0]:
        for tarea, nombre in ((migrar_ids_sec, "la migración de ids"),
                              (repuntuar_pendientes, "el repaso de relevancia")):
            try:
                await tarea(db)
            except Exception:
                # Mantenimiento: que falle no puede impedir vigilar el mercado.
                logger.exception("intel: %s falló", nombre)
    while True:
        espera = intervalo
        try:
            r = await ciclo(db, mod)
            # Tras un fallo se espera MÁS que el intervalo normal. Sin esto, un 403 por
            # identificación mal puesta se reintentaría cada cinco minutos
            # indefinidamente contra una puerta que no se va a abrir sola.
            if r.get("estado") == "error":
                espera = max(intervalo, mod.espera_tras_fallo(r.get("fallos", 1)))
        except Exception:
            logger.exception("intel/%s: el ciclo falló entero", mod.FUENTE)
        await dormir(espera)
