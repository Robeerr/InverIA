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
from datetime import datetime, timezone
from typing import Optional

import market_data
import alerts_worker
import telegram_notifier

logger = logging.getLogger("signal_table")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


ALLOWED_CREATE = (
    "symbol", "name", "mercado",
    "deseado", "nivel1", "nivel2", "nivel3", "nivel4", "nivel5",
    "alert_deseado", "alert_nivel1", "alert_nivel2", "alert_nivel3", "alert_nivel4", "alert_nivel5",
    "riesgo", "sector", "posibles_ganancias", "notes", "active",
)

ALLOWED_UPDATE = (
    "name", "mercado",
    "deseado", "nivel1", "nivel2", "nivel3", "nivel4", "nivel5",
    "alert_deseado", "alert_nivel1", "alert_nivel2", "alert_nivel3", "alert_nivel4", "alert_nivel5",
    "riesgo", "sector", "posibles_ganancias", "notes", "active",
)


def _make_entry(
    symbol: str,
    name: str = "",
    mercado: str = "",
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
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "symbol": symbol.upper().strip(),
        "name": (name or "").strip(),
        "mercado": (mercado or "").strip().upper(),
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

COOLDOWN_SECONDS = 3600  # no repetir la misma alerta en menos de 1h


async def signal_worker_loop(db, interval: int = 60):
    """Background: cada `interval` seg comprueba precios vs niveles activos."""
    logger.info("Signal table worker started (interval=%ds)", interval)
    cooldowns: dict = {}  # "AAPL_nivel1" -> timestamp float

    while True:
        try:
            entries = await db.signal_entries.find(
                {"active": True}, {"_id": 0}
            ).to_list(500)

            for entry in entries:
                symbol = entry["symbol"]
                try:
                    quote = market_data.get_quote(symbol)
                    if not quote:
                        continue
                    price = float(
                        quote.get("price") or quote.get("regularMarketPrice") or 0
                    )
                    if price <= 0:
                        continue

                    await db.signal_entries.update_one(
                        {"id": entry["id"]},
                        {"$set": {"last_price": price, "updated_at": _now()}}
                    )

                    # Niveles de compra (precio baja hasta el nivel → alerta COMPRA)
                    buy_levels = {
                        "nivel1": entry.get("nivel1"),
                        "nivel2": entry.get("nivel2"),
                        "nivel3": entry.get("nivel3"),
                        "nivel4": entry.get("nivel4"),
                        "nivel5": entry.get("nivel5"),
                    }
                    # Nivel deseado/venta (precio sube hasta el objetivo → alerta VENTA)
                    sell_levels = {
                        "deseado": entry.get("deseado"),
                    }

                    for level_key, target in buy_levels.items():
                        if target is None:
                            continue
                        if not entry.get(f"alert_{level_key}", True):
                            continue
                        # Alerta cuando el precio baja hasta el nivel (±1.5% o ya lo ha cruzado por abajo hasta un 3%)
                        # Rango: desde 1.5% por encima hasta 3% por debajo del objetivo
                        if not (target * 0.97 <= price <= target * 1.015):
                            continue
                        cd_key = f"{symbol}_{level_key}"
                        now_ts = datetime.now(timezone.utc).timestamp()
                        if now_ts - cooldowns.get(cd_key, 0) < COOLDOWN_SECONDS:
                            continue
                        cooldowns[cd_key] = now_ts
                        diff_pct = round(((price - target) / target) * 100, 2)
                        level_num = level_key.replace("nivel", "Nivel ")
                        _fire_alert(entry, symbol, level_num, target, price, diff_pct, "COMPRA")

                    for level_key, target in sell_levels.items():
                        if target is None:
                            continue
                        if not entry.get(f"alert_{level_key}", True):
                            continue
                        # Alerta cuando el precio sube hasta el objetivo (±1.5% o ya lo ha cruzado por arriba hasta un 3%)
                        if not (target * 0.985 <= price <= target * 1.03):
                            continue
                        cd_key = f"{symbol}_{level_key}"
                        now_ts = datetime.now(timezone.utc).timestamp()
                        if now_ts - cooldowns.get(cd_key, 0) < COOLDOWN_SECONDS:
                            continue
                        cooldowns[cd_key] = now_ts
                        diff_pct = round(((price - target) / target) * 100, 2)
                        _fire_alert(entry, symbol, "Deseado/Venta", target, price, diff_pct, "VENTA")

                except Exception as e:
                    logger.warning("Signal check error for %s: %s", symbol, e)

        except Exception as e:
            logger.error("Signal worker loop error: %s", e)

        await asyncio.sleep(interval)


def _fire_alert(entry, symbol, level_label, target, price, diff_pct, action):
    """Dispara alerta por Telegram y email."""
    emoji = "🟢" if action == "COMPRA" else "🎯"
    name = entry.get("name", "")
    sector = entry.get("sector", "")
    riesgo = entry.get("riesgo", "")

    logger.info("SIGNAL HIT: %s %s @ %.2f (target %.2f, %s)", symbol, level_label, price, target, action)

    tg_msg = (
        f"{emoji} *Señal InverIA · {telegram_notifier._esc_md(symbol)}*\n\n"
        f"*{telegram_notifier._esc_md(level_label)}* alcanzado: "
        f"*${telegram_notifier._esc_md(f'{target:.2f}')}*\n"
        f"Precio actual: *${telegram_notifier._esc_md(f'{price:.2f}')}* "
        f"\\({telegram_notifier._esc_md(f'{diff_pct:+.2f}')}%\\)\n"
        f"Acción: *{telegram_notifier._esc_md(action)}*\n"
    )
    if name:
        tg_msg += f"{telegram_notifier._esc_md(name)}"
    if sector:
        tg_msg += f" · {telegram_notifier._esc_md(sector)}"
    if riesgo:
        tg_msg += f" · Riesgo: {telegram_notifier._esc_md(riesgo)}"

    asyncio.create_task(telegram_notifier.send_message(tg_msg))
    asyncio.create_task(
        alerts_worker.send_alert_email(
            symbol, target, "below" if action == "COMPRA" else "above", price, diff_pct,
        )
    )
