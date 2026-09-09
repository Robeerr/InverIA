"""Connector de SEC/EDGAR. La primera fuente Tier 1: hechos registrados, no opiniones.

POR QUÉ EMPIEZA POR AQUÍ

Es la fuente más fiable y la más barata: no cuesta dinero, no necesita clave y lo que
publica no es que alguien haya dicho algo — es un documento que una empresa ha tenido
que registrar por ley. Cuando más adelante entren X o YouTube, sus afirmaciones se
podrán contrastar contra esto.

SIN `SEC_USER_AGENT` NO SE HACE NI UNA PETICIÓN

La SEC exige identificarse en la cabecera `User-Agent` y responde 403 a quien no lo
haga. No es una recomendación suya: es su política de acceso.

Así que si la variable no está, el connector se queda en NO_CONFIGURADA y no toca la
red. No hay valor por defecto ni correo escrito en el código: un identificador
inventado sería saltarse su política usando el nombre de otro.

CÓMO SE DESCUBRE LO NUEVO, Y POR QUÉ ASÍ

EDGAR publica un feed Atom con los últimos registros de TODO el mercado. Una sola
petición trae lo más reciente, sin recorrer empresa por empresa.

El orden que sigue este módulo importa tanto como lo que hace:

    1. una petición al feed
    2. cruzar los CIK contra TU universo   ← aquí muere el 99 %
    3. construir eventos solo de lo que queda

El detalle de un filing NO se descarga en esta fase. Lo que no te toca se descarta
sin gastar una segunda petición, que es lo que hace sostenible vigilar el mercado
entero desde un servicio pequeño.

LÍMITES

La SEC pide un máximo de 10 peticiones por segundo. Aquí se hace una cada cinco
minutos, así que el margen es enorme — pero el backoff existe igual, porque un 429 o
un 403 no se responden insistiendo.
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import intel_eventos as ev

logger = logging.getLogger("inveria.intel.sec")

FUENTE = "sec"
TIER = 1
NOMBRE = "SEC/EDGAR"

# Feed de últimos registros. `getcurrent` devuelve lo recién publicado por todo el
# mercado, que es justo lo que hace falta para vigilar sin recorrer empresas.
URL_FEED = "https://www.sec.gov/cgi-bin/browse-edgar"
URL_TICKERS = "https://www.sec.gov/files/company_tickers.json"

# Qué formularios se vigilan y qué significan. Son los dos que mueven precio:
#   8-K → hecho relevante (la empresa está obligada a contarlo)
#   4   → un directivo ha comprado o vendido acciones propias
FORMULARIOS = {
    "8-K": (ev.CORPORATIVO, "Hecho relevante"),
    "4": (ev.INSIDER, "Operación de un directivo"),
}

INTERVALO = int(os.environ.get("INTEL_SEC_INTERVALO", 300))     # 5 min
TIMEOUT = 15

# Estados de salud. Se nombran para que la pantalla los pinte sin interpretarlos.
ONLINE, DEGRADADA, LIMITADA = "ONLINE", "DEGRADADA", "RATE_LIMITED"
NO_CONFIGURADA, ERROR, OFFLINE = "NO_CONFIGURADA", "ERROR", "OFFLINE"

# Backoff: se dobla en cada fallo y se corta a una hora. Sin techo, una caída larga
# dejaría el connector dormido días; sin doblar, insistiría contra una puerta cerrada.
BACKOFF_BASE = 60
BACKOFF_MAX = 3600

_cache_tickers = {"cuando": None, "por_cik": {}}


def user_agent() -> Optional[str]:
    """El identificador exigido por la SEC, o None si no está configurado.

    Se lee del entorno en CADA llamada y no al importar: así, añadirlo en Render y
    reiniciar basta para que el connector arranque, sin tocar código.
    """
    ua = (os.environ.get("SEC_USER_AGENT") or "").strip()
    return ua or None


def configurado() -> bool:
    return user_agent() is not None


def estado_salud(ultimo_error: Optional[str] = None,
                 fallos: int = 0) -> str:
    """El estado que se enseña. NO_CONFIGURADA es de primera clase, no un error.

    Que una fuente sin credenciales se dibuje apagada —y no «con error»— es lo que
    permite que el radar diga la verdad: X y SEC sin configurar no están rotas, es
    que no se han conectado todavía.
    """
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
    """La SEC además pide `Accept-Encoding` y responde mejor con `Host` explícito."""
    return {
        "User-Agent": user_agent() or "",
        "Accept-Encoding": "gzip, deflate",
    }


async def _tickers_por_cik() -> dict:
    """{cik_int: TICKER} desde el fichero público de la SEC. Cacheado 24 h.

    Hace falta porque el feed identifica empresas por CIK y tu cartera por ticker.
    Son ~10.000 entradas y cambian muy poco: pedirlo más de una vez al día sería
    gastar una petición en algo que no se mueve.
    """
    import httpx
    ahora = datetime.now(timezone.utc)
    cuando = _cache_tickers["cuando"]
    if cuando and (ahora - cuando).total_seconds() < 86400 and _cache_tickers["por_cik"]:
        return _cache_tickers["por_cik"]
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_cabeceras()) as c:
        r = await c.get(URL_TICKERS)
        r.raise_for_status()
        datos = r.json()
    por_cik = {}
    for fila in (datos.values() if isinstance(datos, dict) else datos):
        try:
            por_cik[int(fila["cik_str"])] = str(fila["ticker"]).upper()
        except (KeyError, TypeError, ValueError):
            continue
    _cache_tickers["por_cik"], _cache_tickers["cuando"] = por_cik, ahora
    logger.info("SEC: %d tickers cacheados", len(por_cik))
    return por_cik


# El Atom de EDGAR trae el CIK dentro del enlace y el formulario en el título.
_RE_CIK = re.compile(r"/Archives/edgar/data/(\d+)/")
_RE_ACCESION = re.compile(r"/(\d{10}-?\d{2}-?\d{6})[-.]")


def parsear_feed(xml: str, por_cik: dict) -> list:
    """Del Atom crudo a eventos sin procesar. PURA: no toca la red.

    Se separa de la descarga a propósito — es la parte con reglas y la que se puede
    probar con un XML guardado, sin depender de que la SEC esté publicando algo hoy.

    Una entrada sin CIK reconocible, sin número de registro o de un formulario que no
    vigilamos se ignora en silencio: el feed trae decenas de tipos y no todos dicen
    nada sobre una acción.
    """
    if not xml:
        return []
    eventos = []
    # Se parte por `<entry>` en vez de usar un parser XML: el Atom de EDGAR es plano
    # y añadir una dependencia de parseo para esto no se sostiene.
    for bloque in xml.split("<entry>")[1:]:
        titulo = _entre(bloque, "<title>", "</title>")
        enlace = _atributo(bloque, "href")
        actualizado = _entre(bloque, "<updated>", "</updated>")
        if not titulo or not enlace:
            continue
        # El título tiene la forma «8-K - NVIDIA CORP (0001045810) (Filer)».
        forma = titulo.split(" - ")[0].strip().upper()
        if forma not in FORMULARIOS:
            continue
        m_cik = _RE_CIK.search(enlace)
        if not m_cik:
            continue
        symbol = por_cik.get(int(m_cik.group(1)))
        if not symbol:
            continue                      # empresa sin ticker público conocido
        m_acc = _RE_ACCESION.search(enlace)
        externo = m_acc.group(1) if m_acc else enlace
        tipo, etiqueta = FORMULARIOS[forma]
        nombre = titulo.split(" - ", 1)[1].split("(")[0].strip() if " - " in titulo else ""
        e = ev.crear(
            fuente=FUENTE, externo_id=f"{forma}:{externo}",
            titulo=f"{forma} · {etiqueta}" + (f" — {nombre}" if nombre else ""),
            url=enlace, symbol=symbol, tipo=tipo, tier=TIER,
            publicado_en=actualizado or None,
            crudo={"formulario": forma, "cik": m_cik.group(1), "titulo_sec": titulo},
        )
        if e:
            eventos.append(e)
    return eventos


def _entre(texto: str, ini: str, fin: str) -> str:
    a = texto.find(ini)
    if a < 0:
        return ""
    a += len(ini)
    b = texto.find(fin, a)
    return texto[a:b].strip() if b > a else ""


def _atributo(bloque: str, nombre: str) -> str:
    m = re.search(nombre + r'="([^"]+)"', bloque)
    return m.group(1) if m else ""


async def descargar(formulario: str = "8-K", limite: int = 40) -> list:
    """Pide el feed y devuelve eventos crudos. Lanza si la SEC responde mal.

    Deja subir la excepción a propósito: quien decide si eso es un backoff, un cambio
    de estado o una entrada en el log es el worker, que es el que lleva la cuenta de
    fallos seguidos. Tragársela aquí devolvería una lista vacía indistinguible de «no
    hay nada nuevo», y esas dos cosas no se pueden confundir.
    """
    if not configurado():
        raise RuntimeError("SEC_USER_AGENT no configurado")
    import httpx
    params = {"action": "getcurrent", "type": formulario, "company": "",
              "dateb": "", "owner": "include", "count": limite, "output": "atom"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=_cabeceras()) as c:
        r = await c.get(URL_FEED, params=params)
        if r.status_code in (403, 429):
            raise RuntimeError(f"SEC respondió {r.status_code}")
        r.raise_for_status()
        xml = r.text
    return parsear_feed(xml, await _tickers_por_cik())
