"""FastAPI server for the InverIA stock analysis app."""
from fastapi import FastAPI, APIRouter, HTTPException, Request, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import certifi
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone, timedelta

import asyncio
from functools import partial
import market_data
import indicators as ind
import ai_analysis
import external_data
import alerts_worker
import opportunities
import signal_table
import auth

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ── Simple in-memory TTL cache ────────────────────────────────────────────────
import time as _time

class _TTLCache:
    def __init__(self):
        self._store = {}

    def get(self, key):
        entry = self._store.get(key)
        if entry and (_time.time() - entry["ts"]) < entry["ttl"]:
            return entry["val"]
        return None

    def set(self, key, val, ttl=30):
        self._store[key] = {"val": val, "ts": _time.time(), "ttl": ttl}

    def clear(self):
        self._store.clear()

_cache = _TTLCache()

mongo_url = os.environ["MONGO_URL"]
# For MongoDB Atlas (mongodb+srv://) use bundled CA certs to avoid SSL handshake errors
_mongo_kwargs = {}
if "mongodb+srv://" in mongo_url or "mongodb.net" in mongo_url:
    _mongo_kwargs = {"tls": True, "tlsCAFile": certifi.where()}
client = AsyncIOMotorClient(mongo_url, **_mongo_kwargs)
db = client[os.environ["DB_NAME"]]


app = FastAPI(title="InverIA API")
api_router = APIRouter(prefix="/api")

logger = logging.getLogger("inveria")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


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
    model: Optional[str] = "gpt-oss-120b"



class SignalEntryCreate(BaseModel):
    symbol: str
    name: Optional[str] = ""
    mercado: Optional[str] = ""
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


class SignalEntryUpdate(BaseModel):
    name: Optional[str] = None
    mercado: Optional[str] = None
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


class SignalBulkImport(BaseModel):
    rows: List[dict]


# ---------- Health ----------
@api_router.get("/")
async def root():
    return {"app": "InverIA", "status": "ok"}


@api_router.get("/health")
async def health():
    """Lightweight endpoint used by external cron pings (cron-job.org / GitHub Actions)
    to keep the Render free tier instance warm so the alerts worker keeps running."""
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
            {"value": "gpt-oss-120b", "label": "GPT-OSS 120B (Gratis · Recomendado)", "free": True, "available": True},
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
@api_router.get("/chart/{symbol}")
async def get_chart(symbol: str, timeframe: str = "1Y"):
    sym = symbol.upper()
    cached = _cache.get(f"chart:{sym}:{timeframe}")
    if cached:
        return cached
    df = market_data.get_stock_data(sym, timeframe=timeframe)
    if df is None or df.empty:
        raise HTTPException(404, f"No hay datos históricos para '{sym}'")
    result = {"symbol": sym, "timeframe": timeframe, "candles": market_data.df_to_candles(df)}
    _cache.set(f"chart:{sym}:{timeframe}", result, ttl=300)  # 5 min
    return result


@api_router.get("/indicators/{symbol}")
async def get_indicators(symbol: str):
    sym = symbol.upper()
    cached = _cache.get(f"indicators:{sym}")
    if cached:
        return cached
    df = market_data.get_full_indicator_history(sym)
    if df is None or df.empty:
        raise HTTPException(404, f"No hay datos para indicadores: '{sym}'")
    result = ind.compute_all(df)
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


# ---------- AI Analysis ----------
@api_router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    symbol = req.symbol.upper()
    quote = market_data.get_quote(symbol)
    if not quote:
        raise HTTPException(404, f"Símbolo no encontrado: {symbol}")

    df = market_data.get_full_indicator_history(symbol)
    if df is None or df.empty:
        raise HTTPException(404, f"Sin datos suficientes para analizar {symbol}")

    indicators_data = ind.compute_all(df)
    news = market_data.get_news(symbol, limit=5)

    # Enrich with analyst consensus
    trends = external_data.finnhub_recommendation_trends(symbol)
    analyst_consensus = external_data.aggregate_recommendation(trends)
    price_target = external_data.finnhub_price_target(symbol)

    try:
        result = await ai_analysis.analyze_stock(
            quote,
            indicators_data,
            news,
            model_key=req.model or "gpt-oss-120b",
            analyst_consensus=analyst_consensus,
            price_target=price_target,
        )
    except Exception as e:
        logger.exception("AI analysis failed")
        raise HTTPException(500, f"Error de análisis IA: {e}")

    # Persist
    doc = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "model": req.model,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "quote_snapshot": quote,
        "indicators_snapshot": indicators_data,
        "result": result,
    }
    await db.analyses.insert_one(doc)

    return {
        "symbol": symbol,
        "model": req.model,
        "quote": quote,
        "indicators": indicators_data,
        "analysis": result,
        "news": news,
        "analyst_consensus": analyst_consensus,
        "price_target": price_target,
    }


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

    # 6 llamadas bloqueantes en paralelo (thread pool)
    results = await asyncio.gather(
        loop.run_in_executor(None, market_data.get_quote, sym),
        loop.run_in_executor(None, partial(market_data.get_stock_data, sym, timeframe=timeframe)),
        loop.run_in_executor(None, market_data.get_full_indicator_history, sym),
        loop.run_in_executor(None, market_data.get_news, sym),
        loop.run_in_executor(None, external_data.finnhub_recommendation_trends, sym),
        loop.run_in_executor(None, external_data.finnhub_price_target, sym),
        return_exceptions=True,
    )
    quote, df_chart, df_ind, news_items, trends, price_target = results

    if not quote or isinstance(quote, Exception):
        raise HTTPException(404, f"No se encontraron datos para '{sym}'")

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
                indicators_data = ind.compute_all(df_ind)
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

    # Actualizar cachés individuales para que los endpoints separados también sean rápidos
    _cache.set(f"quote:{sym}", quote, ttl=60)
    _cache.set(f"chart:{sym}:{timeframe}", {"symbol": sym, "timeframe": timeframe, "candles": candles}, ttl=300)
    if indicators_data:
        _cache.set(f"indicators:{sym}", indicators_data, ttl=300)
    if news_list:
        _cache.set(f"news:{sym}", {"symbol": sym, "items": news_list}, ttl=1800)
    _cache.set(f"analyst:{sym}", analyst, ttl=900)

    result = {
        "symbol": sym,
        "timeframe": timeframe,
        "quote": quote,
        "candles": candles,
        "indicators": indicators_data,
        "news": news_list,
        "analyst": analyst,
    }
    _cache.set(cache_key, result, ttl=60)
    return result


# ---------- Watchlist ----------
@api_router.get("/watchlist")
async def list_watchlist():
    items = await db.watchlist.find({}, {"_id": 0}).to_list(200)
    if not items:
        return []
    loop = asyncio.get_running_loop()
    quotes = await asyncio.gather(
        *[loop.run_in_executor(None, market_data.get_quote, it["symbol"]) for it in items],
        return_exceptions=True,
    )
    return [
        {**it, "quote": q if not isinstance(q, Exception) else None}
        for it, q in zip(items, quotes)
    ]


@api_router.post("/watchlist")
async def add_watchlist(item: WatchlistCreate):
    symbol = item.symbol.upper().strip()
    existing = await db.watchlist.find_one({"symbol": symbol})
    if existing:
        raise HTTPException(409, f"{symbol} ya está en la watchlist")
    # validate symbol exists
    q = market_data.get_quote(symbol)
    if not q:
        raise HTTPException(404, f"Símbolo no válido: {symbol}")
    obj = WatchlistItem(symbol=symbol)
    await db.watchlist.insert_one(obj.model_dump())
    return {**obj.model_dump(), "quote": q}


@api_router.delete("/watchlist/{symbol}")
async def remove_watchlist(symbol: str):
    res = await db.watchlist.delete_one({"symbol": symbol.upper()})
    if res.deleted_count == 0:
        raise HTTPException(404, "No encontrado")
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
    q = market_data.get_quote(symbol)
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
    trends = external_data.finnhub_recommendation_trends(sym)
    consensus = external_data.aggregate_recommendation(trends)
    target = external_data.finnhub_price_target(sym)
    result = {"symbol": sym, "consensus": consensus, "price_target": target}
    _cache.set(f"analyst:{sym}", result, ttl=900)  # 15 min
    return result


@api_router.get("/sentiment/{symbol}")
async def sentiment_news(symbol: str):
    sym = symbol.upper()
    items = external_data.alpha_sentiment_news(sym) or []
    # avg sentiment
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
    return {
        "symbol": sym,
        "average_score": avg,
        "label": label,
        "items": items,
    }


# ---------- Earnings Calendar ----------
@api_router.get("/calendar/earnings")
async def earnings_calendar(days: int = 14, symbols: Optional[str] = None):
    """Upcoming earnings from Finnhub. If symbols=comma list, filter by those tickers only."""
    sym_filter = None
    if symbols:
        sym_filter = {s.strip().upper() for s in symbols.split(",") if s.strip()}
    data = external_data.finnhub_earnings_calendar(days=days, symbols=sym_filter)
    return data or {"items": []}


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
async def test_telegram():
    import telegram_notifier
    sent, err = await telegram_notifier.send_test()
    if not sent:
        raise HTTPException(500, err or "No se pudo enviar mensaje de Telegram")
    return {"ok": True}


# ---------- Daily Opportunities ----------
@api_router.get("/opportunities/daily")
async def daily_opportunities(refresh: bool = False):
    data = await opportunities.scan_daily_opportunities(force_refresh=refresh)
    return data


# ---------- Signal Table (puntos de compra/venta) ----------
@api_router.get("/signals")
async def list_signals():
    # El worker actualiza last_price en MongoDB cada 60s, así que no
    # necesitamos llamar a Yahoo aquí. Respuesta instantánea desde DB.
    cached = _cache.get("signals_list")
    if cached is not None:
        return cached
    entries = await signal_table.list_entries(db)
    _cache.set("signals_list", entries, ttl=20)
    return entries


@api_router.post("/signals")
async def create_signal(item: SignalEntryCreate):
    entry = await signal_table.create_entry(db, item.model_dump())
    _cache._store.pop("signals_list", None)
    _cache._store.pop("signals_hot", None)
    return entry


@api_router.patch("/signals/{entry_id}")
async def update_signal(entry_id: str, item: SignalEntryUpdate):
    data = {k: v for k, v in item.model_dump().items() if v is not None}
    updated = await signal_table.update_entry(db, entry_id, data)
    if not updated:
        raise HTTPException(404, "Señal no encontrada")
    _cache._store.pop("signals_list", None)
    _cache._store.pop("signals_hot", None)
    return updated


@api_router.delete("/signals/{entry_id}")
async def delete_signal(entry_id: str):
    ok = await signal_table.delete_entry(db, entry_id)
    if not ok:
        raise HTTPException(404, "Señal no encontrada")
    _cache._store.pop("signals_list", None)
    _cache._store.pop("signals_hot", None)
    return {"deleted": entry_id}


@api_router.post("/signals/bulk")
async def bulk_import_signals(payload: SignalBulkImport):
    result = await signal_table.bulk_upsert(db, payload.rows)
    _cache._store.pop("signals_list", None)
    _cache._store.pop("signals_hot", None)
    return result


# ---------- Alert History ----------
@api_router.get("/alerts/history")
async def get_alert_history(limit: int = 50):
    """Historial de alertas disparadas (últimas 50)."""
    items = await db.alert_history.find({}, {"_id": 0}).sort("fired_at", -1).limit(limit).to_list(limit)
    return items


@api_router.delete("/alerts/history")
async def clear_alert_history():
    """Borra todo el historial."""
    await db.alert_history.delete_many({})
    return {"ok": True}


# ---------- Hot Signals (señales calientes para el Dashboard) ----------
@api_router.get("/signals/hot")
async def hot_signals(limit: int = 5):
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
    _cache.set("signals_hot", top, ttl=30)
    return top


# ---------- Mount ----------
app.include_router(api_router)

# Ruta raíz para el health check de Render (evita 404 en /)
@app.get("/")
async def app_root():
    return {"app": "InverIA", "status": "ok"}

_cors_origins = os.environ.get("CORS_ORIGINS", "*")
_origins_list = [o.strip().rstrip("/") for o in _cors_origins.split(",") if o.strip()]

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


@app.on_event("startup")
async def start_alerts_worker():
    asyncio.create_task(alerts_worker.alerts_worker_loop(db))


@app.on_event("startup")
async def start_signal_worker():
    asyncio.create_task(signal_table.signal_worker_loop(db))


@app.on_event("startup")
async def prewarm_opportunities():
    """Pre-cache the daily opportunities scan in background so the first user
    request hits a warm cache (avoids cold-start timeouts on Render/proxy)."""
    async def _run():
        try:
            await asyncio.sleep(3)  # give the app a moment to finish booting
            await opportunities.scan_daily_opportunities(force_refresh=True)
            logger.info("Opportunities pre-warm complete")
        except Exception as e:
            logger.warning(f"Opportunities pre-warm failed: {e}")
    asyncio.create_task(_run())


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
