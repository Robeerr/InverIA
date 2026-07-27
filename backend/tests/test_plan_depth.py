"""Tests de la profundidad máxima del plan de compra.

Caso real que lo motivó (MRVL, 27/07/2026, precio $186.38): el motor cogía los 3 primeros
niveles de confluencia sin mirar la profundidad, y salían a -3,8%, -13,1% y -46,5%. Como el
stop va por debajo de TODAS las entradas del plan, acababa en $78.95: un -57,7%. Eso no es un
stop, es perder media posición antes de reaccionar.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import re

import pytest

_RUTA = os.path.join(os.path.dirname(__file__), "..", "server.py")

# Niveles reales que devolvió el motor para MRVL, con el precio de aquella sesión.
MRVL_PRECIO = 186.38
MRVL_NIVELES = [178.95, 161.80, 99.64, 85.85, 79.48, 69.56]


def _fuente():
    with open(_RUTA, encoding="utf-8") as fh:
        return fh.read()


def _filtrar(precio, niveles, max_depth):
    """Réplica del filtro de _deterministic_levels. Se replica en vez de importar server
    porque importarlo arrastra FastAPI, Mongo y todo el stack."""
    suelo = precio * (1 - max_depth)
    return [p for p in niveles if p >= suelo][:3]


def test_max_plan_depth_declarado_y_es_30_por_ciento():
    m = re.search(r'MAX_PLAN_DEPTH = float\(os\.environ\.get\("MAX_PLAN_DEPTH", "([\d.]+)"\)\)',
                  _fuente())
    assert m, "server.py ya no define MAX_PLAN_DEPTH"
    assert float(m.group(1)) == 0.30


def test_mrvl_excluye_el_nivel_de_menos_46_por_ciento():
    """El caso que destapó el fallo: el tercer nivel estaba a -46,5% y arrastraba el stop."""
    plan = _filtrar(MRVL_PRECIO, MRVL_NIVELES, 0.30)
    assert plan == [178.95, 161.80], f"el plan debería quedarse en 2 zonas, quedó {plan}"
    assert 99.64 not in plan


def test_el_stop_resultante_es_operativo():
    """Con el filtro, el stop cae en un rango usable en vez del -57,7% de antes."""
    plan = _filtrar(MRVL_PRECIO, MRVL_NIVELES, 0.30)
    deepest = min(plan)
    for atr in (6, 9, 12):
        stop = deepest - max(1.0 * atr, deepest * 0.015)
        caida = (stop / MRVL_PRECIO - 1) * 100
        assert -25 < caida < -15, f"con ATR={atr} el stop queda a {caida:.1f}%, fuera de rango"


def test_sin_filtro_el_stop_era_absurdo():
    """Documenta el comportamiento viejo, para que se vea por qué existe el filtro."""
    plan_viejo = MRVL_NIVELES[:3]          # lo que se hacía antes: los 3 primeros a pelo
    deepest = min(plan_viejo)              # 99.64
    stop = deepest - max(9.0, deepest * 0.015)
    assert (stop / MRVL_PRECIO - 1) * 100 < -50, "el caso viejo debería dar un stop atroz"


@pytest.mark.parametrize("max_depth,esperadas", [
    (0.10, 1),   # suelo 167,74 → solo el de -4,0%
    (0.20, 2),   # suelo 149,10 → -4,0% y -13,2% (el de -13,2% SÍ entra en un umbral del 20%)
    (0.30, 2),   # suelo 130,47 → los mismos dos
    (0.50, 3),   # suelo  93,19 → entra también el de -46,5%
])
def test_el_umbral_es_configurable(max_depth, esperadas):
    assert len(_filtrar(MRVL_PRECIO, MRVL_NIVELES, max_depth)) == esperadas


def test_hay_respaldo_si_ninguna_zona_pasa_el_filtro():
    """Si la acción ha subido tanto que no hay soporte dentro del suelo, no se devuelve None:
    se conserva la zona menos profunda para seguir dando un plan coherente."""
    src = _fuente()
    assert "Nos quedamos con la MENOS profunda" in src, (
        "Se ha perdido el respaldo: sin él, una acción disparada cae al flujo clásico, "
        "donde los números los inventa la IA."
    )
