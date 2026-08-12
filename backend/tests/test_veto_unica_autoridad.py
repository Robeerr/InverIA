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

QUÉ NO SE TOCÓ, Y ESTÁ VIGILADO ABAJO

El sumando `conviction += (pot / 100) * 30` sigue en pie. Quitarlo baja el máximo de
convicción de 105 a 75 y deja el umbral de 80 del régimen rojo INALCANZABLE, así que
arrastra una decisión sobre los umbrales que todavía no está tomada. El último test de
este fichero deja esa aritmética explícita para que, cuando se retire, el efecto salte
en vez de descubrirse por un analista diario que se ha quedado mudo.
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

def test_los_dos_consumidores_migrados_preguntan_a_tendencia():
    for nombre in ("daily_analyst.py", "newsletter_ingest.py"):
        codigo = _codigo(nombre)
        assert "hay_tendencia_valida" in codigo, nombre


def test_el_veto_de_conviccion_lo_decide_el_estado_no_los_retornos():
    """Comprobado ejecutando: con los MISMOS fundamentales, lo único que cambia el
    resultado es la dirección. Si el veto volviera a deducirse de `return_52w` o de la
    fuerza relativa, este test lo cazaría."""
    m = {"revenue_growth": 30, "eps_growth": 25, "pe_ratio": 20,
         "return_26w": 20, "return_52w": 40, "rel_strength_52w": 15}
    cons = {"score": 85, "consensus": "Buy"}
    insider = {"net_shares": 1000, "buy_transactions": 3}
    quote = {"price": 100.0, "high_52w": 105.0, "pe_ratio": 20}

    conv_ok, _, hard_ok, _ = da._score_candidate(m, cons, insider, True, None, quote, "ALCISTA")
    assert conv_ok > 0 and hard_ok is True

    for estado in ("BAJISTA", "INDEFINIDA", "SIN_DATOS", "LO_QUE_SEA"):
        conv, razones, hard, _ = da._score_candidate(
            m, cons, insider, True, None, quote, estado)
        assert conv == 0, estado
        assert razones == [], estado


def test_un_estado_desconocido_no_autoriza():
    """Fallo cerrado en toda la cadena: si aparece un estado nuevo y nadie actualiza el
    mapa, no se propone la acción."""
    assert tendencia.hay_tendencia_valida("VOLATIL") is False


# ── La aritmética de `conviction`, explícita antes de tocarla ────────────────

def test_conviction_umbrales_la_cuenta_que_hay_que_mirar_en_5b2():
    """CENTINELA. No prueba un comportamiento: documenta una consecuencia.

    Los catalizadores suman 35 + 25 + 15 = 75. El score de potencial aporta hasta 30 más,
    y el total se recorta a 100. Los umbrales de envío son 65, y 80 cuando el régimen
    está en rojo.

    Si en 5b-2 se retira el sumando del score SIN tocar los umbrales:
      · el máximo alcanzable pasa a 75;
      · el umbral de 80 queda INALCANZABLE y el analista diario enmudece en mercado rojo;
      · con 65, solo pasaría el trío completo de catalizadores.

    Este test falla en cuanto la aritmética cambie, para que esa decisión se tome a
    conciencia y no se descubra por un correo que dejó de llegar.
    """
    CATALIZADORES = {"insiders": 35, "upgrade": 25, "earnings_batido": 15}
    APORTE_SCORE = 30
    assert sum(CATALIZADORES.values()) == 75
    assert da._CONVICTION_THRESHOLD == 65
    assert sum(CATALIZADORES.values()) + APORTE_SCORE == 105  # se recorta a 100

    codigo = _codigo("daily_analyst.py")
    assert "conviction += (pot / 100) * 30" in codigo, (
        "El sumando del score ha cambiado. Antes de seguir: ¿se han revisado los "
        "umbrales 65 y 80? Sin el score el máximo es 75 y el 80 es inalcanzable."
    )
    assert "min_conv = 80" in codigo, (
        "El umbral del régimen rojo ha cambiado. Solo tiene sentido revisarlo junto al "
        "sumando del score, no por separado."
    )
