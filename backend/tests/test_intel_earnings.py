"""El connector de resultados: la primera fuente que mira hacia delante.

LO QUE ESTE FICHERO PROTEGE

  1. QUE UN CAMBIO DE FECHA NO SE PIERDA. Es el motivo por el que esta fuente se
     implementó así. Adelantar resultados suele acompañar a buenas noticias y retrasarlos
     es una de las señales de alarma más viejas que hay; si el cambio se tratara como «el
     mismo evento actualizado», ese movimiento desaparecería sin dejar rastro.

  2. QUE SEGUIR SIENDO IDEMPOTENTE. Leer el mismo calendario dos veces no puede producir
     dos eventos. Las dos cosas —capturar el cambio y no duplicar— tiran en direcciones
     opuestas, y quien las concilia es el id: lleva la fecha dentro.

  3. QUE UNA ESTIMACIÓN NO SE VENDA COMO UN HECHO. Ni una fecha que el proveedor calcula,
     ni un veredicto sobre unos resultados que aquí nadie ha interpretado.

Todo se prueba sobre filas de calendario en memoria: `construir` es pura precisamente para
que estos tests no dependan de que hoy haya temporada de resultados.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import intel_earnings as ea
import intel_eventos as ev


@pytest.fixture(autouse=True)
def _sin_clave(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)


def _fila(symbol="NVDA", date="2026-10-28", quarter=3, year=2026,
          eps_estimate=1.10, eps_actual=None, hour="amc"):
    return {"symbol": symbol, "date": date, "quarter": quarter, "year": year,
            "eps_estimate": eps_estimate, "eps_actual": eps_actual, "hour": hour,
            "revenue_estimate": None, "revenue_actual": None}


# ── Sin clave no hay peticiones ──────────────────────────────────────────────

def test_sin_FINNHUB_API_KEY_la_fuente_esta_NO_CONFIGURADA():
    assert ea.configurado() is False
    assert ea.estado_salud() == ea.NO_CONFIGURADA


def test_sin_clave_recolectar_NI_LO_INTENTA():
    import asyncio
    with pytest.raises(RuntimeError, match="FINNHUB_API_KEY"):
        asyncio.run(ea.recolectar({"universo": {"NVDA"}}))


def test_sin_universo_no_se_pide_el_calendario(monkeypatch):
    """No es un fallo: es que no hay con qué cruzar. Traerse el calendario del mercado
    entero para tirarlo sería gastar cuota en nada."""
    import asyncio
    monkeypatch.setenv("FINNHUB_API_KEY", "x")

    def prohibido(*_a, **_k):
        raise AssertionError("se ha pedido el calendario sin universo")
    import external_data
    monkeypatch.setattr(external_data, "finnhub_earnings_calendar", prohibido)
    assert asyncio.run(ea.recolectar({"universo": set()})) == []


# ── El trimestre es la identidad ─────────────────────────────────────────────

def test_la_clave_de_trimestre_identifica_symbol_y_periodo():
    assert ea.clave_trimestre(_fila()) == "NVDA:2026Q3"


def test_sin_trimestre_fiable_NO_se_adivina_uno():
    """Un trimestre inventado emparejaría anuncios de periodos distintos y produciría
    «cambios de fecha» que nunca ocurrieron."""
    for roto in (_fila(quarter=None), _fila(year=None), _fila(quarter=9), _fila(symbol="")):
        assert ea.clave_trimestre(roto) is None


# ── Programado ───────────────────────────────────────────────────────────────

def test_una_fecha_nueva_produce_un_evento_programado():
    e = ea.construir([_fila()])[0]
    assert e["symbol"] == "NVDA" and e["tipo"] == ev.RESULTADOS and e["tier"] == 2
    assert e["crudo"]["suceso"] == ea.PROGRAMADO
    assert "2026-10-28" in e["titulo"]


def test_el_titulo_dice_CUANDO_publica():
    """Antes de abrir te pilla con la posición abierta y sin poder reaccionar hasta la
    campana. La hora no es un detalle decorativo."""
    assert "tras el cierre" in ea.construir([_fila(hour="amc")])[0]["titulo"]
    assert "antes de abrir" in ea.construir([_fila(hour="bmo")])[0]["titulo"]


def test_sin_fecha_o_sin_trimestre_no_hay_evento():
    assert ea.construir([_fila(date=""), _fila(quarter=None), {}, None]) == []


def test_leer_el_mismo_calendario_dos_veces_da_EL_MISMO_id():
    """La condición de idempotencia: el worker deduplica por id, así que si el id bailara
    cada vuelta crearía un evento nuevo cada seis horas para siempre."""
    a = ea.construir([_fila()])[0]["id"]
    b = ea.construir([_fila()])[0]["id"]
    assert a == b == "earnings:NVDA:2026Q3:2026-10-28"


def test_si_ya_conociamos_ESA_MISMA_fecha_no_se_repite_el_anuncio():
    """Se emite el programado solo la primera vez. Con la fecha ya conocida e igual, la
    fila no produce nada: no ha pasado nada nuevo."""
    assert ea.construir([_fila()], {"NVDA:2026Q3": "2026-10-28"}) == []


# ── Cambio de fecha: el motivo por el que esta fuente es así ─────────────────

def test_si_la_fecha_SE_MUEVE_sale_un_evento_propio():
    evs = ea.construir([_fila(date="2026-11-04")], {"NVDA:2026Q3": "2026-10-28"})
    assert len(evs) == 1
    e = evs[0]
    assert e["crudo"]["suceso"] == ea.CAMBIO_FECHA
    assert e["crudo"]["fecha_anterior"] == "2026-10-28"
    assert "2026-10-28" in e["titulo"] and "2026-11-04" in e["titulo"]


def test_el_cambio_distingue_ADELANTO_de_retraso():
    """No es lo mismo: adelantar suele acompañar a buenas noticias y retrasar es una
    señal de alarma clásica. Pintarlos igual perdería justo lo que se quiere saber."""
    adelanto = ea.construir([_fila(date="2026-10-20")], {"NVDA:2026Q3": "2026-10-28"})[0]
    retraso = ea.construir([_fila(date="2026-11-10")], {"NVDA:2026Q3": "2026-10-28"})[0]
    assert adelanto["crudo"]["adelanta"] is True
    assert retraso["crudo"]["adelanta"] is False
    assert "ADELANTADOS" in adelanto["titulo"] and "retrasados" in retraso["titulo"]


def test_el_cambio_de_fecha_tiene_SU_PROPIO_id_y_no_pisa_al_anterior():
    """Van al radar como dos marcas en dos momentos distintos, que es lo que pasó de
    verdad. Reescribir el evento anterior borraría que hubo un movimiento."""
    programado = ea.construir([_fila(date="2026-10-28")])[0]
    movido = ea.construir([_fila(date="2026-11-04")], {"NVDA:2026Q3": "2026-10-28"})[0]
    assert programado["id"] != movido["id"]


def test_un_cambio_ya_visto_no_se_vuelve_a_emitir():
    """Tras el movimiento, la fecha conocida pasa a ser la nueva y la fila deja de
    producir nada. Sin esto, el mismo cambio entraría en cada vuelta."""
    assert ea.construir([_fila(date="2026-11-04")], {"NVDA:2026Q3": "2026-11-04"}) == []


# ── Publicado ────────────────────────────────────────────────────────────────

def test_cuando_hay_cifras_sale_el_evento_de_publicacion():
    evs = ea.construir([_fila(eps_actual=1.35)], {"NVDA:2026Q3": "2026-10-28"})
    assert len(evs) == 1 and evs[0]["crudo"]["suceso"] == ea.PUBLICADO
    assert "1,35" in evs[0]["titulo"] and "1,10" in evs[0]["titulo"]


def test_la_publicacion_NO_lleva_veredicto():
    """Se enseñan las dos cifras y la resta. «Ha batido expectativas» sería una lectura,
    y en esta fase no se interpreta nada — no hay IA detrás de esto."""
    e = ea.construir([_fila(eps_actual=1.35)], {"NVDA:2026Q3": "2026-10-28"})[0]
    for palabra in ("bate", "batido", "supera", "decepciona", "buenos", "malos"):
        assert palabra not in e["titulo"].lower()
    assert e["crudo"]["diferencia_eps"] == 0.25


def test_la_publicacion_tiene_un_id_SIN_fecha():
    """Los resultados de un trimestre se publican una vez. Si el id llevara la fecha, un
    calendario que bailó antes de publicarse produciría dos eventos de publicación."""
    a = ea.construir([_fila(date="2026-10-28", eps_actual=1.3)],
                     {"NVDA:2026Q3": "2026-10-28"})[0]
    b = ea.construir([_fila(date="2026-11-04", eps_actual=1.3)],
                     {"NVDA:2026Q3": "2026-11-04"})[0]
    assert a["id"] == b["id"] == "earnings:NVDA:2026Q3:publicado"


def test_sin_estimacion_se_publica_igual_pero_sin_comparar():
    """Falta media parte del dato, no el dato entero. Inventar una estimación para poder
    comparar sería peor que no comparar."""
    e = ea.construir([_fila(eps_estimate=None, eps_actual=1.35)],
                     {"NVDA:2026Q3": "2026-10-28"})[0]
    assert "1,35" in e["titulo"] and "esperado" not in e["titulo"]
    assert e["crudo"]["diferencia_eps"] is None


def test_publicar_Y_haber_movido_la_fecha_son_DOS_eventos():
    """Son dos hechos distintos y perder uno por contar el otro sería perder
    información: la empresa retrasó los resultados Y luego los publicó."""
    evs = ea.construir([_fila(date="2026-11-04", eps_actual=1.35)],
                       {"NVDA:2026Q3": "2026-10-28"})
    assert {e["crudo"]["suceso"] for e in evs} == {ea.CAMBIO_FECHA, ea.PUBLICADO}


# ── Salud y ritmo ────────────────────────────────────────────────────────────

def test_el_intervalo_por_defecto_son_seis_horas():
    """El calendario se mueve poco: lo que importa es tener la fecha con días de
    antelación, no con minutos."""
    assert ea.INTERVALO == 6 * 3600


def test_es_TIER_2_y_no_1():
    """Es un dato de proveedor, no un documento registrado. Cuando llegue el 8-K con los
    resultados reales, ese sí es Tier 1 y contrasta contra esto."""
    assert ea.TIER == 2


def test_un_429_se_distingue_de_una_caida(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "x")
    assert ea.estado_salud("Finnhub 429") == ea.LIMITADA
    assert ea.estado_salud("401 unauthorized") == ea.ERROR
    assert ea.estado_salud("timeout", fallos=1) == ea.DEGRADADA
    assert ea.estado_salud("timeout", fallos=5) == ea.OFFLINE


def test_el_backoff_dobla_y_tiene_techo():
    assert ea.espera_tras_fallo(0) == 0
    assert ea.espera_tras_fallo(1) == ea.BACKOFF_BASE
    assert ea.espera_tras_fallo(50) == ea.BACKOFF_MAX


def test_expone_LA_MISMA_interfaz_que_el_connector_de_la_sec():
    """El worker trata a todas las fuentes igual. Si una dejara de cumplir el contrato,
    el bucle se rompería en producción y no aquí."""
    import intel_sec
    for nombre in ("FUENTE", "NOMBRE", "TIER", "INTERVALO", "ONLINE", "NO_CONFIGURADA"):
        assert hasattr(ea, nombre), nombre
        assert hasattr(intel_sec, nombre), nombre
    for f in ("configurado", "estado_salud", "espera_tras_fallo", "recolectar"):
        assert callable(getattr(ea, f)) and callable(getattr(intel_sec, f)), f
