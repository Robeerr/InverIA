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
    for sym in simbolos:
        await _sincronizar_posicion(db, sym, metodo=metodo)
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
    # METODO_GESTION (LIFO), no el fiscal: qué lotes quedan vivos —y por tanto qué
    # campanitas y qué precio medio— depende del método, y aquí la pregunta es cómo llevas
    # tú la posición. Vendiendo por niveles según cae el precio, lo que se vende es lo más
    # reciente; con FIFO las campanitas se encenderían por el extremo contrario.
    # El número total de acciones sale igual con los dos.
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
    if entry:
        cambios.update(lotes.estado_niveles(entry, compras, estado["abiertos"]))

    await db.signal_entries.update_one({"symbol": symbol}, {"$set": cambios})
    return estado


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

    # Nivel: si no se indica a mano, se deduce del precio contra los niveles de la Cartera.
    if not compra["nivel"] and entry:
        det = lotes.detectar_nivel(compra["precio"], entry)
        compra["nivel"] = det.get("nivel")
        compra["nivel_etiqueta"] = det.get("nivel_etiqueta")
        compra["precio_nivel"] = det.get("precio_nivel")
        compra["desvio_nivel_pct"] = det.get("desvio_pct")

    await db.compras.insert_one(dict(compra))
    await _sincronizar_posicion(db, symbol)
    return compra


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
    await _sincronizar_posicion(db, symbol)
    return await estado_simbolo(db, symbol)


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
        for vf, vl in zip(comp["fifo"]["ventas"], comp["lifo"]["ventas"]):
            filas.append({
                "id": vf.get("id"), "symbol": sym, "fecha": vf.get("fecha"),
                "acciones": vf.get("acciones"), "precio_venta": vf.get("precio_venta"),
                "divisa": vf.get("divisa"), "comision_venta": vf.get("comision_venta"),
                "notas": vf.get("notas") or "",
                "fifo": _fila_metodo(vf),
                "lifo": _fila_metodo(vl),
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
    return {
        "items": filas[:limite],
        "por_symbol": resumen_symbol,
        "resumen": _totales(filas),
        "metodo_gestion": gestion,
        "nota_fiscal": lotes.comparar_metodos([], [])["nota_fiscal"],
    }


def _fila_metodo(v: dict) -> dict:
    return {
        "coste_divisa": v.get("coste_divisa"), "coste_eur": v.get("coste_eur"),
        "ganancia_divisa": v.get("ganancia_divisa"), "ganancia_eur": v.get("ganancia_eur"),
        "pct": v.get("pct"), "pct_eur": v.get("pct_eur"),
        "efecto_divisa_eur": v.get("efecto_divisa_eur"),
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
        posiciones.append({
            "symbol": sym, "divisa": divisa,
            **val,
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
        plan = lotes.plan_importacion(e)
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
