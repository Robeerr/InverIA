"""Tesis determinista: qué le pasa a una acción, escrito sin IA.

Al abrir una acción no había ni una frase en lenguaje normal. La interpretación
existía, pero detrás de un botón de IA con espera y coste: `analysis` solo llega
cuando se pulsa «Análisis completo IA», así que en frío la página estaba muda.

Este módulo es SOLO REDACCIÓN. Recibe el dashboard ya construido y describe lo que
sus campos dicen. No llama a nadie, no toca `compute_all` ni `compute_buy_levels`, y
no hace aritmética nueva más allá de distancias entre dos números que ya existen.

DESCRIBE, NO RECOMIENDA
Aquí no se dice «compra» ni «vende». Recomendar sigue siendo trabajo del análisis de
IA y del motor de niveles; si esta capa opinara, acabaría contradiciéndolos con otra
lógica escrita en otro sitio.

TRAZABILIDAD REAL
Cada afirmación queda registrada con la RUTA del campo del que sale —`quote.price`,
`indicators.regime.adx`, `buy_levels[0].price`— y su valor. Eso permite auditarla de
verdad: un test resuelve cada ruta contra el dashboard de origen y comprueba que el
valor coincide. Buscar números sueltos en el texto no serviría: un «2» de «media de
200 sesiones» pasaría por dato verificado sin serlo.

`campos_usados` se DERIVA de esas afirmaciones y señales, nunca de lo que se haya
leído por el camino. La diferencia importa: el RSI y el máximo anual se consultan
siempre, pero solo hablan en su caso extremo, y declararlos «usados» cuando no han
dicho nada convertiría la lista en un inventario de lecturas en vez de en el respaldo
de lo que se afirma — que es justo lo que esta lista promete ser.

LA REGLA QUE LO SOSTIENE
Si un campo falta, la frase NO se escribe. No hay valores por defecto, ni «en torno
a», ni inferir un dato ausente a partir de otro. Un dato que no está no puede
producir una afirmación sobre sí mismo, aunque se intuya desde otro sitio: `regime`
se calcula a partir del ADX, pero si `adx` viene a None, la tesis no cita ningún ADX.
"""

import re
from typing import Optional

# Umbrales. Son los mismos que ya usan los módulos de origen, repetidos aquí solo para
# ELEGIR PALABRAS, nunca para recalcular nada.
ADX_CON_FUERZA = 25          # el propio indicators.market_regime usa 25 para "trending"
RSI_SOBRECOMPRA = 70
RSI_SOBREVENTA = 30
CERCA_DEL_MAXIMO_PCT = 5.0


def _leer(dato, ruta: str):
    """Resuelve una ruta con puntos e índices: `buy_levels[0].reasons`.

    Devuelve None si cualquier tramo falta. Es la misma función que usa el test para
    auditar, así que si la ruta registrada no existiera, el test lo vería.
    """
    actual = dato
    for parte in ruta.split("."):
        m = re.match(r"^(\w+)\[(\d+)\]$", parte)
        if m:
            if not isinstance(actual, dict):
                return None
            actual = actual.get(m.group(1))
            i = int(m.group(2))
            if not isinstance(actual, list) or i >= len(actual):
                return None
            actual = actual[i]
        else:
            if not isinstance(actual, dict):
                return None
            actual = actual.get(parte)
        if actual is None:
            return None
    return actual


class _Fuente:
    """Lee el dashboard y deja constancia de lo que se afirma con lo leído.

    `dato()` solo LEE: devuelve None cuando falta, y quien lo llama tiene que decidir
    no escribir la frase — no rellenar el hueco. Leer no deja rastro a propósito,
    porque consultar un campo no es usarlo; el rastro lo deja `afirmar()`, que es
    quien sabe que esa lectura ha acabado convertida en texto.
    """

    def __init__(self, dashboard: dict):
        self.d = dashboard or {}
        self.afirmaciones: list = []

    def dato(self, ruta: str):
        return _leer(self.d, ruta)

    def afirmar(self, texto: str, ruta: str, valor) -> str:
        """Registra una afirmación y devuelve su texto, para poder encadenar."""
        self.afirmaciones.append({"texto": texto, "valor": valor, "campo_origen": ruta})
        return texto


def _pct(v, decimales=1) -> str:
    return f"{abs(float(v)):.{decimales}f}%"


def _precio(v) -> str:
    return f"{float(v):,.2f}"


def _mejor_zona(dashboard: dict):
    """(índice, zona) de la zona de compra más sólida, o (None, None).

    Se elige por FUERZA y, a igualdad, por cercanía. Devolver el índice no es un
    detalle: es lo que permite registrar la ruta `buy_levels[i].price` y auditarla.
    """
    niveles = (dashboard or {}).get("buy_levels") or []
    candidatas = [(i, z) for i, z in enumerate(niveles)
                  if isinstance(z, dict) and z.get("price") is not None]
    if not candidatas:
        return None, None
    return max(candidatas, key=lambda par: (par[1].get("strength") or 0,
                                            -abs(par[1].get("distance_pct") or 999)))


# ── Bloques ──────────────────────────────────────────────────────────────────

def _titular(f: _Fuente):
    """Devuelve (texto, plantilla, huecos).

    POR QUE HAY PLANTILLA

    El precio y la variacion del dia son los dos unicos datos de la tesis que cambian
    TICK A TICK, y hasta ahora se coccian dentro de la frase. Como el dashboard se cachea
    15 min y se sirve caducado hasta 30, la cabecera acababa enseñando $468.96 en vivo
    mientras la tesis seguia diciendo «AMD cotiza a 468.34». Dos precios de la misma
    accion en la misma pantalla, que es justo lo que la regla de fuente unica prohibe.

    La frase entera —el orden, las palabras, las comas— se sigue escribiendo AQUI. Lo
    unico que viaja aparte son los huecos de esos dos valores, para que la pantalla pueda
    rellenarlos con la cotizacion viva sin rehacer ninguna frase ni recalcular nada.

    Lo que NO se actualiza con el tick, a proposito: «por encima de su media de 200
    sesiones» y «a X% de su maximo anual» son JUICIOS derivados del precio, no el precio.
    Recalcularlos en el navegador seria mover logica de negocio al cliente. Se quedan
    congelados, y el sello de antiguedad del bloque explica de cuando son.
    """
    precio = f.dato("quote.price")
    if precio is None:
        return None, None, None
    simbolo = f.dato("symbol") or "La acción"

    huecos = {}
    partes = []       # la frase tal cual se lee
    plantilla = []    # la misma, con {p0}/{p1} donde hay un valor vivo

    def _volatil(clave, texto, molde, ruta, valor, formato):
        huecos[clave] = {"campo_origen": ruta, "formato": formato, "valor": valor}
        f.afirmar(texto, ruta, valor)
        partes.append(texto)
        plantilla.append(molde)

    def _estable(texto, ruta, valor):
        f.afirmar(texto, ruta, valor)
        partes.append(texto)
        plantilla.append(texto)

    _volatil("p0", f"{simbolo} cotiza a {_precio(precio)}",
             f"{simbolo} cotiza a {{p0}}", "quote.price", precio, "precio")

    cambio = f.dato("quote.change_percent")
    if cambio is not None:
        signo = "+" if float(cambio) >= 0 else "-"
        _volatil("p1", f"({signo}{_pct(cambio, 2)} hoy)", "({p1} hoy)",
                 "quote.change_percent", cambio, "pct_signo")

    sma200 = f.dato("indicators.sma.200")
    if sma200 is not None:
        encima = float(precio) > float(sma200)
        _estable(f"{'por encima' if encima else 'por debajo'} de su media de 200 sesiones",
                 "indicators.sma.200", sma200)

    maximo = f.dato("indicators.high_52w")
    if maximo is not None and float(maximo) > 0:
        dist = (float(precio) - float(maximo)) / float(maximo) * 100
        if abs(dist) <= CERCA_DEL_MAXIMO_PCT:
            _estable(f"a {_pct(dist)} de su máximo anual", "indicators.high_52w", maximo)

    def _unir(xs):
        return xs[0] + (" " + ", ".join(xs[1:]) if len(xs) > 1 else "") + "."

    return _unir(partes), _unir(plantilla), huecos


def _tendencia(f: _Fuente) -> Optional[str]:
    frases = []
    regimen = f.dato("indicators.regime.regime")
    adx = f.dato("indicators.regime.adx")

    if regimen == "tendencia_alcista":
        base = "Tendencia alcista"
    elif regimen == "tendencia_bajista":
        base = "Tendencia bajista"
    elif regimen == "rango":
        base = "Se mueve en lateral: aquí mandan los niveles, no la tendencia"
    elif regimen == "transicion":
        base = "Está en transición: ni tendencia clara ni rango definido"
    else:
        base = None

    if base:
        # El régimen es una afirmación como cualquier otra y se registra con su ruta:
        # de otro modo la frase existiría en el texto sin respaldo auditable.
        f.afirmar(base, "indicators.regime.regime", regimen)

        # El ADX solo se CITA si existe. `regime` se deriva de él, pero eso no autoriza
        # a inventarse la cifra: un dato ausente no puede producir una afirmación sobre
        # sí mismo aunque se intuya desde otro campo.
        if adx is not None:
            if regimen in ("tendencia_alcista", "tendencia_bajista"):
                fuerza = "con fuerza" if float(adx) >= ADX_CON_FUERZA else "sin mucha fuerza"
                base += f" {f.afirmar(f'{fuerza} (ADX {adx:.0f})', 'indicators.regime.adx', adx)}"
            elif regimen == "transicion":
                # En transición el ADX es el dato MÁS informativo —dice cuánto le falta
                # para ser tendencia— pero no admite el adjetivo de las tendencias:
                # «en transición con fuerza» no significa nada. Se cita desnudo, sin
                # convertirlo en una conclusión sobre la dirección.
                base += f" ({f.afirmar(f'ADX {adx:.0f}', 'indicators.regime.adx', adx)})"
        frases.append(base)

    atr = f.dato("indicators.atr_pct")
    if atr is not None:
        frases.append(f.afirmar(f"se mueve un ±{_pct(atr)} al día",
                                "indicators.atr_pct", atr))

    obv = f.dato("indicators.obv_trend")
    if obv:
        texto = {"subiendo": "entra dinero: el volumen acompaña",
                 "bajando": "sale dinero: el volumen no acompaña"}.get(str(obv).lower())
        if texto:
            frases.append(f.afirmar(texto, "indicators.obv_trend", obv))

    return ("; ".join(frases) + ".") if frases else None


def _niveles(f: _Fuente) -> Optional[str]:
    i, zona = _mejor_zona(f.d)
    if zona is None:
        return None

    precio_zona = f.dato(f"buy_levels[{i}].price")

    # El nombre del peldaño va DELANTE del precio. Un precio suelto no se puede cruzar con
    # el panel de niveles, y eso hizo que «la zona más sólida está en 95.55» y «entrada
    # 109.36» parecieran dos recomendaciones en conflicto cuando eran el escalón 3 y el
    # borde del escalón 1 del mismo plan. Con el nombre, la frase apunta a algo que se ve.
    etiqueta = f.dato(f"buy_levels[{i}].label")
    if etiqueta:
        cabeza = f.afirmar(
            f"La zona de compra más sólida es el {etiqueta}, en {_precio(precio_zona)}",
            f"buy_levels[{i}].label", etiqueta)
        f.afirmar(f"{_precio(precio_zona)}", f"buy_levels[{i}].price", precio_zona)
    else:
        # Sin etiqueta no se inventa un número de peldaño: se cae a la redacción de
        # siempre. Un dato ausente no produce una afirmación sobre sí mismo.
        cabeza = f.afirmar(f"La zona de compra más sólida está en {_precio(precio_zona)}",
                           f"buy_levels[{i}].price", precio_zona)
    partes = [cabeza]

    dist = f.dato(f"buy_levels[{i}].distance_pct")
    if dist is not None:
        donde = "por debajo" if float(dist) < 0 else "por encima"
        partes.append(f.afirmar(f"un {_pct(dist)} {donde}",
                                f"buy_levels[{i}].distance_pct", dist))

    fuerza = f.dato(f"buy_levels[{i}].strength")
    razones = f.dato(f"buy_levels[{i}].reasons")
    if fuerza is not None:
        cola = f.afirmar(f"fuerza {fuerza}/100", f"buy_levels[{i}].strength", fuerza)
        if razones:
            # Las razones son la parte más citable de la frase, así que llevan su propia
            # ruta: sin ella, «donde coinciden SMA200 + Fibonacci» iría sin respaldo.
            cola += ", donde coinciden " + f.afirmar(
                " + ".join(list(razones)[:3]), f"buy_levels[{i}].reasons", razones)
        partes.append(cola)

    return partes[0] + (", " + ", ".join(partes[1:]) if len(partes) > 1 else "") + "."


def _senales(f: _Fuente):
    """Comprobaciones binarias, cada una con el dato que la sostiene al lado."""
    a_favor, en_contra = [], []

    def apunta(condicion, texto, ruta, valor):
        (a_favor if condicion else en_contra).append(
            {"texto": texto, "campo_origen": ruta, "valor": valor})

    precio = f.dato("quote.price")
    sma200 = f.dato("indicators.sma.200")
    if precio is not None and sma200 is not None:
        encima = float(precio) > float(sma200)
        apunta(encima,
               f"{'Sobre' if encima else 'Bajo'} la media de 200 sesiones ({_precio(sma200)})",
               "indicators.sma.200", sma200)

    salida = f.dato("indicators.salida_10w")
    if isinstance(salida, dict):
        if salida.get("recien_perdida"):
            # Va SIEMPRE en contra: es la señal de salida del método, no un matiz.
            en_contra.append({"texto": "Acaba de perder la media de 10 semanas",
                              "campo_origen": "indicators.salida_10w.recien_perdida",
                              "valor": True})
        elif salida.get("por_encima") is not None:
            encima = bool(salida["por_encima"])
            apunta(encima,
                   f"{'Sobre' if encima else 'Bajo'} la media de 10 semanas",
                   "indicators.salida_10w.por_encima", encima)

    rs = f.dato("relative_strength.6m.diferencia_pp")
    supera = f.dato("relative_strength.6m.supera")
    if rs is not None and supera is not None:
        apunta(bool(supera),
               f"{'Supera' if supera else 'Va por detrás de'} al índice en "
               f"{_pct(rs)} a 6 meses",
               "relative_strength.6m.diferencia_pp", rs)

    vwap = f.dato("indicators.vwap_anchored")
    if precio is not None and vwap is not None:
        encima = float(precio) > float(vwap)
        apunta(encima,
               f"{'Sobre' if encima else 'Bajo'} el VWAP anclado ({_precio(vwap)})",
               "indicators.vwap_anchored", vwap)

    rsi = f.dato("indicators.rsi")
    if rsi is not None:
        if float(rsi) >= RSI_SOBRECOMPRA:
            en_contra.append({"texto": f"RSI en {rsi:.0f}, en zona de sobrecompra",
                              "campo_origen": "indicators.rsi", "valor": rsi})
        elif float(rsi) <= RSI_SOBREVENTA:
            a_favor.append({"texto": f"RSI en {rsi:.0f}, en zona de sobreventa",
                            "campo_origen": "indicators.rsi", "valor": rsi})

    consenso = f.dato("analyst.consensus.label") or f.dato("analyst.consensus")
    if isinstance(consenso, str) and consenso:
        favorable = any(p in consenso.lower() for p in ("compra", "buy", "outperform"))
        ruta = "analyst.consensus.label" if _leer(f.d, "analyst.consensus.label") else "analyst.consensus"
        apunta(favorable, f"Consenso de analistas: {consenso}", ruta, consenso)

    return a_favor, en_contra


def _limita_confianza(f: _Fuente) -> Optional[dict]:
    """El dato que recorta la fiabilidad, por orden de gravedad. Uno solo: si se
    listaran todos, dejaría de leerse."""
    salud = f.d.get("data_health") or {}
    if salud.get("degraded"):
        nota = salud.get("note") or "fuente degradada"
        # Describe el estado del dato y para ahí. «Trátalo con cautela» era un consejo
        # sobre cómo actuar, que es precisamente lo que esta capa no hace.
        return {"texto": f"Datos de respaldo o con retraso ({nota}).",
                "campo_origen": "data_health.degraded", "valor": True}

    if _leer(f.d, "indicators.sma.200") is None:
        return {"texto": "Histórico corto: no hay media de 200 sesiones, así que no se "
                         "puede juzgar la tendencia primaria.",
                "campo_origen": "indicators.sma.200", "valor": None}

    regimen = _leer(f.d, "indicators.regime.regime")
    if regimen in (None, "indeterminado"):
        return {"texto": "No hay datos suficientes para determinar el régimen de la acción.",
                "campo_origen": "indicators.regime.regime", "valor": regimen}

    if not (f.d.get("buy_levels") or []):
        return {"texto": "El motor no ha encontrado zonas de confluencia para este precio.",
                "campo_origen": "buy_levels", "valor": []}

    luz = _leer(f.d, "market_regime.light")
    if luz in ("rojo", "amarillo"):
        etiqueta = _leer(f.d, "market_regime.label") or "mercado en riesgo"
        return {"texto": f"Contexto de mercado: {etiqueta}. Las señales de compra fallan "
                         f"más en este entorno.",
                "campo_origen": "market_regime.light", "valor": luz}
    return None


def _campos_usados(dashboard: dict, *bloques) -> list:
    """Las rutas que SOSTIENEN algo de lo que se dice, no las que se han consultado.

    Se derivan de las afirmaciones y señales ya registradas. El filtro final contra el
    dashboard existe por un caso concreto: una limitación puede apuntar a un campo
    AUSENTE —`indicators.sma.200` cuando no hay media de 200 sesiones—, y ese campo no
    está aportando un valor, sino su propia falta. Declararlo «usado» sería el mismo
    error de sobre-declaración, solo que del revés.
    """
    rutas = []
    for bloque in bloques:
        for item in bloque:
            ruta = (item or {}).get("campo_origen")
            if ruta and ruta not in rutas and _leer(dashboard, ruta) is not None:
                rutas.append(ruta)
    return sorted(rutas)


# ── Punto de entrada ─────────────────────────────────────────────────────────

def redactar(dashboard: dict) -> Optional[dict]:
    """La tesis, o None si no hay datos para sostener ninguna.

    Determinista por completo: mismos datos, mismo resultado. No lleva marca de
    tiempo a propósito — si hace falta, la pone la capa del servidor, que es la que
    sabe cuándo se construyó el dashboard.
    """
    if not isinstance(dashboard, dict) or not dashboard:
        return None

    f = _Fuente(dashboard)
    titular, titular_plantilla, titular_huecos = _titular(f)
    if not titular:
        # Sin precio no hay nada que describir. Preferible a una frase vacía con
        # aspecto de análisis.
        return None

    parrafos = [p for p in (_tendencia(f), _niveles(f)) if p]
    a_favor, en_contra = _senales(f)

    if not parrafos and not a_favor and not en_contra:
        # Solo el precio: eso no es una tesis, es un dato que ya está en la cabecera.
        return None

    limita = _limita_confianza(f)

    return {
        "titular": titular,
        # La misma frase con los huecos de los valores vivos, para que la pantalla los
        # rellene con la cotizacion del momento sin rehacer la redaccion.
        "titular_plantilla": titular_plantilla,
        "titular_huecos": titular_huecos,
        "parrafos": parrafos,
        "a_favor": a_favor,
        "en_contra": en_contra,
        "limita_confianza": limita,
        "afirmaciones": f.afirmaciones,
        "campos_usados": _campos_usados(dashboard, f.afirmaciones, a_favor, en_contra,
                                        [limita] if limita else []),
    }
