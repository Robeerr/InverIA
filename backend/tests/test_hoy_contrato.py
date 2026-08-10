"""La portada lee del dashboard cacheado: aquí se fija de qué campos depende.

Estos tres bugs aparecieron juntos y ninguno daba error:

  · `buy_levels` se leía como `dash["analysis"]["buy_levels"]`. Ese `analysis` solo
    existe en la respuesta de /analyze; en el dashboard los niveles cuelgan de la
    raíz. Resultado: lista vacía, y una lista vacía se pinta como "el motor no tiene
    todavía una zona calculada para este precio" — una afirmación falsa y además
    tranquilizadora, que es la peor combinación.
  · `data_warning` tampoco existe en el dashboard; el equivalente es `data_health`.
    El aviso de calidad de dato no habría salido nunca.
  · La posición no tiene `pnl_pct`, tiene `pct` y `pct_eur`.

Ninguno rompía nada: simplemente la pantalla enseñaba menos de lo que sabía. Por eso
hace falta un test de CONTRATO — que la forma del dato sea la que se cree — y no solo
tests de la lógica, que ya pasaban perfectamente con datos inventados.
"""
import os

import pytest

pytest.importorskip("fastapi", reason="requiere fastapi")
import server  # noqa: E402


# Un dashboard con la forma REAL que construye _construir_dashboard.
DASHBOARD = {
    "symbol": "MRVL",
    "timeframe": "1D",
    "quote": {"price": 181.6},
    "indicators": {
        "salida_10w": {"sma": 176.2, "por_encima": False, "distancia_pct": -3.1,
                       "senal": "salida", "recien_perdida": True},
        "regime": "alcista", "adx": 31, "atr_pct": 2.4, "obv_trend": "subiendo",
    },
    "buy_levels": [
        {"price": 178.4, "zone_low": 177.0, "zone_high": 179.5, "strength": 78,
         "distance_pct": -1.8, "reasons": ["SMA200", "Fibonacci 38,2%", "VWAP anclado"]},
        {"price": 165.0, "strength": 45, "distance_pct": -9.1, "reasons": ["Mínimo previo"]},
    ],
    "data_health": {"source": "stooq", "as_of": "2026-08-08", "degraded": True,
                    "note": "fuente de respaldo"},
    "generado_en": "2026-08-10T12:00:00+00:00",
}


def test_los_niveles_del_motor_se_leen_de_la_raiz():
    niveles = server._niveles_del_motor(DASHBOARD)
    assert len(niveles) == 2
    assert niveles[0]["strength"] == 78
    assert "SMA200" in niveles[0]["reasons"]


def test_leerlos_del_sitio_equivocado_daria_vacio_sin_avisar():
    """El fallo original, escrito como test para que se vea por qué era peligroso."""
    assert (DASHBOARD.get("analysis") or {}).get("buy_levels") is None
    assert server._niveles_del_motor(DASHBOARD), "la ruta correcta sí devuelve niveles"


def test_un_dashboard_sin_calentar_no_inventa_niveles():
    assert server._niveles_del_motor({}) == []


def test_el_aviso_de_calidad_sale_de_data_health():
    aviso = server._aviso_de_datos(DASHBOARD)
    assert aviso and "respaldo" in aviso
    assert "fuente de respaldo" in aviso


def test_sin_degradacion_no_hay_aviso():
    """Si saliera siempre, dejaría de leerse: un aviso permanente es decoración."""
    assert server._aviso_de_datos({"data_health": {"degraded": False}}) is None
    assert server._aviso_de_datos({}) is None


def test_la_zona_elegida_es_la_del_nivel_que_dispara_no_la_mas_fuerte():
    """Lo que interesa es si el precio al que va a llegar el mercado tiene respaldo."""
    zona = server._mejor_zona(DASHBOARD, 178.4)
    assert zona["strength"] == 78
    # Un objetivo lejos de toda zona no se empareja con la mejor que haya por ahí.
    assert server._mejor_zona(DASHBOARD, 120.0) is None


def test_el_dashboard_real_sigue_teniendo_los_campos_que_la_portada_usa():
    """Centinela contra el renombrado silencioso.

    Si alguien mueve `buy_levels` dentro de otro objeto, o cambia `data_health` de
    nombre, la portada se quedaría muda sin que fallara nada. Se comprueba sobre el
    código que ENSAMBLA el dashboard, que es donde viviría el cambio.
    """
    with open(server.__file__, encoding="utf-8") as fh:
        src = fh.read()
    cuerpo = src.split("async def _construir_dashboard", 1)[1].split("\n@api_router", 1)[0]
    for campo in ('"buy_levels":', '"indicators":', '"data_health":'):
        assert campo in cuerpo, f"el dashboard ya no ensambla {campo}; la portada depende de él"


def test_la_posicion_usa_pct_y_no_pnl_pct():
    """El campo del porcentaje se llama `pct` (divisa de la acción) y `pct_eur`.
    `pnl_pct` no existe, y filtrar por él dejaba el bloque de atención siempre vacío."""
    with open(os.path.join(os.path.dirname(server.__file__), "lotes.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert '"pct":' in src and '"pct_eur":' in src
    assert '"pnl_pct"' not in src
