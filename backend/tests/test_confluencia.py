"""Confluencia = fuentes × elegibilidad estructural. Y nada más.

Reescrito desde cero. El fichero anterior probaba el contrato viejo —fuentes × score,
con cortes en 65 y 45— y esos casos no se adaptan: el eje que medían ha desaparecido.

DOS COSAS DISTINTAS SE PRUEBAN AQUÍ

1. Que la clasificación hace lo que dice, incluidos los bordes de ausencia.
2. Que sigue siendo DESCRIPTIVA. Un estado de confluencia no puede autorizar una compra,
   ubicar una entrada ni sustituir el veto de `tendencia.py`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import confluencia as c  # noqa: E402


# ── Los dos estados que dicen algo ───────────────────────────────────────────

def test_acuerdo_exige_fuentes_favorables_y_elegibilidad():
    assert c.clasificar(2, 2, 0, "ALCISTA") == "ACUERDO"
    assert c.clasificar(5, 4, 0, "ALCISTA") == "ACUERDO"


def test_choque_cuando_las_fuentes_empujan_algo_no_elegible():
    assert c.clasificar(2, 2, 0, "BAJISTA") == "CHOQUE"


def test_choque_tambien_en_el_sentido_contrario():
    """Las fuentes desconfían y la estructura sí acompaña. Es el mismo desacuerdo."""
    assert c.clasificar(2, 0, 2, "ALCISTA") == "CHOQUE"


def test_el_choque_necesita_el_mismo_minimo_de_fuentes():
    assert c.clasificar(1, 1, 0, "BAJISTA") == "NEUTRAL"
    assert c.clasificar(1, 0, 1, "ALCISTA") == "NEUTRAL"


# ── Ausencias: fallo cerrado en los dos sentidos ─────────────────────────────

def test_sin_menciones_no_hay_confluencia():
    """Un ticker elegible del que nadie ha hablado no es un acuerdo: es una idea propia.
    Fabricar una coincidencia que no existe sería el peor fallo posible aquí."""
    assert c.clasificar(0, 0, 0, "ALCISTA") == "SIN_FUENTES"


def test_sin_tendencia_clasificable_es_insuficiente_no_neutral():
    """«No lo sé» y «se compararon y empataron» son cosas distintas."""
    assert c.clasificar(3, 3, 0, "SIN_DATOS") == "INSUFICIENTE"


def test_una_tendencia_desconocida_tambien_es_insuficiente():
    """Fallo cerrado: si aparece un estado nuevo y nadie actualiza el mapa, no se
    fabrica un acuerdo."""
    for basura in ("VOLATIL", "", None, 7):
        assert c.clasificar(3, 3, 0, basura) == "INSUFICIENTE", basura


def test_ninguna_ausencia_produce_acuerdo_ni_choque():
    """El invariante que resume los tres de arriba."""
    for tend in (None, "SIN_DATOS", "LO_QUE_SEA"):
        for n, pos, neg in ((0, 0, 0), (0, 3, 0), (5, 0, 0)):
            assert c.clasificar(n, pos, neg, tend) not in ("ACUERDO", "CHOQUE")


# ── Los estados que no dicen nada ────────────────────────────────────────────

def test_fuentes_divididas_no_se_promedian():
    """Que las fuentes discrepen entre ellas es información. Un promedio la borraría."""
    assert c.clasificar(4, 3, 1, "ALCISTA") == "MIXTO"
    assert c.clasificar(4, 1, 3, "BAJISTA") == "MIXTO"


def test_mixto_manda_sobre_la_tendencia():
    """Sin una opinión con la que cruzar, la elegibilidad no puede decidir sola."""
    for tend in ("ALCISTA", "BAJISTA", "INDEFINIDA", "SIN_DATOS"):
        assert c.clasificar(4, 2, 2, tend) == "MIXTO", tend


def test_indefinida_es_neutral_no_choque():
    """No es un choque porque no hay nada a lo que oponerse: la acción no está en
    tendencia bajista, simplemente no está clara."""
    assert c.clasificar(3, 3, 0, "INDEFINIDA") == "NEUTRAL"


def test_menciones_sin_polaridad_son_neutrales():
    assert c.clasificar(3, 0, 0, "ALCISTA") == "NEUTRAL"


def test_el_acuerdo_negativo_se_queda_en_neutral():
    """Fuentes desfavorables + no elegible ES un acuerdo, pero negativo. `ACUERDO` se lee
    como «esto merece tu atención», y usarlo aquí invitaría a mirar justo lo que no hay
    que mirar. Decisión de producto, deliberada, que sobrevive al cambio de contrato."""
    assert c.clasificar(3, 0, 3, "BAJISTA") == "NEUTRAL"


def test_por_debajo_del_minimo_de_fuentes_es_neutral():
    assert c.clasificar(1, 1, 0, "ALCISTA") == "NEUTRAL"
    assert c.MIN_FUENTES == 2


# ── El objeto que viaja ──────────────────────────────────────────────────────

def test_evaluar_emite_tendencia_y_no_score():
    r = c.evaluar(2, 2, 0, "ALCISTA")
    assert r["tendencia"] == "ALCISTA"
    assert "score_motor" not in r
    assert "score" not in r


def test_una_tendencia_invalida_se_emite_como_sin_datos():
    """El campo que sale nunca es basura: o es un estado conocido o es SIN_DATOS."""
    assert c.evaluar(2, 2, 0, "LO_QUE_SEA")["tendencia"] == "SIN_DATOS"
    assert c.evaluar(2, 2, 0, None)["tendencia"] == "SIN_DATOS"


def test_los_estados_mudos_no_traen_texto():
    for estado, args in (("NEUTRAL", (3, 0, 0, "ALCISTA")),
                         ("SIN_FUENTES", (0, 0, 0, "ALCISTA"))):
        r = c.evaluar(*args)
        assert r["estado"] == estado
        assert r["texto"] is None


def test_los_estados_que_dicen_algo_traen_frase():
    for args in ((2, 2, 0, "ALCISTA"), (2, 2, 0, "BAJISTA"),
                 (4, 2, 2, "ALCISTA"), (3, 3, 0, "SIN_DATOS")):
        assert c.evaluar(*args)["texto"]


def test_el_texto_describe_no_recomienda():
    """Aquí no se dice qué hacer, se dice qué hay."""
    textos = [c.evaluar(*a)["texto"] or "" for a in
              ((2, 2, 0, "ALCISTA"), (2, 2, 0, "BAJISTA"), (2, 0, 2, "ALCISTA"))]
    for t in textos:
        bajo = t.lower()
        for verbo in ("compra", "vende", "entra", "stop", "objetivo", "deberías"):
            assert verbo not in bajo, t


# ── El tono de las fuentes no cambió ─────────────────────────────────────────

def test_el_tono_de_fuentes_es_independiente_de_la_tendencia():
    assert c.tono_de_fuentes(3, 0) == "FAVORABLE"
    assert c.tono_de_fuentes(0, 3) == "DESFAVORABLE"
    assert c.tono_de_fuentes(2, 2) == "MIXTO"
    assert c.tono_de_fuentes(0, 0) == "SIN_SENTIDO"


# ── Cobertura del conjunto de estados ────────────────────────────────────────

def test_todos_los_estados_declarados_son_alcanzables():
    casos = [(0, 0, 0, "ALCISTA"), (4, 2, 2, "ALCISTA"), (3, 3, 0, "SIN_DATOS"),
             (2, 2, 0, "ALCISTA"), (2, 2, 0, "BAJISTA"), (3, 3, 0, "INDEFINIDA")]
    alcanzados = {c.clasificar(*x) for x in casos}
    assert alcanzados == set(c.ESTADOS)
