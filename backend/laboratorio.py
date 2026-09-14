"""El laboratorio: separar lo que hemos leído de lo que hemos medido.

LAS TRES COSAS QUE NO SON LO MISMO

    CONOCIMIENTO   Alguien lo escribió y nos parece razonable. No es evidencia.
    HIPÓTESIS      Creemos que mejoraría una decisión. Todavía no lo sabemos.
    EVIDENCIA      Lo hemos medido sobre NUESTROS datos y sale esto.

Confundirlas es el fallo que este módulo existe para impedir. «Minervini dice que hay
que comprar a menos de un 25% del máximo» es conocimiento; ponerlo en el código es
convertirlo en regla sin haberlo medido nunca, y entonces la aplicación parece rigurosa
sin serlo. `calibracion.py` lleva ese principio desde antes que este fichero.

POR QUÉ EL REGISTRO DE HIPÓTESIS NO SE INVENTA AQUÍ

Porque ya existe. `calibracion.py` es una lista de umbrales que valen `None` a propósito,
y cada uno declara en su docstring QUÉ habría que medir y QUÉ lo bloquea. Eso es un
registro de hipótesis, escrito antes de que lo llamáramos así.

Duplicarlo en una colección de Mongo habría creado dos verdades: el código diciendo que
un umbral sigue sin medir y una tabla diciendo que ya se validó. Aquí se LEE el módulo
—por AST, no por texto— y el código sigue siendo la única fuente.

QUÉ SE PUEDE MEDIR HOY, Y QUÉ NO

Se puede: precio, técnico, eventos, y nuestras propias decisiones. Todo eso o es
histórico público o lo hemos ido anotando.

No se puede: nada que exija fundamentales punto-en-el-tiempo. Las fuentes sirven el
ÚLTIMO valor, así que un backtest de factores fundamentales mediría un mercado sin
quiebras. Sale bien y está mal. Esa puerta está cerrada con llave en `PUEDE_MEDIRSE`.

SOBRE EL SESGO DE SUPERVIVENCIA, QUE AQUÍ PESA MENOS

Nuestro universo son las acciones que vigilas hoy, así que arrastra supervivencia. Pero
la pregunta que hacemos no es «¿cómo se comportó el mercado?» sino «¿cómo se comportó
LO QUE MIRAMOS?», y esa población es exactamente sobre la que el sistema decide. El
sesgo no desaparece —viaja declarado en cada experimento— pero no invalida la medida
como invalidaría un estudio de factores sobre el mercado entero.
"""
import ast
import inspect
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import calibracion

logger = logging.getLogger("inveria.laboratorio")

COL_EXPERIMENTOS = "lab_experimentos"

#: Muestra mínima para que un número signifique algo. El mismo que ya usa
#: `patrones_registro.MUESTRA_MINIMA`, y por el mismo motivo: por debajo, la cifra es
#: ruido con formato de estadística, y el peligro no es que sea imprecisa — es que
#: INVITA a cambiar el sistema sobre nada.
MUESTRA_MINIMA = 20

#: Estados del ciclo de vida de una hipótesis.
IDEA, INVESTIGANDO, LISTA, EJECUTANDO, EVALUANDO = (
    "IDEA", "RESEARCHING", "READY", "RUNNING", "EVALUATING")

#: Estados en los que termina un experimento. Los cuatro son finales legítimos y
#: ninguno es un fracaso del laboratorio: no poder concluir es un resultado.
VALIDADA = "VALIDATED"
RECHAZADA = "REJECTED"
SIN_DATOS = "INSUFFICIENT_DATA"
NO_CONCLUYENTE = "INCONCLUSIVE"
FINALES = (VALIDADA, RECHAZADA, SIN_DATOS, NO_CONCLUYENTE)

#: Qué umbrales de `calibracion` se pueden medir con los datos que TENEMOS, y por qué.
#: Lo que no está aquí no es que sea difícil: es que medirlo hoy daría un número falso,
#: y un número falso es peor que no tener número.
PUEDE_MEDIRSE = {
    "DISTANCIA_MAX_A_MAXIMO_52S": (
        True, "Solo necesita precios históricos, que sí tenemos completos."),
    "ATR_MULTIPLO_STOP": (
        True, "Solo necesita precios, pero exige definir antes entradas y salidas."),
    "VOLUMEN_CONTRACCION_RETROCESO": (
        True, "El volumen está en el histórico y `signal_table._ratio_volumen` ya lo "
              "calcula; falta definir qué cuenta como retroceso."),
    "VOLUMEN_CONFIRMACION": (
        True, "Como el anterior, y además hay que medir lo que CUESTA esperar."),
    "SESIONES_VALIDEZ_CONFIRMACION": (
        True, "Derivado del anterior: sin él no hay confirmaciones que fechar."),
    "SMA200_PENDIENTE_SESIONES": (
        True, "Solo necesita precios. Mientras valga None, `tendencia.py` NO aplica la "
              "condición, y esa ausencia es lo que le permite estar en producción sin "
              "backtest."),
    "RS_PERCENTIL_MINIMO": (
        False, "Hoy `relative_strength` es un diferencial contra SPY, no un percentil. "
               "Sin un universo con el que comparar, «percentil 70» no existe."),
    "PROFUNDIDAD_MAX_RETROCESO": (
        True, "Solo necesita precios. Sustituiría al 0,30 de `MAX_PLAN_DEPTH`, que hoy "
              "está en producción sin haberse medido."),
    "RIESGO_MAX_POR_OPERACION": (
        False, "No es un parámetro estadístico: es tu tolerancia al riesgo. Se pregunta, "
               "no se calcula."),
}


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── El registro de hipótesis, leído de `calibracion.py` ──────────────────────

def _secciones(texto: str) -> dict:
    """Los bloques MIDE / BLOQUEADO POR / RELACIÓN CON LO QUE HAY de un docstring.

    El formato lo fijó `calibracion.py` antes que este módulo, así que aquí solo se lee.
    """
    claves = {"MIDE": "mide", "BLOQUEADO POR": "bloqueado_por",
              "RELACIÓN CON LO QUE HAY": "relacion_con_produccion",
              "MEDIDO": "medido",
              "NO COPIAR": "no_copiar", "IMPORTANTE": "importante"}
    fuera, actual = {}, None
    for linea in (texto or "").splitlines():
        limpia = linea.strip()
        etiqueta = next((v for k, v in claves.items() if limpia.startswith(k)), None)
        if etiqueta:
            actual = etiqueta
            # Se queda TODO lo que sigue a la palabra clave, lleve dos puntos o no. La
            # primera versión solo guardaba lo de detrás de los «:», y una cabecera sin
            # ellos —«MEDIDO el 14-09-2026. HIPÓTESIS RECHAZADA»— se perdía entera: la
            # sección quedaba vacía y el registro seguía diciendo que estaba pendiente.
            clave = next(k for k in claves if limpia.startswith(k))
            resto = limpia[len(clave):].lstrip(": ").strip()
            fuera[actual] = resto
        elif actual and limpia:
            fuera[actual] = (fuera[actual] + " " + limpia).strip()
        elif actual and not limpia:
            # Una línea en blanco NO cierra la sección: la separa en párrafos. La
            # primera versión cortaba ahí, y de «MEDIDO» solo sobrevivía la cabecera
            # —«hipótesis rechazada»— sin el razonamiento de por qué NO se invierte la
            # regla, que es justo la parte que impide repetir el error.
            #
            # Una sección se cierra cuando empieza otra, o cuando se acaba el docstring.
            if not fuera[actual].endswith("\n\n"):
                fuera[actual] = fuera[actual] + "\n\n"
    return {k: v.strip() for k, v in fuera.items()}


def _estado_de(valor, medible: bool, medido: Optional[str]) -> str:
    """El estado de una hipótesis, deducido y no escrito a mano en ningún sitio.

    El orden importa. Un umbral con NÚMERO es una regla en vigor, se haya medido o no —
    el código ya lo aplica—. Uno que se midió y salió rechazado NO vuelve a la cola de
    «medible»: eso lo haría reaparecer como pendiente y alguien lo repetiría.

    Que el rechazo viva en el docstring de `calibracion` y no en una tabla es lo que
    impide la contradicción de siempre: el código diciendo una cosa y el registro otra.
    """
    if valor is not None:
        return VALIDADA
    # Se busca la palabra CASTELLANA, no la constante: los docstrings de `calibracion`
    # están escritos en castellano y `RECHAZADA` vale «REJECTED». Comparar la constante
    # contra ese texto no casaba nunca, y el registro seguía anunciando como pendiente
    # una hipótesis ya medida — que es exactamente lo que haría que se repitiera.
    if medido and "RECHAZADA" in medido.upper():
        return RECHAZADA
    return LISTA if medible else IDEA


def hipotesis() -> list:
    """Las hipótesis pendientes, leídas del código y no de una tabla.

    Se recorre el AST de `calibracion` en vez de buscar texto: así el título de cada
    hipótesis es la primera línea de su docstring, el estado sale del valor REAL de la
    constante, y el día que alguien le ponga un número, este registro lo refleja solo.
    """
    fuente = inspect.getsource(calibracion)
    arbol = ast.parse(fuente)
    fuera, pendiente = [], None
    for nodo in arbol.body:
        if isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            pendiente = nodo.target.id
            continue
        doc = None
        if (isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Constant)
                and isinstance(nodo.value.value, str)):
            doc = nodo.value.value
        if pendiente and doc is not None:
            valor = getattr(calibracion, pendiente, None)
            medible, motivo = PUEDE_MEDIRSE.get(pendiente, (False, "Sin clasificar."))
            lineas = [l for l in doc.strip().splitlines() if l.strip()]
            fuera.append({
                "id": pendiente,
                "titulo": lineas[0].strip() if lineas else pendiente,
                **_secciones(doc),
                "valor_actual": valor,
                "estado": _estado_de(valor, medible, _secciones(doc).get("medido")),
                "medible_hoy": medible,
                "por_que": motivo,
            })
        pendiente = None
    return fuera


# ── El experimento: distancia al máximo de 52 semanas ────────────────────────
#
# Es el primero por cuatro razones, y ninguna es que fuera el más fácil:
#
#   · se mide SOLO con precios, que es el único histórico completo que tenemos;
#   · contradice algo que está en producción — `_potential_score` puntúa HOY más alto
#     una acción a un 33% de su máximo que una pegada a él, y eso apuesta contra la
#     literatura sin que nadie lo haya medido, como avisa `calibracion` por escrito;
#   · el método es una agregación por tramos, sin parámetros que ajustar, así que casi
#     no hay sitio donde sobreajustar;
#   · alimenta directamente la selección de candidatas.

#: Tramos de distancia al máximo, en porcentaje. El último recoge todo lo demás.
TRAMOS = ((0, 5), (5, 10), (10, 20), (20, 33), (33, 100))

#: BARRAS SEMANALES, y no diarias, por una limitación de datos que conviene dejar dicha:
#: `market_data.PERIOD_MAP` solo ofrece DOS AÑOS de histórico diario. Con 252 sesiones de
#: calentamiento eso deja unas seis observaciones por símbolo, que repartidas en cinco
#: tramos no llegan ni de lejos a la muestra mínima. En semanal hay cinco años, y salen
#: unas cincuenta por símbolo.
#:
#: No es una elección metodológica disfrazada de necesidad: es la resolución más fina que
#: los datos permiten para esta pregunta, y por eso viaja declarada en cada resultado.
RESOLUCION = "1W"

#: Barras hacia delante para juzgar. Trece semanas ≈ un trimestre: suficiente para que
#: una tendencia se exprese y poco para que el resultado sea ya otro mercado.
HORIZONTE = 13
#: Cada cuántas barras se toma una observación. Un mes: muestras más juntas comparten
#: casi todo el camino y contarlas como independientes infla la muestra sin añadir nada.
PASO = 4
#: Barras para el máximo de 52 semanas. En semanal, 52.
VENTANA = 52


def _tramo(distancia: float):
    for bajo, alto in TRAMOS:
        if bajo <= distancia < alto:
            return f"{bajo}-{alto}%"
    return None


def observaciones(barras: list, symbol: str = None) -> list:
    """Las observaciones de UNA serie. Pura, sin red y sin mirar el futuro.

    CÓMO SE EVITA EL LEAKAGE, QUE ES TODO EL EXPERIMENTO

    El máximo de 52 semanas se calcula con las barras ANTERIORES al ancla, sin incluirla.
    El resultado se mide con las POSTERIORES. El ancla no entra en ninguna de las dos
    cosas salvo por su cierre, que es el precio al que se habría entrado.

    Escrito con índices explícitos a propósito: un `rolling().max()` de pandas incluye la
    barra actual por defecto, y ese detalle —que no se ve al leer— mete el máximo del día
    en la decisión del día. Es la forma más común de contaminar un estudio como este.
    """
    fuera = []
    n = len(barras or [])
    for ancla in range(VENTANA, n - HORIZONTE, PASO):
        previas = barras[ancla - VENTANA:ancla]          # SIN el ancla
        try:
            maximo = max(float(b["high"]) for b in previas)
            cierre = float(barras[ancla]["close"])
            despues = float(barras[ancla + HORIZONTE]["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if maximo <= 0 or cierre <= 0:
            continue
        distancia = (maximo - cierre) / maximo * 100      # 0 = en máximos
        tramo = _tramo(distancia)
        if tramo is None:
            continue
        fuera.append({
            "symbol": symbol,
            "fecha": barras[ancla].get("date") or barras[ancla].get("time"),
            "distancia_pct": round(distancia, 2),
            "tramo": tramo,
            "retorno_pct": round((despues - cierre) / cierre * 100, 2),
        })
    return fuera


def agregar(obs: list) -> dict:
    """De observaciones a resultado, con su veredicto. Pura.

    EL VEREDICTO NO PUEDE SER OPTIMISTA POR DEFECTO

    Cuatro finales y tres de ellos dicen que no sabemos. `VALIDATED` exige tres cosas a
    la vez: muestra suficiente en cada tramo, que el retorno medio CAIGA al alejarse del
    máximo —la dirección que predice la literatura, fijada ANTES de mirar— y que la
    diferencia entre el mejor y el peor tramo sea de al menos un punto porcentual.

    Exigir la dirección de antemano es lo que impide el resultado de «hemos probado
    quinientas cosas y una salió espectacular»: aquí solo hay una hipótesis y solo puede
    salir bien de una manera.
    """
    por_tramo = {}
    for o in obs or []:
        por_tramo.setdefault(o["tramo"], []).append(o["retorno_pct"])

    filas = []
    for bajo, alto in TRAMOS:
        clave = f"{bajo}-{alto}%"
        rs = por_tramo.get(clave) or []
        filas.append({
            "tramo": clave,
            "n": len(rs),
            "retorno_medio": round(sum(rs) / len(rs), 2) if rs else None,
            "positivos_pct": round(sum(1 for r in rs if r > 0) / len(rs) * 100, 1) if rs else None,
        })

    total = sum(f["n"] for f in filas)
    flacos = [f["tramo"] for f in filas if f["n"] < MUESTRA_MINIMA]
    if flacos:
        return {"estado": SIN_DATOS, "tramos": filas, "n": total,
                "conclusion": f"Tramos sin muestra suficiente ({MUESTRA_MINIMA} mínimo): "
                              + ", ".join(flacos) + ". No se puede concluir nada.",
                "tramos_flacos": flacos}

    medias = [f["retorno_medio"] for f in filas]
    decreciente = all(a >= b for a, b in zip(medias, medias[1:]))
    separacion = round(max(medias) - min(medias), 2)
    if decreciente and separacion >= 1.0:
        return {"estado": VALIDADA, "tramos": filas, "n": total, "separacion_pp": separacion,
                "conclusion": "El retorno posterior cae al alejarse del máximo, en la "
                              f"dirección que se fijó antes de mirar, con {separacion} pp "
                              "entre el mejor y el peor tramo."}
    if separacion < 1.0:
        return {"estado": NO_CONCLUYENTE, "tramos": filas, "n": total,
                "separacion_pp": separacion,
                "conclusion": f"Los tramos no se distinguen ({separacion} pp entre el mejor "
                              "y el peor). No hay diferencia que aprovechar."}
    return {"estado": RECHAZADA, "tramos": filas, "n": total, "separacion_pp": separacion,
            "conclusion": "Los tramos se distinguen pero NO en la dirección esperada: "
                          "alejarse del máximo no empeora el retorno."}


def ficha(obs: list, universo: list, desde: str = None, hasta: str = None) -> dict:
    """El experimento entero, listo para guardar. Pura.

    Lleva su propia auditoría porque un resultado sin su método no se puede revisar
    después, y dentro de seis meses nadie recordará con qué universo se midió.
    """
    r = agregar(obs)
    return {
        "hipotesis_id": "DISTANCIA_MAX_A_MAXIMO_52S",
        "titulo": "¿Rinde más una acción cerca de su máximo anual que una hundida?",
        "metodo": {
            "que_pregunta": f"Retorno a {HORIZONTE} semanas según la distancia al máximo "
                            "de 52 semanas en la fecha de la observación.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "desde": desde, "hasta": hasta,
            "resolucion": RESOLUCION,
            "ventana_maximo": VENTANA, "horizonte": HORIZONTE, "paso": PASO,
            "tramos": [f"{b}-{a}%" for b, a in TRAMOS],
            "muestra_minima_por_tramo": MUESTRA_MINIMA,
            "direccion_esperada": "El retorno medio decrece al alejarse del máximo. "
                                  "Fijada ANTES de mirar los datos.",
        },
        "controles": {
            "leakage": "El máximo usa solo barras anteriores al ancla; el retorno solo "
                       "posteriores. Índices explícitos, sin `rolling` que incluya la "
                       "barra actual.",
            "solapamiento": f"Una observación cada {PASO} barras con horizonte "
                            f"{HORIZONTE}: las muestras se solapan y NO son "
                            "independientes. No se calcula ningún p-valor por eso.",
            "supervivencia": "El universo son las acciones que se vigilan HOY, así que "
                             "excluye las que dejaron de existir. Se mide lo que el "
                             "sistema mira, no el mercado.",
            "costes": "No se aplican comisiones ni deslizamiento: esto no es una "
                      "estrategia, es una medida de comportamiento.",
            "parametros_ajustados": "Ninguno. Los tramos y el horizonte se fijaron antes "
                                    "de ejecutar y no se han movido para mejorar nada.",
        },
        "resultado": r,
        "estado": r["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }


# ── El diagnóstico: ¿el efecto está en el centro o en la cola? ───────────────
#
# POR QUÉ ESTE ES EL SIGUIENTE EXPERIMENTO Y NO OTRA VARIABLE
#
# El primero salió RECHAZADO con un gradiente llamativo —8,66% a 24,74%— y la tentación
# es pasar a la siguiente hipótesis con la sensación de haber descubierto algo. Los
# mismos datos dicen que no:
#
#     tramo        n    media   %aciertos
#     0-5%       282     8,66      64,2
#     5-10%      292    12,72      65,4
#     10-20%     425    12,87      64,5
#     20-33%     330    13,11      59,7
#     33-100%    604    24,74      62,9
#
# La media se dispara 16 pp y el acierto se mueve 5,7 pp SIN ORDEN. Ganar las mismas
# veces y mucho más cuando se gana no es una ventaja: es dispersión. Y los tres tramos
# centrales están a 0,39 pp unos de otros, así que ni siquiera hay gradiente — hay dos
# saltos en los extremos.
#
# Este experimento separa esas dos explicaciones mirando la MEDIANA en vez de la media.
# Si la mediana es plana mientras la media se dispara, el efecto vive en la cola derecha
# y no en el comportamiento típico.
#
# Y va ANTES que cualquier hipótesis nueva porque el confundido afecta a TODAS. El
# siguiente umbral de la lista —`PROFUNDIDAD_MAX_RETROCESO`— mide otra vez cuánto ha
# caído el precio contra el retorno posterior: reproduciría el mismo sesgo y
# «aprenderíamos» lo mismo dos veces.


def _percentil(ordenados: list, q: float):
    """Percentil por interpolación lineal. Sin dependencias nuevas."""
    if not ordenados:
        return None
    if len(ordenados) == 1:
        return ordenados[0]
    pos = q * (len(ordenados) - 1)
    bajo = int(pos)
    alto = min(bajo + 1, len(ordenados) - 1)
    peso = pos - bajo
    return round(ordenados[bajo] * (1 - peso) + ordenados[alto] * peso, 2)


def distribucion(obs: list) -> dict:
    """La forma de la distribución por tramo, no solo su media. Pura.

    Añade tres cosas que el primer experimento no miraba y que aquí lo son todo:

      · la MEDIANA, que no se mueve porque unas pocas observaciones sean enormes;
      · los cuartiles y los extremos, para ver de dónde sale la media;
      · CUÁNDO ocurrió cada observación, porque si un tramo se concentra en un año
        concreto lo que mide no es la distancia al máximo sino ese año.
    """
    por_tramo = {}
    for o in obs or []:
        por_tramo.setdefault(o["tramo"], []).append(o)

    filas = []
    for bajo, alto in TRAMOS:
        clave = f"{bajo}-{alto}%"
        items = por_tramo.get(clave) or []
        rs = sorted(o["retorno_pct"] for o in items)
        años = {}
        for o in items:
            año = str(o.get("fecha") or "")[:4]
            if año:
                años[año] = años.get(año, 0) + 1
        filas.append({
            "tramo": clave,
            "n": len(rs),
            "media": round(sum(rs) / len(rs), 2) if rs else None,
            "mediana": _percentil(rs, 0.5),
            "p25": _percentil(rs, 0.25),
            "p75": _percentil(rs, 0.75),
            # El ancho intercuartílico responde directamente a «¿es solo que el tramo
            # hundido es más volátil?». Una acción que ha caído un 60% se mueve más en
            # las dos direcciones, y eso infla la media sin ser ninguna ventaja. Se
            # publica calculado y no restando cuartiles a mano: si hay que hacer una
            # cuenta para ver el confundido, el confundido no se ve.
            "amplitud_intercuartil": (
                round(_percentil(rs, 0.75) - _percentil(rs, 0.25), 2) if rs else None),
            "peor": rs[0] if rs else None,
            "mejor": rs[-1] if rs else None,
            "positivos_pct": round(sum(1 for r in rs if r > 0) / len(rs) * 100, 1) if rs else None,
            "por_año": dict(sorted(años.items())),
            # Cuánto del retorno total lo aporta el 10% mejor. Si un puñado de
            # observaciones explica la media, la media no describe a nadie.
            "peso_del_10pct_mejor": (
                round(sum(rs[int(len(rs) * 0.9):]) / sum(rs) * 100, 1)
                if rs and sum(rs) > 0 else None),
        })
    return {"tramos": filas, "n": sum(f["n"] for f in filas)}


#: Cuánto tienen que separarse las medianas para que el efecto esté en el CENTRO.
#: Mismo listón que usó el primer experimento para su separación de medias: si allí
#: 1 pp bastaba para afirmar algo, aquí tiene que bastar para negarlo.
SEPARACION_MINIMA = 1.0


def veredicto_distribucion(d: dict) -> dict:
    """Qué explica el gradiente de medias: el centro o la cola. Puro.

    Los tres finales posibles son todos informativos, y ninguno rehabilita la hipótesis
    original — esa quedó rechazada y no se reabre aquí.
    """
    filas = d.get("tramos") or []
    flacos = [f["tramo"] for f in filas if f["n"] < MUESTRA_MINIMA]
    if flacos:
        return {"estado": SIN_DATOS,
                "conclusion": "Tramos sin muestra suficiente: " + ", ".join(flacos)}

    medias = [f["media"] for f in filas]
    medianas = [f["mediana"] for f in filas]
    rango_media = round(max(medias) - min(medias), 2)
    rango_mediana = round(max(medianas) - min(medianas), 2)

    base = {"rango_media_pp": rango_media, "rango_mediana_pp": rango_mediana,
            "n": d.get("n")}
    # La dispersión de cada tramo viaja con el veredicto: si el tramo que más gana de
    # media es también el más ancho, la explicación está ahí y no hace falta buscar más.
    amplitudes = [f["amplitud_intercuartil"] for f in filas
                  if f["amplitud_intercuartil"] is not None]
    if amplitudes:
        base["amplitud_min_pp"] = min(amplitudes)
        base["amplitud_max_pp"] = max(amplitudes)
        base["mas_ancho_es_el_de_mas_media"] = (
            filas[medias.index(max(medias))]["amplitud_intercuartil"] == max(amplitudes))

    if rango_mediana < SEPARACION_MINIMA <= rango_media:
        return {**base, "estado": RECHAZADA,
                "conclusion": f"El gradiente vive en la COLA, no en el centro: las medias "
                              f"se separan {rango_media} pp y las medianas solo "
                              f"{rango_mediana} pp. El comportamiento típico de los tramos "
                              "es el mismo; lo que cambia es el tamaño de los aciertos "
                              "grandes. No hay ventaja que aprovechar."}
    if rango_mediana >= SEPARACION_MINIMA:
        return {**base, "estado": NO_CONCLUYENTE,
                "conclusion": f"Las medianas TAMBIÉN se separan ({rango_mediana} pp), así "
                              "que el efecto no es solo de cola. Queda descartar régimen "
                              "y supervivencia antes de poder decir nada: mira el reparto "
                              "por año de cada tramo."}
    return {**base, "estado": NO_CONCLUYENTE,
            "conclusion": f"Ni las medias ({rango_media} pp) ni las medianas "
                          f"({rango_mediana} pp) se separan lo suficiente. No hay nada "
                          "que explicar."}


def ficha_distribucion(obs: list, universo: list, desde: str = None,
                       hasta: str = None) -> dict:
    """El experimento de diagnóstico, listo para guardar. Puro."""
    d = distribucion(obs)
    v = veredicto_distribucion(d)
    return {
        # MISMA hipótesis: esto no abre una línea nueva, profundiza en la que ya se
        # rechazó. Así el contador de intentos dice la verdad — llevamos dos sobre ella.
        "hipotesis_id": "DISTANCIA_MAX_A_MAXIMO_52S",
        "tipo": "diagnostico",
        "deriva_de": "Experimento 1, que salió RECHAZADO con un gradiente de medias de "
                     "16 pp y una tasa de acierto plana.",
        "titulo": "¿El gradiente de retornos está en el centro de la distribución o en la cola?",
        "metodo": {
            "que_pregunta": "Mediana, cuartiles y reparto por año de cada tramo, sobre "
                            "las MISMAS observaciones del experimento 1.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "desde": desde, "hasta": hasta,
            "resolucion": RESOLUCION,
            "ventana_maximo": VENTANA, "horizonte": HORIZONTE, "paso": PASO,
            "muestra_minima_por_tramo": MUESTRA_MINIMA,
            "direccion_esperada": "Se espera que las medianas NO se separen mientras las "
                                  "medias sí. Fijada ANTES de ejecutar, a partir de la "
                                  "tasa de acierto plana del experimento 1.",
        },
        "controles": {
            "leakage": "Las mismas observaciones del experimento 1: el máximo usa solo "
                       "barras anteriores al ancla y el retorno solo posteriores.",
            "solapamiento": f"Una observación cada {PASO} barras con horizonte "
                            f"{HORIZONTE}: NO son independientes. Con ~1.900 "
                            "observaciones, las independientes son del orden de 600, y "
                            "menos aún porque todas comparten mercado. Ningún p-valor.",
            "supervivencia": "El sesgo NO es uniforme entre tramos, y esa es la clave: "
                             "una acción que cayó un 60% y se recuperó está hoy en el "
                             "universo; la que no se recuperó, no. El tramo más hundido "
                             "es justo donde más muerde.",
            "regimen": "El reparto por año de cada tramo se publica precisamente para "
                       "poder ver si un tramo se concentra en un periodo concreto. Si "
                       "el tramo hundido vive en 2022, lo que mide es 2022.",
            "costes": "Ninguno. No es una estrategia, es una medida de comportamiento.",
            "parametros_ajustados": "Ninguno. Tramos, horizonte y ventana son los mismos "
                                    "del experimento 1, sin tocar.",
        },
        "resultado": {**d, **v},
        "estado": v["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }


# ── El corte temporal: ¿el patrón vive en un año concreto? ──────────────────
#
# LO QUE OBLIGÓ A ESTE EXPERIMENTO
#
# El diagnóstico salió NO CONCLUYENTE y enseñó dos cosas a la vez:
#
#     tramo       media   mediana   media/mediana
#     0-5%         8,66     4,67        1,85x
#     5-10%       12,72     8,55        1,49x
#     10-20%      12,87    10,04        1,28x
#     20-33%      13,11     8,57        1,53x
#     33-100%     24,74     9,89        2,50x
#
# La primera: el +24,74% del tramo hundido SÍ es cola. Su mediana (9,89) está en línea
# con la del 5-10% y la del 10-20%, y su media casi triplica a su mediana mientras el
# resto se queda entre 1,28x y 1,85x. Gana lo mismo de forma típica y muchísimo más en
# sus mejores casos.
#
# La segunda, que no estaba prevista: las medianas NO son planas, pero tampoco forman un
# gradiente. Van 4,67 → 8,55 → 10,04 → 8,57 → 9,89: suben, bajan y vuelven a subir.
# Quitando el primer tramo, las otras cuatro caben en 1,49 pp. Lo único que se distingue
# es que estar a MENOS DE UN 5% del máximo va con una mediana bastante peor.
#
# Un escalón en una frontera no es un efecto de la distancia al máximo: puede ser
# perfectamente el mercado. Cinco años que incluyen un año bajista y su recuperación
# bastan para que «estar en máximos» y «el año que todo cayó» sean casi la misma cosa.
#
# Este experimento parte la muestra por año y mira si el escalón sigue ahí dentro de cada
# uno. Es la única forma de separar «esto es la distancia al máximo» de «esto es 2022».

#: Cuántos años tienen que repetir el patrón para que deje de parecer un año concreto.
#: Dos de tres es el mínimo que distingue un patrón de una casualidad sin exigir una
#: regularidad que cinco años de datos no pueden demostrar.
AÑOS_MINIMOS = 3


def por_periodo(obs: list) -> dict:
    """Las medianas de cada tramo, año a año. Pura.

    Un año solo entra si TODOS sus tramos llegan a la muestra mínima. Un año a medias
    daría medianas calculadas sobre puñados y se leerían igual que las demás.
    """
    años = {}
    for o in obs or []:
        año = str(o.get("fecha") or "")[:4]
        if año:
            años.setdefault(año, {}).setdefault(o["tramo"], []).append(o["retorno_pct"])

    filas, descartados = [], []
    for año in sorted(años):
        tramos = años[año]
        rs = {f"{b}-{a}%": sorted(tramos.get(f"{b}-{a}%") or []) for b, a in TRAMOS}
        if any(len(v) < MUESTRA_MINIMA for v in rs.values()):
            descartados.append({"año": año,
                                "n_por_tramo": {k: len(v) for k, v in rs.items()}})
            continue
        medianas = {k: _percentil(v, 0.5) for k, v in rs.items()}
        primero = medianas[f"{TRAMOS[0][0]}-{TRAMOS[0][1]}%"]
        resto = [v for k, v in medianas.items()
                 if k != f"{TRAMOS[0][0]}-{TRAMOS[0][1]}%"]
        filas.append({
            "año": año,
            "n": sum(len(v) for v in rs.values()),
            "medianas": medianas,
            # El escalón que hay que confirmar: ¿el tramo pegado al máximo es el peor?
            "el_tramo_en_maximos_es_el_PEOR": primero < min(resto),
            "escalon_pp": round(min(resto) - primero, 2),
        })
    return {"años": filas, "años_descartados": descartados,
            "años_con_muestra": len(filas)}


def veredicto_periodo(d: dict) -> dict:
    """¿El escalón es de la distancia al máximo o del calendario? Puro.

    Tampoco aquí se puede llegar a VALIDATED. Confirmar que un patrón se repite en
    varios años lo hace más creíble, no lo convierte en una regla: seguirían en pie el
    sesgo de supervivencia y el hecho de que cinco años son un solo ciclo.
    """
    filas = d.get("años") or []
    if len(filas) < AÑOS_MINIMOS:
        return {"estado": SIN_DATOS,
                "conclusion": f"Solo {len(filas)} año(s) con muestra suficiente en los "
                              f"cinco tramos; hacen falta {AÑOS_MINIMOS}. Los años "
                              "descartados y su reparto van en el resultado."}

    repiten = [f["año"] for f in filas if f["el_tramo_en_maximos_es_el_PEOR"]]
    base = {"años_con_muestra": len(filas), "años_que_repiten": repiten,
            "escalones_pp": {f["año"]: f["escalon_pp"] for f in filas}}
    if len(repiten) == len(filas):
        return {**base, "estado": NO_CONCLUYENTE,
                "conclusion": "El escalón aparece en TODOS los años con muestra, así que "
                              "no es un año concreto. Sigue sin ser una regla: el "
                              "universo arrastra supervivencia y cinco años son un solo "
                              "ciclo. Lo que gana es credibilidad, no permiso."}
    if len(repiten) >= AÑOS_MINIMOS:
        return {**base, "estado": NO_CONCLUYENTE,
                "conclusion": f"El escalón aparece en {len(repiten)} de {len(filas)} "
                              "años. Se repite, pero no siempre: lo que sea que lo "
                              "produce no está actuando todo el tiempo."}
    return {**base, "estado": RECHAZADA,
            "conclusion": f"El escalón solo aparece en {len(repiten)} de {len(filas)} "
                          "años. No es una propiedad de la distancia al máximo: es lo "
                          "que pasó en esos años concretos."}


def ficha_periodo(obs: list, universo: list, desde: str = None,
                  hasta: str = None) -> dict:
    """El corte temporal, listo para guardar. Puro."""
    d = por_periodo(obs)
    v = veredicto_periodo(d)
    return {
        "hipotesis_id": "DISTANCIA_MAX_A_MAXIMO_52S",
        "tipo": "corte_temporal",
        "deriva_de": "El diagnóstico, que salió NO CONCLUYENTE: las medianas se separan "
                     "5,37 pp, pero casi todo viene del tramo 0-5% y las otras cuatro "
                     "caben en 1,49 pp sin orden.",
        "titulo": "¿El escalón de los que están en máximos se repite cada año, o es un año concreto?",
        "metodo": {
            "que_pregunta": "Mediana de cada tramo AÑO A AÑO, sobre las mismas "
                            "observaciones. Se comprueba si el tramo 0-5% es el peor "
                            "dentro de cada año por separado.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "desde": desde, "hasta": hasta,
            "resolucion": RESOLUCION,
            "ventana_maximo": VENTANA, "horizonte": HORIZONTE, "paso": PASO,
            "muestra_minima_por_tramo_y_año": MUESTRA_MINIMA,
            "años_minimos": AÑOS_MINIMOS,
            "direccion_esperada": "Si el escalón es real, se repite en la mayoría de los "
                                  "años. Si solo aparece en uno, es ese año. Fijada "
                                  "ANTES de ejecutar.",
        },
        "controles": {
            "leakage": "Las mismas observaciones: el máximo usa solo barras anteriores "
                       "al ancla y el retorno solo posteriores.",
            "solapamiento": f"Dentro de un año hay pocas observaciones independientes: "
                            f"con paso {PASO} y horizonte {HORIZONTE}, una observación "
                            "de enero y otra de febrero comparten casi todo el camino. "
                            "Por eso se exige la muestra mínima por tramo Y por año, y "
                            "por eso no hay ningún p-valor.",
            "supervivencia": "Intacto: el universo sigue siendo el de hoy. Partir por "
                             "año no lo corrige, solo separa el efecto del calendario.",
            "un_solo_ciclo": "Cinco años con un mercado bajista y su recuperación son UN "
                             "ciclo. Que un patrón se repita dentro de él no dice que "
                             "sobreviva al siguiente.",
            "costes": "Ninguno. No es una estrategia, es una medida de comportamiento.",
            "parametros_ajustados": "Ninguno. Tramos, horizonte y ventana son los del "
                                    "experimento 1, sin tocar.",
        },
        "resultado": {**d, **v},
        "estado": v["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }


# ── Persistencia. Todo queda, también lo que salió mal ───────────────────────

async def guardar_experimento(db, doc: dict) -> dict:
    """Anota un experimento. Los rechazados también, y por eso existe esto.

    Saber que algo NO funcionó evita repetirlo, y es la mitad del valor del laboratorio:
    sin este registro, dentro de un año alguien volvería a probar lo mismo creyendo que
    era una idea nueva.
    """
    if not isinstance(doc, dict) or not doc.get("hipotesis_id"):
        return {"ok": False, "motivo": "sin_datos"}
    try:
        anteriores = await db[COL_EXPERIMENTOS].count_documents(
            {"hipotesis_id": doc["hipotesis_id"]})
        doc = {**doc, "intento": anteriores + 1}
        await db[COL_EXPERIMENTOS].insert_one(doc)
        return {"ok": True, "intento": doc["intento"], "estado": doc.get("estado")}
    except Exception as e:
        logger.warning("laboratorio: no se pudo guardar el experimento: %s", str(e)[:120])
        return {"ok": False, "motivo": "error", "error": str(e)[:200]}


async def experimentos(db, limite: int = 50) -> list:
    """Los experimentos hechos, el más reciente primero. Solo lectura."""
    try:
        docs = await db[COL_EXPERIMENTOS].find({}, {"_id": 0}).sort(
            "ejecutado_en", -1).limit(limite).to_list(limite)
    except Exception as e:
        logger.warning("laboratorio: no se pudo leer el histórico: %s", str(e)[:120])
        return []
    return docs


async def panorama(db) -> dict:
    """Qué sabe, qué cree y qué ha medido el laboratorio. Solo lectura.

    Deliberadamente SIN una puntuación global. Un «InverIA IQ» sería un número agregado
    sobre cosas que no se suman —conocimiento leído, hipótesis abiertas, experimentos
    hechos— y es exactamente el error que `separacion.py` documenta para el score de
    oportunidades. Se enseñan las cuentas por separado.
    """
    hs = hipotesis()
    hechos = await experimentos(db, limite=200)
    por_estado = {}
    for e in hechos:
        por_estado[e.get("estado")] = por_estado.get(e.get("estado"), 0) + 1
    try:
        conceptos = await db.investing_knowledge.count_documents({})
    except Exception:
        conceptos = None
    return {
        # El conocimiento vive donde ya vivía: `investing_knowledge`, la colección que
        # alimentan newsletters, Telegram y YouTube. No se ha creado una segunda.
        "conocimiento": {"conceptos": conceptos, "coleccion": "investing_knowledge"},
        "hipotesis": {
            "total": len(hs),
            "medibles_hoy": sum(1 for h in hs if h["medible_hoy"]),
            "bloqueadas": sum(1 for h in hs if not h["medible_hoy"]),
            "en_vigor": sum(1 for h in hs if h["estado"] == VALIDADA),
            "lista": hs,
        },
        "experimentos": {
            "total": len(hechos),
            "por_estado": por_estado,
            # Cuántas veces se ha probado CADA hipótesis. Es el control contra «probamos
            # quinientas cosas y una salió»: si un id acumula intentos, su resultado hay
            # que leerlo con esa cifra delante.
            "intentos_por_hipotesis": {
                h: sum(1 for e in hechos if e.get("hipotesis_id") == h)
                for h in {e.get("hipotesis_id") for e in hechos if e.get("hipotesis_id")}
            },
        },
    }
