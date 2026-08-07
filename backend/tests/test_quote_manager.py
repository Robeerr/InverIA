"""Tests del gestor de cotizaciones en directo (_QuoteManager).

Dos problemas medidos, los dos invisibles desde la pantalla:

1. El bucle REST de respaldo iba a 15 s FIJOS: 4 llamadas/min por símbolo, las 24 horas,
   fines de semana incluidos. Con una pestaña abierta toda la tarde son ~5.700 llamadas al
   día por símbolo, casi todas reconsultando un precio que no se mueve (mercado cerrado) o
   que ya está llegando por el stream de trades.

2. Cada trade suelto era un envío a cada cliente. Un valor líquido cruza cientos de
   operaciones por segundo; el frontend las junta por fotograma, así que ese tráfico se
   descartaba nada más llegar.

Ejecutar:  cd backend && pytest tests/ -v
"""
import asyncio

import pytest

pytest.importorskip("pandas")
import server  # noqa: E402


@pytest.fixture
def gestor():
    return server._QuoteManager()


# ── Cadencia del bucle REST ──────────────────────────────────────────────────

def test_con_el_mercado_cerrado_apenas_se_consulta(gestor, monkeypatch):
    monkeypatch.setattr(server.alerts_worker, "is_market_open", lambda: False)
    espera = gestor._espera_baseline("AAPL")
    assert espera >= 300, (
        f"{espera}s con el mercado cerrado: no hay precio nuevo que buscar, solo se gasta cuota")


def test_con_el_stream_vivo_el_rest_solo_vigila(gestor, monkeypatch):
    """Si están entrando trades, el precio ya viene por ahí: el REST es red de seguridad."""
    monkeypatch.setattr(server.alerts_worker, "is_market_open", lambda: True)
    gestor._ultimo_tick["AAPL"] = server._time.time()
    assert gestor._espera_baseline("AAPL") == gestor._ESPERA_STREAM
    assert gestor._ESPERA_STREAM >= 60


def test_sin_stream_y_con_mercado_abierto_se_mantiene_el_ritmo(gestor, monkeypatch):
    """Aquí el REST SÍ es la única fuente del precio: no se debe ralentizar."""
    monkeypatch.setattr(server.alerts_worker, "is_market_open", lambda: True)
    assert gestor._espera_baseline("AAPL") == 15.0

    # Un tick MUY viejo cuenta como "sin stream": el símbolo dejó de emitir.
    gestor._ultimo_tick["AAPL"] = server._time.time() - 3600
    assert gestor._espera_baseline("AAPL") == 15.0


def test_si_no_se_sabe_si_el_mercado_esta_abierto_se_elige_lo_seguro(gestor, monkeypatch):
    """Ante un fallo del reloj, equivocarse hacia 'lento' deja el precio congelado."""
    def _explota():
        raise RuntimeError("sin zona horaria")
    monkeypatch.setattr(server.alerts_worker, "is_market_open", _explota)
    assert gestor._espera_baseline("AAPL") == 15.0


def test_el_ahorro_es_real(gestor, monkeypatch):
    """Comprobación del orden de magnitud que justifica el cambio."""
    monkeypatch.setattr(server.alerts_worker, "is_market_open", lambda: False)
    antes = 24 * 60 * 60 / 15
    despues = 24 * 60 * 60 / gestor._espera_baseline("AAPL")
    assert despues <= antes * 0.06, f"solo baja de {antes:.0f} a {despues:.0f} llamadas/día"


# ── Agrupado de ticks ────────────────────────────────────────────────────────

def _correr(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_una_rafaga_de_trades_no_se_reenvia_entera(gestor):
    enviados = []

    async def _prueba():
        gestor._conns["AAPL"] = ["cliente-falso"]
        gestor._baseline["AAPL"] = {"previous_close": 100.0}

        async def _capturar(sym, payload):
            enviados.append(payload)
        gestor._broadcast = _capturar

        # 200 operaciones seguidas, como en una acción líquida.
        for i in range(200):
            await gestor._on_trade("AAPL", 100.0 + i * 0.01)

    _correr(_prueba())
    assert len(enviados) < 5, f"{len(enviados)} envíos para 200 trades: no se está agrupando"
    assert enviados, "algo tiene que salir"


def test_el_ultimo_precio_no_se_queda_sin_enviar(gestor):
    """El fallo del agrupado ingenuo: si el último trade cae dentro de la ventana y el
    valor deja de cruzar operaciones, ese precio no se emitiría NUNCA y la pantalla se
    quedaría clavada en el anterior sin que nada lo delatara."""
    enviados = []

    async def _prueba():
        gestor._conns["AAPL"] = ["cliente-falso"]
        gestor._baseline["AAPL"] = {"previous_close": 100.0}

        async def _capturar(sym, payload):
            enviados.append(payload)
        gestor._broadcast = _capturar

        await gestor._on_trade("AAPL", 100.0)   # sale enseguida
        await gestor._on_trade("AAPL", 999.0)   # cae en la ventana: queda pendiente
        assert len(enviados) == 1
        # Nadie manda nada más. El envío programado debe rescatarlo.
        await asyncio.sleep(gestor._INTERVALO_ENVIO + 0.2)

    _correr(_prueba())
    assert any(p["price"] == 999.0 for p in enviados), (
        "el último precio se perdió: la pantalla se quedaría en el anterior")


def test_el_snapshot_guarda_siempre_el_ultimo_precio(gestor):
    """Aunque un tick no se emita, quien se conecte después debe ver el precio real."""
    async def _prueba():
        gestor._conns["AAPL"] = ["cliente-falso"]
        gestor._baseline["AAPL"] = {"previous_close": 100.0}
        gestor._broadcast = lambda sym, payload: asyncio.sleep(0)
        await gestor._on_trade("AAPL", 100.0)
        await gestor._on_trade("AAPL", 123.45)   # agrupado, no emitido

    _correr(_prueba())
    assert gestor._last["AAPL"]["price"] == 123.45


# ── Tope de símbolos del stream ──────────────────────────────────────────────

def test_hay_tope_por_debajo_del_limite_de_finnhub(gestor):
    """Pasado el límite, Finnhub descarta las suscripciones EN SILENCIO: el símbolo
    parecería conectado y se quedaría con un precio que no avanza, sin ningún aviso."""
    assert gestor._MAX_SIMBOLOS_STREAM < 50


def test_al_reconectar_no_se_piden_mas_simbolos_que_el_tope():
    """El supervisor re-suscribía _conns entero al reconectar, saltándose el tope."""
    import inspect
    src = inspect.getsource(server._QuoteManager._fh_supervisor)
    assert "_MAX_SIMBOLOS_STREAM" in src, (
        "la re-suscripción tras reconectar debe respetar el tope")


# ── Limpieza al desconectar ──────────────────────────────────────────────────

def test_desconectar_no_deja_estado_del_simbolo(gestor):
    """_baseline, _last y los diccionarios del agrupado acumulaban una entrada por cada
    símbolo visto en toda la vida del proceso."""
    class _WSFalso:
        pass

    ws = _WSFalso()
    gestor._conns["AAPL"] = [ws]
    for d in (gestor._baseline, gestor._last, gestor._pendiente):
        d["AAPL"] = {"x": 1}
    gestor._ultimo_tick["AAPL"] = 1.0
    gestor._ultimo_envio["AAPL"] = 1.0

    async def _prueba():
        gestor.disconnect("AAPL", ws)

    _correr(_prueba())
    for nombre, d in (("_baseline", gestor._baseline), ("_last", gestor._last),
                      ("_pendiente", gestor._pendiente),
                      ("_ultimo_tick", gestor._ultimo_tick),
                      ("_ultimo_envio", gestor._ultimo_envio)):
        assert "AAPL" not in d, f"{nombre} conserva el símbolo tras desconectar"


def test_las_tareas_de_fondo_se_referencian():
    """asyncio solo guarda referencias DÉBILES a las tareas: sin guardarlas, el recolector
    puede llevarse la baja a medias y dejar la suscripción a Finnhub viva para siempre."""
    import inspect
    for fn in (server._QuoteManager.disconnect, server._QuoteManager._on_trade):
        src = inspect.getsource(fn)
        if "create_task" in src:
            assert "_bg_tasks" in src, f"{fn.__name__}: create_task sin guardar la referencia"
