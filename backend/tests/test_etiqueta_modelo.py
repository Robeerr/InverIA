"""La versión de Gemini que se enseña es la que se está usando.

`GEMINI_MODEL` es overridable por variable de entorno a propósito: el día que Google
retire o renombre un modelo hay que poder cambiarlo sin desplegar. Eso convierte
cualquier nombre de modelo escrito a mano en una mentira en diferido — y así estaba:
el endpoint decía "Gemini 2.5 Flash" mientras corría `gemini-3.6-flash`.

Ejecutar:  cd backend && pytest tests/test_etiqueta_modelo.py -v
"""
import re
from pathlib import Path

import ai_analysis
import server


def test_la_etiqueta_sale_del_modelo_real(monkeypatch):
    monkeypatch.setattr(ai_analysis, "GEMINI_MODEL", "gemini-3.6-flash")
    assert server._etiqueta_gemini() == "Gemini 3.6 Flash"


def test_cambiar_la_variable_de_entorno_cambia_lo_que_se_lee(monkeypatch):
    """Es el punto entero: si no sigue al valor real, vuelve a caducar sola."""
    monkeypatch.setattr(ai_analysis, "GEMINI_MODEL", "gemini-flash-latest")
    assert server._etiqueta_gemini() == "Gemini Flash Latest"


def test_sin_modelo_no_se_inventa_una_version(monkeypatch):
    monkeypatch.setattr(ai_analysis, "GEMINI_MODEL", "")
    assert server._etiqueta_gemini() == "Gemini"


def test_el_endpoint_no_lleva_ninguna_version_escrita_a_mano():
    """Frontera: la etiqueta del selector no puede volver a llevar un número fijo.

    Se mira el código y no la respuesta porque lo que se protege es la forma de
    escribirlo: un `label` con "Gemini 2.5" dentro pasaría cualquier test de valor que
    fijara ese mismo número.
    """
    src = Path(server.__file__).read_text(encoding="utf-8")
    bloque = src[src.index("async def available_models"):]
    bloque = bloque[:bloque.index("\n\n\n")]
    versiones = re.findall(r"Gemini\s+\d+\.\d+", bloque)
    assert not versiones, f"versión de Gemini escrita a mano en /models: {versiones}"
