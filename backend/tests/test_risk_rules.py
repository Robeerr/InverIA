"""Tests del guardián de riesgo/recompensa (risk_rules.min_rr_stop).

Fija el contrato: si el stop deja un R/R en TP1 por debajo del mínimo (1.5), se ciñe
hacia la entrada hasta cumplirlo; si ya es sano, no se toca; nunca se afloja.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from risk_rules import min_rr_stop  # noqa: E402


def test_ciñe_stop_ancho_hasta_rr_minimo():
    # entrada 100, tp1 104.6 (+4.6%), stop 92.4 (-7.6%) → R/R 0.61 → ceñir a 1.5
    nuevo, ajustado = min_rr_stop(100, 104.6, 92.4)
    assert ajustado is True
    assert nuevo == 96.93
    assert round((104.6 - 100) / (100 - nuevo), 2) == 1.5


def test_no_toca_stop_ya_sano():
    # R/R = 10/5 = 2 (>1.5) → no se toca
    nuevo, ajustado = min_rr_stop(100, 110, 95)
    assert ajustado is False
    assert nuevo == 95


def test_nunca_afloja():
    # Un stop ya más ceñido que el mínimo no se aleja
    nuevo, ajustado = min_rr_stop(100, 110, 98)
    assert ajustado is False
    assert nuevo == 98


def test_datos_invalidos_no_rompen():
    assert min_rr_stop(None, 110, 95) == (95, False)
    assert min_rr_stop(100, 100, 95) == (95, False)   # reward 0
    assert min_rr_stop(100, 110, 100) == (100, False)  # risk 0
