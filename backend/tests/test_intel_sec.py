"""El connector de SEC/EDGAR.

LA GARANTÍA QUE MÁS IMPORTA

Sin `SEC_USER_AGENT` no se hace NI UNA petición. La SEC exige identificarse y
responde 403 a quien no lo haga: eso es su política de acceso, no una recomendación.
Un valor por defecto inventado sería saltársela usando el nombre de otro.

Y la consecuencia visible: una fuente sin configurar se dibuja APAGADA, no rota. Es
la diferencia entre «no me he conectado» y «he fallado», y es lo que permite que el
radar diga la verdad sobre sí mismo.

EL PARSEO SE PRUEBA CON XML GUARDADO

`parsear_feed` es puro y se separa de la descarga justamente para esto: probarlo
contra la SEC real haría que el test dependiera de que hoy haya publicado algo.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import intel_eventos as ev
import intel_sec as sec


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    """Cada test parte sin la variable puesta, y la pone si la necesita."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    sec._cache_tickers["cuando"] = None
    sec._cache_tickers["por_cik"] = {}


# XML real de EDGAR, recortado. Trae a propósito tres casos que hay que ignorar.
FEED = """<?xml version="1.0" encoding="ISO-8859-1"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
  <title>8-K - NVIDIA CORP (0001045810) (Filer)</title>
  <link rel="alternate" type="text/html"
        href="https://www.sec.gov/Archives/edgar/data/1045810/000104581026000042-index.htm"/>
  <updated>2026-09-08T17:55:00-04:00</updated>
</entry>
<entry>
  <title>4 - APPLE INC (0000320193) (Issuer)</title>
  <link rel="alternate" type="text/html"
        href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000011-index.htm"/>
  <updated>2026-09-08T17:40:00-04:00</updated>
</entry>
<entry>
  <title>SC 13G - ALGUNA GESTORA (0000999999) (Filer)</title>
  <link rel="alternate" type="text/html"
        href="https://www.sec.gov/Archives/edgar/data/999999/000099999926000001-index.htm"/>
  <updated>2026-09-08T17:30:00-04:00</updated>
</entry>
<entry>
  <title>8-K - EMPRESA SIN TICKER (0000777777) (Filer)</title>
  <link rel="alternate" type="text/html"
        href="https://www.sec.gov/Archives/edgar/data/777777/000077777726000001-index.htm"/>
  <updated>2026-09-08T17:20:00-04:00</updated>
</entry>
</feed>"""

POR_CIK = {1045810: "NVDA", 320193: "AAPL"}


# ── La garantía: sin identificación, no hay red ──────────────────────────────

def test_sin_user_agent_el_connector_esta_NO_CONFIGURADA():
    assert sec.configurado() is False
    assert sec.estado_salud() == sec.NO_CONFIGURADA


def test_sin_user_agent_descargar_NI_LO_INTENTA(monkeypatch):
    """Si `httpx` llegara a usarse, este test fallaría con otra excepción. Que lance
    RuntimeError antes de importar nada demuestra que no se tocó la red."""
    import asyncio
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        asyncio.run(sec.descargar())


def test_NO_hay_user_agent_por_defecto_en_el_codigo():
    """Ni un correo ni un identificador escritos a mano. Inventar uno sería saltarse
    la política de la SEC usando el nombre de otro."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "intel_sec.py"), encoding="utf-8") as f:
        src = f.read()
    assert "@" not in src.replace("Accept-Encoding", ""), "hay un correo en el código"
    assert 'get("SEC_USER_AGENT") or ""' in src


def test_con_user_agent_pasa_a_ONLINE(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "InverIA/1.0 contacto@ejemplo.com")
    assert sec.configurado() is True
    assert sec.estado_salud() == sec.ONLINE


def test_el_user_agent_se_lee_en_cada_llamada(monkeypatch):
    """Y no al importar: añadirlo en Render y reiniciar tiene que bastar."""
    assert sec.user_agent() is None
    monkeypatch.setenv("SEC_USER_AGENT", "InverIA/1.0 x@y.z")
    assert sec.user_agent() == "InverIA/1.0 x@y.z"


# ── Salud y backoff ──────────────────────────────────────────────────────────

def test_un_429_se_distingue_de_un_error_cualquiera(monkeypatch):
    """Son cosas distintas: 429 es «vas muy rápido» y se espera; un error genérico
    puede ser una caída. Mezclarlos impediría saber cuál está pasando."""
    monkeypatch.setenv("SEC_USER_AGENT", "InverIA/1.0 x@y.z")
    assert sec.estado_salud("SEC respondió 429") == sec.LIMITADA
    assert sec.estado_salud("SEC respondió 403") == sec.ERROR
    assert sec.estado_salud("timeout", fallos=1) == sec.DEGRADADA


def test_tras_varios_fallos_seguidos_se_declara_OFFLINE(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "InverIA/1.0 x@y.z")
    assert sec.estado_salud("timeout", fallos=5) == sec.OFFLINE


def test_el_backoff_dobla_y_tiene_TECHO():
    """Sin doblar, insistiría contra una puerta cerrada. Sin techo, una caída larga
    dejaría el connector dormido durante días."""
    assert sec.espera_tras_fallo(0) == 0
    assert sec.espera_tras_fallo(1) == 60
    assert sec.espera_tras_fallo(2) == 120
    assert sec.espera_tras_fallo(3) == 240
    assert sec.espera_tras_fallo(50) == sec.BACKOFF_MAX


# ── Parseo del feed ──────────────────────────────────────────────────────────

def test_saca_los_formularios_que_vigilamos():
    eventos = sec.parsear_feed(FEED, POR_CIK)
    assert [e["symbol"] for e in eventos] == ["NVDA", "AAPL"]
    assert eventos[0]["tipo"] == ev.CORPORATIVO      # 8-K
    assert eventos[1]["tipo"] == ev.INSIDER          # Form 4


def test_ignora_los_formularios_que_no_mueven_precio():
    """El feed trae decenas de tipos. Un SC 13G no dice nada accionable."""
    assert all("13G" not in e["titulo"] for e in sec.parsear_feed(FEED, POR_CIK))


def test_ignora_las_empresas_sin_ticker_conocido():
    """Sin ticker no se puede cruzar con tu cartera, así que el evento no serviría
    para nada aunque se guardara."""
    assert all(e["symbol"] in ("NVDA", "AAPL") for e in sec.parsear_feed(FEED, POR_CIK))


def test_el_id_sale_del_numero_de_registro_y_es_estable():
    """Es lo que hace idempotente al worker: el mismo filing leído dos veces produce
    el mismo id y por tanto el mismo documento."""
    a = sec.parsear_feed(FEED, POR_CIK)[0]["id"]
    b = sec.parsear_feed(FEED, POR_CIK)[0]["id"]
    assert a == b and a.startswith("sec:8-K:")


def test_conserva_el_enlace_y_lo_que_dijo_la_sec():
    """Trazabilidad: sin el enlace no se puede comprobar nada después."""
    e = sec.parsear_feed(FEED, POR_CIK)[0]
    assert e["url"].startswith("https://www.sec.gov/Archives/")
    assert e["crudo"]["formulario"] == "8-K"
    assert e["crudo"]["cik"] == "1045810"
    assert "NVIDIA" in e["crudo"]["titulo_sec"]


def test_los_eventos_nacen_en_recibido_y_tier_1():
    for e in sec.parsear_feed(FEED, POR_CIK):
        assert e["etapa"] == ev.RECIBIDO and e["tier"] == 1
        assert e["resumen"] is None       # no hay LLM en esta fase


def test_un_feed_vacio_o_roto_no_fabrica_eventos():
    """Si la SEC está caída o responde basura, NO se inventan eventos. Es la
    diferencia entre un radar honesto y una animación."""
    for entrada in ("", None, "<html>error 500</html>", "<feed></feed>"):
        assert sec.parsear_feed(entrada, POR_CIK) == []


def test_sin_tabla_de_tickers_no_sale_nada():
    """Antes que adivinar el símbolo, no producir el evento."""
    assert sec.parsear_feed(FEED, {}) == []


# ── Configuración ────────────────────────────────────────────────────────────

def test_el_intervalo_por_defecto_son_cinco_minutos():
    """Lo acordado. El feed es de novedades, no una búsqueda: no hace falta más."""
    assert sec.INTERVALO == 300


def test_solo_se_vigilan_8K_y_form_4():
    """Los dos que mueven precio: un hecho relevante que la empresa está obligada a
    contar, y un directivo comprando o vendiendo sus propias acciones."""
    assert set(sec.FORMULARIOS) == {"8-K", "4"}
