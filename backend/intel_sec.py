"""Connector de SEC/EDGAR. Vigilancia DIRECTA de tus empresas, una por una.

POR QUÉ SE DEJÓ DE MIRAR EL MERCADO ENTERO

La primera versión leía el feed `getcurrent`, que devuelve los ~40 registros más recientes
de todo el mercado, y luego comprobaba si alguno era tuyo. Medido en producción: **11
vueltas, 509 documentos leídos, 0 aciertos**. No estaba roto — es que con miles de
empresas registrando, la probabilidad de que las tuyas pasen por esa ventana es mínima.

Ahora se pregunta por cada empresa tuya. La cobertura deja de ser estadística y pasa a ser
completa: si registran algo, se ve.

POR QUÉ NO HAY CACHÉ CONDICIONAL

Porque se midió y no existe. `data.sec.gov/submissions` NO devuelve `ETag` ni
`Last-Modified` —comprobado sobre tres empresas reales— así que `If-None-Match` e
`If-Modified-Since` no tienen nada con lo que preguntar. Escribir ese código sería
mantener una optimización que nunca se activa.

Y da igual: lo medido son 22 kB comprimidos por empresa, no los 200 kB que se estimaron.
Con los dos carriles salen ~121 MB al día y el 0,65 % del límite de peticiones de la SEC.

EL MAPA DE TICKERS ES UNO A MUCHOS, Y ESO NO ES UN DETALLE

El fichero de la SEC trae una fila por TICKER, y 1.441 de sus 8.013 empresas tienen varias
clases de acción. La versión anterior construía `{cik: ticker}` y la segunda clase pisaba a
la primera: se perdían 2.394 tickers, el 23 % del mercado.

En el universo real eso tumbaba cinco valores —AEM, BW, GOOGL, NEE y ORCL— cuyos registros
se descartaban como «no es un valor tuyo». Y el ticker que ganaba era sistemáticamente el
peor: ORCL perdía contra su preferente `ORCL-PD`, AEM contra su cotización OTC `AEMRF`,
GOOGL contra `GOOGN`.

Aquí la tabla va de ticker a CIK, y ningún ticker puede pisar a otro.

SIN `SEC_USER_AGENT` NO SE HACE NI UNA PETICIÓN

La SEC exige identificarse y responde 403 a quien no lo haga. No hay valor por defecto ni
correo en el código: un identificador inventado sería saltarse su política con el nombre de
otro.
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import intel_eventos as ev

logger = logging.getLogger("inveria.intel.sec")

FUENTE = "sec"
TIER = 1
NOMBRE = "SEC/EDGAR"

URL_TICKERS = "https://www.sec.gov/files/company_tickers.json"
URL_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
URL_FILING = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
URL_FILING_INDICE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"

# Qué formularios se vigilan y qué significan. Son los dos que mueven precio:
#   8-K → hecho relevante (la empresa está obligada a contarlo)
#   4   → un directivo ha comprado o vendido acciones propias
FORMULARIOS = {
    "8-K": (ev.CORPORATIVO, "Hecho relevante"),
    "4": (ev.INSIDER, "Operación de un directivo"),
}

INTERVALO = int(os.environ.get("INTEL_SEC_INTERVALO", 300))     # 5 min
TIMEOUT = 15

# Los dos carriles. La cartera se mira en cada vuelta porque hay dinero dentro; el
# seguimiento se reparte en turnos para que ningún valor espere más de media hora.
#
# TURNOS × INTERVALO = 30 min es una igualdad, no una coincidencia: si se cambia el
# intervalo hay que recalcular los turnos o la garantía deja de cumplirse. El test
# `test_ningun_valor_de_watchlist_espera_mas_de_30_min` lo comprueba.
TURNOS_WATCHLIST = int(os.environ.get("INTEL_SEC_TURNOS", 6))

# Limitador propio, MUY por debajo de las 10/s que admite la SEC. No hace falta apurar:
# con 52 empresas cada cinco minutos sobra de largo, y ser conservador con una fuente
# pública gratuita no cuesta nada.
PETICIONES_POR_SEGUNDO = float(os.environ.get("INTEL_SEC_RITMO", 3))

# Cuántos días atrás se miran al conocer una empresa por primera vez. Ver `PRIMER
# CONTACTO` en `parsear_submissions`.
DIAS_PRIMER_CONTACTO = int(os.environ.get("INTEL_SEC_DIAS_INICIALES", 7))

ONLINE, DEGRADADA, LIMITADA = "ONLINE", "DEGRADADA", "RATE_LIMITED"
NO_CONFIGURADA, ERROR, OFFLINE = "NO_CONFIGURADA", "ERROR", "OFFLINE"

BACKOFF_BASE = 60
BACKOFF_MAX = 3600

# 24 h. El fichero son diez mil filas que cambian muy poco.
_cache_tabla = {"cuando": None, "por_ticker": {}, "por_cik": {}}


def user_agent() -> Optional[str]:
    """El identificador exigido por la SEC, o None si no está configurado.

    Se lee del entorno en CADA llamada y no al importar: así, añadirlo en Render y
    reiniciar basta para que el connector arranque, sin tocar código.
    """
    ua = (os.environ.get("SEC_USER_AGENT") or "").strip()
    return ua or None


def configurado() -> bool:
    return user_agent() is not None


def estado_salud(ultimo_error: Optional[str] = None, fallos: int = 0) -> str:
    """El estado que se enseña. NO_CONFIGURADA es de primera clase, no un error."""
    if not configurado():
        return NO_CONFIGURADA
    if not ultimo_error:
        return ONLINE
    if "429" in ultimo_error or "rate" in ultimo_error.lower():
        return LIMITADA
    if "403" in ultimo_error:
        return ERROR
    return DEGRADADA if fallos < 3 else OFFLINE


def espera_tras_fallo(fallos: int) -> int:
    """Segundos a esperar tras `fallos` intentos seguidos fallidos."""
    if fallos <= 0:
        return 0
    return min(BACKOFF_BASE * (2 ** (fallos - 1)), BACKOFF_MAX)


def _cabeceras() -> dict:
    """La SEC además pide `Accept-Encoding`. El gzip no es cortesía: es lo que convierte
    250 kB de JSON en los 22 kB que se midieron."""
    return {"User-Agent": user_agent() or "", "Accept-Encoding": "gzip, deflate"}


# ── La tabla de tickers ──────────────────────────────────────────────────────

def construir_tabla(filas) -> dict:
    """De las filas del fichero a las dos direcciones. PURA.

    `por_ticker` es la principal: `{TICKER: cik}`. Es la dirección que hace falta, porque
    partimos de TUS símbolos y queremos saber a quién preguntar. Varios tickers pueden
    apuntar al mismo CIK sin conflicto.

    `por_cik` es `{cik: [TICKER, ...]}` — uno a MUCHOS. Aquí está la corrección: la versión
    anterior guardaba un solo ticker y la segunda clase pisaba a la primera.

    Ningún ticker sobrescribe a otro en ninguna de las dos.
    """
    crudas = filas.values() if isinstance(filas, dict) else (filas or [])
    por_ticker, por_cik = {}, {}
    for f in crudas:
        try:
            cik = int(f["cik_str"])
            ticker = str(f["ticker"]).upper().strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not ticker:
            continue
        por_ticker[ticker] = cik
        lista = por_cik.setdefault(cik, [])
        if ticker not in lista:
            lista.append(ticker)
    return {"por_ticker": por_ticker, "por_cik": por_cik}


async def tabla_tickers() -> dict:
    """La tabla, cacheada 24 h. Una petición al día."""
    import httpx
    ahora = datetime.now(timezone.utc)
    cuando = _cache_tabla["cuando"]
    if cuando and (ahora - cuando).total_seconds() < 86400 and _cache_tabla["por_ticker"]:
        return {"por_ticker": _cache_tabla["por_ticker"], "por_cik": _cache_tabla["por_cik"]}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_cabeceras()) as c:
        r = await c.get(URL_TICKERS)
        r.raise_for_status()
        datos = r.json()
    tabla = construir_tabla(datos)
    _cache_tabla.update(cuando=ahora, **tabla)
    logger.info("SEC: %d tickers sobre %d empresas",
                len(tabla["por_ticker"]), len(tabla["por_cik"]))
    return tabla


# ── De tu universo a la lista de empresas que consultar ──────────────────────

def objetivos(cartera, watchlist, tabla: dict) -> list:
    """Las empresas a vigilar, UNA POR CIK. Pura.

    CIK COMPARTIDO

    Si tienes GOOGL y GOOG, es la misma empresa: se consulta una sola vez. Pero no se
    pierde la asociación — el objetivo conserva TODOS tus tickers de ese CIK, y el
    principal se elige con una regla explícita: cartera antes que seguimiento, porque es
    donde hay dinero.

    Sin esa regla, un filing de una empresa que llevas comprada podría etiquetarse con el
    ticker de la clase que solo sigues, y la relevancia saldría más baja de lo que toca.
    """
    por_ticker = (tabla or {}).get("por_ticker") or {}
    por_cik = (tabla or {}).get("por_cik") or {}
    cartera = {str(s).upper().strip() for s in (cartera or ()) if s}
    watchlist = {str(s).upper().strip() for s in (watchlist or ()) if s}

    por_cik_objetivo = {}
    for symbol in sorted(cartera | watchlist):
        cik = por_ticker.get(symbol)
        if cik is None:
            continue                      # no registra en EDGAR: no hay a quién preguntar
        o = por_cik_objetivo.setdefault(cik, {
            "cik": cik, "tuyos": [], "en_cartera": False,
            # Todos los tickers que la SEC asocia a este CIK, tuyos o no. Sirve para
            # explicar en pantalla por qué se consulta esta empresa.
            "tickers_sec": por_cik.get(cik, []),
        })
        o["tuyos"].append(symbol)
        if symbol in cartera:
            o["en_cartera"] = True
    for o in por_cik_objetivo.values():
        # El símbolo con el que se etiquetan los eventos: el de cartera si lo hay.
        de_cartera = [t for t in o["tuyos"] if t in cartera]
        o["symbol"] = (sorted(de_cartera) or sorted(o["tuyos"]))[0]
    return sorted(por_cik_objetivo.values(), key=lambda o: o["cik"])


def turno(objetivos_: list, vuelta: int, turnos: int = None) -> list:
    """Qué se consulta EN ESTA vuelta: toda la cartera, más un turno del seguimiento.

    El reparto es por posición y no aleatorio: con `turnos` turnos, cada valor de
    seguimiento entra exactamente una vez cada `turnos` vueltas. La cadencia queda
    garantizada, no probable — un reparto al azar dejaría valores sin mirar durante horas
    por pura mala suerte.
    """
    turnos = max(1, turnos or TURNOS_WATCHLIST)
    vuelta = int(vuelta or 0)
    cartera = [o for o in objetivos_ if o["en_cartera"]]
    seguimiento = [o for o in objetivos_ if not o["en_cartera"]]
    toca = [o for i, o in enumerate(seguimiento) if i % turnos == vuelta % turnos]
    return cartera + toca


# ── Números de registro ──────────────────────────────────────────────────────

_SOLO_DIGITOS = re.compile(r"\D")


def canonizar_accession(valor: str) -> str:
    """El número de registro en su única forma. Solo dígitos.

    La SEC lo escribe de dos maneras: `0001045810-26-000042` en el JSON de submissions y
    `000104581026000042` dentro de las URLs. Son el mismo documento.

    Sin canonizar, los eventos guardados por el mecanismo anterior —que salían de la URL—
    y los que llegan ahora tendrían identificadores distintos, y el mismo registro entraría
    dos veces. Toda la deduplicación cuelga de esta función.
    """
    return _SOLO_DIGITOS.sub("", str(valor or ""))


# ── Parseo de submissions ────────────────────────────────────────────────────

def _hoy() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def parsear_submissions(datos: dict, objetivo: dict, cursor: dict = None,
                        hoy: str = None) -> dict:
    """Del JSON de una empresa a sus eventos nuevos. PURA: no toca la red.

    Devuelve `{"eventos": [...], "cursor": {...}}`. El cursor es el registro más reciente
    visto, y es lo que hace que la vuelta siguiente no vuelva a recorrer lo mismo.

    PRIMER CONTACTO

    `filings.recent` trae hasta mil registros: años de historia. Si al añadir una acción a
    la watchlist se emitieran todos, el radar se llenaría de golpe con documentos viejos
    presentados como si acabaran de ocurrir.

    Así que la primera vez solo se miran los últimos `DIAS_PRIMER_CONTACTO` días, y esos
    eventos van marcados con `inicializacion: True` en su crudo. NO son eventos generados
    artificialmente: son registros reales, con su fecha real; la marca dice que entraron al
    incorporar la empresa y no durante la vigilancia, que es una distinción que hace falta
    para leer el histórico después.

    El resto de la historia no se pierde: sigue en EDGAR, y el enlace de cada evento
    apunta al documento original.
    """
    hoy = hoy or _hoy()
    cursor = cursor or {}
    recientes = ((datos or {}).get("filings") or {}).get("recent") or {}
    formas = recientes.get("form") or []
    accesiones = recientes.get("accessionNumber") or []
    fechas = recientes.get("filingDate") or []
    documentos = recientes.get("primaryDocument") or []

    conocido = canonizar_accession(cursor.get("ultimo_accession") or "")
    es_primer_contacto = not conocido
    corte = None
    if es_primer_contacto:
        corte = (datetime.fromisoformat(hoy) - timedelta(days=DIAS_PRIMER_CONTACTO)).date().isoformat()

    cik = objetivo["cik"]
    symbol = objetivo["symbol"]
    eventos, tope = [], None
    for i, forma in enumerate(formas):
        acc = canonizar_accession(accesiones[i] if i < len(accesiones) else "")
        if not acc:
            continue
        # El primero de la lista es el más reciente: ese será el cursor nuevo, se emita
        # o no. Si solo se guardara cuando hay evento, un formulario que no vigilamos
        # haría que la vuelta siguiente volviera a recorrerlo todo.
        if tope is None:
            tope = acc
        if acc == conocido:
            break                         # de aquí para atrás ya lo hemos visto
        forma = str(forma or "").strip().upper()
        if forma not in FORMULARIOS:
            continue
        fecha = str(fechas[i] if i < len(fechas) else "").strip()
        if corte and fecha and fecha < corte:
            continue                      # primer contacto: nada más viejo que el corte
        doc = str(documentos[i] if i < len(documentos) else "").strip()
        tipo, etiqueta = FORMULARIOS[forma]
        url = (URL_FILING.format(cik=cik, acc=acc, doc=doc) if doc
               else URL_FILING_INDICE.format(cik=cik, acc=acc))
        e = ev.crear(
            fuente=FUENTE, externo_id=f"{forma}:{acc}",
            titulo=f"{forma} · {etiqueta} — {symbol}",
            url=url, symbol=symbol, tipo=tipo, tier=TIER,
            publicado_en=fecha or None,
            crudo={"suceso": forma, "formulario": forma, "cik": str(cik),
                   "accession": acc, "fecha_registro": fecha or None,
                   # Los demás tickers tuyos de esta empresa. Sin esto se perdería que
                   # el evento también afecta a la otra clase que tienes.
                   "tickers_tuyos": objetivo.get("tuyos") or [symbol],
                   **({"inicializacion": True} if es_primer_contacto else {})})
        if e:
            eventos.append(e)
    return {"eventos": eventos,
            "cursor": {"cik": cik, "ultimo_accession": tope or conocido,
                       "symbol": symbol, "tuyos": objetivo.get("tuyos") or [],
                       "primer_contacto": es_primer_contacto}}


# ── Descarga ─────────────────────────────────────────────────────────────────

class LimiteSec(RuntimeError):
    """429 o 403: la SEC nos está diciendo que paremos.

    Tiene su propia clase porque se trata distinto que un fallo cualquiera: un CIK que da
    timeout se salta y se sigue, pero esto corta el ciclo entero. Insistir contra una
    puerta cerrada gasta cuota y no la abre.
    """


async def _pedir_submissions(cliente, cik: int) -> dict:
    r = await cliente.get(URL_SUBMISSIONS.format(cik=cik))
    if r.status_code in (403, 429):
        raise LimiteSec(f"SEC respondió {r.status_code}")
    r.raise_for_status()
    return r.json()


async def recolectar(contexto: dict = None) -> list:
    """La vuelta completa: consulta las empresas que tocan y devuelve sus eventos nuevos.

    QUÉ RECIBE Y QUÉ DEVUELVE POR DETRÁS

    `contexto` trae tu universo, los cursores por CIK y el número de vuelta — todo estado
    de base de datos, que el worker inyecta. Y `contexto["salida"]`, si existe, es el canal
    de vuelta: aquí se dejan los cursores nuevos y el recuento de consultas y fallos, para
    que el worker los persista sin que el bucle tenga que saber qué es un CIK.

    Esa frontera es la que permite que el worker siga siendo genérico después de cambiar
    entero el mecanismo de descubrimiento.
    """
    if not configurado():
        raise RuntimeError("SEC_USER_AGENT no configurado")
    import httpx
    contexto = contexto or {}
    salida = contexto.get("salida")
    if salida is None:
        salida = {}

    tabla = await tabla_tickers()
    objs = objetivos(contexto.get("cartera"), contexto.get("watchlist"), tabla)
    tanda = turno(objs, contexto.get("vuelta", 0))
    cursores = contexto.get("cursores") or {}

    espera = 1.0 / max(0.1, PETICIONES_POR_SEGUNDO)
    eventos, nuevos_cursores, fallos = [], {}, []
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_cabeceras()) as c:
        for i, objetivo in enumerate(tanda):
            if i:
                await asyncio.sleep(espera)
            try:
                datos = await _pedir_submissions(c, objetivo["cik"])
            except LimiteSec:
                # Corta el ciclo entero, pero conserva lo ya recogido: los eventos de las
                # empresas que sí contestaron son válidos y perderlos no ayuda a nadie.
                salida["consultados"] = i
                salida["cursores"] = nuevos_cursores
                salida["fallos"] = fallos
                salida["eventos_antes_del_corte"] = len(eventos)
                raise
            except Exception as e:
                # Un CIK que falla NO tumba la vuelta. Se anota y se sigue: el resto de
                # tus empresas no tiene la culpa.
                fallos.append({"cik": objetivo["cik"], "symbol": objetivo["symbol"],
                               "error": str(e)[:120]})
                continue
            r = parsear_submissions(datos, objetivo, cursores.get(str(objetivo["cik"])))
            eventos.extend(r["eventos"])
            nuevos_cursores[str(objetivo["cik"])] = r["cursor"]

    salida["consultados"] = len(tanda)
    salida["cursores"] = nuevos_cursores
    salida["fallos"] = fallos
    salida["objetivos_totales"] = len(objs)
    salida["sin_cik"] = sorted(
        {str(s).upper() for s in (set(contexto.get("cartera") or ())
                                  | set(contexto.get("watchlist") or ()))}
        - set(tabla["por_ticker"]))
    if fallos:
        logger.warning("intel/sec: %d CIK fallaron de %d", len(fallos), len(tanda))
    return eventos
