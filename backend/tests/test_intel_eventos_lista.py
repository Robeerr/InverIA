"""Un evento grave no puede quedar fuera de la lista por llegar antes que cincuenta leves.

El 02-11-2026 el 8-K de AVGO, Importante y recién investigado, no aparecía en
Inteligencia: la lista pedía los 50 eventos más recientes, y en cinco días habían entrado
más de 50 avisos de nivel Atención. Estaba en Mongo; la pantalla no llegaba a pedirlo.

Ahora `/intelligence/eventos` sirve los `limite` más recientes y, además, los Importantes
y Críticos visibles de los últimos `DIAS_GRAVES_EN_LISTA` días. Estos tests fijan las dos
mitades: que el grave antiguo vuelve, y que lo demás —la ventana, las etapas, el filtro
por valor, la auditoría por etapa— sigue igual.

Se llama a la función del endpoint directamente, con un Mongo falso en memoria.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import intel_eventos as ev


# ── El Mongo falso ───────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, campo, sentido):
        self._docs = sorted(self._docs, key=lambda d: str(d.get(campo) or ""),
                            reverse=sentido < 0)
        return self

    async def to_list(self, n):
        return [dict(d) for d in self._docs[:n]]


def _casa(doc, filtro):
    """Igualdad, `$in` y `$gte`: los que usa el endpoint. Cualquier otro operador revienta,
    para que el falso no dé por buena una consulta que no sabe evaluar."""
    for campo, valor in filtro.items():
        actual = doc.get(campo)
        if isinstance(valor, dict):
            if not {"$in", "$gte"} >= set(valor):
                raise NotImplementedError(f"el Mongo falso no entiende {set(valor)}")
            if "$in" in valor and actual not in valor["$in"]:
                return False
            if "$gte" in valor and not (actual is not None and actual >= valor["$gte"]):
                return False
        elif actual != valor:
            return False
    return True


class _Coleccion:
    def __init__(self, docs):
        self.docs = docs

    def find(self, filtro, proyeccion=None):
        return _Cursor([d for d in self.docs if _casa(d, filtro)])


class _DB:
    def __init__(self, docs):
        self.intel_eventos = _Coleccion(docs)


def _hace(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


def _evento(id_, recibido, nivel=ev.WATCH, etapa=ev.SIGNIFICATIVO, symbol="NBIS"):
    return {"id": id_, "symbol": symbol, "titulo": f"evento {id_}", "nivel_alerta": nivel,
            "etapa": etapa, "recibido_en": recibido, "fuente": "sec", "tier": 1}


@pytest.fixture
def server(monkeypatch):
    import server as srv
    return srv


def _pedir(server, monkeypatch, docs, **kw):
    monkeypatch.setattr(server, "db", _DB(docs))
    r = asyncio.run(server.intelligence_eventos(_user="rober", **{"limite": 50, **kw}))
    return [e["id"] for e in r["eventos"]]


def _avisos_recientes(n=60):
    """Más de 50 avisos de Atención, todos de las últimas horas: los que empujaban fuera."""
    return [_evento(f"leve{i}", _hace(minutes=i + 1)) for i in range(n)]


# ── 1 · El caso real ─────────────────────────────────────────────────────────

def test_el_grave_de_hace_5_dias_vuelve_aunque_haya_50_leves_mas_nuevos(server, monkeypatch):
    avgo = _evento("avgo", _hace(days=5), nivel=ev.IMPORTANT, etapa=ev.INVESTIGADO,
                   symbol="AVGO")
    ids = _pedir(server, monkeypatch, _avisos_recientes() + [avgo])
    assert "avgo" in ids
    assert len(ids) == 51                      # los 50 recientes, más él
    assert ids[-1] == "avgo"                   # y en su sitio: es el más antiguo


def test_tambien_los_criticos_y_los_que_siguen_pendientes(server, monkeypatch):
    critico = _evento("critico", _hace(days=3), nivel=ev.CRITICAL)
    pendiente = _evento("pendiente", _hace(days=4), nivel=ev.IMPORTANT)
    ids = _pedir(server, monkeypatch, _avisos_recientes() + [critico, pendiente])
    assert {"critico", "pendiente"} <= set(ids)


# ── 2 · Lo que NO cambia ─────────────────────────────────────────────────────

def test_un_grave_de_hace_MAS_de_la_ventana_no_vuelve(server, monkeypatch):
    """La pantalla enseña siempre las filas que interrumpen. Sin ventana, la lista se
    llenaría de asuntos de hace meses."""
    viejo = _evento("viejo", _hace(days=server.DIAS_GRAVES_EN_LISTA + 1),
                    nivel=ev.IMPORTANT)
    ids = _pedir(server, monkeypatch, _avisos_recientes() + [viejo])
    assert "viejo" not in ids and len(ids) == 50


def test_un_grave_DESCARTADO_no_se_cuela(server, monkeypatch):
    """Solo etapas visibles: un descartado se audita en el diagnóstico, no aquí."""
    descartado = _evento("descartado", _hace(days=2), nivel=ev.IMPORTANT,
                         etapa=ev.DESCARTADO)
    ids = _pedir(server, monkeypatch, _avisos_recientes() + [descartado])
    assert "descartado" not in ids


def test_sin_repetidos_cuando_el_grave_ya_era_reciente(server, monkeypatch):
    reciente = _evento("mrvl", _hace(minutes=0), nivel=ev.IMPORTANT, etapa=ev.INVESTIGADO)
    ids = _pedir(server, monkeypatch, _avisos_recientes() + [reciente])
    assert ids.count("mrvl") == 1 and ids[0] == "mrvl"


def test_el_filtro_por_valor_se_respeta_tambien_en_los_graves(server, monkeypatch):
    otro = _evento("otro", _hace(days=5), nivel=ev.IMPORTANT, symbol="AVGO")
    ids = _pedir(server, monkeypatch, _avisos_recientes() + [otro], symbol="NBIS")
    assert "otro" not in ids


def test_con_etapa_se_sirve_EXACTAMENTE_lo_pedido(server, monkeypatch):
    """Pedir una etapa es auditar: ahí no se añade nada."""
    leves = [_evento(f"inv{i}", _hace(minutes=i + 1), etapa=ev.INVESTIGADO)
             for i in range(60)]
    grave = _evento("grave", _hace(days=5), nivel=ev.IMPORTANT, etapa=ev.INVESTIGADO)
    ids = _pedir(server, monkeypatch, leves + [grave], etapa=ev.INVESTIGADO)
    assert len(ids) == 50 and "grave" not in ids


# ── 3 · La pieza pura ────────────────────────────────────────────────────────

def test_juntar_quita_repetidos_y_ordena_del_mas_reciente_al_mas_antiguo():
    a = {"id": "a", "recibido_en": "2026-11-02T10:00:00+00:00"}
    b = {"id": "b", "recibido_en": "2026-10-28T10:00:00+00:00"}
    c = {"id": "c", "recibido_en": "2026-11-01T10:00:00+00:00"}
    juntos = ev.juntar_con_graves([a, c], [b, a])
    assert [e["id"] for e in juntos] == ["a", "c", "b"]


def test_juntar_no_rompe_con_vacios():
    assert ev.juntar_con_graves(None, None) == []
    assert ev.juntar_con_graves([], [{"id": "x", "recibido_en": "1"}]) == [
        {"id": "x", "recibido_en": "1"}]
