"""Persistencia del libro de operaciones y las cifras que ve la Cartera.

lotes.py es aritmética pura y no sabe de base de datos. Esto es el pegamento: guarda los
apuntes, los reproduce y los mezcla con el precio de mercado y el tipo de cambio de hoy.

Dos colecciones, las dos de solo-añadir:
  · `compras` — cada compra tal como se hizo
  · `ventas`  — cada venta tal como se hizo

Nada guarda saldos. El número de acciones que tienes, tu precio medio y lo que llevas
ganado se CALCULAN reproduciendo el libro. Guardar además un saldo es garantizar que algún
día no cuadre con sus propios apuntes, y entonces no hay forma de saber cuál miente.
"""
import logging
import re
import uuid
from datetime import datetime, timezone

import comisiones
import fx
import lotes
import signal_table

logger = logging.getLogger(__name__)


# El método de gestión es AJUSTABLE y se guarda en la base de datos, no en el código.
#
# El motivo: cual reproduce lo que ves en tu broker es una pregunta empírica, no de diseño.
# Si al vender tu precio medio BAJA, tu broker esta quitando las compras mas antiguas
# (FIFO); si SUBE, las mas recientes (LIFO). Hasta comprobarlo con una operacion real no se
# puede saber, y dejarlo fijo en el codigo obligaba a un despliegue para cambiar de idea.
#
# Cambiarlo NO altera ningun apunte: compras y ventas son las que son. Solo cambia como se
# emparejan al reproducir el libro, y por tanto que lotes quedan vivos, tu precio medio y
# que campanitas se encienden.
_CLAVE_METODO = "metodo_gestion"
_metodo_cache = {"valor": None, "ts": 0.0}
_TTL_AJUSTE = 30    # segundos; se lee en cada peticion y no merece ir a Mongo cada vez


async def metodo_gestion(db) -> str:
    """Método guardado, en MAYÚSCULAS. LIFO si nunca se ha elegido."""
    import time as _t
    if _metodo_cache["valor"] and (_t.time() - _metodo_cache["ts"]) < _TTL_AJUSTE:
        return _metodo_cache["valor"]
    valor = lotes.LIFO
    try:
        doc = await db.ajustes.find_one({"clave": _CLAVE_METODO}, {"_id": 0})
        if doc and doc.get("valor") in lotes.METODOS:
            valor = doc["valor"]
    except Exception as e:
        logger.warning("No se pudo leer el método de gestión: %s", e)
    _metodo_cache.update({"valor": valor, "ts": _t.time()})
    return valor


async def guardar_metodo_gestion(db, metodo: str) -> dict:
    """Guarda el método y RECALCULA todas las posiciones.

    Lo segundo no es opcional: el precio medio y las campanitas de la Cartera se derivan del
    método, así que cambiarlo sin recalcular dejaría la pantalla contando lo de antes.
    """
    metodo = (metodo or "").strip().upper()
    if metodo not in lotes.METODOS:
        raise ValueError(f"Método desconocido: {metodo}. Debe ser FIFO o LIFO.")
    await db.ajustes.update_one({"clave": _CLAVE_METODO},
                                {"$set": {"clave": _CLAVE_METODO, "valor": metodo,
                                          "updated_at": _ahora()}},
                                upsert=True)
    _metodo_cache.update({"valor": metodo, "ts": 0.0})   # ts=0 fuerza relectura
    compras, _ = await _libro(db)
    simbolos = sorted({c.get("symbol") for c in compras if c.get("symbol")})
    await _sincronizar_varias(db, simbolos)
    return {"metodo_gestion": metodo.lower(), "posiciones_recalculadas": len(simbolos)}


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# Mercados que NO cotizan en dólares. Caer a "USD" sin mirar hacía que una compra de OHLA
# (Madrid, en euros) se guardara como dólares y su coste saliera un 13,5% más barato: la
# ganancia se inflaba sola. El ISIN es la señal más fiable —sus dos primeras letras son el
# país de emisión— y el mercado de la ficha, la segunda.
_DIVISA_POR_MERCADO = {
    "MAD": "EUR", "BME": "EUR", "XMAD": "EUR", "MC": "EUR", "AMS": "EUR", "EPA": "EUR",
    "PAR": "EUR", "ETR": "EUR", "FRA": "EUR", "XETRA": "EUR", "MIL": "EUR", "BIT": "EUR",
    "LIS": "EUR", "BRU": "EUR", "VIE": "EUR", "HEL": "EUR", "DUB": "EUR",
    "LON": "GBP", "LSE": "GBP", "SWX": "CHF", "SIX": "CHF",
    "STO": "SEK", "CPH": "DKK", "OSL": "NOK", "TSX": "CAD", "TOR": "CAD",
}
# Los mercados de EE. UU. están AQUÍ y no en el "si no lo conozco, dólares" de abajo. La
# diferencia importa: como hecho conocido, NASDAQ manda sobre un campo `divisa` tecleado a
# mano; como caída por defecto, no mandaría sobre nada.
_DIVISA_POR_MERCADO.update({"NASDAQ": "USD", "NYSE": "USD", "AMEX": "USD",
                            "NYSEARCA": "USD", "BATS": "USD"})
_PAIS_ISIN_EUR = {"ES", "DE", "FR", "NL", "IT", "PT", "BE", "IE", "AT", "FI", "LU", "GR"}


def divisa_de_cotizacion(entry) -> str:
    """En qué moneda COTIZA el valor, según su mercado.

    No es lo mismo que la divisa de la operación, y confundirlas es lo que rompía NVDA: el
    coste iba bien (dólares al cambio del día) mientras el valor de hoy tomaba el precio de
    NASDAQ —dólares— y lo convertía con el cambio del EURO, o sea por 1. Salían dólares con
    el símbolo €: una posición recién comprada, plana, aparecía con +150 € y +16%.

    El mercado lo rellena el proveedor de datos, así que es un hecho comprobable; el campo
    `divisa` de la ficha se teclea a mano. Cuando se contradicen gana el mercado.
    """
    e = entry or {}
    porm = _DIVISA_POR_MERCADO.get((e.get("mercado") or "").strip().upper())
    if porm:
        return porm
    d = (e.get("divisa") or "").strip().upper()
    if d:
        return d
    isin = (e.get("isin") or "").strip().upper()
    if len(isin) >= 2:
        if isin[:2] in _PAIS_ISIN_EUR:
            return "EUR"
        if isin[:2] == "GB":
            return "GBP"
        if isin[:2] == "CH":
            return "CHF"
    return "USD"


def _divisa_de(divisa, entry) -> str:
    """Divisa de una operación. Nunca cae a USD a ciegas si hay pistas de lo contrario."""
    d = (divisa or "").strip().upper()
    if d:
        return d
    e = entry or {}
    # El mercado, que viene del proveedor, por delante del campo tecleado a mano: una ficha
    # de NASDAQ marcada "EUR" es una errata, y esa errata acababa dentro de cada compra.
    porm = _DIVISA_POR_MERCADO.get((e.get("mercado") or "").strip().upper())
    if porm:
        return porm
    d = (e.get("divisa") or "").strip().upper()
    if d:
        return d
    isin = (e.get("isin") or "").strip().upper()
    if len(isin) >= 2:
        if isin[:2] in _PAIS_ISIN_EUR:
            return "EUR"
        if isin[:2] == "GB":
            return "GBP"
        if isin[:2] == "CH":
            return "CHF"
    porm = _DIVISA_POR_MERCADO.get((e.get("mercado") or "").strip().upper())
    if porm:
        return porm
    return "USD"


async def _tasa(divisa: str, fecha: str):
    """Tipo de cambio de una fecha, sin bloquear el event loop (fx abre red)."""
    import asyncio
    try:
        return await asyncio.to_thread(fx.tasa_en_fecha, divisa, fecha)
    except Exception as e:
        logger.warning("No se pudo obtener el cambio de %s en %s: %s", divisa, fecha, e)
        return None


async def _sincronizar_posicion(db, symbol: str, metodo: str = None):
    """Deja las columnas `acciones` y `compra` de la Cartera acordes con el libro.

    Existen dos sitios donde vive el número de acciones: las columnas de la Cartera (que
    usan la tabla, el P&L antiguo y el worker de señales) y este libro. Tener que
    actualizar los dos a mano garantiza que algún día no cuadren, y además obliga a
    recordar un orden de pasos que nadie tiene por qué recordar.

    Así que el libro MANDA y la Cartera se deriva de él: al registrar una venta, las
    acciones de la tabla bajan solas. La Cartera pasa a ser un reflejo, no una segunda
    contabilidad.

    `compra` se pone al precio medio de lo que QUEDA abierto: es lo que hace falta para
    juzgar la posición viva, y es lo que la tabla muestra.
    """
    symbol = (symbol or "").strip().upper()
    compras, ventas = await _libro(db, symbol)
    if not compras and not ventas:
        return None   # sin libro para este valor: no se toca lo que haya puesto a mano
    # Con el método de GESTIÓN elegido (ajustable, ver metodo_gestion). Qué lotes quedan
    # vivos —y por tanto el precio medio y las campanitas— depende de él; el número total de
    # acciones sale igual con los dos.
    estado = lotes.reproducir(compras, ventas, metodo or await metodo_gestion(db))
    cambios = {"acciones": estado["acciones_abiertas"], "updated_at": _ahora()}
    if estado["precio_medio"] is not None:
        cambios["compra"] = estado["precio_medio"]

    # Las campanitas, en los dos sentidos: apagada mientras queden acciones de ese nivel,
    # encendida en cuanto se vende la última. Un nivel libre vuelve a ser un aviso útil —es
    # un sitio donde volverías a entrar— y dejarlo apagado silencia justo esa señal.
    #
    # Se hace en los dos sentidos y no solo al vender: si al comprar hubiera que apagarla a
    # mano, la regla quedaría a medias y una campanita encendida podría significar dos cosas
    # distintas, que es peor que no automatizar nada.
    entry = await db.signal_entries.find_one({"symbol": symbol}, {"_id": 0})
    alertas = lotes.estado_niveles(entry, compras, estado["abiertos"]) if entry else {}
    cambios.update(alertas)

    await db.signal_entries.update_one({"symbol": symbol}, {"$set": cambios})
    # Qué campanitas ha movido esta sincronización, para poder CONTARLO en la respuesta:
    # ver que "Nivel 1 vendido entero — campana reactivada" sin ir a la Cartera a mirarlo.
    estado["campanas"] = {
        "reactivadas": sorted(f"Nivel {k[-1]}" for k, v in alertas.items() if v is True),
        "apagadas": sorted(f"Nivel {k[-1]}" for k, v in alertas.items() if v is False),
    }
    return estado


async def _sincronizar_varias(db, simbolos):
    """Sincroniza VARIAS posiciones leyendo el libro una sola vez.

    Llamar a _sincronizar_posicion en bucle hace dos consultas por símbolo, y en una
    importación con decenas de valores eso son cientos de idas y vueltas a Mongo. Aquí se
    trae todo de una vez y se reparte en memoria.
    """
    simbolos = {(s or "").strip().upper() for s in simbolos if s}
    if not simbolos:
        return
    metodo = await metodo_gestion(db)
    compras, ventas = await _libro(db)
    entradas = {e["symbol"].upper(): e for e in await db.signal_entries.find(
        {}, {"_id": 0}).to_list(500) if e.get("symbol")}

    por_sym = {s: {"compras": [], "ventas": []} for s in simbolos}
    for c in compras:
        if c.get("symbol") in por_sym:
            por_sym[c["symbol"]]["compras"].append(c)
    for v in ventas:
        if v.get("symbol") in por_sym:
            por_sym[v["symbol"]]["ventas"].append(v)

    for sym, libro in por_sym.items():
        if not libro["compras"] and not libro["ventas"]:
            continue
        estado = lotes.reproducir(libro["compras"], libro["ventas"], metodo)
        cambios = {"acciones": estado["acciones_abiertas"], "updated_at": _ahora()}
        if estado["precio_medio"] is not None:
            cambios["compra"] = estado["precio_medio"]
        entry = entradas.get(sym)
        if entry:
            cambios.update(lotes.estado_niveles(entry, libro["compras"], estado["abiertos"]))
        await db.signal_entries.update_one({"symbol": sym}, {"$set": cambios})


async def _comision_o_estimada(comision, importe, divisa, tasa, fx_manual=False):
    """La comisión que se pasa MANDA; si viene vacía se estima con la tarifa publicada.

    Se distingue "vacía" (None) de "cero" a propósito: cero es una afirmación —esta
    operación no me costó nada— y hay que respetarla. Vacío significa "no lo sé", y ahí una
    estimación se acerca mucho más a la verdad que un cero, que infla la ganancia sin decirlo.
    """
    if comision is not None:
        return float(comision), False, None
    est = comisiones.estimar(importe, divisa, tasa, fx_manual=fx_manual)
    if est["total"] is None:
        return 0.0, False, None
    return est["total"], True, est["detalle"]


# ── Compras ──────────────────────────────────────────────────────────────────

async def _asegurar_entry(db, symbol: str, divisa: str) -> dict:
    """Crea la fila de Cartera de un valor que aún no la tiene, SIN niveles.

    El precio de mercado de una posición no lo trae la Cartera: lo escribe el worker de
    señales, que recorre `db.signal_entries` (`active: True`) y les pone `last_price`.
    Comprar algo que no estaba en la Cartera dejaba la posición sin fila y, por tanto, sin
    precio: había que teclearlo a mano o inventarse unos niveles solo para que cotizara.

    Así que la compra crea la fila. Lo que NO crea son los niveles: nivel1..5 quedan a
    None. El precio de compra y los niveles de estrategia son cosas distintas —poner la
    compra como nivel1 haría que la posición se etiquetara "NIVEL 1" y sería indistinguible
    de una donde el nivel sí se decidió— y mientras estén vacíos no puede saltar ninguna
    alerta: el worker recorre nivel1..5 y no hay ninguno que cruzar.
    """
    entry = await signal_table.create_entry(db, {
        "symbol": symbol,
        "grupo": "ideas_javi",
        "divisa": divisa,
        "active": True,
        "notes": "Creada al registrar una compra en Operaciones. Niveles pendientes.",
    })
    # Y el precio ya, sin esperar al worker: registrar una compra un sábado o de noche
    # dejaba la posición con "—" hasta la sesión siguiente. Si no se puede leer, la compra
    # se guarda igual y el worker lo rellena al abrir.
    entry = await signal_table.cotizacion_inicial(db, entry)
    # Nombre, mercado y sector, que son datos públicos. El riesgo NO: ese lo pones tú.
    return await signal_table.completar_ficha(db, entry)


async def registrar_compra(db, symbol: str, acciones: float, precio: float,
                           fecha: str = None, comision: float = None,
                           divisa: str = None, tasa: float = None,
                           nivel: str = None, notas: str = "") -> dict:
    """Guarda una compra. Detecta sola en qué nivel de la Cartera se hizo."""
    symbol = (symbol or "").strip().upper()
    entry = await db.signal_entries.find_one({"symbol": symbol}, {"_id": 0})
    divisa = _divisa_de(divisa, entry)
    if entry is None:
        entry = await _asegurar_entry(db, symbol, divisa)

    compra = lotes.nueva_compra(symbol, acciones, precio, fecha=fecha, comision=0.0,
                                divisa=divisa, tasa=tasa, nivel=nivel, notas=notas)
    # El cambio del día de la compra. El que venga dado MANDA: el del banco incluye su
    # margen y no coincide con el de mercado, y es el que de verdad te cobraron.
    if compra["tasa"] is None:
        compra["tasa"] = await _tasa(divisa, compra["fecha"])
    # La comisión se resuelve DESPUÉS del tipo de cambio: los 2 € fijos hay que pasarlos a
    # la divisa de la operación y sin tasa no se puede.
    compra["comision"], compra["comision_estimada"], compra["comision_detalle"] = (
        await _comision_o_estimada(comision, float(acciones) * float(precio), divisa,
                                   compra["tasa"]))

    if compra["nivel"] and compra["nivel"].startswith("nivel"):
        compra["nivel_etiqueta"] = f"Nivel {compra['nivel'][-1]}"
    # Nivel: si no se indica a mano, se deduce del precio contra los niveles de la Cartera.
    if not compra["nivel"] and entry:
        det = lotes.detectar_nivel(compra["precio"], entry)
        compra["nivel"] = det.get("nivel")
        compra["nivel_etiqueta"] = det.get("nivel_etiqueta")
        compra["precio_nivel"] = det.get("precio_nivel")
        compra["desvio_nivel_pct"] = det.get("desvio_pct")

    await db.compras.insert_one(dict(compra))
    # El precio del nivel en la Cartera pasa a ser el precio REAL al que se compró. Antes
    # había que acordarse de actualizarlo a mano y no se hacía: los niveles se quedaban con
    # el precio planeado y la siguiente compra ya no casaba con ninguno.
    await _actualizar_precio_nivel(db, symbol, compra.get("nivel"), compra["precio"], entry)
    await _sincronizar_posicion(db, symbol)
    return compra


async def _actualizar_precio_nivel(db, symbol: str, nivel, precio, entry=None) -> None:
    """Pone el precio de `nivel` de la Cartera al precio real de la compra que lo tocó.

    Solo niveles de compra (nivel1..5): `deseado` es el objetivo de VENTA y una compra no
    debe moverlo. Y solo si de verdad cambia, para no reescribir la Cartera en balde.
    """
    if not nivel or nivel not in {f"nivel{i}" for i in range(1, 6)}:
        return
    if entry is None:
        entry = await db.signal_entries.find_one({"symbol": symbol}, {"_id": 0})
    if not entry:
        return
    try:
        actual = float(entry.get(nivel) or 0)
    except (TypeError, ValueError):
        actual = 0
    if precio and round(actual, 4) != round(float(precio), 4):
        await db.signal_entries.update_one(
            {"symbol": symbol}, {"$set": {nivel: round(float(precio), 4)}})


async def asignar_nivel_compra(db, compra_id: str, nivel) -> dict:
    """Asigna (o quita, con None) el nivel de una compra a mano.

    La detección automática solo asigna si el precio de ejecución está a menos del 1,5% del
    nivel, y una compra real puede desviarse más — pasó con 2 AAOI a 120,89 $ sobre un nivel
    de 118,90: un 1,67% y el lote quedó "fuera de niveles", con su campanita sin apagar.
    Subir la tolerancia asignaría compras al nivel equivocado cuando hay niveles juntos;
    dejar que lo digas tú, no.
    """
    if nivel is not None and nivel not in {f"nivel{i}" for i in range(1, 6)}:
        raise ValueError(f"Nivel desconocido: {nivel}")
    doc = await db.compras.find_one({"id": compra_id}, {"_id": 0})
    if not doc:
        raise ValueError("No existe esa compra.")
    etiqueta = f"Nivel {nivel[-1]}" if nivel else None
    await db.compras.update_one(
        {"id": compra_id}, {"$set": {"nivel": nivel, "nivel_etiqueta": etiqueta}})
    # Asignar el nivel a mano dice "ESTA compra fue la de ese nivel": el precio del nivel
    # en la Cartera pasa a ser el real de la compra, igual que al registrarla.
    await _actualizar_precio_nivel(db, doc.get("symbol"), nivel, doc.get("precio"))
    await _sincronizar_posicion(db, doc.get("symbol"))
    return {**doc, "nivel": nivel, "nivel_etiqueta": etiqueta}


async def borrar_compra(db, compra_id: str, forzar: bool = False) -> dict:
    """Borra una compra. Se niega si eso dejaría ventas sin coste, salvo `forzar`.

    Borrar el lote del que salió una venta no da un error en ninguna parte: la venta se
    queda sin base de coste, su ingreso entero pasa a contar como ganancia y el Realizado
    sube solo. Antes esto devolvía {"ok": true} sin decir nada. La comprobación se hace
    reproduciendo el libro SIN esa compra, antes de tocar la base de datos.
    """
    doc = await db.compras.find_one({"id": compra_id}, {"_id": 0})
    if not doc:
        return {"borrada": False, "motivo": "no_existe"}
    sym = doc.get("symbol")
    compras, ventas = await _libro(db, sym)
    if ventas and not forzar:
        quedan = [c for c in compras if c.get("id") != compra_id]
        estado = lotes.reproducir(quedan, ventas, await metodo_gestion(db))
        sin_cubrir = round(estado.get("acciones_sin_cubrir") or 0, 6)
        if sin_cubrir > 1e-9:
            return {"borrada": False, "motivo": "dejaria_ventas_sin_coste",
                    "acciones_sin_cubrir": sin_cubrir, "symbol": sym}
    r = await db.compras.delete_one({"id": compra_id})
    if r.deleted_count:
        # Si era el último apunte del símbolo, _sincronizar_posicion se retira sin tocar
        # nada y la Cartera seguiría enseñando acciones que ya no existen en el libro.
        if not [c for c in compras if c.get("id") != compra_id] and not ventas:
            await db.signal_entries.update_one(
                {"symbol": sym}, {"$set": {"acciones": 0, "updated_at": _ahora()}})
        else:
            await _sincronizar_posicion(db, sym)
    return {"borrada": r.deleted_count > 0, "symbol": sym}


# ── Ventas ───────────────────────────────────────────────────────────────────

async def registrar_venta(db, symbol: str, acciones: float, precio: float,
                          fecha: str = None, comision: float = None,
                          divisa: str = None, tasa: float = None,
                          notas: str = "") -> dict:
    """Guarda una venta y devuelve el resultado por los DOS métodos.

    No se comprueba aquí que haya acciones suficientes: eso lo dice el libro al
    reproducirlo, y avisar del descuadre es más útil que rechazar la venta — casi siempre
    significa que falta meter una compra vieja, no que la venta esté mal.
    """
    symbol = (symbol or "").strip().upper()
    entry = await db.signal_entries.find_one({"symbol": symbol}, {"_id": 0})
    divisa = _divisa_de(divisa, entry)

    venta = lotes.nueva_venta(symbol, acciones, precio, fecha=fecha, comision=0.0,
                              divisa=divisa, tasa=tasa, notas=notas)
    if venta["tasa"] is None:
        venta["tasa"] = await _tasa(divisa, venta["fecha"])
    venta["comision"], venta["comision_estimada"], venta["comision_detalle"] = (
        await _comision_o_estimada(comision, float(acciones) * float(precio), divisa,
                                   venta["tasa"]))

    await db.ventas.insert_one(dict(venta))
    # La Cartera se actualiza sola: no hay que tocar el número de acciones a mano.
    sync = await _sincronizar_posicion(db, symbol)
    res = await estado_simbolo(db, symbol)
    # Qué campanitas ha movido esta venta: un nivel vendido entero se reactiva, y decirlo
    # aquí ahorra ir a la Cartera a comprobar que ha pasado.
    res["campanas"] = (sync or {}).get("campanas") or {"reactivadas": [], "apagadas": []}
    return res


async def estimar_comisiones_pendientes(db, aplicar: bool = False) -> dict:
    """Pone la comisión estimada a los apuntes que se quedaron a cero por el fallo del vacío.

    Durante un tiempo el formulario enviaba 0 cuando dejabas el campo en blanco, y el
    servidor hacía lo correcto con ese 0: respetarlo, porque un cero explícito significa
    "esta operación no me costó nada". El resultado es que TODAS las operaciones tecleadas
    a mano quedaron sin comisión, inflando la ganancia realizada entre 6 y 10 € cada venta.

    Solo se tocan las que NO vienen del CSV. Un apunte con huella trae la comisión real del
    fichero, y si esa es cero es que de verdad fue cero: sustituirla por una estimación
    sería cambiar un dato bueno por uno inventado.

    Sin `aplicar` solo se calcula y se devuelve, para poder ver qué va a pasar antes de que
    pase. Lo que se escribe queda marcado como estimado, que es lo que permite distinguirlo
    después de una cifra sacada de tu extracto.
    """
    cambios = {"compras": [], "ventas": []}
    total_eur = 0.0
    for col, clave in (("compras", "compras"), ("ventas", "ventas")):
        for d in await getattr(db, col).find({}, {"_id": 0}).to_list(5000):
            if d.get("huella"):
                continue
            if float(d.get("comision") or 0) > 0.01:
                continue
            bruto = float(d.get("acciones") or 0) * float(d.get("precio") or 0)
            tasa = lotes.tasa_de(d)
            if not tasa:
                tasa = await _tasa(d.get("divisa") or "USD", d.get("fecha"))
            est = comisiones.estimar(bruto, d.get("divisa") or "USD", tasa)
            if est["total"] is None or est["total"] <= 0:
                continue
            en_eur = est["total"] / float(tasa) if tasa else None
            total_eur += en_eur or 0.0
            cambios[clave].append({"id": d.get("id"), "symbol": d.get("symbol"),
                                   "fecha": str(d.get("fecha") or "")[:10],
                                   "acciones": d.get("acciones"),
                                   "comision": round(est["total"], 4),
                                   "eur": round(en_eur, 2) if en_eur is not None else None})
            if aplicar:
                await getattr(db, col).update_one(
                    {"id": d.get("id")},
                    {"$set": {"comision": round(est["total"], 4),
                              "comision_estimada": True,
                              "comision_detalle": est["detalle"]}})
    return {"aplicado": aplicar,
            "compras": len(cambios["compras"]), "ventas": len(cambios["ventas"]),
            "total_eur": round(total_eur, 2),
            "detalle": cambios}


async def registrar_compra_multinivel(db, symbol: str, reparto: list, precio: float,
                                      fecha: str = None, comision=None,
                                      divisa: str = None, tasa: float = None,
                                      notas: str = "") -> dict:
    """UNA orden repartida en varios niveles: 12 acciones que son 6 del Nivel 1 y 6 del 2.

    Pasa de verdad cuando una acción cae tanto que se cruzan dos niveles en la misma compra.
    Se guardan como lotes SEPARADOS —uno por nivel— porque es lo que son: dos entradas a
    precios objetivo distintos, y mantenerlas juntas haría imposible después decir de qué
    nivel salió una venta.

    Lo que NO puede pasar es cobrar la comisión dos veces. Es una sola orden y DEGIRO cobra
    una sola comisión: los 2 € fijos son por operación, no por lote. Así que se calcula una
    vez sobre el importe ENTERO y se prorratea por acciones. Registrar los lotes por
    separado con la comisión en blanco los estimaría por su cuenta y cobraría los 2 € fijos
    tantas veces como niveles hubiera.

    Los lotes se crean del nivel más caro al más barato, que es el orden en que se tocan al
    caer: FIFO desempata por ese orden cuando comparten fecha.
    """
    reparto = [(str(n).strip(), float(a)) for n, a in reparto if float(a or 0) > 0]
    if not reparto:
        raise ValueError("Hay que decir cuántas acciones van en cada nivel.")
    total = sum(a for _, a in reparto)

    entry = await db.signal_entries.find_one({"symbol": (symbol or "").strip().upper()},
                                             {"_id": 0})
    divisa = _divisa_de(divisa, entry)
    if tasa is None:
        tasa = await _tasa(divisa, (fecha or _hoy())[:10])
    # La comisión de la orden ENTERA, una sola vez.
    total_com, estimada, detalle = await _comision_o_estimada(
        comision, total * float(precio), divisa, tasa)

    # Del nivel más caro al más barato. `nivel1` es el más alto por convenio de la Cartera.
    reparto.sort(key=lambda x: x[0])
    creadas = []
    for i, (nivel, acciones) in enumerate(reparto):
        parte = acciones / total
        c = await registrar_compra(
            db, symbol, acciones, precio, fecha=fecha,
            # Prorrateada. El último se lleva el resto para que la suma cuadre al céntimo.
            comision=(round(total_com - sum(x["comision"] for x in creadas), 4)
                      if i == len(reparto) - 1 else round(total_com * parte, 4)),
            divisa=divisa, tasa=tasa, nivel=nivel or None,
            notas=notas or f"Compra repartida en {len(reparto)} niveles")
        if estimada:
            await db.compras.update_one({"id": c["id"]},
                                        {"$set": {"comision_estimada": True,
                                                  "comision_detalle": detalle}})
            c["comision_estimada"] = True
        creadas.append(c)
    return {"compras": creadas, "acciones": total,
            "comision_total": round(total_com, 4), "comision_estimada": estimada}


async def borrar_venta(db, venta_id: str) -> bool:
    doc = await db.ventas.find_one({"id": venta_id}, {"_id": 0})
    r = await db.ventas.delete_one({"id": venta_id})
    if r.deleted_count and doc:
        await _sincronizar_posicion(db, doc.get("symbol"))
    return r.deleted_count > 0


# ── Lectura ──────────────────────────────────────────────────────────────────

async def _libro(db, symbol: str = None):
    filtro = {"symbol": symbol.strip().upper()} if symbol else {}
    compras = await db.compras.find(filtro, {"_id": 0}).to_list(5000)
    ventas = await db.ventas.find(filtro, {"_id": 0}).to_list(5000)
    return compras, ventas


async def estado_simbolo(db, symbol: str, precio_actual=None) -> dict:
    """Todo lo de un símbolo: lotes abiertos, ventas por los dos métodos y latente."""
    symbol = (symbol or "").strip().upper()
    compras, ventas = await _libro(db, symbol)
    comp = lotes.comparar_metodos(compras, ventas)
    gestion = (await metodo_gestion(db)).lower()
    divisa = (compras or ventas or [{}])[0].get("divisa", "USD") if (compras or ventas) else "USD"

    tasa_hoy = None
    if precio_actual is not None:
        import asyncio
        try:
            tasa_hoy = await asyncio.to_thread(fx.tasa_actual, divisa)
        except Exception:
            tasa_hoy = None

    # Los niveles de la Cartera, para poder dar de alta las compras desde ellos sin tener
    # que copiar los precios a mano de una pantalla a otra.
    entry = await db.signal_entries.find_one({"symbol": symbol}, {"_id": 0}) or {}
    niveles = []
    for i in range(1, 6):
        p = entry.get(f"nivel{i}")
        if p in (None, "", 0):
            continue
        try:
            p = float(p)
        except (TypeError, ValueError):
            continue
        if p > 0:
            niveles.append({"nivel": f"nivel{i}", "etiqueta": f"Nivel {i}", "precio": p,
                            "comprado": entry.get(f"alert_nivel{i}") is False})
    niveles.sort(key=lambda n: n["precio"], reverse=True)

    return {
        "symbol": symbol,
        "divisa": divisa,
        "niveles": niveles,
        "compras": sorted(compras, key=lambda c: str(c.get("fecha") or "")),
        **comp,
        # Con el metodo de gestion: es la cifra de "cuanto llevo ganado", no la fiscal.
        "metodo_gestion": gestion,
        # Media ponderada: la cifra que enseña el bróker, SOLO para poder cuadrar las dos
        # pantallas. No entra en ningún cálculo de ganancia por nivel — bajo PMP los niveles
        # dejan de existir, porque todas las acciones cuestan lo mismo.
        "ponderada": lotes.media_ponderada(compras, ventas),
        "latente": lotes.valorar_abierto(comp[gestion], precio_actual, tasa_hoy),
        "tasa_hoy": round(tasa_hoy, 4) if tasa_hoy else None,
        # Con qué precio se ha valorado, y el cierre anterior al lado. Es la única cifra de
        # la posición que no sale de tus apuntes, y cuando el bróker enseña otra ganancia
        # suele ser esto: en NFLX eran 81,78 $ aquí contra los 80,01 $ que implicaba DEGIRO
        # —121,80 € de diferencia— con el mismo coste, el mismo cambio y el mismo método.
        "precio_actual": precio_actual,
        "cierre_anterior": entry.get("previous_close"),
        "estado_mercado": entry.get("market_state"),
        **_cambio_de_la_posicion(comp[gestion], tasa_hoy),
    }


def _cambio_de_la_posicion(estado: dict, tasa_hoy) -> dict:
    """Al cambio de qué se convirtió el coste de la posición, y cuánto se fía uno de él.

    Es la explicación de por qué el latente de InverIA y el del bróker no coinciden aunque
    el precio y las acciones sean idénticos. El coste en euros de cada lote sale del cambio
    de SU día; si ese día no es el día real de la compra —lotes metidos a mano, o traídos
    de una foto de posiciones en vez del CSV de operaciones— el cambio es el del día en que
    se dieron de alta, y el coste en euros sale desviado aunque las acciones y el precio en
    dólares estén perfectos.

    En NFLX salía así: 6.106,40 $ convertidos a 1,1554 de media (5.285 €) cuando el bróker
    los tenía a 1,1273 (5.417 €). Mismo valor de hoy, 131 € de diferencia en la ganancia,
    y ninguna de las dos pantallas equivocada en el precio. Se enseña el cambio medio para
    poder compararlo, y se dice cuántas acciones NO vienen del CSV, que son las sospechosas:
    su fecha es la de importación, no la de la compra.
    """
    abiertos = estado.get("abiertos") or []
    coste_div = estado.get("coste_abierto_divisa") or 0.0
    coste_eur = estado.get("coste_abierto_eur")
    medio = round(coste_div / coste_eur, 4) if coste_eur else None
    # Solo los lotes que creó la FOTO de posiciones, no todo lo que no tenga huella. Esa
    # era la trampa: una compra que acabas de teclear tampoco tiene huella —el CSV de hoy
    # todavía no existe— y salía acusada de llevar "la fecha en que se dio de alta y no la
    # de tu compra", que en una compra de hoy es la misma fecha. El aviso mandaba a borrarla
    # y reimportar un fichero que no puede contenerla.
    #
    # Los lotes de la foto sí se reconocen: los escribe `importar_posiciones_existentes` con
    # esa nota, y son los únicos cuya fecha es demostrablemente inventada.
    sin_csv = [l for l in abiertos
               if not l.get("huella")
               and str(l.get("notas") or "").startswith("Importada de tu Cartera")]
    return {
        "cambio_medio_compras": medio,
        # Con el de hoy al lado: un cambio medio pegado al de hoy en una posición vieja es
        # justo la señal de que las fechas de los lotes no son las de las compras.
        "cambio_hoy": round(tasa_hoy, 4) if tasa_hoy else None,
        "acciones_sin_csv": round(sum(l.get("acciones_abiertas") or 0 for l in sin_csv), 6),
        "acciones_abiertas_total": estado.get("acciones_abiertas"),
    }


def _coinciden(*ventas) -> bool:
    """¿Dan los métodos el mismo resultado? En dólares, que siempre se conoce.

    Un céntimo de holgura por el redondeo de cada lote; más que eso es otro conjunto de
    lotes, no otra forma de redondear.
    """
    cifras = [v.get("ganancia_divisa") for v in ventas if v and v.get("ganancia_divisa") is not None]
    return len(cifras) < 2 or (max(cifras) - min(cifras)) < 0.02


async def historial(db, limite: int = 1000) -> dict:
    """Todas las ventas de todos los símbolos, ya calculadas, más los totales.

    Cada símbolo se reproduce por separado: el emparejamiento es POR VALOR, y mezclar
    símbolos haría que una venta de Apple consumiera un lote de Meta.
    """
    compras, ventas = await _libro(db)
    gestion = (await metodo_gestion(db)).lower()
    por_symbol = {}
    for op in compras + ventas:
        por_symbol.setdefault(op.get("symbol"), {"compras": [], "ventas": []})
    for c in compras:
        por_symbol[c.get("symbol")]["compras"].append(c)
    for v in ventas:
        por_symbol[v.get("symbol")]["ventas"].append(v)

    filas, resumen_symbol = [], []
    for sym, libro in por_symbol.items():
        if not libro["ventas"]:
            continue
        comp = lotes.comparar_metodos(libro["compras"], libro["ventas"])
        # Las ventas de los dos métodos van emparejadas: es la MISMA operación vista de dos
        # maneras, no dos operaciones. Presentarlas por separado invita a sumarlas.
        # La media ponderada de la MISMA venta, para poder cuadrarla con el bróker: es el
        # método que él usa y da un tercer resultado, distinto de FIFO y de LIFO.
        pmp = {x["id"]: x for x in lotes.media_ponderada(
            libro["compras"], libro["ventas"])["ventas"] if x.get("id")}
        for vf, vl in zip(comp["fifo"]["ventas"], comp["lifo"]["ventas"]):
            filas.append({
                "id": vf.get("id"), "symbol": sym, "fecha": vf.get("fecha"),
                "acciones": vf.get("acciones"), "precio_venta": vf.get("precio_venta"),
                "divisa": vf.get("divisa"), "comision_venta": vf.get("comision_venta"),
                "notas": vf.get("notas") or "",
                # El cambio del día de la venta: sin él no se puede rehacer la cuenta en
                # euros a mano, y comprobarla es justo lo que da confianza en la cifra.
                "tasa_venta": vf.get("tasa"),
                "fifo": _fila_metodo(vf),
                "lifo": _fila_metodo(vl),
                "ponderada": pmp.get(vf.get("id")),
                "sin_cubrir": vf.get("sin_cubrir") or 0,
                # Si cerró la posición, los tres métodos coinciden por fuerza. Decirlo evita
                # leer como error de cálculo lo que es la definición de vender por niveles.
                "cierra_posicion": vf.get("cierra_posicion", False),
                "abiertas_despues": vf.get("abiertas_despues"),
                # Cerrar la posición OBLIGA a que los tres métodos den lo mismo: se
                # consumen todos los lotes, así que no queda nada que elegir. Si difieren,
                # el libro tiene lotes que no deberían estar —o le faltan— y la cifra de
                # arriba está calculada sobre un conjunto que no es el real. Callarlo y
                # seguir imprimiendo «los tres coinciden» es afirmar algo que la propia
                # pantalla desmiente tres líneas más abajo.
                "ventas_antes": vf.get("ventas_antes", 0),
                # Los tres métodos SOLO están obligados a coincidir cuando la venta cierra
                # la posición Y es la primera: entonces se consumen todos los lotes y no
                # queda nada que elegir. Con ventas anteriores cada método dejó vivos lotes
                # distintos, así que difieran es lo normal y no un síntoma de nada.
                "metodos_incoherentes": bool(
                    vf.get("cierra_posicion") and not vf.get("ventas_antes")
                    and not _coinciden(vf, vl, pmp.get(vf.get("id")))),
            })
        resumen_symbol.append({
            "symbol": sym,
            "n_ventas": len(libro["ventas"]),
            "ganancia_eur": comp[gestion]["ganancia_realizada_eur"],
            "ganancia_divisa": comp[gestion]["ganancia_realizada_divisa"],
            "divisa": libro["ventas"][0].get("divisa", "USD"),
        })

    filas.sort(key=lambda f: str(f.get("fecha") or ""), reverse=True)
    resumen_symbol.sort(key=lambda r: r.get("ganancia_eur") or 0, reverse=True)

    # Una venta metida a mano y la misma venta venida luego del CSV solo se detectan como
    # iguales si coinciden al céntimo; tecleada de memoria, rara vez lo hace. El resultado
    # es la MISMA venta contada dos veces — y en una posición ya cerrada no se nota en el
    # número de acciones, solo en que la ganancia se dispara. Se avisa de las parejas
    # sospechosas (misma acción, misma fecha, mismas acciones, y solo una con huella de CSV)
    # para poder borrar la copia manual con su botón.
    # LO MISMO CON LAS COMPRAS, que era el hueco. Una compra duplicada no dispara ninguna
    # alarma contable —no deja ventas sin cubrir, no descuadra nada— pero infla la posición
    # y con ella el latente. Pasó de verdad en NFLX: 30 acciones tecleadas a 76,00 $ el
    # 13/08 y la MISMA compra importada del CSV a 76,01. Un céntimo de diferencia, así que
    # el emparejamiento exacto no las veía; en pantalla salían 80 acciones donde el bróker
    # tenía 50, y unos +140 € de ganancia que no existían. Las otras quince posiciones
    # cuadraban al detalle, que es justo lo que hace que un fallo así no se busque.
    dudosas_compra = []
    for sym, libro in por_symbol.items():
        vistos = {}
        for c in libro["compras"]:
            k = (str(c.get("fecha") or "")[:10], round(float(c.get("acciones") or 0), 6))
            vistos.setdefault(k, []).append(c)
        for (fch, acc), grupo in vistos.items():
            if len(grupo) > 1 and any(g.get("huella") for g in grupo) \
                    and any(not g.get("huella") for g in grupo):
                manuales = [g for g in grupo if not g.get("huella")]
                dudosas_compra.append({
                    "symbol": sym, "fecha": fch, "acciones": acc,
                    "precios": sorted({round(float(g.get("precio") or 0), 4) for g in grupo}),
                    "ids_manuales": [g["id"] for g in manuales],
                    # Lo que se quita de la posición si se borran las copias manuales. Es la
                    # cifra que dice si merece la pena mirarlo.
                    "acciones_de_mas": round(sum(g.get("acciones") or 0 for g in manuales), 6),
                })
    dudosas_compra.sort(key=lambda d: d["acciones_de_mas"], reverse=True)

    dudosas = []
    for sym, libro in por_symbol.items():
        vistos = {}
        for v in libro["ventas"]:
            k = (str(v.get("fecha") or "")[:10], round(float(v.get("acciones") or 0), 6))
            vistos.setdefault(k, []).append(v)
        for (fch, acc), grupo in vistos.items():
            if len(grupo) > 1 and any(g.get("huella") for g in grupo) \
                    and any(not g.get("huella") for g in grupo):
                dudosas.append({"symbol": sym, "fecha": fch, "acciones": acc,
                                "ids_manuales": [g["id"] for g in grupo if not g.get("huella")]})

    # Ventas registradas SIN comisión. DEGIRO cobra 2 € por operación más el 0,25% de
    # AutoFX, así que una venta a coste cero es casi siempre un dato que no llegó —del CSV
    # con las columnas sin reconocer, o tecleada dejando el campo vacío—. Cada una infla la
    # ganancia entre 6 y 10 €, y con cien ventas eso es dinero de verdad en una declaración.
    #
    # Se cuenta y se ESTIMA lo que falta, en vez de corregirlo solo: el apunte es del
    # usuario y una comisión inventada sería otro dato falso, solo que en la otra dirección.
    sin_comision, coste_no_contado = [], 0.0
    for sym, libro in por_symbol.items():
        for v in libro["ventas"]:
            if float(v.get("comision") or 0) > 0.01:
                continue
            bruto = float(v.get("acciones") or 0) * float(v.get("precio") or 0)
            tasa = v.get("tasa") or 1.0
            # La tarifa de DEGIRO: 2 € fijos + 0,25% de conversión, en euros.
            coste_no_contado += 2.0 + (bruto / tasa) * 0.0025
            # CUÁLES, no solo cuántas. Casi siempre son ventas tecleadas a mano, y esas no
            # se arreglan reimportando: sin huella no hay nada que emparejar, y encima el
            # apunte manual TAPA la fila del CSV, que sí trae la comisión buena. Se
            # arreglan borrándolas y volviendo a importar, así que hay que poder
            # encontrarlas — con el símbolo y la fecha delante se tarda un minuto.
            sin_comision.append({"symbol": sym, "fecha": str(v.get("fecha") or "")[:10],
                                 "acciones": v.get("acciones"), "id": v.get("id"),
                                 "manual": not v.get("huella")})
    sin_comision.sort(key=lambda x: x["fecha"], reverse=True)

    return {
        "posibles_duplicadas": dudosas,
        "posibles_compras_duplicadas": dudosas_compra,
        "ventas_sin_comision": len(sin_comision),
        "ventas_sin_comision_detalle": sin_comision[:30],
        "ventas_sin_comision_manuales": sum(1 for v in sin_comision if v["manual"]),
        "comision_no_contada_eur": round(coste_no_contado, 2) if sin_comision else None,
        "items": filas[:limite],
        "por_symbol": resumen_symbol,
        "resumen": _totales(filas),
        "metodo_gestion": gestion,
        "nota_fiscal": lotes.comparar_metodos([], [])["nota_fiscal"],
    }


def _fila_metodo(v: dict) -> dict:
    """Lo que hace falta para poder COMPROBAR la cifra a mano, no solo verla.

    Se devuelven los dos lados —divisa y euros— de cada paso: ingresado, coste y ganancia.
    Antes solo salía el coste y la ganancia, y el ingreso había que deducirlo sumando; en
    euros no se podía ni eso, así que el salto de "259 $" a "209 €" era un acto de fe.
    """
    return {
        "ingreso_divisa": v.get("ingreso_divisa"), "ingreso_eur": v.get("ingreso_eur"),
        "coste_divisa": v.get("coste_divisa"), "coste_eur": v.get("coste_eur"),
        "ganancia_divisa": v.get("ganancia_divisa"), "ganancia_eur": v.get("ganancia_eur"),
        "pct": v.get("pct"), "pct_eur": v.get("pct_eur"),
        "efecto_divisa_eur": v.get("efecto_divisa_eur"),
        "comisiones_totales": v.get("comisiones_totales"),
        "exacto": v.get("exacto"), "lotes": v.get("lotes"),
    }


def _totales(filas: list) -> dict:
    """Totales por método.

    Lo exacto y lo que no se pudo calcular van SEPARADOS a propósito: sumarlos daría un
    total con una precisión que no tiene, y ese total acabaría en una declaración.
    """
    out = {}
    for metodo in ("fifo", "lifo"):
        exactas = [f[metodo] for f in filas if f[metodo].get("exacto")]
        out[metodo] = {
            "ganancia_eur": round(sum(x["ganancia_eur"] for x in exactas), 2) if exactas else None,
            "ganancia_divisa": round(sum(f[metodo]["ganancia_divisa"] for f in filas), 2),
            "efecto_divisa_eur": round(
                sum(x.get("efecto_divisa_eur") or 0 for x in exactas), 2) if exactas else None,
            "n_exactas": len(exactas),
        }
    # Y el total por MEDIA PONDERADA, que es el método del bróker. Sin él, el interruptor
    # «Ver como en DEGIRO» solo podía cambiar la tabla de posiciones abiertas: el realizado
    # de arriba seguía en FIFO/LIFO, así que la pantalla enseñaba a la vez dos métodos sin
    # decirlo. Se calcula igual que los otros dos —solo lo exacto— para no mezclar una
    # cifra con tipos de cambio con otra que no los tiene.
    pond = [f["ponderada"] for f in filas if f.get("ponderada")]
    con_eur = [x for x in pond if x.get("ganancia_eur") is not None]
    out["ponderada"] = {
        "ganancia_eur": round(sum(x["ganancia_eur"] for x in con_eur), 2) if con_eur else None,
        "ganancia_divisa": round(sum(x.get("ganancia_divisa") or 0 for x in pond), 2),
        "efecto_divisa_eur": None,
        "n_exactas": len(con_eur),
    }

    sin_cambio = sum(1 for f in filas if not f["fifo"].get("exacto"))
    out["n_ventas"] = len(filas)
    out["ventas_sin_tipo_de_cambio"] = sin_cambio
    # Ventas con más acciones que compras registradas. Esas acciones salen con COSTE CERO
    # y todo su ingreso cuenta como ganancia: el total está HINCHADO exactamente en eso.
    # Pasó de verdad: al quitar los lotes duplicados de la foto, las ventas cuyas compras
    # antiguas no venían en el CSV se quedaron sin coste y el Realizado saltó de golpe.
    # Se estima cuánto sobra (ingreso de las acciones sin cubrir) para que la cifra grande
    # no se lea como buena mientras falten compras.
    descuadre_acciones, descuadre_eur, descuadre_syms, sin_tasa = 0.0, 0.0, {}, 0
    for f in filas:
        sc = f.get("sin_cubrir") or 0
        if sc <= 0:
            continue
        descuadre_acciones += sc
        ingreso = sc * float(f.get("precio_venta") or 0)
        try:
            tasa = float(f.get("tasa_venta") or 0)
        except (TypeError, ValueError):
            tasa = 0
        # Sin tasa NO se suma: meter dólares en un total de euros exagera la cifra (decía
        # 1.200 € donde eran 1.034 €). Se cuentan aparte para poder decir que faltan.
        if tasa > 0:
            descuadre_eur += ingreso / tasa
        else:
            sin_tasa += 1
        s = descuadre_syms.setdefault(f["symbol"], 0.0)
        descuadre_syms[f["symbol"]] = round(s + sc, 6)
    out["sin_cubrir_acciones"] = round(descuadre_acciones, 6)
    out["sin_cubrir_eur_aprox"] = round(descuadre_eur, 2)
    out["sin_cubrir_sin_tasa"] = sin_tasa
    out["sin_cubrir_por_symbol"] = sorted(
        ({"symbol": k, "acciones": v} for k, v in descuadre_syms.items()),
        key=lambda x: x["acciones"], reverse=True)
    out["aviso"] = (
        f"{sin_cambio} venta(s) no tienen el tipo de cambio de la compra, así que su "
        "ganancia en euros no está incluida en el total. Añade la fecha y el cambio en la "
        "compra correspondiente para incluirlas.") if sin_cambio else None
    return out


async def guardar_precio_manual(db, symbol: str, precio) -> dict:
    """Precio puesto a mano para un valor sin cotización en vivo (un ETF, otro mercado).

    Sin él la posición queda FUERA del latente y del total, y el aviso "⚠ 1 sin precio"
    no se va nunca. Con precio 0 o vacío se borra y la posición vuelve a quedar fuera.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise ValueError("Falta el símbolo.")
    try:
        precio = float(precio or 0)
    except (TypeError, ValueError):
        raise ValueError("El precio no es un número.")
    if precio <= 0:
        await db.precios_manuales.delete_one({"symbol": symbol})
        return {"symbol": symbol, "precio": None}
    await db.precios_manuales.update_one(
        {"symbol": symbol},
        {"$set": {"symbol": symbol, "precio": precio, "updated_at": _ahora()}},
        upsert=True)
    return {"symbol": symbol, "precio": precio}


async def resumen_cartera(db, precios: dict) -> dict:
    """P&L de la Cartera entera en EUROS: latente por posición + realizado.

    `precios` es {symbol: precio_actual}; lo trae el llamador, que ya los tiene de la
    watchlist, para no volver a pedirlos aquí.
    """
    import asyncio
    # Los precios manuales solo rellenan HUECOS: si el valor cotiza en vivo, manda el vivo.
    # Un precio manual de hace un mes pisando la cotización de hoy sería el error contrario
    # al que arregla.
    precios = dict(precios or {})
    manuales = set()
    for m in await db.precios_manuales.find({}, {"_id": 0}).to_list(200):
        s = (m.get("symbol") or "").upper()
        if s and precios.get(s) is None and m.get("precio"):
            precios[s] = m["precio"]
            manuales.add(s)
    compras, ventas = await _libro(db)
    gestion = await metodo_gestion(db)
    por_symbol = {}
    for op in compras + ventas:
        por_symbol.setdefault(op.get("symbol"), {"compras": [], "ventas": []})
    for c in compras:
        por_symbol[c.get("symbol")]["compras"].append(c)
    for v in ventas:
        por_symbol[v.get("symbol")]["ventas"].append(v)

    # Las fichas, para saber en qué moneda COTIZA cada valor. El coste sale de la moneda de
    # cada operación; el valor de hoy, de la del mercado donde cotiza. Son dos preguntas
    # distintas y usar la misma respuesta para las dos es lo que inventaba ganancias.
    fichas = {(e.get("symbol") or "").upper(): e for e in await db.signal_entries.find(
        {}, {"_id": 0, "symbol": 1, "mercado": 1, "divisa": 1, "isin": 1,
             "previous_close": 1, "market_state": 1, "updated_at": 1}).to_list(1000)}
    cotiza = {sym: divisa_de_cotizacion(fichas.get(sym)) for sym in por_symbol}

    # Un solo tipo de cambio por divisa para toda la cartera: pedirlo por posición sería la
    # misma llamada repetida, y encima podría dar cifras distintas dentro de la misma tabla.
    divisas = ({(op.get("divisa") or "USD") for op in compras + ventas}
               | set(cotiza.values())) or {"USD"}
    tasas = {}
    for d in divisas:
        try:
            tasas[d] = await asyncio.to_thread(fx.tasa_actual, d)
        except Exception:
            tasas[d] = None

    posiciones = []
    # El realizado se acumula AQUÍ, del mismo `reproducir` que ya hace falta para valorar.
    # Antes se sacaba llamando a historial() entero al final: una segunda lectura completa
    # de las dos colecciones y el libro reproducido otra vez por los DOS métodos, más la
    # media ponderada, para quedarse con un único float que ya estaba calculado.
    realizado_eur, hay_realizado = 0.0, False
    for sym, libro in por_symbol.items():
        estado = lotes.reproducir(libro["compras"], libro["ventas"], gestion)
        if estado["ganancia_realizada_eur"] is not None:
            realizado_eur += estado["ganancia_realizada_eur"]
            hay_realizado = True
        if estado["acciones_abiertas"] <= 1e-9:
            continue
        divisa = (libro["compras"] or libro["ventas"])[0].get("divisa", "USD")
        # Un mismo valor con lotes en dos divisas suma dólares con euros en las cifras "en
        # divisa" (el precio medio, el coste). Pasaba al teclear una compra que caía a USD y
        # luego importar la misma acción en euros desde el CSV. Se avisa en vez de enseñar
        # un número que no significa nada; las cifras en EUROS siguen bien, porque cada lote
        # se convierte con su propia tasa.
        divisas_lote = {(o.get("divisa") or divisa) for o in libro["compras"] + libro["ventas"]}
        mezcla = sorted(divisas_lote) if len(divisas_lote) > 1 else None
        # El precio de hoy viene del mercado donde cotiza, así que se convierte con el
        # cambio de ESA moneda. Antes se usaba el de la operación: con una ficha de NASDAQ
        # etiquetada "EUR", el precio en dólares se dividía entre 1 y se enseñaba como
        # euros. El coste, en cambio, sigue saliendo del cambio propio de cada lote.
        divisa_cot = cotiza.get(sym, divisa)
        val = lotes.valorar_abierto(estado, precios.get(sym), tasas.get(divisa_cot))
        pmp = lotes.media_ponderada(libro["compras"], libro["ventas"])
        posiciones.append({
            "symbol": sym, "divisa": divisa, "divisas_mezcladas": mezcla,
            # Cuando la operación dice una moneda y el mercado otra, una de las dos es una
            # errata. Se dice cuál es cada una en vez de elegir en silencio: las cifras en
            # euros ya salen bien, pero el precio medio "en divisa" mezcla peras y manzanas.
            "divisa_cotizacion": divisa_cot,
            "divisa_incoherente": divisa_cot != divisa,
            **val,
            # Para cuadrar con el bróker. Va aparte del precio_medio y etiquetado: son dos
            # medidas distintas y mezclarlas haría pensar que una de las dos está mal.
            "precio_medio_ponderado": pmp["precio_medio"],
            # La posición valorada COMO EL BRÓKER, para poder comparar fila a fila. Lo que
            # FIFO/LIFO se apuntan de más aquí ya se lo apuntaron en lo realizado: sumando
            # latente y realizado, los dos métodos dan el mismo total.
            "ponderada": lotes.valorar_ponderado(pmp, precios.get(sym), tasas.get(divisa_cot)),
            "acciones": estado["acciones_abiertas"],
            # A qué cambio se pasó a euros el coste de esta posición, y cuánto de ella no
            # viene del CSV. Es lo que explica que el latente no cuadre con el del bróker
            # teniendo el mismo precio y las mismas acciones.
            **_cambio_de_la_posicion(estado, tasas.get(divisa_cot)),
            "precio_medio": estado["precio_medio"],
            "precio_actual": precios.get(sym),
            # Etiquetado siempre: un precio puesto a mano que pareciera de mercado haría
            # creer que la posición está valorada en vivo cuando no lo está.
            "precio_manual": sym in manuales,
            # De dónde sale el "Valor hoy". Es la única cifra de la fila que no se puede
            # comprobar mirando tus apuntes, y cuando el bróker enseña otro número suele
            # ser esto y no el coste: en NFLX, 81,78 $ contra los 80,01 $ que implicaba
            # DEGIRO daban 121,80 € de diferencia, exactamente el desvío que se veía.
            # Con el cierre anterior al lado se distingue en un vistazo un precio en vivo
            # de uno que se quedó en la sesión pasada, que es de lo que suele ir la cosa.
            "cierre_anterior": (fichas.get(sym) or {}).get("previous_close"),
            "estado_mercado": (fichas.get(sym) or {}).get("market_state"),
            "precio_actualizado": (fichas.get(sym) or {}).get("updated_at"),
            # El coste se sabe siempre; el valor de hoy solo con precio. Se ponen DESPUÉS
            # de val para que no los pise cuando la posición no se puede valorar.
            "coste_divisa": estado["coste_abierto_divisa"],
            "coste_eur": estado["coste_abierto_eur"],
            "niveles_comprados": sorted({c.get("nivel") for c in libro["compras"]
                                         if c.get("nivel")}),
        })
    posiciones.sort(key=lambda p: p.get("pnl_eur") or 0, reverse=True)

    latentes = [p["pnl_eur"] for p in posiciones if p.get("pnl_eur") is not None]
    lat_pmp = [p["ponderada"]["pnl_eur"] for p in posiciones
               if (p.get("ponderada") or {}).get("pnl_eur") is not None]
    return {
        "posiciones": posiciones,
        "latente_eur": round(sum(latentes), 2) if latentes else None,
        # El mismo latente visto como lo ve el bróker. Se devuelve siempre para poder
        # enseñar las dos cifras juntas: al usuario le cuadra una u otra según con qué
        # pantalla esté comparando, y esconder una de las dos parecía un error de cálculo.
        "latente_ponderada_eur": round(sum(lat_pmp), 2) if lat_pmp else None,
        "invertido_eur": round(sum(p["coste_eur"] for p in posiciones
                                   if p.get("coste_eur") is not None), 2) or None,
        "valor_eur": round(sum(p["valor_eur"] for p in posiciones
                               if p.get("valor_eur") is not None), 2) or None,
        "realizado_eur": round(realizado_eur, 2) if hay_realizado else None,
        "metodo_gestion": gestion.lower(),
        "posiciones_sin_valorar": sum(1 for p in posiciones if p.get("pnl_eur") is None),
        # Separadas: decir "sin precio" cuando lo que falta es el tipo de cambio manda a
        # buscar el problema donde no está. Son dos averías distintas y se arreglan distinto.
        "posiciones_sin_precio": sum(
            1 for p in posiciones if p.get("precio_actual") is None),
        "posiciones_sin_tipo_de_cambio": sum(
            1 for p in posiciones
            if p.get("precio_actual") is not None and not tasas.get(p["divisa"])),
        "tasas": {d: (round(t, 4) if t else None) for d, t in tasas.items()},
        # Cuántos segundos hace que se consultó cada cambio. Sin esto, un "1 € = 1,1563 USD"
        # se lee como si fuera de ahora mismo cuando puede tener hasta una hora.
        "tasas_edad_s": {d: fx.edad_tasa_actual(d) for d in tasas},
    }


# ── Importación desde el CSV del bróker ──────────────────────────────────────

async def _mapa_isin(db) -> dict:
    """ISIN → símbolo, de lo ya emparejado en otras importaciones.

    Se guarda en su PROPIA colección y no dentro de la ficha de la acción. El motivo: un
    CSV con años de historial trae ETFs y posiciones ya cerradas que NO están en la Cartera,
    y esos no tienen ficha donde anotar nada. Guardándolo ahí, cada importación volvía a
    preguntar por ellos — que son justo los que más cuesta emparejar, porque hay que ir a
    buscar su ticker fuera.

    Se sigue leyendo también de las fichas, para no perder lo emparejado antes de esto.
    """
    mapa = {}
    for e in await db.signal_entries.find({}, {"_id": 0, "symbol": 1, "isin": 1}).to_list(500):
        if e.get("isin") and e.get("symbol"):
            mapa[str(e["isin"]).strip().upper()] = e["symbol"].upper()
    for d in await db.isin_map.find({}, {"_id": 0}).to_list(2000):
        if d.get("isin") and d.get("symbol"):
            mapa[str(d["isin"]).strip().upper()] = str(d["symbol"]).upper()
    return mapa


async def guardar_mapa_isin(db, mapeo: dict):
    """Recuerda cada decisión: el ticker elegido, y también el "ignorar".

    Lo segundo importa tanto como lo primero. Sin ello, cada importación volvería a
    preguntar por los mismos ETFs que ya se decidió dejar fuera.
    """
    for isin, valor in (mapeo or {}).items():
        limpio = _ticker_valido(valor)
        if not isin or not limpio:
            continue
        await db.isin_map.update_one(
            {"isin": isin.strip().upper()},
            {"$set": {"isin": isin.strip().upper(), "symbol": limpio,
                      "updated_at": _ahora()}},
            upsert=True)


#: Valor especial del mapeo para "este producto no me interesa, sáltalo".
#: Hace falta distinguirlo de "todavía no lo he decidido": si no, un producto que se quiere
#: dejar fuera bloquearía la importación entera para siempre.
IGNORAR = "__IGNORAR__"


def _ticker_valido(v: str) -> str:
    """Normaliza un ticker escrito a mano. Cadena vacía si no lo parece.

    Se admite escribirlo libremente y no solo elegirlo de la Cartera: un CSV con años de
    historial trae posiciones ya cerradas y valores que se dejaron de seguir, y esas ventas
    son parte de lo ganado. Obligar a tenerlas en la Cartera para poder importarlas dejaría
    fuera justo el historial que se quiere recuperar.
    """
    v = (v or "").strip().upper()
    if v == IGNORAR:
        return IGNORAR
    return v if re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", v or "") else ""


async def preparar_importacion_degiro(db, operaciones: list, mapeo: dict = None) -> dict:
    """Qué productos del fichero se sabe a qué acción corresponden y cuáles no.

    El CSV trae ISIN y nombre, no ticker. Emparejarlos una vez y RECORDARLO es lo que hace
    que la segunda importación no vuelva a preguntar: el ISIN se guarda en la Cartera.
    """
    mapa = await _mapa_isin(db)
    for k, v in (mapeo or {}).items():
        limpio = _ticker_valido(v)
        if k and limpio:
            mapa[k.strip().upper()] = limpio

    entradas = await db.signal_entries.find(
        {}, {"_id": 0, "symbol": 1, "name": 1}).to_list(500)
    conocidos = sorted({e["symbol"].upper() for e in entradas if e.get("symbol")})

    por_isin = {}
    for op in operaciones:
        d = por_isin.setdefault(op["isin"], {"isin": op["isin"], "producto": op["producto"],
                                             "operaciones": 0, "symbol": mapa.get(op["isin"])})
        d["operaciones"] += 1

    # Sugerencia por parecido del nombre. Es solo una propuesta: acertar el ticker
    # equivocado metería las operaciones en otra posición, así que lo confirma el usuario.
    for d in por_isin.values():
        if d["symbol"]:
            continue
        nombre = (d["producto"] or "").upper()
        for e in entradas:
            sym = (e.get("symbol") or "").upper()
            nom = (e.get("name") or "").upper()
            if sym and (nombre.startswith(sym) or (nom and (nom in nombre or nombre in nom))):
                d["sugerencia"] = sym
                break

    productos = sorted(por_isin.values(), key=lambda p: p["producto"])
    for p in productos:
        p["ignorado"] = p.get("symbol") == IGNORAR
        if p["ignorado"]:
            p["symbol"] = None
    return {"productos": productos,
            # Ignorado NO es pendiente: si lo fuera, un producto que se quiere dejar fuera
            # bloquearía la importación entera.
            "pendientes": [p for p in productos if not p.get("symbol") and not p["ignorado"]],
            "ignorados": [p["isin"] for p in productos if p["ignorado"]],
            "simbolos_conocidos": conocidos}


async def importar_degiro(db, operaciones: list, mapeo: dict = None,
                          actualizar: bool = False, sustituir: bool = False) -> dict:
    """Guarda las operaciones del CSV como compras y ventas del libro.

    Se salta las que ya estén (por huella), así que subir el mismo fichero dos veces —o uno
    nuevo que solape con el anterior— no duplica nada. Es la diferencia entre poder
    reexportar tranquilamente cada mes y tener que llevar la cuenta de lo ya subido.

    `actualizar` REPARA las que ya estaban. Hace falta porque saltarlas es correcto para no
    duplicar, pero deja intacto lo que se importó mal: cuando el lector no reconocía la
    columna "Tasa de cambio" —la comisión de AutoFX del CSV español— cientos de operaciones
    entraron con comisión cero, y volver a subir el fichero no las arreglaba. Se toca SOLO
    la comisión: precio, fecha y acciones se quedan como están, porque ahí no había ningún
    fallo y reescribirlos sería arriesgar datos buenos para arreglar uno malo.
    """
    # Se recuerda ANTES de comprobar si falta algo: así emparejar diez y dejarse dos no
    # tira por la borda los diez. Con un fichero de años, volver a teclearlo todo es lo que
    # hace que uno no quiera repetir la importación.
    await guardar_mapa_isin(db, mapeo)
    prep = await preparar_importacion_degiro(db, operaciones, mapeo)
    if prep["pendientes"]:
        return {**prep, "importadas": 0, "saltadas": 0,
                "aviso": "Falta decir a qué acción corresponde cada producto."}

    mapa = {p["isin"]: p["symbol"] for p in prep["productos"] if p.get("symbol")}
    # El ISIN se guarda en la Cartera: la próxima importación ya no pregunta. Solo para los
    # que estén en ella — un valor que se dejó de seguir no tiene fila que anotar, y sus
    # operaciones se guardan igual en el libro.
    for isin, sym in mapa.items():
        await db.signal_entries.update_one({"symbol": sym}, {"$set": {"isin": isin}})

    # Anti-duplicados por DOS vías, y la segunda importa más de lo que parece.
    #
    # La huella solo la llevan las operaciones que vinieron de un CSV. Las metidas a mano no
    # tienen ninguna, así que un fichero que las incluya las volvería a crear — y basta con
    # importar una vez, seguir a mano y reimportar meses después para acabar con la posición
    # duplicada sin haber hecho nada raro.
    #
    # Por eso se compara también por lo que define la operación: mismo valor, misma fecha,
    # mismo sentido, mismas acciones y precio. El precio se redondea a 4 decimales porque
    # teclearlo a mano y leerlo del fichero rara vez dan exactamente el mismo float.
    def _clave(op, tipo):
        return (str(op.get("symbol") or "").upper(), tipo, str(op.get("fecha") or "")[:10],
                round(float(op.get("acciones") or 0), 6),
                round(float(op.get("precio") or 0), 4))

    compras_db = await db.compras.find({}, {"_id": 0}).to_list(5000)
    ventas_db = await db.ventas.find({}, {"_id": 0}).to_list(5000)
    ya = {c.get("huella") for c in compras_db if c.get("huella")}
    ya |= {v.get("huella") for v in ventas_db if v.get("huella")}
    # SOLO los apuntes metidos a mano (sin huella). Este filtro existe para no duplicar lo
    # que tecleaste tú; aplicárselo también a lo que viene con huella descartaba ejecuciones
    # legítimas: DEGIRO parte una orden en varias, y dos ejecuciones de la misma orden pueden
    # ser idénticas (misma fecha, cantidad y precio — pasó con 2×5 CRWV a 90,55 el mismo
    # segundo). Entre filas del CSV ya distingue la huella, que lleva contador de repetición.
    # Un CONTEO, no un conjunto: un apunte manual debe tapar UNA fila del CSV, no todas las
    # que se le parezcan. DEGIRO parte una orden en ejecuciones idénticas, así que con un
    # set bastaba haber tecleado una para perder las demás — y esas acciones desaparecían
    # del libro. Es el mismo patrón que ya usa importar_dividendos.
    ya_manual = {}
    # Y QUIÉN la tapa, para poder sustituirla. Una fila tapada es la MISMA operación que un
    # apunte tuyo —coinciden fecha, acciones y precio al cuarto decimal— solo que la del
    # fichero trae además la comisión y el tipo de cambio que te aplicaron de verdad. Con
    # `sustituir` se borra el apunte tecleado y entra el del CSV; sin él, todo sigue igual.
    quien_tapa = {}
    for c in compras_db:
        if not c.get("huella"):
            k = _clave(c, "compra")
            ya_manual[k] = ya_manual.get(k, 0) + 1
            quien_tapa.setdefault(k, []).append(("compras", c))
    for v in ventas_db:
        if not v.get("huella"):
            k = _clave(v, "venta")
            ya_manual[k] = ya_manual.get(k, 0) + 1
            quien_tapa.setdefault(k, []).append(("ventas", v))

    # Las posiciones de la Cartera, UNA vez. Antes se consultaba una por cada compra para
    # detectar su nivel: con un fichero de años son cientos de idas y vueltas a Mongo, y la
    # importación tardaba tanto que el navegador se rendía antes de terminar.
    entradas = {e["symbol"].upper(): e for e in await db.signal_entries.find(
        {}, {"_id": 0}).to_list(500) if e.get("symbol")}

    nuevas_compras, nuevas_ventas, descartadas, reparables = [], [], [], []
    importadas, saltadas, tocados = 0, 0, set()
    # POR QUÉ se salta cada fila, no solo cuántas. "Ya estaba todo importado (443
    # operaciones)" es un dato que no se puede accionar: con él delante es imposible
    # distinguir un fichero que en efecto ya está entero de otro cuyas filas están siendo
    # tapadas por apuntes manuales —que es un problema, y bien distinto—. Se cuentan los
    # tres motivos por separado y se guarda qué símbolos toca cada uno.
    motivos = {"sin_ticker": 0, "ya_estaba": 0, "la_tapa_un_apunte_manual": 0}
    tapadas_por_symbol, sust_por_symbol, sustituidas = {}, {}, 0
    for op in sorted(operaciones, key=lambda o: (o["fecha"], o.get("hora") or "")):
        sym = mapa.get(op["isin"])
        if not sym:
            saltadas += 1
            motivos["sin_ticker"] += 1
            continue
        if op["huella"] in ya:
            saltadas += 1
            motivos["ya_estaba"] += 1
            if actualizar:
                reparables.append(op)
            continue
        km = _clave({**op, "symbol": sym}, op["tipo"])
        if ya_manual.get(km, 0) > 0:
            ya_manual[km] -= 1      # esta fila la cubre UN apunte manual, no todas
            if sustituir and quien_tapa.get(km):
                # Se borra el apunte tecleado y se deja pasar la fila: misma operación, con
                # la comisión y el cambio reales en vez de estimados. Sin esto la fila no
                # entraba nunca, y encima bloqueaba el borrado de los lotes de la foto —el
                # CSV "no cubría" unas acciones que sí estaban en el fichero.
                col, doc = quien_tapa[km].pop()
                await getattr(db, col).delete_one({"id": doc.get("id")})
                sustituidas += 1
                sust_por_symbol.setdefault(sym, {"symbol": sym, "apuntes": 0, "acciones": 0})
                sust_por_symbol[sym]["apuntes"] += 1
                sust_por_symbol[sym]["acciones"] = round(
                    sust_por_symbol[sym]["acciones"] + (op.get("acciones") or 0), 6)
                tocados.add(sym)
            else:
                saltadas += 1
                motivos["la_tapa_un_apunte_manual"] += 1
                d = tapadas_por_symbol.setdefault(sym, {"symbol": sym, "filas": 0,
                                                        "acciones": 0})
                d["filas"] += 1
                d["acciones"] = round(d["acciones"] + (op.get("acciones") or 0), 6)
                continue
        comun = dict(symbol=sym, acciones=op["acciones"], precio=op["precio"],
                     fecha=op["fecha"], comision=op["comision"], divisa=op["divisa"],
                     tasa=op["tasa"], notas=f"DEGIRO · orden {op.get('orden') or '—'}")
        try:
            if op["tipo"] == "compra":
                doc = lotes.nueva_compra(**comun)
                det = lotes.detectar_nivel(op["precio"], entradas.get(sym) or {})
                doc.update({"nivel": det.get("nivel"),
                            "nivel_etiqueta": det.get("nivel_etiqueta")})
                doc["huella"] = op["huella"]
                nuevas_compras.append(doc)
            else:
                doc = lotes.nueva_venta(**comun)
                doc["huella"] = op["huella"]
                nuevas_ventas.append(doc)
            importadas += 1
            tocados.add(sym)
            ya.add(op["huella"])
        except ValueError as e:
            # A la lista, no solo al log: una compra descartada aquí es una venta futura
            # SIN COSTE — su ganancia saldrá hinchada — y desde el log del servidor nadie
            # se entera. Pasó con OHLA y CRWV: filas a precio 0 (ampliaciones, splits)
            # descartadas en silencio y 205 acciones vendidas "sin compra registrada".
            logger.warning("Operación descartada (%s %s): %s", op["fecha"], sym, e)
            descartadas.append({"symbol": sym, "fecha": op["fecha"], "tipo": op["tipo"],
                                "acciones": op["acciones"], "precio": op["precio"],
                                "motivo": str(e)})
            saltadas += 1

    # Una escritura por colección en vez de una por operación. Con cientos de apuntes la
    # diferencia no es de milisegundos: es que termine o que el navegador se canse.
    if nuevas_compras:
        await db.compras.insert_many(nuevas_compras)
    if nuevas_ventas:
        await db.ventas.insert_many(nuevas_ventas)

    # Reparación de las que ya estaban: solo la comisión, y solo si CAMBIA. Escribir por
    # escribir dejaría un `updated_at` nuevo en cientos de apuntes intactos y haría
    # imposible ver, mirando la base de datos, qué tocó de verdad esta importación.
    actualizadas, comision_recuperada = 0, 0.0
    por_huella = {}
    if reparables:
        for col, docs in (("compras", compras_db), ("ventas", ventas_db)):
            for d in docs:
                if d.get("huella"):
                    por_huella[d["huella"]] = (col, d)
    for op in reparables:
        destino = por_huella.get(op["huella"])
        if not destino:
            continue
        col, doc = destino
        nueva = round(float(op.get("comision") or 0), 4)
        vieja = round(float(doc.get("comision") or 0), 4)
        if abs(nueva - vieja) < 0.005:
            continue
        # `getattr` y no `db[col]`: todo el módulo accede a las colecciones por
        # atributo, y el doble de Mongo de los tests solo implementa esa forma.
        await getattr(db, col).update_one({"id": doc["id"]},
                                          {"$set": {"comision": nueva}})
        actualizadas += 1
        comision_recuperada += nueva - vieja
        tocados.add((doc.get("symbol") or "").upper())

    await _sincronizar_varias(db, tocados)

    return {**prep, "importadas": importadas, "saltadas": saltadas,
            "motivos_salto": motivos,
            # Los símbolos cuyas filas del CSV están siendo tapadas por apuntes tuyos. Es la
            # lista que hace falta para decidir: esas compras del fichero —con su fecha, su
            # precio y su comisión reales— NO están en el libro, y no entrarán mientras el
            # apunte que las tapa siga ahí.
            "tapadas_por_symbol": sorted(tapadas_por_symbol.values(),
                                         key=lambda d: -d["acciones"]),
            "sustituidas": sustituidas,
            "sustituidas_por_symbol": sorted(sust_por_symbol.values(),
                                             key=lambda d: -d["acciones"]),
            # Se devuelve si se PIDIÓ reparar, no solo cuántas se repararon. Sin esto el
            # cliente no puede distinguir "no lo pediste" de "no había nada que corregir",
            # y las dos acaban en el mismo mensaje: "ya estaba todo importado".
            "actualizar_pedido": bool(actualizar),
            "actualizadas": actualizadas,
            "comision_recuperada": round(comision_recuperada, 2) if actualizadas else None,
            "descartadas": descartadas, "simbolos": sorted(tocados)}


async def quitar_lotes_de_la_foto(db) -> dict:
    """Borra los lotes de "Importar mis posiciones" en los símbolos que ya están en el CSV.

    Las dos importaciones cuentan LAS MISMAS acciones: la foto de la Cartera es tu posición
    en un momento dado, y el CSV de DEGIRO es la historia completa que desemboca en esa misma
    posición. Con ambas en el libro, cada posición sale al doble — pasó de verdad: 24 RDDT en
    pantalla con 12 en el bróker. El CSV es la versión buena (trae fechas y precios reales,
    no un reparto estimado), así que lo que sobra es la foto.

    Solo se toca un símbolo si tiene apuntes con huella (es decir, si el CSV lo cubre): una
    posición que nunca vino en ningún fichero se queda exactamente como está.

    Y solo si el CSV cubre AL MENOS las mismas acciones que la foto. La exportación de
    DEGIRO se descarga por rango de fechas: un fichero de este año no trae las compras de
    años anteriores. Bastaba una compra reciente para dar el símbolo por cubierto y borrar
    la foto entera — 24 RDDT se quedaban en 4. Los símbolos a medias se informan en
    `insuficientes` para poder subir el CSV completo antes de tocar nada.
    """
    compras = await db.compras.find({}, {"_id": 0}).to_list(5000)
    ventas = await db.ventas.find({}, {"_id": 0}).to_list(5000)
    con_csv = ({c["symbol"] for c in compras if c.get("huella")}
               | {v["symbol"] for v in ventas if v.get("huella")})

    def _acciones(ops, con_huella):
        t = {}
        for o in ops:
            if bool(o.get("huella")) is con_huella:
                t[o["symbol"]] = round(t.get(o["symbol"], 0) + (o.get("acciones") or 0), 6)
        return t

    del_csv = _acciones(compras, True)
    de_foto = {s: n for s, n in _acciones(compras, False).items() if s in con_csv}
    insuficientes = [{"symbol": s, "en_el_csv": del_csv.get(s, 0), "en_la_foto": n}
                     for s, n in sorted(de_foto.items())
                     if del_csv.get(s, 0) + 1e-9 < n]
    a_medias = {x["symbol"] for x in insuficientes}

    borrados, detalle = 0, {}
    for c in compras:
        if (c["symbol"] in con_csv and c["symbol"] not in a_medias
                and not c.get("huella")
                and str(c.get("notas") or "").startswith("Importada de tu Cartera")):
            await db.compras.delete_one({"id": c["id"]})
            borrados += 1
            d = detalle.setdefault(c["symbol"], {"lotes": 0, "acciones": 0})
            d["lotes"] += 1
            d["acciones"] = round(d["acciones"] + (c.get("acciones") or 0), 6)
    await _sincronizar_varias(db, set(detalle))
    return {"borrados": borrados,
            "detalle": sorted(({"symbol": k, **v} for k, v in detalle.items()),
                              key=lambda x: x["symbol"]),
            "insuficientes": insuficientes,
            "simbolos": sorted(detalle)}


# ── Dividendos ───────────────────────────────────────────────────────────────

async def importar_dividendos(db, dividendos: list, mapeo: dict = None) -> dict:
    """Guarda los dividendos del Account.csv.

    Van en su PROPIA colección y no como una venta rara: fiscalmente son rendimientos del
    capital mobiliario, no ganancias patrimoniales, y en la declaración van a casillas
    distintas. Sumarlos a lo realizado por ventas daría un total que no sirve para nada
    oficial.

    Un dividendo de un valor que no está en la Cartera se guarda igual, con el ISIN por
    nombre: es dinero cobrado, y perderlo por no tener ficha sería absurdo.
    """
    mapa = await _mapa_isin(db)
    for k, v in (mapeo or {}).items():
        limpio = _ticker_valido(v)
        if k and limpio and limpio != IGNORAR:
            mapa[k.strip().upper()] = limpio

    # Anti-duplicados por CONTEO, no por huella.
    #
    # La huella funciona mientras su forma no cambie, y ya cambió una vez (hubo que añadirle
    # un contador para no perder dos apuntes idénticos el mismo día). Un método que se rompe
    # al arreglar otra cosa no sirve para algo que se va a reimportar cada pocos meses.
    #
    # Aquí se cuenta: de cada apunte idéntico —misma fecha, valor, tipo, importe y divisa—
    # se mira cuántos hay ya guardados y cuántos trae el fichero, y solo entra la
    # diferencia. Funciona reimportando, con ficheros que se solapan y con pagos repetidos.
    def _clave(d):
        return (str(d.get("fecha") or "")[:10], str(d.get("isin") or "").upper(),
                d.get("tipo"), round(float(d.get("importe") or 0), 4),
                str(d.get("divisa") or "").upper())

    guardados = {}
    for d in await db.dividendos.find({}, {"_id": 0}).to_list(5000):
        guardados[_clave(d)] = guardados.get(_clave(d), 0) + 1

    nuevos, saltados = [], 0
    for d in dividendos:
        k = _clave(d)
        if guardados.get(k, 0) > 0:
            guardados[k] -= 1
            saltados += 1
            continue
        tasa = d.get("tasa")
        if not tasa or float(tasa) <= 0:
            tasa = 1.0 if d["divisa"] == "EUR" else await _tasa(d["divisa"], d["fecha"])
        importe_eur = None
        if tasa and float(tasa) > 0:
            importe_eur = round(float(d["importe"]) / float(tasa), 2)
        nuevos.append({**d,
                       # `id` propio, como las compras y las ventas. Sin él todos los
                       # apuntes entraban con id nulo y el índice único de Mongo los
                       # rechazaba a partir del segundo: la importación fallaba entera.
                       "id": str(uuid.uuid4()),
                       "symbol": mapa.get(d["isin"]) or d["isin"],
                       "tasa": tasa, "importe_eur": importe_eur,
                       "created_at": _ahora()})

    if nuevos:
        await db.dividendos.insert_many(nuevos)
    return {"importados": len(nuevos), "saltados": saltados}


async def resumen_dividendos(db) -> dict:
    """Lo cobrado por dividendos, en euros, con la retención aparte.

    Se separan a propósito: la retención en origen de EE.UU. es recuperable en parte con el
    convenio de doble imposición, así que verla suelta no es un detalle contable — es dinero
    que puede volver.
    """
    docs = await db.dividendos.find({}, {"_id": 0}).to_list(5000)
    brutos = [d for d in docs if d["tipo"] == "dividendo"]
    retenciones = [d for d in docs if d["tipo"] == "retencion"]
    # Intereses del saldo en negativo y conectividad con mercados. Se enseñan aparte de los
    # dividendos —son la otra cara: dinero que se va, no que llega— y son lo que separa el
    # total propio del Total P/L del bróker, que sí los descuenta.
    costes = [d for d in docs if d["tipo"] == "coste"]

    def _suma(lista):
        vals = [d["importe_eur"] for d in lista if d.get("importe_eur") is not None]
        return round(sum(vals), 2) if vals else None

    por_symbol = {}
    for d in docs:
        if d.get("importe_eur") is None or d["tipo"] == "coste":
            continue
        sym = d.get("symbol") or d.get("isin")
        por_symbol[sym] = round(por_symbol.get(sym, 0) + d["importe_eur"], 2)

    bruto, retenido = _suma(brutos), _suma(retenciones)
    return {
        "bruto_eur": bruto,
        "retenido_eur": retenido,
        "neto_eur": (round((bruto or 0) + (retenido or 0), 2)
                     if bruto is not None else None),
        "n_cobros": len(brutos),
        # Los intereses llegan en negativo en el fichero y se respeta el signo: sumarlos al
        # total ya los resta, sin acordarse de cambiar signos por el camino.
        "costes_eur": _suma(costes),
        "n_costes": len(costes),
        "por_symbol": sorted(({"symbol": k, "eur": v} for k, v in por_symbol.items()),
                             key=lambda x: x["eur"], reverse=True),
        "sin_convertir": sum(1 for d in docs if d.get("importe_eur") is None),
    }


# ── Migración desde el modelo viejo ──────────────────────────────────────────

async def importar_posiciones_existentes(db, reemplazar: bool = False) -> dict:
    """Crea un lote inicial por cada posición de la Cartera que aún no tenga compras.

    Sin esto, estrenar el libro dejaría todas las posiciones a cero y parecería que se han
    borrado. Se salta las que ya tienen apuntes para poder llamarlo dos veces sin duplicar.
    """
    creados, saltados, detalle = 0, 0, []
    entries = await db.signal_entries.find(
        {"acciones": {"$gt": 0}}, {"_id": 0}).to_list(1000)
    for e in entries:
        sym = (e.get("symbol") or "").strip().upper()
        if not sym or not e.get("compra"):
            saltados += 1
            continue
        if await db.compras.find_one({"symbol": sym}, {"_id": 0}):
            # Rehacer la importación tiene sentido cuando la primera salió mal (un reparto
            # que no cuadraba, o niveles mal marcados) y borrar los lotes a mano son decenas
            # de clics. Pero NO se toca nada si el símbolo ya tiene ventas registradas:
            # borrar sus compras dejaría esas ventas sin coste y su ganancia sería falsa.
            if not reemplazar or await db.ventas.find_one({"symbol": sym}, {"_id": 0}):
                saltados += 1
                continue
            suyas = await db.compras.find({"symbol": sym}, {"_id": 0}).to_list(1000)
            # NUNCA se borran compras que vinieron del CSV: son la versión buena (fechas,
            # precios y tasas reales) y la foto que las sustituiría es de la primera
            # importación y no se actualiza nunca. Rehacer sobre un símbolo ya importado
            # convertía 12 acciones correctas en un único lote de 24 al precio medio de hace
            # meses. Solo se rehace lo que la propia foto creó.
            if any(c.get("huella") for c in suyas):
                saltados += 1
                continue
            for c in suyas:
                await db.compras.delete_one({"id": c["id"]})
        # Las campanitas apagadas dicen EN QUÉ NIVELES se compró, así que en vez de un
        # único lote al precio medio se reconstruyen los lotes de verdad. Ver
        # lotes.plan_importacion: con uno o dos niveles el reparto es exacto.
        # De dónde salen `acciones` y `compra` para repartir. NO se leen de la Cartera tal
        # cual: _sincronizar_posicion ESCRIBE en esos mismos campos el resultado de la
        # importación, así que una segunda importación leería su propia salida y reproduciría
        # el reparto anterior en vez de corregirlo. Pasó de verdad: una posición se quedó
        # clavada en 166,20 $ cuando lo que se había tecleado era 142,43 $.
        #
        # Por eso se guarda una foto de los valores ORIGINALES la primera vez y se usa
        # siempre esa. Es el único registro de lo que tecleaste antes de que nada derivado
        # lo pisara.
        origen = e.get("import_origen")
        if not origen:
            origen = {"acciones": e.get("acciones"), "compra": e.get("compra")}
            await db.signal_entries.update_one(
                {"symbol": sym}, {"$set": {"import_origen": origen}})
        plan = lotes.plan_importacion({**e, **origen})
        fecha = (str(e.get("fecha_compra"))[:10] if e.get("fecha_compra") else None)
        nota_base = ("Importada de tu Cartera"
                     if plan["exacto"] else
                     "Importada de tu Cartera — REPARTO ESTIMADO, revísalo")
        try:
            for lote in plan["lotes"]:
                if lote["acciones"] <= 0:
                    continue
                await registrar_compra(
                    db, sym, lote["acciones"], lote["precio"], fecha=fecha,
                    divisa=e.get("divisa"), nivel=lote.get("nivel"),
                    # comision=0 y NO estimada: el precio medio del que sale esta
                    # importación ya incluye lo que pagaste en su día. Estimarla encima la
                    # cobraría dos veces e inflaría el coste de toda la posición.
                    comision=0,
                    notas=f"{nota_base}. {plan['motivo']}")
            creados += 1
            detalle.append({"symbol": sym, "lotes": len(plan["lotes"]),
                            "exacto": plan["exacto"], "motivo": plan["motivo"]})
        except Exception as exc:
            logger.warning("No se pudo importar %s: %s", sym, exc)
            saltados += 1
    return {"creados": creados, "saltados": saltados, "detalle": detalle,
            "estimados": [d["symbol"] for d in detalle if not d["exacto"]]}
