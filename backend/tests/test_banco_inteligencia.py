"""El banco de pruebas de la Inteligencia y la exportación de investigaciones.

QUÉ PROTEGE ESTE FICHERO

  1. El banco se congela UNA vez, con exactamente los casos de PROMPT_V = 2, y sin tocar
     los eventos de producción. Si no son 20, o si algún documento enviado no se puede
     re-descargar, no se guarda nada.
  2. Lo que no se registró en su día queda como ausente: no se inventa. Una confianza
     guardada de 0 no se da por declarada.
  3. La entrada se reconstruye con las funciones de producción y se contrasta con lo
     registrado; con los topes de producción, el banco produce la misma entrada.
  4. Ejecutar una versión sobre el banco no escribe en los eventos ni en el contador.
  5. La exportación es de solo lectura.

Mongo y la SEC son dobles en memoria. Los documentos son inventados para el test.
"""
import asyncio
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import banco_inteligencia as banco
import intel_eventos as ev
import intel_investigacion as inv


# ── Mongo falso, con lo que usa el banco ─────────────────────────────────────

def _valor(doc, ruta):
    for parte in ruta.split("."):
        if not isinstance(doc, dict):
            return None
        doc = doc.get(parte)
    return doc


def _casa(doc, filtro):
    for campo, cond in (filtro or {}).items():
        actual = _valor(doc, campo)
        if isinstance(cond, dict):
            if not {"$ne", "$in"} >= set(cond):
                raise NotImplementedError(cond)
            if "$ne" in cond and actual == cond["$ne"]:
                return False
            if "$in" in cond and actual not in cond["$in"]:
                return False
        elif actual != cond:
            return False
    return True


def _quitar(doc, ruta):
    cabeza, _, resto = ruta.partition(".")
    if isinstance(doc, list):
        for d in doc:
            _quitar(d, ruta)
    elif isinstance(doc, dict) and cabeza in doc:
        if resto:
            _quitar(doc[cabeza], resto)
        else:
            del doc[cabeza]


def _proyectar(doc, proy):
    doc = copy.deepcopy(doc)
    for ruta, v in (proy or {}).items():
        if v == 0:
            _quitar(doc, ruta)
    return doc


class _Cursor:
    def __init__(self, docs, proy):
        self.docs, self.proy = docs, proy

    def sort(self, campo, sentido):
        self.docs = sorted(self.docs, key=lambda d: str(_valor(d, campo) or ""),
                           reverse=sentido < 0)
        return self

    async def to_list(self, n):
        return [_proyectar(d, self.proy) for d in self.docs[:n]]


class _Col:
    def __init__(self):
        self.docs, self.escrituras = [], 0

    def find(self, filtro=None, proy=None):
        return _Cursor([d for d in self.docs if _casa(d, filtro)], proy)

    async def find_one(self, filtro=None, proy=None):
        for d in self.docs:
            if _casa(d, filtro):
                return _proyectar(d, proy)
        return None

    async def insert_one(self, doc):
        self.escrituras += 1
        self.docs.append(copy.deepcopy(doc))


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, n):
        return self._c.setdefault(n, _Col())

    def __getattr__(self, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return self[n]


# ── Los 20 casos sintéticos ──────────────────────────────────────────────────

def _html(t):
    return f"<html><body><p>{t}</p></body></html>"


def _caso(i, con_anexos, prompt_v=2, confianza=95):
    cik = str(1000 + i)
    acc = f"{i:018d}"
    carpeta = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"
    principal = carpeta + "doc8k.htm"
    guiones = inv.accession_con_guiones(acc)
    filas = [("8-K", "doc8k.htm"), ("EX-99.1", "ex991.htm"), ("EX-2.1", "ex21.htm")]
    indice = ("<html><body><div>Accession No. <strong>" + guiones + "</strong></div><table>"
              "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th>"
              "<th>Size</th></tr>" + "".join(
                  f'<tr><td>{n}</td><td>d</td><td><a href="/Archives/edgar/data/{cik}/{acc}/'
                  f'{nombre}">{nombre}</a></td><td>{tipo}</td><td>1</td></tr>'
                  for n, (tipo, nombre) in enumerate(filas, 1)) + "</table></body></html>")
    web = {principal: _html(f"FORM 8-K caso {i}. Revenue of $1,{i:03d} million. " + "x" * 50),
           carpeta + guiones + "-index.htm": indice,
           carpeta + "ex991.htm": _html(f"Press release {i}: dividend of $0.{i:02d} per share."),
           carpeta + "ex21.htm": _html(f"AGREEMENT AND PLAN OF MERGER number {i}.")}
    evento = {"id": f"sec:8-K:{acc}", "symbol": f"S{i}", "titulo": f"8-K · caso {i}",
              "url": principal, "recibido_en": f"2026-10-{i + 1:02d}T10:00:00+00:00",
              "investigado_en": f"2026-10-{i + 1:02d}T11:00:00+00:00",
              "etapa": ev.INVESTIGADO,
              "crudo": {"formulario": "8-K", "suceso": "8-K", "accession": acc, "cik": cik,
                        "fecha_registro": "2026-10-01"},
              "investigacion": {"hay_informacion": True, "resumen": f"Caso {i}.",
                                "hechos": [f"Ingresos de $1.{i:03d} millones."],
                                "implicaciones": [], "incertidumbres": [], "fuente": "8-K",
                                "confianza": confianza, "modelo": "gemini-2.5-flash",
                                "prompt_v": prompt_v}}
    if con_anexos:
        # Lo que se registró en su día, calculado con las funciones de producción.
        texto = inv.texto_del_documento(web[principal], maximo=inv.MAX_BYTES)
        anexo = {"tipo": "EX-99.1", "documento": "ex991.htm", "url": carpeta + "ex991.htm",
                 "texto": inv.texto_del_documento(web[carpeta + "ex991.htm"],
                                                  maximo=inv.MAX_BYTES)}
        evento["documentos_enviados"] = inv.ensamblar_envio(texto, evento, [anexo])["documentos"]
    return evento, web


@pytest.fixture
def mundo(monkeypatch):
    db, web = _DB(), {}
    for i in range(1, 21):
        evento, paginas = _caso(i, con_anexos=i > 8, confianza=0 if i == 20 else 95)
        db.intel_eventos.docs.append(evento)
        web.update(paginas)
    viejo, paginas = _caso(30, con_anexos=False, prompt_v=1)     # PROMPT_V = 1: fuera
    db.intel_eventos.docs.append(viejo)
    pedidas = []

    async def sec(url):
        pedidas.append(url)
        if url not in web:
            return {"ok": False, "http": 404, "bytes": 0, "ms": 1, "error": "404"}
        return {"ok": True, "http": 200, "bytes": len(web[url]), "ms": 1, "error": None,
                "html": web[url]}
    monkeypatch.setattr(inv, "descargar_documento", sec)
    monkeypatch.setattr(banco, "PAUSA_ENTRE_CASOS_S", 0)
    return db, web, pedidas


# ── 1 · Congelar ─────────────────────────────────────────────────────────────

def test_congela_los_20_y_NO_toca_los_eventos(mundo):
    db, _, _ = mundo
    antes = copy.deepcopy(db.intel_eventos.docs)
    r = asyncio.run(banco.congelar(db))
    assert r["ok"] is True and r["manifiesto"]["casos"] == 20
    assert db.intel_eventos.docs == antes and db.intel_eventos.escrituras == 0
    casos = [d for d in db[banco.COL_BANCO].docs if d["tipo"] == "caso"]
    assert len(casos) == 20 and [c["orden"] for c in casos] == list(range(1, 21))
    assert "sec:8-K:000000000000000030" not in r["manifiesto"]["ids"]


def test_si_no_son_20_no_congela_nada(mundo):
    db, _, _ = mundo
    db.intel_eventos.docs.pop(0)
    r = asyncio.run(banco.congelar(db))
    assert r["ok"] is False and "20" in r["motivo"] and len(r["candidatos"]) == 19
    assert db[banco.COL_BANCO].escrituras == 0


def test_congelar_otra_vez_NO_sobrescribe(mundo):
    db, _, _ = mundo
    asyncio.run(banco.congelar(db))
    escrituras = db[banco.COL_BANCO].escrituras
    r = asyncio.run(banco.congelar(db))
    assert r["ok"] is False and r["manifiesto"]
    assert db[banco.COL_BANCO].escrituras == escrituras


def test_si_un_documento_ENVIADO_no_baja_no_se_guarda_nada(mundo):
    db, web, _ = mundo
    del web["https://www.sec.gov/Archives/edgar/data/1015/000000000000000015/ex991.htm"]
    r = asyncio.run(banco.congelar(db))
    assert r["ok"] is False and r["errores"]
    assert db[banco.COL_BANCO].escrituras == 0


# ── 2 · Lo que falta, como falta ─────────────────────────────────────────────

def _casos(db):
    return {c["evento_id"]: c for c in asyncio.run(banco.casos(db, con_textos=True))}


def test_lo_no_registrado_queda_AUSENTE(mundo):
    db, _, _ = mundo
    asyncio.run(banco.congelar(db))
    c = _casos(db)["sec:8-K:000000000000000001"]
    assert c["respuesta_original"] is None and c["tiempos_ms"] is None
    assert c["modelo"]["real"] is None and c["modelo"]["nota"] == banco.NO_REGISTRADO
    assert {"respuesta_original", "modelo_real", "tiempos", "errores",
            "documentos_enviados"} <= set(c["faltantes"])


def test_una_confianza_guardada_de_0_NO_se_da_por_declarada(mundo):
    db, _, _ = mundo
    asyncio.run(banco.congelar(db))
    casos = _casos(db)
    cero = casos["sec:8-K:000000000000000020"]["salida"]
    assert cero["confianza_guardada"] == 0 and cero["confianza_declarada"] is None
    assert cero["nota_confianza"]
    normal = casos["sec:8-K:000000000000000002"]["salida"]
    assert normal["confianza_declarada"] == 95


# ── 3 · Reconstrucción ───────────────────────────────────────────────────────

def test_la_reconstruccion_se_contrasta_con_lo_registrado(mundo):
    db, _, _ = mundo
    r = asyncio.run(banco.congelar(db))
    casos = _casos(db)
    antiguo = casos["sec:8-K:000000000000000001"]["entrada_historica"]["reconstruccion"]
    assert antiguo["metodo"] == "ninguno" and antiguo["coincide"] is None
    con = casos["sec:8-K:000000000000000012"]["entrada_historica"]["reconstruccion"]
    assert con == {"metodo": "longitudes", "coincide": True, "diferencias": []}
    assert r["manifiesto"]["reconstruccion"]["comprobada_por_longitudes"] == 12
    assert r["manifiesto"]["reconstruccion"]["no_coinciden"] == []


def test_una_reconstruccion_que_no_cuadra_se_DICE(mundo):
    db, _, _ = mundo
    evento = next(e for e in db.intel_eventos.docs if e["id"] == "sec:8-K:000000000000000012")
    evento["documentos_enviados"][0]["caracteres_extraidos"] += 1
    r = asyncio.run(banco.congelar(db))
    assert r["manifiesto"]["reconstruccion"]["no_coinciden"] == ["sec:8-K:000000000000000012"]


def test_los_antiguos_reconstruyen_solo_el_principal(mundo):
    db, _, _ = mundo
    asyncio.run(banco.congelar(db))
    c = _casos(db)["sec:8-K:000000000000000003"]
    assert c["era"] == banco.SOLO_PRINCIPAL
    assert "=== ANEXO" not in c["entrada_historica"]["texto"]


def test_con_los_topes_de_produccion_el_banco_da_la_MISMA_entrada(mundo):
    db, _, _ = mundo
    asyncio.run(banco.congelar(db))
    version = banco.version_produccion()
    for c in _casos(db).values():
        if c["era"] == banco.CON_ANEXOS:
            assert banco.entrada_para(c, version) == c["entrada_historica"]["texto"]


def test_los_anexos_que_produccion_NO_lee_se_guardan_aparte(mundo):
    db, _, pedidas = mundo
    asyncio.run(banco.congelar(db))
    c = _casos(db)["sec:8-K:000000000000000012"]
    otros = c["documentos"]["otros"]
    assert [o["tipo"] for o in otros] == ["EX-2.1"]
    assert otros[0]["leido_por_produccion"] is False
    assert "MERGER" in otros[0]["texto"]
    assert "MERGER" not in c["entrada_historica"]["texto"]


def test_los_hechos_se_verifican_contra_la_entrada_reconstruida(mundo):
    db, _, _ = mundo
    asyncio.run(banco.congelar(db))
    v = _casos(db)["sec:8-K:000000000000000012"]["verificacion_hechos"]
    assert v["sobre"] == "entrada reconstruida"
    assert v["recuento"]["localizado"] == 1


def test_sin_textos_la_lectura_es_ligera(mundo):
    db, _, _ = mundo
    asyncio.run(banco.congelar(db))
    c = asyncio.run(banco.casos(db, con_textos=False))[11]
    assert "texto" not in c["documentos"]["principal"]
    assert all("texto" not in a for a in c["documentos"]["anexos"])
    assert "texto" not in c["entrada_historica"]


# ── 4 · Ejecutar una versión ─────────────────────────────────────────────────

def test_ejecutar_NO_toca_los_eventos_ni_el_contador(mundo):
    db, _, _ = mundo
    asyncio.run(banco.congelar(db))
    antes = copy.deepcopy(db.intel_eventos.docs)
    peticiones = []

    async def modelo(m, sistema, usuario, max_tokens=None):
        peticiones.append((m, sistema, max_tokens))
        return {"hay_informacion": True, "resumen": "r", "hechos": ["Ingresos de $1.012 millones."],
                "implicaciones": [], "incertidumbres": ["u"], "fuente": "8-K",
                "confianza": 90}
    r = asyncio.run(banco.ejecutar(db, "produccion", run_model=modelo))
    assert r["ok"] is True and r["llamadas"] == 20
    assert db.intel_eventos.docs == antes
    assert db["intel_uso_ia"].escrituras == 0
    assert len(db[banco.COL_EJECUCIONES].docs) == 1
    assert all(p == (inv.MODELO, inv.SISTEMA, inv.MAX_TOKENS_SALIDA) for p in peticiones)
    assert len(r["comparacion"]["casos"]) == 20
    assert "sistema" not in r["version"] and r["version"]["sistema_sha256"]


def test_una_version_desconocida_no_se_ejecuta(mundo):
    db, _, _ = mundo
    asyncio.run(banco.congelar(db))
    r = asyncio.run(banco.ejecutar(db, "inventada"))
    assert r["ok"] is False


def test_sin_banco_congelado_no_se_ejecuta(mundo):
    db, _, _ = mundo
    assert asyncio.run(banco.ejecutar(db))["ok"] is False


# ── 5 · Exportación de investigaciones (endpoint) ────────────────────────────

def test_la_exportacion_es_de_SOLO_LECTURA_y_sin_crudo(mundo, monkeypatch):
    import server
    db, _, _ = mundo
    db.intel_eventos.docs.append({"id": "sin-investigar", "etapa": ev.SIGNIFICATIVO,
                                  "investigacion": None})
    monkeypatch.setattr(server, "db", db)
    antes = copy.deepcopy(db.intel_eventos.docs)
    r = asyncio.run(server.intelligence_exportar_investigaciones(prompt_v=2, _user="rober"))
    assert r["total"] == 20 and r["con_traza"] == 0
    assert all("crudo" not in i for i in r["investigaciones"])
    assert all(i["detalle"]["accession"] for i in r["investigaciones"])
    assert db.intel_eventos.docs == antes and db.intel_eventos.escrituras == 0
    todas = asyncio.run(server.intelligence_exportar_investigaciones(_user="rober"))
    assert todas["total"] == 21                            # también la de PROMPT_V = 1


def test_el_endpoint_del_banco_sin_congelar_enseña_los_candidatos(mundo, monkeypatch):
    import server
    db, _, _ = mundo
    monkeypatch.setattr(server, "db", db)
    r = asyncio.run(server.intelligence_banco(_user="rober"))
    assert r["congelado"] is False and len(r["candidatos"]) == 20
