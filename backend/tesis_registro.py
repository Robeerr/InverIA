"""El histórico de la tesis de cada acción. Guardar y consultar, nada más.

QUÉ PROBLEMA RESUELVE

`tesis.redactar()` describe lo que le pasa a una acción HOY, y no deja rastro: es una
función pura sobre el dashboard del momento. Así que la pantalla puede enseñar la tesis
pero no puede enseñar **cómo ha cambiado**, que suele ser la pregunta más útil —una
acción que pasó de «tendencia alcista con fuerza» a «sale dinero» hace dos semanas dice
mucho más que cualquiera de las dos frases por separado.

LO QUE ESTE MÓDULO NO HACE, Y ES DELIBERADO

No juzga la tesis, no la compara con el precio posterior y no dice si acertó. Guarda y
deja consultar. Acertar es otra pregunta —se responde con lo que hizo el precio después—
y tiene su propio sitio (`patrones_registro`, `track_record`); mezclarla aquí produciría
un tercer aprendizaje distinto de los dos que ya existen.

Tampoco decide cuándo dos tesis «son la misma». El hilo es el SÍMBOLO y punto: las
versiones son su historia en orden. Modelar la continuidad de una tesis —que esto es un
matiz y aquello un giro— es un juicio que no se puede tomar sin haber mirado antes unas
cuantas, y por eso no hay ningún `tesis_id` aquí.

EL PROBLEMA CENTRAL: EL TEXTO LLEVA NÚMEROS DENTRO

Versionar por el hash del texto no funciona, y conviene dejar medido por qué. El mismo
símbolo, dos días después, sin que cambie una sola conclusión:

    T0  Tendencia alcista con fuerza (ADX 31); se mueve un ±1.9% al día; …
        La zona más sólida es el NIVEL 1, en 178.40, un 16.5% por debajo, fuerza 78/100…

    T1  Tendencia alcista con fuerza (ADX 32); se mueve un ±2.0% al día; …
        La zona más sólida es el NIVEL 1, en 178.40, un 17.7% por debajo, fuerza 78/100…

Tres diferencias, cero cambios de fondo. Y el precio del titular cambia con cada tick,
no cada día: `server` vuelve a redactar la tesis en cada refresco de cotización para que
la cabecera y la frase no enseñen dos precios distintos. Un hash del texto habría
producido miles de versiones idénticas en conclusiones.

De ahí la regla: SE VERSIONAN CONCLUSIONES, NO NÚMEROS. La huella se calcula sobre el
texto con los números sueltos normalizados; los números viajan enteros dentro de la
versión guardada, que es donde se pueden consultar.
"""
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("inveria.tesis")


def _ahora() -> str:
    """UTC e ISO 8601, como el resto del proyecto."""
    return datetime.now(timezone.utc).isoformat()

#: Versión del FORMATO de la huella. Si algún día cambia qué entra en ella, las versiones
#: anteriores dejan de ser comparables con las nuevas y hay que poder saberlo. Misma
#: convención que `RELEVANCIA_V`, `SEC_ID_V` y `PROMPT_V`.
TESIS_V = 1

#: Cuánto se conserva del SHA-256. 16 hex son 64 bits: de sobra para que dos tesis
#: distintas no colisionen nunca en una colección de decenas de símbolos, y corto para
#: poder leerlo en pantalla y en un log.
LARGO_HUELLA = 16

#: Qué número se normaliza y cuál no. Se captura el TOKEN entero —letras pegadas
#: incluidas— y solo se sustituye si no lleva ninguna letra:
#:
#:     "ADX 31"              → "ADX #"        el número deriva, el adjetivo manda
#:     "un 16.5% por debajo" → "un #% por debajo"
#:     "SMA200"              → "SMA200"       intacto: es un NOMBRE, no una medida
#:     "Fibonacci 38,2%"     → "Fibonacci #%" el nombre se conserva, la cifra no
#:
#: La primera versión usaba un `(?<![A-Za-z])` delante del número, y un test la tumbó:
#: la expresión solo mira el carácter anterior al punto donde empieza a casar, así que
#: en `SMA200` rechazaba el `2` —precedido de `A`— pero casaba los `00` siguientes y
#: producía `SMA2#`. Distinguía `SMA200` de `SMA50` por casualidad, y habría fundido
#: `SMA200` con `SMA204`. Capturar el token entero no tiene ese borde.
#:
#: Importa porque las razones que sostienen una zona de compra son nombres con dígitos
#: pegados: que una zona deje de apoyarse en la media de 200 y pase a la de 50 es un
#: cambio de tesis, y con la regla ingenua se perdía en silencio.
_TOKEN = re.compile(r"[A-Za-z]*\d+(?:[.,]\d+)*")


def normalizar(texto: Optional[str]) -> str:
    """El texto con los números sueltos sustituidos por `#`. Base de la identidad."""
    return _TOKEN.sub(lambda m: m.group(0) if m.group(0)[0].isalpha() else "#",
                      texto or "")


def _textos(bloque) -> list:
    """Los `texto` de una lista de señales, normalizados y con su campo de origen.

    Va el campo de origen ADEMÁS del texto porque dos frases pueden leerse parecido y
    apoyarse en datos distintos, y eso es un cambio real de lo que sostiene la tesis.
    """
    salida = []
    for item in bloque or []:
        if not isinstance(item, dict):
            continue
        salida.append([normalizar(item.get("texto")), item.get("campo_origen")])
    return salida


def identidad(tesis: Optional[dict]) -> Optional[dict]:
    """Lo que DEFINE la tesis, separado de los valores que la sustentan hoy.

    QUÉ ENTRA Y POR QUÉ

      · `titular_plantilla` y no `titular`. La plantilla ya trae `{p0}`/`{p1}` en lugar
        del precio y la variación del día: esa separación la hizo `tesis._titular` para
        que la pantalla pudiera refrescar la cotización sin rehacer la frase, y aquí se
        reutiliza en vez de inventar otra. `titular_huecos` son precisamente los valores
        volátiles, así que quedan fuera enteros.

      · `parrafos`, NORMALIZADOS. Literales reintroducirían el problema del titular por
        otra puerta: ADX, ATR y la distancia al nivel se mueven solos todos los días.

      · `a_favor`, `en_contra` y `limita_confianza` por su texto normalizado y su campo
        de origen. Su `valor` no: la SMA200 de hoy no es la tesis, «estar por encima de
        la SMA200» sí lo es. Y el lado importa — la MISMA frase en `a_favor` o en
        `en_contra` es lo contrario.

      · `campos_usados` tal cual. Que la tesis deje de apoyarse en un campo, o empiece a
        apoyarse en otro, es un cambio aunque las frases se parezcan.

    QUÉ NO ENTRA

      · `afirmaciones`. Es la traza de auditoría de ESTA redacción y sus valores cambian
        con cada dato. Se conserva dentro de la versión guardada, que es donde sirve.

    LO QUE ESTA IDENTIDAD NO VE, Y SE ACEPTA A SABIENDAS

    Un número que cambia sin cambiar la conclusión no crea versión. El caso concreto es
    `fuerza 78/100` → `fuerza 45/100`: si la misma zona sigue siendo la mejor pero se
    debilita, la huella no se entera. No es del todo invisible —`tesis._mejor_zona`
    elige por fuerza, así que una caída suele cambiar CUÁL es la mejor zona, y eso sí
    cambia la etiqueta—, pero el caso existe. Meterlo exigiría partir la fuerza en
    bandas, y dónde van los cortes no lo hemos medido: es el mismo motivo por el que
    `separacion.py` se niega a producir un `tendencia_score`.
    """
    if not isinstance(tesis, dict) or not tesis:
        return None
    limita = tesis.get("limita_confianza")
    return {
        "tesis_v": TESIS_V,
        "titular": normalizar(tesis.get("titular_plantilla")),
        "parrafos": [normalizar(p) for p in (tesis.get("parrafos") or [])],
        "a_favor": _textos(tesis.get("a_favor")),
        "en_contra": _textos(tesis.get("en_contra")),
        "limita": _textos([limita] if limita else []),
        "campos_usados": list(tesis.get("campos_usados") or []),
    }


def _plano(valor) -> str:
    """La identidad como texto, de forma estable y sin depender de `json`.

    Se escribe a mano en vez de con `json.dumps` para que el resultado no dependa de
    opciones del serializador —separadores, orden de claves, escapado de acentos— que
    alguien podría cambiar sin darse cuenta de que estaba moviendo todas las huellas.
    """
    if isinstance(valor, dict):
        return "{" + "|".join(f"{k}={_plano(valor[k])}" for k in sorted(valor)) + "}"
    if isinstance(valor, (list, tuple)):
        return "[" + "|".join(_plano(v) for v in valor) + "]"
    if valor is None:
        return "~"
    return str(valor)


def huella(tesis: Optional[dict]) -> Optional[str]:
    """La huella de una tesis, o None si no hay tesis. Determinista y pura."""
    ident = identidad(tesis)
    if ident is None:
        return None
    crudo = _plano(ident).encode("utf-8")
    return hashlib.sha256(crudo).hexdigest()[:LARGO_HUELLA]


def diff_de_campos(anterior: Optional[dict], nueva: Optional[dict]) -> dict:
    """Qué campos entraron, salieron y siguen entre dos tesis. Mecánico, no un juicio.

    Es lo único que se ofrece para leer un cambio de versión. Decir si un cambio fue un
    matiz o un giro sería interpretar, y eso todavía no se puede hacer con criterio.
    """
    antes = set((anterior or {}).get("campos_usados") or [])
    ahora = set((nueva or {}).get("campos_usados") or [])
    return {"entran": sorted(ahora - antes),
            "salen": sorted(antes - ahora),
            "siguen": sorted(ahora & antes)}


def nueva_version(anterior: Optional[dict], tesis: Optional[dict],
                  cuando: str = None) -> Optional[dict]:
    """El documento de una versión nueva, o None si no hay tesis que guardar.

    `anterior` es la versión vigente de ese símbolo, o None si es la primera. No se
    comprueba aquí si hace falta una versión nueva: eso lo decide quien compara las
    huellas, que es quien ha leído la base de datos.
    """
    if not isinstance(tesis, dict) or not tesis:
        return None
    h = huella(tesis)
    if h is None:
        return None
    version = int((anterior or {}).get("version") or 0) + 1
    return {
        "symbol": (tesis.get("symbol") or (anterior or {}).get("symbol") or "").upper(),
        "version": version,
        "huella": h,
        "tesis_v": TESIS_V,
        "tesis": tesis,
        "campos_usados": list(tesis.get("campos_usados") or []),
        "cambios": diff_de_campos((anterior or {}).get("tesis"), tesis),
        "creada_en": cuando,
        "observada_por_ultima_vez": cuando,
        #: Cuántas redacciones CONSECUTIVAS produjeron esta misma huella. Dice que la
        #: tesis no ha cambiado, NO que sea correcta: acertar es otra pregunta, se
        #: responde con el precio de después y no se responde aquí.
        #:
        #: Se llamó `veces_confirmada` en el diseño y se cambió a propósito:
        #: `patrones_registro` ya usa `acierto` para «la predicción se cumplió», y tener
        #: dos vocabularios parecidos con significados opuestos es pedir que alguien los
        #: cruce. `veces_mantenida` tampoco vale — «mantener» ya es un verbo de operativa
        #: en este código (`indicators.salida_10w.senal`).
        "veces_observada": 1,
    }


def para_api(doc: Optional[dict], completa: bool = True) -> dict:
    """Una versión tal como sale por la API. Sin `_id`, que no le sirve al navegador."""
    if not isinstance(doc, dict):
        return {}
    salida = {k: v for k, v in doc.items() if k != "_id"}
    if not completa:
        # En la lista no viaja la tesis entera: son decenas de versiones y lo que se
        # quiere ver de un vistazo es cuándo cambió y qué cambió.
        tesis = salida.pop("tesis", None) or {}
        salida["titular"] = tesis.get("titular")
    return salida


# ── La única parte que toca la base de datos ─────────────────────────────────
#
# Todo lo de arriba es puro y se prueba sin Mongo. Aquí abajo están las tres funciones
# que leen y escriben, y ninguna de ellas decide nada: la identidad, la huella y la forma
# del documento ya vienen resueltas.

COLECCION = "tesis_versiones"


async def vigente(db, symbol: str) -> Optional[dict]:
    """La última versión de un símbolo, o None. Lectura, nunca escribe."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None
    docs = await db[COLECCION].find({"symbol": symbol}, {"_id": 0}).sort(
        "version", -1).limit(1).to_list(1)
    return docs[0] if docs else None


async def guardar_si_cambia(db, symbol: str, tesis: Optional[dict],
                            cuando: str = None) -> dict:
    """Registra la tesis. Versión nueva solo si la huella cambió.

    NUNCA LANZA, Y ESO ES LO PRINCIPAL

    Esto cuelga del camino que construye el dashboard. Un fallo de Mongo aquí no puede
    dejar sin página a quien abre una acción: el histórico es un extra, los datos de la
    acción son la pantalla. Mismo criterio que ya sigue `server` cuando falla la propia
    redacción de la tesis — se registra el fallo y se sigue.

    UNA TESIS QUE VUELVE ES UNA VERSIÓN NUEVA

    Si la huella coincide con una ANTIGUA pero no con la vigente, se crea versión nueva
    igual. Que una acción vuelva a estar por encima de su media es un hecho con fecha, y
    reutilizar la versión de hace tres meses borraría que entremedias pasó otra cosa.
    Por eso se compara solo contra la vigente.

    Devuelve qué ha pasado: `creada`, `observada` o `nada`.
    """
    symbol = (symbol or "").strip().upper()
    h = huella(tesis)
    if not symbol or h is None:
        # Sin tesis no se registra nada. Una versión vacía sería una fila que dice que
        # hubo una tesis cuando no la hubo.
        return {"accion": "nada", "motivo": "sin_tesis"}

    cuando = cuando or _ahora()
    try:
        actual = await vigente(db, symbol)
        if actual and actual.get("huella") == h:
            await db[COLECCION].update_one(
                {"symbol": symbol, "version": actual["version"]},
                {"$set": {"observada_por_ultima_vez": cuando},
                 "$inc": {"veces_observada": 1}})
            return {"accion": "observada", "version": actual["version"], "huella": h}

        doc = nueva_version(actual, {**tesis, "symbol": symbol}, cuando=cuando)
        await db[COLECCION].insert_one(doc)
        return {"accion": "creada", "version": doc["version"], "huella": h}
    except Exception as e:
        # Incluye la carrera entre dos procesos que redactan el mismo símbolo a la vez:
        # el índice único `(symbol, version)` deja pasar a uno y el otro cae aquí. No hay
        # nada que reparar —el que ganó escribió la misma versión— y reintentar solo
        # abriría la puerta a escribir dos.
        logger.warning("tesis: no se pudo registrar la de %s: %s", symbol, str(e)[:120])
        return {"accion": "nada", "motivo": "error", "error": str(e)[:200]}


async def historial(db, symbol: str, limite: int = 50) -> list:
    """Las versiones de un símbolo, la más reciente primero. Solo lectura."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return []
    docs = await db[COLECCION].find({"symbol": symbol}, {"_id": 0}).sort(
        "version", -1).limit(limite).to_list(limite)
    return [para_api(d, completa=False) for d in docs]


async def version(db, symbol: str, numero: int) -> Optional[dict]:
    """Una versión concreta, entera y tal como se escribió. Solo lectura."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None
    doc = await db[COLECCION].find_one({"symbol": symbol, "version": int(numero)},
                                       {"_id": 0})
    return para_api(doc) if doc else None
