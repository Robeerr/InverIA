# Congelado para 5b

Inventario de lo que 5a **deliberadamente no toca**. No es una lista de tareas
pendientes: es la lista de sitios donde hoy hay una contradicción conocida y donde
tocar algo sin decidir antes su semántica volvería a crear el problema que estamos
desmontando.

5a solo añade información separada. Cero consumidores migrados, cero ordenaciones
cambiadas, cero umbrales nuevos.

---

## 1 · ~~El veto que vive dentro de una cadena de texto~~ · RESUELTO en 5b-1

**Bandera roja.** `tendencia.py` debe ser la única autoridad sobre la elegibilidad, y
hoy no lo es: hay un veto de tendencia funcionando a través del prefijo de un emoji.

- `daily_analyst._score_candidate`: `if mom_label.startswith("⚠"): return 0, [], False, pot`
- `newsletter_ingest`: `if mom_label.startswith("⚠"): verdict = "🔴 Tu motor la EVITA…"`

Dos problemas a la vez. Que un veto dependa de que una etiqueta empiece por un carácter
concreto significa que cambiar un emoji en `_potential_score_detalle` desactiva
silenciosamente el filtro en dos módulos que no lo mencionan. Y que el veto exista ahí
duplica una regla que ya tiene dueño.

**Hecho en 5b-1.** Los dos preguntan a `tendencia.hay_tendencia_valida` a través de
`market_data.tendencia_de`. Se retiró además una tercera lectura del mismo prefijo en
`server._top_seleccion`, que no vetaba pero mantenía viva la vía.

---

## 2 · ~~`daily_analyst`: el score mezclado dentro de otro score~~ · RESUELTO en 5b-2

```python
conviction += (pot / 100) * 30          # _score_candidate
"conviction": r.get("potential_score")  # ideas del screener
```

La primera línea mete el score mezclado dentro de otro compuesto, y de ahí sale a
correo y a Telegram. La segunda es peor conceptualmente: el mismo número **renombrado**
a «convicción», que sobreviviría intacto a cualquier renombrado que hiciéramos en
`opportunities.py`.

**Hecho en 5b-2.** `conviction` desaparece como escala y se sustituye por
`catalizadores` (recuento 0-3) con puerta en dos. La segunda vía pierde el campo, sin
reemplazo. Los umbrales 65 y 80 se retiran sin sustituto; en régimen rojo solo se recorta
`max_alerts`.

Limitación conocida y aceptada: contar iguala catalizadores de frescura muy distinta —un
*beat* de hasta tres meses vale lo mismo que una compra de directivos de esta semana—.
Exigir frescura introduciría un número de días sin medir.

---

## 3 · Confluencia: los 65/45 se quedan sin significado

`newsletter_ingest` produce el veredicto del motor con `pot >= 65` / `>= 45`, y ese
veredicto es el `score_motor` que entra en `confluencia.py`, cuyos umbrales son los
mismos dos números. Se calibraron sobre un score que mezcla crecimiento, valoración,
punto de entrada, consenso, calidad y momentum — es decir, sobre un número sin una
pregunta detrás.

**Decidido para 5b:** confluencia pasa a cruzar **fuentes × elegibilidad estructural**,
no fuentes × score. Es la única opción que no exige un umbral nuevo, y por tanto la
única que puede entrar sin backtest. Los 65/45 desaparecen; no se reasignan a otro
número.

---

## 4 · Consumidores congelados a la espera de su pregunta

Ninguno se migra en 5a. Los que ya tienen destino claro y los que no:

| Consumidor | Destino |
|---|---|
| Orden del screener | espera a que exista `tendencia_score` |
| Top Selección | espera a que exista `tendencia_score` |
| Alternativa sectorial (`MoreInsights`) | espera a que exista `tendencia_score` |
| `OpportunitiesView` (chip y color) | espera a que exista `tendencia_score` |
| `/opportunities/score/{symbol}` | pasa a explicar dos bloques; **desaparece el total** |
| `newsletter_ingest` / Radar / confluencia | ver punto 3 |
| `daily_analyst` (dos vías) | ver punto 2 |

---

## 5 · Lo que bloquea a casi todos: no hay `tendencia_score`

5a **no lo crea**, y es deliberado. Las dos medidas que describen la tendencia —retorno
a 52 semanas y fuerza relativa— hoy no son puntos en ninguna parte: son un multiplicador
de tres escalones. Agregarlas exige decidir cuánto pesa cada una, y ese reparto no está
medido.

Se emiten los insumos crudos en `separacion.tendencia_insumos`, con `agregado: None`
explícito para que quede claro que no es un cálculo pendiente sino una decisión bloqueada.

**Lo desbloquea el experimento D/E**, no una discusión.

---

## 6 · Parámetros heredados que nadie ha medido

Siguen en producción y 5a no los toca. Cambiarlos por otro número sin medir sería
inventarlos dos veces.

- Pesos de `calidad`: 30 ventas / 12 BPA / 8 negocio. Viajan con `pesos_validados: False`.
- Topes de saturación: 60%, 50%, 25%, 30%.
- Bandas del PEG: 1 / 1,5 / 2,5 / 4.
- Escalones del multiplicador de tendencia: −10 y −5, ×0,75 y ×0,55.
- `server.MAX_PLAN_DEPTH = 0.30`.
- Múltiplos de ATR de los stops: 1,0 / 1,6 / 2,4.

Los que tienen experimento asignado están en `calibracion.py` con valor `None`.

---

## 7 · La duplicación de aritmética, con fecha de caducidad

`separacion.py` replica las fórmulas de `_potential_score_detalle` en vez de
refactorizarla. Es el precio de que «5a no cambia comportamiento» sea comprobable en
lugar de prometido: la función vieja está literalmente intacta.

Dos sitios que pueden divergir. Lo vigila `test_potential_score_congelado.py` con 220
valores dorados. **La duplicación termina cuando 5b retire la ruta vieja**, y ese test
desaparece con ella.

---

## 8 · Requisito del experimento D

Cuando se diseñe, D no puede hacer desaparecer `UNKNOWN` por conveniencia. Debe informar:
total de señales, cuántas son clasificables, cuántas quedan `UNKNOWN`, el porcentaje, y
**por qué** quedaron sin clasificar.

Si resulta que la mayoría del histórico no se puede clasificar sin mirar información
futura, **eso es el resultado**: significaría que la arquitectura de playbooks no se
puede validar retrospectivamente con lo que estamos persistiendo, y la conclusión sería
cambiar qué se guarda, no forzar la clasificación.
