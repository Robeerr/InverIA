"""Tests de la detección ALGORÍTMICA de líneas de gráfico (chart_lines)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chart_lines  # noqa: E402


def _candles(closes, spread=2.0):
    return [{"high": c + spread, "low": c - spread, "close": c, "date": f"d{i}"}
            for i, c in enumerate(closes)]


def test_pocas_velas_no_revienta():
    for r in (chart_lines.detect_lines([]), chart_lines.detect_lines(_candles([1, 2, 3]))):
        assert r["trendlines"] == [] and r["levels"] == []
        assert r["pattern"] is None and r["zones"] == []


def _noisy_uptrend(seed=3, n=120):
    rng = np.random.default_rng(seed)
    return list(np.linspace(100, 140, n) + rng.normal(0, 2, n))


def test_detecta_tendencia_alcista():
    closes = _noisy_uptrend()
    r = chart_lines.detect_lines(_candles(closes), current_price=closes[-1])
    assert len(r["trendlines"]) >= 1
    assert all(tl["direction"] in ("alcista", "bajista") for tl in r["trendlines"])


def test_trendline_tiene_dos_puntos_ordenados():
    closes = _noisy_uptrend()
    r = chart_lines.detect_lines(_candles(closes), current_price=closes[-1])
    for tl in r["trendlines"]:
        assert len(tl["points"]) == 2
        assert tl["points"][0]["index"] < tl["points"][1]["index"]


def test_niveles_horizontales_en_rango():
    # Precio oscilando entre 90 y 110 varias veces → niveles cerca de esos extremos.
    closes = [100 + 10 * np.sin(i / 3) for i in range(120)]
    r = chart_lines.detect_lines(_candles(closes), current_price=closes[-1])
    for lv in r["levels"]:
        assert lv["touches"] >= 2
        assert lv["role"] in ("soporte", "resistencia")
        assert 80 <= lv["price"] <= 120


def test_detecta_doji():
    velas = [{"open": 100, "high": 102, "low": 98, "close": 100.05, "date": f"d{i}"} for i in range(20)]
    r = chart_lines.detect_lines(velas)
    assert r["candlestick"] and r["candlestick"]["tipo"] == "doji"


def test_detecta_envolvente_alcista():
    velas = [{"open": 100 - i * 0.1, "high": 101, "low": 99, "close": 99.5 - i * 0.1, "date": f"d{i}"} for i in range(18)]
    velas.append({"open": 98, "high": 98.2, "low": 96, "close": 96.5, "date": "d18"})
    velas.append({"open": 96, "high": 99, "low": 95.8, "close": 98.8, "date": "d19"})
    r = chart_lines.detect_lines(velas)
    assert r["candlestick"] and r["candlestick"]["sentido"] == "alcista"


def test_candlestick_tiene_sentido_valido():
    velas = [{"open": 100, "high": 102, "low": 98, "close": 100.05, "date": f"d{i}"} for i in range(20)]
    r = chart_lines.detect_lines(velas)
    if r["candlestick"]:
        assert r["candlestick"]["sentido"] in ("alcista", "bajista", "indecision")


def test_resultado_serializable():
    closes = list(np.linspace(50, 80, 100))
    r = chart_lines.detect_lines(_candles(closes))
    import json
    json.dumps(r)  # no debe lanzar
