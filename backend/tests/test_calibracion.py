"""Ningún umbral sin medir puede colarse como número.

LO QUE SE PROTEGE

Un `or 0`, un `or 0.5` o un `if x > (UMBRAL or 30)` convierte la ausencia de dato en un
número inventado — y encima uno que nadie ha discutido, porque está escondido dentro de
una expresión. Este fichero vigila las dos mitades del problema:

  1. Que las constantes sigan valiendo None hasta que haya un experimento detrás.
  2. Que ningún consumidor las use en una comparación mientras valgan None.

La segunda es la que de verdad importa: una constante a None no hace daño; un consumidor
que la lea con un valor por defecto, sí.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import calibracion  # noqa: E402

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_AQUI, "..")


def _constantes():
    """Las constantes de calibración: MAYÚSCULAS y anotadas como pendientes."""
    return {n: getattr(calibracion, n) for n in dir(calibracion)
            if n.isupper() and not n.startswith("_")}


# ── Ninguna tiene número ─────────────────────────────────────────────────────

def test_todas_valen_none():
    con_valor = {n: v for n, v in _constantes().items() if v is not None}
    assert not con_valor, (
        f"Estas constantes tienen número sin experimento detrás: {con_valor}. "
        "Un umbral solo se fija después de medirlo en nuestro histórico."
    )


def test_hay_constantes_declaradas():
    """Centinela: si el módulo se vaciara, el test anterior pasaría sin comprobar nada."""
    assert len(_constantes()) >= 8


def test_cada_constante_dice_qué_experimento_la_determina():
    """Un None sin explicación es indistinguible de un olvido."""
    fuente = open(os.path.join(_BACKEND, "calibracion.py"), encoding="utf-8").read()
    for nombre in _constantes():
        i = fuente.index(f"{nombre}:")
        siguiente = fuente[i:i + 1200]
        assert "MIDE:" in siguiente, f"{nombre} no dice qué experimento la determina"


# ── Cómo se leen ─────────────────────────────────────────────────────────────

def test_exigir_falla_ruidosamente():
    with pytest.raises(calibracion.SinCalibrar):
        calibracion.exigir("RS_PERCENTIL_MINIMO", calibracion.RS_PERCENTIL_MINIMO)


def test_exigir_devuelve_el_valor_cuando_lo_hay():
    assert calibracion.exigir("ya_medido", 42) == 42


def test_esta_calibrado_distingue_cero_de_ausencia():
    """`if valor:` trataría un 0 legítimo como «sin calibrar». Un umbral puede ser 0."""
    assert calibracion.esta_calibrado(0) is True
    assert calibracion.esta_calibrado(0.0) is True
    assert calibracion.esta_calibrado(None) is False


# ── Ningún consumidor las convierte en número ────────────────────────────────

def _ficheros_python():
    for nombre in sorted(os.listdir(_BACKEND)):
        if nombre.endswith(".py") and nombre not in ("calibracion.py",):
            yield nombre


def test_ningun_consumidor_usa_un_valor_por_defecto():
    """El fallo que este fichero existe para impedir: `CONSTANTE or 30`.

    Se busca sobre todo el backend porque el peligro no está en `calibracion.py`, que no
    consume nada, sino en quien la lea.
    """
    nombres = list(_constantes())
    for fichero in _ficheros_python():
        src = open(os.path.join(_BACKEND, fichero), encoding="utf-8").read()
        src = re.sub(r'""".*?"""', "", src, flags=re.S)
        src = re.sub(r"#.*", "", src)
        for constante in nombres:
            for patron in (rf"{constante}\s+or\s+", rf"{constante}\s*,\s*\d",
                           rf"or\s+{constante}"):
                assert not re.search(patron, src), (
                    f"{fichero}: '{constante}' con valor por defecto. Si falta el umbral, "
                    "la condición se omite y se dice; no se adivina."
                )


def test_nadie_las_compara_todavia():
    """Mientras valgan None, una comparación numérica lanzaría o daría siempre False en
    silencio. Cuando alguna se calibre, este test habrá que relajarlo A CONCIENCIA."""
    nombres = list(_constantes())
    for fichero in _ficheros_python():
        src = open(os.path.join(_BACKEND, fichero), encoding="utf-8").read()
        src = re.sub(r'""".*?"""', "", src, flags=re.S)
        src = re.sub(r"#.*", "", src)
        for constante in nombres:
            assert not re.search(rf"[<>]=?\s*calibracion\.{constante}", src), fichero
            assert not re.search(rf"calibracion\.{constante}\s*[<>]", src), fichero


# ── Ningún umbral copiado ────────────────────────────────────────────────────

def test_no_se_han_colado_los_numeros_de_los_libros():
    """25% de crecimiento, RS 70, 25% al máximo, 2-3× de volumen: todos verificables y
    todos de otro mercado y otra década."""
    src = open(os.path.join(_BACKEND, "calibracion.py"), encoding="utf-8").read()
    codigo = re.sub(r'""".*?"""', "", src, flags=re.S)
    codigo = re.sub(r"#.*", "", codigo)
    numeros = set(re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)", codigo))
    assert numeros <= {"0", "0.0"}, (
        f"Números en el código de calibracion.py: {sorted(numeros)}. "
        "Aquí no puede haber ni uno hasta que salga de un experimento."
    )
