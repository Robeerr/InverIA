"""«Sería una compra» solo si el motor ha demostrado ganar dinero comprando.

Hoy imprimía «· sería una compra» en cada nivel de compra cercano, mientras el Track record
medía que las señales de compra pierden un 0,8 % por operación después de costes. Que el
precio esté en tu nivel es un hecho y se sigue diciendo; llamarlo compra es una
recomendación, y esa solo se hace con una esperanza positiva medida.
"""
import hoy
from tests.test_hoy import caliente, zona


def _vigilar(**kw):
    return hoy.tarjeta_nivel(caliente(), zona(), **kw)["que_vigilar"]


def test_con_esperanza_negativa_no_dice_que_seria_una_compra():
    t = _vigilar(esperanza_motor=-0.8)
    assert "sería una compra" not in t
    assert "tu nivel de compra" in t
    assert "0.8%" in t


def test_con_esperanza_positiva_lo_sigue_llamando_compra():
    assert "sería una compra" in _vigilar(esperanza_motor=1.5)


def test_sin_track_record_medido_no_recomienda_comprar():
    t = _vigilar()
    assert "sería una compra" not in t
    assert "tu nivel de compra" in t


def test_una_venta_no_depende_del_track_record_de_compras():
    t = hoy.tarjeta_nivel(caliente(action="VENTA"), zona(), esperanza_motor=-0.8)["que_vigilar"]
    assert "sería una venta" in t


def test_la_tarjeta_dice_si_la_compra_esta_respaldada():
    t = hoy.tarjeta_nivel(caliente(), zona(), esperanza_motor=-0.8)
    assert t["datos"]["compra_respaldada"] is False
    assert hoy.tarjeta_nivel(caliente(), zona(), esperanza_motor=2.0)["datos"]["compra_respaldada"] is True


# ── De dónde sale la esperanza en la portada ─────────────────────────────────

import pytest


@pytest.fixture(autouse=True)
def _cache_limpia(monkeypatch):
    import server
    server._cache._store.clear()
    monkeypatch.setattr(server, "_esperanza_calculando", False)
    yield
    server._cache._store.clear()


def test_la_portada_lee_la_esperanza_del_track_record_ya_calculado():
    import asyncio
    import server
    server._cache.set("track_record_180", {"esperanza": -0.8}, ttl=300)
    assert asyncio.run(server._esperanza_motor()) == -0.8


def test_una_esperanza_positiva_con_poca_muestra_no_respalda_la_compra():
    import asyncio
    import server
    server._cache.set("track_record_180", {"esperanza": 3.0, "aciertos": 2, "fallos": 0}, ttl=300)
    assert asyncio.run(server._esperanza_motor()) is None
    server._cache.set("track_record_180", {"esperanza": 3.0, "aciertos": 40, "fallos": 20}, ttl=300)
    assert asyncio.run(server._esperanza_motor()) == 3.0


def test_sin_track_record_calculado_no_inventa_y_lo_pide_por_detras(monkeypatch):
    import asyncio
    import server
    import track_record
    llamadas = []

    async def _calcular(db, days=180, **_k):
        llamadas.append(days)
        return {"esperanza": 2.0, "aciertos": 40, "fallos": 20}

    monkeypatch.setattr(track_record, "compute_track_record", _calcular)

    async def _dos_visitas():
        primera = await server._esperanza_motor()
        await asyncio.sleep(0)          # deja correr el cálculo de fondo
        await asyncio.sleep(0)
        segunda = await server._esperanza_motor()
        return primera, segunda

    primera, segunda = asyncio.run(_dos_visitas())
    assert primera is None              # la primera portada no espera al cálculo
    assert segunda == 2.0               # la siguiente ya lo tiene
    assert llamadas == [180]
