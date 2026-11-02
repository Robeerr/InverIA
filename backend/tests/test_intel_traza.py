"""La traza de una investigación, y que la investigación sigue siendo la misma.

QUÉ PROTEGE ESTE FICHERO

La fase de trazabilidad añade cosas AL LADO de la investigación —la traza, el estado de
la respuesta, la verificación de los hechos— y no puede cambiar nada de lo que ya hacía:

  1. La petición al modelo es idéntica: mismo sistema, mismo texto, mismo modelo, mismo
     límite de salida. Los topes y la validación no se mueven.
  2. La lectura guardada (`investigacion`) es exactamente la que daba `validar`.
  3. La traza deja reconstruir la investigación: documentos, tiempos, anexos del índice
     con su decisión, huella de lo enviado, modelo real y respuesta original.
  4. Una respuesta cortada o reparada se sigue aceptando —eso es `validar`, congelada—,
     pero queda marcada; y una confianza que falta no se lee como 0.

Todo en memoria: la SEC y el modelo son dobles.
"""
import asyncio
import hashlib
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import ai_analysis
import intel_eventos as ev
import intel_investigacion as inv

CIK = "97476"
ACC = "000095010326014118"
CARPETA = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{ACC}/"
PRINCIPAL = CARPETA + "dp1_8k.htm"
INDICE = CARPETA + "0000950103-26-014118-index.htm"


def _evento():
    e = ev.crear(fuente="sec", externo_id=f"8-K:{ACC}", titulo="8-K · Hecho relevante — TXN",
                 url=PRINCIPAL, symbol="TXN", tipo=ev.CORPORATIVO, tier=1,
                 crudo={"suceso": "8-K", "formulario": "8-K", "cik": CIK, "accession": ACC,
                        "fecha_registro": "2026-09-17"})
    e.update(etapa=ev.SIGNIFICATIVO, nivel_alerta=ev.IMPORTANT, relevancia=80)
    return e


def _fila(tipo, nombre, seq=2, desc="PRESS RELEASE", ruta=None):
    href = ruta or f"/Archives/edgar/data/{CIK}/{ACC}/{nombre}"
    return (f'<tr><td scope="row">{seq}</td><td scope="row">{desc}</td>'
            f'<td scope="row"><a href="{href}">{nombre}</a></td>'
            f'<td scope="row">{tipo}</td><td scope="row">9000</td></tr>')


def _indice(*filas):
    return ("<html><body><div id='formHeader'>Accession No. "
            "<strong>0000950103-26-014118</strong></div>"
            "<table class='tableFile' summary='Document Format Files'>"
            "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
            + _fila("8-K", "dp1_8k.htm", 1, "8-K")
            + "".join(filas) + "</table></body></html>")


def _html(t):
    return f"<html><body><p>{t}</p></body></html>"


CARATULA = ("FORM 8-K Texas Instruments 0000950103-26-014118 Item 7.01. The press release "
            "is furnished as Exhibit 99.1. Revenue was $4,212 million.")
NOTA = "On September 17, 2026 the Board declared a quarterly dividend of $1.42 per share."

LECTURA = {"hay_informacion": True, "resumen": "TI sube su dividendo trimestral.",
           "hechos": ["Dividendo trimestral de $1,42 por acción.",
                      "Ingresos de $4.212 millones.",
                      "Ingresos de $9.999 millones."],
           "implicaciones": ["x"], "incertidumbres": ["y"],
           "fuente": "Form 8-K", "confianza": 90}


class _Sec:
    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.pedidas = []

    async def __call__(self, url):
        self.pedidas.append(url)
        r = self.respuestas.get(url)
        if r is None:
            return {"ok": False, "http": 404, "bytes": 0, "ms": 3,
                    "error": "la SEC respondió 404"}
        return {"ok": True, "http": 200, "bytes": len(r), "ms": 7, "error": None, "html": r}


def _montar(monkeypatch, respuesta=LECTURA, registro=None, respuestas=None):
    """La SEC con un 8-K y su EX-99.1, y un modelo que apunta en el registro como lo
    haría `ai_analysis` y devuelve `respuesta`."""
    sec = _Sec(respuestas if respuestas is not None else {
        PRINCIPAL: _html(CARATULA),
        INDICE: _indice(_fila("EX-99.1", "dp1_ex991.htm"),
                        _fila("EX-99.2", "dp1_ex992.htm", 3),
                        _fila("EX-99.3", "dp1_ex993.htm", 4),
                        _fila("EX-2.1", "dp1_ex21.htm", 5, "MERGER AGREEMENT"),
                        _fila("EX-99.4", "fuera.htm", 6,
                              ruta="/Archives/edgar/data/1/000000000000000001/fuera.htm")),
        CARPETA + "dp1_ex991.htm": _html(NOTA),
        CARPETA + "dp1_ex992.htm": _html("Second exhibit."),
    })
    monkeypatch.setattr(inv, "descargar_documento", sec)
    llamadas = []
    reg = {"modelo_real": "gemini-3.8-flash", "respuesta_bruta": json.dumps(respuesta),
           "finish_reason": "STOP", "parseo": "directo",
           "tokens": {"entrada": 3000, "salida": 400, "pensamiento": 300, "total": 3700}}
    reg.update(registro or {})

    async def modelo(m, sistema, usuario, max_tokens=None):
        llamadas.append({"modelo": m, "sistema": sistema, "usuario": usuario,
                         "max_tokens": max_tokens})
        ai_analysis._anotar(**reg)
        return dict(respuesta) if isinstance(respuesta, dict) else respuesta
    monkeypatch.setattr(ai_analysis, "_run_model", modelo)
    return sec, llamadas


# ── 1 · La petición al modelo NO cambia ──────────────────────────────────────

def test_los_topes_y_el_limite_de_salida_son_los_de_siempre():
    assert (inv.MAX_CARACTERES, inv.MAX_CARACTERES_ANEXO, inv.MAX_ANEXOS) == (12000, 8000, 2)
    assert (inv.MAX_RESUMEN, inv.MAX_ITEM, inv.MAX_LISTA) == (600, 300, 8)
    assert inv.MAX_TOKENS_SALIDA == 1200
    assert inv.PROMPT_V == 2
    assert hashlib.sha256(inv.SISTEMA.encode("utf-8")).hexdigest() == (
        "53300882e2840dcf40d2bd7cfe5be79973573cf167ad731de67f032078b5d995")


def test_la_peticion_es_IDENTICA_a_la_que_se_construia_antes(monkeypatch):
    """Se recalcula a mano con las funciones de siempre y se compara carácter a carácter."""
    _, llamadas = _montar(monkeypatch)
    evento = _evento()
    asyncio.run(inv.investigar(evento))
    principal = inv.texto_del_documento(_html(CARATULA), maximo=inv.MAX_BYTES)
    anexos = [{"tipo": "EX-99.1", "documento": "dp1_ex991.htm",
               "url": CARPETA + "dp1_ex991.htm",
               "texto": inv.texto_del_documento(_html(NOTA), maximo=inv.MAX_BYTES)},
              {"tipo": "EX-99.2", "documento": "dp1_ex992.htm",
               "url": CARPETA + "dp1_ex992.htm",
               "texto": inv.texto_del_documento(_html("Second exhibit."),
                                                maximo=inv.MAX_BYTES)}]
    esperado = inv.construir_peticion(evento, inv.ensamblar_envio(principal, evento,
                                                                  anexos)["texto"])
    assert llamadas == [{"modelo": esperado["modelo"], "sistema": esperado["sistema"],
                         "usuario": esperado["usuario"], "max_tokens": 1200}]


def test_la_lectura_guardada_es_EXACTAMENTE_la_de_validar(monkeypatch):
    _montar(monkeypatch)
    r = asyncio.run(inv.investigar(_evento()))
    assert r["ok"] is True
    assert r["investigacion"] == inv.validar(dict(LECTURA))["investigacion"]


def test_la_auditoria_conserva_sus_campos_de_siempre(monkeypatch):
    _montar(monkeypatch)
    r = asyncio.run(inv.investigar(_evento()))
    for campo in ("symbol", "accession", "formulario", "url", "http", "bytes_descargados",
                  "ms_descarga", "caracteres_extraidos", "caracteres_enviados",
                  "caracteres_enviados_total", "documentos_enviados", "anexos_ex99",
                  "muestra_del_texto", "verificacion", "ms_modelo", "error"):
        assert campo in r["auditoria"]


# ── 2 · La traza ─────────────────────────────────────────────────────────────

def test_la_traza_permite_reconstruir_la_investigacion(monkeypatch):
    _, llamadas = _montar(monkeypatch)
    r = asyncio.run(inv.investigar(_evento()))
    t = r["traza"]
    assert t["version"] == inv.TRAZA_V and t["prompt_v"] == 2
    assert t["modelo_pedido"] == inv.MODELO
    assert t["limites"]["tokens_salida"] == 1200
    assert t["principal"]["http"] == 200 and t["principal"]["url"] == PRINCIPAL
    # Huella exacta de lo que recibió el modelo.
    usuario = llamadas[0]["usuario"]
    assert t["envio"]["sha256_usuario"] == hashlib.sha256(usuario.encode()).hexdigest()
    assert t["envio"]["caracteres_enviados"] == sum(
        d["caracteres_enviados"] for d in r["auditoria"]["documentos_enviados"])
    assert 0 < t["envio"]["cobertura"] <= 1
    # Tiempos de cada paso.
    for paso in ("descarga_principal", "extraccion_principal", "anexos", "validacion",
                 "verificacion", "modelo", "total"):
        assert paso in t["tiempos_ms"]
    assert t["fase"] == "completa" and t["error"] is None and t["fin"]


def test_la_traza_registra_el_modelo_REAL_y_la_respuesta_original(monkeypatch):
    _montar(monkeypatch)
    r = asyncio.run(inv.investigar(_evento()))
    assert r["traza"]["llamada"]["modelo_real"] == "gemini-3.8-flash"
    assert r["traza"]["llamada"]["tokens"]["salida"] == 400
    assert json.loads(r["traza"]["respuesta"]["original"]) == LECTURA


def test_el_inventario_dice_que_se_hizo_con_CADA_documento_del_indice(monkeypatch):
    sec, _ = _montar(monkeypatch)
    r = asyncio.run(inv.investigar(_evento()))
    decision = {i["documento"]: i["decision"] for i in r["traza"]["anexos"]["inventario"]}
    assert decision == {"dp1_8k.htm": "documento_principal",
                        "dp1_ex991.htm": "seleccionado",
                        "dp1_ex992.htm": "seleccionado",
                        "dp1_ex993.htm": "omitido_por_tope",
                        "dp1_ex21.htm": "no_leido",
                        "fuera.htm": "descartado"}
    # Y el inventario no descarga nada: solo lo seleccionado, como siempre.
    assert CARPETA + "dp1_ex993.htm" not in sec.pedidas
    assert CARPETA + "dp1_ex21.htm" not in sec.pedidas


def test_cada_descarga_queda_apuntada(monkeypatch):
    _montar(monkeypatch)
    r = asyncio.run(inv.investigar(_evento()))
    papeles = [d["papel"] for d in r["traza"]["anexos"]["descargas"]]
    assert papeles == ["indice", "EX-99.1", "EX-99.2"]
    assert all(d["ms"] == 7 and d["http"] == 200 for d in r["traza"]["anexos"]["descargas"])


def test_un_fallo_tambien_trae_su_traza(monkeypatch):
    _montar(monkeypatch, respuestas={})                 # la SEC no sirve nada
    r = asyncio.run(inv.investigar(_evento()))
    assert r["ok"] is False and r["fase"] == "descarga"
    assert r["traza"]["fase"] == "descarga" and r["traza"]["error"]
    assert r["traza"]["principal"]["http"] == 404


def test_un_TIMEOUT_trae_su_traza(monkeypatch):
    _montar(monkeypatch)
    monkeypatch.setattr(inv, "TIMEOUT_MODELO", 0.05)

    async def colgado(*a, **k):
        await asyncio.sleep(30)
    monkeypatch.setattr(ai_analysis, "_run_model", colgado)
    r = asyncio.run(inv.investigar(_evento()))
    assert r["traza"]["fase"] == "modelo"
    assert "no contestó" in r["traza"]["error"]


def test_el_registro_no_se_queda_puesto_despues_de_la_llamada(monkeypatch):
    _montar(monkeypatch)
    asyncio.run(inv.investigar(_evento()))
    assert ai_analysis.REGISTRO_LLAMADA.get() is None


# ── 3 · Respuestas completas, truncadas y recortadas ─────────────────────────

def test_una_respuesta_entera_es_COMPLETA(monkeypatch):
    _montar(monkeypatch)
    r = asyncio.run(inv.investigar(_evento()))
    assert r["traza"]["respuesta"]["estado"] == inv.COMPLETA
    assert r["traza"]["respuesta"]["confianza_declarada"] == 90


def test_si_el_proveedor_para_por_tokens_es_TRUNCADA(monkeypatch):
    _montar(monkeypatch, registro={"finish_reason": "MAX_TOKENS"})
    r = asyncio.run(inv.investigar(_evento()))
    assert r["traza"]["respuesta"]["estado"] == inv.TRUNCADA_PROVEEDOR


def test_una_respuesta_REPARADA_se_acepta_pero_NO_en_silencio(monkeypatch, caplog):
    """El caso de RDDT: JSON cortado, reparado, y sin el último campo. `validar` lo
    acepta —está congelada— y la ficha guarda 0; la traza dice que la confianza NO se
    declaró y que la respuesta llegó truncada, y queda un aviso en el log."""
    cortada = {k: v for k, v in LECTURA.items() if k != "confianza"}
    _montar(monkeypatch, respuesta=cortada,
            registro={"finish_reason": "MAX_TOKENS", "parseo": "reparado"})
    with caplog.at_level(logging.WARNING, logger="intel_investigacion"):
        r = asyncio.run(inv.investigar(_evento()))
    assert r["ok"] is True                                   # validar, sin cambios
    assert r["investigacion"]["confianza"] == 0              # la ficha, sin cambios
    resp = r["traza"]["respuesta"]
    assert resp["estado"] == inv.TRUNCADA_PROVEEDOR
    assert resp["confianza_declarada"] is None                # ausente NO es cero
    assert resp["campos_ausentes"] == ["confianza"]
    assert any("truncada" in m for m in caplog.messages)


def test_lo_que_recortan_NUESTROS_topes_se_distingue():
    bruto = {**LECTURA, "resumen": "a" * 700, "hechos": [f"hecho {i}" for i in range(11)]}
    e = inv.estado_de_respuesta(bruto, {"finish_reason": "STOP", "parseo": "directo"})
    assert e["estado"] == inv.RECORTADA_POR_LIMITES
    assert e["recortes_propios"]["resumen"] == {"caracteres": 700, "tope": 600}
    assert e["recortes_propios"]["hechos"]["descartados"] == 3


def test_truncada_Y_recortada_a_la_vez():
    bruto = {**LECTURA, "resumen": "a" * 700}
    e = inv.estado_de_respuesta(bruto, {"finish_reason": "MAX_TOKENS"})
    assert e["estado"] == inv.TRUNCADA_Y_RECORTADA


def test_una_confianza_no_numerica_tampoco_es_cero():
    e = inv.estado_de_respuesta({**LECTURA, "confianza": "alta"}, {})
    assert e["confianza_declarada"] is None and e["confianza_no_numerica"] is True
    assert inv.validar({**LECTURA, "confianza": "alta"})["investigacion"]["confianza"] == 0


# ── 4 · La verificación de hechos va aparte ──────────────────────────────────

def test_los_hechos_se_verifican_contra_lo_ENVIADO_sin_tocarlos(monkeypatch):
    _montar(monkeypatch)
    r = asyncio.run(inv.investigar(_evento()))
    v = r["verificacion_hechos"]
    estados = [d["estado"] for d in v["detalle"]]
    assert estados == ["localizado", "localizado", "no_localizado"]
    assert v["no_localizados"] == [2]
    assert r["investigacion"]["hechos"] == LECTURA["hechos"]


def test_la_verificacion_no_depende_de_la_confianza(monkeypatch):
    _montar(monkeypatch, respuesta={**LECTURA, "confianza": 10})
    baja = asyncio.run(inv.investigar(_evento()))["verificacion_hechos"]
    _montar(monkeypatch, respuesta={**LECTURA, "confianza": 100})
    alta = asyncio.run(inv.investigar(_evento()))["verificacion_hechos"]
    assert baja == alta


def test_si_el_verificador_falla_la_investigacion_sigue(monkeypatch):
    _montar(monkeypatch)
    import verificador_hechos

    def revienta(*a, **k):
        raise RuntimeError("roto")
    monkeypatch.setattr(verificador_hechos, "verificar", revienta)
    r = asyncio.run(inv.investigar(_evento()))
    assert r["ok"] is True and "error" in r["verificacion_hechos"]


# ── 5 · La API de la lista no cambia de forma ────────────────────────────────

def test_la_API_de_eventos_no_sirve_la_traza():
    e = {**_evento(), "traza": {"x": 1}, "verificacion_hechos": {"y": 2}}
    salida = ev.para_api(e)
    assert "traza" not in salida and "verificacion_hechos" not in salida
