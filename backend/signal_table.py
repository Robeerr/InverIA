"""
signal_table.py  –  Tabla de señales (puntos de compra/venta) para InverIA
---------------------------------------------------------------------------
Colección MongoDB: signal_entries
Cada entrada representa una acción con niveles de compra y venta definidos
manualmente por el usuario (importados desde Excel o editados en la app).

El worker comprueba precios cada 60s y dispara alertas por Telegram+email
cuando el precio toca cualquiera de los niveles activos.
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


def _make_entry(
    symbol: str,
    name: str = "",
    buy1: Optional[float] = None,
    buy2: Optional[float] = None,
    buy3: Optional[float] = None,
    sell1: Optional[float] = None,
    sell2: Optional[float] = None,
    sell3: Optional[float] = None,
    notes: str = "",
    active: bool = True,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "symbol": symbol.upper().strip(),
        "name": (name or "").strip(),
        "buy1": buy1,
        "buy2": buy2,
        "buy3": buy3,
        "sell1": sell1,
        "sell2": sell2,
        "sell3": sell3,
        "notes": (notes or "").strip(),
        "active": active,
        "created_at": _now(),
        "updated_at": _now(),
        "last_price": None,
    }


# ── CRUD ────────────────────────────────────────────────────────────────────

async def list_entries(db) -> list:
    return await db.signal_entries.find({}, {"_id": 0}).to_list(500)


async def get_entry(db, entry_id: str) -> Optional[dict]:
    return await db.signal_entries.find_one({"id": entry_id}, {"_id": 0})


async def create_entry(db, data: dict) -> dict:
    allowed = ("symbol", "name", "buy1", "buy2", "buy3",
               "sell1", "sell2", "sell3", "notes", "active")
    clean = {k: v for k, v in data.items() if k in allowed}
    entry = _make_entry(**clean)
    await db.signal_entries.insert_one(entry)
    entry.pop("_id", None)
    return entry


async def update_entry(db, entry_id: str, data: dict) -> Optional[dict]:
    allowed = ("name", "buy1", "buy2", "buy3",
               "sell1", "sell2", "sell3", "notes", "active")
    update_data = {k: v for k, v in data.items() if k in allowed}
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
            fields = {}
            for k in ("name", "buy1", "buy2", "buy3",
                       "sell1", "sell2", "sell3", "notes", "active"):
                if k in row and row[k] is not None:
                    fields[k] = row[k]
            fields["updated_at"] = _now()
            await db.signal_entries.update_one({"symbol": symbol}, {"$set": fields})
            updated += 1
        else:
            allowed = ("symbol", "name", "buy1", "buy2", "buy3",
                       "sell1", "sell2", "sell3", "notes", "active")
            clean = {k: row[k] for k in allowed if k in row and row[k] is not None}
            entry = _make_entry(**clean)
            await db.signal_entries.insert_one(entry)
            created += 1
    return {"created": created, "updated": updated}


# ── Price-monitoring worker ─────────────────────────────────────────────────

COOLDOWN_SECONDS = 3600  # no repetir la misma alerta en menos de 1h


async def signal_worker_loop(db, interval: int = 60):
    """Background: cada `interval` seg comprueba precios vs niveles activos."""
    logger.info("Signal table worker started (interval=%ds)", interval)

    cooldowns: dict = {}  # "AAPL_buy1" -> timestamp float

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
                        quote.get("price")
                        or quote.get("regularMarketPrice")
                        or 0
                    )
                    if price <= 0:
                        continue

                    # Update last_price
                    await db.signal_entries.update_one(
                        {"id": entry["id"]},
                        {"$set": {"last_price": price, "updated_at": _now()}}
                    )

                    levels = {
                        "buy1":  (entry.get("buy1"),  "COMPRA", "below"),
                        "buy2":  (entry.get("buy2"),  "COMPRA", "below"),
                        "buy3":  (entry.get("buy3"),  "COMPRA", "below"),
                        "sell1": (entry.get("sell1"), "VENTA",  "above"),
                        "sell2": (entry.get("sell2"), "VENTA",  "above"),
                        "sell3": (entry.get("sell3"), "VENTA",  "above"),
                    }

                    for level_key, (target, action, direction) in levels.items():
                        if target is None:
                            continue

                        tolerance = target * 0.005  # ±0.5%
                        if abs(price - target) > tolerance:
                            continue

                        cd_key = f"{symbol}_{level_key}"
                        now_ts = datetime.now(timezone.utc).timestamp()
                        if now_ts - cooldowns.get(cd_key, 0) < COOLDOWN_SECONDS:
                            continue

                        cooldowns[cd_key] = now_ts
                        diff_pct = round(((price - target) / target) * 100, 2)

                        logger.info(
                            "SIGNAL HIT: %s %s @ %.2f (target %.2f)",
                            symbol, level_key, price, target,
                        )

                        # Telegram (using existing MarkdownV2 notifier)
                        emoji = "🟢" if action == "COMPRA" else "🔴"
                        tg_msg = (
                            f"{emoji} *Señal InverIA · {telegram_notifier._esc_md(symbol)}*\n\n"
                            f"Nivel {telegram_notifier._esc_md(level_key)}: "
                            f"*${telegram_notifier._esc_md(f'{target:.2f}')}*\n"
                            f"Precio actual: *${telegram_notifier._esc_md(f'{price:.2f}')}* "
                            f"\\({telegram_notifier._esc_md(f'{diff_pct:+.2f}')}%\\)\n"
                            f"{telegram_notifier._esc_md(entry.get('name', ''))}"
                        )
                        asyncio.create_task(
                            telegram_notifier.send_message(tg_msg)
                        )

                        # Email backup
                        asyncio.create_task(
                            alerts_worker.send_alert_email(
                                symbol, target, direction, price, diff_pct,
                            )
                        )

                except Exception as e:
                    logger.warning("Signal check error for %s: %s", symbol, e)

        except Exception as e:
            logger.error("Signal worker loop error: %s", e)

        await asyncio.sleep(interval)
