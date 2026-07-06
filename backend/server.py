"""FastAPI server for the InverIA stock analysis app."""
import math
import json
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
    def render(self, content) -> bytes:
        return json.dumps(_clean_nans(content), ensure_ascii=False).encode("utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ----- Startup -----
    # DB indexes
    await db.signal_entries.create_index("symbol")
    await db.signal_entries.create_index("active")
    await db.analyses.create_index([("symbol", 1), ("created_at", -1)])
    await db.watchlist.create_index("symbol")
    await db.alerts.create_index("symbol")
    await db.analyst_ideas.create_index([("symbol", 1), ("detected_at", -1)])

    # Wire the persistent snapshot cache and hydrate in-memory caches from the last
    # saved scan so the first request returns data instantly (no "warming" screen).
    opportunities.set_db(db)
    try:
        await opportunities.load_snapshots_into_cache()
    except Exception as e:
        logger.warning(f"Snapshot hydrate failed: {e}")

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
    alert_deseado: Optional[bool] = True
    alert_nivel1: Optional[bool] = True
    alert_nivel2: Optional[bool] = True
    alert_nivel3: Optional[bool] = True
    alert_nivel4: Optional[bool] = True
    alert_nivel5: Optional[bool] = True
    riesgo: Optional[str] = ""
    sector: Optional[str] = ""
    posibles_ganancias: Optional[float] = None
    notes: Optional[str] = ""
    active: Optional[bool] = True
    divisa: Optional[str] = ""
    bz: Optional[float] = None
    objetivo_5a: Optional[float] = None


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
    alert_deseado: Optional[bool] = None
    alert_nivel1: Optional[bool] = None
    alert_nivel2: Optional[bool] = None
    alert_nivel3: Optional[bool] = None
    alert_nivel4: Optional[bool] = None
    alert_nivel5: Optional[bool] = None
    riesgo: Optional[str] = None
    sector: Optional[str] = None
    posibles_ganancias: Optional[float] = None
    notes: Optional[str] = None
    active: Optional[bool] = None
    divisa: Optional[str] = None
    bz: Optional[float] = None
    objetivo_5a: Optional[float] = None


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


# ---------- AI Analysis ----------
@api_router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    symbol = req.symbol.upper()
    loop = asyncio.get_running_loop()

    # quote y df son operaciones bloqueantes e independientes: las sacamos del event
    # loop y las corremos en paralelo (antes bloqueaban ~3-5s con 1 solo worker).
    quote, df = await asyncio.gather(
        loop.run_in_executor(None, market_data.get_quote, symbol),
        loop.run_in_executor(None, market_data.get_full_indicator_history, symbol),
    )
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

    # Guarantee real support/resistance levels and realistic take-profits regardless
    # of how the model filled them (key_levels can come back empty -> NaN in the UI).
    # Seed the supports with the confluence engine's zones so the floor is always solid.
    if buy_levels and isinstance(result, dict):
        kl = result.get("key_levels") if isinstance(result.get("key_levels"), dict) else {}
        existing = kl.get("support") if isinstance(kl.get("support"), list) else []
        kl["support"] = [z["price"] for z in buy_levels] + list(existing)
        result["key_levels"] = kl
    result = _ensure_key_levels(result, indicators_data, vp, quote.get("price"))
    result = _cap_take_profits(result, quote.get("high_52w"))

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
async def why_moving(symbol: str, model: Optional[str] = None):
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
async def compare_stocks(req: CompareRequest):
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
@api_router.get("/dashboard/{symbol}")
async def dashboard_data(symbol: str, timeframe: str = "1Y"):
    """Endpoint combinado: devuelve quote + chart + indicators + news + analyst en una sola llamada.
    Todas las peticiones a Yahoo Finance / Finnhub se lanzan en paralelo via thread pool."""
    sym = symbol.upper()
    cache_key = f"dashboard:{sym}:{timeframe}"
    cached = _cache.get(cache_key)
    if cached:
        return cached

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
        return_exceptions=True,
    )
    quote, df_chart, df_ind, news_items, trends, price_target, vp = results
    _dt_total = _time.time() - _t_total
    if _dt_total > 8.0:
        logger.warning("dashboard[%s] TOTAL fetch LENTO: %.1fs", sym, _dt_total)

    if not quote or isinstance(quote, Exception):
        raise HTTPException(404, f"No se encontraron datos para '{sym}'")

    # Fill missing fundamentals from Finnhub if yfinance returned an incomplete quote
    quote = await _timed("enrich", _enrich_quote_fundamentals, quote, sym)

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
        "market_regime": market_regime.get_market_regime(),
    }
    _cache.set(cache_key, result, ttl=300)
    return result


@api_router.get("/market-regime")
async def market_regime_endpoint():
    """Semáforo de mercado (S&P vs SMA200 + tendencia) — condiciona la fiabilidad de las
    señales de compra. 🟢 sano · 🟡 transición · 🔴 riesgo."""
    return market_regime.get_market_regime()


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
    import re as _re
    def _clean_source(sender: str, subject: str) -> str:
        """Nombre legible de la fuente. Make a veces manda el 'from' como objeto JSON
        ({"address":"x@y.com","name":"The Daily Upside"}) o como 'Nombre <x@y.com>'."""
        s = sender or ""
        # 1) Si trae un "name":"..." (JSON de Make), úsalo.
        m = _re.search(r'"name"\s*:\s*"([^"]+)"', s, _re.I)
        if m and m.group(1).strip():
            return m.group(1).strip()
        # 2) "Nombre <email>" → el nombre.
        m = _re.match(r'\s*([^<@"]+?)\s*<', s)
        if m and m.group(1).strip():
            return m.group(1).strip()
        # 3) Dominio del email como último recurso.
        m = _re.search(r'@([\w.-]+)', s)
        if m:
            dom = m.group(1).split(".")[0]
            return dom.replace("-", " ").title()
        return (subject or "Newsletter")[:40]

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
    # del día que llegó el email y puede estar rancio (un ticker bueno marcado como
    # "Evítala" por un bajón puntual ya superado). Recalculamos el score fresco para
    # los más relevantes, con límite de concurrencia y caché para no saturar las APIs.
    top = acciones[:25]
    sem = asyncio.Semaphore(5)

    async def _refresh(item):
        cache_key = f"radar_score_{item['ticker']}"
        fresh = _cache.get(cache_key)
        if fresh is None:
            async with sem:
                fresh = await newsletter_ingest._score_ticker(item["ticker"])
            if fresh is not None:
                _cache.set(cache_key, fresh, ttl=1800)  # 30 min
        if fresh is not None:
            item["inveria"] = fresh
            item["inveria_actualizado"] = True

    await asyncio.gather(*[_refresh(a) for a in top], return_exceptions=True)

    return {
        "days": days,
        "total_newsletters": len(docs),
        "acciones": acciones,
        "informacion": info_feed[:40],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


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
async def earnings_calendar(days: int = 14, symbols: Optional[str] = None):
    """Upcoming earnings from Finnhub. Always fetches 60 days and caches by symbols only;
    the day range is then filtered in-memory so every day-filter combo shares the same cache."""
    from datetime import datetime, timedelta
    sym_list = sorted({s.strip().upper() for s in symbols.split(",") if s.strip()}) if symbols else []
    # Cache key ignores `days` — we always fetch 60d and slice in memory
    cache_key = f"earnings60:{','.join(sym_list)}"
    cached = _cache.get(cache_key)
    if cached is None:
        sym_filter = set(sym_list) if sym_list else None
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            None, lambda: external_data.finnhub_earnings_calendar(days=60, symbols=sym_filter)
        )
        cached = data or {"items": []}
        _cache.set(cache_key, cached, ttl=7200)  # 2h — earnings don't change intraday

    # Filter down to the requested day window
    cutoff = (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()
    filtered = [it for it in (cached.get("items") or []) if (it.get("date") or "") <= cutoff]
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
async def test_email():
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
async def daily_opportunities(refresh: bool = False):
    data = await opportunities.scan_daily_opportunities(force_refresh=refresh)
    return data


@api_router.get("/opportunities/screener")
async def growth_screener(refresh: bool = False):
    """Growth screener: 7 hard filters (market cap, price, no dividend, volume,
    near 52w high, revenue growth, EPS growth) over a curated growth universe."""
    data = await opportunities.scan_growth_screener(force_refresh=refresh)
    return data


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


_backtest_cache: dict = {}


@api_router.get("/backtest/{symbol}")
async def backtest_levels(symbol: str, window: int = 60):
    """Walk-forward backtest of the confluence buy-levels engine for one symbol.
    Returns empirical hold rates by strength bucket (how often price actually
    bounced at each level type, with no lookahead). Cached 6h per symbol."""
    sym = symbol.upper()
    ck = f"{sym}:{window}"
    cached = _backtest_cache.get(ck)
    if cached and (datetime.now(timezone.utc) - cached["ts"]).total_seconds() < 21600:
        return cached["data"]

    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, market_data.get_full_indicator_history, sym)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No hay histórico suficiente para esta acción.")

    result = await loop.run_in_executor(
        None, lambda: backtest.backtest_symbol(df, forward_window=window)
    )
    result["symbol"] = sym
    _backtest_cache[ck] = {"data": result, "ts": datetime.now(timezone.utc)}
    return result


_universe_bt_cache: dict = {}
_universe_bt_lock = asyncio.Lock()


@api_router.get("/backtest")
async def backtest_universe_endpoint(window: int = 60, limit: int = 30):
    """Aggregate walk-forward backtest across the opportunities universe. Pools
    hundreds of point-in-time touches so the hold-rate-by-strength is statistically
    meaningful (single symbols give too few samples). Heavy: cached 24h."""
    ck = f"{window}:{limit}"
    cached = _universe_bt_cache.get(ck)
    if cached and (datetime.now(timezone.utc) - cached["ts"]).total_seconds() < 86400:
        return cached["data"]

    if _universe_bt_lock.locked():
        if cached:
            return cached["data"]
        return {"status": "running", "message": "Backtest del universo en curso, vuelve en un minuto."}

    async with _universe_bt_lock:
        symbols = opportunities.UNIVERSE[:limit]
        loop = asyncio.get_event_loop()

        def _load(sym):
            return market_data.get_full_indicator_history(sym)

        result = await loop.run_in_executor(
            None, lambda: backtest.backtest_universe(_load, symbols, forward_window=window)
        )
        _universe_bt_cache[ck] = {"data": result, "ts": datetime.now(timezone.utc)}
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
    entry = await signal_table.create_entry(db, item.model_dump())
    _cache._store.pop("signals_list", None)
    _cache._store.pop("signals_hot", None)
    return entry


@api_router.patch("/signals/{entry_id}")
async def update_signal(entry_id: str, item: SignalEntryUpdate, _user: str = Depends(auth.get_current_user)):
    data = {k: v for k, v in item.model_dump().items() if v is not None}
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
async def ws_quote(websocket: WebSocket, symbol: str):
    """Stream live price updates for a symbol — tick-by-tick via the Finnhub trade
    stream while the market is open, with a 15s REST baseline as fallback."""
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

_cors_origins = os.environ.get("CORS_ORIGINS", "*")
_origins_list = [o.strip().rstrip("/") for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=_origins_list if "*" not in _origins_list else ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app",
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
