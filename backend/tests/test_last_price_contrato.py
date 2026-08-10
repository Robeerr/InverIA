"""El contrato de frescura de `last_price`.

El worker de señales escribe `last_price` y `updated_at` en signal_entries, pero SOLO
durante la sesión extendida (L-V 04:00-20:00 ET). Fuera de ella duerme, así que el
precio guardado puede tener 3 horas un martes por la noche y 49 un domingo.

Por eso un umbral en minutos a secas sería un error: rechazaría el precio todo el fin
de semana, y justo entonces pedir una cotización nueva devolvería EL MISMO cierre del
viernes, gastando cuota para obtener lo que ya teníamos.

El fondo: fuera de sesión, un precio de 49 horas no es viejo — es el precio actual.
Lo que caduca un precio no es el reloj, es que el mercado haya cotizado después.

    Sesión activa   -> vale si `updated_at` está dentro de 10 minutos.
    Sesión cerrada  -> vale si `updated_at` es posterior al último cierre.
    Ninguna de las dos -> no se calcula nada, y la tarjeta lo dice.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("fastapi", reason="requiere fastapi")
import server  # noqa: E402

ET = ZoneInfo("America/New_York")


def entry(minutos_atras=None, marca=None, precio=100.0):
    if marca is None:
        marca = datetime.now(timezone.utc) - timedelta(minutes=minutos_atras or 0)
    return {"last_price": precio, "updated_at": marca.isoformat()}


# ── Sesión abierta · la frontera de los 10 minutos ──────────────────────────
def test_sesion_abierta_y_precio_de_9_59_es_valido():
    ahora = datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc)  # martes
    e = entry(marca=ahora - timedelta(minutes=9, seconds=59))
    precio, motivo = server.precio_para_niveles(e, ahora=ahora, sesion_activa=True)
    assert precio == 100.0 and motivo == "fresco"


def test_sesion_abierta_y_precio_de_10_01_es_invalido():
    ahora = datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc)
    e = entry(marca=ahora - timedelta(minutes=10, seconds=1))
    precio, motivo = server.precio_para_niveles(e, ahora=ahora, sesion_activa=True)
    assert precio is None and motivo == "precio_desfasado"


def test_la_frontera_exacta_de_10_minutos_entra():
    ahora = datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc)
    e = entry(marca=ahora - timedelta(seconds=server.LAST_PRICE_MAX_EDAD))
    assert server.precio_para_niveles(e, ahora=ahora, sesion_activa=True)[0] == 100.0


def test_el_margen_tolera_varios_ciclos_del_worker():
    """No es un número redondo elegido a ojo: con 40 símbolos el ciclo del worker es de
    ~96 s, así que 10 minutos absorben unos seis ciclos perdidos."""
    import signal_table
    import market_data
    ciclo = max(signal_table.SIGNAL_WORKER_INTERVAL, 40 * 60 / market_data.get_finnhub_limiter().bg_cap)
    assert server.LAST_PRICE_MAX_EDAD >= ciclo * 4


# ── Sesión cerrada · vale lo posterior al último cierre ─────────────────────
def test_sesion_cerrada_y_precio_posterior_al_cierre_es_valido_aunque_sea_viejo():
    """Domingo por la tarde con un precio del viernes: 49 horas, y es el precio actual.
    No ha habido negociación desde entonces."""
    ahora = datetime(2026, 8, 16, 21, 0, tzinfo=ET)          # domingo
    del_viernes = datetime(2026, 8, 14, 19, 55, tzinfo=ET)   # antes del cierre del viernes
    precio, motivo = server.precio_para_niveles(
        entry(marca=del_viernes), ahora=ahora, sesion_activa=False)
    assert precio == 100.0 and motivo == "cierre_vigente"
    assert (ahora - del_viernes).total_seconds() / 3600 > 48, "el caso tiene que ser viejo de verdad"


def test_sesion_cerrada_y_precio_anterior_al_ultimo_cierre_es_invalido():
    """Un precio del jueves visto el sábado: el viernes SÍ hubo sesión, así que ese
    precio ya no refleja el último que existió."""
    ahora = datetime(2026, 8, 15, 18, 0, tzinfo=ET)          # sábado
    del_jueves = datetime(2026, 8, 13, 15, 0, tzinfo=ET)
    precio, motivo = server.precio_para_niveles(
        entry(marca=del_jueves), ahora=ahora, sesion_activa=False)
    assert precio is None and motivo == "precio_desfasado"


def test_de_noche_entre_semana_vale_el_cierre_del_mismo_dia():
    ahora = datetime(2026, 8, 11, 23, 0, tzinfo=ET)          # martes noche
    de_la_tarde = datetime(2026, 8, 11, 19, 50, tzinfo=ET)
    assert server.precio_para_niveles(
        entry(marca=de_la_tarde), ahora=ahora, sesion_activa=False)[1] == "cierre_vigente"


def test_de_madrugada_vale_el_cierre_de_la_vispera():
    ahora = datetime(2026, 8, 12, 3, 0, tzinfo=ET)           # miércoles de madrugada
    del_martes = datetime(2026, 8, 11, 19, 50, tzinfo=ET)
    assert server.precio_para_niveles(
        entry(marca=del_martes), ahora=ahora, sesion_activa=False)[1] == "cierre_vigente"


@pytest.mark.parametrize("ahora,esperado", [
    (datetime(2026, 8, 11, 23, 0, tzinfo=ET), datetime(2026, 8, 11, 4, 0, tzinfo=ET)),  # mar noche -> sesión del martes
    (datetime(2026, 8, 12, 3, 0, tzinfo=ET), datetime(2026, 8, 11, 4, 0, tzinfo=ET)),   # mié 03:00 -> aún no ha abierto: la del martes
    (datetime(2026, 8, 15, 18, 0, tzinfo=ET), datetime(2026, 8, 14, 4, 0, tzinfo=ET)),  # sábado -> la del viernes
    (datetime(2026, 8, 16, 21, 0, tzinfo=ET), datetime(2026, 8, 14, 4, 0, tzinfo=ET)),  # domingo -> la del viernes
    (datetime(2026, 8, 17, 3, 0, tzinfo=ET), datetime(2026, 8, 14, 4, 0, tzinfo=ET)),   # lun 03:00 -> la del viernes
])
def test_el_inicio_de_la_ultima_sesion_se_calcula_bien(ahora, esperado):
    assert server._inicio_de_la_ultima_sesion(ahora) == esperado


def test_se_compara_contra_el_inicio_de_sesion_y_no_contra_el_cierre():
    """El fallo que cazaron estos tests: el worker escribe DURANTE la sesión, así que su
    última anotación del viernes es de las 19:59, ANTERIOR al cierre de las 20:00.
    Comparando contra el cierre, ningún precio lo superaría nunca y el contrato
    rechazaría todo fuera de horario — justo el caso que venía a resolver."""
    ahora = datetime(2026, 8, 16, 21, 0, tzinfo=ET)              # domingo
    ultima_anotacion = datetime(2026, 8, 14, 19, 59, tzinfo=ET)  # viernes, antes del cierre
    assert ultima_anotacion < datetime(2026, 8, 14, 20, 0, tzinfo=ET)
    assert server.precio_para_niveles(
        entry(marca=ultima_anotacion), ahora=ahora, sesion_activa=False)[0] == 100.0


# ── Sin precio · y el símbolo recién añadido ────────────────────────────────
@pytest.mark.parametrize("e", [
    {}, None,
    {"last_price": None, "updated_at": "2026-08-11T19:00:00+00:00"},
    {"last_price": 100.0},                       # sin marca de tiempo
    {"last_price": 100.0, "updated_at": "no es una fecha"},
])
def test_sin_precio_utilizable_no_se_calcula_nada(e):
    precio, motivo = server.precio_para_niveles(e, sesion_activa=True)
    assert precio is None and motivo == "sin_precio"


def test_un_simbolo_recien_anadido_queda_sin_datos_hasta_tener_precio():
    """Aceptado a conciencia: es preferible a enseñar una señal calculada sobre un
    precio que no sabemos si es actual."""
    ahora = datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc)
    recien = {"symbol": "NUEVA", "active": True}          # el worker aún no ha pasado
    assert server.precio_para_niveles(recien, ahora=ahora, sesion_activa=True) == (None, "sin_precio")
    # Y en cuanto el worker escribe, pasa a valer.
    ya = entry(marca=ahora - timedelta(seconds=30))
    assert server.precio_para_niveles(ya, ahora=ahora, sesion_activa=True)[0] == 100.0


def test_una_marca_sin_zona_horaria_se_interpreta_como_utc():
    """Defensa: si alguien guardara la fecha sin zona, tratarla como local daría un
    desfase de horas y rechazaría precios buenos (o aceptaría malos)."""
    ahora = datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc)
    sin_zona = {"last_price": 100.0, "updated_at": "2026-08-11T18:55:00"}
    assert server.precio_para_niveles(sin_zona, ahora=ahora, sesion_activa=True)[0] == 100.0


# ── El camino ligero no gasta cuota ─────────────────────────────────────────
def test_el_camino_ligero_no_llama_a_finnhub(monkeypatch):
    """La razón de ser de P2. Se cuenta cada intento de reservar hueco en el limitador,
    que es por donde pasa TODA llamada a Finnhub: si alguna se colara, se vería aquí."""
    import asyncio

    import market_data
    import server as srv
    import test_dashboard_dependencias as datos

    reservas = []
    lim = market_data.get_finnhub_limiter()
    monkeypatch.setattr(lim, "acquire", lambda *a, **k: reservas.append(1) or True)
    monkeypatch.setattr(market_data, "get_full_indicator_history",
                        lambda *a, **k: datos.DF.copy())
    # Si el camino ligero pidiera cotización, sería por aquí: se deja explotar.
    def _prohibido(*a, **k):
        raise AssertionError("el camino ligero ha pedido una cotización")
    monkeypatch.setattr(market_data, "get_quote", _prohibido)
    monkeypatch.setattr(market_data, "get_quote_fast", _prohibido)
    srv._cache.clear()

    resultado = asyncio.run(srv.construir_niveles_ligero("TEST", 123.45))

    assert reservas == [], f"el camino ligero ha reservado {len(reservas)} huecos de Finnhub"
    assert resultado["buy_levels"], "y aun así tiene que producir niveles"
    assert resultado["indicators"] and resultado["data_health"] is not None
    assert resultado["precio_usado"] == 123.45
    assert resultado["ligero"] is True


def test_el_ligero_produce_las_mismas_tres_claves_que_consume_la_portada():
    import asyncio

    import market_data
    import server as srv
    import test_dashboard_dependencias as datos
    from unittest.mock import patch

    with patch.object(market_data, "get_full_indicator_history", lambda *a, **k: datos.DF.copy()):
        srv._cache.clear()
        ligero = asyncio.run(srv.construir_niveles_ligero("TEST", float(datos.DF["Close"].iloc[-1])))

    assert set(("buy_levels", "indicators", "data_health")) <= set(ligero)
    # Y sirve tal cual a los lectores de la portada, sin adaptadores por el medio.
    assert srv._niveles_del_motor(ligero) == ligero["buy_levels"]
