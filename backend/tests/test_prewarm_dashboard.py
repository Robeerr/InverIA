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



def _cuerpo_del_precalentado() -> str:
    """Codigo de _prewarm_dashboards, delimitado por sus marcas de inicio y fin.

    Antes se cortaba a 3.000 caracteres: al documentar un cambio, el comentario empujaba
    el codigo fuera del trozo y el test fallaba sin que nada estuviera roto.
    """
    import inspect
    src = inspect.getsource(server)
    ini = src.index("async def _prewarm_dashboards")
    fin = src.index("asyncio.create_task(_prewarm_dashboards", ini)
    return src[ini:fin]


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
    # 8 s del tope por fuente de _construir_dashboard + ~2 s del backtest, que ahora
    # también se precalienta.
    _PEOR_CASO_POR_SIMBOLO = 10.0
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


# ── Los paneles que se cargan solos ──────────────────────────────────────────
# Medido en produccion tras arreglar el dashboard: la carga bajo a 254 ms, pero los paneles
# que se disparan solos al cambiar de accion sumaban 1.894 ms — o sea el 88% de lo que se
# esperaba. Arreglar solo el dashboard no arregla la sensacion de lentitud.

def test_el_precalentado_cubre_los_paneles_que_se_cargan_solos():
    """No basta con calentar el dashboard: 'Tus fuentes' (~985 ms) y 'Backtest' (~900 ms)
    se piden solos al elegir una accion y eran el grueso de la espera."""
    cuerpo = _cuerpo_del_precalentado()
    assert "backtest_levels(" in cuerpo, "el Backtest se paga entero en la primera visita"
    assert "_newsletters_recientes(" in cuerpo, "'Tus fuentes' se paga entero en la primera visita"


def test_las_newsletters_se_leen_una_vez_y_no_por_simbolo():
    """La lectura del ultimo mes es la MISMA para cualquier accion. Repetirla por simbolo
    era ~985 ms en cada cambio de accion, y ademas tres veces (panel, radar y menciones)."""
    import inspect
    src = inspect.getsource(server)
    # Nadie debe consultar la coleccion directamente: todo pasa por el lector cacheado.
    crudas = [ln.strip() for ln in src.splitlines()
              if "db.newsletter_summaries.find(" in ln and not ln.strip().startswith("#")]
    assert len(crudas) == 1, (
        f"{len(crudas)} lecturas directas de newsletter_summaries; deben ir por "
        f"_newsletters_recientes(): {crudas}")
    assert server._TTL_NEWSLETTERS >= 300, "una cache tan corta no ahorra las lecturas"


def test_los_tickers_se_normalizan_al_guardar():
    """Se guardaban tal cual los devolvia la IA, asi que cada lectura tenia que limpiarlos
    y era imposible filtrar por ticker en Mongo sin perder menciones."""
    import inspect
    import newsletter_ingest
    src = inspect.getsource(newsletter_ingest)
    assert 'a["ticker"] = t' in src, "el ticker debe quedar normalizado en el documento"


# ── Ceder el paso al usuario ─────────────────────────────────────────────────
# Medido en produccion: con la cuota en 49/50, una carga que normalmente son ~500 ms se fue
# a 5.043 ms. Las fuentes costaban 309 ms; el resto era esperar al limitador de Finnhub.
# bg_cap impide que el fondo se PASE, pero no impide que llene la ventana justo mientras
# alguien navega — y entonces las llamadas del usuario, que si pueden llegar a max_per_min,
# se quedan haciendo cola detras.

def test_hay_umbral_para_apartarse():
    lim = md.get_finnhub_limiter()
    umbral = server._umbral_prewarm()
    assert umbral < lim.max_per_min, (
        "un umbral igual o mayor que el tope no se alcanza nunca: no aparta nada")
    # Tiene que dejar sitio para que una carga completa no espere al limitador.
    libres = lim.max_per_min - umbral
    assert libres >= 10, (
        f"solo deja {libres} llamadas libres: una carga hace varias y acabaria esperando")


def test_el_precalentado_no_se_para_a_si_mismo():
    """El fallo que tuvo la primera version: el umbral estaba en 25, exactamente el techo
    de las tareas de fondo (bg_cap). El precalentado gasta 15 llamadas/min el solo; sumando
    el resto del fondo se llegaba al techo, y entonces se detenia creyendo que habia alguien
    navegando — cuando ese alguien era el. Calentaba dos o tres simbolos y abandonaba.

    Estando el umbral POR ENCIMA de bg_cap, superarlo implica por fuerza llamadas de primer
    plano, porque el fondo no puede pasar de ahi. Que es justo lo que se quiere detectar."""
    lim = md.get_finnhub_limiter()
    assert server._umbral_prewarm() > lim.bg_cap, (
        f"umbral {server._umbral_prewarm()} contra un techo de fondo de {lim.bg_cap}: "
        "las propias tareas de fondo lo disparan y el precalentado se apaga solo")


def test_el_umbral_se_deriva_del_limitador():
    """Si fuera un numero suelto, cambiar bg_cap volveria a romper la relacion en silencio."""
    original = md._finnhub_limiter
    try:
        md._finnhub_limiter = md._FinnhubLimiter(max_per_min=200, bg_reserve=100)
        assert server._umbral_prewarm() > md._finnhub_limiter.bg_cap
    finally:
        md._finnhub_limiter = original


def test_el_precalentado_mira_la_cuota_antes_de_gastarla():
    cuerpo = _cuerpo_del_precalentado()
    assert "uso_ultimo_minuto()" in cuerpo, (
        "el precalentado debe consultar la cuota ANTES de gastarla, no descubrir que no "
        "hay bloqueandose")
    assert "_umbral_prewarm()" in cuerpo


def test_el_limitador_sabe_decir_cuanto_lleva_gastado():
    lim = md._FinnhubLimiter(max_per_min=50)
    assert lim.uso_ultimo_minuto() == 0
    ahora = md.time.time()
    lim.calls = [ahora - 5, ahora - 10, ahora - 90]   # el de 90 s ya no cuenta
    assert lim.uso_ultimo_minuto() == 2


def test_mirar_la_cuota_no_la_gasta():
    """Consultarla no debe reservar hueco: seria contraproducente."""
    lim = md._FinnhubLimiter(max_per_min=50)
    for _ in range(5):
        lim.uso_ultimo_minuto()
    assert lim.uso_ultimo_minuto() == 0
