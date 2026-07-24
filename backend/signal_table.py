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
from time import perf_counter
from zoneinfo import ZoneInfo
from typing import Optional

# Margen de alerta anticipada: disparar cuando el precio está dentro de este %
# por encima del nivel de compra (o por debajo del de venta). Da tiempo de reacción.
_ALERT_MARGIN_PCT = 0.5
# Anti-pánico: caída diaria (%) a partir de la cual recordamos la tesis ANTES de que el
# usuario venda por impulso. Una vez al día por símbolo (cooldown).
_PANIC_DROP_PCT = -7.0

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
    "compra", "acciones",  # posición real (precio medio de compra y nº de acciones) para el P&L
)

ALLOWED_UPDATE = (
    "name", "mercado", "grupo",
    "deseado", "nivel1", "nivel2", "nivel3", "nivel4", "nivel5",
    "alert_deseado", "alert_nivel1", "alert_nivel2", "alert_nivel3", "alert_nivel4", "alert_nivel5",
    "riesgo", "sector", "posibles_ganancias", "notes", "active",
    "divisa", "bz", "objetivo_5a",
    "compra", "acciones",
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
    compra: Optional[float] = None,
    acciones: Optional[float] = None,
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
        "compra": compra,
        "acciones": acciones,
        "created_at": _now(),
        "updated_at": _now(),
        "last_price": None,
    }


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def list_entries(db) -> list:
    return await db.signal_entries.find({}, {"_id": 0}).to_list(500)


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
            # NUNCA sobrescribir el estado que el usuario gestiona A MANO al reimportar:
            # las campanas (una campana apagada = ese nivel YA lo compró) ni el flag
            # activo/inactivo de la fila. El Excel solo aporta precios/niveles, no ese estado.
            for protected in ("alert_deseado", "alert_nivel1", "alert_nivel2",
                              "alert_nivel3", "alert_nivel4", "alert_nivel5", "active"):
                fields.pop(protected, None)
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


async def _volume_ratio(symbol: str):
    """Volumen de HOY / media de las últimas ~20 sesiones, desde el histórico diario
    (cacheado). >1.5 ≈ volumen alto → un rebote en soporte es más fiable. None si no hay
    datos. Se calcula SOLO al disparar una alerta (raro), así que el coste es mínimo.
    Antes esto se sacaba de get_quote_fast, que no trae volumen → salía siempre None."""
    try:
        df = await asyncio.to_thread(market_data.get_stock_data, symbol, "3M")
        if df is None or df.empty or "Volume" not in df.columns:
            return None
        vols = df["Volume"].dropna().astype(float)
        if len(vols) < 6:
            return None
        hoy = float(vols.iloc[-1])
        prev = vols.iloc[-21:-1] if len(vols) >= 21 else vols.iloc[:-1]
        media = float(prev.mean())
        if media <= 0:
            return None
        return round(hoy / media, 2)
    except Exception:
        return None


async def signal_worker_loop(db, interval: int = 10):
    """Background: comprueba precios vs niveles activos lo más rápido posible.

    El espaciado entre símbolos lo impone el rate-limiter de Finnhub (bg_cap=40/min
    ≈ 1.5s/llamada) sin sleep artificial. Al acabar el ciclo dormimos sólo el tiempo
    sobrante hasta `interval`, mínimo 3s. Con TTL de caché=8s y sin sleep manual la
    latencia real de alerta baja de ~90s a ~20-40s (según número de símbolos).
    """
    logger.info("Signal table worker started (interval=%ds)", interval)

    # Índice para búsquedas rápidas de cooldown
    await db.alert_cooldowns.create_index("key", unique=True)

    while True:
        cycle_start = perf_counter()
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

            # Fase 1: precios EN SERIE. El rate-limiter de Finnhub (bg_cap≈40/min)
            # cadencia las llamadas a ~1.5s c/u sin necesidad de sleep explícito.
            # TTL de caché=8s garantiza precios frescos en cada ciclo.
            market_data.enter_finnhub_background()
            symbols = list({e["symbol"] for e in entries})
            price_map: dict = {}
            for sym in symbols:
                try:
                    quote = await asyncio.to_thread(market_data.get_quote_fast, sym)
                    if not quote:
                        quote = await asyncio.to_thread(market_data.get_quote, sym)
                    ext = None
                    if quote and not market_open:
                        ext = await asyncio.to_thread(market_data.get_extended_quote, sym)
                    price_map[sym] = (quote, ext)
                except Exception:
                    pass
                # Ceder el event loop brevemente para no bloquear otras corrutinas
                await asyncio.sleep(0)

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

                    daily_chg = quote.get("change_percent")
                    prev_close = quote.get("previous_close")
                    upd = {
                        "last_price": price,
                        "market_state": "REGULAR" if market_open else None,
                        "pre_market_price": None,
                        "post_market_price": None,
                        "previous_close": round(float(prev_close), 2) if prev_close else None,
                        "daily_change_percent": round(float(daily_chg), 2) if daily_chg is not None else None,
                        "extended_change_percent": None,
                        "updated_at": _now(),
                    }
                    # Fuera del horario regular, calcular el pre/post.
                    if not market_open and ext:
                        state = ext.get("market_state")
                        ext_price = ext.get("extended_price")
                        upd["market_state"] = state
                        if state == "PRE":
                            upd["pre_market_price"] = ext_price
                        elif state == "POST":
                            upd["post_market_price"] = ext_price
                        # Base del % extendido = último cierre regular. El precio de
                        # Finnhub (`price`) se congela en ese cierre fuera de horario y
                        # es fiable; yfinance `regular_close` en el cloud llega desfasado
                        # un día (de ahí el valor "pegado" tipo 599.80). Por eso NO
                        # sobrescribimos last_price con regular_close: lo dejamos en el
                        # valor de Finnhub y calculamos el % contra él en el servidor.
                        base = price
                        if ext_price and base:
                            upd["extended_change_percent"] = round(
                                (ext_price - base) / base * 100, 2
                            )
                    await db.signal_entries.update_one({"id": entry["id"]}, {"$set": upd})

                    # Las alertas de nivel solo se disparan en horario regular
                    if not market_open:
                        continue

                    # ── ANTI-PÁNICO (DESACTIVADO) ────────────────────────────
                    # El recordatorio "RESPIRA — antes de vender" generaba demasiado ruido en
                    # Telegram, así que se desactiva a petición del usuario. Se deja el código
                    # de _fire_panic_alert por si se quiere reactivar en el futuro.
                    # if daily_chg is not None and float(daily_chg) <= _PANIC_DROP_PCT:
                    #     cd_key = f"{symbol}_panic_{today}"
                    #     if not await _is_in_cooldown(db, cd_key):
                    #         await _set_cooldown(db, cd_key)
                    #         await _fire_panic_alert(entry, symbol, price, float(daily_chg), db=db)

                    # Niveles de compra — disparo con margen anticipado (_ALERT_MARGIN_PCT)
                    # para que la alerta llegue ligeramente ANTES de tocar el nivel exacto.
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
                        # Disparar cuando el precio ENTRA en la zona [−∞, target*(1+margin)].
                        # Requiere baseline anterior (prev_price>threshold) para detectar cruce.
                        threshold = round(target * (1 + _ALERT_MARGIN_PCT / 100), 4)
                        if price > threshold:
                            continue  # todavía por encima de la zona
                        if prev_price is None or prev_price <= threshold:
                            continue  # sin baseline aún, o ya estaba en zona (no es cruce nuevo)
                        cd_key = f"{symbol}_{level_key}_{today}"
                        if await _is_in_cooldown(db, cd_key):
                            continue
                        await _set_cooldown(db, cd_key)
                        diff_pct = round(((price - target) / target) * 100, 2)
                        level_num = level_key.replace("nivel", "Nivel ")
                        approaching = price > target  # precio en zona pero aún sobre el nivel exacto
                        # Confirmación por VOLUMEN: un rebote en soporte con volumen alto es
                        # mucho más fiable. Ratio volumen-hoy / media, desde el histórico diario
                        # (el quote rápido no trae volumen, por eso antes salía siempre None).
                        vol_ratio = await _volume_ratio(symbol)
                        await _fire_alert(
                            entry, symbol, level_num, target, price, diff_pct, "COMPRA",
                            db=db, approaching=approaching, vol_ratio=vol_ratio,
                        )

                    for level_key, target in sell_levels.items():
                        if target is None:
                            continue
                        if not entry.get(f"alert_{level_key}", True):
                            continue
                        # Disparar cuando el precio SUPERA target*(1-margin) al alza.
                        threshold = round(target * (1 - _ALERT_MARGIN_PCT / 100), 4)
                        if price < threshold:
                            continue  # todavía por debajo de la zona
                        if prev_price is None or prev_price >= threshold:
                            continue  # sin baseline o ya estaba en zona
                        cd_key = f"{symbol}_{level_key}_{today}"
                        if await _is_in_cooldown(db, cd_key):
                            continue
                        await _set_cooldown(db, cd_key)
                        diff_pct = round(((price - target) / target) * 100, 2)
                        approaching = price < target
                        await _fire_alert(
                            entry, symbol, "Deseado/Venta", target, price, diff_pct, "VENTA",
                            db=db, approaching=approaching,
                        )

                except Exception as e:
                    logger.warning("Signal check error for %s: %s", symbol, e)

        except Exception as e:
            logger.error("Signal worker loop error: %s", e)

        # Dormir solo el tiempo que falte hasta `interval` (mínimo 3s).
        elapsed = perf_counter() - cycle_start
        await asyncio.sleep(max(3.0, interval - elapsed))


async def _fire_panic_alert(entry, symbol, price, daily_chg, db=None):
    """Recordatorio de DISCIPLINA cuando una acción de la cartera cae fuerte: devuelve al
    usuario a su tesis fría ANTES de que venda por pánico. No le dice qué hacer — le hace
    parar y comprobar si la tesis ha cambiado de verdad o es solo ruido."""
    name = entry.get("name") or symbol
    notes = (entry.get("notes") or "").strip()
    sector = entry.get("sector", "")
    e = telegram_notifier._esc_md

    logger.info("PANIC REMINDER: %s cae %.1f%% @ %.2f", symbol, daily_chg, price)

    tg = (
        "🧭 *RESPIRA — antes de vender*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *{e(name)} \\({e(symbol)}\\)* cae *{e(f'{daily_chg:.1f}')}%* hoy\n"
        f"💰 Precio: \\${e(f'{price:.2f}')}\n\n"
    )
    if notes:
        tg += f"📝 *Por qué la tienes:* {e(notes)}\n\n"
    tg += (
        "Antes de vender por impulso, pregúntate:\n"
        "• ¿Ha cambiado la TESIS, o es solo ruido de mercado\\?\n"
        "• ¿Cae por la EMPRESA o por TODO el mercado\\?\n"
        "• Vender en una caída sin motivo real es el error más caro\\.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🧭 _InverIA · Recordatorio de disciplina_"
    )
    await telegram_notifier.send_message(tg, grupo=entry.get("grupo", "ideas_javi"))

    if db is not None:
        try:
            await db.alert_history.insert_one({
                "id": str(uuid.uuid4()),
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "type": "PANICO",
                "price": round(price, 2),
                "daily_change_percent": round(daily_chg, 2),
                "fired_at": _now(),
            })
        except Exception:
            pass


async def _fire_alert(entry, symbol, level_label, target, price, diff_pct, action, db=None, approaching=False, vol_ratio=None):
    """Dispara alerta por Telegram y guarda en historial."""
    name = entry.get("name", "") or symbol
    sector = entry.get("sector", "")
    riesgo = entry.get("riesgo", "")
    mercado = entry.get("mercado", "")
    posibles = entry.get("posibles_ganancias")

    logger.info("SIGNAL HIT: %s %s @ %.2f (target %.2f, %s approaching=%s)",
                symbol, level_label, price, target, action, approaching)

    e = telegram_notifier._esc_md

    if action == "COMPRA":
        if approaching:
            header = "⚡⚡⚡ *ZONA DE COMPRA PRÓXIMA* ⚡⚡⚡"
        else:
            header = "🟢🟢🟢 *ALERTA DE COMPRA* 🟢🟢🟢"
        price_emoji = "💰"
        target_emoji = "🎯"
        extra = f"📈 Posible ganancia: *\\+{e(f'{posibles:.2f}')}%*\n" if posibles else ""
    else:
        if approaching:
            header = "⚡⚡⚡ *OBJETIVO DE VENTA PRÓXIMO* ⚡⚡⚡"
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
    # Confirmación por volumen (solo en compras): rebote fiable si el volumen es alto.
    if action == "COMPRA" and vol_ratio is not None:
        if vol_ratio >= 1.5:
            tg_msg += f"🔊 Volumen *{e(f'{vol_ratio:.1f}')}× la media* — rebote fiable\n"
        elif vol_ratio < 0.7:
            tg_msg += f"🔈 Volumen *{e(f'{vol_ratio:.1f}')}× la media* — flojo, rebote menos fiable\n"
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
