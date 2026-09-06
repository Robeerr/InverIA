"""Avisar cuando el veto de tendencia SE LEVANTA. La otra mitad del veto.

EL HUECO QUE CIERRA

`veto_compra` sabe decir que no. Analizas una acción, sale «Compra vetada por la
tendencia», el plan se queda sin niveles y el botón de Cartera no guarda nada. Correcto:
esa acción está por debajo de su SMA200 y sus soportes no son zonas de compra.

Pero ahí se acababa. El veto no caduca solo ni avisa de nada, así que la única forma de
enterarse de que una acción vetada ya se puede comprar era volver a analizarla a mano, sin
saber cuándo. En la práctica eso significa no enterarse: nadie reanaliza a ciegas una lista
de acciones que le dijeron que no compre.

El vigilante del Chartista (`server._chartist_vigilante`) tampoco lo cubría, y merece la
pena entender por qué, porque parece que sí. Ese bucle solo recorre
`_simbolos_que_te_importan()` — watchlist más entradas activas de la Cartera. Una acción
vetada no está en la Cartera precisamente porque el veto impidió guardarla, así que el
vigilante no la mira nunca. El aviso ESPERAR → COMPRAR que tiene preparado no puede
dispararse sobre la acción que más falta hace.

QUÉ VIGILA, Y QUÉ NO

La ESTRUCTURA, no la opinión. Este módulo no pregunta si el Chartista recomienda comprar:
pregunta si la acción ha vuelto a tendencia alcista, que es exactamente la condición que la
bloqueaba. Son dos avisos distintos y los dos tienen sitio:

    vigilancia_veto   →  «ya PUEDES comprarla»   (se levantó la prohibición)
    _chartist_vigilante →  «el Chartista dice que COMPRES»  (hay una opinión a favor)

Fundirlos convertiría el primero en una recomendación, que es justo lo que no es. Que una
acción deje de estar vetada no dice que haya que comprarla; dice que la decisión vuelve a
ser tuya.

POR QUÉ ES BARATO

La condición se lee de `market_data.tendencia_de`, que trabaja sobre el histórico diario
gratuito y cacheado. Ni Finnhub ni Gemini. Vigilar una acción cuesta lo mismo que ya cuesta
aplicarle el veto cuando la miras, así que el bucle puede pasar por muchas sin que aparezca
en ninguna factura. Es la razón de que el aviso mire la tendencia y no el veredicto del
Chartista: vigilar eso último sí costaría una llamada de IA por acción y vuelta.

SE AVISA UNA VEZ Y LA VIGILANCIA SE RETIRA

No es ahorro, es la definición de la tarea. Lo que se pidió fue «avísame cuando se pueda
comprar», y eso ocurre una vez. Dejar la vigilancia puesta convertiría una acción que
oscila alrededor de su SMA200 en un aviso por cada cruce, que es ruido con formato de
señal. Si vuelve a vetarse y sigue interesando, se rearma desde la pantalla — un gesto
consciente, igual que el primero.
"""
from typing import Optional

import tendencia
import veto_compra

# Cuántas acciones se pueden vigilar a la vez. No es un límite técnico —cada vuelta cuesta
# una lectura de histórico cacheado— sino de atención: una lista de vigilancia que no cabe
# en la cabeza deja de ser una lista de vigilancia y pasa a ser una segunda watchlist que
# nadie repasa. Si se llena, el mensaje pide retirar algo en vez de crecer en silencio.
MAX_VIGILADAS = 40


def puede_vigilarse(estado_tendencia: Optional[str]) -> bool:
    """¿Tiene sentido armar una vigilancia sobre una acción en este estado?

    Sí en todo lo que NO es alcista, y ahí entran dos casos que conviene no separar:

        BAJISTA / INDEFINIDA  →  vetada o sin autorizar. Es el caso para el que se hizo.
        SIN_DATOS             →  no se ha podido comprobar. También vale la pena.

    SIN_DATOS entra a propósito. Una salida a bolsa reciente no tiene 200 cierres y no los
    tendrá hasta dentro de meses; el día que los tenga, esta vigilancia es la única cosa en
    todo el sistema que se va a dar cuenta. Y es seguro porque disparar exige ALCISTA, no
    exige «ya no es SIN_DATOS»: mientras no haya histórico suficiente la condición no se
    cumple y no sale ningún aviso.

    Lo que se rechaza es armar sobre una acción YA alcista, y no por ahorrar trabajo: esa
    vigilancia se cumpliría en la primera vuelta y mandaría un aviso de que se levantó un
    veto que nunca existió. Un aviso falso al teléfono cuesta más que no tenerlo.
    """
    return not tendencia.hay_tendencia_valida(estado_tendencia)


def se_levanta(estado_tendencia: Optional[str]) -> bool:
    """¿Ha vuelto esta acción a la tendencia que autoriza comprarla?

    Se pregunta a `tendencia`, que es el dueño de la regla, y no se compara con la cadena
    «ALCISTA» aquí. El motivo es el mismo que ya explica `veto_compra.hay_veto`: si algún
    día la condición se amplía —con la pendiente de la SMA200 medida, por ejemplo—, el
    aviso tiene que moverse con ella o pasaría a avisar de algo que el veto ya no considera
    suficiente, y nadie lo notaría hasta comprar.

    Fallo cerrado por herencia: `hay_tendencia_valida` solo dice que sí ante ALCISTA, así
    que SIN_DATOS, None y cualquier etiqueta desconocida NO disparan. Un aviso que se
    escapara por un histórico que no cargó sería peor que el silencio.
    """
    return tendencia.hay_tendencia_valida(estado_tendencia)


def mensaje(symbol: str, estado_previo: Optional[str] = None) -> str:
    """El aviso que llega al teléfono.

    Dice lo que ha pasado y NO dice qué hacer. La diferencia entre «ya se puede comprar» y
    «cómprala» es la que separa este módulo de una recomendación, y en un mensaje de cuatro
    líneas leído de pasada esa distinción se pierde si no se escribe a propósito.

    Se nombra el estado del que viene porque cambia lo que significa el aviso: salir de
    BAJISTA es un giro, y salir de SIN_DATOS es que por fin hay histórico para comprobarlo.
    """
    de = {
        "BAJISTA": "venía de tendencia bajista",
        "INDEFINIDA": "venía sin tendencia definida",
        "SIN_DATOS": "antes no había histórico suficiente para comprobarlo",
    }.get(estado_previo or "")
    linea = f"✅ {symbol}: se ha levantado el veto de tendencia."
    if de:
        linea += f" ({de.capitalize()}.)"
    return (f"{linea}\n"
            "Ya está por encima de su SMA200 y de la SMA50, así que sus soportes vuelven a "
            "ser zonas de compra y puedes añadirle niveles en la Cartera.\n"
            "No es una recomendación: es que la prohibición ha desaparecido. La decisión "
            "vuelve a ser tuya.")


def motivo_no_armable(estado_tendencia: Optional[str]) -> str:
    """Por qué no se puede vigilar esta acción. Solo se llama cuando ya se sabe que no.

    Un único caso posible —ya es alcista—, pero se redacta aquí y no en el endpoint para
    que el día que `puede_vigilarse` acepte menos cosas el texto viva junto a la regla que
    lo provoca.
    """
    return ("Esta acción ya está en tendencia alcista: no hay ningún veto que levantar. "
            "Puedes añadirle niveles en la Cartera ahora mismo.")


# Se re-exporta para que quien vigila no tenga que importar `veto_compra` solo para nombrar
# el estado que no se pudo comprobar. La lista de estados sigue teniendo un único dueño.
TENDENCIA_NO_VERIFICABLE = veto_compra.TENDENCIA_NO_VERIFICABLE
