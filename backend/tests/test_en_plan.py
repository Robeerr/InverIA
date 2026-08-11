"""`en_plan`: qué zonas de confluencia entran en el plan escalonado.

POR QUE EXISTE ESTE CAMPO

La pantalla mostraba seis niveles y el plan usaba tres, sin nada que dijera cuales. Con
FORM a $112.47 eso hizo que la tesis («la zona mas solida esta en $95.55») y el plan de la
IA («entrada $109.36») parecieran dos recomendaciones en conflicto cuando son el peldano 3
y el borde inferior del peldano 1 del MISMO plan.

La alternativa barata era replicar el umbral del 30% en React. Se descarto: MAX_PLAN_DEPTH
es configurable por entorno, asi que el dia que cambiara en Render la pantalla mentiria en
silencio. El corte lo calcula quien ya lo calculaba.

QUE PROTEGE ESTE FICHERO

  1. Que `en_plan` coincide EXACTAMENTE con la seleccion real del plan, no con una regla
     parecida escrita en otro sitio.
  2. Que es puramente ADITIVO: ni un precio, ni una fuerza, ni una razon, ni el orden
     cambian por haberlo anadido.
  3. El caso limite del 30%, que es donde una desigualdad mal puesta no se nota nunca
     hasta que se nota.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import levels_engine  # noqa: E402


# ── Fixture determinista, el mismo generador que usa test_levels_engine ──────
def _df(n=300, base=100.0, seed=7):
    rng = np.random.default_rng(seed)
    trend = np.linspace(base * 0.8, base, n)
    noise = np.cumsum(rng.normal(0, base * 0.01, n))
    close = np.clip(trend + noise, base * 0.4, base * 1.6)
    high = close * (1 + rng.uniform(0.001, 0.02, n))
    low = close * (1 - rng.uniform(0.001, 0.02, n))
    open_ = close * (1 + rng.uniform(-0.01, 0.01, n))
    vol = rng.integers(1_000_000, 5_000_000, n)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({"Date": dates, "Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": vol})


CURRENT = 130.0


def _crudos():
    """Lo que devuelve el motor. NO lleva `en_plan`: el motor calcula zonas, y quien marca
    el plan es el servidor, que es el que tiene `MAX_PLAN_DEPTH`. Esa separacion es lo que
    hace que el campo sea aditivo de verdad."""
    return levels_engine.compute_buy_levels(_df(), None, CURRENT, sma=None, atr_val=2.0)


def _niveles_reales():
    """Los mismos, marcados como los marca `_construir_dashboard`."""
    return levels_engine.marcar_en_plan(_crudos(), CURRENT, 0.30)


# Zonas de la captura real de FORM (11/08/2026), precio $112.47.
FORM_PRECIO = 112.47
FORM = [
    {"price": 110.84, "strength": 83,  "label": "NIVEL 1"},
    {"price": 102.74, "strength": 78,  "label": "NIVEL 2", "tactical": True},
    {"price": 95.55,  "strength": 100, "label": "NIVEL 3"},
    {"price": 90.55,  "strength": 100, "label": "NIVEL 4"},
    {"price": 70.24,  "strength": 75,  "label": "NIVEL 5", "tactical": True},
    {"price": 55.40,  "strength": 100, "label": "NIVEL 6"},
]


# ── 1 · El contrato de buy_levels queda congelado ────────────────────────────
CLAVES_CONTRATO = {"price", "zone_low", "zone_high", "strength", "distance_pct",
                   "reasons", "sources", "label", "tactical"}


def test_el_motor_no_devuelve_en_plan_por_su_cuenta():
    """La prueba de la separacion: el motor calcula zonas y no sabe nada del plan. Si
    algun dia lo marcara el, `MAX_PLAN_DEPTH` habria bajado al motor sin decirlo."""
    for z in _crudos():
        assert "en_plan" not in z


def test_el_contrato_de_buy_levels_no_pierde_ninguna_clave():
    """Congela lo que el motor devuelve. Si una desaparece, este test lo dice antes de
    que una pantalla se quede sin dato."""
    niveles = _crudos()
    assert niveles, "el motor no ha devuelto zonas con la fixture determinista"
    for z in niveles:
        faltan = CLAVES_CONTRATO - set(z)
        assert not faltan, f"el contrato ha perdido {sorted(faltan)}"


def test_en_plan_es_la_unica_clave_nueva():
    """La prueba de que es ADITIVO: nada mas ha entrado por el camino."""
    niveles = _niveles_reales()
    for z in niveles:
        sobran = set(z) - CLAVES_CONTRATO - {"en_plan"}
        assert not sobran, f"claves inesperadas en buy_levels: {sorted(sobran)}"
        assert "en_plan" in z, "en_plan deberia venir marcado en todas las zonas"
        assert isinstance(z["en_plan"], bool)


def test_marcar_en_plan_no_toca_ningun_otro_campo():
    """El nucleo de 'aditivo': se compara zona a zona antes y despues de marcar."""
    copia = [dict(z) for z in _crudos()]

    despues = levels_engine.marcar_en_plan([dict(z) for z in copia], CURRENT, 0.30)

    assert len(despues) == len(copia), "el numero de zonas ha cambiado"
    for original, marcado in zip(copia, despues):
        sin_marca = {k: v for k, v in marcado.items() if k != "en_plan"}
        assert sin_marca == original, (
            f"marcar en_plan ha modificado la zona: {original} -> {sin_marca}")


def test_el_orden_no_cambia():
    """El orden (precio descendente) es lo que hace que NIVEL 1 sea el mas cercano."""
    antes = [z["price"] for z in _crudos()]
    despues = [z["price"] for z in _niveles_reales()]
    assert antes == despues == sorted(antes, reverse=True)


# ── 2 · en_plan coincide con la seleccion real del plan ──────────────────────
def test_en_plan_coincide_con_los_indices_del_plan():
    niveles = _niveles_reales()
    esperados = set(levels_engine.indices_del_plan(CURRENT, niveles, 0.30))
    for i, z in enumerate(niveles):
        assert z["en_plan"] is (i in esperados), (
            f"zona {i} ({z['price']}): en_plan={z['en_plan']} pero el plan usa {sorted(esperados)}")


def test_el_plan_nunca_pasa_de_tres_escalones():
    for precio in (80.0, 130.0, 400.0):
        niveles = levels_engine.compute_buy_levels(_df(), None, precio, sma=None, atr_val=2.0)
        assert len(levels_engine.indices_del_plan(precio, niveles, 0.30)) <= 3


def test_el_plan_respeta_el_orden_de_la_lista():
    """Los indices salen crecientes: el plan es un escalonado de cerca a lejos."""
    niveles = _niveles_reales()
    idx = levels_engine.indices_del_plan(CURRENT, niveles, 0.30)
    assert idx == sorted(idx)


# ── 3 · El caso de FORM, que es el que motivo todo esto ──────────────────────
def test_form_el_plan_son_los_tres_primeros():
    idx = levels_engine.indices_del_plan(FORM_PRECIO, FORM, 0.30)
    assert idx == [0, 1, 2]


def test_form_el_nivel_mas_solido_esta_dentro_del_plan():
    """$95.55 tiene fuerza 100 y esta a -15%: es el NIVEL 3 del plan, no una idea rival."""
    marcados = levels_engine.marcar_en_plan([dict(z) for z in FORM], FORM_PRECIO, 0.30)
    n3 = next(z for z in marcados if z["price"] == 95.55)
    assert n3["en_plan"] is True


def test_form_los_estructurales_quedan_fuera():
    marcados = levels_engine.marcar_en_plan([dict(z) for z in FORM], FORM_PRECIO, 0.30)
    fuera = {z["price"]: z["en_plan"] for z in marcados if not z["en_plan"]}
    # 90.55 cae fuera por el tope de 3 escalones; 70.24 y 55.40 por profundidad.
    assert set(fuera) == {90.55, 70.24, 55.40}


# ── 4 · El limite del 30%, donde una desigualdad mal puesta no se ve ─────────
def test_el_limite_del_30_por_ciento_es_inclusivo():
    """A exactamente -30% la zona SI entra. Es la frontera que el codigo ya usaba
    (`p < suelo` descarta), y se fija para que un refactor no la vuelva del reves."""
    precio = 100.0
    zonas = [{"price": 70.0, "strength": 90}]     # exactamente el suelo
    assert levels_engine.indices_del_plan(precio, zonas, 0.30) == [0]


def test_un_centimo_por_debajo_del_limite_queda_fuera():
    precio = 100.0
    zonas = [{"price": 69.99, "strength": 90}]
    # Sin ninguna zona valida se activa el respaldo, que coge la menos profunda.
    # Lo que importa es que NO paso el filtro por si misma: se comprueba con una
    # segunda zona que si lo pasa.
    zonas2 = [{"price": 85.0, "strength": 90}, {"price": 69.99, "strength": 99}]
    assert levels_engine.indices_del_plan(precio, zonas2, 0.30) == [0]


@pytest.mark.parametrize("max_depth,esperado", [
    (0.30, [0]),      # suelo 70.0 → solo la de 85
    (0.50, [0, 1]),   # suelo 50.0 → entran las dos
    (0.10, [0]),      # suelo 90.0 → ninguna pasa → respaldo: la menos profunda
])
def test_el_umbral_es_un_parametro_no_una_constante_replicada(max_depth, esperado):
    """La regla vive en un sitio y se le pasa el umbral. Si alguien la duplicara con el
    0.30 escrito a mano, este test seguiria pasando pero el de server.py no."""
    zonas = [{"price": 85.0, "strength": 90}, {"price": 60.0, "strength": 99}]
    assert levels_engine.indices_del_plan(100.0, zonas, max_depth) == esperado


# ── 5 · Respaldo: la accion ha subido tanto que no hay soporte cercano ───────
def test_sin_zonas_dentro_del_suelo_se_coge_la_menos_profunda():
    """Preferible a quedarse sin plan: sin el, los numeros los inventaria la IA."""
    zonas = [{"price": 40.0, "strength": 100}, {"price": 20.0, "strength": 100}]
    assert levels_engine.indices_del_plan(100.0, zonas, 0.30) == [0]


def test_sin_zonas_con_precio_no_hay_plan():
    assert levels_engine.indices_del_plan(100.0, [{"strength": 50}], 0.30) == []
    assert levels_engine.indices_del_plan(100.0, [], 0.30) == []


@pytest.mark.parametrize("precio", [None, 0, -5])
def test_sin_precio_utilizable_no_se_marca_nada(precio):
    """Sin precio no hay distancia, y sin distancia no hay plan. No se inventa uno."""
    marcados = levels_engine.marcar_en_plan([dict(z) for z in FORM], precio, 0.30)
    assert all(z["en_plan"] is False for z in marcados)


def test_las_zonas_sin_precio_se_saltan_sin_reventar():
    zonas = [{"strength": 10}, {"price": 90.0, "strength": 90}]
    assert levels_engine.indices_del_plan(100.0, zonas, 0.30) == [1]
