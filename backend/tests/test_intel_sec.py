"""El connector de SEC/EDGAR: vigilancia directa por CIK.

LO QUE ESTE FICHERO PROTEGE

  1. QUE NINGÚN TICKER PISE A OTRO. El fallo que se midió en producción: 1.441 empresas
     tienen varias clases de acción, el mapa colapsado perdía 2.394 tickers —el 23 % del
     mercado— y en el universo real tumbaba cinco valores. El ticker que ganaba era
     además el peor: ORCL perdía contra su preferente, AEM contra su cotización OTC.

  2. QUE UN CIK COMPARTIDO SE CONSULTE UNA VEZ Y NO SE PIERDA NADA. Una empresa es una
     petición, aunque tengas dos clases suyas; pero las dos clases siguen asociadas.

  3. QUE EL PRIMER CONTACTO NO INUNDE EL RADAR. `filings.recent` trae años de historia.

  4. QUE LA COBERTURA SEA GARANTIZADA Y NO ESTADÍSTICA. Es el motivo del cambio: el
     mecanismo anterior tuvo 0 aciertos en 11 vueltas.

  5. QUE UN FALLO DE UNA EMPRESA NO TUMBE LA VUELTA, y que un 429 sí la corte.

SIN RED

`construir_tabla`, `objetivos`, `turno`, `canonizar_accession` y `parsear_submissions` son
puras. Toda la lógica se prueba sobre diccionarios; lo único que necesita red es pedir.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import intel_eventos as ev
import intel_sec as sec


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    sec._cache_tabla.update(cuando=None, por_ticker={}, por_cik={})


# Las filas reales que causaron el problema, tal como vienen del fichero de la SEC.
FILAS = [
    {"cik_str": 320193, "ticker": "AAPL"},
    {"cik_str": 1652044, "ticker": "GOOGL"},
    {"cik_str": 1652044, "ticker": "GOOG"},
    {"cik_str": 1652044, "ticker": "GOOGM"},
    {"cik_str": 1652044, "ticker": "GOOGN"},      # el que ganaba antes
    {"cik_str": 1341439, "ticker": "ORCL"},
    {"cik_str": 1341439, "ticker": "ORCL-PD"},    # preferente: ganaba antes
    {"cik_str": 2809, "ticker": "AEM"},
    {"cik_str": 2809, "ticker": "AEMRF"},         # cotización OTC: ganaba antes
    {"cik_str": 753308, "ticker": "NEE"},
    {"cik_str": 753308, "ticker": "NEE-PR"},
    {"cik_str": 1630805, "ticker": "BW"},
    {"cik_str": 1630805, "ticker": "BW-PA"},
]
TABLA = sec.construir_tabla(FILAS)


# ── 1 · El mapa no pierde tickers ────────────────────────────────────────────

def test_ticker_a_CIK_es_la_direccion_principal():
    assert TABLA["por_ticker"]["AAPL"] == 320193


def test_VARIOS_TICKERS_pueden_compartir_CIK():
    p = TABLA["por_ticker"]
    assert p["GOOGL"] == p["GOOG"] == p["GOOGM"] == p["GOOGN"] == 1652044


def test_la_relacion_inversa_es_UNO_A_MUCHOS():
    """Aquí estaba el fallo: guardar un solo ticker por CIK hacía desaparecer al resto."""
    assert TABLA["por_cik"][1652044] == ["GOOGL", "GOOG", "GOOGM", "GOOGN"]
    assert TABLA["por_cik"][1341439] == ["ORCL", "ORCL-PD"]


def test_NINGUN_ticker_se_pierde():
    """La comprobación global: tantas entradas como filas válidas."""
    assert len(TABLA["por_ticker"]) == len(FILAS)


@pytest.mark.parametrize("ticker,cik,perdia_contra", [
    ("GOOGL", 1652044, "GOOGN"),
    ("ORCL", 1341439, "ORCL-PD"),
    ("AEM", 2809, "AEMRF"),
    ("NEE", 753308, "NEE-PR"),
    ("BW", 1630805, "BW-PA"),
])
def test_LOS_CINCO_CASOS_REALES_quedan_resueltos(ticker, cik, perdia_contra):
    """Los cinco valores del universo que el mapa viejo descartaba como «no es un valor
    tuyo». Cada uno perdía contra una preferente o una cotización OTC."""
    assert TABLA["por_ticker"][ticker] == cik
    assert TABLA["por_ticker"][perdia_contra] == cik      # el otro tampoco se pierde


def test_una_fila_corrupta_no_tumba_la_tabla():
    t = sec.construir_tabla([{"cik_str": "x", "ticker": "A"}, {"ticker": "B"},
                             {"cik_str": 1, "ticker": ""}, {"cik_str": 320193, "ticker": "AAPL"}])
    assert t["por_ticker"] == {"AAPL": 320193}


# ── 2 · Un CIK compartido, una sola consulta ─────────────────────────────────

def test_dos_clases_de_la_misma_empresa_son_UNA_consulta():
    """Es la misma empresa: preguntar dos veces gastaría el doble y produciría el mismo
    filing dos veces."""
    objs = sec.objetivos(cartera=["GOOGL", "GOOG"], watchlist=[], tabla=TABLA)
    assert len(objs) == 1 and objs[0]["cik"] == 1652044


def test_pero_NO_se_pierde_la_asociacion_con_el_otro_ticker():
    objs = sec.objetivos(cartera=["GOOGL", "GOOG"], watchlist=[], tabla=TABLA)
    assert sorted(objs[0]["tuyos"]) == ["GOOG", "GOOGL"]


def test_la_CARTERA_manda_sobre_el_seguimiento():
    """Si tienes una clase comprada y otra solo en seguimiento, el evento se etiqueta con
    la comprada: es donde hay dinero, y la relevancia depende de eso."""
    objs = sec.objetivos(cartera=["GOOG"], watchlist=["GOOGL"], tabla=TABLA)
    assert objs[0]["symbol"] == "GOOG" and objs[0]["en_cartera"] is True


def test_un_ticker_sin_CIK_no_genera_objetivo():
    """No hay a quién preguntar. No es un error: hay valores que no registran en EDGAR."""
    assert sec.objetivos(cartera=["IBE"], watchlist=[], tabla=TABLA) == []


def test_la_lista_de_objetivos_es_ESTABLE_entre_vueltas():
    """El reparto en turnos es por posición, así que un orden que bailara haría que unos
    valores se miraran de más y otros nunca."""
    a = [o["cik"] for o in sec.objetivos([], ["AAPL", "ORCL", "AEM"], TABLA)]
    b = [o["cik"] for o in sec.objetivos([], ["AEM", "AAPL", "ORCL"], TABLA)]
    assert a == b


# ── 3 · Los dos carriles ─────────────────────────────────────────────────────

def _muchos(n, prefijo="W"):
    filas = [{"cik_str": 1000 + i, "ticker": f"{prefijo}{i}"} for i in range(n)]
    return sec.construir_tabla(filas), [f"{prefijo}{i}" for i in range(n)]


def test_la_cartera_se_mira_en_TODAS_las_vueltas():
    tabla, syms = _muchos(4, "C")
    objs = sec.objetivos(cartera=syms, watchlist=[], tabla=tabla)
    for vuelta in range(sec.TURNOS_WATCHLIST * 2):
        assert len(sec.turno(objs, vuelta)) == 4


def test_el_seguimiento_se_reparte_en_turnos():
    tabla, syms = _muchos(12)
    objs = sec.objetivos(cartera=[], watchlist=syms, tabla=tabla)
    porciento = [len(sec.turno(objs, v)) for v in range(sec.TURNOS_WATCHLIST)]
    assert sum(porciento) == 12                 # todos, exactamente una vez
    assert max(porciento) - min(porciento) <= 1  # y repartidos, no en bloque


def test_ningun_valor_de_watchlist_espera_mas_de_30_min():
    """La garantía acordada. TURNOS × INTERVALO = 30 min es una igualdad que hay que
    mantener: si alguien cambia el intervalo sin tocar los turnos, la promesa se rompe en
    silencio y este test lo impide."""
    assert sec.TURNOS_WATCHLIST * sec.INTERVALO == 30 * 60


def test_TODO_el_universo_queda_cubierto_en_una_ronda_completa():
    """Cobertura completa, no estadística: es el motivo del cambio entero."""
    tabla, syms = _muchos(37)
    objs = sec.objetivos(cartera=[], watchlist=syms, tabla=tabla)
    vistos = set()
    for v in range(sec.TURNOS_WATCHLIST):
        vistos |= {o["cik"] for o in sec.turno(objs, v)}
    assert vistos == {o["cik"] for o in objs}


def test_la_rotacion_no_repite_dentro_de_la_ronda():
    tabla, syms = _muchos(18)
    objs = sec.objetivos(cartera=[], watchlist=syms, tabla=tabla)
    todos = [o["cik"] for v in range(sec.TURNOS_WATCHLIST) for o in sec.turno(objs, v)]
    assert len(todos) == len(set(todos))


# ── 4 · Números de registro ──────────────────────────────────────────────────

def test_las_DOS_FORMAS_de_la_sec_dan_el_mismo_identificador():
    """De esto cuelga toda la deduplicación entre lo guardado por el mecanismo viejo y lo
    que llega por el nuevo."""
    assert (sec.canonizar_accession("0001045810-26-000042")
            == sec.canonizar_accession("000104581026000042")
            == "000104581026000042")


def test_canonizar_aguanta_basura():
    assert sec.canonizar_accession(None) == ""
    assert sec.canonizar_accession("") == ""


# ── 5 · Parseo de submissions ────────────────────────────────────────────────

OBJETIVO = {"cik": 1045810, "symbol": "NVDA", "tuyos": ["NVDA"], "en_cartera": True}


def _submissions(*filas):
    """`filings.recent` son arrays paralelos, del más reciente al más antiguo."""
    return {"filings": {"recent": {
        "form": [f[0] for f in filas],
        "accessionNumber": [f[1] for f in filas],
        "filingDate": [f[2] for f in filas],
        "primaryDocument": [f[3] if len(f) > 3 else "d.htm" for f in filas]}}}


HOY = "2026-09-09"
RECIENTE = _submissions(
    ("8-K", "0001045810-26-000042", "2026-09-08"),
    ("4", "0001045810-26-000041", "2026-09-07"),
    ("10-Q", "0001045810-26-000040", "2026-09-06"),     # no se vigila
    ("8-K", "0001045810-24-000001", "2024-01-15"),      # antiguo
)


def test_saca_los_formularios_que_vigilamos_y_solo_esos():
    r = sec.parsear_submissions(RECIENTE, OBJETIVO, {"ultimo_accession": "000104581024000001"}, HOY)
    assert [e["crudo"]["formulario"] for e in r["eventos"]] == ["8-K", "4"]


def test_el_id_sale_del_numero_canonizado():
    r = sec.parsear_submissions(RECIENTE, OBJETIVO, {"ultimo_accession": "000104581024000001"}, HOY)
    assert r["eventos"][0]["id"] == "sec:8-K:000104581026000042"


def test_el_enlace_apunta_al_documento_ORIGINAL():
    """Sin el enlace el evento es una afirmación. Y NO se descarga: solo se guarda."""
    r = sec.parsear_submissions(RECIENTE, OBJETIVO, {"ultimo_accession": "000104581024000001"}, HOY)
    url = r["eventos"][0]["url"]
    assert url.startswith("https://www.sec.gov/Archives/edgar/data/1045810/")
    assert url.endswith("d.htm")


def test_el_evento_conserva_TUS_OTROS_tickers_de_esa_empresa():
    """Si tienes GOOGL y GOOG, el evento se etiqueta con uno pero recuerda los dos."""
    obj = {"cik": 1652044, "symbol": "GOOGL", "tuyos": ["GOOGL", "GOOG"], "en_cartera": True}
    r = sec.parsear_submissions(RECIENTE, obj, {"ultimo_accession": "000104581024000001"}, HOY)
    assert r["eventos"][0]["crudo"]["tickers_tuyos"] == ["GOOGL", "GOOG"]


# ── 6 · El cursor ────────────────────────────────────────────────────────────

def test_el_cursor_CORTA_lo_ya_visto():
    r = sec.parsear_submissions(RECIENTE, OBJETIVO,
                                {"ultimo_accession": "000104581026000041"}, HOY)
    assert [e["crudo"]["accession"] for e in r["eventos"]] == ["000104581026000042"]


def test_el_cursor_nuevo_es_el_registro_MAS_RECIENTE_aunque_no_se_emita():
    """El más reciente es un 10-Q, que no vigilamos. Si el cursor solo avanzara con los
    eventos emitidos, la vuelta siguiente volvería a recorrerlo todo desde ahí."""
    datos = _submissions(("10-Q", "0001045810-26-000099", "2026-09-09"),
                         ("8-K", "0001045810-26-000042", "2026-09-08"))
    r = sec.parsear_submissions(datos, OBJETIVO, {"ultimo_accession": "000104581026000042"}, HOY)
    assert r["eventos"] == [] and r["cursor"]["ultimo_accession"] == "000104581026000099"


def test_un_filing_YA_CONOCIDO_no_vuelve_a_salir():
    cursor = {"ultimo_accession": "000104581026000042"}
    assert sec.parsear_submissions(RECIENTE, OBJETIVO, cursor, HOY)["eventos"] == []


def test_un_filing_NUEVO_si_sale():
    cursor = {"ultimo_accession": "000104581026000041"}
    assert len(sec.parsear_submissions(RECIENTE, OBJETIVO, cursor, HOY)["eventos"]) == 1


def test_el_cursor_acepta_la_forma_CON_GUIONES():
    """Por si alguna vez se guardó así. Se canoniza antes de comparar."""
    cursor = {"ultimo_accession": "0001045810-26-000042"}
    assert sec.parsear_submissions(RECIENTE, OBJETIVO, cursor, HOY)["eventos"] == []


# ── 7 · Primer contacto ──────────────────────────────────────────────────────

def test_una_empresa_NUEVA_no_vuelca_su_historial():
    """`filings.recent` trae años. Emitirlos todos llenaría el radar de documentos viejos
    presentados como si acabaran de ocurrir."""
    r = sec.parsear_submissions(RECIENTE, OBJETIVO, None, HOY)
    assert [e["crudo"]["accession"] for e in r["eventos"]] == \
        ["000104581026000042", "000104581026000041"]     # el de 2024 se queda fuera


def test_lo_del_primer_contacto_va_MARCADO_como_tal():
    """No son eventos inventados: son registros reales con su fecha real. La marca dice
    que entraron al incorporar la empresa y no durante la vigilancia, que es una
    distinción que hace falta para leer el histórico después."""
    r = sec.parsear_submissions(RECIENTE, OBJETIVO, None, HOY)
    assert all(e["crudo"]["inicializacion"] is True for e in r["eventos"])
    assert r["cursor"]["primer_contacto"] is True


def test_tras_el_primer_contacto_ya_NO_se_marca():
    r = sec.parsear_submissions(RECIENTE, OBJETIVO,
                                {"ultimo_accession": "000104581026000041"}, HOY)
    assert "inicializacion" not in r["eventos"][0]["crudo"]


def test_una_empresa_que_VUELVE_al_universo_no_reprocesa_su_historia():
    """Su cursor sigue guardado, así que se retoma donde se dejó."""
    r = sec.parsear_submissions(RECIENTE, OBJETIVO,
                                {"ultimo_accession": "000104581026000042"}, HOY)
    assert r["eventos"] == [] and r["cursor"]["primer_contacto"] is False


# ── 8 · Nada se inventa ──────────────────────────────────────────────────────

def test_un_json_vacio_o_roto_no_fabrica_eventos():
    for basura in ({}, None, {"filings": {}}, {"filings": {"recent": {}}}):
        assert sec.parsear_submissions(basura, OBJETIVO, None, HOY)["eventos"] == []


def test_una_entrada_sin_numero_de_registro_se_ignora():
    datos = _submissions(("8-K", "", "2026-09-08"), ("8-K", "0001045810-26-000042", "2026-09-08"))
    r = sec.parsear_submissions(datos, OBJETIVO, {"ultimo_accession": "x"}, HOY)
    assert len(r["eventos"]) == 1


def test_los_eventos_nacen_en_recibido_y_sin_resumen():
    r = sec.parsear_submissions(RECIENTE, OBJETIVO, {"ultimo_accession": "x"}, HOY)
    for e in r["eventos"]:
        assert e["etapa"] == ev.RECIBIDO and e["tier"] == 1 and e["resumen"] is None


# ── 9 · Identificación y configuración ───────────────────────────────────────

def test_sin_user_agent_el_connector_esta_NO_CONFIGURADA():
    assert sec.configurado() is False and sec.estado_salud() == sec.NO_CONFIGURADA


def test_sin_user_agent_recolectar_NI_LO_INTENTA():
    import asyncio
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        asyncio.run(sec.recolectar({"cartera": {"NVDA"}}))


def test_NO_hay_user_agent_por_defecto_en_el_codigo():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "intel_sec.py"), encoding="utf-8") as f:
        src = f.read()
    assert "@" not in src.replace("Accept-Encoding", ""), "hay un correo en el código"
    assert 'get("SEC_USER_AGENT") or ""' in src


def test_NO_se_implementa_cache_condicional():
    """Se midió sobre tres empresas reales y `data.sec.gov` no manda ETag ni
    Last-Modified. Escribir ese código sería mantener una optimización que nunca se
    activa, y hacer creer que ahorra algo.

    Se miran solo las CADENAS del módulo, no los comentarios: la cabecera del fichero
    nombra esas cabeceras precisamente para explicar por qué no están, y un test que
    prohibiera mencionarlas prohibiría documentar la decisión."""
    import ast
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "intel_sec.py")
    arbol = ast.parse(open(ruta, encoding="utf-8").read())
    # Fuera las docstrings: lo que queda son las cadenas que el código usa de verdad.
    # `clean=False` a propósito: `get_docstring` normaliza la indentación por defecto y
    # entonces la cadena devuelta ya no es igual a la del árbol, así que no se descartaría
    # ninguna. El test pasaría a comparar contra un conjunto vacío sin que se notara.
    docstrings = {ast.get_docstring(n, clean=False) for n in ast.walk(arbol)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef))}
    literales = [n.value for n in ast.walk(arbol)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)
                 and n.value not in docstrings]
    for cabecera in ("If-None-Match", "If-Modified-Since"):
        assert not any(cabecera in x for x in literales), f"{cabecera} está en el código"


def test_el_limitador_es_CONSERVADOR():
    """La SEC admite 10/s. Ir muy por debajo no cuesta nada con 52 empresas cada cinco
    minutos, y con una fuente pública gratuita es lo correcto."""
    assert 0 < sec.PETICIONES_POR_SEGUNDO <= 5


def test_un_429_se_distingue_de_un_error_cualquiera(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "InverIA/1.0 x@y.z")
    assert sec.estado_salud("SEC respondió 429") == sec.LIMITADA
    assert sec.estado_salud("SEC respondió 403") == sec.ERROR
    assert sec.estado_salud("timeout", fallos=1) == sec.DEGRADADA
    assert sec.estado_salud("timeout", fallos=5) == sec.OFFLINE


def test_el_backoff_dobla_y_tiene_TECHO():
    assert sec.espera_tras_fallo(0) == 0
    assert sec.espera_tras_fallo(1) == 60
    assert sec.espera_tras_fallo(3) == 240
    assert sec.espera_tras_fallo(50) == sec.BACKOFF_MAX


def test_solo_se_vigilan_8K_y_form_4():
    assert set(sec.FORMULARIOS) == {"8-K", "4"}


def test_el_intervalo_por_defecto_son_cinco_minutos():
    assert sec.INTERVALO == 300
