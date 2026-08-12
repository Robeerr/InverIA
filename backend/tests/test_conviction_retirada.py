"""`conviction` era un score disfrazado. Este fichero impide que vuelva.

QUÉ ERA

Una escala 0-100 que sumaba tres catalizadores verificables (35+25+15) MÁS un tramo de
hasta 30 puntos del `potential_score` — el número que mezcla crecimiento, valoración,
punto de entrada, consenso y momentum. Es decir: una métrica que decía medir
catalizadores y que en las combinaciones intermedias la decidía un score de otra cosa.

QUÉ ES AHORA

Un recuento de eventos: `catalizadores` ∈ {0,1,2,3}. La puerta pregunta si llegan a dos.
Nada más.

QUÉ PROTEGE ESTE FICHERO

Que no vuelva ninguna de las tres formas de deshacerlo: reintroducir un score en el
recuento, reutilizar el nombre `conviction` para la métrica nueva, o recrear los
umbrales 65/80 con otros números.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import daily_analyst as da  # noqa: E402

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_FRONT = os.path.join(_BACKEND, "..", "frontend", "src")


def _codigo(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"#.*", "", src)


DA = _codigo(os.path.join(_BACKEND, "daily_analyst.py"))


def _produccion():
    for nombre in sorted(os.listdir(_BACKEND)):
        if nombre.endswith(".py"):
            yield os.path.join(_BACKEND, nombre)
    for raiz, _, ficheros in os.walk(_FRONT):
        for nombre in ficheros:
            if nombre.endswith((".js", ".jsx")) and ".test." not in nombre:
                yield os.path.join(raiz, nombre)


# ── Ningún score vuelve al recuento ──────────────────────────────────────────

def test_el_analista_ya_no_calcula_el_score_de_potencial():
    """No es solo que no lo sume: es que ya no lo pide. Mientras la llamada exista,
    volver a usarlo es una línea."""
    assert "_potential_score" not in DA


def test_no_hay_ninguna_acumulacion_de_puntos():
    """Un `+=` sobre una variable de decisión es como nació el problema."""
    for patron in (r"conviction\s*\+=", r"catalizadores\s*\+=", r"score\s*\+="):
        assert not re.search(patron, DA), patron


def test_no_quedan_los_pesos_viejos():
    """35, 25 y 15 eran los pesos de los catalizadores. Ahora cada uno vale 1."""
    for peso in ("35", "25", "15", "30"):
        assert not re.search(rf"\+=\s*{peso}\b", DA), peso


# ── El nombre no se reutiliza ────────────────────────────────────────────────

def test_ningun_codigo_nuevo_escribe_conviction():
    """Reutilizar el nombre con un dominio nuevo (2-3 en vez de 65-100) sería el
    renombrado semántico que llevamos todo el proyecto evitando."""
    for patron in (r'"conviction"\s*:', r"'conviction'\s*:", r"\[\s*[\"']conviction[\"']\s*\]\s*="):
        assert not re.search(patron, DA), patron


def test_nadie_escribe_potential_score_en_las_ideas():
    assert not re.search(r'"potential_score"\s*:', DA)


def test_el_campo_nuevo_se_llama_catalizadores():
    assert '"catalizadores"' in DA and '"catalizadores_detalle"' in DA


# ── Los umbrales retirados no vuelven ────────────────────────────────────────

def test_no_existe_el_umbral_de_conviccion():
    assert "_CONVICTION_THRESHOLD" not in DA
    assert "min_conv" not in DA


def test_el_65_y_el_80_no_reaparecen_como_puerta():
    """No basta con que no esté la constante: lo que no puede volver es la comparación."""
    for patron in (r"[<>]=?\s*65\b", r"[<>]=?\s*80\b", r"\b65\s*[<>]", r"\b80\s*[<>]"):
        assert not re.search(patron, DA), patron


def test_el_regimen_solo_cambia_el_numero_de_avisos():
    """En rojo se recorta `max_alerts`, no se sube el listón. Si volviera a aparecer un
    umbral por régimen, estaríamos reconstruyendo el 80 con otro número."""
    trozo = DA[DA.index('light == "rojo"'):][:400]
    assert "max_alerts" in trozo
    for prohibido in ("min_", "umbral", "catalizadores >=", "catalizadores <"):
        assert prohibido not in trozo, prohibido


# ── La puerta es un recuento, y solo eso ─────────────────────────────────────

def test_min_catalizadores_no_tiene_familia():
    """Un solo número, sobre eventos independientes. Si aparecieran variantes por
    régimen, por sector o por lo que sea, habría dejado de ser una regla semántica."""
    # Solo las NUMÉRICAS: `POCOS_CATALIZADORES` y compañía son estados de diagnóstico,
    # no umbrales. Lo que no puede haber es un segundo número que module la puerta.
    numericas = [n for n in dir(da)
                 if n.isupper() and "CATALIZADOR" in n
                 and isinstance(getattr(da, n), (int, float))
                 and not isinstance(getattr(da, n), bool)]
    assert numericas == ["MIN_CATALIZADORES"], numericas
    assert da.MIN_CATALIZADORES == 2


def test_la_puerta_solo_mira_el_recuento():
    import inspect
    assert list(inspect.signature(da.pasa_la_puerta).parameters) == ["n"]


def test_hard_catalyst_desaparece():
    """Significaba «tiene al menos uno», y la puerta ya exige dos. Mantenerlo sería una
    comprobación redundante que solo puede desincronizarse."""
    assert "hard_catalyst" not in DA


# ── El veto sigue teniendo un solo dueño ─────────────────────────────────────

def test_el_veto_lo_sigue_decidiendo_tendencia():
    assert "tendencia.hay_tendencia_valida" in DA


def test_los_catalizadores_no_recrean_el_veto_de_tendencia():
    """`catalizadores` no puede convertirse en una segunda autoridad sobre elegibilidad:
    su recuento decide si hay idea, no si la acción es comprable."""
    assert not re.search(r"catalizadores.*NO_COMPRAR", DA)
    assert not re.search(r"catalizadores.*EN_SEGUIMIENTO", DA)


# ── El orden, explícito ──────────────────────────────────────────────────────

def test_el_desempate_esta_escrito_y_es_determinista():
    """Con solo dos valores posibles tras la puerta, los empates son la norma: sin
    criterio, quien entra en el tope lo decide el orden del fichero del universo."""
    trozo = DA[DA.index("candidates.sort"):][:600]
    assert '"symbol"' in trozo
    assert '"detected_at"' in trozo
    assert '"catalizadores"' in trozo


def test_el_resumen_diario_ordena_por_catalizadores():
    assert '("catalizadores", -1)' in DA and '("detected_at", -1)' in DA


# ── Y el centinela de 5b-1 ya cumplió ────────────────────────────────────────

def test_el_centinela_de_5b1_ya_no_existe():
    """Su trabajo era avisar de que retirar el score dejaba el 80 inalcanzable. La
    decisión está tomada; mantenerlo sería vigilar un código que ya no existe."""
    assert not os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_veto_unica_autoridad.py")
    ) or "conviction += (pot / 100) * 30" not in _codigo(
        os.path.join(_BACKEND, "daily_analyst.py"))
