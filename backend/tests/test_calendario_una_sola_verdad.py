"""El calendario de resultados se descarga UNA vez, no dos.

QUÉ ESTABA PASANDO

Dos consumidores pedían el mismo calendario a Finnhub por su cuenta:

  · `server.earnings_calendar` → 60 días, caché propia de 30 min, alimenta la portada
    (`hoy.tarjeta_resultados`) y la pantalla de calendario;
  · `intel_earnings.recolectar` → 21 días, cada 6 h, alimenta el radar de Intelligence.

El propio docstring de `intel_earnings` lo reconocía: «es la misma llamada que ya hace el
calendario». Dos descargas del mismo dato y dos cuotas gastadas.

PERO EL PROBLEMA GORDO NO ERA LA CUOTA

Eran dos cachés que envejecen distinto. La portada podía decir que una empresa presenta
el día 4 y el radar el día 6, con los dos «en lo cierto» según su copia, y sin que nada
pareciera roto. Un sistema que se contradice consigo mismo sobre un hecho —cuándo
presenta una empresa— no es un sistema del que uno se pueda fiar.

POR QUÉ LA CONVERGENCIA ES TAN BARATA

Porque la llamada de Finnhub es MASIVA por rango de fechas y el filtro por símbolo va en
cliente. La ventana de 60 días ya contenía la de 21: solo hacía falta que alguien se
diera cuenta y recortara en vez de volver a bajar.

Los dos consumidores no cambian ni una línea: `finnhub_earnings_calendar` mantiene su
firma y la forma de su respuesta. Lo único que desaparece es la segunda descarga.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

import pytest

import external_data as ed


class _Respuesta:
    def __init__(self, items):
        self.status_code = 200
        self._items = items

    def json(self):
        return {"earningsCalendar": list(self._items)}


@pytest.fixture(autouse=True)
def _sin_caches(monkeypatch):
    """Caché vacía y clave falsa en cada test: si no, el primero contamina al resto."""
    # `_ext_cache`, en minúsculas. La primera versión parcheaba `_EXT_CACHE`
    # con `raising=False`, así que no parcheaba nada y los tests se
    # contaminaban entre sí sin avisar.
    monkeypatch.setattr(ed, "_ext_cache", {})
    monkeypatch.setattr(ed, "_finnhub_key", lambda: "clave-de-prueba")
    yield


def _fila(sym, fecha, **extra):
    base = {"symbol": sym, "date": fecha, "hour": "amc", "epsEstimate": 1.0,
            "epsActual": None, "revenueEstimate": None, "revenueActual": None,
            "quarter": 1, "year": 2026}
    base.update(extra)
    return base


def _espia(monkeypatch, filas):
    """Cuenta cuántas veces se pide el calendario a Finnhub."""
    llamadas = []

    def falso(ruta, params=None, timeout=None):
        llamadas.append((ruta, dict(params or {})))
        return _Respuesta(filas)

    monkeypatch.setattr(ed, "_finnhub_get", falso)
    return llamadas


def test_dos_consumidores_con_VENTANAS_DISTINTAS_descargan_UNA_vez(monkeypatch):
    """El test que justifica el cambio: 21 días y 60 días, una sola llamada."""
    from datetime import datetime, timedelta
    hoy = datetime.utcnow().date()
    filas = [_fila("NVDA", (hoy + timedelta(days=5)).isoformat()),
             _fila("AAPL", (hoy + timedelta(days=40)).isoformat())]
    llamadas = _espia(monkeypatch, filas)

    ed.finnhub_earnings_calendar(21, {"NVDA", "AAPL"})     # el radar
    ed.finnhub_earnings_calendar(60, {"NVDA"})             # la portada

    assert len(llamadas) == 1, f"se ha bajado {len(llamadas)} veces"


def test_la_descarga_pide_SIEMPRE_la_ventana_ancha(monkeypatch):
    """Aunque quien llame pida 21. Si bajara la corta, el consumidor de 60 se quedaría
    sin la mitad del calendario o tendría que volver a bajar."""
    llamadas = _espia(monkeypatch, [])
    ed.finnhub_earnings_calendar(21, {"NVDA"})
    from datetime import datetime, timedelta
    esperado = (datetime.utcnow().date()
                + timedelta(days=ed.DIAS_CALENDARIO)).isoformat()
    assert llamadas[0][1]["to"] == esperado


def test_cada_consumidor_RECORTA_su_ventana(monkeypatch):
    """La caché guarda 60 días. Quien pide 21 no puede recibir resultados a 40 días vista
    y creer que son inminentes — sería peor que la duplicación que esto arregla."""
    from datetime import datetime, timedelta
    hoy = datetime.utcnow().date()
    cerca = (hoy + timedelta(days=5)).isoformat()
    lejos = (hoy + timedelta(days=40)).isoformat()
    _espia(monkeypatch, [_fila("NVDA", cerca), _fila("AAPL", lejos)])

    corto = ed.finnhub_earnings_calendar(21, {"NVDA", "AAPL"})
    largo = ed.finnhub_earnings_calendar(60, {"NVDA", "AAPL"})

    assert [x["symbol"] for x in corto["items"]] == ["NVDA"]
    assert {x["symbol"] for x in largo["items"]} == {"NVDA", "AAPL"}


def test_NO_se_pregunta_una_a_una_por_quien_simplemente_no_presenta_pronto(monkeypatch):
    """Una empresa que presenta dentro de cuarenta días no «falta» del lote cuando se
    piden veintiuno. Preguntando por ella se gastaba una petición por símbolo para volver
    a saber lo mismo.

    Distinguirlo solo es posible desde que se baja la ventana ancha: antes, un símbolo
    ausente podía serlo porque Finnhub lo truncó o porque no presenta pronto, y las dos
    cosas se veían igual.
    """
    from datetime import datetime, timedelta
    hoy = datetime.utcnow().date()
    llamadas = _espia(monkeypatch, [
        _fila("NVDA", (hoy + timedelta(days=5)).isoformat()),
        _fila("AAPL", (hoy + timedelta(days=40)).isoformat()),   # fuera de los 21
    ])
    r = ed.finnhub_earnings_calendar(21, {"NVDA", "AAPL"})
    assert [x["symbol"] for x in r["items"]] == ["NVDA"]
    assert len(llamadas) == 1, "se ha preguntado por AAPL una a una sin necesidad"


def test_SI_se_rellena_a_quien_falta_de_la_ventana_ancha(monkeypatch):
    """El lote gratuito de Finnhub se trunca y deja fuera acciones reales. Ese relleno
    tiene que seguir funcionando: es lo que hacía que NFLX no apareciera nunca."""
    from datetime import datetime, timedelta
    hoy = datetime.utcnow().date()
    pedidos = []

    def _uno(sym, desde, hasta, key):
        pedidos.append(sym)
        return [{"symbol": sym, "date": (hoy + timedelta(days=2)).isoformat(),
                 "hour": "amc", "eps_estimate": None, "eps_actual": None,
                 "revenue_estimate": None, "revenue_actual": None,
                 "quarter": 1, "year": 2026}]

    monkeypatch.setattr(ed, "_fetch_earnings_for_symbol", _uno)
    _espia(monkeypatch, [_fila("NVDA", (hoy + timedelta(days=5)).isoformat())])
    r = ed.finnhub_earnings_calendar(21, {"NVDA", "NFLX"})
    assert pedidos == ["NFLX"]
    assert {x["symbol"] for x in r["items"]} == {"NVDA", "NFLX"}


def test_el_filtro_por_SIMBOLO_sigue_funcionando(monkeypatch):
    from datetime import datetime, timedelta
    fecha = (datetime.utcnow().date() + timedelta(days=3)).isoformat()
    _espia(monkeypatch, [_fila("NVDA", fecha), _fila("AAPL", fecha),
                         _fila("TSLA", fecha)])
    r = ed.finnhub_earnings_calendar(21, {"NVDA", "TSLA"})
    assert {x["symbol"] for x in r["items"]} == {"NVDA", "TSLA"}


def test_la_FORMA_de_la_respuesta_no_ha_cambiado(monkeypatch):
    """Sus dos consumidores leen `items`, `date`, `symbol`, `hour`, `eps_estimate`… Si
    esto cambiara, la convergencia habría roto justo lo que venía a unificar."""
    from datetime import datetime, timedelta
    fecha = (datetime.utcnow().date() + timedelta(days=3)).isoformat()
    _espia(monkeypatch, [_fila("NVDA", fecha, epsEstimate=1.23, epsActual=1.31)])
    r = ed.finnhub_earnings_calendar(21, {"NVDA"})

    assert set(r) >= {"items", "from", "to"}
    it = r["items"][0]
    assert set(it) == {"symbol", "date", "hour", "eps_estimate", "eps_actual",
                       "revenue_estimate", "revenue_actual", "quarter", "year"}
    assert it["eps_estimate"] == 1.23 and it["eps_actual"] == 1.31


def test_sin_CLAVE_no_se_toca_la_red(monkeypatch):
    """Misma regla que el connector de la SEC: sin credencial, cero peticiones."""
    monkeypatch.setattr(ed, "_finnhub_key", lambda: None)

    def prohibido(*a, **k):
        raise AssertionError("se ha llamado a Finnhub sin clave")

    monkeypatch.setattr(ed, "_finnhub_get", prohibido)
    assert ed.finnhub_earnings_calendar(21, {"NVDA"}) is None


def test_si_finnhub_FALLA_se_devuelve_None_y_no_una_lista_vacia(monkeypatch):
    """`intel_earnings` distingue «no hay resultados próximos» de «la fuente está caída»
    para decidir el backoff. Una lista vacía haría las dos cosas indistinguibles."""
    def rompe(*a, **k):
        raise RuntimeError("timeout")

    monkeypatch.setattr(ed, "_finnhub_get", rompe)
    assert ed.finnhub_earnings_calendar(21, {"NVDA"}) is None


def test_un_ERROR_HTTP_tampoco_se_cachea(monkeypatch):
    """Cachear un fallo dejaría media hora sin calendario a los dos consumidores."""
    class _Mala:
        status_code = 500

        def json(self):
            return {}

    llamadas = []

    def falso(*a, **k):
        llamadas.append(1)
        return _Mala()

    monkeypatch.setattr(ed, "_finnhub_get", falso)
    assert ed.finnhub_earnings_calendar(21, {"NVDA"}) is None
    assert ed.finnhub_earnings_calendar(21, {"NVDA"}) is None
    assert len(llamadas) == 2, "el fallo se ha cacheado"


def test_SOLO_UNA_funcion_baja_el_LOTE_del_calendario():
    """El invariante de fondo. Si mañana alguien vuelve a pedir el lote por su cuenta,
    reaparecen las dos verdades que esto arregla.

    La primera versión de este test exigía UNA sola aparición del endpoint en el módulo,
    y hay dos legítimas: el lote y el relleno por símbolo, que pide el calendario de UNA
    acción cuando Finnhub la deja fuera del lote. Son cosas distintas y las dos tienen
    que existir; lo que no puede haber es un segundo sitio bajando el lote entero.
    """
    import ast
    import inspect
    arbol = ast.parse(inspect.getsource(ed))
    bajan = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.FunctionDef):
            continue
        for hijo in ast.walk(nodo):
            if (isinstance(hijo, ast.Call) and isinstance(hijo.func, ast.Name)
                    and hijo.func.id == "_finnhub_get"
                    and hijo.args and isinstance(hijo.args[0], ast.Constant)
                    and hijo.args[0].value == "/calendar/earnings"):
                bajan.append(nodo.name)
    assert sorted(set(bajan)) == ["_calendario_completo", "_fetch_earnings_for_symbol"], bajan


def test_los_DOS_consumidores_siguen_llamando_a_la_misma_puerta():
    """`server` e `intel_earnings` pasan por `finnhub_earnings_calendar`. Si uno de los
    dos se saltara esa puerta, volveríamos a tener dos verdades."""
    import re
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fichero in ("server.py", "intel_earnings.py"):
        with open(os.path.join(raiz, fichero), encoding="utf-8") as f:
            src = f.read()
        assert "finnhub_earnings_calendar" in src, fichero
        # `_finnhub_get` y no la ruta: `server` expone un endpoint PROPIO que se llama
        # «/calendar/earnings» y buscar la cadena daba un falso positivo sobre su propia
        # URL. Lo que delata una descarga es llamar al cliente de Finnhub.
        assert "_finnhub_get" not in src, f"{fichero} baja el calendario por su cuenta"


def test_la_EXCURSION_ADVERSA_se_mide_hasta_la_RESOLUCION():
    """Una caída posterior al rebote no habría saltado ningún stop de esa operación.
    Contarla haría parecer peligrosos stops que nunca corrieron riesgo."""
    import inspect
    import backtest
    fuente = inspect.getsource(backtest)
    assert "tramo_low = fwd_low[touch_at:resuelto_en + 1]" in fuente
    assert '"mae_atr": mae_atr,' in fuente


def test_la_PROFUNDIDAD_se_mide_con_la_formula_de_produccion():
    """`levels_engine.indices_del_plan_detallado` mete una zona en el plan si su precio
    queda por encima de `precio × (1 − MAX_PLAN_DEPTH)`. La magnitud que ese 0,30
    gobierna es ésta, y medir otra parecida daría un número que no se puede llevar al
    parámetro — que es el único motivo de medirlo."""
    import inspect
    import backtest
    import levels_engine
    assert '"depth": round((current_price - L) / current_price, 4),' in \
        inspect.getsource(backtest)
    # Y el filtro de producción sigue comparando contra ese mismo suelo.
    assert "suelo = precio * (1 - max_depth)" in inspect.getsource(levels_engine)
