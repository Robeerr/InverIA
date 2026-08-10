"""Caché de dashboards y reparto del precalentado.

Los dos fallos que cubren estos tests tenían el mismo síntoma —la portada sin fuerza,
sin razones y sin aviso de calidad de dato— y ninguno daba error. Una pantalla más
pobre no se parece a una avería, así que pueden durar meses.

  Bug A · el precalentado hacía `list(syms)[:20]` sobre un CONJUNTO. El orden de
          iteración de un conjunto es arbitrario pero estable dentro del proceso, así
          que con más de 20 símbolos se calentaban siempre los mismos veinte y el
          resto nunca. No era una rotación lenta: era un punto ciego fijo.

  Bug B · la purga de la caché borraba por `ttl`, sin saber que el dashboard se sirve
          caducado hasta 30 minutos con `get_stale`. A los 5 minutos ya era carne de
          purga, y bastaba una escritura cualquiera con la caché llena.
"""
import time

import pytest

pytest.importorskip("fastapi", reason="requiere fastapi")
import server  # noqa: E402


# ── Bug B · la purga respeta la ventana de "caducado pero servible" ──────────
def test_la_purga_no_se_lleva_lo_que_todavia_es_servible():
    c = server._TTLCache(maxsize=10)
    c.set("dashboard:INTC:1D", {"buy_levels": [1]}, ttl=1, servible_hasta=1800)
    time.sleep(1.05)  # caducado, pero dentro de la ventana de servible

    for i in range(15):  # fuerza la purga varias veces
        c.set(f"quote:S{i}", {"p": 1}, ttl=60)

    val, fresco = c.get_stale("dashboard:INTC:1D", max_age=1800)
    assert val is not None, "la purga se llevó una entrada que get_stale debía servir"
    assert fresco is False, "y sigue marcándose como no fresca, que es lo correcto"


def test_lo_que_ya_no_es_servible_si_se_purga():
    """La corrección no puede convertir la caché en un almacén que no suelta nada."""
    c = server._TTLCache(maxsize=10)
    c.set("dashboard:X:1D", {"v": 1}, ttl=1, servible_hasta=1)
    time.sleep(1.05)
    for i in range(15):
        c.set(f"quote:S{i}", {"p": 1}, ttl=60)
    assert c.get_stale("dashboard:X:1D", max_age=1800)[0] is None


def test_una_entrada_normal_sin_ventana_se_purga_como_siempre():
    """Comportamiento anterior intacto para todo lo que no declara `servible_hasta`."""
    c = server._TTLCache(maxsize=10)
    c.set("quote:AAPL", {"p": 1}, ttl=1)
    time.sleep(1.05)
    for i in range(15):
        c.set(f"otro:{i}", {"p": 1}, ttl=60)
    assert c.get("quote:AAPL") is None


def test_get_y_get_stale_siguen_comportandose_igual():
    c = server._TTLCache(maxsize=100)
    c.set("k", "v", ttl=60, servible_hasta=600)
    assert c.get("k") == "v"
    assert c.get_stale("k", max_age=600) == ("v", True)
    assert c.get("no-existe") is None
    assert c.get_stale("no-existe", max_age=600) == (None, False)


def test_los_valores_del_dashboard_encajan_entre_si():
    """ttl < cadencia del precalentado < ventana de servible.

    Si el ttl igualara la cadencia, cualquier desfase dejaría la entrada fresca y el
    `if fresco: continue` del precalentado se saltaría la vuelta entera.
    """
    assert server.DASHBOARD_TTL < server.DASHBOARD_PREWARM_CADENCIA
    assert server.DASHBOARD_PREWARM_CADENCIA < server._DASHBOARD_STALE_MAX


# ── Bug A · el reparto por tandas rotatorias ────────────────────────────────
def test_con_pocos_simbolos_entran_todos():
    syms = {"AAPL", "MSFT", "NVDA"}
    assert server._tanda_a_precalentar(syms, vuelta=0, tamano=20) == ["AAPL", "MSFT", "NVDA"]


def test_ningun_simbolo_se_queda_fuera_para_siempre():
    """El corazón del Bug A: con 50 símbolos y tandas de 20, en 3 vueltas están todos."""
    syms = {f"S{i:02d}" for i in range(50)}
    vistos = set()
    for vuelta in range(3):
        vistos.update(server._tanda_a_precalentar(syms, vuelta, tamano=20))
    assert vistos == syms


def test_el_reparto_es_determinista():
    """Mismo conjunto y misma vuelta -> misma tanda, aunque el conjunto se construya
    en otro orden. Sin esto no se puede razonar sobre qué se calentó."""
    a = {f"S{i}" for i in range(30)}
    b = set(reversed(sorted(a)))
    assert server._tanda_a_precalentar(a, 1, tamano=20) == server._tanda_a_precalentar(b, 1, tamano=20)


def test_el_coste_por_vuelta_no_sube():
    syms = {f"S{i:03d}" for i in range(200)}
    for vuelta in range(5):
        assert len(server._tanda_a_precalentar(syms, vuelta, tamano=20)) == 20


def test_la_ventana_da_la_vuelta_sin_partirse():
    """Al llegar al final continúa por el principio, en vez de devolver una tanda corta
    que desperdiciaría parte del presupuesto de la vuelta."""
    syms = {f"S{i}" for i in range(25)}
    tanda = server._tanda_a_precalentar(syms, vuelta=1, tamano=20)
    assert len(tanda) == 20
    assert len(set(tanda)) == 20, "sin repetidos dentro de la misma tanda"


def test_sin_simbolos_no_revienta():
    assert server._tanda_a_precalentar(set(), vuelta=0) == []


# ── Las dos ventanas de la portada ──────────────────────────────────────────
def test_la_ventana_de_alertas_no_depende_de_la_ultima_visita():
    """El fallo que hacía desaparecer las alertas al recargar.

    El frontend sella la última visita en CADA carga con éxito. Si esa marca decidiera
    también qué alertas cuentan, recargar la pantalla borraría las alertas del día — y
    recargar es lo primero que uno hace cuando algo no cuadra.
    """
    from datetime import datetime, timedelta, timezone
    ahora = datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc)
    hace_un_minuto = (ahora - timedelta(minutes=1)).isoformat()

    corte_alertas, corte_cerebro = server._ventanas_de_hoy(hace_un_minuto, ahora=ahora)

    assert corte_alertas != hace_un_minuto, "las alertas no pueden mirar solo el último minuto"
    assert corte_alertas == (ahora - timedelta(hours=24)).isoformat()
    # Y una alerta de hace tres horas sigue entrando.
    assert (ahora - timedelta(hours=3)).isoformat() >= corte_alertas


def test_el_cerebro_si_usa_la_ultima_visita():
    """Ahí la pregunta es otra: qué ha cambiado desde que no vengo."""
    from datetime import datetime, timedelta, timezone
    ahora = datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc)
    hace_dos_dias = (ahora - timedelta(days=2)).isoformat()
    _, corte_cerebro = server._ventanas_de_hoy(hace_dos_dias, ahora=ahora)
    assert corte_cerebro == hace_dos_dias


def test_sin_visita_previa_ambas_ventanas_son_de_24h():
    from datetime import datetime, timezone
    ahora = datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc)
    corte_alertas, corte_cerebro = server._ventanas_de_hoy(None, ahora=ahora)
    assert corte_alertas == corte_cerebro


def test_una_visita_muy_antigua_no_alarga_la_ventana_de_alertas():
    """Volver después de un mes no debe sacar alertas de hace tres semanas: siguen
    siendo 24 h. Lo viejo es historia, no atención de hoy."""
    from datetime import datetime, timedelta, timezone
    ahora = datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc)
    hace_un_mes = (ahora - timedelta(days=30)).isoformat()
    corte_alertas, corte_cerebro = server._ventanas_de_hoy(hace_un_mes, ahora=ahora)
    assert corte_alertas > hace_un_mes
    assert corte_cerebro == hace_un_mes


# ── P1 · El precalentado es trabajo de FONDO y hay que decirlo ───────────────
def test_el_limitador_distingue_fondo_de_primer_plano():
    """El techo NO es el mismo, y de ahí venía el 50/50: sin marcar el contexto, el
    precalentado usaba `max_per_min` (50) en vez de `bg_cap` (25). Con 5 llamadas por
    símbolo llenaba la ventana él solo, veía 50 > umbral y concluía "hay alguien
    navegando" — siendo él quien navegaba."""
    import market_data
    lim = market_data.get_finnhub_limiter()
    assert lim.bg_cap < lim.max_per_min
    # El umbral de pausa tiene que quedar POR ENCIMA del techo de fondo, o el
    # precalentado se pararía a sí mismo aun estando bien marcado.
    assert server._umbral_prewarm() > lim.bg_cap


def test_el_contexto_de_fondo_se_marca_y_se_restaura():
    import market_data
    assert market_data._finnhub_bg_ctx.get() is False
    token = market_data.enter_finnhub_background()
    try:
        assert market_data._finnhub_bg_ctx.get() is True
    finally:
        market_data.reset_finnhub_background(token)
    assert market_data._finnhub_bg_ctx.get() is False, "el contexto se ha quedado sucio"


def test_el_bucle_de_precalentado_marca_el_contexto():
    """Centinela sobre el código: la marca tiene que estar en el bucle, no en un sitio
    cualquiera, y con su restauración."""
    import inspect
    src = inspect.getsource(server.lifespan)
    assert "enter_finnhub_background()" in src
    assert "reset_finnhub_background(" in src


# ── P3 · La cola de calentado a petición ────────────────────────────────────
@pytest.fixture(autouse=True)
def _cola_limpia():
    server._cola_calentado.clear()
    server._hay_pendientes.clear()
    yield
    server._cola_calentado.clear()
    server._hay_pendientes.clear()


def test_encolar_deduplica():
    assert server._encolar_calentado(["AAPL", "NVDA"]) == 2
    assert server._encolar_calentado(["AAPL", "MSFT"]) == 1, "AAPL ya estaba"
    assert set(server._cola_calentado) == {"AAPL", "NVDA", "MSFT"}


def test_la_cola_esta_acotada():
    """Si creciera sin límite, recargar la portada en bucle la haría crecer sin fin."""
    server._encolar_calentado([f"S{i:03d}" for i in range(200)])
    assert len(server._cola_calentado) == server._COLA_CALENTADO_MAX


def test_se_atiende_por_orden_de_llegada():
    server._encolar_calentado(["AAA", "BBB", "CCC"])
    assert server._tomar_de_la_cola(2) == ["AAA", "BBB"]
    assert list(server._cola_calentado) == ["CCC"]


def test_tomar_de_la_cola_la_vacia():
    server._encolar_calentado(["AAA"])
    assert server._tomar_de_la_cola(10) == ["AAA"]
    assert server._cola_calentado == {}


def test_el_evento_despierta_al_bucle_y_se_apaga_al_vaciarse():
    """Sin el evento, un símbolo pedido desde la portada esperaría hasta la cadencia
    completa —20 minutos—, y encolar sería peor que el calentado directo que sustituye."""
    assert not server._hay_pendientes.is_set()
    server._encolar_calentado(["AAA"])
    assert server._hay_pendientes.is_set()
    server._tomar_de_la_cola(10)
    assert not server._hay_pendientes.is_set()


def test_encolar_normaliza_y_descarta_vacios():
    server._encolar_calentado([" aapl ", "", None, "nvda"])
    assert set(server._cola_calentado) == {"AAPL", "NVDA"}


def test_la_portada_encola_y_no_calcula():
    """El punto de P3: /hoy no puede lanzar _construir_dashboard. Lanzaba hasta cinco a
    la vez —unas 25 llamadas de golpe— saltándose el umbral y en primer plano."""
    import inspect
    src = inspect.getsource(server.dashboard_hoy)
    assert "_encolar_calentado(" in src
    # Se miran las LLAMADAS del árbol de sintaxis, no el texto: el comentario que
    # explica por qué se quitó menciona esas funciones, y un test sobre el texto
    # obligaría a borrar la explicación para tenerlo en verde.
    import ast
    import textwrap
    llamadas = {
        n.func.id
        for n in ast.walk(ast.parse(textwrap.dedent(src)))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_refrescar_dashboard_en_segundo_plano" not in llamadas
    assert "_construir_dashboard" not in llamadas
