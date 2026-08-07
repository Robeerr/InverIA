"""Regresiones del camino crítico: lo que se paga cada vez que cambias de acción.

Contexto: tras arreglar los 8,7 s de la cotización, la carga bajó a ~1,3 s. Una auditoría
del backend encontró que lo que quedaba eran fuentes lentas SIN caché y llamadas de red
hechas directamente dentro de funciones `async`. Estos tests fijan las dos cosas.

Ejecutar:  cd backend && pytest tests/ -v
"""
import ast
import os

import pytest

pytest.importorskip("pandas")

_DIR = os.path.join(os.path.dirname(__file__), "..")


def _fuente(nombre):
    with open(os.path.join(_DIR, nombre), encoding="utf-8") as fh:
        return fh.read()


def _cuerpo_funcion(src, nombre):
    """Código fuente de una función (async o no) por nombre, vía AST."""
    arbol = ast.parse(src)
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre:
            return ast.get_source_segment(src, n)
    return None


# ── I/O bloqueante dentro del event loop ─────────────────────────────────────
# Una función `async def` que llama a market_data.get_quote() SIN to_thread bloquea el
# hilo del event loop mientras dura la red. No ralentiza solo a quien pidió: congela el
# servidor entero para todos. /quote además lo sondea cada pestaña abierta cada 30 s
# como respaldo del WebSocket, así que era el peor sitio posible para tenerlo.

_ENDPOINTS_BLOQUEANTES = [
    ("get_quote", "market_data.get_quote"),
    ("get_chart", "market_data.get_stock_data"),
    ("get_news", "market_data.get_news"),
]


@pytest.mark.parametrize("funcion,llamada", _ENDPOINTS_BLOQUEANTES)
def test_los_endpoints_async_no_hacen_red_en_el_event_loop(funcion, llamada):
    cuerpo = _cuerpo_funcion(_fuente("server.py"), funcion)
    assert cuerpo, f"no se encontró {funcion} en server.py"
    assert llamada in cuerpo, f"el test apunta a una llamada que ya no existe: {llamada}"
    for linea in cuerpo.splitlines():
        if llamada in linea and not linea.strip().startswith("#"):
            assert "to_thread" in linea or "run_in_executor" in linea, (
                f"{funcion}: '{llamada}' se llama directa dentro de un async def; "
                "bloquea el event loop y congela el servidor para todos los usuarios"
            )


# ── Fuentes lentas sin caché ─────────────────────────────────────────────────

def test_el_volume_profile_del_dashboard_va_cacheado():
    """365 días de agregados de Polygon (~900 ms) para un histograma que apenas cambia
    de un día para otro. Iba sin caché: se pagaba en cada cambio de ticker."""
    src = _fuente("server.py")
    assert "def _cached_vp" in src, "falta el envoltorio con caché del volume profile"

    # Toda llamada cruda a get_volume_profile debe estar dentro de _cached_vp. Única
    # excepción: el endpoint de diagnóstico, que mide el coste REAL de la fuente y con
    # caché mediría siempre 0 ms. Se localizan por línea para que, si aparece un tercer
    # sitio (ya pasó: había dos, no uno), el test lo cace.
    cuerpo_envoltorio = _cuerpo_funcion(src, "_cached_vp") or ""
    crudas = [
        (i + 1, ln.strip())
        for i, ln in enumerate(src.splitlines())
        if "polygon_data.get_volume_profile" in ln
        and not ln.strip().startswith("#")
        and ln not in cuerpo_envoltorio
        and "_medir" not in ln
    ]
    assert not crudas, f"get_volume_profile sin caché en {crudas}"


def test_el_dashboard_lee_la_cache_de_noticias():
    """El dashboard ESCRIBE news:{sym} al terminar, pero no la leía: cada carga volvía a
    descargar las noticias que ya tenía guardadas 30 minutos."""
    src = _fuente("server.py")
    assert "def _cached_news" in src
    assert '_timed("news", _cached_news' in src


# ── Fallos no cacheados ──────────────────────────────────────────────────────

def test_los_fallos_de_finnhub_se_recuerdan_un_rato():
    """Un símbolo que Finnhub no cubre devolvía None sin guardar nada: pagaba limitador +
    red en CADA carga, para siempre, gastando cuota que necesitan los que sí funcionan."""
    import external_data as ed
    assert ed._TTL_FALLO <= 900, "recordar un fallo más de 15 min retrasa la recuperación"

    ed._ext_cache.clear()
    assert not ed._fallo_reciente("trends:XYZ")
    ed._marcar_fallo("trends:XYZ")
    assert ed._fallo_reciente("trends:XYZ")
    # No debe contaminar el valor real: son claves distintas.
    _, hit = ed._ext_cache_get("trends:XYZ", 14400)
    assert not hit


# ── Cotización de índices/futuros ────────────────────────────────────────────

def test_get_index_quote_va_acotado():
    """Se quedó fuera del arreglo de los 8,7 s y usa el mismo fast_info/.info sin tope.
    Alimenta la barra de futuros de la portada: es lo primero que bloquearía al entrar."""
    cuerpo = _cuerpo_funcion(_fuente("market_data.py"), "get_index_quote")
    assert cuerpo, "no se encontró get_index_quote"
    assert "_call_with_timeout" in cuerpo, "fast_info/.info sin tope: puede colgarse"
    for linea in cuerpo.splitlines():
        if "fast_info" in linea and not linea.strip().startswith("#"):
            assert "def _leer" in cuerpo, "fast_info debe usarse dentro de _leer()"


# ── Fuga de conexiones WebSocket ─────────────────────────────────────────────

def test_el_websocket_se_desregistra_siempre():
    """Con try/except, una cancelación de tarea (apagado, timeout) NO ejecuta el except:
    el símbolo se queda con un suscriptor fantasma sondeando cuota para nadie."""
    src = _fuente("server.py")
    arbol = ast.parse(src)
    encontrado = False
    for n in ast.walk(arbol):
        if not isinstance(n, ast.Try):
            continue
        texto = ast.get_source_segment(src, n) or ""
        if "_quote_manager.disconnect" not in texto:
            continue
        encontrado = True
        assert n.finalbody, (
            "la baja del WebSocket debe ir en un finally, no solo en un except")
    assert encontrado, "no se encontró el try que da de baja el WebSocket"
