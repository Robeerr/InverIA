"""Tests de la estimacion de comisiones.

Contexto: las comisiones suman al coste al comprar y restan al ingreso al vender. Si el
campo se deja vacio y se toma como cero, la ganancia sale inflada SIN avisar — que es peor
que una estimacion, porque un cero parece un dato.

Tarifa de DEGIRO consultada 08/2026: 1 EUR de comision + 1 EUR de tramitacion por operacion
(EE.UU. y Espana), mas 0,25% de conversion automatica de divisa.

Ejecutar:  cd backend && pytest tests/test_comisiones.py -v
"""
import pytest

import comisiones


def test_una_operacion_en_euros_solo_paga_la_fija():
    r = comisiones.estimar(1000.0, "EUR")
    assert r["total"] == 2.0
    assert r["conversion_divisa"] == 0.0


def test_en_dolares_los_dos_euros_se_pasan_a_dolares():
    """Los 2 EUR son EUROS. Sumarlos tal cual a una operacion en dolares seria cobrar de
    menos: a 1,10, dos euros son 2,20 $."""
    r = comisiones.estimar(0.0, "USD", tasa=1.10)
    assert r["fija"] == pytest.approx(2.20)


def test_se_incluye_el_025_de_conversion_de_divisa():
    """Es el coste que mas pasa desapercibido: no aparece como "comision" en ningun sitio,
    va incorporado al tipo de cambio que te aplican."""
    r = comisiones.estimar(1000.0, "USD", tasa=1.10)
    assert r["conversion_divisa"] == pytest.approx(2.50)      # 0,25% de 1000
    assert r["total"] == pytest.approx(4.70)                  # 2,20 + 2,50


def test_la_conversion_pesa_mas_que_la_fija_en_operaciones_grandes():
    """Justifica incluirla: en una venta de 5.000 $ son 12,50 $, seis veces la fija."""
    r = comisiones.estimar(5000.0, "USD", tasa=1.10)
    assert r["conversion_divisa"] > r["fija"] * 5


def test_con_cambio_manual_no_hay_conversion():
    r = comisiones.estimar(1000.0, "USD", tasa=1.10, fx_manual=True)
    assert r["conversion_divisa"] == 0.0
    assert r["total"] == pytest.approx(2.20)


def test_sin_tipo_de_cambio_no_se_inventa_una_paridad():
    """Suponer 1:1 daria una comision fija equivocada y silenciosa."""
    r = comisiones.estimar(1000.0, "USD", tasa=None)
    assert r["total"] is None
    assert r["fija"] is None


def test_siempre_queda_marcada_como_estimacion():
    assert comisiones.estimar(100.0, "USD", tasa=1.1)["estimada"] is True


def test_el_desglose_permite_cuadrarlo_con_el_extracto():
    """Un total suelto no se puede comprobar y acabaria aceptandose sin mirar."""
    d = comisiones.estimar(1000.0, "USD", tasa=1.10)["detalle"]
    assert "DEGIRO" in d and "0.25%" in d.replace(",", ".")


def test_un_importe_raro_no_rompe_nada():
    for malo in (None, "", "n/d", -100):
        r = comisiones.estimar(malo, "USD", tasa=1.10)
        assert r["total"] is not None and r["total"] >= 0
