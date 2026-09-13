"""La foto diaria: el dato que mañana ya no se puede tomar.

LO QUE ESTE FICHERO TIENE QUE DEMOSTRAR

Dos cosas, y la segunda es la que de verdad importa:

  · que la foto recoge lo que el sistema veía, sin inventarse nada donde faltaba un dato;
  · que la PRIMERA foto del día manda y nadie la reescribe después.

Lo segundo es la diferencia entre un dataset y una trampa. Si la foto de la tarde pisara
la de la mañana, al cruzar una decisión de las 9:00 con «el dato del día» estaríamos
mirando información que en ese momento no existía. Es data leakage, y del que no se ve:
el estudio saldría bien y estaría mal.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import mercado_registro as mr
from test_tesis import dash


# ── Mongo falso ──────────────────────────────────────────────────────────────
#
# Implementa `upsert` con `$setOnInsert`, que es justo la semántica de la que depende
# «la primera del día manda». Un falso que ignorara el `$setOnInsert` y escribiera
# siempre dejaría pasar el bug que estos tests existen para impedir.

class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, campo, orden=1):
        self.docs.sort(key=lambda d: d.get(campo) or "", reverse=orden < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n=None):
        return list(self.docs[:n] if n else self.docs)


class _Resultado:
    def __init__(self, upserted_id=None):
        self.upserted_id = upserted_id


class _Col:
    def __init__(self):
        self.docs = []

    def _casa(self, doc, filtro):
        return all(doc.get(k) == v for k, v in (filtro or {}).items())

    def find(self, filtro=None, proyeccion=None):
        return _Cursor([d for d in self.docs if self._casa(d, filtro)])

    async def count_documents(self, filtro=None):
        return len([d for d in self.docs if self._casa(d, filtro)])

    async def distinct(self, campo):
        return list({d.get(campo) for d in self.docs})

    async def update_one(self, filtro, update, upsert=False):
        existente = next((d for d in self.docs if self._casa(d, filtro)), None)
        if existente is not None:
            for k, v in (update.get("$set") or {}).items():
                existente[k] = v
            return _Resultado()                    # `$setOnInsert` NO toca lo que ya hay
        if not upsert:
            return _Resultado()
        doc = {**(update.get("$setOnInsert") or {}), **(update.get("$set") or {})}
        self.docs.append(doc)
        return _Resultado(upserted_id="nuevo")


class _DB:
    def __init__(self):
        self._cols = {}

    def __getitem__(self, nombre):
        return self._cols.setdefault(nombre, _Col())

    def __getattr__(self, nombre):
        return self[nombre]


# ── La foto ──────────────────────────────────────────────────────────────────

def test_la_foto_recoge_los_insumos_de_decision():
    f = mr.foto(dash())
    assert f["symbol"] == "AAPL"
    assert f["precio"] == 213.64
    assert f["tecnico"]["adx"] == 31.0
    assert f["tecnico"]["regimen"] == "tendencia_alcista"
    assert f["zona_de_compra"]["etiqueta"] == "NIVEL 1"
    assert f["zona_de_compra"]["razones"] == ["SMA200", "Fibonacci 38,2%", "VWAP anclado"]
    assert f["consenso"]["nota"] == 78
    assert f["origen"]["fuente"] == "yfinance" and f["origen"]["degradado"] is False
    assert f["foto_v"] == mr.FOTO_V


def test_la_foto_NO_lleva_ningun_total():
    """`separacion.py` existe para impedir que calidad, valoración y tendencia se fundan
    en un número donde un 60 puede ser «cara pero líder» o «barata pero muerta». Una foto
    con un total heredaría ese defecto y además lo congelaría en el histórico."""
    plano = str(mr.foto(dash()))
    for prohibido in ("total", "score_total", "puntuacion", "potential_score"):
        assert prohibido not in plano


def test_un_dato_AUSENTE_se_anota_como_ausente_y_no_como_cero():
    """`or 0` convierte «no lo sabíamos» en «valía cero», y después no hay forma de
    distinguirlos. Es la misma regla que defiende `calibracion.py`."""
    d = dash()
    d["indicators"].pop("rsi")
    d["analyst"] = {}
    f = mr.foto(d)
    assert f["tecnico"]["rsi"] is None
    assert f["consenso"]["nota"] is None


def test_un_NaN_no_es_un_numero():
    d = dash()
    d["indicators"]["rsi"] = float("nan")
    assert mr.foto(d)["tecnico"]["rsi"] is None


def test_un_BOOLEANO_no_se_cuela_como_numero():
    d = dash()
    d["indicators"]["atr_pct"] = True
    assert mr.foto(d)["tecnico"]["atr_pct"] is None


def test_sin_dashboard_no_hay_foto():
    assert mr.foto(None) is None
    assert mr.foto({}) is None
    assert mr.foto({"quote": {"price": 10}}) is None        # sin símbolo, no se anota


def test_una_accion_sin_zonas_de_compra_no_inventa_ninguna():
    d = dash()
    d["buy_levels"] = []
    z = mr.foto(d)["zona_de_compra"]
    assert z["precio"] is None and z["razones"] == [] and z["cuantas_zonas"] == 0


# ── La primera del día manda ─────────────────────────────────────────────────

def _guardar(db, d=None, cuando=None, huella=None):
    return asyncio.run(mr.guardar(db, d if d is not None else dash(),
                                  tesis_huella=huella, cuando=cuando))


def test_la_primera_foto_del_dia_se_anota():
    db = _DB()
    r = _guardar(db, cuando="2026-09-14T09:00:00Z", huella="abc123")
    assert r["accion"] == "creada" and r["dia"] == "2026-09-14"
    doc = db[mr.COLECCION].docs[0]
    assert doc["tesis_huella"] == "abc123"
    assert doc["tomada_en"] == "2026-09-14T09:00:00Z"


def test_la_SEGUNDA_foto_del_mismo_dia_NO_pisa_a_la_primera():
    """El test que justifica el módulo. Si la de la tarde reescribiera la de la mañana,
    cruzar una decisión de las 9:00 con «el dato del día» sería mirar el futuro."""
    db = _DB()
    _guardar(db, cuando="2026-09-14T09:00:00Z")

    tarde = dash()
    tarde["quote"]["price"] = 240.00
    tarde["indicators"]["regime"]["regime"] = "tendencia_bajista"
    r = _guardar(db, tarde, cuando="2026-09-14T21:00:00Z")

    assert r["accion"] == "ya_estaba"
    assert len(db[mr.COLECCION].docs) == 1
    doc = db[mr.COLECCION].docs[0]
    assert doc["precio"] == 213.64                          # la de la mañana, intacta
    assert doc["tecnico"]["regimen"] == "tendencia_alcista"
    assert doc["tomada_en"] == "2026-09-14T09:00:00Z"


def test_al_dia_siguiente_SI_hay_foto_nueva():
    db = _DB()
    _guardar(db, cuando="2026-09-14T09:00:00Z")
    r = _guardar(db, cuando="2026-09-15T09:00:00Z")
    assert r["accion"] == "creada"
    assert sorted(d["dia"] for d in db[mr.COLECCION].docs) == ["2026-09-14", "2026-09-15"]


def test_un_fallo_de_MONGO_no_lanza():
    """Cuelga del camino que construye el dashboard: no puede dejar sin página a quien
    abre una acción."""
    db = _DB()
    db[mr.COLECCION].update_one = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caído"))
    r = _guardar(db)
    assert r["accion"] == "nada" and r["motivo"] == "error"


def test_un_dashboard_vacio_no_escribe_nada():
    db = _DB()
    assert asyncio.run(mr.guardar(db, None))["accion"] == "nada"
    assert db[mr.COLECCION].docs == []


# ── Consulta ─────────────────────────────────────────────────────────────────

def test_el_historial_va_del_dia_mas_RECIENTE_al_mas_antiguo():
    db = _DB()
    for dia in ("2026-09-14", "2026-09-15", "2026-09-16"):
        _guardar(db, cuando=f"{dia}T09:00:00Z")
    filas = asyncio.run(mr.historial(db, "AAPL"))
    assert [f["dia"] for f in filas] == ["2026-09-16", "2026-09-15", "2026-09-14"]


def test_la_cobertura_cuenta_DIAS_no_conceptos():
    """La única métrica honesta mientras no haya muestra. «Hemos ingerido 700
    documentos» no dice nada sobre si el sistema piensa mejor; los días de historia sí,
    porque son exactamente lo que limita qué se puede estudiar."""
    db = _DB()
    _guardar(db, cuando="2026-09-14T09:00:00Z")
    _guardar(db, cuando="2026-09-15T09:00:00Z")
    c = asyncio.run(mr.cobertura(db))
    assert c == {"fotos": 2, "dias": 2, "simbolos": 1,
                 "desde": "2026-09-14", "hasta": "2026-09-15", "foto_v": mr.FOTO_V}


@pytest.mark.parametrize("symbol", ["", None, "   "])
def test_un_simbolo_vacio_no_devuelve_historial(symbol):
    assert asyncio.run(mr.historial(_DB(), symbol)) == []
