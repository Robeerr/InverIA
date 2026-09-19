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

CORRECCIÓN del 15-09-2026: casi todo lo de arriba era RUIDO

La auditoría del método midió el suelo: con esta muestra el azar alcanza 8,26 pp de
separación de medianas una vez de cada veinte. Puestas al lado:

    medias                   16,08 pp   por encima del ruido
    medianas                  5,37 pp   DENTRO
    escalón 2023              4,39 pp   DENTRO
    escalón 2024              5,35 pp   DENTRO
    escalón 2025              1,69 pp   DENTRO
    escalón 2026              7,68 pp   DENTRO

Seis de siete caben enteras dentro del azar. Así que «las medianas también se separan» y
«el escalón cambia de signo con el año» no eran hallazgos: eran ruido leído como si
dijera algo. El rechazo se sostiene por la SEPARACIÓN DE MEDIAS, que sí supera el suelo y
sí va en la dirección contraria a la fijada.

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

MEDIDO el 15-09-2026. NO CONCLUYENTE — corregido el 15-09-2026. SIGUE VALIENDO None.

CORRECCIÓN: se registró primero como RECHAZADA. No lo es. La auditoría del método midió
ese mismo día que el suelo de ruido de nuestra muestra está en 8,26 pp, y la separación
de medianas de este experimento es de 7,91: cabe entera dentro del azar.

Con el listón inventado de 1 pp parecía un rechazo, porque las medianas no seguían el
orden fijado. Pero si la separación entera es ruido, ese «orden» no significa nada —una
ordenación al azar se ve exactamente así—. Lo honesto es NO CONCLUYENTE: no sabemos si
la hipótesis es falsa; sabemos que con esta muestra no se puede saber.

Lo que NO cambia: `tendencia.py` sigue sin aplicar la condición, y sigue siendo lo
correcto. Añadir un filtro cuyo efecto no somos capaces de medir es peor que no añadirlo.

1.787 observaciones semanales sobre el universo vigilado, cinco años, horizonte de trece
semanas, media de fondo de 40 barras semanales (≈200 sesiones). La dirección se fijó
antes de mirar: más barras subiendo, más retorno, también en mediana.

Las medianas salieron 10,29 → 9,56 → 10,30 → 13,70 → 5,79. Ni crecientes ni
decrecientes. Y el tramo de rachas más largas —27 barras o más, el que la condición
habría privilegiado— es el PEOR de los cinco: la mediana más baja y el peor porcentaje
de aciertos (60,6%).

NO ES UN PROBLEMA DE RÉGIMEN. El corte por año lo dice: la dirección no se cumple en
2023, ni en 2024, ni en 2025. Ni uno. Aquí no hay dos regímenes opuestos promediándose
como en la hipótesis de la distancia al máximo: simplemente no está.

CONSECUENCIA PARA `tendencia.py`: seguir sin aplicar la condición es lo correcto, y ahora
por una razón medida y no por prudencia. Añadirla habría filtrado señales sin ninguna
mejora, y en el extremo habría preferido justo las rachas que peor se comportan.

APROXIMACIÓN, declarada: la condición de producción habla de la media de 200 SESIONES
sobre velas diarias; se midió con la de 40 barras semanales, que cubre el mismo
calendario pero suaviza distinto. Se midió la DIRECCIÓN de la tendencia de fondo, que es
lo que la condición pretende capturar, no el valor exacto de la media.
"""


# ── Setup ────────────────────────────────────────────────────────────────────

PROFUNDIDAD_MAX_RETROCESO: Optional[float] = None
"""Hasta dónde puede caer el precio para que siga siendo un retroceso comprable.

MIDE: distribución de la profundidad real de los retrocesos que acabaron bien frente a
los que acabaron mal.

RELACIÓN CON LO QUE HAY: `server.MAX_PLAN_DEPTH` vale 0,30 y está en producción. No
viene de ningún dato — sale del rango que pedía un prompt. Se deja intacto a propósito:
cambiarlo por otro número sin medir sería inventarlo dos veces.

MEDIDO el 19-09-2026, dos veces. NO CONCLUYENTE. SIGUE VALIENDO None, y `MAX_PLAN_DEPTH`
SIGUE EN 0,30.

1 · LA MÉTRICA PRE-REGISTRADA NO SEPARA

Tasa de «aguantó», 1.200 toques resueltos del universo vigilado: 87,9 / 91,0 / 86,7 /
92,2 por tramo de profundidad. 5,5 pp de separación contra un suelo de ruido de 9,4.
Cabe dentro del azar.

El fallo fue mío y es el mismo que con la fuerza de las zonas: «aguantó» SATURA. Cuatro
cifras pegadas al 90% no pueden ordenar nada, y elegí esa métrica antes de darme cuenta.

2 · LA COLUMNA DE AL LADO SEPARABA 32 pp, Y AL REPLICAR SE CAYÓ

En esos mismos datos el aguante LIMPIO iba 31,7 / 40,4 / 54,8 / 64,1: monótono, 32 pp, y
EN LA DIRECCIÓN CONTRARIA a la que el 0,30 da por supuesta —las zonas hondas aguantaban
MEJOR—. Pero eso se vio después de mirar, así que se llevó fuera de muestra con la
métrica fijada de antemano.

1.537 toques de símbolos que no están en watchlist ni cartera: 32,7 / 38,8 / 43,4 /
48,1. La dirección se mantiene, pero la separación baja de 32 a 15,4 pp y el suelo de
ruido sube a 21,9. No replica.

POR QUÉ SUBE EL SUELO: los tramos están muy desiguales —988 / 423 / 99 / 27—. Para que
una zona al 40% llegue a tocarse el precio ha tenido que caer un 40%, y eso pasa poco.
Con 27 casos en el tramo hondo, barajar produce rangos grandes por sí solo. Ese problema
NO se arregla con más símbolos: los toques profundos son raros de verdad.

3 · LO QUE SÍ SE SABE, QUE NO ES NADA

Con 1.537 toques, un efecto mayor de 21,9 pp se habría visto. Si la profundidad ordena
el aguante, ordena menos que eso. Es una cota superior y es información.

LO QUE QUEDA ANOTADO Y NO SE PERSIGUE: la dirección salió invertida en las DOS muestras.
Eso no es un hallazgo —el contraste se hace sobre la separación, no sobre el orden, y
fijarse en el orden después de ver los datos es inventar un test nuevo—. Pero si algún
día hay muestra para el tramo hondo, la pregunta que merece hacerse es si el 0,30 está
escondiendo las zonas que mejor se comportan, no si las protege.

NO SE MIDE UNA TERCERA VEZ sobre los mismos datos. Tres tiros a la misma pregunta y
quedarse con el que brilla es lo contrario de medir.
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

MEDIDO el 14 y el 19-09-2026. VALIDADO Y REPLICADO FUERA DE MUESTRA. SIGUE VALIENDO None,
y los tres múltiplos de producción SIGUEN COMO ESTÁN.

Es el único resultado positivo que ha dado el laboratorio, y por eso conviene ser preciso
sobre qué dice y qué no.

1 · LOS TRES MÚLTIPLOS SÍ DISTINGUEN UN CORTE BUENO DE UNO EN FALSO

Sobre el universo vigilado: 1,0×ATR salta en falso el 22,9% de las veces (166 saltos),
1,6× el 5,6% (71) y 2,4× el 0% (16, excluido por muestra). 17,3 pp de diferencia entre
los dos juzgables, banda de 12,48 a 21,8 pp por remuestreo de 23 bloques de fecha. No
toca el cero.

2 · Y REPLICA EN SÍMBOLOS QUE EL USUARIO NO ELIGIÓ

Universo de oportunidades fuera de watchlist y cartera: 20,5% / 7,3% / 4,1%. Esta vez los
tres tramos tuvieron muestra (220 / 123 / 49) y el más ancho entró en la comparación por
derecho. 16,4 pp, banda de 11,09 a 22,31, tampoco toca el cero. Misma dirección, fijada
antes de mirar las dos veces.

3 · LO QUE ESTO NO AUTORIZA A HACER

No dice que haya que cambiar el stop a 1,6. Sabemos que 1,0 saca de operaciones que iban
a aguantar tres veces más a menudo; NO sabemos cuánto se pierde las veces que 1,6 deja
correr una caída que 1,0 habría cortado. Eso exige medir retornos, y con esta muestra los
retornos están dominados por el ruido. Falta la mitad de la ecuación.

Por eso este umbral sigue en None: la pregunta «qué múltiplo usar» no está respondida. Lo
que está respondido es que los tres que hay separan calidad de corte, que es lo que
justifica tener tres y no uno.

4 · EL PUNTO FLOJO, QUE NO SE DISIMULA

El remuestreo es por BLOQUES DE FECHA porque los toques del mismo día comparten mercado.
Eso deja 23 bloques en el primero y 9 en la réplica. Las bandas son honestas, pero
descansan sobre pocas unidades independientes. Dos muestras distintas coincidiendo pesa
más que cualquiera de las dos por separado, y aun así es lo más frágil del resultado.

5 · UN CAMBIO QUE SE HIZO DESPUÉS DE VER EL PRIMER RESULTADO

El intento 1 salió SIN MUESTRA porque 2,4×ATR solo saltó 16 veces y el veredicto se
rendía entero, tirando la comparación válida entre 1,0 y 1,6. Se cambió para juzgar los
múltiplos con muestra y nombrar los excluidos. La exclusión es por muestra y nunca por
resultado, la dirección no se tocó, y el excluido tenía 0% de falsos — el dato MÁS
favorable a la hipótesis. Dejarlo fuera jugaba en contra de lo que se quería demostrar.
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
