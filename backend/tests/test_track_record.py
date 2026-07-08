"""Tests de la lógica de evaluación del Track record (track_record.evaluate_signal).

Fija el "contrato": una señal cuenta como acierto si toca TP1 antes que el stop,
fallo si toca el stop antes, y abierta si no toca ninguno. El stop se comprueba
primero (criterio conservador).

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from track_record import evaluate_signal, evaluate_signal_tp2  # noqa: E402


def test_acierto_toca_tp1():
    # entrada 100, tp 110, stop 90; sube y toca 110 → acierto +10%
    fut = [(105, 98, 104), (111, 106, 110)]
    assert evaluate_signal(100, 110, 90, fut) == ("tp1", 10.0)


def test_fallo_toca_stop():
    # entrada 100, tp 110, stop 90; cae y toca 90 → fallo -10%
    fut = [(103, 95, 100), (98, 89, 91)]
    assert evaluate_signal(100, 110, 90, fut) == ("stop", -10.0)


def test_stop_tiene_prioridad_si_ambos_en_misma_vela():
    # Vela que toca tanto stop como tp: cuenta el stop (conservador).
    fut = [(112, 88, 100)]
    assert evaluate_signal(100, 110, 90, fut) == ("stop", -10.0)


def test_abierta_no_toca_ninguno():
    fut = [(105, 96, 103), (107, 98, 105)]
    res, ret = evaluate_signal(100, 110, 90, fut)
    assert res == "abierta"
    assert ret == 5.0  # retorno actual sobre el último cierre (105)


def test_sin_entrada_devuelve_none():
    assert evaluate_signal(None, 110, 90, [(1, 1, 1)]) is None


def test_sin_futuro_devuelve_none():
    assert evaluate_signal(100, 110, 90, []) is None


def test_tp2_acierto_da_mayor_retorno():
    # Contra TP2 (120) el mismo movimiento da +20% en vez del +10% de TP1.
    fut = [(105, 98, 104), (121, 112, 120)]
    assert evaluate_signal_tp2(100, 120, 90, fut) == ("tp2", 20.0)


def test_tp2_stop_prioritario():
    fut = [(112, 88, 100)]
    assert evaluate_signal_tp2(100, 120, 90, fut) == ("stop", -10.0)


def test_ignora_nan_en_niveles():
    # tp NaN → nunca acierto; solo puede fallar o quedar abierta.
    fut = [(105, 96, 103)]
    res, _ = evaluate_signal(100, float("nan"), 90, fut)
    assert res == "abierta"
