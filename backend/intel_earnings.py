"""Connector de resultados (Finnhub). La primera fuente que mira HACIA DELANTE.

QUÉ APORTA QUE NO APORTA LA SEC

Todo lo de la fase 0.5 es retrospectivo: te cuenta lo que ya pasó. Unos resultados son lo
contrario — se sabe con semanas de antelación que van a publicarse, y son el mayor
generador de volatilidad programada que tiene una acción. Es la primera fuente que puede
avisarte ANTES de que el precio se mueva.

TRES EVENTOS DISTINTOS, NO UNO

Del mismo calendario salen tres cosas que no significan lo mismo:

    PROGRAMADO   ·  hay fecha para los resultados de este trimestre
    CAMBIO       ·  esa fecha se ha movido
    PUBLICADO    ·  ya hay cifras

El cambio de fecha es información de verdad: adelantar resultados suele acompañar a
buenas noticias y retrasarlos es una de las señales de alarma más antiguas que hay. Si se
tratara como «el mismo evento actualizado», ese movimiento desaparecería sin dejar rastro.

CÓMO SE MANTIENE LA IDEMPOTENCIA CON UN DATO QUE CAMBIA

El id lleva la fecha dentro: `earnings:AAPL:2026Q3:2026-10-28`. De ahí salen las dos
propiedades a la vez, sin tocar el modelo de eventos ni añadir etapas:

  · leer el mismo calendario otra vez produce el MISMO id → ya conocido, no se reescribe;
  · si la fecha se mueve, el id es OTRO → entra como evento nuevo, con su propia entrada
    en el radar y su propio momento en el tiempo.

Para poder decir «antes era el 28» hace falta saber qué fecha teníamos. Eso es estado de
base de datos, así que NO se consulta aquí: se inyecta. `construir()` es pura y recibe las
fechas conocidas, igual que `intel_sec.parsear_feed` recibe la tabla de tickers.

UNA FECHA ESTIMADA NO ES UN HECHO

Finnhub sirve fechas que a veces son estimación suya y no anuncio de la empresa. Se marca
en el propio evento y se dice en el título. Confundir «la empresa ha anunciado que publica
el 28» con «el proveedor cree que será el 28» es exactamente el tipo de detalle que hace
que un sistema deje de ser fiable sin que se note.

COSTE

Cero: Finnhub ya está integrado y con clave. Una llamada masiva cada seis horas, filtrada
por tu universo del lado del cliente — es la misma llamada que ya hace el calendario de la
aplicación, y ni siquiera sube el gasto de cuota de forma apreciable.
"""
import asyncio
import logging
import os
from typing import Optional

import intel_eventos as ev

logger = logging.getLogger("inveria.intel.earnings")

FUENTE = "earnings"
TIER = 2                     # dato de proveedor, no documento registrado
NOMBRE = "Finnhub · Resultados"

# Seis horas. El calendario se mueve poco y lo que importa es tener la fecha con días de
# antelación, no con minutos. Pedirlo más a menudo gastaría cuota para leer lo mismo.
INTERVALO = int(os.environ.get("INTEL_EARNINGS_INTERVALO", 6 * 3600))

# Cuántos días hacia delante se miran. Tres semanas cubren la temporada de resultados
# entera con margen; más allá las fechas son casi todas estimaciones y cambian solas.
DIAS_VISTA = int(os.environ.get("INTEL_EARNINGS_DIAS", 21))

ONLINE, DEGRADADA, LIMITADA = "ONLINE", "DEGRADADA", "RATE_LIMITED"
NO_CONFIGURADA, ERROR, OFFLINE = "NO_CONFIGURADA", "ERROR", "OFFLINE"

BACKOFF_BASE, BACKOFF_MAX = 300, 3600

# Los tres sucesos. Se nombran porque viajan a Mongo y la pantalla los distingue.
PROGRAMADO, CAMBIO_FECHA, PUBLICADO = "programado", "cambio_fecha", "publicado"

# Cuándo publica, en el vocabulario de Finnhub. Se traduce porque «bmo» no significa nada
# para quien lee la pantalla, y la hora importa: antes de abrir te pilla con la posición
# abierta y sin poder reaccionar hasta la campana.
_MOMENTOS = {"bmo": "antes de abrir", "amc": "tras el cierre", "dmh": "con el mercado abierto"}


def configurado() -> bool:
    return bool((os.environ.get("FINNHUB_API_KEY") or "").strip())


def estado_salud(ultimo_error: Optional[str] = None, fallos: int = 0) -> str:
    """Mismo contrato que `intel_sec.estado_salud`: la pantalla no distingue de quién es.

    NO_CONFIGURADA es de primera clase y no un error: sin clave la fuente está apagada,
    que no es lo mismo que rota.
    """
    if not configurado():
        return NO_CONFIGURADA
    if not ultimo_error:
        return ONLINE
    if "429" in ultimo_error or "rate" in ultimo_error.lower():
        return LIMITADA
    if "401" in ultimo_error or "403" in ultimo_error:
        return ERROR
    return DEGRADADA if fallos < 3 else OFFLINE


def espera_tras_fallo(fallos: int) -> int:
    if fallos <= 0:
        return 0
    return min(BACKOFF_BASE * (2 ** (fallos - 1)), BACKOFF_MAX)


def clave_trimestre(fila: dict) -> Optional[str]:
    """`AAPL:2026Q3` — la identidad del trimestre, sin la fecha.

    Es lo que permite reconocer que dos anuncios con fechas distintas hablan del MISMO
    trimestre, que es justo lo que hay que saber para detectar que la fecha se ha movido.

    Sin trimestre ni año no se inventa uno: se devuelve None y la fila se ignora. Un
    trimestre mal adivinado emparejaría anuncios de periodos distintos y produciría
    «cambios de fecha» que nunca ocurrieron.
    """
    symbol = (fila.get("symbol") or "").upper().strip()
    try:
        trimestre, anio = int(fila.get("quarter")), int(fila.get("year"))
    except (TypeError, ValueError):
        return None
    if not symbol or not (1 <= trimestre <= 4):
        return None
    return f"{symbol}:{anio}Q{trimestre}"


def _cifra(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _importe(v) -> str:
    return f"{v:.2f}".replace(".", ",")


def construir(filas: list, fechas_conocidas: dict = None) -> list:
    """Del calendario crudo a eventos. PURA: no toca la red ni la base de datos.

    `fechas_conocidas` es `{clave_trimestre: última_fecha_vista}`. Se inyecta porque es
    estado de base de datos y este módulo no la tiene — la misma frontera que hace
    testeable a `intel_sec.parsear_feed`.

    Una fila puede producir dos eventos: si ya hay cifras publicadas, sale el evento de
    publicación Y, si además la fecha se movió respecto de lo que sabíamos, el de cambio.
    Son dos hechos distintos y perder uno por contar el otro sería perder información.
    """
    conocidas = fechas_conocidas or {}
    eventos = []
    for fila in filas or []:
        if not isinstance(fila, dict):
            continue
        clave = clave_trimestre(fila)
        fecha = (fila.get("date") or "").strip()
        if not clave or not fecha:
            continue                      # sin trimestre o sin fecha no hay evento posible
        symbol = clave.split(":")[0]
        trimestre = clave.split(":")[1]
        momento = _MOMENTOS.get((fila.get("hour") or "").lower().strip())
        estimado = _cifra(fila.get("eps_estimate"))
        real = _cifra(fila.get("eps_actual"))

        crudo_base = {"trimestre": trimestre, "fecha": fecha,
                      "momento": fila.get("hour") or None,
                      "eps_estimado": estimado, "eps_real": real,
                      "ingresos_estimados": _cifra(fila.get("revenue_estimate")),
                      "ingresos_reales": _cifra(fila.get("revenue_actual"))}

        anterior = conocidas.get(clave)
        if anterior and anterior != fecha:
            # LA FECHA SE HA MOVIDO. Evento propio, con su id y su sitio en el radar:
            # adelantar resultados suele acompañar a buenas noticias y retrasarlos es una
            # de las señales de alarma más viejas del oficio. Tratarlo como una simple
            # actualización del evento anterior lo borraría del histórico.
            adelanta = fecha < anterior
            eventos.append(ev.crear(
                fuente=FUENTE, externo_id=f"{clave}:{fecha}",
                titulo=(f"{symbol} {trimestre} · Resultados "
                        f"{'ADELANTADOS' if adelanta else 'retrasados'}: "
                        f"del {anterior} al {fecha}"),
                symbol=symbol, tipo=ev.RESULTADOS, tier=TIER, publicado_en=None,
                crudo={**crudo_base, "suceso": CAMBIO_FECHA, "fecha_anterior": anterior,
                       "adelanta": adelanta}))
        elif not anterior:
            eventos.append(ev.crear(
                fuente=FUENTE, externo_id=f"{clave}:{fecha}",
                titulo=(f"{symbol} {trimestre} · Resultados el {fecha}"
                        + (f", {momento}" if momento else "")
                        + (f" · BPA esperado {_importe(estimado)} $" if estimado is not None else "")),
                symbol=symbol, tipo=ev.RESULTADOS, tier=TIER, publicado_en=None,
                crudo={**crudo_base, "suceso": PROGRAMADO}))

        if real is not None:
            # YA HAY CIFRAS. Id sin fecha: los resultados de un trimestre se publican una
            # vez, y si la fecha bailó antes de publicarse eso no puede convertirse en dos
            # eventos de publicación.
            #
            # El titular compara lo real con lo esperado, que es aritmética de la propia
            # fuente. No lleva veredicto: «ha batido expectativas» sería una lectura, y
            # aquí no se interpreta nada todavía.
            comparacion = ""
            if estimado is not None:
                comparacion = f" frente a {_importe(estimado)} $ esperado"
            eventos.append(ev.crear(
                fuente=FUENTE, externo_id=f"{clave}:publicado",
                titulo=(f"{symbol} {trimestre} · Resultados publicados: "
                        f"BPA {_importe(real)} $" + comparacion),
                symbol=symbol, tipo=ev.RESULTADOS, tier=TIER, publicado_en=fecha,
                crudo={**crudo_base, "suceso": PUBLICADO,
                       "diferencia_eps": (round(real - estimado, 4)
                                          if estimado is not None else None)}))

    return [e for e in eventos if e]


async def recolectar(contexto: dict = None) -> list:
    """Pide el calendario y devuelve eventos crudos. Lanza si Finnhub responde mal.

    Deja subir la excepción a propósito, igual que el connector de la SEC: quien lleva la
    cuenta de fallos seguidos y decide el backoff es el worker. Devolver una lista vacía
    haría indistinguible «no hay resultados próximos» de «la fuente está caída».

    La llamada de Finnhub es síncrona y pasa por su limitador compartido, así que va en un
    hilo aparte: bloquear el bucle de eventos pararía los otros quince workers.
    """
    if not configurado():
        raise RuntimeError("FINNHUB_API_KEY no configurada")
    contexto = contexto or {}
    universo = contexto.get("universo") or set()
    if not universo:
        # Sin universo no se pide nada. No es un fallo: es que no hay con qué cruzar, y
        # traerse el calendario del mercado entero para tirarlo sería gastar la cuota en
        # nada.
        return []

    import external_data
    datos = await asyncio.to_thread(
        external_data.finnhub_earnings_calendar, DIAS_VISTA, set(universo))
    if datos is None:
        raise RuntimeError("Finnhub no devolvió calendario")
    return construir(datos.get("items") or [], contexto.get("fechas_conocidas"))
