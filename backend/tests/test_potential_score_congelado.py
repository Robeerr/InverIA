"""La ruta vieja no ha cambiado ni un decimal. Esta es la prueba de que 5a no cambia
comportamiento.

POR QUÉ VALORES DORADOS Y NO UNA COMPARACIÓN CON LA IMPLEMENTACIÓN NUEVA

`separacion.py` calcula OTRA cosa —la información separada, sin total— así que no hay
nada con lo que compararla. Lo que hay que demostrar es lo contrario: que
`_potential_score` sigue devolviendo exactamente lo que devolvía antes de existir la
separación, porque hay once consumidores leyéndolo y ninguno se ha migrado.

Los 220 casos se generaron ejecutando la función tal como estaba en `52ddd12`, antes de
tocar nada. Cubren los bordes que importan: sin datos, PER negativo, crecimiento
saturado, las cuatro bandas de distancia al máximo y los tres escalones del multiplicador
de tendencia.

CUÁNDO SE PUEDE REGENERAR ESTE FICHERO

Nunca «porque falla». Si falla, alguien ha cambiado el score que once consumidores leen,
y la pregunta es si ese cambio estaba aprobado — no cómo actualizar el fichero. Se
regenera cuando 5b retire la ruta vieja, y entonces este test desaparece con ella.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import opportunities  # noqa: E402

_ORO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oro_potential_score.json")

with open(_ORO, encoding="utf-8") as f:
    CASOS = json.load(f)

# Los mismos fundamentales fijos con los que se generaron. Cambiarlos invalidaría la
# comparación entera sin que ningún test se quejase.
FIJOS = dict(net_margin=14, roe=18, debt_to_equity=0.6)


def test_hay_casos_suficientes():
    """Centinela: con el fichero vacío, el test de abajo pasaría sin comparar nada."""
    assert len(CASOS) >= 200


def test_el_score_viejo_devuelve_exactamente_lo_mismo():
    fallos = []
    for caso in CASOS:
        score, val, mom = opportunities._potential_score(*caso["in"], **FIJOS)
        if [score, val, mom] != [caso["score"], caso["val"], caso["mom"]]:
            fallos.append({
                "entrada": caso["in"],
                "esperado": [caso["score"], caso["val"], caso["mom"]],
                "obtenido": [score, val, mom],
            })
    assert not fallos, (
        f"{len(fallos)} casos han cambiado. Once consumidores leen este número; el "
        f"primero: {fallos[0]}"
    )


def test_los_casos_cubren_los_bordes_que_importan():
    """Un fichero de valores dorados sin bordes da una falsa sensación de cobertura."""
    scores = {c["score"] for c in CASOS}
    vals = {c["val"] for c in CASOS}
    moms = {c["mom"] for c in CASOS}
    assert len(scores) > 40, "poca variedad de resultados"
    assert "sin beneficios (PER negativo)" in vals
    assert "sin datos" in vals
    # Los tres escalones del multiplicador de tendencia tienen que aparecer.
    assert any(m.startswith("⚠") for m in moms)
    assert "tendencia alcista sólida" in moms
    assert "neutra" in moms


def test_la_firma_publica_sigue_intacta():
    """Los consumidores llaman por posición. Un parámetro nuevo en medio los rompería en
    silencio."""
    import inspect
    esperada = ["rev_g", "eps_g", "pe", "dist_52w", "cons_score", "ret_26w", "ret_52w",
                "rel_strength", "net_margin", "roe", "debt_to_equity"]
    assert list(inspect.signature(opportunities._potential_score).parameters) == esperada
