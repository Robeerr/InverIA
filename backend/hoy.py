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

# Fuerza a partir de la cual un nivel se considera "fuerte" y merece la portada.
# Sale del propio motor: es la escala 0-100 de confluencia de métodos.
UMBRAL_FUERZA = 55

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
        que_pasa = f"{symbol} ha tocado {etiqueta}"
        por_que = (
            f"Saltó tu alerta de {accion.lower() or 'precio'} en "
            f"{_fmt_precio(alerta.get('target'))}, con el precio en "
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


def tarjeta_nivel(caliente, nivel_motor=None, aviso=None, tiene_posicion=False):
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

    if fuerza and razones:
        por_que = (
            f"El motor marca ahí una zona de fuerza {fuerza}/100: "
            + " + ".join(razones[:3]) + "."
        )
    elif fuerza:
        por_que = f"El motor marca ahí una zona de fuerza {fuerza}/100."
    else:
        por_que = (
            "Es un nivel de tu tabla. El motor no tiene todavía una zona calculada "
            "para este precio."
        )

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
        },
        aviso=aviso,
    )


def confluencia(fuentes, veredicto_motor, distancia_nivel=None, fuerza_nivel=None):
    """Estado del cruce entre lo que dicen tus fuentes y lo que mide tu motor.

    Devuelve uno de: acuerdo_alto · acuerdo · choque · solo_fuentes · solo_motor · None.

    El CHOQUE importa tanto como el acuerdo, y por eso tiene tarjeta propia: es el
    único caso en que la app puede evitarte una decisión mala en vez de acompañarte
    en una buena. Un sistema que solo destaca coincidencias acaba siendo una máquina
    de confirmar lo que ya te habían contado.
    """
    fuentes = fuentes or {}
    n_fuentes = len(fuentes.get("fuentes") or [])
    positivos = fuentes.get("positivos") or 0
    negativos = fuentes.get("negativos") or 0
    menciones = fuentes.get("menciones") or 0
    score = (veredicto_motor or {}).get("score")
    verdict = (veredicto_motor or {}).get("verdict") or ""
    motor_evita = verdict.startswith("🔴")

    hay_fuentes = menciones > 0
    hay_motor = score is not None

    if not hay_fuentes and not hay_motor:
        return None
    if hay_fuentes and not hay_motor:
        return "solo_fuentes"
    if hay_motor and not hay_fuentes:
        return "solo_motor" if score >= 65 else None

    fuentes_positivas = positivos > negativos
    fuentes_negativas = negativos > positivos

    # Choque: unos empujan y el otro frena. En cualquiera de los dos sentidos.
    if (fuentes_positivas and motor_evita) or (fuentes_negativas and score >= 65):
        return "choque"

    if fuentes_positivas and score >= 65:
        cerca = distancia_nivel is not None and abs(distancia_nivel) <= 5
        fuerte = (fuerza_nivel or 0) >= UMBRAL_FUERZA
        if n_fuentes >= 2 and cerca and fuerte:
            return "acuerdo_alto"
        return "acuerdo"
    if fuentes_positivas and score >= 45:
        return "acuerdo"
    return None


def tarjeta_confluencia(symbol, nombre, estado, fuentes, veredicto_motor,
                        distancia_nivel=None, fuerza_nivel=None, tiene_posicion=False):
    """4 y 5 · Choque o acuerdo entre motor y fuentes."""
    if estado not in ("choque", "acuerdo_alto", "acuerdo"):
        return None

    fuentes = fuentes or {}
    lista = fuentes.get("fuentes") or []
    positivos = fuentes.get("positivos") or 0
    negativos = fuentes.get("negativos") or 0
    menciones = fuentes.get("menciones") or 0
    score = (veredicto_motor or {}).get("score")
    quienes = ", ".join(lista[:3]) + ("…" if len(lista) > 3 else "")

    if estado == "choque":
        urgencia = BASE["divergencia"] + min(60, menciones * 8)
        if positivos > negativos:
            que_pasa = f"Tus fuentes empujan {symbol} y tu motor la evita"
            por_que = (
                f"{menciones} menciones en {len(lista)} "
                f"{'fuente' if len(lista) == 1 else 'fuentes'} ({quienes}), "
                f"{positivos} en positivo. Tu motor le da {score}/100 y la descarta."
            )
            vigilar = (
                "Es el caso en que conviene desconfiar del entusiasmo: mira qué ve el "
                "motor que la fuente no cuenta."
            )
        else:
            que_pasa = f"Tus fuentes desconfían de {symbol} y tu motor la puntúa alto"
            por_que = (
                f"{negativos} de {menciones} menciones son negativas ({quienes}), "
                f"pero tu motor le da {score}/100."
            )
            vigilar = "Mira qué riesgo ven las fuentes que los números todavía no reflejan."
        return _tarjeta(
            "divergencia", symbol, nombre, urgencia, que_pasa, por_que, vigilar,
            datos={"menciones": menciones, "positivos": positivos, "negativos": negativos,
                   "fuentes": lista, "score_motor": score, "estado": estado,
                   "tiene_posicion": tiene_posicion},
        )

    # Acuerdo. Solo sube a portada lo que NO tienes: sobre lo que ya tienes, la
    # coincidencia no es una decisión pendiente.
    if tiene_posicion:
        return None
    urgencia = BASE["confluencia"] + min(80, menciones * 6)
    alto = estado == "acuerdo_alto"
    if alto:
        urgencia += 60

    return _tarjeta(
        "confluencia", symbol, nombre, urgencia,
        que_pasa=(
            f"{symbol}: tus fuentes y tu motor coinciden"
            + (" y el precio está en zona" if alto else "")
        ),
        por_que=(
            f"{positivos} menciones positivas en {len(lista)} "
            f"{'fuente' if len(lista) == 1 else 'fuentes'} ({quienes}), "
            f"y tu motor le da {score}/100."
            + (f" Además hay una zona de fuerza {fuerza_nivel}/100 a "
               f"{_fmt_pct(distancia_nivel)}." if alto else "")
        ),
        que_vigilar=(
            "No la tienes en cartera. Es la coincidencia con más convicción que hay hoy."
            if alto else "No la tienes en cartera. Coinciden, pero el precio aún no acompaña."
        ),
        datos={"menciones": menciones, "positivos": positivos, "negativos": negativos,
               "fuentes": lista, "score_motor": score, "estado": estado,
               "distancia_nivel": distancia_nivel, "fuerza_nivel": fuerza_nivel},
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
