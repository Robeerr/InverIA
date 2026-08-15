"""FastAPI server for the InverIA stock analysis app."""
import math
import json
import re
import hmac
from fastapi import FastAPI, APIRouter, HTTPException, Header, Request, UploadFile, File, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import certifi
from pathlib import Path
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone, timedelta

import asyncio
from functools import partial
import market_data
import indicators as ind
import ai_analysis
import external_data
import polygon_data
import fmp_data
import alerts_worker
import opportunities
import backtest
import signal_table
import daily_analyst
import sp500_rsi_watch
import ventas as ventas_mod
import cartera_api
import degiro_csv
import lotes
import fx
import newsletter_ingest
import market_regime
import chart_lines
import chartist
import hoy
import tesis
import confluencia as confluencia_mod
import mem
import levels_engine
import estado_accion
import veto_compra
import auth

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ── Simple in-memory TTL cache ────────────────────────────────────────────────
import time as _time

class _TTLCache:
    """Bounded TTL cache. Purges expired entries and evicts oldest (FIFO) past
    maxsize so memory can't grow without limit on the 512MB instance."""

    def __init__(self, maxsize=500):
        self._store = {}
        self._maxsize = maxsize

    @staticmethod
    def _protegida(entry, ahora) -> bool:
        """¿Sigue esta entrada dentro de su ventana de 'caducado pero servible'?"""
        ventana = entry.get("servible_hasta", 0)
        return bool(ventana) and (ahora - entry["ts"]) < ventana

    def get(self, key):
        entry = self._store.get(key)
        if entry and (_time.time() - entry["ts"]) < entry["ttl"]:
            return entry["val"]
        if entry:
            self._store.pop(key, None)  # drop expired
        return None

    def get_stale(self, key, max_age):
        """Devuelve (valor, fresco). Si la entrada caducó pero no supera max_age, la
        devuelve igualmente con fresco=False, para poder servirla YA y refrescarla por
        detrás. No purga: quien la pide se encarga de renovarla."""
        entry = self._store.get(key)
        if not entry:
            return None, False
        edad = _time.time() - entry["ts"]
        if edad < entry["ttl"]:
            return entry["val"], True
        if edad < max_age:
            return entry["val"], False
        self._store.pop(key, None)
        return None, False

    def set(self, key, val, ttl=30, servible_hasta=0):
        """`servible_hasta`: segundos durante los que la entrada sigue valiendo aunque
        haya pasado su ttl, porque quien la lee usa `get_stale`.

        Sin esto, la purga de aquí abajo borraba entradas que `get_stale` habría
        servido perfectamente. El dashboard se guardaba con ttl de 5 minutos pero se
        sirve caducado hasta 30; a los 6 minutos ya contaba como "expirada" y la
        primera escritura con la caché llena se lo llevaba por delante. El síntoma no
        era un error: era una pantalla sin fuerza, sin razones y sin aviso de calidad
        de dato, es decir sin la mitad de lo que la hace útil.
        """
        now = _time.time()
        # Opportunistic purge of expired entries.
        if len(self._store) >= self._maxsize:
            expired = [k for k, e in self._store.items()
                       if (now - e["ts"]) >= max(e["ttl"], e.get("servible_hasta", 0))]
            for k in expired:
                self._store.pop(k, None)
            # Sigue sobrando -> se desaloja por antigüedad, pero SALTÁNDOSE lo que aún
            # es servible. Sin esto la corrección de arriba no sirve de nada: el
            # dashboard es de lo más antiguo que hay (se calienta y no se vuelve a
            # tocar), así que el desalojo FIFO se lo llevaba igualmente por la puerta
            # de al lado. Solo se toca lo protegido si TODO lo es, para que la caché
            # siga sin poder crecer sin límite.
            while len(self._store) >= self._maxsize:
                candidato = next(
                    (k for k, e in self._store.items() if not self._protegida(e, now)),
                    None,
                )
                self._store.pop(candidato or next(iter(self._store)), None)
        self._store[key] = {"val": val, "ts": now, "ttl": ttl,
                            "servible_hasta": servible_hasta}

    def clear(self):
        self._store.clear()

_cache = _TTLCache()

# Coste del pre-cálculo del Chartista (ver _prewarm_chartist). El ciclo va al ritmo de la
# caché, así que subir CHARTIST_TTL baja el consumo de cuota de Gemini proporcionalmente.
CHARTIST_TTL = int(os.environ.get("CHARTIST_TTL", 4 * 3600))   # 4h (antes 2h)
CHARTIST_PREWARM_MAX = int(os.environ.get("CHARTIST_PREWARM_MAX", 20))  # antes 30

# Precalentado del dashboard (ver _prewarm_dashboards). Al contrario que el del Chartista,
# este NO llama a ninguna IA: solo ensambla datos de mercado que en su mayoría ya están
# cacheados, así que es barato. Lo único que gasta es ~1 cotización de Finnhub por símbolo
# y vuelta.
DASHBOARD_PREWARM = os.environ.get("DASHBOARD_PREWARM", "1") != "0"
DASHBOARD_PREWARM_MAX = int(os.environ.get("DASHBOARD_PREWARM_MAX", 20))
# Por debajo de DASHBOARD_STALE_MAX (30 min) para que una entrada de la watchlist nunca se
# caiga de la ventana de "caducado pero servible".
DASHBOARD_PREWARM_CADENCIA = int(os.environ.get("DASHBOARD_PREWARM_CADENCIA", 1200))  # 20 min
# Espaciado entre símbolos. El limitador de Finnhub reserva 25 llamadas/min para tareas de
# fondo; a 4 s son 15/min, que deja margen para el worker de señales y no compite con quien
# esté navegando en ese momento.
DASHBOARD_PREWARM_PAUSA = float(os.environ.get("DASHBOARD_PREWARM_PAUSA", 4.0))
# Cuánta ocupación de la ventana de Finnhub hace que el precalentado se aparte.
#
# NO es un número suelto: se deriva de bg_cap, el techo de las tareas de FONDO. Tiene que
# quedar POR ENCIMA, o el precalentado se para a sí mismo — gasta 15 llamadas/min, el resto
# del fondo llega al techo, y con el umbral en ese mismo techo se detendría creyendo que hay
# alguien navegando cuando ese alguien es él. Puesto a 25 (= bg_cap) calentaba dos o tres
# símbolos por vuelta y abandonaba.
#
# Estando por encima, superarlo implica por fuerza llamadas de PRIMER plano —el fondo no
# puede pasar de bg_cap—, que es justo la señal que se quiere detectar.
PREWARM_MARGEN_CUOTA = int(os.environ.get("PREWARM_MARGEN_CUOTA", 10))
# Cuánto se considera FRESCO un dashboard. Ver el comentario largo donde se guarda:
# tiene que quedar por debajo de la cadencia del precalentado y muy por debajo de
# DASHBOARD_STALE_MAX.
DASHBOARD_TTL = int(os.environ.get("DASHBOARD_TTL", 900))  # 15 min
# Cuánto tiempo una alerta disparada sigue mereciendo la portada. NO depende de la
# última visita: mirar la pantalla no es haber actuado.
VENTANA_ALERTAS_HORAS = int(os.environ.get("VENTANA_ALERTAS_HORAS", 24))


def _umbral_prewarm() -> int:
    """Se calcula en cada vuelta para que siga siendo correcto si cambia el limitador."""
    return market_data.get_finnhub_limiter().bg_cap + PREWARM_MARGEN_CUOTA
# El mismo timeframe que pide el Dashboard al abrirse (frontend: TIMEFRAME_BASE). Si no
# coinciden, se calienta una clave que nadie pide después.
_TIMEFRAME_PREWARM = "1D"

mongo_url = os.environ.get("MONGO_URL")
if not mongo_url:
    raise RuntimeError("MONGO_URL no está configurada. Añádela en las variables de entorno de Render.")
# For MongoDB Atlas (mongodb+srv://) use bundled CA certs to avoid SSL handshake errors.
# Timeouts acotados: si Atlas M0 está dormido/lento, las queries fallan rápido en vez de
# colgar la corrutina hasta 30s (el default de Motor) y congelar el endpoint.
_mongo_kwargs = {
    "serverSelectionTimeoutMS": 5000,
    "connectTimeoutMS": 5000,
    "socketTimeoutMS": 10000,
}
if "mongodb+srv://" in mongo_url or "mongodb.net" in mongo_url:
    _mongo_kwargs.update({"tls": True, "tlsCAFile": certifi.where()})
client = AsyncIOMotorClient(mongo_url, **_mongo_kwargs)
db = client[os.environ.get("DB_NAME", "inveria")]


def _clean_nans(v):
    """Recursively replace NaN/Inf floats with None so JSON serialization never fails."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, dict):
        return {k: _clean_nans(v2) for k, v2 in v.items()}
    if isinstance(v, list):
        return [_clean_nans(v2) for v2 in v]
    return v


class SafeJSONResponse(JSONResponse):
    # Declara charset=utf-8 para que los navegadores (Safari en el móvil) no adivinen mal
    # la codificación al mostrar el JSON en crudo — sin esto, los acentos se ven como
    # mojibake ('ó' → 'Ã³') aunque los datos y los bytes sean UTF-8 correctos.
    media_type = "application/json; charset=utf-8"

    def render(self, content) -> bytes:
        return json.dumps(_clean_nans(content), ensure_ascii=False).encode("utf-8")


async def _chartist_vigilante(sym: str, result: dict):
    """VIGILANTE DEL CHARTISTA (#1): al recalcular el veredicto, compara con el estado
    anterior y avisa por Telegram SOLO cuando cambia algo accionable (el plan activa COMPRA,
    o el sentido gira a alcista/bajista). Muy selectivo + 1 aviso/día por acción para que sea
    señal y no ruido. Guarda el estado en Mongo (db.chartist_state)."""
    try:
        # El MISMO veto que aplica el endpoint, y por el mismo motivo. Un aviso de compra
        # es mas fuerte que una pantalla: llega al telefono sin que nadie lo haya pedido y
        # no tiene al lado el panel que explica que la accion esta vetada.
        #
        # Se decide sobre el veredicto degradado, no sobre el original.
        estado_t = await asyncio.to_thread(market_data.tendencia_de, sym)
        est = estado_accion.evaluar(estado_t)
        vetado = veto_compra.hay_veto(est["estado"])
        result = veto_compra.degradar_chartista(result, est["estado"], est["motivo"])

        plan = result.get("plan") or {}
        accion = (plan.get("accion") or "").upper()
        sentido = (result.get("sentido") or "").lower()
        prev = await db.chartist_state.find_one({"symbol": sym}, {"_id": 0})
        today = datetime.now(timezone.utc).date().isoformat()
        # Se guarda la accion DEGRADADA, no la del modelo. `chartist_state` no es el
        # veredicto generativo: es la contabilidad de avisos, y su unica pregunta es "ha
        # cambiado algo desde la ultima vez que mire?".
        #
        # Guardar COMPRAR mientras se veta romperia el aviso futuro: al levantarse el veto,
        # `prev_accion` ya seria COMPRAR, la transicion no dispararia y el usuario no se
        # enteraria nunca de que la compra quedo autorizada. Con ESPERAR guardado, el paso
        # ESPERAR -> COMPRAR llega el dia en que la estructura acompana.
        nuevo_estado = {"symbol": sym, "accion": accion, "sentido": sentido,
                        "updated_at": datetime.now(timezone.utc).isoformat()}
        if vetado:
            logger.info("Vigilante Chartista %s: compra vetada por tendencia (%s)",
                        sym, est["tendencia"])

        async def _guardar():
            await db.chartist_state.update_one({"symbol": sym}, {"$set": nuevo_estado}, upsert=True)

        if not prev:
            await _guardar()
            return  # primera vez: solo guardamos, no avisamos (evita avalancha al arrancar)
        if prev.get("last_notify_date") == today:
            await _guardar()
            return  # ya avisamos hoy de esta acción: no spameamos

        msg = None
        prev_accion = (prev.get("accion") or "").upper()
        prev_sentido = (prev.get("sentido") or "").lower()
        # 1) El plan ACTIVA compra (antes esperabas, ahora toca entrar).
        if accion == "COMPRAR" and prev_accion and prev_accion != "COMPRAR":
            niveles = [n.get("precio") for n in (plan.get("niveles_entrada") or []) if n.get("precio") is not None]
            nivstr = ", ".join(f"${float(p):.2f}" for p in niveles[:3]) if niveles else "ver plan"
            msg = (f"🎯 {sym}: el Chartista IA ha activado COMPRA.\n"
                   f"Niveles escalonados: {nivstr}.\n"
                   f"Invalidación: ${float(plan['invalidacion']):.2f}." if plan.get("invalidacion") else
                   f"🎯 {sym}: el Chartista IA ha activado COMPRA.\nNiveles: {nivstr}.")
        # 2) Giro de sentido a una dirección firme (alcista/bajista), distinto del anterior.
        elif sentido in ("alcista", "bajista") and prev_sentido and sentido != prev_sentido:
            flecha = "📈" if sentido == "alcista" else "📉"
            msg = f"{flecha} {sym}: el Chartista IA ha girado a {sentido.upper()} (antes {prev_sentido or '—'})."

        if not msg:
            await _guardar()
            return
        # Enviar PRIMERO y guardar solo si salió: send_message NO lanza (devuelve (ok, err)),
        # así que si se guardaba antes y Telegram fallaba, el cambio quedaba registrado como
        # "ya avisado" y el aviso se perdía para siempre.
        import telegram_notifier
        ok, err = await telegram_notifier.send_message(msg, parse_mode="", grupo="ideas_javi")
        if ok:
            nuevo_estado["last_notify_date"] = today
            await _guardar()
            logger.info("Vigilante Chartista avisó de %s", sym)
        else:
            # No guardamos: el próximo ciclo volverá a detectar el cambio y reintentará.
            logger.warning("Vigilante %s: Telegram falló (%s); reintentaré", sym, str(err)[:120])
    except Exception as e:
        logger.warning("Vigilante Chartista %s falló: %s", sym, str(e)[:120])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ----- Startup -----
    # Diagnóstico de memoria opcional: con MEM_TRACE=1 arranca tracemalloc desde el
    # principio para que /api/debug/memory pueda mostrar las líneas que más asignan.
    if os.environ.get("MEM_TRACE") == "1":
        try:
            import tracemalloc
            tracemalloc.start(25)  # guarda hasta 25 frames de traceback por asignación
            logger.info("tracemalloc ACTIVO (MEM_TRACE=1)")
        except Exception as e:
            logger.warning("No se pudo arrancar tracemalloc: %s", e)
    # DB indexes
    await db.signal_entries.create_index("symbol")
    await db.signal_entries.create_index("active")

    # Limpieza: el grupo "Cimientos" se ha retirado. Borra sus entradas para que no
    # aparezcan en Alertas ni en el Calendario. (No se crean nuevas: la UI ya no lo ofrece.)
    try:
        _rm = await db.signal_entries.delete_many({"grupo": "cimientos"})
        if _rm.deleted_count:
            logger.info("Cimientos retirado: %d entradas borradas", _rm.deleted_count)
            _cache._store.pop("signals_list", None)
            _invalidar_signals_hot()
    except Exception as e:
        logger.warning(f"Purga de Cimientos falló: {e}")
    await db.analyses.create_index([("symbol", 1), ("created_at", -1)])
    await db.watchlist.create_index("symbol")
    await db.chartist_state.create_index("symbol", unique=True)
    await db.alerts.create_index("symbol")
    # Libro de operaciones: todo se consulta por símbolo y se ordena por fecha.
    await db.isin_map.create_index("isin", unique=True)
    for coleccion in (db.compras, db.ventas, db.dividendos):
        await coleccion.create_index([("symbol", 1), ("fecha", 1)])
        await coleccion.create_index("id", unique=True)
    # Las tres consultas de newsletters filtran por received_at >= cutoff y ordenan por
    # received_at descendente. Sin índice, Mongo recorría la colección entera y ordenaba en
    # memoria en cada cambio de ticker (/fuentes está en ese camino).
    await db.newsletter_summaries.create_index([("received_at", -1)])
    await db.analyst_ideas.create_index([("symbol", 1), ("detected_at", -1)])

    # Wire the persistent snapshot cache and hydrate in-memory caches from the last
    # saved scan so the first request returns data instantly (no "warming" screen).
    opportunities.set_db(db)
    try:
        await opportunities.load_snapshots_into_cache()
    except Exception as e:
        logger.warning(f"Snapshot hydrate failed: {e}")

    # Carga el "cerebro" (conocimiento acumulado de newsletters) en memoria para que el
    # motor de análisis lo inyecte desde el primer request.
    try:
        import knowledge_base
        await db.investing_knowledge.create_index("_key", unique=True)
        await knowledge_base.ensure_loaded(db)
        # Mantenimiento automático: dedup semántico LLM una vez por semana.
        asyncio.create_task(knowledge_base.maintenance_loop(db))
    except Exception as e:
        logger.warning(f"Knowledge base load failed: {e}")

    # Lector de Telegram: escucha los canales de tu grupo de pago (si está configurado).
    try:
        import telegram_reader
        asyncio.create_task(telegram_reader.reader_worker_loop(db))
    except Exception as e:
        logger.warning(f"Telegram reader start failed: {e}")

    # Ingesta de noticias de mercado → cerebro + Radar (cada ~6 h).
    try:
        import news_ingest
        asyncio.create_task(news_ingest.news_worker_loop(db))
    except Exception as e:
        logger.warning(f"News ingest start failed: {e}")

    # Aviso de seguridad no-bloqueante: si faltan secretos en producción, se usan
    # defaults públicos del repo (cualquiera podría forjar un token). No rompe el arranque.
    if not os.environ.get("JWT_SECRET"):
        logger.warning("JWT_SECRET no configurada — usando secreto por defecto. Configúrala en Render.")
    if not os.environ.get("APP_PASSWORD_HASH"):
        logger.warning("APP_PASSWORD_HASH no configurada — usando contraseña por defecto. Configúrala en Render.")

    # Single alert system: the portfolio table (signal_table) worker.
    asyncio.create_task(signal_table.signal_worker_loop(db))

    # Analista Institucional: vigía que busca confluencia de catalizadores (insiders,
    # upgrades, earnings, score) y avisa cuando algo destaca de verdad.
    asyncio.create_task(daily_analyst.worker_loop(db))
    # Resumen diario por email tras el cierre de mercado.
    asyncio.create_task(daily_analyst.digest_loop(db))

    # Vigía del RSI del S&P 500: avisa por Telegram cuando el ÍNDICE entra en sobreventa.
    # Coste ínfimo: una comprobación por hora sobre el histórico de SPY que ya está cacheado.
    asyncio.create_task(sp500_rsi_watch.worker_loop(db))

    # Pre-warm daily opportunities so the first user request hits a warm cache —
    # PERO solo si el snapshot hidratado desde Mongo ya está caducado. En la mayoría
    # de redeploys el snapshot es reciente, así que nos saltamos el escaneo (pesado en
    # memoria: carga DataFrames de 2 años) y evitamos el pico de RAM al arrancar. Si
    # hace falta, se recalcula en segundo plano cuando un usuario llame al endpoint.
    async def _prewarm_opportunities():
        try:
            await asyncio.sleep(20)  # deja terminar el arranque (índices, hidratación, worker)
            if opportunities.daily_cache_is_fresh():
                logger.info("Opportunities snapshot aún fresco — se omite el precalentado")
                return
            await opportunities.scan_daily_opportunities(force_refresh=True)
            logger.info("Opportunities pre-warm complete")
        except Exception as e:
            logger.warning(f"Opportunities pre-warm failed: {e}")

    asyncio.create_task(_prewarm_opportunities())

    # Pre-warm the growth screener, bien escalonado tras las oportunidades para que
    # los dos escaneos pesados NO coincidan en memoria. También se omite si el
    # snapshot del screener sigue vigente.
    async def _prewarm_screener():
        try:
            await asyncio.sleep(240)
            if opportunities.screener_cache_is_fresh():
                logger.info("Screener snapshot aún fresco — se omite el precalentado")
                return
            await opportunities._run_screener_scan()
            logger.info("Growth screener pre-warm complete")
        except Exception as e:
            logger.warning(f"Screener pre-warm failed: {e}")

    asyncio.create_task(_prewarm_screener())

    # Auto-refresh daily opportunities during US market hours so signals are always
    # fresh without user interaction. Runs every 20 min; only refreshes if stale
    # and within the market trading window (13:00-21:30 UTC covers EDT + EST).
    async def _auto_refresh_opportunities():
        while True:
            try:
                await asyncio.sleep(1200)  # 20 min
                now = datetime.now(timezone.utc)
                in_window = now.weekday() < 5 and 13 <= now.hour < 22
                if in_window and not opportunities.daily_cache_is_fresh():
                    await opportunities.scan_daily_opportunities(force_refresh=True)
                    logger.info("Auto-refreshed daily opportunities (market hours)")
            except Exception as e:
                logger.warning(f"Auto-refresh opportunities failed: {e}")

    asyncio.create_task(_auto_refresh_opportunities())

    # PRECALENTADO del dashboard para la watchlist + la cartera.
    #
    # Por qué: el servir-caducado-y-refrescar ya hace que la SEGUNDA visita a un ticker sea
    # instantánea, pero la PRIMERA del día sigue pagando el ensamblado completo. Y como esas
    # acciones son justo las que vas a mirar, la primera visita es la norma, no la excepción.
    # Con la caché caliente, elegir una acción de la watchlist se sirve de memoria.
    #
    # El ciclo va por DEBAJO de DASHBOARD_STALE_MAX (30 min) a propósito: así una entrada de
    # la watchlist nunca se cae de la ventana de "caducado pero servible", y el peor caso
    # deja de ser la carga completa.
    #
    # Coste: la parte cara (analistas 4h, fundamentales 1h, volume profile 12h) ya está
    # cacheada, así que cada vuelta es ~1 llamada de cotización por símbolo. Se espacian
    # DASHBOARD_PREWARM_PAUSA segundos para no vaciar de golpe la reserva de fondo del
    # limitador de Finnhub y dejar sin cuota a quien esté navegando en ese momento.
    async def _prewarm_dashboards():
        """Precalienta los dashboards por tandas ROTATORIAS.

        Antes hacía `list(syms)[:20]` sobre un CONJUNTO. El orden de iteración de un
        conjunto es arbitrario pero estable dentro del proceso, así que con más de 20
        símbolos se calentaban siempre los mismos veinte y el resto NUNCA — no era una
        rotación lenta, era un punto ciego fijo hasta reiniciar. Y los que caían fuera
        eran siempre los mismos sin que nada lo dijera.
        """
        if not DASHBOARD_PREWARM:
            logger.info("Precalentado de dashboards desactivado (DASHBOARD_PREWARM=0)")
            return
        await asyncio.sleep(45)  # tras el arranque, pero antes que los escaneos pesados
        vuelta = 0
        # P1 · Este bucle es una tarea de FONDO y hay que decirlo, porque el limitador de
        # Finnhub decide su techo por contexto: sin la marca usaba `max_per_min` (50) en
        # vez de `bg_cap` (25). Con 5 llamadas por símbolo, llenaba la ventana él solo,
        # veía 50 > 35 y concluía "hay alguien navegando" — siendo él quien navegaba.
        #
        # Va aquí y no dentro del `while` porque es un contextvar de ESTA tarea: se fija
        # una vez y lo heredan los hilos de run_in_executor, que es por donde salen las
        # llamadas. No contamina las peticiones de usuario, que corren en su propio
        # contexto. Aun así se restaura al salir, para no dejar el contexto tocado si
        # alguien reutiliza la tarea.
        token_bg = market_data.enter_finnhub_background()
        try:
            await _vueltas_de_precalentado()
        finally:
            market_data.reset_finnhub_background(token_bg)

    async def _vueltas_de_precalentado():
        vuelta = 0
        while True:
            try:
                now = datetime.now(timezone.utc)
                # Se incluye la pre-apertura (12:00 UTC): la primera mirada del día suele
                # ser antes de que abra, y es justo la que hoy paga la carga entera.
                in_window = now.weekday() < 5 and 12 <= now.hour < 22

                # La COLA se atiende SIEMPRE, dentro y fuera de la ventana. La ventana
                # existe para no gastar cuota adelantando trabajo por si acaso; un símbolo
                # encolado no es especulación: alguien tiene la portada abierta ahora y le
                # falta ese dato. Si solo se atendiera en horario, un sábado por la tarde
                # la cola no se vaciaría nunca y volveríamos al problema que P3 arregla.
                pendientes = _tomar_de_la_cola(DASHBOARD_PREWARM_MAX)
                syms = set(pendientes)
                tanda = list(pendientes)
                if in_window:
                    syms = await _simbolos_que_te_importan()
                    rotatoria = _tanda_a_precalentar(syms, vuelta)
                    vuelta += 1
                    # La cola va primero y el resto del presupuesto lo llena la rotación,
                    # sin repetir. El coste por vuelta no sube: sigue topado en el mismo
                    # número de símbolos.
                    tanda += [s for s in rotatoria if s not in pendientes]
                    tanda = tanda[:DASHBOARD_PREWARM_MAX]

                if tanda:
                    calentados = 0
                    omitidos = []
                    for sym in tanda:
                        # CEDER EL PASO. Medido en producción: con la cuota en 49/50, una
                        # carga que normalmente son ~500 ms se fue a 5.043 ms, porque cada
                        # llamada de Finnhub esperaba al limitador y un dashboard hace
                        # varias. El tope bg_cap impide que el fondo se PASE, pero no impide
                        # que llene la ventana justo mientras alguien navega.
                        #
                        # Adelantar trabajo por si acaso nunca justifica frenar el que se
                        # está pidiendo ahora. Si hay actividad, este ciclo se deja para la
                        # próxima vuelta — y si estás navegando tanto, tus propias visitas
                        # ya están calentando la caché de todos modos.
                        try:
                            uso = market_data.get_finnhub_limiter().uso_ultimo_minuto()
                        except Exception:
                            uso = 0
                        if uso > _umbral_prewarm():
                            logger.info(
                                "Precalentado en pausa: %d/%d llamadas en el último minuto "
                                "(umbral %d — hay alguien navegando); se reanuda en la "
                                "próxima vuelta",
                                uso, market_data.get_finnhub_limiter().max_per_min,
                                _umbral_prewarm())
                            break
                        # Si el dashboard COMPLETO sigue fresco —porque abriste la acción
                        # hace poco— no hay nada que hacer: ya trae las tres claves.
                        _, fresco = _cache.get_stale(
                            f"dashboard:{sym}:{_TIMEFRAME_PREWARM}",
                            max_age=_DASHBOARD_STALE_MAX)
                        clave = f"{CLAVE_NIVELES}:{sym}"
                        if fresco or _cache.get_stale(clave, max_age=_DASHBOARD_STALE_MAX)[1]:
                            continue

                        # P2 · CAMINO LIGERO. Se calculan solo las tres claves que consume
                        # la portada, con el precio que el worker de señales ya guardó en
                        # Mongo. Cero llamadas a Finnhub por símbolo, frente a las cinco
                        # del dashboard completo.
                        entry = await db.signal_entries.find_one(
                            {"symbol": sym}, {"_id": 0, "last_price": 1, "updated_at": 1})
                        precio, motivo = precio_para_niveles(entry or {})
                        if precio is None:
                            # Ni se calcula con un precio viejo ni se pide una cotización a
                            # escondidas para aparentar frescura: el símbolo se queda sin
                            # datos y la tarjeta lo dice.
                            omitidos.append(f"{sym}({motivo})")
                            continue
                        try:
                            ligero = await construir_niveles_ligero(sym, precio)
                            if ligero:
                                _cache.set(clave, ligero, ttl=DASHBOARD_TTL,
                                           servible_hasta=_DASHBOARD_STALE_MAX)
                                calentados += 1
                        except Exception as e:
                            logger.warning("Precalentado de %s falló: %s", sym, str(e)[:120])
                        # El Backtest se carga SOLO al elegir una acción y se cachea 6 h,
                        # así que la primera visita a cada símbolo pagaba ~900 ms medidos en
                        # producción. Calentarlo aquí lo quita del camino. No usa Finnhub
                        # (trabaja sobre el histórico, que acaba de quedar en caché), así
                        # que no cuesta cuota: solo CPU, y aquí sobra.
                        try:
                            await backtest_levels(sym, _user="prewarm")
                        except Exception:
                            pass  # sin histórico suficiente: no es un problema
                        await asyncio.sleep(DASHBOARD_PREWARM_PAUSA)
                    # "Tus fuentes" lee las newsletters del último mes, y esa lectura ya va
                    # cacheada y es la MISMA para todos los símbolos: basta con calentarla
                    # una vez por vuelta, no una por acción.
                    try:
                        await _newsletters_recientes(30, 300)
                    except Exception:
                        pass
                    # Se registran los símbolos, no solo cuántos. Es lo que permite
                    # comprobar desde los logos de Render QUÉ hay caliente sin necesidad
                    # de un endpoint nuevo: la caché vive en la memoria de este proceso y
                    # un script en la Shell arranca otro proceso con la caché vacía, así
                    # que preguntarle a él no dice nada de lo que tiene el servicio web.
                    if calentados or omitidos:
                        logger.info("Niveles precalentados (vuelta %d): %d de %d · %s",
                                    vuelta, calentados, len(syms), ", ".join(tanda))
                    if omitidos:
                        # Se dice CUÁLES y POR QUÉ. Un símbolo omitido acaba viéndose como
                        # "Motor de niveles: sin datos todavía", y sin esta línea no habría
                        # forma de saber si es por falta de precio o por precio desfasado.
                        logger.info("Omitidos por el contrato de last_price: %s",
                                    ", ".join(omitidos))
                    mem.trim()  # el ensamblado crea DataFrames: devuélvelos al SO
            except Exception as e:
                logger.warning("Bucle de precalentado de dashboards: %s", e)
            # Espera la cadencia normal, PERO despierta antes si alguien encola algo.
            # Con un `sleep` a secas, un símbolo pedido desde la portada podía quedarse
            # hasta 20 minutos esperando, y encolar habría sido peor que el calentado
            # directo que sustituye. Con el evento, la espera es de segundos y el gasto
            # sigue cadenciado por el limitador.
            try:
                await asyncio.wait_for(_hay_pendientes.wait(),
                                       timeout=DASHBOARD_PREWARM_CADENCIA)
            except asyncio.TimeoutError:
                pass

    _tarea_prewarm = asyncio.create_task(_prewarm_dashboards())
    _bg_tasks.add(_tarea_prewarm)
    _tarea_prewarm.add_done_callback(_bg_tasks.discard)

    # PRE-CÁLCULO del Chartista para la watchlist + la cartera. REGLAS DE COSTE (tras quemar
    # 3.65 EUR en un día): SOLO usa la key Gemini GRATIS (free_only=True — jamás la de pago
    # ni Groq); si la cuota gratis se agota (429), CORTA el ciclo entero hasta la siguiente
    # vuelta. El crédito de pago queda reservado a los análisis que pides con el botón.
    #
    # OJO con el volumen: a 2h de caché y 30 símbolos salían ~30 × 4,5 ciclos = ~135 llamadas
    # a Gemini AL DÍA antes de que tocaras un botón. Este bucle no paga (es gratis), pero
    # agota la cuota gratis diaria, y entonces son TUS análisis manuales los que caen a la
    # key de pago. O sea: el pre-cálculo no paga, hace que pagues tú. A 4h y 20 símbolos
    # baja a ~40-45/día (un tercio), dejando cuota gratis de sobra para el uso manual.
    async def _prewarm_chartist():
        await asyncio.sleep(120)  # deja que el arranque respire antes de empezar
        while True:
            try:
                now = datetime.now(timezone.utc)
                in_window = now.weekday() < 5 and 13 <= now.hour < 22
                if in_window:
                    syms = await _simbolos_que_te_importan()
                    for sym in list(syms)[:CHARTIST_PREWARM_MAX]:
                        if _cache.get(f"chartist:{sym}") is not None:
                            continue  # ya está fresco en caché
                        try:
                            result = await chartist.analyze(sym, free_only=True)
                            _cache.set(f"chartist:{sym}", result, ttl=CHARTIST_TTL)
                            await _chartist_vigilante(sym, result)  # #1 avisa si cambia algo
                            logger.info("Chartista pre-calculado para %s (gratis)", sym)
                        except Exception as e:
                            msg = str(e)
                            low = msg.lower()
                            # Cuota gratis agotada → parar TODO el ciclo (los demás también
                            # fallarían y no queremos ni un reintento de más).
                            if "429" in msg or "resource_exhausted" in low or "quota" in low:
                                logger.warning("Pre-cálculo: cuota GRATIS agotada; ciclo cortado hasta la próxima vuelta")
                                break
                            logger.warning("Pre-cálculo Chartista %s falló: %s", sym, msg[:120])
                        await asyncio.sleep(10)  # espacia las llamadas (datos + IA)
                    mem.trim()  # el pre-cálculo crea muchos DataFrames: devuélvelos al SO
            except Exception as e:
                logger.warning("Prewarm chartist loop error: %s", e)
            await asyncio.sleep(CHARTIST_TTL)  # el ciclo va al ritmo de la caché

    asyncio.create_task(_prewarm_chartist())

    # Trimmer periódico: devuelve al SO la memoria libre que glibc retiene tras los jobs
    # pesados (pandas). Coste ínfimo (1 vez cada 10 min) y evita que la RSS se quede en el
    # máximo alcanzado y trepe hacia el límite de 512MB.
    async def _mem_trim_loop():
        while True:
            await asyncio.sleep(600)  # 10 min
            try:
                mem.trim()
            except Exception:
                pass

    asyncio.create_task(_mem_trim_loop())

    yield

    # ----- Shutdown -----
    client.close()


# La documentación interactiva se sirve solo FUERA de producción. No filtra datos,
# pero publica el mapa completo de la API —cada ruta, cada parámetro, cada modelo—,
# que es justo lo que ahorra trabajo a quien quiera sondearla. En local sigue
# disponible en /docs porque ahí sí resuelve un problema real al desarrollar.
_EN_PRODUCCION = bool(os.environ.get("RENDER"))

app = FastAPI(
    title="InverIA API",
    default_response_class=SafeJSONResponse,
    lifespan=lifespan,
    docs_url=None if _EN_PRODUCCION else "/docs",
    redoc_url=None if _EN_PRODUCCION else "/redoc",
    openapi_url=None if _EN_PRODUCCION else "/openapi.json",
)
api_router = APIRouter(prefix="/api")

logger = logging.getLogger("inveria")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Referencias fuertes a tareas en segundo plano (si no, el GC puede cancelarlas).
_bg_tasks: set = set()


# ── Contrato de frescura de last_price ───────────────────────────────────────
# El worker de señales escribe `last_price` y `updated_at` en signal_entries, pero SOLO
# durante la sesión extendida (L-V 04:00-20:00 ET). Fuera de ella duerme.
#
# Por eso un umbral en minutos a secas sería un error: rechazaría el precio todo el fin
# de semana, y justo entonces pedir una cotización nueva devolvería EL MISMO cierre del
# viernes, gastando cuota para obtener lo que ya teníamos.
#
# El fondo: fuera de sesión, un precio de 49 horas no es viejo, es el precio actual. Lo
# que caduca un precio no es el reloj, es que el mercado haya cotizado después. De ahí
# las dos reglas:
#
#   · Sesión activa  -> `updated_at` dentro de LAST_PRICE_MAX_EDAD. Con 40 símbolos el
#                       ciclo del worker es de ~96 s, así que 10 min tolera seis ciclos
#                       perdidos: absorbe una pausa del limitador o un reinicio sin
#                       rechazar en falso.
#   · Sesión cerrada -> vale si `updated_at` es POSTERIOR al último cierre, sin límite
#                       en minutos, porque refleja el último precio que existió.
#
# Si no se cumple ninguna, no se calcula nada: ni con un precio viejo disfrazado de
# actual, ni pidiendo una cotización a escondidas para aparentar frescura.
LAST_PRICE_MAX_EDAD = int(os.environ.get("LAST_PRICE_MAX_EDAD", 600))  # 10 min


def _inicio_de_la_ultima_sesion(ahora_et):
    """Las 04:00 ET del día de la última sesión extendida (la de hoy o la anterior).

    Se compara contra el INICIO y no contra el cierre. Parece un detalle y no lo es: el
    worker escribe DURANTE la sesión, así que su última anotación del viernes es de las
    19:59 — anterior al cierre de las 20:00. Comparando contra el cierre, ningún precio
    lo superaría nunca y el contrato rechazaría absolutamente todo fuera de horario,
    justo el caso que venía a resolver.

    Lo que se quiere comprobar es otra cosa: que el precio se escribiera DURANTE la
    última sesión, o sea que no haya habido negociación posterior que lo deje viejo.
    """
    from datetime import time as _t
    dia = ahora_et.date()
    if ahora_et.weekday() < 5 and ahora_et.time() >= _t(4, 0):
        return datetime.combine(dia, _t(4, 0), tzinfo=ahora_et.tzinfo)
    while True:
        dia -= timedelta(days=1)
        if dia.weekday() < 5:
            return datetime.combine(dia, _t(4, 0), tzinfo=ahora_et.tzinfo)


def precio_para_niveles(entry: dict, ahora=None, sesion_activa=None):
    """El precio con el que se pueden calcular niveles, o None si no lo hay.

    Devuelve (precio, motivo). El motivo es para poder explicarlo, no para adornar:
    "sin_precio" y "precio_desfasado" llevan a sitios distintos.
    """
    import signal_table
    from zoneinfo import ZoneInfo

    precio = (entry or {}).get("last_price")
    marca = (entry or {}).get("updated_at")
    if not precio or not marca:
        # Símbolo recién añadido: no tiene precio hasta que el worker complete un ciclo.
        # Quedarse en "sin datos" un minuto es preferible a inventarse una señal.
        return None, "sin_precio"

    try:
        actualizado = datetime.fromisoformat(str(marca))
    except (TypeError, ValueError):
        return None, "sin_precio"
    if actualizado.tzinfo is None:
        actualizado = actualizado.replace(tzinfo=timezone.utc)

    ahora = ahora or datetime.now(timezone.utc)
    if sesion_activa is None:
        sesion_activa = signal_table._extended_session_active()

    if sesion_activa:
        if (ahora - actualizado).total_seconds() <= LAST_PRICE_MAX_EDAD:
            return float(precio), "fresco"
        return None, "precio_desfasado"

    inicio = _inicio_de_la_ultima_sesion(ahora.astimezone(ZoneInfo("America/New_York")))
    if actualizado >= inicio:
        return float(precio), "cierre_vigente"
    return None, "precio_desfasado"


# ── Cola de calentado a petición ─────────────────────────────────────────────
# La portada encola los símbolos que necesita en vez de calentarlos ella misma.
#
# Antes lanzaba hasta 5 `_construir_dashboard` a la vez: unas 25 llamadas a Finnhub de
# golpe, sin espaciar, sin pasar por el umbral de pausa y en PRIMER PLANO —heredaba el
# contexto de la petición—. Es decir, el único camino que se saltaba entero el control
# de cuota era el que yo había añadido.
#
# Ahora hay un solo mecanismo: el bucle de precalentado, con su marca de background, su
# cadencia y su tope. La portada solo apunta qué le falta y sigue respondiendo.
_COLA_CALENTADO_MAX = 20
_cola_calentado: dict = {}          # dict = orden de llegada + deduplicado
_hay_pendientes = asyncio.Event()


def _encolar_calentado(simbolos) -> int:
    """Apunta símbolos para que el precalentado los atienda en su próxima pasada.

    Devuelve cuántos se han añadido de nuevo. Acotada a `_COLA_CALENTADO_MAX`: si se
    llena, se descartan los nuevos en vez de crecer sin límite — quien llega tarde
    entrará en la vuelta siguiente, que es preferible a una cola que no para de crecer
    mientras alguien recarga la portada.
    """
    añadidos = 0
    for sym in simbolos:
        sym = (sym or "").upper().strip()
        if not sym or sym in _cola_calentado:
            continue
        if len(_cola_calentado) >= _COLA_CALENTADO_MAX:
            break
        _cola_calentado[sym] = True
        añadidos += 1
    if _cola_calentado:
        _hay_pendientes.set()
    return añadidos


def _tomar_de_la_cola(tope: int) -> list:
    """Saca hasta `tope` símbolos pendientes, los más antiguos primero."""
    salida = []
    for sym in list(_cola_calentado)[:tope]:
        _cola_calentado.pop(sym, None)
        salida.append(sym)
    if not _cola_calentado:
        _hay_pendientes.clear()
    return salida


def _tanda_a_precalentar(simbolos, vuelta: int, tamano: int = None) -> list:
    """Los símbolos que toca calentar en esta vuelta.

    Orden alfabético (determinista: el mismo conjunto da siempre la misma secuencia) y
    ventana deslizante que avanza `tamano` posiciones por vuelta, dando la vuelta al
    final. Con 50 símbolos y tandas de 20, todos quedan cubiertos en 3 vueltas — una
    hora — en vez de no cubrirse nunca.

    El coste por vuelta no cambia: se sigue calentando como mucho `tamano`.
    """
    tamano = tamano or DASHBOARD_PREWARM_MAX
    ordenados = sorted(simbolos)
    if not ordenados:
        return []
    if len(ordenados) <= tamano:
        return ordenados
    inicio = (vuelta * tamano) % len(ordenados)
    # Se duplica la lista para poder cortar una ventana que cruza el final sin partirla.
    return (ordenados + ordenados)[inicio:inicio + tamano]


async def _simbolos_que_te_importan() -> set:
    """Watchlist (el corazón) + cartera (señales activas), en mayúsculas y sin repetidos.

    Es el conjunto que alimenta TODO lo que se precalienta. Estaba escrito a mano dentro
    del pre-cálculo del Chartista; al necesitarlo también el del dashboard, tenerlo en dos
    sitios garantizaba que un día se calentaran conjuntos distintos.
    """
    syms = set()
    try:
        for it in await db.watchlist.find({}, {"_id": 0, "symbol": 1}).to_list(200):
            if it.get("symbol"):
                syms.add(it["symbol"].upper())
        for it in await db.signal_entries.find({"active": True}, {"_id": 0, "symbol": 1}).to_list(200):
            if it.get("symbol"):
                syms.add(it["symbol"].upper())
    except Exception as e:
        logger.warning("No se pudieron leer los símbolos a precalentar: %s", e)
    return syms


# ---------- Models ----------
class WatchlistItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    added_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WatchlistCreate(BaseModel):
    symbol: str


class PriceAlert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    target_price: float
    direction: str  # "above" or "below"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    triggered: bool = False


class PriceAlertCreate(BaseModel):
    symbol: str
    target_price: float
    direction: str


class AnalyzeRequest(BaseModel):
    symbol: str
    model: Optional[str] = "gemini-2.5-flash"


class CompareRequest(BaseModel):
    symbols: List[str]



class SignalEntryCreate(BaseModel):
    symbol: str
    name: Optional[str] = ""
    mercado: Optional[str] = ""
    grupo: Optional[str] = "ideas_javi"
    deseado: Optional[float] = None
    nivel1: Optional[float] = None
    nivel2: Optional[float] = None
    nivel3: Optional[float] = None
    nivel4: Optional[float] = None
    nivel5: Optional[float] = None
    venta1: Optional[float] = None
    venta2: Optional[float] = None
    venta3: Optional[float] = None
    alert_deseado: Optional[bool] = True
    alert_nivel1: Optional[bool] = True
    alert_nivel2: Optional[bool] = True
    alert_nivel3: Optional[bool] = True
    alert_nivel4: Optional[bool] = True
    alert_nivel5: Optional[bool] = True
    alert_venta1: Optional[bool] = True
    alert_venta2: Optional[bool] = True
    alert_venta3: Optional[bool] = True
    riesgo: Optional[str] = ""
    sector: Optional[str] = ""
    posibles_ganancias: Optional[float] = None
    notes: Optional[str] = ""
    active: Optional[bool] = True
    divisa: Optional[str] = ""
    bz: Optional[float] = None
    objetivo_5a: Optional[float] = None
    compra: Optional[float] = None
    fecha_compra: Optional[str] = None
    acciones: Optional[float] = None
    # Saltarse el veto de tendencia a conciencia. NO se guarda: no esta en
    # `signal_table.ALLOWED_CREATE`, asi que la capa de datos lo descarta sola.
    #
    # Existe porque el veto protege del automatismo, no del usuario. Que la IA no pueda
    # autorizar una compra no significa que la aplicacion pueda prohibirsela a quien la
    # decide: querer los niveles preparados de una accion todavia bajista, para cuando
    # gire, es un caso legitimo. Por defecto se bloquea; saltarselo hay que decirlo.
    forzar: Optional[bool] = False


class SignalEntryUpdate(BaseModel):
    name: Optional[str] = None
    mercado: Optional[str] = None
    grupo: Optional[str] = None
    deseado: Optional[float] = None
    nivel1: Optional[float] = None
    nivel2: Optional[float] = None
    nivel3: Optional[float] = None
    nivel4: Optional[float] = None
    nivel5: Optional[float] = None
    venta1: Optional[float] = None
    venta2: Optional[float] = None
    venta3: Optional[float] = None
    alert_deseado: Optional[bool] = None
    alert_nivel1: Optional[bool] = None
    alert_nivel2: Optional[bool] = None
    alert_nivel3: Optional[bool] = None
    alert_nivel4: Optional[bool] = None
    alert_nivel5: Optional[bool] = None
    alert_venta1: Optional[bool] = None
    alert_venta2: Optional[bool] = None
    alert_venta3: Optional[bool] = None
    riesgo: Optional[str] = None
    sector: Optional[str] = None
    posibles_ganancias: Optional[float] = None
    notes: Optional[str] = None
    active: Optional[bool] = None
    divisa: Optional[str] = None
    bz: Optional[float] = None
    objetivo_5a: Optional[float] = None
    compra: Optional[float] = None
    acciones: Optional[float] = None
    # Necesaria para el tipo de cambio del día de la compra: sin ella la ganancia en
    # euros al vender sale aproximada. Editable para poder rellenarla en posiciones viejas.
    fecha_compra: Optional[str] = None
    # Mismo escape explicito que en el alta, y tampoco se guarda: `ALLOWED_UPDATE` no lo
    # incluye. Va con default `False` y no `None` para que `exclude_unset` no lo arrastre
    # como campo a escribir cuando el cliente no lo manda.
    forzar: Optional[bool] = False


class SignalBulkImport(BaseModel):
    rows: List[dict]


# ---------- Health ----------
@api_router.get("/")
async def root():
    return {"app": "InverIA", "status": "ok"}


@api_router.api_route("/health", methods=["GET", "HEAD"])
async def health():
    """Lightweight liveness probe (Render health check / uptime monitoring).
    Accepts both GET and HEAD."""
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ---------- Auth ----------
@api_router.post("/auth/login", response_model=auth.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    motivo = auth.motivo_de_rechazo(form_data.username, form_data.password)
    if motivo:
        # Se registra la ETAPA, nunca el dato. Sin esto, un 401 obliga a adivinar entre
        # cuatro causas que se arreglan de forma distinta: el usuario no coincide, el
        # hash está mal pegado, la contraseña es incorrecta, o se está cayendo al
        # respaldo de desarrollo. Al usuario se le sigue devolviendo el mismo mensaje
        # genérico: decirle cuál de las cuatro es sería decirle si el usuario existe.
        logger.warning("Login rechazado · etapa: %s", motivo)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token = auth.create_access_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer", "username": form_data.username}


@api_router.get("/auth/me")
async def me(current_user: str = Depends(auth.get_current_user)):
    return {"username": current_user, "authenticated": True}


def _etiqueta_gemini() -> str:
    """Nombre legible del Gemini que se está usando DE VERDAD.

    Estaba escrito a mano como "Gemini 2.5 Flash" mientras `GEMINI_MODEL` valía
    `gemini-3.6-flash`: dos modelos distintos, y el texto no se movía al cambiar la
    variable de entorno. El modelo es overridable sin desplegar (justamente para poder
    cambiarlo el día que Google retire uno), así que cualquier nombre escrito a mano
    caduca solo. Se deriva del valor real y deja de haber dos versiones de la verdad.
    """
    crudo = (ai_analysis.GEMINI_MODEL or "").strip()
    if not crudo:
        return "Gemini"
    return " ".join(t.capitalize() if not t[0].isdigit() else t
                    for t in crudo.split("-"))


@api_router.get("/models")
async def available_models(_user: str = Depends(auth.get_current_user)):
    return {
        "models": [
            {"value": "gemini-2.5-flash", "label": f"{_etiqueta_gemini()} (Gratis · Recomendado)", "free": True, "available": True},
            {"value": "gpt-oss-120b", "label": "GPT-OSS 120B (Gratis)", "free": True, "available": True},
            {"value": "gpt-5.2", "label": "GPT-5.2 (Premium)", "free": False, "available": ai_analysis.EMERGENT_AVAILABLE},
        ],
        "premium_available": ai_analysis.EMERGENT_AVAILABLE,
    }


def _cached_vp(sym: str, dias: int = 365):
    """Volume profile con caché de 12 h.

    Son 365 días de agregados de Polygon (~900 ms) para dibujar un histograma que apenas
    se mueve de un día para otro. Iba SIN caché en NINGUNO de sus dos usos, así que se
    pagaba entero en cada cambio de ticker y otra vez a los 5 minutos.

    El endpoint de diagnóstico llama a polygon_data directamente a propósito: mide el coste
    real de la fuente, y leerlo de caché daría siempre 0 ms y no mediría nada.
    """
    ck = f"vp:{sym}:{dias}"
    v = _cache.get(ck)
    if v is not None:
        return v
    v = polygon_data.get_volume_profile(sym, dias)
    if v:
        _cache.set(ck, v, ttl=43200)
    return v


# ---------- Quote ----------
@api_router.get("/quote/{symbol}")
async def get_quote(symbol: str, _user: str = Depends(auth.get_current_user)):
    sym = symbol.upper()
    cached = _cache.get(f"quote:{sym}")
    if cached:
        return cached
    # to_thread: get_quote abre red (Finnhub + yfinance). Llamarlo directo desde un
    # `async def` bloquea el event loop y CONGELA el servidor entero mientras dura —
    # y este endpoint lo sondea cada tab abierta cada 30 s como respaldo del WebSocket.
    q = await asyncio.to_thread(market_data.get_quote, sym)
    if not q:
        raise HTTPException(404, f"No se encontraron datos para '{sym}'")
    _cache.set(f"quote:{sym}", q, ttl=30)  # 30s — precio casi en tiempo real
    return q


# ---------- Chart (candles + indicators) ----------
def _compute_chart_lines(candles):
    """Detecta líneas de tendencia + niveles y mapea los índices de vela a sus fechas
    (para que el frontend las dibuje en el eje temporal). Best-effort: [] si falla."""
    try:
        lines = chart_lines.detect_lines(candles)
        for tl in lines.get("trendlines", []):
            for pt in tl.get("points", []):
                idx = pt.get("index")
                if idx is not None and 0 <= idx < len(candles):
                    pt["date"] = candles[idx].get("date")
        return lines
    except Exception:
        return {"trendlines": [], "levels": []}


@api_router.get("/chart/{symbol}")
async def get_chart(symbol: str, timeframe: str = "1Y", _user: str = Depends(auth.get_current_user)):
    sym = symbol.upper()
    cached = _cache.get(f"chart:{sym}:{timeframe}")
    if cached:
        return cached
    df = await asyncio.to_thread(market_data.get_stock_data, sym, timeframe=timeframe)
    if df is None or df.empty:
        raise HTTPException(404, f"No hay datos históricos para '{sym}'")
    candles = market_data.df_to_candles(df)
    result = {"symbol": sym, "timeframe": timeframe, "candles": candles,
              "lines": _compute_chart_lines(candles)}
    _cache.set(f"chart:{sym}:{timeframe}", result, ttl=300)  # 5 min
    return result


@api_router.get("/debug/patterns")
async def debug_patterns(symbols: str = "", timeframes: str = "1D,4H,1W",
                         _user: str = Depends(auth.get_current_user)):
    """DIAGNÓSTICO: escanea varias acciones × temporalidades y devuelve, por cada una, el
    patrón detectado + chequeos de dibujo (coordenadas fuera de rango, nº de líneas/marcadores).
    Para validar la detección sobre datos reales sin capturas. Ej:
    /api/debug/patterns?symbols=AAPL,NVDA,META&timeframes=1D,4H

    Requiere auth: cada símbolo × temporalidad descarga histórico y corre la detección, así
    que sin credencial era un amplificador de CPU y de cuota de datos para cualquiera."""
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        syms = ["AAPL", "NVDA", "MSFT", "META", "AMZN", "GOOGL", "AVGO", "PLTR",
                "TSLA", "AMD", "NFLX", "SPY", "QQQ", "HOOD", "SOFI", "COIN"]
    tfs = [t.strip() for t in timeframes.split(",") if t.strip()]
    # Techo duro al trabajo que puede pedir una sola llamada (16 × 3 = 48 escaneos).
    syms, tfs = syms[:16], tfs[:3]
    out = []
    for sym in syms:
        for tf in tfs:
            row = {"symbol": sym, "tf": tf}
            try:
                df = await asyncio.to_thread(market_data.get_stock_data, sym, tf)
                if df is None or df.empty:
                    row["error"] = "sin datos"
                    out.append(row)
                    continue
                candles = market_data.df_to_candles(df)
                lines = _compute_chart_lines(candles)
                n = len(candles)
                pat = lines.get("pattern") or {}
                pd = lines.get("pattern_draw") or {}
                px = candles[-1].get("close")
                lo = min(c.get("low", px) for c in candles)
                hi = max(c.get("high", px) for c in candles)
                bad = []
                for ln in pd.get("lines", []):
                    for q in ln.get("points", []):
                        idx, pr = q.get("index"), q.get("price")
                        if idx is None or not (0 <= idx < n):
                            bad.append("linea_idx:%s" % idx)
                        elif pr is not None and not (lo * 0.5 <= pr <= hi * 1.5):
                            bad.append("linea_precio:%s=%s" % (ln.get("tipo"), pr))
                for m in pd.get("markers", []):
                    if not (0 <= m.get("index", -1) < n):
                        bad.append("marker_idx:%s" % m.get("index"))
                row.update({
                    "n": n, "precio": round(px, 2) if px else None,
                    "patron": pat.get("nombre"), "sentido": pat.get("sentido"),
                    "confirmado": pat.get("confirmado"),
                    "vela": (lines.get("candlestick") or {}).get("nombre"),
                    "dibujo": {"lineas": len(pd.get("lines", [])), "markers": len(pd.get("markers", [])),
                               "problemas": bad[:5]},
                })
            except Exception as e:
                row["error"] = str(e)[:120]
            out.append(row)
    return {"total": len(out), "resultados": out}


@api_router.get("/debug/memory")
async def debug_memory(top: int = 25, _user: str = Depends(auth.get_current_user)):
    """DIAGNÓSTICO DE MEMORIA: dónde se está yendo la RAM del proceso.

    Requiere auth: con MEM_TRACE=1 devuelve trazas de tracemalloc, es decir rutas absolutas
    y líneas del código fuente del servidor. Eso es información interna, no vale exponerla.
    - rss_mb: memoria real que usa el proceso (lo que Render mide contra el límite de 512MB).
    - objetos: recuento de objetos vivos por tipo (top N). Un tipo que crece sin parar entre
      llamadas = el sospechoso del leak (p.ej. DataFrame, dict, list acumulándose).
    - caches: tamaño de las cachés en memoria conocidas.
    - tracemalloc: si está activo (env MEM_TRACE=1), las líneas de código que más han
      asignado memoria — el diagnóstico más preciso.
    Uso: llama 2-3 veces separadas en el tiempo y compara qué recuentos suben."""
    import gc
    import sys

    # 1) RSS del proceso desde /proc (Linux/Render), sin depender de psutil.
    rss_mb = None
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_mb = round(int(line.split()[1]) / 1024, 1)  # kB -> MB
                    break
    except Exception:
        pass

    # 2) Recuento de objetos vivos por tipo (top N). El mejor indicador de acumulación.
    gc.collect()
    counts = {}
    for obj in gc.get_objects():
        t = type(obj).__name__
        counts[t] = counts.get(t, 0) + 1
    top_types = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top]

    # 3) Tamaño de las cachés en memoria conocidas.
    caches = {}
    try:
        caches["server._cache (TTL)"] = len(_cache._store)
    except Exception:
        pass
    try:
        import market_data as _md
        caches["market_data._history_cache"] = len(getattr(_md, "_history_cache", {}))
        caches["market_data._info_cache"] = len(getattr(_md, "_info_cache", {}))
        caches["market_data._fh_quote_cache"] = len(getattr(_md, "_fh_quote_cache", {}))
    except Exception:
        pass
    try:
        import opportunities as _op
        sc = (_op._screener_cache.get("data") or {}).get("results") or []
        caches["opportunities._screener_cache (results)"] = len(sc)
    except Exception:
        pass

    # 4) tracemalloc (solo si se arrancó con MEM_TRACE=1): top asignaciones por línea.
    trace = None
    try:
        import tracemalloc
        if tracemalloc.is_tracing():
            snap = tracemalloc.take_snapshot()
            stats = snap.statistics("lineno")[:15]
            trace = [
                {"donde": f"{st.traceback[0].filename.split('/')[-1]}:{st.traceback[0].lineno}",
                 "mb": round(st.size / 1024 / 1024, 2), "bloques": st.count}
                for st in stats
            ]
        else:
            trace = "inactivo (arranca el backend con MEM_TRACE=1 para el detalle por línea)"
    except Exception as e:
        trace = f"error: {str(e)[:100]}"

    return {
        "rss_mb": rss_mb,
        "limite_mb": 512,
        "objetos_totales": len(gc.get_objects()),
        "objetos_por_tipo_top": [{"tipo": t, "n": n} for t, n in top_types],
        "caches": caches,
        "tracemalloc": trace,
    }


@api_router.get("/chartist/{symbol}")
async def chartist_verdict(symbol: str, refresh: bool = False, cached_only: bool = False,
                           _user: str = Depends(auth.get_current_user)):
    """Veredicto del Chartista IA: análisis multi-timeframe (geometría real + Gemini +
    cerebro) con plan accionable y explicación pedagógica. Cacheado 30 min.
    cached_only=true: devuelve el veredicto SOLO si ya está pre-calculado (no consume IA);
    si no lo está, responde {"cached": false}. Lo usa el panel para mostrar al instante los
    análisis que el pre-cálculo de la watchlist ya dejó listos."""
    sym = symbol.upper()
    key = f"chartist:{sym}"
    precomputado = False
    result = None
    if not refresh:
        cached = _cache.get(key)
        if cached:
            result = cached
            precomputado = True
    if result is None and cached_only:
        # Sin veredicto guardado no hay nada que vetar, y resolver la tendencia aqui
        # gastaria una lectura de historico por cada accion que el pre-calculo aun no ha
        # tocado - que es justo el caso mas frecuente de esta rama.
        return {"cached": False}
    if result is None:
        try:
            result = await chartist.analyze(sym)
        except RuntimeError as e:
            raise HTTPException(422, str(e))
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            # Límite de la API de Gemini (plan gratis): mensaje limpio en vez del JSON crudo.
            if "429" in msg or "resource_exhausted" in low or "quota" in low or "rate limit" in low:
                raise HTTPException(429, "Límite de la API de Gemini alcanzado (plan gratis: 20 análisis/día). "
                                         "Espera un momento y reintenta, o activa el plan de pago de Gemini para subir el tope.")
            # Errores de config/clave frecuentes -> mensaje útil.
            if "api key" in low or "api_key" in low or "permission" in low or "invalid" in low or "no configurada" in low:
                raise HTTPException(500, "Problema con la API key de Gemini: " + msg[:200])
            if "billing" in low or "consumer" in low or "disabled" in low or "suspend" in low:
                raise HTTPException(500, "La cuenta de Gemini de pago tiene un problema de facturación: " + msg[:200])
            raise HTTPException(500, "El Chartista IA no pudo generar el análisis (" + msg[:180] + ")")
        # Se guarda LO QUE DIJO EL MODELO, sin tocar. El veto viene despues y sobre una
        # copia: la cache tiene que conservar el veredicto generativo integro para que un
        # cambio de tendencia se refleje en la siguiente lectura sin regenerar nada.
        _cache.set(key, result, ttl=1800)  # 30 min

    # -- El veto, aqui y no antes -------------------------------------------
    # Se resuelve la tendencia AHORA, no cuando se genero el veredicto: entre una cosa y
    # otra pueden pasar hasta 4 horas (el pre-calculo guarda con CHARTIST_TTL) y la
    # direccion de la accion se recalcula cada 15 minutos.
    #
    # La autoridad es la de siempre: `market_data.tendencia_de` lee el historico diario ya
    # cacheado y `estado_accion` traduce. Aqui no se compara ningun precio contra ninguna
    # media - reimplementarlo seria la tercera copia de una regla que tiene dueno.
    estado_t = await asyncio.to_thread(market_data.tendencia_de, sym)
    est = estado_accion.evaluar(estado_t)
    salida = veto_compra.degradar_chartista(result, est["estado"], est["motivo"])
    if cached_only and precomputado:
        salida = {**salida, "_precomputed": True}
    return salida


@api_router.get("/indicators/{symbol}")
async def get_indicators(symbol: str, _user: str = Depends(auth.get_current_user)):
    sym = symbol.upper()
    cached = _cache.get(f"indicators:{sym}")
    if cached:
        return cached
    loop = asyncio.get_running_loop()
    df = await loop.run_in_executor(None, market_data.get_full_indicator_history, sym)
    if df is None or df.empty:
        raise HTTPException(404, f"No hay datos para indicadores: '{sym}'")
    # compute_all es pandas pesado (RSI/MACD/Bollinger/SR sobre 2 años): fuera del loop.
    result = await loop.run_in_executor(None, ind.compute_all, df)
    _cache.set(f"indicators:{sym}", result, ttl=300)  # 5 min
    return result


# ---------- News ----------
@api_router.get("/news/{symbol}")
async def get_news(symbol: str, _user: str = Depends(auth.get_current_user)):
    sym = symbol.upper()
    cached = _cache.get(f"news:{sym}")
    if cached:
        return cached
    result = {"symbol": sym, "items": await asyncio.to_thread(market_data.get_news, sym)}
    _cache.set(f"news:{sym}", result, ttl=1800)  # 30 min — noticias no cambian tan rápido
    return result


def _enrich_quote_fundamentals(quote: dict, symbol: str) -> dict:
    """Fill missing fundamentals (P/E, EPS, beta, 52w, dividend yield) and add growth
    metrics (revenue/EPS YoY) from Finnhub. yfinance never provides the growth fields,
    so this effectively always runs — but it's cached 1h per symbol."""
    if not quote:
        return quote
    fields = ("pe_ratio", "eps", "beta", "high_52w", "low_52w", "dividend_yield",
              "revenue_growth", "eps_growth")
    if not any(quote.get(k) is None for k in fields):
        return quote
    cache_key = f"fin_metrics:{symbol}"
    metrics = _cache.get(cache_key)
    if metrics is None:
        metrics = external_data.finnhub_basic_financials(symbol) or {}
        _cache.set(cache_key, metrics, ttl=3600)
    for k, v in metrics.items():
        if quote.get(k) is None and v is not None:
            quote[k] = v
    return quote


def _valid_positive_nums(arr):
    out = []
    for x in (arr or []):
        try:
            v = float(x)
            if v > 0:
                out.append(round(v, 2))
        except (TypeError, ValueError):
            continue
    return out


def _ensure_key_levels(result: dict, indicators_data: dict, vp: dict, price) -> dict:
    """Guarantee analysis.key_levels has real support/resistance numbers. Models
    occasionally return empty or non-numeric levels (shown as NaN in the UI); when that
    happens, fill from real data — Volume Profile (POC/VAH/VAL/HVN) + technical pivots."""
    if not isinstance(result, dict) or not price:
        return result
    kl = result.get("key_levels") if isinstance(result.get("key_levels"), dict) else {}
    supports = [s for s in _valid_positive_nums(kl.get("support")) if s < price]
    resistances = [r for r in _valid_positive_nums(kl.get("resistance")) if r > price]

    below, above = set(), set()
    sr = (indicators_data or {}).get("support_resistance") or {}
    for v in _valid_positive_nums(sr.get("supports")):
        below.add(v)
    for v in _valid_positive_nums(sr.get("resistances")):
        above.add(v)
    if isinstance(vp, dict):
        for key in ("poc", "vah", "val"):
            v = vp.get(key)
            if isinstance(v, (int, float)) and v > 0:
                (below if v < price else above).add(round(float(v), 2))
        for h in _valid_positive_nums(vp.get("hvn")):
            (below if h < price else above).add(h)

    for c in sorted([c for c in below if c < price], reverse=True):
        if len(supports) >= 3:
            break
        if c not in supports:
            supports.append(c)
    for c in sorted([c for c in above if c > price]):
        if len(resistances) >= 3:
            break
        if c not in resistances:
            resistances.append(c)

    result["key_levels"] = {
        "support": sorted(set(supports), reverse=True)[:4],
        "resistance": sorted(set(resistances))[:4],
    }
    return result


def _cap_take_profits(result: dict, high_52w) -> dict:
    """Keep take-profits realistic: never more than 15% above the 52-week high. Some
    models ignore the prompt rule and emit absurd Fibonacci-extension targets."""
    if not isinstance(result, dict) or not high_52w:
        return result
    ceiling = round(float(high_52w) * 1.15, 2)
    for tp in (result.get("take_profits") or []):
        if isinstance(tp, dict) and isinstance(tp.get("price"), (int, float)) and tp["price"] > ceiling:
            tp["price"] = ceiling
    for k in ("take_profit_1", "take_profit_2"):
        v = result.get(k)
        if isinstance(v, (int, float)) and v > ceiling:
            result[k] = ceiling
    return result


def _apply_regime_filter(result: dict) -> dict:
    """Filtro de régimen de mercado: las señales de COMPRA fallan más en mercado bajista
    (SPY bajo su SMA200). Cuando el régimen es rojo/amarillo, rebaja la confianza de las
    señales de COMPRA y añade un aviso. No cambia la recomendación (eso lo decides tú),
    solo la calibra a la realidad del mercado. Determinista."""
    if not isinstance(result, dict):
        return result
    if (result.get("recommendation") or "").upper() != "COMPRAR":
        return result
    try:
        regime = market_regime.get_market_regime()
    except Exception:
        return result
    light = regime.get("light")
    conf = result.get("confidence")
    if not isinstance(conf, (int, float)):
        conf = None
    if light == "rojo":
        # Mercado bajista: techo de confianza duro + aviso explícito.
        if conf is not None:
            result["confidence"] = min(conf, 50)
        result["regime_warning"] = (
            "⚠️ Mercado bajista (SPY bajo su SMA200): las compras fallan más aquí. "
            "Confianza recortada; reduce tamaño y sé muy selectivo.")
        result["regime_light"] = "rojo"
    elif light == "amarillo":
        if conf is not None:
            result["confidence"] = min(conf, 70)
        result["regime_warning"] = (
            "Mercado en transición: reduce agresividad y espera confirmación.")
        result["regime_light"] = "amarillo"
    else:
        result["regime_light"] = light
    return result


def _enforce_rr(result: dict, price, atr=None) -> dict:
    """Guardián determinista de niveles de riesgo. Arregla el 'stop pegado a la entrada' de
    forma COHERENTE entre los campos escalares y los arrays que pinta la UI:
      1) Deriva los escalares (entry/stop/tp1) de los arrays si el modelo solo llenó estos
         (antes el guardián se saltaba entero y el análisis salía sin protección).
      2) Distancia mínima del stop (>=1×ATR o 2%); si viene pegado, lo recoloca por ATR,
         nunca más cerca que ese mínimo (antes en baja volatilidad el 'arreglo' se quedaba corto).
      3) Ciñe por R/R, pero la DISTANCIA MÍNIMA SIEMPRE gana (clamp final). Antes el paso R/R
         volvía a pegar el stop a la entrada y reintroducía el stop degenerado.
      4) Recalcula stop_losses[] (AJUSTADO/2×ATR/3×ATR) desde el ATR: así el número cuadra con
         la etiqueta y NADIE (ni TradingLevels ni la barra) pinta un stop degenerado.
    """
    import risk_rules
    if not isinstance(result, dict):
        return result

    def _num(x):
        return x if isinstance(x, (int, float)) else None

    # 1) Derivar escalares desde los arrays si faltan.
    ez = result.get("entry_zone") if isinstance(result.get("entry_zone"), dict) else {}
    ezs = result.get("entry_zones")
    entry = _num(ez.get("min"))
    if entry is None:
        if isinstance(ezs, list) and ezs and isinstance(ezs[0], dict):
            entry = _num(ezs[0].get("min"))
        if entry is None:
            entry = _num(price)
        if entry is not None:
            emax = _num(ez.get("max"))
            if emax is None and isinstance(ezs, list) and ezs and isinstance(ezs[0], dict):
                emax = _num(ezs[0].get("max"))
            result["entry_zone"] = {"min": entry, "max": emax if emax is not None else entry}

    tp1 = _num(result.get("take_profit_1"))
    if tp1 is None:
        tps = result.get("take_profits")
        if isinstance(tps, list) and tps and isinstance(tps[0], dict):
            tp1 = _num(tps[0].get("price"))
            if tp1 is not None:
                result["take_profit_1"] = tp1

    stop = _num(result.get("stop_loss"))
    if stop is None:
        sls0 = result.get("stop_losses")
        if isinstance(sls0, list) and sls0 and isinstance(sls0[0], dict):
            stop = _num(sls0[0].get("price"))

    if entry is None or tp1 is None or stop is None:
        return result  # aún sin datos suficientes para proteger

    try:
        atr = float(atr) if atr else None
    except (TypeError, ValueError):
        atr = None
    if atr is not None and atr <= 0:
        atr = None

    min_dist = max(atr, entry * 0.02) if atr else entry * 0.02  # >=1×ATR o 2%

    # 2) Stop demasiado PEGADO → recolócalo a una distancia sensata (nunca < min_dist).
    if (entry - stop) < min_dist:
        repl_dist = max(1.5 * atr, min_dist) if atr else max(entry * 0.03, min_dist)
        stop = round(entry - repl_dist, 2)
        result["stop_corregido_distancia"] = True

    # 3) R/R: ciñe si quedó demasiado ancho...
    nuevo, ajustado = risk_rules.min_rr_stop(entry, tp1, stop)
    if ajustado:
        stop = nuevo
        result["stop_ajustado_rr"] = True
    # ...pero la DISTANCIA MÍNIMA gana: el stop nunca puede quedar más cerca que min_dist.
    max_stop = round(entry - min_dist, 2)
    if stop > max_stop:
        stop = max_stop
    result["stop_loss"] = stop

    # 4) Recalcular los stop_losses[] MONÓTONOS: ajustado = stop saneado; estándar y amplio
    #    siempre más anchos (nunca más cerca de la entrada que el ajustado). Así ninguno sale
    #    degenerado y el orden ajustado→estándar→amplio se respeta aunque el R/R haya movido
    #    el ajustado.
    sls = result.get("stop_losses")
    if isinstance(sls, list) and sls:
        d0 = entry - stop  # distancia del ajustado (>= min_dist, ya saneada)
        precios = [
            stop,
            round(entry - (max(2.0 * atr, d0 * 1.3) if atr else d0 * 1.3), 2),
            round(entry - (max(3.0 * atr, d0 * 1.7) if atr else d0 * 1.7), 2),
        ]
        for i, sl in enumerate(sls[:3]):
            if isinstance(sl, dict):
                sl["price"] = precios[i]
    return result


# R/R mínimo exigible a TP1. Debe coincidir con el que pide SYSTEM_PROMPT en ai_analysis.py:
# si divergen, la IA narra un ratio que los números no cumplen.
MIN_RR = 2.0

# Profundidad máxima del plan de compra: ninguna zona de entrada puede estar más de un 30%
# por debajo del precio actual. Es el límite que ya pedía SYSTEM_PROMPT para el NIVEL 3
# ("de -15% a -30%") y que el motor no aplicaba. Marca dónde acaba el stop, porque el stop
# va por debajo de la zona más profunda del plan.
#
# PENDIENTE DE VALIDACIÓN, NO REGLA RESPALDADA. Este 30% no lo eligió nadie con datos:
# viene del rango que pedía el prompt. Se queda intacto a propósito —cambiarlo por otro
# número sería inventarlo dos veces— hasta que el experimento sobre el histórico diga
# cuál es la profundidad de retroceso que de verdad aporta.
MAX_PLAN_DEPTH = float(os.environ.get("MAX_PLAN_DEPTH", "0.30"))


def _aplicar_estado_tendencia(payload: dict, precio, indicadores) -> dict:
    """Añade el estado de la acción y OCULTA las zonas de compra si no hay tendencia.

    Es una capa de PRESENTACIÓN, y solo eso. No cambia ni un número: `buy_levels` se ha
    calculado igual que siempre y `key_levels.support` sigue intacto como información
    técnica. Lo que se retira es su INTERPRETACIÓN como oportunidad de compra, que es lo
    que un soporte nunca ha podido autorizar por sí solo.

    Se aplica en los dos sitios que producen zonas —el ensamblado del dashboard y
    /analyze— para que la respuesta no dependa de por dónde se haya entrado.

    POR QUÉ SE OCULTAN AQUÍ Y NO SE DEJAN DE CALCULAR

    Es tentador vaciar `buy_levels` antes y ahorrarse el cálculo. Sería un error en
    /analyze: sin zonas deterministas, `_deterministic_levels` devuelve None, el flujo
    cae al clásico y entonces LOS NÚMEROS LOS INVENTA EL MODELO. Ocultar una zona
    calculada es seguro; no calcularla abre la puerta a una peor.
    """
    est = estado_accion.desde_indicadores(precio, indicadores)
    payload["tendencia"] = est["tendencia"]
    payload["estado"] = est["estado"]
    payload["estado_motivo"] = est["motivo"]
    if not est["zonas_visibles"]:
        payload["buy_levels"] = []
        payload["zonas_ocultas_por_tendencia"] = True
    return payload


async def _puerta_de_tendencia(symbol, datos: dict, forzar) -> None:
    """Corta la escritura de niveles de compra sobre una accion vetada. O deja pasar.

    Es la MISMA autoridad que el resto: `market_data.tendencia_de` lee el historico diario
    ya cacheado y `estado_accion` traduce; quien decide si eso bloquea es
    `veto_compra.hay_veto`. Aqui no se compara ningun estado a mano.

    POR QUE EXISTE, HABIENDO YA UNA GUARDA EN LA PANTALLA

    `ChartistPanel.addToCartera` se para si el veredicto viene vetado, pero es codigo de
    cliente: una peticion directa a la API no pasa por ahi, y tampoco lo haria una
    respuesta servida desde la cache del navegador. Mostrar se protege en la pantalla;
    ESCRIBIR se protege en el servidor.

    QUE NO CORTA

    Nada si no hay niveles de compra en el payload - un alta sin niveles, o una edicion de
    `notes`, no consultan la tendencia y ni siquiera pagan la lectura de historico. Y nunca
    `deseado` ni `venta1..3`: son objetivos de VENTA, y el veto es sobre comprar.
    """
    if forzar or not veto_compra.niveles_de_compra_en(datos):
        return
    estado_t = await asyncio.to_thread(market_data.tendencia_de, symbol)
    est = estado_accion.evaluar(estado_t)
    if not veto_compra.hay_veto(est["estado"]):
        return
    # 409 y no 403: el conflicto es con el estado del recurso, igual que el duplicado que
    # se comprueba justo antes. El motivo sale de `estado_accion`, que es su dueno -
    # redactarlo aqui seria una segunda explicacion de lo mismo.
    #
    # El detalle va ESTRUCTURADO y no como cadena porque ahora hay dos 409 distintos en
    # este endpoint, y el cliente tiene que poder separarlos sin leer prosa. Distinguirlos
    # por texto ya falló: `ChartistPanel` trataba cualquier 409 como duplicado y pintaba el
    # check verde de «En Cartera» sobre un veto — el peor final posible, porque un rechazo
    # se leia como exito. El duplicado conserva su cadena: su contrato no cambia.
    raise HTTPException(409, {"error": "vetado_por_tendencia",
                              "symbol": symbol,
                              "mensaje": est["motivo"]})


def _ocultar_plan_de_entrada(analisis: dict) -> dict:
    """Quita del análisis los campos que invitan a comprar, dejando el resto.

    Solo para /analyze y solo cuando no hay tendencia. Se van la zona de entrada y el
    plan escalonado; se quedan soportes, resistencias y el texto, que siguen siendo
    lectura técnica válida sobre una acción que no se debe comprar todavía.

    Los stops y objetivos se van con ellos: un stop sin entrada no protege nada y en
    pantalla se lee como parte de un plan que ya no existe.
    """
    if not isinstance(analisis, dict):
        return analisis
    for campo in ("entry_zones", "entry_zone", "entry_avg", "plan_nota",
                  "stop_losses", "stop_loss", "take_profits",
                  "take_profit_1", "take_profit_2", "risk_reward_ratio", "rr_bajo"):
        analisis.pop(campo, None)
    return analisis


def _deterministic_levels(quote: dict, indicators: dict, buy_levels, price_target) -> dict:
    """#6 — Calcula el conjunto COMPLETO de niveles de forma DETERMINISTA, con etiquetas que
    CUADRAN con el número (el número ES lo que la etiqueta promete). Mata el desajuste
    'la etiqueta dice Fibonacci 161.8% pero el número es otro'. Se pasan a la IA como
    definitivos (solo los narra) y se sobrescriben al final. Devuelve None si no hay zonas de
    confluencia (entonces se usa el flujo clásico con guardianes).

    - entradas: del motor de confluencia (levels_engine, ordenado por PRECIO de cerca a
      lejos — NO por fuerza: la mas solida puede ser el escalon 3)
    - stops: ATR reales bajo el soporte MÁS PROFUNDO del plan (monótonos), uno para la posición
      completa — así el stop nunca queda por encima de los niveles 2 y 3
    - objetivos: resistencia cercana + extensiones Fibonacci + objetivo de analistas (cap 15% s/ máx 52s)
    """
    ind = indicators or {}
    price = quote.get("price")
    if not price or not isinstance(buy_levels, list) or not buy_levels:
        return None

    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    atr = _f(ind.get("atr"))
    if atr is not None and atr <= 0:
        atr = None
    high_52w = _f(quote.get("high_52w")) or _f(ind.get("high_52w")) or price * 1.3
    low_52w = _f(quote.get("low_52w")) or _f(ind.get("low_52w")) or price * 0.7
    ceiling = round(high_52w * 1.15, 2)

    # ── ENTRADAS: del motor de confluencia (top 3) ──
    # Suelo del PLAN: una zona más profunda que esto no forma parte del plan operativo.
    # Sin este filtro se cogían los 3 primeros niveles de confluencia sin mirar a qué
    # profundidad estaban. En MRVL salían a -3,8%, -13,1% y -46,5%: al meter el tercero en el
    # plan, el stop (que va por debajo de TODAS las entradas) acababa en -58%, que no es un
    # stop, es perder media posición. El propio SYSTEM_PROMPT ya pedía que el NIVEL 3 fuera
    # de -15% a -30%; el motor lo ignoraba.
    # Los soportes profundos NO se pierden: siguen saliendo en key_levels/"Soportes (compra)".
    def _zona(z, n):
        p = _f(z.get("price"))
        if p is None:
            return None
        lo = _f(z.get("zone_low")) or p
        hi = _f(z.get("zone_high")) or p
        motivo = " + ".join((z.get("reasons") or [])[:3]) or (z.get("label") or "confluencia")
        return {"label": z.get("label") or f"NIVEL {n}",
                "min": round(min(lo, hi), 2), "max": round(max(lo, hi), 2),
                "comment": f"Fuerza {z.get('strength')}/100 · {motivo}"}

    # La seleccion vive en levels_engine para que sea UNA sola: la misma que marca
    # `en_plan` en cada zona. Antes este bucle era la unica implementacion y la pantalla
    # no tenia forma de saber que zonas usaba el plan sin replicar el umbral.
    ez = []
    indices, respaldo = levels_engine.indices_del_plan_detallado(
        price, buy_levels, MAX_PLAN_DEPTH)
    for n, i in enumerate(indices, 1):
        zona = _zona(buy_levels[i], n)
        if zona:
            ez.append(zona)
    if not ez:
        # Ninguna zona dentro del suelo: la acción ha subido tanto que no hay soporte cercano.
        # Nos quedamos con la MENOS profunda para seguir dando un plan (y un stop coherente)
        # en vez de caer al flujo clásico, donde los números los inventa la IA.
        primera = next((_zona(z, 1) for z in buy_levels if _f(z.get("price")) is not None), None)
        if not primera:
            return None
        ez = [primera]

    # Si el filtro ha dejado fuera zonas que sí salen en la lista de confluencia de arriba,
    # dilo. Ver "NIVEL 3" en el panel superior y solo dos zonas en el plan, sin explicación,
    # parece un fallo.
    # El total son las zonas CON PRECIO, no `len(ez) + descartadas`. Aquella cuenta solo
    # sumaba las que caen por profundidad e ignoraba las que quedan fuera por el tope de
    # escalones: con FORM a $112.47 decia «3 de las 5» habiendo SEIS, porque el NIVEL 4
    # —a -19,5%, dentro del 30%— no lo contaba nadie.
    #
    # La frase tambien atribuia a la profundidad TODAS las exclusiones. Ahora nombra los
    # dos motivos, que es lo que de verdad pasa.
    #
    # Y hay un tercer motivo, que no es una exclusion sino un RESCATE. Cuando ninguna zona
    # sobrevive al suelo, `indices_del_plan` devuelve igualmente la menos profunda para no
    # dejar el plan sin niveles. La frase de arriba era entonces falsa sobre su propio
    # plan: decia que se dejan fuera las que pasan del 30% mientras la unica que usaba
    # estaba a -35%. Y con UNA sola zona no sobraba ninguna, asi que ni siquiera salia:
    # un plan con el stop a -38% y ningun aviso.
    con_precio = [z for z in buy_levels if _f(z.get("price")) is not None]
    fuera = len(con_precio) - len(ez)
    plan_nota = None
    if respaldo:
        # Sale SIEMPRE, no solo si sobran zonas: aqui lo que hay que contar no es cuantas
        # quedaron fuera, sino que la que se usa tampoco cumple.
        plan_nota = (
            f"Ninguna zona de confluencia queda dentro del umbral del {MAX_PLAN_DEPTH:.0%}. "
            f"Se ha rescatado la zona menos profunda para evitar dejar el plan sin niveles "
            f"y que los números los determine la IA. El stop queda por debajo de esa zona, "
            f"por lo que la distancia de riesgo es elevada."
        )
    elif fuera > 0:
        plan_nota = (
            f"El plan usa {len(ez)} de las {len(con_precio)} zonas de confluencia: se reparte "
            f"en {levels_engine.MAX_ESCALONES} escalones como mucho y deja fuera las que están "
            f"a más de un {MAX_PLAN_DEPTH:.0%} bajo el precio, que arrastrarían el stop hasta "
            f"ahí. Todas siguen listadas como soportes."
        )
    entry_hi = ez[0]["max"]
    entry_lo = ez[0]["min"]
    # Precio medio REALISTA de una compra escalonada (el usuario reparte entre las 3 zonas):
    # es la referencia honesta para el R/R, no el borde alto de la zona 1.
    entry_ref = round(sum((e["min"] + e["max"]) / 2 for e in ez) / len(ez), 2)
    # Zona MÁS PROFUNDA a la que el plan invita a comprar: el stop debe quedar POR DEBAJO de
    # ella. Anclarlo a la zona 1 (como se hacía) dejaba el stop por encima de NIVEL 2 y 3 —
    # el plan se contradecía: "compra en 91" y "sal si pierde 94".
    deepest = min(e["min"] for e in ez)

    # ── STOPS: por debajo de TODAS las entradas del plan, ATR real, monótonos ──
    stops = []
    if atr:
        base_d = max(1.0 * atr, deepest * 0.015)      # colchón bajo el soporte más profundo
        d = [base_d, max(1.6 * atr, base_d * 1.4), max(2.4 * atr, base_d * 1.9)]
        labels = ["STOP AJUSTADO", "STOP ESTÁNDAR", "STOP AMPLIO"]
        # El número de compras se lee del plan: desde que las zonas se filtran por
        # profundidad, el plan puede tener 1, 2 o 3, y decir "las 3 compras" con dos zonas
        # en pantalla es exactamente la etiqueta mentirosa que perseguimos.
        n = len(ez)
        cuantas = "la compra" if n == 1 else f"las {n} compras"
        comments = [
            f"1×ATR bajo el soporte más profundo del plan — el más ceñido que respeta {cuantas}",
            "1,6×ATR bajo el soporte más profundo — invalida la tesis técnica",
            "2,4×ATR bajo el soporte más profundo — solo largo plazo",
        ]
    else:
        d = [deepest * 0.03, deepest * 0.05, deepest * 0.08]
        labels = ["STOP AJUSTADO (~3%)", "STOP ESTÁNDAR (~5%)", "STOP AMPLIO (~8%)"]
        comments = [f"~{p}% bajo el soporte más profundo del plan" for p in (3, 5, 8)]
    for i in range(3):
        stops.append({"label": labels[i], "price": round(deepest - d[i], 2), "comment": comments[i]})
    stop_scalar = stops[0]["price"]

    # ── OBJETIVOS: resistencias + Fibonacci + analistas ──
    sr = ind.get("support_resistance") or {}
    res_up = sorted(r for r in (_f(x) for x in (sr.get("resistances") or [])) if r and r > price * 1.01)
    rng = high_52w - low_52w
    fib127 = round(low_52w + rng * 1.272, 2) if rng > 0 else None
    fib161 = round(low_52w + rng * 1.618, 2) if rng > 0 else None
    analyst = _f((price_target or {}).get("target_mean")) if isinstance(price_target, dict) else None
    # Techo DEFENDIBLE: además del 15% sobre el máximo de 52s, ningún objetivo puede exceder
    # lo que sostengan la resistencia más alta, los analistas o un +50%. En una acción que ha
    # caído un 70%, la extensión Fibonacci del rango 52s daba objetivos de +283% (fantasía).
    ceiling = min(ceiling, max([r for r in res_up] + [analyst or 0] + [price * 1.5]))

    def _cap(x):
        return min(x, ceiling) if x else x

    # TP1 debe dar R/R >= MIN_RR sobre el stop DEFINITIVO y la entrada media realista.
    # 2:1 (no 1,5) porque es el mínimo profesional y porque la matemática lo exige: el umbral
    # de rentabilidad es 1/(1+R), así que 1,5:1 necesita un 40% de aciertos y los swing traders
    # rondan el 40-50% — es decir, 1,5 te deja justo en la línea de no ganar nada antes de
    # comisiones. A 2:1 basta con un 33%.
    risk = entry_ref - stop_scalar
    min_tp1 = entry_ref + MIN_RR * risk if risk > 0 else price * 1.04
    # Cada candidato lleva SU etiqueta pegada desde el origen (antes se asignaban por índice
    # sobre una lista deduplicada, así que al colapsar valores las etiquetas mentían).
    #
    # ORDEN DE PREFERENCIA: primero niveles que el mercado ha dejado DE VERDAD (resistencias
    # donde el precio ya se dio la vuelta, el máximo de 52 semanas, el objetivo de los
    # analistas) y solo al final las extensiones Fibonacci.
    #
    # Antes TP2 ERA la extensión 127,2% y TP3 la 161,8% por definición, sin que nadie hubiera
    # comprobado que el precio llegue ahí. Eso producía objetivos de fantasía (+283% en
    # acciones machacadas, que hubo que tapar con un techo) porque la extensión se calcula
    # sobre el rango de 52 semanas: cuanto más ha caído la acción, más arriba proyecta.
    # Una resistencia, en cambio, es un sitio donde el precio ya se paró: es observable y no
    # depende de dónde empiece a medir cada uno.
    # Fibonacci NO se elimina: queda como relleno cuando no hay suficientes niveles reales
    # (típico en una acción en máximos históricos, donde por encima no hay nada).
    cands = []
    t1 = next((r for r in res_up if r >= min_tp1), None)
    cands.append((t1, f"TP1 — Resistencia con R/R ≥ {MIN_RR:g}") if t1
                 else (round(min_tp1, 2), f"TP1 — Objetivo por R/R ≥ {MIN_RR:g}"))
    # Resistencias reales por encima de TP1, en orden. Se piden hasta 4: con TP1 ya hay de
    # sobra para los tres objetivos sin tocar Fibonacci.
    ancla = t1 or min_tp1
    for r in res_up:
        if r > ancla * 1.02:
            cands.append((r, "TP — Siguiente resistencia"))
            ancla = r
            if len(cands) >= 4:
                break
    # Máximo de 52 semanas: la resistencia más objetiva que existe y la que más se vigila.
    if high_52w and high_52w > price * 1.01:
        cands.append((round(high_52w, 2), "TP — Máximo de 52 semanas"))
    if analyst:
        cands.append((analyst, "TP — Objetivo medio de analistas"))
    # Fibonacci, al final: solo entra si lo anterior no ha dado para tres objetivos.
    if fib127:
        cands.append((fib127, "TP — Extensión Fibonacci 127,2% (sin resistencia arriba)"))
    if fib161:
        cands.append((fib161, "TP — Extensión Fibonacci 161,8% (sin resistencia arriba)"))

    # Se recorre en ORDEN DE PREFERENCIA (no por precio) para que Fibonacci solo entre si
    # falta hueco; luego se ordenan por precio para presentarlos.
    tps, vistos = [], set()
    for val, lab in ((v, l) for v, l in cands if v):
        capped = round(_cap(val), 2)
        if capped <= price or capped in vistos:   # capar ANTES de filtrar por precio
            continue
        # Ningún objetivo por debajo del suelo de R/R. Si no llega al mínimo, tomarlo sería
        # arriesgar más de lo que se gana, que es justo lo que el R/R está ahí para descartar.
        # Sin este filtro, una extensión Fibonacci un poco por debajo del suelo se colaba como
        # TP1 y el plan salía con un R/R de 1,95 pidiendo 2.
        if capped < min_tp1 - 0.01:
            continue
        vistos.add(capped)
        # Si el cap ha mordido el valor, la etiqueta original ya no describe el número.
        lab_final = lab if abs(capped - round(val, 2)) < 0.01 else "TP — Techo realista (máx. 52s / analistas)"
        tps.append({"label": lab_final, "price": capped, "comment": ""})
        if len(tps) >= 3:
            break
    if not tps:
        tps = [{"label": "TP1 — Objetivo técnico", "price": round(price * 1.05, 2), "comment": ""}]
    # Se eligieron por preferencia de método, no por precio: hay que ordenarlos ANTES de
    # renumerar o saldría un TP2 más bajo que el TP1 (el objetivo de analistas o el máximo de
    # 52 semanas pueden quedar por debajo de una resistencia elegida después).
    tps.sort(key=lambda t: t["price"])
    # Renumera TP1/TP2/TP3 respetando la etiqueta de método ya asignada.
    for i, t in enumerate(tps):
        t["label"] = t["label"].replace("TP1 — ", "TP — ", 1)
        t["label"] = f"TP{i + 1} — " + t["label"].split("— ", 1)[-1]
    tp1s = tps[0]["price"]
    tp2s = tps[1]["price"] if len(tps) > 1 else None
    rr = round((tp1s - entry_ref) / risk, 1) if risk > 0 else None
    # Aviso honesto si ni así se alcanza un R/R sano (antes lo garantizaba _enforce_rr, que
    # en esta rama ya no se ejecuta).
    rr_low = bool(rr is not None and rr < MIN_RR)

    # ── key_levels ──
    supports = sorted({e["min"] for e in ez} |
                      {r for r in (_f(x) for x in (sr.get("supports") or [])) if r and r < price}, reverse=True)[:4]
    resistances = sorted(set(res_up) | {t["price"] for t in tps})[:4]

    return {
        "entry_zones": ez,
        "stop_losses": stops,
        "take_profits": tps,
        "entry_zone": {"min": entry_lo, "max": entry_hi},
        "entry_avg": entry_ref,   # precio medio si escalonas TODAS las zonas del plan (base del R/R)
        "plan_nota": plan_nota,   # por qué el plan tiene menos zonas que la lista de confluencia
        "stop_loss": stop_scalar,
        "take_profit_1": tp1s,
        "take_profit_2": tp2s,
        "rr_bajo": rr_low,
        "risk_reward_ratio": rr,
        "key_levels": {"support": supports, "resistance": resistances},
    }


def _validate_analysis(result: dict, price) -> dict:
    """Validación determinista de la salida del LLM (independiente de si se usó el flujo
    determinista o el clásico). Normaliza enums, acota la confianza y descarta números
    incoherentes que el modelo pueda colar (TP por debajo de la entrada, confianza 150, etc.)."""
    if not isinstance(result, dict):
        return result
    # Recomendación y tendencia a enums conocidos.
    # Mapeo por CONTENCIÓN, no por igualdad: los modelos de respaldo (Groq/Llama) devuelven
    # variantes ("COMPRA FUERTE", "ACUMULAR", "BUY", "VENDER PARCIAL") que con un mapa cerrado
    # se degradaban TODAS a MANTENER, matando la señal justo cuando Gemini está saturado.
    rec = (result.get("recommendation") or "").strip().upper()
    if rec:
        if any(k in rec for k in ("COMPR", "BUY", "ACUMUL")):
            result["recommendation"] = "COMPRAR"
        elif any(k in rec for k in ("VEND", "SELL", "REDUC")):
            result["recommendation"] = "VENDER"
        else:
            result["recommendation"] = "MANTENER"
    # Confianza acotada a 0-100.
    conf = result.get("confidence")
    if isinstance(conf, (int, float)):
        result["confidence"] = max(0, min(100, round(conf)))
    # Zona de entrada: min <= max.
    ez = result.get("entry_zone")
    if isinstance(ez, dict) and isinstance(ez.get("min"), (int, float)) and isinstance(ez.get("max"), (int, float)):
        if ez["min"] > ez["max"]:
            ez["min"], ez["max"] = ez["max"], ez["min"]
    entry_ref = ez.get("min") if isinstance(ez, dict) and isinstance(ez.get("min"), (int, float)) else price
    # Take-profits deben estar POR ENCIMA de la entrada (para un largo); descarta los que no.
    if isinstance(entry_ref, (int, float)) and isinstance(result.get("take_profits"), list):
        result["take_profits"] = [t for t in result["take_profits"]
                                  if isinstance(t, dict) and isinstance(t.get("price"), (int, float)) and t["price"] > entry_ref]
    for k in ("take_profit_1", "take_profit_2"):
        v = result.get(k)
        if isinstance(v, (int, float)) and isinstance(entry_ref, (int, float)) and v <= entry_ref:
            result[k] = None
    # R/R: número positivo o nada.
    rr = result.get("risk_reward_ratio")
    if not (isinstance(rr, (int, float)) and rr > 0):
        result.pop("risk_reward_ratio", None) if rr is not None else None
    return result


# ---------- AI Analysis ----------
@api_router.post("/analyze")
async def analyze(req: AnalyzeRequest, _user: str = Depends(auth.get_current_user)):
    symbol = req.symbol.upper()
    loop = asyncio.get_running_loop()

    # quote y df son operaciones bloqueantes e independientes: las sacamos del event
    # loop y las corremos en paralelo (antes bloqueaban ~3-5s con 1 solo worker).
    quote, df, df_spy = await asyncio.gather(
        loop.run_in_executor(None, market_data.get_quote, symbol),
        loop.run_in_executor(None, market_data.get_full_indicator_history, symbol),
        # SPY para la Fuerza Relativa. Cacheado (lo comparte con el semáforo de mercado),
        # y va en el gather para no añadir latencia cuando toque descargarlo.
        loop.run_in_executor(None, market_data.get_full_indicator_history, "SPY"),
        return_exceptions=True,
    )
    if isinstance(quote, Exception):
        quote = None
    if isinstance(df, Exception):
        df = None
    if isinstance(df_spy, Exception):
        df_spy = None
    if not quote:
        raise HTTPException(404, f"Símbolo no encontrado: {symbol}")
    if df is None or df.empty:
        raise HTTPException(404, f"Sin datos suficientes para analizar {symbol}")

    indicators_data = await loop.run_in_executor(None, ind.compute_all, df)

    # Enrich with analyst consensus + Volume Profile + insider/earnings/financials + news (all in parallel)
    trends, price_target, vp, insider, earnings_hist, basic_fin, news, earnings_cal = await asyncio.gather(
        loop.run_in_executor(None, external_data.finnhub_recommendation_trends, symbol),
        loop.run_in_executor(None, external_data.finnhub_price_target, symbol),
        loop.run_in_executor(None, _cached_vp, symbol, 365),
        loop.run_in_executor(None, external_data.finnhub_insider_transactions, symbol),
        loop.run_in_executor(None, external_data.finnhub_earnings_surprises, symbol),
        loop.run_in_executor(None, external_data.finnhub_basic_financials, symbol),
        loop.run_in_executor(None, market_data.get_news, symbol, 5),
        loop.run_in_executor(None, lambda: external_data.finnhub_earnings_calendar(90, [symbol])),
        return_exceptions=True,
    )
    news = news if isinstance(news, list) else []
    trends = trends if isinstance(trends, list) else []
    price_target = price_target if isinstance(price_target, dict) else {}
    vp = vp if isinstance(vp, dict) else {}
    insider = insider if isinstance(insider, dict) else None
    earnings_hist = earnings_hist if isinstance(earnings_hist, dict) else None
    basic_fin = basic_fin if isinstance(basic_fin, dict) else {}

    # Próxima fecha de resultados → riesgo binario si está cerca (los pros evitan
    # abrir posición justo antes de earnings: la acción puede saltar ±10% de golpe).
    next_earnings_date, days_to_earnings = None, None
    if isinstance(earnings_cal, dict):
        _today = datetime.now(timezone.utc).date()
        for _it in (earnings_cal.get("items") or []):
            _d = _it.get("date")
            if not _d:
                continue
            try:
                _ed = datetime.strptime(_d, "%Y-%m-%d").date()
            except Exception:
                continue
            if _ed >= _today:
                next_earnings_date = _d
                days_to_earnings = (_ed - _today).days
                break  # items vienen ordenados por fecha ascendente
    # Fill missing quote fundamentals + add growth metrics (revenue/EPS YoY) from Finnhub
    for k, v in basic_fin.items():
        if quote.get(k) is None and v is not None:
            quote[k] = v
    analyst_consensus = external_data.aggregate_recommendation(trends)

    # Motor de confluencia: calcula deterministamente las zonas de compra
    # (Volume Profile + Fibonacci del swing + pivotes + medias + nº redondos)
    # rankeadas por fuerza, para anclar los niveles de la IA a estructura real.
    buy_levels = []
    try:
        _ind = indicators_data or {}
        buy_levels = levels_engine.compute_buy_levels(
            df, vp, quote.get("price"), _ind.get("sma"),
            atr_val=_ind.get("atr"),
            regime=_ind.get("regime"),
            vwap_anchored=_ind.get("vwap_anchored"),
        )
    except Exception:
        logger.exception("compute_buy_levels failed")

    # Se marca tambien aqui: el frontend sustituye `buyLevels` por los de esta respuesta al
    # pulsar «Ampliar con IA», y sin `en_plan` el panel perderia la agrupacion en ese momento.
    levels_engine.marcar_en_plan(buy_levels, quote.get("price"), MAX_PLAN_DEPTH)

    # Perfil de empresa (FMP): descripción del negocio/productos para el "qué hace".
    company_profile = None
    try:
        company_profile = await asyncio.to_thread(external_data.fmp_company_profile, symbol)
    except Exception:
        company_profile = None

    # #6 — NIVELES DETERMINISTAS: calculamos TODO (entradas/stops/objetivos/key_levels) con
    # etiquetas que cuadran con el número. Se pasan a la IA como definitivos (solo los narra)
    # y se sobrescriben al final → la prosa nunca contradice a los números. None si no hay
    # confluencia (entonces se usa el flujo clásico con guardianes).
    det_levels = _deterministic_levels(quote, indicators_data, buy_levels, price_target)

    requested_model = req.model or ai_analysis.DEFAULT_MODEL
    analyze_kwargs = dict(
        analyst_consensus=analyst_consensus,
        price_target=price_target,
        volume_profile=vp,
        insider=insider,
        earnings_history=earnings_hist,
        buy_levels=buy_levels,
        next_earnings_date=next_earnings_date,
        days_to_earnings=days_to_earnings,
        company_profile=company_profile,
        final_levels=det_levels,
        relative_strength=(
            await loop.run_in_executor(None, ind.relative_strength, df, df_spy)
            if df_spy is not None else None
        ),
    )
    used_model = requested_model
    # Cadena de fallback en orden de preferencia, ENTRE PROVEEDORES distintos: si Gemini
    # da un 503/limite transitorio, probamos con Groq (otro proveedor) en vez de reintentar
    # el mismo Gemini. Antes el fallback era el propio gemini-2.5-flash, así que cuando el
    # modelo por defecto (Gemini) fallaba, la condición "distinto" era falsa y NO había
    # fallback real → el 503 llegaba directo al usuario.
    FALLBACK_CHAIN = ["gemini-2.5-flash", "gpt-oss-120b", "llama-3.3-70b"]
    candidates = [requested_model] + [m for m in FALLBACK_CHAIN if m != requested_model]
    result = None
    last_err = None
    for cand in candidates:
        try:
            result = await ai_analysis.analyze_stock(
                quote, indicators_data, news, model_key=cand, **analyze_kwargs
            )
            used_model = cand
            if cand != requested_model:
                logger.warning(f"Model '{requested_model}' failed; served with fallback '{cand}'")
            break
        except Exception as e:
            last_err = e
            logger.warning(f"Model '{cand}' failed ({e}); trying next fallback")
    if result is None:
        logger.exception("AI analysis failed (all models in fallback chain)")
        raise HTTPException(503, f"Los modelos de IA están saturados ahora mismo. Inténtalo en unos minutos. ({last_err})")

    if det_levels and isinstance(result, dict):
        # FLUJO DETERMINISTA: sobrescribimos los campos numéricos con los del motor (la IA solo
        # narra). No hace falta pasar por los guardianes de números: ya son coherentes.
        for k, v in det_levels.items():
            result[k] = v
    else:
        # FLUJO CLÁSICO (sin confluencia): la IA produjo los números → guardianes deterministas.
        if buy_levels and isinstance(result, dict):
            kl = result.get("key_levels") if isinstance(result.get("key_levels"), dict) else {}
            existing = kl.get("support") if isinstance(kl.get("support"), list) else []
            kl["support"] = [z["price"] for z in buy_levels] + list(existing)
            result["key_levels"] = kl
        result = _ensure_key_levels(result, indicators_data, vp, quote.get("price"))
        result = _cap_take_profits(result, quote.get("high_52w"))
        result = _enforce_rr(result, quote.get("price"), atr=(indicators_data or {}).get("atr"))
    # Normalizar ANTES de filtrar por régimen: _apply_regime_filter solo actúa si la
    # recomendación es literalmente "COMPRAR", así que un "BUY" del modelo de respaldo se
    # colaba sin recorte de confianza en mercado bajista.
    result = _validate_analysis(result, quote.get("price"))
    result = _apply_regime_filter(result)

    # #7 — Si los datos son de una fuente de respaldo o con retraso, avisa en el análisis y
    # recorta la confianza (el análisis se calculó sobre datos degradados; que se sepa).
    try:
        health = market_data.data_health(df)
        if isinstance(result, dict) and health and health.get("degraded"):
            result["data_warning"] = "⚠️ Datos de respaldo/con retraso (" + (health.get("note") or "fuente degradada") + "). Trátalo con cautela."
            c = result.get("confidence")
            if isinstance(c, (int, float)):
                result["confidence"] = min(c, 60)
    except Exception:
        pass

    # Persist
    doc = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "model": used_model,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "quote_snapshot": quote,
        "indicators_snapshot": indicators_data,
        "result": result,
    }
    await db.analyses.insert_one(doc)

    # Mismo estado y mismas reglas de visibilidad que en el dashboard. Se aplica DESPUÉS
    # de que `_deterministic_levels` haya hecho su trabajo: así los números que se ocultan
    # son los del motor y no los que habría inventado el modelo si le hubiéramos quitado
    # las zonas de debajo antes de llamarlo.
    respuesta = {"buy_levels": buy_levels or []}
    _aplicar_estado_tendencia(respuesta, quote.get("price"), indicators_data)
    if respuesta.get("zonas_ocultas_por_tendencia"):
        _ocultar_plan_de_entrada(result)
    # Y el veredicto, no solo sus numeros. Quitar la zona de entrada dejaba en pantalla la
    # pildora verde "COMPRAR" junto al panel rojo que dice que la accion no se compra: dos
    # respuestas incompatibles a la misma pregunta, y la del modelo era la que se leia
    # primero. La IA recomienda; autorizar es de la estructura.
    #
    # Va DESPUES del `insert_one` de arriba a proposito: en Mongo queda lo que dijo el
    # modelo, integro. Lo que se degrada es lo que se ensena, no lo que se midio.
    result = veto_compra.degradar_analisis(result, respuesta.get("estado"))

    return {
        "symbol": symbol,
        "model": used_model,
        "requested_model": requested_model,
        "fellback": used_model != requested_model,
        # Tier de Gemini que sirvió el análisis (free/paid) para el badge de la UI.
        "ai_tier": (result.get("_ai_tier") if isinstance(result, dict) else None),
        "quote": quote,
        "indicators": indicators_data,
        "analysis": result,
        "news": news,
        "analyst_consensus": analyst_consensus,
        "price_target": price_target,
        "insider": insider,
        "earnings_history": earnings_hist,
        "volume_profile": vp or None,
        # Del `respuesta` de arriba, no de `buy_levels` a pelo: ahí es donde se ha
        # decidido si las zonas se pueden enseñar. Leerlo dos veces de sitios distintos
        # es como se acaba enviando una lista de zonas junto a un NO_COMPRAR.
        "buy_levels": respuesta["buy_levels"],
        "tendencia": respuesta["tendencia"],
        "estado": respuesta["estado"],
        "estado_motivo": respuesta["estado_motivo"],
        "zonas_ocultas_por_tendencia": respuesta.get("zonas_ocultas_por_tendencia", False),
    }


# ---------- "¿Por qué se mueve hoy?" ----------
@api_router.get("/why-moving/{symbol}")
async def why_moving(symbol: str, model: Optional[str] = None,
                     _user: str = Depends(auth.get_current_user)):
    """Explicación breve y barata de por qué la acción se mueve hoy: conecta el
    cambio del día con los titulares recientes mediante IA. Cacheado 10 min."""
    sym = symbol.upper()
    model_key = model or ai_analysis.DEFAULT_MODEL
    cache_key = f"why_moving:{sym}:{model_key}"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_running_loop()
    quote, news = await asyncio.gather(
        loop.run_in_executor(None, market_data.get_quote, sym),
        loop.run_in_executor(None, market_data.get_news, sym, 8),
        return_exceptions=True,
    )
    if not isinstance(quote, dict) or not quote:
        raise HTTPException(404, f"Símbolo no encontrado: {sym}")
    news = news if isinstance(news, list) else []
    quote = _enrich_quote_fundamentals(quote, sym)

    FALLBACK_MODEL = "gpt-oss-120b"
    used_model = model_key
    try:
        explanation = await ai_analysis.explain_daily_move(quote, news, model_key=model_key)
    except Exception as e:
        if model_key != FALLBACK_MODEL:
            logger.warning(f"why-moving model '{model_key}' failed ({e}); fallback {FALLBACK_MODEL}")
            try:
                explanation = await ai_analysis.explain_daily_move(quote, news, model_key=FALLBACK_MODEL)
                used_model = FALLBACK_MODEL
            except Exception as e2:
                logger.exception("why-moving failed (including fallback)")
                raise HTTPException(500, f"Error al explicar el movimiento: {e2}")
        else:
            logger.exception("why-moving failed")
            raise HTTPException(500, f"Error al explicar el movimiento: {e}")

    result = {
        "symbol": sym,
        "model": used_model,
        "fellback": used_model != model_key,
        "change_percent": quote.get("change_percent"),
        "price": quote.get("price"),
        "explanation": explanation,
        "news": news[:5],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _cache.set(cache_key, result, ttl=600)  # 10 min — las noticias no cambian tan rápido
    return result


# ---------- Compare ----------
@api_router.post("/compare")
async def compare_stocks(req: CompareRequest, _user: str = Depends(auth.get_current_user)):
    """Compare up to 6 stocks side by side: quote + key indicators + 3-month candles
    for the normalized performance chart."""
    syms = []
    for s in (req.symbols or []):
        s = (s or "").strip().upper()
        if s and s not in syms:
            syms.append(s)
    syms = syms[:6]
    if not syms:
        return {"items": []}

    loop = asyncio.get_running_loop()

    async def _one(sym):
        try:
            quote = await loop.run_in_executor(None, market_data.get_quote, sym)
            if not quote:
                return {"symbol": sym, "error": "No encontrado"}
            dfi = await loop.run_in_executor(None, market_data.get_full_indicator_history, sym)
            candles, indicators_data = [], None
            if dfi is not None and not dfi.empty:
                try:
                    indicators_data = await loop.run_in_executor(None, ind.compute_all, dfi)
                    candles = market_data.df_to_candles(dfi.tail(63))  # ~3 months
                except Exception:
                    pass
            return {"symbol": sym, "quote": quote, "indicators": indicators_data, "candles": candles}
        except Exception as e:
            return {"symbol": sym, "error": str(e)[:120]}

    items = await asyncio.gather(*[_one(s) for s in syms])
    return {"items": list(items)}


# ---------- Combined Dashboard ----------
# Cuánto puede servirse una respuesta caducada mientras se recalcula por detrás.
_DASHBOARD_STALE_MAX = int(os.environ.get("DASHBOARD_STALE_MAX", 1800))  # 30 min
_refrescos_en_curso: set = set()


def _refrescar_dashboard_en_segundo_plano(sym: str, timeframe: str, cache_key: str):
    """Recalcula un dashboard caducado sin hacer esperar a quien lo pidió.

    El candado evita la estampida: si el usuario cambia de ticker y vuelve, o si hay varias
    pestañas abiertas, no se lanzan N recálculos simultáneos del mismo símbolo.
    """
    if cache_key in _refrescos_en_curso:
        return
    _refrescos_en_curso.add(cache_key)

    async def _run():
        try:
            await _construir_dashboard(sym, timeframe, cache_key)
        except Exception as e:
            logger.warning("refresco de fondo de %s falló: %s", sym, str(e)[:120])
        finally:
            _refrescos_en_curso.discard(cache_key)

    asyncio.create_task(_run())


@api_router.get("/dashboard/{symbol}")
async def dashboard_data(symbol: str, timeframe: str = "1Y",
                         _user: str = Depends(auth.get_current_user)):
    """Endpoint combinado: devuelve quote + chart + indicators + news + analyst en una sola llamada.
    Todas las peticiones a Yahoo Finance / Finnhub se lanzan en paralelo via thread pool."""
    sym = symbol.upper()
    cache_key = f"dashboard:{sym}:{timeframe}"

    # Servir-caducado-y-refrescar: si hay una respuesta previa de menos de 30 min, se
    # devuelve AL INSTANTE aunque haya pasado su TTL de 5 min, y se recalcula por detrás.
    # Antes, cada 5 min el siguiente que abriera ese ticker pagaba la carga completa
    # (7 fuentes externas); ahora solo la paga quien lo abre por primera vez.
    cached, fresco = _cache.get_stale(cache_key, max_age=_DASHBOARD_STALE_MAX)
    if cached is not None:
        if not fresco:
            # Lo pesado (histórico, indicadores, volume profile) se sirve caducado sin
            # problema: son velas DIARIAS, media hora no las cambia. La COTIZACIÓN sí, y es
            # lo primero que se mira, así que se refresca aquí mismo. Es barato (una llamada,
            # cacheada 60s) y va acotado para no perder la ganancia de velocidad.
            cached = await _refrescar_cotizacion(cached, sym)
            _refrescar_dashboard_en_segundo_plano(sym, timeframe, cache_key)
        return cached
    return await _construir_dashboard(sym, timeframe, cache_key)


async def _refrescar_cotizacion(payload: dict, sym: str) -> dict:
    """Devuelve una copia del payload con la cotización al día. Si no llega a tiempo,
    devuelve el payload tal cual: mejor un precio de hace un rato que una página en blanco
    (y el WebSocket lo corrige en segundos de todas formas)."""
    try:
        quote = await asyncio.wait_for(asyncio.to_thread(market_data.get_quote, sym),
                                       timeout=2.0)
    except Exception:   # incluye el TimeoutError de wait_for
        return payload
    if not quote:
        return payload
    nuevo = dict(payload)
    anterior = nuevo.get("quote") or {}
    # Fusionar sin pisar con nulos: get_quote a veces vuelve sin fundamentales (PER, beta...)
    # y no queremos borrar los que ya teníamos.
    fusion = dict(anterior)
    for k, v in quote.items():
        if v is not None:
            fusion[k] = v
    nuevo["quote"] = fusion

    # La tesis lleva el precio DENTRO de la frase, asi que refrescar la cotizacion y dejarla
    # como estaba producia dos precios distintos de la misma accion en la misma pantalla: la
    # cabecera al dia y «AMD cotiza a 468.34» debajo. Se reescribe sobre el payload ya
    # fusionado. Es gratis: `redactar` es una funcion pura sobre datos en memoria.
    try:
        nuevo["tesis"] = tesis.redactar(nuevo)
    except Exception:
        logger.exception("refresco de cotizacion: la redaccion de la tesis fallo")
        # Se conserva la anterior: una tesis con el precio de hace un rato es peor que una
        # al dia, pero mucho mejor que ninguna.
    return nuevo


async def _sin_estallar(coro):
    """Ejecuta una corrutina y devuelve None si falla, en vez de propagar.

    Se usa para las tareas que se lanzan por adelantado: si una falla y su resultado acaba
    no recogiéndose —porque otra rama corta antes—, asyncio suelta un "Task exception was
    never retrieved" en los logs por algo que ya estaba contemplado.
    """
    try:
        return await coro
    except Exception:
        return None


async def _extended_quote_cacheada(sym: str):
    """Precio de pre-apertura / after-hours, cacheado 60 s. Extraído para poder lanzarlo en
    paralelo con el resto de la segunda tanda: abre red (yfinance) y no depende de nada."""
    ext = _cache.get(f"ext:{sym}")
    if ext is None:
        ext = await asyncio.to_thread(market_data.get_extended_quote, sym)
        _cache.set(f"ext:{sym}", ext or {}, ttl=60)
    return ext


async def _construir_dashboard(sym: str, timeframe: str, cache_key: str):
    """El cálculo real. Separado del endpoint para que el refresco de fondo pueda
    invocarlo sin pasar por la caché ni por la comprobación de credencial, y sin exponer
    un parámetro extra como query param público."""
    loop = asyncio.get_running_loop()

    # Instrumentación: medimos cuánto tarda cada fuente para diagnosticar lentitud en Render.
    _t_total = _time.time()

    # Tope de 8s por fuente: la página carga siempre en <8s aunque alguna fuente externa
    # esté lenta (Finnhub bloqueado, Yahoo caído). Los datos ausentes aparecen None y
    # quedan en caché la próxima vez que el usuario cargue el mismo ticker.
    _SRC_TIMEOUT = 8.0

    async def _timed(name, fn, *args):
        t0 = _time.time()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, fn, *args),
                timeout=_SRC_TIMEOUT,
            )
        except asyncio.TimeoutError:
            dt = _time.time() - t0
            logger.warning("dashboard[%s] %s TIMEOUT %.1fs", sym, name, dt)
            return None
        except Exception as exc:
            return exc
        finally:
            dt = _time.time() - t0
            if dt > 5.0:
                logger.warning("dashboard[%s] %s LENTO: %.1fs", sym, name, dt)

    # 6 llamadas bloqueantes en paralelo (thread pool).
    # trends y price_target se cachean 4h — los datos de analistas cambian pocas veces al día
    # y son los más lentos al tener que pasar por el rate limiter de Finnhub.
    def _cached_trends(s):
        ck = f"trends:{s}"
        v = _cache.get(ck)
        if v is not None:
            return v
        v = external_data.finnhub_recommendation_trends(s)
        if v is not None:
            _cache.set(ck, v, ttl=14400)
        return v

    def _cached_price_target(s):
        ck = f"price_target:{s}"
        v = _cache.get(ck)
        if v is not None:
            return v
        v = external_data.finnhub_price_target(s)
        if v is not None:
            _cache.set(ck, v, ttl=14400)
        return v

    # Las noticias YA se cachean 30 min (las escribe este mismo endpoint más abajo y
    # /api/news/{sym}), pero aquí no se leía: se volvían a descargar en cada carga.
    def _cached_news(s):
        v = _cache.get(f"news:{s}")
        if v is not None:
            return v.get("items") if isinstance(v, dict) else v
        return market_data.get_news(s)

    results = await asyncio.gather(
        _timed("quote", market_data.get_quote, sym),
        _timed("chart", partial(market_data.get_stock_data, sym, timeframe=timeframe)),
        _timed("indicators", market_data.get_full_indicator_history, sym),
        _timed("news", _cached_news, sym),
        _timed("trends", _cached_trends, sym),
        _timed("price_target", _cached_price_target, sym),
        _timed("vp", _cached_vp, sym),
        # Histórico del índice para la Fuerza Relativa. No es una fuente nueva de verdad: es
        # el mismo SPY que ya descarga y cachea el semáforo de mercado, así que casi siempre
        # sale de caché. Va en el gather para que, cuando toque bajarlo, no alargue la carga.
        _timed("spy", market_data.get_full_indicator_history, "SPY"),
        return_exceptions=True,
    )
    quote, df_chart, df_ind, news_items, trends, price_target, vp, df_spy = results
    _dt_total = _time.time() - _t_total
    if _dt_total > 8.0:
        logger.warning("dashboard[%s] TOTAL fetch LENTO: %.1fs", sym, _dt_total)

    if not quote or isinstance(quote, Exception):
        raise HTTPException(404, f"No se encontraron datos para '{sym}'")

    # SEGUNDA TANDA, también en paralelo. Medido en producción: las fuentes de arriba
    # costaban 230 ms pero la carga completa 1.115 ms. La diferencia estaba aquí: lo que
    # sigue al gather se hacía TODO en serie —enriquecer, precio extendido, indicadores,
    # fuerza relativa, niveles, régimen— aunque las tres cosas que abren red no dependen
    # unas de otras.
    #
    # Se lanzan ya y se recogen más abajo, después del trabajo de CPU: así la red de estas
    # tres y el cálculo de indicadores/niveles ocurren a la vez en vez de encadenarse.
    _t_enrich = asyncio.ensure_future(_timed("enrich", _enrich_quote_fundamentals, quote, sym))
    _t_ext = asyncio.ensure_future(_sin_estallar(_extended_quote_cacheada(sym)))
    # El régimen de mercado no depende del símbolo y su caché dura 1 h, pero cuando caduca
    # descarga el histórico de SPY. En serie, esa descarga la pagaba entera quien tuviera la
    # mala suerte de cargar justo en ese momento.
    _t_regimen = asyncio.ensure_future(_sin_estallar(asyncio.to_thread(market_regime.get_market_regime)))

    quote = await _t_enrich
    # Se recoge SIEMPRE, aunque no haya quote: `enrich` puede devolver None al agotar su
    # tope, y entonces la tarea del precio extendido se quedaría colgando sin dueño.
    ext = await _t_ext

    # Extended hours (pre-market / after-hours): añade estado + precio + % al quote para que
    # el header del dashboard lo muestre igual que la watchlist. Cacheado 60s (dato volátil).
    if quote:
        try:
            state = (ext or {}).get("market_state")
            ext_price = (ext or {}).get("extended_price")
            reg_close = (ext or {}).get("regular_close") or quote.get("price")
            quote["market_state"] = state
            if state == "PRE":
                quote["pre_market_price"] = ext_price
            elif state == "POST":
                quote["post_market_price"] = ext_price
            if ext_price and reg_close:
                quote["extended_change_percent"] = round((ext_price - reg_close) / reg_close * 100, 2)
        except Exception:
            pass

    candles = []
    if df_chart is not None and not isinstance(df_chart, Exception):
        try:
            if not df_chart.empty:
                candles = market_data.df_to_candles(df_chart)
        except Exception:
            pass

    indicators_data = None
    if df_ind is not None and not isinstance(df_ind, Exception):
        try:
            if not df_ind.empty:
                indicators_data = await loop.run_in_executor(None, ind.compute_all, df_ind)
        except Exception:
            pass

    news_list = []
    if news_items and not isinstance(news_items, Exception):
        news_list = news_items

    # Fuerza Relativa frente al S&P 500. Es el filtro que más usan las metodologías de
    # momentum para separar líderes de rezagadas, y es el único indicador de peso que no
    # teníamos. Sale de datos ya descargados, así que no cuesta ni una llamada extra.
    fuerza_relativa = None
    if (df_ind is not None and not isinstance(df_ind, Exception)
            and df_spy is not None and not isinstance(df_spy, Exception)):
        try:
            fuerza_relativa = await loop.run_in_executor(
                None, ind.relative_strength, df_ind, df_spy)
        except Exception:
            fuerza_relativa = None

    analyst_consensus = None
    if trends and not isinstance(trends, Exception):
        try:
            analyst_consensus = external_data.aggregate_recommendation(trends)
        except Exception:
            pass

    pt = None if isinstance(price_target, Exception) else price_target

    analyst = {"symbol": sym, "consensus": analyst_consensus, "price_target": pt}

    # Motor de confluencia: los niveles son DETERMINISTAS (no dependen de la IA), así que
    # se calculan ya al cargar la acción. Así el gráfico y la tarjeta muestran siempre los
    # niveles del motor sin necesidad de pulsar "Generar análisis".
    vp_dict = vp if isinstance(vp, dict) else {}
    buy_levels = []
    if indicators_data and df_ind is not None and not isinstance(df_ind, Exception):
        try:
            buy_levels = await loop.run_in_executor(
                None,
                partial(
                    levels_engine.compute_buy_levels,
                    df_ind, vp_dict, quote.get("price"), indicators_data.get("sma"),
                    atr_val=indicators_data.get("atr"),
                    regime=indicators_data.get("regime"),
                    vwap_anchored=indicators_data.get("vwap_anchored"),
                ),
            )
        except Exception:
            logger.exception("dashboard[%s] compute_buy_levels failed", sym)

    # `en_plan`: que zonas usa el plan escalonado. Se marca aqui, con la MISMA funcion que
    # usa `_deterministic_levels` para construirlo, para que la pantalla pueda agrupar sin
    # replicar el umbral del 30% en el cliente. Es aditivo: no toca precio, fuerza,
    # distancia, razones ni el orden.
    levels_engine.marcar_en_plan(buy_levels, quote.get("price"), MAX_PLAN_DEPTH)

    # Actualizar cachés individuales para que los endpoints separados también sean rápidos
    _cache.set(f"quote:{sym}", quote, ttl=60)
    _cache.set(f"chart:{sym}:{timeframe}", {"symbol": sym, "timeframe": timeframe, "candles": candles}, ttl=3600)
    if indicators_data:
        _cache.set(f"indicators:{sym}", indicators_data, ttl=3600)
    if news_list:
        _cache.set(f"news:{sym}", {"symbol": sym, "items": news_list}, ttl=1800)
    _cache.set(f"analyst:{sym}", analyst, ttl=604800)

    # #7 — Salud de los datos: avisa si los datos vienen de una fuente de respaldo (Stooq,
    # sin volumen) o con retraso, para que no operes sobre un fallback silencioso.
    # OJO: se mide SOLO sobre df_ind (siempre DIARIO). Medirlo sobre df_chart daba un falso
    # "datos con retraso" permanente en los timeframes 1W y 1M, cuya última vela lleva la
    # fecha de INICIO del periodo (una vela mensual "tiene" hasta 30 días de antigüedad).
    health = None
    try:
        if df_ind is not None and not isinstance(df_ind, Exception):
            health = market_data.data_health(df_ind)
    except Exception:
        health = None

    result = {
        "symbol": sym,
        "timeframe": timeframe,
        "quote": quote,
        "candles": candles,
        "lines": _compute_chart_lines(candles),
        "indicators": indicators_data,
        "news": news_list,
        "analyst": analyst,
        "buy_levels": buy_levels or [],
        "volume_profile": vp_dict or None,
        "relative_strength": fuerza_relativa,
        # A un hilo: cuando su caché de 1h caduca, get_market_regime DESCARGA el histórico de
        # SPY. Llamándolo aquí tal cual, esa descarga corría en el event loop y congelaba el
        # servidor entero —todas las peticiones de todos— hasta que terminara.
        # Lanzado arriba, junto al resto de la segunda tanda: para cuando se llega aquí ya
        # ha corrido en paralelo con el cálculo de indicadores y niveles.
        "market_regime": await _t_regimen,
        "data_health": health,
        # Cuándo se calculó DE VERDAD todo lo pesado. Al servirse caducado, la cotización se
        # refresca aparte pero esta marca no cambia: así queda claro de cuándo es el resto.
        "generado_en": datetime.now(timezone.utc).isoformat(),
    }
    # ttl 900 < cadencia del precalentado 1200 < ventana de servible 1800.
    #
    # Con el ttl anterior de 300 la entrada estaba "caducada" 15 de cada 20 minutos y
    # solo sobrevivía gracias a `get_stale`, que es justo lo que la purga anulaba. Se
    # sube a 900 para que la exposición baje a 5 de cada 20, y se deja POR DEBAJO de la
    # cadencia para que el precalentado siempre la encuentre no-fresca y la renueve: con
    # ttl igual a la cadencia, cualquier desfase la dejaría fresca y el `if fresco:
    # continue` se saltaría la vuelta entera.
    #
    # No hay riesgo de servir precios viejos: la cotización se refresca aparte, y lo
    # pesado —indicadores y niveles— se calcula sobre velas diarias, que no cambian de
    # un minuto a otro.
    # Tesis DETERMINISTA. Se redacta aquí, dentro del ensamblado, para que entre en la
    # caché y no se rehaga en cada lectura. Es una capa de redacción sobre los campos que
    # ya trae `result`: no llama a nadie, no toca el motor y no inventa aritmética.
    #
    # Va antes del `set` a propósito: así viaja EN la respuesta cacheada y la página tiene
    # una explicación en frío, sin pulsar «Análisis completo IA» ni esperar.
    # Estado de la acción y visibilidad de las zonas. Va ANTES de la tesis a propósito:
    # la tesis se redacta sobre `result`, así que si las zonas se ocultaran después, la
    # frase «la zona de compra más sólida es…» seguiría en pantalla señalando una lista
    # que ya no está. Aplicado aquí, la tesis describe lo mismo que se ve.
    _aplicar_estado_tendencia(result, quote.get("price"), indicators_data)

    try:
        result["tesis"] = tesis.redactar(result)
    except Exception:
        # Que falle la redacción no puede tumbar el dashboard entero: sin tesis la página
        # sigue teniendo todos sus datos, que es como está hoy.
        logger.exception("dashboard[%s] redacción de la tesis falló", sym)
        result["tesis"] = None

    _cache.set(cache_key, result, ttl=DASHBOARD_TTL, servible_hasta=_DASHBOARD_STALE_MAX)
    return result


@api_router.get("/estudio/rsi-sobreventa")
async def estudio_rsi_sobreventa(umbral: float = 30.0,
                                 _user: str = Depends(auth.get_current_user)):
    """Contrasta con datos FRESCOS la idea de que "cuando el RSI baja de 30, siempre sube".

    Existe porque el estudio original se hizo con un dataset público que acaba en 2018: no
    incluía el COVID, 2022 ni nada posterior. Desde aquí sí hay acceso a Yahoo, así que
    devuelve el análisis con datos hasta HOY.

    Devuelve, para 1/3/6/12 meses: cuántas veces subió tras la sobreventa, la media, el peor
    caso — y lo mismo para un día CUALQUIERA, que es la referencia que hay que batir. Separa
    además los episodios en tendencia sana (sobre la SMA200) y rota (por debajo).

    Tarda unos segundos: descarga 25 años de velas diarias.
    """
    return await asyncio.to_thread(sp500_rsi_watch.estudio_completo, umbral)


# ---------- Ventas ejecutadas (ganancia REALIZADA, en euros) ----------
class VentaCreate(BaseModel):
    acciones: float
    precio_venta: float
    fecha: Optional[str] = None          # YYYY-MM-DD; por defecto, hoy
    tasa_compra: Optional[float] = None  # si lo dejas vacío se busca por la fecha de compra
    tasa_venta: Optional[float] = None   # idem por la fecha de venta


@api_router.post("/signals/{entry_id}/vender")
async def registrar_venta(entry_id: str, item: VentaCreate,
                          _user: str = Depends(auth.get_current_user)):
    """Registra una venta y devuelve lo ganado, en la divisa original y en EUROS.

    La ganancia en euros usa el tipo de cambio de la fecha de COMPRA y el de la de VENTA:
    convertir el beneficio en dólares al cambio de hoy no da lo que entró en la cuenta.
    """
    entry = await db.signal_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(404, "Esa posición no existe en tu Cartera.")
    # ESTA VENTA VA AL LIBRO, como cualquier otra. Antes se guardaba en su propia colección
    # (`signal_sales`) y descontaba a mano las acciones de la Cartera: eran DOS
    # contabilidades. La de Ventas no veía estas ventas —su Realizado no las contaba— y en
    # cuanto cualquier cosa disparaba _sincronizar_posicion, la Cartera se recalculaba desde
    # el libro y las acciones vendidas VOLVÍAN. Un solo libro, una sola verdad.
    try:
        estado = await cartera_api.registrar_venta(
            db, entry.get("symbol"), item.acciones, item.precio_venta,
            fecha=item.fecha, tasa=item.tasa_venta,
            divisa=entry.get("divisa"), notas="Vendida desde la Cartera")
    except ValueError as e:
        raise HTTPException(400, str(e))
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)

    # Respuesta con la forma que espera el diálogo de la Cartera, sacada del libro.
    metodo = (estado.get("metodo_gestion") or "lifo").lower()
    ultima = ((estado.get(metodo) or {}).get("ventas") or [{}])[-1]
    return {
        "symbol": entry.get("symbol"),
        "acciones": item.acciones,
        "divisa": ultima.get("divisa") or entry.get("divisa") or "USD",
        "ganancia_divisa": ultima.get("ganancia_divisa"),
        "ganancia_pct": ultima.get("pct"),
        "ganancia_eur": ultima.get("ganancia_eur"),
        "efecto_divisa_eur": ultima.get("efecto_divisa_eur"),
        "exacto": ultima.get("exacto"),
        "acciones_restantes": (estado.get(metodo) or {}).get("acciones_abiertas"),
        "campanas": estado.get("campanas"),
        "sin_cubrir": ultima.get("sin_cubrir") or 0,
    }


@api_router.get("/ventas")
async def listar_ventas(_user: str = Depends(auth.get_current_user)):
    lista = await ventas_mod.listar(db)
    return {"items": lista, "resumen": ventas_mod.resumen(lista)}


@api_router.delete("/ventas/{venta_id}")
async def borrar_venta(venta_id: str, _user: str = Depends(auth.get_current_user)):
    """Borra una venta y DEVUELVE las acciones a la posición."""
    if not await ventas_mod.borrar(db, venta_id):
        raise HTTPException(404, "Venta no encontrada")
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return {"ok": True}


# ---------- Libro de operaciones: compras por lotes y ventas ----------
# Sustituye al modelo anterior (un precio medio en la posición y restar al vender), que no
# puede contestar a "estas 3 que me quedan, ¿de qué compra son?" ni recalcular sin mentir en
# cuanto vuelves a comprar. Ver lotes.py para el porqué de FIFO y LIFO.

class CompraCreate(BaseModel):
    symbol: str
    acciones: float
    precio: float
    fecha: Optional[str] = None          # YYYY-MM-DD; por defecto, hoy
    # None = "no lo sé, estímalo con la tarifa". 0 = "no me costó nada".
    comision: Optional[float] = None     # en la divisa de la operación
    divisa: Optional[str] = None         # por defecto, la de la posición
    tasa: Optional[float] = None         # divisa por 1 EUR; vacío = se busca por la fecha
    nivel: Optional[str] = None          # vacío = se deduce del precio
    notas: Optional[str] = ""


class VentaLoteCreate(BaseModel):
    symbol: str
    acciones: float
    precio: float
    fecha: Optional[str] = None
    comision: Optional[float] = None
    divisa: Optional[str] = None
    tasa: Optional[float] = None
    notas: Optional[str] = ""


@api_router.post("/cartera/compras")
async def crear_compra(item: CompraCreate, _user: str = Depends(auth.get_current_user)):
    """Registra una compra. Detecta sola en qué nivel de la Cartera se hizo."""
    try:
        compra = await cartera_api.registrar_compra(
            db, item.symbol, item.acciones, item.precio, fecha=item.fecha,
            comision=item.comision, divisa=item.divisa, tasa=item.tasa,
            nivel=item.nivel, notas=item.notas or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return compra


@api_router.delete("/cartera/compras/{compra_id}")
async def eliminar_compra(compra_id: str, forzar: bool = False,
                          _user: str = Depends(auth.get_current_user)):
    """Borra una compra. Se niega (409) si dejaría ventas sin coste; `forzar=true` la borra
    igualmente, para poder corregir de verdad cuando sabes lo que haces."""
    r = await cartera_api.borrar_compra(db, compra_id, forzar=forzar)
    if r.get("motivo") == "no_existe":
        raise HTTPException(404, "Esa compra no existe.")
    if r.get("motivo") == "dejaria_ventas_sin_coste":
        raise HTTPException(409,
            f"Si borras esta compra, {r['acciones_sin_cubrir']:g} acción(es) vendidas de "
            f"{r['symbol']} se quedan sin coste y su ganancia saldrá hinchada. "
            f"Mete antes la compra que las cubra, o bórrala de todos modos si sabes lo que "
            f"haces.")
    if not r.get("borrada"):
        raise HTTPException(404, "Esa compra no existe.")
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return {"ok": True}


@api_router.put("/cartera/compras/{compra_id}/nivel")
async def cambiar_nivel_compra(compra_id: str, nivel: Optional[str] = None,
                               _user: str = Depends(auth.get_current_user)):
    """Asigna a mano el nivel de una compra que la detección automática (±1,5%) no pilló."""
    try:
        r = await cartera_api.asignar_nivel_compra(db, compra_id, nivel or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return r


@api_router.post("/cartera/ventas")
async def crear_venta(item: VentaLoteCreate, _user: str = Depends(auth.get_current_user)):
    """Registra una venta y devuelve el resultado por los DOS métodos (FIFO y LIFO)."""
    try:
        estado = await cartera_api.registrar_venta(
            db, item.symbol, item.acciones, item.precio, fecha=item.fecha,
            comision=item.comision, divisa=item.divisa, tasa=item.tasa,
            notas=item.notas or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return estado


@api_router.delete("/cartera/ventas/{venta_id}")
async def eliminar_venta(venta_id: str, _user: str = Depends(auth.get_current_user)):
    """Borra una venta. No hay que 'devolver' acciones a ninguna parte: la posición se
    deriva del libro, así que quitar el apunte la deja correcta sola."""
    if not await cartera_api.borrar_venta(db, venta_id):
        raise HTTPException(404, "Esa venta no existe.")
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return {"ok": True}


@api_router.get("/cartera/posicion/{symbol}")
async def posicion_simbolo(symbol: str, _user: str = Depends(auth.get_current_user)):
    """Lotes abiertos, ventas por los dos métodos y ganancia latente de un valor."""
    sym = symbol.strip().upper()
    precio = None
    try:
        q = _cache.get(f"quote:{sym}")
        precio = (q or {}).get("price") if q else None
        if precio is None:
            q = await asyncio.to_thread(market_data.get_quote_fast, sym)
            precio = (q or {}).get("price")
    except Exception:
        pass
    return await cartera_api.estado_simbolo(db, sym, precio_actual=precio)


@api_router.get("/cartera/fechas-niveles/{symbol}")
async def fechas_niveles(symbol: str, _user: str = Depends(auth.get_current_user)):
    """Cuándo el precio tocó cada nivel de la Cartera, para estimar la fecha de cada compra.

    Existe porque nadie recuerda en qué día compró cada nivel, y la fecha no es un adorno:
    determina el tipo de cambio con el que se calculan los euros de esa compra.
    """
    sym = symbol.strip().upper()
    entry = await db.signal_entries.find_one({"symbol": sym}, {"_id": 0})
    if not entry:
        raise HTTPException(404, f"{sym} no está en tu Cartera.")

    df = await asyncio.to_thread(market_data.get_full_indicator_history, sym)
    velas = market_data.df_to_candles(df) if df is not None and not df.empty else []

    out = []
    for i in range(1, 6):
        precio = entry.get(f"nivel{i}")
        if precio in (None, "", 0):
            continue
        try:
            precio = float(precio)
        except (TypeError, ValueError):
            continue
        if precio <= 0:
            continue
        out.append({"nivel": f"nivel{i}", "etiqueta": f"Nivel {i}", "precio": precio,
                    **lotes.fechas_en_que_toco(velas, precio)})
    out.sort(key=lambda n: n["precio"], reverse=True)
    return {"symbol": sym, "niveles": out,
            "desde": (velas[0]["date"][:10] if velas else None),
            "aviso": ("Fechas estimadas por cuándo el precio pasó por cada nivel, sobre el "
                      "histórico de 2 años. Si compraste antes, o el precio pasó varias "
                      "veces, ajústalas: la fecha decide el tipo de cambio de esa compra.")}


@api_router.get("/cartera/dividendos")
async def dividendos(_user: str = Depends(auth.get_current_user)):
    """Lo cobrado por dividendos, en euros, con la retención en origen aparte."""
    return await cartera_api.resumen_dividendos(db)


@api_router.get("/cartera/historial")
async def historial_ventas(_user: str = Depends(auth.get_current_user)):
    """Todas las ventas hechas, con lo ganado por FIFO y por LIFO, y los totales."""
    r = await cartera_api.historial(db)
    # Ventas de la contabilidad VIEJA (`signal_sales`, el diálogo Vender de la Cartera antes
    # de que escribiera en el libro). Si quedan, sus acciones y su ganancia no están en
    # ninguna cifra de esta pantalla. Se cuentan para poder avisar en vez de callarlo.
    try:
        r["ventas_antiguas"] = await db.signal_sales.count_documents({})
    except Exception:
        r["ventas_antiguas"] = 0
    return r


@api_router.get("/cartera/resumen")
async def resumen_cartera(_user: str = Depends(auth.get_current_user)):
    """P&L de la cartera entera en EUROS: latente por posición + realizado."""
    # Los precios salen de la Cartera, donde el worker escribe last_price cada 60 s. Antes
    # se leían de la caché en memoria de /signals, y si estaba vacía —proceso recién
    # arrancado, o nadie había abierto la Cartera todavía— NINGUNA posición se podía
    # valorar y la pantalla salía entera a "—". Leerlo de la base de datos no gasta cuota
    # de Finnhub y no depende de que otra pantalla se haya visitado antes.
    precios = {}
    try:
        for e in await signal_table.list_entries(db):
            if e.get("symbol") and e.get("last_price") is not None:
                precios[e["symbol"].upper()] = e["last_price"]
    except Exception as exc:
        logger.warning("No se pudieron leer los precios para el resumen: %s", exc)
    return await cartera_api.resumen_cartera(db, precios)


class PrecioManual(BaseModel):
    symbol: str
    precio: Optional[float] = None       # 0 o vacío = quitarlo


@api_router.put("/cartera/precio-manual")
async def poner_precio_manual(item: PrecioManual,
                              _user: str = Depends(auth.get_current_user)):
    """Precio a mano para un valor sin cotización en vivo. Solo rellena huecos: si el valor
    cotiza, manda la cotización."""
    try:
        return await cartera_api.guardar_precio_manual(db, item.symbol, item.precio)
    except ValueError as e:
        raise HTTPException(400, str(e))


class AjusteMetodo(BaseModel):
    metodo_gestion: str          # "FIFO" o "LIFO"


@api_router.get("/cartera/ajustes")
async def leer_ajustes(_user: str = Depends(auth.get_current_user)):
    return {"metodo_gestion": (await cartera_api.metodo_gestion(db)).lower()}


@api_router.put("/cartera/ajustes")
async def guardar_ajustes(item: AjusteMetodo, _user: str = Depends(auth.get_current_user)):
    """Cambia el método con el que se emparejan las ventas y RECALCULA todo.

    No altera ningún apunte: compras y ventas son las que son. Cambia cómo se emparejan, y
    con ello qué lotes quedan vivos, tu precio medio y qué campanitas están encendidas.
    """
    try:
        r = await cartera_api.guardar_metodo_gestion(db, item.metodo_gestion)
    except ValueError as e:
        raise HTTPException(400, str(e))
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return r


@api_router.post("/cartera/importar-degiro")
async def importar_degiro(archivo: UploadFile = File(...),
                          mapeo: Optional[str] = None,
                          confirmar: bool = False,
                          _user: str = Depends(auth.get_current_user)):
    """Importa el CSV de Transacciones de DEGIRO.

    Dos pasos a propósito. Sin `confirmar` solo se LEE y se devuelve lo que hay, incluidos
    los productos que no se sabe a qué acción corresponden: el fichero trae ISIN y nombre,
    no ticker, y meter operaciones en la posición equivocada es peor que no importarlas.
    Con `confirmar=true` y el mapeo resuelto, se guardan.

    `mapeo` es un JSON {"US5738741041": "MRVL", ...}.
    """
    contenido = await archivo.read()
    if len(contenido) > 5_000_000:
        raise HTTPException(413, "El fichero es demasiado grande (máximo 5 MB).")

    # Se detecta SOLO qué fichero es. Pedir un botón distinto para cada uno obliga a saber
    # cuál trae qué, y los dos se llaman parecido: Transactions.csv y Account.csv.
    leido = await asyncio.to_thread(degiro_csv.leer, contenido)
    if leido["errores"] and not leido["operaciones"]:
        cuenta = await asyncio.to_thread(degiro_csv.leer_cuenta, contenido)
        if cuenta["dividendos"]:
            r = await cartera_api.importar_dividendos(db, cuenta["dividendos"])
            return {"tipo": "dividendos", "confirmado": True,
                    "productos": [], "pendientes": [],
                    "resumen": degiro_csv.resumen_dividendos(cuenta["dividendos"]),
                    "errores": cuenta["errores"], **r}
        raise HTTPException(400, leido["errores"][0])

    try:
        mapa = json.loads(mapeo) if mapeo else {}
    except Exception:
        raise HTTPException(400, "El mapeo de productos no es un JSON válido.")

    if not confirmar:
        if mapa:
            await cartera_api.guardar_mapa_isin(db, mapa)
        prep = await cartera_api.preparar_importacion_degiro(db, leido["operaciones"], mapa)
        return {**prep, "resumen": degiro_csv.resumen(leido["operaciones"]),
                "errores": leido["errores"], "confirmado": False}

    r = await cartera_api.importar_degiro(db, leido["operaciones"], mapa)
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return {**r, "resumen": degiro_csv.resumen(leido["operaciones"]),
            "errores": leido["errores"], "confirmado": not r.get("pendientes")}


@api_router.post("/cartera/importar-posiciones")
async def importar_posiciones(reemplazar: bool = False,
                              _user: str = Depends(auth.get_current_user)):
    """Reconstruye los lotes de cada posición que ya tenías, para no empezar de cero.

    Con `reemplazar=true` rehace las que ya se importaron — útil si la primera vez salió mal.
    Nunca toca un símbolo que ya tenga ventas: borrar sus compras dejaría esas ventas sin
    coste y su ganancia sería falsa.
    """
    r = await cartera_api.importar_posiciones_existentes(db, reemplazar=reemplazar)
    # Era el único endpoint de escritura que no vaciaba la caché: justo después de importar,
    # la Cartera seguía sirviendo lo de antes hasta 5 minutos y parecía que no había hecho
    # nada.
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return r


@api_router.post("/cartera/quitar-duplicados")
async def quitar_duplicados(_user: str = Depends(auth.get_current_user)):
    """Quita los lotes de "Importar mis posiciones" en los símbolos que ya cubre el CSV.

    Las dos importaciones describen las mismas acciones; con ambas en el libro cada posición
    sale al doble. Se conserva la versión del CSV, que trae fechas y precios reales.
    """
    r = await cartera_api.quitar_lotes_de_la_foto(db)
    for k in ("signals_list", "signals_hot"):
        _cache._store.pop(k, None)
    return r


@api_router.get("/fx/{divisa}")
async def tipo_cambio(divisa: str, fecha: Optional[str] = None,
                      _user: str = Depends(auth.get_current_user)):
    """Tipo de cambio (unidades de la divisa por 1 EUR). Sin fecha, el de ahora."""
    tasa = await asyncio.to_thread(
        fx.tasa_en_fecha, divisa, fecha) if fecha else await asyncio.to_thread(
        fx.tasa_actual, divisa)
    if not tasa:
        raise HTTPException(503, f"No se pudo obtener el tipo de cambio de {divisa.upper()}.")
    return {"divisa": divisa.upper(), "fecha": fecha or "ahora", "tasa": round(tasa, 4)}


@api_router.get("/diagnostico/carga/{symbol}")
async def diagnostico_carga(symbol: str, _user: str = Depends(auth.get_current_user)):
    """Cronometra CADA fuente de datos por separado y dice cuál está tardando.

    Existe porque la lentitud se estuvo diagnosticando a ojo y se acertó a medias: el
    servidor ya tenía instrumentación, pero solo escribía en los logs de Render y nadie los
    miraba. Esto devuelve lo mismo en pantalla y SIN caché, para ver el coste real.

    Cada fuente lleva su propio cronómetro, así que se ve exactamente cuál es la lenta en
    vez de saber solo que "el dashboard tarda".
    """
    sym = symbol.upper()
    loop = asyncio.get_running_loop()

    async def _medir(nombre, fn, *args):
        t0 = _time.time()
        estado = "ok"
        detalle = None
        try:
            r = await asyncio.wait_for(loop.run_in_executor(None, fn, *args), timeout=20.0)
            if r is None:
                estado = "sin datos"
            elif hasattr(r, "empty") and r.empty:
                estado = "vacío"
            elif hasattr(r, "__len__"):
                detalle = f"{len(r)} filas"
        except asyncio.TimeoutError:
            estado = "TIMEOUT (>20s)"
        except Exception as e:
            estado = f"error: {str(e)[:60]}"
        return {"fuente": nombre, "ms": int((_time.time() - t0) * 1000),
                "estado": estado, "detalle": detalle}

    # ── LO QUE DE VERDAD TARDA AL ELEGIR ESTA ACCIÓN ──────────────────────────
    # Lo de abajo mide las fuentes SIN caché a propósito, para ver cuánto cuestan de verdad.
    # Eso sirve para saber cuál va lenta, pero NO es lo que vive el usuario: la web pasa por
    # las cachés y el precalentado. Medido solo así, cualquier mejora que consista en dejar
    # de repetir trabajo —que es la mayoría— resulta invisible, y se saca la conclusión
    # equivocada de que no sirvió de nada.
    #
    # Esta primera medida recorre EXACTAMENTE el mismo camino que el navegador. Va antes que
    # las demás para no aprovecharse de las cachés que ellas puedan calentar.
    clave_real = f"dashboard:{sym}:{_TIMEFRAME_PREWARM}"
    _, estaba_fresco = _cache.get_stale(clave_real, max_age=_DASHBOARD_STALE_MAX)
    _t_real = _time.time()
    try:
        await dashboard_data(sym, _TIMEFRAME_PREWARM, _user="diag")
        _estado_real = "ok"
    except Exception as e:
        _estado_real = f"error: {str(e)[:60]}"
    experiencia_real = {
        "ms": int((_time.time() - _t_real) * 1000),
        "estado": _estado_real,
        "desde_cache": bool(estaba_fresco),
        "nota": ("servido de caché (precalentado o visita reciente)" if estaba_fresco
                 else "ensamblado completo: primera visita a esta acción"),
    }

    t_total = _time.time()
    # En PARALELO, igual que hace el dashboard: así el total refleja la experiencia real.
    medidas = await asyncio.gather(
        _medir("cotización", market_data.get_quote, sym),
        _medir("histórico (gráfico + indicadores)", market_data.get_full_indicator_history, sym),
        _medir("noticias", market_data.get_news, sym),
        _medir("recomendaciones analistas", external_data.finnhub_recommendation_trends, sym),
        _medir("precio objetivo analistas", external_data.finnhub_price_target, sym),
        _medir("volume profile", partial(polygon_data.get_volume_profile, sym, 365)),
        _medir("histórico SPY (fuerza relativa)", market_data.get_full_indicator_history, "SPY"),
    )
    total_ms = int((_time.time() - t_total) * 1000)
    lentas = sorted(medidas, key=lambda m: m["ms"], reverse=True)

    # Los PANELES que se cargan solos al cambiar de acción. No estaban medidos y son los
    # sospechosos: /backtest corre un backtest completo por símbolo y /alternativa invoca el
    # escáner de crecimiento. Sus timeouts en el frontend (2 y 5 minutos) ya delatan que se
    # esperaban lentos. Van DESPUÉS y en serie para no falsear el total de arriba.
    async def _medir_http(nombre, corutina):
        t0 = _time.time()
        estado = "ok"
        try:
            await asyncio.wait_for(corutina, timeout=30.0)
        except asyncio.TimeoutError:
            estado = "TIMEOUT (>30s)"
        except Exception as e:
            estado = f"error: {str(e)[:60]}"
        return {"fuente": nombre, "ms": int((_time.time() - t0) * 1000), "estado": estado}

    paneles = []
    for nombre, cor in (
        ("panel Chartista (cacheado)", chartist_verdict(sym, cached_only=True, _user="diag")),
        ("panel Tus fuentes", fuentes_de_accion(sym, _user="diag")),
        ("panel Alternativa sectorial", alternativa_sectorial(sym, _user="diag")),
        ("panel Backtest", backtest_levels(sym, _user="diag")),
    ):
        paneles.append(await _medir_http(nombre, cor))
    paneles.sort(key=lambda m: m["ms"], reverse=True)

    # Estado del limitador de Finnhub: si está saturado, TODO lo que pase por él se arrastra.
    try:
        lim = market_data.get_finnhub_limiter()
        with lim.lock:
            ahora = _time.time()
            usadas = len([t for t in lim.calls if ahora - t < 60])
        # OJO con el umbral: superar bg_cap NO es un problema, es el diseño — solo frena a
        # las tareas de FONDO para dejarte hueco a ti. Comparar contra bg_cap daba una
        # alarma falsa ("SATURADA" con 28 de 50, teniendo 22 libres para navegar).
        cuota = {"usadas_ultimo_minuto": usadas, "tope_total": lim.max_per_min,
                 "tope_tareas_de_fondo": lim.bg_cap,
                 "libres_para_ti": max(0, lim.max_per_min - usadas),
                 "saturado": usadas >= lim.max_per_min,
                 "fondo_frenado": usadas >= lim.bg_cap}
    except Exception:
        cuota = None

    # Desglose interno de la cotización: es la que se lleva el tiempo, así que se abre
    # fase por fase para ver EXACTAMENTE cuál se atasca y por qué rama va.
    desglose = await asyncio.to_thread(market_data.diagnostico_quote, sym)

    return {
        "simbolo": sym,
        # Lo primero de la respuesta porque es la cifra que contesta a la pregunta que se
        # hace de verdad ("¿va rápido?"). total_ms responde a otra distinta y más técnica
        # ("¿cuánto cuestan las fuentes?"), y confundirlas lleva a conclusiones al revés.
        "experiencia_real": experiencia_real,
        "total_ms": total_ms,
        "desglose_cotizacion": desglose,
        "veredicto": ("rápido" if total_ms < 1500 else
                      "aceptable" if total_ms < 4000 else "LENTO"),
        "la_mas_lenta": lentas[0]["fuente"] if lentas else None,
        "por_fuente": lentas,
        "paneles_al_cambiar_de_accion": paneles,
        "panel_mas_lento": paneles[0]["fuente"] if paneles else None,
        "total_paneles_ms": sum(p["ms"] for p in paneles),
        "cuota_finnhub": cuota,
        "nota": ("Medido SIN caché: es el peor caso, el de abrir un ticker por primera vez. "
                 "Al repetirlo debería ser casi instantáneo."),
    }


@api_router.get("/market-regime")
async def market_regime_endpoint(_user: str = Depends(auth.get_current_user)):
    """Semáforo de mercado (S&P vs SMA200 + tendencia) — condiciona la fiabilidad de las
    señales de compra. 🟢 sano · 🟡 transición · 🔴 riesgo."""
    return market_regime.get_market_regime()


@api_router.get("/market/sentiment")
async def market_sentiment_endpoint(_user: str = Depends(auth.get_current_user)):
    """Termómetro Miedo/Codicia del mercado (0-100) a partir del VIX y el momento del S&P.
    Cacheado 15 min internamente."""
    return await asyncio.to_thread(market_regime.get_fear_greed)


@api_router.get("/search")
async def search_symbols(q: str = "", _user: str = Depends(auth.get_current_user)):
    """Autocompletado del buscador: busca acciones por NOMBRE o ticker (Finnhub search),
    para no tener que memorizar el ticker exacto. Devuelve [{symbol, name}]. Cacheado 1h."""
    q = (q or "").strip()
    if len(q) < 1:
        return []
    ck = f"search:{q.lower()}"
    cached = _cache.get(ck)
    if cached is not None:
        return cached
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return []
    q = q[:40]  # acota la entrada (además es la clave de caché)
    ok = False
    try:
        def _call():
            # El límite de Finnhub es por CLAVE y /search también cuenta: sin pasar por el
            # rate limiter, teclear en el buscador podía dejar sin precios a toda la app.
            # La espera va ACOTADA: esto se dispara mientras el usuario TECLEA, así que
            # bloquear hasta 60s por un hueco dejaría el autocompletado congelado. Sin
            # hueco, no hay sugerencias y punto.
            if not market_data.get_finnhub_limiter().acquire(max_wait=1.5):
                return None
            return market_data.get_http_session().get(
                "https://finnhub.io/api/v1/search",
                params={"q": q, "token": key}, timeout=6,
            )
        r = await asyncio.to_thread(_call)
        ok = bool(r) and r.status_code == 200
        data = r.json() if ok else {}
    except Exception:
        data = {}
    out, seen = [], set()
    for it in (data.get("result") or []):
        sym = (it.get("symbol") or "").upper()
        desc = it.get("description") or ""
        # Solo acciones "limpias": sin sufijos raros (.PA, :HK...) y con nombre. Prioriza US.
        if not sym or not desc or "." in sym or ":" in sym or sym in seen:
            continue
        seen.add(sym)
        out.append({"symbol": sym, "name": desc.title()})
        if len(out) >= 8:
            break
    # Solo cachear 1h si la fuente respondió: antes un hipo de Finnhub dejaba el
    # autocompletado de esa consulta devolviendo lista vacía durante una hora.
    if ok:
        _cache.set(ck, out, ttl=3600 if out else 60)
    return out


# 11 ETFs sectoriales SPDR: representan el rendimiento de cada sector del S&P 500.
_SECTOR_ETFS = [
    ("XLK", "Tecnología"), ("XLC", "Comunicaciones"), ("XLY", "Consumo discr."),
    ("XLP", "Consumo básico"), ("XLE", "Energía"), ("XLF", "Financiero"),
    ("XLV", "Salud"), ("XLI", "Industrial"), ("XLB", "Materiales"),
    ("XLRE", "Inmobiliario"), ("XLU", "Servicios públ."),
]


@api_router.get("/market/heatmap")
async def market_heatmap(_user: str = Depends(auth.get_current_user)):
    """Mapa de calor de sectores: variación del día de cada sector del S&P (vía sus ETFs).
    Contexto de mercado de un vistazo. Cotizaciones ligeras (Finnhub), cacheado 5 min."""
    cached = _cache.get("market_heatmap")
    if cached is not None:
        return cached
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(6)

    async def _q(sym):
        async with sem:
            q = await loop.run_in_executor(None, market_data.get_quote_fast, sym)
            if not q:
                q = await loop.run_in_executor(None, market_data.get_quote, sym)
            return q

    quotes = await asyncio.gather(*[_q(s) for s, _ in _SECTOR_ETFS], return_exceptions=True)
    out = []
    for (sym, name), q in zip(_SECTOR_ETFS, quotes):
        if isinstance(q, dict) and q.get("change_percent") is not None:
            out.append({"symbol": sym, "sector": name,
                        "change_percent": round(float(q["change_percent"]), 2)})
    out.sort(key=lambda x: x["change_percent"], reverse=True)
    result = {"sectors": out}
    if out:
        _cache.set("market_heatmap", result, ttl=300)  # 5 min
    return result


import re as _re_mod


def _clean_source(sender: str, subject: str) -> str:
    """Nombre legible de la fuente. Make a veces manda el 'from' como objeto JSON
    ({"address":"x@y.com","name":"The Daily Upside"}) o como 'Nombre <x@y.com>'."""
    s = sender or ""
    m = _re_mod.search(r'"name"\s*:\s*"([^"]+)"', s, _re_mod.I)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = _re_mod.match(r'\s*([^<@"]+?)\s*<', s)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = _re_mod.search(r'@([\w.-]+)', s)
    if m:
        dom = m.group(1).split(".")[0]
        return dom.replace("-", " ").title()
    return (subject or "Newsletter")[:40]


# Campos que realmente se leen de newsletter_summaries. `{"_id": 0}` NO es una proyección
# restrictiva: quita el _id y trae TODO lo demás, incluido el cuerpo crudo del email, que es
# lo gordo. Medido: ~3,6 MB por consulta, tres veces (aquí, en /fuentes y en /radar), y
# /fuentes está en el camino de cada cambio de ticker. Pidiendo solo estos cuatro campos
# viajan unos pocos KB.
_PROYECCION_NEWSLETTER = {"_id": 0, "received_at": 1, "sender": 1, "subject": 1,
                          "extracted": 1}

# Las newsletters llegan a lo sumo unas cuantas veces al día, pero la lectura de los últimos
# 30 días se hacía en CADA cambio de acción (el panel "Tus fuentes"), y otra vez en /radar y
# en el mapa de menciones. Medido en producción: ~985 ms del camino de cambiar de acción,
# aun con la proyección puesta.
#
# No se puede filtrar por ticker en Mongo: newsletter_ingest guarda el ticker tal cual lo
# devuelve la IA (el .strip().upper() está solo en la LECTURA), así que una igualdad contra
# el símbolo en mayúsculas perdería menciones guardadas en minúsculas. Se cachea la lectura
# entera y se filtra en memoria, que además sirve a los tres sitios a la vez.
_TTL_NEWSLETTERS = 600  # 10 min


async def _newsletters_recientes(days: int, limite: int = 300):
    """Documentos de los últimos `days` días, cacheados. Devuelve SIEMPRE una lista."""
    from datetime import timedelta
    ck = f"newsletters:{days}:{limite}"
    v = _cache.get(ck)
    if v is not None:
        return v
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = await db.newsletter_summaries.find(
        {"received_at": {"$gte": cutoff}}, _PROYECCION_NEWSLETTER
    ).sort("received_at", -1).to_list(limite)
    _cache.set(ck, docs, ttl=_TTL_NEWSLETTERS)
    return docs


async def _mentions_by_ticker(days: int = 30) -> dict:
    """Mapa ticker → {menciones, positivos, negativos, fuentes} desde lo que dicen tus
    fuentes (Telegram + newsletters) en los últimos `days` días."""
    docs = await _newsletters_recientes(days, 300)
    out: dict = {}
    for d in docs:
        ex = d.get("extracted") or {}
        src = _clean_source(d.get("sender"), d.get("subject"))
        for a in (ex.get("acciones") or []):
            tk = (a.get("ticker") or "").strip().upper()
            if not tk:
                continue
            slot = out.setdefault(tk, {"menciones": 0, "positivos": 0, "negativos": 0, "fuentes": set()})
            slot["menciones"] += 1
            slot["fuentes"].add(src)
            sent = (a.get("sentimiento") or "").upper()
            if sent == "POSITIVO":
                slot["positivos"] += 1
            elif sent == "NEGATIVO":
                slot["negativos"] += 1
    for tk, s in out.items():
        s["fuentes"] = sorted(s["fuentes"])
    return out


@api_router.get("/fuentes/{symbol}")
async def fuentes_de_accion(symbol: str, days: int = 30,
                            _user: str = Depends(auth.get_current_user)):
    """Qué han dicho TUS fuentes (Telegram + newsletters) de esta acción: cada mención
    con su fuente, sentimiento, tesis y fecha. Para mostrarlo junto al análisis."""
    sym = symbol.strip().upper()
    docs = await _newsletters_recientes(days, 300)
    menciones, pos, neg = [], 0, 0
    for d in docs:
        ex = d.get("extracted") or {}
        src = _clean_source(d.get("sender"), d.get("subject"))
        for a in (ex.get("acciones") or []):
            if (a.get("ticker") or "").strip().upper() != sym:
                continue
            sent = (a.get("sentimiento") or "").upper()
            if sent == "POSITIVO":
                pos += 1
            elif sent == "NEGATIVO":
                neg += 1
            menciones.append({
                "fuente": src, "accion": a.get("accion"), "sentimiento": sent or None,
                "niveles": a.get("niveles"), "motivo": a.get("motivo"),
                "fecha": d.get("received_at"),
            })
    # Fuentes DISTINTAS, no menciones: cuarenta correos del mismo boletin son una sola
    # opinion repetida, y el consenso mide cuanta gente distinta lo dice.
    fuentes_distintas = {m["fuente"] for m in menciones if m.get("fuente")}
    # La elegibilidad estructural, de HOY. Antes aqui se leia un score guardado con la
    # mencion, que podia tener semanas; la tendencia sale del historico diario cacheado y
    # de fuente gratuita, asi que ademas cuesta menos que lo que sustituye.
    estado_tendencia = await asyncio.to_thread(market_data.tendencia_de, sym)

    return {"symbol": sym, "n": len(menciones), "positivos": pos, "negativos": neg,
            "menciones": menciones[:20],
            "confluencia": confluencia_mod.evaluar(len(fuentes_distintas), pos, neg,
                                                   estado_tendencia)}


# ---------- Radar: inteligencia acumulada de todas las newsletters ----------
@api_router.get("/radar")
async def radar(days: int = 14, _user: str = Depends(auth.get_current_user)):
    """Recopila TODA la información de las newsletters recibidas en los últimos `days` días
    y la divide en dos: (1) ACCIONES agregadas (cada ticker, cuántas fuentes lo mencionan,
    con qué ángulo y el veredicto del motor), y (2) INFORMACIÓN (feed de resúmenes)."""
    docs = await _newsletters_recientes(days, 200)

    # 1) Feed de información
    info_feed = []
    # 2) Acciones agregadas por ticker
    by_ticker = {}

    for d in docs:
        ex = d.get("extracted") or {}
        src_short = _clean_source(d.get("sender"), d.get("subject"))
        when = d.get("received_at")
        if ex.get("resumen"):
            info_feed.append({
                "titulo": ex.get("titulo") or d.get("subject"),
                "resumen": ex.get("resumen"),
                "fuente": src_short,
                "fecha": when,
            })
        for a in (ex.get("acciones") or []):
            tk = (a.get("ticker") or "").strip().upper()
            if not tk:
                continue
            # Oculta patrocinadores/anuncios que se colaron antes del filtro de ingesta
            # (ej. "Oracle NetSuite" como patrocinador, no como idea de inversión).
            if newsletter_ingest._is_sponsor(a):
                continue
            slot = by_ticker.setdefault(tk, {
                "ticker": tk, "nombre": a.get("nombre") or "",
                "menciones": 0, "fuentes": set(), "angulos": [],
                "acciones_reco": set(), "ultima": when,
                "positivos": 0, "negativos": 0,
            })
            slot["menciones"] += 1
            slot["fuentes"].add(src_short)
            if a.get("motivo"):
                slot["angulos"].append(a["motivo"])
            if a.get("accion"):
                slot["acciones_reco"].add(a["accion"])
            sent = (a.get("sentimiento") or "").upper()
            if sent == "POSITIVO":
                slot["positivos"] += 1
            elif sent == "NEGATIVO":
                slot["negativos"] += 1
            # Guarda el veredicto del motor más reciente disponible.
            if not slot["nombre"] and a.get("nombre"):
                slot["nombre"] = a["nombre"]

    acciones = []
    for tk, s in by_ticker.items():
        acciones.append({
            "ticker": tk,
            "nombre": s["nombre"],
            "menciones": s["menciones"],
            "fuentes": sorted(s["fuentes"]),
            "n_fuentes": len(s["fuentes"]),
            "angulos": s["angulos"][:3],
            "recomendaciones": sorted(s["acciones_reco"]),
            "positivos": s["positivos"],
            "negativos": s["negativos"],
            "ultima": s["ultima"],
            # La confluencia se rellena despues, en bloque: hace falta la tendencia de
            # cada simbolo y resolverlas de una en una dentro de este bucle serializaria
            # 25 lecturas de historico.
            "confluencia": None,
        })
    # Ordena por nº de fuentes distintas (consenso) y menciones.
    acciones.sort(key=lambda x: (x["n_fuentes"], x["menciones"]), reverse=True)

    # La confluencia de TODAS las acciones que se devuelven, no solo de las 25 primeras.
    #
    # El limite de 25 pertenece al trabajo caro del Radar —refrescar el veredicto guardado
    # con llamadas a Finnhub—, no a la presencia del campo en la respuesta. Calcularla
    # solo para el top dejaba a los elementos 26 en adelante con `confluencia: None`, y
    # como el componente hace `confluencia ? ... : null`, esas tarjetas perdian el chip
    # sin que fallara nada: una degradacion silenciosa.
    #
    # La tendencia sale del historico diario, que `market_data.tendencia_de` ya cachea 15
    # minutos y lee de fuente gratuita — no toca Finnhub. Se resuelven EN PARALELO sobre
    # hilos: de una en una bloquearian la peticion aunque cada una acierte en cache.
    if acciones:
        tendencias = await asyncio.gather(*[
            asyncio.to_thread(market_data.tendencia_de, item["ticker"]) for item in acciones
        ], return_exceptions=True)
        for item, tend in zip(acciones, tendencias):
            # Un fallo suelto no puede tumbar el Radar entero: SIN_DATOS no autoriza
            # nada y se lee como lo que es, «no se ha podido clasificar».
            estado_t = tend if isinstance(tend, str) else "SIN_DATOS"
            item["confluencia"] = confluencia_mod.evaluar(
                item["n_fuentes"], item["positivos"], item["negativos"], estado_t)

    return {
        "days": days,
        "total_newsletters": len(docs),
        "acciones": acciones,
        "informacion": info_feed[:40],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@api_router.api_route("/inbound/news/ingest", methods=["GET", "POST"])
async def inbound_news_ingest(_user: str = Depends(auth.get_current_user)):
    """Dispara la ingesta de noticias de mercado al vuelo (para probar). Protegido."""
    import news_ingest
    return await news_ingest.ingest_general_news(db)


@api_router.post("/youtube/ingest")
async def youtube_ingest_ep(request: Request, _user: str = Depends(auth.get_current_user)):
    """Ingiere un vídeo de YouTube al cerebro/Radar y devuelve qué ha conseguido."""
    import youtube_ingest
    payload = await request.json()
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "Falta el enlace del vídeo.")
    return await youtube_ingest.ingest_youtube(db, url)


@api_router.post("/ingest/text")
async def ingest_text_ep(request: Request, _user: str = Depends(auth.get_current_user)):
    """Ingiere TEXTO pegado a mano (transcripción de vídeo, artículo, etc.) al cerebro/
    Radar. Es la vía 100% fiable cuando YouTube/webs bloquean al servidor."""
    import newsletter_ingest
    payload = await request.json()
    text = (payload.get("text") or "").strip()
    fuente = (payload.get("fuente") or "Texto pegado").strip()[:80]
    if len(text) < 60:
        raise HTTPException(400, "Pega un texto más largo (al menos unas frases).")
    r = await newsletter_ingest.ingest_message(db, fuente, text, tipo="manual")
    return {"ok": True, "chars": len(text), **r}


@api_router.get("/brain")
async def brain_overview(_user: str = Depends(auth.get_current_user)):
    """Estado del CEREBRO para la web: qué ha capturado (feed de actividad), de qué
    fuentes, cuántos principios tiene y el conocimiento acumulado por categoría."""
    cached = _cache.get("brain_overview")
    if cached is not None:
        return cached
    import knowledge_base
    result = await knowledge_base.get_overview(db)
    _cache.set("brain_overview", result, ttl=30)
    return result


@api_router.get("/track-record")
async def track_record(days: int = 180, refresh: bool = False, _user: str = Depends(auth.get_current_user)):
    """Auto-examen del sistema: ¿funcionaron las señales de COMPRA del motor? Mira qué
    hizo el precio tras cada análisis (tocó antes TP1 = acierto, o stop = fallo).
    `refresh=true` salta la caché (para ver al instante una señal recién generada)."""
    if not refresh:
        cached = _cache.get(f"track_record_{days}")
        if cached is not None:
            return cached
    import track_record as tr
    result = await tr.compute_track_record(db, days=days)
    _cache.set(f"track_record_{days}", result, ttl=300)  # 5 min
    return result


# ---------- Watchlist ----------
@api_router.get("/watchlist")
async def list_watchlist(_user: str = Depends(auth.get_current_user)):
    cached = _cache.get("watchlist_with_quotes")
    if cached is not None:
        return cached
    items = await db.watchlist.find({}, {"_id": 0}).to_list(200)
    if not items:
        return []
    loop = asyncio.get_running_loop()
    # Límite de concurrencia: sin esto, una watchlist grande dispara N llamadas .info
    # simultáneas que saturan el pool de yfinance y el rate-limiter de Finnhub.
    sem = asyncio.Semaphore(5)

    async def _q(sym):
        async with sem:
            return await loop.run_in_executor(None, market_data.get_quote, sym)

    quotes = await asyncio.gather(
        *[_q(it["symbol"]) for it in items],
        return_exceptions=True,
    )
    result = [
        {**it, "quote": q if not isinstance(q, Exception) else None}
        for it, q in zip(items, quotes)
    ]
    _cache.set("watchlist_with_quotes", result, ttl=45)
    return result


@api_router.get("/watchlist/symbols")
async def list_watchlist_symbols(_user: str = Depends(auth.get_current_user)):
    """Solo los tickers de la watchlist (sin cotizaciones). Ligero: para que el botón de
    corazón sepa al instante si la acción actual ya está guardada."""
    items = await db.watchlist.find({}, {"_id": 0, "symbol": 1}).to_list(500)
    return [it["symbol"] for it in items if it.get("symbol")]


@api_router.post("/watchlist")
async def add_watchlist(item: WatchlistCreate, _user: str = Depends(auth.get_current_user)):
    symbol = item.symbol.upper().strip()
    existing = await db.watchlist.find_one({"symbol": symbol})
    if existing:
        raise HTTPException(409, f"{symbol} ya está en la watchlist")
    # validate symbol exists (solo existencia → quote rápido sin fundamentales)
    loop = asyncio.get_running_loop()
    q = await loop.run_in_executor(None, market_data.get_quote_fast, symbol)
    if not q:
        q = await loop.run_in_executor(None, market_data.get_quote, symbol)
    if not q:
        raise HTTPException(404, f"Símbolo no válido: {symbol}")
    obj = WatchlistItem(symbol=symbol)
    await db.watchlist.insert_one(obj.model_dump())
    _cache._store.pop("watchlist_with_quotes", None)
    return {**obj.model_dump(), "quote": q}


@api_router.delete("/watchlist/{symbol}")
async def remove_watchlist(symbol: str, _user: str = Depends(auth.get_current_user)):
    res = await db.watchlist.delete_one({"symbol": symbol.upper()})
    if res.deleted_count == 0:
        raise HTTPException(404, "No encontrado")
    _cache._store.pop("watchlist_with_quotes", None)
    return {"deleted": symbol.upper()}


# ---------- Correlación de la cartera (#22) ----------
@api_router.get("/portfolio/correlation")
async def portfolio_correlation(_user: str = Depends(auth.get_current_user)):
    """Correlación entre las acciones de la Cartera: detecta 'concentración oculta' —
    acciones que se mueven a la vez aunque sean de sectores distintos (si cae una, caen
    todas). Bajo demanda, cacheado 6h, con liberación de RAM (mem.trim) tras el cálculo."""
    cached = _cache.get("portfolio_corr")
    if cached is not None:
        return cached
    import pandas as pd
    import numpy as np

    rows = await db.signal_entries.find({"active": True}, {"_id": 0, "symbol": 1}).to_list(200)
    syms, seen = [], set()
    for r in rows:
        s = (r.get("symbol") or "").upper()
        if s and s not in seen:
            seen.add(s)
            syms.append(s)
    syms = syms[:25]  # techo: bounded en memoria
    if len(syms) < 2:
        return {"pairs": [], "avg_corr": None, "n": len(syms),
                "message": "Necesitas al menos 2 acciones en la Cartera para medir la correlación."}

    loop = asyncio.get_running_loop()
    series = {}
    for s in syms:
        try:
            df = await loop.run_in_executor(None, market_data.get_stock_data, s, "1Y")
            if df is None or df.empty or "Close" not in df.columns:
                continue
            series[s] = df.set_index("Date")["Close"].astype(float).tail(160)
        except Exception:
            continue
    mem.trim()
    if len(series) < 2:
        return {"pairs": [], "avg_corr": None, "n": len(series),
                "message": "No hay histórico suficiente para las acciones de la Cartera."}
    mat = pd.DataFrame(series).dropna()
    if len(mat) < 20:
        return {"pairs": [], "avg_corr": None, "n": len(series),
                "message": "Histórico común insuficiente entre las acciones."}
    corr = mat.pct_change().dropna().corr()
    cols = list(corr.columns)
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c = corr.iloc[i, j]
            if pd.notna(c):
                pairs.append({"a": cols[i], "b": cols[j], "corr": round(float(c), 2)})
    pairs.sort(key=lambda x: x["corr"], reverse=True)
    avg = round(float(np.mean([p["corr"] for p in pairs])), 2) if pairs else None
    result = {
        "n": len(cols),
        "avg_corr": avg,
        "pairs": pairs[:8],
        "high": [p for p in pairs if p["corr"] >= 0.7],
    }
    _cache.set("portfolio_corr", result, ttl=21600)  # 6h
    mem.trim()
    return result


# ---------- Price Alerts ----------
@api_router.get("/alerts")
async def list_alerts(_user: str = Depends(auth.get_current_user)):
    items = await db.alerts.find({}, {"_id": 0}).to_list(500)
    return items


@api_router.post("/alerts")
async def add_alert(item: PriceAlertCreate, _user: str = Depends(auth.get_current_user)):
    if item.direction not in ("above", "below"):
        raise HTTPException(400, "direction debe ser 'above' o 'below'")
    symbol = item.symbol.upper().strip()
    loop = asyncio.get_running_loop()
    q = await loop.run_in_executor(None, market_data.get_quote_fast, symbol)
    if not q:
        q = await loop.run_in_executor(None, market_data.get_quote, symbol)
    if not q:
        raise HTTPException(404, f"Símbolo no válido: {symbol}")
    obj = PriceAlert(
        symbol=symbol,
        target_price=float(item.target_price),
        direction=item.direction,
    )
    await db.alerts.insert_one(obj.model_dump())
    return obj.model_dump()


# Va ANTES de `/alerts/{alert_id}` por lo mismo que el bloque del Analista: con la ruta
# con parámetro por delante, DELETE /api/alerts/history intentaba borrar una alerta cuyo
# id fuera «history», no encontraba ninguna y devolvía 404 «Alerta no encontrada». Aquí
# el síntoma sí era visible, pero apuntaba al sitio equivocado: parecía que el historial
# no existía, no que la ruta estuviera tapada.
@api_router.delete("/alerts/history")
async def clear_alert_history(_user: str = Depends(auth.get_current_user)):
    """Borra todo el historial."""
    await db.alert_history.delete_many({})
    return {"ok": True}


@api_router.delete("/alerts/{alert_id}")
async def remove_alert(alert_id: str, _user: str = Depends(auth.get_current_user)):
    res = await db.alerts.delete_one({"id": alert_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Alerta no encontrada")
    return {"deleted": alert_id}


# ---------- Market overview (popular tickers) ----------
@api_router.get("/market/popular")
async def popular_stocks(_user: str = Depends(auth.get_current_user)):
    cached = _cache.get("popular")
    if cached:
        return cached
    symbols = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META", "AMD"]
    loop = asyncio.get_running_loop()
    quotes = await asyncio.gather(
        *[loop.run_in_executor(None, market_data.get_quote, s) for s in symbols],
        return_exceptions=True,
    )
    out = [q for q in quotes if q and not isinstance(q, Exception)]
    _cache.set("popular", out, ttl=120)  # 2 min
    return out


# ---------- Analyst consensus & sentiment ----------
# ---------- Analista Institucional ----------
# ORDEN IMPORTANTE: estas dos rutas van ANTES de `/analyst/{symbol}`. FastAPI resuelve
# por orden de registro, así que una ruta con parámetro declarada antes se traga
# cualquier ruta estática que comparta prefijo. Con `/analyst/{symbol}` por delante,
# GET /api/analyst/ideas devolvía el consenso de analistas del «símbolo» IDEAS —
# 200 OK, cuerpo con sentido, y el endpoint correcto inalcanzable. Un 404 se habría
# visto; esto no.
@api_router.get("/analyst/ideas")
async def analyst_ideas(limit: int = 30, _user: str = Depends(auth.get_current_user)):
    """Histórico de ideas que el Analista Institucional ha detectado (más recientes primero)."""
    items = await db.analyst_ideas.find({}, {"_id": 0}).sort("detected_at", -1).limit(limit).to_list(limit)
    return {"ideas": items}


@api_router.post("/analyst/scan")
async def analyst_scan(notify: bool = False, _user: str = Depends(auth.get_current_user)):
    """Lanza un barrido manual del Analista Institucional. Con notify=false solo devuelve
    las candidatas (para probar sin enviar Telegram); con notify=true además avisa."""
    return await daily_analyst.scan(db, notify=notify)


@api_router.get("/analyst/{symbol}")
async def analyst_data(symbol: str, _user: str = Depends(auth.get_current_user)):
    sym = symbol.upper()
    cached = _cache.get(f"analyst:{sym}")
    if cached:
        return cached
    loop = asyncio.get_running_loop()
    # Estas llamadas usan requests (red) + posibles sleeps de rate-limit: NUNCA en el
    # event loop, o con 0.1 CPU bloquean todas las demás peticiones.
    trends, target = await asyncio.gather(
        loop.run_in_executor(None, external_data.finnhub_recommendation_trends, sym),
        loop.run_in_executor(None, external_data.finnhub_price_target, sym),
    )
    consensus = external_data.aggregate_recommendation(trends)
    result = {"symbol": sym, "consensus": consensus, "price_target": target}
    _cache.set(f"analyst:{sym}", result, ttl=604800)  # 7 días — Finnhub actualiza mensualmente
    return result


@api_router.get("/sentiment/{symbol}")
async def sentiment_news(symbol: str, _user: str = Depends(auth.get_current_user)):
    sym = symbol.upper()
    cached = _cache.get(f"sentiment:{sym}")
    if cached:
        return cached
    loop = asyncio.get_running_loop()
    items = await loop.run_in_executor(None, external_data.alpha_sentiment_news, sym) or []
    scores = [i["ticker_sentiment_score"] for i in items if i.get("ticker_sentiment_score") is not None]
    avg = round(sum(scores) / len(scores), 3) if scores else None
    label = None
    if avg is not None:
        if avg >= 0.35:
            label = "MUY POSITIVO"
        elif avg >= 0.15:
            label = "POSITIVO"
        elif avg <= -0.35:
            label = "MUY NEGATIVO"
        elif avg <= -0.15:
            label = "NEGATIVO"
        else:
            label = "NEUTRO"
    result = {"symbol": sym, "average_score": avg, "label": label, "items": items}
    _cache.set(f"sentiment:{sym}", result, ttl=86400)  # 24h — Alpha Vantage: 5 calls/min
    return result


# ---------- Earnings Calendar ----------
@api_router.get("/calendar/earnings")
async def earnings_calendar(days: int = 14, symbols: Optional[str] = None, refresh: bool = False, _user: str = Depends(auth.get_current_user)):
    """Upcoming earnings from Finnhub. Always fetches 60 days and caches by symbols only;
    the day range is then filtered in-memory so every day-filter combo shares the same cache.
    `refresh=true` salta la caché (para forzar datos frescos)."""
    from datetime import datetime, timedelta
    sym_list = sorted({s.strip().upper() for s in symbols.split(",") if s.strip()}) if symbols else []
    # Cache key ignores `days` — we always fetch 60d and slice in memory
    cache_key = f"earnings60:{','.join(sym_list)}"
    cached = None if refresh else _cache.get(cache_key)
    if cached is None:
        sym_filter = set(sym_list) if sym_list else None
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            None, lambda: external_data.finnhub_earnings_calendar(days=60, symbols=sym_filter)
        )
        cached = data or {"items": []}
        _cache.set(cache_key, cached, ttl=1800)  # 30 min

    # Ventana: desde HOY hasta +days. Y deduplica por símbolo (Finnhub a veces devuelve
    # la misma acción con dos fechas → salía repetida): nos quedamos con la MÁS CERCANA.
    hoy = datetime.now(timezone.utc).date().isoformat()
    cutoff = (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()
    permitido = set(sym_list) if sym_list else None
    por_symbol: dict = {}
    for it in (cached.get("items") or []):
        d = it.get("date") or ""
        sym = (it.get("symbol") or "").upper()
        if not (hoy <= d <= cutoff):
            continue
        if permitido is not None and sym not in permitido:
            continue  # solo tus acciones de Alertas
        if sym not in por_symbol or d < por_symbol[sym]["date"]:
            por_symbol[sym] = it
    filtered = sorted(por_symbol.values(), key=lambda x: x.get("date") or "")
    return {"items": filtered}


# ---------- Analysis History ----------
@api_router.get("/history/{symbol}")
async def history_by_symbol(symbol: str, limit: int = 20, _user: str = Depends(auth.get_current_user)):
    sym = symbol.upper()
    try:
        cursor = (
            db.analyses.find({"symbol": sym}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        return {"symbol": sym, "items": items}
    except Exception as e:
        logger.exception(f"history error: {e}")
        return {"symbol": sym, "items": []}


@api_router.get("/history")
async def history_all(limit: int = 30, _user: str = Depends(auth.get_current_user)):
    try:
        cursor = (
            db.analyses.find({}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        items = await cursor.to_list(limit)
        return {"items": items}
    except Exception as e:
        logger.exception(f"history_all error: {e}")
        return {"items": []}


# ---------- Test email ----------
@api_router.post("/alerts/test-email")
async def test_email(_user: str = Depends(auth.get_current_user)):
    """Requiere auth: cada llamada envía un email REAL. Sin credencial, cualquiera podía
    quemar la cuota del proveedor de correo (o usarlo para machacar tu bandeja) en bucle."""
    sent, err = await alerts_worker.send_alert_email("TEST", 100.0, "above", 105.0, 5.0)
    if not sent:
        raise HTTPException(500, err or "No se pudo enviar email de prueba")
    return {"ok": True}


@api_router.post("/alerts/test-telegram")
async def test_telegram(grupo: Optional[str] = None, _user: str = Depends(auth.get_current_user)):
    import telegram_notifier
    sent, err = await telegram_notifier.send_test(grupo=grupo)
    if not sent:
        raise HTTPException(500, err or "No se pudo enviar mensaje de Telegram")
    return {"ok": True}


# ---------- Daily Opportunities ----------
@api_router.get("/opportunities/daily")
async def daily_opportunities(refresh: bool = False,
                              _user: str = Depends(auth.get_current_user)):
    # refresh=true fuerza un rescan completo (pesado); sin auth cualquiera podía dispararlo.
    data = await opportunities.scan_daily_opportunities(force_refresh=refresh)
    return data


def _sector_heat(results: list) -> dict:
    """Calcula el 'calor' de cada sector EN VIVO (dónde va el dinero), combinando dos
    señales, sin listas fijas — se adapta solo:
      1) Mercado: momentum de las acciones del sector (cuánto de cerca de máximos están).
      2) Tus fuentes: cuánto mencionan tus jefes/newsletters acciones de ese sector.
    Devuelve heat normalizado 0..1 por sector."""
    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "mom": 0.0, "ment": 0})
    for r in results:
        sec = r.get("sector")
        if not sec:
            continue
        a = agg[sec]
        a["n"] += 1
        d = r.get("dist_52w_high")           # negativo: -3 = a 3% de máximos (fuerte)
        if isinstance(d, (int, float)):
            a["mom"] += max(0.0, 20.0 + d)   # 0..20 (0 = a 20% o más de máximos)
        f = r.get("fuentes")
        if isinstance(f, dict):
            a["ment"] += f.get("menciones", 0)
    heat = {}
    for sec, a in agg.items():
        avg_mom = a["mom"] / a["n"] if a["n"] else 0.0   # 0..20 (mercado)
        heat[sec] = avg_mom + 5.0 * a["ment"]            # + interés de tus fuentes
    if heat:
        lo, hi = min(heat.values()), max(heat.values())
        rng = (hi - lo) or 1.0
        heat = {k: round((v - lo) / rng, 3) for k, v in heat.items()}
    return heat


def _top_seleccion(results: list, heat: dict, n: int = 5) -> list:
    """La 'Top Selección': los N mejores ponderando el potential_score por el CALOR del
    sector (adaptativo). Un sector caliente sube sus acciones; uno frío las baja — sin
    listas fijas, se actualiza solo según a dónde va el dinero."""
    def efectivo(r):
        base = r.get("potential_score") or 0
        h = heat.get(r.get("sector"), 0.5)   # sin dato → neutro
        return base * (0.85 + 0.30 * h)      # sector caliente hasta +30%, frío −15%
    top = sorted(results, key=efectivo, reverse=True)[:n]
    out = []
    for r in top:
        razones = []
        rg = r.get("revenue_growth")
        if isinstance(rg, (int, float)):
            razones.append(f"ventas +{round(rg)}%")
        d = r.get("dist_52w_high")
        if isinstance(d, (int, float)) and d >= -8:
            razones.append("cerca de máximos")
        cs = r.get("consensus_score")
        if isinstance(cs, (int, float)) and cs >= 70:
            razones.append("consenso analista fuerte")
        # La razón «momentum sano» se retira. NO era un veto —solo añadía una frase— pero
        # salía del mismo sitio que los dos vetos que acabamos de migrar: de comprobar si
        # una etiqueta de texto empezaba por «⚠». Mientras quede una sola lectura de ese
        # prefijo, el veto puede volver por ahí sin que nadie lo note, así que se va con
        # ellos y el test de arquitectura puede exigir CERO apariciones en vez de una lista
        # de excepciones. Top Selección está congelada hasta que exista `tendencia_score`;
        # reponer la razón con otro origen sería migrar un consumidor bloqueado.
        if heat.get(r.get("sector"), 0) >= 0.75:
            razones.append("sector caliente 🔥")
        out.append({
            "symbol": r.get("symbol"), "name": r.get("name"),
            "potential_score": r.get("potential_score"), "sector": r.get("sector"),
            "motivo": ", ".join(razones) or "cumple todos los filtros de crecimiento",
        })
    return out


@api_router.get("/opportunities/screener")
async def growth_screener(refresh: bool = False,
                          _user: str = Depends(auth.get_current_user)):
    """Growth screener: 7 hard filters (market cap, price, no dividend, volume,
    near 52w high, revenue growth, EPS growth) over a curated growth universe.
    Anota qué acciones mencionan TUS fuentes y añade la 'Top Selección' (mejores 3-5)."""
    data = await opportunities.scan_growth_screener(force_refresh=refresh)
    results = data.get("results") or []
    try:
        mentions = await _mentions_by_ticker(30)
        annotated, con_fuentes = [], []
        for r in results:
            tk = (r.get("symbol") or "").strip().upper()
            m = mentions.get(tk) if mentions else None
            if m:
                annotated.append({**r, "fuentes": m})
                con_fuentes.append(tk)
            else:
                annotated.append(r)
        heat = _sector_heat(annotated)
        # Sectores calientes: top por calor, solo los con varias acciones (señal fiable).
        conteo = {}
        for r in annotated:
            s = r.get("sector")
            if s:
                conteo[s] = conteo.get(s, 0) + 1
        calientes = sorted([s for s in heat if conteo.get(s, 0) >= 2],
                           key=lambda s: heat[s], reverse=True)[:5]
        data = {**data, "results": annotated, "con_fuentes": con_fuentes,
                "top_seleccion": _top_seleccion(annotated, heat),
                "sectores_calientes": [{"sector": s, "heat": heat[s]} for s in calientes]}
    except Exception:
        logger.warning("screener: no se pudieron anotar menciones/top selección")
        data = {**data, "top_seleccion": _top_seleccion(results, _sector_heat(results))}
    return data


@api_router.get("/opportunities/score/{symbol}")
async def desglose_del_score(symbol: str, _user: str = Depends(auth.get_current_user)):
    """El desglose de los puntos que componen el score de potencial.

    SOLO LECTURA DE CACHE. El escaneo del screener ya calcula este desglose por dentro;
    aqui se sirve el que quedo guardado. No se recalcula: recalcular exigiria
    fundamentales, cotizacion y consenso —o sea Finnhub— por cada vez que alguien abre un
    detalle, y eso es justo lo que este diseño evita.

    Va aparte y no dentro de /opportunities/screener porque ese endpoint devuelve la lista
    ENTERA desde cache: meter siete componentes en cada resultado son unos 70 KB en cada
    carga, para algo que se despliega en dos o tres acciones.
    """
    d = opportunities.desglose_de(symbol)
    if d is None:
        raise HTTPException(
            404,
            f"El desglose de '{symbol.upper()}' no esta disponible en la cache actual del "
            f"screener. Se recalculara en el proximo escaneo.",
        )
    return d


@api_router.get("/alternativa/{symbol}")
async def alternativa_sectorial(symbol: str, _user: str = Depends(auth.get_current_user)):
    """Sugiere otra acción del MISMO sector con mejores métricas (mayor potential_score)
    que la analizada, tomada del screener growth. Para descubrir mejores oportunidades."""
    sym = symbol.strip().upper()
    data = await opportunities.scan_growth_screener()
    results = data.get("results") or []
    # Sector e INDUSTRIA de la acción: del screener si está, si no de la cotización.
    propia = next((r for r in results if (r.get("symbol") or "").upper() == sym), None)
    sector = propia.get("sector") if propia else None
    industry = propia.get("industry") if propia else None
    mi_score = propia.get("potential_score") if propia else None
    if not sector or not industry:
        try:
            q = await asyncio.to_thread(market_data.get_quote, sym)
            sector = sector or (q or {}).get("sector")
            industry = industry or (q or {}).get("industry")
        except Exception:
            pass
    if not sector and not industry:
        return {"symbol": sym, "sector": None, "alternativas": []}

    def _mejores(pred):
        c = [r for r in results
             if pred(r) and (r.get("symbol") or "").upper() != sym
             and (mi_score is None or (r.get("potential_score") or 0) > (mi_score or 0))]
        c.sort(key=lambda x: x.get("potential_score") or 0, reverse=True)
        return c

    # 1) Peers REALES: misma industria (p.ej. "Semiconductors", no todo "Technology").
    #    Comparar ASTS (satélites) con NVDA (GPUs) no tiene sentido aunque compartan sector.
    cands, grupo = [], industry
    if industry:
        cands = _mejores(lambda r: r.get("industry") == industry)
        # Conocemos la industria: si no hay peer real, NO caemos a sector (evita comparar
        # satélites con GPUs). El panel se ocultará — mejor eso que una alternativa absurda.
    elif sector:
        # 2) Solo si NO sabemos la industria usamos el sector amplio como último recurso.
        cands = _mejores(lambda r: r.get("sector") == sector)
        grupo = sector
    alts = [{"symbol": r["symbol"], "name": r.get("name"),
             "potential_score": r.get("potential_score"),
             "revenue_growth": r.get("revenue_growth"),
             "dist_52w_high": r.get("dist_52w_high")} for r in cands[:2]]
    return {"symbol": sym, "sector": sector, "industry": industry,
            "grupo": grupo, "alternativas": alts}



# ---------- Newsletter (Capa 3): buzón de entrada ----------
def _newsletter_body_from(payload: dict) -> tuple:
    """Extrae (subject, html, text, sender) de los formatos comunes de servicios de
    email entrante (Mailgun, SendGrid, Cloudflare, o un JSON genérico)."""
    subject = payload.get("subject") or payload.get("Subject") or ""
    html = (payload.get("html") or payload.get("body-html") or payload.get("HtmlBody")
            or payload.get("body_html") or "")
    text = (payload.get("text") or payload.get("body-plain") or payload.get("TextBody")
            or payload.get("body_text") or payload.get("body") or "")
    sender = (payload.get("from") or payload.get("sender") or payload.get("From") or "")
    return subject, html, text, sender


# ---------- Lector de Telegram (alimenta el cerebro con tu grupo de pago) ----------
def _check_inbound_token(token: str):
    """Valida el secreto compartido de la ingesta máquina-a-máquina.

    `compare_digest` en vez de `!=`: comparar cadenas con el operador normal sale antes
    cuanto antes difieran, y ese tiempo es medible. Aquí el secreto no caduca ni se rota
    solo, así que un atacante tiene todos los intentos que quiera para adivinarlo carácter
    a carácter. La comparación de tiempo constante quita esa pista y no cuesta nada.

    Sigue siendo a prueba de fallos: sin la variable de entorno, deniega.
    """
    secret = os.environ.get("INBOUND_SECRET")
    if not secret or not hmac.compare_digest(token or "", secret):
        raise HTTPException(401, "Token de entrada inválido.")


@api_router.get("/telegram/status")
async def telegram_status(x_inbound_token: str = Header(default="")):
    _check_inbound_token(x_inbound_token)
    import telegram_reader
    return await telegram_reader.status(db)


@api_router.post("/telegram/login/start")
async def telegram_login_start(request: Request, x_inbound_token: str = Header(default="")):
    _check_inbound_token(x_inbound_token)
    import telegram_reader
    payload = await request.json()
    phone = (payload.get("phone") or "").strip()
    if not phone:
        raise HTTPException(400, "Falta el teléfono (con prefijo, ej. +34...).")
    return await telegram_reader.login_start(phone)


@api_router.post("/telegram/login/code")
async def telegram_login_code(request: Request, x_inbound_token: str = Header(default="")):
    _check_inbound_token(x_inbound_token)
    import telegram_reader
    payload = await request.json()
    return await telegram_reader.login_code(
        db, str(payload.get("code") or "").strip(), str(payload.get("password") or "").strip())


@api_router.get("/telegram/dialogs")
async def telegram_dialogs(x_inbound_token: str = Header(default="")):
    _check_inbound_token(x_inbound_token)
    import telegram_reader
    return await telegram_reader.list_dialogs(db)


@api_router.post("/telegram/capture")
async def telegram_capture(request: Request, x_inbound_token: str = Header(default="")):
    _check_inbound_token(x_inbound_token)
    import telegram_reader
    payload = await request.json()
    return await telegram_reader.set_capture(db, payload.get("chat_ids") or [])


@api_router.post("/inbound/newsletter")
async def inbound_newsletter(request: Request, token: str = ""):
    """Buzón que recibe una newsletter reenviada y devuelve un resumen destilado por email.
    Protegido con un secreto (?token=... o cabecera X-Inbound-Token) para que solo el
    conector de email autorizado pueda dispararlo. Acepta JSON o form-urlencoded."""
    secret = os.environ.get("INBOUND_SECRET")
    if not secret:
        raise HTTPException(503, "INBOUND_SECRET no configurado en el servidor.")
    por_cabecera = request.headers.get("x-inbound-token") or ""
    # La cabecera manda; el query param se sigue aceptando A PROPÓSITO. Es el único
    # endpoint que llama una máquina externa —el conector de correo—, y cerrarlo sin
    # que esté reconfigurado dejaría de alimentar el Cerebro sin avisar.
    provided = por_cabecera or token or ""
    if not hmac.compare_digest(provided, secret):
        raise HTTPException(401, "Token de entrada inválido.")
    if not por_cabecera and token:
        # Cuando este aviso deje de aparecer, el conector ya usa cabecera y se puede
        # cerrar el query param. Mientras salga, cerrarlo rompería la ingesta.
        logger.warning(
            "INBOUND: /inbound/newsletter autenticado por QUERY PARAM. El secreto viaja "
            "en la URL y queda en logs de proxies e historiales. Reconfigura el conector "
            "para que mande la cabecera X-Inbound-Token; cuando este aviso desaparezca, "
            "se podrá cerrar el parámetro.")

    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        payload = await request.json()
    else:
        form = await request.form()
        payload = {k: v for k, v in form.items()}

    subject, html, text, sender = _newsletter_body_from(payload)

    # Procesa en SEGUNDO PLANO y responde al instante. La extracción con IA + el cruce
    # de tickers (quotes/financials/consenso) puede tardar >40s en Render free, y Make
    # corta la conexión a los 40s ("timeout of 40000ms exceeded") y acaba desactivando
    # el escenario. Devolviendo 200 de inmediato, Make nunca hace timeout.
    async def _bg():
        try:
            await newsletter_ingest.process_newsletter(db, subject, html, text, sender)
        except Exception:
            logger.exception("newsletter: procesado en segundo plano falló")

    task = asyncio.create_task(_bg())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return {"ok": True, "queued": True}


@api_router.api_route("/inbound/newsletter/backfill-knowledge", methods=["GET", "POST"])
async def inbound_newsletter_backfill(limit: int = 200, _user: str = Depends(auth.get_current_user)):
    """Reprocesa los correos ya guardados para poblar el cerebro (investing_knowledge)
    con el método/sabiduría que enseñan. Protegido con INBOUND_SECRET. Acepta GET para
    poder lanzarlo tocando un enlace desde el móvil."""

    # Reprocesar N correos con una llamada al LLM cada uno tarda minutos: si se hace de
    # forma síncrona, el navegador/Render cortan ("server stopped responding"). Se lanza
    # en segundo plano y se responde al instante; el progreso se ve en /knowledge.
    async def _bg():
        try:
            res = await newsletter_ingest.backfill_knowledge(db, limit=limit)
            logger.info("backfill cerebro: %s", res)
        except Exception:
            logger.exception("backfill cerebro falló")

    task = asyncio.create_task(_bg())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return {"ok": True, "queued": True,
            "mensaje": "Backfill en marcha en segundo plano. Mira el progreso en "
                       "/api/inbound/newsletter/knowledge?token=..."}


@api_router.api_route("/inbound/newsletter/dedupe-knowledge", methods=["GET", "POST"])
async def inbound_newsletter_dedupe(_user: str = Depends(auth.get_current_user)):
    """Fusiona principios casi idénticos del cerebro (dedup semántico) y reconstruye el
    cache. Protegido con INBOUND_SECRET. Acepta GET para lanzarlo desde el móvil."""
    import knowledge_base
    result = await knowledge_base.dedupe_semantic(db)
    return {"ok": True, **result}


@api_router.api_route("/inbound/newsletter/dedupe-knowledge-llm", methods=["GET", "POST"])
async def inbound_newsletter_dedupe_llm(_user: str = Depends(auth.get_current_user)):
    """Dedup SEMÁNTICO con LLM (entiende paráfrasis) del cerebro. Tarda (varias llamadas
    al modelo), así que va en segundo plano; mira el resultado en /knowledge (baja el nº
    de principios). Protegido con INBOUND_SECRET."""
    import knowledge_base

    async def _bg():
        try:
            res = await knowledge_base.dedupe_semantic_llm(db)
            logger.info("dedupe-llm cerebro: %s", res)
        except Exception:
            logger.exception("dedupe-llm cerebro falló")

    task = asyncio.create_task(_bg())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return {"ok": True, "queued": True,
            "mensaje": "Dedup semántico en marcha en segundo plano. Mira el nº de "
                       "principios en /api/inbound/newsletter/knowledge?token=..."}


@api_router.api_route("/inbound/newsletter/fix-encoding", methods=["GET", "POST"])
async def inbound_newsletter_fix_encoding(_user: str = Depends(auth.get_current_user)):
    """Repara el mojibake (acentos corruptos: 'selecciÃ³n' → 'selección') de los
    principios ya guardados en el cerebro y reconstruye el cache. Acepta GET para
    lanzarlo desde el móvil."""
    import knowledge_base
    result = await knowledge_base.fix_existing_encoding(db)
    return {"ok": True, **result}


@api_router.get("/inbound/newsletter/knowledge")
async def inbound_newsletter_knowledge(_user: str = Depends(auth.get_current_user)):
    """Estado del cerebro: cuántos principios ha aprendido y el digest actual."""
    import knowledge_base
    total = await db.investing_knowledge.count_documents({})
    top = await db.investing_knowledge.find({}, {"_id": 0}).sort(
        "refuerzos", -1).to_list(50)
    # Diagnóstico de codificación: repr con escapes unicode del primer principio, para
    # distinguir mojibake real en BD de un simple artefacto de visualización/caché.
    muestra = top[0].get("principio") if top else ""
    dbg = {
        "raw_repr": ascii(muestra),
        "tiene_marca_mojibake": any(m in (muestra or "") for m in ("Ã", "â€", "Â")),
        "reparado": knowledge_base.fix_mojibake(muestra or ""),
    }
    return {"_encoding_debug": dbg, "principios": total,
            "digest_inyectado": knowledge_base._DIGEST, "top": top}


@api_router.get("/inbound/newsletter/debug")
async def inbound_newsletter_debug(_user: str = Depends(auth.get_current_user)):
    """Diagnóstico: devuelve el resultado de los últimos procesados de newsletter
    (extracción / envío de email) para depurar sin acceso a los logs de Render.
    Protegido con el mismo INBOUND_SECRET."""
    return {
        "resend_configurado": bool(os.environ.get("RESEND_API_KEY")),
        "destino": (os.environ.get("ANALYST_RECIPIENT_EMAIL")
                    or os.environ.get("ALERT_RECIPIENT_EMAIL") or "(SIN DESTINO)"),
        "from": (os.environ.get("ALERT_FROM_EMAIL")
                 or os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"),
        "ultimos_procesados": newsletter_ingest._LAST_RUNS,
    }


@api_router.get("/backtest/{symbol}")
# Con auth: corre un backtest walk-forward COMPLETO por simbolo. Sin credencial era
# un amplificador de CPU gratis, igual que /debug/patterns.
async def backtest_levels(symbol: str, window: int = 60,
                          _user: str = Depends(auth.get_current_user)):
    """Walk-forward backtest of the confluence buy-levels engine for one symbol.
    Returns empirical hold rates by strength bucket (how often price actually
    bounced at each level type, with no lookahead). Cached 6h per symbol."""
    sym = symbol.upper()
    # Usa la caché ACOTADA (_TTLCache): antes era un dict de módulo sin límite que retenía
    # un resultado pesado por cada symbol:window distinto para siempre (leak con el uso).
    ck = f"bt:{sym}:{window}"
    cached = _cache.get(ck)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, market_data.get_full_indicator_history, sym)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No hay histórico suficiente para esta acción.")

    result = await loop.run_in_executor(
        None, lambda: backtest.backtest_symbol(df, forward_window=window)
    )
    result["symbol"] = sym
    # 24 h, antes 6 h. Es un backtest walk-forward sobre 2 años de velas DIARIAS: entre una
    # sesión y la siguiente el resultado cambia en una vela de 500, o sea nada apreciable.
    # A 6 h se recalculaba hasta cuatro veces al día para dar prácticamente lo mismo, y
    # medido en producción es ~1.100 ms — el panel más lento al cambiar de acción.
    _cache.set(ck, result, ttl=86400)
    mem.trim()  # el histórico (2 años) es un DataFrame grande: devuélvelo al SO
    return result


_universe_bt_lock = asyncio.Lock()


@api_router.get("/backtest")
async def backtest_universe_endpoint(window: int = 60, limit: int = 30, _user: str = Depends(auth.get_current_user)):
    """Aggregate walk-forward backtest across the opportunities universe. Pools
    hundreds of point-in-time touches so the hold-rate-by-strength is statistically
    meaningful (single symbols give too few samples). Heavy: cached 24h."""
    ck = f"btuniv:{window}:{limit}"
    cached = _cache.get(ck)  # caché acotada (antes dict de módulo sin límite)
    if cached is not None:
        return cached

    if _universe_bt_lock.locked():
        return {"status": "running", "message": "Backtest del universo en curso, vuelve en un minuto."}

    async with _universe_bt_lock:
        # Re-chequea dentro del lock por si otro request lo calculó mientras esperábamos.
        cached = _cache.get(ck)
        if cached is not None:
            return cached
        symbols = opportunities.UNIVERSE[:limit]
        loop = asyncio.get_event_loop()

        def _load(sym):
            return market_data.get_full_indicator_history(sym)

        result = await loop.run_in_executor(
            None, lambda: backtest.backtest_universe(_load, symbols, forward_window=window)
        )
        _cache.set(ck, result, ttl=86400)  # 24h
        mem.trim()  # backtest del universo: carga histórico de decenas de símbolos → libera al SO
        return result


@api_router.get("/market/futures")
async def market_futures(_user: str = Depends(auth.get_current_user)):
    """Index futures (S&P 500, Nasdaq 100, Dow) — trade ~24h, so they show where the
    market is heading before the equity pre-market opens."""
    cached = _cache.get("market_futures")
    if cached is not None:
        return cached
    loop = asyncio.get_running_loop()
    futs = [("ES=F", "S&P 500"), ("NQ=F", "Nasdaq 100"), ("YM=F", "Dow Jones")]

    async def _one(sym, label):
        q = await loop.run_in_executor(None, market_data.get_index_quote, sym)
        return {
            "symbol": sym,
            "label": label,
            "price": (q or {}).get("price"),
            "change_percent": (q or {}).get("change_percent"),
        }

    items = await asyncio.gather(*[_one(s, l) for s, l in futs])
    data = {"items": list(items)}
    _cache.set("market_futures", data, ttl=60)
    return data


#: Caché del panel de "más movidas". El plan GRATUITO de FMP son 250 peticiones al día y
#: este panel hace 3 llamadas por refresco. Con la caché de 10 min que había: 3 × 96
#: refrescos en 16 h = 288 peticiones/día — se pasaba del límite ÉL SOLO, y al agotarse FMP
#: devuelve listas vacías sin error, así que el panel se quedaba en blanco sin explicación.
#: A 30 min son 96/día, con margen de sobra. Los gainers del día no cambian tanto como para
#: notar la diferencia.
_MOVERS_TTL = int(os.environ.get("MOVERS_TTL", 1800))


@api_router.get("/market/movers")
async def market_movers(_user: str = Depends(auth.get_current_user)):
    """Biggest gainers / losers / most-active US stocks (Financial Modeling Prep).

    Con credencial porque cada llamada gasta 3 de las 250 peticiones diarias de FMP: sin
    auth, cualquiera podía dejarte sin cuota para el resto del día.
    """
    cached = _cache.get("market_movers")
    if cached is not None:
        return cached
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, fmp_data.get_market_movers)
    # Si las tres listas vienen vacías lo normal es que se haya agotado la cuota diaria:
    # FMP no devuelve error, devuelve nada. Sin este aviso el fallo es invisible.
    if isinstance(data, dict) and not any(data.get(k) for k in ("gainers", "losers", "actives")):
        logger.warning("FMP devolvió las 3 listas vacías — probable cuota diaria agotada "
                       "(plan gratuito: 250 peticiones/día)")
    _cache.set("market_movers", data, ttl=_MOVERS_TTL)
    return data


# ---------- Signal Table (puntos de compra/venta) ----------
@api_router.get("/signals")
async def list_signals(_user: str = Depends(auth.get_current_user)):
    # El worker actualiza last_price en MongoDB cada 60s, así que no
    # necesitamos llamar a Yahoo aquí. Respuesta instantánea desde DB.
    cached = _cache.get("signals_list")
    if cached is not None:
        return cached
    entries = await signal_table.list_entries(db)
    _cache.set("signals_list", entries, ttl=60)  # fresco para ver pre/post sin retraso
    return entries


@api_router.post("/signals")
async def create_signal(item: SignalEntryCreate, _user: str = Depends(auth.get_current_user)):
    # Evita DUPLICADOS: sin esto, "Añadir a Cartera" del Chartista creaba una 2ª fila del
    # mismo símbolo → P&L y diversificación contados dos veces y alertas de Telegram dobles.
    # El frontend ya sabe interpretar el 409 ("ya estaba en tu Cartera").
    sym = (item.symbol or "").upper().strip()
    if sym and await db.signal_entries.find_one({"symbol": sym}, {"_id": 0, "id": 1}):
        raise HTTPException(409, f"{sym} ya está en tu Cartera")
    datos = item.model_dump()
    # La puerta de tendencia, ANTES de cualquier escritura. La guarda del Chartista es de
    # cliente y una peticion directa se la salta; esta no.
    #
    # Va DESPUES del duplicado a proposito: aquel es una lectura de Mongo que ya se hacia,
    # y comprobarlo primero evita gastar una lectura de historico en un alta que iba a
    # fallar de todos modos.
    await _puerta_de_tendencia(sym, datos, item.forzar)
    entry = await signal_table.create_entry(db, datos)
    # Una cotización AL MOMENTO, aunque el mercado esté cerrado. El worker solo trabaja en
    # sesión, así que un valor añadido el sábado se quedaba sin precio ("—" en toda la fila)
    # hasta el lunes a las 15:30 — pasó con UBER. Una única llamada; si falla, el worker lo
    # rellenará igualmente al abrir.
    try:
        q = (await asyncio.to_thread(market_data.get_quote_fast, sym)
             or await asyncio.to_thread(market_data.get_quote, sym))
        precio = float((q or {}).get("price") or 0)
        if precio > 0:
            upd = {"last_price": precio, "updated_at": datetime.now(timezone.utc).isoformat()}
            if q.get("previous_close"):
                upd["previous_close"] = round(float(q["previous_close"]), 2)
            if q.get("change_percent") is not None:
                upd["daily_change_percent"] = round(float(q["change_percent"]), 2)
            await db.signal_entries.update_one({"id": entry["id"]}, {"$set": upd})
            entry.update(upd)
    except Exception as e:
        logger.info("Sin cotización inicial para %s: %s", sym, e)
    _cache._store.pop("signals_list", None)
    _invalidar_signals_hot()
    return entry


@api_router.patch("/signals/{entry_id}")
async def update_signal(entry_id: str, item: SignalEntryUpdate, _user: str = Depends(auth.get_current_user)):
    # exclude_unset: distingue "no enviado" de "enviado como null". Antes se filtraban todos
    # los None, así que era IMPOSIBLE borrar compra/acciones/venta1-3: el valor viejo volvía.
    data = item.model_dump(exclude_unset=True)
    # El simbolo NO viaja en el payload de un PATCH: sale de la entrada guardada. Fiarse de
    # uno enviado por el cliente permitiria pedir la tendencia de un simbolo alcista para
    # escribir los niveles de otro.
    if veto_compra.niveles_de_compra_en(data) and not item.forzar:
        existente = await db.signal_entries.find_one({"id": entry_id}, {"_id": 0, "symbol": 1})
        if not existente:
            # 404 antes que 409: si la entrada no existe, el problema no es la tendencia.
            raise HTTPException(404, "Señal no encontrada")
        await _puerta_de_tendencia(existente.get("symbol"), data, False)
    updated = await signal_table.update_entry(db, entry_id, data)
    if not updated:
        raise HTTPException(404, "Señal no encontrada")
    _cache._store.pop("signals_list", None)
    _invalidar_signals_hot()
    return updated


@api_router.delete("/signals/{entry_id}")
async def delete_signal(entry_id: str, _user: str = Depends(auth.get_current_user)):
    ok = await signal_table.delete_entry(db, entry_id)
    if not ok:
        raise HTTPException(404, "Señal no encontrada")
    _cache._store.pop("signals_list", None)
    _invalidar_signals_hot()
    return {"deleted": entry_id}


@api_router.post("/signals/bulk")
async def bulk_import_signals(payload: SignalBulkImport, _user: str = Depends(auth.get_current_user)):
    result = await signal_table.bulk_upsert(db, payload.rows)
    _cache._store.pop("signals_list", None)
    _invalidar_signals_hot()
    return result


@api_router.post("/signals/import-image")
async def import_signals_from_image(
    file: UploadFile = File(...),
    dry_run: bool = False,
    _user: str = Depends(auth.get_current_user),
):
    """Lee una FOTO de la tabla de watchlist (Gemini visión), la convierte en filas y las
    upserta. Con dry_run=true solo devuelve las filas leídas para previsualizar sin guardar.
    Respeta el estado manual (campanas/activo) igual que la importación por texto."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "Imagen vacía")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "La imagen es demasiado grande (máx. 8 MB)")
    mime = file.content_type or "image/jpeg"
    try:
        rows = await ai_analysis.extract_watchlist_from_image(data, mime)
    except Exception as e:
        logger.exception("import-image OCR failed")
        raise HTTPException(502, f"No se pudo leer la tabla de la foto: {e}")
    if not rows:
        raise HTTPException(422, "No se detectó ninguna fila con símbolo en la foto.")
    if dry_run:
        return {"rows": rows, "count": len(rows), "saved": False}
    result = await signal_table.bulk_upsert(db, rows)
    _cache._store.pop("signals_list", None)
    _invalidar_signals_hot()
    return {**result, "rows": rows, "saved": True}


# ---------- Alert History ----------
@api_router.get("/alerts/history")
async def get_alert_history(limit: int = 50, _user: str = Depends(auth.get_current_user)):
    """Historial de alertas disparadas (últimas 50)."""
    items = await db.alert_history.find({}, {"_id": 0}).sort("fired_at", -1).limit(limit).to_list(limit)
    return items



# ---------- Hot Signals (señales calientes para el Dashboard) ----------
# El umbral histórico de este endpoint. Se nombra para que quede claro que el 10% es SU
# valor por defecto y no una constante del dominio: cada consumidor tiene el suyo.
_HOT_MAX_PCT_POR_DEFECTO = 10.0


def _clave_signals_hot(limit, max_pct) -> str:
    """La caché va por PARÁMETROS, no por endpoint.

    Antes era una sola clave, `signals_hot`, y ya entonces mentía: quien pedía `limit=5`
    dejaba cacheadas 5 filas y la portada, que pide más, recibía esas 5. Con `max_pct` el
    error dejaría de ser de cantidad para pasar a ser de CONTENIDO —una lista acotada al
    4% servida a quien pidió el 10%—, así que la clave tiene que distinguirlos.
    """
    return f"signals_hot:{limit}:{max_pct}"


def _invalidar_signals_hot() -> None:
    """Tira TODAS las variantes. Con la clave parametrizada, olvidar una dejaría filas
    viejas servidas a un consumidor concreto y a ningún otro — el peor tipo de caché
    rancia, porque solo se nota en una pantalla."""
    for clave in [k for k in _cache._store if k.startswith("signals_hot")]:
        _cache._store.pop(clave, None)
@api_router.get("/signals/hot")
async def hot_signals(limit: int = 5, max_pct: float = _HOT_MAX_PCT_POR_DEFECTO,
                      _user: str = Depends(auth.get_current_user)):
    """Devuelve las acciones con precio más cercano a algún nivel de compra o venta.
    Usa last_price guardado por el worker en MongoDB — respuesta instantánea.

    `max_pct` acota la distancia al nivel. Existe porque cada consumidor descarta a una
    distancia distinta y traerse lo que el llamador va a tirar dejó de ser gratis: desde
    que la fila de COMPRA se cruza con la tendencia, cada candidato cuesta una lectura de
    histórico. La portada «Hoy» descarta por encima de `hoy.UMBRAL_NIVEL_PCT`, así que
    pedirle la banda 4-10% era pagar decenas de lecturas para nada.

    NO es un recorte por cercanía disfrazado: dentro del umbral vienen TODOS, porque quien
    ordena las tarjetas de nivel es `hoy.tarjeta_nivel` y su urgencia no depende solo de la
    distancia — suma hasta 60 puntos por la fuerza de la zona del motor y 15 por tener
    posición abierta. Un candidato al 3,5% con zona fuerte puede mandar sobre uno al 0,5%
    sin ella, y recortando por distancia habría desaparecido sin que nadie lo notara.
    """
    cached = _cache.get(_clave_signals_hot(limit, max_pct))
    if cached is not None:
        return cached
    top = await _candidatos_calientes(limit, max_pct)
    # El endpoint publico VETA todo lo que devuelve. Su contrato no se relaja: quien lo
    # llame directamente no puede recibir una compra que la estructura no autoriza.
    await _vetar_calientes(top)
    _cache.set(_clave_signals_hot(limit, max_pct), top, ttl=300)
    return top


async def _candidatos_calientes(limit: int, max_pct: float) -> list:
    """Los niveles mas cercanos al precio, SIN cruzar con la tendencia.

    Es la mitad barata del endpoint: Mongo y aritmetica, cero red. Se separa porque la
    portada necesita rankear ANTES de pagar ninguna lectura de historico — la urgencia de
    una tarjeta de nivel sale de la distancia, de la fuerza de la zona (que
    `_dashboard_cacheado` sirve de cache) y de si tienes posicion, y ninguna de las tres
    depende de la tendencia.

    Medido: con 39 candidatos dentro del 4% se resolvian 31 tendencias para acabar
    pintando 5 tarjetas. Rankear primero convierte esas 31 lecturas en 5.
    """
    entries = await db.signal_entries.find({"active": True}, {"_id": 0}).to_list(200)
    results = []
    for entry in entries:
        symbol = entry["symbol"]
        try:
            # Usa el precio guardado por el worker (actualizado cada 60s)
            price = float(entry.get("last_price") or 0)
            if price <= 0:
                continue
            # Revisar todos los niveles
            levels = {}
            for lk in ["nivel1", "nivel2", "nivel3", "nivel4", "nivel5"]:
                if entry.get(lk) and entry.get(f"alert_{lk}", True):
                    levels[lk] = entry[lk]
            if entry.get("deseado") and entry.get("alert_deseado", True):
                levels["deseado"] = entry["deseado"]
            if not levels:
                continue
            best_pct = None
            best_label = None
            best_target = None
            best_action = None
            for lk, target in levels.items():
                pct = abs(price - target) / target * 100
                if best_pct is None or pct < best_pct:
                    best_pct = pct
                    best_label = lk
                    best_target = target
                    best_action = "VENTA" if lk == "deseado" else "COMPRA"
            if best_pct is not None and best_pct <= max_pct:
                results.append({
                    "symbol": symbol,
                    "name": entry.get("name", symbol),
                    "mercado": entry.get("mercado", ""),
                    "sector": entry.get("sector", ""),
                    "riesgo": entry.get("riesgo", ""),
                    "price": price,
                    "target": best_target,
                    "level_label": best_label,
                    "action": best_action,
                    "pct_away": round(best_pct, 2),
                    "posibles_ganancias": entry.get("posibles_ganancias"),
                })
        except Exception:
            continue
    # ── El veto, sobre los candidatos de COMPRA ya filtrados ────────────────
    #
    # «Está a un 2% de tu Nivel 3» es un HECHO y se conserva. Lo que no se sostiene es
    # llamarlo COMPRA cuando la estructura no autoriza comprar: la portada «Hoy» imprime
    # «· sería una compra» desde este campo (`hoy.tarjeta_nivel`), así que un valor en
    # caída libre acercándose a un nivel escrito hace meses aparecía como una compra
    # próxima. Con `action` a None esa coletilla desaparece sola y la tarjeta sigue
    # contando lo que de verdad pasa.
    #
    # Se pregunta DESPUÉS de ordenar y recortar, y solo por los de COMPRA.
    #
    # EL ORDEN IMPORTA, Y ES UNA CORRECCIÓN DE RENDIMIENTO
    #
    # Antes se preguntaba por TODOS los candidatos del 10% y solo después se recortaba a
    # `limit`. La portada «Hoy» llama con un límite pequeño, así que se pagaban decenas de
    # lecturas de histórico para tirar casi todas: medido, con 150 candidatos y 5 hilos
    # eran 150 lecturas y ~36 s bloqueando la respuesta, contra 12 s recortando antes.
    #
    # Es seguro porque el veto NO toca `pct_away`, que es la única clave de ordenación:
    # solo escribe `action`, `vetado_por_tendencia` y `veto_motivo`. Ni el orden ni qué
    # elementos entran en el recorte pueden cambiar por vetar antes o después, así que la
    # salida es idéntica y solo cambia cuánto se paga por ella.
    #
    # Los niveles guardados no se tocan — esto es presentación, no una reescritura de tu
    # tabla.
    results.sort(key=lambda x: x["pct_away"])
    return results[:limit]


async def _vetar_calientes(items) -> None:
    """Cruza con la tendencia los candidatos de COMPRA de una lista, EN EL SITIO.

    Se extrae del endpoint para que la portada pueda llamarlo sobre las tarjetas que de
    verdad va a pintar, en vez de sobre todos los candidatos: medido, 31 lecturas de
    histórico para enseñar 5 tarjetas. Aquí no se decide QUÉ se enseña —eso lo decide la
    urgencia, que no depende de la tendencia— sino qué se puede llamar compra.

    Autoridad de siempre: `market_data.tendencia_de` lee el histórico cacheado,
    `estado_accion` traduce y `veto_compra` decide. Ningún estado se compara a mano.
    """
    compras = [r for r in items if r.get("action") == "COMPRA"]
    if compras:
        tendencias = await asyncio.gather(*[
            asyncio.to_thread(market_data.tendencia_de, r["symbol"]) for r in compras
        ], return_exceptions=True)
        for item, tend in zip(compras, tendencias):
            # Una excepción se convierte al estado de «no se pudo comprobar», que es
            # exactamente lo que ha ocurrido. Fallo CERRADO: no presentar como compra lo
            # que no se ha podido verificar.
            estado_t = tend if isinstance(tend, str) else veto_compra.TENDENCIA_NO_VERIFICABLE
            if veto_compra.no_verificable(estado_t):
                # «No lo sé» y «está bajista» ocultan los dos la compra, pero no son lo
                # mismo y no pueden explicarse igual: la segunda es una afirmación sobre el
                # mercado, y aquí nadie la ha hecho.
                item["action"] = None
                item["vetado_por_tendencia"] = True
                item["veto_motivo"] = veto_compra.MOTIVO_NO_VERIFICABLE
                continue
            est = estado_accion.evaluar(estado_t)
            if veto_compra.hay_veto(est["estado"]):
                item["action"] = None
                item["vetado_por_tendencia"] = True
                item["veto_motivo"] = est["motivo"]


# ---------- Dashboard «Hoy» ----------
async def _fuentes_con_tendencia(days: int = 14):
    """Las menciones de tus fuentes y la tendencia de las que pueden dar tarjeta.

    DOS CORRECCIONES DE RENDIMIENTO, MEDIDAS

    Antes esto eran dos pasos y los dos costaban de más. `_fuentes_por_ticker` iba en el
    `gather` de la portada, pero la resolución de tendencias iba DESPUÉS, en el cuerpo:
    su latencia se sumaba a la de `hot_signals` en vez de solaparse. Y se preguntaba por
    TODOS los tickers mencionados en 14 días de newsletters, sin tope.

    Con 120 tickers eso son 120 descargas de dos años de velas. Medido con 5 hilos —lo que
    da un CPU en Render— y 1,2 s por lectura: 39,8 s de portada, y la caché de histórico
    (120 entradas) desbordada, así que ni la segunda carga se salvaba.

    La mayoría no podían cambiar nada. `hoy.tarjeta_confluencia` solo emite con ACUERDO o
    CHOQUE, y `confluencia.puede_cruzarse` dice cuáles pueden llegar ahí SIN reimplementar
    la condición: se la pregunta a `clasificar`. Un ticker mencionado una sola vez, o con
    opiniones encontradas, sale NEUTRAL o MIXTO diga lo que diga la estructura.

    Devolver las dos cosas juntas es lo que permite meterlo entero en el `gather`: la
    tendencia depende de las fuentes, así que no podían ser dos ramas hermanas.

    Ante cualquier fallo, SIN_DATOS — que da INSUFICIENTE y no produce tarjeta. Fallo
    cerrado, igual que antes.
    """
    fuentes = await _fuentes_por_ticker(days)
    cruzables = [tk for tk, f in fuentes.items()
                 if confluencia_mod.puede_cruzarse(len(f.get("fuentes") or []),
                                                   f.get("positivos") or 0,
                                                   f.get("negativos") or 0)]
    tendencias: dict = {}
    if cruzables:
        resueltas = await asyncio.gather(*[
            asyncio.to_thread(market_data.tendencia_de, tk) for tk in cruzables
        ], return_exceptions=True)
        for tk, tend in zip(cruzables, resueltas):
            tendencias[tk] = tend if isinstance(tend, str) else "SIN_DATOS"
    return fuentes, tendencias



async def _fuentes_por_ticker(days: int = 14) -> dict:
    """Mapa ticker → menciones, sentimiento, quién lo dice y el veredicto del motor.

    Es lo mismo que agrega /radar, pero devuelto como mapa para poder cruzarlo por
    símbolo. Reutiliza la lectura cacheada de newsletters, así que no cuesta ni una
    consulta nueva cuando el precalentado ya ha pasado por aquí.
    """
    docs = await _newsletters_recientes(days, 300)
    out: dict = {}
    for d in docs:
        ex = d.get("extracted") or {}
        src = _clean_source(d.get("sender"), d.get("subject"))
        for a in (ex.get("acciones") or []):
            tk = (a.get("ticker") or "").strip().upper()
            if not tk or newsletter_ingest._is_sponsor(a):
                continue
            slot = out.setdefault(tk, {
                "menciones": 0, "positivos": 0, "negativos": 0,
                "fuentes": set(), "ultima": d.get("received_at"),
                "nombre": a.get("nombre") or "",
            })
            slot["menciones"] += 1
            slot["fuentes"].add(src)
            sent = (a.get("sentimiento") or "").upper()
            if sent == "POSITIVO":
                slot["positivos"] += 1
            elif sent == "NEGATIVO":
                slot["negativos"] += 1
            if not slot["nombre"] and a.get("nombre"):
                slot["nombre"] = a["nombre"]

    for tk, s in out.items():
        s["fuentes"] = sorted(s["fuentes"])
    return out


CLAVE_NIVELES = "niveles"  # caché del cálculo ligero, separada del dashboard completo


async def construir_niveles_ligero(sym: str, precio: float) -> dict:
    """Las TRES claves que consume la portada, y nada más: sin una sola llamada a Finnhub.

    El dashboard completo cuesta 5 llamadas por símbolo —quote, news, trends,
    price_target y fundamentales— y la portada solo lee `buy_levels`, `data_health` e
    `indicators`. Está verificado con un test que construye el dashboard con esas cuatro
    fuentes anuladas y comprueba que las tres claves salen idénticas.

    Las tres se calculan sobre el histórico (yfinance/Stooq, sin cuota) y un único
    escalar: el precio, que aquí llega de `last_price` en vez de una cotización nueva.

    NO se toca el motor: se llama a `levels_engine.compute_buy_levels` con los mismos
    argumentos que usa el camino completo.
    """
    loop = asyncio.get_running_loop()
    df_ind = await loop.run_in_executor(None, market_data.get_full_indicator_history, sym)
    if df_ind is None or getattr(df_ind, "empty", True):
        return {}

    indicadores = await loop.run_in_executor(None, ind.compute_all, df_ind)
    if not indicadores:
        return {}

    vp = await loop.run_in_executor(None, _cached_vp, sym)
    vp_dict = vp if isinstance(vp, dict) else {}

    niveles = []
    try:
        niveles = await loop.run_in_executor(
            None,
            partial(
                levels_engine.compute_buy_levels,
                df_ind, vp_dict, precio, indicadores.get("sma"),
                atr_val=indicadores.get("atr"),
                regime=indicadores.get("regime"),
                vwap_anchored=indicadores.get("vwap_anchored"),
            ),
        )
    except Exception:
        logger.exception("niveles ligeros[%s] compute_buy_levels falló", sym)

    salud = None
    try:
        salud = market_data.data_health(df_ind)
    except Exception:
        salud = None

    return {
        "symbol": sym,
        "buy_levels": niveles or [],
        "indicators": indicadores,
        "data_health": salud,
        "precio_usado": precio,
        "ligero": True,
        "generado_en": datetime.now(timezone.utc).isoformat(),
    }


def _dashboard_cacheado(symbol: str):
    """El dashboard de un símbolo SOLO si ya está en caché. Nunca lo calcula.

    Es la pieza que hace que esta portada responda en un par de segundos: los
    niveles con su fuerza y sus razones, el `data_warning` y los indicadores ya los
    deja calculados el bucle de precalentado. Si un símbolo no está caliente, su
    tarjeta sale igual con lo que sí es barato —la distancia a TU nivel, que vive en
    la tabla— y sin el porqué del motor. Preferimos una tarjeta con menos detalle
    que una portada que tarda veinte segundos.

    Mira DOS cachés, en este orden:

      1. El dashboard completo, que deja quien abre la página de acción.
      2. El cálculo ligero del precalentado, que trae las mismas tres claves sin gastar
         cuota.

    Van en claves separadas a propósito. Guardar el ligero bajo la clave del completo
    haría que /dashboard/{symbol} sirviera a la página de acción un objeto sin
    cotización, sin noticias y sin analistas — y el fallo aparecería en otra pantalla,
    lejos del cambio que lo causó.
    """
    valor, _ = _cache.get_stale(f"dashboard:{symbol}:{_TIMEFRAME_PREWARM}",
                                max_age=_DASHBOARD_STALE_MAX)
    if valor:
        return valor
    valor, _ = _cache.get_stale(f"{CLAVE_NIVELES}:{symbol}", max_age=_DASHBOARD_STALE_MAX)
    return valor or {}


def _niveles_del_motor(dash: dict) -> list:
    """Las zonas de confluencia del dashboard cacheado.

    `buy_levels` cuelga de la RAÍZ del dashboard, no de un `analysis`: ese objeto solo
    existe en la respuesta de /analyze, que es otra cosa. Se centraliza aquí porque
    equivocarse en la ruta no da error, da una lista vacía — y una lista vacía se lee
    como "el motor no tiene zona para este precio", que es una afirmación falsa y
    tranquilizadora.
    """
    return dash.get("buy_levels") or []


def _aviso_de_datos(dash: dict) -> Optional[str]:
    """El aviso de calidad de dato del dashboard, si lo hay.

    El dashboard no trae `data_warning` —ese campo lo redacta /analyze— sino
    `data_health`, con la fuente y si está degradada. Se redacta aquí con las mismas
    palabras que usa /analyze para que el usuario lea siempre lo mismo.
    """
    salud = dash.get("data_health") or {}
    if not salud.get("degraded"):
        return None
    return ("⚠️ Datos de respaldo/con retraso (" + (salud.get("note") or "fuente degradada")
            + "). Trátalo con cautela.")


def _mejor_zona(dash: dict, precio_objetivo):
    """La zona de confluencia del motor más cercana al nivel que ha disparado.

    Se busca la más cercana y no la más fuerte a propósito: lo que queremos saber es
    si el precio al que va a llegar el mercado tiene respaldo, no cuál es la mejor
    zona en abstracto.
    """
    niveles = _niveles_del_motor(dash)
    objetivo = None
    try:
        objetivo = float(precio_objetivo)
    except (TypeError, ValueError):
        return None
    mejor, mejor_dist = None, None
    for z in niveles:
        try:
            centro = float(z.get("price"))
        except (TypeError, ValueError):
            continue
        dist = abs(centro - objetivo) / objetivo * 100 if objetivo else None
        # Más allá del 3% ya no está hablando del mismo precio.
        if dist is not None and dist <= 3 and (mejor_dist is None or dist < mejor_dist):
            mejor, mejor_dist = z, dist
    return mejor


def _ventanas_de_hoy(desde: Optional[str], ahora=None) -> tuple:
    """Devuelve (corte_alertas, corte_cerebro). DOS ventanas, porque son dos preguntas.

      · Las ALERTAS preguntan "¿qué ha saltado y sigue sin resolverse?". Una alerta que
        salta a las 9:00 sigue pendiente a las 9:05 aunque hayas mirado la pantalla en
        medio: mirar no es actuar. Ventana FIJA de 24 h, independiente de las visitas.
      · El CEREBRO pregunta "¿qué ha cambiado desde que no vengo?". Ahí sí, la última
        visita es la referencia correcta.

    Compartían una sola ventana, y eso hacía DESAPARECER las alertas al recargar: el
    frontend sella la visita en cada carga con éxito, así que la petición siguiente
    mandaba un `desde` de hacía minutos y las alertas del día quedaban fuera. La portada
    enseñaba niveles cercanos en vez de las alertas que sí habían saltado, y no había
    forma de recuperarlas recargando — porque recargar era justo lo que las borraba.
    """
    ahora = ahora or datetime.now(timezone.utc)
    corte_alertas = (ahora - timedelta(hours=VENTANA_ALERTAS_HORAS)).isoformat()
    return corte_alertas, (desde or corte_alertas)


async def _tarjetas_de_nivel(calientes, posiciones, limite) -> list:
    """Las tarjetas de nivel de la portada, resolviendo la tendencia SOLO de las que salen.

    EL DESPERDICIO QUE ESTO CORTA

    Medido: 39 candidatos dentro del 4% producían 31 lecturas de histórico y acababan
    pintando 5 tarjetas. Las otras 34 pagaban la descarga y las descartaba
    `hoy.ordenar_y_recortar`, que devuelve `finales[:limite]`.

    POR QUÉ SE PUEDE RANKEAR ANTES DE PREGUNTAR

    La urgencia de una tarjeta de nivel no depende de la tendencia:

        urgencia = BASE + (UMBRAL - distancia)*20 + min(60, fuerza*0.6) + 15 si hay posición

    La distancia ya está calculada, `fuerza` sale de `_dashboard_cacheado` —que solo lee
    caché y nunca calcula— y la posición, de Mongo. Ninguna toca la red. La tendencia solo
    decide si la tarjeta puede llamarse compra, no si sale ni en qué orden.

    POR QUÉ EL TOPE ES EXACTO Y NO UNA APROXIMACIÓN

    La respuesta final trae como mucho `limite` tarjetas EN TOTAL, de todos los tipos. Así
    que las `limite` de nivel más urgentes son un SUPERCONJUNTO de las que van a salir:
    otras tarjetas pueden robarles sitio, nunca al revés. Resolver la tendencia de esas es
    suficiente, y no puede dejar sin vetar ninguna que llegue a pantalla.

    Se reconstruye la tarjeta después de vetar en vez de parchear su texto: el «· sería una
    compra» lo redacta `hoy.py`, y escribirlo aquí sería tener la misma frase en dos sitios.
    La urgencia no cambia al vetar, así que la posición en el ranking tampoco.
    """
    contexto = {}
    for c in calientes:
        sym = (c.get("symbol") or "").upper()
        dash = _dashboard_cacheado(sym)
        # `bool(dash)` distingue "el motor no ha calculado este símbolo" de "ha
        # calculado pero sus zonas caen lejos de este precio". Se leían igual y no lo son.
        contexto[id(c)] = {"zona": _mejor_zona(dash, c.get("target")),
                           "aviso": _aviso_de_datos(dash),
                           "tiene": (posiciones.get(sym, {}).get("acciones") or 0) > 0,
                           "con_datos": bool(dash)}

    def _construir(c):
        ctx = contexto[id(c)]
        return hoy.tarjeta_nivel(c, ctx["zona"], aviso=ctx["aviso"],
                                 tiene_posicion=ctx["tiene"],
                                 motor_con_datos=ctx["con_datos"])

    previas = [(c, _construir(c)) for c in calientes]
    vivas = [(c, t) for c, t in previas if t]
    vivas.sort(key=lambda par: par[1]["urgencia"], reverse=True)

    candidatas = [c for c, _ in vivas[:limite]]
    await _vetar_calientes(candidatas)
    vetadas = {id(c) for c in candidatas}

    # Solo se rehacen las que pasaron por el veto; el resto conserva su tarjeta original.
    return [(_construir(c) if id(c) in vetadas else t) for c, t in vivas]


# Techo de tarjetas de la portada. Estaba escrito a mano dentro del saneado del
# parametro; se le pone nombre porque un tope no puede ser un numero suelto en mitad de
# una expresion.
_HOY_MAX_TARJETAS = 10

# Cuantos candidatos de nivel puede traer la portada. No es un recorte por cercania: es el
# mismo tope que ya acota la lectura de `signal_entries`, puesto aqui para que ninguna
# consulta pueda crecer sin limite. Dentro del umbral de distancia vienen TODOS, porque
# quien decide cuales se pintan es `hoy.tarjeta_nivel` por urgencia — y su urgencia suma la
# fuerza de la zona del motor y si tienes posicion abierta, no solo la distancia.
_HOY_MAX_CANDIDATOS_NIVEL = 200


@api_router.get("/hoy")
async def dashboard_hoy(desde: Optional[str] = None, limite: int = hoy.LIMITE_POR_DEFECTO,
                        _user: str = Depends(auth.get_current_user)):
    """Portada: qué merece tu atención hoy, por qué, y qué deberías revisar.

    `desde` es la última visita (la guarda el navegador). Sin ella se usan 24 h, que
    es lo razonable para «qué me he perdido».

    Todo lo que sirve sale de datos que ya existían y que el frontend no usaba. La
    única regla dura: aquí no se CALCULA nada caro. Se lee de las cachés que el
    precalentado deja listas, y lo que no esté caliente sale con menos detalle en vez
    de hacer esperar a la página.
    """
    limite = max(1, min(int(limite or hoy.LIMITE_POR_DEFECTO), _HOY_MAX_TARJETAS))

    corte_alertas, corte = _ventanas_de_hoy(desde)

    entradas, calientes, alertas, resumen, fuentes_y_tendencias = await asyncio.gather(
        db.signal_entries.find({"active": True}, {"_id": 0}).to_list(200),
        # Se pide por DISTANCIA, no por cantidad. `hoy.tarjeta_nivel` descarta todo lo que
        # supere `UMBRAL_NIVEL_PCT`, así que la banda 4-10% eran filas que se traían, se
        # pagaba una lectura de histórico por cada una y se tiraban aquí mismo.
        #
        # Y NO se recorta por cercanía: dentro del 4% vienen todas. La urgencia de una
        # tarjeta de nivel no es solo la distancia —suma hasta 60 por la fuerza de la zona
        # y 15 por tener posición—, así que quedarse con las diez más cercanas habría
        # borrado en silencio una tarjeta al 3,5% con zona fuerte que sí debía salir.
        _candidatos_calientes(_HOY_MAX_CANDIDATOS_NIVEL, hoy.UMBRAL_NIVEL_PCT),
        db.alert_history.find({"fired_at": {"$gte": corte_alertas}}, {"_id": 0})
                        .sort("fired_at", -1).limit(20).to_list(20),
        resumen_cartera(_user="hoy"),
        # Las fuentes Y la tendencia de las que pueden dar tarjeta, juntas. La segunda
        # depende de la primera, así que no pueden ser ramas hermanas — pero metidas en
        # una sola corrutina su latencia se solapa con la de `hot_signals` en vez de
        # sumarse, que es lo que pasaba cuando esto vivía detrás del `gather`.
        _fuentes_con_tendencia(14),
        return_exceptions=True,
    )
    # Un fallo aislado degrada su bloque, no la portada entera: es preferible una
    # portada con cuatro fuentes de cinco que una pantalla de error.
    def _ok(v, por_defecto):
        if isinstance(v, Exception):
            logger.warning("Portada «Hoy»: un bloque falló: %s", v)
            return por_defecto
        return v

    entradas = _ok(entradas, [])
    calientes = _ok(calientes, [])
    alertas = _ok(alertas, [])
    resumen = _ok(resumen, {})
    fuentes, tendencias_fuentes = _ok(fuentes_y_tendencias, ({}, {}))

    por_symbol = {(e.get("symbol") or "").upper(): e for e in entradas}
    posiciones = {(p.get("symbol") or "").upper(): p
                  for p in (resumen.get("posiciones") or [])}

    tarjetas = []

    # 1 · Rupturas donde hay dinero dentro.
    for sym, pos in posiciones.items():
        if not (pos.get("acciones") or 0) > 0:
            continue
        dash = _dashboard_cacheado(sym)
        indicadores = dash.get("indicators") or {}
        tarjetas.append(hoy.tarjeta_ruptura(por_symbol.get(sym, {"symbol": sym}), pos, indicadores))

    # 2 · Alertas disparadas desde la última visita.
    for a in alertas:
        tarjetas.append(hoy.tarjeta_alerta(a, por_symbol.get((a.get("symbol") or "").upper())))

    # 3 · Niveles cerca, con el porqué del motor cuando esté caliente.
    tarjetas += await _tarjetas_de_nivel(calientes, posiciones, limite)

    # 4 y 5 · Choque y coincidencia entre las fuentes y la elegibilidad estructural.
    # Una sola implementación, la de `confluencia.py`. La que vivía en `hoy.py` tenía
    # estados distintos y los mismos umbrales de score duplicados: la misma acción podía
    # salir en ACUERDO en el Radar y en «choque» aquí.
    #
    # Desaparece el cálculo de `zona`: solo existía para pasar distancia y fuerza del
    # nivel, que es información de ENTRADA y no de confluencia.
    #
    # La tendencia ya viene resuelta desde el `gather`, y SOLO para los tickers que podían
    # dar tarjeta. Los demás entran igual con SIN_DATOS: `clasificar` los manda a
    # INSUFICIENTE, que es lo que ya salía, y `tarjeta_confluencia` calla. No se resuelven
    # porque su estado no puede cambiar el resultado — y cada uno costaba una descarga de
    # dos años de velas.
    if fuentes:
        for tk in fuentes:
            f = fuentes[tk]
            estado_t = tendencias_fuentes.get(tk, "SIN_DATOS")
            estado = confluencia_mod.clasificar(
                len(f.get("fuentes") or []), f.get("positivos") or 0,
                f.get("negativos") or 0, estado_t)
            tiene = (posiciones.get(tk, {}).get("acciones") or 0) > 0
            tarjetas.append(hoy.tarjeta_confluencia(
                tk, f.get("nombre"), estado, f, tiene_posicion=tiene,
            ))

    # 6 · Resultados con posición abierta.
    proximos = []
    try:
        simbolos_cartera = [s for s, p in posiciones.items() if (p.get("acciones") or 0) > 0]
        if simbolos_cartera:
            cal = await earnings_calendar(days=7, symbols=",".join(simbolos_cartera), _user="hoy")
            hoy_fecha = datetime.now(timezone.utc).date()
            for it in (cal.get("items") or []):
                try:
                    dias = (datetime.fromisoformat(it["date"]).date() - hoy_fecha).days
                except Exception:
                    continue
                evento = {**it, "dias": dias, "symbol": (it.get("symbol") or "").upper()}
                proximos.append(evento)
                # Sin historial de sorpresas por ahora: no viaja en el dashboard y
                # pedirlo aquí sería una llamada de red por símbolo en el camino de la
                # portada. La tarjeta funciona sin él.
                tarjetas.append(hoy.tarjeta_resultados(
                    evento, posiciones.get(evento["symbol"])))
    except Exception as e:
        logger.warning("Portada «Hoy»: calendario no disponible: %s", e)

    importa = hoy.ordenar_y_recortar(tarjetas, limite)

    # ENCOLA los finalistas que no estén en caché. No los calcula.
    #
    # La versión anterior lanzaba aquí mismo hasta cinco `_construir_dashboard`: unas 25
    # llamadas a Finnhub de golpe, sin espaciar, sin pasar por el umbral de pausa y en
    # primer plano, porque las tareas heredan el contexto de la petición. Era el único
    # camino que se saltaba entero el control de cuota.
    #
    # Ahora hay un solo mecanismo. El bucle de precalentado atiende la cola con su marca
    # de background y su tope, y despierta en segundos en vez de esperar la cadencia.
    # Esta carga sale con lo que haya; la siguiente ya sale completa — igual que antes,
    # pero sin la ráfaga.
    faltan = [t["symbol"] for t in importa
              if _cache.get_stale(f"dashboard:{t['symbol']}:{_TIMEFRAME_PREWARM}",
                                  max_age=_DASHBOARD_STALE_MAX)[0] is None]
    if faltan:
        _encolar_calentado(faltan)

    # Novedades del Cerebro desde la última visita.
    cerebro = {"desde": corte, "tickers_nuevos": [], "menciones_nuevas": 0}
    try:
        recientes = await _newsletters_recientes(14, 300)
        vistos_antes, nuevos = set(), {}
        for d in recientes:
            reciente = (d.get("received_at") or "") >= corte
            for a in ((d.get("extracted") or {}).get("acciones") or []):
                tk = (a.get("ticker") or "").strip().upper()
                if not tk or newsletter_ingest._is_sponsor(a):
                    continue
                if reciente:
                    nuevos[tk] = nuevos.get(tk, 0) + 1
                else:
                    vistos_antes.add(tk)
        cerebro["menciones_nuevas"] = sum(nuevos.values())
        cerebro["tickers_nuevos"] = sorted(t for t in nuevos if t not in vistos_antes)
    except Exception as e:
        logger.warning("Portada «Hoy»: novedades del Cerebro no disponibles: %s", e)

    # Posiciones que piden atención: las que están en pérdidas o han roto algo. No
    # las diez: solo las que tienen algo que decir hoy.
    # `pct` (rendimiento de la acción en su divisa) y no `pct_eur`: lo que dice si una
    # tesis va mal es cómo se comporta la acción, no cuánto se ha movido el dólar. El
    # euro se enseña aparte, en el importe.
    atencion = []
    for sym, p in posiciones.items():
        if not (p.get("acciones") or 0) > 0:
            continue
        pct = p.get("pct")
        if pct is None:
            pct = p.get("pct_eur")
        if pct is not None and pct <= -8:
            atencion.append({"symbol": sym, "motivo": "en pérdidas",
                             "pct": pct, "pnl_eur": p.get("pnl_eur")})
    atencion.sort(key=lambda x: x.get("pct") or 0)

    regimen = None
    try:
        regimen = market_regime.get_market_regime()
    except Exception as e:
        logger.warning("Portada «Hoy»: régimen no disponible: %s", e)

    return {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "desde": corte,
        "saludo": hoy.resumen_de_saludo(importa, cerebro),
        "importa_hoy": importa,
        "cartera": {
            "valor_eur": resumen.get("valor_eur"),
            "latente_eur": resumen.get("latente_eur"),
            "realizado_eur": resumen.get("realizado_eur"),
            "invertido_eur": resumen.get("invertido_eur"),
            "posiciones_sin_valorar": resumen.get("posiciones_sin_valorar"),
            "atencion": atencion[:4],
        },
        "mercado": regimen,
        "cerebro": cerebro,
        "proximos_7_dias": sorted(proximos, key=lambda e: e.get("dias") or 99)[:5],
    }


# ---------- WebSocket: live quote streaming ----------
import websockets as _ws_client

_FINNHUB_WS_URL = "wss://ws.finnhub.io"


class _QuoteManager:
    """Streams live price updates to connected frontend WebSocket clients.

    Hybrid design that minimises Finnhub REST quota:
      • A single shared Finnhub trade WebSocket pushes tick-by-tick prices the
        instant a trade happens (no REST quota used while streaming).
      • A light REST loop per symbol (every 15s) seeds the baseline — previous
        close, day high/low — and acts as a fallback when the market is closed
        or the Finnhub stream is unavailable, so the price is never stale/blank.
      • The Finnhub stream auto-reconnects with exponential backoff and
        re-subscribes every active symbol. If Finnhub WS can't be used at all
        (no key, network), the REST loop alone keeps everything working.
    """

    def __init__(self):
        self._conns: dict[str, list[WebSocket]] = {}
        self._baseline: dict[str, dict] = {}   # symbol -> {previous_close, day_high, day_low}
        self._last: dict[str, dict] = {}        # symbol -> last payload sent (snapshot for new clients)
        self._rest_tasks: dict[str, asyncio.Task] = {}
        self._fh_task: asyncio.Task | None = None
        self._fh_ws = None
        self._lock = asyncio.Lock()
        self._ultimo_tick: dict[str, float] = {}   # símbolo -> instante del último trade
        self._ultimo_envio: dict[str, float] = {}  # símbolo -> instante del último broadcast
        self._pendiente: dict[str, dict] = {}      # payloads en espera de agruparse
        self._suscritos: set = set()               # símbolos pedidos al stream de Finnhub

    # Tope de símbolos con stream. El plan gratuito de Finnhub admite ~50 por conexión.
    _MAX_SIMBOLOS_STREAM = 45  # margen por debajo del límite real

    async def connect(self, symbol: str, ws: WebSocket):
        await ws.accept()
        self._conns.setdefault(symbol, []).append(ws)
        # Send an immediate snapshot if we already have a recent price.
        if self._last.get(symbol):
            try:
                await ws.send_json(self._last[symbol])
            except Exception:
                pass
        # Start the per-symbol REST baseline loop (seeds baseline + fallback).
        if symbol not in self._rest_tasks or self._rest_tasks[symbol].done():
            self._rest_tasks[symbol] = asyncio.create_task(self._baseline_loop(symbol))
        # Ensure the shared Finnhub trade stream is running and subscribe.
        # Finnhub limita el nº de símbolos por conexión (50 en el plan gratuito). Pasado el
        # tope, las suscripciones fallan EN SILENCIO: el símbolo 51 parecería conectado y se
        # quedaría con un precio que no avanza, sin ningún aviso. Mejor no pedirla y dejar
        # que ese símbolo se sirva por REST, que sí funciona, solo que con menos frecuencia.
        if len(self._conns) > self._MAX_SIMBOLOS_STREAM and symbol not in self._suscritos:
            logger.warning("WS: %d símbolos activos, %s se sirve solo por REST",
                           len(self._conns), symbol)
            return
        await self._ensure_fh_stream()
        await self._fh_send({"type": "subscribe", "symbol": symbol})
        self._suscritos.add(symbol)

    def disconnect(self, symbol: str, ws: WebSocket):
        conns = self._conns.get(symbol, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._conns.pop(symbol, None)
            task = self._rest_tasks.pop(symbol, None)
            if task:
                task.cancel()
            # Libera también el estado por-símbolo: si no, _baseline y _last acumulan una
            # entrada por cada símbolo distinto visto en toda la vida del proceso (leak lento).
            self._baseline.pop(symbol, None)
            self._last.pop(symbol, None)
            self._ultimo_tick.pop(symbol, None)
            self._ultimo_envio.pop(symbol, None)
            self._pendiente.pop(symbol, None)
            # Defer the Finnhub unsubscribe / stream teardown to a lock-guarded coroutine
            # so it can't race with a concurrent connect (which would spawn a 2nd stream).
            # La referencia en _bg_tasks no es decorativa: asyncio solo guarda referencias
            # DÉBILES a las tareas, así que sin esto el recolector puede llevarse la baja a
            # medias y dejar la suscripción a Finnhub viva para siempre.
            tarea = asyncio.create_task(self._cleanup_symbol(symbol))
            _bg_tasks.add(tarea)
            tarea.add_done_callback(_bg_tasks.discard)

    async def _cleanup_symbol(self, symbol: str):
        async with self._lock:
            await self._fh_send({"type": "unsubscribe", "symbol": symbol})
            self._suscritos.discard(symbol)
            # No clients left at all -> tear down the shared Finnhub stream and wait for
            # it to actually close before allowing a new one to be created.
            if not self._conns and self._fh_task and not self._fh_task.done():
                self._fh_task.cancel()
                try:
                    await self._fh_task
                except BaseException:
                    pass
                self._fh_task = None

    # ----- Finnhub trade stream (shared) -----
    async def _ensure_fh_stream(self):
        async with self._lock:
            if self._fh_task and not self._fh_task.done():
                return
            if not os.environ.get("FINNHUB_API_KEY"):
                return  # no key -> REST-only mode (still fully functional)
            self._fh_task = asyncio.create_task(self._fh_supervisor())

    async def _fh_send(self, msg: dict):
        ws = self._fh_ws
        if ws is None:
            return
        try:
            await ws.send(json.dumps(msg))
        except Exception:
            pass

    async def _fh_supervisor(self):
        """Maintain the Finnhub WS connection; reconnect with backoff and re-subscribe."""
        key = os.environ.get("FINNHUB_API_KEY")
        backoff = 1
        while self._conns:
            try:
                async with _ws_client.connect(f"{_FINNHUB_WS_URL}?token={key}", ping_interval=20) as ws:
                    self._fh_ws = ws
                    backoff = 1  # connected -> reset backoff
                    # Re-subscribe every active symbol.
                    # Se re-suscribe respetando el tope, no _conns entero: si hay mas
                    # simbolos que huecos, mandarlos todos hace que Finnhub descarte los
                    # sobrantes sin decir nada y no habria forma de saber cuales.
                    self._suscritos = set(list(self._conns.keys())[:self._MAX_SIMBOLOS_STREAM])
                    for sym in self._suscritos:
                        await ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue
                        if msg.get("type") != "trade":
                            continue
                        for tr in msg.get("data") or []:
                            await self._on_trade(tr.get("s"), tr.get("p"))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Finnhub WS dropped, reconnecting in %ds: %s", backoff, e)
            finally:
                self._fh_ws = None
            if not self._conns:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    # Agrupado de ticks. Un valor líquido cruza cientos de operaciones por segundo y cada
    # una era un send_json a CADA cliente conectado. Ni la pantalla puede mostrar eso ni el
    # ojo distinguirlo: el frontend ya junta los mensajes por fotograma al recibirlos, así
    # que todo ese tráfico se descartaba nada más llegar. Se manda como mucho 4 veces por
    # segundo, que se sigue viendo como un precio vivo.
    _INTERVALO_ENVIO = 0.25

    async def _on_trade(self, symbol: str, price):
        if not symbol or price is None or symbol not in self._conns:
            return
        self._ultimo_tick[symbol] = _time.time()
        base = self._baseline.get(symbol) or {}
        prev = base.get("previous_close")
        change = round(price - prev, 4) if prev else None
        change_pct = round((price - prev) / prev * 100, 4) if prev else None
        # Track intraday high/low locally as trades stream in.
        day_high = base.get("day_high")
        day_low = base.get("day_low")
        day_high = price if day_high is None else max(day_high, price)
        day_low = price if day_low is None else min(day_low, price)
        base["day_high"], base["day_low"] = day_high, day_low
        self._baseline[symbol] = base
        payload = {
            "price": price,
            "change": change,
            "change_percent": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "previous_close": prev,
        }
        # El último precio siempre queda guardado (para el snapshot de quien se conecte),
        # pero solo se emite si toca. Si no toca, queda pendiente y lo manda el siguiente
        # tick que sí entre en ventana — nunca se pierde el precio, solo los intermedios.
        self._last[symbol] = payload
        ahora = _time.time()
        restante = self._INTERVALO_ENVIO - (ahora - self._ultimo_envio.get(symbol, 0.0))
        if restante > 0:
            # Queda pendiente Y se programa su envío. Sin lo segundo, si este resultara ser
            # el último trade antes de una pausa, ese precio no llegaría nunca: la pantalla
            # se quedaría clavada en el anterior sin que nada lo delatara.
            hay_espera = symbol in self._pendiente
            self._pendiente[symbol] = payload
            if not hay_espera:
                tarea = asyncio.create_task(self._enviar_pendiente(symbol, restante))
                _bg_tasks.add(tarea)
                tarea.add_done_callback(_bg_tasks.discard)
            return
        self._pendiente.pop(symbol, None)
        self._ultimo_envio[symbol] = ahora
        await self._broadcast(symbol, payload)

    async def _enviar_pendiente(self, symbol: str, espera: float):
        try:
            await asyncio.sleep(espera)
            payload = self._pendiente.pop(symbol, None)
            if payload is None or symbol not in self._conns:
                return
            self._ultimo_envio[symbol] = _time.time()
            await self._broadcast(symbol, payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    # ----- REST baseline / fallback loop -----
    async def _baseline_loop(self, symbol: str):
        loop = asyncio.get_running_loop()
        while self._conns.get(symbol):
            try:
                q = await loop.run_in_executor(None, market_data.get_quote_fast, symbol)
                if not q:
                    q = await loop.run_in_executor(None, market_data.get_quote, symbol)
                if q and q.get("price") is not None:
                    prev = q.get("previous_close")
                    base = self._baseline.get(symbol) or {}
                    base["previous_close"] = prev if prev is not None else base.get("previous_close")
                    # Seed/raise day high-low from the REST snapshot.
                    for k_src, k in (("day_high", "day_high"), ("day_low", "day_low")):
                        v = q.get(k_src)
                        if v is not None:
                            cur = base.get(k)
                            if cur is None:
                                base[k] = v
                            else:
                                base[k] = max(cur, v) if k == "day_high" else min(cur, v)
                    self._baseline[symbol] = base
                    payload = {
                        "price": q.get("price"),
                        "change": q.get("change"),
                        "change_percent": q.get("change_percent"),
                        "day_high": base.get("day_high", q.get("day_high")),
                        "day_low": base.get("day_low", q.get("day_low")),
                        "previous_close": base.get("previous_close"),
                    }
                    await self._broadcast(symbol, payload)
            except Exception:
                pass
            await asyncio.sleep(self._espera_baseline(symbol))

    # Cadencia del bucle REST. Antes era 15 s fijos: 4 llamadas/min por símbolo, las 24
    # horas, sábados incluidos. Con una pestaña abierta toda la tarde son ~5.700 llamadas
    # al día por símbolo, gastadas en su mayoría reconsultando un precio que no se mueve
    # porque el mercado está cerrado, o que ya está llegando por el stream de trades.
    #
    # Este bucle NO es la fuente del precio en directo; es la red de seguridad. Su cadencia
    # debe depender de si hace falta:
    _ESPERA_CERRADO = 300.0   # mercado cerrado: nada se mueve, solo refrescar el cierre
    _ESPERA_STREAM = 60.0     # abierto y con ticks llegando: el stream ya da el precio
    _ESPERA_SOLO_REST = 15.0  # abierto y sin stream: aquí sí es la única fuente
    # Un símbolo se considera "con stream vivo" si ha dado un trade hace poco. Margen amplio
    # a propósito: un valor poco líquido puede pasar un minuto sin cruzar una sola operación
    # y seguir perfectamente conectado.
    _MARGEN_TICK = 120.0

    def _espera_baseline(self, symbol: str) -> float:
        try:
            if not alerts_worker.is_market_open():
                return self._ESPERA_CERRADO
        except Exception:
            return self._ESPERA_SOLO_REST  # ante la duda, la cadencia segura
        ultimo = self._ultimo_tick.get(symbol)
        if ultimo and (_time.time() - ultimo) < self._MARGEN_TICK:
            return self._ESPERA_STREAM
        return self._ESPERA_SOLO_REST

    async def _broadcast(self, symbol: str, payload: dict):
        self._last[symbol] = payload
        dead = []
        for ws in list(self._conns.get(symbol, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(symbol, ws)


_quote_manager = _QuoteManager()


@api_router.websocket("/ws/quote/{symbol}")
async def ws_quote(websocket: WebSocket, symbol: str, token: str = ""):
    """Stream live price updates for a symbol — tick-by-tick via the Finnhub trade
    stream while the market is open, with a 15s REST baseline as fallback.

    Requiere credencial. Cada conexión arranca un bucle REST cada 15s (4 llamadas/min por
    símbolo) contra NUESTRA cuota de Finnhub, así que sin autenticar cualquiera podía abrir
    conexiones para decenas de símbolos y dejar la app sin cuota. Se escapó de las rondas
    anteriores porque los WebSocket no salen al listar las rutas HTTP normales.

    El token va como query param y no en cabecera porque la API de WebSocket del navegador
    no permite cabeceras personalizadas. Se rechaza ANTES de aceptar la conexión, para no
    llegar a arrancar el bucle de cuota.
    """
    try:
        auth.get_current_user(token)
    except HTTPException:
        # 1008 = policy violation. El frontend lo distingue de una caída de red y NO
        # reintenta: pasa al respaldo REST, que al dar 401 lleva a iniciar sesión.
        await websocket.close(code=1008)
        return
    sym = symbol.upper()
    # try/finally, no try/except: si connect() registra el socket y falla DESPUÉS (al
    # arrancar el bucle de sondeo, por ejemplo), o si la tarea se cancela —apagado del
    # servidor, timeout—, el except no se ejecuta y el símbolo se queda con un suscriptor
    # fantasma sondeando cuota de Finnhub para nadie, hasta reiniciar el proceso.
    await _quote_manager.connect(sym, websocket)
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _quote_manager.disconnect(sym, websocket)


# ---------- Mount ----------
app.include_router(api_router)

# Ruta raíz para el health check de Render (evita 404 en /)
@app.get("/")
async def app_root():
    return {"app": "InverIA", "status": "ok"}

# ---------- CORS ----------
# Antes: allow_origins="*" por defecto. Con auth por Bearer eso no expone tu sesión (el
# navegador de un tercero no tiene tu token), pero sí deja que cualquier web invoque los
# endpoints públicos —/dashboard, /quote, /chart— desde el navegador de sus visitantes, o sea
# gastando TU cuota de datos. El defecto pasa a ser restrictivo; para abrirlo hay que pedirlo.
# Origen de PRODUCCIÓN de la web. Es una URL exacta, que es la forma más segura de
# permitir un origen: no hay patrón que pueda colarse por parecido.
_PROD_ORIGIN = "https://inver-ia.vercel.app"
_DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
_cors_origins = os.environ.get("CORS_ORIGINS", "").strip()
_origins_list = [o.strip().rstrip("/") for o in _cors_origins.split(",") if o.strip()]
_allow_all = "*" in _origins_list

# Por DEFECTO no hay patrón: solo valen las URLs exactas de arriba. Antes el defecto era
# https://.*\.vercel\.app, que acepta CUALQUIER dominio de Vercel — cualquiera podía
# desplegar una web ahí y llamar a esta API desde el navegador de sus visitantes.
#
# Si necesitas que funcionen los despliegues de PREVIEW de Vercel (los de cada rama/commit),
# actívalos con CORS_VERCEL_PROJECT=inver-ia. Ten en cuenta el matiz: las URLs de preview son
# <proyecto>-<hash>-<scope>.vercel.app, así que cualquier patrón que las acepte acepta también
# un proyecto ajeno llamado "inver-ia-loquesea". Es el precio de tener previews; por eso no
# viene activado. Para un patrón a medida, CORS_ORIGIN_REGEX.
_vercel_project = os.environ.get("CORS_VERCEL_PROJECT", "").strip()
_default_regex = (
    rf"https://{re.escape(_vercel_project)}(-[a-z0-9-]+)?\.vercel\.app"
    if _vercel_project else None
)
_cors_regex = os.environ.get("CORS_ORIGIN_REGEX", "").strip() or _default_regex

if _allow_all:
    logger.warning(
        "CORS abierto a '*' por configuración explícita. Cualquier web puede llamar a los "
        "endpoints públicos desde el navegador de sus visitantes, gastando tu cuota de datos."
    )
_allowed_origins = ["*"] if _allow_all else (_origins_list or [_PROD_ORIGIN] + _DEV_ORIGINS)

if not _allow_all:
    logger.info("CORS: orígenes permitidos %s · patrón %s",
                ", ".join(_allowed_origins), _cors_regex or "(ninguno)")
    if _cors_regex and ".*" in _cors_regex:
        logger.warning(
            "CORS: el patrón %s es muy amplio y puede aceptar dominios de terceros. "
            "Usa CORS_VERCEL_PROJECT=<nombre> para que se genere uno acotado.", _cors_regex,
        )

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=_allowed_origins,
    allow_origin_regex=None if _allow_all else _cors_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url.path}: {exc}")
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal error: {str(exc)[:200]}"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        },
    )


# Startup/shutdown logic lives in the `lifespan` handler above (FastAPI lifespan API).
