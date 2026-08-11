"""El coste de abrir una accion no puede crecer sin que nos enteremos.

La Fase 3 saca a la pantalla una docena de datos que ya viajaban en la respuesta. Todos
son CPU local sobre historico ya descargado, asi que la reestructuracion es gratis. El
riesgo no esta en lo que se ha hecho, sino en lo siguiente que se haga: la tentacion
natural al ver «faltan insider y sorpresas de resultados en frio» es subirlos al
dashboard, y eso ANADE llamadas a Finnhub en cada carga de pagina en vez de solo cuando
tu pides analisis.

Se comprueba sobre el codigo porque lo que se protege es DONDE se llama a una fuente de
pago, y eso es una propiedad de la forma del servidor, no de una respuesta concreta.
"""
import os
import re

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _fuente(nombre: str) -> str:
    with open(os.path.join(_AQUI, "..", nombre), encoding="utf-8") as f:
        return f.read()


def _cuerpo(nombre_funcion: str) -> str:
    src = _fuente("server.py")
    ini = src.index(f"async def {nombre_funcion}")
    fin = src.index("\n@api_router", ini)
    return src[ini:fin]


# ── Insider y sorpresas de resultados: solo por la via de la IA ──────────────
FUENTES_DE_PAGO_SOLO_IA = [
    "external_data.finnhub_insider_transactions",   # movimientos de directivos
    "external_data.finnhub_earnings_surprises",     # historial de sorpresas de resultados
]


def test_las_fuentes_caras_solo_se_piden_desde_analyze():
    """El requisito: /analyze es la UNICA ruta que las solicita.

    Si aparecieran en `_construir_dashboard`, pasarian de costar una llamada cuando
    pulsas el boton a costar una por cada accion que abras en el dia.

    Se cuenta: todas las apariciones en el servidor tienen que estar dentro del cuerpo
    de /analyze. Una sola fuera ya rompe la garantia.
    """
    src = _fuente("server.py")
    cuerpo_analyze = _cuerpo("analyze")
    for llamada in FUENTES_DE_PAGO_SOLO_IA:
        en_todo_el_servidor = src.count(llamada)
        en_analyze = cuerpo_analyze.count(llamada)
        assert en_todo_el_servidor > 0, f"{llamada} ha desaparecido del servidor"
        assert en_todo_el_servidor == en_analyze, (
            f"{llamada} aparece {en_todo_el_servidor} veces y solo {en_analyze} dentro de "
            f"/analyze: alguna la pide otra ruta, y eso anade coste fuera del boton de IA")


def test_el_dashboard_no_toca_insider_ni_el_historial_de_resultados():
    cuerpo = _cuerpo("_construir_dashboard")
    for prohibido in ("insider", "earnings_history", "earnings_hist", "earnings_surprises"):
        assert prohibido not in cuerpo, (
            f"'{prohibido}' ha entrado en el ensamblado del dashboard: eso es una llamada "
            f"a Finnhub en CADA apertura de accion, no solo al pulsar analisis")


def test_analyze_sigue_sirviendolos():
    """La otra mitad: que no se hayan perdido por el camino."""
    cuerpo = _cuerpo("analyze")
    assert "finnhub_insider_transactions" in cuerpo
    assert "finnhub_earnings_surprises" in cuerpo
    assert '"insider": insider' in cuerpo
    assert '"earnings_history": earnings_hist' in cuerpo


# ── Las fuentes que SI paga la carga de la pagina ────────────────────────────
def test_el_dashboard_no_ha_ganado_fuentes_externas_nuevas():
    """Congela la lista de lo que cuesta red al abrir una accion.

    Si alguien anade una fuente, este test falla y obliga a decirlo en la revision en
    vez de que aparezca en la factura.
    """
    cuerpo = _cuerpo("_construir_dashboard")
    esperadas = {
        "market_data.get_quote",                  # cotizacion
        "market_data.get_stock_data",             # velas
        "market_data.get_full_indicator_history",  # historico diario (accion y SPY)
        "external_data.finnhub_recommendation_trends",  # consenso, cache 4 h
        "external_data.finnhub_price_target",     # precio objetivo, cache 4 h
        "polygon_data.get_volume_profile",        # perfil de volumen, cache 12 h
    }
    # Cualquier `modulo.funcion` que huela a fuente externa.
    encontradas = set(re.findall(
        r"\b(?:market_data|external_data|polygon_data|fmp_data)\.[a-z_]+", cuerpo))
    # `_cached_vp` envuelve a polygon_data; se resuelve en su propio helper.
    encontradas.discard("market_data.data_health")   # inspecciona un DataFrame ya cargado
    encontradas.discard("market_data.df_to_candles")  # transformacion en memoria
    encontradas.discard("market_data.get_news")       # va por el helper cacheado
    # Agregacion en memoria sobre los `trends` ya descargados: no abre red.
    encontradas.discard("external_data.aggregate_recommendation")
    nuevas = encontradas - esperadas
    assert not nuevas, f"fuentes externas nuevas en el dashboard: {sorted(nuevas)}"


# ── Datos degradados y confianza ─────────────────────────────────────────────
def test_los_datos_degradados_recortan_la_confianza():
    """El requisito 7. `data_health.degraded` no puede quedarse en un aviso de texto:
    el analisis se calculo sobre datos de respaldo, y la confianza tiene que reflejarlo.
    """
    cuerpo = _cuerpo("analyze")
    assert "market_data.data_health(df)" in cuerpo
    assert 'health.get("degraded")' in cuerpo
    assert 'result["confidence"] = min(c, 60)' in cuerpo, (
        "el techo de confianza por datos degradados ha desaparecido")


def test_el_dashboard_sigue_publicando_data_health():
    """La pantalla en frio no tiene `analysis`, asi que su unica via para saber que los
    datos estan degradados es este campo — y la tesis lo lee para `limita_confianza`."""
    cuerpo = _cuerpo("_construir_dashboard")
    assert '"data_health": health' in cuerpo
    assert "market_data.data_health(df_ind)" in cuerpo


def test_la_tesis_viaja_en_la_respuesta_del_dashboard():
    """Sin esto la pagina vuelve a estar muda en frio, que es el fallo que abrio la Fase 3."""
    cuerpo = _cuerpo("_construir_dashboard")
    assert 'result["tesis"] = tesis.redactar(result)' in cuerpo
    assert '"generado_en"' in cuerpo
