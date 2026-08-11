"""El script de inspeccion: que mida bien y que no toque nada.

Es una herramienta de diagnostico, no codigo de producto, pero de su salida van a salir
los umbrales de la confluencia. Un recuento mal hecho aqui se convierte en un umbral mal
elegido alli, y eso ya no se ve.

Lo que protege este fichero:

  1. Que el analisis clasifica lo que dice clasificar, incluida la regla dura de que sin
     menciones NO se fabrica confluencia.
  2. Que el script es de SOLO LECTURA y no abre red. Se comprueba sobre el codigo, porque
     lo que se protege es la forma del fichero y no el resultado de una ejecucion.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import inspeccion_confluencia as insp  # noqa: E402


FUENTE = lambda sender, subject: (sender or "?")  # noqa: E731


def doc(sender, acciones, cuando="2026-08-01T10:00:00+00:00"):
    return {"sender": sender, "subject": "x", "received_at": cuando,
            "extracted": {"acciones": acciones}}


def accion(ticker, sent=None, score=None, verdict=None, motivo=None, nombre=None):
    a = {"ticker": ticker}
    if sent:
        a["sentimiento"] = sent
    if score is not None:
        a["inveria"] = {"score": score, "verdict": verdict or f"score {score}"}
    if motivo:
        a["motivo"] = motivo
    if nombre:
        a["nombre"] = nombre
    return a


MEDIO = {"nombre": "medio", "min_fuentes": 2, "score_alto": 65, "score_bajo": 45}


# ── 1 · El resumen cuenta lo que debe ────────────────────────────────────────
def test_las_fuentes_se_cuentan_distintas_no_por_correo():
    """El fallo que el Cerebro ya tuvo: 40 correos de la misma newsletter contados como
    40 fuentes. El consenso es cuanta gente DISTINTA lo dice."""
    docs = [doc("The Daily Upside", [accion("NVDA", "POSITIVO")]) for _ in range(5)]
    docs.append(doc("Otro Boletin", [accion("NVDA", "POSITIVO")]))
    r = insp.resumir_por_ticker(docs, FUENTE)["NVDA"]
    assert r["menciones"] == 6
    assert r["n_fuentes"] == 2


def test_reparte_el_sentimiento_en_tres_cubos():
    docs = [doc("A", [accion("X", "POSITIVO")]),
            doc("B", [accion("X", "NEGATIVO")]),
            doc("C", [accion("X")])]
    r = insp.resumir_por_ticker(docs, FUENTE)["X"]
    assert (r["positivos"], r["negativos"], r["neutros"]) == (1, 1, 1)


def test_coge_el_veredicto_del_motor_ya_guardado():
    """De `acciones[].inveria`, que se escribio en la ingesta. NO se recalcula: eso
    costaria Finnhub."""
    r = insp.resumir_por_ticker([doc("A", [accion("X", "POSITIVO", score=72)])], FUENTE)["X"]
    assert r["score"] == 72


def test_sin_veredicto_guardado_el_score_queda_a_none():
    r = insp.resumir_por_ticker([doc("A", [accion("X", "POSITIVO")])], FUENTE)["X"]
    assert r["score"] is None


def test_descarta_patrocinadores():
    """Ya los filtra la ingesta, pero alguno se colo antes de que existiera el filtro."""
    docs = [doc("A", [{"ticker": "ORCL", "nombre": "Oracle NetSuite",
                       "motivo": "patrocinado por Oracle NetSuite"}])]
    r = insp.resumir_por_ticker(docs, FUENTE)
    # Si el filtro de produccion lo considera patrocinador, no debe aparecer.
    import newsletter_ingest
    if newsletter_ingest._is_sponsor(docs[0]["extracted"]["acciones"][0]):
        assert "ORCL" not in r


def test_ignora_menciones_sin_ticker():
    r = insp.resumir_por_ticker([doc("A", [{"sentimiento": "POSITIVO"}])], FUENTE)
    assert r == {}


def test_no_revienta_con_documentos_rotos():
    for basura in ([], [None], [{}], [{"extracted": None}], [{"extracted": {"acciones": None}}]):
        assert insp.resumir_por_ticker(basura, FUENTE) == {}


# ── 2 · El tono de las fuentes ───────────────────────────────────────────────
@pytest.mark.parametrize("pos,neg,esperado", [
    (3, 0, "FAVORABLE"),
    (0, 2, "DESFAVORABLE"),
    (2, 1, "MIXTO"),
    (0, 0, "SIN_SENTIDO"),
])
def test_tono_de_fuentes(pos, neg, esperado):
    r = {"positivos": pos, "negativos": neg, "neutros": 0}
    assert insp.tono_de_fuentes(r) == esperado


def test_mixto_no_se_promedia_a_neutro():
    """Que unas fuentes lo vean bien y otras mal ES informacion. Un promedio la borraria."""
    assert insp.tono_de_fuentes({"positivos": 5, "negativos": 1, "neutros": 0}) == "MIXTO"


# ── 3 · La clasificacion ────────────────────────────────────────────────────
def _r(**kw):
    base = {"menciones": 1, "n_fuentes": 1, "positivos": 0, "negativos": 0,
            "neutros": 0, "score": None}
    base.update(kw)
    return base


def test_sin_menciones_nunca_hay_confluencia():
    """LA REGLA DURA. Un ticker que el motor puntua alto y del que nadie ha hablado no es
    un acuerdo: es una idea propia. Llamarlo confluencia seria fabricar una coincidencia."""
    r = _r(menciones=0, n_fuentes=0, score=95)
    assert insp.clasificar(r, MEDIO) == "SIN_FUENTES"


def test_sin_veredicto_del_motor_es_insuficiente_no_neutral():
    """Falta una de las dos opiniones: no se puede cruzar nada. Decir «neutral» sugeriria
    que se han comparado y empatan."""
    r = _r(menciones=3, n_fuentes=3, positivos=3, score=None)
    assert insp.clasificar(r, MEDIO) == "INSUFICIENTE"


def test_acuerdo_pide_las_tres_condiciones():
    assert insp.clasificar(_r(n_fuentes=2, positivos=2, score=70), MEDIO) == "ACUERDO"
    # Con una sola fuente no hay consenso, aunque el motor acompañe.
    assert insp.clasificar(_r(n_fuentes=1, positivos=1, score=70), MEDIO) != "ACUERDO"
    # Con el motor tibio tampoco.
    assert insp.clasificar(_r(n_fuentes=3, positivos=3, score=50), MEDIO) != "ACUERDO"


def test_choque_en_las_dos_direcciones():
    """Las fuentes lo empujan y el motor lo evita — o al reves. Es el caso mas informativo
    de todos, porque es el unico donde la app puede evitarte una decision mala."""
    assert insp.clasificar(_r(n_fuentes=3, positivos=3, score=20), MEDIO) == "CHOQUE"
    assert insp.clasificar(_r(n_fuentes=3, negativos=3, score=80), MEDIO) == "CHOQUE"


def test_el_choque_no_exige_minimo_de_fuentes():
    """Una sola fuente empujando algo que el motor evita ya merece decirse."""
    assert insp.clasificar(_r(n_fuentes=1, positivos=1, score=20), MEDIO) == "CHOQUE"


def test_mixto_nunca_es_acuerdo_ni_choque():
    """Si las fuentes no se ponen de acuerdo entre ellas, no hay con que cruzar."""
    for score in (10, 50, 90):
        assert insp.clasificar(_r(n_fuentes=3, positivos=2, negativos=2, score=score),
                               MEDIO) == "NEUTRAL"


def test_los_estados_son_exactamente_los_cinco_acordados():
    posibles = set()
    for menciones in (0, 3):
        for nf in (1, 3):
            for pos, neg in ((0, 0), (3, 0), (0, 3), (2, 2)):
                for score in (None, 20, 50, 80):
                    posibles.add(insp.clasificar(
                        _r(menciones=menciones, n_fuentes=nf, positivos=pos,
                           negativos=neg, score=score), MEDIO))
    assert posibles <= {"ACUERDO", "CHOQUE", "NEUTRAL", "INSUFICIENTE", "SIN_FUENTES"}


def test_un_corte_mas_estricto_nunca_da_mas_acuerdos():
    """Monotonia: subir el liston no puede fabricar acuerdos. Si pasara, el corte estaria
    mal escrito y la tabla del informe no significaria nada."""
    resumenes = {f"T{i}": _r(n_fuentes=(i % 4) + 1, positivos=i % 3,
                             negativos=(i + 1) % 2, menciones=3, score=(i * 7) % 100)
                 for i in range(40)}
    acuerdos = [insp.reparto(resumenes, c).get("ACUERDO", 0) for c in insp.CORTES]
    assert acuerdos == sorted(acuerdos, reverse=True), acuerdos


# ── 4 · Solo lectura, sin red ───────────────────────────────────────────────
def _codigo():
    ruta = os.path.join(os.path.dirname(__file__), "..", "inspeccion_confluencia.py")
    with open(ruta, encoding="utf-8") as fh:
        src = fh.read()
    # Sin comentarios ni docstrings: explican POR QUE no se escribe, y mencionarlo no
    # puede contar como infraccion.
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return "\n".join(l.split("#")[0] for l in src.splitlines())


@pytest.mark.parametrize("escritura", [
    "insert_one", "insert_many", "update_one", "update_many", "replace_one",
    "delete_one", "delete_many", "drop", "bulk_write", "find_one_and",
])
def test_el_script_no_escribe_en_mongo(escritura):
    assert escritura not in _codigo()


@pytest.mark.parametrize("red", [
    "finnhub", "_score_ticker", "external_data", "requests", "httpx",
    "market_data", "polygon_data", "urlopen",
])
def test_el_script_no_abre_red(red):
    """El veredicto del motor se lee de lo ya guardado. Recalcularlo costaria Finnhub una
    vez por ticker, que en una muestra de 90 dias son cientos de llamadas."""
    assert red not in _codigo()


def test_solo_usa_find():
    codigo = _codigo()
    assert ".find(" in codigo
    assert "await db." in codigo


def test_no_fija_ningun_umbral_en_la_clasificacion():
    """`clasificar` recibe el corte como parametro. Si algun numero se colara dentro, este
    fichero habria empezado a decidir umbrales en vez de solo medirlos."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "inspeccion_confluencia.py"),
               encoding="utf-8").read()
    cuerpo = src[src.index("def clasificar("):src.index("# Cortes candidatos")]
    cuerpo = "\n".join(l.split("#")[0] for l in cuerpo.splitlines())
    cuerpo = re.sub(r'"""[\s\S]*?"""', "", cuerpo)
    assert not re.search(r"[><]=?\s*\d+", cuerpo), "hay un umbral escrito dentro de clasificar"
