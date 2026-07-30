"""Tests de la Fuerza Relativa (indicators.relative_strength).

Compara la rentabilidad de la acción con la de su índice a 1, 3 y 6 meses. Era el único
indicador de peso que faltaba, y sale de datos ya descargados (el histórico de SPY que ya
cachea el semáforo de mercado), así que no cuesta ni una llamada de red extra.

Ejecutar:  cd backend && pytest tests/ -v
"""
import pytest

pytest.importorskip("pandas")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import indicators as ind  # noqa: E402


def _serie(n, ret_total, inicio="2025-01-01"):
    """Serie que sube (o baja) de forma suave hasta ret_total en n sesiones."""
    fechas = pd.bdate_range(inicio, periods=n)
    precios = 100 * (1 + ret_total) ** (np.arange(n) / (n - 1))
    return pd.DataFrame({"Date": fechas, "Close": precios})


def test_detecta_una_lider():
    r = ind.relative_strength(_serie(200, 0.40), _serie(200, 0.10))
    assert r["veredicto"] == "LÍDER"
    assert r["ventanas"]["6m"]["diferencia_pp"] > 10
    assert r["ventanas"]["6m"]["supera"] is True


def test_detecta_una_rezagada():
    r = ind.relative_strength(_serie(200, -0.20), _serie(200, 0.15))
    assert r["veredicto"] == "REZAGADA"
    assert r["referencia_pp"] < -10
    assert r["ventanas"]["6m"]["supera"] is False


def test_la_diferencia_es_accion_menos_indice():
    r = ind.relative_strength(_serie(200, 0.30), _serie(200, 0.10))
    v = r["ventanas"]["6m"]
    assert v["diferencia_pp"] == pytest.approx(v["accion_pct"] - v["indice_pct"], abs=0.02)


def test_alinea_por_FECHA_y_no_por_posicion():
    """El detalle que hace que el número signifique algo. Si a la acción le faltan sesiones
    (IPO, suspensión, festivos distintos), tomar iloc[-126] en cada serie por separado
    compararía ventanas de tiempo DISTINTAS."""
    n = 200
    fechas = pd.bdate_range("2025-01-01", periods=n)
    indice = pd.DataFrame({"Date": fechas, "Close": 100 * 1.10 ** (np.arange(n) / (n - 1))})
    accion_full = pd.DataFrame({"Date": fechas, "Close": 100 * 1.40 ** (np.arange(n) / (n - 1))})
    # Quitamos 30 sesiones sueltas a la acción.
    rng = np.random.default_rng(3)
    accion = accion_full.drop(index=rng.choice(n - 1, size=30, replace=False)).reset_index(drop=True)

    r = ind.relative_strength(accion, indice)
    correcto = r["ventanas"]["6m"]["diferencia_pp"]

    # Lo que habría dado indexando por posición en cada serie por separado.
    ia, fa = float(accion["Close"].iloc[-127]), float(accion["Close"].iloc[-1])
    ib, fb = float(indice["Close"].iloc[-127]), float(indice["Close"].iloc[-1])
    por_posicion = (fa / ia - 1) * 100 - (fb / ib - 1) * 100

    assert r["sesiones_comunes"] == len(accion)
    assert abs(correcto - por_posicion) > 0.5, (
        "si ambos métodos coinciden, este test no está probando nada: "
        "asegúrate de que las series están realmente desalineadas"
    )


def test_omite_las_ventanas_sin_historico():
    """Una acción recién salida a bolsa no tiene 6 meses. Se devuelve solo lo que hay, en
    vez de rellenar con un número inventado."""
    r = ind.relative_strength(_serie(40, 0.10), _serie(200, 0.05))
    assert list(r["ventanas"].keys()) == ["1m"]


def test_sin_historico_comun_devuelve_None():
    assert ind.relative_strength(_serie(10, 0.1), _serie(200, 0.05)) is None


@pytest.mark.parametrize("a,b", [
    (None, None),
    (None, "serie"),
    ("serie", None),
])
def test_entradas_ausentes_no_rompen(a, b):
    s = _serie(200, 0.1)
    assert ind.relative_strength(s if a else None, s if b else None) is None


def test_dataframe_vacio_no_rompe():
    vacio = pd.DataFrame(columns=["Date", "Close"])
    assert ind.relative_strength(vacio, _serie(200, 0.05)) is None
    assert ind.relative_strength(_serie(200, 0.05), vacio) is None


def test_precios_a_cero_no_dividen_por_cero():
    s = _serie(200, 0.10)
    roto = s.copy()
    roto.loc[:, "Close"] = 0.0
    # No debe lanzar; devuelve None porque ninguna ventana es calculable.
    assert ind.relative_strength(roto, s) is None
