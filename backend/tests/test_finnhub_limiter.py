"""Tests del limitador de Finnhub, en concreto de la espera acotada.

Síntoma que lo motivó: abrir AAPL mostraba "No se encontró el símbolo AAPL". El símbolo
existe; lo que pasaba es que el vigilante de la Cartera saturaba el cupo, acquire() bloqueaba
hasta 60s, el endpoint /dashboard corta cada fuente a los 8s y la cotización llegaba vacía.
El frontend interpretaba "sin cotización" como "el ticker no existe".

Ejecutar:  cd backend && pytest tests/ -v
"""
import time

import pytest

pytest.importorskip("pandas", reason="market_data importa pandas/yfinance")
import market_data  # noqa: E402


@pytest.fixture
def limitador():
    return market_data._FinnhubLimiter(max_per_min=3, bg_reserve=1)


def test_concede_hueco_mientras_haya_cupo(limitador):
    for _ in range(3):
        assert limitador.acquire(max_wait=1) is True


def test_devuelve_False_en_vez_de_bloquear_cuando_no_hay_cupo(limitador):
    for _ in range(3):
        limitador.acquire()
    t0 = time.time()
    concedido = limitador.acquire(max_wait=0.5)
    esperado = time.time() - t0
    assert concedido is False, "debería rendirse, no conceder"
    assert esperado < 1.5, f"tardó {esperado:.1f}s: la espera no está acotada"


def test_sin_max_wait_mantiene_el_comportamiento_de_siempre(limitador):
    """Las llamadas de fondo siguen esperando su turno: no queremos que se rindan y
    pierdan la comprobación de niveles."""
    assert limitador.acquire() is True


def test_la_espera_del_usuario_es_mas_corta_que_el_corte_del_dashboard():
    """El margen del usuario (2,5s) debe caber holgado en los 8s que espera /dashboard,
    para que quede tiempo de consultar el proveedor alternativo."""
    import re
    with open(market_data.__file__, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"_espera = ([\d.]+) if _finnhub_bg_ctx\.get\(\) else ([\d.]+)", src)
    assert m, "ya no se distingue la espera de fondo de la del usuario"
    fondo, usuario = float(m.group(1)), float(m.group(2))
    assert usuario < 3.0, "la espera del usuario debe ser corta"
    assert usuario < fondo, "el fondo puede esperar más que el usuario, no al revés"
    assert usuario * 2 < 8.0, "debe quedar margen dentro del corte de 8s del dashboard"
