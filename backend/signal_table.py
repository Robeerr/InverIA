"""
signal_table.py  –  Tabla de señales (cartera) para InverIA
------------------------------------------------------------
Colección MongoDB: signal_entries
Cada entrada tiene niveles de compra (nivel1-5), nivel deseado/venta,
y toggles individuales por nivel para activar/desactivar alertas.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo
from typing import Optional

import market_data
import telegram_notifier

logger = logging.getLogger("signal_table")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


ALLOWED_CREATE = (
    "symbol", "name", "mercado", "grupo",
    "deseado", "nivel1", "nivel2", "nivel3", "nivel4", "nivel5",
    "alert_deseado", "alert_nivel1", "alert_nivel2", "alert_nivel3", "alert_nivel4", "alert_nivel5",
    "riesgo", "sector", "posibles_ganancias", "notes", "active",
    "divisa", "bz", "objetivo_5a",
)

ALLOWED_UPDATE = (
    "name", "mercado", "grupo",
    "deseado", "nivel1", "nivel2", "nivel3", "nivel4", "nivel5",
    "alert_deseado", "alert_nivel1", "alert_nivel2", "alert_nivel3", "alert_nivel4", "alert_nivel5",
    "riesgo", "sector", "posibles_ganancias", "notes", "active",
    "divisa", "bz", "objetivo_5a",
)


def _make_entry(
    symbol: str,
    name: str = "",
    mercado: str = "",
    grupo: str = "ideas_javi",
    deseado: Optional[float] = None,
    nivel1: Optional[float] = None,
    nivel2: Optional[float] = None,
    nivel3: Optional[float] = None,
    nivel4: Optional[float] = None,
    nivel5: Optional[float] = None,
    alert_deseado: bool = True,
    alert_nivel1: bool = True,
    alert_nivel2: bool = True,
    alert_nivel3: bool = True,
    alert_nivel4: bool = True,
    alert_nivel5: bool = True,
    riesgo: str = "",
    sector: str = "",
    posibles_ganancias: Optional[float] = None,
    notes: str = "",
    active: bool = True,
    divisa: str = "",
    bz: Optional[float] = None,
    objetivo_5a: Optional[float] = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "symbol": symbol.upper().strip(),
        "name": (name or "").strip(),
        "mercado": (mercado or "").strip().upper(),
        "grupo": (grupo or "ideas_javi").strip(),
        "deseado": deseado,
        "nivel1": nivel1,
        "nivel2": nivel2,
        "nivel3": nivel3,
        "nivel4": nivel4,
        "nivel5": nivel5,
        "alert_deseado": alert_deseado,
        "alert_nivel1": alert_nivel1,
        "alert_nivel2": alert_nivel2,
        "alert_nivel3": alert_nivel3,
        "alert_nivel4": alert_nivel4,
        "alert_nivel5": alert_nivel5,
        "riesgo": (riesgo or "").strip().upper(),
        "sector": (sector or "").strip(),
        "posibles_ganancias": posibles_ganancias,
        "notes": (notes or "").strip(),
        "active": active,
        "divisa": (divisa or "").strip().upper(),
        "bz": bz,
        "objetivo_5a": objetivo_5a,
        "created_at": _now(),
        "updated_at": _now(),
        "last_price": None,
    }


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def list_entries(db) -> list:
    return await db.signal_entries.find({}, {"_id": 0}).to_list(500)


async def get_entry(db, entry_id: str) -> Optional[dict]:
    return await db.signal_entries.find_one({"id": entry_id}, {"_id": 0})


async def create_entry(db, data: dict) -> dict:
    clean = {k: v for k, v in data.items() if k in ALLOWED_CREATE and v is not None}
    # bools default to True even if not sent
    for toggle in ("alert_deseado", "alert_nivel1", "alert_nivel2", "alert_nivel3", "alert_nivel4", "alert_nivel5"):
        clean.setdefault(toggle, True)
    clean.setdefault("active", True)
    entry = _make_entry(**clean)
    await db.signal_entries.insert_one(entry)
    entry.pop("_id", None)
    return entry


async def update_entry(db, entry_id: str, data: dict) -> Optional[dict]:
    update_data = {k: v for k, v in data.items() if k in ALLOWED_UPDATE}
    update_data["updated_at"] = _now()
    result = await db.signal_entries.update_one(
        {"id": entry_id}, {"$set": update_data}
    )
    if result.matched_count == 0:
        return None
    return await db.signal_entries.find_one({"id": entry_id}, {"_id": 0})


async def delete_entry(db, entry_id: str) -> bool:
    result = await db.signal_entries.delete_one({"id": entry_id})
    return result.deleted_count > 0


async def bulk_upsert(db, rows: list) -> dict:
    """Import masivo desde Excel. Upsert por símbolo."""
    created = 0
    updated = 0
    for row in rows:
        symbol = (row.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        existing = await db.signal_entries.find_one({"symbol": symbol})
        if existing:
            fields = {k: row[k] for k in ALLOWED_UPDATE if k in row and row[k] is not None}
            fields["updated_at"] = _now()
            await db.signal_entries.update_one({"symbol": symbol}, {"$set": fields})
            updated += 1
        else:
            clean = {k: row[k] for k in ALLOWED_CREATE if k in row and row[k] is not None}
            entry = _make_entry(**clean)
            await db.signal_entries.insert_one(entry)
            created += 1
    return {"created": created, "updated": updated}


# ── Price-monitoring worker ──────────────────────────────────────────────────

EASTERN = ZoneInfo("America/New_York")


def is_market_open() -> bool:
    """True solo en horario regular de mercado US: L-V 9:30-16:00 ET."""
    now = datetime.now(EASTERN)
    if now.weekday() >= 5:  # sábado=5, domingo=6
        return False
    return time(9, 30) <= now.time() <= time(16, 0)


def _extended_session_active() -> bool:
    """True durante pre-market, regular y after-hours (L-V 4:00-20:00 ET).
    Usado para refrescar precios (incl. pre/post) sin disparar alertas fuera de hora."""
    now = datetime.now(EASTERN)
    if now.weekday() >= 5:
        return False
    return time(4, 0) <= now.time() <= time(20, 0)


def _market_day() -> str:
    """Fecha de la sesión de hoy en horario del Este (para 'una vez al día')."""
    return datetime.now(EASTERN).date().isoformat()


async def _is_in_cooldown(db, cd_key: str) -> bool:
    """True si ese nivel ya disparó hoy. La cd_key incluye la fecha de mercado,
    así que cada día de trading es una clave nueva → máximo 1 alerta por nivel y día."""
    doc = await db.alert_cooldowns.find_one({"key": cd_key})
    return doc is not None


async def _set_cooldown(db, cd_key: str):
    """Marca el nivel como disparado hoy (persiste en MongoDB)."""
    await db.alert_cooldowns.update_one(
        {"key": cd_key},
        {"$set": {"key": cd_key, "fired_at": datetime.now(timezone.utc).timestamp()}},
        upsert=True,
    )


async def signal_worker_loop(db, interval: int = 30):
    """Background: cada `interval` seg comprueba precios vs niveles activos."""
    logger.info("Signal table worker started (interval=%ds)", interval)

    # Índice para búsquedas rápidas de cooldown
    await db.alert_cooldowns.create_index("key", unique=True)

    while True:
        try:
            # Refrescar precios durante toda la sesión extendida (pre/regular/post);
            # las alertas, en cambio, solo se disparan en horario regular.
            if not _extended_session_active():
                await asyncio.sleep(interval)
                continue
            market_open = is_market_open()
            today = _market_day()
            entries = await db.signal_entries.find(
                {"active": True}, {"_id": 0}
            ).to_list(500)
            if not entries:
                await asyncio.sleep(interval)
                continue

            # Fase 1: traer precios en PARALELO (Finnhub-only, sin el .info lento), un
            # fetch por símbolo único. Antes era un loop secuencial que con muchos
            # símbolos no terminaba dentro del intervalo y saturaba la única CPU.
            symbols = list({e["symbol"] for e in entries})
            sem = asyncio.Semaphore(6)

            async def _fetch_price(sym):
                async with sem:
                    quote = await asyncio.to_thread(market_data.get_quote_fast, sym)
                    if not quote:
                        quote = await asyncio.to_thread(market_data.get_quote, sym)
                    ext = None
                    # Pre/post solo fuera del horario regular (velas 1m, caro)
                    if quote and not market_open:
                        ext = await asyncio.to_thread(market_data.get_extended_quote, sym)
                    return sym, quote, ext

            fetched = await asyncio.gather(
                *[_fetch_price(s) for s in symbols], return_exceptions=True
            )
            price_map: dict = {}
            for res in fetched:
                if isinstance(res, Exception) or not res:
                    continue
                sym, quote, ext = res
                price_map[sym] = (quote, ext)

            # Fase 2: detección de cruce + alertas. Secuencial pero sin red (solo DB).
            for entry in entries:
                symbol = entry["symbol"]
                # Precio de la comprobación anterior: solo alertamos en el CRUCE de nivel
                # (antes fuera del nivel, ahora dentro), no por estar ya dentro de la zona.
                prev_price = entry.get("last_price")
                try:
                    quote, ext = price_map.get(symbol, (None, None))
                    if not quote:
                        continue
                    price = float(
                        quote.get("price") or quote.get("regularMarketPrice") or 0
                    )
                    if price <= 0:
                        continue

                    upd = {
                        "last_price": price,
                        "market_state": "REGULAR" if market_open else None,
                        "pre_market_price": None,
                        "post_market_price": None,
                        "updated_at": _now(),
                    }
                    # Fuera del horario regular, usar el pre/post ya obtenido en Fase 1
                    if not market_open:
                        if ext:
                            upd["market_state"] = ext.get("market_state")
                            if ext.get("market_state") == "PRE":
                                upd["pre_market_price"] = ext.get("extended_price")
                            elif ext.get("market_state") == "POST":
                                upd["post_market_price"] = ext.get("extended_price")
                            if ext.get("regular_close"):
                                upd["last_price"] = ext["regular_close"]
                    await db.signal_entries.update_one({"id": entry["id"]}, {"$set": upd})

                    # Las alertas de nivel solo se disparan en horario regular
                    if not market_open:
                        continue

                    # Niveles de compra
                    buy_levels = {
                        "nivel1": entry.get("nivel1"),
                        "nivel2": entry.get("nivel2"),
                        "nivel3": entry.get("nivel3"),
                        "nivel4": entry.get("nivel4"),
                        "nivel5": entry.get("nivel5"),
                    }
                    # Nivel deseado/venta
                    sell_levels = {
                        "deseado": entry.get("deseado"),
                    }

                    for level_key, target in buy_levels.items():
                        if target is None:
                            continue
                        if not entry.get(f"alert_{level_key}", True):
                            continue
                        # Compra: disparar SOLO en el cruce a la baja (antes por encima del
                        # nivel, ahora en/por debajo). Si el precio ya estaba dentro de la zona
                        # —o es la primera lectura (sin baseline)— no se alerta.
                        if price > target:
                            continue
                        if prev_price is None or prev_price <= target:
                            continue
                        cd_key = f"{symbol}_{level_key}_{today}"
                        if await _is_in_cooldown(db, cd_key):
                            continue
                        await _set_cooldown(db, cd_key)
                        diff_pct = round(((price - target) / target) * 100, 2)
                        level_num = level_key.replace("nivel", "Nivel ")
                        await _fire_alert(entry, symbol, level_num, target, price, diff_pct, "COMPRA", db=db)

                    for level_key, target in sell_levels.items():
                        if target is None:
                            continue
                        if not entry.get(f"alert_{level_key}", True):
                            continue
                        # Venta: disparar SOLO en el cruce al alza (antes por debajo del
                        # objetivo, ahora en/por encima). Si ya estaba por encima —o es la
                        # primera lectura (sin baseline)— no se alerta.
                        if price < target:
                            continue
                        if prev_price is None or prev_price >= target:
                            continue
                        cd_key = f"{symbol}_{level_key}_{today}"
                        if await _is_in_cooldown(db, cd_key):
                            continue
                        await _set_cooldown(db, cd_key)
                        diff_pct = round(((price - target) / target) * 100, 2)
                        await _fire_alert(entry, symbol, "Deseado/Venta", target, price, diff_pct, "VENTA", db=db)

                except Exception as e:
                    logger.warning("Signal check error for %s: %s", symbol, e)

        except Exception as e:
            logger.error("Signal worker loop error: %s", e)

        await asyncio.sleep(interval)


async def _fire_alert(entry, symbol, level_label, target, price, diff_pct, action, db=None):
    """Dispara alerta por Telegram y guarda en historial."""
    name = entry.get("name", "") or symbol
    sector = entry.get("sector", "")
    riesgo = entry.get("riesgo", "")
    mercado = entry.get("mercado", "")
    posibles = entry.get("posibles_ganancias")

    logger.info("SIGNAL HIT: %s %s @ %.2f (target %.2f, %s)", symbol, level_label, price, target, action)

    e = telegram_notifier._esc_md

    if action == "COMPRA":
        header = "🟢🟢🟢 *ALERTA DE COMPRA* 🟢🟢🟢"
        price_emoji = "💰"
        target_emoji = "🎯"
        extra = f"📈 Posible ganancia: *\\+{e(f'{posibles:.2f}')}%*\n" if posibles else ""
    else:
        header = "🔴🔴🔴 *ALERTA DE VENTA* 🔴🔴🔴"
        price_emoji = "💸"
        target_emoji = "🏁"
        extra = f"📈 Ganancia realizada: *\\+{e(f'{posibles:.2f}')}%*\n" if posibles else ""

    info_line = f"🏛️ {e(mercado)}" if mercado else ""
    if sector:
        info_line += f" · {e(sector)}"
    if riesgo:
        info_line += f" · Riesgo {e(riesgo)}"

    tg_msg = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *{e(name)} \\({e(symbol)}\\)*\n"
    )
    if info_line:
        tg_msg += f"{info_line}\n"
    tg_msg += (
        f"\n"
        f"{price_emoji} *Precio actual: \\${e(f'{price:.2f}')}*\n"
        f"{target_emoji} *{e(level_label)}: \\${e(f'{target:.2f}')}*\n\n"
        f"📊 Diferencia: *{e(f'{diff_pct:+.2f}')}%*\n"
    )
    if extra:
        tg_msg += extra
    tg_msg += (
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ _InverIA · Alerta automática_"
    )

    # Enviar Telegram al bot del grupo (Cartera o Cimientos)
    await telegram_notifier.send_message(tg_msg, grupo=entry.get("grupo", "ideas_javi"))

    # Guardar en historial de alertas
    if db is not None:
        history_entry = {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "name": name,
            "mercado": mercado,
            "sector": sector,
            "riesgo": riesgo,
            "action": action,
            "level_label": level_label,
            "target": target,
            "price": price,
            "diff_pct": diff_pct,
            "posibles_ganancias": posibles,
            "fired_at": _now(),
        }
        await db.alert_history.insert_one(history_entry)
