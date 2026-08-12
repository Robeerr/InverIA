"""Tests del ANALISTA INSTITUCIONAL (daily_analyst).

Fijan el comportamiento de la lógica de convicción: que una acción con
catalizadores reales (insiders, upgrade, earnings) puntúe alto, que el guardián
de tendencia descarte las bajistas, y que sin catalizador duro no dispare aviso.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import daily_analyst as da  # noqa: E402


def _base_inputs():
    m = {"revenue_growth": 40, "eps_growth": 25, "pe_ratio": 25,
         "return_26w": 15, "return_52w": 30, "rel_strength_52w": 10, "high_52w": 150}
    cons = {"consensus": "COMPRAR", "score": 82}
    insider = {"net_shares": 50000, "buy_transactions": 3, "sell_transactions": 0}
    earnings = {"quarters": [{"actual": 2.1, "estimate": 1.9, "surprise_percent": 10.5}]}
    quote = {"price": 130, "high_52w": 150, "pe_ratio": 25}
    return m, cons, insider, earnings, quote


# ── Detección de upgrade de analistas ───────────────────────────────────────

def test_detecta_upgrade_cuando_mejora():
    trends = [
        {"strongBuy": 5, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0},  # mes actual
        {"strongBuy": 3, "buy": 8, "hold": 5, "sell": 2, "strongSell": 1},   # mes anterior
    ]
    assert da._detect_upgrade(trends) is True


def test_no_detecta_upgrade_cuando_empeora():
    trends = [
        {"strongBuy": 2, "buy": 5, "hold": 5, "sell": 4, "strongSell": 2},
        {"strongBuy": 5, "buy": 10, "hold": 3, "sell": 1, "strongSell": 0},
    ]
    assert da._detect_upgrade(trends) is False


def test_upgrade_sin_datos_suficientes():
    assert da._detect_upgrade(None) is False
    assert da._detect_upgrade([{"strongBuy": 5}]) is False


# ── Catalizadores ───────────────────────────────────────────────────────────

def test_los_tres_catalizadores_cuentan_uno_cada_uno():
    _, cons, insider, earnings, _ = _base_inputs()
    r = da.catalizadores_de(insider, True, earnings, cons=cons)
    assert r["n"] == 3
    assert set(r["detalle"]) == {"insiders", "mejora_recomendacion", "beat_earnings"}
    assert len(r["razones"]) == 3


def test_el_recuento_va_de_cero_a_tres_y_nada_mas():
    """El dominio es exactamente {0,1,2,3}. Si apareciera cualquier otro valor, alguien
    habría vuelto a ponderar."""
    _, cons, insider, earnings, _ = _base_inputs()
    vistos = set()
    for i in (None, insider):
        for u in (False, True):
            for e in (None, earnings):
                vistos.add(da.catalizadores_de(i, u, e, cons=cons)["n"])
    assert vistos == {0, 1, 2, 3}


def test_uno_solo_no_pasa_la_puerta_ni_siquiera_insiders():
    """Decisión explícita: no hay excepción por importancia histórica de un catalizador.
    Los insiders son la señal que el código llamaba «la más fuerte» y aun así no bastan
    en solitario."""
    _, cons, insider, _, _ = _base_inputs()
    solo_insiders = da.catalizadores_de(insider, False, None, cons=cons)
    assert solo_insiders["n"] == 1
    assert da.pasa_la_puerta(1) is False
    assert da.pasa_la_puerta(2) is True
    assert da.pasa_la_puerta(3) is True


def test_ningun_score_entra_en_el_recuento():
    """La firma es la garantía: no hay por dónde meter fundamentales, valoración,
    tendencia ni ningún score."""
    import inspect
    params = set(inspect.signature(da.catalizadores_de).parameters)
    assert params == {"insider", "upgrade", "earnings", "cons"}


def test_cambiar_fundamentales_no_cambia_el_recuento():
    """Comprobado ejecutando: `cons` solo aporta el NOMBRE de la recomendación al texto."""
    _, _, insider, earnings, _ = _base_inputs()
    a = da.catalizadores_de(insider, True, earnings, cons={"score": 95, "consensus": "Strong Buy"})
    b = da.catalizadores_de(insider, True, earnings, cons={"score": 10, "consensus": "Sell"})
    assert a["n"] == b["n"] == 3
    assert a["detalle"] == b["detalle"]


# ── Veto y puerta son decisiones independientes ─────────────────────────────

def test_la_tendencia_descarta_pero_el_recuento_se_conserva():
    """El punto del rediseño: antes las dos salidas eran un cero indistinguible y no
    había forma de saber si una idea no llegaba por dirección o por catalizadores."""
    _, cons, insider, earnings, _ = _base_inputs()
    v = da.evaluar_candidato(insider, True, earnings, cons=cons, estado_tendencia="BAJISTA")
    assert v["estado"] == da.DESCARTADA_POR_TENDENCIA
    assert v["aceptada"] is False
    assert v["catalizadores"] == 3        # el recuento NO se pierde


def test_pocos_catalizadores_es_otro_diagnostico():
    _, cons, insider, _, _ = _base_inputs()
    v = da.evaluar_candidato(insider, False, None, cons=cons, estado_tendencia="ALCISTA")
    assert v["estado"] == da.POCOS_CATALIZADORES
    assert v["catalizadores"] == 1


def test_aceptada_exige_las_dos_cosas():
    _, cons, insider, earnings, _ = _base_inputs()
    v = da.evaluar_candidato(insider, True, earnings, cons=cons, estado_tendencia="ALCISTA")
    assert v["estado"] == da.ACEPTADA and v["aceptada"] is True


def test_sin_estado_de_tendencia_no_pasa_nada():
    """Por defecto SIN_DATOS. Quien llame sin pasar el estado no cuela la señal."""
    _, cons, insider, earnings, _ = _base_inputs()
    v = da.evaluar_candidato(insider, True, earnings, cons=cons)
    assert v["estado"] == da.DESCARTADA_POR_TENDENCIA


def test_un_estado_desconocido_tampoco_autoriza():
    _, cons, insider, earnings, _ = _base_inputs()
    v = da.evaluar_candidato(insider, True, earnings, cons=cons, estado_tendencia="VOLATIL")
    assert v["aceptada"] is False


# ── El texto que sustituye al «/100» ────────────────────────────────────────

def test_texto_de_catalizadores():
    assert da._texto_catalizadores({"catalizadores": 2}) == "2 catalizadores"
    assert da._texto_catalizadores({"catalizadores": 1}) == "1 catalizador"


def test_los_documentos_historicos_no_se_reinterpretan():
    """Un documento viejo lleva `conviction` en la escala antigua. No se traduce a un
    número de catalizadores: significaba otra cosa y convertirlo sería inventárselo."""
    assert da._texto_catalizadores({"conviction": 82}) == ""
    assert da._texto_catalizadores({}) == ""
    assert da._texto_catalizadores(None) == ""


# ── Horario de mercado ──────────────────────────────────────────────────────

def test_is_market_open_devuelve_bool():
    assert isinstance(da.is_market_open(), bool)
