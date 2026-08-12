"""Dashboard «Hoy» — qué merece tu atención, y por qué.

Este módulo es SOLO decisión de producto: recibe datos ya calculados por otros y
decide qué sube a la portada, en qué orden y con qué frase. No calcula ni un
número financiero. Esa separación es deliberada: la lógica de niveles, scoring y
cartera está cubierta por 451 tests y no se toca para pintar una portada.

LAS TRES PREGUNTAS

Cada tarjeta responde exactamente a tres cosas, y esos son sus tres campos:

    que_pasa     → ¿Qué está pasando?      "MRVL está a un 1,8% de tu Nivel 3"
    por_que      → ¿Por qué?               "Nivel fuerte (78/100): SMA200 + Fib 38,2%"
    que_vigilar  → ¿Qué debería revisar?   "Si pierde 178,40 el plan cambia"

Un dato que no cabe en ninguna de las tres no entra. Es el filtro que evita que
esto se convierta en un panel de widgets.

PRECEDENCIA

El orden no es una preferencia estética: es lo que decide qué ves cuando abres la
app con treinta segundos. De más a menos urgente:

    1. Se ha roto algo donde tienes dinero  → es lo único que puede costarte hoy
    2. Ha saltado una alerta que pediste    → es una promesa pendiente
    3. Un nivel fuerte está muy cerca       → es la oportunidad con fecha
    4. Tus fuentes y tu motor CHOCAN        → el antídoto contra el bombo
    5. Coinciden sobre algo que no tienes   → la señal de mayor convicción
    6. Resultados en pocos días con dinero dentro

MÁXIMO CINCO, MÍNIMO HONESTO

Cinco es el techo. El suelo no existe: si un día solo hay dos cosas que merezcan
tu atención, salen dos y la pantalla lo dice. Rellenar hasta cinco con lo sexto
más urgente entrena a desconfiar del bloque, que es justo lo contrario de para lo
que existe.

UNA TARJETA POR TICKER

Si MRVL dispara tres reglas, sale UNA tarjeta —la de mayor precedencia— y las
otras dos se doblan dentro como contexto. Tres tarjetas del mismo ticker ocuparían
la portada entera y dirían lo mismo tres veces.
"""

from typing import Optional

# Peso base por tipo. Los huecos entre tramos son grandes a propósito: así los
# ajustes finos (distancia, fuerza) reordenan DENTRO de un tipo y no saltan por
# encima de uno más urgente.
BASE = {
    "ruptura": 1000,
    "alerta": 850,
    "nivel": 700,
    "divergencia": 600,
    "confluencia": 500,
    "resultados": 400,
}

LIMITE_POR_DEFECTO = 5

# Un nivel entra en portada si está a menos de esto. /signals/hot ya filtra al 10%,
# pero un 9% no es "hoy": es "algún día". La portada es para hoy.
UMBRAL_NIVEL_PCT = 4.0

UMBRAL_RESULTADOS_DIAS = 3


def _pct(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_pct(v, decimales=1) -> str:
    n = _pct(v)
    return "—" if n is None else f"{abs(n):.{decimales}f}%"


def _fmt_precio(v) -> str:
    n = _pct(v)
    return "—" if n is None else f"{n:,.2f}"


def _etiqueta_nivel(clave: str) -> str:
    """`nivel3` → «Nivel 3»; `deseado` → «tu precio de venta»."""
    if clave == "deseado":
        return "tu precio de venta"
    if clave and clave.startswith("nivel"):
        return f"tu Nivel {clave[5:]}"
    return clave or "un nivel"


def _tarjeta(tipo, symbol, nombre, urgencia, que_pasa, por_que, que_vigilar,
             datos=None, aviso=None):
    return {
        "tipo": tipo,
        "symbol": symbol,
        "nombre": nombre or symbol,
        "urgencia": round(urgencia),
        "que_pasa": que_pasa,
        "por_que": por_que,
        "que_vigilar": que_vigilar,
        "datos": datos or {},
        # El aviso del motor sobre la calidad del dato. Va PEGADO a la tarjeta que
        # sostiene, nunca suelto: una confianza recortada solo significa algo al lado
        # de la afirmación que recorta.
        "aviso": aviso,
        "ruta": f"/accion/{symbol}",
    }


# ── Reglas ───────────────────────────────────────────────────────────────────

def tarjeta_ruptura(entrada, posicion, indicadores):
    """1 · Tienes dinero dentro y el precio acaba de perder la media de 10 semanas.

    `recien_perdida` es el dato clave y hoy se enseña como un chip de 11px
    indistinguible del resto. Es lo único de toda la portada que puede costarte
    dinero hoy, así que va arriba del todo.
    """
    salida = (indicadores or {}).get("salida_10w") or {}
    if not salida.get("recien_perdida"):
        return None
    if not posicion or not (posicion.get("acciones") or 0) > 0:
        return None

    symbol = entrada.get("symbol")
    pnl = posicion.get("pnl_eur")
    urgencia = BASE["ruptura"]
    # Perder la media con la posición ya en pérdidas es peor que con ganancias.
    if pnl is not None and pnl < 0:
        urgencia += 40

    return _tarjeta(
        "ruptura", symbol, entrada.get("name"), urgencia,
        que_pasa=f"{symbol} acaba de perder su media de 10 semanas",
        por_que=(
            f"Cotiza a {_fmt_precio(salida.get('sma'))} de media y está "
            f"{_fmt_pct(salida.get('distancia_pct'))} por debajo. "
            "Es la señal de salida del método de dejar correr los ganadores."
        ),
        que_vigilar=(
            f"Tienes {posicion.get('acciones')} acciones"
            + (f" con {pnl:+,.0f} € latentes" if pnl is not None else "")
            + ". Decide si la regla de salida aplica o si hay motivo para esperar."
        ),
        datos={
            "sma_10w": salida.get("sma"),
            "distancia_pct": salida.get("distancia_pct"),
            "acciones": posicion.get("acciones"),
            "pnl_eur": pnl,
        },
    )


def tarjeta_alerta(alerta, entrada=None):
    """2 · Ha saltado una alerta que tú pediste. Es una promesa pendiente."""
    symbol = alerta.get("symbol")
    accion = (alerta.get("action") or "").upper()
    etiqueta = _etiqueta_nivel(alerta.get("level_label") or "")
    urgencia = BASE["alerta"]
    diff = _pct(alerta.get("diff_pct"))
    if diff is not None:
        urgencia += max(0, 20 - abs(diff) * 4)

    if alerta.get("type") == "PANICO":
        que_pasa = f"{symbol} se ha desplomado un {_fmt_pct(alerta.get('daily_change_percent'))} en el día"
        por_que = "Saltó la alerta de pánico: una caída fuerte sin más contexto."
        vigilar = "Antes de tocar nada, mira si hay un motivo real detrás de la caída."
    else:
        # El titular dice que la ALERTA se ha disparado, no que el precio "está cerca".
        # Son cosas distintas y la primera es la que exige una decisión: una alerta
        # saltada es una promesa que tú pediste que se cumpliera. El nivel pasa a
        # contexto, que es su papel.
        verbo = "compra" if accion == "COMPRA" else ("venta" if accion == "VENTA" else "precio")
        que_pasa = (f"{symbol}: se ha disparado tu alerta de {verbo} en "
                    f"{_fmt_precio(alerta.get('target'))}")
        por_que = (
            f"Es {etiqueta} de tu tabla y el precio la ha tocado: cotiza a "
            f"{_fmt_precio(alerta.get('price'))}."
        )
        vigilar = "Tú pediste que te avisara aquí. Toca decidir si actúas o mueves el nivel."

    return _tarjeta(
        "alerta", symbol, alerta.get("name") or (entrada or {}).get("name"), urgencia,
        que_pasa=que_pasa, por_que=por_que, que_vigilar=vigilar,
        datos={
            "target": alerta.get("target"),
            "price": alerta.get("price"),
            "accion": accion,
            "nivel": alerta.get("level_label"),
            "fired_at": alerta.get("fired_at"),
        },
    )


def tarjeta_nivel(caliente, nivel_motor=None, aviso=None, tiene_posicion=False,
                  motor_con_datos=False):
    """3 · Un nivel está muy cerca. Con el porqué del motor, si lo hay.

    `caliente` viene de /signals/hot, que ya calcula y ordena la distancia al nivel
    más cercano de TU tabla. `nivel_motor` es la zona de confluencia que el motor
    calcula por su cuenta, con su fuerza y sus métodos coincidentes — es lo que
    convierte «está cerca de un número que escribiste» en «está cerca de un número
    que además tiene respaldo».
    """
    distancia = _pct(caliente.get("pct_away"))
    if distancia is None or distancia > UMBRAL_NIVEL_PCT:
        return None

    symbol = caliente.get("symbol")
    etiqueta = _etiqueta_nivel(caliente.get("level_label") or "")
    fuerza = (nivel_motor or {}).get("strength")
    razones = (nivel_motor or {}).get("reasons") or []

    # Más cerca = más urgente. Y un nivel con respaldo del motor sube sobre uno
    # que solo existe porque lo escribiste a mano.
    urgencia = BASE["nivel"] + max(0, (UMBRAL_NIVEL_PCT - distancia) * 20)
    if fuerza:
        urgencia += min(60, fuerza * 0.6)
    if tiene_posicion:
        urgencia += 15

    # Hay DOS motores y hasta ahora se llamaban igual, que es lo que hacía leer
    # "el motor no tiene zona" como "el motor lo rechaza":
    #
    #   · Motor de NIVELES        → buy_levels con fuerza y métodos. Vive solo en la
    #                               caché en memoria; si el proceso reinicia, no está.
    #   · Motor de OPORTUNIDADES  → el score que cruza con tus fuentes. Persistido en
    #                               Mongo. Es el de las tarjetas de coincidencia.
    #
    # Aquí solo se habla del primero, y se nombra entero para no confundirlos.
    if fuerza and razones:
        estado_motor = "confirma"
        por_que = (f"Motor de niveles: zona de fuerza {fuerza}/100 · "
                   + " + ".join(razones[:3]) + ".")
    elif fuerza:
        estado_motor = "confirma"
        por_que = f"Motor de niveles: zona de fuerza {fuerza}/100."
    elif motor_con_datos:
        # Ha calculado, pero sus zonas caen lejos de ESTE precio. No es lo mismo que
        # no haber calculado, y desde luego no es un rechazo.
        estado_motor = "sin_zona"
        por_que = ("Es un nivel de tu tabla. El motor de niveles ha calculado zonas para "
                   "este símbolo, pero ninguna cae en este precio.")
    else:
        estado_motor = "sin_datos"
        por_que = ("Es un nivel de tu tabla. Motor de niveles: sin datos todavía — aún no "
                   "se ha calculado para este símbolo. No es un rechazo ni una confirmación.")

    accion = (caliente.get("action") or "").lower()
    return _tarjeta(
        "nivel", symbol, caliente.get("name"), urgencia,
        que_pasa=f"{symbol} está a un {_fmt_pct(distancia)} de {etiqueta}",
        por_que=por_que,
        que_vigilar=(
            f"Precio {_fmt_precio(caliente.get('price'))} contra "
            f"{_fmt_precio(caliente.get('target'))}"
            + (f" · sería una {accion}" if accion else "")
        ),
        datos={
            "price": caliente.get("price"),
            "target": caliente.get("target"),
            "distancia_pct": distancia,
            "nivel": caliente.get("level_label"),
            "accion": caliente.get("action"),
            "fuerza": fuerza,
            "razones": razones[:3],
            "tiene_posicion": tiene_posicion,
            "motor_niveles": estado_motor,
        },
        aviso=aviso,
    )


def tarjeta_confluencia(symbol, nombre, estado, fuentes, tiene_posicion=False):
    """4 y 5 · Choque o acuerdo entre lo que dicen tus fuentes y la elegibilidad.

    `estado` viene de `confluencia.py`, que es la única implementación. Antes esta
    pantalla tenía la suya propia, con estados distintos y los mismos umbrales de score
    duplicados: la misma acción podía salir en ACUERDO en el Radar y en `choque` aquí.

    QUÉ SE FUE, Y LO QUE ESO CUESTA

    `acuerdo_alto` no existe. Combinaba fuentes + motor + «el precio está a menos del 5%
    de un nivel de fuerza ≥55», y esa última mitad es información de ENTRADA, no de
    confluencia. Con ella se va el +60 de urgencia que subía esas tarjetas por encima de
    los choques: todas las coincidencias pasan a la banda normal.

    Es un cambio de orden visible en la portada, y es deliberado. Ese +60 estaba
    justificado por información de zona que hemos retirado; conservar el efecto sin
    conservar el significado habría sido inventar un número. La información de zona no
    se pierde para siempre: tiene dueño, y es la capa de decisión de entrada, que aún no
    existe.
    """
    if estado not in ("CHOQUE", "ACUERDO"):
        return None

    fuentes = fuentes or {}
    lista = fuentes.get("fuentes") or []
    positivos = fuentes.get("positivos") or 0
    negativos = fuentes.get("negativos") or 0
    menciones = fuentes.get("menciones") or 0
    quienes = ", ".join(lista[:3]) + ("…" if len(lista) > 3 else "")
    cuantas = f"{len(lista)} {'fuente' if len(lista) == 1 else 'fuentes'}"

    if estado == "CHOQUE":
        urgencia = BASE["divergencia"] + min(60, menciones * 8)
        if positivos > negativos:
            que_pasa = f"Tus fuentes empujan {symbol} y no está en tendencia alcista"
            por_que = (
                f"{menciones} menciones en {cuantas} ({quienes}), {positivos} en "
                f"positivo. Pero el precio no está por encima de su media de 200 "
                f"sesiones con la de 50 acompañando."
            )
            vigilar = (
                "Es el caso en que conviene desconfiar del entusiasmo: mira qué ve la "
                "estructura que la fuente no cuenta."
            )
        else:
            que_pasa = f"Tus fuentes desconfían de {symbol} y sí está en tendencia alcista"
            por_que = (
                f"{negativos} de {menciones} menciones son negativas ({quienes}), "
                f"pero estructuralmente la acción sí es elegible."
            )
            vigilar = "Mira qué riesgo ven las fuentes que la estructura todavía no refleja."
        return _tarjeta(
            "divergencia", symbol, nombre, urgencia, que_pasa, por_que, vigilar,
            datos={"menciones": menciones, "positivos": positivos, "negativos": negativos,
                   "fuentes": lista, "estado": estado,
                   "tiene_posicion": tiene_posicion},
        )

    # Acuerdo. Solo sube a portada lo que NO tienes: sobre lo que ya tienes, la
    # coincidencia no es una decisión pendiente.
    if tiene_posicion:
        return None
    urgencia = BASE["confluencia"] + min(80, menciones * 6)
    return _tarjeta(
        "confluencia", symbol, nombre, urgencia,
        que_pasa=f"{symbol}: tus fuentes la ven bien y está en tendencia alcista",
        por_que=(
            f"{positivos} menciones positivas en {cuantas} ({quienes}), y la acción "
            f"cotiza por encima de su media de 200 sesiones con la de 50 acompañando."
        ),
        que_vigilar=(
            "No la tienes en cartera. Coinciden tus fuentes y la estructura; queda por "
            "ver a qué precio tendría sentido entrar."
        ),
        datos={"menciones": menciones, "positivos": positivos, "negativos": negativos,
               "fuentes": lista, "estado": estado,
               "tiene_posicion": tiene_posicion},
    )


def tarjeta_resultados(evento, posicion, historial_sorpresas=None):
    """6 · Resultados a la vuelta de la esquina con dinero dentro.

    Sin posición abierta no sube a portada: unos resultados de una acción que no
    tienes ni vigilas son una noticia, no una decisión.
    """
    dias = evento.get("dias")
    if dias is None or dias > UMBRAL_RESULTADOS_DIAS:
        return None
    if not posicion or not (posicion.get("acciones") or 0) > 0:
        return None

    symbol = evento.get("symbol")
    urgencia = BASE["resultados"] + max(0, (UMBRAL_RESULTADOS_DIAS - dias) * 15)
    cuando = "hoy" if dias == 0 else ("mañana" if dias == 1 else f"en {dias} días")

    por_que = f"Tienes {posicion.get('acciones')} acciones"
    pnl = posicion.get("pnl_eur")
    if pnl is not None:
        por_que += f" con {pnl:+,.0f} € latentes"
    por_que += ". Unos resultados mueven el precio más que cualquier nivel técnico."

    if historial_sorpresas:
        aciertos = historial_sorpresas.get("supera")
        total = historial_sorpresas.get("total")
        if aciertos is not None and total:
            por_que += f" Ha batido estimaciones {aciertos} de los últimos {total} trimestres."

    return _tarjeta(
        "resultados", symbol, evento.get("name"), urgencia,
        que_pasa=f"{symbol} presenta resultados {cuando}",
        por_que=por_que,
        que_vigilar="Decide antes de la publicación si mantienes, reduces o cubres.",
        datos={"fecha": evento.get("date"), "dias": dias,
               "acciones": posicion.get("acciones"), "pnl_eur": pnl,
               "sorpresas": historial_sorpresas},
    )


# ── Composición ──────────────────────────────────────────────────────────────

def ordenar_y_recortar(tarjetas, limite=LIMITE_POR_DEFECTO):
    """Una tarjeta por ticker, ordenadas por urgencia, como mucho `limite`.

    Las tarjetas que pierden por duplicado no se tiran: se doblan dentro de la
    ganadora como `tambien`, porque «además está a un 2% de tu Nivel 2» es contexto
    útil aunque no merezca una tarjeta propia.
    """
    validas = [t for t in tarjetas if t]
    validas.sort(key=lambda t: t["urgencia"], reverse=True)

    por_symbol = {}
    for t in validas:
        sym = t["symbol"]
        if sym in por_symbol:
            por_symbol[sym].setdefault("tambien", []).append({
                "tipo": t["tipo"], "que_pasa": t["que_pasa"],
            })
        else:
            por_symbol[sym] = t

    finales = sorted(por_symbol.values(), key=lambda t: t["urgencia"], reverse=True)
    return finales[:limite]


def resumen_de_saludo(tarjetas, cerebro=None):
    """La línea de arriba: el índice de lo que hay debajo.

    Se construye contando las tarjetas que de verdad han salido, no consultando otra
    vez los datos. Si dijera «3 niveles cerca» y debajo hubiera uno, la línea estaría
    mintiendo, y es lo primero que se lee.
    """
    conteo = {}
    for t in tarjetas:
        conteo[t["tipo"]] = conteo.get(t["tipo"], 0) + 1

    piezas = []
    plantillas = [
        ("ruptura", "{n} posición que ha roto su media", "{n} posiciones que han roto su media"),
        ("alerta", "{n} alerta saltada", "{n} alertas saltadas"),
        ("nivel", "{n} nivel cerca", "{n} niveles cerca"),
        ("divergencia", "{n} choque entre tus fuentes y el motor", "{n} choques entre tus fuentes y el motor"),
        ("confluencia", "{n} coincidencia motor-fuentes", "{n} coincidencias motor-fuentes"),
        ("resultados", "{n} resultados a la vista", "{n} resultados a la vista"),
    ]
    for clave, singular, plural in plantillas:
        n = conteo.get(clave)
        if n:
            piezas.append((singular if n == 1 else plural).format(n=n))

    nuevos = (cerebro or {}).get("tickers_nuevos") or []
    if nuevos:
        piezas.append(
            f"{len(nuevos)} ticker nuevo en tus fuentes" if len(nuevos) == 1
            else f"{len(nuevos)} tickers nuevos en tus fuentes"
        )

    return {"piezas": piezas, "conteo": conteo, "total": len(tarjetas)}
