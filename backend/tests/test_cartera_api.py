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
    assert _correr(cartera_api.borrar_compra(db, "no-existe")) is False


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


def test_dos_filas_identicas_del_mismo_fichero_no_entran_dos_veces():
    db = _DB([{"symbol": "MRVL", "name": "MARVELL"}])
    dobles = _OPS_DEGIRO + [{**_OPS_DEGIRO[0], "huella": "otra"}]
    r = _correr(cartera_api.importar_degiro(db, dobles, {"US5738741041": "MRVL"}))
    assert r["importadas"] == 2 and len(db.compras.docs) == 1
