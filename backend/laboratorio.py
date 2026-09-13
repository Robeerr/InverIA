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
              "NO COPIAR": "no_copiar", "IMPORTANTE": "importante"}
    fuera, actual = {}, None
    for linea in (texto or "").splitlines():
        limpia = linea.strip()
        etiqueta = next((v for k, v in claves.items() if limpia.startswith(k)), None)
        if etiqueta:
            actual = etiqueta
            fuera[actual] = limpia.split(":", 1)[-1].strip() if ":" in limpia else ""
        elif actual and limpia:
            fuera[actual] = (fuera[actual] + " " + limpia).strip()
        elif not limpia:
            actual = None
    return fuera


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
                # Un umbral con número ya no es una hipótesis: es una regla en vigor.
                "estado": VALIDADA if valor is not None else (LISTA if medible else IDEA),
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
