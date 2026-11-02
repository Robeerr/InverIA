"""El verificador de hechos: cifras, fechas y nombres de cada HECHO contra el texto enviado.

Los hechos están en español y los documentos de la SEC en inglés. Estos tests fijan que
se comparan VALORES —«1.914 millones» con «$1,914 million»—, que lo que no aparece se
marca, y que el verificador no toca la lectura ni mira la confianza.

Los textos de aquí son de prueba, escritos para el test; no son filings reales.
"""
import copy
import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import verificador_hechos as v

TEXTO = """Reported diluted EPS of $0.69. Reported net revenues of $1,914 million.
Customer equity increased 27% to $964.7 billion. Customer accounts increased 35% to 5.58 million.
The Board declared a dividend payable on December 14, 2026 to holders of record as of 12/01/2026.
Each share converts into 4.500 shares of Marvell common stock. Lumentum Holdings Inc. agreed.
Morgan Stanley & Co. LLC and Goldman Sachs & Co. LLC acted as underwriters for the
'Depositary Shares'. The certificate was filed in Delaware on 28 October 2026.
Free cash flow is expected to turn positive in the second half of fiscal 2028."""


def _estado(hecho, texto=TEXTO):
    return v.verificar([hecho], texto)["detalle"][0]


# ── 1 · Cifras: valores, no cadenas ──────────────────────────────────────────

def test_millones_en_español_casan_con_million_en_ingles():
    d = _estado("Ingresos netos de $1.914 millones.")
    assert d["estado"] == v.LOCALIZADO
    assert d["anclas"][0]["como"] == "escalado"


def test_y_con_billion_cuando_cambia_la_escala():
    """964.700 millones son 964,7 mil millones: la misma cifra en otra unidad."""
    assert _estado("Capital de clientes de $964.700 millones.")["estado"] == v.LOCALIZADO


def test_la_coma_decimal_española():
    assert _estado("Beneficio por acción de $0,69.")["estado"] == v.LOCALIZADO
    assert _estado("Cuentas de clientes: 5,58 millones.")["estado"] == v.LOCALIZADO


def test_una_cifra_ambigua_prueba_las_dos_lecturas():
    """«4,500» en español es cuatro y medio; en el documento pone «4.500». Las dos
    lecturas se prueban: un falso «no localizado» es peor que una coincidencia doble."""
    assert _estado("Cada acción se convierte en 4,500 acciones.")["estado"] == v.LOCALIZADO


def test_porcentajes():
    assert _estado("Crecimiento del 27% interanual.")["estado"] == v.LOCALIZADO


def test_una_cifra_que_no_esta_se_marca():
    d = _estado("Ingresos netos de $1.655 millones.")
    assert d["estado"] == v.NO_LOCALIZADO
    assert d["anclas"][0]["encontrada"] is False


def test_unas_si_y_otras_no_es_PARCIAL():
    d = _estado("Ingresos de $1.914 millones frente a $1.655 millones un año antes.")
    assert d["estado"] == v.PARCIAL


# ── 2 · Fechas ───────────────────────────────────────────────────────────────

def test_fechas_en_los_formatos_del_documento():
    assert _estado("Pagadero el 14 de diciembre de 2026.")["estado"] == v.LOCALIZADO
    assert _estado("Accionistas registrados al 1 de diciembre de 2026.")["estado"] == v.LOCALIZADO
    assert _estado("Registrado el 28 de octubre de 2026.")["estado"] == v.LOCALIZADO


def test_una_fecha_que_no_esta():
    assert _estado("Cierre previsto el 3 de marzo de 2027.")["estado"] == v.NO_LOCALIZADO


def test_los_numeros_de_una_fecha_no_cuentan_dos_veces():
    anclas = v.anclas_de("Pagadero el 14 de diciembre de 2026.")
    assert [a["tipo"] for a in anclas] == ["fecha"]


# ── 3 · Nombres y términos ───────────────────────────────────────────────────

def test_nombres_propios_y_terminos_citados():
    d = _estado("Acuerdo con Morgan Stanley & Co. LLC para emitir 'Depositary Shares'.")
    assert d["estado"] == v.LOCALIZADO
    tipos = {a["tipo"] for a in d["anclas"]}
    assert {"nombre", "termino"} <= tipos


def test_un_nombre_que_no_esta():
    assert _estado("Acuerdo con Bank of Nowhere Partners.")["estado"] == v.NO_LOCALIZADO


def test_los_acronimos_españoles_no_se_buscan():
    """«IA», «BPA» o «EE. UU.» no estarían en un documento en inglés."""
    anclas = v.anclas_de("Racks de IA con BPA alto en EE. UU.")
    assert all(a["tipo"] not in ("nombre", "termino") for a in anclas)


# ── 4 · Lo que no se puede comprobar ─────────────────────────────────────────

def test_sin_nada_comprobable():
    assert _estado("No cambia nada relevante para el accionista.")["estado"] == v.SIN_ANCLAS


def test_un_año_suelto_no_decide():
    assert _estado("Se espera en el ejercicio 2028.")["estado"] == v.SOLO_DEBILES


# ── 5 · El informe ───────────────────────────────────────────────────────────

def test_el_fragmento_contiene_el_ancla():
    d = _estado("Ingresos netos de $1.914 millones.")
    assert "1,914 million" in d["fragmento"]


def test_el_recuento_y_la_lista_de_no_localizados():
    r = v.verificar(["Ingresos de $1.914 millones.", "Ingresos de $1.655 millones.",
                     "No cambia nada."], TEXTO)
    assert r["hechos"] == 3
    assert r["recuento"][v.LOCALIZADO] == 1 and r["recuento"][v.NO_LOCALIZADO] == 1
    assert r["no_localizados"] == [1]


def test_NO_toca_los_hechos():
    hechos = ["Ingresos de $1.914 millones.", "Cierre el 3 de marzo de 2027."]
    antes = copy.deepcopy(hechos)
    v.verificar(hechos, TEXTO)
    assert hechos == antes


def test_es_INDEPENDIENTE_de_la_confianza():
    """Solo recibe los hechos y el texto: no hay forma de que la confianza influya."""
    import ast
    assert list(inspect.signature(v.verificar).parameters) == ["hechos", "texto"]
    # Y el código no la nombra: ni variables, ni claves, ni atributos. Los docstrings sí
    # la mencionan, para decir precisamente que no se mira.
    arbol = ast.parse(inspect.getsource(v))
    docstrings = {id(n.body[0].value) for n in ast.walk(arbol)
                  if isinstance(n, (ast.Module, ast.FunctionDef))
                  and n.body and isinstance(n.body[0], ast.Expr)
                  and isinstance(getattr(n.body[0], "value", None), ast.Constant)}
    usados = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Name):
            usados.add(n.id)
        elif isinstance(n, ast.Attribute):
            usados.add(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) \
                and id(n) not in docstrings:
            usados.add(n.value)
    assert not any("confianza" in u for u in usados)


def test_vacio_no_rompe():
    assert v.verificar(None, "")["hechos"] == 0
    assert v.verificar([""], "")["detalle"][0]["estado"] == v.SIN_ANCLAS
