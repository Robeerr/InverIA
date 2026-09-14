"""Los números que todavía no tenemos derecho a poner.

QUÉ ES ESTO

Una lista de umbrales que el sistema NECESITARÁ y que hoy valen None a propósito. No es
un fichero de configuración pendiente de rellenar: es la declaración explícita de que
cada uno de estos números exige un experimento sobre NUESTRO histórico antes de existir.

POR QUÉ NO SE COPIAN

Los métodos documentados traen umbrales concretos: crecimiento del beneficio por encima
del 25%, fuerza relativa mínima de 70, precio dentro del 25% de su máximo anual, volumen
de dos a tres veces la media. Todos son verificables y todos vienen de otro mercado,
otra década y otro universo de acciones. Copiarlos daría una aplicación que parece
rigurosa y que en realidad no ha medido nada.

La DIRECCIÓN de cada regla sí está documentada —comprar en tendencia, exigir volumen en
la confirmación— y esa parte ya está en producción, precisamente porque no lleva
números: `tendencia.py` no tiene ni un umbral elegible, y por eso pudo entrar sin
backtest.

NINGÚN VALOR POR DEFECTO. NUNCA.

Un `or 0`, un `or 0.5` o un `if x > (UMBRAL or 30)` convierte la ausencia de dato en un
número inventado, y encima uno que nadie ha discutido porque está escondido en una
expresión. Si un consumidor necesita uno de estos valores y no lo hay, la respuesta
correcta es degradar visiblemente —no evaluar esa condición, decirlo— no adivinar.

`exigir()` está para eso: falla ruidosamente antes que devolver un número falso.
"""
from typing import Optional


class SinCalibrar(RuntimeError):
    """Se ha pedido un umbral que todavía no se ha medido."""


# ── Selección ────────────────────────────────────────────────────────────────

RS_PERCENTIL_MINIMO: Optional[float] = None
"""Percentil de fuerza relativa por debajo del cual una acción no es candidata.

MIDE: la distribución de resultados de nuestras señales pasadas segmentada por el
percentil de fuerza relativa del símbolo en la fecha de la señal. El corte es donde las
poblaciones dejan de distinguirse, no donde el resultado histórico se maximiza.

BLOQUEADO POR: hoy `relative_strength` es un diferencial contra SPY, no un percentil.
Sin un universo con el que comparar, no existe el concepto de «percentil 70».
"""

DISTANCIA_MAX_A_MAXIMO_52S: Optional[float] = None
"""Distancia máxima al máximo de 52 semanas para considerar una acción candidata.

MIDE: retorno posterior de las señales agrupado por distancia al máximo en la fecha.

NO COPIAR el 25% de Minervini. Y hay un motivo concreto para desconfiar de nuestra
intuición aquí: el componente «punto de entrada» de `_potential_score` puntúa HOY más
alto una acción a un 33% de su máximo que una pegada a él, lo cual apuesta en la
dirección contraria a la literatura sin que nadie lo haya medido.

MEDIDO el 14-09-2026, tres veces. HIPÓTESIS CERRADA Y RECHAZADA. SIGUE VALIENDO None.

1.933 observaciones semanales sobre el universo vigilado, cinco años, horizonte de trece
semanas. Tres experimentos sobre los MISMOS datos, cada uno respondiendo a lo que dejaba
abierto el anterior. Los tres apuntan a lo mismo: la distancia al máximo anual no lleva
información estable sobre el retorno posterior.

1 · LA MEDIA SUBE AL ALEJARSE DEL MÁXIMO — pero no es una ventaja

8,66% → 12,72% → 12,87% → 13,11% → 24,74%. La dirección se había fijado antes de mirar
y salió la contraria, así que la hipótesis original queda rechazada. Pero los tres
tramos centrales están a 0,39 pp unos de otros y la tasa de acierto va de 59,7% a 65,4%
SIN ORDEN: el que más gana de media acierta menos que el 5-10%.

2 · EL GRADIENTE ERA COLA

La mediana del tramo hundido (9,89) está en línea con la del 5-10% (8,55) y la del
10-20% (10,04). Lo que lo distingue es que su media casi TRIPLICA a su mediana —2,50x
frente a 1,28x-1,85x del resto—. Gana lo mismo de forma típica y muchísimo más en sus
mejores casos.

3 · Y EL ÚNICO ESCALÓN QUE QUEDABA CAMBIA DE SIGNO SEGÚN EL AÑO

Quedaba una mediana peor en el tramo 0-5%. Partido por año:

    2023   -4,39 pp    estar en máximos era MEJOR
    2024   -5,35 pp    estar en máximos era MEJOR
    2025   +1,69 pp    estar en máximos era peor
    2026   +7,68 pp    estar en máximos era peor

No es que el escalón falte en dos años: es que en esos dos iba al revés. El escalón
agregado era el promedio de dos regímenes opuestos.

POR QUÉ NO SE PONE NINGÚN NÚMERO, NI EL ORIGINAL NI EL INVERSO

Porque un efecto que cambia de signo con el año no es un umbral: es el mercado de ese
año. Poner aquí «comprar solo lo hundido» sería el error que este fichero existe para
impedir, con el agravante de tener un experimento para justificarlo.

OBSERVACIÓN NO PRE-REGISTRADA, que por eso NO cuenta como evidencia

La amplitud intercuartílica sí es monótona con la distancia: 25,84 → 27,50 → 30,27 →
37,95 → 45,58 pp. El tramo hundido es un 76% más ancho que el pegado al máximo, mientras
su mediana no se distingue. Sugiere que esta variable mide VOLATILIDAD y no retorno
esperado. Se anota como pista, no como hallazgo: se vio después de mirar los datos, y
afirmarlo exigiría su propio experimento con la dirección fijada de antemano.

LO QUE ESTO DICE DE `_potential_score`, y que NO se ha tocado

Su componente de «punto de entrada» puntúa más alto una acción a un 33% de su máximo que
una pegada a él. Ahora sabemos que esa variable no lleva señal estable en NINGUNA
dirección, así que el componente no está respaldado. Quitarlo o cambiarlo es una
decisión de producto que no se toma desde aquí.
"""

SMA200_PENDIENTE_SESIONES: Optional[int] = None
"""Durante cuántas sesiones debe llevar subiendo la SMA200 para reforzar la tendencia.

MIDE: si añadir esta condición al filtro de `tendencia.py` mejora el resultado o solo
reduce el número de señales.

IMPORTANTE: mientras valga None, `tendencia.py` NO la aplica, y esa ausencia es lo que
permite que ese módulo esté en producción sin backtest. Ponerle un número aquí obliga a
medirlo antes, no después.
"""


# ── Setup ────────────────────────────────────────────────────────────────────

PROFUNDIDAD_MAX_RETROCESO: Optional[float] = None
"""Hasta dónde puede caer el precio para que siga siendo un retroceso comprable.

MIDE: distribución de la profundidad real de los retrocesos que acabaron bien frente a
los que acabaron mal.

RELACIÓN CON LO QUE HAY: `server.MAX_PLAN_DEPTH` vale 0,30 y está en producción. No
viene de ningún dato — sale del rango que pedía un prompt. Se deja intacto a propósito:
cambiarlo por otro número sin medir sería inventarlo dos veces. Cuando este experimento
dé un resultado, ese 0,30 se sustituye o se elimina.
"""

VOLUMEN_CONTRACCION_RETROCESO: Optional[float] = None
"""Cuánto debe contraerse el volumen durante el retroceso para que sea ordenado.

MIDE: tasa de acierto de las señales según el ratio de volumen del retroceso.

BLOQUEADO POR: nada técnico. `signal_table._ratio_volumen` ya calcula el dato y ya viaja
en las alertas. Lo único que falta es el número, y por eso sigue siendo informativo en
vez de filtrar.
"""


# ── Gatillo ──────────────────────────────────────────────────────────────────

VOLUMEN_CONFIRMACION: Optional[float] = None
"""Volumen mínimo, en múltiplos de su media, para dar por confirmada una reacción.

MIDE: diferencia de expectativa entre entrar al llegar a la zona y entrar solo tras una
reacción con volumen. Debe medir también lo que CUESTA esperar: cuántas operaciones
buenas se pierden por no llegar la confirmación.

NO COPIAR el «dos a tres veces la media» de Weinstein.
"""

SESIONES_VALIDEZ_CONFIRMACION: Optional[int] = None
"""Cuántas sesiones sigue siendo válida una confirmación antes de caducar.

MIDE: decaimiento del resultado según los días transcurridos entre la confirmación y la
entrada.
"""


# ── Riesgo ───────────────────────────────────────────────────────────────────

ATR_MULTIPLO_STOP: Optional[float] = None
"""Múltiplo de ATR bajo la estructura donde colocar el stop.

MIDE: frecuencia con la que cada múltiplo salta por ruido frente a la pérdida media que
evita cuando la tesis falla de verdad.

RELACIÓN CON LO QUE HAY: `_deterministic_levels` ya usa 1,0 / 1,6 / 2,4×ATR. Están en
producción y tampoco se han medido; este experimento los valida o los sustituye.
"""

RIESGO_MAX_POR_OPERACION: Optional[float] = None
"""Fracción de la cartera que se puede perder en una sola operación.

MIDE: nada del histórico de precios. Es una decisión de tolerancia al riesgo del
usuario, no un parámetro estadístico, y debe preguntarse, no calcularse. Está aquí para
que no acabe siendo un número escondido en el código.
"""


# ── Cómo se leen ─────────────────────────────────────────────────────────────

def esta_calibrado(valor) -> bool:
    """¿Hay número? Se escribe así y no `if valor:` porque un 0 legítimo es un número."""
    return valor is not None


def exigir(nombre: str, valor):
    """El valor, o un fallo ruidoso.

    Para el código que NO puede continuar sin el umbral. Falla al leerlo, no más tarde y
    en otro sitio con un resultado silenciosamente equivocado.

    Cuando una condición pueda simplemente no evaluarse, no se usa esto: se comprueba con
    `esta_calibrado`, se omite la condición y se dice que se ha omitido.
    """
    if valor is None:
        raise SinCalibrar(
            f"'{nombre}' no está calibrado. Sale del experimento sobre el histórico, no "
            "de un valor por defecto ni de un libro."
        )
    return valor
