"""Tests del SCORE DE POTENCIAL (opportunities._potential_score).

Este score decide qué acciones sube el buscador arriba. Estos tests fijan su
comportamiento esperado como "contrato": si un día se retocan los pesos o el
guardián de tendencia, `pytest` avisa si se rompe la lógica de discriminación
(p. ej. si un value trap tipo CRM/SLB dejara de ser penalizado).

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from opportunities import _potential_score  # noqa: E402


def score(**kw):
    """Wrapper: devuelve solo el número de score (primer elemento de la tupla)."""
    return _potential_score(
        kw.get("rev_g"), kw.get("eps_g"), kw.get("pe"), kw.get("dist_52w"),
        cons_score=kw.get("cons_score"), ret_26w=kw.get("ret_26w"),
        ret_52w=kw.get("ret_52w"), rel_strength=kw.get("rel_strength"),
    )[0]


# ── Rango válido ────────────────────────────────────────────────────────────

def test_score_siempre_entre_0_y_100():
    """El score nunca puede salirse de [0, 100], pase lo que pase de entrada."""
    casos = [
        dict(rev_g=200, eps_g=200, pe=1, dist_52w=-12, cons_score=100, ret_26w=100, ret_52w=100, rel_strength=100),
        dict(rev_g=-50, eps_g=-50, pe=-10, dist_52w=-90, cons_score=0, ret_26w=-90, ret_52w=-90, rel_strength=-90),
        dict(),  # todo None
    ]
    for c in casos:
        s = score(**c)
        assert 0 <= s <= 100, f"score fuera de rango: {s} con {c}"


def test_sin_datos_no_revienta():
    """Con todo a None debe devolver un número (0), no lanzar excepción."""
    assert score() == 0


# ── Discriminación: buenas arriba, malas abajo ──────────────────────────────

def test_joya_puntua_alto():
    """Crece rápido + barata (PEG<1) + retroceso sano + analistas comprar +
    tendencia alcista → debe ser una oportunidad fuerte (>75)."""
    s = score(rev_g=45, eps_g=30, pe=25, dist_52w=-12,
              cons_score=85, ret_26w=20, ret_52w=40, rel_strength=15)
    assert s > 75, f"la joya debería puntuar >75, dio {s}"


def test_value_trap_crm_penalizado():
    """Sector muerto tipo CRM: crece poco, cara, cae en el año y peor que el
    mercado → el guardián de tendencia debe hundirla (<30)."""
    s = score(rev_g=11, eps_g=8, pe=45, dist_52w=-25,
              cons_score=48, ret_26w=-12, ret_52w=-22, rel_strength=-18)
    assert s < 30, f"el value trap debería puntuar <30, dio {s}"


def test_slb_delicada_penalizada_pese_a_peg_bajo():
    """SLB: parece barata (PEG bajo) pero en tendencia bajista y peor que el
    mercado. El guardián debe pesar más que la 'ganga' aparente (<40)."""
    s = score(rev_g=14, eps_g=10, pe=13, dist_52w=-30,
              cons_score=62, ret_26w=-8, ret_52w=-16, rel_strength=-12)
    assert s < 40, f"SLB delicada debería puntuar <40, dio {s}"


def test_joya_supera_a_value_trap():
    """Invariante clave: una buena oportunidad SIEMPRE por encima de un value trap."""
    joya = score(rev_g=45, eps_g=30, pe=25, dist_52w=-12,
                 cons_score=85, ret_26w=20, ret_52w=40, rel_strength=15)
    trap = score(rev_g=11, eps_g=8, pe=45, dist_52w=-25,
                 cons_score=48, ret_26w=-12, ret_52w=-22, rel_strength=-18)
    assert joya > trap + 30, f"la joya ({joya}) debe superar claramente al trap ({trap})"


# ── Efecto de cada factor (monotonía) ───────────────────────────────────────

def test_mas_crecimiento_mejor():
    """A igualdad de todo lo demás, más crecimiento de ventas → más score."""
    base = dict(eps_g=10, pe=20, dist_52w=-12, cons_score=70, ret_26w=10, ret_52w=20, rel_strength=5)
    assert score(rev_g=50, **base) > score(rev_g=15, **base)


def test_mejor_valoracion_mejor():
    """A igualdad de crecimiento, PER más bajo (más barata) → más score."""
    base = dict(rev_g=30, eps_g=15, dist_52w=-12, cons_score=70, ret_26w=10, ret_52w=20, rel_strength=5)
    barata = score(pe=15, **base)   # PEG 0.5
    cara = score(pe=120, **base)    # PEG 4
    assert barata > cara, f"la barata ({barata}) debe puntuar más que la cara ({cara})"


def test_guardian_penaliza_tendencia_bajista():
    """El MISMO fundamental puntúa menos si la acción está en tendencia bajista."""
    base = dict(rev_g=30, eps_g=15, pe=25, dist_52w=-15, cons_score=70)
    alcista = score(ret_26w=15, ret_52w=30, rel_strength=10, **base)
    bajista = score(ret_26w=-10, ret_52w=-20, rel_strength=-15, **base)
    assert alcista > bajista, f"alcista ({alcista}) debe superar a bajista ({bajista})"


def test_consenso_analistas_suma():
    """Mejor consenso de Wall Street → más score, resto igual."""
    base = dict(rev_g=30, eps_g=15, pe=25, dist_52w=-12, ret_26w=10, ret_52w=20, rel_strength=5)
    assert score(cons_score=90, **base) > score(cons_score=50, **base)


# ── Etiquetas de valoración ─────────────────────────────────────────────────

def test_etiqueta_infravalorada_peg_bajo():
    _, val, _ = _potential_score(40, 20, 20, -12)  # PEG 0.5
    assert "infravalorada" in val.lower()


def test_etiqueta_cara_peg_alto():
    _, val, _ = _potential_score(20, 10, 120, -12)  # PEG 6
    assert "cara" in val.lower()
