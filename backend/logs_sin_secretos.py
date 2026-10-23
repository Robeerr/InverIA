"""Las claves no se escriben en los logs, aunque un error cite la URL entera.

POR QUÉ HACE FALTA

Polygon, Finnhub y FMP reciben la clave DENTRO de la URL (`?apiKey=`, `?token=`,
`?apikey=`), y el bot de Telegram la lleva en la ruta (`/bot<token>/`). Cuando una de esas
peticiones falla, el error de `requests` cita la URL completa, y un
`logger.warning(f"... {e}")` la escribe tal cual. El 23-10-2026 salió así la clave de
Polygon, entera, en un 429 de MSFT: quedó en los logs de Render y, al copiarlos para
diagnosticar otra cosa, en una conversación.

POR QUÉ EN EL FORMATEADOR Y NO EN CADA LLAMADA

Hay decenas de `logger.warning(..., e)` repartidos por el código. Arreglarlos uno a uno
deja fuera el próximo que se escriba. Aquí se tapa el texto FINAL de cada línea, ya
formateada: da igual que la clave venga en el mensaje, en los argumentos o en la traza de
una excepción. También cubre el log de accesos de uvicorn, que escribe la ruta con su
`?token=` cuando alguien llama a un endpoint protegido así.

QUÉ NO HACE

No cambia ninguna petición ni dónde viaja cada clave: eso es de cada proveedor. Solo
decide qué llega a escribirse.
"""
import logging
import re

#: Parámetros de URL que llevan una clave. Solo cuentan detrás de `?` o `&`: así «token»
#: en una frase o «tokens=» en un recuento no se tocan.
_PARAMETRO = re.compile(
    r"(?i)([?&](?:api[_-]?key|apikey|access_token|token|key)=)[^&\s\"'<>]+")

#: El token del bot de Telegram va en la ruta: `/bot123456:AAH.../sendMessage`.
_BOT_TELEGRAM = re.compile(r"(/bot)\d+:[A-Za-z0-9_-]+")

TAPADO = "***"


def tapar(texto: str) -> str:
    """El mismo texto con cada clave sustituida por `***`. Lo demás, intacto."""
    if not texto:
        return texto
    texto = _PARAMETRO.sub(lambda m: m.group(1) + TAPADO, texto)
    return _BOT_TELEGRAM.sub(lambda m: m.group(1) + TAPADO, texto)


class FormatoSinSecretos(logging.Formatter):
    """Envuelve el formateador que ya tuviera el handler y tapa lo que produce.

    Se conserva el original —con su formato, sus colores y su forma de leer los
    argumentos, que en el log de accesos de uvicorn no es la estándar— y solo se toca la
    línea final.
    """

    def __init__(self, base: logging.Formatter = None):
        super().__init__()
        self.base = base or logging.Formatter()

    def format(self, record: logging.LogRecord) -> str:
        return tapar(self.base.format(record))


def instalar(*nombres: str, raiz: bool = True) -> int:
    """Pone el formateador en los handlers de los loggers `nombres` y, salvo `raiz=False`,
    en los del logger raíz, que es por donde sale todo lo de la aplicación.

    Idempotente: un handler que ya lo tiene no se envuelve dos veces. Devuelve cuántos
    handlers se han envuelto en esta llamada.
    """
    envueltos = 0
    for nombre in ((None,) if raiz else ()) + nombres:
        for handler in logging.getLogger(nombre).handlers:
            if not isinstance(handler.formatter, FormatoSinSecretos):
                handler.setFormatter(FormatoSinSecretos(handler.formatter))
                envueltos += 1
    return envueltos
