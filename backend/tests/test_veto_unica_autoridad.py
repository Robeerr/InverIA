"""El veto estructural tiene un solo dueño: `tendencia.py`.

QUÉ SE ELIMINÓ

Había dos vetos duplicados que funcionaban leyendo el prefijo de una etiqueta de texto:

    if mom_label.startswith("⚠"):   # daily_analyst  → descartaba el candidato
    if mom_label.startswith("⚠"):   # newsletter_ingest → veredicto «la EVITA»

Dos problemas a la vez. Un veto que depende de que una cadena empiece por un emoji se
desactiva en silencio si alguien cambia ese emoji en `opportunities._potential_score_detalle`
— un módulo que ni siquiera menciona los otros dos. Y la regla estaba duplicada en sitios
que no son su dueño.

Se retiró además una TERCERA lectura, en `server._top_seleccion`, que no era un veto
—solo añadía la razón «momentum sano»— pero salía del mismo prefijo. Mientras quedara
una sola lectura, el veto podía volver por ahí; retirándola, este fichero puede exigir
CERO apariciones en vez de mantener una lista de excepciones que nadie revisa.

EL CENTINELA QUE YA CUMPLIÓ

Este fichero llevaba un test que dejaba escrita la aritmética de `conviction` para que
retirar el score no dejara el umbral de 80 inalcanzable sin que nadie se enterase. Esa
decisión se tomó en 5b-2 —la puerta pasó a contar catalizadores y el 80 desapareció—,
así que el centinela se retira: vigilaba un código que ya no existe.

Lo demás sigue en pie, que es lo que este fichero protege de verdad.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import daily_analyst as da  # noqa: E402
import tendencia  # noqa: E402

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _codigo(nombre: str) -> str:
    with open(os.path.join(_BACKEND, nombre), encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    return re.sub(r"#.*", "", src)


def _modulos_de_produccion():
    for nombre in sorted(os.listdir(_BACKEND)):
        if nombre.endswith(".py"):
            yield nombre


# ── El emoji no puede vetar nada ─────────────────────────────────────────────

# Formas de RAMIFICAR sobre el emoji. La regla no es que el carácter no aparezca —hay
# avisos legítimos para el usuario que empiezan por «⚠», y `opportunities` todavía
# PRODUCE la etiqueta— sino que nadie lo INSPECCIONE para decidir. Escribir un aviso es
# presentación; leerlo para ramificar es una regla de negocio escondida en una cadena.
_INSPECCIONES = (
    r"""startswith\(\s*["']⚠""",
    r"""["']⚠[^"']*["']\s+in\s""",
    r"""[!=]=\s*["']⚠""",
    r"""in\s*\(\s*["']⚠""",
)


def test_nadie_ramifica_sobre_el_emoji_en_todo_el_backend():
    """Sin excepciones y sin lista blanca: en cuanto se admite una, deja de ser una regla
    y pasa a ser una costumbre."""
    culpables = []
    for nombre in _modulos_de_produccion():
        codigo = _codigo(nombre)
        if any(re.search(p, codigo) for p in _INSPECCIONES):
            culpables.append(nombre)
    assert not culpables, (
        f"Estos módulos deciden leyendo el emoji: {culpables}. "
        "Un veto no puede depender de cómo empiece una cadena."
    )


def test_la_etiqueta_que_queda_no_la_consume_nadie():
    """`opportunities` sigue produciendo `momentum_label` con «⚠» porque el score viejo
    sigue en pie. Es aceptable mientras NADIE la lea para decidir — que es justo lo que
    comprueba el test de arriba. Desaparecerá con el score en 5b-2."""
    productor = _codigo("opportunities.py")
    assert "momentum_label" in productor
    consumidores = [n for n in _modulos_de_produccion()
                    if n != "opportunities.py" and "momentum_label" in _codigo(n)]
    assert not consumidores, f"{consumidores} leen una etiqueta pensada para la pantalla"


def test_nadie_inspecciona_momentum_label_para_decidir():
    """La etiqueta es para leerla en pantalla, no para ramificar sobre ella."""
    for nombre in _modulos_de_produccion():
        codigo = _codigo(nombre)
        for patron in (r"mom_label\.startswith", r"momentum_label\.startswith",
                       r'\.get\("momentum"\)\s*\)?\.startswith'):
            assert not re.search(patron, codigo), f"{nombre}: {patron}"


# ── Y `tendencia.py` sí ──────────────────────────────────────────────────────

def test_el_consumidor_que_queda_pregunta_a_tendencia():
    """Eran dos. `newsletter_ingest` ya no pregunta nada porque ya no emite veredicto:
    `_score_ticker` se retiró entero al quedarse sin lectores. Que no consulte la
    tendencia dejó de ser un defecto y pasó a ser la consecuencia de no decidir nada."""
    assert "hay_tendencia_valida" in _codigo("daily_analyst.py")


def test_newsletter_ingest_ya_no_emite_ningun_veredicto():
    codigo = _codigo("newsletter_ingest.py")
    for muerto in ("_score_ticker", "verdict", "_potential_score"):
        assert muerto not in codigo, muerto
    # `inveria` se comprueba como CAMPO, no como palabra: es también el nombre de la
    # aplicación y aparece legítimamente en `getLogger("inveria.newsletter")`. Prohibir
    # la palabra sería leer el nombre del proyecto en vez del código.
    assert '"inveria"' not in codigo
    assert "['inveria']" not in codigo


def test_el_veto_lo_decide_el_estado_y_nada_mas():
    """Comprobado ejecutando: con los MISMOS catalizadores, lo único que cambia el
    veredicto es la dirección. Si el veto volviera a deducirse de un score o de los
    retornos, este test lo cazaría.

    Reescrito en 5b-2 contra `evaluar_candidato`: `_score_candidate` desapareció con la
    métrica de puntos, pero lo que protegía sigue vigente.
    """
    cons = {"score": 85, "consensus": "Buy"}
    insider = {"net_shares": 1000, "buy_transactions": 3}

    ok = da.evaluar_candidato(insider, True, None, cons=cons, estado_tendencia="ALCISTA")
    assert ok["aceptada"] is True

    for estado in ("BAJISTA", "INDEFINIDA", "SIN_DATOS", "LO_QUE_SEA"):
        v = da.evaluar_candidato(insider, True, None, cons=cons, estado_tendencia=estado)
        assert v["aceptada"] is False, estado
        assert v["estado"] == da.DESCARTADA_POR_TENDENCIA, estado
        # El recuento se conserva: el veto no borra el diagnóstico.
        assert v["catalizadores"] == 2, estado


def test_un_estado_desconocido_no_autoriza():
    """Fallo cerrado en toda la cadena: si aparece un estado nuevo y nadie actualiza el
    mapa, no se propone la acción."""
    assert tendencia.hay_tendencia_valida("VOLATIL") is False


# ── La aritmética de `conviction`, explícita antes de tocarla ────────────────
