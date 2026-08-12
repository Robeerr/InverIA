"""Dirección estructural de la tendencia: la pregunta previa a cualquier zona de compra.

POR QUÉ EXISTE

Hasta ahora la misma pregunta se contestaba de tres formas distintas según quién
preguntara:

  - `opportunities.py` tenía un guardián que MULTIPLICA el score (×0,75 / ×0,55).
  - `signal_table.py` no tenía ninguna: una alerta de COMPRA se disparaba porque el
    precio cruzaba un nivel, con la acción en caída libre si hacía falta.
  - La página de acción tampoco: `levels_engine` calcula zonas por debajo del precio
    sin mirar en qué dirección va la acción.

Tres comportamientos para una sola pregunta es la definición de regla duplicada. Aquí
se contesta una vez.

LA REGLA, Y POR QUÉ ES ESTA Y NO OTRA

    ALCISTA  =  precio > SMA200  Y  SMA50 > SMA200
    BAJISTA  =  precio < SMA200  Y  SMA50 < SMA200

Dos comparaciones estructurales. Lo importante no es lo que incluye, sino lo que deja
fuera A PROPÓSITO: no hay pendiente de la SMA200, ni número de meses, ni distancia
mínima a las medias, ni ADX.

El motivo es que este módulo tiene que poder entrar en producción SIN backtest, y eso
solo se sostiene si no hay ni un número que elegir. En cuanto se añade «SMA200
ascendente durante N sesiones» aparece N, y N no lo puede decidir un paper de otro
mercado y otra década: hay que medirlo sobre nuestro histórico. Esas extensiones viven
en `calibracion.py` como pendientes, no aquí como suposiciones.

Que no haya parámetros es la razón por la que este commit es seguro.

DIRECCIÓN NO ES FUERZA

Este módulo dice HACIA DÓNDE va la acción, no CUÁNTO. «Va mejor que el mercado» o
«lidera su sector» son otra medida —la calidad de la tendencia— y viven en otro sitio.
Mezclarlas aquí crearía justo lo que estamos desmontando: un número que responde a dos
preguntas a la vez y en el que una puede compensar a la otra.

FALLO CERRADO

Si falta cualquiera de los tres datos, el estado es SIN_DATOS y NO habilita una compra.
Es deliberado: una acción con menos de 200 sesiones de histórico —una salida a bolsa
reciente— dejará de generar alertas de compra. Preferimos no autorizar lo que no
podemos comprobar antes que autorizarlo por defecto.
"""
from typing import Optional

ESTADOS = ("ALCISTA", "BAJISTA", "INDEFINIDA", "SIN_DATOS")


def _num(x) -> Optional[float]:
    """El valor como número, o None. NaN cuenta como ausencia, no como número.

    Sin la comprobación `v == v`, un NaN de pandas atravesaría las comparaciones
    devolviendo False en todas y la acción saldría INDEFINIDA en vez de SIN_DATOS —
    que son dos cosas distintas: «no encaja en ningún patrón» y «no lo sé».
    """
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def clasificar(precio, sma50, sma200) -> str:
    """La dirección estructural de la acción.

    INDEFINIDA no es un término medio entre alcista y bajista: es que las dos señales
    no coinciden. Un precio por encima de la SMA200 con la SMA50 por debajo suele ser
    una acción saliendo de un suelo, y una acción saliendo de un suelo no es lo mismo
    que una en tendencia — merece vigilancia, no compra.
    """
    p, s50, s200 = _num(precio), _num(sma50), _num(sma200)
    if p is None or s50 is None or s200 is None:
        return "SIN_DATOS"
    if p <= 0 or s50 <= 0 or s200 <= 0:
        return "SIN_DATOS"

    if p > s200 and s50 > s200:
        return "ALCISTA"
    if p < s200 and s50 < s200:
        return "BAJISTA"
    return "INDEFINIDA"


def hay_tendencia_valida(estado: str) -> bool:
    """¿Autoriza este estado a presentar una compra?

    Solo ALCISTA. Se escribe como función y no como `estado == "ALCISTA"` repetido por
    ahí para que el día que la regla se amplíe —con la pendiente de la SMA200 ya
    medida, por ejemplo— cambie en un sitio y no en cinco.
    """
    return estado == "ALCISTA"


def desde_cierres(cierres) -> str:
    """La tendencia a partir de una serie de cierres diarios, de más antiguo a más nuevo.

    Es el atajo para quien tiene el histórico pero no los indicadores calculados — el
    caso del bucle de alertas, que trabaja desde la lista de la Cartera y una cotización
    y nunca ha tenido un `compute_all` a mano.

    Medias SIMPLES, iguales a las que ya usa `_buy_zones` en chartist.py. Con menos de
    200 cierres devuelve SIN_DATOS: calcular una «SMA200» con 120 sesiones sería
    inventarse el dato que precisamente sirve para no inventar.
    """
    try:
        serie = [c for c in (cierres or []) if _num(c) is not None]
    except TypeError:
        return "SIN_DATOS"
    if len(serie) < 200:
        return "SIN_DATOS"
    serie = [float(c) for c in serie]
    sma50 = sum(serie[-50:]) / 50
    sma200 = sum(serie[-200:]) / 200
    return clasificar(serie[-1], sma50, sma200)
