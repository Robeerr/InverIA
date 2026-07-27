"""Tests de los orígenes permitidos para CORS.

El defecto era https://.*\\.vercel\\.app, que acepta CUALQUIER dominio de Vercel: cualquiera
podía desplegar una web ahí y llamar a la API desde el navegador de sus visitantes. Ahora el
defecto es el origen EXACTO de producción y el patrón de previews es opt-in.

Ejecutar:  cd backend && pytest tests/ -v
"""
import re

import pytest

PROYECTO = "inver-ia"
PROD = "https://inver-ia.vercel.app"


def _patron(proyecto: str) -> str:
    """Misma construcción que server.py. Se replica aquí en vez de importar server porque el
    patrón se calcula a nivel de módulo al arrancar, leyendo el entorno de ese momento."""
    return rf"https://{re.escape(proyecto)}(-[a-z0-9-]+)?\.vercel\.app"


def test_origen_de_produccion_declarado_en_server():
    """_PROD_ORIGIN debe ser la URL exacta y sin barra final."""
    import os
    ruta = os.path.join(os.path.dirname(__file__), "..", "server.py")
    with open(ruta, encoding="utf-8") as fh:
        m = re.search(r'^_PROD_ORIGIN = "([^"]+)"', fh.read(), re.MULTILINE)
    assert m, "server.py ya no define _PROD_ORIGIN"
    assert m.group(1) == PROD
    assert not m.group(1).endswith("/"), "El header Origin nunca lleva barra final"


@pytest.mark.parametrize("origen", [
    PROD,                                                 # producción
    "https://inver-ia-a1b2c3d4-robeerr.vercel.app",       # preview por hash
    "https://inver-ia-git-main-robeerr.vercel.app",       # preview por rama
])
def test_el_patron_opcional_acepta_los_dominios_del_proyecto(origen):
    assert re.fullmatch(_patron(PROYECTO), origen), f"debería aceptar {origen}"


@pytest.mark.parametrize("origen", [
    "https://malicioso.vercel.app",                  # proyecto de un tercero
    "https://noinver-ia.vercel.app",                 # no cuela por contener el nombre
    "https://inver-ia.vercel.app.malicioso.com",     # sufijo pegado (Starlette usa fullmatch)
    "https://inver-ia.attacker.com",                 # otro dominio
    "http://inver-ia.vercel.app",                    # sin TLS
])
def test_el_patron_opcional_rechaza_lo_demas(origen):
    assert not re.fullmatch(_patron(PROYECTO), origen), f"NO debería aceptar {origen}"


def test_limitacion_conocida_de_los_previews():
    """Las URLs de preview son <proyecto>-<sufijo>, así que CUALQUIER patrón que las acepte
    acepta también un proyecto ajeno llamado 'inver-ia-loquesea'. Es el precio de tener
    previews, y por eso el patrón NO viene activado por defecto: el defecto es la URL exacta.
    Este test documenta el agujero para que nadie lo descubra por sorpresa."""
    assert re.fullmatch(_patron(PROYECTO), "https://inver-ia-malicioso.vercel.app")


def test_por_defecto_no_hay_patron():
    """Sin CORS_VERCEL_PROJECT ni CORS_ORIGIN_REGEX no debe generarse ningún patrón."""
    import os
    ruta = os.path.join(os.path.dirname(__file__), "..", "server.py")
    with open(ruta, encoding="utf-8") as fh:
        src = fh.read()
    assert 'if _vercel_project else None' in src, "El patrón debe ser None si no se configura"
    assert r'"https://.*\.vercel\.app"' not in src.split("_default_regex")[-1][:200], (
        "Ha vuelto el patrón abierto como valor por defecto"
    )


def test_el_nombre_del_proyecto_se_escapa():
    """Un nombre con puntos o guiones no debe convertirse en comodines del regex."""
    patron = _patron("mi.proyecto")
    assert re.fullmatch(patron, "https://mi.proyecto.vercel.app")
    assert not re.fullmatch(patron, "https://miXproyecto.vercel.app")
