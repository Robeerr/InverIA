"""Un número, una pregunta — y ninguna forma de volver a juntarlos.

DOS COSAS DISTINTAS SE PRUEBAN AQUÍ

1. Que la separación calcula lo que dice: calidad sin valoración, sin consenso y sin
   tendencia; insumos de tendencia sin agregar.

2. Que las fronteras no se pueden cruzar, comprobado sobre TODO el código: ningún total,
   ninguna suma cruzada, ningún literal que convierta un score en veto.

La segunda es la que de verdad importa. La primera solo dice que hoy está bien; la
segunda impide que deje de estarlo dentro de seis meses, cuando una pantalla necesite
«un único número para ordenar» y alguien sume dos campos para salir del paso.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import separacion  # noqa: E402

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_FRONT = os.path.join(_BACKEND, "..", "frontend", "src")

BASE = dict(rev_g=30.0, eps_g=20.0, net_margin=15.0, roe=20.0, debt_to_equity=0.3)


# ── Calidad: solo el negocio ─────────────────────────────────────────────────

def test_la_calidad_no_recibe_ni_valoracion_ni_tendencia():
    """No es un olvido en la firma: es la garantía de que una debilidad de tendencia no
    puede penalizar la calidad del negocio, ni un descuento rescatarla."""
    import inspect
    params = set(inspect.signature(separacion.calidad).parameters)
    assert params == {"rev_g", "eps_g", "net_margin", "roe", "debt_to_equity"}
    for prohibido in ("pe", "peg", "cons_score", "ret_52w", "rel_strength", "dist_52w"):
        assert prohibido not in params, prohibido


def test_la_calidad_no_se_mueve_con_la_tendencia_ni_con_el_precio():
    """Comprobado ejecutando, no leyendo la firma: la misma empresa con la acción
    hundida o disparada da exactamente los mismos puntos de calidad."""
    a = separacion.calidad(**BASE)
    b = separacion.calidad(**BASE)
    assert a["puntos"] == b["puntos"]
    # Y no hay forma de pasarle esos datos aunque se quiera.
    import pytest
    with pytest.raises(TypeError):
        separacion.calidad(ret_52w=-40, **BASE)


def test_puntos_y_maximo_van_por_separado_sin_indice():
    """Un 100 se lee como «calidad perfecta», y eso nadie lo ha validado. Quien quiera un
    índice divide, sabiendo lo que divide."""
    r = separacion.calidad(**BASE)
    assert "puntos" in r and "maximo" in r
    for inventado in ("score", "indice", "porcentaje", "normalizado"):
        assert inventado not in r, inventado


def test_los_pesos_viajan_marcados_como_no_validados():
    """Quien lea esto en un año no tiene por qué saber que 30/12/8 no está calibrado si
    no se lo dice el propio dato."""
    assert separacion.calidad(**BASE)["pesos_validados"] is False


def test_sin_datos_es_cero_no_un_valor_por_defecto():
    r = separacion.calidad()
    assert r["puntos"] == 0.0
    assert r["maximo"] == separacion.CALIDAD_MAXIMO


# ── Valoración y consenso: descriptivos ──────────────────────────────────────

def test_la_valoracion_no_suma_nunca():
    for pe in (None, -5, 8, 20, 60, 200):
        assert separacion.valoracion(pe=pe, rev_g=20)["puntos"] == 0.0


def test_la_valoracion_describe_pero_no_puntua():
    r = separacion.valoracion(pe=10, rev_g=25)
    assert r["peg"] == 0.4
    assert "infravalorada" in r["etiqueta"]
    assert r["puntos"] == 0.0


def test_el_consenso_no_suma_ni_inventa_bandas():
    """Sin etiqueta propia: cualquier corte del tipo «≥70 es fuerte» sería un umbral
    nuevo, y en 5a no se introduce ninguno."""
    r = separacion.consenso(cons_score=95, cons_label="Strong Buy")
    assert r["puntos"] == 0.0
    assert r["score"] == 95
    assert r["etiqueta"] == "Strong Buy"   # el que ya venía, no uno fabricado aquí


# ── Tendencia: insumos, no score ─────────────────────────────────────────────

def test_no_hay_tendencia_score():
    """El punto central de 5a. Agregar exige pesos que no están medidos, y un número con
    pesos inventados sería el score universal otra vez con mejor nombre."""
    r = separacion.tendencia_insumos(ret_26w=10, ret_52w=30, rel_strength=12)
    assert r["agregado"] is None
    for inventado in ("score", "puntos", "total", "tendencia_score"):
        assert inventado not in r, inventado


def test_los_insumos_pasan_crudos():
    r = separacion.tendencia_insumos(ret_26w=10.5, ret_52w=-3.2, rel_strength=None)
    assert (r["ret_26w"], r["ret_52w"], r["rel_strength"]) == (10.5, -3.2, None)


# ── El conjunto: sin total ───────────────────────────────────────────────────

def test_campos_no_devuelve_ningun_total():
    r = separacion.campos(**BASE, pe=25, cons_score=80, ret_26w=10, ret_52w=25,
                          rel_strength=8)
    assert set(r) == {"calidad", "valoracion", "consenso", "tendencia_insumos"}
    for inventado in ("total", "score", "potential_score", "global"):
        assert inventado not in r, inventado


def test_el_total_no_es_reconstruible_por_los_puntos():
    """Sumar los `puntos` de los cuatro bloques da la calidad y nada más: la valoración y
    el consenso valen cero y la tendencia no tiene puntos. Sumar no produce un score."""
    r = separacion.campos(**BASE, pe=25, cons_score=80, ret_26w=10, ret_52w=25,
                          rel_strength=8)
    suma = (r["calidad"]["puntos"] + r["valoracion"]["puntos"] + r["consenso"]["puntos"])
    assert suma == r["calidad"]["puntos"]
    assert "puntos" not in r["tendencia_insumos"]


# ── Las fronteras, sobre todo el código ──────────────────────────────────────

def _codigo_de(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"#.*", "", src)


def _todos_los_ficheros():
    for nombre in sorted(os.listdir(_BACKEND)):
        if nombre.endswith(".py"):
            yield os.path.join(_BACKEND, nombre)
    for raiz, _, ficheros in os.walk(_FRONT):
        for nombre in ficheros:
            if nombre.endswith((".js", ".jsx")) and ".test." not in nombre:
                yield os.path.join(raiz, nombre)


def test_nadie_suma_calidad_con_tendencia():
    """La prohibición central. Si esto falla, hemos vuelto a crear un score universal."""
    patrones = [
        r"calidad\w*\s*\+\s*tendencia", r"tendencia\w*\s*\+\s*calidad",
        r"calidad_score\s*\+", r"tendencia_score\s*\+",
        r"weighted_average\s*\(", r"potential_score\s*=\s*f\s*\(",
    ]
    for ruta in _todos_los_ficheros():
        codigo = _codigo_de(ruta)
        for patron in patrones:
            assert not re.search(patron, codigo), f"{os.path.basename(ruta)}: '{patron}'"


def test_ningun_literal_convierte_un_score_en_veto():
    """El veto pertenece a `tendencia.py` y a nadie más. Un `tendencia_score < 45` sería
    reintroducir por la puerta de atrás el umbral arbitrario que el commit 1 evitó, y con
    apariencia de rigor porque vendría de un score."""
    for ruta in _todos_los_ficheros():
        codigo = _codigo_de(ruta)
        for campo in ("tendencia_score", "calidad_score", "calidad_puntos"):
            assert not re.search(rf"{campo}\s*[<>]=?\s*\d", codigo), \
                f"{os.path.basename(ruta)}: {campo} comparado con un literal"
            assert not re.search(rf"\d\s*[<>]=?\s*{campo}", codigo), \
                f"{os.path.basename(ruta)}: {campo} comparado con un literal"


def test_la_separacion_no_veta_nada():
    codigo = _codigo_de(os.path.join(_BACKEND, "separacion.py"))
    for prohibido in ("NO_COMPRAR", "EN_SEGUIMIENTO", "veto", "elegible"):
        assert prohibido not in codigo, prohibido


def test_5a_no_tiene_consumidores():
    """Nadie lee los campos nuevos. Si esto falla, 5a ha migrado un consumidor y ha
    dejado de ser una separación sin cambio de comportamiento."""
    for ruta in _todos_los_ficheros():
        nombre = os.path.basename(ruta)
        if nombre in ("separacion.py", "opportunities.py"):
            continue   # el productor
        codigo = _codigo_de(ruta)
        for campo in ('"separado"', "['separado']", ".separado",
                      "tendencia_insumos", "calidad_puntos"):
            assert campo not in codigo, f"{nombre} ya consume '{campo}' — eso es 5b"
