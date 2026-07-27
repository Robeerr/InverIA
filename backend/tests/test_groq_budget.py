"""Tests del presupuesto de tokens del respaldo de Groq.

Groq free tier son 8000 TPM contando entrada + salida, y max_tokens cuenta como
"solicitado" aunque no se gaste. Antes había un cap fijo de 3000 de salida basado en una
estimación de entrada que se quedó obsoleta (el SYSTEM_PROMPT creció a ~4300 tokens), así
que se pedía por encima del límite: el respaldo daba 429 o devolvía el JSON cortado.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_RUTA = os.path.join(os.path.dirname(__file__), "..", "ai_analysis.py")


def _fuente():
    with open(_RUTA, encoding="utf-8") as fh:
        return fh.read()


def _prompt(nombre):
    m = re.search(nombre + r' = """(.*?)\n"""', _fuente(), re.S)
    assert m, f"No se encontró {nombre} en ai_analysis.py"
    return m.group(1)


def test_prompt_compacto_cabe_de_sobra_en_el_limite():
    """El prompt compacto + un payload generoso debe dejar sitio holgado para la respuesta.

    Se comprueba sobre el fuente (sin importar ai_analysis, que arrastra el SDK de groq)
    porque lo que se quiere fijar es el tamaño del prompt, no el comportamiento del cliente.
    """
    estimar = lambda t: int(len(t) / 3.3) + 1  # noqa: E731 — misma fórmula que el módulo
    compacto = estimar(_prompt("SYSTEM_PROMPT_COMPACTO"))
    completo = estimar(_prompt("SYSTEM_PROMPT"))

    assert compacto < completo / 3, (
        f"El prompt compacto ({compacto} tok) debe ser mucho menor que el completo "
        f"({completo} tok); si crece, vuelve el truncado en el respaldo."
    )
    # Con el payload más grande que cabe esperar, debe quedar sitio de sobra para el JSON.
    salida = int(8000 * 0.9 - (compacto + 2000))
    assert salida >= 3000, f"Solo quedarían {salida} tokens para la respuesta"


def test_prompt_completo_NO_cabe_y_por_eso_existe_el_compacto():
    """Documenta el motivo del cambio: el prompt completo no entra en el free tier."""
    estimar = lambda t: int(len(t) / 3.3) + 1  # noqa: E731
    entrada = estimar(_prompt("SYSTEM_PROMPT")) + 2000  # + payload típico
    assert int(8000 * 0.9 - entrada) < 3000, (
        "Si el prompt completo ya cabe en el límite de Groq, el prompt compacto sobra."
    )


def test_presupuesto_se_calcula_sobre_la_entrada_real():
    """Regresión: no debe volver el cap fijo `min(max_tokens, 3000)`."""
    src = _fuente()
    assert "min(max_tokens, 3000)" not in src, "Ha vuelto el cap fijo de 3000 tokens"
    assert "GROQ_TPM_LIMIT" in src and "_estimar_tokens" in src


def test_estimador_de_tokens_es_conservador():
    """Debe SOBREestimar la entrada: pasarse de largo cuesta un 429, quedarse corto solo
    recorta un poco la respuesta."""
    ai = pytest.importorskip(
        "ai_analysis", reason="requiere el SDK de groq instalado"
    )
    texto = "palabra " * 1000  # 8000 caracteres
    # A 3.3 c/token estima ~2424; el ratio real del español ronda 3.5 (~2285). Debe pasarse.
    assert ai._estimar_tokens(texto) > len(texto) / 3.5
    assert ai._estimar_tokens("") == 1
    assert ai._estimar_tokens(None) == 1
