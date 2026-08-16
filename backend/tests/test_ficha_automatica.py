"""Nombre, mercado y sector se detectan solos. El riesgo NO.

Esa asimetría es el contenido de este archivo, no un detalle. Nombre, mercado y sector
son hechos publicados: se consultan. "ALTO/MEDIO/BAJO" es la clasificación del inversor
del usuario y ninguna API la devuelve; derivarla de la beta pondría un número con pinta
de criterio justo en la casilla donde se lee el criterio de otra persona.

Lo demás que se fija:

  · solo se rellenan HUECOS — el sector que escribió el usuario ("TECH GROWTH") es su
    taxonomía y dice algo que "Technology" no dice
  · un código de mercado que no se reconoce se deja VACÍO, no se escribe en crudo: de él
    se deduce la divisa, y un mercado mal puesto convierte mal el coste en euros
  · si el proveedor no sabe el nombre devuelve el propio símbolo; eso no se guarda

Ejecutar:  cd backend && pytest tests/test_ficha_automatica.py -v
"""
import asyncio

import pytest

import cartera_api
import signal_table

from test_cartera_api import _DB


def _correr(coro):
    return asyncio.run(coro)


PERFIL = {"name": "Agnico Eagle Mines Limited", "exchange": "NYQ",
          "sector": "Basic Materials", "price": 191.25}


@pytest.fixture(autouse=True)
def ajuste_limpio():
    cartera_api._metodo_cache.update({"valor": None, "ts": 0.0})
    yield
    cartera_api._metodo_cache.update({"valor": None, "ts": 0.0})


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    monkeypatch.setattr(cartera_api.fx, "tasa_en_fecha", lambda d, f: 1.10)
    monkeypatch.setattr(cartera_api.fx, "tasa_actual", lambda d: 1.20)
    monkeypatch.setattr(signal_table.market_data, "get_quote_fast", lambda s: None)
    monkeypatch.setattr(signal_table.market_data, "get_quote", lambda s: None)


def _perfil(monkeypatch, datos=PERFIL):
    monkeypatch.setattr(signal_table.market_data, "get_quote", lambda s: datos)


# ── Traducción del mercado ───────────────────────────────────────────────────

def test_los_codigos_de_yfinance_se_traducen():
    """yfinance no dice "NASDAQ": dice "NMS". Escribir el código crudo cambiaría un hueco
    por un jeroglífico."""
    assert signal_table.mercado_legible("NYQ") == "NYSE"
    assert signal_table.mercado_legible("NMS") == "NASDAQ"
    assert signal_table.mercado_legible("MCE") == "MAD"


def test_un_mercado_desconocido_se_deja_vacio():
    """De `mercado` se deduce la DIVISA (_DIVISA_POR_MERCADO). Escribir uno equivocado
    convierte mal el coste en euros y la ganancia se infla sola."""
    assert signal_table.mercado_legible("XXXX") == ""
    assert signal_table.mercado_legible(None) == ""


def test_el_mercado_deducido_sirve_para_la_divisa():
    """Los nombres que se guardan tienen que ser los que cartera_api sabe leer, o la
    traducción no habría servido de nada."""
    assert cartera_api._divisa_de(None, {"mercado": signal_table.mercado_legible("MCE")}) == "EUR"
    assert cartera_api._divisa_de(None, {"mercado": signal_table.mercado_legible("LSE")}) == "GBP"


# ── Al comprar algo nuevo ────────────────────────────────────────────────────

def test_comprar_algo_nuevo_rellena_nombre_mercado_y_sector(monkeypatch):
    _perfil(monkeypatch)
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    fila = db.signal_entries.docs[0]
    assert fila["name"] == "Agnico Eagle Mines Limited"
    assert fila["mercado"] == "NYSE"
    assert fila["sector"] == "Basic Materials"


def test_el_riesgo_no_se_inventa(monkeypatch):
    """La frontera. Es la clasificación de tu inversor, no un dato de mercado."""
    _perfil(monkeypatch, {**PERFIL, "beta": 2.4})
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    assert db.signal_entries.docs[0]["riesgo"] == ""


def test_si_el_proveedor_no_sabe_el_nombre_no_se_guarda_el_simbolo(monkeypatch):
    """Devuelven el propio ticker cuando no saben nada. Guardarlo deja "AEM · AEM"."""
    _perfil(monkeypatch, {"name": "AEM", "exchange": "NYQ", "sector": ""})
    db = _DB()
    _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    fila = db.signal_entries.docs[0]
    assert fila["name"] == ""
    assert fila["mercado"] == "NYSE", "lo que sí se sabe se guarda igual"


def test_sin_red_la_compra_se_guarda_igual(monkeypatch):
    def _revienta(s):
        raise RuntimeError("yfinance caído")

    monkeypatch.setattr(signal_table.market_data, "get_quote", _revienta)
    db = _DB()
    c = _correr(cartera_api.registrar_compra(db, "AEM", 10, 180.0, comision=0))
    assert c["precio"] == 180.0 and len(db.compras.docs) == 1


# ── El repaso de las filas que ya existían ───────────────────────────────────

def test_el_repaso_no_pisa_lo_que_ya_habia(monkeypatch):
    """"TECH GROWTH" lo escribió el usuario y dice algo que "Basic Materials" no dice.
    Sustituirlo sería perder información con cara de mejorarla."""
    _perfil(monkeypatch)
    db = _DB([{"id": "x", "symbol": "AEM", "name": "Agnico", "mercado": "",
               "sector": "TECH GROWTH", "riesgo": "MEDIO"}])
    _correr(signal_table.completar_fichas(db))
    fila = db.signal_entries.docs[0]
    assert fila["sector"] == "TECH GROWTH"
    assert fila["name"] == "Agnico"
    assert fila["mercado"] == "NYSE", "el único hueco que había sí se rellena"


def test_el_repaso_dice_cuales_no_pudo_completar(monkeypatch):
    """Un recuento que solo cuenta los éxitos deja creer que ya está todo, y esas filas
    se quedan vacías para siempre."""
    monkeypatch.setattr(signal_table.market_data, "get_quote", lambda s: None)
    db = _DB([{"id": "x", "symbol": "AEM", "name": "", "mercado": "", "sector": ""}])
    r = _correr(signal_table.completar_fichas(db))
    assert r["revisadas"] == 1
    assert r["completadas"] == []
    assert r["sin_datos"] == ["AEM"]


def test_el_repaso_no_toca_las_fichas_completas(monkeypatch):
    llamadas = []
    monkeypatch.setattr(signal_table.market_data, "get_quote",
                        lambda s: llamadas.append(s) or PERFIL)
    db = _DB([{"id": "x", "symbol": "MU", "name": "Micron", "mercado": "NASDAQ",
               "sector": "TECH"}])
    r = _correr(signal_table.completar_fichas(db))
    assert r["revisadas"] == 0 and llamadas == []
