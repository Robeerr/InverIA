"""Tests del precalentado del dashboard.

Qué resuelve: servir-caducado-y-refrescar ya hace instantánea la SEGUNDA visita a un
ticker, pero la primera del día paga el ensamblado completo. Para la watchlist y la cartera
—las acciones que de verdad se miran— la primera visita es la norma, no la excepción.

El riesgo de un bucle así no es que falle, es que se coma la cuota de Finnhub por detrás y
deje sin datos a quien está navegando. Estos tests fijan el presupuesto.

Ejecutar:  cd backend && pytest tests/ -v
"""
import asyncio

import pytest

pytest.importorskip("pandas")
import server  # noqa: E402
import market_data as md  # noqa: E402


# ── Que la caché que se calienta sea la que se pide ──────────────────────────

def test_se_calienta_el_mismo_timeframe_que_pide_la_web():
    """La clave es dashboard:{símbolo}:{timeframe}. Calentar otro llena una entrada
    distinta de la que se pide después, y el clic sigue pagando la carga entera. Ya pasó
    una vez con la precarga del ratón, que usaba "1Y" contra el "1D" del Dashboard."""
    assert server._TIMEFRAME_PREWARM == "1D"

    ruta = "../frontend/src/pages/Dashboard.jsx"
    import os
    ruta = os.path.join(os.path.dirname(__file__), "..", ruta)
    if not os.path.exists(ruta):
        pytest.skip("frontend no disponible")
    with open(ruta, encoding="utf-8") as fh:
        js = fh.read()
    assert f'TIMEFRAME_BASE = "{server._TIMEFRAME_PREWARM}"' in js, (
        "el timeframe del precalentado y el del Dashboard han dejado de coincidir")


def test_el_ciclo_cabe_en_la_ventana_de_servible():
    """Si el ciclo fuera más lento que DASHBOARD_STALE_MAX, la entrada se caería de la
    ventana entre vuelta y vuelta y el peor caso volvería a ser la carga completa —
    justo lo que el precalentado viene a evitar."""
    # No basta con contar las pausas: ensamblar un dashboard TARDA, y ese es justamente el
    # trabajo que se está adelantando. Se presupuesta el peor caso realista — el tope de 8 s
    # por fuente que aplica _construir_dashboard — o el margen se evapora en producción sin
    # que el test se entere.
    _PEOR_CASO_POR_SIMBOLO = 8.0
    vuelta_completa = (server.DASHBOARD_PREWARM_CADENCIA
                       + server.DASHBOARD_PREWARM_MAX
                       * (server.DASHBOARD_PREWARM_PAUSA + _PEOR_CASO_POR_SIMBOLO))
    assert vuelta_completa < server._DASHBOARD_STALE_MAX, (
        f"una vuelta tarda hasta {vuelta_completa:.0f}s y la ventana es "
        f"{server._DASHBOARD_STALE_MAX}s: habría huecos sin cubrir")


# ── Presupuesto de cuota ─────────────────────────────────────────────────────

def test_las_llamadas_van_espaciadas_por_debajo_de_la_reserva_de_fondo():
    """El limitador da como mucho bg_cap llamadas/min a las tareas de fondo (el resto queda
    reservado para lo que sirve a una petición del usuario). Si el precalentado se come ese
    tope entero, el worker de señales y el refresco en segundo plano se quedan sin cuota."""
    lim = md.get_finnhub_limiter()
    por_minuto = 60.0 / server.DASHBOARD_PREWARM_PAUSA
    assert por_minuto <= lim.bg_cap * 0.7, (
        f"{por_minuto:.0f} llamadas/min contra un tope de fondo de {lim.bg_cap}: "
        "no deja margen para el worker de señales ni el refresco en segundo plano")


def test_el_gasto_diario_es_una_fraccion_pequena_de_la_cuota():
    """Cifra de cabecera: cuánto cuesta al día tener la watchlist siempre caliente."""
    lim = md.get_finnhub_limiter()
    horas_ventana = 10                      # 12:00-22:00 UTC, de lunes a viernes
    vueltas = horas_ventana * 3600 / server.DASHBOARD_PREWARM_CADENCIA
    # Lo caro (analistas 4h, fundamentales 1h, volume profile 12h) ya va cacheado: lo que
    # se paga cada vuelta es del orden de una cotización por símbolo.
    llamadas = vueltas * server.DASHBOARD_PREWARM_MAX
    disponibles = lim.max_per_min * 60 * horas_ventana
    assert llamadas / disponibles < 0.05, (
        f"{llamadas:.0f} llamadas sobre {disponibles:.0f} disponibles "
        f"({llamadas / disponibles:.1%}): demasiado para un trabajo de fondo")


# ── Se puede apagar ──────────────────────────────────────────────────────────

def test_se_puede_desactivar():
    """Un bucle que gasta cuota sola tiene que tener interruptor, sin tocar código."""
    assert isinstance(server.DASHBOARD_PREWARM, bool)
    import inspect
    src = inspect.getsource(server)
    assert "if not DASHBOARD_PREWARM:" in src, "el interruptor no se comprueba"


# ── Los símbolos: una sola definición ────────────────────────────────────────

def test_los_simbolos_salen_de_la_watchlist_y_la_cartera(monkeypatch):
    class _Cursor:
        def __init__(self, docs): self._docs = docs
        async def to_list(self, n): return self._docs

    class _Col:
        def __init__(self, docs): self._docs = docs
        def find(self, *a, **k): return _Cursor(self._docs)

    class _DB:
        watchlist = _Col([{"symbol": "aapl"}, {"symbol": "MSFT"}])
        signal_entries = _Col([{"symbol": "MSFT"}, {"symbol": "nvda"}])

    monkeypatch.setattr(server, "db", _DB())
    syms = asyncio.run(server._simbolos_que_te_importan())
    assert syms == {"AAPL", "MSFT", "NVDA"}, "deben ir en mayúsculas y sin repetidos"


def test_si_la_base_de_datos_falla_no_se_rompe_el_bucle(monkeypatch):
    """Mongo caído no debe tumbar la tarea de fondo para siempre: la siguiente vuelta
    tiene que poder reintentarlo."""
    class _DBRota:
        @property
        def watchlist(self): raise RuntimeError("Atlas no responde")

    monkeypatch.setattr(server, "db", _DBRota())
    assert asyncio.run(server._simbolos_que_te_importan()) == set()


def test_el_precalentado_del_chartista_usa_los_mismos_simbolos():
    """Estaban escritos a mano en dos sitios: así se calentaban conjuntos distintos."""
    import inspect
    src = inspect.getsource(server)
    assert src.count("_simbolos_que_te_importan()") >= 2, (
        "los dos precalentados deben partir del mismo conjunto de símbolos")
