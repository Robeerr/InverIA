"""Tests del registro de ventas y de la ganancia en euros.

Lo que se juega aquí es dinero mal contado, así que se comprueban sobre todo los casos que
descuadran la cartera: vender más de lo que tienes, borrar una venta, y que la ganancia en
euros use los tipos de cambio de las DOS fechas y no el de hoy.

Ejecutar:  cd backend && pytest tests/ -v
"""
import asyncio

import pytest

import fx
import ventas as v


# ── Conversión a euros ───────────────────────────────────────────────────────

def test_la_ganancia_en_euros_depende_de_las_DOS_fechas():
    """Misma ganancia en dólares, resultados muy distintos en euros. Es la razón de ser de
    todo esto: convertir al cambio de hoy daría un número que no ocurrió."""
    base = dict(acciones=10, precio_compra=120, precio_venta=186, divisa="USD")
    estable = fx.calcular_venta(**base, tasa_compra=1.08, tasa_venta=1.08)
    euro_sube = fx.calcular_venta(**base, tasa_compra=1.05, tasa_venta=1.18)
    euro_baja = fx.calcular_venta(**base, tasa_compra=1.18, tasa_venta=1.05)

    assert estable["ganancia_divisa"] == euro_sube["ganancia_divisa"] == 660.0
    assert euro_sube["ganancia_eur"] < estable["ganancia_eur"] < euro_baja["ganancia_eur"]
    # El efecto divisa debe explicar la diferencia.
    assert euro_sube["efecto_divisa_eur"] < 0 < euro_baja["efecto_divisa_eur"]
    assert estable["efecto_divisa_eur"] == 0.0


def test_se_marca_como_aproximado_si_falta_el_cambio_de_compra():
    r = fx.calcular_venta(10, 120, 186, "USD", tasa_compra=None, tasa_venta=1.08)
    assert r["exacto"] is False
    assert r["ganancia_eur"] is not None      # da una estimación...
    assert r["efecto_divisa_eur"] is None     # ...pero no finge saber el efecto divisa


def test_en_euros_no_se_convierte_nada():
    r = fx.calcular_venta(10, 100, 120, "EUR")
    assert r["ganancia_eur"] == r["ganancia_divisa"] == 200.0
    assert r["exacto"] is True


def test_sin_ningun_tipo_de_cambio_no_se_inventa_un_numero():
    r = fx.calcular_venta(10, 120, 186, "USD")
    assert r["ganancia_divisa"] == 660.0
    assert r["ganancia_eur"] is None


def test_a_euros_aguanta_entradas_invalidas():
    assert fx.a_euros(100, "USD", 0) is None
    assert fx.a_euros(100, "USD", None) is None
    assert fx.a_euros(None, "USD", 1.08) is None


# ── Registro de ventas ───────────────────────────────────────────────────────

class _Col:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, filtro, *a, **k):
        for d in self.docs:
            if all(d.get(kk) == vv for kk, vv in filtro.items()):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, filtro, cambio, upsert=False):
        for d in self.docs:
            if all(d.get(kk) == vv for kk, vv in filtro.items()):
                d.update(cambio.get("$set", {}))
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()

    async def delete_one(self, filtro):
        antes = len(self.docs)
        self.docs = [d for d in self.docs
                     if not all(d.get(k) == vv for k, vv in filtro.items())]
        return type("R", (), {"deleted_count": antes - len(self.docs)})()

    def find(self, *a, **k):
        col = self

        class _C:
            def sort(self, *a, **k): return self
            async def to_list(self, n): return [dict(d) for d in col.docs][:n]
        return _C()


class _DB:
    def __init__(self, entradas):
        self.signal_entries = _Col(entradas)
        self.signal_sales = _Col()


def _entrada(**kw):
    base = {"id": "e1", "symbol": "MRVL", "name": "Marvell", "compra": 120.0,
            "acciones": 25.0, "divisa": "USD", "fecha_compra": "2025-01-15"}
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    """Nada de llamadas a Yahoo en los tests: tipos de cambio fijos y conocidos."""
    monkeypatch.setattr(fx, "tasa_en_fecha", lambda d, f: 1.05 if str(f) < "2025-06" else 1.15)
    monkeypatch.setattr(fx, "tasa_actual", lambda d: 1.15)


def test_una_venta_parcial_descuenta_las_acciones():
    e = _entrada()
    db = _DB([e])
    r = asyncio.run(v.registrar(db, e, 10, 186.0, fecha="2025-08-04"))
    assert r["acciones"] == 10
    assert r["acciones_restantes"] == 15
    assert db.signal_entries.docs[0]["acciones"] == 15
    assert r["ganancia_divisa"] == 660.0
    assert r["exacto"] is True


def test_no_deja_vender_mas_de_lo_que_tienes():
    e = _entrada(acciones=25.0)
    with pytest.raises(ValueError, match="Solo tienes"):
        asyncio.run(v.registrar(_DB([e]), e, 30, 186.0))


def test_no_deja_vender_sin_precio_de_compra():
    e = _entrada(compra=None)
    with pytest.raises(ValueError, match="precio de compra"):
        asyncio.run(v.registrar(_DB([e]), e, 5, 186.0))


def test_no_deja_vender_sin_numero_de_acciones():
    e = _entrada(acciones=None)
    with pytest.raises(ValueError, match="número de acciones"):
        asyncio.run(v.registrar(_DB([e]), e, 5, 186.0))


@pytest.mark.parametrize("acc,precio", [(0, 186.0), (-5, 186.0), (5, 0), (5, -1)])
def test_rechaza_cantidades_absurdas(acc, precio):
    e = _entrada()
    with pytest.raises(ValueError):
        asyncio.run(v.registrar(_DB([e]), e, acc, precio))


def test_vender_todo_deja_la_posicion_a_cero():
    e = _entrada(acciones=25.0)
    db = _DB([e])
    r = asyncio.run(v.registrar(db, e, 25, 186.0))
    assert r["acciones_restantes"] == 0
    assert db.signal_entries.docs[0]["acciones"] == 0
    # El precio de compra se conserva: es historia.
    assert db.signal_entries.docs[0]["compra"] == 120.0


def test_borrar_una_venta_DEVUELVE_las_acciones():
    """Sin esto, corregir una venta mal metida dejaría la cartera descuadrada."""
    e = _entrada(acciones=25.0)
    db = _DB([e])
    venta = asyncio.run(v.registrar(db, e, 10, 186.0))
    assert db.signal_entries.docs[0]["acciones"] == 15
    assert asyncio.run(v.borrar(db, venta["id"])) is True
    assert db.signal_entries.docs[0]["acciones"] == 25
    assert db.signal_sales.docs == []


def test_borrar_una_venta_inexistente_no_rompe():
    assert asyncio.run(v.borrar(_DB([_entrada()]), "no-existe")) is False


def test_la_venta_guarda_una_FOTO_del_precio_de_compra():
    """Si luego compras más y cambia tu precio medio, la venta vieja NO debe recalcularse:
    daría una ganancia que nunca ocurrió."""
    e = _entrada(compra=120.0)
    db = _DB([e])
    venta = asyncio.run(v.registrar(db, e, 10, 186.0))
    db.signal_entries.docs[0]["compra"] = 150.0      # compra posterior más cara
    assert venta["precio_compra"] == 120.0
    assert db.signal_sales.docs[0]["precio_compra"] == 120.0


def test_el_resumen_separa_lo_exacto_de_lo_aproximado():
    """Sumarlo todo junto daría un total con una precisión que no tiene."""
    r = v.resumen([
        {"exacto": True, "ganancia_eur": 100.0, "efecto_divisa_eur": -20.0,
         "ganancia_divisa": 110.0, "divisa": "USD"},
        {"exacto": False, "ganancia_eur": 50.0, "efecto_divisa_eur": None,
         "ganancia_divisa": 55.0, "divisa": "USD"},
    ])
    assert r["ganancia_eur_exacta"] == 100.0
    assert r["ganancia_eur_aproximada"] == 50.0
    assert r["efecto_divisa_eur"] == -20.0
    assert r["ganancia_por_divisa"]["USD"] == 165.0
    assert r["aviso"]


def test_el_resumen_sin_ventas_no_rompe():
    r = v.resumen([])
    assert r["n_ventas"] == 0 and r["aviso"] is None
