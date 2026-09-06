"""Qué acciones entran en la correlación de la Cartera.

El techo de 25 existe porque cada símbolo descarga un año de histórico. El fallo no era el
techo: era QUIÉNES entraban. Se cogían los 25 primeros que devolvía Mongo —orden arbitrario
y ni siquiera estable— así que con 83 valores en la Cartera se medía la diversificación de
un trozo cualquiera y se enseñaba como si fuera la cartera entera.
"""
import os
import re

_AQUI = os.path.dirname(__file__)


def _fuente():
    with open(os.path.join(_AQUI, "..", "server.py"), encoding="utf-8") as f:
        texto = f.read()
    i = texto.index("async def portfolio_correlation")
    return texto[i:texto.index("\n@api_router", i)]


def test_las_posiciones_abiertas_entran_antes_que_la_lista_de_seguimiento():
    """«Si cae una, caen todas» es una pregunta sobre el dinero que está puesto."""
    src = _fuente()
    assert "acciones" in src, "hace falta leer las acciones para saber qué se tiene abierto"
    assert re.search(r"0 if _acc\(r\) > 0 else 1", src)
    assert "candidatos.sort()" in src


def test_el_orden_es_estable_entre_llamadas():
    """Sin orden, dos recálculos del mismo día podían dar cifras distintas."""
    filas = [{"symbol": "ZZZ", "acciones": 0}, {"symbol": "AAA", "acciones": 0},
             {"symbol": "MMM", "acciones": 10}, {"symbol": "BBB", "acciones": 3}]

    def _orden(rows):
        vistos, cand = set(), []
        for r in rows:
            s = (r.get("symbol") or "").upper()
            if not s or s in vistos:
                continue
            vistos.add(s)
            cand.append((0 if float(r.get("acciones") or 0) > 0 else 1, s))
        cand.sort()
        return [s for _, s in cand]

    assert _orden(filas) == ["BBB", "MMM", "AAA", "ZZZ"]
    assert _orden(list(reversed(filas))) == ["BBB", "MMM", "AAA", "ZZZ"]


def test_la_respuesta_dice_cuantas_ha_mirado_de_cuantas_hay():
    """Un número calculado sobre un tercio de la cartera se lee como si fuera sobre toda."""
    src = _fuente()
    for clave in ("analizadas", "total", "en_cartera", "truncado"):
        assert f'"{clave}"' in src, clave
    # Y en TODAS las salidas, no solo en la buena: las de error también se enseñan.
    assert src.count("**alcance") >= 4


def test_el_techo_es_una_constante_con_nombre():
    with open(os.path.join(_AQUI, "..", "server.py"), encoding="utf-8") as f:
        texto = f.read()
    assert "TECHO_CORRELACION = 25" in texto
    assert "syms[:25]" not in texto, "el número suelto no dice por qué es 25"
