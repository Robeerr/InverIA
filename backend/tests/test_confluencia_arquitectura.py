"""La confluencia es descriptiva, es única, y no puede volver a decidir.

TRES COSAS SE PROTEGEN AQUÍ

1. Que exista UNA sola implementación. Había dos: `confluencia.py` para el Radar y
   `hoy.confluencia()` para la portada, con estados distintos y los mismos umbrales de
   score duplicados. La misma acción podía salir en ACUERDO en una pantalla y en
   «choque» en la otra.

2. Que siga siendo DESCRIPTIVA. No autoriza una compra, no ubica una entrada, no define
   zona, stop ni tamaño, y no sustituye el veto de `tendencia.py` — lo consume.

3. Que no vuelva ningún score. Los cortes 65/45 medían un número que mezclaba
   crecimiento, valoración, punto de entrada, consenso y momentum.

EL VETO POR EMOJI, AHORA GENERALIZADO

El test de 5b-1 prohibía inspeccionar `"⚠"`. Estaba acotado a un carácter, y por eso NO
cazó `hoy.py`, que hacía lo mismo con `"🔴"`. Aquí se prohíbe ramificar sobre cualquier
emoji: la regla no era ese símbolo, era no meter una decisión dentro de una cadena.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import confluencia  # noqa: E402

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_FRONT = os.path.join(_BACKEND, "..", "frontend", "src")


def _codigo(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"#.*", "", src)


def _modulos():
    for nombre in sorted(os.listdir(_BACKEND)):
        if nombre.endswith(".py"):
            yield nombre, _codigo(os.path.join(_BACKEND, nombre))


CONF = _codigo(os.path.join(_BACKEND, "confluencia.py"))


# ── 1 · Una sola implementación ──────────────────────────────────────────────

def test_solo_confluencia_py_clasifica():
    """Ningún otro módulo puede producir estados de confluencia por su cuenta."""
    for nombre, codigo in _modulos():
        if nombre == "confluencia.py":
            continue
        for estado in ("ACUERDO", "CHOQUE", "MIXTO", "SIN_FUENTES"):
            assert f'"{estado}"' not in codigo or "confluencia" in codigo, nombre


def test_hoy_ya_no_clasifica():
    codigo = dict(_modulos())["hoy.py"]
    assert "def confluencia(" not in codigo
    for muerto in ("acuerdo_alto", "acuerdo_sin_niveles", "solo_motor", "solo_fuentes",
                   "UMBRAL_FUERZA"):
        assert muerto not in codigo, muerto


# ── 2 · Descriptiva: no decide, no ubica ─────────────────────────────────────

def test_no_conoce_zonas_ni_ejecucion():
    for prohibido in ("zona", "stop", "entry", "entrada", "tamano", "tamaño",
                      "fuerza_nivel", "distancia_nivel", "levels_engine", "atr"):
        assert prohibido not in CONF.lower(), prohibido


def test_no_importa_nada_de_ejecucion_ni_de_scores():
    for modulo in ("levels_engine", "separacion", "opportunities", "hoy", "server"):
        assert f"import {modulo}" not in CONF, modulo


def test_ningun_estado_produce_una_decision_de_compra():
    """Si un estado apareciera en la condición que emite NO_COMPRAR o equivalente,
    habría dejado de describir."""
    for nombre, codigo in _modulos():
        for estado in ("ACUERDO", "CHOQUE"):
            for decision in ("NO_COMPRAR", "EN_SEGUIMIENTO", "COMPRAR"):
                patron = rf'{estado}[^\n]{{0,80}}{decision}|{decision}[^\n]{{0,80}}{estado}'
                assert not re.search(patron, codigo), f"{nombre}: {estado}/{decision}"


def test_consume_el_veto_pero_no_lo_recrea():
    """La elegibilidad se decide en `tendencia.py` y en ningún otro sitio."""
    assert "tendencia.hay_tendencia_valida" in CONF
    for propio in ("sma200", "sma50", "precio >", "close"):
        assert propio not in CONF.lower(), propio


def test_nadie_ordena_ni_filtra_por_el_estado():
    for nombre, codigo in _modulos():
        for patron in (r'sort\([^)]*confluencia', r'confluencia[^\n]{0,40}reverse=True',
                       r'if\s+\w*confluencia\w*\s*==\s*["\']ACUERDO'):
            assert not re.search(patron, codigo), f"{nombre}: {patron}"


# ── 3 · Ningún score vuelve ──────────────────────────────────────────────────

def test_no_quedan_los_umbrales_del_score():
    for muerto in ("SCORE_ACUERDO", "SCORE_CHOQUE", "score_motor"):
        for nombre, codigo in _modulos():
            assert muerto not in codigo, f"{nombre}: {muerto}"


def test_evaluar_no_recibe_ningun_score():
    import inspect
    params = list(inspect.signature(confluencia.evaluar).parameters)
    assert params == ["n_fuentes", "positivos", "negativos", "estado_tendencia"]
    assert list(inspect.signature(confluencia.clasificar).parameters) == params


def test_el_modulo_no_compara_contra_ningun_numero_salvo_el_minimo_de_fuentes():
    """Los únicos números que pueden quedar son los del recuento de fuentes."""
    numeros = set(re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)", CONF))
    assert numeros <= {"0", "1", "2"}, sorted(numeros)


# ── El veto por emoji, para cualquier carácter ───────────────────────────────

_EMOJI = r"[\U0001F300-\U0001FAFF☀-➿]"
_INSPECCIONES = (
    rf"""startswith\(\s*["']{_EMOJI}""",
    rf"""["']{_EMOJI}[^"']*["']\s+in\s""",
    rf"""[!=]=\s*["']{_EMOJI}""",
)


def test_nadie_ramifica_sobre_ningun_emoji():
    """Generalizado: la regla no era `⚠` ni `🔴`, era no meter una decisión en una cadena.
    El test anterior estaba acotado a un carácter y por eso `hoy.py` se le escapó."""
    culpables = [n for n, c in _modulos()
                 if any(re.search(p, c) for p in _INSPECCIONES)]
    assert not culpables, f"Deciden leyendo un emoji: {culpables}"


# ── El frontend tampoco decide ───────────────────────────────────────────────

def test_el_componente_no_deriva_estado_de_los_numeros():
    ruta = os.path.join(_FRONT, "components", "Confluencia.jsx")
    codigo = _codigo(ruta)
    assert "confluencia.estado" in codigo
    for propio in ("n_fuentes >", "positivos >", "score", "65", "45"):
        assert propio not in codigo, propio


def test_el_radar_ya_no_pinta_el_veredicto_del_motor():
    codigo = _codigo(os.path.join(_FRONT, "pages", "RadarView.jsx"))
    for muerto in ("verdictStyle", "inveria"):
        assert muerto not in codigo, muerto
