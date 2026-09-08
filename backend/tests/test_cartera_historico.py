"""El histórico de la cartera y el índice de salud.

LO QUE MÁS IMPORTA AQUÍ

El índice es un número compuesto, y un número compuesto es la forma más fácil de
colar una métrica inventada: nadie sabe de dónde sale, así que nadie puede
discutirlo. Los tests que siguen protegen justo eso — que el número se pueda ABRIR,
que un componente que no se ha podido medir DESAPAREZCA del reparto en vez de contar
como cero, y que la volatilidad diga «no lo sé» en lugar de decir «cero».
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import cartera_historico as ch


def _serie(valores, desde="2026-01-"):
    return [{"dia": f"{desde}{i+1:02d}", "valor_eur": v} for i, v in enumerate(valores)]


# ── Snapshot ─────────────────────────────────────────────────────────────────

def test_guarda_valor_e_invertido_no_solo_el_valor():
    """Sin lo invertido no se distingue una cartera que sube porque el mercado sube
    de una que sube porque has metido más dinero. En un gráfico se ven igual."""
    s = ch.snapshot(12000, 10000, realizado_eur=500, posiciones=6, cuando="2026-03-04")
    assert s["dia"] == "2026-03-04"
    assert s["valor_eur"] == 12000 and s["invertido_eur"] == 10000
    assert s["realizado_eur"] == 500 and s["posiciones"] == 6


def test_no_se_guarda_una_cartera_sin_valor():
    for malo in (0, -5, None, "x"):
        assert ch.snapshot(malo, 100) is None


def test_un_solo_registro_por_dia():
    """El trabajo puede correr dos veces el mismo día —un reinicio, un reintento— y la
    serie no puede tener dos puntos para la misma fecha."""
    s = ch.serie([{"dia": "2026-01-01", "valor_eur": 100},
                  {"dia": "2026-01-01", "valor_eur": 110},
                  {"dia": "2026-01-02", "valor_eur": 120}])
    assert [x["valor_eur"] for x in s] == [110, 120]


def test_la_serie_sale_ordenada_aunque_entre_desordenada():
    s = ch.serie([{"dia": "2026-01-03", "valor_eur": 3},
                  {"dia": "2026-01-01", "valor_eur": 1}])
    assert [x["dia"] for x in s] == ["2026-01-01", "2026-01-03"]


# ── Volatilidad ──────────────────────────────────────────────────────────────

def test_sin_serie_suficiente_devuelve_None_y_NO_cero():
    """Cero afirmaría que la cartera no se mueve. None dice que aún no se sabe, que
    es lo único cierto el primer mes."""
    assert ch.volatilidad_anualizada(_serie([100] * 5)) is None
    assert ch.volatilidad_anualizada([]) is None


def test_una_cartera_quieta_tiene_volatilidad_cero():
    v = ch.volatilidad_anualizada(_serie([100] * 30))
    assert v == 0.0


def test_una_cartera_que_oscila_tiene_volatilidad_alta():
    vals = [100 * (1.03 if i % 2 else 0.97) for i in range(30)]
    v = ch.volatilidad_anualizada(_serie(vals))
    assert v is not None and v > 40


# ── Índice ───────────────────────────────────────────────────────────────────

def test_el_indice_viene_SIEMPRE_con_sus_componentes():
    """Un número compuesto que no se puede abrir es una métrica inventada con otro
    nombre: nadie sabría si baja por concentración o por estructura."""
    r = ch.indice_salud(25, 15, 90, 20)
    assert r["puntuacion"] is not None
    assert len(r["componentes"]) == 4
    for c in r["componentes"]:
        assert {"clave", "nombre", "peso", "nota", "explica", "medible"} <= set(c)


def test_una_cartera_sana_puntua_alto_y_una_concentrada_bajo():
    sana = ch.indice_salud(18, 9, 100, 12)["puntuacion"]
    mala = ch.indice_salud(70, 55, 30, 70)["puntuacion"]
    assert sana >= 95 and mala <= 10 and sana > mala


def test_un_componente_no_medible_DESAPARECE_del_reparto():
    """No puntúa cero: se va. Contar como cero lo que no se ha medido hundiría el
    índice de cualquier cartera nueva y haría que subiera solo al pasar el tiempo,
    sin que nada hubiera mejorado."""
    con = ch.indice_salud(20, 10, 100, 15)
    sin = ch.indice_salud(20, 10, 100, None)
    assert con["puntuacion"] == sin["puntuacion"] == 100
    assert sin["medidos"] == 3 and con["medidos"] == 4
    vol = next(c for c in sin["componentes"] if c["clave"] == "volatilidad")
    assert vol["medible"] is False and vol["peso_efectivo"] == 0


def test_los_pesos_efectivos_suman_cien_y_no_son_los_nominales():
    """Cuando falta un componente, el peso APLICADO no es el nominal. Enseñar el
    nominal haría que el número pareciera salir de un reparto que no es el que se hizo."""
    r = ch.indice_salud(20, 10, 100, None)
    efectivos = [c["peso_efectivo"] for c in r["componentes"] if c["medible"]]
    assert sum(efectivos) == 100
    sector = next(c for c in r["componentes"] if c["clave"] == "concentracion_sector")
    assert sector["peso"] == 30 and sector["peso_efectivo"] == 35   # 30/85


def test_sin_ningun_componente_medible_no_se_inventa_un_numero():
    r = ch.indice_salud(None, None, None, None)
    assert r["puntuacion"] is None and r["etiqueta"] is None and r["medidos"] == 0


def test_la_nota_se_satura_y_un_componente_no_puede_hundir_el_resto():
    """Pasar del 60% al 90% de concentración no resta más: ya estaba en cero. Sin
    saturar, un solo componente extremo se llevaría el índice entero por delante."""
    assert ch.indice_salud(60, 10, 100, 15)["puntuacion"] == \
           ch.indice_salud(90, 10, 100, 15)["puntuacion"]


def test_la_etiqueta_cambia_donde_cambia_lo_que_habria_que_hacer():
    assert ch.indice_salud(18, 9, 100, 12)["etiqueta"] == "Estable"
    assert ch.indice_salud(70, 55, 30, 70)["etiqueta"] == "Frágil"


def test_mas_estructura_nunca_puntua_peor():
    """`estructura` es el único componente donde MÁS es mejor. Un signo invertido ahí
    premiaría tener la cartera en acciones vetadas."""
    previo = -1
    for pct in (0, 25, 50, 75, 100):
        n = ch.indice_salud(20, 10, pct, 15)["puntuacion"]
        assert n >= previo
        previo = n
