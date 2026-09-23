"""Los EX-99 de un 8-K: se leen, y no cambian nada de lo que ya había.

QUÉ PROTEGE ESTE FICHERO

La investigación leía solo la carátula del 8-K. En EDGAR cada documento de un registro es
un fichero aparte, así que las notas de prensa —EX-99— nunca llegaban al modelo: en TXN el
importe del dividendo estaba en el anexo y la lectura tuvo que listarlo como incertidumbre.

La corrección añade los EX-99 DETRÁS del documento principal. Estos tests fijan las tres
promesas que la hacen aceptable sin contaminar la muestra de `PROMPT_V = 2`:

  1. Sin EX-99, la entrada al modelo es la MISMA, carácter a carácter, que antes.
  2. Con EX-99, los primeros 12.000 caracteres siguen siendo los mismos; el anexo va
     después, delimitado y con su propio presupuesto.
  3. Nada fuera de la carpeta del registro se descarga nunca, y cualquier fallo deja la
     investigación exactamente como estaba.

Todo en memoria: `descargar_documento` se sustituye por un doble que anota cada URL que se
le pide, que es lo que permite demostrar lo que NO se descarga.
"""
import asyncio
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import ai_analysis            # antes que nada: su import no puede depender de ningún doble
import intel_eventos as ev
import intel_investigacion as inv

CIK = "97476"
ACC = "000095010326014118"
CARPETA = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{ACC}/"
PRINCIPAL = CARPETA + "dp1_8k.htm"
INDICE = CARPETA + "0000950103-26-014118-index.htm"


def _evento(url=PRINCIPAL, formulario="8-K", accession=ACC):
    e = ev.crear(fuente="sec", externo_id=f"{formulario}:{accession}",
                 titulo=f"{formulario} · Hecho relevante — TXN", url=url, symbol="TXN",
                 tipo=ev.CORPORATIVO, tier=1,
                 crudo={"suceso": formulario, "formulario": formulario, "cik": CIK,
                        "accession": accession, "fecha_registro": "2026-09-17"})
    e.update(etapa=ev.SIGNIFICATIVO, nivel_alerta=ev.IMPORTANT, relevancia=80,
             afecta_cartera=True)
    return e


def _fila(tipo, href, seq=2, desc="PRESS RELEASE"):
    return (f'<tr><td scope="row">{seq}</td><td scope="row">{desc}</td>'
            f'<td scope="row"><a href="{href}">{href.rsplit("/", 1)[-1]}</a></td>'
            f'<td scope="row">{tipo}</td><td scope="row">9000</td></tr>')


def _indice(*filas, accession_con_guiones="0000950103-26-014118"):
    """Un índice con la forma del `-index.htm` de EDGAR: cabecera en <th>, y una fila por
    documento con Seq · Description · Document · Type · Size."""
    return (f"<html><body><div id='formHeader'>Accession No. "
            f"<strong>{accession_con_guiones}</strong></div>"
            "<table class='tableFile' summary='Document Format Files'>"
            "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
            + _fila("8-K", f"/ix?doc=/Archives/edgar/data/{CIK}/{ACC}/dp1_8k.htm", 1, "8-K")
            + "".join(filas) + "</table></body></html>")


def _html(texto):
    return f"<html><body><p>{texto}</p></body></html>"


CARATULA = ("FORM 8-K Texas Instruments 0000950103-26-014118 Item 7.01 Regulation FD. "
            "A copy of the press release is furnished as Exhibit 99 hereto.")


class _Sec:
    """Doble de `descargar_documento`: responde por URL y anota todo lo que se pide."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.pedidas = []

    async def __call__(self, url):
        self.pedidas.append(url)
        r = self.respuestas.get(url)
        if r is None:
            return {"ok": False, "http": 404, "bytes": 0, "ms": 1,
                    "error": "la SEC respondió 404"}
        if isinstance(r, int):
            return {"ok": False, "http": r, "bytes": 0, "ms": 1,
                    "error": f"la SEC respondió {r}"}
        return {"ok": True, "http": 200, "bytes": len(r), "ms": 1, "error": None,
                "html": r}


BUENA = {"hay_informacion": True, "resumen": "TI sube su dividendo trimestral.",
         "hechos": ["Nota de prensa del 17-09-2026."], "implicaciones": ["x"],
         "incertidumbres": [], "fuente": "Form 8-K", "confianza": 90}


def _con(monkeypatch, respuestas):
    sec = _Sec(respuestas)
    monkeypatch.setattr(inv, "descargar_documento", sec)
    llamadas = []

    async def modelo(m, sistema, usuario, max_tokens=None):
        llamadas.append({"sistema": sistema, "usuario": usuario})
        return BUENA
    monkeypatch.setattr(ai_analysis, "_run_model", modelo)
    return sec, llamadas


def _entrada_de_antes(evento, html_principal):
    """Lo que se le mandaba al modelo ANTES de este cambio. Se recalcula aquí a mano con
    la fórmula vieja —texto extraído, recortado a 12.000— para compararlo con lo de ahora."""
    texto = inv.texto_del_documento(html_principal, maximo=inv.MAX_BYTES)
    return inv.construir_peticion(evento, texto[:inv.MAX_CARACTERES])["usuario"]


# ── 1 · Lo que NO cambia ─────────────────────────────────────────────────────

def test_el_PROMPT_no_cambia():
    """Huella del `SISTEMA` tomada ANTES de tocar nada. Si cambia, la muestra de
    `PROMPT_V = 2` deja de ser una sola muestra."""
    assert hashlib.sha256(inv.SISTEMA.encode("utf-8")).hexdigest() == (
        "53300882e2840dcf40d2bd7cfe5be79973573cf167ad731de67f032078b5d995")


def test_PROMPT_V_sigue_siendo_2():
    assert inv.PROMPT_V == 2


def test_SIN_EX99_la_entrada_es_IDENTICA_a_la_de_antes(monkeypatch):
    """La promesa principal. Un 8-K cuyo índice no lista notas de prensa tiene que producir
    exactamente la misma entrada al modelo que antes de existir la lectura de anexos."""
    evento = _evento()
    sec, llamadas = _con(monkeypatch, {
        PRINCIPAL: _html(CARATULA),
        INDICE: _indice(_fila("EX-104", f"/Archives/edgar/data/{CIK}/{ACC}/cover.htm")),
    })
    r = asyncio.run(inv.investigar(evento))
    assert r["ok"] is True
    assert llamadas[0]["usuario"] == _entrada_de_antes(evento, _html(CARATULA))
    assert llamadas[0]["sistema"] == inv.SISTEMA
    assert r["auditoria"]["anexos_ex99"]["estado"] == "sin_ex99"
    assert len(r["auditoria"]["documentos_enviados"]) == 1
    # El EX-104 —la portada XBRL— no se descarga: no es un EX-99.
    assert sec.pedidas == [PRINCIPAL, INDICE]


# ── 2 · Con EX-99 ────────────────────────────────────────────────────────────

def test_CON_EX99_se_descarga_y_se_añade_DETRAS_y_delimitado(monkeypatch):
    evento = _evento()
    anexo = CARPETA + "dp1_ex9901.htm"
    sec, llamadas = _con(monkeypatch, {
        PRINCIPAL: _html(CARATULA),
        INDICE: _indice(_fila("EX-99.1", f"/Archives/edgar/data/{CIK}/{ACC}/dp1_ex9901.htm")),
        anexo: _html("TI raises quarterly dividend 4% to $1.42 per share."),
    })
    r = asyncio.run(inv.investigar(evento))
    usuario = llamadas[0]["usuario"]
    antes = _entrada_de_antes(evento, _html(CARATULA))
    # Lo que ya se enviaba va delante, sin cambiar un carácter.
    assert usuario.startswith(antes)
    # Y el anexo detrás, con su delimitador.
    assert "=== ANEXO EX-99.1 ===" in usuario[len(antes):]
    assert "$1.42 per share" in usuario[len(antes):]
    assert sec.pedidas == [PRINCIPAL, INDICE, anexo]
    assert r["auditoria"]["anexos_ex99"]["estado"] == "con_ex99"


def test_con_VARIOS_EX99_se_bajan_como_mucho_DOS_y_en_orden(monkeypatch):
    evento = _evento()
    base = f"/Archives/edgar/data/{CIK}/{ACC}/"
    sec, llamadas = _con(monkeypatch, {
        PRINCIPAL: _html(CARATULA),
        # Desordenados en el índice a propósito: 99.3, 99.1, 99.2.
        INDICE: _indice(_fila("EX-99.3", base + "c.htm", 4),
                        _fila("EX-99.1", base + "a.htm", 2),
                        _fila("EX-99.2", base + "b.htm", 3)),
        CARPETA + "a.htm": _html("uno"), CARPETA + "b.htm": _html("dos"),
        CARPETA + "c.htm": _html("tres"),
    })
    r = asyncio.run(inv.investigar(evento))
    assert sec.pedidas == [PRINCIPAL, INDICE, CARPETA + "a.htm", CARPETA + "b.htm"]
    assert CARPETA + "c.htm" not in sec.pedidas
    docs = r["auditoria"]["documentos_enviados"]
    assert [d["tipo"] for d in docs[1:]] == ["EX-99.1", "EX-99.2"]
    assert r["auditoria"]["anexos_ex99"]["omitidos_por_tope"] == 1
    assert llamadas[0]["usuario"].index("EX-99.1") < llamadas[0]["usuario"].index("EX-99.2")


# ── 3 · Lo que nunca se descarga ─────────────────────────────────────────────

def test_un_EX99_de_OTRO_registro_nunca_se_descarga(monkeypatch):
    """Mismo CIK, otra carpeta de registro. Si se siguiera, el modelo leería como propio el
    anexo de otro filing."""
    otro = f"/Archives/edgar/data/{CIK}/000000000000000001/ex99.htm"
    sec, _ = _con(monkeypatch, {PRINCIPAL: _html(CARATULA),
                                INDICE: _indice(_fila("EX-99.1", otro))})
    r = asyncio.run(inv.investigar(_evento()))
    assert sec.pedidas == [PRINCIPAL, INDICE]
    assert r["ok"] is True
    assert r["auditoria"]["anexos_ex99"]["estado"] == "sin_ex99"
    assert "ninguno dentro de la carpeta" in r["auditoria"]["anexos_ex99"]["motivo"]


@pytest.mark.parametrize("href", [
    "https://evil.example/ex99.htm",
    "http://www.sec.gov/Archives/edgar/data/97476/000095010326014118/ex99.htm",
    f"/Archives/edgar/data/{CIK}/{ACC}/../000000000000000001/ex99.htm",
    f"/Archives/edgar/data/{CIK}/{ACC}/sub/ex99.htm",
    "javascript:alert(1)",
    f"/Archives/edgar/data/{CIK}/{ACC}/ex99.pdf",
    f"/Archives/edgar/data/{CIK}/{ACC}/ex99.htm?x=1",
])
def test_una_URL_ARBITRARIA_en_el_href_nunca_se_sigue(monkeypatch, href):
    """El `href` del índice nunca se usa como URL. Solo se acepta un nombre de fichero
    seguro dentro de la carpeta conocida, y la URL se construye con ella."""
    sec, _ = _con(monkeypatch, {PRINCIPAL: _html(CARATULA),
                                INDICE: _indice(_fila("EX-99.1", href))})
    r = asyncio.run(inv.investigar(_evento()))
    assert sec.pedidas == [PRINCIPAL, INDICE], href
    assert r["ok"] is True


def test_los_demas_EXHIBITS_no_se_descargan(monkeypatch):
    """Colocación, instrumentos, opinión legal, contratos, XBRL: contrato o trámite."""
    base = f"/Archives/edgar/data/{CIK}/{ACC}/"
    filas = [_fila(t, base + f"f{i}.htm", i + 2)
             for i, t in enumerate(("EX-1.1", "EX-4.1", "EX-5.1", "EX-10.1", "EX-101.SCH",
                                    "EX-104", "GRAPHIC", "EX-23.1"))]
    sec, _ = _con(monkeypatch, {PRINCIPAL: _html(CARATULA), INDICE: _indice(*filas)})
    asyncio.run(inv.investigar(_evento()))
    assert sec.pedidas == [PRINCIPAL, INDICE]


# ── 4 · Fallback: cualquier fallo deja la investigación como estaba ──────────

@pytest.mark.parametrize("indice,estado", [
    ("<html><body>Página no encontrada</body></html>", "formato_inesperado"),
    ("<html>0000950103-26-014118 <p>sin tabla</p></html>", "formato_inesperado"),
    # El índice de OTRO registro: ni la cabecera ni los enlaces mencionan el nuestro.
    (_indice(_fila("EX-99.1", f"/Archives/edgar/data/{CIK}/000000000000000001/x.htm"),
             accession_con_guiones="0000000000-00-000001").replace(ACC, "0" * 17 + "1"),
     "formato_inesperado"),
    (404, "indice_no_disponible"),
    (503, "indice_no_disponible"),
])
def test_un_indice_INESPERADO_o_caido_cae_al_comportamiento_de_antes(monkeypatch,
                                                                    indice, estado):
    evento = _evento()
    sec, llamadas = _con(monkeypatch, {PRINCIPAL: _html(CARATULA), INDICE: indice})
    r = asyncio.run(inv.investigar(evento))
    assert r["ok"] is True and r["fase"] == "completa"
    assert llamadas[0]["usuario"] == _entrada_de_antes(evento, _html(CARATULA))
    assert r["auditoria"]["anexos_ex99"]["estado"] == estado
    assert r["auditoria"]["anexos_ex99"]["motivo"]


def test_si_falla_la_descarga_del_EXHIBIT_la_investigacion_CONTINUA(monkeypatch):
    evento = _evento()
    anexo = CARPETA + "dp1_ex9901.htm"
    sec, llamadas = _con(monkeypatch, {
        PRINCIPAL: _html(CARATULA),
        INDICE: _indice(_fila("EX-99.1", f"/Archives/edgar/data/{CIK}/{ACC}/dp1_ex9901.htm")),
        anexo: 503,
    })
    r = asyncio.run(inv.investigar(evento))
    assert r["ok"] is True and r["fase"] == "completa"
    assert llamadas[0]["usuario"] == _entrada_de_antes(evento, _html(CARATULA))
    fallos = r["auditoria"]["anexos_ex99"]["fallos"]
    assert fallos[0]["url"] == anexo and fallos[0]["http"] == 503
    # Lo que no vio el modelo no figura como enviado.
    assert len(r["auditoria"]["documentos_enviados"]) == 1


def test_si_el_calculo_de_anexos_REVIENTA_la_investigacion_continua(monkeypatch):
    """Cualquier excepción dentro de la lectura de anexos se queda dentro."""
    evento = _evento()
    sec, llamadas = _con(monkeypatch, {PRINCIPAL: _html(CARATULA), INDICE: _indice()})

    def revienta(*_a, **_k):
        raise RuntimeError("formato imposible")
    monkeypatch.setattr(inv, "ex99_del_indice", revienta)
    r = asyncio.run(inv.investigar(evento))
    assert r["ok"] is True
    assert r["auditoria"]["anexos_ex99"]["estado"] == "error"
    assert llamadas[0]["usuario"] == _entrada_de_antes(evento, _html(CARATULA))


def test_una_URL_que_no_es_de_EDGAR_no_pide_NADA_mas(monkeypatch):
    """Sin carpeta conocida no se puede garantizar que no se sale de ella: ni índice."""
    evento = _evento(url="https://sec.gov/x.htm")
    sec, _ = _con(monkeypatch, {"https://sec.gov/x.htm": _html(CARATULA)})
    r = asyncio.run(inv.investigar(evento))
    assert sec.pedidas == ["https://sec.gov/x.htm"]
    assert r["auditoria"]["anexos_ex99"]["estado"] == "sin_indice"


def test_un_accession_que_no_casa_con_la_URL_no_pide_el_indice(monkeypatch):
    evento = _evento(accession="000000000000000999")
    sec, _ = _con(monkeypatch, {PRINCIPAL: _html(CARATULA)})
    asyncio.run(inv.investigar(evento))
    assert sec.pedidas == [PRINCIPAL]


def test_un_FORM_4_no_pide_el_indice():
    """Un Form 4 no lleva notas de prensa: pedir su índice sería gastar una petición."""
    r = asyncio.run(inv.anexos_ex99(_evento(formulario="4")))
    assert r["estado"] == "no_aplica" and r["indice_url"] is None


# ── 5 · Presupuestos ─────────────────────────────────────────────────────────

def test_un_EXHIBIT_de_mas_de_8000_se_RECORTA_y_queda_anotado(monkeypatch):
    anexo = CARPETA + "big.htm"
    sec, llamadas = _con(monkeypatch, {
        PRINCIPAL: _html(CARATULA),
        INDICE: _indice(_fila("EX-99.1", f"/Archives/edgar/data/{CIK}/{ACC}/big.htm")),
        anexo: _html("y" * 20000),
    })
    r = asyncio.run(inv.investigar(_evento()))
    d = r["auditoria"]["documentos_enviados"][1]
    assert d["caracteres_extraidos"] == 20000
    assert d["caracteres_enviados"] == inv.MAX_CARACTERES_ANEXO == 8000
    assert d["recortado"] is True
    assert "y" * 8000 in llamadas[0]["usuario"] and "y" * 8001 not in llamadas[0]["usuario"]


def test_el_PRINCIPAL_sigue_limitado_a_12000_y_no_se_mezcla_con_el_anexo(monkeypatch):
    """El anexo tiene presupuesto APARTE. Si compartieran bolsa, un 8-K corto cambiaría el
    recorte del principal respecto a lo que se enviaba antes."""
    evento = _evento()
    largo = "FORM 8-K 0000950103-26-014118 " + "x" * 30000
    anexo = CARPETA + "a.htm"
    sec, llamadas = _con(monkeypatch, {
        PRINCIPAL: _html(largo),
        INDICE: _indice(_fila("EX-99.1", f"/Archives/edgar/data/{CIK}/{ACC}/a.htm")),
        anexo: _html("nota"),
    })
    r = asyncio.run(inv.investigar(evento))
    principal = r["auditoria"]["documentos_enviados"][0]
    assert principal["caracteres_enviados"] == inv.MAX_CARACTERES == 12000
    assert principal["recortado"] is True
    assert llamadas[0]["usuario"].startswith(_entrada_de_antes(evento, _html(largo)))
    # `caracteres_enviados` conserva su significado de siempre: el del principal.
    assert r["auditoria"]["caracteres_enviados"] == 12000
    assert r["auditoria"]["caracteres_enviados_total"] > 12000


# ── 6 · Trazabilidad ─────────────────────────────────────────────────────────

def test_la_trazabilidad_dice_EXACTAMENTE_que_documentos_vio_el_modelo(monkeypatch):
    anexo = CARPETA + "dp1_ex9901.htm"
    sec, _ = _con(monkeypatch, {
        PRINCIPAL: _html(CARATULA),
        INDICE: _indice(_fila("EX-99.1", f"/Archives/edgar/data/{CIK}/{ACC}/dp1_ex9901.htm")),
        anexo: _html("nota de prensa"),
    })
    r = asyncio.run(inv.investigar(_evento()))
    principal, ex = r["auditoria"]["documentos_enviados"]
    assert principal == {"url": PRINCIPAL, "tipo": "8-K", "documento": "dp1_8k.htm",
                         "caracteres_extraidos": len(inv.texto_del_documento(_html(CARATULA))),
                         "caracteres_enviados": len(inv.texto_del_documento(_html(CARATULA))),
                         "recortado": False}
    assert ex == {"url": anexo, "tipo": "EX-99.1", "documento": "dp1_ex9901.htm",
                  "caracteres_extraidos": 14, "caracteres_enviados": 14,
                  "recortado": False}
    assert r["auditoria"]["anexos_ex99"]["indice_url"] == INDICE


def test_la_auditoria_de_anexos_NO_lleva_el_texto():
    """No se guarda el HTML ni el texto de los anexos: solo lo necesario para trazar."""
    import inspect
    fuente = inspect.getsource(inv.investigar)
    assert 'if k != "anexos"' in fuente


def test_el_worker_PERSISTE_la_trazabilidad_sin_textos():
    import inspect
    import intel_worker
    guardar = inspect.getsource(intel_worker._guardar_investigacion)
    assert '"documentos_enviados": evento.get("documentos_enviados")' in guardar
    assert '"anexos_ex99": evento.get("anexos_ex99")' in guardar
    investigar_eventos = inspect.getsource(intel_worker.investigar_eventos)
    assert 'r["auditoria"].get("documentos_enviados")' in investigar_eventos


# ── 7 · Piezas puras ─────────────────────────────────────────────────────────

def test_el_accession_se_pasa_a_guiones_10_2_6():
    assert inv.accession_con_guiones(ACC) == "0000950103-26-014118"
    for malo in ("", "123", "0000950103-26-014118", ACC + "0", None):
        assert inv.accession_con_guiones(malo) is None


def test_la_carpeta_se_saca_de_la_URL_y_se_coteja_con_el_accession():
    assert inv.carpeta_del_registro(PRINCIPAL, ACC) == CARPETA
    assert inv.carpeta_del_registro(CARPETA, ACC) == CARPETA        # URL de carpeta
    assert inv.carpeta_del_registro(PRINCIPAL, "000000000000000999") is None
    assert inv.carpeta_del_registro("https://evil.example/data/1/" + ACC + "/x", ACC) is None
    assert inv.carpeta_del_registro(None, ACC) is None


def test_el_indice_se_reconoce_con_el_accession_CON_o_SIN_guiones():
    """La cabecera lo escribe con guiones y los enlaces sin ellos. Depender solo de la
    cabecera dejaría la corrección sin efecto por un detalle de presentación."""
    sin_cabecera = _indice(
        _fila("EX-99.1", f"/Archives/edgar/data/{CIK}/{ACC}/a.htm"),
        accession_con_guiones="(sin número en la cabecera)")
    r = inv.ex99_del_indice(sin_cabecera, CARPETA, ACC)
    assert r["estado"] == "con_ex99"
    # Y uno que no menciona el registro de NINGUNA forma sigue rechazándose.
    ajeno = sin_cabecera.replace(ACC, "000000000000000001")
    assert inv.ex99_del_indice(ajeno, CARPETA, ACC)["estado"] == "formato_inesperado"
