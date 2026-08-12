"""Todas las acciones del Radar llevan confluencia, no solo las 25 primeras.

LA REGRESIÓN QUE ESTE FICHERO IMPIDE

Al migrar la confluencia a `fuentes × elegibilidad`, el cálculo se sacó del bucle de
construcción y se puso junto al bloque que refresca el veredicto guardado — que trabaja
sobre `acciones[:25]`. Resultado: los elementos 26 en adelante salían con
`confluencia: None`, y el endpoint devuelve la lista ENTERA.

No se rompía nada. `Confluencia.jsx` hace `confluencia ? … : null`, así que esas
tarjetas simplemente perdían el chip. Una degradación silenciosa, que es peor que un
error: no hay síntoma que investigar.

El límite de 25 pertenece al trabajo caro —refrescar el veredicto, que gasta cuota de
Finnhub por símbolo— y no a la presencia de un campo en la respuesta.

CÓMO SE PRUEBA

Sobre la FORMA del endpoint. Montar `/radar` de verdad exige Mongo, correos ingeridos y
lecturas de histórico de decenas de símbolos; lo que hay que proteger es que el bucle de
confluencia recorra `acciones` y no `top`, y eso se ve en el código. La lógica de
clasificación ya está probada aparte, en `test_confluencia.py`.

Además se ejecuta la parte que SÍ es pura: emparejar tendencias con símbolos.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import confluencia  # noqa: E402

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _codigo() -> str:
    with open(os.path.join(_AQUI, "..", "server.py"), encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    return re.sub(r"#.*", "", src)


SRC = _codigo()


def _bloque_radar() -> str:
    """Desde el orden de la lista hasta el `return` del endpoint."""
    ini = SRC.index('acciones.sort(key=lambda x: (x["n_fuentes"]')
    fin = SRC.index('"total_newsletters": len(docs),')
    return SRC[ini:fin]


# ── El bucle recorre TODAS ───────────────────────────────────────────────────

def test_la_confluencia_se_calcula_sobre_acciones_no_sobre_el_top():
    bloque = _bloque_radar()
    assert "for item, tend in zip(acciones, tendencias)" in bloque, (
        "El bucle de confluencia debe recorrer `acciones`. Si recorre `top`, los "
        "elementos 26 en adelante salen sin el campo."
    )
    assert "zip(top, tendencias)" not in bloque


def test_las_tendencias_se_piden_para_todas():
    bloque = _bloque_radar()
    trozo = bloque[bloque.index("asyncio.gather"):bloque.index("for item, tend")]
    assert "for item in acciones" in trozo
    assert "for item in top" not in trozo


def test_ya_no_queda_ningun_recorte_a_25():
    """`top = acciones[:25]` existía SOLO para acotar el refresco del veredicto guardado,
    que gastaba cuota de Finnhub. Retirado ese refresco en el commit 2, la variable se
    quedó sin función: mantenerla habría sido código muerto, y aplicarla a la resolución
    de tendencias habría reintroducido la regresión que este fichero existe para impedir.
    """
    bloque = _bloque_radar()
    assert "acciones[:25]" not in bloque
    assert "radar_score_" not in bloque
    assert "_refresh_bg" not in bloque


def test_la_respuesta_sigue_devolviendo_la_lista_entera():
    """El contrato de la API no cambia: `acciones` completo, mismo orden. Nunca estuvo
    recortada, ni antes ni después."""
    cola = SRC[SRC.index("for item, tend in zip(acciones, tendencias)"):]
    cola = cola[:cola.index("@api_router")] if "@api_router" in cola else cola
    assert '"acciones": acciones,' in cola
    assert '"acciones": top' not in cola
    assert "acciones[:25]" not in cola


# ── La parte pura: emparejar y clasificar ────────────────────────────────────

def _simular(n_acciones, tendencias):
    """Reproduce el emparejamiento del endpoint sin montar nada.

    `zip` sobre dos listas del mismo origen conserva orden y conjunto; lo que se
    comprueba aquí es que el resultado sea correcto EN TODAS las posiciones, incluida
    la 26, y que una excepción suelta degrade a SIN_DATOS sin contaminar al resto.
    """
    acciones = [{"ticker": f"T{i:02d}", "n_fuentes": 2, "positivos": 2, "negativos": 0}
                for i in range(n_acciones)]
    for item, tend in zip(acciones, tendencias):
        estado_t = tend if isinstance(tend, str) else "SIN_DATOS"
        item["confluencia"] = confluencia.evaluar(
            item["n_fuentes"], item["positivos"], item["negativos"], estado_t)
    return acciones


def test_el_elemento_26_lleva_confluencia_valida():
    """El caso concreto de la regresión, con 40 acciones."""
    acciones = _simular(40, ["ALCISTA"] * 40)
    assert len(acciones) == 40
    assert all(a.get("confluencia") for a in acciones), "alguna se quedó sin confluencia"
    # El 26 (índice 25) es el primero que caía fuera del top.
    assert acciones[25]["confluencia"]["estado"] == "ACUERDO"
    assert acciones[39]["confluencia"]["estado"] == "ACUERDO"


def test_ninguna_se_queda_en_none():
    acciones = _simular(60, ["BAJISTA"] * 60)
    assert [a for a in acciones if a["confluencia"] is None] == []


def test_un_fallo_suelto_no_contamina_al_resto():
    tends = ["ALCISTA"] * 40
    tends[30] = RuntimeError("histórico caído")
    acciones = _simular(40, tends)
    assert acciones[30]["confluencia"]["estado"] == "INSUFICIENTE"
    assert acciones[30]["confluencia"]["tendencia"] == "SIN_DATOS"
    assert acciones[29]["confluencia"]["estado"] == "ACUERDO"
    assert acciones[31]["confluencia"]["estado"] == "ACUERDO"


def test_el_orden_y_el_conjunto_se_conservan():
    tends = ["ALCISTA", "BAJISTA", "SIN_DATOS"] * 14
    acciones = _simular(42, tends)
    assert [a["ticker"] for a in acciones] == [f"T{i:02d}" for i in range(42)]
    esperado = {"ALCISTA": "ACUERDO", "BAJISTA": "CHOQUE", "SIN_DATOS": "INSUFICIENTE"}
    for a, t in zip(acciones, tends):
        assert a["confluencia"]["estado"] == esperado[t], a["ticker"]
