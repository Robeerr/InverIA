"""Confluencia: qué dicen tus fuentes cruzado con la elegibilidad estructural.

QUÉ RESUELVE

Tu Cerebro guarda quién menciona cada ticker y con qué sentimiento. `tendencia.py` dice
si la acción está estructuralmente en tendencia alcista. Este módulo cruza las dos cosas
y lo convierte en un dato.

Su gemelo importa tanto como él: el CHOQUE —tus fuentes empujan algo que no es
elegible— es el único estado donde la app puede evitarte una decisión mala en vez de
acompañarte en una buena.

QUÉ CAMBIÓ, Y POR QUÉ

Antes esto cruzaba fuentes con un SCORE del motor, y el corte estaba en 65/45. Ese score
sumaba en un mismo número crecimiento, valoración, punto de entrada, consenso, calidad y
momentum: un 60 podía significar «cara pero líder» o «barata pero muerta». Los umbrales
estaban calibrados sobre esa mezcla, así que medían un ruido bien medido.

Ahora el motor aporta un SÍ/NO estructural. Se pierde granularidad —ya no se puede decir
CUÁNTO acompaña— y se gana que la palabra signifique algo. Y no hace falta calibrar
nada: no hay ningún umbral de score que elegir.

El concepto de «MOTOR» desaparece. No se renombra: lo que aporta ya tiene nombre exacto,
que es elegibilidad, y conservar la palabra solo arrastraría su ambigüedad.

ES DESCRIPTIVA. NO AUTORIZA NADA

De un estado de confluencia NO se puede inferir una compra, un punto de entrada, una
zona, un stop ni un tamaño. Cruza una opinión externa con un estado estructural, y
ninguno de los dos insumos es una decisión de entrada: su cruce tampoco puede serlo sin
fabricar autoridad que ninguna de las partes tenía.

ACUERDO **consume** el veto de `tendencia.py`; no lo sustituye ni lo reemplaza. La
elegibilidad se decide en un solo sitio y no es este.

LAS REGLAS QUE NO SE NEGOCIAN

  - Sin menciones NO hay confluencia. Un ticker elegible del que nadie ha hablado no es
    un acuerdo: es una idea propia. Fabricar una coincidencia que no existe sería el
    peor fallo posible en un módulo que se llama así.
  - Sin tendencia clasificable es INSUFICIENTE, no NEUTRAL. Falta una de las dos partes,
    así que no se ha cruzado nada; «neutral» sugeriría que se compararon y empataron.
  - MIXTO —unas fuentes a favor y otras en contra— no es acuerdo ni choque. Que las
    fuentes discrepen entre ellas es información, y promediarla la borraría.
"""
from typing import Optional

import tendencia

# Fuentes DISTINTAS, no menciones: cuarenta correos del mismo boletín son una sola
# opinión repetida.
#
# PARÁMETRO HEREDADO, NO CALIBRADO. Se eligió en la misma sesión de medición que los
# umbrales de score que este módulo acaba de retirar. Sobrevive porque cuenta opiniones
# INDEPENDIENTES y no puntos de un score, así que su significado no dependía de lo que
# se ha ido — pero nadie ha comprobado que 2 discrimine mejor que 1. Queda pendiente de
# medir, y hoy no existe herramienta para hacerlo: la que había medía el eje del score.
MIN_FUENTES = 2

ESTADOS = ("ACUERDO", "CHOQUE", "NEUTRAL", "MIXTO", "INSUFICIENTE", "SIN_FUENTES")


def tono_de_fuentes(positivos: int, negativos: int) -> str:
    """FAVORABLE / DESFAVORABLE / MIXTO / SIN_SENTIDO, solo con las menciones.

    MIXTO no es neutro: es que unas fuentes lo ven bien y otras mal. Esa discrepancia es
    un dato, y un promedio la haría desaparecer.

    No cambia con el nuevo contrato: nunca dependió del score.
    """
    pos, neg = int(positivos or 0), int(negativos or 0)
    if pos and neg:
        return "MIXTO"
    if pos:
        return "FAVORABLE"
    if neg:
        return "DESFAVORABLE"
    return "SIN_SENTIDO"


def clasificar(n_fuentes: int, positivos: int, negativos: int,
               estado_tendencia: Optional[str]) -> str:
    """El estado de confluencia de un ticker.

    Fallo cerrado en los dos sentidos: ninguna ausencia de datos produce ACUERDO ni
    CHOQUE. Los dos estados que dicen algo exigen las dos partes presentes.
    """
    n_fuentes = int(n_fuentes or 0)
    if n_fuentes <= 0:
        return "SIN_FUENTES"

    tono = tono_de_fuentes(positivos, negativos)
    if tono == "MIXTO":
        # Las fuentes no se ponen de acuerdo entre ellas: no hay una opinión con la que
        # cruzar la elegibilidad. Se dice, en vez de resolverlo por mayoría.
        return "MIXTO"
    if tono == "SIN_SENTIDO":
        return "NEUTRAL"

    # SIGNIFICADO NUEVO. Antes INSUFICIENTE era «el motor no lo ha puntuado»; ahora es
    # «no se puede clasificar la tendencia». El concepto se conserva —falta una de las
    # dos opiniones— y solo cambia cuál falta.
    if estado_tendencia == "SIN_DATOS" or estado_tendencia not in tendencia.ESTADOS:
        return "INSUFICIENTE"

    bastantes = n_fuentes >= MIN_FUENTES
    elegible = tendencia.hay_tendencia_valida(estado_tendencia)

    if not bastantes:
        return "NEUTRAL"

    if tono == "FAVORABLE":
        if elegible:
            return "ACUERDO"
        if estado_tendencia == "BAJISTA":
            return "CHOQUE"
        # INDEFINIDA: ni una cosa ni otra. No es un choque porque no hay nada a lo que
        # oponerse — la acción no está en tendencia bajista, simplemente no está clara.
        return "NEUTRAL"

    # DESFAVORABLE: las fuentes lo evitan.
    #
    # Que sea elegible SÍ es un choque —opiniones opuestas—, con el mismo mínimo de
    # fuentes que el resto.
    #
    # Que tampoco sea elegible es un acuerdo, pero NEGATIVO, y se queda en NEUTRAL a
    # propósito: `ACUERDO` se lee en la interfaz como «esto merece tu atención», y usarlo
    # para «los dos coinciden en que no» invitaría a mirar justo lo que no hay que mirar.
    # Merece un estado propio; darle uno es una decisión de producto, no de umbral.
    if elegible:
        return "CHOQUE"
    return "NEUTRAL"


def describir(estado: str, n_fuentes: int, positivos: int, negativos: int) -> Optional[str]:
    """Una frase que dice qué se ha cruzado. DESCRIBE, no recomienda.

    Misma regla que en `tesis.py`: aquí no se dice qué hacer, se dice qué hay. Devuelve
    None cuando no hay nada que contar.
    """
    fuentes = f"{n_fuentes} fuente" + ("s" if n_fuentes != 1 else "")
    if estado == "ACUERDO":
        return f"{fuentes} lo ven bien y está en tendencia alcista."
    if estado == "CHOQUE":
        if positivos and not negativos:
            return f"{fuentes} lo ven bien, pero no está en tendencia alcista."
        return f"{fuentes} lo ven mal, pero sí está en tendencia alcista."
    if estado == "MIXTO":
        return f"Tus fuentes no coinciden: {positivos} a favor y {negativos} en contra."
    if estado == "INSUFICIENTE":
        return (f"{fuentes} lo mencionan; no hay histórico suficiente para saber si está "
                "en tendencia.")
    return None


def evaluar(n_fuentes: int, positivos: int, negativos: int,
            estado_tendencia: Optional[str]) -> dict:
    """El objeto que viaja en la respuesta.

    `tendencia` sustituye al antiguo `score_motor`. No es un renombrado: es otro dato,
    con otro significado y sin escala.
    """
    estado = clasificar(n_fuentes, positivos, negativos, estado_tendencia)
    return {
        "estado": estado,
        "texto": describir(estado, int(n_fuentes or 0), int(positivos or 0),
                           int(negativos or 0)),
        "n_fuentes": int(n_fuentes or 0),
        "positivos": int(positivos or 0),
        "negativos": int(negativos or 0),
        "tendencia": estado_tendencia if estado_tendencia in tendencia.ESTADOS else "SIN_DATOS",
    }
