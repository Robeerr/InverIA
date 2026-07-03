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


# ── Convicción ──────────────────────────────────────────────────────────────

def test_confluencia_total_da_conviccion_alta():
    """Insiders + upgrade + earnings batido + score alto → convicción muy alta y
    catalizador duro presente."""
    m, cons, insider, earnings, quote = _base_inputs()
    conv, reasons, hard, pot = da._score_candidate(m, cons, insider, True, earnings, quote)
    assert conv >= 80
    assert hard is True
    assert len(reasons) >= 3


def test_guardian_tendencia_descarta_bajista():
    """Aunque tenga insiders y upgrade, si está en clara tendencia bajista y peor que
    el mercado, el guardián la descarta (convicción 0) — no vamos contra la tendencia."""
    m, cons, insider, earnings, quote = _base_inputs()
    m = dict(m, return_52w=-25, rel_strength_52w=-18)
    conv, reasons, hard, pot = da._score_candidate(m, cons, insider, True, earnings, quote)
    assert conv == 0


def test_sin_catalizador_duro_no_dispara():
    """Solo un score decente, sin insiders/upgrade/earnings → NO es catalizador duro
    (para eso está el screener; el analista exige un catalizador real)."""
    m, cons, insider, earnings, quote = _base_inputs()
    conv, reasons, hard, pot = da._score_candidate(m, cons, None, False, None, quote)
    assert hard is False


def test_solo_insiders_es_catalizador_duro():
    """Insiders comprando por sí solo YA es catalizador duro (la señal nº1)."""
    m, cons, insider, earnings, quote = _base_inputs()
    conv, reasons, hard, pot = da._score_candidate(m, cons, insider, False, None, quote)
    assert hard is True
    assert any("Insiders" in r for r in reasons)


# ── Horario de mercado ──────────────────────────────────────────────────────

def test_is_market_open_devuelve_bool():
    assert isinstance(da.is_market_open(), bool)
