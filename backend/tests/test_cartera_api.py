"""Tests de la capa que guarda y lee el libro de operaciones (cartera_api.py).

Sin Mongo: una base de datos falsa en memoria basta, porque lo que se comprueba es la
lógica, no el driver. Lo importante que se fija aquí:

  · nada guarda saldos — la posición se deriva de los apuntes
  · borrar una venta deja la posición correcta sola, sin "devolver" acciones a ningún sitio
  · cada símbolo se empareja por separado
  · la importación de posiciones viejas no duplica si se llama dos veces

Ejecutar:  cd backend && pytest tests/test_cartera_api.py -v
"""
import asyncio

import pytest

import cartera_api
import lotes


# ── Base de datos falsa ──────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return list(self._docs)[:n]


class _Coleccion:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, filtro=None, proj=None):
        filtro = filtro or {}
        out = []
        for d in self.docs:
            if all(self._cumple(d, k, v) for k, v in filtro.items()):
                out.append({k: v for k, v in d.items() if k != "_id"})
        return _Cursor(out)

    @staticmethod
    def _cumple(doc, clave, cond):
        v = doc.get(clave)
        if isinstance(cond, dict):
            if "$gt" in cond:
                return v is not None and v > cond["$gt"]
        return v == cond

    async def find_one(self, filtro, proj=None):
        r = await self.find(filtro, proj).to_list(1)
        return r[0] if r else None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, filtro, cambios):
        for d in self.docs:
            if all(self._cumple(d, k, v) for k, v in filtro.items()):
                d.update(cambios.get("$set") or {})
                break

    async def delete_one(self, filtro):
        antes = len(self.docs)
        self.docs = [d for d in self.docs
                     if not all(self._cumple(d, k, v) for k, v in filtro.items())]
        class _R:  # noqa: E301
            deleted_count = antes - len(self.docs)
        return _R()


class _DB:
    def __init__(self, entries=None):
        self.compras = _Coleccion()
        self.ventas = _Coleccion()
        self.signal_entries = _Coleccion(entries or [])


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Los tipos de cambio no deben salir a Internet en un test: darían un número
    distinto cada día y el test dejaría de significar nada."""
    monkeypatch.setattr(cartera_api.fx, "tasa_en_fecha", lambda d, f: 1.10)
    monkeypatch.setattr(cartera_api.fx, "tasa_actual", lambda d: 1.20)


def _correr(coro):
    return asyncio.run(coro)


# ── Compras ──────────────────────────────────────────────────────────────────

def test_una_compra_guarda_el_cambio_de_su_fecha():
    db = _DB()
    c = _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10"))
    assert c["tasa"] == 1.10, "sin el cambio de la compra, el euro sale aproximado"
    assert len(db.compras.docs) == 1


def test_el_cambio_que_das_tu_manda_sobre_el_de_mercado():
    """El del banco incluye su margen y es el que de verdad te cobraron."""
    db = _DB()
    c = _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10",
                                             tasa=1.0567))
    assert c["tasa"] == 1.0567


def test_la_compra_detecta_sola_en_que_nivel_se_hizo():
    db = _DB([{"symbol": "FN", "nivel1": 220.0, "nivel2": 200.0, "nivel3": 180.0}])
    c = _correr(cartera_api.registrar_compra(db, "FN", 5, 180.0))
    assert c["nivel"] == "nivel3"
    assert c["nivel_etiqueta"] == "Nivel 3"


def test_una_compra_fuera_de_niveles_no_se_atribuye_a_ninguno():
    db = _DB([{"symbol": "FN", "nivel1": 220.0, "nivel2": 200.0}])
    c = _correr(cartera_api.registrar_compra(db, "FN", 5, 155.0))
    assert c["nivel"] is None


def test_la_divisa_sale_de_la_posicion_si_no_se_indica():
    db = _DB([{"symbol": "FN", "divisa": "USD"}])
    c = _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0))
    assert c["divisa"] == "USD"


# ── El libro se deriva, no se guarda ─────────────────────────────────────────

def test_la_posicion_se_calcula_y_no_se_almacena():
    """Guardar además un saldo garantiza que algún día no cuadre con sus propios apuntes,
    y entonces no hay forma de saber cuál de los dos miente."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-03-05"))
    est = _correr(cartera_api.estado_simbolo(db, "FN"))
    assert est["fifo"]["acciones_abiertas"] == 5
    for doc in db.compras.docs:
        assert "acciones_abiertas" not in doc and "_libres" not in doc


def test_borrar_una_venta_deja_la_posicion_correcta_sola():
    """Con el modelo viejo había que 'devolver' las acciones a mano y era la fuente segura
    de descuadres. Aquí solo desaparece el apunte."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_venta(db, "FN", 2, 130.0, fecha="2026-06-01"))
    assert _correr(cartera_api.estado_simbolo(db, "FN"))["fifo"]["acciones_abiertas"] == 3

    vid = db.ventas.docs[0]["id"]
    assert _correr(cartera_api.borrar_venta(db, vid))
    assert _correr(cartera_api.estado_simbolo(db, "FN"))["fifo"]["acciones_abiertas"] == 5


def test_borrar_una_compra_recalcula_todo():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-03-05"))
    cid = [c for c in db.compras.docs if c["precio"] == 80.0][0]["id"]
    assert _correr(cartera_api.borrar_compra(db, cid))
    est = _correr(cartera_api.estado_simbolo(db, "FN"))
    assert est["fifo"]["acciones_abiertas"] == 2
    assert est["fifo"]["precio_medio"] == 120.0


def test_borrar_algo_que_no_existe_no_miente():
    db = _DB()
    assert _correr(cartera_api.borrar_venta(db, "no-existe")) is False
    assert _correr(cartera_api.borrar_compra(db, "no-existe")) is False


# ── Varios símbolos ──────────────────────────────────────────────────────────

def test_cada_simbolo_se_empareja_por_separado():
    """El emparejamiento es POR VALOR: si se mezclaran, una venta de FN consumiría un lote
    de AAPL y las dos posiciones quedarían mal."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_compra(db, "AAPL", 5, 200.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_venta(db, "FN", 5, 130.0, fecha="2026-06-01"))

    assert _correr(cartera_api.estado_simbolo(db, "FN"))["fifo"]["acciones_abiertas"] == 0
    assert _correr(cartera_api.estado_simbolo(db, "AAPL"))["fifo"]["acciones_abiertas"] == 5

    hist = _correr(cartera_api.historial(db))
    assert [f["symbol"] for f in hist["items"]] == ["FN"]


# ── Historial ────────────────────────────────────────────────────────────────

def test_el_historial_da_los_dos_metodos_por_venta():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-03-05"))
    _correr(cartera_api.registrar_venta(db, "FN", 1, 130.0, fecha="2026-06-01"))

    hist = _correr(cartera_api.historial(db))
    fila = hist["items"][0]
    assert fila["fifo"]["ganancia_divisa"] == 50.0
    assert fila["lifo"]["ganancia_divisa"] == 10.0
    assert "37.2" in hist["nota_fiscal"]


def test_el_historial_dice_de_que_lote_salio_cada_venta():
    """Es lo que se quiere ver para saber si comprar en los niveles funciona."""
    db = _DB([{"symbol": "FN", "nivel1": 120.0, "nivel3": 80.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_venta(db, "FN", 1, 130.0, fecha="2026-06-01"))
    fila = _correr(cartera_api.historial(db))["items"][0]
    assert fila["fifo"]["lotes"][0]["nivel"] == "nivel3"
    assert fila["fifo"]["lotes"][0]["fecha_compra"] == "2026-01-10"


def test_los_totales_separan_lo_exacto_de_lo_que_no_se_pudo_calcular(monkeypatch):
    """Sumarlo todo junto daría un total con una precisión que no tiene, y ese total
    acabaría en una declaración."""
    monkeypatch.setattr(cartera_api.fx, "tasa_en_fecha", lambda d, f: None)
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_venta(db, "FN", 5, 130.0, fecha="2026-06-01"))
    res = _correr(cartera_api.historial(db))["resumen"]
    assert res["fifo"]["ganancia_eur"] is None
    assert res["fifo"]["ganancia_divisa"] == 150.0
    assert res["ventas_sin_tipo_de_cambio"] == 1
    assert res["aviso"] and "tipo de cambio" in res["aviso"]


# ── Resumen de la cartera ────────────────────────────────────────────────────

def test_el_resumen_da_el_latente_en_euros():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 10, 100.0, fecha="2026-01-10"))
    res = _correr(cartera_api.resumen_cartera(db, {"FN": 120.0}))
    pos = res["posiciones"][0]
    assert pos["acciones"] == 10
    assert pos["pnl_divisa"] == 200.0                    # 1200 - 1000
    # Coste 1000/1,10 = 909,09 €; valor 1200/1,20 = 1000 € -> +90,91 €
    assert pos["pnl_eur"] == pytest.approx(90.91, abs=0.01)


def test_una_posicion_vendida_entera_no_sale_en_la_cartera():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_venta(db, "FN", 5, 130.0, fecha="2026-06-01"))
    res = _correr(cartera_api.resumen_cartera(db, {"FN": 130.0}))
    assert res["posiciones"] == []
    assert res["realizado_eur"] is not None


def test_una_posicion_sin_precio_no_rompe_el_total():
    """Que falte una cotización no puede dejar la cartera entera sin cifra."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_compra(db, "XX", 5, 50.0, fecha="2026-01-10"))
    res = _correr(cartera_api.resumen_cartera(db, {"FN": 120.0}))   # XX sin precio
    assert res["latente_eur"] is not None
    assert res["posiciones_sin_valorar"] == 1


def test_el_resumen_dice_en_que_niveles_se_compro():
    db = _DB([{"symbol": "FN", "nivel1": 120.0, "nivel3": 80.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-02-10"))
    res = _correr(cartera_api.resumen_cartera(db, {"FN": 130.0}))
    assert res["posiciones"][0]["niveles_comprados"] == ["nivel1", "nivel3"]


# ── Importación de lo que ya había ───────────────────────────────────────────

def test_las_posiciones_que_ya_tenias_se_importan():
    """Sin esto, estrenar el libro dejaría todas las posiciones a cero y parecería que se
    han borrado."""
    db = _DB([{"symbol": "ORCL", "acciones": 35, "compra": 142.43,
               "fecha_compra": "2025-11-02", "divisa": "USD"}])
    r = _correr(cartera_api.importar_posiciones_existentes(db))
    assert r["creados"] == 1
    est = _correr(cartera_api.estado_simbolo(db, "ORCL"))
    assert est["fifo"]["acciones_abiertas"] == 35
    assert est["fifo"]["precio_medio"] == 142.43


def test_importar_dos_veces_no_duplica():
    db = _DB([{"symbol": "ORCL", "acciones": 35, "compra": 142.43, "divisa": "USD"}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    r2 = _correr(cartera_api.importar_posiciones_existentes(db))
    assert r2["creados"] == 0 and r2["saltados"] == 1
    assert len(db.compras.docs) == 1


def test_no_se_importa_una_posicion_sin_precio_de_compra():
    """Inventar un coste falsearía todas las ganancias que salgan de ahí."""
    db = _DB([{"symbol": "META", "acciones": 10, "compra": None}])
    r = _correr(cartera_api.importar_posiciones_existentes(db))
    assert r["creados"] == 0 and r["saltados"] == 1


def test_lo_importado_queda_marcado_como_tal():
    db = _DB([{"symbol": "ORCL", "acciones": 35, "compra": 142.43}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    assert "Importada" in db.compras.docs[0]["notas"]


# ── Coherencia con el motor ──────────────────────────────────────────────────

def test_el_metodo_oficial_de_la_cartera_es_el_fiscal():
    """La Cartera valora la posición viva por FIFO. No es un detalle: tras vender parte,
    FIFO y LIFO dejan lotes distintos abiertos y por tanto un precio medio distinto."""
    import inspect
    src = inspect.getsource(cartera_api.resumen_cartera)
    assert "lotes.FIFO" in src
    assert lotes.comparar_metodos([], [])["oficial"] == lotes.FIFO


# ── La Cartera se actualiza sola ─────────────────────────────────────────────
# El numero de acciones vivia en DOS sitios: las columnas de la Cartera y el libro. Tener
# que actualizar los dos a mano garantiza que algun dia no cuadren, y obliga a recordar un
# orden de pasos que nadie tiene por que recordar. El libro manda; la Cartera se deriva.

def test_registrar_una_venta_baja_las_acciones_de_la_cartera():
    db = _DB([{"symbol": "FN", "acciones": 5, "compra": 100.0, "divisa": "USD"}])
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_venta(db, "FN", 2, 130.0, fecha="2026-06-01"))
    fila = db.signal_entries.docs[0]
    assert fila["acciones"] == 3, "no deberia hacer falta tocarlo a mano"


def test_vender_la_posicion_entera_deja_la_cartera_a_cero():
    db = _DB([{"symbol": "SPCX", "acciones": 10, "compra": 50.0}])
    _correr(cartera_api.registrar_compra(db, "SPCX", 10, 50.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_venta(db, "SPCX", 10, 70.0, fecha="2026-06-01"))
    assert db.signal_entries.docs[0]["acciones"] == 0


def test_el_precio_medio_de_la_cartera_sigue_al_de_lo_que_queda():
    """Tras vender parte por FIFO, lo que queda son los lotes caros: el medio sube."""
    db = _DB([{"symbol": "FN", "acciones": 5, "compra": 96.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-03-05"))
    _correr(cartera_api.registrar_venta(db, "FN", 3, 130.0, fecha="2026-06-01"))
    fila = db.signal_entries.docs[0]
    assert fila["acciones"] == 2
    assert fila["compra"] == 120.0, "quedan las 2 de 120, no el medio original"


def test_borrar_una_venta_devuelve_las_acciones_a_la_cartera():
    db = _DB([{"symbol": "FN", "acciones": 5, "compra": 100.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_venta(db, "FN", 2, 130.0, fecha="2026-06-01"))
    _correr(cartera_api.borrar_venta(db, db.ventas.docs[0]["id"]))
    assert db.signal_entries.docs[0]["acciones"] == 5


def test_una_accion_sin_libro_no_se_toca():
    """Las posiciones que aun no se han importado deben quedarse como estan."""
    db = _DB([{"symbol": "META", "acciones": 7, "compra": 500.0}])
    _correr(cartera_api._sincronizar_posicion(db, "META"))
    assert db.signal_entries.docs[0]["acciones"] == 7


# ── Importacion usando las campanitas ────────────────────────────────────────

def test_la_importacion_reconstruye_un_lote_por_nivel_comprado():
    """Antes creaba UN lote al precio medio y perdia el desglose por niveles, que es
    justo lo que se quiere saber."""
    db = _DB([{"symbol": "FN", "acciones": 10, "compra": 130.0, "divisa": "USD",
               "nivel1": 200.0, "alert_nivel1": False,
               "nivel2": 100.0, "alert_nivel2": False}])
    r = _correr(cartera_api.importar_posiciones_existentes(db))
    assert r["creados"] == 1
    assert r["estimados"] == [], "con dos niveles el reparto es exacto"
    assert len(db.compras.docs) == 2
    por_nivel = {c["nivel"]: c["acciones"] for c in db.compras.docs}
    assert por_nivel == {"nivel1": 3.0, "nivel2": 7.0}


def test_la_importacion_avisa_cuando_el_reparto_es_una_estimacion():
    db = _DB([{"symbol": "FN", "acciones": 9, "compra": 200.0,
               "nivel1": 220.0, "alert_nivel1": False,
               "nivel2": 200.0, "alert_nivel2": False,
               "nivel3": 180.0, "alert_nivel3": False}])
    r = _correr(cartera_api.importar_posiciones_existentes(db))
    assert r["estimados"] == ["FN"]
    assert all("REPARTO ESTIMADO" in c["notas"] for c in db.compras.docs)


def test_la_importacion_deja_la_cartera_cuadrada():
    db = _DB([{"symbol": "FN", "acciones": 10, "compra": 130.0,
               "nivel1": 200.0, "alert_nivel1": False,
               "nivel2": 100.0, "alert_nivel2": False}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    assert db.signal_entries.docs[0]["acciones"] == 10
    assert db.signal_entries.docs[0]["compra"] == pytest.approx(130.0)


# ── Las campanitas, de punta a punta ─────────────────────────────────────────

def test_vender_un_nivel_entero_enciende_su_campanita_de_verdad():
    db = _DB([{"symbol": "FN", "nivel1": 200.0, "alert_nivel1": False,
               "nivel2": 100.0, "alert_nivel2": False, "acciones": 10, "compra": 130.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 200.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_compra(db, "FN", 7, 100.0, fecha="2026-02-10"))
    # FIFO consume primero la del 10/01, que es la del Nivel 1.
    _correr(cartera_api.registrar_venta(db, "FN", 3, 250.0, fecha="2026-06-01"))
    fila = db.signal_entries.docs[0]
    assert fila["alert_nivel1"] is True, "Nivel 1 vendido entero: vuelve a avisar"
    assert fila["alert_nivel2"] is False, "Nivel 2 sigue comprado"
    assert fila["acciones"] == 7


def test_comprar_en_un_nivel_apaga_su_campanita_de_verdad():
    db = _DB([{"symbol": "FN", "nivel3": 180.0, "alert_nivel3": True}])
    _correr(cartera_api.registrar_compra(db, "FN", 5, 180.0, fecha="2026-01-10"))
    assert db.signal_entries.docs[0]["alert_nivel3"] is False


def test_deshacer_la_venta_vuelve_a_apagar_la_campanita():
    """Corregir un error no puede dejar las campanitas contando otra historia."""
    db = _DB([{"symbol": "FN", "nivel1": 200.0, "alert_nivel1": False}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 200.0, fecha="2026-01-10"))
    _correr(cartera_api.registrar_venta(db, "FN", 3, 250.0, fecha="2026-06-01"))
    assert db.signal_entries.docs[0]["alert_nivel1"] is True
    _correr(cartera_api.borrar_venta(db, db.ventas.docs[0]["id"]))
    assert db.signal_entries.docs[0]["alert_nivel1"] is False
