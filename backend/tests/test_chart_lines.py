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
    assert chart_lines.detect_lines([]) == {"trendlines": [], "levels": []}
    assert chart_lines.detect_lines(_candles([1, 2, 3])) == {"trendlines": [], "levels": []}


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


def test_resultado_serializable():
    closes = list(np.linspace(50, 80, 100))
    r = chart_lines.detect_lines(_candles(closes))
    import json
    json.dumps(r)  # no debe lanzar
