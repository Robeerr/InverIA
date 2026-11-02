"""El registro PASIVO de una llamada a Gemini: apunta, y no cambia nada.

`ai_analysis` es de toda la web. La trazabilidad de la investigación necesita saber el
modelo real, la respuesta original, el motivo de parada, los tokens y si el JSON hubo que
repararlo, y lo apunta en un registro que solo existe si alguien lo pone. Estos tests
fijan las dos mitades: que se apunta todo, y que con o sin registro la llamada devuelve
exactamente lo mismo.

Gemini es un doble: ninguna red.
"""
import asyncio
import json
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import ai_analysis


class _Parada:
    def __init__(self, nombre):
        self.name = nombre


class _Respuesta:
    def __init__(self, texto, parada="STOP", salida=400):
        self.text = texto
        self.candidates = [types.SimpleNamespace(finish_reason=_Parada(parada))]
        self.usage_metadata = types.SimpleNamespace(
            prompt_token_count=3000, candidates_token_count=salida,
            thoughts_token_count=300, total_token_count=3000 + salida + 300)


class _Cliente:
    def __init__(self, guion):
        self.guion = list(guion)            # respuestas o excepciones, en orden
        self.llamadas = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.llamadas.append({"model": model, "contents": contents, "config": config})
        paso = self.guion.pop(0)
        if isinstance(paso, Exception):
            raise paso
        return paso


@pytest.fixture
def gemini(monkeypatch):
    """Gemini falso con una sola clave, la gratuita."""
    tipos = types.SimpleNamespace(
        ThinkingConfig=lambda **kw: ("thinking", kw),
        GenerateContentConfig=lambda **kw: ("config", tuple(sorted(kw))))
    monkeypatch.setattr(ai_analysis, "GEMINI_AVAILABLE", True)
    monkeypatch.setattr(ai_analysis, "genai_types", tipos)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-gratis")
    monkeypatch.delenv("GEMINI_API_KEY_PAID", raising=False)

    def montar(guion):
        cliente = _Cliente(guion)
        monkeypatch.setattr(ai_analysis, "_genai_client", lambda key: cliente)
        return cliente
    return montar


def _llamar(registro=None):
    async def correr():
        marca = ai_analysis.REGISTRO_LLAMADA.set(registro) if registro is not None else None
        try:
            return await ai_analysis._analyze_with_gemini_free(
                "gemini-3.8-flash", "usuario", "sistema", 1200)
        finally:
            if marca is not None:
                ai_analysis.REGISTRO_LLAMADA.reset(marca)
    return asyncio.run(correr())


LECTURA = {"hay_informacion": True, "resumen": "x", "confianza": 95}


def test_apunta_el_modelo_la_respuesta_la_parada_y_los_tokens(gemini):
    gemini([_Respuesta(json.dumps(LECTURA))])
    registro = {}
    datos = _llamar(registro)
    assert datos["resumen"] == "x"
    assert registro["modelo_real"] == "gemini-3.8-flash"
    assert registro["respuesta_bruta"] == json.dumps(LECTURA)
    assert registro["finish_reason"] == "STOP"
    assert registro["tokens"] == {"entrada": 3000, "salida": 400, "pensamiento": 300,
                                  "total": 3700}
    assert registro["parseo"] == "directo"
    assert registro["clave"] == "GRATIS"


def test_con_o_sin_registro_devuelve_EXACTAMENTE_lo_mismo(gemini):
    c1 = gemini([_Respuesta(json.dumps(LECTURA))])
    sin = _llamar()
    c2 = gemini([_Respuesta(json.dumps(LECTURA))])
    con = _llamar({})
    assert sin == con
    assert c1.llamadas == c2.llamadas                     # y la misma petición


def test_un_JSON_cortado_queda_como_REPARADO(gemini):
    # Cortado a mitad del resumen: sin la confianza ni el cierre, como el de RDDT.
    cortado = '{"hay_informacion": true, "resumen": "Reddit present'
    gemini([_Respuesta(cortado, parada="MAX_TOKENS")])
    registro = {}
    datos = _llamar(registro)
    assert "confianza" not in datos
    assert registro["parseo"] == "reparado"
    assert registro["finish_reason"] == "MAX_TOKENS"


def test_el_reintento_sin_thinking_guarda_las_dos_respuestas(gemini):
    gemini([_Respuesta("esto no es json"), _Respuesta(json.dumps(LECTURA))])
    registro = {}
    _llamar(registro)
    assert registro["reintento_sin_thinking"] is True
    assert registro["respuesta_bruta_descartada"] == "esto no es json"
    assert registro["respuesta_bruta"] == json.dumps(LECTURA)


def test_los_intentos_fallidos_quedan_apuntados_y_SIN_claves(gemini, monkeypatch):
    async def sin_espera(_s):
        return None
    monkeypatch.setattr(ai_analysis.asyncio, "sleep", sin_espera)
    gemini([RuntimeError("503 UNAVAILABLE high demand https://x.example/v1?key=SECRETO"),
            _Respuesta(json.dumps(LECTURA))])
    registro = {}
    _llamar(registro)
    primero, segundo = registro["intentos"]
    assert primero["resultado"] == "transitorio"
    assert "SECRETO" not in primero["error"] and "key=***" in primero["error"]
    assert segundo["resultado"] == "respuesta"


def test_sin_registro_no_apunta_nada_ni_rompe(gemini):
    gemini([_Respuesta(json.dumps(LECTURA))])
    assert _llamar() == LECTURA | {"_ai_tier": "free", "_ai_model": "gemini-3.8-flash"}
    assert ai_analysis.REGISTRO_LLAMADA.get() is None


def test_run_model_apunta_el_routing_y_el_modelo_real(monkeypatch):
    async def falso(model_id, user_msg, system_prompt, max_tokens):
        return {"ok": True}
    monkeypatch.setattr(ai_analysis, "_analyze_with_gemini_free", falso)
    registro = {}

    async def correr():
        marca = ai_analysis.REGISTRO_LLAMADA.set(registro)
        try:
            return await ai_analysis._run_model("gemini-2.5-flash", "s", "u", max_tokens=1200)
        finally:
            ai_analysis.REGISTRO_LLAMADA.reset(marca)
    assert asyncio.run(correr()) == {"ok": True}
    assert registro["clave_de_routing"] == "gemini-2.5-flash"
    assert registro["modelo_real"] == ai_analysis.GEMINI_MODEL
    assert registro["max_tokens"] == 1200
