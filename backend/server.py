"""FastAPI server for the InverIA stock analysis app."""
import math
import json
import re
from fastapi import FastAPI, APIRouter, HTTPException, Request, UploadFile, File, Depends, WebSocket, WebSocketDisconnect
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
import newsletter_ingest
import market_regime
import chart_lines
import chartist
import mem
import levels_engine
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

    def set(self, key, val, ttl=30):
        now = _time.time()
        # Opportunistic purge of expired entries.
        if len(self._store) >= self._maxsize:
            expired = [k for k, e in self._store.items() if (now - e["ts"]) >= e["ttl"]]
            for k in expired:
                self._store.pop(k, None)
            # Still over budget -> evict oldest by insertion order.
            while len(self._store) >= self._maxsize:
                self._store.pop(next(iter(self._store)), None)
        self._store[key] = {"val": val, "ts": now, "ttl": ttl}

    def clear(self):
        self._store.clear()

_cache = _TTLCache()

# Coste del pre-cálculo del Chartista (ver _prewarm_chartist). El ciclo va al ritmo de la
# caché, así que subir CHARTIST_TTL baja el consumo de cuota de Gemini proporcionalmente.
CHARTIST_TTL = int(os.environ.get("CHARTIST_TTL", 4 * 3600))   # 4h (antes 2h)
CHARTIST_PREWARM_MAX = int(os.environ.get("CHARTIST_PREWARM_MAX", 20))  # antes 30

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
        plan = result.get("plan") or {}
        accion = (plan.get("accion") or "").upper()
        sentido = (result.get("sentido") or "").lower()
        prev = await db.chartist_state.find_one({"symbol": sym}, {"_id": 0})
        today = datetime.now(timezone.utc).date().isoformat()
        nuevo_estado = {"symbol": sym, "accion": accion, "sentido": sentido,
                        "updated_at": datetime.now(timezone.utc).isoformat()}

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
            _cache._store.pop("signals_hot", None)
    except Exception as e:
        logger.warning(f"Purga de Cimientos falló: {e}")
    await db.analyses.create_index([("symbol", 1), ("created_at", -1)])
    await db.watchlist.create_index("symbol")
    await db.chartist_state.create_index("symbol", unique=True)
    await db.alerts.create_index("symbol")
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
                    # Símbolos que te importan: watchlist (corazón) + cartera (signals).
                    syms = set()
                    for it in await db.watchlist.find({}, {"_id": 0, "symbol": 1}).to_list(200):
                        if it.get("symbol"):
                            syms.add(it["symbol"].upper())
                    for it in await db.signal_entries.find({"active": True}, {"_id": 0, "symbol": 1}).to_list(200):
                        if it.get("symbol"):
                            syms.add(it["symbol"].upper())
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


app = FastAPI(title="InverIA API", default_response_class=SafeJSONResponse, lifespan=lifespan)
api_router = APIRouter(prefix="/api")

logger = logging.getLogger("inveria")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Referencias fuertes a tareas en segundo plano (si no, el GC puede cancelarlas).
_bg_tasks: set = set()


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
    acciones: Optional[float] = None


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
    if not auth.authenticate_user(form_data.username, form_data.password):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token = auth.create_access_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer", "username": form_data.username}


@api_router.get("/auth/me")
async def me(current_user: str = Depends(auth.get_current_user)):
    return {"username": current_user, "authenticated": True}


@api_router.get("/models")
async def available_models():
    return {
        "models": [
            {"value": "gemini-2.5-flash", "label": "Gemini 2.5 Flash (Gratis · Recomendado)", "free": True, "available": True},
            {"value": "gpt-oss-120b", "label": "GPT-OSS 120B (Gratis)", "free": True, "available": True},
            {"value": "gpt-5.2", "label": "GPT-5.2 (Premium)", "free": False, "available": ai_analysis.EMERGENT_AVAILABLE},
        ],
        "premium_available": ai_analysis.EMERGENT_AVAILABLE,
    }


# ---------- Quote ----------
@api_router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    sym = symbol.upper()
    cached = _cache.get(f"quote:{sym}")
    if cached:
        return cached
    q = market_data.get_quote(sym)
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
async def get_chart(symbol: str, timeframe: str = "1Y"):
    sym = symbol.upper()
    cached = _cache.get(f"chart:{sym}:{timeframe}")
    if cached:
        return cached
    df = market_data.get_stock_data(sym, timeframe=timeframe)
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
    if not refresh:
        cached = _cache.get(key)
        if cached:
            return {**cached, "_precomputed": True} if cached_only else cached
    if cached_only:
        return {"cached": False}
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
    _cache.set(key, result, ttl=1800)  # 30 min
    return result


@api_router.get("/indicators/{symbol}")
async def get_indicators(symbol: str):
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
async def get_news(symbol: str):
    sym = symbol.upper()
    cached = _cache.get(f"news:{sym}")
    if cached:
        return cached
    result = {"symbol": sym, "items": market_data.get_news(sym)}
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
MAX_PLAN_DEPTH = float(os.environ.get("MAX_PLAN_DEPTH", "0.30"))


def _deterministic_levels(quote: dict, indicators: dict, buy_levels, price_target) -> dict:
    """#6 — Calcula el conjunto COMPLETO de niveles de forma DETERMINISTA, con etiquetas que
    CUADRAN con el número (el número ES lo que la etiqueta promete). Mata el desajuste
    'la etiqueta dice Fibonacci 161.8% pero el número es otro'. Se pasan a la IA como
    definitivos (solo los narra) y se sobrescriben al final. Devuelve None si no hay zonas de
    confluencia (entonces se usa el flujo clásico con guardianes).

    - entradas: del motor de confluencia (levels_engine, ya rankeado por fuerza)
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
    suelo = price * (1 - MAX_PLAN_DEPTH)
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

    ez = []
    for z in buy_levels[:6]:
        if len(ez) >= 3:
            break
        p = _f(z.get("price"))
        if p is None or p < suelo:
            continue
        zona = _zona(z, len(ez) + 1)
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
    descartadas = sum(1 for z in buy_levels
                      if (_f(z.get("price")) or 0) < suelo and _f(z.get("price")) is not None)
    plan_nota = None
    if descartadas:
        plan_nota = (
            f"El plan usa {len(ez)} de las {len(ez) + descartadas} zonas de confluencia: "
            f"las demás están a más de un {MAX_PLAN_DEPTH:.0%} bajo el precio y arrastrarían "
            f"el stop hasta ahí. Siguen listadas como soportes."
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
    cands = []
    t1 = next((r for r in res_up if r >= min_tp1), None)
    cands.append((t1, f"TP1 — Resistencia con R/R ≥ {MIN_RR:g}") if t1 else (round(min_tp1, 2), f"TP1 — Objetivo por R/R ≥ {MIN_RR:g}"))
    if fib127:
        cands.append((fib127, "TP2 — Extensión Fibonacci 127,2%"))
    t2r = next((r for r in res_up if r > (t1 or min_tp1) * 1.02), None)
    if t2r:
        cands.append((t2r, "TP — Siguiente resistencia"))
    if analyst:
        cands.append((analyst, "TP — Objetivo medio de analistas"))
    if fib161:
        cands.append((fib161, "TP — Extensión Fibonacci 161,8%"))

    tps, vistos = [], set()
    for val, lab in sorted(((v, l) for v, l in cands if v), key=lambda x: x[0]):
        capped = round(_cap(val), 2)
        if capped <= price or capped in vistos:   # capar ANTES de filtrar por precio
            continue
        vistos.add(capped)
        # Si el cap ha mordido el valor, la etiqueta original ya no describe el número.
        lab_final = lab if abs(capped - round(val, 2)) < 0.01 else "TP — Techo realista (máx. 52s / analistas)"
        tps.append({"label": lab_final, "price": capped, "comment": ""})
        if len(tps) >= 3:
            break
    if not tps:
        tps = [{"label": "TP1 — Objetivo técnico", "price": round(price * 1.05, 2), "comment": ""}]
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
        loop.run_in_executor(None, polygon_data.get_volume_profile, symbol, 365),
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
        "buy_levels": buy_levels or [],
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
    return nuevo


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

    results = await asyncio.gather(
        _timed("quote", market_data.get_quote, sym),
        _timed("chart", partial(market_data.get_stock_data, sym, timeframe=timeframe)),
        _timed("indicators", market_data.get_full_indicator_history, sym),
        _timed("news", market_data.get_news, sym),
        _timed("trends", _cached_trends, sym),
        _timed("price_target", _cached_price_target, sym),
        _timed("vp", partial(polygon_data.get_volume_profile, sym, 365)),
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

    # Fill missing fundamentals from Finnhub if yfinance returned an incomplete quote
    quote = await _timed("enrich", _enrich_quote_fundamentals, quote, sym)

    # Extended hours (pre-market / after-hours): añade estado + precio + % al quote para que
    # el header del dashboard lo muestre igual que la watchlist. Cacheado 60s (dato volátil).
    if quote:
        try:
            ext = _cache.get(f"ext:{sym}")
            if ext is None:
                ext = await asyncio.to_thread(market_data.get_extended_quote, sym)
                _cache.set(f"ext:{sym}", ext or {}, ttl=60)
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
        "market_regime": await asyncio.to_thread(market_regime.get_market_regime),
        "data_health": health,
        # Cuándo se calculó DE VERDAD todo lo pesado. Al servirse caducado, la cotización se
        # refresca aparte pero esta marca no cambia: así queda claro de cuándo es el resto.
        "generado_en": datetime.now(timezone.utc).isoformat(),
    }
    _cache.set(cache_key, result, ttl=300)
    return result


@api_router.get("/market-regime")
async def market_regime_endpoint():
    """Semáforo de mercado (S&P vs SMA200 + tendencia) — condiciona la fiabilidad de las
    señales de compra. 🟢 sano · 🟡 transición · 🔴 riesgo."""
    return market_regime.get_market_regime()


@api_router.get("/market/sentiment")
async def market_sentiment_endpoint():
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
            market_data.get_finnhub_limiter().acquire()
            return market_data.get_http_session().get(
                "https://finnhub.io/api/v1/search",
                params={"q": q, "token": key}, timeout=6,
            )
        r = await asyncio.to_thread(_call)
        ok = r.status_code == 200
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
async def market_heatmap():
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


async def _mentions_by_ticker(days: int = 30) -> dict:
    """Mapa ticker → {menciones, positivos, negativos, fuentes} desde lo que dicen tus
    fuentes (Telegram + newsletters) en los últimos `days` días."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = await db.newsletter_summaries.find(
        {"received_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("received_at", -1).to_list(300)
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
async def fuentes_de_accion(symbol: str, days: int = 30):
    """Qué han dicho TUS fuentes (Telegram + newsletters) de esta acción: cada mención
    con su fuente, sentimiento, tesis y fecha. Para mostrarlo junto al análisis."""
    from datetime import timedelta
    sym = symbol.strip().upper()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = await db.newsletter_summaries.find(
        {"received_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("received_at", -1).to_list(300)
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
                "fecha": d.get("received_at"), "inveria": a.get("inveria"),
            })
    return {"symbol": sym, "n": len(menciones), "positivos": pos, "negativos": neg,
            "menciones": menciones[:20]}


# ---------- Radar: inteligencia acumulada de todas las newsletters ----------
@api_router.get("/radar")
async def radar(days: int = 14):
    """Recopila TODA la información de las newsletters recibidas en los últimos `days` días
    y la divide en dos: (1) ACCIONES agregadas (cada ticker, cuántas fuentes lo mencionan,
    con qué ángulo y el veredicto del motor), y (2) INFORMACIÓN (feed de resúmenes)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = await db.newsletter_summaries.find(
        {"received_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("received_at", -1).to_list(200)

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
                "acciones_reco": set(), "inveria": a.get("inveria"), "ultima": when,
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
            if a.get("inveria") and not slot.get("inveria"):
                slot["inveria"] = a["inveria"]
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
            "inveria": s.get("inveria"),
            "ultima": s["ultima"],
        })
    # Ordena por nº de fuentes distintas (consenso) y menciones.
    acciones.sort(key=lambda x: (x["n_fuentes"], x["menciones"]), reverse=True)

    # Reconcilia el veredicto con el motor EN VIVO: el "inveria" guardado es una foto
    # del día que llegó el email y puede estar rancio. NO bloqueamos la respuesta con
    # esto: puntuar 25 tickers (quote+financials+consenso) tarda demasiado y el Radar
    # deja de cargar. En su lugar: servimos al instante lo que haya en caché fresca y
    # lanzamos el recálculo en SEGUNDO PLANO para que la próxima carga ya esté fresca.
    top = acciones[:25]
    faltan = []
    for item in top:
        fresh = _cache.get(f"radar_score_{item['ticker']}")
        if fresh is not None:
            item["inveria"] = fresh
            item["inveria_actualizado"] = True
        else:
            faltan.append(item["ticker"])

    if faltan:
        async def _refresh_bg(tickers):
            sem = asyncio.Semaphore(5)

            async def _one(tk):
                async with sem:
                    try:
                        fresh = await newsletter_ingest._score_ticker(tk)
                    except Exception:
                        fresh = None
                if fresh is not None:
                    _cache.set(f"radar_score_{tk}", fresh, ttl=1800)  # 30 min
            await asyncio.gather(*[_one(tk) for tk in tickers], return_exceptions=True)

        task = asyncio.create_task(_refresh_bg(faltan))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)

    return {
        "days": days,
        "total_newsletters": len(docs),
        "acciones": acciones,
        "informacion": info_feed[:40],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@api_router.api_route("/inbound/news/ingest", methods=["GET", "POST"])
async def inbound_news_ingest(token: str = ""):
    """Dispara la ingesta de noticias de mercado al vuelo (para probar). Protegido."""
    _check_inbound_token(token)
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
async def brain_overview():
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
async def track_record(days: int = 180, refresh: bool = False):
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
async def list_watchlist():
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
async def list_watchlist_symbols():
    """Solo los tickers de la watchlist (sin cotizaciones). Ligero: para que el botón de
    corazón sepa al instante si la acción actual ya está guardada."""
    items = await db.watchlist.find({}, {"_id": 0, "symbol": 1}).to_list(500)
    return [it["symbol"] for it in items if it.get("symbol")]


@api_router.post("/watchlist")
async def add_watchlist(item: WatchlistCreate):
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
async def remove_watchlist(symbol: str):
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
async def list_alerts():
    items = await db.alerts.find({}, {"_id": 0}).to_list(500)
    return items


@api_router.post("/alerts")
async def add_alert(item: PriceAlertCreate):
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


@api_router.delete("/alerts/{alert_id}")
async def remove_alert(alert_id: str):
    res = await db.alerts.delete_one({"id": alert_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Alerta no encontrada")
    return {"deleted": alert_id}


# ---------- Market overview (popular tickers) ----------
@api_router.get("/market/popular")
async def popular_stocks():
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
@api_router.get("/analyst/{symbol}")
async def analyst_data(symbol: str):
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
async def sentiment_news(symbol: str):
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
async def earnings_calendar(days: int = 14, symbols: Optional[str] = None, refresh: bool = False):
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
async def history_by_symbol(symbol: str, limit: int = 20):
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
async def history_all(limit: int = 30):
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
        mom = r.get("momentum") or ""
        if mom and not mom.startswith("⚠"):
            razones.append("momentum sano")
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


# ---------- Analista Institucional ----------
@api_router.get("/analyst/ideas")
async def analyst_ideas(limit: int = 30):
    """Histórico de ideas que el Analista Institucional ha detectado (más recientes primero)."""
    items = await db.analyst_ideas.find({}, {"_id": 0}).sort("detected_at", -1).limit(limit).to_list(limit)
    return {"ideas": items}


@api_router.post("/analyst/scan")
async def analyst_scan(notify: bool = False, _user: str = Depends(auth.get_current_user)):
    """Lanza un barrido manual del Analista Institucional. Con notify=false solo devuelve
    las candidatas (para probar sin enviar Telegram); con notify=true además avisa."""
    return await daily_analyst.scan(db, notify=notify)


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
    secret = os.environ.get("INBOUND_SECRET")
    if not secret or token != secret:
        raise HTTPException(401, "Token de entrada inválido.")


@api_router.get("/telegram/status")
async def telegram_status(token: str = ""):
    _check_inbound_token(token)
    import telegram_reader
    return await telegram_reader.status(db)


@api_router.post("/telegram/login/start")
async def telegram_login_start(request: Request, token: str = ""):
    _check_inbound_token(token)
    import telegram_reader
    payload = await request.json()
    phone = (payload.get("phone") or "").strip()
    if not phone:
        raise HTTPException(400, "Falta el teléfono (con prefijo, ej. +34...).")
    return await telegram_reader.login_start(phone)


@api_router.post("/telegram/login/code")
async def telegram_login_code(request: Request, token: str = ""):
    _check_inbound_token(token)
    import telegram_reader
    payload = await request.json()
    return await telegram_reader.login_code(
        db, str(payload.get("code") or "").strip(), str(payload.get("password") or "").strip())


@api_router.get("/telegram/dialogs")
async def telegram_dialogs(token: str = ""):
    _check_inbound_token(token)
    import telegram_reader
    return await telegram_reader.list_dialogs(db)


@api_router.post("/telegram/capture")
async def telegram_capture(request: Request, token: str = ""):
    _check_inbound_token(token)
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
    provided = token or request.headers.get("x-inbound-token") or ""
    if provided != secret:
        raise HTTPException(401, "Token de entrada inválido.")

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
async def inbound_newsletter_backfill(token: str = "", limit: int = 200):
    """Reprocesa los correos ya guardados para poblar el cerebro (investing_knowledge)
    con el método/sabiduría que enseñan. Protegido con INBOUND_SECRET. Acepta GET para
    poder lanzarlo tocando un enlace desde el móvil."""
    secret = os.environ.get("INBOUND_SECRET")
    if not secret or token != secret:
        raise HTTPException(401, "Token de entrada inválido.")

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
async def inbound_newsletter_dedupe(token: str = ""):
    """Fusiona principios casi idénticos del cerebro (dedup semántico) y reconstruye el
    cache. Protegido con INBOUND_SECRET. Acepta GET para lanzarlo desde el móvil."""
    secret = os.environ.get("INBOUND_SECRET")
    if not secret or token != secret:
        raise HTTPException(401, "Token de entrada inválido.")
    import knowledge_base
    result = await knowledge_base.dedupe_semantic(db)
    return {"ok": True, **result}


@api_router.api_route("/inbound/newsletter/dedupe-knowledge-llm", methods=["GET", "POST"])
async def inbound_newsletter_dedupe_llm(token: str = ""):
    """Dedup SEMÁNTICO con LLM (entiende paráfrasis) del cerebro. Tarda (varias llamadas
    al modelo), así que va en segundo plano; mira el resultado en /knowledge (baja el nº
    de principios). Protegido con INBOUND_SECRET."""
    secret = os.environ.get("INBOUND_SECRET")
    if not secret or token != secret:
        raise HTTPException(401, "Token de entrada inválido.")
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
async def inbound_newsletter_fix_encoding(token: str = ""):
    """Repara el mojibake (acentos corruptos: 'selecciÃ³n' → 'selección') de los
    principios ya guardados en el cerebro y reconstruye el cache. Acepta GET para
    lanzarlo desde el móvil."""
    secret = os.environ.get("INBOUND_SECRET")
    if not secret or token != secret:
        raise HTTPException(401, "Token de entrada inválido.")
    import knowledge_base
    result = await knowledge_base.fix_existing_encoding(db)
    return {"ok": True, **result}


@api_router.get("/inbound/newsletter/knowledge")
async def inbound_newsletter_knowledge(token: str = ""):
    """Estado del cerebro: cuántos principios ha aprendido y el digest actual."""
    secret = os.environ.get("INBOUND_SECRET")
    if not secret or token != secret:
        raise HTTPException(401, "Token de entrada inválido.")
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
async def inbound_newsletter_debug(token: str = ""):
    """Diagnóstico: devuelve el resultado de los últimos procesados de newsletter
    (extracción / envío de email) para depurar sin acceso a los logs de Render.
    Protegido con el mismo INBOUND_SECRET."""
    secret = os.environ.get("INBOUND_SECRET")
    if not secret or token != secret:
        raise HTTPException(401, "Token de entrada inválido.")
    return {
        "resend_configurado": bool(os.environ.get("RESEND_API_KEY")),
        "destino": (os.environ.get("ANALYST_RECIPIENT_EMAIL")
                    or os.environ.get("ALERT_RECIPIENT_EMAIL") or "(SIN DESTINO)"),
        "from": (os.environ.get("ALERT_FROM_EMAIL")
                 or os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"),
        "ultimos_procesados": newsletter_ingest._LAST_RUNS,
    }


@api_router.get("/backtest/{symbol}")
async def backtest_levels(symbol: str, window: int = 60):
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
    _cache.set(ck, result, ttl=21600)  # 6h
    mem.trim()  # el histórico (2 años) es un DataFrame grande: devuélvelo al SO
    return result


_universe_bt_lock = asyncio.Lock()


@api_router.get("/backtest")
async def backtest_universe_endpoint(window: int = 60, limit: int = 30):
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
async def market_futures():
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


@api_router.get("/market/movers")
async def market_movers():
    """Biggest gainers / losers / most-active US stocks (Financial Modeling Prep)."""
    cached = _cache.get("market_movers")
    if cached is not None:
        return cached
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, fmp_data.get_market_movers)
    _cache.set("market_movers", data, ttl=600)  # 10 min
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
    entry = await signal_table.create_entry(db, item.model_dump())
    _cache._store.pop("signals_list", None)
    _cache._store.pop("signals_hot", None)
    return entry


@api_router.patch("/signals/{entry_id}")
async def update_signal(entry_id: str, item: SignalEntryUpdate, _user: str = Depends(auth.get_current_user)):
    # exclude_unset: distingue "no enviado" de "enviado como null". Antes se filtraban todos
    # los None, así que era IMPOSIBLE borrar compra/acciones/venta1-3: el valor viejo volvía.
    data = item.model_dump(exclude_unset=True)
    updated = await signal_table.update_entry(db, entry_id, data)
    if not updated:
        raise HTTPException(404, "Señal no encontrada")
    _cache._store.pop("signals_list", None)
    _cache._store.pop("signals_hot", None)
    return updated


@api_router.delete("/signals/{entry_id}")
async def delete_signal(entry_id: str, _user: str = Depends(auth.get_current_user)):
    ok = await signal_table.delete_entry(db, entry_id)
    if not ok:
        raise HTTPException(404, "Señal no encontrada")
    _cache._store.pop("signals_list", None)
    _cache._store.pop("signals_hot", None)
    return {"deleted": entry_id}


@api_router.post("/signals/bulk")
async def bulk_import_signals(payload: SignalBulkImport, _user: str = Depends(auth.get_current_user)):
    result = await signal_table.bulk_upsert(db, payload.rows)
    _cache._store.pop("signals_list", None)
    _cache._store.pop("signals_hot", None)
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
    _cache._store.pop("signals_hot", None)
    return {**result, "rows": rows, "saved": True}


# ---------- Alert History ----------
@api_router.get("/alerts/history")
async def get_alert_history(limit: int = 50, _user: str = Depends(auth.get_current_user)):
    """Historial de alertas disparadas (últimas 50)."""
    items = await db.alert_history.find({}, {"_id": 0}).sort("fired_at", -1).limit(limit).to_list(limit)
    return items


@api_router.delete("/alerts/history")
async def clear_alert_history(_user: str = Depends(auth.get_current_user)):
    """Borra todo el historial."""
    await db.alert_history.delete_many({})
    return {"ok": True}


# ---------- Hot Signals (señales calientes para el Dashboard) ----------
@api_router.get("/signals/hot")
async def hot_signals(limit: int = 5, _user: str = Depends(auth.get_current_user)):
    """Devuelve las acciones con precio más cercano a algún nivel de compra o venta.
    Usa last_price guardado por el worker en MongoDB — respuesta instantánea."""
    cached = _cache.get("signals_hot")
    if cached is not None:
        return cached
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
            if best_pct is not None and best_pct <= 10:  # solo si está a menos del 10%
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
    results.sort(key=lambda x: x["pct_away"])
    top = results[:limit]
    _cache.set("signals_hot", top, ttl=300)
    return top


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
        await self._ensure_fh_stream()
        await self._fh_send({"type": "subscribe", "symbol": symbol})

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
            # Defer the Finnhub unsubscribe / stream teardown to a lock-guarded coroutine
            # so it can't race with a concurrent connect (which would spawn a 2nd stream).
            asyncio.create_task(self._cleanup_symbol(symbol))

    async def _cleanup_symbol(self, symbol: str):
        async with self._lock:
            await self._fh_send({"type": "unsubscribe", "symbol": symbol})
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
                    for sym in list(self._conns.keys()):
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

    async def _on_trade(self, symbol: str, price):
        if not symbol or price is None or symbol not in self._conns:
            return
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
        await self._broadcast(symbol, payload)

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
            await asyncio.sleep(15)  # light: 4 REST calls/min per symbol

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
    await _quote_manager.connect(sym, websocket)
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
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
