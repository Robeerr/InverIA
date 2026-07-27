"""Tests del guardián de riesgo/recompensa (risk_rules.min_rr_stop).

Fija el contrato: si el stop deja un R/R en TP1 por debajo del mínimo (RR_MIN), se ciñe
hacia la entrada hasta cumplirlo; si ya es sano, no se toca; nunca se afloja.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from risk_rules import RR_MIN, min_rr_stop  # noqa: E402


def test_minimo_es_2_y_coincide_con_el_motor():
    """RR_MIN debe ser 2.0 y no divergir de server.MIN_RR: si el motor exige un ratio y el
    guardián otro, la IA narra un R/R que los números no cumplen.

    Se lee del fuente en vez de importar server: importarlo arrastra fastapi y todo el stack,
    y esto es una comprobación de acoplamiento entre dos constantes, no un test de integración.
    """
    import re

    assert RR_MIN == 2.0
    ruta = os.path.join(os.path.dirname(__file__), "..", "server.py")
    with open(ruta, encoding="utf-8") as fh:
        m = re.search(r"^MIN_RR\s*=\s*([0-9.]+)", fh.read(), re.MULTILINE)
    assert m, "server.py ya no define MIN_RR a nivel de módulo"
    assert float(m.group(1)) == RR_MIN


def test_ciñe_stop_ancho_hasta_rr_minimo():
    # entrada 100, tp1 104.6 (+4.6%), stop 92.4 (-7.6%) → R/R 0.61 → ceñir a RR_MIN
    nuevo, ajustado = min_rr_stop(100, 104.6, 92.4)
    assert ajustado is True
    assert round((104.6 - 100) / (100 - nuevo), 2) == RR_MIN


def test_stop_que_daba_1_5_ahora_se_ciñe():
    """Regresión del cambio de 1.5 → 2.0: un R/R de exactamente 1.5 pasaba antes y ahora no."""
    # entrada 100, tp1 115, stop 90 → R/R = 15/10 = 1.5 → ya no cumple
    nuevo, ajustado = min_rr_stop(100, 115, 90)
    assert ajustado is True
    assert round((115 - 100) / (100 - nuevo), 2) == 2.0


def test_no_toca_stop_ya_sano():
    # R/R = 10/5 = 2 → justo en el mínimo, no se toca
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
