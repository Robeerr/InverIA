"""
signal_table.py  –  Tabla de señales (cartera) para InverIA
------------------------------------------------------------
Colección MongoDB: signal_entries
Cada entrada tiene niveles de compra (nivel1-5), nivel deseado/venta,
y toggles individuales por nivel para activar/desactivar alertas.
"""

import asyncio
import logging
import os
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
import tendencia

logger = logging.getLogger("signal_table")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


ALLOWED_CREATE = (
    "symbol", "name", "mercado", "grupo",
    "deseado", "nivel1", "nivel2", "nivel3", "nivel4", "nivel5",
    "venta1", "venta2", "venta3",  # objetivos de venta escalonada
    "alert_deseado", "alert_nivel1", "alert_nivel2", "alert_nivel3", "alert_nivel4", "alert_nivel5",
    "alert_venta1", "alert_venta2", "alert_venta3",
    "riesgo", "sector", "posibles_ganancias", "notes", "active",
    # Cómo agrupa DEGIRO esta acción para su límite de concentración sectorial. VA APARTE
    # de `sector` a propósito: ese lo rellena el proveedor de datos y además es la
    # taxonomía del usuario —la que separa lo que él separa—, mientras que esta solo tiene
    # que reproducir en qué saco la mete el bróker, que agrupa mucho más grueso. Machacar
    # uno con el otro cambiaría un dato bueno por otro, y se perdería el primero.
    "sector_degiro",
    # La letra A-D del modelo de MARGEN de DEGIRO. No es el campo `riesgo`, que es la
    # clasificación del inversor del usuario: esta la publica el bróker junto a cada
    # producto y determina cuánto riesgo le asigna su modelo. Sin API que la sirva y
    # revisada mensualmente, se teclea a mano.
    "categoria_degiro",
    "divisa", "bz", "objetivo_5a",
    "compra", "acciones",  # posición real (precio medio de compra y nº de acciones) para el P&L
    "fecha_compra",        # fecha de la compra: fija el tipo de cambio para la ganancia en EUR
)

ALLOWED_UPDATE = (
    "name", "mercado", "grupo",
    "deseado", "nivel1", "nivel2", "nivel3", "nivel4", "nivel5",
    "venta1", "venta2", "venta3",  # objetivos de venta escalonada
    "alert_deseado", "alert_nivel1", "alert_nivel2", "alert_nivel3", "alert_nivel4", "alert_nivel5",
    "alert_venta1", "alert_venta2", "alert_venta3",
    "riesgo", "sector", "posibles_ganancias", "notes", "active",
    # Cómo agrupa DEGIRO esta acción para su límite de concentración sectorial. VA APARTE
    # de `sector` a propósito: ese lo rellena el proveedor de datos y además es la
    # taxonomía del usuario —la que separa lo que él separa—, mientras que esta solo tiene
    # que reproducir en qué saco la mete el bróker, que agrupa mucho más grueso. Machacar
    # uno con el otro cambiaría un dato bueno por otro, y se perdería el primero.
    "sector_degiro",
    # La letra A-D del modelo de MARGEN de DEGIRO. No es el campo `riesgo`, que es la
    # clasificación del inversor del usuario: esta la publica el bróker junto a cada
    # producto y determina cuánto riesgo le asigna su modelo. Sin API que la sirva y
    # revisada mensualmente, se teclea a mano.
    "categoria_degiro",
    "divisa", "bz", "objetivo_5a",
    "compra", "acciones",
    "fecha_compra",   # para el tipo de cambio del dia de la compra (ganancia real en EUR)
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
    venta1: Optional[float] = None,
    venta2: Optional[float] = None,
    venta3: Optional[float] = None,
    alert_deseado: bool = True,
    alert_nivel1: bool = True,
    alert_nivel2: bool = True,
    alert_nivel3: bool = True,
    alert_nivel4: bool = True,
    alert_nivel5: bool = True,
    alert_venta1: bool = True,
    alert_venta2: bool = True,
    alert_venta3: bool = True,
    riesgo: str = "",
    categoria_degiro: str = "",
    sector: str = "",
    sector_degiro: str = "",
    posibles_ganancias: Optional[float] = None,
    notes: str = "",
    active: bool = True,
    divisa: str = "",
    bz: Optional[float] = None,
    objetivo_5a: Optional[float] = None,
    compra: Optional[float] = None,
    acciones: Optional[float] = None,
    fecha_compra: str = "",
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
        "venta1": venta1,
        "venta2": venta2,
        "venta3": venta3,
        "alert_deseado": alert_deseado,
        "alert_nivel1": alert_nivel1,
        "alert_nivel2": alert_nivel2,
        "alert_nivel3": alert_nivel3,
        "alert_nivel4": alert_nivel4,
        "alert_nivel5": alert_nivel5,
        "alert_venta1": alert_venta1,
        "alert_venta2": alert_venta2,
        "alert_venta3": alert_venta3,
        "riesgo": (riesgo or "").strip().upper(),
        "categoria_degiro": (categoria_degiro or "").strip().upper()[:1],
        "sector": (sector or "").strip(),
        "sector_degiro": (sector_degiro or "").strip(),
        "posibles_ganancias": posibles_ganancias,
        "notes": (notes or "").strip(),
        "active": active,
        "divisa": (divisa or "").strip().upper(),
        "bz": bz,
        "objetivo_5a": objetivo_5a,
        "compra": compra,
        "acciones": acciones,
        "fecha_compra": (fecha_compra or "").strip()[:10] or None,
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
    for toggle in ("alert_deseado", "alert_nivel1", "alert_nivel2", "alert_nivel3", "alert_nivel4", "alert_nivel5",
                   "alert_venta1", "alert_venta2", "alert_venta3"):
        clean.setdefault(toggle, True)
    clean.setdefault("active", True)
    entry = _make_entry(**clean)
    await db.signal_entries.insert_one(entry)
    entry.pop("_id", None)
    return entry


async def cotizacion_inicial(db, entry: dict) -> dict:
    """Pone precio a una fila RECIÉN creada, sin esperar al worker.

    El worker solo trabaja en sesión extendida (L-V 4:00-20:00 ET), así que un valor dado
    de alta un sábado se quedaba con "—" en toda la fila hasta el lunes. Pasó con UBER al
    añadirlo desde el Chartista, y volvía a pasar con las compras registradas en
    Operaciones, que ahora también crean su fila.

    Una sola llamada, y solo al crear. Si falla no se propaga: el alta y la compra ya han
    ocurrido, y negarlas porque el precio no se pudo leer sería perder el apunte por lo de
    menos. El worker lo rellena igual en cuanto abra el mercado.
    """
    sym = (entry or {}).get("symbol")
    if not sym:
        return entry
    try:
        q = (await asyncio.to_thread(market_data.get_quote_fast, sym)
             or await asyncio.to_thread(market_data.get_quote, sym))
        precio = float((q or {}).get("price") or 0)
        if precio <= 0:
            return entry
        upd = {"last_price": precio, "updated_at": _now()}
        if q.get("previous_close"):
            upd["previous_close"] = round(float(q["previous_close"]), 2)
        if q.get("change_percent") is not None:
            upd["daily_change_percent"] = round(float(q["change_percent"]), 2)
        await db.signal_entries.update_one({"id": entry["id"]}, {"$set": upd})
        entry.update(upd)
    except Exception as e:
        logger.info("Sin cotización inicial para %s: %s", sym, e)
    return entry


# Códigos de mercado que devuelve yfinance → el nombre que se lee en la Cartera.
#
# yfinance no dice "NASDAQ": dice "NMS" (Nasdaq Global Select), "NYQ" (NYSE) o "PCX"
# (NYSE Arca). Escribir el código crudo en la columna Mdo. sería cambiar un hueco por un
# jeroglífico. Lo que no está en esta tabla se deja VACÍO a propósito: una casilla vacía
# se ve y se corrige; un mercado equivocado se cuela y se queda, y encima `_DIVISA_POR_MERCADO`
# deduce la divisa a partir de él — un mercado mal puesto convierte mal el coste en euros.
_MERCADO_POR_CODIGO = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "NAS": "NASDAQ",
    "NASDAQGS": "NASDAQ", "NASDAQGM": "NASDAQ", "NASDAQCM": "NASDAQ", "NASDAQ": "NASDAQ",
    "NYQ": "NYSE", "NYSE": "NYSE",
    "ASE": "AMEX", "AMX": "AMEX", "AMEX": "AMEX",
    "PCX": "NYSEARCA", "ARCA": "NYSEARCA", "BTS": "BATS",
    "MCE": "MAD", "MAD": "MAD", "BME": "MAD",
    "GER": "ETR", "FRA": "FRA", "ETR": "ETR",
    "PAR": "PAR", "AMS": "AMS", "BRU": "BRU", "LIS": "LIS", "MIL": "MIL",
    "LSE": "LON", "LON": "LON",
    "TOR": "TSX", "TSX": "TSX", "VAN": "TSXV",
    "EBS": "SWX", "SWX": "SWX",
    "STO": "STO", "CPH": "CPH", "OSL": "OSL", "HEL": "HEL", "VIE": "VIE",
}


def mercado_legible(codigo) -> str:
    """Nombre de mercado a partir del código de yfinance. "" si no se reconoce."""
    return _MERCADO_POR_CODIGO.get((codigo or "").strip().upper().replace(" ", ""), "")


# Lo que se rellena solo, y lo que NO.
#
# Nombre, mercado y sector son HECHOS: los publica el mercado y se pueden consultar. El
# RIESGO no está aquí a propósito. "ALTO/MEDIO/BAJO" es la clasificación de tu inversor, y
# ninguna API la devuelve. Derivarlo de la beta o de la volatilidad daría un número con
# pinta de criterio, escrito justo en la casilla donde lees el criterio de otra persona.
# Prefiere quedarse vacío: un hueco se ve, y una etiqueta inventada no.
_CAMPOS_FICHA = ("name", "mercado", "sector")


async def completar_ficha(db, entry: dict) -> dict:
    """Rellena nombre, mercado y sector de una fila que los tenga vacíos.

    SOLO rellena huecos. Nunca pisa lo que ya hay: el sector que tú escribiste ("TECH
    GROWTH", "Viajes") es tu taxonomía y dice algo que "Technology" no dice; sustituirlo
    por lo que devuelve el proveedor sería perder información con cara de mejorarla.

    Si la consulta falla no se propaga: la fila ya existe y sirve, solo le faltan rótulos.
    """
    sym = (entry or {}).get("symbol")
    if not sym:
        return entry
    faltan = [c for c in _CAMPOS_FICHA if not (entry.get(c) or "").strip()]
    if not faltan:
        return entry
    try:
        q = await asyncio.to_thread(market_data.get_quote, sym)
        if not q:
            return entry
        candidatos = {
            "name": (q.get("name") or "").strip(),
            "mercado": mercado_legible(q.get("exchange")),
            "sector": (q.get("sector") or "").strip(),
        }
        # El nombre que devuelven los proveedores cuando no saben nada es el propio
        # símbolo. Guardarlo dejaría "AEM · AEM", que no informa de nada.
        if candidatos["name"].upper() == sym.upper():
            candidatos["name"] = ""
        upd = {c: candidatos[c] for c in faltan if candidatos[c]}
        if not upd:
            return entry
        upd["updated_at"] = _now()
        await db.signal_entries.update_one({"id": entry["id"]}, {"$set": upd})
        entry.update(upd)
    except Exception as e:
        logger.info("Sin ficha para %s: %s", sym, e)
    return entry


async def completar_fichas(db, limite: int = 200) -> dict:
    """Repasa la Cartera entera y completa las fichas incompletas.

    Existe porque las filas creadas antes de esto —y las que crearon las compras de
    Operaciones— se quedaron sin nombre ni mercado, y arreglarlas una a una a mano es
    justo lo que no se debe pedir.
    """
    entries = await db.signal_entries.find({}, {"_id": 0}).to_list(500)
    pendientes = [e for e in entries
                  if any(not (e.get(c) or "").strip() for c in _CAMPOS_FICHA)][:limite]
    completadas, sin_datos = [], []
    for e in pendientes:
        antes = {c: e.get(c) for c in _CAMPOS_FICHA}
        despues = await completar_ficha(db, dict(e))
        cambios = {c: despues.get(c) for c in _CAMPOS_FICHA
                   if (despues.get(c) or "") != (antes.get(c) or "")}
        (completadas if cambios else sin_datos).append(
            {"symbol": e.get("symbol"), **cambios} if cambios else e.get("symbol"))
    return {
        "revisadas": len(pendientes),
        "completadas": completadas,
        # Los que no se pudieron completar se DICEN. Un recuento que solo cuenta los
        # éxitos deja creer que ya está todo, y esas filas se quedan vacías para siempre.
        "sin_datos": sin_datos,
        "nota": "El riesgo no se rellena solo: es la clasificación de tu inversor, no un "
                "dato de mercado.",
    }


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
                              "alert_nivel3", "alert_nivel4", "alert_nivel5",
                              "alert_venta1", "alert_venta2", "alert_venta3", "active"):
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


def _ratio_volumen(df):
    """Volumen de HOY / media de las últimas ~20 sesiones. None si no hay datos.

    Sigue siendo INFORMATIVO: viaja en el mensaje de la alerta para que se lea, pero no
    condiciona el disparo. Convertirlo en condición exige decidir a partir de qué ratio
    un rebote «tiene volumen», y ese número hay que medirlo en nuestro histórico antes
    de ponerlo a filtrar alertas.
    """
    try:
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


async def _contexto_alerta(symbol: str):
    """Lo que hace falta para decidir si una alerta de COMPRA puede salir: (tendencia, ratio).

    UNA SOLA DESCARGA. Antes se pedían «3M» solo para el volumen; ahora se piden las
    velas diarias de dos años, que es lo que exige una SMA200, y de ese mismo DataFrame
    salen las dos cosas. Con «3M» (unas 126 sesiones) no hay 200 cierres y la tendencia
    saldría siempre SIN_DATOS, que es la forma silenciosa de dejar el veto inservible.

    Se calcula SOLO cuando una alerta está a punto de dispararse —que es raro— y el
    histórico va cacheado, así que el coste sigue siendo el de antes. No toca Finnhub:
    es la fuente gratuita de histórico.

    Si algo falla, la tendencia queda SIN_DATOS y la alerta NO sale. Fallo cerrado a
    propósito: ante la duda, no se manda un mensaje que dice COMPRA.
    """
    try:
        df = await asyncio.to_thread(market_data.get_stock_data, symbol, "1D")
    except Exception:
        logger.warning("alerta[%s]: no se pudo leer el histórico para la tendencia", symbol)
        return "SIN_DATOS", None
    if df is None or getattr(df, "empty", True) or "Close" not in df.columns:
        return "SIN_DATOS", None
    try:
        cierres = df["Close"].dropna().astype(float).tolist()
    except Exception:
        cierres = []
    return tendencia.desde_cierres(cierres), _ratio_volumen(df)


SIGNAL_WORKER_INTERVAL = int(os.environ.get("SIGNAL_WORKER_INTERVAL", 45))


async def signal_worker_loop(db, interval: int = SIGNAL_WORKER_INTERVAL):
    """Background: comprueba precios vs niveles activos.

    El espaciado entre símbolos lo impone el rate-limiter de Finnhub (bg_cap=40/min
    ≈ 1.5s/llamada) sin sleep artificial. Al acabar el ciclo dormimos sólo el tiempo
    sobrante hasta `interval`, mínimo 3s.

    COSTE: a interval=10s el ciclo no llegaba a dormir en cuanto había ~7 símbolos, así que
    el worker saturaba el cap de fondo las 16h de sesión extendida: 40/min × 60 × 16 ≈ 38.400
    llamadas a Finnhub AL DÍA, dejando solo 10/min del límite de 50 para tu propia navegación
    (de ahí que abrir una acción fuera lento a ratos). A 45s el ciclo respira y el consumo cae
    a una fracción. Para una cartera de medio plazo la diferencia entre enterarse de que se
    ha tocado un nivel en 20s o en 60s es irrelevante; la de quedarte sin cuota, no.
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
                    # Nivel deseado + objetivos de venta ESCALONADA (venta1-3)
                    sell_levels = {
                        "deseado": entry.get("deseado"),
                        "venta1": entry.get("venta1"),
                        "venta2": entry.get("venta2"),
                        "venta3": entry.get("venta3"),
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
                        # ── VETO DE TENDENCIA ────────────────────────────────
                        # Un soporte dice DÓNDE sería interesante comprar. Nunca dice
                        # que HAYA que comprar. Hasta aquí, esta alerta salía por el
                        # solo hecho de que el precio cruzara un nivel: una acción en
                        # caída libre generaba un mensaje que ponía COMPRA cada vez que
                        # atravesaba uno de sus soportes, que es exactamente lo que se
                        # espera de una acción en caída libre.
                        #
                        # Va ANTES del cooldown a propósito: si se marcara el cooldown y
                        # luego se vetara, el nivel quedaría quemado por hoy y la alerta
                        # no saldría tampoco si la tendencia se arreglara en la sesión.
                        #
                        # Las alertas de VENTA no pasan por aquí. Exigir tendencia
                        # alcista para avisar de una salida sería el error inverso:
                        # callarse justo cuando la acción se está rompiendo.
                        estado_tendencia, vol_ratio = await _contexto_alerta(symbol)
                        if not tendencia.hay_tendencia_valida(estado_tendencia):
                            logger.info(
                                "alerta COMPRA vetada %s %s: tendencia %s",
                                symbol, level_key, estado_tendencia,
                            )
                            continue
                        cd_key = f"{symbol}_{level_key}_{today}"
                        if await _is_in_cooldown(db, cd_key):
                            continue
                        await _set_cooldown(db, cd_key)
                        diff_pct = round(((price - target) / target) * 100, 2)
                        level_num = level_key.replace("nivel", "Nivel ")
                        approaching = price > target  # precio en zona pero aún sobre el nivel exacto
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
                        sell_label = "Deseado/Venta" if level_key == "deseado" else level_key.replace("venta", "Venta ")
                        await _fire_alert(
                            entry, symbol, sell_label, target, price, diff_pct, "VENTA",
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
