"""De materia prima a evento significativo, sin tocar la red ni la base de datos.

EL ORDEN IMPORTA, Y ES LO BARATO PRIMERO

    normalizar → deduplicar → filtrar → puntuar

Cada paso descarta trabajo del siguiente. Deduplicar antes de filtrar evita puntuar
seis veces el mismo suceso; filtrar antes de puntuar evita evaluar lo que no te toca.

Esto no es elegancia: es la regla que impide repetir los 3,65 € que este proyecto se
gastó en un día. Cuando la fase siguiente añada investigación con IA, se enchufará
DESPUÉS de este filtro, y no antes.

LA RELEVANCIA ES PERSONAL, Y ESE ES EL PUNTO

La misma noticia vale 15 para quien no tiene la acción y 90 para quien la lleva al
30 % de su cartera. Por eso `puntuar` recibe tu contexto —cartera, watchlist, tesis—
y no solo el evento. Un sistema que puntuara «relevancia objetiva» estaría midiendo
otra cosa.

LO QUE NO HACE ESTE MÓDULO

No sabe qué es SEC, no abre conexiones y no escribe nada. Recibe listas y diccionarios
y devuelve listas y diccionarios. Todo lo que decide se puede probar en memoria.
"""
from typing import Optional

import intel_eventos as ev

# ── Pesos de la relevancia. DECISIONES, con su motivo al lado. ───────────────
#
# Tener la acción EN CARTERA pesa más que tenerla en watchlist porque hay dinero
# dentro: el mismo hecho cambia lo que puedes perder, no solo lo que te interesa.
PESO_CARTERA = 45
PESO_WATCHLIST = 25
PESO_TESIS = 20

# El TIER de la fuente. Un filing de la SEC es un hecho registrado; un tuit es que
# alguien ha dicho algo. Los dos pueden descubrir una señal, pero no valen igual como
# evidencia, y esta diferencia es la que impide que un rumor entre como si fuera un
# hecho.
PESO_TIER = {1: 25, 2: 15, 3: 8, 4: 0}

# Suelo para que un evento pase de `filtrado` a `significativo`. Por debajo se guarda
# y se puede consultar, pero no aparece solo.
UMBRAL_SIGNIFICATIVO = 40

# Motivos de descarte. Se nombran para poder CONTARLOS en diagnóstico: «cuántos
# descarté y por qué» es la única forma de saber si el filtro está bien calibrado o
# está tirando cosas buenas.
SIN_SYMBOL = "sin_symbol"
FUERA_DE_UNIVERSO = "fuera_de_universo"
SIN_RELEVANCIA = "sin_relevancia"
MOTIVOS = (SIN_SYMBOL, FUERA_DE_UNIVERSO, SIN_RELEVANCIA)

# «Ya conocido» NO es un motivo de descarte, y por eso vive fuera de MOTIVOS.
#
# Un documento que ya tenemos no es un evento irrelevante: simplemente no es nuevo. La
# distinción no es cosmética — mezclarlos hace que el diagnóstico empeore justo cuando el
# sistema va bien. Con el feed de la SEC, que devuelve los mismos 40 registros cada cinco
# minutos, casi todo lo que se lee ya lo teníamos: contarlo como descarte daría una tasa
# de descarte del 90 % y parecería un filtro fuera de control, cuando lo que demuestra es
# que la deduplicación funciona.
#
# La constante se conserva porque el propio pipeline no cambia: `deduplicar` sigue
# separando repetidos igual que antes. Lo que cambia es dónde se CUENTAN.
DUPLICADO = "duplicado"


def normalizar(evento: dict) -> dict:
    """Deja el evento en forma canónica. Hoy: el símbolo en mayúsculas y sin espacios.

    Parece poco, y lo es a propósito: normalizar es donde se acumulan las reglas de
    cada fuente, y meterlas aquí antes de tener más de una fuente sería inventarse
    problemas. Existe como paso porque el ORDEN del pipeline sí es definitivo aunque
    su contenido crezca.
    """
    if not isinstance(evento, dict):
        return evento
    if evento.get("etapa") != ev.RECIBIDO:
        return evento
    limpio = dict(evento)
    s = (limpio.get("symbol") or "").strip().upper()
    limpio["symbol"] = s or None
    limpio["titulo"] = " ".join((limpio.get("titulo") or "").split())
    return ev.avanzar(limpio, ev.NORMALIZADO)


def deduplicar(eventos: list, ids_conocidos=None) -> tuple:
    """Separa los nuevos de los que ya habíamos visto.

    Devuelve `(nuevos, repetidos)`. Los repetidos NO se marcan como descartados y no
    se devuelven para escribir: simplemente ya existen. Marcarlos descartados
    reescribiría un documento que quizá ya avanzó a `significativo`, y un evento
    procesado no puede retroceder porque su feed lo haya vuelto a mencionar.

    La deduplicación es por `id`, que es determinista (`fuente:externo_id`). Eso es lo
    que hace idempotente al worker: dos vueltas sobre el mismo feed no crean nada.
    """
    conocidos = set(ids_conocidos or ())
    nuevos, repetidos, vistos_ahora = [], [], set()
    for e in eventos or []:
        if not isinstance(e, dict):
            continue
        eid = e.get("id")
        if not eid:
            continue
        # `vistos_ahora` cubre el duplicado DENTRO del mismo lote: un feed puede
        # traer la misma entrada dos veces, y sin esto entrarían las dos.
        if eid in conocidos or eid in vistos_ahora:
            repetidos.append(e)
            continue
        vistos_ahora.add(eid)
        nuevos.append(ev.avanzar(e, ev.DEDUPLICADO) if e.get("etapa") == ev.NORMALIZADO else e)
    return nuevos, repetidos


def filtrar(eventos: list, universo=None) -> tuple:
    """Se queda con lo que toca a TU universo. Devuelve `(pasan, descartados)`.

    El universo son tus símbolos: watchlist más cartera. Un evento sin símbolo o de
    una acción que no sigues se descarta AQUÍ, antes de puntuar y mucho antes de que
    ninguna IA lo mire. Es el filtro que hace sostenible vigilar un mercado entero.

    Un universo VACÍO no deja pasar nada, y es deliberado: significa que aún no
    tienes cartera ni watchlist, no que todo te interese. Dejar pasar todo en ese
    caso llenaría el radar de ruido justo el día que lo estrenas.
    """
    uni = {str(s).upper() for s in (universo or ()) if s}
    pasan, descartados = [], []
    for e in eventos or []:
        if not isinstance(e, dict):
            continue
        sym = e.get("symbol")
        if not sym:
            descartados.append(ev.avanzar(e, ev.DESCARTADO, SIN_SYMBOL))
            continue
        if sym not in uni:
            descartados.append(ev.avanzar(e, ev.DESCARTADO, FUERA_DE_UNIVERSO))
            continue
        pasan.append(ev.avanzar(e, ev.FILTRADO) if e.get("etapa") == ev.DEDUPLICADO else e)
    return pasan, descartados


def puntuar(evento: dict, cartera=None, watchlist=None, tesis=None) -> dict:
    """Pone nota de relevancia y decide si el evento es significativo.

    La nota suma tres contextos personales y el tier de la fuente. No hay ninguna
    fórmula financiera aquí: no se estima impacto en el precio ni se predice nada.
    Se mide CUÁNTO TE TOCA, que es lo único que este módulo puede saber.

    Guarda además los tres booleanos por separado —cartera, watchlist, tesis— porque
    la pantalla necesita decir POR QUÉ importa, y un número solo no lo dice.
    """
    if not isinstance(evento, dict):
        return evento
    sym = (evento.get("symbol") or "").upper()
    en_cartera = sym in {str(s).upper() for s in (cartera or ()) if s}
    en_watchlist = sym in {str(s).upper() for s in (watchlist or ()) if s}
    en_tesis = sym in {str(s).upper() for s in (tesis or ()) if s}

    nota = 0
    nota += PESO_CARTERA if en_cartera else 0
    nota += PESO_WATCHLIST if en_watchlist else 0
    nota += PESO_TESIS if en_tesis else 0
    nota += PESO_TIER.get(int(evento.get("tier") or 4), 0)
    nota = max(0, min(100, nota))

    salida = dict(evento)
    salida["relevancia"] = nota
    salida["nivel_alerta"] = ev.nivel_de(nota)
    salida["afecta_cartera"] = en_cartera
    salida["afecta_watchlist"] = en_watchlist
    salida["afecta_tesis"] = en_tesis

    if nota >= UMBRAL_SIGNIFICATIVO:
        return ev.avanzar(salida, ev.SIGNIFICATIVO)
    # Por debajo del umbral NO se descarta: se queda en `filtrado`. Es información
    # tuya que no merece interrumpirte, y borrarla impediría responder después «¿qué
    # sabía InverIA de esto?». Descartar y no-alertar son cosas distintas.
    return salida


def procesar(crudos: list, universo=None, ids_conocidos=None,
             cartera=None, watchlist=None, tesis=None) -> dict:
    """El pipeline entero, de una tirada. Es lo que llama el worker.

    Devuelve todo lo que hace falta para escribir Y para explicar qué ha pasado:
    los que se guardan, los que se descartan y el recuento por motivo. Ese recuento
    es lo que alimenta el diagnóstico — sin él, un filtro demasiado agresivo se ve
    igual que un mercado tranquilo.
    """
    normalizados = [normalizar(e) for e in (crudos or []) if isinstance(e, dict)]
    nuevos, repetidos = deduplicar(normalizados, ids_conocidos)
    pasan, descartados = filtrar(nuevos, universo)
    puntuados = [puntuar(e, cartera, watchlist, tesis) for e in pasan]

    # Solo motivos del FILTRO. Los repetidos se cuentan aparte, en `repetidos`.
    por_motivo = {m: 0 for m in MOTIVOS}
    for d in descartados:
        motivo = d.get("motivo_descarte")
        if motivo in por_motivo:
            por_motivo[motivo] += 1

    significativos = [e for e in puntuados if e.get("etapa") == ev.SIGNIFICATIVO]
    return {
        # Se guardan los que pasaron Y los descartados: el descarte también es
        # historia, y es lo que permite auditar el filtro más adelante.
        "guardar": puntuados + descartados,
        "significativos": significativos,
        # Los cuatro números que cuentan la vuelta, y cada uno significa UNA cosa:
        #   recibidos = repetidos + nuevos
        #   nuevos    = descartados + los que pasan
        "recibidos": len(normalizados),
        "repetidos": len(repetidos),          # ya los teníamos: no son nuevos, no se tiran
        "nuevos": len(nuevos),
        "descartados": len(descartados),      # SOLO los que tumbó el filtro
        "por_motivo": por_motivo,
    }
