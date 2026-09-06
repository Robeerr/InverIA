"""El veto tiene que poder levantarse, y alguien tiene que enterarse.

EL AGUJERO QUE ESTOS TESTS PROTEGEN

Antes de `vigilancia_veto`, una acción vetada entraba en un callejón sin salida. El veto no
caduca ni avisa, y el vigilante del Chartista solo recorre watchlist + Cartera — donde una
acción vetada NO está, precisamente porque el veto impidió guardarla. La única forma de
saber que ya se podía comprar era reanalizarla a mano, sin saber cuándo.

Los tests que más importan aquí no son los de «avisa cuando toca», sino los tres que
impiden avisar cuando NO toca: un aviso falso llega al teléfono sin que nadie lo haya
pedido y no trae al lado el panel que lo explique.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import tendencia
import veto_compra
import vigilancia_veto


# ── Armar: sobre qué se puede y sobre qué no ─────────────────────────────────

def test_se_puede_vigilar_lo_que_esta_vetado():
    assert vigilancia_veto.puede_vigilarse("BAJISTA")
    assert vigilancia_veto.puede_vigilarse("INDEFINIDA")


def test_se_puede_vigilar_lo_que_no_se_ha_podido_comprobar():
    """Una salida a bolsa reciente no tiene 200 cierres. El día que los tenga, esta
    vigilancia es lo único en todo el sistema que se va a dar cuenta."""
    assert vigilancia_veto.puede_vigilarse("SIN_DATOS")


def test_no_se_vigila_una_accion_que_ya_es_alcista():
    """Se cumpliría en la primera vuelta y mandaría un aviso de que se levantó un veto que
    nunca existió."""
    assert not vigilancia_veto.puede_vigilarse("ALCISTA")


# ── Disparar: los tres silencios que hay que garantizar ──────────────────────

def test_solo_dispara_ALCISTA():
    assert vigilancia_veto.se_levanta("ALCISTA")


def test_no_dispara_si_no_se_pudo_comprobar():
    """El caso más peligroso: un histórico que no cargó devuelve SIN_DATOS, y si eso
    disparara, un fallo de red se leería como «ya puedes comprar»."""
    assert not vigilancia_veto.se_levanta("SIN_DATOS")
    assert not vigilancia_veto.se_levanta(None)
    assert not vigilancia_veto.se_levanta("")


def test_no_dispara_con_un_estado_desconocido():
    """Si alguien añade un estado a `tendencia.ESTADOS`, el aviso NO lo autoriza por
    defecto. Fallo cerrado, igual que el veto."""
    assert not vigilancia_veto.se_levanta("LATERAL_ALCISTA")


def test_salir_de_bajista_a_indefinida_no_avisa():
    """INDEFINIDA no autoriza comprar —lo dice `veto_compra`—, así que avisar ahí sería
    invitar a una compra que la Cartera seguiría rechazando con un 409."""
    assert not vigilancia_veto.se_levanta("INDEFINIDA")
    # Y la prueba de que las dos mitades están de acuerdo, que es lo que de verdad importa:
    import estado_accion
    for est in tendencia.ESTADOS:
        avisa = vigilancia_veto.se_levanta(est)
        veta = veto_compra.hay_veto(estado_accion.evaluar(est)["estado"])
        assert not (avisa and veta), f"{est}: avisaría de algo que la Cartera rechazaría"


# ── La regla tiene un solo dueño ─────────────────────────────────────────────

def test_la_condicion_se_le_pregunta_a_tendencia():
    """Ni «ALCISTA» escrito a mano ni comparaciones de precio contra medias. Si la regla se
    amplía en `tendencia.py`, el aviso tiene que moverse con ella o pasaría a avisar de algo
    que el veto ya no considera suficiente — y nadie lo notaría hasta comprar.

    Se leen SOLO las dos funciones que deciden. El texto de `mensaje` nombra la SMA200 a
    propósito —para que el aviso explique al usuario qué ha cambiado— y meterlo en este
    barrido haría fallar el test por una frase, no por una regla duplicada.
    """
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "vigilancia_veto.py"), encoding="utf-8") as f:
        src = f.read()
    for nombre in ("puede_vigilarse", "se_levanta"):
        cuerpo = src[src.index(f"def {nombre}("):]
        cuerpo = cuerpo[:cuerpo.index("\n\n\n")]
        cuerpo = re.sub(r'""".*?"""', "", cuerpo, flags=re.S)
        cuerpo = re.sub(r"#.*", "", cuerpo)
        assert "hay_tendencia_valida" in cuerpo, f"{nombre} decide por su cuenta"
        assert "ALCISTA" not in cuerpo, f"{nombre} compara la cadena a mano"
        for medida in ("sma200", "SMA200", "sma50"):
            assert medida not in cuerpo, "la comparación estructural vive en tendencia.py"


# ── El mensaje ───────────────────────────────────────────────────────────────

def test_el_mensaje_nombra_la_accion_y_lo_que_ha_pasado():
    msg = vigilancia_veto.mensaje("VST", "BAJISTA")
    assert "VST" in msg
    assert "veto" in msg.lower()
    assert "bajista" in msg.lower()


def test_el_mensaje_no_recomienda_comprar():
    """La diferencia entre «ya se puede comprar» y «cómprala» es la que separa este módulo
    de una recomendación, y en un mensaje leído de pasada se pierde si no se escribe a
    propósito.

    Lo que se busca es el IMPERATIVO, no la palabra «compra». El mensaje dice «sus soportes
    vuelven a ser zonas de compra», que describe el estado del gráfico; prohibir el
    sustantivo obligaría a redactar el aviso sin poder nombrar aquello de lo que trata.
    """
    msg = vigilancia_veto.mensaje("VST", "BAJISTA")
    bajo = msg.lower()
    assert "no es una recomendación" in bajo
    for orden in ("cómprala", "compra ya", "entra ahora", "es momento de comprar",
                  "deberías comprar", "buena compra", "oportunidad de compra"):
        assert orden not in bajo, f"«{orden}» convierte el aviso en una recomendación"


def test_el_mensaje_aguanta_un_estado_previo_ausente():
    """El documento puede venir de antes de que se guardara `estado_al_armar`."""
    for previo in (None, "", "LO_QUE_SEA"):
        msg = vigilancia_veto.mensaje("VST", previo)
        assert "VST" in msg and msg.strip()


def test_sin_datos_se_explica_distinto_de_bajista():
    """Salir de BAJISTA es un giro; salir de SIN_DATOS es que por fin hay histórico. Decir
    lo mismo en los dos casos afirmaría sobre el mercado algo que nadie ha comprobado."""
    a = vigilancia_veto.mensaje("VST", "BAJISTA")
    b = vigilancia_veto.mensaje("VST", "SIN_DATOS")
    assert a != b
    assert "histórico" in b.lower()
