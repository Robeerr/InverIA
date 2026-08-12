"""La dirección estructural, y sobre todo lo que NO decide.

Estos tests protegen dos cosas distintas:

  1. Que la regla haga lo que dice — comprobable con aritmética, sin datos de mercado.
  2. Que la regla siga SIN PARÁMETROS. Es lo que permite que entre en producción sin
     backtest, así que es una propiedad que hay que vigilar activamente: el día que
     alguien añada «y la SMA200 lleva N meses subiendo», el módulo deja de ser seguro
     y el test tiene que enterarse.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import tendencia  # noqa: E402


# ── La regla ─────────────────────────────────────────────────────────────────

def test_alcista_exige_las_dos_condiciones():
    # precio > sma200 Y sma50 > sma200
    assert tendencia.clasificar(110, 105, 100) == "ALCISTA"


def test_precio_sobre_la_200_no_basta_si_la_50_esta_debajo():
    """Es el caso de una acción saliendo de un suelo. No es tendencia todavía."""
    assert tendencia.clasificar(110, 95, 100) == "INDEFINIDA"


def test_la_50_arriba_no_basta_si_el_precio_esta_debajo():
    assert tendencia.clasificar(95, 105, 100) == "INDEFINIDA"


def test_bajista_es_simetrico():
    assert tendencia.clasificar(90, 95, 100) == "BAJISTA"


def test_el_limite_es_estricto_no_inclusivo():
    """Precio exactamente EN la media no es estar por encima. Sin esta decisión, una
    acción parada sobre su SMA200 saldría alcista un día y bajista al siguiente por
    un céntimo."""
    assert tendencia.clasificar(100, 105, 100) == "INDEFINIDA"
    assert tendencia.clasificar(110, 100, 100) == "INDEFINIDA"


# ── Fallo cerrado ────────────────────────────────────────────────────────────

def test_falta_un_dato_es_sin_datos_no_indefinida():
    """SIN_DATOS e INDEFINIDA no son lo mismo: «no lo sé» y «no encaja» llevan a sitios
    distintos, y solo uno de los dos admite investigarse."""
    assert tendencia.clasificar(None, 105, 100) == "SIN_DATOS"
    assert tendencia.clasificar(110, None, 100) == "SIN_DATOS"
    assert tendencia.clasificar(110, 105, None) == "SIN_DATOS"


def test_nan_cuenta_como_ausencia():
    assert tendencia.clasificar(float("nan"), 105, 100) == "SIN_DATOS"


def test_valores_no_positivos_son_sin_datos():
    assert tendencia.clasificar(0, 105, 100) == "SIN_DATOS"
    assert tendencia.clasificar(110, 105, -3) == "SIN_DATOS"


def test_texto_basura_no_revienta():
    assert tendencia.clasificar("hola", 105, 100) == "SIN_DATOS"


# ── Qué autoriza ─────────────────────────────────────────────────────────────

def test_solo_alcista_autoriza():
    assert tendencia.hay_tendencia_valida("ALCISTA") is True
    for estado in ("BAJISTA", "INDEFINIDA", "SIN_DATOS"):
        assert tendencia.hay_tendencia_valida(estado) is False, estado


def test_un_estado_desconocido_no_autoriza():
    """Si alguien inventa un estado nuevo y olvida actualizar esto, la respuesta segura
    es NO autorizar una compra."""
    assert tendencia.hay_tendencia_valida("VOLATIL") is False
    assert tendencia.hay_tendencia_valida(None) is False


# ── Desde cierres ────────────────────────────────────────────────────────────

def test_desde_cierres_necesita_200_sesiones():
    assert tendencia.desde_cierres(list(range(1, 200))) == "SIN_DATOS"
    assert tendencia.desde_cierres([]) == "SIN_DATOS"
    assert tendencia.desde_cierres(None) == "SIN_DATOS"


def test_desde_cierres_serie_ascendente_es_alcista():
    # 300 cierres subiendo: el último está por encima de ambas medias y la de 50 por
    # encima de la de 200.
    assert tendencia.desde_cierres([100 + i for i in range(300)]) == "ALCISTA"


def test_desde_cierres_serie_descendente_es_bajista():
    assert tendencia.desde_cierres([500 - i for i in range(300)]) == "BAJISTA"


def test_desde_cierres_coincide_con_clasificar():
    """El atajo no puede tener una regla propia: tiene que dar lo mismo que calcular las
    medias a mano y llamar a `clasificar`."""
    serie = [100 + (i % 37) - (i % 11) + i * 0.4 for i in range(400)]
    sma50 = sum(serie[-50:]) / 50
    sma200 = sum(serie[-200:]) / 200
    assert tendencia.desde_cierres(serie) == tendencia.clasificar(serie[-1], sma50, sma200)


# ── La propiedad que hace seguro este commit ─────────────────────────────────

def _fuente() -> str:
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tendencia.py")
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _sin_comentarios(src: str) -> str:
    """El código sin docstrings ni comentarios: aquí se examina lo que se EJECUTA.

    Sin esto, el propio texto que explica «no hay ADX ni pendiente ni 200 días» haría
    fallar al test que comprueba que no los hay.
    """
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    return re.sub(r"#.*", "", src)


def test_la_regla_no_tiene_parametros_libres():
    """Los únicos números del código son los tamaños de las medias (50 y 200) y los
    índices de corte. Ningún umbral elegido a ojo.

    Este test es el contrato de seguridad del módulo. Si falla porque alguien añadió
    una constante, la pregunta no es cómo arreglar el test: es si ese número está
    medido sobre nuestro histórico o copiado de un libro.
    """
    codigo = _sin_comentarios(_fuente())
    numeros = {n for n in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)", codigo)}
    permitidos = {"0", "1", "50", "200"}
    assert numeros <= permitidos, (
        f"Números no esperados en tendencia.py: {sorted(numeros - permitidos)}. "
        "Un umbral nuevo aquí exige medirlo antes, no añadirlo."
    )


def test_no_se_cuela_ningun_indicador_de_fuerza():
    """Dirección no es fuerza. ADX, RSI o la fuerza relativa miden CUÁNTO, y mezclarlos
    aquí devolvería un estado que responde a dos preguntas a la vez."""
    codigo = _sin_comentarios(_fuente()).lower()
    for prohibido in ("adx", "rsi", "rel_strength", "relative_strength", "momentum", "volumen"):
        assert prohibido not in codigo, f"'{prohibido}' no pertenece a este módulo"
