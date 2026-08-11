"""Confluencia motor ↔ fuentes: cuándo tus datos y tus fuentes dicen lo mismo.

QUÉ RESUELVE

Tu Cerebro guarda quién menciona cada ticker y con qué sentimiento, y el motor guarda su
propio veredicto sobre el mismo ticker. Hasta ahora las dos opiniones viajaban juntas y
el cruce lo hacía la cabeza del lector: un chip verde al lado de un número de fuentes.

Este módulo lo convierte en un dato. Y su gemelo importa tanto como él: el CHOQUE —tus
fuentes empujan algo que tu motor evita— es el único estado donde la app puede evitarte
una decisión mala en vez de acompañarte en una buena.

LOS UMBRALES, Y DE DÓNDE SALEN

No están puestos a ojo: salen de medir la distribución real de las menciones con
`inspeccion_confluencia.py`, comparar cuatro cortes candidatos y elegir uno viendo qué
casos concretos caían en cada grupo.

    ≥2 fuentes distintas + motor ≥65  →  ACUERDO
    ≥2 fuentes distintas + motor <45  →  CHOQUE
    45 a 64,9                          →  NEUTRAL

Están aquí como constantes de módulo y no dentro de la función a propósito: se pueden
mirar, discutir y cambiar en un sitio, y el script de inspección los usa como valores por
defecto para poder barrer alternativas sin duplicar la lógica.

LO QUE NO MIDE TODAVÍA

El tercer eje —«además hay un nivel fuerte cerca»— no entra aún. Exige `buy_levels`, que
solo existe donde el motor ha corrido sobre el histórico. Cuando se añada, un ACUERDO con
el precio a un 2% de una zona de fuerza 100 valdrá más que uno a un 30%; hoy los dos
salen igual.

LAS REGLAS QUE NO SE NEGOCIAN

  - Sin menciones NO hay confluencia. Un ticker con score 95 del que nadie ha hablado no
    es un acuerdo: es una idea propia. Fabricar una coincidencia que no existe sería el
    peor fallo posible en un módulo que se llama así.
  - Sin veredicto del motor es INSUFICIENTE, no NEUTRAL. Falta una de las dos opiniones,
    así que no se ha cruzado nada; «neutral» sugeriría que se compararon y empataron.
  - MIXTO —unas fuentes a favor y otras en contra— no es acuerdo ni choque. Que las
    fuentes discrepen entre ellas es información, y promediarla la borraría.
"""
from typing import Optional

# ── Umbrales del corte «medio», elegido sobre la distribución real ───────────
MIN_FUENTES = 2          # fuentes DISTINTAS, no menciones: 40 correos del mismo boletín
                         # son una sola opinión repetida
SCORE_ACUERDO = 65       # el motor acompaña
SCORE_CHOQUE = 45        # el motor lo evita; entre 45 y 64,9 no dice ni una cosa ni otra

ESTADOS = ("ACUERDO", "CHOQUE", "NEUTRAL", "MIXTO", "INSUFICIENTE", "SIN_FUENTES")


def tono_de_fuentes(positivos: int, negativos: int) -> str:
    """FAVORABLE / DESFAVORABLE / MIXTO / SIN_SENTIDO, solo con las menciones.

    MIXTO no es neutro: es que unas fuentes lo ven bien y otras mal. Esa discrepancia es
    un dato, y un promedio la haría desaparecer.
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
               score: Optional[float], umbrales: Optional[dict] = None) -> str:
    """El estado de confluencia de un ticker.

    `umbrales` existe para que el script de inspección pueda barrer cortes alternativos
    sin duplicar esta lógica. En producción no se pasa: manda el corte elegido.
    """
    u = umbrales or {}
    min_fuentes = u.get("min_fuentes", MIN_FUENTES)
    score_acuerdo = u.get("score_alto", SCORE_ACUERDO)
    score_choque = u.get("score_bajo", SCORE_CHOQUE)

    n_fuentes = int(n_fuentes or 0)
    if n_fuentes <= 0:
        return "SIN_FUENTES"

    tono = tono_de_fuentes(positivos, negativos)
    if tono == "MIXTO":
        # Las fuentes no se ponen de acuerdo entre ellas: no hay una opinión con la que
        # cruzar la del motor. Se dice, en vez de resolverlo por mayoría.
        return "MIXTO"
    if tono == "SIN_SENTIDO":
        return "NEUTRAL"

    if score is None:
        return "INSUFICIENTE"

    bastantes = n_fuentes >= min_fuentes
    acompana = score >= score_acuerdo
    evita = score < score_choque

    if tono == "FAVORABLE":
        if bastantes and acompana:
            return "ACUERDO"
        if bastantes and evita:
            return "CHOQUE"
        return "NEUTRAL"

    # DESFAVORABLE: las fuentes lo evitan.
    #
    # Que el motor lo puntúe alto SÍ es un choque —opiniones opuestas—, y va con el mismo
    # mínimo de fuentes que el resto.
    #
    # Que el motor también lo evite es un acuerdo, pero NEGATIVO, y se queda en NEUTRAL a
    # propósito: `ACUERDO` se lee en la interfaz como «esto merece tu atención», y usarlo
    # para «los dos coinciden en que no» invitaría a mirar justo lo que no hay que mirar.
    # Merece un estado propio; darle uno es una decisión de producto, no de umbral.
    if bastantes and acompana:
        return "CHOQUE"
    return "NEUTRAL"


def describir(estado: str, n_fuentes: int, positivos: int, negativos: int,
              score: Optional[float]) -> Optional[str]:
    """Una frase que dice qué se ha cruzado. DESCRIBE, no recomienda.

    Misma regla que en `tesis.py`: aquí no se dice qué hacer, se dice qué hay. Devuelve
    None cuando no hay nada que contar.
    """
    fuentes = f"{n_fuentes} fuente" + ("s" if n_fuentes != 1 else "")
    if estado == "ACUERDO":
        return f"{fuentes} lo ven bien y tu motor acompaña ({score:.0f}/100)."
    if estado == "CHOQUE":
        if positivos and not negativos:
            return f"{fuentes} lo ven bien, pero tu motor lo evita ({score:.0f}/100)."
        return f"{fuentes} lo ven mal, pero tu motor lo puntúa alto ({score:.0f}/100)."
    if estado == "MIXTO":
        return f"Tus fuentes no coinciden: {positivos} a favor y {negativos} en contra."
    if estado == "INSUFICIENTE":
        return f"{fuentes} lo mencionan; tu motor aún no lo ha puntuado."
    return None


def evaluar(n_fuentes: int, positivos: int, negativos: int,
            score: Optional[float], umbrales: Optional[dict] = None) -> dict:
    """El objeto que viaja en la respuesta. Aditivo: no sustituye a nada."""
    estado = clasificar(n_fuentes, positivos, negativos, score, umbrales)
    return {
        "estado": estado,
        "texto": describir(estado, int(n_fuentes or 0), int(positivos or 0),
                           int(negativos or 0), score),
        "n_fuentes": int(n_fuentes or 0),
        "positivos": int(positivos or 0),
        "negativos": int(negativos or 0),
        "score_motor": score,
    }
