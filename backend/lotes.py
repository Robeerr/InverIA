"""Libro de operaciones: compras por lotes, ventas emparejadas y ganancia REALIZADA.

Por qué un libro y no un saldo
------------------------------
Lo que había antes guardaba en la posición un precio medio y un número de acciones, y al
vender restaba. Eso no puede contestar a lo que de verdad se pregunta uno: "estas 3 que me
quedan, ¿de qué compra son?", "esta venta, ¿sobre qué coste?". Y en cuanto compras más
después de haber vendido, el precio medio cambia y recalcular una venta vieja con el precio
medio nuevo da una ganancia que nunca ocurrió.

Aquí las compras y las ventas se guardan tal como ocurrieron y NO se tocan. Todo lo demás
—lo que queda abierto, lo ganado, el precio medio— se deriva reproduciendo el libro. Eso
hace que corregir un error sea editar un apunte, no descuadrar la posición para siempre.

FIFO y LIFO
-----------
Se calculan LOS DOS sobre las mismas operaciones, porque contestan a preguntas distintas:

  · FIFO ("lo primero que compré es lo primero que vendo") es OBLIGATORIO en España para
    acciones cotizadas — artículo 37.2 de la Ley del IRPF. Es la cifra que va a la
    declaración y la que cuadra con lo que Hacienda considera tu ganancia. El coste medio
    ponderado, que usan casi todos los brókeres anglosajones, NO está admitido.

  · LIFO ("he vendido las últimas que compré") es como suele pensarlo uno cuando va
    promediando a la baja. Es útil para juzgar la operación, pero no vale para la renta.

Pueden diferir muchísimo: con 3 acciones a 80 $ y 2 a 120 $, vender 1 a 130 $ da +50 $ por
FIFO y +10 $ por LIFO. Por eso se muestran las dos etiquetadas, y nunca un número a secas.

Los euros
---------
Cada lote se convierte a euros al cambio de SU fecha, y lo ingresado al cambio del día de la
venta. Convertir el beneficio en dólares al cambio de hoy daría un número que no corresponde
a ninguna operación real: si compras a 1,05 y vendes a 1,15 USD/EUR, cada dólar que
recuperas vale menos euros que los que pusiste, y puedes ganar en dólares y perder en euros.

Las comisiones
--------------
Suman al coste en la compra y restan de lo ingresado en la venta, que es como se calcula la
ganancia patrimonial de verdad. Van por operación porque en DeGiro no son fijas: dependen
del mercado y del producto.
"""
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FIFO = "FIFO"
LIFO = "LIFO"
METODOS = (FIFO, LIFO)

#: Tolerancia para dar por bueno que una compra se hizo "en" un nivel de la Cartera.
#: 1,5% cubre el hueco normal entre la orden y la ejecución sin llegar a atribuir a un nivel
#: una compra que se hizo claramente en otro sitio.
TOLERANCIA_NIVEL = 0.015


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hoy() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ── Un lote de compra ────────────────────────────────────────────────────────

def coste_lote(precio: float, acciones: float, comision: float = 0.0) -> float:
    """Lo que te costó de verdad, comisión incluida."""
    return acciones * precio + (comision or 0.0)


def detectar_nivel(precio: float, entry: dict) -> dict:
    """A qué nivel de la Cartera corresponde una compra hecha a `precio`.

    Devuelve {"nivel": "nivel3", "precio_nivel": 180.0, "desvio_pct": -0.4} o
    {"nivel": None} si no cae cerca de ninguno.

    Se elige el nivel MÁS CERCANO dentro de la tolerancia, no el primero que cumpla: con
    niveles juntos (180 y 178) el primero que cumpla puede no ser el que tocó.
    """
    if not entry or precio is None:
        return {"nivel": None}
    try:
        precio = float(precio)
    except (TypeError, ValueError):
        return {"nivel": None}
    if precio <= 0:
        return {"nivel": None}

    mejor = None
    candidatos = [(f"nivel{i}", f"Nivel {i}") for i in range(1, 6)]
    candidatos.append(("deseado", "Deseado"))
    for clave, etiqueta in candidatos:
        v = entry.get(clave)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        desvio = (precio - v) / v
        if abs(desvio) <= TOLERANCIA_NIVEL and (mejor is None or abs(desvio) < abs(mejor[2])):
            mejor = (clave, etiqueta, desvio, v)
    if mejor is None:
        return {"nivel": None}
    return {"nivel": mejor[0], "nivel_etiqueta": mejor[1],
            "precio_nivel": round(mejor[3], 4),
            "desvio_pct": round(mejor[2] * 100, 2)}


def nueva_compra(symbol: str, acciones: float, precio: float, fecha: str = None,
                 comision: float = 0.0, divisa: str = "USD", tasa: float = None,
                 nivel: str = None, notas: str = "") -> dict:
    """Construye el apunte de una compra. No toca la base de datos."""
    acciones = float(acciones)
    precio = float(precio)
    if acciones <= 0:
        raise ValueError("El número de acciones debe ser mayor que cero.")
    if precio <= 0:
        raise ValueError("El precio de compra debe ser mayor que cero.")
    comision = float(comision or 0.0)
    if comision < 0:
        raise ValueError("La comisión no puede ser negativa.")
    return {
        "id": str(uuid.uuid4()),
        "tipo": "compra",
        "symbol": (symbol or "").strip().upper(),
        "fecha": (fecha or _hoy())[:10],
        "acciones": acciones,
        "precio": precio,
        "comision": comision,
        "divisa": (divisa or "USD").strip().upper() or "USD",
        "tasa": tasa,           # divisa por 1 EUR el día de la compra
        "nivel": nivel,         # "nivel3", "deseado"… o None si fue fuera de niveles
        "notas": notas or "",
        "created_at": _ahora(),
    }


def nueva_venta(symbol: str, acciones: float, precio: float, fecha: str = None,
                comision: float = 0.0, divisa: str = "USD", tasa: float = None,
                notas: str = "") -> dict:
    acciones = float(acciones)
    precio = float(precio)
    if acciones <= 0:
        raise ValueError("El número de acciones vendidas debe ser mayor que cero.")
    if precio <= 0:
        raise ValueError("El precio de venta debe ser mayor que cero.")
    comision = float(comision or 0.0)
    if comision < 0:
        raise ValueError("La comisión no puede ser negativa.")
    return {
        "id": str(uuid.uuid4()),
        "tipo": "venta",
        "symbol": (symbol or "").strip().upper(),
        "fecha": (fecha or _hoy())[:10],
        "acciones": acciones,
        "precio": precio,
        "comision": comision,
        "divisa": (divisa or "USD").strip().upper() or "USD",
        "tasa": tasa,
        "notas": notas or "",
        "created_at": _ahora(),
    }


# ── El emparejamiento ────────────────────────────────────────────────────────

def _orden(compras: list, metodo: str) -> list:
    """Compras en el orden en que se consumen.

    Se desempata por created_at: dos compras del MISMO día en un orden arbitrario darían
    resultados distintos entre ejecuciones, y una cifra que baila no vale para nada.
    """
    clave = lambda c: (str(c.get("fecha") or ""), str(c.get("created_at") or ""))  # noqa: E731
    orden = sorted(compras, key=clave)
    return orden if metodo == FIFO else list(reversed(orden))


def emparejar(compras: list, cantidad: float, metodo: str = FIFO) -> tuple:
    """Reparte `cantidad` acciones vendidas entre los lotes disponibles.

    Devuelve (consumos, sin_cubrir). `sin_cubrir` > 0 significa que se están vendiendo más
    acciones de las que constan compradas: se informa en vez de fallar, porque puede ser
    simplemente que falte meter una compra antigua, y es mejor enseñar el descuadre que
    negarse a registrar la venta.

    Los lotes NO se modifican: se devuelve cuánto se toma de cada uno.
    """
    restante = float(cantidad)
    consumos = []
    for c in _orden(compras, metodo):
        libres = float(c.get("_libres", c.get("acciones") or 0))
        if libres <= 1e-9 or restante <= 1e-9:
            continue
        toma = min(libres, restante)
        restante -= toma
        acciones_lote = float(c.get("acciones") or 0) or 1.0
        comision_prorrateada = float(c.get("comision") or 0.0) * (toma / acciones_lote)
        consumos.append({
            "compra_id": c.get("id"),
            "fecha_compra": c.get("fecha"),
            "acciones": round(toma, 6),
            "precio_compra": c.get("precio"),
            "comision_parte": round(comision_prorrateada, 4),
            "tasa_compra": c.get("tasa"),
            "nivel": c.get("nivel"),
            "coste_divisa": round(toma * float(c.get("precio") or 0) + comision_prorrateada, 4),
        })
    return consumos, round(max(restante, 0.0), 6)


def _a_eur(importe: float, tasa) -> float:
    """La tasa es 'unidades de divisa por 1 EUR' (como cotiza EURUSD): se DIVIDE."""
    if tasa is None:
        return None
    try:
        tasa = float(tasa)
    except (TypeError, ValueError):
        return None
    if tasa <= 0:
        return None
    return importe / tasa


def resultado_venta(venta: dict, consumos: list) -> dict:
    """Ganancia de una venta ya emparejada, en la divisa original y en euros."""
    acciones = float(venta.get("acciones") or 0)
    precio = float(venta.get("precio") or 0)
    comision = float(venta.get("comision") or 0.0)
    tasa_venta = venta.get("tasa")

    bruto_divisa = acciones * precio
    ingreso_divisa = bruto_divisa - comision
    coste_divisa = sum(c["coste_divisa"] for c in consumos)
    ganancia_divisa = ingreso_divisa - coste_divisa

    ingreso_eur = _a_eur(ingreso_divisa, tasa_venta)
    # Cada lote a SU cambio: es lo que de verdad se pagó en euros.
    costes_eur = [_a_eur(c["coste_divisa"], c.get("tasa_compra")) for c in consumos]
    completo = all(x is not None for x in costes_eur) and ingreso_eur is not None
    coste_eur = sum(x for x in costes_eur if x is not None) if costes_eur else 0.0
    ganancia_eur = (ingreso_eur - coste_eur) if completo else None

    # Cuánto de la diferencia es el movimiento del euro y no la acción. Es la pregunta que
    # aparece sola en cuanto ves que ganaste en dólares y menos en euros.
    efecto_divisa_eur = None
    if completo:
        sin_efecto = _a_eur(ganancia_divisa, tasa_venta)
        if sin_efecto is not None:
            efecto_divisa_eur = ganancia_eur - sin_efecto

    pct_divisa = (ganancia_divisa / coste_divisa * 100) if coste_divisa else None
    pct_eur = (ganancia_eur / coste_eur * 100) if (completo and coste_eur) else None

    return {
        "acciones": round(acciones, 6),
        "precio_venta": precio,
        "comision_venta": round(comision, 4),
        "bruto_divisa": round(bruto_divisa, 2),
        "ingreso_divisa": round(ingreso_divisa, 2),
        "coste_divisa": round(coste_divisa, 2),
        "ganancia_divisa": round(ganancia_divisa, 2),
        "pct": round(pct_divisa, 2) if pct_divisa is not None else None,
        "ingreso_eur": round(ingreso_eur, 2) if ingreso_eur is not None else None,
        "coste_eur": round(coste_eur, 2) if completo else None,
        "ganancia_eur": round(ganancia_eur, 2) if ganancia_eur is not None else None,
        "pct_eur": round(pct_eur, 2) if pct_eur is not None else None,
        "efecto_divisa_eur": round(efecto_divisa_eur, 2) if efecto_divisa_eur is not None else None,
        # `exacto` marca si TODOS los cambios necesarios estaban disponibles. Sin esta marca
        # un total mezclaría cifras exactas con estimaciones y aparentaría una precisión
        # que no tiene.
        "exacto": bool(completo),
        "lotes": consumos,
        "comisiones_totales": round(comision + sum(c["comision_parte"] for c in consumos), 2),
    }


def reproducir(compras: list, ventas: list, metodo: str = FIFO) -> dict:
    """Reproduce el libro entero de UN símbolo y devuelve el estado y lo realizado.

    Las ventas se aplican en orden cronológico: vender antes de una compra posterior no
    puede consumirla, y hacerlo daría una ganancia imposible.
    """
    if metodo not in METODOS:
        raise ValueError(f"Método desconocido: {metodo}")

    # Copia de trabajo: la función no debe tocar lo que le pasan.
    lotes = []
    for c in sorted(compras, key=lambda x: (str(x.get("fecha") or ""),
                                            str(x.get("created_at") or ""))):
        d = dict(c)
        d["_libres"] = float(d.get("acciones") or 0)
        lotes.append(d)

    realizadas, descuadres = [], 0.0
    for v in sorted(ventas, key=lambda x: (str(x.get("fecha") or ""),
                                           str(x.get("created_at") or ""))):
        # Solo cuentan los lotes comprados en la fecha de la venta o antes.
        disponibles = [l for l in lotes if str(l.get("fecha") or "") <= str(v.get("fecha") or "")]
        consumos, sin_cubrir = emparejar(disponibles, float(v.get("acciones") or 0), metodo)
        for c in consumos:
            for l in lotes:
                if l.get("id") == c["compra_id"]:
                    l["_libres"] = round(l["_libres"] - c["acciones"], 6)
                    break
        descuadres += sin_cubrir
        res = resultado_venta(v, consumos)
        res["sin_cubrir"] = sin_cubrir
        realizadas.append({**{k: val for k, val in v.items() if k != "_libres"}, **res,
                           "metodo": metodo})

    abiertos = []
    for l in lotes:
        if l["_libres"] > 1e-9:
            abierto = {k: val for k, val in l.items() if k != "_libres"}
            abierto["acciones_abiertas"] = round(l["_libres"], 6)
            parte = l["_libres"] / (float(l.get("acciones") or 0) or 1.0)
            abierto["coste_divisa"] = round(
                l["_libres"] * float(l.get("precio") or 0)
                + float(l.get("comision") or 0.0) * parte, 4)
            abierto["coste_eur"] = _a_eur(abierto["coste_divisa"], l.get("tasa"))
            if abierto["coste_eur"] is not None:
                abierto["coste_eur"] = round(abierto["coste_eur"], 2)
            abiertos.append(abierto)

    acciones_abiertas = round(sum(a["acciones_abiertas"] for a in abiertos), 6)
    coste_abierto_divisa = round(sum(a["coste_divisa"] for a in abiertos), 2)
    costes_eur = [a["coste_eur"] for a in abiertos]
    coste_abierto_eur = (round(sum(costes_eur), 2)
                         if costes_eur and all(x is not None for x in costes_eur) else None)

    return {
        "metodo": metodo,
        "abiertos": abiertos,
        "acciones_abiertas": acciones_abiertas,
        "coste_abierto_divisa": coste_abierto_divisa,
        "coste_abierto_eur": coste_abierto_eur,
        # Precio medio de LO QUE QUEDA, que es lo que importa para juzgar la posición viva.
        # Depende del método: tras vender parte, FIFO y LIFO dejan lotes distintos abiertos.
        "precio_medio": (round(coste_abierto_divisa / acciones_abiertas, 4)
                         if acciones_abiertas > 1e-9 else None),
        "ventas": realizadas,
        "ganancia_realizada_divisa": round(sum(v["ganancia_divisa"] for v in realizadas), 2),
        # None, y NO 0, cuando ninguna venta tiene los tipos de cambio necesarios. Un 0 se
        # lee como "no has ganado nada", que es una afirmación; lo cierto es que no se sabe.
        # Además hacía que dos métodos con resultados distintos parecieran idénticos.
        "ganancia_realizada_eur": (
            round(sum(v["ganancia_eur"] for v in realizadas if v["ganancia_eur"] is not None), 2)
            if any(v["ganancia_eur"] is not None for v in realizadas) else None),
        "todo_exacto": all(v["exacto"] for v in realizadas) if realizadas else True,
        "acciones_sin_cubrir": round(descuadres, 6),
    }


def valorar_abierto(estado: dict, precio_actual, tasa_hoy) -> dict:
    """Ganancia LATENTE (lo que llevas ganado sin vender) en divisa y en euros.

    El coste va al cambio de cada compra y el valor de hoy al cambio de hoy: así el número
    incluye el movimiento del euro, que es real aunque no lo hayas materializado. Es
    exactamente la diferencia entre lo que ingresarías vendiendo ahora y lo que pusiste.
    """
    n = estado.get("acciones_abiertas") or 0
    if n <= 1e-9 or precio_actual in (None, ""):
        return {"acciones": 0, "valor_divisa": None, "pnl_divisa": None,
                "valor_eur": None, "pnl_eur": None, "pct": None, "pct_eur": None}
    try:
        precio_actual = float(precio_actual)
    except (TypeError, ValueError):
        return {"acciones": n, "valor_divisa": None, "pnl_divisa": None,
                "valor_eur": None, "pnl_eur": None, "pct": None, "pct_eur": None}

    valor_divisa = n * precio_actual
    coste_divisa = estado.get("coste_abierto_divisa") or 0
    pnl_divisa = valor_divisa - coste_divisa

    valor_eur = _a_eur(valor_divisa, tasa_hoy)
    coste_eur = estado.get("coste_abierto_eur")
    pnl_eur = (valor_eur - coste_eur) if (valor_eur is not None and coste_eur is not None) else None

    return {
        "acciones": n,
        "valor_divisa": round(valor_divisa, 2),
        "coste_divisa": round(coste_divisa, 2),
        "pnl_divisa": round(pnl_divisa, 2),
        "pct": round(pnl_divisa / coste_divisa * 100, 2) if coste_divisa else None,
        "valor_eur": round(valor_eur, 2) if valor_eur is not None else None,
        "coste_eur": coste_eur,
        "pnl_eur": round(pnl_eur, 2) if pnl_eur is not None else None,
        "pct_eur": (round(pnl_eur / coste_eur * 100, 2)
                    if (pnl_eur is not None and coste_eur) else None),
    }


def comparar_metodos(compras: list, ventas: list) -> dict:
    """FIFO y LIFO sobre las mismas operaciones, con la diferencia ya calculada.

    Se devuelven juntos y etiquetados a propósito: enseñar un solo número sin decir de qué
    método es invita a meterlo en la declaración, y solo FIFO vale para eso.
    """
    fifo = reproducir(compras, ventas, FIFO)
    lifo = reproducir(compras, ventas, LIFO)
    # La diferencia se mide sobre la DIVISA, que siempre se conoce, y en euros solo si los
    # dos lados la tienen. Compararlos por el importe en euros hacía que dos resultados
    # distintos parecieran iguales cuando faltaban los tipos de cambio.
    f_eur, l_eur = fifo["ganancia_realizada_eur"], lifo["ganancia_realizada_eur"]
    hay_eur = f_eur is not None and l_eur is not None
    dif_divisa = round(fifo["ganancia_realizada_divisa"] - lifo["ganancia_realizada_divisa"], 2)
    return {
        "fifo": fifo,
        "lifo": lifo,
        "diferencia_divisa": dif_divisa,
        "diferencia_eur": round(f_eur - l_eur, 2) if hay_eur else None,
        "coinciden": abs(dif_divisa) < 0.005 and (not hay_eur or abs(f_eur - l_eur) < 0.005),
        "oficial": FIFO,
        "nota_fiscal": (
            "FIFO es el método obligatorio en España para acciones cotizadas "
            "(art. 37.2 de la Ley del IRPF): es la cifra que va a tu declaración. LIFO se "
            "muestra solo como referencia de gestión."),
    }
