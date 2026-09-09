"""Sondeo de EDGAR: medir antes de construir.

QUÉ PREGUNTA CONTESTA, Y POR QUÉ ES LA ÚNICA QUE IMPORTA AHORA

Vigilar por CIK significa pedir el historial de cada empresa en cada vuelta. Si esas
peticiones devuelven el JSON entero cada vez, son ~2,9 GB al día para descubrir quizá un
registro. Si devuelven `304 Not Modified`, son 3 MB. Tres órdenes de magnitud de
diferencia, y toda la arquitectura depende de cuál de las dos es cierta.

Eso no se puede estimar de memoria. Se mide.

QUÉ HACE Y QUÉ NO

Hace seis peticiones —dos por cada uno de tres CIK— y devuelve lo que midió: tamaño real
transferido, cabeceras de caché, código de la segunda petición y tiempos.

NO escribe en la base de datos, NO toca `intel_sec` y NO cambia el comportamiento de nada.
Lee la Cartera para elegir tres símbolos y reutiliza la identificación y la tabla de
tickers del connector, porque usar otras sería medir algo distinto de lo que se va a
construir.

LO QUE SE MIDE ES LO QUE VIAJA POR EL CABLE

`len(response.content)` es el JSON ya descomprimido, y con gzip eso puede ser cinco veces
lo que de verdad se descargó. La cifra que decide si el diseño es viable es la comprimida,
así que se anotan las dos por separado y se dice cuál es cuál.
"""
import asyncio
import logging
import time
from typing import Optional

import intel_sec as sec

logger = logging.getLogger("inveria.intel.sondeo")

URL_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

#: Cuántas empresas se sondean. Tres bastan para ver si la caché condicional funciona;
#: sondear las 51 sería gastar peticiones en confirmar lo mismo tres veces por empresa.
CUANTOS = 3

#: Espera entre peticiones. La SEC admite 10/s; aquí se va muy por debajo porque esto es
#: una prueba manual y no hay ninguna prisa.
ESPERA = 0.4
TIMEOUT = 20


def _peso(respuesta) -> dict:
    """Lo que viajó de verdad y lo que ocupa ya descomprimido. No es lo mismo.

    `num_bytes_downloaded` es lo que httpx contó en el socket: bytes reales, comprimidos.
    `content-length` es lo que anunció el servidor, también comprimido, y puede faltar si
    la respuesta llegó troceada. `len(content)` es el JSON ya expandido, que es la cifra
    que engaña — con gzip suele ser varias veces mayor.
    """
    try:
        cl = respuesta.headers.get("content-length")
        cl = int(cl) if cl is not None else None
    except (TypeError, ValueError):
        cl = None
    return {
        "bytes_transferidos": getattr(respuesta, "num_bytes_downloaded", None),
        "content_length": cl,
        "bytes_descomprimidos": len(respuesta.content or b""),
        "compresion": respuesta.headers.get("content-encoding"),
    }


def _cache(respuesta) -> dict:
    h = respuesta.headers
    return {
        "etag": h.get("etag"),
        "last_modified": h.get("last-modified"),
        "cache_control": h.get("cache-control"),
        "age": h.get("age"),
    }


def condicionales(cabeceras_cache: dict) -> dict:
    """Las cabeceras con las que se repite la petición. EXACTAMENTE las que tocan.

    `If-None-Match` con el ETag e `If-Modified-Since` con el Last-Modified. Si el servidor
    no dio ninguna de las dos, no se envía nada inventado: preguntar con una fecha que no
    salió de él daría un `304` que no demuestra nada sobre su caché.
    """
    cond = {}
    if cabeceras_cache.get("etag"):
        cond["If-None-Match"] = cabeceras_cache["etag"]
    if cabeceras_cache.get("last_modified"):
        cond["If-Modified-Since"] = cabeceras_cache["last_modified"]
    return cond


async def _pedir(cliente, url: str, extra: dict = None) -> dict:
    t0 = time.perf_counter()
    r = await cliente.get(url, headers=extra or None)
    ms = round((time.perf_counter() - t0) * 1000)
    return {"http": r.status_code, "ms": ms, **_peso(r), "cache": _cache(r)}


async def sondear_cik(cliente, cik: int, symbol: str) -> dict:
    """Las dos peticiones de una empresa: normal y condicional."""
    url = URL_SUBMISSIONS.format(cik=cik)
    primera = await _pedir(cliente, url)
    if primera["http"] != 200:
        return {"symbol": symbol, "cik": cik, "url": url,
                "primera": primera, "segunda": None,
                "condicionales_enviadas": {},
                "error": f"la primera petición respondió {primera['http']}"}

    await asyncio.sleep(ESPERA)
    cond = condicionales(primera["cache"])
    if not cond:
        # Sin ETag ni Last-Modified no hay caché condicional que probar. Se dice, en vez
        # de repetir la petición a secas y presentarlo como si fuera una prueba.
        return {"symbol": symbol, "cik": cik, "url": url,
                "primera": primera, "segunda": None, "condicionales_enviadas": {},
                "error": "la respuesta no trae ni ETag ni Last-Modified"}
    segunda = await _pedir(cliente, url, cond)
    return {"symbol": symbol, "cik": cik, "url": url,
            "primera": primera, "segunda": segunda,
            "condicionales_enviadas": cond, "error": None}


def veredicto(resultados: list) -> dict:
    """¿Funciona la caché condicional? Sí, no, o a medias. Sin interpretar de más.

    Se exige que TODAS las empresas sondeadas devuelvan 304. Con dos de tres el diseño no
    se sostiene: bastaría una empresa que no cachea para que su JSON entero entrara en
    cada vuelta, y no sabríamos cuáles hasta desplegarlo.
    """
    utiles = [r for r in resultados if r.get("segunda")]
    if not utiles:
        return {"funciona": False, "veredicto": "SIN_DATOS",
                "detalle": "Ninguna petición condicional llegó a hacerse."}
    con_304 = [r for r in utiles if r["segunda"]["http"] == 304]
    if len(con_304) == len(resultados):
        return {"funciona": True, "veredicto": "APOYA",
                "detalle": f"Las {len(con_304)} respondieron 304."}
    if con_304:
        return {"funciona": False, "veredicto": "PARCIAL",
                "detalle": (f"Solo {len(con_304)} de {len(resultados)} respondieron 304. "
                            "Una empresa que no cachea descargaría su JSON entero en cada "
                            "vuelta, y no sabríamos cuál hasta desplegarlo.")}
    return {"funciona": False, "veredicto": "NO_APOYA",
            "detalle": "Ninguna respondió 304: no hay caché condicional que aprovechar."}


def _media(valores) -> Optional[float]:
    v = [x for x in valores if isinstance(x, (int, float))]
    return sum(v) / len(v) if v else None


def proyeccion(resultados: list, en_cartera: int, en_watchlist: int,
               ciclo_s: int = 300, turnos_watchlist: int = 6) -> dict:
    """El tráfico diario que saldría de verdad, calculado con los bytes MEDIDOS.

    Se devuelven los dos escenarios siempre —con y sin caché condicional— porque el
    segundo es el que hay que mirar si el sondeo sale mal, y tenerlo calculado evita
    decidir la arquitectura con una cifra estimada de memoria.
    """
    pesa = lambda cual, campo: _media(
        [(r.get(cual) or {}).get(campo) for r in resultados if r.get(cual)])
    # Se prefiere lo que httpx contó en el socket; el content-length es el respaldo.
    b_primera = pesa("primera", "bytes_transferidos") or pesa("primera", "content_length")
    b_segunda = pesa("segunda", "bytes_transferidos") or pesa("segunda", "content_length")

    ciclos = 86400 / ciclo_s
    por_ciclo = en_cartera + en_watchlist / max(1, turnos_watchlist)
    peticiones = por_ciclo * ciclos

    def mb(bytes_por_peticion):
        if not bytes_por_peticion:
            return None
        return round(peticiones * bytes_por_peticion / (1024 * 1024), 1)

    return {
        "supuestos": {"en_cartera": en_cartera, "en_watchlist": en_watchlist,
                      "ciclo_s": ciclo_s, "turnos_watchlist": turnos_watchlist,
                      "cada_cartera_min": round(ciclo_s / 60),
                      "cada_watchlist_min": round(ciclo_s * turnos_watchlist / 60)},
        "peticiones_por_ciclo": round(por_ciclo, 1),
        "peticiones_por_dia": round(peticiones),
        "pet_por_segundo": round(peticiones / 86400, 3),
        "porcentaje_del_limite_sec": round(peticiones / 86400 / 10 * 100, 2),
        "bytes_medios_primera": round(b_primera) if b_primera else None,
        "bytes_medios_segunda": round(b_segunda) if b_segunda else None,
        # Los dos escenarios, con los bytes reales.
        "mb_dia_con_condicional": mb(b_segunda),
        "mb_dia_sin_condicional": mb(b_primera),
        "ms_medio_primera": round(_media([r["primera"]["ms"] for r in resultados
                                          if r.get("primera")]) or 0),
        "ms_medio_segunda": round(_media([r["segunda"]["ms"] for r in resultados
                                          if r.get("segunda")]) or 0),
    }


async def sondear(ciks: list, en_cartera: int = 0, en_watchlist: int = 0) -> dict:
    """El sondeo entero. `ciks` es una lista de `(cik_int, symbol)`.

    Lanza si falta la identificación, igual que el connector: sin `SEC_USER_AGENT` no se
    toca la red tampoco para medir.
    """
    if not sec.configurado():
        raise RuntimeError("SEC_USER_AGENT no configurado")
    import httpx
    resultados = []
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=sec._cabeceras()) as c:
        for i, (cik, symbol) in enumerate(ciks):
            if i:
                await asyncio.sleep(ESPERA)
            try:
                resultados.append(await sondear_cik(c, cik, symbol))
            except Exception as e:
                resultados.append({"symbol": symbol, "cik": cik,
                                   "url": URL_SUBMISSIONS.format(cik=cik),
                                   "primera": None, "segunda": None,
                                   "condicionales_enviadas": {}, "error": str(e)[:200]})
    return {
        "endpoint": URL_SUBMISSIONS,
        "peticiones_hechas": sum(1 for r in resultados if r.get("primera"))
                             + sum(1 for r in resultados if r.get("segunda")),
        "resultados": resultados,
        **veredicto(resultados),
        "proyeccion": proyeccion(resultados, en_cartera, en_watchlist),
    }
