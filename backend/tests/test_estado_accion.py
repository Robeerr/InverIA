"""El estado de una acción, y sobre todo lo que ese estado NO promete.

LA DISTINCIÓN QUE PROTEGE ESTE FICHERO

    tendencia ALCISTA  ≠  comprable

Una acción alcista solo ha pasado el primer filtro. Lo que se vigila aquí es que ese
hecho no se convierta, por comodidad de nombres, en un permiso: ni en un estado que se
lea como «apta», ni en un COMPRAR_AHORA que todavía no tiene definición determinista.

Y la otra mitad: que la ausencia de datos no ascienda a señal positiva.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import estado_accion  # noqa: E402


# ── El mapa ──────────────────────────────────────────────────────────────────

def test_bajista_es_no_comprar_y_oculta_zonas():
    r = estado_accion.evaluar("BAJISTA")
    assert r["estado"] == "NO_COMPRAR"
    assert r["zonas_visibles"] is False


def test_indefinida_es_seguimiento_y_oculta_zonas():
    r = estado_accion.evaluar("INDEFINIDA")
    assert r["estado"] == "EN_SEGUIMIENTO"
    assert r["zonas_visibles"] is False


def test_sin_datos_es_seguimiento_no_una_senal():
    """No saber es una razón para mirar, no para comprar. Y desde luego no para
    presentar zonas."""
    r = estado_accion.evaluar("SIN_DATOS")
    assert r["estado"] == "EN_SEGUIMIENTO"
    assert r["zonas_visibles"] is False


def test_alcista_no_es_comprable_solo_pendiente_de_evaluar():
    """El punto entero del módulo: alcista abre la puerta a evaluar la entrada, no la
    concede."""
    r = estado_accion.evaluar("ALCISTA")
    assert r["estado"] == "SIN_EVALUAR"
    assert r["zonas_visibles"] is True


def test_una_direccion_desconocida_no_habilita_zonas():
    for basura in ("VOLATIL", "", None, 3):
        r = estado_accion.evaluar(basura)
        assert r["zonas_visibles"] is False, basura
        assert r["estado"] == "EN_SEGUIMIENTO", basura


# ── Desde los indicadores del dashboard ──────────────────────────────────────

def test_desde_indicadores_lee_las_medias_donde_estan():
    r = estado_accion.desde_indicadores(110, {"sma": {"50": 105, "200": 100}})
    assert r["tendencia"] == "ALCISTA"
    assert r["zonas_visibles"] is True


def test_desde_indicadores_sin_medias_oculta_zonas():
    for indicadores in ({}, None, {"sma": {}}, {"sma": {"50": 105}}):
        r = estado_accion.desde_indicadores(110, indicadores)
        assert r["tendencia"] == "SIN_DATOS", indicadores
        assert r["zonas_visibles"] is False, indicadores


def test_desde_indicadores_bajista():
    r = estado_accion.desde_indicadores(90, {"sma": {"50": 95, "200": 100}})
    assert r["estado"] == "NO_COMPRAR"


# ── Siempre hay motivo ───────────────────────────────────────────────────────

def test_todo_estado_viene_con_su_motivo():
    """Un NO_COMPRAR sin explicación es indistinguible de un fallo de la aplicación."""
    for direccion in ("ALCISTA", "BAJISTA", "INDEFINIDA", "SIN_DATOS"):
        r = estado_accion.evaluar(direccion)
        assert isinstance(r["motivo"], str) and len(r["motivo"]) > 40, direccion


# ── Lo que no puede existir todavía ──────────────────────────────────────────

def _fuente(nombre: str) -> str:
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", nombre)
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _solo_codigo(src: str) -> str:
    """El código que se EJECUTA: sin docstrings, sin comentarios y sin literales de texto.

    Los literales se quitan porque los motivos que ve el usuario mencionan «retroceso» o
    «tendencia» con toda la razón — son la explicación, no la lógica. Sin este recorte,
    el test estaría leyendo la prosa y fallaría por una frase bien escrita, que es
    exactamente el fallo que ya nos ha mordido en los tests del frontend.
    """
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    src = re.sub(r"#.*", "", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    return re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)


def test_no_existen_todavia_los_estados_de_compra():
    """COMPRAR_AHORA, COMPRAR_EN_ZONA y ESPERAR_CONFIRMACION exigen comparar el precio
    con la zona y definir qué es una confirmación. Ninguna de las dos cosas está
    decidida, y declarar constantes inalcanzables invita a rellenarlas por intuición.
    """
    codigo = _solo_codigo(_fuente("estado_accion.py"))
    for prematuro in ("COMPRAR_AHORA", "COMPRAR_EN_ZONA", "ESPERAR_CONFIRMACION"):
        assert prematuro not in codigo, f"{prematuro} no puede existir todavía"
    assert set(estado_accion.ESTADOS) == {"NO_COMPRAR", "EN_SEGUIMIENTO", "SIN_EVALUAR"}


def test_no_se_evalua_setup_ni_zona_ni_confirmacion():
    """Este commit es una separación de presentación. Si aquí aparece profundidad de
    retroceso, volumen de confirmación o comparación con la zona, ha dejado de serlo y
    se ha convertido en una primera versión encubierta del playbook."""
    codigo = _solo_codigo(_fuente("estado_accion.py")).lower()
    for fuera in ("entry_zone", "buy_levels", "vol_ratio", "retroceso", "confirmacion",
                  "setup", "playbook", "atr"):
        assert fuera not in codigo, f"'{fuera}' no pertenece a este commit"
