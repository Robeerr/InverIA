"""El secreto de ingesta sale de las URLs.

Un secreto en la barra de direcciones acaba en el historial del navegador, en el log
de cualquier proxy y en la cabecera Referer de lo que se cargue después. No es un
detalle: `INBOUND_SECRET` no caduca ni se rota solo.

Los trece endpoints no se movieron igual, porque no los llama lo mismo:

  GRUPO A · los cinco de Telegram → los llama el frontend, que controlamos.
            Pasan a CABECERA X-Inbound-Token y dejan de aceptar el query param.

  GRUPO B · /inbound/newsletter → lo llama un conector de correo externo. Sigue
            aceptando las dos formas A PROPÓSITO; cerrarlo sin reconfigurarlo
            dejaría de alimentar el Cerebro sin avisar. Se registra un aviso cuando
            llega por query, para saber cuándo se puede cerrar.

  GRUPO C · los siete de mantenimiento del Cerebro → pasan a SESIÓN normal. Eran
            operaciones del dueño lanzadas tocando un enlace desde el móvil, y un
            enlace no puede mandar cabeceras. Con sesión, el secreto desaparece de
            la URL en vez de cambiar de sitio.
"""
import pytest

pytest.importorskip("httpx", reason="requiere httpx para TestClient")
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

SECRETO = "secreto-de-ingesta-para-el-test"

GRUPO_A = [
    ("get", "/api/telegram/status"),
    ("post", "/api/telegram/login/start"),
    ("post", "/api/telegram/login/code"),
    ("get", "/api/telegram/dialogs"),
    ("post", "/api/telegram/capture"),
]

GRUPO_C = [
    "/api/inbound/news/ingest",
    "/api/inbound/newsletter/backfill-knowledge",
    "/api/inbound/newsletter/dedupe-knowledge",
    "/api/inbound/newsletter/dedupe-knowledge-llm",
    "/api/inbound/newsletter/fix-encoding",
    "/api/inbound/newsletter/knowledge",
    "/api/inbound/newsletter/debug",
]


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", SECRETO)
    # `raise_server_exceptions=False`: lo que se prueba aquí es la PUERTA, no la
    # operación. Con la credencial correcta la petición sigue adelante e intenta hablar
    # con Telegram y con Mongo, que aquí no existen; sin esto, ese fallo posterior
    # llegaría como excepción y taparía justo lo que se quiere medir. Con esto llega
    # como 500, que para este test significa "la credencial se aceptó".
    return TestClient(server.app, raise_server_exceptions=False)


def _pedir(cliente, metodo, ruta, **kw):
    # GET no lleva cuerpo: TestClient.get() ni siquiera acepta `json`.
    if metodo == "get":
        kw.pop("json", None)
    return getattr(cliente, metodo)(ruta, **kw)


# ── Grupo A · cabecera, y solo cabecera ─────────────────────────────────────
@pytest.mark.parametrize("metodo,ruta", GRUPO_A)
def test_sin_cabecera_no_se_pasa(cliente, metodo, ruta):
    assert _pedir(cliente, metodo, ruta, json={}).status_code == 401


@pytest.mark.parametrize("metodo,ruta", GRUPO_A)
def test_el_query_param_ya_no_vale(cliente, metodo, ruta):
    """El objetivo del cambio: que el secreto no pueda ir en la URL."""
    r = _pedir(cliente, metodo, ruta, params={"token": SECRETO}, json={})
    assert r.status_code == 401, f"{ruta} sigue aceptando el secreto por la URL"


@pytest.mark.parametrize("metodo,ruta", GRUPO_A)
def test_con_la_cabecera_correcta_se_pasa_del_control(cliente, metodo, ruta):
    """No se comprueba que la operación funcione —necesitaría Telegram— sino que YA
    NO se rechaza por credencial: cualquier cosa menos 401."""
    r = _pedir(cliente, metodo, ruta, headers={"X-Inbound-Token": SECRETO}, json={})
    assert r.status_code != 401


@pytest.mark.parametrize("metodo,ruta", GRUPO_A)
def test_una_cabecera_equivocada_se_rechaza(cliente, metodo, ruta):
    r = _pedir(cliente, metodo, ruta, headers={"X-Inbound-Token": "otro"}, json={})
    assert r.status_code == 401


# ── Grupo C · sesión normal, sin secreto por ningún lado ────────────────────
@pytest.mark.parametrize("ruta", GRUPO_C)
def test_mantenimiento_exige_sesion(cliente, ruta):
    assert cliente.get(ruta).status_code == 401


@pytest.mark.parametrize("ruta", GRUPO_C)
def test_mantenimiento_ya_no_acepta_el_secreto_por_la_url(cliente, ruta):
    """Era el caso peor: enlaces que se tocaban desde el móvil, con el secreto en la
    barra de direcciones y por tanto en el historial."""
    r = cliente.get(ruta, params={"token": SECRETO})
    assert r.status_code == 401, f"{ruta} sigue aceptando el secreto por la URL"


def test_mantenimiento_pasa_el_control_con_sesion(cliente, monkeypatch):
    import auth
    monkeypatch.setattr(auth, "APP_USERNAME", "rober")
    token = auth.create_access_token({"sub": "rober"})
    r = cliente.get("/api/inbound/newsletter/debug",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code != 401


# ── Grupo B · compatibilidad mientras se migra el conector ──────────────────
def test_el_webhook_sigue_aceptando_el_query_param(cliente):
    """Si esto se rompe, dejas de recibir newsletters y el Cerebro se queda sin
    alimentar. Es el único sitio donde la compatibilidad importa más que la limpieza."""
    r = cliente.post("/api/inbound/newsletter", params={"token": SECRETO}, json={})
    assert r.status_code != 401


def test_el_webhook_acepta_tambien_la_cabecera(cliente):
    r = cliente.post("/api/inbound/newsletter",
                     headers={"X-Inbound-Token": SECRETO}, json={})
    assert r.status_code != 401


def test_el_webhook_rechaza_un_secreto_equivocado(cliente):
    assert cliente.post("/api/inbound/newsletter",
                        params={"token": "otro"}, json={}).status_code == 401


def test_se_avisa_cuando_el_conector_usa_la_url(cliente, caplog):
    """Cuando este aviso deje de aparecer en los logs, el conector ya usa cabecera y
    se puede cerrar el parámetro. Mientras salga, cerrarlo rompería la ingesta."""
    import logging
    with caplog.at_level(logging.WARNING):
        cliente.post("/api/inbound/newsletter", params={"token": SECRETO}, json={})
    registrado = " ".join(r.getMessage() for r in caplog.records)
    assert "QUERY PARAM" in registrado
    assert SECRETO not in registrado, "el aviso no puede llevar el secreto dentro"


def test_no_se_avisa_cuando_ya_usa_cabecera(cliente, caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        cliente.post("/api/inbound/newsletter",
                     headers={"X-Inbound-Token": SECRETO}, json={})
    assert "QUERY PARAM" not in " ".join(r.getMessage() for r in caplog.records)


def test_la_cabecera_manda_sobre_el_query(cliente, caplog):
    """Con las dos presentes gana la cabecera, para que migrar el conector no dependa
    de que además quite el parámetro viejo."""
    import logging
    with caplog.at_level(logging.WARNING):
        r = cliente.post("/api/inbound/newsletter",
                         params={"token": "basura"},
                         headers={"X-Inbound-Token": SECRETO}, json={})
    assert r.status_code != 401
    assert "QUERY PARAM" not in " ".join(x.getMessage() for x in caplog.records)
