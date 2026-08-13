"""La portada no descarga dos años de velas para tickers que no van a salir en pantalla.

EL PROBLEMA MEDIDO

`/hoy` pedía la tendencia de TODOS los tickers mencionados en 14 días de newsletters, sin
tope y sin filtro. Con 120 tickers son 120 descargas de histórico, en un batch que además
iba DETRÁS del `gather` — así que su latencia se sumaba a la de `hot_signals` en vez de
solaparse. Medido con 5 hilos (1 CPU en Render) y 1,2 s por lectura: 39,8 s.

Y la mayoría de esas lecturas no podían cambiar nada. `hoy.tarjeta_confluencia` solo emite
con ACUERDO o CHOQUE, y los dos exigen al menos `MIN_FUENTES` fuentes distintas y un tono
que no sea mixto. Un ticker mencionado una sola vez, o con opiniones encontradas, sale
NEUTRAL o MIXTO diga lo que diga la tendencia: se descargaba su histórico para tirarlo.

CÓMO SE ACOTA SIN DUPLICAR LA REGLA

`confluencia.puede_cruzarse` no reescribe la condición: pregunta a `clasificar` por todos
los estados de tendencia posibles y responde si alguno daría ACUERDO o CHOQUE. Si mañana
cambia la clasificación, esto la sigue sin tocarse. Es la diferencia entre acotar y
adivinar.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import confluencia  # noqa: E402
import tendencia  # noqa: E402

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _codigo(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    return re.sub(r"#.*", "", src)


SRV = _codigo(os.path.join(_BACKEND, "server.py"))


def _cuerpo(nombre: str, src: str = None) -> str:
    src = SRV if src is None else src
    ini = src.index(f"def {nombre}(")
    resto = src[ini:]
    m = re.search(r"\n(?:def |async def |@api_router|@app\.)", resto[1:])
    return resto[: m.start() + 1] if m else resto


def _fuente(nombre, n, pos, neg):
    return {"fuentes": [f"S{i}" for i in range(n)], "positivos": pos, "negativos": neg,
            "menciones": max(n, pos + neg), "nombre": nombre}


# ── La condición se deriva, no se copia ─────────────────────────────────────

def test_puede_cruzarse_delega_en_clasificar():
    """No es una segunda regla: es la primera, consultada. Si `clasificar` cambiara y esto
    fuera una copia, el filtro empezaría a descartar tickers que sí debían salir."""
    codigo = _codigo(os.path.join(_BACKEND, "confluencia.py"))
    cuerpo = _cuerpo("puede_cruzarse", codigo)
    assert "clasificar(" in cuerpo
    assert "tendencia.ESTADOS" in cuerpo
    # Y NO reimplementa la condición por su cuenta.
    for copiado in ("MIN_FUENTES", "tono_de_fuentes", "FAVORABLE", "DESFAVORABLE"):
        assert copiado not in cuerpo, copiado


def test_lo_que_se_descarta_no_podia_dar_tarjeta_con_NINGUNA_tendencia():
    """El invariante que hace seguro el filtro, comprobado por fuerza bruta sobre todas
    las combinaciones pequeñas y todos los estados de tendencia."""
    for n in range(0, 5):
        for pos in range(0, 4):
            for neg in range(0, 4):
                alcanzables = {confluencia.clasificar(n, pos, neg, t)
                               for t in tendencia.ESTADOS}
                puede = confluencia.puede_cruzarse(n, pos, neg)
                cruza = bool(alcanzables & {"ACUERDO", "CHOQUE"})
                assert puede is cruza, (n, pos, neg, alcanzables)


def test_los_casos_que_se_van_son_los_que_esperamos():
    assert confluencia.puede_cruzarse(1, 1, 0) is False   # una sola fuente
    assert confluencia.puede_cruzarse(3, 2, 1) is False   # tono mixto
    assert confluencia.puede_cruzarse(3, 0, 0) is False   # menciones sin polaridad
    assert confluencia.puede_cruzarse(0, 0, 0) is False   # sin fuentes
    assert confluencia.puede_cruzarse(2, 2, 0) is True    # favorable con bastantes
    assert confluencia.puede_cruzarse(2, 0, 2) is True    # desfavorable con bastantes


# ── Dobles para el camino de /hoy ───────────────────────────────────────────

class _Cursor:
    def __init__(s, d): s.d = d
    async def to_list(s, n): return list(s.d)[:n]
    def sort(s, *a, **k): return s
    def limit(s, n): return s


class _Col:
    def __init__(s, d, nombre, registro):
        s.d, s.n, s.reg = d, nombre, registro

    def find(s, *a, **k):
        return _Cursor(s.d)

    async def find_one(s, *a, **k):
        return None

    async def insert_one(s, *a, **k):
        s.reg.append(("insert_one", s.n))

    async def update_one(s, *a, **k):
        s.reg.append(("update_one", s.n))


class _DB:
    def __init__(s, entradas=()):
        s.escrituras = []
        s.signal_entries = _Col(list(entradas), "signal_entries", s.escrituras)
        s.alert_history = _Col([], "alert_history", s.escrituras)
        s.newsletter_summaries = _Col([], "newsletter_summaries", s.escrituras)


@pytest.fixture
def portada(monkeypatch):
    """Monta `/hoy` con todo lo caro sustituido, salvo lo que se está midiendo."""
    import server

    estado = {"consultas": [], "orden": [], "tendencia": "ALCISTA", "fuentes": {},
              "entradas": []}

    def _tendencia_de(sym):
        estado["consultas"].append(sym)
        return estado["tendencia"]

    async def _fuentes(days=14):
        estado["orden"].append("fuentes:inicio")
        return estado["fuentes"]

    async def _resumen(_user=None):
        return {"posiciones": []}

    async def _cal(**k):
        return {"items": []}

    async def _news(a, b):
        return []

    monkeypatch.setattr(server.market_data, "tendencia_de", _tendencia_de)
    monkeypatch.setattr(server, "_fuentes_por_ticker", _fuentes)
    monkeypatch.setattr(server, "resumen_cartera", _resumen)
    monkeypatch.setattr(server, "earnings_calendar", _cal)
    monkeypatch.setattr(server, "_newsletters_recientes", _news)
    server._invalidar_signals_hot()
    server._cache._store.clear()
    return server, estado


async def _abrir(server, estado, monkeypatch):
    db = _DB(estado["entradas"])
    monkeypatch.setattr(server, "db", db)
    server._invalidar_signals_hot()
    r = await server.dashboard_hoy(_user="test")
    return r, db


def _confluencias(respuesta):
    """Las tarjetas que produce `tarjeta_confluencia`, que son de DOS tipos.

    ACUERDO sale como «confluencia» y CHOQUE como «divergencia»: son la misma función y
    la misma decisión, con dos caras. Filtrar solo por «confluencia» dejaría fuera
    justo la mitad que más importa."""
    return {t["symbol"]: t for t in (respuesta.get("importa_hoy") or [])
            if t.get("tipo") in ("confluencia", "divergencia")}


# ── A · No se consulta lo que no puede salir ────────────────────────────────

@pytest.mark.anyio
async def test_no_se_consulta_la_tendencia_de_fuentes_sin_futuro(portada, monkeypatch):
    server, estado = portada
    estado["fuentes"] = {
        "UNA": _fuente("UNA", 1, 1, 0),      # una sola fuente
        "MIX": _fuente("MIX", 3, 2, 1),      # tono mixto
        "MUDA": _fuente("MUDA", 3, 0, 0),    # menciones sin polaridad
    }
    await _abrir(server, estado, monkeypatch)
    assert estado["consultas"] == []


@pytest.mark.anyio
async def test_si_se_consulta_la_tendencia_de_las_que_si_pueden(portada, monkeypatch):
    server, estado = portada
    estado["fuentes"] = {"BUENA": _fuente("BUENA", 2, 2, 0),
                         "UNA": _fuente("UNA", 1, 1, 0)}
    await _abrir(server, estado, monkeypatch)
    assert estado["consultas"] == ["BUENA"]


@pytest.mark.anyio
async def test_el_recorte_es_grande_en_un_escenario_realista(portada, monkeypatch):
    """La mayoría de menciones de una newsletter son de una sola fuente."""
    server, estado = portada
    estado["fuentes"] = {}
    for i in range(100):
        if i % 10 == 0:
            estado["fuentes"][f"T{i:03d}"] = _fuente(f"T{i:03d}", 2, 2, 0)
        else:
            estado["fuentes"][f"T{i:03d}"] = _fuente(f"T{i:03d}", 1, 1, 0)
    await _abrir(server, estado, monkeypatch)
    assert len(estado["consultas"]) == 10, len(estado["consultas"])


# ── B · Las tarjetas no cambian ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_las_tarjetas_de_confluencia_son_identicas(portada, monkeypatch):
    """Equivalencia contra la referencia: lo que saldría preguntando por TODOS."""
    import hoy
    server, estado = portada
    estado["tendencia"] = "BAJISTA"
    estado["fuentes"] = {
        "CHOCA": _fuente("CHOCA", 3, 3, 0),   # favorable + no elegible -> CHOQUE
        "UNA": _fuente("UNA", 1, 1, 0),
        "MIX": _fuente("MIX", 4, 2, 2),
        "MUDA": _fuente("MUDA", 2, 0, 0),
        "NEG": _fuente("NEG", 3, 0, 3),       # desfavorable + no elegible -> NEUTRAL
    }
    r, _ = await _abrir(server, estado, monkeypatch)
    obtenidas = _confluencias(r)

    esperadas = {}
    for tk, f in estado["fuentes"].items():
        est = confluencia.clasificar(len(f["fuentes"]), f["positivos"], f["negativos"],
                                     "BAJISTA")
        t = hoy.tarjeta_confluencia(tk, f["nombre"], est, f, tiene_posicion=False)
        if t:
            esperadas[tk] = t
    assert set(obtenidas) == set(esperadas) == {"CHOCA"}
    for tk in esperadas:
        assert obtenidas[tk]["que_pasa"] == esperadas[tk]["que_pasa"]
        assert obtenidas[tk]["urgencia"] == esperadas[tk]["urgencia"]


@pytest.mark.anyio
async def test_el_acuerdo_tambien_sobrevive(portada, monkeypatch):
    server, estado = portada
    estado["tendencia"] = "ALCISTA"
    estado["fuentes"] = {"OK": _fuente("OK", 3, 3, 0), "UNA": _fuente("UNA", 1, 1, 0)}
    r, _ = await _abrir(server, estado, monkeypatch)
    assert set(_confluencias(r)) == {"OK"}


@pytest.mark.anyio
async def test_una_tendencia_no_verificable_sigue_sin_producir_tarjeta(portada, monkeypatch):
    """Fallo cerrado, intacto: SIN_DATOS da INSUFICIENTE y `tarjeta_confluencia` calla."""
    server, estado = portada
    estado["tendencia"] = "SIN_DATOS"
    estado["fuentes"] = {"OK": _fuente("OK", 3, 3, 0)}
    r, _ = await _abrir(server, estado, monkeypatch)
    assert _confluencias(r) == {}
    assert estado["consultas"] == ["OK"], "se pregunta igual: el filtro es previo a saberlo"


# ── C · Las dos ramas caras se solapan ──────────────────────────────────────

def test_el_batch_de_fuentes_vive_dentro_del_gather():
    """B: estaba DETRÁS del `gather`, así que su latencia se sumaba a la de
    `hot_signals` en vez de solaparse. Se comprueba sobre la estructura, porque un
    cronómetro aquí mediría sobre todo los dobles."""
    cuerpo = _cuerpo("dashboard_hoy")
    cabecera = cuerpo[:cuerpo.index("return_exceptions=True")]
    assert "_fuentes_con_tendencia" in cabecera
    # Y ya no queda un segundo `gather` de tendencias colgando detrás.
    cola = cuerpo[cuerpo.index("return_exceptions=True"):]
    assert "asyncio.to_thread(market_data.tendencia_de" not in cola
    # Por límite de palabra: `tendencias_fuentes` —el mapa YA resuelto que el cuerpo
    # consume— contiene la vieja `tendencias_f` como subcadena, y buscarla a pelo daría
    # un falso positivo sobre el código correcto.
    assert not re.search(r"\btendencias_f\b", cola)


@pytest.mark.anyio
async def test_fuentes_y_hot_corren_a_la_vez(portada, monkeypatch):
    """Medición real de solape: con las dos ramas tardando lo mismo, el total tiene que
    parecerse al máximo y no a la suma."""
    import asyncio
    import time
    server, estado = portada
    RETRASO = 0.25

    def _lento(sym):
        estado["consultas"].append(sym)
        time.sleep(RETRASO)
        return "ALCISTA"

    monkeypatch.setattr(server.market_data, "tendencia_de", _lento)
    estado["fuentes"] = {f"F{i}": _fuente(f"F{i}", 2, 2, 0) for i in range(4)}
    estado["entradas"] = [{"symbol": f"C{i}", "name": "x", "active": True,
                           "last_price": 100.0, "nivel1": 99.0} for i in range(4)]

    t0 = time.time()
    await _abrir(server, estado, monkeypatch)
    total = time.time() - t0

    # 4 de fuentes (todas cruzables) + 4 de niveles (todas dentro del ranking).
    assert len(estado["consultas"]) == 8
    # Las cuatro de FUENTES se resuelven dentro del `gather`, en una sola tanda. Las de
    # niveles ya no pueden ir ahí: rankear exige tener antes las tarjetas, y el ranking es
    # justamente lo que evita resolver la tendencia de las que no salen. Así que el suelo
    # son dos tandas, no una — y esa segunda tanda es la que el ranking mantiene pequeña.
    assert total < RETRASO * 4, f"{total:.2f}s: más de dos tandas, algo va en serie de más"


# ── D · Fronteras y escrituras ──────────────────────────────────────────────

def test_no_se_tocan_las_fronteras_del_veto():
    for fichero in ("tendencia.py", "estado_accion.py", "veto_compra.py",
                    "signal_table.py", "cartera_api.py"):
        codigo = _codigo(os.path.join(_BACKEND, fichero))
        assert "puede_cruzarse" not in codigo, fichero
        assert "_fuentes_con_tendencia" not in codigo, fichero
    assert '"NO_COMPRAR"' not in SRV
    op = _codigo(os.path.join(_BACKEND, "opportunities.py"))
    assert "_potential_score" in op
    assert "/opportunities/score/{symbol}" in SRV


def test_confluencia_sigue_sin_numeros_nuevos():
    """El test de arquitectura de `confluencia.py` exige que los únicos números sean los
    del recuento de fuentes. Acotar no puede colar un umbral por la puerta de atrás."""
    codigo = _codigo(os.path.join(_BACKEND, "confluencia.py"))
    numeros = set(re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)", codigo))
    assert numeros <= {"0", "1", "2"}, sorted(numeros)


def test_hoy_py_no_se_ha_tocado():
    codigo = _codigo(os.path.join(_BACKEND, "hoy.py"))
    for ajeno in ("puede_cruzarse", "tendencia_de", "_fuentes_con_tendencia"):
        assert ajeno not in codigo, ajeno


@pytest.mark.anyio
async def test_abrir_la_portada_no_escribe_nada(portada, monkeypatch):
    server, estado = portada
    estado["fuentes"] = {"OK": _fuente("OK", 3, 3, 0), "UNA": _fuente("UNA", 1, 1, 0)}
    estado["entradas"] = [{"symbol": "C1", "name": "x", "active": True,
                           "last_price": 100.0, "nivel1": 99.0}]
    _, db = await _abrir(server, estado, monkeypatch)
    assert db.escrituras == []


# ── Opción 1 · Rankear antes de vetar ───────────────────────────────────────
#
# La urgencia de una tarjeta de nivel no depende de la tendencia: sale de la distancia, de
# `fuerza` (que `_dashboard_cacheado` sirve de caché, sin red) y de `tiene_posicion`. Así
# que se puede saber QUÉ tarjetas van a salir antes de pagar ninguna lectura de histórico,
# y resolver la tendencia solo de esas.
#
# Medido antes del cambio: 39 candidatos dentro del 4% -> 31 lecturas -> 5 tarjetas.

def _niveles(n, pct_max=4.0):
    """n entradas repartidas dentro del umbral, todas de COMPRA."""
    return [{"symbol": f"C{i:03d}", "name": f"C{i:03d}", "active": True,
             "last_price": 100.0,
             "nivel1": round(100 / (1 + ((i + 1) * pct_max / n) / 100), 4)}
            for i in range(n)]


def _tarjetas_nivel(respuesta):
    return [t for t in (respuesta.get("importa_hoy") or []) if t.get("tipo") == "nivel"]


@pytest.mark.anyio
async def test_39_candidatos_solo_consultan_lo_que_sale(portada, monkeypatch):
    """El caso medido en la auditoría: 31 lecturas para pintar 5 tarjetas."""
    import hoy
    server, estado = portada
    estado["entradas"] = _niveles(39)
    r, _ = await _abrir(server, estado, monkeypatch)
    assert len(estado["consultas"]) <= hoy.LIMITE_POR_DEFECTO, estado["consultas"]
    assert len(_tarjetas_nivel(r)) == hoy.LIMITE_POR_DEFECTO


@pytest.mark.anyio
async def test_un_candidato_descartado_por_el_ranking_no_consulta(portada, monkeypatch):
    """El invariante literal: quien no sale, no cuesta."""
    server, estado = portada
    estado["entradas"] = _niveles(39)
    r, _ = await _abrir(server, estado, monkeypatch)
    salen = {t["symbol"] for t in _tarjetas_nivel(r)}
    for sym in estado["consultas"]:
        assert sym in salen, f"{sym} se consultó y no sale en pantalla"


@pytest.mark.anyio
async def test_la_seleccion_es_identica_ignorando_action(portada, monkeypatch):
    """Requisito 6: consultar la tendencia no puede mover el ranking. Se compara la
    selección con TODO vetado contra la selección sin nada vetado."""
    server, estado = portada
    estado["entradas"] = _niveles(39)

    estado["tendencia"] = "BAJISTA"
    r_vetado, _ = await _abrir(server, estado, monkeypatch)
    estado["consultas"].clear()
    estado["tendencia"] = "ALCISTA"
    r_libre, _ = await _abrir(server, estado, monkeypatch)

    clave = lambda t: (t["symbol"], t["urgencia"], t["que_pasa"])  # noqa: E731
    assert [clave(t) for t in _tarjetas_nivel(r_vetado)] == \
           [clave(t) for t in _tarjetas_nivel(r_libre)]


@pytest.mark.anyio
async def test_una_tarjeta_final_vetada_sale_sin_compra_y_con_motivo(portada, monkeypatch):
    import estado_accion
    server, estado = portada
    estado["tendencia"] = "BAJISTA"
    estado["entradas"] = _niveles(6)
    r, _ = await _abrir(server, estado, monkeypatch)
    tarjetas = _tarjetas_nivel(r)
    assert tarjetas
    for t in tarjetas:
        assert t["datos"]["accion"] is None
        assert "sería una" not in t["que_vigilar"]
    # El motivo viaja en el candidato, que es lo que `hot` marca.
    server._invalidar_signals_hot()
    cands = await server._candidatos_calientes(200, 4.0)
    await server._vetar_calientes(cands)
    assert cands[0]["veto_motivo"] == estado_accion.evaluar("BAJISTA")["motivo"]


@pytest.mark.anyio
async def test_alcista_e_indefinida_conservan_su_comportamiento(portada, monkeypatch):
    server, estado = portada
    for tend in ("ALCISTA", "INDEFINIDA"):
        estado["tendencia"] = tend
        estado["entradas"] = _niveles(6)
        r, _ = await _abrir(server, estado, monkeypatch)
        for t in _tarjetas_nivel(r):
            assert t["datos"]["accion"] == "COMPRA", tend
            assert "sería una compra" in t["que_vigilar"], tend


@pytest.mark.anyio
async def test_el_fallo_cerrado_sigue_en_pie_en_la_portada(portada, monkeypatch):
    """SIN_DATOS, excepciones y basura: ninguna produce una compra en pantalla."""
    server, estado = portada
    for valor in ("SIN_DATOS", RuntimeError("caído"), TimeoutError(), None):
        def _t(sym, v=valor):
            estado["consultas"].append(sym)
            if isinstance(v, Exception):
                raise v
            return v
        monkeypatch.setattr(server.market_data, "tendencia_de", _t)
        estado["entradas"] = _niveles(4)
        r, _ = await _abrir(server, estado, monkeypatch)
        for t in _tarjetas_nivel(r):
            assert t["datos"]["accion"] is None, valor


@pytest.mark.anyio
async def test_el_endpoint_publico_sigue_vetando_todo(portada, monkeypatch):
    """Requisito 7: el contrato de `/signals/hot` no se relaja. Quien lo llame directo
    recibe TODAS las filas vetadas, no solo las que la portada pinta."""
    server, estado = portada
    estado["tendencia"] = "BAJISTA"
    # 3,5% y no 4,0%: el último de la serie caería justo en el borde del umbral y el
    # redondeo del cálculo lo deja fuera. Eso se prueba aparte; aquí estorba.
    estado["entradas"] = _niveles(20, pct_max=3.5)
    monkeypatch.setattr(server, "db", _DB(estado["entradas"]))
    server._invalidar_signals_hot()
    filas = await server.hot_signals(limit=200, max_pct=4.0, _user="directo")
    assert len(filas) == 20
    assert all(f["action"] is None for f in filas)
    assert all(f["vetado_por_tendencia"] for f in filas)
    assert len(estado["consultas"]) == 20


@pytest.mark.anyio
async def test_la_portada_no_escribe_nada_con_niveles(portada, monkeypatch):
    server, estado = portada
    estado["entradas"] = _niveles(39)
    _, db = await _abrir(server, estado, monkeypatch)
    assert db.escrituras == []


def test_el_calculo_de_candidatos_no_toca_la_red():
    calc = _cuerpo("_candidatos_calientes")
    for ajeno in ("tendencia_de", "veto_compra", "estado_accion", "asyncio.gather"):
        assert ajeno not in calc, ajeno


def test_la_portada_rankea_antes_de_vetar():
    """El orden ES la corrección. Si el veto subiera por delante del `sort`, los tests de
    salida seguirían pasando y el coste volvería a ser el de antes."""
    helper = _cuerpo("_tarjetas_de_nivel")
    assert helper.index("vivas.sort(") < helper.index("_vetar_calientes")
    assert "vivas[:limite]" in helper
    assert '"NO_COMPRAR"' not in helper


def test_una_tendencia_desconocida_se_trata_como_no_verificable():
    """EL HUECO QUE ESTE TEST DOCUMENTABA, YA CERRADO.

    `estado_accion.evaluar` mapea a SIN_DATOS cualquier estado que no conozca —o sea, LO
    RECONOCE como no comprobable— y devuelve EN_SEGUIMIENTO, que no veta. Pero
    `no_verificable` solo miraba `""` y SIN_DATOS, así que una etiqueta desconocida caía
    entre las dos capas y salía como COMPRA.

    No era alcanzable —`tendencia_de` solo devuelve los cuatro estados de
    `tendencia.ESTADOS`— pero una capa defensiva que depende de que nadie añada un estado
    nuevo no está defendiendo: está esperando.
    """
    import estado_accion
    import tendencia
    import veto_compra
    desconocido = "ESTADO_QUE_NADIE_HA_MAPEADO"
    assert desconocido not in tendencia.ESTADOS
    assert veto_compra.no_verificable(desconocido) is True
    # Y las dos capas dicen ahora lo mismo sobre él.
    assert estado_accion.evaluar(desconocido)["tendencia"] == "SIN_DATOS"


def test_los_cuatro_estados_conocidos_no_se_vuelven_no_verificables():
    """Cerrar el hueco no puede convertir en «no lo sé» lo que sí se comprobó."""
    import tendencia
    import veto_compra
    for estado in tendencia.ESTADOS:
        esperado = (estado == veto_compra.TENDENCIA_NO_VERIFICABLE)
        assert veto_compra.no_verificable(estado) is esperado, estado


def test_el_modulo_pregunta_por_los_estados_en_vez_de_copiarlos():
    """Si aquí hubiera una tupla propia con los cuatro nombres, añadir un estado nuevo en
    `tendencia.py` volvería a abrir el mismo hueco sin que fallara nada."""
    codigo = _codigo(os.path.join(_BACKEND, "veto_compra.py"))
    assert "tendencia.ESTADOS" in codigo
    for copiado in ("ALCISTA", "BAJISTA", "INDEFINIDA"):
        assert copiado not in codigo, copiado


@pytest.mark.anyio
async def test_una_tendencia_desconocida_no_produce_compra_en_la_portada(portada, monkeypatch):
    """El efecto de extremo a extremo, que es lo que de verdad importaba."""
    server, estado = portada
    estado["tendencia"] = "ESTADO_QUE_NADIE_HA_MAPEADO"
    estado["entradas"] = _niveles(4)
    r, _ = await _abrir(server, estado, monkeypatch)
    tarjetas = _tarjetas_nivel(r)
    assert tarjetas
    for t in tarjetas:
        assert t["datos"]["accion"] is None
