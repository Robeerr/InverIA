"""Cuánto RIESGO DE CARTERA retira una venta. No cuánto margen devuelve DEGIRO.

POR QUÉ EXISTE

Con perfil Trader, el "Margen libre" de DEGIRO no es un contador de caja: es el valor de
garantía menos el RIESGO que su modelo asigna a la cartera. Vender mueve dinero de
"cartera" a "efectivo" dentro de la misma ecuación, así que ese movimiento por sí solo no
explica nada: lo que mueve el margen libre es cuánto baja el riesgo. De ahí que vender
1.000 € de una acción dispare el margen y vender 1.000 € de otra no lo mueva —y que la
propia ayuda de DEGIRO tenga una página dedicada a explicar que, si la operación "no tiene
un impacto suficiente en el riesgo de su cartera", el margen no cambiará o apenas lo hará.

EL MODELO, Y POR QUÉ EL MÁXIMO LO CAMBIA TODO

DEGIRO calcula cuatro componentes y se queda con el MAYOR, no con la suma. Eso es lo que
produce el comportamiento que desconcierta: si vendes algo que NO era el componente que
marcaba el máximo, el máximo lo sigue fijando otra cosa y el riesgo no baja nada.

LO QUE ESTO NO ES

Una reproducción del margen libre de DEGIRO. Faltan tres piezas y ninguna es obtenible:

  · la CATEGORÍA A-D del instrumento, que fija su porcentaje de riesgo de evento. No está
    en ninguna API ni en ningún CSV. Aquí se aplica el mismo porcentaje a todas, así que
    el componente de evento ordena SOLO por tamaño. Una acción en categoría C o D lleva
    mucho más riesgo del que este cálculo ve, y ahí la estimación se queda corta.
  · la TAXONOMÍA sectorial de DEGIRO, que no coincide con la de yfinance ni con la que el
    usuario escribe a mano.
  · el EFECTIVO y la deuda de la cuenta, sin los cuales no hay cifra absoluta posible.

Por eso este módulo devuelve una CLASE (ALTO/MEDIO/BAJO) y un índice relativo, nunca euros
de margen. La diferencia no es de precisión: es que una cifra en euros afirmaría algo que
no podemos sostener.

Aritmética pura: sin red, sin base de datos, sin fechas. Se prueba entera con listas.
"""

from typing import List, Optional

# Porcentajes del modelo de riesgo de DEGIRO, perfil TRADER.
#
# El de evento es el publicado para una acción de categoría A (62,50% en Trader; en Active
# sería 83,75%). Como la categoría real de cada acción no se puede saber, se aplica el
# mismo a todas: eso mantiene el ORDEN entre posiciones, que es lo único que esta
# estimación afirma.
P_EVENTO = 0.625          # sobre la posición individual mayor
P_NETO_CATEGORIA = 0.20   # sobre el neto de la categoría de inversión
P_SECTOR = 0.30           # sobre el neto del sector mayor
P_BRUTO = 0.07            # sobre el bruto de la cartera

# UMBRALES — se recalibran con operaciones reales, por eso están aquí y con nombre.
#
# El índice `r` se mide contra una venta GENÉRICA del mismo importe: el componente del 20%
# siempre baja en esa proporción, así que r = 1,0 es "una venta normal". Los cortes son
# una banda de ±50% alrededor de esa referencia, no un umbral por importe.
UMBRAL_MEDIO = 0.5        # por debajo: retira menos de la mitad que una venta normal
UMBRAL_ALTO = 1.5         # por encima: retira vez y media o más

ALTO, MEDIO, BAJO = "ALTO", "MEDIO", "BAJO"
SIN_ESTIMACION = "SIN_ESTIMACION"

# Nombres legibles de cada componente, para poder enseñar cuál manda sin traducir en la
# pantalla —que es donde una traducción a mano se queda vieja.
NOMBRES = {
    "evento": "mayor posición individual",
    "neto_categoria": "peso total de la cartera",
    "sector": "concentración sectorial",
    "bruto": "bruto de la cartera",
}


def _valida(posiciones: List[dict]):
    """Qué le falta a la cartera para poder estimar. Lista vacía = se puede.

    Una posición sin sector o sin valorar no se puede "estimar igualmente": entraría en
    los totales como si valiera cero y hundiría el componente que quizá manda. Un hueco
    que se ve es mejor que una clase que parece calculada.
    """
    sin_sector = [p.get("symbol") for p in posiciones
                  if not (p.get("sector") or "").strip()]
    sin_valor = [p.get("symbol") for p in posiciones if p.get("valor_eur") is None]
    faltas = []
    if sin_sector:
        faltas.append(("sector", sorted(s for s in sin_sector if s)))
    if sin_valor:
        faltas.append(("valor", sorted(s for s in sin_valor if s)))
    return faltas


def componentes(posiciones: List[dict]) -> dict:
    """Los cuatro componentes de riesgo de una cartera, en euros."""
    valores = [float(p["valor_eur"]) for p in posiciones if p.get("valor_eur") is not None]
    if not valores:
        return {"evento": 0.0, "neto_categoria": 0.0, "sector": 0.0, "bruto": 0.0}
    total = sum(valores)
    por_sector: dict = {}
    for p in posiciones:
        if p.get("valor_eur") is None:
            continue
        s = (p.get("sector") or "").strip().upper()
        por_sector[s] = por_sector.get(s, 0.0) + float(p["valor_eur"])
    return {
        # Todas las posiciones son LARGAS: el neto de la categoría de inversión coincide
        # con el bruto. Por eso el componente del 7% nunca puede mandar sobre el del 20%
        # —se deja calculado igual, para que el desglose no mienta por omisión.
        "evento": P_EVENTO * max(valores),
        "neto_categoria": P_NETO_CATEGORIA * total,
        "sector": P_SECTOR * max(por_sector.values()),
        "bruto": P_BRUTO * total,
    }


def riesgo(posiciones: List[dict]) -> tuple:
    """(riesgo, componente que manda, todos los componentes).

    El riesgo es el MÁXIMO, no la suma. Es la pieza que explica el comportamiento raro.
    """
    comps = componentes(posiciones)
    dominante = max(comps, key=comps.get)
    return comps[dominante], dominante, comps


def _motivo(clase: str, dom_antes: str, dom_despues: str, es_dominante: bool) -> str:
    """Por qué esta venta retira poco, medio o mucho riesgo. En una frase."""
    if clase == BAJO and not es_dominante:
        return (f"Esta posición no es lo que marca el riesgo de tu cartera: lo marca "
                f"{NOMBRES[dom_antes]}. Al venderla, ese factor sigue igual, así que el "
                f"riesgo apenas baja.")
    if clase == BAJO:
        return (f"Aunque {NOMBRES[dom_antes]} sea hoy el factor que manda, al venderla "
                f"toma el relevo {NOMBRES[dom_despues]}, que estaba casi igual de alto. "
                f"El riesgo baja poco.")
    if clase == ALTO:
        return (f"Esta venta retira justo lo que marca el riesgo de tu cartera "
                f"({NOMBRES[dom_antes]}). Al quitarla, el factor que manda pasa a ser "
                f"{NOMBRES[dom_despues]}, mucho más bajo.")
    return (f"Hoy manda {NOMBRES[dom_antes]}; después de la venta mandaría "
            f"{NOMBRES[dom_despues]}. La venta retira riesgo en una proporción parecida "
            f"a la de cualquier otra venta del mismo importe.")


def estimar(posiciones: List[dict], symbol: str) -> dict:
    """Cuánto riesgo de cartera retira vender `symbol`.

    `posiciones` es [{"symbol", "valor_eur", "sector"}]. Devuelve la clase, el índice `r`
    y el desglose antes/después, para que el cálculo se pueda auditar en pantalla.

    NUNCA devuelve euros de margen: el único euro que aparece es el riesgo de cartera de
    cada componente, que es una magnitud del modelo y no dinero disponible.
    """
    sym = (symbol or "").strip().upper()
    posiciones = [p for p in (posiciones or []) if (p.get("symbol") or "").strip()]
    faltas = _valida(posiciones)
    if faltas:
        return {"clase": SIN_ESTIMACION, "faltas": faltas,
                "motivo": _texto_faltas(faltas)}

    vendida = next((p for p in posiciones
                    if (p["symbol"] or "").strip().upper() == sym), None)
    if vendida is None:
        return {"clase": SIN_ESTIMACION, "faltas": [("posicion", [sym])],
                "motivo": f"{sym} no está entre tus posiciones abiertas."}

    importe = float(vendida["valor_eur"])
    if importe <= 0:
        return {"clase": SIN_ESTIMACION, "faltas": [("valor", [sym])],
                "motivo": f"{sym} no tiene un valor con el que calcular nada."}

    r_antes, dom_antes, comps_antes = riesgo(posiciones)
    resto = [p for p in posiciones if p is not vendida]
    if resto:
        r_despues, dom_despues, comps_despues = riesgo(resto)
    else:
        # Vender lo último deja la cartera vacía: riesgo cero y ningún componente que
        # mande. Se dice así en vez de inventar un dominante.
        r_despues, dom_despues, comps_despues = 0.0, None, componentes([])

    retirado = r_antes - r_despues
    # El denominador es lo que retiraría una venta CUALQUIERA del mismo importe: el
    # componente del 20% siempre baja en esa proporción. Así `r` se lee como "veces una
    # venta normal" y no depende del tamaño de la cartera.
    generico = P_NETO_CATEGORIA * importe
    r = retirado / generico if generico else 0.0

    clase = ALTO if r >= UMBRAL_ALTO else (MEDIO if r >= UMBRAL_MEDIO else BAJO)
    es_dominante = (dom_antes == "evento"
                    and abs(comps_antes["evento"] - P_EVENTO * importe) < 1e-6)

    return {
        "clase": clase,
        "symbol": sym,
        "indice": round(r, 3),
        "riesgo_retirado_eur": round(retirado, 2),
        "riesgo_antes_eur": round(r_antes, 2),
        "riesgo_despues_eur": round(r_despues, 2),
        "dominante_antes": dom_antes,
        "dominante_despues": dom_despues,
        "dominante_antes_texto": NOMBRES.get(dom_antes, dom_antes),
        "dominante_despues_texto": NOMBRES.get(dom_despues) if dom_despues else None,
        "componentes_antes": {k: round(v, 2) for k, v in comps_antes.items()},
        "componentes_despues": {k: round(v, 2) for k, v in comps_despues.items()},
        "motivo": _motivo(clase, dom_antes, dom_despues or dom_antes, es_dominante),
        "umbrales": {"medio": UMBRAL_MEDIO, "alto": UMBRAL_ALTO},
    }


def _texto_faltas(faltas) -> str:
    partes = []
    for que, simbolos in faltas:
        if que == "sector":
            partes.append(f"faltan datos de sector en {len(simbolos)} "
                          f"posición{'es' if len(simbolos) != 1 else ''} "
                          f"({', '.join(simbolos)})")
        elif que == "valor":
            partes.append(f"{len(simbolos)} posición"
                          f"{'es' if len(simbolos) != 1 else ''} sin valorar "
                          f"({', '.join(simbolos)})")
    return "No se puede estimar — " + "; ".join(partes) + "."
