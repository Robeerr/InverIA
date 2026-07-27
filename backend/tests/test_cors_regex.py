"""Tests del patrón de orígenes permitidos para CORS.

El patrón por defecto (https://.*\\.vercel\\.app) acepta CUALQUIER dominio de Vercel, así que
cualquiera podía desplegar una web ahí y llamar a la API desde el navegador de sus visitantes.
Con CORS_VERCEL_PROJECT el patrón queda anclado al proyecto propio.

Ejecutar:  cd backend && pytest tests/ -v
"""
import re

import pytest


def _patron(proyecto: str) -> str:
    """Misma construcción que server.py. Se replica aquí en vez de importar server porque
    el patrón se calcula a nivel de módulo al arrancar, leyendo el entorno de ese momento."""
    return rf"https://{re.escape(proyecto)}(-[a-z0-9-]+)?\.vercel\.app"


@pytest.mark.parametrize("origen", [
    "https://inveria.vercel.app",                        # producción
    "https://inveria-a1b2c3d4-robeerr.vercel.app",       # preview por hash
    "https://inveria-git-main-robeerr.vercel.app",       # preview por rama
])
def test_acepta_los_dominios_del_proyecto(origen):
    assert re.fullmatch(_patron("inveria"), origen), f"debería aceptar {origen}"


@pytest.mark.parametrize("origen", [
    "https://malicioso.vercel.app",              # proyecto de un tercero
    "https://noinveria.vercel.app",              # no debe colar por contener el nombre
    "https://inveria.vercel.app.malicioso.com",  # sufijo pegado
    "https://inveria.attacker.com",              # otro dominio
    "http://inveria.vercel.app",                 # sin TLS
])
def test_rechaza_todo_lo_demas(origen):
    assert not re.fullmatch(_patron("inveria"), origen), f"NO debería aceptar {origen}"


def test_el_patron_abierto_acepta_a_cualquiera():
    """Documenta por qué existe CORS_VERCEL_PROJECT: el defecto deja pasar a cualquiera."""
    abierto = r"https://.*\.vercel\.app"
    assert re.fullmatch(abierto, "https://malicioso.vercel.app")


def test_el_nombre_del_proyecto_se_escapa():
    """Un nombre con puntos o guiones no debe convertirse en comodines del regex."""
    patron = _patron("mi.proyecto")
    assert re.fullmatch(patron, "https://mi.proyecto.vercel.app")
    assert not re.fullmatch(patron, "https://miXproyecto.vercel.app")
