"""Medir si los patrones aciertan, sin regalarles nada.

Los tests que más importan aquí no son los de «cuenta bien los aciertos», sino los
que impiden que la estadística salga favorecida: el empate dentro de una vela, el
patrón caducado y el detector con dos observaciones. Los tres, mal resueltos, dan un
sistema que parece funcionar.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import patrones_registro as pr


def _v(hi, lo, fecha="2026-01-01"):
    return {"high": hi, "low": lo, "date": fecha}


ALCISTA = {"tipo": "taza_asa", "detector": "taza_asa", "sentido": "alcista",
           "confianza": 0.9, "objetivo": 120.0, "invalidacion": 90.0}


# ── Anotar ───────────────────────────────────────────────────────────────────

def test_se_anota_un_patron_con_objetivo_y_stop():
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    assert f["symbol"] == "NVDA" and f["estado"] == "pendiente"
    assert f["objetivo"] == 120.0 and f["invalidacion"] == 90.0
    assert f["detector"] == "taza_asa" and f["confianza"] == 0.9


def test_sin_objetivo_o_sin_stop_no_se_anota():
    """No es comodidad: sin esos dos números no existe la pregunta que este módulo
    contesta, y la fila quedaría pendiente para siempre ensuciando su detector."""
    assert pr.ficha({**ALCISTA, "objetivo": None}, "NVDA", "1D", 100.0) is None
    assert pr.ficha({**ALCISTA, "invalidacion": None}, "NVDA", "1D", 100.0) is None


def test_un_patron_con_la_geometria_al_reves_no_se_anota():
    """Objetivo por DEBAJO del precio en un patrón alcista no es un patrón raro: es
    uno mal construido. Medirlo daría una estadística sobre un fallo de geometría."""
    assert pr.ficha({**ALCISTA, "objetivo": 80.0}, "NVDA", "1D", 100.0) is None
    assert pr.ficha({**ALCISTA, "invalidacion": 110.0}, "NVDA", "1D", 100.0) is None


def test_el_bajista_se_anota_con_el_objetivo_debajo():
    baj = {**ALCISTA, "sentido": "bajista", "objetivo": 80.0, "invalidacion": 110.0}
    assert pr.ficha(baj, "NVDA", "1D", 100.0) is not None
    # Y al revés no: sería un alcista disfrazado.
    assert pr.ficha({**baj, "objetivo": 120.0}, "NVDA", "1D", 100.0) is None


def test_sin_sentido_no_se_anota():
    """«indecision» es lo que devuelven algunos patrones de vela. No prometen
    dirección, así que no hay nada que comprobar."""
    assert pr.ficha({**ALCISTA, "sentido": "indecision"}, "NVDA", "1D", 100.0) is None


# ── Resolver ─────────────────────────────────────────────────────────────────

def test_acierto_cuando_toca_el_objetivo_antes():
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    r = pr.evaluar(f, [_v(105, 99), _v(112, 104), _v(121, 118)])
    assert r["estado"] == "acierto" and r["velas_vistas"] == 3


def test_fallo_cuando_pierde_la_invalidacion_antes():
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    r = pr.evaluar(f, [_v(105, 99), _v(103, 89), _v(125, 120)])
    assert r["estado"] == "fallo" and r["velas_vistas"] == 2


def test_el_empate_en_la_misma_vela_cuenta_COMO_FALLO():
    """Con velas diarias no se sabe qué se tocó primero. Suponer que fue el objetivo
    es el sesgo que hace que cualquier sistema parezca mejor de lo que es."""
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    r = pr.evaluar(f, [_v(125, 85)])
    assert r["estado"] == "fallo"


def test_se_mira_el_maximo_y_el_minimo_no_el_cierre():
    """Un objetivo tocado a media sesión cuenta: es exactamente lo que ejecuta una
    orden limitada puesta en ese precio."""
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    assert pr.evaluar(f, [{"high": 121, "low": 99, "close": 101}])["estado"] == "acierto"


def test_sigue_pendiente_mientras_no_pase_nada():
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    r = pr.evaluar(f, [_v(105, 99), _v(108, 101)])
    assert r["estado"] == "pendiente" and r["velas_vistas"] == 2


def test_caduca_y_NO_cuenta_como_fallo():
    """Un patrón que en 60 velas ni llega ni se rompe no se equivocó: no dijo nada
    aprovechable. Contarlo como fallo castigaría al detector prudente y premiaría al
    que promete objetivos imposibles, que nunca se tocan pero tampoco se invalidan."""
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    r = pr.evaluar(f, [_v(105, 99)] * pr.VELAS_MAXIMAS)
    assert r["estado"] == "caducado"


def test_no_se_reevalua_lo_ya_resuelto():
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    r = pr.evaluar(f, [_v(121, 118)])
    assert pr.evaluar(r, [_v(80, 70)])["estado"] == "acierto"


def test_no_muta_el_registro_original():
    """Suele venir de Mongo; quien llama decide si escribe."""
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    pr.evaluar(f, [_v(121, 118)])
    assert f["estado"] == "pendiente"


def test_una_vela_corrupta_no_rompe_la_evaluacion():
    f = pr.ficha(ALCISTA, "NVDA", "1D", 100.0)
    r = pr.evaluar(f, [{"high": None, "low": "x"}, _v(121, 118)])
    assert r["estado"] == "acierto"


# ── Agregar ──────────────────────────────────────────────────────────────────

def _reg(det, estado, n):
    return [{"detector": det, "estado": estado} for _ in range(n)]


def test_la_tasa_ignora_los_caducados_pero_los_cuenta_aparte():
    """Un detector que caduca el 80 % puede tener un acierto altísimo entre los pocos
    que resuelve y no servir para nada. Fundirlos escondería eso."""
    r = pr.rendimiento(_reg("taza_asa", "acierto", 15) + _reg("taza_asa", "fallo", 5)
                       + _reg("taza_asa", "caducado", 40))
    e = r[0]
    assert e["tasa"] == 75.0 and e["resueltos"] == 20 and e["caducado"] == 40


def test_sin_muestra_suficiente_no_encabeza_la_lista():
    """Que un detector con 2 de 2 salga primero es la forma más rápida de tomar una
    decisión mala con buena cara."""
    r = pr.rendimiento(_reg("suerte", "acierto", 2)
                       + _reg("solido", "acierto", 18) + _reg("solido", "fallo", 7))
    assert r[0]["detector"] == "solido"
    assert r[0]["suficiente"] is True
    assert next(e for e in r if e["detector"] == "suerte")["suficiente"] is False


def test_sin_resueltos_la_tasa_es_None_y_no_cero():
    """Cero por ciento afirma que falla siempre. None dice que no se sabe."""
    assert pr.rendimiento(_reg("nuevo", "pendiente", 5))[0]["tasa"] is None


def test_la_muestra_minima_es_un_numero_con_nombre():
    """Se compara contra la constante y no contra un 20 escrito a mano, para que
    subirla el día que haya datos sea un cambio en un sitio."""
    assert pr.MUESTRA_MINIMA >= 20
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "patrones_registro.py"), encoding="utf-8").read()
    cuerpo = src[src.index("def rendimiento"):]
    assert "MUESTRA_MINIMA" in cuerpo
