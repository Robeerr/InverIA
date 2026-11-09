"""La salud de la cartera devuelve también la tendencia de cada posición.

La columna Estado de Cartera la necesita y ya se leía aquí para la estructura: sin
devolverla, la pantalla enseñaba «Sin datos» en las once posiciones.
"""
import asyncio

import server


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, _n):
        return list(self.docs)


class _Coleccion:
    def find(self, *_a, **_k):
        return _Cursor([])


class _DB:
    cartera_historico = _Coleccion()


def test_la_salud_devuelve_la_tendencia_de_cada_posicion(monkeypatch):
    async def _entries(_db):
        return [{"symbol": "ORCL", "last_price": 119.27, "sector": "Technology"},
                {"symbol": "META", "last_price": 641.96, "sector": "Communication Services"}]

    async def _resumen(_db, _precios):
        return {"posiciones": [{"symbol": "ORCL", "valor_eur": 4895.0},
                               {"symbol": "META", "valor_eur": 2200.0}]}

    tend = {"ORCL": "BAJISTA", "META": "ALCISTA"}
    monkeypatch.setattr(server.signal_table, "list_entries", _entries)
    monkeypatch.setattr(server.cartera_api, "resumen_cartera", _resumen)
    monkeypatch.setattr(server.market_data, "tendencia_de", lambda s: tend[s])
    monkeypatch.setattr(server, "db", _DB())

    r = asyncio.run(server._salud_de_la_cartera())
    assert r["tendencias"] == {"ORCL": "BAJISTA", "META": "ALCISTA"}
    assert r["salud"] is not None


def test_una_tendencia_que_falla_no_se_inventa(monkeypatch):
    async def _entries(_db):
        return [{"symbol": "ORCL", "last_price": 119.27}]

    async def _resumen(_db, _precios):
        return {"posiciones": [{"symbol": "ORCL", "valor_eur": 4895.0}]}

    def _falla(_s):
        raise RuntimeError("sin red")

    monkeypatch.setattr(server.signal_table, "list_entries", _entries)
    monkeypatch.setattr(server.cartera_api, "resumen_cartera", _resumen)
    monkeypatch.setattr(server.market_data, "tendencia_de", _falla)
    monkeypatch.setattr(server, "db", _DB())

    assert asyncio.run(server._salud_de_la_cartera())["tendencias"] == {}
