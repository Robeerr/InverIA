"""Los desgloses entre reinicios: que sobrevivan, y que su ausencia no rompa nada.

EL CASO REAL QUE MOTIVA ESTE FICHERO

Al desplegar el endpoint del desglose, el snapshot que habia en Mongo lo habia escrito el
codigo ANTERIOR, asi que no tiene la clave `desgloses`. La pregunta no es academica: de
ella depende que el desglose este disponible al arrancar o que devuelva 404 hasta el
siguiente escaneo.

Se prueba con un Mongo de mentira porque lo que se protege es la FORMA de la hidratacion
—que lea la clave correcta, que aguante su ausencia, que no toque `data`— y eso no
depende de tener una base de datos delante.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import opportunities as op  # noqa: E402


class _Coleccion:
    """Lo minimo de `db.scan_snapshots` que usa la hidratacion: un `find_one` y un
    `replace_one` que apunta lo que se le pidio guardar."""

    def __init__(self, docs):
        self.docs = docs
        self.guardado = []

    async def find_one(self, filtro):
        return self.docs.get(filtro["_id"])

    async def replace_one(self, filtro, doc, upsert=False):
        self.guardado.append(doc)
        self.docs[filtro["_id"]] = doc


class _Db:
    def __init__(self, docs):
        self.scan_snapshots = _Coleccion(docs)


@pytest.fixture
def cache_limpia(monkeypatch):
    limpia = {"data": None, "ts": None, "desgloses": {}}
    monkeypatch.setattr(op, "_screener_cache", limpia)
    monkeypatch.setattr(op, "_cache", {"data": None, "ts": None})
    return limpia


def _hidratar(docs):
    asyncio.run(op.load_snapshots_into_cache())


DESGLOSE = {"bruto": 80.5, "multiplicador": 0.55, "motivo_multiplicador": "cae en el año",
            "recortado": False, "componentes": [{"clave": "x", "etiqueta": "X",
                                                 "puntos": 10, "maximo": 10}]}
DATA = {"generated_at": "2026-08-11T13:00:00+00:00",
        "results": [{"symbol": "NVDA", "potential_score": 44.3}]}


# ── 1 · Snapshot CON desgloses ──────────────────────────────────────────────
def test_un_snapshot_con_desgloses_se_restaura(cache_limpia, monkeypatch):
    docs = {"screener": {"_id": "screener", "data": DATA, "saved_at": None,
                         "desgloses": {"NVDA": DESGLOSE}}}
    monkeypatch.setattr(op, "_db", _Db(docs))
    _hidratar(docs)
    assert cache_limpia["desgloses"] == {"NVDA": DESGLOSE}
    assert cache_limpia["data"] == DATA


def test_y_el_endpoint_lo_encuentra_tras_la_hidratacion(cache_limpia, monkeypatch):
    """La cadena entera: snapshot -> cache -> `desglose_de`. Sin escaneo de por medio."""
    docs = {"screener": {"_id": "screener", "data": DATA, "saved_at": None,
                         "desgloses": {"NVDA": DESGLOSE}}}
    monkeypatch.setattr(op, "_db", _Db(docs))
    _hidratar(docs)
    servido = op.desglose_de("NVDA")
    assert servido is not None
    assert servido["score"] == 44.3
    assert servido["desglose"] == DESGLOSE


# ── 2 · Snapshot ANTIGUO, sin la clave ──────────────────────────────────────
def test_un_snapshot_sin_desgloses_no_revienta(cache_limpia, monkeypatch):
    """El caso real del despliegue: el snapshot lo escribio el codigo anterior."""
    docs = {"screener": {"_id": "screener", "data": DATA, "saved_at": None}}
    monkeypatch.setattr(op, "_db", _Db(docs))
    _hidratar(docs)
    assert cache_limpia["desgloses"] == {}
    # Y los resultados SI se restauran: la pantalla de Oportunidades funciona igual.
    assert cache_limpia["data"] == DATA


def test_sin_desgloses_el_endpoint_dice_que_no_hay_en_vez_de_calcular(cache_limpia, monkeypatch):
    docs = {"screener": {"_id": "screener", "data": DATA, "saved_at": None}}
    monkeypatch.setattr(op, "_db", _Db(docs))

    def prohibido(*a, **kw):
        raise AssertionError("ha recalculado en vez de devolver None")
    monkeypatch.setattr(op, "_potential_score_detalle", prohibido)

    _hidratar(docs)
    assert op.desglose_de("NVDA") is None


def test_un_desglose_vacio_se_trata_como_ausente(cache_limpia, monkeypatch):
    """`{}` es falsy: la guarda lo deja pasar y la cache conserva su valor inicial en vez
    de sobrescribirse con nada."""
    docs = {"screener": {"_id": "screener", "data": DATA, "saved_at": None, "desgloses": {}}}
    monkeypatch.setattr(op, "_db", _Db(docs))
    cache_limpia["desgloses"] = {"YA": DESGLOSE}
    _hidratar(docs)
    assert cache_limpia["desgloses"] == {"YA": DESGLOSE}


def test_la_hidratacion_del_daily_no_toca_los_desgloses(cache_limpia, monkeypatch):
    """Los dos snapshots se recorren en el mismo bucle. La guarda por `kind` evita que el
    de oportunidades diarias pise la clave del screener."""
    docs = {"daily": {"_id": "daily", "data": {"x": 1}, "saved_at": None,
                      "desgloses": {"NO": "deberia colarse"}},
            "screener": {"_id": "screener", "data": DATA, "saved_at": None,
                         "desgloses": {"NVDA": DESGLOSE}}}
    monkeypatch.setattr(op, "_db", _Db(docs))
    _hidratar(docs)
    assert cache_limpia["desgloses"] == {"NVDA": DESGLOSE}


# ── 3 · El proximo escaneo SI los escribe ───────────────────────────────────
def test_el_escaneo_guarda_en_cache_antes_de_persistir():
    """El orden importa: si el guardado en Mongo fallara, la cache en memoria ya los
    tiene y el endpoint funciona igual hasta el proximo reinicio."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "opportunities.py"),
               encoding="utf-8").read()
    i_cache = src.index('_screener_cache["desgloses"] = desgloses')
    i_snap = src.index('extra={"desgloses": desgloses}')
    assert i_cache < i_snap


def test_el_snapshot_guarda_los_desgloses_fuera_de_data(cache_limpia, monkeypatch):
    """`data` es lo que /opportunities/screener devuelve entero: todo lo que se meta ahi
    engorda esa respuesta."""
    docs = {}
    db = _Db(docs)
    monkeypatch.setattr(op, "_db", db)
    asyncio.run(op._save_snapshot("screener", DATA, extra={"desgloses": {"NVDA": DESGLOSE}}))
    guardado = db.scan_snapshots.guardado[0]
    assert guardado["desgloses"] == {"NVDA": DESGLOSE}
    assert "desgloses" not in guardado["data"]


def test_save_snapshot_sigue_funcionando_sin_extra(cache_limpia, monkeypatch):
    """El snapshot de `daily` lo llama sin `extra`: el parametro es opcional."""
    db = _Db({})
    monkeypatch.setattr(op, "_db", db)
    asyncio.run(op._save_snapshot("daily", {"x": 1}))
    assert db.scan_snapshots.guardado[0]["data"] == {"x": 1}


def test_el_desglose_persistido_va_y_vuelve_igual(cache_limpia, monkeypatch):
    """Ida y vuelta completa: se guarda, se reinicia, se hidrata y el endpoint lo sirve."""
    docs = {}
    monkeypatch.setattr(op, "_db", _Db(docs))
    asyncio.run(op._save_snapshot("screener", DATA, extra={"desgloses": {"NVDA": DESGLOSE}}))

    cache_limpia["data"] = None
    cache_limpia["desgloses"] = {}
    _hidratar(docs)

    assert op.desglose_de("NVDA")["desglose"] == DESGLOSE


# ── 4 · El endpoint lee EXACTAMENTE esa cache ───────────────────────────────
def test_desglose_de_lee_la_cache_del_modulo(cache_limpia):
    """Se mete a mano en la cache y el lector lo ve: no hay copia intermedia ni otra
    fuente de la que pudiera estar leyendo."""
    cache_limpia["data"] = DATA
    cache_limpia["desgloses"] = {"NVDA": DESGLOSE}
    assert op.desglose_de("NVDA")["desglose"] == DESGLOSE
    del cache_limpia["desgloses"]["NVDA"]
    assert op.desglose_de("NVDA") is None


def test_el_endpoint_del_servidor_llama_a_ese_lector():
    src = open(os.path.join(os.path.dirname(__file__), "..", "server.py"),
               encoding="utf-8").read()
    ini = src.index('@api_router.get("/opportunities/score/{symbol}")')
    cuerpo = src[ini:src.index("\n@api_router", ini + 10)]
    assert "opportunities.desglose_de(symbol)" in cuerpo


def test_el_placeholder_de_warming_no_pisa_la_cache():
    """`scan_growth_screener` DEVUELVE el placeholder pero no lo guarda. Si lo guardara,
    `results` quedaria vacio y el desglose no encontraria su fila."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "opportunities.py"),
               encoding="utf-8").read()
    ini = src.index("async def scan_growth_screener")
    cuerpo = src[ini:src.index("\nasync def _analyze_one", ini)]
    assert '"status": "warming"' in cuerpo
    assert '_screener_cache["data"] =' not in cuerpo
