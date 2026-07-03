"""Tests del MOTOR DE NIVELES (levels_engine.compute_buy_levels).

El motor calcula de forma determinista las zonas de compra por confluencia.
Estos tests fijan sus INVARIANTES — las reglas que SIEMPRE deben cumplirse
sin importar los datos de entrada. Si un cambio en el código rompe alguna
(p. ej. un nivel de compra por ENCIMA del precio, como el bug del gráfico que
mostraba $475 en vez de $375.98), `pytest` lo caza antes de desplegar.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import levels_engine  # noqa: E402


def _synthetic_df(n=300, base=100.0, seed=7):
    """Genera un histórico OHLC realista y determinista (sin aleatoriedad libre:
    seed fijo) alrededor de `base`, con oscilación suave para que aparezcan
    pivotes, medias y zonas de volumen."""
    rng = np.random.default_rng(seed)
    # Tendencia suave + ruido acotado → precios plausibles y con estructura.
    trend = np.linspace(base * 0.8, base, n)
    noise = np.cumsum(rng.normal(0, base * 0.01, n))
    close = np.clip(trend + noise, base * 0.4, base * 1.6)
    high = close * (1 + rng.uniform(0.001, 0.02, n))
    low = close * (1 - rng.uniform(0.001, 0.02, n))
    open_ = close * (1 + rng.uniform(-0.01, 0.01, n))
    vol = rng.integers(1_000_000, 5_000_000, n)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "Date": dates, "Open": open_, "High": high, "Low": low,
        "Close": close, "Volume": vol,
    })


CURRENT = 130.0  # precio actual por encima del rango → habrá soportes debajo


def _levels(**over):
    df = over.pop("df", None)
    if df is None:
        df = _synthetic_df()
    kw = dict(
        volume_profile={"poc": 110.0, "val": 95.0, "hvn": [105.0, 90.0]},
        current_price=CURRENT,
        sma={"50": 118.0, "200": 100.0},
        atr_val=3.5,
        vwap_anchored=112.0,
    )
    kw.update(over)
    return levels_engine.compute_buy_levels(df, **kw)


# ── Casos degenerados ───────────────────────────────────────────────────────

def test_df_vacio_devuelve_lista_vacia():
    assert levels_engine.compute_buy_levels(pd.DataFrame(), {}, 130.0) == []


def test_precio_invalido_devuelve_lista_vacia():
    df = _synthetic_df()
    assert levels_engine.compute_buy_levels(df, {}, 0) == []
    assert levels_engine.compute_buy_levels(df, {}, -5) == []


# ── INVARIANTES del ladder (las reglas de oro) ──────────────────────────────

def test_todos_los_niveles_por_debajo_del_precio():
    """REGLA DE ORO: una zona de COMPRA nunca puede estar por encima del precio
    actual. Este es exactamente el bug que dio $475 con precio $375."""
    for z in _levels():
        assert z["price"] < CURRENT, f"nivel {z['price']} por ENCIMA del precio {CURRENT}"


def test_niveles_ordenados_de_cercano_a_profundo():
    """El ladder se entrega del más cercano al precio al más profundo (desc)."""
    precios = [z["price"] for z in _levels()]
    assert precios == sorted(precios, reverse=True), f"no ordenado: {precios}"


def test_fuerza_en_rango_0_100():
    for z in _levels():
        assert 0 <= z["strength"] <= 100, f"fuerza fuera de rango: {z['strength']}"


def test_distancia_pct_es_negativa():
    """Como todos los niveles están por debajo, la distancia % debe ser <= 0."""
    for z in _levels():
        assert z["distance_pct"] <= 0, f"distancia positiva: {z['distance_pct']}"


def test_zona_low_menor_o_igual_que_zona_high():
    for z in _levels():
        assert z["zone_low"] <= z["zone_high"]
        assert z["zone_low"] <= z["price"] <= z["zone_high"] + 1e-6


def test_respeta_max_levels():
    """El nº de niveles estructurales no excede max_levels (+ rellenos tácticos)."""
    niveles = _levels(max_levels=4)
    estructurales = [z for z in niveles if not z.get("tactical")]
    assert len(estructurales) <= 4, f"{len(estructurales)} estructurales > 4"


def test_cada_nivel_tiene_campos_esperados():
    for z in _levels():
        for campo in ("price", "zone_low", "zone_high", "strength", "distance_pct", "reasons", "sources"):
            assert campo in z, f"falta el campo '{campo}' en {z}"


# ── Determinismo (mismos datos → mismo resultado) ───────────────────────────

def test_determinista():
    """El motor NO debe depender del azar: dos llamadas con el mismo df dan lo mismo."""
    df = _synthetic_df()
    a = levels_engine.compute_buy_levels(df, {"poc": 110.0}, CURRENT, sma={"200": 100.0})
    b = levels_engine.compute_buy_levels(df, {"poc": 110.0}, CURRENT, sma={"200": 100.0})
    assert [z["price"] for z in a] == [z["price"] for z in b]


# ── Confluencia: más fuentes coincidentes → más fuerza ──────────────────────

def test_confluencia_sube_la_fuerza():
    """Una zona con MÚLTIPLES metodologías coincidentes debe puntuar más fuerte
    que una con una sola. Metemos POC+VAL+HVN+SMA200+VWAP cerca de 100-112."""
    df = _synthetic_df()
    con_confluencia = levels_engine.compute_buy_levels(
        df, {"poc": 100.5, "val": 100.0, "hvn": [99.5]}, CURRENT,
        sma={"200": 100.2}, vwap_anchored=100.3,
    )
    sin_confluencia = levels_engine.compute_buy_levels(
        df, {"poc": 100.5}, CURRENT, sma=None,
    )
    # La mejor zona con confluencia debe ser al menos tan fuerte como la mejor sin ella.
    if con_confluencia and sin_confluencia:
        assert max(z["strength"] for z in con_confluencia) >= max(z["strength"] for z in sin_confluencia)
