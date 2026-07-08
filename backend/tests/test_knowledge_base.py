"""Tests del CEREBRO (knowledge_base): acumula el método de las newsletters y lo
deduplica por tema para inyectarlo en el motor de análisis.

Ejecutar:  cd backend && pytest tests/ -v
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import knowledge_base as kb  # noqa: E402


class _FakeColl:
    def __init__(self):
        self.docs = {}

    def find(self, q, proj=None):
        data = sorted(self.docs.values(), key=lambda d: d.get("refuerzos", 0), reverse=True)

        class _C:
            def sort(self, *a):
                return self

            async def to_list(self, n):
                return data[:n]

        return _C()

    async def find_one(self, q):
        return self.docs.get(q["_key"])

    async def insert_one(self, doc):
        self.docs[doc["_key"]] = doc

    async def update_one(self, q, upd):
        d = self.docs[q["_key"]]
        d.update(upd.get("$set", {}))
        for k, v in upd.get("$inc", {}).items():
            d[k] = d.get(k, 0) + v


class _FakeDB:
    def __init__(self):
        self.investing_knowledge = _FakeColl()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _reset():
    kb._DIGEST = ""


def test_dedup_por_tema_incrementa_refuerzos():
    _reset()
    db = _FakeDB()
    _run(kb.add_learnings(db, [{"tema": "Rotación de sectores", "categoria": "sectores",
                                "principio": "El dinero rota del hardware IA al software"}], "A"))
    _run(kb.add_learnings(db, [{"tema": "rotacion de sectores", "categoria": "sectores",
                                "principio": "El dinero rota del hardware de IA hacia el software claramente"}], "B"))
    # Mismo tema (normalizado) → un solo doc con refuerzos=2 y el principio más largo.
    assert len(db.investing_knowledge.docs) == 1
    doc = next(iter(db.investing_knowledge.docs.values()))
    assert doc["refuerzos"] == 2
    assert "claramente" in doc["principio"]


def test_temas_distintos_se_guardan_separados():
    _reset()
    db = _FakeDB()
    _run(kb.add_learnings(db, [
        {"tema": "Rotación", "categoria": "sectores", "principio": "rota el dinero"},
        {"tema": "Stops", "categoria": "riesgo", "principio": "limita al 5% por posición"},
    ], "A"))
    assert len(db.investing_knowledge.docs) == 2


def test_categoria_invalida_cae_en_metodo():
    _reset()
    db = _FakeDB()
    _run(kb.add_learnings(db, [{"tema": "X", "categoria": "inventada", "principio": "algo"}], "A"))
    doc = next(iter(db.investing_knowledge.docs.values()))
    assert doc["categoria"] == "método"


def test_ignora_aprendizajes_incompletos():
    _reset()
    db = _FakeDB()
    n = _run(kb.add_learnings(db, [{"tema": "", "principio": "sin tema"},
                                   {"tema": "T", "principio": ""}], "A"))
    assert n == 0
    assert len(db.investing_knowledge.docs) == 0


def test_digest_vacio_sin_conocimiento():
    _reset()
    assert kb.digest_for_prompt() == ""


def test_digest_incluye_principios_tras_aprender():
    _reset()
    db = _FakeDB()
    _run(kb.add_learnings(db, [{"tema": "Stops", "categoria": "riesgo",
                                "principio": "limita al 5% por posición"}], "A"))
    d = kb.digest_for_prompt()
    assert "CONOCIMIENTO ACUMULADO" in d
    assert "5%" in d
