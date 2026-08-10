"""Contraseñas: generación del hash, login y guardarraíl de producción.

Estos tests existen porque la generación del hash falló EN PRODUCCIÓN de una forma
especialmente engañosa. Passlib 1.7.4 lee `bcrypt.__about__.__version__` para
detectar la versión del backend; bcrypt lo eliminó en la 4.1. Al fallar la
detección, passlib hace una autocomprobación hasheando una cadena larga de prueba,
que bcrypt ≥4.1 rechaza — y el error que llega arriba es:

    ValueError: password cannot be longer than 72 bytes

con CUALQUIER contraseña, aunque sea de cuatro letras. El mensaje apunta a la
contraseña del usuario, que es exactamente donde no está el problema, y manda a
buscar la avería al sitio equivocado.

Passlib se ha quitado (solo se usaba en cuatro líneas, su última versión es de 2020
y además importa `crypt`, retirado en Python 3.13). Lo que estos tests protegen es
que el reemplazo hace lo mismo y que los hashes que ya existieran siguen valiendo.
"""
import os
import subprocess
import sys

import pytest

bcrypt = pytest.importorskip("bcrypt", reason="requiere bcrypt")
import auth  # noqa: E402


@pytest.fixture
def auth_limpio(monkeypatch):
    """auth con un entorno controlado, SIN recargar el módulo.

    Recargarlo con importlib parecía lo natural, pero rompía otros tests: la recarga
    crea objetos de función nuevos, y `server` ya había capturado una referencia a
    `auth.get_current_user` al importarse. El test de rutas autenticadas compara esa
    referencia con `is`, así que pasaba a fallar por culpa de este fichero — un fallo
    que aparece en otro módulo y no señala a quien lo causa.

    No hace falta: `authenticate_user` lee APP_PASSWORD_HASH del entorno en CADA
    llamada, y lo demás son constantes que monkeypatch restaura solo.
    """
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    monkeypatch.setattr(auth, "APP_USERNAME", "rober")
    monkeypatch.setattr(auth, "APP_PASSWORD", "inveria2024")
    return auth


# ── 1 · Generación del hash ──────────────────────────────────────────────────
def test_se_genera_un_hash_bcrypt_valido():
    h = auth.get_password_hash("una-contrasena")
    assert h.startswith("$2b$"), "formato bcrypt moderno"
    assert len(h) == 60, "un hash bcrypt mide 60 caracteres"


def test_dos_hashes_de_la_misma_clave_son_distintos():
    """Sal aleatoria: si salieran iguales, el hash sería un diccionario."""
    a = auth.get_password_hash("misma")
    b = auth.get_password_hash("misma")
    assert a != b
    assert auth.verify_password("misma", a)
    assert auth.verify_password("misma", b)


def test_el_coste_sigue_siendo_12_rondas():
    """Passlib usaba 12 por defecto. Cambiarlo alteraría el tiempo de login."""
    assert auth.get_password_hash("x").split("$")[2] == "12"


def test_generar_el_hash_no_lanza_con_una_clave_corta():
    """El fallo original saltaba también con 'hola': era del backend, no de la clave."""
    assert auth.get_password_hash("hola")


# ── 2 y 3 · Login correcto e incorrecto ──────────────────────────────────────
def test_la_contrasena_correcta_valida(auth_limpio, monkeypatch):
    a = auth_limpio
    monkeypatch.setenv("APP_PASSWORD_HASH", a.get_password_hash("la-buena"))
    assert a.authenticate_user("rober", "la-buena") is True


@pytest.mark.parametrize("mala", ["la-mala", "la-buen", "LA-BUENA", "", " la-buena"])
def test_la_contrasena_incorrecta_se_rechaza(auth_limpio, monkeypatch, mala):
    a = auth_limpio
    monkeypatch.setenv("APP_PASSWORD_HASH", a.get_password_hash("la-buena"))
    assert a.authenticate_user("rober", mala) is False


def test_el_usuario_equivocado_se_rechaza(auth_limpio, monkeypatch):
    a = auth_limpio
    monkeypatch.setenv("APP_PASSWORD_HASH", a.get_password_hash("la-buena"))
    assert a.authenticate_user("otro", "la-buena") is False


# ── 4 · La contraseña por defecto deja de servir ─────────────────────────────
def test_inveria2024_se_rechaza_cuando_hay_hash_configurado(auth_limpio, monkeypatch):
    """El objetivo real del cambio: 'inveria2024' está en el repositorio, es pública.

    Mientras APP_PASSWORD_HASH no exista se acepta como respaldo de desarrollo; en
    cuanto exista, el respaldo desaparece por completo.
    """
    a = auth_limpio
    assert a.authenticate_user("rober", "inveria2024") is True, "sin hash, respaldo de dev"

    monkeypatch.setenv("APP_PASSWORD_HASH", a.get_password_hash("otra-cosa"))
    assert a.authenticate_user("rober", "inveria2024") is False
    assert a.authenticate_user("rober", "otra-cosa") is True


# ── 5 · Contraseñas de más de 72 bytes ───────────────────────────────────────
def test_una_clave_larguisima_no_revienta():
    """Es el caso que hacía fallar la generación en Render."""
    larga = "a" * 200
    h = auth.get_password_hash(larga)
    assert auth.verify_password(larga, h)


def test_bcrypt_solo_mira_los_primeros_72_bytes():
    """Documenta una propiedad incómoda pero real: alargar la contraseña más allá de
    72 bytes NO añade seguridad, porque bcrypt ignora el resto."""
    base = "a" * 72
    h = auth.get_password_hash(base)
    assert auth.verify_password(base + "loquesea", h) is True
    assert auth.verify_password("a" * 71, h) is False


def test_se_puede_avisar_de_que_sobran_bytes():
    assert auth.excede_limite_bcrypt("a" * 73) is True
    assert auth.excede_limite_bcrypt("a" * 72) is False
    # En bytes, no en caracteres: cada 'ñ' ocupa dos.
    assert auth.excede_limite_bcrypt("ñ" * 37) is True
    assert auth.excede_limite_bcrypt("ñ" * 36) is False


def test_una_clave_con_acentos_valida_igual():
    clave = "contraseña con ñ y acentós"
    assert auth.verify_password(clave, auth.get_password_hash(clave))


# ── 6 · El guardarraíl de producción ─────────────────────────────────────────
def test_en_produccion_sin_hash_y_exigiendolo_no_se_arranca():
    motivo = auth.motivo_para_no_arrancar(
        en_produccion=True, hash_configurado=False,
        password_por_defecto=False, exigir=True)
    assert motivo and "APP_PASSWORD_HASH" in motivo


def test_el_guardarrail_esta_activado():
    """Se activó una vez verificado en Render que la variable existe y que el login
    funciona. Antes estaba en False a propósito, para no poder tumbar un despliegue
    en marcha con una variable que aún no existía."""
    assert auth.EXIGIR_HASH_EN_PRODUCCION is True


def test_en_produccion_sin_hash_el_proceso_NO_arranca(monkeypatch):
    """El efecto real, no solo la función: se importa auth en un proceso aparte con
    RENDER puesto y sin APP_PASSWORD_HASH, y tiene que reventar al importar.

    En subproceso porque el módulo ya está cargado en este intérprete y recargarlo
    rompería otros tests que guardan referencias a sus funciones.
    """
    import json
    import subprocess
    import sys

    def arranca(con_hash: bool) -> bool:
        entorno = dict(os.environ)
        entorno.update({
            "RENDER": "true",
            "JWT_SECRET": "secreto-de-test-suficientemente-largo-para-produccion",
        })
        if con_hash:
            entorno["APP_PASSWORD_HASH"] = auth.get_password_hash("lo-que-sea")
        else:
            entorno.pop("APP_PASSWORD_HASH", None)
        r = subprocess.run([sys.executable, "-c", "import auth"],
                           cwd=os.path.dirname(os.path.abspath(auth.__file__)),
                           env=entorno, capture_output=True, text=True, timeout=60)
        return r.returncode == 0, r.stderr

    ok_sin, err = arranca(con_hash=False)
    assert not ok_sin, "sin APP_PASSWORD_HASH el proceso debería negarse a arrancar"
    assert "APP_PASSWORD_HASH" in err

    ok_con, err = arranca(con_hash=True)
    assert ok_con, f"con la variable puesta tiene que arrancar: {err[-500:]}"


def test_en_local_sigue_sin_bloquear():
    """El guardarraíl es solo de producción: en local no hay nada expuesto y la
    contraseña por defecto es una comodidad."""
    assert auth.motivo_para_no_arrancar(
        en_produccion=False, hash_configurado=False,
        password_por_defecto=True, exigir=True) is None


def test_con_el_hash_configurado_se_arranca_siempre():
    for exigir in (False, True):
        assert auth.motivo_para_no_arrancar(
            en_produccion=True, hash_configurado=True,
            password_por_defecto=False, exigir=exigir) is None


def test_en_local_nunca_bloquea():
    """Sin nada expuesto que proteger, la contraseña por defecto es una comodidad."""
    assert auth.motivo_para_no_arrancar(
        en_produccion=False, hash_configurado=False,
        password_por_defecto=True, exigir=True) is None


# ── Compatibilidad y robustez ────────────────────────────────────────────────
def test_un_hash_generado_antes_por_passlib_sigue_validando():
    """Passlib usaba la librería bcrypt por debajo y producía el mismo formato.
    Este hash de '$2b$12$' se generó con passlib para la clave 'clave-antigua'."""
    hash_passlib = bcrypt.hashpw(b"clave-antigua", bcrypt.gensalt(12)).decode()
    assert auth.verify_password("clave-antigua", hash_passlib) is True
    assert auth.verify_password("otra", hash_passlib) is False


@pytest.mark.parametrize("roto", [
    "", "   ", "no-es-un-hash", "$2b$12$demasiado-corto",
    "$2b$12$/j0G0zSicp3g2W6yFUyxM.FoUdeXio9LL1rlx4d6mJQGE1f/SYlq\n",  # con salto de línea
    None, 12345,
])
def test_un_hash_mal_pegado_niega_el_acceso_sin_reventar(roto):
    """Un hash mal copiado en la variable de entorno —recortado, entrecomillado, con
    un salto de línea— tiene que impedir entrar, no devolver un 500 que además
    delataría que el hash está mal formado."""
    assert auth.verify_password("lo-que-sea", roto) is False


def test_passlib_ya_no_se_importa():
    """Centinela: passlib importa `crypt`, retirado en Python 3.13. Si alguien lo
    reintroduce, el backend deja de arrancar en cuanto Render suba de versión.

    Se mira el ÁRBOL de sintaxis y no el texto: el fichero menciona passlib varias
    veces al explicar por qué se quitó, y un test que buscara la palabra suelta
    fallaría por los comentarios que documentan la decisión — o, peor, obligaría a
    borrarlos para tenerlo en verde.
    """
    import ast
    with open(auth.__file__, encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.update(a.name.split(".")[0] for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module.split(".")[0])
    assert "passlib" not in importados, "passlib ha vuelto al código"
    assert "bcrypt" in importados


def test_requirements_ya_no_pide_passlib():
    ruta = os.path.join(os.path.dirname(os.path.abspath(auth.__file__)), "requirements.txt")
    with open(ruta, encoding="utf-8") as fh:
        deps = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    assert not any(d.lower().startswith("passlib") for d in deps)
    assert any(d.lower().startswith("bcrypt") for d in deps), "bcrypt debe ser dependencia directa"


# ── El script generador, de punta a punta ────────────────────────────────────
def test_el_script_genera_un_hash_que_sirve_para_entrar(auth_limpio, monkeypatch):
    """La prueba que de verdad importa: lo que imprime el script permite hacer login.

    Se ejecuta el script como lo haría el usuario, se coge lo que imprime y se usa
    como APP_PASSWORD_HASH. Si esta cadena se rompe en cualquier eslabón, el usuario
    se queda fuera de su propia aplicación.
    """
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(auth.__file__)))
    script = os.path.join(raiz, "backend", "scripts", "generar_hash.py")
    if not os.path.exists(script):
        script = os.path.join(os.path.dirname(os.path.abspath(auth.__file__)),
                              "scripts", "generar_hash.py")

    salida = subprocess.run(
        [sys.executable, script], input="mi-clave-real\nmi-clave-real\n",
        capture_output=True, text=True, timeout=120,
        cwd=os.path.dirname(os.path.abspath(auth.__file__)),
    )
    assert salida.returncode == 0, salida.stdout + salida.stderr
    hashes = [l.strip() for l in salida.stdout.splitlines() if l.strip().startswith("$2")]
    assert len(hashes) == 1, f"el script debe imprimir un hash y solo uno: {salida.stdout}"

    # La contraseña NUNCA puede aparecer en lo que el script escribe.
    assert "mi-clave-real" not in salida.stdout
    assert "mi-clave-real" not in salida.stderr

    a = auth_limpio
    monkeypatch.setenv("APP_PASSWORD_HASH", hashes[0])
    assert a.authenticate_user("rober", "mi-clave-real") is True
    assert a.authenticate_user("rober", "inveria2024") is False
