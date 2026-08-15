"""Comprar algo que NO estaba en la Cartera crea su fila, y la crea SIN niveles.

El problema que arregla: el precio de mercado de una posición lo escribe el worker de
señales recorriendo `db.signal_entries`. Una compra de un valor que no estaba en la
Cartera no tenía fila, así que no cotizaba: había que teclear el precio a mano o
inventarse unos niveles solo para que el valor se actualizara.

Lo que se fija aquí, y que es justo lo que hace que la solución no sea peor que el
problema:

  · la fila se crea sola al registrar la compra, con `active: True`
  · nivel1..5 quedan a None — el precio de compra NO es un nivel de estrategia
  · el worker le pone precio igualmente, porque no filtra por niveles
  · y no dispara ninguna alerta, porque no hay ningún nivel que cruzar
  · si la fila ya existía, no se toca (los niveles de verdad no se pisan)

Ejecutar:  cd backend && pytest tests/test_compra_sin_niveles.py -v
"""
import asyncio

import pytest

import cartera_api
import signal_table

from test_cartera_api import _DB, _Coleccion, _correr  # noqa: F401  (fakes ya probados)


class _Cooldowns(_Coleccion):
    async def create_index(self, *a, **k):
        return None


@pytest.fixture(autouse=True)
def ajuste_limpio():
    cartera_api._metodo_cache.update({"valor": None, "ts": 0.0})
    yield
    cartera_api._metodo_cache.update({"valor": None, "ts": 0.0})


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    monkeypatch.setattr(cartera_api.fx, "tasa_en_fecha", lambda d, f: 1.10)
    monkeypatch.setattr(cartera_api.fx, "tasa_actual", lambda d: 1.20)


NIVELES = ("nivel1", "nivel2", "nivel3", "nivel4", "nivel5")


@pytest.fixture(autouse=True)
def sin_cotizacion(monkeypatch):
    """Por defecto, sin red: la fila nace sin precio. Los tests que miran la cotización
    inicial la ponen ellos, para que se vea que es esa llamada y no otra cosa."""
    monkeypatch.setattr(signal_table.market_data, "get_quote_fast", lambda s: None)
    monkeypatch.setattr(signal_table.market_data, "get_quote", lambda s: None)


def _con_cotizacion(monkeypatch, precio, previous_close=None, change=None):
    q = {"price": precio, "previous_close": previous_close, "change_percent": change}
    monkeypatch.setattr(signal_table.market_data, "get_quote_fast", lambda s: q)


# ── La fila se crea ──────────────────────────────────────────────────────────

def test_comprar_algo_que_no_esta_en_cartera_crea_su_fila():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "aem", 10, 180.0, fecha="2026-08-13",
                                         comision=0))
    filas = [e for e in db.signal_entries.docs if e["symbol"] == "AEM"]
    assert len(filas) == 1, "sin fila en la Cartera, la posición no coge precio nunca"
    assert filas[0]["active"] is True, "el worker solo mira las filas activas"


def test_la_fila_nace_sin_niveles():
    """El precio de compra y los niveles de estrategia son cosas distintas.

    Poner la compra como nivel1 haría que la posición se etiquetara "NIVEL 1" y fuera
    indistinguible de una donde el nivel lo decidió el análisis.
    """
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    fila = db.signal_entries.docs[0]
    for n in NIVELES:
        assert fila[n] is None, f"{n} no debe salir de la nada al comprar"
    assert fila["deseado"] is None
    assert 180.0 not in [fila[n] for n in NIVELES], "el precio de compra NO es un nivel"


def test_la_compra_conserva_su_precio_real():
    db = _DB()
    c = _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    assert c["precio"] == 180.0
    assert c["nivel"] is None, "sin niveles no hay nivel que detectar: queda 'fuera de niveles'"
    fila = db.signal_entries.docs[0]
    assert fila["acciones"] == 10
    assert fila["compra"] == 180.0, "el precio medio de lo abierto sí se deriva del libro"


def test_la_divisa_deducida_se_guarda_en_la_fila():
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "OHLA", 100, 0.5, divisa="EUR", comision=0))
    assert db.signal_entries.docs[0]["divisa"] == "EUR"


def test_si_la_fila_ya_existe_no_se_crea_otra_ni_se_tocan_sus_niveles():
    db = _DB([{"id": "x", "symbol": "MU", "nivel1": 180.0, "nivel2": None, "nivel3": None,
               "nivel4": None, "nivel5": None, "deseado": None, "active": True}])
    _correr(cartera_api.registrar_compra(db, "MU", 1, 921.0, comision=0))
    filas = [e for e in db.signal_entries.docs if e["symbol"] == "MU"]
    assert len(filas) == 1, "una compra no puede duplicar la fila de la Cartera"
    assert filas[0]["nivel1"] == 180.0, "los niveles que ya existían no se pisan"


# ── Precio desde el primer segundo ───────────────────────────────────────────

def test_la_fila_nace_con_precio(monkeypatch):
    """Sin esto hay que esperar al worker, que no gira ni de noche ni en fin de semana:
    una compra registrada un sábado se quedaba con "—" hasta el lunes."""
    _con_cotizacion(monkeypatch, 191.25, previous_close=188.0, change=1.73)
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    fila = db.signal_entries.docs[0]
    assert fila["last_price"] == 191.25
    assert fila["previous_close"] == 188.0
    assert fila["daily_change_percent"] == 1.73


def test_si_no_hay_cotizacion_la_compra_se_guarda_igual(monkeypatch):
    """La compra ya ocurrió. Negarla porque no se pudo leer el precio sería perder el
    apunte por lo de menos."""
    def _revienta(s):
        raise RuntimeError("Finnhub 503")

    monkeypatch.setattr(signal_table.market_data, "get_quote_fast", _revienta)
    monkeypatch.setattr(signal_table.market_data, "get_quote", _revienta)
    db = _DB()
    c = _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    assert c["precio"] == 180.0
    assert len(db.compras.docs) == 1
    assert db.signal_entries.docs[0]["last_price"] is None


def test_un_precio_de_cero_no_se_guarda(monkeypatch):
    """Un 0 en la Cartera se lee como "vale nada", que es una afirmación distinta de "no
    se sabe" y encima cuadra el latente con una cifra falsa."""
    _con_cotizacion(monkeypatch, 0)
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    assert db.signal_entries.docs[0]["last_price"] is None


def test_la_cotizacion_no_se_pide_si_la_fila_ya_existia(monkeypatch):
    """Pedirla en cada compra gastaría cuota para pisar lo que el worker ya mantiene."""
    llamadas = []
    monkeypatch.setattr(signal_table.market_data, "get_quote_fast",
                        lambda s: llamadas.append(s) or {"price": 999.0})
    db = _DB([{"id": "x", "symbol": "MU", "nivel1": 180.0, "active": True,
               "last_price": 921.0}])
    _correr(cartera_api.registrar_compra(db, "MU", 1, 921.0, comision=0))
    assert llamadas == []
    assert db.signal_entries.docs[0]["last_price"] == 921.0


# ── El worker: precio sí, alertas no ─────────────────────────────────────────

class _Parar(Exception):
    """Corta el bucle del worker tras un ciclo, para poder observarlo."""


def _preparar_worker(monkeypatch, precio):
    """Deja el worker en horario regular, con red falsa y sin dormir de verdad."""
    monkeypatch.setattr(signal_table, "_extended_session_active", lambda: True)
    monkeypatch.setattr(signal_table, "is_market_open", lambda: True)
    monkeypatch.setattr(signal_table.market_data, "enter_finnhub_background", lambda: None)
    monkeypatch.setattr(signal_table.market_data, "get_quote_fast",
                        lambda s: {"price": precio, "previous_close": precio,
                                   "change_percent": 0.0})
    monkeypatch.setattr(signal_table.market_data, "get_quote", lambda s: None)

    disparos = []

    async def _no_alertar(*a, **k):
        disparos.append(a)

    monkeypatch.setattr(signal_table, "_fire_alert", _no_alertar)

    real_sleep = asyncio.sleep

    async def _sleep(delay, *a, **k):
        if delay == 0:
            return await real_sleep(0)
        raise _Parar()

    monkeypatch.setattr(signal_table.asyncio, "sleep", _sleep)
    return disparos


def _un_ciclo(db, monkeypatch, precio):
    disparos = _preparar_worker(monkeypatch, precio)

    async def _correr_worker():
        try:
            await signal_table.signal_worker_loop(db, interval=60)
        except _Parar:
            pass

    asyncio.run(_correr_worker())
    return disparos


def _db_con_posicion_sin_niveles():
    db = _DB()
    db.alert_cooldowns = _Cooldowns()
    _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    return db


def test_el_worker_pone_precio_a_una_posicion_sin_niveles(monkeypatch):
    """Es el punto entero del cambio: sin esto la fila no sirve de nada."""
    db = _db_con_posicion_sin_niveles()
    assert db.signal_entries.docs[0].get("last_price") is None
    _un_ciclo(db, monkeypatch, 191.25)
    assert db.signal_entries.docs[0]["last_price"] == 191.25


def test_una_posicion_sin_niveles_no_dispara_ninguna_alerta(monkeypatch):
    """Aunque el precio se mueva y el mercado esté abierto: no hay nivel que cruzar."""
    db = _db_con_posicion_sin_niveles()
    db.signal_entries.docs[0]["last_price"] = 250.0   # baseline: viene de MUY arriba
    disparos = _un_ciclo(db, monkeypatch, 120.0)      # y se desploma
    assert disparos == [], "una fila sin niveles no puede generar alertas de nivel"
    assert db.alert_cooldowns.docs == [], "ni siquiera debe quemar un cooldown"
