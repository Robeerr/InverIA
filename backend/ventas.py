"""Registro de ventas ejecutadas y ganancia REALIZADA.

Distinto de lo que ya había: `venta1/2/3` en la Cartera son PRECIOS OBJETIVO ("quiero vender
a 210"). Esto es otra cosa: ventas que ya has hecho, con lo que ganaste de verdad.

Cada venta guarda una FOTO de los datos del momento (precio medio de compra, tipos de cambio)
en vez de recalcular después contra la posición actual. Es imprescindible: si vendes 10 de 25
acciones y luego compras más, tu precio medio cambia, y recalcular la venta vieja con el
precio medio nuevo daría una ganancia que nunca ocurrió.
"""
import logging
import uuid
from datetime import datetime, timezone

import fx

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def registrar(db, entry: dict, acciones: float, precio_venta: float,
                    fecha: str = None, tasa_compra: float = None,
                    tasa_venta: float = None) -> dict:
    """Registra una venta y descuenta las acciones de la posición.

    Devuelve el documento de la venta con el resultado ya calculado.
    Lanza ValueError si los datos no permiten un cálculo honesto.
    """
    acciones = float(acciones)
    precio_venta = float(precio_venta)
    if acciones <= 0:
        raise ValueError("El número de acciones vendidas debe ser mayor que cero.")
    if precio_venta <= 0:
        raise ValueError("El precio de venta debe ser mayor que cero.")

    tenia = entry.get("acciones")
    if tenia is None:
        raise ValueError(
            "Esta posición no tiene número de acciones. Rellénalo en la Cartera antes de "
            "registrar una venta.")
    tenia = float(tenia)
    if acciones > tenia + 1e-9:
        raise ValueError(f"Solo tienes {tenia:g} acciones de {entry.get('symbol')}; "
                         f"no puedes vender {acciones:g}.")

    precio_compra = entry.get("compra")
    if precio_compra is None:
        raise ValueError(
            "Esta posición no tiene precio de compra. Sin él no se puede calcular la "
            "ganancia. Rellénalo en la Cartera.")
    precio_compra = float(precio_compra)

    divisa = (entry.get("divisa") or "USD").strip().upper() or "USD"
    fecha = (fecha or datetime.now(timezone.utc).date().isoformat())[:10]

    # Tipos de cambio. Los que vengan dados MANDAN (el usuario puede saber el real de su
    # banco, que incluye comisión y no coincide con el de mercado).
    if tasa_venta is None:
        tasa_venta = fx.tasa_en_fecha(divisa, fecha) or fx.tasa_actual(divisa)
    if tasa_compra is None and entry.get("fecha_compra"):
        tasa_compra = fx.tasa_en_fecha(divisa, str(entry["fecha_compra"])[:10])

    res = fx.calcular_venta(acciones, precio_compra, precio_venta, divisa,
                            tasa_compra, tasa_venta)
    venta = {
        "id": str(uuid.uuid4()),
        "entry_id": entry.get("id"),
        "symbol": entry.get("symbol"),
        "name": entry.get("name") or "",
        "fecha": fecha,
        # Foto del momento: ver la explicación de arriba.
        "precio_compra": precio_compra,
        "precio_venta": precio_venta,
        "fecha_compra": (str(entry["fecha_compra"])[:10] if entry.get("fecha_compra") else None),
        **res,
        "created_at": _now(),
    }
    await db.signal_sales.insert_one(dict(venta))

    # Descontar de la posición. Si se vende todo, quedan 0 acciones y el precio medio se
    # deja como estaba (es historia, y borrarlo perdería el dato de la siguiente venta).
    restantes = round(tenia - acciones, 6)
    await db.signal_entries.update_one(
        {"id": entry.get("id")},
        {"$set": {"acciones": restantes if restantes > 1e-9 else 0, "updated_at": _now()}})
    venta["acciones_restantes"] = restantes if restantes > 1e-9 else 0
    return venta


async def listar(db, limite: int = 500) -> list:
    return await db.signal_sales.find({}, {"_id": 0}).sort("fecha", -1).to_list(limite)


async def borrar(db, venta_id: str) -> bool:
    """Borra una venta y DEVUELVE las acciones a la posición. Sin esto, corregir una venta
    mal metida dejaría la posición descuadrada para siempre."""
    v = await db.signal_sales.find_one({"id": venta_id}, {"_id": 0})
    if not v:
        return False
    await db.signal_sales.delete_one({"id": venta_id})
    entry = await db.signal_entries.find_one({"id": v.get("entry_id")}, {"_id": 0})
    if entry:
        actuales = float(entry.get("acciones") or 0)
        await db.signal_entries.update_one(
            {"id": entry["id"]},
            {"$set": {"acciones": round(actuales + float(v.get("acciones") or 0), 6),
                      "updated_at": _now()}})
    return True


def resumen(ventas: list) -> dict:
    """Totales. Separa lo que se sabe con exactitud de lo aproximado en vez de sumarlo todo
    junto: mezclarlos daría un total con una precisión que no tiene."""
    total_eur = sum(v.get("ganancia_eur") or 0 for v in ventas if v.get("exacto"))
    aprox_eur = sum(v.get("ganancia_eur") or 0 for v in ventas
                    if not v.get("exacto") and v.get("ganancia_eur") is not None)
    efecto = sum(v.get("efecto_divisa_eur") or 0 for v in ventas if v.get("exacto"))
    por_divisa = {}
    for v in ventas:
        d = v.get("divisa") or "USD"
        por_divisa[d] = round(por_divisa.get(d, 0) + (v.get("ganancia_divisa") or 0), 2)
    sin_calcular = sum(1 for v in ventas if v.get("ganancia_eur") is None)
    return {
        "n_ventas": len(ventas),
        "ganancia_eur_exacta": round(total_eur, 2),
        "ganancia_eur_aproximada": round(aprox_eur, 2),
        "efecto_divisa_eur": round(efecto, 2),
        "ganancia_por_divisa": por_divisa,
        "ventas_sin_calcular": sin_calcular,
        "aviso": ("Algunas ventas no tienen el tipo de cambio de la compra, así que su "
                  "ganancia en euros es aproximada. Añade la fecha de compra en la Cartera "
                  "para afinarlas.") if aprox_eur or sin_calcular else None,
    }
