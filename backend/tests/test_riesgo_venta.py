"""Cuánto riesgo de cartera retira una venta — y qué NO afirma este cálculo.

DEGIRO calcula el riesgo de una cartera como el MÁXIMO de cuatro componentes, no como la
suma. Esa sola pieza explica lo que desconcierta al vender: si vendes algo que no era el
componente que marcaba el máximo, el máximo lo sigue fijando otra cosa y el riesgo no baja
nada, por mucho dinero que hayas vendido.

Lo que se fija aquí es esa mecánica, y la frontera que la acompaña: esto estima RIESGO
RETIRADO, no el margen libre que devolverá DEGIRO. Faltan la categoría A-D del
instrumento, la taxonomía sectorial del bróker y el efectivo de la cuenta. Una cifra en
euros de margen afirmaría algo que no se puede sostener, así que no existe.

Ejecutar:  cd backend && pytest tests/test_riesgo_venta.py -v
"""
import re
from pathlib import Path

import riesgo_cartera as rc


def _p(symbol, valor, sector):
    return {"symbol": symbol, "valor_eur": valor, "sector": sector}


# Cartera con una posición grande (META) que marca el riesgo de evento, y varias pequeñas.
# Componentes: evento 1.875 · neto 1.786,8 · sector 900 · bruto 625,4  →  manda evento.
CARTERA = [
    _p("META", 3000, "Comunicación"), _p("AEM", 1560, "Materiales"),
    _p("MU", 837, "Tecnología"), _p("ANET", 800, "Tecnología"),
    _p("TXN", 720, "Tecnología"), _p("VRT", 600, "Industrial"),
    _p("MP", 517, "Materiales"), _p("RH", 500, "Consumo"),
    _p("CIB", 400, "Financiero"),
]


# ── 1 · No reduce el componente dominante ───────────────────────────────────

def test_vender_algo_que_no_marca_el_riesgo_sale_bajo():
    """El caso que desconcierta al usuario: vendes y el margen no se mueve.

    META sigue marcando el máximo después de vender CIB, así que el riesgo de cartera es
    EXACTAMENTE el mismo. No es que baje poco: no baja.
    """
    r = rc.estimar(CARTERA, "CIB")
    assert r["clase"] == rc.BAJO
    assert r["riesgo_retirado_eur"] == 0.0
    assert r["indice"] == 0.0
    assert r["dominante_antes"] == "evento" and r["dominante_despues"] == "evento"
    assert "no es lo que marca el riesgo" in r["motivo"]


# ── 2 · Reduce el dominante moderadamente ───────────────────────────────────

def test_vender_la_mayor_posicion_de_una_cartera_repartida_sale_medio():
    """META ES el factor dominante, y aun así solo sale MEDIO.

    Al venderla toma el relevo el peso total de la cartera, que estaba casi igual de alto
    (1.786,8 frente a 1.875). Es justo el matiz que un umbral por importe no vería: la
    mayor posición no libera mucho si el segundo componente le pisa los talones.
    """
    r = rc.estimar(CARTERA, "META")
    assert r["clase"] == rc.MEDIO
    assert 0.5 <= r["indice"] < 1.5
    assert r["dominante_antes"] == "evento"
    assert r["dominante_despues"] == "neto_categoria"
    assert r["riesgo_retirado_eur"] > 0


def test_la_via_sectorial_tambien_cuenta():
    """Un sector que domina se retira vendiendo dentro de él, aunque esa posición no sea
    la mayor de la cartera."""
    tecnologica = [
        _p("MU", 2200, "Tecnología"), _p("TXN", 2000, "Tecnología"),
        _p("ANET", 1800, "Tecnología"), _p("AEM", 900, "Materiales"),
        _p("CIB", 600, "Financiero"),
    ]
    antes = rc.riesgo(tecnologica)
    assert antes[1] == "sector", "esta cartera existe para probar la vía sectorial"
    r = rc.estimar(tecnologica, "MU")
    assert r["clase"] == rc.MEDIO
    assert r["dominante_antes"] == "sector"


# ── 3 · Elimina una concentración dominante ─────────────────────────────────

def test_vender_una_concentracion_que_manda_sale_alto():
    """META es 6.000 de 8.474: ella ES el riesgo de la cartera. Al venderla el máximo se
    desploma de 3.750 a 523."""
    concentrada = [
        _p("META", 6000, "Comunicación"), _p("MU", 837, "Tecnología"),
        _p("TXN", 720, "Tecnología"), _p("MP", 517, "Materiales"),
        _p("CIB", 400, "Financiero"),
    ]
    r = rc.estimar(concentrada, "META")
    assert r["clase"] == rc.ALTO
    assert r["indice"] >= rc.UMBRAL_ALTO
    assert r["riesgo_antes_eur"] > r["riesgo_despues_eur"] * 3


def test_las_tres_clases_salen_de_la_misma_regla():
    """Ordinalidad: a más riesgo retirado por euro vendido, clase más alta. Si esto
    fallara, las clases no significarían nada aunque cada test suelto pasara."""
    concentrada = [
        _p("META", 6000, "Comunicación"), _p("MU", 837, "Tecnología"),
        _p("TXN", 720, "Tecnología"), _p("MP", 517, "Materiales"),
        _p("CIB", 400, "Financiero"),
    ]
    bajo = rc.estimar(CARTERA, "CIB")["indice"]
    medio = rc.estimar(CARTERA, "META")["indice"]
    alto = rc.estimar(concentrada, "META")["indice"]
    assert bajo < medio < alto


# ── 4 · Falta el sector ─────────────────────────────────────────────────────

def test_sin_sector_no_se_estima_nada():
    """Una posición sin sector entraría en los totales como si valiera cero y hundiría el
    componente que quizá manda. Un hueco que se ve es mejor que una clase que parece
    calculada."""
    incompleta = [_p("META", 3000, "Comunicación"), _p("AEM", 1560, ""),
                  _p("MU", 837, None)]
    r = rc.estimar(incompleta, "META")
    assert r["clase"] == rc.SIN_ESTIMACION
    assert "No se puede estimar" in r["motivo"]
    assert "AEM" in r["motivo"] and "MU" in r["motivo"], "hay que decir CUÁLES faltan"
    for prohibido in ("indice", "riesgo_retirado_eur", "dominante_antes"):
        assert prohibido not in r, f"sin estimación no puede haber {prohibido}"


def test_una_posicion_sin_valorar_tampoco_se_estima():
    """Mismo motivo: sin precio no hay valor, y sin valor los totales mienten."""
    incompleta = [_p("META", 3000, "Comunicación"), _p("AEM", None, "Materiales")]
    r = rc.estimar(incompleta, "META")
    assert r["clase"] == rc.SIN_ESTIMACION
    assert "sin valorar" in r["motivo"]


def test_un_simbolo_que_no_esta_en_la_cartera_no_inventa_una_clase():
    r = rc.estimar(CARTERA, "NVDA")
    assert r["clase"] == rc.SIN_ESTIMACION


# ── 5 · Esto NO es el margen libre de DEGIRO ────────────────────────────────

def test_no_devuelve_ninguna_cifra_de_margen():
    """La frontera. Los euros que salen son RIESGO DE CARTERA —una magnitud del modelo—,
    nunca dinero disponible. Sin la categoría A-D del instrumento, sin la taxonomía de
    DEGIRO y sin el efectivo de la cuenta, una cifra de margen sería una afirmación que no
    se puede sostener."""
    r = rc.estimar(CARTERA, "META")
    for clave in r:
        assert "margen" not in clave.lower(), f"{clave} suena a margen y no lo es"
        assert "libre" not in clave.lower(), clave
    # Los únicos euros son de riesgo, y lo dicen en su propio nombre.
    euros = [k for k in r if k.endswith("_eur")]
    assert euros and all(k.startswith("riesgo_") for k in euros), euros


def test_el_modulo_no_promete_reproducir_a_degiro():
    """Se mira el CÓDIGO y no la respuesta: lo que se protege es que el módulo siga
    declarando lo que le falta. Un día alguien añade `efectivo` y la frontera cae."""
    src = Path(rc.__file__).read_text(encoding="utf-8")
    assert "No cuánto margen devuelve DEGIRO" in src
    for hueco in ("CATEGORÍA A-D", "TAXONOMÍA", "EFECTIVO"):
        assert hueco in src, f"el módulo debe seguir declarando que le falta {hueco}"


def test_los_umbrales_estan_donde_se_pueden_recalibrar():
    """Se aceptaron 0,5 y 1,5 como punto de partida, a la espera de operaciones reales.
    Enterrados en un `if` no se cambian: se reescriben mal."""
    assert rc.UMBRAL_MEDIO == 0.5 and rc.UMBRAL_ALTO == 1.5
    src = Path(rc.__file__).read_text(encoding="utf-8")
    cuerpo = src[src.index("def estimar"):]
    assert not re.search(r">=\s*0\.5|>=\s*1\.5", cuerpo), (
        "los umbrales van por constante, no escritos dentro de la comparación")


def test_el_indice_se_mide_contra_una_venta_normal():
    """`r = 1` debe significar "como cualquier otra venta del mismo importe". Se comprueba
    construyendo el caso donde manda el peso total antes y después."""
    plana = [_p(f"S{i}", 1000, f"Sector{i}") for i in range(10)]
    antes = rc.riesgo(plana)
    assert antes[1] == "neto_categoria"
    r = rc.estimar(plana, "S0")
    assert abs(r["indice"] - 1.0) < 0.01, r["indice"]
    assert r["clase"] == rc.MEDIO


# ── La pantalla tampoco lo confunde con margen ──────────────────────────────

_FRONT = Path(__file__).resolve().parents[2] / "frontend/src"
_BLOQUE = (_FRONT / "components/RiesgoVenta.jsx").read_text(encoding="utf-8")


def test_la_pantalla_dice_lo_que_es_y_lo_que_no():
    """El aviso no es letra pequeña de descargo: es la diferencia entre una estimación y
    una promesa. Y va SIEMPRE, también cuando no se puede estimar."""
    assert "Riesgo eliminado estimado" in _BLOQUE
    assert "No representa el margen libre que DEGIRO liberará" in _BLOQUE
    # Fuera del `if` de la clase: el aviso se pinta aunque salga SIN_ESTIMACION.
    tras_condicional = _BLOQUE[_BLOQUE.index('data.clase !== "SIN_ESTIMACION"'):]
    assert "No representa el margen libre" in tras_condicional


def test_la_pantalla_no_pinta_euros_de_margen():
    """Los únicos euros del bloque son los del RIESGO por componente, que son magnitudes
    del modelo. Un euro de "margen recuperado" sería lo que el usuario prohibió."""
    for prohibido in ("margen recuperado", "Margen recuperado",
                      "margen estimado", "Margen estimado",
                      "margen liberado", "Margen liberado"):
        assert prohibido not in _BLOQUE, prohibido


def test_el_bloque_se_ve_antes_de_confirmar_en_los_dos_sitios():
    """Después de vender ya no es una decisión, es un apunte: tiene que salir ANTES del
    botón de confirmar, en Operaciones y en la Cartera."""
    ventas = (_FRONT / "pages/VentasView.jsx").read_text(encoding="utf-8")
    assert "<RiesgoVenta" in ventas
    assert ventas.index("<RiesgoVenta") < ventas.index('type="submit"'), (
        "en Operaciones va antes del botón de guardar")

    cartera = (_FRONT / "pages/SignalsView.jsx").read_text(encoding="utf-8")
    assert "<RiesgoVenta" in cartera
    assert cartera.index("<RiesgoVenta") < cartera.index("Registrar venta"), (
        "el bloque va antes del botón, no después")
