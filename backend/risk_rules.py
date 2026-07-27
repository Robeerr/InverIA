"""Reglas de gestión de riesgo deterministas (independientes del LLM).

El track record reveló que el motor colocaba stops demasiado anchos (perder ~7.6%
para ganar ~4.6% en TP1 → R/R 0.61). Estas reglas garantizan un R/R sano ciñendo
el stop, sin depender de que el modelo cumpla el prompt.
"""

# Relación riesgo/recompensa mínima exigida en TP1. 2.0, no 1.5: el umbral de rentabilidad es
# 1/(1+R), así que 1,5:1 exige un 40% de aciertos y los swing traders rondan el 40-50% — queda
# justo en la línea de no ganar nada antes de comisiones. A 2:1 basta un 33%.
# Debe coincidir con server.MIN_RR y con el mínimo que pide SYSTEM_PROMPT.
# Ceñir el stop para cumplirlo es seguro aquí SOLO porque _enforce_rr aplica después un clamp
# de distancia mínima (>=1×ATR o 2%) que siempre gana: nunca se produce un stop de ruido.
RR_MIN = 2.0


def min_rr_stop(entry, tp1, stop, rr_min: float = RR_MIN):
    """Devuelve el stop ajustado para cumplir un R/R mínimo en TP1, o el stop original
    si ya lo cumple (o si los datos no son válidos). SOLO tensa el stop hacia la
    entrada (nunca lo afloja), reduciendo la pérdida potencial.

    entry/tp1/stop: precios (float). Devuelve (nuevo_stop, ajustado: bool).
    """
    try:
        entry, tp1, stop = float(entry), float(tp1), float(stop)
    except (TypeError, ValueError):
        return stop, False
    reward = tp1 - entry
    risk = entry - stop
    if reward <= 0 or risk <= 0:
        return stop, False
    if reward / risk >= rr_min:
        return stop, False
    nuevo = round(entry - reward / rr_min, 2)
    if nuevo > stop:  # solo tensar
        return nuevo, True
    return stop, False
