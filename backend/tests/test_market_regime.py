"""Tests del SEMÁFORO DE MERCADO (market_regime._compute).

Fija las reglas del régimen: mercado alcista → verde, bajista → rojo, y el estado
de transición. Es el filtro que evita generar señales de compra cuando el mercado
general está en riesgo (donde fallan más).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import market_regime  # noqa: E402


def _df(closes):
    return pd.DataFrame({"Close": np.array(closes, dtype=float)})


def test_mercado_alcista_es_verde():
    """Precio claramente sobre SMA200 y SMA50 → semáforo verde."""
    closes = list(np.linspace(400, 500, 260))
    r = market_regime._compute(_df(closes))
    assert r["light"] == "verde"
    assert r["above_sma200"] is True


def test_mercado_bajista_es_rojo():
    """Precio por debajo de SMA200 (tendencia primaria bajista) → semáforo rojo."""
    closes = list(np.linspace(500, 380, 260))
    r = market_regime._compute(_df(closes))
    assert r["light"] == "rojo"
    assert r["above_sma200"] is False


def test_devuelve_campos_esperados():
    r = market_regime._compute(_df(list(np.linspace(400, 500, 260))))
    for campo in ("light", "label", "advice", "spy_price", "sma200", "dist_sma200_pct"):
        assert campo in r


def test_light_es_uno_de_los_validos():
    for closes in (np.linspace(400, 500, 260), np.linspace(500, 380, 260),
                   np.linspace(450, 455, 260)):
        r = market_regime._compute(_df(list(closes)))
        assert r["light"] in ("verde", "amarillo", "rojo")
