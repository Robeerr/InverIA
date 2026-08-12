"""En qué punto está una acción respecto a una posible compra. Solo el primer filtro.

QUÉ ES Y QUÉ NO ES

Este módulo traduce la DIRECCIÓN de la tendencia a un estado presentable, y nada más.
No sabe si hay retroceso, ni si el precio está en zona, ni si el volumen confirma. No
es una primera versión del playbook: es la separación entre «esta acción ni siquiera
pasa el primer filtro» y «pasa el primer filtro, y lo demás está por evaluar».

LA DISTINCIÓN QUE JUSTIFICA QUE EXISTA

    tendencia ALCISTA  ≠  comprable

Una acción alcista solo ha superado la condición previa. No implica que tenga setup,
zona válida ni entrada. Por eso el estado que le corresponde es SIN_EVALUAR y no algo
como «apta» o «candidata»: cualquiera de esas palabras se lee como un permiso, y aquí
no se ha concedido ninguno.

Es la razón de que NO existan todavía COMPRAR_AHORA, COMPRAR_EN_ZONA ni
ESPERAR_CONFIRMACION. Los tres exigen comparar el precio con la zona y definir qué
cuenta como confirmación, y ninguna de las dos cosas está decidida. Declarar constantes
que hoy son inalcanzables invitaría a rellenarlas por intuición, que es exactamente lo
que estamos evitando.

LA AUSENCIA DE DATOS NO ES UNA SEÑAL

SIN_DATOS e INDEFINIDA van las dos a EN_SEGUIMIENTO. No se ascienden a nada positivo
por no saber: no saber es una razón para mirar, no para comprar.
"""
from typing import Optional

import tendencia

ESTADOS = ("NO_COMPRAR", "EN_SEGUIMIENTO", "SIN_EVALUAR")

# Qué estado corresponde a cada dirección. Como tabla y no como cadena de `if` para que
# se pueda leer entera de un vistazo y para que añadir una dirección nueva obligue a
# decidir su estado en vez de caer en un `else` silencioso.
_POR_TENDENCIA = {
    "BAJISTA": "NO_COMPRAR",
    "INDEFINIDA": "EN_SEGUIMIENTO",
    "SIN_DATOS": "EN_SEGUIMIENTO",
    "ALCISTA": "SIN_EVALUAR",
}

_MOTIVOS = {
    "BAJISTA": ("La acción está por debajo de su media de 200 sesiones y la de 50 también. "
                "Mientras siga así, sus soportes no son zonas de compra: son las siguientes "
                "paradas de una caída."),
    "INDEFINIDA": ("La acción no está en tendencia bajista, pero tampoco alcista: el precio y "
                   "la media de 50 no coinciden respecto a la de 200. Suele ser una acción "
                   "saliendo de un suelo, y eso se vigila antes de comprarse."),
    "SIN_DATOS": ("No hay histórico suficiente para saber en qué tendencia está — hacen falta "
                  "200 sesiones. No se presenta una zona de compra sobre algo que no se ha "
                  "podido comprobar."),
    "ALCISTA": ("La acción está en tendencia alcista. Es el primer filtro, no una compra: "
                "queda por evaluar si hay un retroceso aprovechable y a qué precio."),
}


def evaluar(estado_tendencia: Optional[str]) -> dict:
    """El estado presentable de una acción a partir de su dirección.

    Devuelve también `zonas_visibles`, que es la decisión de PRESENTACIÓN: si las zonas
    de compra se pueden enseñar como oportunidades. Va aquí y no en el servidor para que
    la respuesta no se pueda contradecir con el estado — un NO_COMPRAR con la lista de
    zonas debajo sería peor que cualquiera de las dos cosas por separado.
    """
    dir_ = estado_tendencia if estado_tendencia in _POR_TENDENCIA else "SIN_DATOS"
    return {
        "estado": _POR_TENDENCIA[dir_],
        "motivo": _MOTIVOS[dir_],
        "tendencia": dir_,
        "zonas_visibles": tendencia.hay_tendencia_valida(dir_),
    }


def desde_indicadores(precio, indicadores: Optional[dict]) -> dict:
    """El estado a partir del precio y los indicadores ya calculados del dashboard.

    Las medias llegan dentro de `indicadores["sma"]` con las claves "50" y "200", que es
    la forma que ya usan `compute_buy_levels` y el resto del servidor. Se lee aquí para
    que ningún consumidor tenga que conocer esa estructura.
    """
    sma = ((indicadores or {}).get("sma") or {})
    return evaluar(tendencia.clasificar(precio, sma.get("50"), sma.get("200")))
