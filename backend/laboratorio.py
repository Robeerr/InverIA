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
        True, "MEDIDO: `backtest` guarda la profundidad de cada zona con la fórmula de "
              "producción y `ficha_profundidad` la juzga contra el suelo de ruido."),
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
    # SOLO LA PRIMERA LÍNEA, que es donde la convención pone el veredicto.
    #
    # Antes se buscaba en la sección entera, y eso se rompió al corregir un resultado: el
    # texto decía «NO CONCLUYENTE — se registró primero como RECHAZADA», y el registro
    # leyó la segunda palabra. Una corrección que explica lo que corrige no puede
    # clasificarse por las palabras que cita.
    #
    # Se buscan las CASTELLANAS y no las constantes: los docstrings de `calibracion` están
    # en castellano y `RECHAZADA` vale «REJECTED». Comparar la constante contra ese texto
    # no casaba nunca, y el registro anunciaba como pendiente una hipótesis ya medida.
    # Y por la RAÍZ, sin la última letra. Se buscaba «VALIDADA» y una ficha escrita en
    # masculino —«VALIDADO Y REPLICADO»— no casaba: el resultado positivo del laboratorio
    # se quedó semanas anunciándose como pendiente de medir, sin que nada fallara.
    #
    # Un fallo silencioso aquí tiene el peor efecto posible: una hipótesis ya cerrada
    # reaparece como medible y alguien la vuelve a medir. Más vale aceptar las dos formas
    # que confiar en que nadie escriba la otra.
    cabecera = (medido or "").splitlines()[0].upper() if medido else ""
    if "NO CONCLUYENTE" in cabecera:
        return NO_CONCLUYENTE
    if "RECHAZAD" in cabecera:
        return RECHAZADA
    if "VALIDAD" in cabecera:
        return VALIDADA
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


def agregar(obs: list, tramos=None) -> dict:
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
    tramos = TRAMOS if tramos is None else tramos
    por_tramo = {}
    for o in obs or []:
        por_tramo.setdefault(o["tramo"], []).append(o["retorno_pct"])

    filas = []
    for bajo, alto in tramos:
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


def distribucion(obs: list, tramos=None) -> dict:
    """La forma de la distribución por tramo, no solo su media. Pura.

    Añade tres cosas que el primer experimento no miraba y que aquí lo son todo:

      · la MEDIANA, que no se mueve porque unas pocas observaciones sean enormes;
      · los cuartiles y los extremos, para ver de dónde sale la media;
      · CUÁNDO ocurrió cada observación, porque si un tramo se concentra en un año
        concreto lo que mide no es la distancia al máximo sino ese año.
    """
    tramos = TRAMOS if tramos is None else tramos
    por_tramo = {}
    for o in obs or []:
        por_tramo.setdefault(o["tramo"], []).append(o)

    filas = []
    for bajo, alto in tramos:
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


#: RESPALDO, y ya sabemos que es malo. Este número me lo inventé: salió de que un punto
#: porcentual parecía razonable. La auditoría del 15-09-2026 lo midió barajando las
#: etiquetas de tramo dentro de cada fecha, y el puro azar lo supera el 100% de las
#: veces: con esta muestra el ruido alcanza 8,26 pp una vez de cada veinte.
#:
#: Solo se usa cuando no se ha medido el suelo de ruido de ese experimento concreto, y
#: entonces el veredicto lo dice. Lo correcto es que cada experimento mida el suyo con
#: `umbral_de_ruido`: el suelo depende del universo, del periodo, de la resolución y de
#: cómo estén repartidas las observaciones entre tramos, así que no hay UN número bueno
#: para todos.
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


def por_periodo(obs: list, tramos=None, creciente=None) -> dict:
    """Las medianas de cada tramo, año a año. Pura.

    Un año solo entra si TODOS sus tramos llegan a la muestra mínima. Un año a medias
    daría medianas calculadas sobre puñados y se leerían igual que las demás.

    `creciente` es la dirección que la hipótesis fijó antes de mirar, si la tiene. Con
    ella, cada año dice si esa dirección se cumplió DENTRO de él. Sin ella solo se
    informa de si el primer tramo es el peor, que es una pregunta más pobre y la única
    que esta función sabía hacer al principio — cuando solo existía una hipótesis y ese
    primer tramo era «estar en máximos».
    """
    tramos = TRAMOS if tramos is None else tramos
    primera_clave = f"{tramos[0][0]}-{tramos[0][1]}%"
    años = {}
    for o in obs or []:
        año = str(o.get("fecha") or "")[:4]
        if año:
            años.setdefault(año, {}).setdefault(o["tramo"], []).append(o["retorno_pct"])

    filas, descartados = [], []
    for año in sorted(años):
        # `del_año` y no `tramos`: al generalizar la función, `tramos` pasó a ser el
        # parámetro, y esta variable local lo pisaba dentro del bucle. Los tests lo
        # cazaron con un `too many values to unpack`.
        del_año = años[año]
        rs = {f"{b}-{a}%": sorted(del_año.get(f"{b}-{a}%") or []) for b, a in tramos}
        if any(len(v) < MUESTRA_MINIMA for v in rs.values()):
            descartados.append({"año": año,
                                "n_por_tramo": {k: len(v) for k, v in rs.items()}})
            continue
        medianas = {k: _percentil(v, 0.5) for k, v in rs.items()}
        primero = medianas[primera_clave]
        resto = [v for k, v in medianas.items()
                 if k != primera_clave]
        filas.append({
            "año": año,
            "n": sum(len(v) for v in rs.values()),
            "medianas": medianas,
            # El escalón que hay que confirmar: ¿el tramo pegado al máximo es el peor?
            # Nombre GENÉRICO. Se llamaba `el_tramo_en_maximos_es_el_PEOR`, y al
            # reutilizar esta función para la persistencia de la tendencia la pantalla
            # acabó preguntando por «máximos» en una hipótesis que no habla de máximos.
            # Es el mismo error que el veredicto reutilizado, una capa más abajo.
            "el_primer_tramo_es_el_PEOR": primero < min(resto),
            "escalon_pp": round(min(resto) - primero, 2),
            # Lo que de verdad interesa cuando la hipótesis declaró una dirección: ¿se
            # cumple DENTRO de este año, o el resultado agregado era el promedio de
            # años que iban cada uno por su lado?
            "direccion_se_cumple": (
                None if creciente is None
                else list(medianas.values()) == sorted(medianas.values(),
                                                       reverse=not creciente)),
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

    repiten = [f["año"] for f in filas if f["el_primer_tramo_es_el_PEOR"]]
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


# ── Segunda hipótesis: la persistencia de la tendencia ──────────────────────
#
# POR QUÉ ESTA Y NO `PROFUNDIDAD_MAX_RETROCESO`
#
# Porque la profundidad de un retroceso es OTRA VEZ cuánto ha caído el precio, y sobre
# esa familia de variables ya hemos gastado tres experimentos para acabar en nada: la
# media era cola, la mediana no tenía gradiente y el único escalón cambiaba de signo
# según el año. Medir lo mismo con otro nombre daría el mismo nada.
#
# Esta es de otra familia: no mide dónde está el precio respecto a un extremo, sino
# CUÁNTO TIEMPO lleva la tendencia apuntando hacia arriba. Y tiene una ventaja que
# ninguna otra de la lista tiene: `tendencia.py` está en producción precisamente porque
# NO aplica esta condición —el umbral vale None—, así que medirla no cuestiona un número
# existente, decide si hace falta uno.
#
# SMA40 SEMANAL EN VEZ DE SMA200 DIARIA, Y HAY QUE DECIRLO
#
# `tendencia.py` mira la media de 200 sesiones sobre velas diarias. En diario solo
# tenemos dos años, y 200 de calentamiento dejan una muestra ridícula. Cuarenta barras
# semanales cubren el mismo tramo de calendario —unas 200 sesiones— y dan cinco años.
#
# No es lo mismo: una media de 40 puntos semanales suaviza distinto que una de 200
# puntos diarios, aunque abarquen las mismas fechas. Lo que se mide aquí es la DIRECCIÓN
# de la tendencia de fondo, que es lo que la condición pretende capturar, no el valor
# exacto de la media. Va declarado en el método.

#: Cuántas barras semanales lleva subiendo la media de fondo. El último tramo recoge el
#: resto. Fijados antes de ejecutar y no se tocan después.
TRAMOS_PENDIENTE = ((0, 1), (1, 5), (5, 13), (13, 27), (27, 999))

#: Barras de la media de fondo. 40 semanales ≈ 200 sesiones.
VENTANA_MEDIA = 40


def _media(valores: list):
    return sum(valores) / len(valores) if valores else None


def observaciones_pendiente(barras: list, symbol: str = None) -> list:
    """Observaciones por CUÁNTAS barras lleva subiendo la media de fondo. Pura.

    El mismo cuidado con el leakage que en el otro experimento, y por el mismo motivo:
    la media del ancla se calcula con las barras que TERMINAN en ella, la racha mira
    hacia atrás, y el retorno solo hacia delante. Ni la racha ni la media saben nada de
    lo que pasa después.
    """
    fuera = []
    n = len(barras or [])
    # Hace falta la ventana de la media MÁS margen para poder mirar la racha hacia atrás.
    arranque = VENTANA_MEDIA * 2
    for ancla in range(arranque, n - HORIZONTE, PASO):
        try:
            cierres = [float(b["close"]) for b in barras[:ancla + 1]]
            despues = float(barras[ancla + HORIZONTE]["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if cierres[ancla] <= 0:
            continue
        # Cuántas barras consecutivas lleva subiendo la media, mirando hacia atrás.
        racha = 0
        i = ancla
        while i - VENTANA_MEDIA >= 0:
            actual = _media(cierres[i - VENTANA_MEDIA + 1:i + 1])
            previa = _media(cierres[i - VENTANA_MEDIA:i])
            if actual is None or previa is None or actual <= previa:
                break
            racha += 1
            i -= 1
            if racha >= TRAMOS_PENDIENTE[-1][1]:
                break
        tramo = next((f"{b}-{a}%" for b, a in TRAMOS_PENDIENTE if b <= racha < a), None)
        if tramo is None:
            continue
        fuera.append({
            "symbol": symbol,
            "fecha": barras[ancla].get("date") or barras[ancla].get("time"),
            "racha": racha,
            "tramo": tramo,
            "retorno_pct": round((despues - cierres[ancla]) / cierres[ancla] * 100, 2),
        })
    return fuera


def veredicto_direccion(d: dict, creciente: bool = True,
                        umbral: Optional[float] = None) -> dict:
    """¿Se cumple la dirección que se fijó ANTES de mirar? Sobre la MEDIANA. Puro.

    POR QUÉ ESTA FUNCIÓN EXISTE Y NO SE REUTILIZÓ `veredicto_distribucion`

    Porque responden a preguntas distintas y confundirlas ya costó un resultado mal
    etiquetado. `veredicto_distribucion` diagnostica si un gradiente de MEDIAS ya
    encontrado vive en la cola; su salida habla de colas. Aplicada a una hipótesis nueva
    devolvía «el efecto no es solo de cola» sobre algo que nunca había afirmado tener una
    cola, y marcaba NO CONCLUYENTE lo que en realidad era un RECHAZO.

    SOBRE LA MEDIANA Y NO SOBRE LA MEDIA

    Es la lección de la hipótesis anterior, aplicada. Allí la media subía 16 pp y resultó
    ser cola; la mediana no se movía. Juzgar la dirección por la media vuelve a poner el
    veredicto en manos de unos pocos aciertos enormes.
    """
    filas = d.get("tramos") or []
    flacos = [f["tramo"] for f in filas if f["n"] < MUESTRA_MINIMA]
    if flacos:
        return {"estado": SIN_DATOS,
                "conclusion": "Tramos sin muestra suficiente: " + ", ".join(flacos)}

    # El suelo MEDIDO manda sobre el inventado. Si no se midió, se usa el respaldo y el
    # veredicto lo dice: un umbral que nadie ha comprobado no puede presentarse como si
    # lo hubieran comprobado.
    medido = umbral is not None
    liston = umbral if medido else SEPARACION_MINIMA
    aviso = "" if medido else (" AVISO: el umbral no se ha medido para esta muestra; se "
                               f"usa el respaldo de {SEPARACION_MINIMA} pp, que la "
                               "auditoría del método declaró insuficiente.")

    medianas = [f["mediana"] for f in filas]
    esperado = sorted(medianas) if creciente else sorted(medianas, reverse=True)
    separacion = round(max(medianas) - min(medianas), 2)
    mejor = filas[medianas.index(max(medianas))]["tramo"]
    peor = filas[medianas.index(min(medianas))]["tramo"]
    base = {"separacion_mediana_pp": separacion, "n": d.get("n"),
            "mejor_tramo": mejor, "peor_tramo": peor, "umbral_pp": liston,
            "umbral_medido": medido,
            "medianas": {f["tramo"]: f["mediana"] for f in filas}}

    if separacion < liston:
        return {**base, "estado": NO_CONCLUYENTE,
                "conclusion": f"Las medianas se separan {separacion} pp, por DEBAJO del "
                              f"suelo de ruido ({liston} pp): cabe entero dentro de lo "
                              "que el azar produce solo con esta muestra. No hay nada que "
                              "aprovechar, y tampoco nada que explicar." + aviso}
    if medianas == esperado:
        return {**base, "estado": VALIDADA,
                "conclusion": f"Las medianas siguen la dirección fijada antes de mirar, "
                              f"con {separacion} pp — por encima del suelo de ruido "
                              f"({liston} pp)." + aviso}
    return {**base, "estado": RECHAZADA,
            "conclusion": f"Las medianas se separan {separacion} pp pero NO en la "
                          f"dirección fijada antes de mirar: el mejor tramo es {mejor} y "
                          f"el peor {peor}. La hipótesis, tal como se planteó, no se "
                          "sostiene. Lo que se vea ahora en la forma de la curva es una "
                          "hipótesis NUEVA y necesita su propio experimento."}


def ficha_pendiente(obs: list, universo: list, desde: str = None,
                    hasta: str = None) -> dict:
    """La segunda hipótesis, con las lecciones de la primera aplicadas. Pura.

    LO QUE SE APRENDIÓ Y AQUÍ YA VIENE DE SERIE

    El primer experimento reportó solo medias y hubo que hacer dos experimentos más para
    descubrir que mentían: una era cola y el resto cambiaba de signo con el año. Este
    trae mediana, cuartiles, amplitud, peso del 10% mejor Y el corte por año desde la
    primera ejecución. No es cortesía: es lo único que permite leer el resultado sin
    volver a equivocarse dos veces.
    """
    d = distribucion(obs, tramos=TRAMOS_PENDIENTE)
    # `veredicto_direccion` y NO `veredicto_distribucion`: esta hipótesis se juzga por si
    # cumple la dirección que se fijó antes de mirar, no por si un gradiente ya conocido
    # vive en la cola. Reutilizar el otro etiquetó el primer resultado como NO
    # CONCLUYENTE cuando era un RECHAZO.
    # El suelo de ruido de ESTE experimento, medido sobre sus propias observaciones. Sin
    # él, el veredicto se apoyaría en un número inventado que la auditoría ya tumbó.
    suelo = umbral_de_ruido(obs, tramos=TRAMOS_PENDIENTE)
    v = veredicto_direccion(d, creciente=True, umbral=suelo)
    periodo = por_periodo(obs, tramos=TRAMOS_PENDIENTE, creciente=True)
    return {
        "hipotesis_id": "SMA200_PENDIENTE_SESIONES",
        "tipo": "primero",
        "titulo": "¿Rinde más una acción cuya tendencia de fondo lleva más tiempo subiendo?",
        "metodo": {
            "que_pregunta": f"Retorno a {HORIZONTE} semanas según cuántas barras lleva "
                            "subiendo la media de fondo en la fecha de la observación.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "desde": desde, "hasta": hasta,
            "resolucion": RESOLUCION,
            "media_de_fondo": f"{VENTANA_MEDIA} barras semanales ≈ 200 sesiones",
            "horizonte": HORIZONTE, "paso": PASO,
            "tramos": [f"{b}-{a}%" for b, a in TRAMOS_PENDIENTE],
            "muestra_minima_por_tramo": MUESTRA_MINIMA,
            "direccion_esperada": "Más barras subiendo → mayor retorno posterior, tanto "
                                  "en media como en MEDIANA. Fijada ANTES de ejecutar.",
        },
        "controles": {
            "leakage": "La media del ancla usa las barras que terminan en ella, la racha "
                       "mira hacia atrás y el retorno solo hacia delante.",
            "solapamiento": f"Una observación cada {PASO} barras con horizonte "
                            f"{HORIZONTE}: NO son independientes. Ningún p-valor.",
            "supervivencia": "El universo es el de hoy. Aquí pesa menos que en la "
                             "hipótesis anterior —una racha alcista no selecciona "
                             "supervivientes como lo hace una caída del 60%— pero sigue.",
            "aproximacion": "La condición de producción habla de la media de 200 SESIONES "
                            "sobre velas diarias; aquí se usa la de 40 barras semanales, "
                            "que cubre el mismo calendario. Suaviza distinto. Se mide la "
                            "DIRECCIÓN de la tendencia de fondo, no el valor de la media.",
            "un_solo_ciclo": "Los mismos cinco años, el mismo ciclo. Por eso el corte por "
                             "año viene de serie: el experimento anterior enseñó que un "
                             "resultado agregado puede ser el promedio de dos regímenes "
                             "opuestos.",
            "costes": "Ninguno. No es una estrategia, es una medida de comportamiento.",
            "parametros_ajustados": "Ninguno. Tramos, ventana y horizonte fijados antes.",
        },
        "resultado": {**d, **v, "por_periodo": periodo},
        "estado": v["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }


# ── El instrumento: ¿cuánta separación produce el puro azar? ────────────────
#
# POR QUÉ ESTO VA ANTES QUE UNA TERCERA VARIABLE
#
# Dos hipótesis medidas, dos rechazadas. La tentación es seguir con la lista. Pero hay
# una pregunta sin responder que afecta a TODAS las que vengan y a las dos que ya se
# cerraron:
#
#     `SEPARACION_MINIMA = 1.0` me lo inventé yo.
#
# Es el listón que decide si dos tramos «se distinguen». Salió de que un punto porcentual
# parecía razonable, no de ninguna medida. Y si el azar, con nuestra muestra concreta,
# produce rutinariamente separaciones de tres o cuatro puntos, entonces ese listón no
# filtra nada: cualquier hipótesis futura podría «validarse» por ruido, y las dos que
# rechazamos lo habrían hecho igual.
#
# Es exactamente el error que `calibracion.py` existe para impedir, cometido por mí
# dentro del módulo que vigila que no se cometa.
#
# CÓMO SE MIDE SIN DATOS NUEVOS
#
# Barajando. Se toman las observaciones REALES y se cambia de sitio la etiqueta del
# tramo, rompiendo cualquier relación entre el tramo y el retorno. Si tras barajar
# siguen saliendo separaciones grandes, la separación no venía del tramo.
#
# SE BARAJA DENTRO DE CADA FECHA, Y ESO ES LA MITAD DEL MÉTODO
#
# Barajar todo junto rompería también el hecho de que en una misma semana todas las
# acciones se mueven a la vez. Esa dependencia es real y es la que más infla el ruido:
# destruirla haría que el azar pareciera más manso de lo que es, y el listón saldría
# demasiado bajo. Barajando dentro de cada fecha, el mercado de esa semana se conserva
# intacto y solo se rompe lo que queremos romper: qué tramo le tocó a cada acción.

#: Cuántas veces se baraja. Doscientas bastan para situar el observado entre los
#: percentiles sin que la medición tarde más que el experimento que audita.
VUELTAS_AZAR = 200

#: Semilla fija: el mismo dataset tiene que dar el mismo listón. Un umbral que cambia
#: con cada ejecución no es un umbral.
SEMILLA = 20260915


def separacion_de(obs: list, tramos=None) -> Optional[float]:
    """La separación de medianas entre el mejor y el peor tramo. Pura."""
    filas = distribucion(obs, tramos=tramos)["tramos"]
    medianas = [f["mediana"] for f in filas if f["mediana"] is not None]
    if len(medianas) < 2:
        return None
    return round(max(medianas) - min(medianas), 2)


def barajar_dentro_del_dia(obs: list, azar) -> list:
    """Las mismas observaciones con los tramos cambiados de sitio DENTRO de cada fecha.

    Cada observación conserva su retorno y su fecha; lo único que viaja es la etiqueta
    del tramo, y solo entre observaciones de la misma semana.
    """
    por_fecha = {}
    for o in obs or []:
        por_fecha.setdefault(o.get("fecha"), []).append(o)
    fuera = []
    for items in por_fecha.values():
        etiquetas = [o["tramo"] for o in items]
        azar.shuffle(etiquetas)
        fuera += [{**o, "tramo": t} for o, t in zip(items, etiquetas)]
    return fuera


def azar(obs: list, tramos=None, vueltas: int = None) -> dict:
    """Qué separaciones produce el puro azar con ESTA muestra. Pura y determinista."""
    import random
    vueltas = VUELTAS_AZAR if vueltas is None else vueltas
    generador = random.Random(SEMILLA)
    observada = separacion_de(obs, tramos=tramos)
    simuladas = []
    for _ in range(vueltas):
        s = separacion_de(barajar_dentro_del_dia(obs, generador), tramos=tramos)
        if s is not None:
            simuladas.append(s)
    simuladas.sort()
    if not simuladas:
        return {"observada": observada, "vueltas": 0}
    # Cuántas veces el azar iguala o supera lo observado. No es un p-valor —las
    # observaciones se solapan en el tiempo y eso no lo arregla barajar— pero sí dice si
    # lo que vimos cabe cómodamente dentro de lo que el ruido produce solo.
    mayores = sum(1 for s in simuladas if observada is not None and s >= observada)
    return {
        "observada": observada,
        "vueltas": len(simuladas),
        "azar_mediana": _percentil(simuladas, 0.5),
        "azar_p90": _percentil(simuladas, 0.90),
        "azar_p95": _percentil(simuladas, 0.95),
        "azar_maxima": simuladas[-1],
        "veces_que_el_azar_lo_iguala_pct": round(mayores / len(simuladas) * 100, 1),
        "liston_actual": SEPARACION_MINIMA,
        "veces_que_el_azar_supera_el_liston_pct": round(
            sum(1 for s in simuladas if s >= SEPARACION_MINIMA) / len(simuladas) * 100, 1),
    }


def umbral_de_ruido(obs: list, tramos=None, vueltas: int = None) -> Optional[float]:
    """El suelo de ruido de ESTE experimento: lo que el azar alcanza una vez de cada
    veinte con estas mismas observaciones. Puro y determinista.

    Es el número que `SEPARACION_MINIMA` pretendía ser y no era. Depende del universo,
    del periodo, de la resolución y de cómo estén repartidas las observaciones entre
    tramos — por eso se mide por experimento y no se fija una vez para todos.
    """
    d = azar(obs, tramos=tramos, vueltas=vueltas)
    return d.get("azar_p95")


def veredicto_azar(d: dict) -> dict:
    """¿Sirve de algo el listón que usamos? Puro.

    No juzga ninguna hipótesis: juzga la herramienta con la que las juzgamos.
    """
    if not d.get("vueltas"):
        return {"estado": SIN_DATOS,
                "conclusion": "No hay observaciones suficientes para barajar."}
    p95 = d["azar_p95"]
    cuela = d["veces_que_el_azar_supera_el_liston_pct"]
    if cuela >= 50:
        return {"estado": RECHAZADA,
                "conclusion": f"El listón NO filtra nada: el puro azar lo supera el "
                              f"{cuela}% de las veces con esta muestra. Habría que "
                              f"subirlo al menos a {p95} pp, que es lo que el ruido "
                              "alcanza una vez de cada veinte. Los rechazos anteriores "
                              "siguen siendo válidos —rechazar por dirección no depende "
                              "del listón— pero cualquier VALIDACIÓN con el listón actual "
                              "habría sido ruido."}
    if cuela >= 10:
        return {"estado": NO_CONCLUYENTE,
                "conclusion": f"El azar supera el listón el {cuela}% de las veces. Filtra, "
                              f"pero poco: el percentil 95 del ruido está en {p95} pp."}
    return {"estado": VALIDADA,
            "conclusion": f"El listón aguanta: el azar solo lo supera el {cuela}% de las "
                          f"veces, y su percentil 95 está en {p95} pp."}


def ficha_azar(obs: list, universo: list, desde: str = None, hasta: str = None) -> dict:
    """La auditoría del propio instrumento, lista para guardar. Pura."""
    d = azar(obs)
    v = veredicto_azar(d)
    return {
        "hipotesis_id": "SEPARACION_MINIMA",
        "tipo": "auditoria_del_metodo",
        "deriva_de": "Dos hipótesis rechazadas con un listón de 1 pp que nadie midió.",
        "titulo": "¿Cuánta separación entre tramos produce el puro azar con nuestra muestra?",
        "metodo": {
            "que_pregunta": "Se barajan las etiquetas de tramo DENTRO de cada fecha y se "
                            "mide cuánta separación de medianas sale. Si el azar produce "
                            "rutinariamente lo que exigimos, el listón no filtra nada.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "desde": desde, "hasta": hasta,
            "resolucion": RESOLUCION,
            "vueltas": VUELTAS_AZAR,
            "semilla": SEMILLA,
            "direccion_esperada": "Ninguna. Esto no prueba una hipótesis: mide la "
                                  "herramienta. El resultado se acepta como salga.",
        },
        "controles": {
            "por_que_dentro_del_dia": "Barajar todo junto rompería también que en una "
                                      "misma semana todas las acciones se mueven a la "
                                      "vez. Esa dependencia es real y es la que más "
                                      "infla el ruido: destruirla haría que el azar "
                                      "pareciera más manso y el listón saldría bajo.",
            "no_es_un_p_valor": "Las observaciones se solapan en el tiempo y barajar no "
                                "lo arregla. Esto dice si lo observado cabe dentro de lo "
                                "que el ruido produce solo, no cuál es su probabilidad.",
            "determinismo": f"Semilla fija ({SEMILLA}). Un listón que cambia con cada "
                            "ejecución no es un listón.",
            "alcance": "Mide ESTA muestra: este universo, estos cinco años, esta "
                       "resolución. Con más símbolos o más historia, el ruido bajaría.",
        },
        "resultado": {**d, **v},
        "estado": v["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }


# ── Tercera hipótesis: ¿aguantan las zonas de compra? ───────────────────────
#
# POR QUÉ ESTA PREGUNTA Y NO OTRA VARIABLE DE PRECIO
#
# Las dos hipótesis anteriores murieron por lo mismo: preguntaban «¿qué retorno viene
# después?», y el retorno a trece semanas es tan ruidoso que con nuestra muestra hace
# falta un efecto de más de 8 pp de mediana para verlo. No existe ninguno así.
#
# Esta pregunta es de otra forma, y ahí está toda la diferencia:
#
#   · el resultado es BINARIO —el nivel aguantó o se rompió—, no un retorno continuo;
#   · hay MILES de toques en lugar de ~1.900 observaciones;
#   · el evento es LOCAL: lo que pasa en los días siguientes a tocar un soporte depende
#     mucho menos del régimen del año que un retorno trimestral.
#
# Las tres cosas bajan el ruido. Es la primera pregunta que hacemos donde el instrumento
# tiene una posibilidad real de detectar algo.
#
# Y AFECTA A LO QUE YA SE ENSEÑA EN PANTALLA
#
# `levels_engine` puntúa cada zona de 0 a 100 y la ficha de la acción dice «Nivel fuerte
# (78/100)». Ese número nunca se ha comprobado. Si las zonas «fuertes» no aguantan más
# que las «débiles», el usuario está leyendo una etiqueta sin respaldo — y la tesis
# determinista la cita («la zona de compra más sólida es el NIVEL 1»).
#
# `backtest.py` lleva meses escrito, hace el walk-forward punto-en-el-tiempo y nunca se
# ha ejecutado como experimento registrado: sus resultados viven en una caché de 24 h y
# se pierden. Aquí no se reimplementa nada; se le pone alrededor la disciplina que les
# falta a sus dos endpoints — dirección fijada antes, suelo de ruido medido, corte por
# año y un veredicto que puede decir que no sabe.

#: Los tres cubos que ya usa `backtest._bucket`, de menos a más fuerte. El orden importa:
#: es la dirección que la hipótesis afirma.
CUBOS_FUERZA = ("debil", "media", "fuerte")


def aguante_por_cubo(registros: list, metrica: str = "held",
                     campo: str = "bucket", cubos: tuple = None) -> dict:
    """Con qué frecuencia aguantó cada cubo. Pura.

    Solo cuentan los toques RESUELTOS: un nivel que no llegó a tocarse no aguantó ni se
    rompió, y contarlo como cualquiera de las dos cosas sería inventar el dato.

    `campo` y `cubos` existen porque la pregunta «¿aguantan más unas zonas que otras?» se
    hace sobre más de un criterio: la fuerza que el motor puntúa, y la profundidad a la
    que está el nivel. La cuenta es la misma y el suelo de ruido se mide igual; lo único
    que cambia es por qué columna se agrupa. Copiar la función para cambiar una cadena
    dejaría dos sitios donde arreglar el mismo fallo.
    """
    filas = []
    for cubo in (cubos or CUBOS_FUERZA):
        rs = [r for r in (registros or [])
              if r.get(campo) == cubo and r.get(metrica) is not None]
        aguantan = sum(1 for r in rs if r[metrica])
        limpios = [r for r in rs if r.get("clean") is not None]
        años = {}
        for r in rs:
            a = str(r.get("anchor") or "")[:4]
            if a:
                años[a] = años.get(a, 0) + 1
        filas.append({
            "cubo": cubo,
            "n": len(rs),
            "aguante_pct": round(aguantan / len(rs) * 100, 1) if rs else None,
            # «Limpio» es más exigente: aguantó Y no llegó a romperse en ningún momento
            # de la ventana. Un rebote que llega después de haber perdido el nivel no es
            # lo que promete una zona de compra.
            # Solo tiene sentido como columna APARTE cuando la métrica principal es
            # «aguantó». Si ya se está midiendo el limpio, repetirlo pondría el mismo
            # número dos veces en la tabla y parecerían dos medidas distintas.
            "aguante_limpio_pct": (
                round(sum(1 for r in limpios if r["clean"]) / len(limpios) * 100, 1)
                if limpios and metrica == "held" else None),
            "por_año": dict(sorted(años.items())),
        })
    return {"cubos": filas, "n": sum(f["n"] for f in filas)}


def _rango_de_aguante(registros: list, metrica: str = "held",
                      campo: str = "bucket", cubos: tuple = None) -> Optional[float]:
    filas = aguante_por_cubo(registros, metrica=metrica, campo=campo, cubos=cubos)["cubos"]
    tasas = [f["aguante_pct"] for f in filas if f["aguante_pct"] is not None]
    return round(max(tasas) - min(tasas), 2) if len(tasas) > 1 else None


def azar_del_aguante(registros: list, vueltas: int = None,
                     metrica: str = "held", campo: str = "bucket",
                     cubos: tuple = None) -> dict:
    """Qué diferencia de aguante produce el azar con ESTOS toques. Pura y determinista.

    Se barajan los cubos de fuerza DENTRO de cada fecha, por el mismo motivo que en el
    otro experimento: en un mismo día el mercado entero empuja en la misma dirección, y
    romper eso haría que el azar pareciera más manso de lo que es.
    """
    import random
    vueltas = VUELTAS_AZAR if vueltas is None else vueltas
    generador = random.Random(SEMILLA)
    observado = _rango_de_aguante(registros, metrica=metrica, campo=campo, cubos=cubos)

    por_fecha = {}
    for r in registros or []:
        por_fecha.setdefault(r.get("anchor"), []).append(r)

    simulados = []
    for _ in range(vueltas):
        barajados = []
        for items in por_fecha.values():
            etiquetas = [r.get(campo) for r in items]
            generador.shuffle(etiquetas)
            barajados += [{**r, campo: c} for r, c in zip(items, etiquetas)]
        s = _rango_de_aguante(barajados, metrica=metrica, campo=campo, cubos=cubos)
        if s is not None:
            simulados.append(s)
    simulados.sort()
    if not simulados:
        return {"observado_pp": observado, "vueltas": 0}
    return {
        "observado_pp": observado,
        "vueltas": len(simulados),
        "azar_p95_pp": _percentil(simulados, 0.95),
        "azar_mediana_pp": _percentil(simulados, 0.5),
        "azar_maximo_pp": simulados[-1],
    }


def veredicto_aguante(d: dict, ruido: dict) -> dict:
    """¿Aguantan más las zonas fuertes? Puro.

    La dirección se fijó antes de mirar y es la que el propio número afirma: si la
    pantalla dice «Nivel fuerte (78/100)», las zonas fuertes tienen que aguantar más que
    las medias, y estas más que las débiles.
    """
    filas = d.get("cubos") or []
    flacos = [f["cubo"] for f in filas if f["n"] < MUESTRA_MINIMA]
    if flacos:
        return {"estado": SIN_DATOS,
                "conclusion": "Cubos sin muestra suficiente: " + ", ".join(flacos)}

    tasas = [f["aguante_pct"] for f in filas]
    observado = ruido.get("observado_pp")
    suelo = ruido.get("azar_p95_pp")
    base = {"aguantes": {f["cubo"]: f["aguante_pct"] for f in filas},
            "rango_pp": observado, "suelo_de_ruido_pp": suelo, "n": d.get("n")}

    if suelo is None or observado is None:
        return {**base, "estado": SIN_DATOS,
                "conclusion": "No se ha podido medir el suelo de ruido."}
    if observado < suelo:
        # NO SABER POR FALTA DE MUESTRA Y SABER QUE ES PEQUEÑO NO ES LO MISMO.
        #
        # Con muestra suficiente, quedarse por debajo del suelo SÍ dice algo: que un
        # efecto mayor que el suelo se habría visto. Eso es una cota superior, y es
        # información. Decir solo «no concluyente» la tiraría a la basura.
        n = d.get("n") or 0
        cota = (f" Con {n} toques resueltos, un efecto real mayor que {suelo} pp se "
                "habría visto: si existe algo, es más pequeño que eso."
                if n >= MUESTRA_MINIMA * 10 else
                " La muestra es corta, así que tampoco se puede acotar cuánto.")
        return {**base, "estado": NO_CONCLUYENTE, "cota_superior_pp": suelo,
                "conclusion": f"Los cubos se separan {observado} pp, por debajo del suelo "
                              f"de ruido ({suelo} pp): cabe dentro de lo que el azar "
                              "produce solo. La puntuación de fuerza NO ordena las zonas "
                              "por lo bien que aguantan." + cota}
    if tasas == sorted(tasas):
        return {**base, "estado": VALIDADA,
                "conclusion": f"Las zonas fuertes aguantan más que las medias y estas más "
                              f"que las débiles, con {observado} pp entre la mejor y la "
                              f"peor — por encima del suelo de ruido ({suelo} pp). La "
                              "puntuación de fuerza mide algo real."}
    return {**base, "estado": RECHAZADA,
            "conclusion": f"Los cubos se separan {observado} pp, por encima del ruido "
                          f"({suelo} pp), pero NO en el orden que la puntuación afirma. "
                          "El número que la pantalla enseña como «fuerza» no ordena las "
                          "zonas por lo bien que aguantan."}


# ── La profundidad del retroceso, que gobierna MAX_PLAN_DEPTH ────────────────

#: Los tramos de profundidad. EL CORTE DE 0,30 NO ES MÍO: es el `MAX_PLAN_DEPTH` que está
#: en producción decidiendo qué zonas se te enseñan como comprables. Los otros dos parten
#: el interior del suelo en tercios iguales, que es la división más sosa posible.
#:
#: Elegir los cortes después de mirar los datos —«aquí se separa bien»— es la forma más
#: cómoda de fabricar un hallazgo. Por eso quedan escritos antes, y anclados a un número
#: que ya existía.
CUBOS_PROFUNDIDAD = ("0-10%", "10-20%", "20-30%", ">30%")
CORTE_DEL_PLAN = 0.30


def cubo_de_profundidad(depth) -> Optional[str]:
    """En qué tramo cae una zona. Puro. `None` si no se puede saber."""
    try:
        d = float(depth)
    except (TypeError, ValueError):
        return None
    if d < 0:
        return None
    if d <= 0.10:
        return CUBOS_PROFUNDIDAD[0]
    if d <= 0.20:
        return CUBOS_PROFUNDIDAD[1]
    if d <= CORTE_DEL_PLAN:
        return CUBOS_PROFUNDIDAD[2]
    return CUBOS_PROFUNDIDAD[3]


def con_cubo_de_profundidad(registros: list) -> list:
    """Los mismos registros con su tramo de profundidad puesto. Puro.

    Se añade un campo en vez de tocar `bucket`: `bucket` es la fuerza y hay experimentos
    vivos que la usan. Dos criterios distintos no pueden compartir columna.
    """
    salida = []
    for r in registros or []:
        cubo = cubo_de_profundidad(r.get("depth"))
        if cubo:
            salida.append({**r, "cubo_profundidad": cubo})
    return salida


def veredicto_profundidad(d: dict, ruido: dict) -> dict:
    """¿Aguantan menos las zonas más profundas? Puro.

    LA DIRECCIÓN LA FIJA EL NÚMERO QUE YA ESTÁ EN PRODUCCIÓN, NO YO

    `MAX_PLAN_DEPTH = 0,30` afirma que una zona a más del 30% bajo el precio no merece
    enseñarse como zona de compra. Eso solo tiene sentido si las zonas profundas aguantan
    PEOR. Así que se prueba exactamente eso: cuanto menos profunda, más aguanta.

    Si sale al revés —las profundas aguantan igual o mejor—, el 0,30 no está protegiendo
    de nada y está escondiendo zonas por ninguna razón medida.
    """
    filas = d.get("cubos") or []
    flacos = [f["cubo"] for f in filas if f["n"] < MUESTRA_MINIMA]
    if flacos:
        return {"estado": SIN_DATOS,
                "conclusion": "Tramos sin muestra suficiente: " + ", ".join(flacos)
                              + ". Sin ellos no hay comparación que hacer."}

    tasas = [f["aguante_pct"] for f in filas]
    observado = ruido.get("observado_pp")
    suelo = ruido.get("azar_p95_pp")
    base = {"aguantes": {f["cubo"]: f["aguante_pct"] for f in filas},
            "rango_pp": observado, "suelo_de_ruido_pp": suelo, "n": d.get("n"),
            "corte_del_plan": CORTE_DEL_PLAN,
            # Cómo se llama la columna en la tabla. La comparte con el experimento de la
            # fuerza, y una tabla de profundidades con «Fuerza» de cabecera estaría
            # diciendo que se midió otra cosa.
            "etiqueta_cubo": "Profundidad"}

    if suelo is None or observado is None:
        return {**base, "estado": SIN_DATOS,
                "conclusion": "No se ha podido medir el suelo de ruido."}
    if observado < suelo:
        n = d.get("n") or 0
        cota = (f" Con {n} toques resueltos, un efecto real mayor que {suelo} pp se "
                "habría visto: si existe algo, es más pequeño que eso."
                if n >= MUESTRA_MINIMA * 10 else
                " La muestra es corta, así que tampoco se puede acotar cuánto.")
        return {**base, "estado": NO_CONCLUYENTE, "cota_superior_pp": suelo,
                "conclusion": f"Los tramos se separan {observado} pp, por debajo del "
                              f"suelo de ruido ({suelo} pp): cabe dentro de lo que el "
                              "azar produce solo. La profundidad NO ordena las zonas por "
                              f"lo bien que aguantan, y el {CORTE_DEL_PLAN:.0%} de "
                              "`MAX_PLAN_DEPTH` sigue sin respaldo." + cota}
    # `tasas` va de menos profundo a más profundo. Que la lista sea DECRECIENTE es que
    # cuanto más hondo, peor — que es lo que el corte de producción da por supuesto.
    if tasas == sorted(tasas, reverse=True):
        return {**base, "estado": VALIDADA,
                "conclusion": f"Cuanto más profunda la zona, menos aguanta: {observado} "
                              f"pp entre el tramo menos hondo y el más hondo, por encima "
                              f"del suelo de ruido ({suelo} pp). El corte del "
                              f"{CORTE_DEL_PLAN:.0%} protege de algo real."}
    return {**base, "estado": RECHAZADA,
            "conclusion": f"Los tramos se separan {observado} pp, por encima del ruido "
                          f"({suelo} pp), pero NO en el orden que el corte da por "
                          f"supuesto: las zonas más profundas no aguantan menos. El "
                          f"{CORTE_DEL_PLAN:.0%} de `MAX_PLAN_DEPTH` está escondiendo "
                          "zonas sin una razón medida."}


def ficha_profundidad(registros: list, universo: list, ventana: int = None) -> dict:
    """El experimento de la profundidad, listo para guardar. Puro."""
    regs = con_cubo_de_profundidad(registros)
    d = aguante_por_cubo(regs, campo="cubo_profundidad", cubos=CUBOS_PROFUNDIDAD)
    ruido = azar_del_aguante(regs, campo="cubo_profundidad", cubos=CUBOS_PROFUNDIDAD)
    v = veredicto_profundidad(d, ruido)
    fechas = [str(r.get("anchor") or "")[:10] for r in regs if r.get("anchor")]
    ficha = {
        "hipotesis_id": "PROFUNDIDAD_MAX_RETROCESO",
        "tipo": "primero",
        "titulo": "¿Aguantan menos las zonas de compra que están más abajo?",
        "metodo": {
            "que_pregunta": "De los soportes tocados, con qué frecuencia el precio rebotó "
                            "sin perder el nivel, agrupados por lo lejos que estaba la "
                            "zona bajo el precio del día.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "desde": min(fechas) if fechas else None,
            "hasta": max(fechas) if fechas else None,
            "motor": "backtest.backtest_universe · walk-forward punto-en-el-tiempo",
            "ventana_dias": ventana,
            "tramos": list(CUBOS_PROFUNDIDAD),
            "muestra_minima_por_tramo": MUESTRA_MINIMA,
            "direccion_esperada": "Cuanto MENOS profunda, MÁS aguanta. Fijada ANTES de "
                                  "ejecutar, y no la elegí yo: es lo que da por supuesto "
                                  "`MAX_PLAN_DEPTH = 0,30`, que hoy esconde las zonas a "
                                  "más del 30% bajo el precio.",
        },
        "controles": {
            "leakage": "Cada zona se calcula con las velas ANTERIORES al ancla y se juzga "
                       "con las posteriores.",
            "la_profundidad_es_la_de_produccion": "Se mide `(precio − nivel) / precio` en "
                                                  "el ancla, que es exactamente la "
                                                  "magnitud que `MAX_PLAN_DEPTH` "
                                                  "gobierna. Medir otra parecida daría un "
                                                  "número que no se podría llevar a ese "
                                                  "parámetro, que es el único motivo de "
                                                  "medirlo.",
            "cortes_pre_registrados": "El 30% es el de producción; los otros dos parten "
                                      "el interior en tercios. Elegir los cortes después "
                                      "de ver dónde separan es la forma más cómoda de "
                                      "fabricar un hallazgo.",
            "suelo_de_ruido": "Se barajan los tramos DENTRO de cada fecha y se toma el "
                              "p95. En un mismo día el mercado entero empuja igual, y "
                              "barajar sin respetar la fecha haría parecer manso al azar.",
            "lo_que_NO_mide": "No dice cuánto se gana entrando en cada tramo, solo con "
                              "qué frecuencia el nivel aguanta. Una zona honda que "
                              "aguanta menos veces puede compensar si paga más cuando "
                              "acierta, y eso exige medir retornos.",
            "no_es_una_recomendacion_de_umbral": "Aunque salga validado, esto NO dice que "
                                                 "0,30 sea el mejor corte: dice que la "
                                                 "profundidad ordena. Buscar el corte "
                                                 "óptimo sobre estos mismos datos sería "
                                                 "ajustarlo a la muestra.",
            "supervivencia": "El universo es el de hoy. Pesa poco: se mide qué pasó tras "
                             "tocar un soporte.",
            "parametros_ajustados": "Ninguno.",
        },
        "resultado": {**d, **v},
        "estado": v["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }
    return ficha


def ficha_profundidad_limpia(registros: list, universo: list,
                             ventana: int = None) -> dict:
    """La profundidad sobre la métrica EXIGENTE, y fuera de la muestra. Pura.

    POR QUÉ HACE FALTA, Y POR QUÉ NO SOBRE LOS MISMOS DATOS

    El intento 1 pre-registró la tasa de «aguantó» y salió plana: 87,9 / 91,0 / 86,7 /
    92,2, cuatro cifras pegadas al 90%. El motivo no fue la profundidad sino la métrica,
    que SATURA — casi todo la cumple, y algo que aprueba al 90% no separa nada. Es el
    mismo fallo de pre-registro que ya cometí con la fuerza de las zonas.

    Al mirar el resultado apareció que el aguante LIMPIO sí se repartía: 31,7 / 40,4 /
    54,8 / 64,1. Treinta y dos puntos, monótonos, y en la dirección CONTRARIA a la que
    `MAX_PLAN_DEPTH` da por supuesta. Pero eso se vio DESPUÉS de tener los datos delante,
    y cambiar de métrica al ver que la primera no separa es cómo se fabrica un hallazgo
    falso. Con la fuerza de las zonas pasó exactamente esto y la réplica lo tumbó.

    Por eso corre sobre OTROS SÍMBOLOS: los del universo de oportunidades que no están en
    watchlist ni en cartera. Dato nuevo para una pregunta ya formulada.

    LA DIRECCIÓN QUE SE PRUEBA SIGUE SIENDO LA DE PRODUCCIÓN

    Se prueba «cuanto menos profunda, más aguanta», que es lo que `MAX_PLAN_DEPTH`
    afirma — NO «cuanto más honda, mejor», que es lo que vi. Fijar como hipótesis lo que
    ya se ha visto es hacerse trampas al solitario. Si vuelve a salir invertido, ESO sí
    sería una réplica, y entonces el 0,30 estaría escondiendo justo las zonas que mejor
    se comportan.

    QUÉ NO RESUELVE ESTA RÉPLICA

    Queda una explicación mecánica en pie: para que una zona al 40% llegue a tocarse, el
    precio ha tenido que caer un 40%. Esos toques ocurren en condiciones distintas, y
    puede que lo que separa no sea la profundidad sino lo que hace falta para llegar
    ahí. Cambiar de símbolos no distingue esas dos cosas; haría falta comparar dentro de
    episodios parecidos, y eso es otro experimento.
    """
    regs = con_cubo_de_profundidad(registros)
    d = aguante_por_cubo(regs, metrica="clean", campo="cubo_profundidad",
                         cubos=CUBOS_PROFUNDIDAD)
    ruido = azar_del_aguante(regs, metrica="clean", campo="cubo_profundidad",
                             cubos=CUBOS_PROFUNDIDAD)
    v = veredicto_profundidad(d, ruido)
    # LA COLUMNA SE LLAMA COMO LO QUE MIDE. Con `metrica="clean"` la tasa que va a la
    # columna principal es la del aguante LIMPIO, y dejarla bajo el rótulo «Aguantó»
    # pondría el número exigente donde se espera el laxo — que es justo la confusión que
    # hizo falta un experimento entero para deshacer.
    v = {**v, "etiqueta_metrica": "Aguantó limpio"}
    fechas = [str(r.get("anchor") or "")[:10] for r in regs if r.get("anchor")]
    return {
        "hipotesis_id": "PROFUNDIDAD_MAX_RETROCESO",
        "tipo": "replica_fuera_de_muestra",
        "deriva_de": "El intento 1 pre-registró la tasa de «aguantó», que satura al 90% y "
                     "no separa. El aguante LIMPIO sí se repartía —32 pp y al revés de lo "
                     "que supone el 0,30— pero eso se vio después de mirar.",
        "titulo": "¿Aguantan LIMPIAMENTE menos las zonas hondas, en símbolos que no vigilas?",
        "metodo": {
            "que_pregunta": "De los soportes tocados, con qué frecuencia el precio rebotó "
                            "SIN llegar a perder el nivel en ningún momento de la ventana, "
                            "agrupados por lo lejos que estaba la zona bajo el precio.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "desde": min(fechas) if fechas else None,
            "hasta": max(fechas) if fechas else None,
            "motor": "backtest.backtest_universe · walk-forward punto-en-el-tiempo",
            "ventana_dias": ventana,
            "tramos": list(CUBOS_PROFUNDIDAD),
            "muestra_minima_por_tramo": MUESTRA_MINIMA,
            "direccion_esperada": "Cuanto MENOS profunda, MÁS aguanta limpio — que es lo "
                                  "que afirma `MAX_PLAN_DEPTH = 0,30`, y NO «cuanto más "
                                  "honda mejor», que es lo que se vio en la muestra "
                                  "anterior. Fijar como hipótesis lo ya visto es hacerse "
                                  "trampas.",
        },
        "controles": {
            "leakage": "Cada zona se calcula con las velas ANTERIORES al ancla y se juzga "
                       "con las posteriores.",
            "fuera_de_muestra": "Símbolos distintos de los del intento 1: ni watchlist ni "
                                "cartera. Dato nuevo para una pregunta ya formulada, no el "
                                "mismo dato mirado dos veces.",
            "por_que_cambia_la_metrica": "El intento 1 salió plano porque «aguantó» satura "
                                         "al 90%. El cambio se hizo DESPUÉS de ver el "
                                         "resultado, y por eso corre sobre otros símbolos: "
                                         "es la única forma de que el cambio no valga como "
                                         "hallazgo por sí mismo.",
            "que_contaria_como_fallo": "Que los tramos se separen por debajo del suelo de "
                                       "ruido. Eso dejaría lo visto en el intento 1 en "
                                       "«solo pasó allí», y `MAX_PLAN_DEPTH` seguiría sin "
                                       "respaldo ni a favor ni en contra.",
            "la_profundidad_es_la_de_produccion": "Se mide `(precio − nivel) / precio` en "
                                                  "el ancla, la magnitud que "
                                                  "`MAX_PLAN_DEPTH` gobierna.",
            "cortes_pre_registrados": "Los mismos del intento 1, sin tocar. El 30% es el "
                                      "de producción.",
            "lo_que_NO_descarta": "Para que una zona al 40% llegue a tocarse, el precio ha "
                                  "tenido que caer un 40%. Esos toques ocurren en "
                                  "condiciones distintas, y puede que lo que separa no sea "
                                  "la profundidad sino lo que hace falta para llegar ahí. "
                                  "Cambiar de símbolos NO distingue esas dos cosas.",
            "lo_que_NO_mide": "No dice cuánto se gana entrando en cada tramo, solo con qué "
                              "frecuencia el nivel aguanta sin romperse.",
            "supervivencia": "El universo es el de hoy. Pesa poco: se mide qué pasó tras "
                             "tocar un soporte.",
            "parametros_ajustados": "Ninguno.",
        },
        "resultado": {**d, **v},
        "estado": v["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }


def ficha_aguante(registros: list, universo: list, ventana: int = None) -> dict:
    """El experimento del aguante, listo para guardar. Puro."""
    d = aguante_por_cubo(registros)
    ruido = azar_del_aguante(registros)
    v = veredicto_aguante(d, ruido)
    fechas = [str(r.get("anchor") or "")[:10] for r in (registros or []) if r.get("anchor")]
    return {
        "hipotesis_id": "FUERZA_DE_LAS_ZONAS",
        "tipo": "primero",
        "titulo": "¿Aguantan más las zonas de compra que el motor puntúa como fuertes?",
        "metodo": {
            "que_pregunta": "De los soportes que el precio llegó a TOCAR, con qué "
                            "frecuencia rebotó antes de romperse, agrupado por el cubo de "
                            "fuerza que les asignó `levels_engine`.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "desde": min(fechas) if fechas else None,
            "hasta": max(fechas) if fechas else None,
            "motor": "backtest.backtest_universe · walk-forward punto-en-el-tiempo",
            "ventana_dias": ventana,
            "cubos": list(CUBOS_FUERZA),
            "muestra_minima_por_cubo": MUESTRA_MINIMA,
            "direccion_esperada": "débil < media < fuerte en tasa de aguante. Fijada "
                                  "ANTES de ejecutar, y no la elegí yo: es lo que afirma "
                                  "el propio número que la pantalla enseña.",
        },
        "controles": {
            "leakage": "Cada zona se calcula con las velas ANTERIORES al ancla y se juzga "
                       "con las posteriores. Lo garantiza `backtest._walk_forward_records`, "
                       "que es el mismo motor que sirve los dos endpoints de backtest.",
            "solo_los_tocados": "Un nivel que el precio no llegó a tocar no aguantó ni se "
                                "rompió. Contarlo de cualquiera de las dos formas sería "
                                "inventar el dato, así que se excluye.",
            "por_que_esta_pregunta_tiene_mas_fuerza": "El resultado es binario, hay miles "
                                                      "de toques en vez de ~1.900 "
                                                      "observaciones, y el evento es "
                                                      "local: depende mucho menos del "
                                                      "régimen del año que un retorno "
                                                      "trimestral.",
            "supervivencia": "El universo es el de hoy. Aquí pesa poco: se mide qué pasó "
                             "al tocar un soporte, no qué acción acabó sobreviviendo.",
            "costes": "Ninguno. No es una estrategia: mide si una etiqueta que ya se "
                      "enseña en pantalla describe algo real.",
            "parametros_ajustados": "Ninguno. Los cubos (75/50) y las tolerancias son los "
                                    "que `backtest.py` ya usaba en producción; no se han "
                                    "movido para este experimento.",
        },
        "resultado": {**d, **v, "ruido": ruido},
        "estado": v["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }


def ficha_aguante_limpio(registros: list, universo: list, ventana: int = None,
                         fuera_de_muestra: bool = True) -> dict:
    """El aguante LIMPIO, y fuera de la muestra donde se vio el patrón. Pura.

    POR QUÉ HACE FALTA UN SEGUNDO EXPERIMENTO Y POR QUÉ NO SOBRE LOS MISMOS DATOS

    El primero pre-registró la tasa de «aguantó» y salió plana: 88,0 / 87,2 / 87,8, ocho
    décimas entre el mejor y el peor. El motivo no fue el score sino la métrica: el
    criterio SATURA —casi todo lo cumple— y algo que aprueba al 88% no puede separar
    nada. Eso fue un fallo de mi pre-registro.

    Al mirar el resultado apareció que la tasa de aguante LIMPIO sí se repartía —36,2 /
    47,3 / 34,5— y encima no era monótona: la mejor era «media». Pero eso se vio DESPUÉS
    de tener los datos delante, y cambiar de métrica al ver que la primera no separaba es
    exactamente cómo se fabrica un hallazgo falso.

    Por eso este experimento corre sobre OTROS SÍMBOLOS: los del universo de
    oportunidades que no están en tu watchlist ni en tu cartera. No es el mismo dato
    mirado dos veces, son datos nuevos para una pregunta que ya estaba formulada.

    LA DIRECCIÓN SIGUE SIENDO LA DEL SCORE, NO LA QUE VI

    Se prueba «débil < media < fuerte», que es lo que el número afirma, y no «media es la
    mejor», que es lo que vi. Si volviera a salir que la mejor es «media», ESO sí sería
    una réplica y merecería mirarse. Fijar como hipótesis lo que ya se ha visto es
    hacerse trampas al solitario.
    """
    d = aguante_por_cubo(registros, metrica="clean")
    ruido = azar_del_aguante(registros, metrica="clean")
    # Mismo motivo: aquí la columna principal ya trae la tasa LIMPIA. Llevaba desde que
    # existe este experimento con el rótulo del otro.
    v = {**veredicto_aguante(d, ruido), "etiqueta_metrica": "Aguantó limpio"}
    fechas = [str(r.get("anchor") or "")[:10] for r in (registros or []) if r.get("anchor")]
    return {
        "hipotesis_id": "FUERZA_DE_LAS_ZONAS",
        "tipo": "replica_fuera_de_muestra",
        "deriva_de": "El primero pre-registró la tasa de «aguantó», que satura al 88% y no "
                     "separa. El aguante LIMPIO sí se repartía, pero eso se vio después.",
        "titulo": "¿Aguantan LIMPIAMENTE más las zonas fuertes, en símbolos que no vigilas?",
        "metodo": {
            "que_pregunta": "De los soportes tocados, con qué frecuencia el precio rebotó "
                            "SIN llegar a perder el nivel en ningún momento de la ventana.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "fuera_de_muestra": fuera_de_muestra,
            "desde": min(fechas) if fechas else None,
            "hasta": max(fechas) if fechas else None,
            "motor": "backtest.backtest_universe · walk-forward punto-en-el-tiempo",
            "ventana_dias": ventana,
            "cubos": list(CUBOS_FUERZA),
            "muestra_minima_por_cubo": MUESTRA_MINIMA,
            "direccion_esperada": "débil < media < fuerte, que es lo que el score afirma "
                                  "— NO «media es la mejor», que es lo que se vio en la "
                                  "muestra anterior. Fijar como hipótesis lo ya visto es "
                                  "hacerse trampas.",
        },
        "controles": {
            "leakage": "Cada zona se calcula con las velas ANTERIORES al ancla y se juzga "
                       "con las posteriores, igual que el primero.",
            "fuera_de_muestra": "Símbolos del universo de oportunidades que NO están en "
                                "watchlist ni en cartera. No es el mismo dato mirado dos "
                                "veces: es dato nuevo para una pregunta ya formulada.",
            "hipotesis_probadas": "Esta es la SEGUNDA métrica que se prueba sobre la "
                                  "misma idea. Aunque los datos sean otros, la cuenta "
                                  "sube: dos intentos dan el doble de oportunidades a "
                                  "que algo salga por azar, y el resultado hay que "
                                  "leerlo con esa cifra delante.",
            "metrica_mas_exigente": "«Limpio» pide rebotar SIN haber perdido el nivel en "
                                    "ningún momento. Por eso reparte donde «aguantó» "
                                    "saturaba: aprueba a un tercio, no al 88%.",
            "supervivencia": "El universo de oportunidades es el de hoy. Pesa poco: se "
                             "mide qué pasó al tocar un soporte, no qué acción sobrevivió.",
            "costes": "Ninguno. No es una estrategia.",
            "parametros_ajustados": "Ninguno. Cubos y tolerancias son los de "
                                    "`backtest.py` en producción.",
        },
        "resultado": {**d, **v, "ruido": ruido, "metrica": "clean"},
        "estado": v["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }


# ── Cuarta hipótesis: ¿dónde poner el stop? ─────────────────────────────────
#
# `_deterministic_levels` coloca los stops en 1,0 / 1,6 / 2,4 × ATR bajo la estructura.
# Están en producción y nunca se han medido. Es el número donde equivocarse cuesta dinero
# de verdad: demasiado ajustado te saca de operaciones que iban bien.
#
# POR QUÉ ESTA PREGUNTA TIENE POTENCIA
#
# Resultado binario —el stop saltó o no— y el mismo toque sirve para evaluar los TRES
# múltiplos, porque un stop en L−m·ATR salta exactamente cuando la excursión adversa
# llega a `m`. Miles de toques, sin backtest nuevo.
#
# QUÉ NO SE PUEDE PREGUNTAR AQUÍ, Y ES IMPORTANTE
#
# «Cuántas veces salta cada múltiplo» está determinado por aritmética: si el precio no
# bajó 1,0 ATR, tampoco bajó 2,4. Un stop más ancho salta menos SIEMPRE, y comprobarlo no
# sería evidencia de nada.
#
# Lo que no es aritmético es la calidad de esos saltos: de las veces que salta, ¿cuántas
# eran ruido? Un stop ancho salta menos, pero cuando salta, ¿acierta más? Esa es la
# pregunta, y la respuesta útil no es un orden sino un NIVEL — «el de 1,0 salta en falso
# el X% de las veces» es lo que `calibracion` pide.
#
# EL CONTRASTE NO ES UNA PERMUTACIÓN, Y POR QUÉ
#
# En los experimentos anteriores cada observación tenía UNA etiqueta y barajarlas medía
# el azar. Aquí cada toque se evalúa con los tres múltiplos a la vez: es una comparación
# PAREADA y no hay etiqueta que barajar. Se usa un remuestreo por bloques de fecha sobre
# la diferencia entre el más ajustado y el más ancho; si la banda incluye el cero, los
# múltiplos no se distinguen.

#: Los múltiplos que `_deterministic_levels` usa HOY en producción. No se eligen aquí:
#: se miden los que ya están puestos.
MULTIPLOS_STOP = (1.0, 1.6, 2.4)

#: Remuestreos del bootstrap. Mismo orden que las vueltas del azar y por lo mismo: sitúa
#: la banda sin que la medición tarde más que el experimento que audita.
VUELTAS_BOOTSTRAP = 200


def _falsos_de(registros: list, m: float) -> dict:
    """Qué hace un stop a `m`×ATR sobre estos toques. Puro.

    Solo cuentan los toques donde el stop LLEGÓ a saltar: de los que no saltan no se
    puede decir si habrían sido un acierto o un error.
    """
    saltan = [r for r in (registros or [])
              if r.get("mae_atr") is not None and r.get("held") is not None
              and r["mae_atr"] >= m]
    # FALSO = saltó y el nivel acabó aguantando. Te sacó de una operación que iba bien.
    falsos = [r for r in saltan if r["held"]]
    buenos = [r for r in saltan if not r["held"]]
    ahorros = sorted(round(r["mae_atr"] - m, 3) for r in buenos)
    evaluables = [r for r in (registros or [])
                  if r.get("mae_atr") is not None and r.get("held") is not None]
    return {
        "multiplo": m,
        "n_evaluables": len(evaluables),
        "n_saltan": len(saltan),
        "salta_pct": round(len(saltan) / len(evaluables) * 100, 1) if evaluables else None,
        "falsos_pct": round(len(falsos) / len(saltan) * 100, 1) if saltan else None,
        # Cuánto MÁS cayó el precio por debajo del stop cuando el corte fue acertado. Es
        # lo que el stop te ahorró, medido en ATR. Mediana: unas pocas caídas enormes no
        # pueden decidir dónde se pone un stop.
        "ahorro_atr_mediana": _percentil(ahorros, 0.5),
    }


def stops(registros: list) -> dict:
    """Los tres múltiplos, evaluados sobre los mismos toques. Puro."""
    return {"multiplos": [_falsos_de(registros, m) for m in MULTIPLOS_STOP],
            "n": len([r for r in (registros or [])
                      if r.get("mae_atr") is not None and r.get("held") is not None])}


def juzgables(registros: list) -> list:
    """Los múltiplos con saltos suficientes para poder decir algo de ellos. Puro.

    Uno que casi nunca actúa no se puede evaluar, y fingir que sí sería peor que
    excluirlo. Se excluye por MUESTRA, nunca por resultado, y el veredicto dice cuáles
    se han quedado fuera y con cuántos casos.
    """
    return [f["multiplo"] for f in stops(registros)["multiplos"]
            if (f["n_saltan"] or 0) >= MUESTRA_MINIMA]


def banda_de_la_diferencia(registros: list, vueltas: int = None) -> dict:
    """Cuánto se distingue el más ajustado del más ancho, con su incertidumbre. Puro.

    Remuestreo por BLOQUES DE FECHA, no por toques sueltos: los toques del mismo día
    comparten mercado, y tratarlos como independientes estrecharía la banda y haría
    parecer seguro lo que no lo es. Es el mismo motivo por el que las permutaciones de
    los otros experimentos se hacen dentro de cada fecha.
    """
    import random
    vueltas = VUELTAS_BOOTSTRAP if vueltas is None else vueltas
    generador = random.Random(SEMILLA)

    por_fecha = {}
    for r in registros or []:
        if r.get("mae_atr") is not None and r.get("held") is not None:
            por_fecha.setdefault(r.get("anchor"), []).append(r)
    fechas = list(por_fecha)
    if len(fechas) < 3:
        return {"vueltas": 0}

    # Los dos EXTREMOS de los que sí se pueden juzgar. Con los tres fijos, un múltiplo
    # que casi nunca actúa dejaba la banda sin calcular y se perdía una comparación
    # perfectamente válida entre los otros dos.
    evaluables = juzgables(registros)
    if len(evaluables) < 2:
        return {"vueltas": 0, "juzgables": evaluables}
    ajustado, ancho = evaluables[0], evaluables[-1]

    def _dif(regs):
        a = _falsos_de(regs, ajustado)["falsos_pct"]
        b = _falsos_de(regs, ancho)["falsos_pct"]
        return None if a is None or b is None else round(a - b, 2)

    observada = _dif([r for rs in por_fecha.values() for r in rs])
    extremos = (ajustado, ancho)
    muestras = []
    for _ in range(vueltas):
        elegidas = [generador.choice(fechas) for _ in fechas]
        regs = [r for f in elegidas for r in por_fecha[f]]
        d = _dif(regs)
        if d is not None:
            muestras.append(d)
    muestras.sort()
    if not muestras:
        return {"vueltas": 0, "observada_pp": observada}
    return {
        "observada_pp": observada,
        "vueltas": len(muestras),
        "banda_baja_pp": _percentil(muestras, 0.05),
        "banda_alta_pp": _percentil(muestras, 0.95),
        "bloques": len(fechas),
        "comparados": list(extremos),
        "juzgables": evaluables,
    }


def veredicto_stops(d: dict, banda: dict) -> dict:
    """¿Distingue algo el múltiplo del stop? Puro.

    La dirección se fijó antes de mirar y es la que justifica tener tres múltiplos: uno
    más ajustado salta en falso MÁS a menudo que uno más ancho. Si no fuera así, los tres
    números de producción estarían distinguiendo solo el tamaño de la pérdida, no la
    calidad del corte.
    """
    filas = d.get("multiplos") or []
    con_muestra = [f for f in filas if (f["n_saltan"] or 0) >= MUESTRA_MINIMA]
    flacos = [f for f in filas if (f["n_saltan"] or 0) < MUESTRA_MINIMA]
    aviso = ""
    if flacos:
        # SE EXCLUYEN POR MUESTRA, NO POR RESULTADO, y se dice con cuántos casos.
        #
        # La primera versión se rendía entera si fallaba UNO de los tres, y tiraba una
        # comparación válida entre los otros dos. Un múltiplo tan ancho que casi nunca
        # actúa no se puede evaluar — pero eso no impide evaluar los que sí actúan.
        aviso = (" Fuera por falta de saltos: "
                 + ", ".join(f"{f['multiplo']}×ATR ({f['n_saltan']})" for f in flacos)
                 + ". Un stop que casi nunca actúa no se puede juzgar.")
    if len(con_muestra) < 2:
        return {"estado": SIN_DATOS,
                "conclusion": "Hacen falta al menos dos múltiplos con saltos suficientes "
                              "para compararlos." + aviso}

    falsos = [f["falsos_pct"] for f in con_muestra]
    # LAS CLAVES VAN EN TEXTO PORQUE MONGO NO ADMITE OTRA COSA. Con el múltiplo como
    # número (1.0, 1.6, 2.4) el documento se calcula entero y luego revienta al
    # insertarlo, y como el fallo se recoge, la pantalla queda exactamente igual que si
    # el botón no hiciera nada: sin error, sin línea nueva.
    base = {"falsos_pct": {str(f["multiplo"]): f["falsos_pct"] for f in filas},
            "ahorro_atr": {str(f["multiplo"]): f["ahorro_atr_mediana"] for f in filas},
            "juzgados": [f["multiplo"] for f in con_muestra],
            "sin_muestra": [f["multiplo"] for f in flacos],
            "banda": banda, "n": d.get("n")}

    baja, alta = banda.get("banda_baja_pp"), banda.get("banda_alta_pp")
    if baja is None or alta is None:
        return {**base, "estado": SIN_DATOS,
                "conclusion": "No se ha podido acotar la diferencia."}
    if baja <= 0 <= alta:
        return {**base, "estado": NO_CONCLUYENTE,
                "conclusion": f"La diferencia entre {MULTIPLOS_STOP[0]}×ATR y "
                              f"{MULTIPLOS_STOP[-1]}×ATR en saltos en falso es de "
                              f"{banda.get('observada_pp')} pp, pero su banda va de "
                              f"{baja} a {alta} pp e incluye el cero: no se distinguen. "
                              "Los tres múltiplos de producción cortan con la misma "
                              "calidad; lo único que cambia es cuánto pierdes cuando "
                              "aciertan." + aviso}
    if falsos == sorted(falsos, reverse=True):
        return {**base, "estado": VALIDADA,
                "conclusion": f"El stop más ajustado salta en falso más a menudo, en la "
                              f"dirección fijada antes de mirar: {banda.get('observada_pp')} "
                              f"pp de diferencia, banda de {baja} a {alta}. Los números "
                              "de producción sí distinguen la calidad del corte." + aviso}
    return {**base, "estado": RECHAZADA,
            "conclusion": f"Los múltiplos se distinguen (banda de {baja} a {alta} pp) "
                          "pero NO en la dirección esperada: el stop más ancho salta en "
                          "falso MÁS que el ajustado. Eso invierte el motivo de tener "
                          "tres." + aviso}


def ficha_stops(registros: list, universo: list, ventana: int = None) -> dict:
    """El experimento de los stops, listo para guardar. Puro."""
    d = stops(registros)
    banda = banda_de_la_diferencia(registros)
    v = veredicto_stops(d, banda)
    fechas = [str(r.get("anchor") or "")[:10] for r in (registros or []) if r.get("anchor")]
    ficha = {
        "hipotesis_id": "ATR_MULTIPLO_STOP",
        "tipo": "primero",
        "titulo": "¿Los tres múltiplos de stop distinguen un corte bueno de uno en falso?",
        "metodo": {
            "que_pregunta": "De los toques donde el stop llegó a saltar, qué porcentaje "
                            "eran ruido —el nivel acabó aguantando— para cada múltiplo.",
            "universo": sorted(universo or []),
            "simbolos": len(universo or []),
            "desde": min(fechas) if fechas else None,
            "hasta": max(fechas) if fechas else None,
            "motor": "backtest.backtest_universe · walk-forward punto-en-el-tiempo",
            "ventana_dias": ventana,
            "multiplos": list(MULTIPLOS_STOP),
            "muestra_minima_por_multiplo": MUESTRA_MINIMA,
            "direccion_esperada": "El más ajustado salta en falso MÁS que el más ancho. "
                                  "Fijada ANTES de ejecutar, y es lo que justifica tener "
                                  "tres múltiplos distintos en producción.",
        },
        "controles": {
            "leakage": "El stop se evalúa con las velas POSTERIORES al toque, y el nivel "
                       "se calcula con las anteriores al ancla.",
            "no_se_prueba_lo_aritmetico": "«Cuántas veces salta cada múltiplo» está "
                                          "determinado: si el precio no bajó 1,0 ATR, "
                                          "tampoco bajó 2,4. Eso se informa pero NO se "
                                          "juzga — comprobar una identidad no es medir.",
            "solo_hasta_la_resolucion": "La excursión adversa se mide mientras la "
                                        "operación está viva. Una caída posterior al "
                                        "rebote no habría saltado ningún stop, y "
                                        "contarla haría parecer peligrosos stops que "
                                        "nunca corrieron riesgo.",
            "por_que_no_hay_permutacion": "Cada toque se evalúa con los TRES múltiplos a "
                                          "la vez: es una comparación pareada y no hay "
                                          "etiqueta que barajar. Se usa remuestreo por "
                                          "bloques de fecha sobre la diferencia.",
            "bloques_por_fecha": "Los toques del mismo día comparten mercado. "
                                 "Remuestrear toques sueltos estrecharía la banda y "
                                 "haría parecer seguro lo que no lo es.",
            "lo_que_NO_mide": "No compara la ganancia perdida al salir en falso contra "
                              "la pérdida evitada. Eso exige medir retornos, y con esta "
                              "muestra los retornos están dominados por el ruido.",
            "supervivencia": "El universo es el de hoy. Pesa poco: se mide qué pasó tras "
                             "tocar un soporte.",
            "parametros_ajustados": "Ninguno. Los tres múltiplos son los de producción.",
            "cambio_tras_el_primer_intento": "El intento 1 salió SIN MUESTRA porque "
                                             "2,4×ATR solo saltó 16 veces — es tan ancho "
                                             "que apenas actúa. El veredicto se rendía "
                                             "entero y tiraba la comparación válida entre "
                                             "1,0 y 1,6. Ahora se juzgan los que tienen "
                                             "muestra y se dice cuáles quedan fuera. El "
                                             "cambio se hizo DESPUÉS de ver el resultado, "
                                             "así que conviene saber que la exclusión es "
                                             "por muestra y nunca por resultado, que la "
                                             "dirección no se tocó, y que el excluido "
                                             "tenía 0% de falsos — el dato MÁS favorable "
                                             "a la hipótesis. Dejarlo fuera juega en "
                                             "contra de lo que se quiere demostrar.",
        },
        "resultado": {**d, **v},
        "estado": v["estado"],
        "ejecutado_en": _ahora(),
        "lab_v": 1,
    }
    # LA MUESTRA EFECTIVA SON LOS BLOQUES, NO LOS SALTOS, y tiene que leerse al lado del
    # resultado. El remuestreo es por fecha porque los toques del mismo día comparten
    # mercado; eso es lo correcto, pero significa que 166 saltos repartidos en 23 días
    # son 23 unidades independientes, no 166. Sin esto la banda se lee como si tuviera
    # detrás un tamaño de muestra que no tiene.
    bloques = banda.get("bloques")
    if bloques:
        ficha["controles"]["muestra_efectiva"] = (
            f"El remuestreo tiene {bloques} bloques de fecha. Ésa es la muestra "
            f"independiente: los saltos del mismo día no cuentan por separado. Con "
            f"pocos bloques la banda es real, pero descansa sobre poco.")
    return ficha


def ficha_stops_fuera(registros: list, universo: list, ventana: int = None) -> dict:
    """Los mismos stops, en símbolos que no vigilas. Pura.

    POR QUÉ NO BASTA CON EL PRIMERO

    El intento 1 salió VALIDADO: 22,9% de saltos en falso con 1,0xATR contra 5,6% con
    1,6xATR, banda de 12,48 a 21,8 pp sin tocar el cero. Dos cosas piden una replica
    antes de que eso gobierne una decision.

    La primera: la regla de exclusion por muestra se escribio DESPUES de ver el intento
    1. Esta declarada y juega en contra de la hipotesis, pero se escribio despues.

    La segunda, y pesa mas: el universo son TUS simbolos. Los elegiste tu, y el mismo
    motor que dibuja los niveles es el que decide donde mirarlos. Aqui corre sobre los
    del universo de oportunidades que NO estan en tu watchlist ni en tu cartera.

    LA DIRECCION ES LA MISMA Y NO SE TOCA

    Se prueba «el mas ajustado salta en falso MAS que el mas ancho», que es lo que
    justifica tener tres multiplos en produccion. Es la misma frase del intento 1. Ya
    paso con el aguante: la primera metrica saturaba, cambie de metrica al ver el
    resultado, y la replica fuera de muestra lo tumbo. Ese es el trabajo de esto.
    """
    f = ficha_stops(registros, universo, ventana)
    f["tipo"] = "replica_fuera_de_muestra"
    f["titulo"] = ("¿El stop ajustado sigue cortando en falso más, en símbolos que no "
                   "vigilas?")
    f["deriva_de"] = ("El intento 1 salió validado sobre TUS símbolos, y con una regla "
                      "de exclusión escrita después de ver el resultado.")
    f["controles"]["fuera_de_muestra"] = (
        "Símbolos distintos de los del intento 1: ni watchlist ni cartera. Dato nuevo "
        "para una pregunta ya formulada, no el mismo dato mirado dos veces.")
    f["controles"]["que_contaria_como_fallo"] = (
        "Que la banda incluya el cero, o que el ajustado NO salte en falso más que el "
        "ancho. Cualquiera de las dos deja el hallazgo del intento 1 en «solo pasó "
        "allí», y los múltiplos de producción siguen sin respaldo.")
    return f


# ── Persistencia. Todo queda, también lo que salió mal ───────────────────────

def claves_en_texto(valor):
    """Deja el documento en algo que Mongo admita: claves de texto, y nada más. Puro.

    Mongo solo acepta cadenas como clave. Un experimento que agrupa por un número —el
    múltiplo del stop, un percentil, un año— produce un documento perfectamente válido
    en Python que revienta al insertarlo. Como el fallo de guardado se recoge para no
    tumbar la petición, el resultado era un botón que corría minutos y no dejaba rastro.

    Convierte, no descarta: el número sigue estando, escrito. Y no toca nada más — si el
    documento falla por otra causa, tiene que seguir fallando y verse.
    """
    if isinstance(valor, dict):
        return {str(k): claves_en_texto(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [claves_en_texto(v) for v in valor]
    return valor


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
        doc = claves_en_texto({**doc, "intento": anteriores + 1})
        await db[COL_EXPERIMENTOS].insert_one(doc)
        return {"ok": True, "intento": doc["intento"], "estado": doc.get("estado")}
    except Exception as e:
        # ERROR y no warning: el experimento ya ha corrido entero —minutos de descarga y
        # de cálculo— y perderlo aquí deja la pantalla exactamente igual que si el botón
        # no hiciera nada. El tipo de excepción va delante porque distingue las dos
        # causas que importan: Mongo caído, o un valor que BSON no sabe codificar.
        logger.error("laboratorio: el experimento %s se ha medido pero NO se ha "
                     "guardado: %s: %s", doc.get("hipotesis_id"),
                     type(e).__name__, str(e)[:200])
        return {"ok": False, "motivo": type(e).__name__, "error": str(e)[:200]}


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
