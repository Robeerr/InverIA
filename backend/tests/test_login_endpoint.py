"""POST /api/auth/login, ejercitado de verdad contra la app.

Contexto: una prueba manual en Render demostró que `bcrypt.checkpw` valida el hash
configurado contra la contraseña real, y aun así el login fallaba. Ese comando
comprobaba SOLO la contraseña; el endpoint comprueba antes el usuario, y después
firma un JWT. Estos tests recorren el camino entero para que la próxima vez no haya
que deducir dónde se rompe.

Ninguna credencial real aparece aquí: se configura un usuario y un hash de prueba.
"""
import pytest

pytest.importorskip("httpx", reason="requiere httpx para TestClient")
from fastapi.testclient import TestClient  # noqa: E402

import auth  # noqa: E402
import server  # noqa: E402

USUARIO = "usuario-de-test"
CLAVE = "contrasena-de-test"


@pytest.fixture
def cliente(monkeypatch):
    """App con credenciales de prueba. Sin `with`: el gestor de contexto arrancaría
    el lifespan —tareas de fondo, Mongo, precalentado— que no pinta nada aquí."""
    monkeypatch.setattr(auth, "APP_USERNAME", USUARIO)
    monkeypatch.setattr(auth, "APP_PASSWORD", "inveria2024")
    monkeypatch.setenv("APP_PASSWORD_HASH", auth.get_password_hash(CLAVE))
    return TestClient(server.app)


def entrar(cliente, usuario=USUARIO, clave=CLAVE):
    return cliente.post("/api/auth/login", data={"username": usuario, "password": clave})


# ── El camino feliz, entero ──────────────────────────────────────────────────
def test_con_usuario_y_contrasena_correctos_se_entra(cliente):
    r = entrar(cliente)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["username"] == USUARIO
    assert cuerpo["access_token"]


def test_el_token_devuelto_sirve_para_pedir_datos(cliente):
    """Cubre la etapa siguiente: que el JWT que se firma sea el que se acepta después.
    Un token que se emite pero no se valida daría un login "correcto" que deja la app
    igual de inutilizable."""
    token = entrar(cliente).json()["access_token"]
    r = cliente.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"username": USUARIO, "authenticated": True}


def test_sin_token_no_se_pasa(cliente):
    assert cliente.get("/api/auth/me").status_code == 401


# ── La etapa que la prueba manual NO ejercitaba ──────────────────────────────
def test_el_usuario_equivocado_da_401_aunque_la_contrasena_sea_correcta(cliente):
    """ESTE es el caso que explica el síntoma: `bcrypt.checkpw` valida, pero el login
    falla, porque `authenticate_user` compara el usuario ANTES de mirar la contraseña
    y sale sin llegar a bcrypt."""
    r = entrar(cliente, usuario="otro-usuario")
    assert r.status_code == 401
    assert auth.motivo_de_rechazo("otro-usuario", CLAVE) == "usuario_no_coincide"


def test_el_usuario_no_distingue_mayusculas(cliente):
    assert entrar(cliente, usuario=USUARIO.upper()).status_code == 200


def test_un_espacio_en_el_usuario_lo_invalida(cliente):
    """No se recorta el usuario a propósito, pero conviene tenerlo escrito: si el
    navegador o un gestor de contraseñas añade un espacio, esto es lo que pasa."""
    assert entrar(cliente, usuario=f" {USUARIO}").status_code == 401


# ── Contraseña ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mala", ["otra-cosa", CLAVE + " ", " " + CLAVE, CLAVE.upper()])
def test_la_contrasena_incorrecta_da_401(cliente, mala):
    assert entrar(cliente, clave=mala).status_code == 401


def test_la_contrasena_vacia_da_422_y_no_401(cliente):
    """No es lo mismo y conviene saberlo: el formulario exige el campo, así que una
    contraseña vacía la rechaza la validación de FastAPI antes de llegar a la
    autenticación. Si en producción sale un 422, el problema está en lo que manda el
    navegador, no en las credenciales."""
    assert entrar(cliente, clave="").status_code == 422


def test_el_mensaje_de_error_no_revela_cual_de_los_dos_falla(cliente):
    """Decir "el usuario no existe" delataría qué usuario sí existe."""
    a = entrar(cliente, usuario="otro").json()["detail"]
    b = entrar(cliente, clave="otra").json()["detail"]
    assert a == b == "Usuario o contraseña incorrectos"


# ── El diagnóstico por etapas ────────────────────────────────────────────────
def test_las_etapas_identifican_cada_averia(cliente, monkeypatch):
    assert auth.motivo_de_rechazo(USUARIO, CLAVE) is None
    assert auth.motivo_de_rechazo("otro", CLAVE) == "usuario_no_coincide"
    assert auth.motivo_de_rechazo(USUARIO, "mala") == "bcrypt_no_valida_la_contrasena"

    monkeypatch.setenv("APP_PASSWORD_HASH", "$2b$12$recortado")
    assert auth.motivo_de_rechazo(USUARIO, CLAVE) == "APP_PASSWORD_HASH_mal_formado"

    monkeypatch.delenv("APP_PASSWORD_HASH")
    assert auth.motivo_de_rechazo(USUARIO, "mala") == "password_de_respaldo_no_coincide"
    assert auth.motivo_de_rechazo(USUARIO, "inveria2024") is None


def test_el_log_no_escribe_ni_la_contrasena_ni_el_hash(cliente, caplog):
    """El logging de diagnóstico solo puede decir la etapa. Si algún día alguien mete
    el valor en el mensaje "para depurar mejor", acaba en los logs de Render."""
    import logging
    with caplog.at_level(logging.WARNING):
        entrar(cliente, clave="una-contrasena-secreta-inventada")
    registrado = " ".join(r.getMessage() for r in caplog.records)
    assert "bcrypt_no_valida_la_contrasena" in registrado
    assert "una-contrasena-secreta-inventada" not in registrado
    assert "$2b$" not in registrado


def test_authenticate_user_y_el_motivo_no_pueden_divergir(cliente):
    """authenticate_user está definido sobre motivo_de_rechazo justamente para esto."""
    for usuario, clave in [(USUARIO, CLAVE), ("otro", CLAVE), (USUARIO, "mala"), ("", "")]:
        assert auth.authenticate_user(usuario, clave) == (auth.motivo_de_rechazo(usuario, clave) is None)


# ── Forma de la petición ─────────────────────────────────────────────────────
def test_el_login_espera_un_formulario_no_json(cliente):
    """El endpoint usa OAuth2PasswordRequestForm: si el cliente manda JSON, FastAPI
    responde 422 y no 401. Distinguirlos ahorra buscar en el sitio equivocado."""
    r = cliente.post("/api/auth/login", json={"username": USUARIO, "password": CLAVE})
    assert r.status_code == 422


def test_el_login_no_exige_sesion_previa(cliente):
    """Centinela: es la puerta. Si alguna ronda de seguridad le pusiera la dependencia
    de auth, nadie podría entrar nunca y el síntoma sería idéntico a este."""
    ruta = next(r for r in server.api_router.routes
                if getattr(r, "path", "") == "/api/auth/login")
    pendientes, encontrada = [ruta.dependant], False
    while pendientes:
        d = pendientes.pop()
        if getattr(d, "call", None) is auth.get_current_user:
            encontrada = True
        pendientes.extend(getattr(d, "dependencies", []) or [])
    assert not encontrada, "/auth/login no puede exigir sesión: es la puerta"
