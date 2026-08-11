"""Confluencia motor ↔ fuentes: los umbrales y sus fronteras.

Los umbrales salieron de medir la distribucion real con `inspeccion_confluencia.py`, no
de elegirlos a ojo. Este fichero los congela — y sobre todo congela las FRONTERAS, que es
donde un `>=` mal puesto no se nota nunca hasta que un ticker aparece en el grupo
equivocado y nadie sabe por que.

    >=2 fuentes distintas + motor >=65  ->  ACUERDO
    >=2 fuentes distintas + motor <45   ->  CHOQUE
    45 a 64,9                            ->  NEUTRAL
"""
import pytest

import confluencia as c


def clas(n_fuentes=2, pos=0, neg=0, score=None):
    return c.clasificar(n_fuentes, pos, neg, score)


# ── Las fronteras ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("score,esperado", [
    (64.9, "NEUTRAL"),   # justo por debajo: todavia no acompaña
    (65.0, "ACUERDO"),   # el limite entra
    (65.1, "ACUERDO"),
])
def test_frontera_del_acuerdo(score, esperado):
    assert clas(pos=3, score=score) == esperado


@pytest.mark.parametrize("score,esperado", [
    (44.9, "CHOQUE"),    # el limite del choque es ESTRICTO: 44,9 ya evita
    (45.0, "NEUTRAL"),   # 45 exacto ya no es choque
    (45.1, "NEUTRAL"),
])
def test_frontera_del_choque(score, esperado):
    assert clas(pos=3, score=score) == esperado


def test_la_franja_intermedia_entera_es_neutral():
    """De 45 a 64,9 el motor no dice ni una cosa ni la otra."""
    for score in (45.0, 50.0, 55.5, 60.0, 64.9):
        assert clas(pos=3, score=score) == "NEUTRAL", score


def test_los_dos_umbrales_no_se_solapan_ni_dejan_hueco():
    """Barrido fino: cada decimo de punto cae en uno y solo un estado, sin saltos."""
    vistos = []
    for i in range(0, 1001):
        s = i / 10.0
        vistos.append((s, clas(pos=3, score=s)))
    estados = [e for _, e in vistos]
    assert set(estados) == {"CHOQUE", "NEUTRAL", "ACUERDO"}
    # Y el orden es monotono: choque, luego neutral, luego acuerdo. Sin islas.
    cambios = [e for i, e in enumerate(estados) if i == 0 or e != estados[i - 1]]
    assert cambios == ["CHOQUE", "NEUTRAL", "ACUERDO"]


# ── El minimo de fuentes ─────────────────────────────────────────────────────
def test_una_sola_fuente_no_basta_ni_para_acuerdo_ni_para_choque():
    """Una fuente es una opinion, no un consenso. Aunque el motor acompañe del todo."""
    assert clas(n_fuentes=1, pos=1, score=95) == "NEUTRAL"
    assert clas(n_fuentes=1, pos=1, score=10) == "NEUTRAL"


def test_dos_fuentes_ya_cuentan():
    assert clas(n_fuentes=2, pos=2, score=95) == "ACUERDO"
    assert clas(n_fuentes=2, pos=2, score=10) == "CHOQUE"


def test_las_fuentes_son_DISTINTAS_no_menciones():
    """La firma recibe `n_fuentes`, no `menciones`: cuarenta correos del mismo boletin
    son una sola opinion repetida. Quien llama es responsable de deduplicar, y ambos
    endpoints lo hacen."""
    import inspect
    assert list(inspect.signature(c.clasificar).parameters)[0] == "n_fuentes"


# ── Sin fuentes: la regla dura ───────────────────────────────────────────────
@pytest.mark.parametrize("score", [None, 0, 50, 95, 100])
def test_sin_fuentes_nunca_hay_confluencia(score):
    """Un ticker con score 95 del que nadie ha hablado NO es un acuerdo: es una idea
    propia. Llamarlo confluencia seria fabricar una coincidencia que no existe."""
    assert clas(n_fuentes=0, pos=0, neg=0, score=score) == "SIN_FUENTES"


# ── Sin motor ────────────────────────────────────────────────────────────────
def test_sin_veredicto_del_motor_es_insuficiente_y_no_neutral():
    """Falta una de las dos opiniones: no se ha cruzado nada. «Neutral» sugeriria que se
    compararon y empataron."""
    assert clas(n_fuentes=3, pos=3, score=None) == "INSUFICIENTE"
    assert clas(n_fuentes=3, neg=3, score=None) == "INSUFICIENTE"


def test_sin_motor_pero_tambien_sin_fuentes_manda_sin_fuentes():
    assert clas(n_fuentes=0, score=None) == "SIN_FUENTES"


# ── Mixto ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("score", [None, 10, 50, 95])
def test_mixto_gana_a_cualquier_score(score):
    """Si las fuentes discrepan entre ellas no hay una opinion con la que cruzar la del
    motor. Se dice, en vez de resolverlo por mayoria."""
    assert clas(n_fuentes=4, pos=3, neg=1, score=score) == "MIXTO"


def test_mixto_no_se_resuelve_por_mayoria():
    assert clas(n_fuentes=9, pos=8, neg=1, score=95) == "MIXTO"


# ── Choque en las dos direcciones ────────────────────────────────────────────
def test_choque_cuando_las_fuentes_empujan_y_el_motor_evita():
    assert clas(n_fuentes=3, pos=3, score=20) == "CHOQUE"


def test_choque_cuando_las_fuentes_evitan_y_el_motor_empuja():
    assert clas(n_fuentes=3, neg=3, score=80) == "CHOQUE"


def test_fuentes_negativas_y_motor_bajo_se_queda_en_neutral():
    """Los dos coinciden en que no. Es un acuerdo, pero NEGATIVO, y ACUERDO se lee en la
    interfaz como «esto merece tu atencion». Merece un estado propio; darselo es una
    decision de producto y no de umbral."""
    assert clas(n_fuentes=3, neg=3, score=20) == "NEUTRAL"


# ── Menciones sin sentimiento ────────────────────────────────────────────────
def test_menciones_sin_sentimiento_son_neutral():
    assert clas(n_fuentes=3, pos=0, neg=0, score=95) == "NEUTRAL"


# ── El objeto que viaja ──────────────────────────────────────────────────────
def test_evaluar_devuelve_el_estado_y_su_frase():
    e = c.evaluar(3, 3, 0, 72)
    assert e["estado"] == "ACUERDO"
    assert "72" in e["texto"] and "3 fuentes" in e["texto"]
    assert (e["n_fuentes"], e["positivos"], e["negativos"], e["score_motor"]) == (3, 3, 0, 72)


def test_los_estados_sin_nada_que_contar_no_inventan_frase():
    assert c.evaluar(0, 0, 0, None)["texto"] is None
    assert c.evaluar(3, 0, 0, 50)["texto"] is None


def test_la_frase_describe_y_no_recomienda():
    """Misma regla que en tesis.py: aqui no se dice que hacer."""
    prohibido = ("compra", "vende", "deberias", "conviene", "recomend", "cautela", "evita tu")
    for args in [(3, 3, 0, 90), (3, 3, 0, 10), (3, 0, 3, 90), (4, 3, 1, 50), (2, 2, 0, None)]:
        texto = (c.evaluar(*args)["texto"] or "").lower()
        for p in prohibido:
            assert p not in texto, f"{args}: «{texto}»"


def test_el_singular_de_una_fuente_esta_bien_escrito():
    assert "1 fuente " in c.evaluar(1, 1, 0, None)["texto"]


def test_evaluar_solo_produce_estados_declarados():
    for nf in (0, 1, 2, 5):
        for pos, neg in ((0, 0), (3, 0), (0, 3), (2, 2)):
            for score in (None, 10, 45, 64.9, 65, 99):
                assert c.evaluar(nf, pos, neg, score)["estado"] in c.ESTADOS


def test_aguanta_entradas_a_none():
    assert c.evaluar(None, None, None, None)["estado"] == "SIN_FUENTES"


# ── Los umbrales se pueden barrer sin duplicar la logica ─────────────────────
def test_los_umbrales_son_sustituibles_para_la_inspeccion():
    laxo = {"min_fuentes": 1, "score_alto": 55, "score_bajo": 40}
    assert c.clasificar(1, 1, 0, 60, laxo) == "ACUERDO"
    assert c.clasificar(1, 1, 0, 60) == "NEUTRAL"


def test_el_script_de_inspeccion_usa_esta_misma_logica():
    """Si el script tuviera su propia copia, la distribucion que informa podria dejar de
    corresponder con lo que la app hace de verdad."""
    import inspeccion_confluencia as insp
    assert insp.clasificar({"n_fuentes": 2, "positivos": 2, "negativos": 0, "score": 70},
                           None) == "ACUERDO"
