"""¿De qué depende REALMENTE lo que consume /hoy?

La portada lee exactamente tres claves del dashboard cacheado: `buy_levels`,
`data_health` e `indicators`. El precalentado, en cambio, construye el dashboard
ENTERO —el de la página de acción— y eso cuesta 5 llamadas a Finnhub por símbolo:
quote, news, trends, price_target y fundamentales.

Antes de aligerar el precalentado hay que demostrar, no suponer, que esas tres
claves no dependen ni directa ni indirectamente de las cuatro fuentes caras. Leer
la firma de `compute_buy_levels` sugiere que solo necesita el precio, pero una
dependencia indirecta —un enriquecimiento que modifica `quote` y de ahí el precio,
por ejemplo— no se ve leyendo.

Así que se construye el dashboard DOS VECES sobre los mismos datos de mercado:
una con las cuatro fuentes respondiendo y otra con las cuatro anuladas, y se
comparan las tres claves.

No se toca red ni base de datos: se sustituyen las funciones que salen fuera.
"""
import asyncio

import pytest

pytest.importorskip("pandas", reason="requiere pandas")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import external_data  # noqa: E402
import market_data  # noqa: E402
import market_regime  # noqa: E402
import server  # noqa: E402

SYM = "TEST"


def _velas(n=400, semilla=7):
    """Serie OHLCV determinista y con forma realista.

    Hace falta longitud de sobra: la SMA200 necesita 200 sesiones y la salida por
    media de 10 semanas otras 50. Con una serie corta, las tres claves saldrían
    vacías en los dos casos y el test pasaría sin comprobar nada.
    """
    rng = np.random.default_rng(semilla)
    precio = 100 + np.cumsum(rng.normal(0.05, 1.2, n))
    precio = np.maximum(precio, 5.0)
    fechas = pd.bdate_range(end="2026-08-07", periods=n)
    return pd.DataFrame({
        "Date": fechas,
        "Open": precio + rng.normal(0, 0.3, n),
        "High": precio + np.abs(rng.normal(0.8, 0.4, n)),
        "Low": precio - np.abs(rng.normal(0.8, 0.4, n)),
        "Close": precio,
        "Volume": rng.integers(1_000_000, 5_000_000, n),
    })


DF = _velas()
QUOTE = {"price": float(DF["Close"].iloc[-1]), "previous_close": float(DF["Close"].iloc[-2]),
         "change_percent": 0.8, "symbol": SYM, "name": "Test Corp"}

# Lo que devolverían las cuatro fuentes caras cuando SÍ responden.
NOTICIAS = [{"headline": "Titular de prueba", "datetime": 1_700_000_000, "url": "http://x"}]
TRENDS = [{"buy": 10, "hold": 3, "sell": 1, "strongBuy": 5, "strongSell": 0, "period": "2026-08-01"}]
PRECIO_OBJETIVO = {"targetMean": 180.0, "targetHigh": 220.0, "targetLow": 140.0}
FUNDAMENTALES = {"pe_ratio": 24.5, "revenue_growth": 0.18, "eps_growth": 0.22,
                 "high_52w": 210.0, "return_52w": 0.31}


@pytest.fixture
def mercado(monkeypatch):
    """Las fuentes que NO cuestan cuota, fijas y siempre iguales."""
    monkeypatch.setattr(market_data, "get_quote", lambda *a, **k: dict(QUOTE))
    monkeypatch.setattr(market_data, "get_stock_data", lambda *a, **k: DF.copy())
    monkeypatch.setattr(market_data, "get_full_indicator_history", lambda *a, **k: DF.copy())
    monkeypatch.setattr(market_data, "get_extended_quote", lambda *a, **k: {})
    monkeypatch.setattr(market_regime, "get_market_regime",
                        lambda *a, **k: {"light": "verde", "label": "Mercado sano"})
    server._cache.clear()


def _construir(con_fuentes_caras: bool, monkeypatch):
    """Construye el dashboard con las cuatro fuentes caras activas o anuladas."""
    if con_fuentes_caras:
        monkeypatch.setattr(market_data, "get_news", lambda *a, **k: list(NOTICIAS))
        monkeypatch.setattr(external_data, "finnhub_recommendation_trends", lambda *a, **k: list(TRENDS))
        monkeypatch.setattr(external_data, "finnhub_price_target", lambda *a, **k: dict(PRECIO_OBJETIVO))
        monkeypatch.setattr(external_data, "finnhub_basic_financials", lambda *a, **k: dict(FUNDAMENTALES))
    else:
        # Anuladas: es lo que devolverían si el precalentado dejara de pedirlas.
        monkeypatch.setattr(market_data, "get_news", lambda *a, **k: [])
        monkeypatch.setattr(external_data, "finnhub_recommendation_trends", lambda *a, **k: None)
        monkeypatch.setattr(external_data, "finnhub_price_target", lambda *a, **k: None)
        monkeypatch.setattr(external_data, "finnhub_basic_financials", lambda *a, **k: {})

    server._cache.clear()
    return asyncio.run(server._construir_dashboard(SYM, "1D", f"prueba:{con_fuentes_caras}"))


# ── La comprobación que pide P2 ──────────────────────────────────────────────
CLAVES_DE_HOY = ("buy_levels", "data_health", "indicators")


def test_las_tres_claves_de_hoy_no_dependen_de_las_fuentes_caras(mercado, monkeypatch):
    completo = _construir(True, monkeypatch)
    ligero = _construir(False, monkeypatch)

    for clave in CLAVES_DE_HOY:
        assert completo[clave] == ligero[clave], (
            f"'{clave}' CAMBIA al quitar news/trends/price_target/fundamentales: "
            f"hay una dependencia indirecta y el precalentado ligero no sería seguro")


def test_el_test_anterior_comprueba_algo_de_verdad(mercado, monkeypatch):
    """Centinela: si la serie fuera demasiado corta o el motor fallara, las tres claves
    saldrían vacías en los dos casos y la comparación pasaría sin medir nada."""
    d = _construir(True, monkeypatch)
    assert d["buy_levels"], "sin niveles calculados, la comparación no demuestra nada"
    assert d["indicators"], "sin indicadores, ídem"
    assert d["indicators"].get("sma"), "faltan las medias: la serie es demasiado corta"
    assert any(z.get("strength") for z in d["buy_levels"]), "los niveles no traen fuerza"


def test_las_fuentes_caras_si_afectan_a_lo_demas(mercado, monkeypatch):
    """La otra cara: quitarlas NO es gratis para la página de acción. Es el coste que
    hay que aceptar a cambio, y conviene tenerlo escrito."""
    completo = _construir(True, monkeypatch)
    ligero = _construir(False, monkeypatch)

    assert completo["news"] and not ligero["news"]
    assert completo["analyst"] != ligero["analyst"]


def test_hoy_solo_lee_esas_tres_claves():
    """Si algún día la portada empezara a leer una cuarta clave, este test lo caza:
    aligerar el precalentado dejaría de ser seguro sin que nada avisara."""
    import ast
    import inspect
    leidas = set()
    for fn in (server._niveles_del_motor, server._aviso_de_datos, server.dashboard_hoy):
        for nodo in ast.walk(ast.parse(inspect.getsource(fn))):
            # dash.get("x") / dash["x"] sobre la variable del dashboard cacheado
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) \
                    and nodo.func.attr == "get" and isinstance(nodo.func.value, ast.Name) \
                    and nodo.func.value.id == "dash" and nodo.args \
                    and isinstance(nodo.args[0], ast.Constant):
                leidas.add(nodo.args[0].value)
    assert leidas <= set(CLAVES_DE_HOY), (
        f"la portada lee claves nuevas del dashboard: {leidas - set(CLAVES_DE_HOY)}")
    assert leidas == set(CLAVES_DE_HOY), f"esperadas {CLAVES_DE_HOY}, encontradas {leidas}"
