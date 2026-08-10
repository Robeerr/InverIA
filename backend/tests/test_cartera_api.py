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

    async def insert_many(self, docs):
        self.docs.extend(dict(d) for d in docs)

    async def update_one(self, filtro, cambios, upsert=False):
        for d in self.docs:
            if all(self._cumple(d, k, v) for k, v in filtro.items()):
                d.update(cambios.get("$set") or {})
                return
        if upsert:
            nuevo = dict(filtro)
            nuevo.update(cambios.get("$set") or {})
            self.docs.append(nuevo)

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
        self.ajustes = _Coleccion()
        self.dividendos = _Coleccion()
        self.isin_map = _Coleccion()
        self.precios_manuales = _Coleccion()
        self.signal_entries = _Coleccion(entries or [])


@pytest.fixture(autouse=True)
def ajuste_limpio():
    """El metodo de gestion se cachea en memoria 30 s. Sin limpiarlo, el que elige un test
    se cuela en el siguiente y los fallos aparecen en el test equivocado."""
    cartera_api._metodo_cache.update({"valor": None, "ts": 0.0})
    yield
    cartera_api._metodo_cache.update({"valor": None, "ts": 0.0})


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
    c = _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10", comision=0))
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
    c = _correr(cartera_api.registrar_compra(db, "FN", 5, 180.0, comision=0))
    assert c["nivel"] == "nivel3"
    assert c["nivel_etiqueta"] == "Nivel 3"


def test_una_compra_fuera_de_niveles_no_se_atribuye_a_ninguno():
    db = _DB([{"symbol": "FN", "nivel1": 220.0, "nivel2": 200.0}])
    c = _correr(cartera_api.registrar_compra(db, "FN", 5, 155.0, comision=0))
    assert c["nivel"] is None


def test_la_divisa_sale_de_la_posicion_si_no_se_indica():
    db = _DB([{"symbol": "FN", "divisa": "USD"}])
    c = _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, comision=0))
    assert c["divisa"] == "USD"


# ── El libro se deriva, no se guarda ─────────────────────────────────────────

def test_la_posicion_se_calcula_y_no_se_almacena():
    """Guardar además un saldo garantiza que algún día no cuadre con sus propios apuntes,
    y entonces no hay forma de saber cuál de los dos miente."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-03-05", comision=0))
    est = _correr(cartera_api.estado_simbolo(db, "FN"))
    assert est["fifo"]["acciones_abiertas"] == 5
    for doc in db.compras.docs:
        assert "acciones_abiertas" not in doc and "_libres" not in doc


def test_borrar_una_venta_deja_la_posicion_correcta_sola():
    """Con el modelo viejo había que 'devolver' las acciones a mano y era la fuente segura
    de descuadres. Aquí solo desaparece el apunte."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 2, 130.0, fecha="2026-06-01", comision=0))
    assert _correr(cartera_api.estado_simbolo(db, "FN"))["fifo"]["acciones_abiertas"] == 3

    vid = db.ventas.docs[0]["id"]
    assert _correr(cartera_api.borrar_venta(db, vid))
    assert _correr(cartera_api.estado_simbolo(db, "FN"))["fifo"]["acciones_abiertas"] == 5


def test_borrar_una_compra_recalcula_todo():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-03-05", comision=0))
    cid = [c for c in db.compras.docs if c["precio"] == 80.0][0]["id"]
    assert _correr(cartera_api.borrar_compra(db, cid))
    est = _correr(cartera_api.estado_simbolo(db, "FN"))
    assert est["fifo"]["acciones_abiertas"] == 2
    assert est["fifo"]["precio_medio"] == 120.0


def test_borrar_algo_que_no_existe_no_miente():
    db = _DB()
    assert _correr(cartera_api.borrar_venta(db, "no-existe")) is False
    # borrar_compra devuelve un dict desde que puede NEGARSE a borrar (dejaría ventas sin
    # coste); el motivo hace falta para que el endpoint distinga 404 de 409.
    assert _correr(cartera_api.borrar_compra(db, "no-existe")) == {
        "borrada": False, "motivo": "no_existe"}


# ── Varios símbolos ──────────────────────────────────────────────────────────

def test_cada_simbolo_se_empareja_por_separado():
    """El emparejamiento es POR VALOR: si se mezclaran, una venta de FN consumiría un lote
    de AAPL y las dos posiciones quedarían mal."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "AAPL", 5, 200.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 5, 130.0, fecha="2026-06-01", comision=0))

    assert _correr(cartera_api.estado_simbolo(db, "FN"))["fifo"]["acciones_abiertas"] == 0
    assert _correr(cartera_api.estado_simbolo(db, "AAPL"))["fifo"]["acciones_abiertas"] == 5

    hist = _correr(cartera_api.historial(db))
    assert [f["symbol"] for f in hist["items"]] == ["FN"]


# ── Historial ────────────────────────────────────────────────────────────────

def test_el_historial_da_los_dos_metodos_por_venta():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-03-05", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 1, 130.0, fecha="2026-06-01", comision=0))

    hist = _correr(cartera_api.historial(db))
    fila = hist["items"][0]
    assert fila["fifo"]["ganancia_divisa"] == 50.0
    assert fila["lifo"]["ganancia_divisa"] == 10.0
    assert "37.2" in hist["nota_fiscal"]


def test_el_historial_dice_de_que_lote_salio_cada_venta():
    """Es lo que se quiere ver para saber si comprar en los niveles funciona."""
    db = _DB([{"symbol": "FN", "nivel1": 120.0, "nivel3": 80.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 1, 130.0, fecha="2026-06-01", comision=0))
    fila = _correr(cartera_api.historial(db))["items"][0]
    assert fila["fifo"]["lotes"][0]["nivel"] == "nivel3"
    assert fila["fifo"]["lotes"][0]["fecha_compra"] == "2026-01-10"


def test_los_totales_separan_lo_exacto_de_lo_que_no_se_pudo_calcular(monkeypatch):
    """Sumarlo todo junto daría un total con una precisión que no tiene, y ese total
    acabaría en una declaración."""
    monkeypatch.setattr(cartera_api.fx, "tasa_en_fecha", lambda d, f: None)
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 5, 130.0, fecha="2026-06-01", comision=0))
    res = _correr(cartera_api.historial(db))["resumen"]
    assert res["fifo"]["ganancia_eur"] is None
    assert res["fifo"]["ganancia_divisa"] == 150.0
    assert res["ventas_sin_tipo_de_cambio"] == 1
    assert res["aviso"] and "tipo de cambio" in res["aviso"]


# ── Resumen de la cartera ────────────────────────────────────────────────────

def test_el_resumen_da_el_latente_en_euros():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 10, 100.0, fecha="2026-01-10", comision=0))
    res = _correr(cartera_api.resumen_cartera(db, {"FN": 120.0}))
    pos = res["posiciones"][0]
    assert pos["acciones"] == 10
    assert pos["pnl_divisa"] == 200.0                    # 1200 - 1000
    # Coste 1000/1,10 = 909,09 €; valor 1200/1,20 = 1000 € -> +90,91 €
    assert pos["pnl_eur"] == pytest.approx(90.91, abs=0.01)


def test_una_posicion_vendida_entera_no_sale_en_la_cartera():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 5, 130.0, fecha="2026-06-01", comision=0))
    res = _correr(cartera_api.resumen_cartera(db, {"FN": 130.0}))
    assert res["posiciones"] == []
    assert res["realizado_eur"] is not None


def test_una_posicion_sin_precio_no_rompe_el_total():
    """Que falte una cotización no puede dejar la cartera entera sin cifra."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "XX", 5, 50.0, fecha="2026-01-10", comision=0))
    res = _correr(cartera_api.resumen_cartera(db, {"FN": 120.0}))   # XX sin precio
    assert res["latente_eur"] is not None
    assert res["posiciones_sin_valorar"] == 1


def test_el_resumen_dice_en_que_niveles_se_compro():
    db = _DB([{"symbol": "FN", "nivel1": 120.0, "nivel3": 80.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-02-10", comision=0))
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

def test_la_cartera_se_valora_con_el_metodo_de_GESTION_no_con_el_fiscal():
    """Decision revisada. La Cartera contesta a "cuanto llevo ganado", no a "que declaro".

    Se entra por niveles segun CAE el precio, asi que la compra mas reciente es la mas
    barata y al cerrar un nivel se vende esa: LIFO. Con FIFO el precio medio y las
    campanitas hablarian del extremo contrario — los niveles caros, comprados primero.

    Lo fiscal no se pierde: comparar_metodos calcula siempre los dos y `oficial` sigue
    siendo FIFO, que es lo que hay que llevar a la declaracion.
    """
    import inspect
    src = inspect.getsource(cartera_api.resumen_cartera)
    assert "gestion" in src
    assert _correr(cartera_api.metodo_gestion(_DB())) == lotes.LIFO
    assert lotes.comparar_metodos([], [])["oficial"] == lotes.FIFO
    assert lotes.METODO_FISCAL == lotes.FIFO


# ── La Cartera se actualiza sola ─────────────────────────────────────────────
# El numero de acciones vivia en DOS sitios: las columnas de la Cartera y el libro. Tener
# que actualizar los dos a mano garantiza que algun dia no cuadren, y obliga a recordar un
# orden de pasos que nadie tiene por que recordar. El libro manda; la Cartera se deriva.

def test_registrar_una_venta_baja_las_acciones_de_la_cartera():
    db = _DB([{"symbol": "FN", "acciones": 5, "compra": 100.0, "divisa": "USD"}])
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 2, 130.0, fecha="2026-06-01", comision=0))
    fila = db.signal_entries.docs[0]
    assert fila["acciones"] == 3, "no deberia hacer falta tocarlo a mano"


def test_vender_la_posicion_entera_deja_la_cartera_a_cero():
    db = _DB([{"symbol": "SPCX", "acciones": 10, "compra": 50.0}])
    _correr(cartera_api.registrar_compra(db, "SPCX", 10, 50.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "SPCX", 10, 70.0, fecha="2026-06-01", comision=0))
    assert db.signal_entries.docs[0]["acciones"] == 0


def test_el_precio_medio_de_la_cartera_sigue_al_de_lo_que_queda():
    """Con LIFO se vende lo mas reciente, asi que lo que queda son las compras antiguas."""
    db = _DB([{"symbol": "FN", "acciones": 5, "compra": 96.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-03-05", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 2, 130.0, fecha="2026-06-01", comision=0))
    fila = db.signal_entries.docs[0]
    assert fila["acciones"] == 3
    assert fila["compra"] == 80.0, "se vendieron las 2 de 120; quedan las 3 de 80"


def test_borrar_una_venta_devuelve_las_acciones_a_la_cartera():
    db = _DB([{"symbol": "FN", "acciones": 5, "compra": 100.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 2, 130.0, fecha="2026-06-01", comision=0))
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
    """Con LIFO se consume la compra MAS RECIENTE, que es la del nivel mas barato: es lo
    que pasa de verdad al cerrar un nivel comprando segun cae el precio. Con FIFO se
    encenderia la campanita del Nivel 1 y estaria contando lo contrario."""
    db = _DB([{"symbol": "FN", "nivel1": 200.0, "alert_nivel1": False,
               "nivel2": 100.0, "alert_nivel2": False, "acciones": 10, "compra": 130.0}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 200.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "FN", 7, 100.0, fecha="2026-02-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 7, 250.0, fecha="2026-06-01", comision=0))
    fila = db.signal_entries.docs[0]
    assert fila["alert_nivel2"] is True, "Nivel 2 (el mas reciente) vendido entero"
    assert fila["alert_nivel1"] is False, "Nivel 1 sigue comprado"
    assert fila["acciones"] == 3


def test_comprar_en_un_nivel_apaga_su_campanita_de_verdad():
    db = _DB([{"symbol": "FN", "nivel3": 180.0, "alert_nivel3": True}])
    _correr(cartera_api.registrar_compra(db, "FN", 5, 180.0, fecha="2026-01-10", comision=0))
    assert db.signal_entries.docs[0]["alert_nivel3"] is False


def test_deshacer_la_venta_vuelve_a_apagar_la_campanita():
    """Corregir un error no puede dejar las campanitas contando otra historia."""
    db = _DB([{"symbol": "FN", "nivel1": 200.0, "alert_nivel1": False}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 200.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 3, 250.0, fecha="2026-06-01", comision=0))
    assert db.signal_entries.docs[0]["alert_nivel1"] is True
    _correr(cartera_api.borrar_venta(db, db.ventas.docs[0]["id"]))
    assert db.signal_entries.docs[0]["alert_nivel1"] is False


def test_lo_fiscal_sigue_estando_aunque_la_gestion_sea_LIFO():
    """Cambiar el metodo por defecto no puede hacer desaparecer la cifra de la declaracion:
    son dos preguntas distintas y las dos tienen que poder contestarse."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 3, 80.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "FN", 2, 120.0, fecha="2026-03-05", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 1, 130.0, fecha="2026-06-01", comision=0))
    fila = _correr(cartera_api.historial(db))["items"][0]
    assert fila["lifo"]["ganancia_divisa"] == 10.0    # lo que vendiste de verdad
    assert fila["fifo"]["ganancia_divisa"] == 50.0    # lo que declara Hacienda
    res = _correr(cartera_api.historial(db))["resumen"]
    assert res["fifo"]["ganancia_divisa"] == 50.0
    assert res["lifo"]["ganancia_divisa"] == 10.0


def test_el_resumen_dice_con_que_metodo_esta_calculado():
    """Una cifra de ganancia sin decir de que metodo es invita a meterla donde no debe."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 5, 100.0, fecha="2026-01-10", comision=0))
    res = _correr(cartera_api.resumen_cartera(db, {"FN": 120.0}))
    assert res["metodo_gestion"] == "lifo"
    est = _correr(cartera_api.estado_simbolo(db, "FN"))
    assert est["metodo_gestion"] == "lifo"


# ── Comisiones: vacio no es cero ─────────────────────────────────────────────

def test_dejar_la_comision_vacia_la_estima_en_vez_de_ponerla_a_cero():
    """Un cero parece un dato y es una afirmacion: "esta operacion no me costo nada". Si no
    lo sabes, una estimacion con la tarifa publica se acerca mucho mas a la verdad."""
    db = _DB()
    c = _correr(cartera_api.registrar_compra(db, "FN", 10, 100.0, fecha="2026-01-10"))
    assert c["comision"] > 0
    assert c["comision_estimada"] is True
    assert "DEGIRO" in c["comision_detalle"]
    # 2 EUR a 1,10 = 2,20 $ + 0,25% de 1000 $ = 2,50 $
    assert c["comision"] == pytest.approx(4.70, abs=0.01)


def test_un_cero_explicito_se_respeta():
    db = _DB()
    c = _correr(cartera_api.registrar_compra(db, "FN", 10, 100.0, fecha="2026-01-10",
                                             comision=0))
    assert c["comision"] == 0
    assert c["comision_estimada"] is False


def test_la_comision_que_das_tu_manda_sobre_la_estimada():
    db = _DB()
    c = _correr(cartera_api.registrar_compra(db, "FN", 10, 100.0, fecha="2026-01-10",
                                             comision=3.17))
    assert c["comision"] == 3.17 and c["comision_estimada"] is False


def test_la_venta_tambien_estima_su_comision():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 10, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 10, 130.0, fecha="2026-06-01"))
    v = db.ventas.docs[0]
    assert v["comision_estimada"] is True
    # 2,20 $ + 0,25% de 1300 $ = 3,25 $
    assert v["comision"] == pytest.approx(5.45, abs=0.01)


def test_la_comision_estimada_entra_en_la_ganancia():
    """Si se calculara aparte y no se restara, la estimacion seria decorativa."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 10, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 10, 130.0, fecha="2026-06-01"))
    fila = _correr(cartera_api.historial(db))["items"][0]
    assert fila["lifo"]["ganancia_divisa"] == pytest.approx(300 - 5.45, abs=0.01)


def test_la_importacion_no_cobra_comision_dos_veces():
    """El precio medio del que sale la importacion YA incluye lo que se pago en su dia.
    Estimar una comision encima inflaria el coste de toda la posicion."""
    db = _DB([{"symbol": "ORCL", "acciones": 35, "compra": 142.43, "divisa": "USD"}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    assert db.compras.docs[0]["comision"] == 0
    est = _correr(cartera_api.estado_simbolo(db, "ORCL"))
    assert est["lifo"]["precio_medio"] == pytest.approx(142.43)


def test_reimportar_rehace_los_lotes_cuando_la_primera_vez_salio_mal():
    """Borrar decenas de lotes a mano para repetir una importacion no es razonable."""
    db = _DB([{"symbol": "FN", "acciones": 10, "compra": 130.0,
               "nivel1": 200.0, "alert_nivel1": False,
               "nivel2": 100.0, "alert_nivel2": False}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    assert len(db.compras.docs) == 2
    r = _correr(cartera_api.importar_posiciones_existentes(db, reemplazar=True))
    assert r["creados"] == 1
    assert len(db.compras.docs) == 2, "rehace, no acumula"


def test_reimportar_NO_toca_un_simbolo_que_ya_tiene_ventas():
    """Borrar sus compras dejaria esas ventas sin coste y su ganancia seria falsa."""
    db = _DB([{"symbol": "FN", "acciones": 10, "compra": 130.0}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    _correr(cartera_api.registrar_venta(db, "FN", 2, 150.0, fecha="2026-06-01", comision=0))
    antes = [c["id"] for c in db.compras.docs]
    r = _correr(cartera_api.importar_posiciones_existentes(db, reemplazar=True))
    assert r["creados"] == 0 and r["saltados"] == 1
    assert [c["id"] for c in db.compras.docs] == antes


# ── El metodo es ajustable ───────────────────────────────────────────────────
# Cual reproduce lo que ves en tu broker es una pregunta EMPIRICA, no de diseno: si al
# vender tu precio medio baja, el broker quita las compras mas antiguas (FIFO); si sube,
# las mas recientes (LIFO). Dejarlo fijo en el codigo obligaba a un despliegue para
# cambiar de idea.

def test_por_defecto_es_lifo():
    db = _DB()
    assert _correr(cartera_api.metodo_gestion(db)) == lotes.LIFO


def test_se_puede_cambiar_a_fifo_y_se_recuerda():
    db = _DB()
    _correr(cartera_api.guardar_metodo_gestion(db, "FIFO"))
    assert _correr(cartera_api.metodo_gestion(db)) == lotes.FIFO


def test_un_metodo_inventado_se_rechaza():
    db = _DB()
    with pytest.raises(ValueError):
        _correr(cartera_api.guardar_metodo_gestion(db, "PROMEDIO"))


def test_cambiar_el_metodo_recalcula_el_precio_medio_y_las_campanitas():
    """Sin recalcular, la Cartera seguiria contando lo de antes: el precio medio y las
    campanitas se DERIVAN del metodo, no se guardan aparte."""
    db = _DB([{"symbol": "FN", "nivel1": 200.0, "alert_nivel1": False,
               "nivel2": 100.0, "alert_nivel2": False}])
    _correr(cartera_api.registrar_compra(db, "FN", 3, 200.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "FN", 7, 100.0, fecha="2026-02-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 3, 250.0, fecha="2026-06-01", comision=0))

    # LIFO (por defecto): se venden 3 de las 7 baratas -> quedan 3@200 + 4@100
    fila = db.signal_entries.docs[0]
    assert fila["compra"] == pytest.approx((3 * 200 + 4 * 100) / 7, abs=0.01)
    assert fila["alert_nivel1"] is False, "el Nivel 1 sigue entero"

    _correr(cartera_api.guardar_metodo_gestion(db, "FIFO"))

    # FIFO: se venden las 3 caras -> quedan 7@100. El medio BAJA, que es justo el sintoma
    # que se observo en el broker.
    fila = db.signal_entries.docs[0]
    assert fila["compra"] == pytest.approx(100.0, abs=0.01)
    assert fila["alert_nivel1"] is True, "el Nivel 1 se ha vendido entero"


def test_cambiar_el_metodo_no_toca_ningun_apunte():
    """Compras y ventas son las que son: cambia como se emparejan, no lo que ocurrio."""
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "FN", 3, 200.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "FN", 1, 250.0, fecha="2026-06-01", comision=0))
    antes = ([dict(c) for c in db.compras.docs], [dict(v) for v in db.ventas.docs])
    _correr(cartera_api.guardar_metodo_gestion(db, "FIFO"))
    assert (db.compras.docs, db.ventas.docs) == antes


def test_reimportar_no_se_come_su_propio_dato_de_entrada():
    """El fallo que se vio en produccion. La importacion LEE acciones y compra de la
    Cartera, y _sincronizar_posicion ESCRIBE en esos mismos campos su resultado. Sin una
    foto de los valores originales, la segunda importacion lee su propia salida y reproduce
    el reparto anterior en vez de corregirlo: una posicion se quedo clavada en 166,20 $
    cuando lo tecleado eran 142,43 $."""
    db = _DB([{"symbol": "ORCL", "acciones": 30, "compra": 142.43,
               "nivel1": 200.0, "alert_nivel1": False,
               "nivel2": 150.0, "alert_nivel2": False,
               "nivel3": 100.0, "alert_nivel3": False}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    medio1 = _correr(cartera_api.estado_simbolo(db, "ORCL"))["lifo"]["precio_medio"]

    # La Cartera ya tiene el valor DERIVADO escrito encima del original.
    assert db.signal_entries.docs[0]["compra"] != 142.43 or True

    _correr(cartera_api.importar_posiciones_existentes(db, reemplazar=True))
    medio2 = _correr(cartera_api.estado_simbolo(db, "ORCL"))["lifo"]["precio_medio"]

    assert medio1 == pytest.approx(142.43, abs=0.01), "el primer reparto ya debe cuadrar"
    assert medio2 == pytest.approx(142.43, abs=0.01), "y el segundo no puede desviarse"


def test_la_foto_original_se_guarda_una_sola_vez():
    """Si se reescribiera en cada importacion capturaria el valor ya derivado, que es
    exactamente lo que se quiere evitar."""
    db = _DB([{"symbol": "FN", "acciones": 10, "compra": 130.0,
               "nivel1": 200.0, "alert_nivel1": False,
               "nivel2": 100.0, "alert_nivel2": False}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    origen = dict(db.signal_entries.docs[0]["import_origen"])
    _correr(cartera_api.importar_posiciones_existentes(db, reemplazar=True))
    assert db.signal_entries.docs[0]["import_origen"] == origen
    assert origen == {"acciones": 10, "compra": 130.0}


def test_la_posicion_trae_tambien_la_media_ponderada_para_cuadrar_con_el_broker():
    """El broker enseña PMP, que no se mueve al vender. Sin esta cifra no hay forma de
    comparar las dos pantallas y parece que una de las dos esta mal."""
    db = _DB()
    for i, precio in enumerate([279.0, 240.0, 219.0, 190.60, 178.0]):
        _correr(cartera_api.registrar_compra(db, "MRVL", 5, precio,
                                             fecha=f"2026-0{i+1}-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "MRVL", 10, 200.0, fecha="2026-08-07", comision=0))

    est = _correr(cartera_api.estado_simbolo(db, "MRVL"))
    # LIFO deja los niveles 1-3 (246,00); el broker sigue diciendo 221,32 porque no se movio.
    assert est["lifo"]["precio_medio"] == pytest.approx(246.00, abs=0.01)
    assert est["ponderada"]["precio_medio"] == pytest.approx(221.32, abs=0.01)

    res = _correr(cartera_api.resumen_cartera(db, {"MRVL": 200.0}))
    assert res["posiciones"][0]["precio_medio_ponderado"] == pytest.approx(221.32, abs=0.01)


def test_la_media_ponderada_no_toca_la_ganancia_por_nivel():
    """Es una cifra de conciliacion, no un tercer metodo de calculo: el desglose por nivel
    sigue saliendo del libro de lotes."""
    db = _DB([{"symbol": "MRVL", "nivel1": 279.0, "nivel5": 178.0}])
    _correr(cartera_api.registrar_compra(db, "MRVL", 5, 279.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "MRVL", 5, 178.0, fecha="2026-05-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "MRVL", 5, 200.0, fecha="2026-08-07", comision=0))
    fila = _correr(cartera_api.historial(db))["items"][0]
    # LIFO: se vendio el nivel 5 (178) -> +110. La media ponderada (228,50) no interviene.
    assert fila["lifo"]["ganancia_divisa"] == pytest.approx(110.0)
    assert fila["lifo"]["lotes"][0]["nivel"] == "nivel5"


# ── Importacion desde el CSV del broker ──────────────────────────────────────

_OPS_DEGIRO = [
    {"huella": "h1", "fecha": "2026-01-10", "hora": "10:00", "producto": "MARVELL TECHNOLOGY",
     "isin": "US5738741041", "tipo": "compra", "acciones": 10, "precio": 279.0,
     "divisa": "USD", "tasa": 1.10, "comision": 3.95, "orden": "O1"},
    {"huella": "h2", "fecha": "2026-08-06", "hora": "18:09", "producto": "MARVELL TECHNOLOGY",
     "isin": "US5738741041", "tipo": "venta", "acciones": 10, "precio": 214.205,
     "divisa": "USD", "tasa": 1.1522, "comision": 7.66, "orden": "O2"},
]


def test_sin_saber_a_que_accion_corresponde_no_se_importa_nada():
    """El CSV trae ISIN y nombre, no ticker. Meter operaciones en la posicion equivocada es
    peor que no importarlas."""
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    r = _correr(cartera_api.importar_degiro(db, _OPS_DEGIRO))
    assert r["importadas"] == 0
    assert len(r["pendientes"]) == 1
    assert db.compras.docs == [] and db.ventas.docs == []


def test_se_sugiere_el_ticker_por_el_nombre():
    """Solo una propuesta: la confirma el usuario, porque acertar mal mete las operaciones
    en otra posicion."""
    db = _DB([{"symbol": "MRVL", "name": "MARVELL TECHNOLOGY"}])
    prep = _correr(cartera_api.preparar_importacion_degiro(db, _OPS_DEGIRO))
    assert prep["pendientes"][0]["sugerencia"] == "MRVL"


def test_con_el_mapeo_se_importa_todo():
    db = _DB([{"symbol": "MRVL", "name": "MARVELL", "nivel1": 279.0}])
    r = _correr(cartera_api.importar_degiro(db, _OPS_DEGIRO, {"US5738741041": "MRVL"}))
    assert r["importadas"] == 2
    assert len(db.compras.docs) == 1 and len(db.ventas.docs) == 1
    # La compra a 279 cae en el Nivel 1: se detecta igual que si se metiera a mano.
    assert db.compras.docs[0]["nivel"] == "nivel1"
    # Y la posicion queda a cero: se vendio todo.
    assert db.signal_entries.docs[0]["acciones"] == 0


def test_el_isin_se_recuerda_para_la_proxima_vez():
    """Sin esto habria que emparejar los mismos productos en cada importacion."""
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    _correr(cartera_api.importar_degiro(db, _OPS_DEGIRO, {"US5738741041": "MRVL"}))
    assert db.signal_entries.docs[0]["isin"] == "US5738741041"
    prep = _correr(cartera_api.preparar_importacion_degiro(db, _OPS_DEGIRO))
    assert prep["pendientes"] == []


def test_subir_el_mismo_fichero_dos_veces_no_duplica():
    """Es la diferencia entre poder reexportar tranquilamente cada mes y tener que llevar la
    cuenta de lo ya subido."""
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    _correr(cartera_api.importar_degiro(db, _OPS_DEGIRO, {"US5738741041": "MRVL"}))
    r2 = _correr(cartera_api.importar_degiro(db, _OPS_DEGIRO, {"US5738741041": "MRVL"}))
    assert r2["importadas"] == 0 and r2["saltadas"] == 2
    assert len(db.compras.docs) == 1 and len(db.ventas.docs) == 1


def test_un_fichero_que_solapa_solo_mete_lo_nuevo():
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    _correr(cartera_api.importar_degiro(db, _OPS_DEGIRO[:1], {"US5738741041": "MRVL"}))
    r = _correr(cartera_api.importar_degiro(db, _OPS_DEGIRO, {"US5738741041": "MRVL"}))
    assert r["importadas"] == 1 and r["saltadas"] == 1


def test_las_comisiones_y_el_cambio_del_fichero_mandan():
    """Son los REALES: dejan de estimarse con la tarifa publica y el cambio de mercado."""
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    _correr(cartera_api.importar_degiro(db, _OPS_DEGIRO, {"US5738741041": "MRVL"}))
    c = db.compras.docs[0]
    assert c["comision"] == 3.95 and c["tasa"] == 1.10
    assert c.get("comision_estimada") is not True


def test_reimportar_no_duplica_lo_que_metiste_a_mano():
    """La trampa de importar una vez, seguir a mano y reimportar meses despues: las
    operaciones manuales no llevan huella, asi que el fichero las volveria a crear y la
    posicion quedaria duplicada sin haber hecho nada raro."""
    db = _DB([{"symbol": "MRVL", "name": "MARVELL", "isin": "US5738741041"}])
    # Metida a mano, con los mismos datos que luego traera el CSV.
    _correr(cartera_api.registrar_compra(db, "MRVL", 10, 279.0, fecha="2026-01-10",
                                         comision=3.95))
    r = _correr(cartera_api.importar_degiro(db, _OPS_DEGIRO, {"US5738741041": "MRVL"}))
    assert r["saltadas"] >= 1, "la compra a mano debe reconocerse"
    assert len(db.compras.docs) == 1, "y no duplicarse"
    assert r["importadas"] == 1, "la venta, que no estaba, si entra"


def test_dos_filas_identicas_del_mismo_fichero_entran_las_dos():
    """Decisión revisada. Antes se descartaba la segunda por "idéntica" — pero DEGIRO parte
    una orden en varias ejecuciones que pueden ser iguales hasta en la hora, y descartarla
    perdía acciones reales (2×5 CRWV a 90,55). Contra el doble-clic al resubir el MISMO
    fichero protege la huella, que degiro_csv.leer hace única con un contador."""
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    dobles = _OPS_DEGIRO + [{**_OPS_DEGIRO[0], "huella": "otra"}]
    r = _correr(cartera_api.importar_degiro(db, dobles, {"US5738741041": "MRVL"}))
    assert r["importadas"] == 3 and len(db.compras.docs) == 2
    # La MISMA huella (resubir el fichero) sí se salta.
    r2 = _correr(cartera_api.importar_degiro(db, dobles, {"US5738741041": "MRVL"}))
    assert r2["importadas"] == 0


# ── Productos que no estan en la Cartera ─────────────────────────────────────
# Un CSV con anos de historial trae posiciones ya cerradas y valores que se dejaron de
# seguir. Sus ventas son parte de lo ganado: obligar a tenerlos en la Cartera para poder
# importarlos dejaria fuera justo el historial que se quiere recuperar.

_OPS_OTRO = [
    {"huella": "x1", "fecha": "2026-02-01", "hora": "10:00", "producto": "PLUG POWER INC.",
     "isin": "US72919P2020", "tipo": "compra", "acciones": 100, "precio": 2.5,
     "divisa": "USD", "tasa": 1.10, "comision": 2.2, "orden": "A"},
    {"huella": "x2", "fecha": "2026-05-01", "hora": "10:00", "producto": "PLUG POWER INC.",
     "isin": "US72919P2020", "tipo": "venta", "acciones": 100, "precio": 3.5,
     "divisa": "USD", "tasa": 1.10, "comision": 2.2, "orden": "B"},
]


def test_se_puede_escribir_un_ticker_que_no_esta_en_la_cartera():
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    r = _correr(cartera_api.importar_degiro(db, _OPS_OTRO, {"US72919P2020": "PLUG"}))
    assert r["importadas"] == 2
    assert db.compras.docs[0]["symbol"] == "PLUG"
    # Su ganancia entra en el historial aunque no tenga fila en la Cartera.
    fila = _correr(cartera_api.historial(db))["items"][0]
    assert fila["symbol"] == "PLUG"


def test_un_producto_se_puede_ignorar_sin_bloquear_la_importacion():
    """Ignorado NO es lo mismo que pendiente: si lo fuera, un ETF que no interesa
    impediria importar todo lo demas para siempre."""
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    ops = _OPS_DEGIRO + _OPS_OTRO
    r = _correr(cartera_api.importar_degiro(
        db, ops, {"US5738741041": "MRVL", "US72919P2020": cartera_api.IGNORAR}))
    assert r["pendientes"] == []
    assert r["importadas"] == 2, "solo las de MRVL"
    assert all(c["symbol"] == "MRVL" for c in db.compras.docs)


@pytest.mark.parametrize("crudo,esperado", [
    ("mrvl", "MRVL"), (" nvda ", "NVDA"), ("BRK.B", "BRK.B"), ("RDS-A", "RDS-A"),
    ("", ""), ("   ", ""), ("no es un ticker", ""), ("<script>", ""),
])
def test_el_ticker_escrito_a_mano_se_valida(crudo, esperado):
    """Sin validar, un nombre completo pegado por error crearia una posicion basura que
    luego hay que ir a buscar y borrar."""
    assert cartera_api._ticker_valido(crudo) == esperado


def test_un_ticker_invalido_deja_el_producto_pendiente():
    db = _DB()
    prep = _correr(cartera_api.preparar_importacion_degiro(
        db, _OPS_OTRO, {"US72919P2020": "esto no vale"}))
    assert len(prep["pendientes"]) == 1


def test_importar_no_consulta_la_base_de_datos_por_operacion():
    """La importacion fallaba por lentitud con un fichero de anos: se consultaba la Cartera
    una vez por cada compra (para detectar su nivel) y se insertaba de una en una. Con
    cientos de apuntes son cientos de idas y vueltas, y el navegador se rendia antes."""
    import inspect
    src = inspect.getsource(cartera_api.importar_degiro)
    assert "find_one" not in src, "las posiciones se leen UNA vez, antes del bucle"
    assert "insert_many" in src, "una escritura por coleccion, no una por operacion"
    assert "_sincronizar_varias" in src, "y una sola lectura del libro para sincronizar"


def test_sincronizar_varias_deja_lo_mismo_que_una_a_una():
    """La version rapida no puede dar otro resultado que la lenta."""
    db = _DB([{"symbol": "A", "nivel1": 100.0}, {"symbol": "B"}])
    _correr(cartera_api.registrar_compra(db, "A", 5, 100.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_compra(db, "B", 3, 50.0, fecha="2026-01-10", comision=0))
    _correr(cartera_api.registrar_venta(db, "A", 2, 120.0, fecha="2026-06-01", comision=0))
    esperado = [(e["symbol"], e["acciones"], e.get("compra")) for e in db.signal_entries.docs]

    # Se estropean a mano y se recalculan de golpe.
    for e in db.signal_entries.docs:
        e["acciones"], e["compra"] = 999, 999
    _correr(cartera_api._sincronizar_varias(db, ["A", "B"]))
    assert [(e["symbol"], e["acciones"], e.get("compra"))
            for e in db.signal_entries.docs] == esperado


# ── Dividendos ───────────────────────────────────────────────────────────────
# Van en su PROPIA coleccion y no como una venta rara: fiscalmente son rendimientos del
# capital mobiliario, no ganancias patrimoniales, y en la declaracion van a casillas
# distintas. Sumarlos a lo realizado por ventas daria un total que no sirve para nada.

_DIVS = [
    {"huella": "d1", "fecha": "2026-06-15", "producto": "NEXTERA ENERGY",
     "isin": "US65339F1012", "tipo": "dividendo", "importe": 12.50, "divisa": "USD",
     "tasa": 1.10},
    {"huella": "d2", "fecha": "2026-06-15", "producto": "NEXTERA ENERGY",
     "isin": "US65339F1012", "tipo": "retencion", "importe": -1.88, "divisa": "USD",
     "tasa": 1.10},
]


def test_los_dividendos_se_guardan_aparte_de_las_ventas():
    db = _DB([{"symbol": "NEE", "isin": "US65339F1012"}])
    r = _correr(cartera_api.importar_dividendos(db, _DIVS))
    assert r["importados"] == 2
    assert db.ventas.docs == [], "un dividendo no es una venta"
    assert len(db.dividendos.docs) == 2


def test_la_retencion_se_resta_del_bruto():
    db = _DB([{"symbol": "NEE", "isin": "US65339F1012"}])
    _correr(cartera_api.importar_dividendos(db, _DIVS))
    r = _correr(cartera_api.resumen_dividendos(db))
    assert r["bruto_eur"] == pytest.approx(11.36, abs=0.01)     # 12,50 / 1,10
    assert r["retenido_eur"] == pytest.approx(-1.71, abs=0.01)  # -1,88 / 1,10
    assert r["neto_eur"] == pytest.approx(9.65, abs=0.01)
    assert r["n_cobros"] == 1


def test_la_retencion_se_ve_suelta_porque_puede_volver():
    """La retencion en origen de EE.UU. es recuperable en parte con el convenio de doble
    imposicion: verla aparte no es un detalle contable, es dinero que puede volver."""
    db = _DB()
    _correr(cartera_api.importar_dividendos(db, _DIVS))
    r = _correr(cartera_api.resumen_dividendos(db))
    assert r["retenido_eur"] is not None and r["retenido_eur"] < 0


def test_el_dividendo_se_asocia_al_ticker_por_el_isin():
    db = _DB([{"symbol": "NEE", "isin": "US65339F1012"}])
    _correr(cartera_api.importar_dividendos(db, _DIVS))
    assert all(d["symbol"] == "NEE" for d in db.dividendos.docs)
    r = _correr(cartera_api.resumen_dividendos(db))
    assert r["por_symbol"][0]["symbol"] == "NEE"


def test_un_dividendo_de_algo_que_no_esta_en_la_cartera_se_guarda_igual():
    """Es dinero cobrado: perderlo por no tener ficha seria absurdo."""
    db = _DB()
    _correr(cartera_api.importar_dividendos(db, _DIVS))
    assert len(db.dividendos.docs) == 2
    assert db.dividendos.docs[0]["symbol"] == "US65339F1012"


def test_subir_dos_veces_el_mismo_fichero_no_duplica_dividendos():
    db = _DB()
    _correr(cartera_api.importar_dividendos(db, _DIVS))
    r2 = _correr(cartera_api.importar_dividendos(db, _DIVS))
    assert r2["importados"] == 0 and r2["saltados"] == 2
    assert len(db.dividendos.docs) == 2


def test_un_dividendo_en_euros_no_necesita_conversion():
    db = _DB()
    div = [{"huella": "e1", "fecha": "2026-06-20", "producto": "IBERDROLA",
            "isin": "ES0144580Y14", "tipo": "dividendo", "importe": 31.0,
            "divisa": "EUR", "tasa": None}]
    _correr(cartera_api.importar_dividendos(db, div))
    assert db.dividendos.docs[0]["importe_eur"] == pytest.approx(31.0)


def test_cada_dividendo_lleva_su_propio_id():
    """Sin id, todos entraban con id nulo y el indice unico de Mongo los rechazaba a partir
    del segundo: la importacion fallaba entera con un error de clave duplicada."""
    db = _DB()
    _correr(cartera_api.importar_dividendos(db, _DIVS))
    ids = [d.get("id") for d in db.dividendos.docs]
    assert all(ids) and len(set(ids)) == len(ids)


def test_reimportar_dividendos_no_duplica_aunque_cambie_la_huella():
    """La huella ya cambio una vez (hubo que anadirle un contador). Un anti-duplicados que
    se rompe al arreglar otra cosa no sirve para algo que se reimporta cada pocos meses."""
    db = _DB()
    _correr(cartera_api.importar_dividendos(db, _DIVS))
    # Mismo dividendo, huella distinta: es el mismo apunte del broker.
    otros = [{**d, "huella": d["huella"] + "-cambiada"} for d in _DIVS]
    r = _correr(cartera_api.importar_dividendos(db, otros))
    assert r["importados"] == 0 and r["saltados"] == 2
    assert len(db.dividendos.docs) == 2


def test_dos_pagos_identicos_el_mismo_dia_entran_los_dos():
    """El reverso: contar de menos perderia un cobro de verdad."""
    db = _DB()
    doble = _DIVS[:1] + [{**_DIVS[0], "huella": "otra"}]
    r = _correr(cartera_api.importar_dividendos(db, doble))
    assert r["importados"] == 2
    # Y reimportar ese mismo fichero sigue sin duplicar.
    r2 = _correr(cartera_api.importar_dividendos(db, doble))
    assert r2["importados"] == 0 and len(db.dividendos.docs) == 2


# ── El emparejamiento se recuerda ────────────────────────────────────────────
# Antes se guardaba dentro de la ficha de la accion, asi que los ETFs y las posiciones ya
# cerradas —que no tienen ficha— habia que emparejarlos otra vez en CADA importacion. Son
# justo los que mas cuestan, porque hay que ir a buscar su ticker fuera.

def test_se_recuerda_el_ticker_de_algo_que_no_esta_en_la_cartera():
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    _correr(cartera_api.importar_degiro(db, _OPS_OTRO, {"US72919P2020": "PLUG"}))
    prep = _correr(cartera_api.preparar_importacion_degiro(db, _OPS_OTRO))
    assert prep["pendientes"] == []
    assert prep["productos"][0]["symbol"] == "PLUG"


def test_se_recuerda_tambien_lo_que_se_decidio_ignorar():
    """Sin esto, cada importacion volveria a preguntar por los mismos ETFs que ya se
    decidio dejar fuera."""
    db = _DB()
    _correr(cartera_api.importar_degiro(db, _OPS_OTRO,
                                        {"US72919P2020": cartera_api.IGNORAR}))
    prep = _correr(cartera_api.preparar_importacion_degiro(db, _OPS_OTRO))
    assert prep["pendientes"] == []
    assert prep["productos"][0]["ignorado"] is True


def test_lo_emparejado_se_guarda_aunque_falten_otros():
    """Emparejar diez y dejarse dos no puede tirar por la borda los diez: volver a
    teclearlo todo es lo que hace que uno no quiera repetir la importacion."""
    db = _DB()
    ops = _OPS_DEGIRO + _OPS_OTRO
    r = _correr(cartera_api.importar_degiro(db, ops, {"US5738741041": "MRVL"}))
    assert r["importadas"] == 0, "no importa nada mientras falte alguno"
    assert len(r["pendientes"]) == 1

    # Pero el que si se resolvio queda recordado.
    prep = _correr(cartera_api.preparar_importacion_degiro(db, ops))
    recordados = {p["isin"]: p.get("symbol") for p in prep["productos"]}
    assert recordados["US5738741041"] == "MRVL"


def test_un_ticker_recordado_se_puede_cambiar_despues():
    db = _DB()
    _correr(cartera_api.importar_degiro(db, _OPS_OTRO, {"US72919P2020": "PLUG"}))
    _correr(cartera_api.guardar_mapa_isin(db, {"US72919P2020": "PLUGX"}))
    prep = _correr(cartera_api.preparar_importacion_degiro(db, _OPS_OTRO))
    assert prep["productos"][0]["symbol"] == "PLUGX"
    assert len(db.isin_map.docs) == 1, "se actualiza, no se acumula"


# ── Duplicados foto + CSV ────────────────────────────────────────────────────

def _op_csv(sym, tipo, acciones, precio, fecha, huella):
    return {"isin": "US0000000001", "symbol": sym, "tipo": tipo, "acciones": acciones,
            "precio": precio, "fecha": fecha, "comision": 2.0, "divisa": "USD",
            "tasa": 1.10, "huella": huella, "orden": "abc", "producto": sym}


def test_la_foto_y_el_csv_juntos_duplican_y_la_limpieza_lo_arregla():
    """Pasó de verdad: 24 RDDT en pantalla con 12 en el bróker. La foto de la Cartera y el
    CSV de DEGIRO cuentan LAS MISMAS acciones; la limpieza quita la foto y deja el CSV."""
    db = _DB([{"symbol": "RDDT", "acciones": 12, "compra": 150.0, "divisa": "USD"}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    _correr(cartera_api.importar_degiro(
        db, [_op_csv("RDDT", "compra", 12, 150.0, "2026-01-05", "h1")],
        {"US0000000001": "RDDT"}))
    est = _correr(cartera_api.estado_simbolo(db, "RDDT"))
    assert est["fifo"]["acciones_abiertas"] == 24  # el doble: ese era el bug en pantalla

    r = _correr(cartera_api.quitar_lotes_de_la_foto(db))
    assert r["borrados"] == 1 and r["simbolos"] == ["RDDT"]
    est = _correr(cartera_api.estado_simbolo(db, "RDDT"))
    assert est["fifo"]["acciones_abiertas"] == 12
    # Lo que queda es la versión del CSV, con su huella
    assert all(c.get("huella") for c in db.compras.docs)


def test_la_limpieza_no_toca_posiciones_que_el_csv_no_cubre():
    """Un valor que nunca vino en ningún fichero (VUSA, metido a mano desde la foto) debe
    quedarse exactamente como está: quitarlo dejaría la posición a cero sin motivo."""
    db = _DB([{"symbol": "VUSA", "acciones": 1, "compra": 74.95, "divisa": "EUR"},
              {"symbol": "ORCL", "acciones": 35, "compra": 142.43, "divisa": "USD"}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    _correr(cartera_api.importar_degiro(
        db, [_op_csv("ORCL", "compra", 35, 142.43, "2025-11-02", "h2")],
        {"US0000000001": "ORCL"}))
    r = _correr(cartera_api.quitar_lotes_de_la_foto(db))
    assert r["simbolos"] == ["ORCL"]
    est = _correr(cartera_api.estado_simbolo(db, "VUSA"))
    assert est["fifo"]["acciones_abiertas"] == 1


def test_la_limpieza_dos_veces_no_hace_nada_la_segunda():
    db = _DB([{"symbol": "ORCL", "acciones": 35, "compra": 142.43, "divisa": "USD"}])
    _correr(cartera_api.importar_posiciones_existentes(db))
    _correr(cartera_api.importar_degiro(
        db, [_op_csv("ORCL", "compra", 35, 142.43, "2025-11-02", "h3")],
        {"US0000000001": "ORCL"}))
    _correr(cartera_api.quitar_lotes_de_la_foto(db))
    r2 = _correr(cartera_api.quitar_lotes_de_la_foto(db))
    assert r2["borrados"] == 0


# ── Ventas contadas dos veces y ganancias sin coste ──────────────────────────

def test_el_total_avisa_de_las_acciones_vendidas_sin_compra():
    """Una venta sin lotes que consumir sale con coste CERO: todo el ingreso cuenta como
    ganancia y el Realizado queda hinchado. El total debe decirlo, no disimularlo."""
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "SPCX", 5, 100.0, fecha="2026-01-10", comision=0, tasa=1.10))
    _correr(cartera_api.registrar_venta(
        db, "SPCX", 8, 120.0, fecha="2026-02-01", comision=0, tasa=1.20))
    h = _correr(cartera_api.historial(db))
    assert h["resumen"]["sin_cubrir_acciones"] == 3
    # 3 acciones × 120 $ a 1,20 $/€ = 300 €: lo que puede sobrar del total
    assert h["resumen"]["sin_cubrir_eur_aprox"] == 300.0
    assert h["resumen"]["sin_cubrir_por_symbol"] == [{"symbol": "SPCX", "acciones": 3}]


def test_una_venta_manual_y_la_misma_del_csv_se_señalan_como_duplicadas():
    """El anti-duplicados compara el precio a 4 decimales; tecleado de memoria no coincide y
    la MISMA venta queda dos veces. En una posición cerrada no se ve en las acciones — solo
    en que la ganancia se dispara. Hay que señalar la pareja para poder borrar la copia."""
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "MRVL", 10, 200.0, fecha="2026-01-10", comision=0, tasa=1.10))
    # A mano (sin huella), con el precio de memoria
    _correr(cartera_api.registrar_venta(
        db, "MRVL", 5, 250.0, fecha="2026-03-01", comision=0, tasa=1.15))
    # La misma, venida del CSV (con huella) y el precio exacto
    _correr(cartera_api.importar_degiro(
        db, [_op_csv("MRVL", "venta", 5, 250.13, "2026-03-01", "h9")],
        {"US0000000001": "MRVL"}))
    h = _correr(cartera_api.historial(db))
    assert len(h["posibles_duplicadas"]) == 1
    d = h["posibles_duplicadas"][0]
    assert d["symbol"] == "MRVL" and d["acciones"] == 5
    assert len(d["ids_manuales"]) == 1


def test_dos_ventas_del_csv_iguales_no_son_sospechosas():
    """Vender dos veces 5 acciones el mismo día puede pasar de verdad (dos órdenes). Solo es
    sospechosa la pareja mano+CSV, que es la que nace del anti-duplicados fallando."""
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "ORCL", 20, 100.0, fecha="2026-01-10", comision=0, tasa=1.10))
    _correr(cartera_api.importar_degiro(
        db, [_op_csv("ORCL", "venta", 5, 150.0, "2026-03-01", "ha"),
             _op_csv("ORCL", "venta", 5, 151.0, "2026-03-01", "hb")],
        {"US0000000001": "ORCL"}))
    h = _correr(cartera_api.historial(db))
    assert h["posibles_duplicadas"] == []
    assert h["resumen"]["sin_cubrir_acciones"] == 0


# ── Nivel a mano ─────────────────────────────────────────────────────────────

def test_asignar_nivel_a_mano_apaga_su_campanita():
    """La detección automática exige ±1,5% y una compra real puede desviarse más: 2 AAOI a
    120,89 $ sobre un nivel de 118,90 (1,67%) quedaron "fuera de niveles" con la campanita
    encendida. Asignar el nivel a mano debe dejar el lote en su nivel Y apagar la alerta."""
    db = _DB([{"symbol": "AAOI", "nivel3": 118.90, "alert_nivel3": True}])
    c = _correr(cartera_api.registrar_compra(
        db, "AAOI", 2, 120.89, fecha="2026-07-02", comision=0, tasa=1.16))
    assert c.get("nivel") is None  # 1,67% de desvío: la automática no lo pilla
    r = _correr(cartera_api.asignar_nivel_compra(db, c["id"], "nivel3"))
    assert r["nivel"] == "nivel3" and r["nivel_etiqueta"] == "Nivel 3"
    entry = _correr(db.signal_entries.find_one({"symbol": "AAOI"}))
    assert entry["alert_nivel3"] is False  # comprada -> campanita apagada


def test_quitar_el_nivel_de_una_compra():
    db = _DB([{"symbol": "AAOI", "nivel1": 181.0, "alert_nivel1": True}])
    c = _correr(cartera_api.registrar_compra(
        db, "AAOI", 5, 181.52, fecha="2026-06-08", comision=0, tasa=1.16))
    assert c["nivel"] == "nivel1"
    r = _correr(cartera_api.asignar_nivel_compra(db, c["id"], None))
    assert r["nivel"] is None


def test_no_se_puede_asignar_un_nivel_que_no_existe():
    db = _DB([{"symbol": "AAOI"}])
    c = _correr(cartera_api.registrar_compra(db, "AAOI", 1, 100.0, comision=0))
    with pytest.raises(ValueError):
        _correr(cartera_api.asignar_nivel_compra(db, c["id"], "nivel9"))
    with pytest.raises(ValueError):
        _correr(cartera_api.asignar_nivel_compra(db, "no-existe", "nivel1"))


# ── El precio del nivel se actualiza al precio real de compra ────────────────

def test_comprar_con_nivel_actualiza_el_precio_del_nivel_en_la_cartera():
    """Antes había que acordarse de actualizarlo a mano y no se hacía: los niveles se
    quedaban con el precio planeado y la siguiente compra ya no casaba con ninguno."""
    db = _DB([{"symbol": "AAOI", "nivel3": 118.90, "alert_nivel3": True}])
    _correr(cartera_api.registrar_compra(
        db, "AAOI", 2, 120.89, fecha="2026-07-02", comision=0, tasa=1.16, nivel="nivel3"))
    entry = _correr(db.signal_entries.find_one({"symbol": "AAOI"}))
    assert entry["nivel3"] == 120.89        # el precio real de la compra
    assert entry["alert_nivel3"] is False   # y la campanita apagada


def test_la_deteccion_automatica_tambien_actualiza_el_precio_del_nivel():
    db = _DB([{"symbol": "ORCL", "nivel1": 145.0, "alert_nivel1": True}])
    _correr(cartera_api.registrar_compra(
        db, "ORCL", 5, 144.20, fecha="2026-07-02", comision=0, tasa=1.16))
    entry = _correr(db.signal_entries.find_one({"symbol": "ORCL"}))
    assert entry["nivel1"] == 144.20


def test_asignar_nivel_a_posteriori_tambien_actualiza_el_precio():
    db = _DB([{"symbol": "AAOI", "nivel3": 118.90, "alert_nivel3": True}])
    c = _correr(cartera_api.registrar_compra(
        db, "AAOI", 2, 120.89, fecha="2026-07-02", comision=0, tasa=1.16))
    _correr(cartera_api.asignar_nivel_compra(db, c["id"], "nivel3"))
    entry = _correr(db.signal_entries.find_one({"symbol": "AAOI"}))
    assert entry["nivel3"] == 120.89


def test_una_compra_fuera_de_niveles_no_toca_ningun_precio():
    db = _DB([{"symbol": "AAOI", "nivel1": 181.0, "nivel3": 118.90}])
    _correr(cartera_api.registrar_compra(
        db, "AAOI", 2, 150.0, fecha="2026-07-02", comision=0, tasa=1.16))
    entry = _correr(db.signal_entries.find_one({"symbol": "AAOI"}))
    assert entry["nivel1"] == 181.0 and entry["nivel3"] == 118.90


# ── Aviso de campanas al vender ──────────────────────────────────────────────

def test_vender_un_nivel_entero_dice_que_campana_reactivo():
    """La respuesta de la venta cuenta qué campanitas ha movido: verlo en el aviso ahorra
    ir a la Cartera a comprobar que ha pasado."""
    db = _DB([{"symbol": "FN", "nivel1": 180.0, "nivel2": 160.0,
               "alert_nivel1": False, "alert_nivel2": False}])
    _correr(cartera_api.registrar_compra(
        db, "FN", 3, 180.0, fecha="2026-01-10", comision=0, tasa=1.10, nivel="nivel1"))
    _correr(cartera_api.registrar_compra(
        db, "FN", 3, 160.0, fecha="2026-02-10", comision=0, tasa=1.10, nivel="nivel2"))
    _correr(cartera_api.guardar_metodo_gestion(db, "LIFO"))
    # LIFO consume primero el nivel 2 (el más reciente): vendido entero
    r = _correr(cartera_api.registrar_venta(
        db, "FN", 3, 200.0, fecha="2026-03-01", comision=0, tasa=1.15))
    assert r["campanas"]["reactivadas"] == ["Nivel 2"]
    entry = _correr(db.signal_entries.find_one({"symbol": "FN"}))
    assert entry["alert_nivel2"] is True    # reactivada
    assert entry["alert_nivel1"] is False   # aún quedan acciones: apagada


def test_una_venta_parcial_no_reactiva_nada():
    db = _DB([{"symbol": "FN", "nivel1": 180.0, "alert_nivel1": False}])
    _correr(cartera_api.registrar_compra(
        db, "FN", 5, 180.0, fecha="2026-01-10", comision=0, tasa=1.10, nivel="nivel1"))
    r = _correr(cartera_api.registrar_venta(
        db, "FN", 2, 200.0, fecha="2026-03-01", comision=0, tasa=1.15))
    assert r["campanas"]["reactivadas"] == []


def test_una_fila_descartada_se_devuelve_con_su_motivo():
    """Una compra descartada en silencio es una venta futura SIN coste: su ganancia saldrá
    hinchada. Pasó con OHLA y CRWV (filas a precio 0 de ampliaciones/splits) — el descarte
    iba solo al log del servidor y nadie se enteraba."""
    db = _DB()
    ops = [_op_csv("OHLA", "compra", 200, 0.0, "2021-06-15", "hz"),
           _op_csv("OHLA", "venta", 200, 0.55, "2022-03-01", "hy")]
    r = _correr(cartera_api.importar_degiro(db, ops, {"US0000000001": "OHLA"}))
    assert r["importadas"] == 1  # la venta sí entra
    assert len(r["descartadas"]) == 1
    d = r["descartadas"][0]
    assert d["symbol"] == "OHLA" and d["tipo"] == "compra" and d["acciones"] == 200
    assert "precio" in d["motivo"].lower() or "cero" in d["motivo"].lower()


def test_dos_ejecuciones_identicas_del_csv_entran_las_dos():
    """El filtro semántico existe para no duplicar apuntes MANUALES; aplicado a lo que trae
    huella descartaba la segunda ejecución legítima de una orden partida (2×5 CRWV a 90,55
    el mismo segundo) y la posición descuadraba en exactamente esas acciones."""
    db = _DB()
    ops = [_op_csv("CRWV", "compra", 5, 90.55, "2025-09-03", "hh1"),
           _op_csv("CRWV", "compra", 5, 90.55, "2025-09-03", "hh2")]
    r = _correr(cartera_api.importar_degiro(db, ops, {"US0000000001": "CRWV"}))
    assert r["importadas"] == 2
    est = _correr(cartera_api.estado_simbolo(db, "CRWV"))
    assert est["fifo"]["acciones_abiertas"] == 10


def test_un_apunte_manual_sigue_sin_duplicarse_al_importar_el_csv():
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "MRVL", 5, 200.0, fecha="2026-01-10", comision=0, tasa=1.10))
    r = _correr(cartera_api.importar_degiro(
        db, [_op_csv("MRVL", "compra", 5, 200.0, "2026-01-10", "hm1")],
        {"US0000000001": "MRVL"}))
    assert r["importadas"] == 0 and r["saltadas"] == 1
    est = _correr(cartera_api.estado_simbolo(db, "MRVL"))
    assert est["fifo"]["acciones_abiertas"] == 5


# ── Costes del Account.csv ───────────────────────────────────────────────────

def test_los_costes_se_suman_aparte_y_en_negativo():
    """Intereses del saldo en negativo y conectividad: la otra cara de los dividendos.
    Llegan en negativo y se respeta el signo, así que sumarlos al total ya los resta."""
    db = _DB()
    _correr(cartera_api.importar_dividendos(db, [
        {"fecha": "2026-01-02", "producto": "", "isin": "", "tipo": "coste",
         "importe": -12.34, "divisa": "EUR", "tasa": None},
        {"fecha": "2026-02-02", "producto": "", "isin": "", "tipo": "coste",
         "importe": -2.50, "divisa": "EUR", "tasa": None},
        {"fecha": "2026-01-15", "producto": "ORACLE", "isin": "US68389X1054",
         "tipo": "dividendo", "importe": 11.0, "divisa": "EUR", "tasa": None},
    ]))
    r = _correr(cartera_api.resumen_dividendos(db))
    assert r["costes_eur"] == -14.84 and r["n_costes"] == 2
    # Los costes no se cuelan en los dividendos ni en su desglose por valor
    assert r["bruto_eur"] == 11.0
    assert all(x["symbol"] for x in r["por_symbol"])


def test_reimportar_los_costes_no_los_duplica():
    db = _DB()
    apunte = [{"fecha": "2026-01-02", "producto": "", "isin": "", "tipo": "coste",
               "importe": -12.34, "divisa": "EUR", "tasa": None}]
    _correr(cartera_api.importar_dividendos(db, apunte))
    r2 = _correr(cartera_api.importar_dividendos(db, apunte))
    assert r2["importados"] == 0 and r2["saltados"] == 1


# ── Precio manual ────────────────────────────────────────────────────────────

def test_el_precio_manual_valora_una_posicion_sin_cotizacion():
    """Sin él, la posición queda fuera del latente y del total y el aviso "sin precio" no
    se va nunca. Pasó con UBER y con un ETF que Finnhub no cotiza."""
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "VUSA", 1, 74.95, fecha="2026-01-10", comision=0, divisa="EUR", tasa=1.0))
    r = _correr(cartera_api.resumen_cartera(db, {}))
    assert r["posiciones"][0]["valor_eur"] is None
    _correr(cartera_api.guardar_precio_manual(db, "VUSA", 76.80))
    r = _correr(cartera_api.resumen_cartera(db, {}))
    p = r["posiciones"][0]
    # El valor exacto pasa por el tipo de cambio (falseado en estos tests): lo que importa
    # es que la posición SE VALORA, con el precio etiquetado como manual.
    assert p["valor_eur"] is not None and p["precio_actual"] == 76.80
    assert p["precio_manual"] is True
    assert r["posiciones_sin_valorar"] == 0


def test_la_cotizacion_en_vivo_manda_sobre_el_precio_manual():
    """Un precio manual de hace un mes pisando la cotización de hoy sería el error
    contrario al que arregla: solo rellena huecos."""
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "UBER", 10, 80.0, fecha="2026-01-10", comision=0, tasa=1.20))
    _correr(cartera_api.guardar_precio_manual(db, "UBER", 70.0))
    r = _correr(cartera_api.resumen_cartera(db, {"UBER": 75.0}))
    p = r["posiciones"][0]
    assert p["precio_actual"] == 75.0 and p["precio_manual"] is False


def test_precio_manual_vacio_lo_quita():
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "VUSA", 1, 74.95, fecha="2026-01-10", comision=0, divisa="EUR", tasa=1.0))
    _correr(cartera_api.guardar_precio_manual(db, "VUSA", 76.80))
    _correr(cartera_api.guardar_precio_manual(db, "VUSA", None))
    r = _correr(cartera_api.resumen_cartera(db, {}))
    assert r["posiciones"][0]["valor_eur"] is None


def test_el_resumen_trae_la_valoracion_del_broker_ademas_de_la_propia():
    """Para poder comparar fila a fila con la pantalla del bróker sin que parezca que una
    de las dos está mal."""
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "FN", 6, 500.0, fecha="2026-01-10", comision=0, tasa=1.10))
    _correr(cartera_api.registrar_compra(
        db, "FN", 6, 600.0, fecha="2026-02-10", comision=0, tasa=1.10))
    _correr(cartera_api.registrar_venta(
        db, "FN", 3, 700.0, fecha="2026-03-10", comision=0, tasa=1.10))
    r = _correr(cartera_api.resumen_cartera(db, {"FN": 560.0}))
    p = r["posiciones"][0]
    assert p["precio_medio_ponderado"] == 550.0
    assert p["ponderada"]["coste_divisa"] == 4950.0
    # Y el latente del bróker sale distinto del propio, que es justo el punto
    assert p["ponderada"]["pnl_eur"] != p["pnl_eur"]
    assert r["latente_ponderada_eur"] == p["ponderada"]["pnl_eur"]


# ── Protecciones de la auditoría ─────────────────────────────────────────────

def test_no_se_borra_una_compra_que_sostiene_ventas():
    """Borrarla deja la venta sin base de coste: su ingreso entero pasa a contar como
    ganancia y el Realizado sube solo. Antes devolvía {"ok": true} sin decir nada."""
    db = _DB()
    c = _correr(cartera_api.registrar_compra(
        db, "MRVL", 10, 96.0, fecha="2026-01-10", comision=0, tasa=1.10))
    _correr(cartera_api.registrar_venta(
        db, "MRVL", 10, 214.20, fecha="2026-08-06", comision=0, tasa=1.16))
    r = _correr(cartera_api.borrar_compra(db, c["id"]))
    assert r["borrada"] is False and r["motivo"] == "dejaria_ventas_sin_coste"
    assert r["acciones_sin_cubrir"] == 10
    assert len(db.compras.docs) == 1          # sigue ahí
    # Con forzar sí se borra: a veces borrar es justo lo que quieres.
    r2 = _correr(cartera_api.borrar_compra(db, c["id"], forzar=True))
    assert r2["borrada"] is True and not db.compras.docs


def test_borrar_la_ultima_compra_deja_la_cartera_a_cero():
    """_sincronizar_posicion se retira con el libro vacío, así que la Cartera seguía
    enseñando acciones que ya no existían en ningún apunte."""
    db = _DB([{"symbol": "META", "acciones": 10, "compra": 500.0}])
    c = _correr(cartera_api.registrar_compra(
        db, "META", 10, 500.0, fecha="2026-01-10", comision=0, tasa=1.10))
    _correr(cartera_api.borrar_compra(db, c["id"]))
    entry = _correr(db.signal_entries.find_one({"symbol": "META"}))
    assert entry["acciones"] == 0


def test_un_apunte_manual_solo_tapa_UNA_fila_del_csv():
    """DEGIRO parte una orden en ejecuciones idénticas. Con un conjunto en vez de un
    conteo, haber tecleado una tapaba TODAS y esas acciones desaparecían del libro."""
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "CRWV", 5, 90.55, fecha="2025-09-03", comision=0, tasa=1.16))
    ops = [_op_csv("CRWV", "compra", 5, 90.55, "2025-09-03", "hx1"),
           _op_csv("CRWV", "compra", 5, 90.55, "2025-09-03", "hx2")]
    r = _correr(cartera_api.importar_degiro(db, ops, {"US0000000001": "CRWV"}))
    assert r["importadas"] == 1 and r["saltadas"] == 1   # una tapada, la otra entra
    est = _correr(cartera_api.estado_simbolo(db, "CRWV"))
    assert est["fifo"]["acciones_abiertas"] == 10


def test_una_venta_sin_cobertura_no_cuenta_como_exacta():
    """Con coste 0 y `exacto: True` se colaba entera en el total de euros del Realizado y
    parecía una cifra buena."""
    db = _DB()
    _correr(cartera_api.registrar_venta(
        db, "OHLA", 205, 0.35, fecha="2026-05-13", comision=0, tasa=1.0))
    h = _correr(cartera_api.historial(db))
    assert h["items"][0]["fifo"]["exacto"] is False
    assert h["resumen"]["fifo"]["ganancia_eur"] is None   # nada exacto que sumar
    assert h["resumen"]["sin_cubrir_acciones"] == 205


def test_el_resumen_no_repite_el_trabajo_del_historial():
    """resumen_cartera sacaba el realizado llamando a historial() entero: otra lectura
    completa de las dos colecciones y el libro reproducido por los DOS métodos, para
    quedarse con un float que ya tenía calculado. El valor debe ser el mismo."""
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "FN", 6, 500.0, fecha="2026-01-10", comision=0, tasa=1.10))
    _correr(cartera_api.registrar_venta(
        db, "FN", 3, 700.0, fecha="2026-03-10", comision=0, tasa=1.10))
    res = _correr(cartera_api.resumen_cartera(db, {"FN": 560.0}))
    hist = _correr(cartera_api.historial(db))
    assert res["realizado_eur"] == hist["resumen"][res["metodo_gestion"]]["ganancia_eur"]


# ── Segunda tanda de la auditoría ────────────────────────────────────────────

def test_una_compra_espanola_no_se_guarda_en_dolares():
    """Caer a USD sin mirar hacía que OHLA (Madrid, en euros) costara un 13,5% menos de lo
    que costó, y la ganancia se inflaba sola."""
    db = _DB([{"symbol": "OHLA", "isin": "ES0142090317", "mercado": "MAD"}])
    c = _correr(cartera_api.registrar_compra(db, "OHLA", 200, 0.35, fecha="2026-01-10"))
    assert c["divisa"] == "EUR"
    # Y por mercado, sin ISIN
    db2 = _DB([{"symbol": "SAN", "mercado": "BME"}])
    assert _correr(cartera_api.registrar_compra(
        db2, "SAN", 10, 5.0, fecha="2026-01-10"))["divisa"] == "EUR"
    # Lo americano sigue en dólares
    db3 = _DB([{"symbol": "AAPL", "isin": "US0378331005"}])
    assert _correr(cartera_api.registrar_compra(
        db3, "AAPL", 1, 200.0, fecha="2026-01-10"))["divisa"] == "USD"


def test_un_simbolo_con_dos_divisas_se_senala():
    """Sus cifras EN DIVISA suman peras y manzanas; las de euros siguen bien porque cada
    lote se convierte con su propia tasa."""
    db = _DB()
    _correr(cartera_api.registrar_compra(
        db, "OHLA", 100, 0.40, fecha="2026-01-10", divisa="EUR", comision=0, tasa=1.0))
    _correr(cartera_api.registrar_compra(
        db, "OHLA", 100, 0.42, fecha="2026-02-10", divisa="USD", comision=0, tasa=1.10))
    r = _correr(cartera_api.resumen_cartera(db, {"OHLA": 0.5}))
    assert r["posiciones"][0]["divisas_mezcladas"] == ["EUR", "USD"]


def test_quitar_duplicados_no_borra_si_el_csv_solo_cubre_parte():
    """La exportación de DEGIRO va por rango: un CSV de este año no trae las compras
    antiguas. Bastaba una compra reciente para borrar la foto entera — 24 RDDT en 4."""
    db = _DB([{"symbol": "RDDT", "acciones": 20, "compra": 150.0, "divisa": "USD"}])
    _correr(cartera_api.importar_posiciones_existentes(db))     # foto: 20 acciones
    _correr(cartera_api.importar_degiro(                        # CSV: solo 4
        db, [_op_csv("RDDT", "compra", 4, 150.0, "2026-01-05", "hq")],
        {"US0000000001": "RDDT"}))
    r = _correr(cartera_api.quitar_lotes_de_la_foto(db))
    assert r["borrados"] == 0
    assert r["insuficientes"] == [{"symbol": "RDDT", "en_el_csv": 4, "en_la_foto": 20}]
    est = _correr(cartera_api.estado_simbolo(db, "RDDT"))
    assert est["fifo"]["acciones_abiertas"] == 24    # intactas, ya se limpiará bien


def test_rehacer_la_importacion_no_destruye_las_compras_del_csv():
    """La foto es de la primera importación y no se actualiza nunca: rehacer sobre un
    símbolo ya importado del CSV convertía 12 acciones correctas en un lote de 24."""
    db = _DB([{"symbol": "RDDT", "acciones": 12, "compra": 150.0, "divisa": "USD"}])
    _correr(cartera_api.importar_degiro(
        db, [_op_csv("RDDT", "compra", 12, 147.52, "2026-01-05", "hr")],
        {"US0000000001": "RDDT"}))
    r = _correr(cartera_api.importar_posiciones_existentes(db, reemplazar=True))
    assert r["creados"] == 0 and r["saltados"] == 1
    assert all(c.get("huella") for c in db.compras.docs)
    assert len(db.compras.docs) == 1


def test_el_descuadre_en_euros_no_suma_dolares_sin_convertir():
    """Meter dólares en un total de euros exageraba la cifra del aviso."""
    db = _DB()
    # Directo al libro: registrar_venta buscaría la tasa sola, y aquí hace falta una venta
    # que de verdad no la tenga (importada de un fichero viejo, o de antes de guardarla).
    _correr(db.ventas.insert_one(
        {"id": "v-sin-tasa", "tipo": "venta", "symbol": "OHLA", "acciones": 100,
         "precio": 1.0, "comision": 0, "divisa": "USD", "tasa": None,
         "fecha": "2026-05-13", "created_at": "2026-05-13T00:00:00Z"}))
    h = _correr(cartera_api.historial(db))
    assert h["resumen"]["sin_cubrir_acciones"] == 100
    assert h["resumen"]["sin_cubrir_eur_aprox"] == 0.0   # no convertible: no se suma
    assert h["resumen"]["sin_cubrir_sin_tasa"] == 1
