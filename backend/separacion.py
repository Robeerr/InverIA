"""Un número, una pregunta. La separación descriptiva del score mezclado.

QUÉ RESUELVE

`opportunities._potential_score` responde a la vez a «¿está barata?», «¿crece?»,
«¿lidera?», «¿qué opinan los analistas?» y «¿es buen punto de entrada?», y devuelve un
solo número. Un 60 puede significar «cara pero líder» o «barata pero muerta», y las dos
cosas se presentan igual. Peor: valoración y momentum son factores negativamente
correlacionados —una acción barata suele serlo PORQUE ha caído—, así que en ese número
una debilidad de tendencia se puede compensar con un descuento.

Este módulo produce la información SEPARADA. No sustituye nada todavía.

QUÉ NO HACE, Y ES LA MITAD DEL PUNTO

  · NO produce un `tendencia_score`. Las dos medidas que describen la tendencia —el
    retorno a 52 semanas y la fuerza relativa— hoy no son puntos en ninguna parte: son
    un multiplicador de tres escalones. Convertirlas en un score exige decidir cuánto
    pesa cada una, y ese peso no está medido. Se emiten los INSUMOS sin agregar.

  · NO produce un total, ni reconstruible. `calidad_puntos` no se suma con nada.

  · NO puntúa la valoración ni el consenso. Los dos pasan a descriptivos: viajan como
    dato, con cero peso. Si algún día el consenso merece gobernar una estrategia, será
    una decisión validada, no un peso heredado sin que nadie se diera cuenta.

  · NO produce un índice 0-100. Se emiten `puntos` y `maximo` por separado, porque un
    100 se lee como «calidad perfecta» y eso es una afirmación que nadie ha validado.
    Quien quiera un índice lo divide, sabiendo lo que divide.

SOBRE LOS PESOS

Los pesos (30 para ventas, 12 para el BPA, 8 para la calidad del negocio) y los topes
de saturación (60%, 50%, 25%, 30%) se heredan TAL CUAL de la lógica existente, para que
esta separación no cambie ningún comportamiento.

NO son pesos óptimos ni una calibración: nadie los ha medido. Que las ventas pesen casi
cuatro veces más que la rentabilidad del negocio no lo decidió ningún dato. Se conservan
porque cambiarlos aquí mezclaría dos trabajos —separar y calibrar— y el segundo necesita
un backtest que todavía no existe.

EL VETO NO ESTÁ AQUÍ

`calidad_puntos` no puede vetar nada, ni rescatar una acción que falle la tendencia. La
elegibilidad estructural es de `tendencia.py` y de nadie más.
"""
from typing import Optional

# Topes y pesos HEREDADOS de `opportunities._potential_score_detalle`. Se replican para
# no tocar la ruta vieja; ninguno está validado.
_TOPE_VENTAS, _PESO_VENTAS = 60.0, 30.0
_TOPE_EPS, _PESO_EPS = 50.0, 12.0
_TOPE_MARGEN, _PESO_MARGEN = 25.0, 3.0
_TOPE_ROE, _PESO_ROE = 30.0, 3.0
_DEUDA_BAJA, _DEUDA_MEDIA = 0.5, 1.5
_PESO_DEUDA_BAJA, _PESO_DEUDA_MEDIA = 2.0, 1.0

CALIDAD_MAXIMO = _PESO_VENTAS + _PESO_EPS + _PESO_MARGEN + _PESO_ROE + _PESO_DEUDA_BAJA


def _crece(valor, tope, peso) -> float:
    """Puntos por una métrica de crecimiento, saturada en `tope`. Igual que la ruta vieja."""
    if valor is None or valor <= 0:
        return 0.0
    return min(valor, tope) / tope * peso


def calidad(rev_g=None, eps_g=None, net_margin=None, roe=None,
            debt_to_equity=None) -> dict:
    """La calidad fundamental del negocio, y SOLO eso.

    No entra la valoración —lo barato no es una virtud del negocio, es un precio—, ni el
    consenso —que es opinión de terceros—, ni nada de tendencia. Que esta función no
    reciba `ret_52w` ni `rel_strength` no es un olvido: es la garantía de que una
    debilidad de tendencia no puede penalizar la calidad ni al revés.

    Devuelve `puntos` y `maximo` por separado, nunca un índice.
    """
    p_ventas = _crece(rev_g, _TOPE_VENTAS, _PESO_VENTAS)
    p_eps = _crece(eps_g, _TOPE_EPS, _PESO_EPS)
    p_margen = _crece(net_margin, _TOPE_MARGEN, _PESO_MARGEN)
    p_roe = _crece(roe, _TOPE_ROE, _PESO_ROE)

    p_deuda = 0.0
    if debt_to_equity is not None and debt_to_equity >= 0:
        if debt_to_equity < _DEUDA_BAJA:
            p_deuda = _PESO_DEUDA_BAJA
        elif debt_to_equity < _DEUDA_MEDIA:
            p_deuda = _PESO_DEUDA_MEDIA

    return {
        "puntos": round(p_ventas + p_eps + p_margen + p_roe + p_deuda, 2),
        "maximo": CALIDAD_MAXIMO,
        "componentes": [
            {"clave": "crecimiento_ventas", "puntos": round(p_ventas, 2), "maximo": _PESO_VENTAS},
            {"clave": "crecimiento_eps", "puntos": round(p_eps, 2), "maximo": _PESO_EPS},
            {"clave": "margen_neto", "puntos": round(p_margen, 2), "maximo": _PESO_MARGEN},
            {"clave": "roe", "puntos": round(p_roe, 2), "maximo": _PESO_ROE},
            {"clave": "deuda", "puntos": round(p_deuda, 2), "maximo": _PESO_DEUDA_BAJA},
        ],
        # Que los pesos viajen con el dato: quien lea esto en un año no tiene por qué
        # saber que no están calibrados si no se lo dice el propio dato.
        "pesos_validados": False,
    }


def valoracion(pe=None, rev_g=None) -> dict:
    """La valoración, DESCRIPTIVA. Cero puntos, aquí y en cualquier otro sitio.

    Las bandas del PEG se heredan de la ruta vieja y tampoco están validadas; sirven para
    poner una palabra al número, no para puntuar. Si algún día existe un playbook de
    valor, el PEG será un input suyo, no un componente clandestino de otro score.
    """
    etiqueta, peg = "sin datos", None
    if pe is not None and pe > 0 and rev_g and rev_g > 0:
        peg = round(pe / rev_g, 2)
        if peg < 1:
            etiqueta = "infravalorada (PEG<1)"
        elif peg < 1.5:
            etiqueta = "precio atractivo (PEG<1.5)"
        elif peg < 2.5:
            etiqueta = "valoración razonable"
        elif peg < 4:
            etiqueta = "algo cara"
        else:
            etiqueta = "cara (PEG>4)"
    elif pe is not None and pe <= 0:
        etiqueta = "sin beneficios (PER negativo)"
    return {"etiqueta": etiqueta, "peg": peg, "pe": pe, "puntos": 0.0}


def consenso(cons_score=None, cons_label=None) -> dict:
    """El consenso de analistas, DESCRIPTIVO. Cero puntos.

    Pasa el dato tal cual, SIN etiqueta propia ni bandas. Cualquier corte del tipo
    «≥70 es fuerte» sería un umbral nuevo, y en 5a no se introduce ninguno. Además la
    evidencia publicada dice que el NIVEL del consenso no predice retornos —solo su
    cambio, y débilmente—, así que ponerle bandas sugeriría una capacidad que no tiene.

    Si algún día merece gobernar algo, será tras validarlo, no por un peso heredado.
    """
    return {"score": cons_score, "etiqueta": cons_label, "puntos": 0.0}


def tendencia_insumos(ret_26w=None, ret_52w=None, rel_strength=None) -> dict:
    """Los datos de tendencia SIN AGREGAR. No hay `tendencia_score` y es deliberado.

    Agregarlos exige decidir cuánto pesa el retorno de seis meses frente al de un año y
    frente a la fuerza relativa. Ese reparto no está medido, y un número con pesos
    inventados sería el score universal otra vez, más pequeño y con mejor nombre.

    Se emiten crudos para que el experimento sobre el histórico pueda decidir después qué
    significan y cómo se combinan — si es que se combinan.

    OJO: nada de esto es elegibilidad. Que una acción tenga buenos insumos no la hace
    comprable; eso lo dice `tendencia.py` y solo él.
    """
    return {
        "ret_26w": ret_26w,
        "ret_52w": ret_52w,
        "rel_strength": rel_strength,
        "agregado": None,   # explícito: no hay score, y no es que falte por calcular
    }


def campos(rev_g=None, eps_g=None, pe=None, cons_score=None, cons_label=None,
           ret_26w=None, ret_52w=None, rel_strength=None,
           net_margin=None, roe=None, debt_to_equity=None) -> dict:
    """Los cuatro bloques separados, listos para viajar en una fila del screener.

    Devuelve un diccionario SIN total y sin ninguna clave que invite a sumar. Si alguna
    vez hace falta un único número para ordenar una pantalla, la decisión correcta es
    elegir qué pregunta responde esa pantalla y usar el campo que le corresponde — no
    fabricar aquí un total para que la interfaz quede cómoda.
    """
    return {
        "calidad": calidad(rev_g=rev_g, eps_g=eps_g, net_margin=net_margin,
                           roe=roe, debt_to_equity=debt_to_equity),
        "valoracion": valoracion(pe=pe, rev_g=rev_g),
        "consenso": consenso(cons_score=cons_score, cons_label=cons_label),
        "tendencia_insumos": tendencia_insumos(ret_26w=ret_26w, ret_52w=ret_52w,
                                               rel_strength=rel_strength),
    }
