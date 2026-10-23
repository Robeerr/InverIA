"""Ninguna clave llega a escribirse en el log.

El 23-10-2026 la clave de Polygon salió entera en un 429 de MSFT: el error de `requests`
cita la URL con su `?apiKey=` y el aviso la escribía tal cual. Estos tests fijan que se
tapa en todos los caminos por los que un texto llega al log —el mensaje, los argumentos,
la traza de una excepción y el log de accesos de uvicorn— y que lo demás no se toca.

Las claves de aquí son inventadas.
"""
import io
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import logs_sin_secretos as lss

CLAVE = "CLAVEFALSA123abc"


# ── 1 · Qué se tapa ──────────────────────────────────────────────────────────

def test_la_URL_de_Polygon_pierde_la_clave_y_conserva_lo_demas():
    url = (f"https://api.polygon.io/v2/aggs/ticker/MSFT/range/1/day/2025-10-23/2026-10-23"
           f"?apiKey={CLAVE}&limit=5000&adjusted=true")
    tapada = lss.tapar(f"Polygon bars error for MSFT: 429 Client Error: for url: {url}")
    assert CLAVE not in tapada
    assert "?apiKey=***&limit=5000&adjusted=true" in tapada
    assert tapada.startswith("Polygon bars error for MSFT: 429")


@pytest.mark.parametrize("url", [
    f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={CLAVE}",            # Finnhub
    f"https://financialmodelingprep.com/api/v3/profile/AAPL?apikey={CLAVE}",  # FMP
    f"https://generativelanguage.googleapis.com/v1/models?key={CLAVE}",      # Google
    f"/api/inbound/newsletter/knowledge?token={CLAVE}",                      # la nuestra
    f"https://x.example/a?access_token={CLAVE}",
    f"https://x.example/a?API_KEY={CLAVE}",
])
def test_cualquier_parametro_de_clave_se_tapa(url):
    assert CLAVE not in lss.tapar(url)


def test_el_token_del_bot_de_Telegram_se_tapa_en_la_ruta():
    url = "https://api.telegram.org/bot123456789:AAH-ab_cd/sendMessage"
    assert lss.tapar(url) == "https://api.telegram.org/bot***/sendMessage"


# ── 2 · Qué NO se toca ───────────────────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "https://www.sec.gov/Archives/edgar/data/1717115/000119312526429533/d135568d8k.htm",
    "Gemini usage · finish=STOP · prompt=4100 thoughts=600 output=900 total=5600",
    "el token de sesión caducó",
    "presupuesto de tokens=1200",
    "GET /api/hoy?desde=2026-10-10T11:19:00.477Z&limite=5",
    "",
])
def test_lo_que_no_es_una_clave_queda_igual(texto):
    assert lss.tapar(texto) == texto


def test_None_no_rompe():
    assert lss.tapar(None) is None


# ── 3 · Por todos los caminos del log ────────────────────────────────────────

@pytest.fixture
def registro():
    """Un logger propio con un handler que escribe en memoria, con el formateador puesto."""
    salida = io.StringIO()
    handler = logging.StreamHandler(salida)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    log = logging.getLogger("test_logs_sin_secretos")
    log.handlers = [handler]
    log.propagate = False
    log.setLevel(logging.INFO)
    # `raiz=False`: el raíz es de pytest, y aquí solo se prueba este logger. Tampoco se
    # cuentan handlers: pytest añade los suyos durante el test.
    lss.instalar(log.name, raiz=False)
    assert isinstance(handler.formatter, lss.FormatoSinSecretos)
    yield log, salida, handler
    log.handlers = []


URL = f"https://api.polygon.io/v2/aggs?apiKey={CLAVE}&limit=5000"


def test_en_un_mensaje_con_f_string(registro):
    log, salida, _ = registro
    log.warning(f"Polygon bars error for MSFT: 429 for url: {URL}")
    assert CLAVE not in salida.getvalue() and "apiKey=***" in salida.getvalue()
    assert salida.getvalue().startswith("WARNING Polygon bars error")   # el formato sigue


def test_en_los_argumentos(registro):
    log, salida, _ = registro
    log.warning("fallo: %s", RuntimeError(f"429 for url: {URL}"))
    assert CLAVE not in salida.getvalue()


def test_en_la_traza_de_una_excepcion(registro):
    log, salida, _ = registro
    try:
        raise RuntimeError(f"429 for url: {URL}")
    except RuntimeError:
        log.exception("algo falló")
    assert "Traceback" in salida.getvalue() and CLAVE not in salida.getvalue()


def test_en_el_log_de_accesos_de_uvicorn():
    """Su formateador lee los argumentos a su manera —los desempaqueta—, así que no basta
    con tapar el mensaje: hay que conservarlo y tapar la línea que produce."""
    uvicorn_logging = pytest.importorskip("uvicorn.logging")
    salida = io.StringIO()
    handler = logging.StreamHandler(salida)
    handler.setFormatter(uvicorn_logging.AccessFormatter(
        '%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False))
    log = logging.getLogger("test_logs_sin_secretos.acceso")
    log.handlers = [handler]
    log.propagate = False
    log.setLevel(logging.INFO)
    lss.instalar(log.name, raiz=False)
    log.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:0", "GET",
             f"/api/inbound/newsletter/knowledge?token={CLAVE}", "1.1", 200)
    linea = salida.getvalue()
    assert CLAVE not in linea
    assert 'GET /api/inbound/newsletter/knowledge?token=*** HTTP/1.1" 200' in linea
    log.handlers = []


# ── 4 · Instalación ──────────────────────────────────────────────────────────

def test_instalar_dos_veces_no_envuelve_dos_veces(registro):
    log, _, handler = registro
    antes = handler.formatter
    lss.instalar(log.name, raiz=False)
    assert handler.formatter is antes
    assert not isinstance(antes.base, lss.FormatoSinSecretos)


def test_el_servidor_lo_instala_al_importarse_y_al_arrancar():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server.py")
    src = open(ruta, encoding="utf-8").read()
    assert src.count("logs_sin_secretos.instalar(*LOGGERS_DE_UVICORN)") == 2
    assert '"uvicorn.access"' in src
