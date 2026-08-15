"""El nombre de modelo que se ENSEÑA es el del modelo que se USA.

Las claves de `MODEL_MAP` son de routing, no nombres: "gemini-2.5-flash" enruta a
`GEMINI_MODEL`, que vale `gemini-3.6-flash`. La clave no se puede renombrar (está en el
localStorage de la gente y en respuestas ya cacheadas), así que lo que hay que garantizar
es que nunca se enseñe. Se enseñaba en dos sitios:

  · el aviso "Análisis completado (gemini-2.5-flash)" tras pulsar Analizar
  · la etiqueta del selector en /api/models, escrita a mano como "Gemini 2.5 Flash"

Ejecutar:  cd backend && pytest tests/test_etiqueta_modelo.py -v
"""
import re
from pathlib import Path

import ai_analysis
import server


# ── El nombre sale del modelo real ───────────────────────────────────────────

def test_la_clave_de_routing_nunca_se_enseña(monkeypatch):
    """El bug tal cual: la clave dice 2.5 y se ejecuta 3.6."""
    monkeypatch.setitem(ai_analysis.MODEL_MAP, "gemini-2.5-flash",
                        ("google_free", "gemini-3.6-flash", True))
    assert ai_analysis.nombre_visible("gemini-2.5-flash") == "Gemini 3.6 Flash"


def test_cambiar_el_modelo_cambia_lo_que_se_lee(monkeypatch):
    """Es el punto entero: GEMINI_MODEL se cambia sin desplegar, así que un nombre
    escrito a mano caduca solo."""
    monkeypatch.setitem(ai_analysis.MODEL_MAP, "gemini-2.5-flash",
                        ("google_free", "gemini-3.7-flash", True))
    assert ai_analysis.nombre_visible("gemini-2.5-flash") == "Gemini 3.7 Flash"


def test_los_modelos_que_no_son_gemini_tienen_su_nombre():
    assert ai_analysis.nombre_visible("gpt-oss-120b") == "GPT-OSS 120B"
    assert ai_analysis.nombre_visible("llama-3.3-70b") == "Llama 3.3 70B"


def test_una_clave_desconocida_no_revienta():
    assert ai_analysis.nombre_visible("lo-que-sea") == "lo-que-sea"
    assert ai_analysis.nombre_visible("") == ""


# ── Fronteras: que no vuelva a escribirse a mano ─────────────────────────────

def _bloque(nombre: str) -> str:
    src = Path(server.__file__).read_text(encoding="utf-8")
    resto = src[src.index(nombre):]
    return resto[:resto.index("\n\n\n")]


def test_el_selector_no_lleva_ninguna_version_escrita_a_mano():
    """Se mira el CÓDIGO y no la respuesta: un `label` con "Gemini 2.5" dentro pasaría
    cualquier test de valor que fijara ese mismo número."""
    versiones = re.findall(r"Gemini\s+\d+\.\d+", _bloque("async def available_models"))
    assert not versiones, f"versión de Gemini escrita a mano en /models: {versiones}"


def test_el_analisis_devuelve_el_nombre_legible_ademas_de_la_clave():
    """Sin esto la pantalla no tiene de dónde sacar el nombre: la clave de routing es lo
    único que sabe, y es justo lo que no debe enseñar."""
    src = Path(server.__file__).read_text(encoding="utf-8")
    assert '"model_label": ai_analysis.nombre_visible(used_model)' in src
    assert '"requested_model_label": ai_analysis.nombre_visible(requested_model)' in src


def test_la_pantalla_no_pinta_la_clave_cruda():
    """El aviso de "Análisis completado" era el sitio donde el usuario lo vio."""
    dash = Path(server.__file__).parent.parent / "frontend/src/pages/Dashboard.jsx"
    src = dash.read_text(encoding="utf-8")
    assert "${res.model}" not in src, "eso pinta la clave de routing, no el modelo"
    assert "${res.requested_model}" not in src
    assert "res.model_label" in src
