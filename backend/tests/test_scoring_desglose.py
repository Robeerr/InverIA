"""El desglose del score de potencial: que cuadre y que no cambie nada.

Un score de 0 a 100 sin denominador no se puede discutir. La descomposicion ya se hacia
dentro de `_potential_score` y se tiraba al devolver solo la suma; ahora se devuelve.

DOS COSAS PROTEGE ESTE FICHERO, Y LA SEGUNDA IMPORTA MAS

  1. Que el desglose CUADRE con el score. Un desglose que no reconstruya el numero es
     peor que ninguno: da una sensacion de transparencia que no se sostiene.
  2. Que el contrato viejo siga intacto. `_potential_score` la usan el screener, el
     analista diario y `newsletter_ingest._score_ticker` — este ultimo alimenta la
     confluencia, asi que romperlo se llevaria por delante algo ya aprobado.

EL SCORE NO ES UNA SUMA

Son tres etapas: suma de siete componentes, multiplicador del guardian de tendencia
(1,0 / 0,75 / 0,55) y recorte a [0, 100]. El invariante lo dice tal cual, porque afirmar
que «la suma da el score» seria falso en cuanto el guardian actuara.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from opportunities import _potential_score, _potential_score_detalle  # noqa: E402


# Rejilla determinista: cubre cada valor de cada eje muchas veces sin explotar en tamaño.
REJILLA = {
    "rev_g": [None, -10, 0, 5, 25, 60, 120],
    "eps_g": [None, -5, 0, 10, 50, 90],
    "pe": [None, -3, 0, 8, 25, 120],
    "dist_52w": [None, 2, 0, -5, -12, -25, -45],
    "cons_score": [None, 40, 50, 75, 100],
    "ret_26w": [None, -20, -5, 5, 15, 40],
    "ret_52w": [None, -30, -11, -5, 15, 60],
    "rel_strength": [None, -20, -6, 0, 10],
    "net_margin": [None, -5, 0, 12, 40],
    "roe": [None, -2, 0, 15, 45],
    "debt_to_equity": [None, 0, 0.4, 1.0, 3.0],
}
CLAVES = list(REJILLA)


def casos(n=3000):
    for i in range(n):
        yield {k: REJILLA[k][(i * (j + 3)) % len(REJILLA[k])] for j, k in enumerate(CLAVES)}


# ── 1 · EL INVARIANTE ────────────────────────────────────────────────────────
def test_el_desglose_reconstruye_el_score_exactamente():
    """suma(componentes) × multiplicador, recortado a [0,100] y redondeado = score.

    Si esto falla, el desglose miente: enseñaria unos puntos que no son los que producen
    el numero de al lado.
    """
    for kw in casos():
        d = _potential_score_detalle(**kw)
        suma = sum(c["puntos"] for c in d["componentes"])
        esperado = round(min(max(suma * d["multiplicador"], 0), 100), 1)
        assert esperado == d["score"], (kw, suma, d["multiplicador"], d["score"])


def test_el_bruto_es_la_suma_antes_del_guardian():
    for kw in casos(500):
        d = _potential_score_detalle(**kw)
        assert round(sum(c["puntos"] for c in d["componentes"]), 2) == d["bruto"]


def test_el_subdetalle_de_calidad_suma_su_componente():
    """Calidad va como UN componente con tres partes dentro. Si el subdetalle no sumara
    lo mismo, abrirlo daria una cuenta distinta de la que se ve cerrada."""
    for kw in casos(500):
        d = _potential_score_detalle(**kw)
        cal = next(c for c in d["componentes"] if c["clave"] == "calidad")
        assert round(sum(s["puntos"] for s in cal["sub"]), 2) == cal["puntos"]


# ── 2 · COMPATIBILIDAD: el contrato viejo, intacto ───────────────────────────
def test_potential_score_devuelve_lo_mismo_que_el_detalle():
    """La funcion de siempre es ahora un envoltorio. Si divergieran, los cuatro
    consumidores verian un numero distinto del que se explica en pantalla."""
    for kw in casos():
        d = _potential_score_detalle(**kw)
        assert _potential_score(**kw) == (d["score"], d["val_label"], d["momentum_label"])


def test_sigue_devolviendo_una_tupla_de_tres():
    """Los cuatro consumidores la desempaquetan asi: `pot, val, mom = ...`. Añadir un
    cuarto elemento los romperia todos, incluido el que alimenta la confluencia."""
    r = _potential_score(30, 20, 15, -12)
    assert isinstance(r, tuple) and len(r) == 3


def test_la_firma_no_ha_cambiado():
    import inspect
    esperada = ["rev_g", "eps_g", "pe", "dist_52w", "cons_score", "ret_26w",
                "ret_52w", "rel_strength", "net_margin", "roe", "debt_to_equity"]
    assert list(inspect.signature(_potential_score).parameters) == esperada
    assert list(inspect.signature(_potential_score_detalle).parameters) == esperada


def test_newsletter_ingest_lo_sigue_desempaquetando_igual():
    """`_score_ticker` alimenta la confluencia aprobada. Se comprueba la FORMA de la
    llamada, que es lo que se romperia con un cuarto elemento."""
    ruta = os.path.join(os.path.dirname(__file__), "..", "newsletter_ingest.py")
    with open(ruta, encoding="utf-8") as fh:
        src = fh.read()
    assert "pot, val_label, mom_label = opportunities._potential_score(" in src


# ── 3 · Los componentes se portan ───────────────────────────────────────────
CLAVES_ESPERADAS = ["crecimiento_ventas", "crecimiento_eps", "valoracion_peg",
                    "punto_de_entrada", "consenso_analistas", "calidad",
                    "momentum_reciente"]


def test_los_siete_componentes_estan_siempre_y_en_orden():
    """Siempre los siete, aunque valgan cero: una lista que cambia de largo segun los
    datos no se puede leer de un vistazo ni comparar entre acciones."""
    for kw in casos(300):
        d = _potential_score_detalle(**kw)
        assert [c["clave"] for c in d["componentes"]] == CLAVES_ESPERADAS


def test_ningun_componente_pasa_de_su_maximo():
    for kw in casos():
        for c in _potential_score_detalle(**kw)["componentes"]:
            assert 0 <= c["puntos"] <= c["maximo"], c


def test_los_maximos_suman_110_y_no_100():
    """A proposito, y por eso existe el recorte: se puede llegar al tope sin ser perfecto
    en todo. Normalizar a 100 para que «cuadre» descuadraria los numeros del desglose."""
    d = _potential_score_detalle(60, 50, 8, -12, cons_score=100, ret_26w=40,
                                 net_margin=40, roe=45, debt_to_equity=0)
    assert sum(c["maximo"] for c in d["componentes"]) == 110


def test_todo_componente_lleva_etiqueta_legible():
    d = _potential_score_detalle(30, 20, 15, -12)
    for c in d["componentes"]:
        assert c["etiqueta"] and not c["etiqueta"].islower()


# ── 4 · El guardian es un MULTIPLICADOR, no puntos negativos ────────────────
def test_el_multiplicador_solo_toma_tres_valores():
    vistos = {_potential_score_detalle(**kw)["multiplicador"] for kw in casos()}
    assert vistos <= {1.0, 0.75, 0.55}


def test_ningun_componente_es_negativo_nunca():
    """Meter el guardian como puntos negativos dentro de la suma seria mentir sobre la
    mecanica, y encima esconderia lo que explica que una buena empresa puntue bajo."""
    for kw in casos():
        assert all(c["puntos"] >= 0 for c in _potential_score_detalle(**kw)["componentes"])


@pytest.mark.parametrize("ret_52w,rel,mult", [
    (-30, -20, 0.55),   # cae en el año Y peor que el mercado
    (-30, 10, 0.75),    # solo cae en el año
    (-11, -6, 0.55),
    (-5, -20, 1.0),     # no cae lo bastante: el guardian no actua
    (60, 10, 1.0),
])
def test_el_guardian_actua_donde_debe(ret_52w, rel, mult):
    d = _potential_score_detalle(40, 30, 10, -12, ret_52w=ret_52w, rel_strength=rel)
    assert d["multiplicador"] == mult


def test_el_motivo_acompana_al_castigo_y_solo_entonces():
    con = _potential_score_detalle(40, 30, 10, -12, ret_52w=-30, rel_strength=-20)
    assert con["motivo_multiplicador"]
    sin = _potential_score_detalle(40, 30, 10, -12, ret_52w=60, rel_strength=10)
    assert sin["motivo_multiplicador"] is None


# ── 5 · El recorte se dice ──────────────────────────────────────────────────
def test_se_avisa_cuando_el_recorte_ha_actuado():
    """Sin esto, un 100 podria ser un 100 justo o un 118 recortado, y no son lo mismo."""
    tope = _potential_score_detalle(60, 50, 8, -12, cons_score=100, ret_26w=40,
                                    net_margin=40, roe=45, debt_to_equity=0)
    assert tope["score"] == 100 and tope["recortado"] is True
    normal = _potential_score_detalle(10, 5, 40, -45)
    assert normal["recortado"] is False


# ── 6 · Casos limite ────────────────────────────────────────────────────────
def test_todo_a_none_no_revienta_y_da_cero():
    d = _potential_score_detalle(None, None, None, None)
    assert d["score"] == 0.0
    assert all(c["puntos"] == 0 for c in d["componentes"])
    assert d["multiplicador"] == 1.0


def test_el_score_nunca_sale_del_rango():
    for kw in casos():
        assert 0 <= _potential_score_detalle(**kw)["score"] <= 100
