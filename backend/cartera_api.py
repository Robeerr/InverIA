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

async def registrar_compra(db, symbol: str, acciones: float, precio: float,
                           fecha: str = None, comision: float = None,
                           divisa: str = None, tasa: float = None,
                           nivel: str = None, notas: str = "") -> dict:
    """Guarda una compra. Detecta sola en qué nivel de la Cartera se hizo."""
    symbol = (symbol or "").strip().upper()
    entry = await db.signal_entries.find_one({"symbol": symbol}, {"_id": 0})
    divisa = (divisa or (entry or {}).get("divisa") or "USD").strip().upper() or "USD"

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


async def borrar_compra(db, compra_id: str) -> bool:
    doc = await db.compras.find_one({"id": compra_id}, {"_id": 0})
    r = await db.compras.delete_one({"id": compra_id})
    if r.deleted_count and doc:
        await _sincronizar_posicion(db, doc.get("symbol"))
    return r.deleted_count > 0


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
    divisa = (divisa or (entry or {}).get("divisa") or "USD").strip().upper() or "USD"

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
    }


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

    return {
        "posibles_duplicadas": dudosas,
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
    sin_cambio = sum(1 for f in filas if not f["fifo"].get("exacto"))
    out["n_ventas"] = len(filas)
    out["ventas_sin_tipo_de_cambio"] = sin_cambio
    # Ventas con más acciones que compras registradas. Esas acciones salen con COSTE CERO
    # y todo su ingreso cuenta como ganancia: el total está HINCHADO exactamente en eso.
    # Pasó de verdad: al quitar los lotes duplicados de la foto, las ventas cuyas compras
    # antiguas no venían en el CSV se quedaron sin coste y el Realizado saltó de golpe.
    # Se estima cuánto sobra (ingreso de las acciones sin cubrir) para que la cifra grande
    # no se lea como buena mientras falten compras.
    descuadre_acciones, descuadre_eur, descuadre_syms = 0.0, 0.0, {}
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
        descuadre_eur += (ingreso / tasa) if tasa > 0 else ingreso
        s = descuadre_syms.setdefault(f["symbol"], 0.0)
        descuadre_syms[f["symbol"]] = round(s + sc, 6)
    out["sin_cubrir_acciones"] = round(descuadre_acciones, 6)
    out["sin_cubrir_eur_aprox"] = round(descuadre_eur, 2)
    out["sin_cubrir_por_symbol"] = sorted(
        ({"symbol": k, "acciones": v} for k, v in descuadre_syms.items()),
        key=lambda x: x["acciones"], reverse=True)
    out["aviso"] = (
        f"{sin_cambio} venta(s) no tienen el tipo de cambio de la compra, así que su "
        "ganancia en euros no está incluida en el total. Añade la fecha y el cambio en la "
        "compra correspondiente para incluirlas.") if sin_cambio else None
    return out


async def resumen_cartera(db, precios: dict) -> dict:
    """P&L de la Cartera entera en EUROS: latente por posición + realizado.

    `precios` es {symbol: precio_actual}; lo trae el llamador, que ya los tiene de la
    watchlist, para no volver a pedirlos aquí.
    """
    import asyncio
    compras, ventas = await _libro(db)
    gestion = await metodo_gestion(db)
    por_symbol = {}
    for op in compras + ventas:
        por_symbol.setdefault(op.get("symbol"), {"compras": [], "ventas": []})
    for c in compras:
        por_symbol[c.get("symbol")]["compras"].append(c)
    for v in ventas:
        por_symbol[v.get("symbol")]["ventas"].append(v)

    # Un solo tipo de cambio por divisa para toda la cartera: pedirlo por posición sería la
    # misma llamada repetida, y encima podría dar cifras distintas dentro de la misma tabla.
    divisas = {(op.get("divisa") or "USD") for op in compras + ventas} or {"USD"}
    tasas = {}
    for d in divisas:
        try:
            tasas[d] = await asyncio.to_thread(fx.tasa_actual, d)
        except Exception:
            tasas[d] = None

    posiciones = []
    for sym, libro in por_symbol.items():
        estado = lotes.reproducir(libro["compras"], libro["ventas"], gestion)
        if estado["acciones_abiertas"] <= 1e-9:
            continue
        divisa = (libro["compras"] or libro["ventas"])[0].get("divisa", "USD")
        val = lotes.valorar_abierto(estado, precios.get(sym), tasas.get(divisa))
        pmp = lotes.media_ponderada(libro["compras"], libro["ventas"])
        posiciones.append({
            "symbol": sym, "divisa": divisa,
            **val,
            # Para cuadrar con el bróker. Va aparte del precio_medio y etiquetado: son dos
            # medidas distintas y mezclarlas haría pensar que una de las dos está mal.
            "precio_medio_ponderado": pmp["precio_medio"],
            "acciones": estado["acciones_abiertas"],
            "precio_medio": estado["precio_medio"],
            "precio_actual": precios.get(sym),
            # El coste se sabe siempre; el valor de hoy solo con precio. Se ponen DESPUÉS
            # de val para que no los pise cuando la posición no se puede valorar.
            "coste_divisa": estado["coste_abierto_divisa"],
            "coste_eur": estado["coste_abierto_eur"],
            "niveles_comprados": sorted({c.get("nivel") for c in libro["compras"]
                                         if c.get("nivel")}),
        })
    posiciones.sort(key=lambda p: p.get("pnl_eur") or 0, reverse=True)

    latentes = [p["pnl_eur"] for p in posiciones if p.get("pnl_eur") is not None]
    hist = await historial(db)
    return {
        "posiciones": posiciones,
        "latente_eur": round(sum(latentes), 2) if latentes else None,
        "invertido_eur": round(sum(p["coste_eur"] for p in posiciones
                                   if p.get("coste_eur") is not None), 2) or None,
        "valor_eur": round(sum(p["valor_eur"] for p in posiciones
                               if p.get("valor_eur") is not None), 2) or None,
        "realizado_eur": hist["resumen"][gestion.lower()]["ganancia_eur"],
        "metodo_gestion": gestion.lower(),
        "posiciones_sin_valorar": sum(1 for p in posiciones if p.get("pnl_eur") is None),
        "tasas": {d: (round(t, 4) if t else None) for d, t in tasas.items()},
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


async def importar_degiro(db, operaciones: list, mapeo: dict = None) -> dict:
    """Guarda las operaciones del CSV como compras y ventas del libro.

    Se salta las que ya estén (por huella), así que subir el mismo fichero dos veces —o uno
    nuevo que solape con el anterior— no duplica nada. Es la diferencia entre poder
    reexportar tranquilamente cada mes y tener que llevar la cuenta de lo ya subido.
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
    ya_manual = ({_clave(c, "compra") for c in compras_db if not c.get("huella")}
                 | {_clave(v, "venta") for v in ventas_db if not v.get("huella")})

    # Las posiciones de la Cartera, UNA vez. Antes se consultaba una por cada compra para
    # detectar su nivel: con un fichero de años son cientos de idas y vueltas a Mongo, y la
    # importación tardaba tanto que el navegador se rendía antes de terminar.
    entradas = {e["symbol"].upper(): e for e in await db.signal_entries.find(
        {}, {"_id": 0}).to_list(500) if e.get("symbol")}

    nuevas_compras, nuevas_ventas, descartadas = [], [], []
    importadas, saltadas, tocados = 0, 0, set()
    for op in sorted(operaciones, key=lambda o: (o["fecha"], o.get("hora") or "")):
        sym = mapa.get(op["isin"])
        if not sym:
            saltadas += 1
            continue
        if op["huella"] in ya or _clave({**op, "symbol": sym}, op["tipo"]) in ya_manual:
            saltadas += 1
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

    await _sincronizar_varias(db, tocados)

    return {**prep, "importadas": importadas, "saltadas": saltadas,
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
    """
    compras = await db.compras.find({}, {"_id": 0}).to_list(5000)
    ventas = await db.ventas.find({}, {"_id": 0}).to_list(5000)
    con_csv = ({c["symbol"] for c in compras if c.get("huella")}
               | {v["symbol"] for v in ventas if v.get("huella")})
    borrados, detalle = 0, {}
    for c in compras:
        if (c["symbol"] in con_csv and not c.get("huella")
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
            for c in await db.compras.find({"symbol": sym}, {"_id": 0}).to_list(1000):
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
