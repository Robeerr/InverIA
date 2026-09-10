"""El evento de inteligencia y las ocho etapas por las que pasa.

QUÉ ES UN EVENTO AQUÍ

Algo que ha ocurrido en una fuente y que PODRÍA importarte. Todavía no es una señal,
no es una recomendación y no es un hecho verificado: es materia prima con trazabilidad.

Por eso cada evento guarda de dónde salió y cuándo se recogió, y esos campos no son
opcionales. Una afirmación sin origen no se puede auditar después, y todo el valor de
este sistema está en poder preguntarle dentro de tres meses «¿por qué dijiste eso?».

LAS OCHO ETAPAS, Y POR QUÉ SON UN CAMPO Y NO OCHO COLECCIONES

    recibido → normalizado → deduplicado → filtrado ─┬→ descartado    (fin)
                                                     └→ significativo → alertado

Un evento no cambia de sitio al avanzar: cambia de `etapa`. Así el historial completo
vive en un solo documento y se puede responder «¿qué pasó con esto?» sin reconstruir
nada. Y la pantalla dibuja exactamente ese campo: una partícula que muere en
`descartado` se apaga a mitad de camino; una que llega a `significativo` entra al
centro del radar. La animación NO es decorativa — es este enum.

DOS ETAPAS EXISTEN Y NO SE ALCANZAN TODAVÍA

`investigado` y `agrupado` están declaradas pero ninguna transición lleva a ellas: la
investigación con IA y el agrupamiento de un mismo suceso en varias fuentes son fases
posteriores. Se declaran ahora para que el hueco sea visible y para que el día que se
implementen no haya que migrar los documentos ya escritos. Un test lo afirma, de modo
que su ausencia es una decisión y no un olvido.

LO QUE ESTE MÓDULO NO HACE

No llama a nadie, no toca Mongo y no sabe qué es SEC. Recibe datos y devuelve datos.
Es la misma separación que hace que `patrones_registro` tenga sus tests sin una sola
conexión: lo que se puede probar sin red, se prueba sin red.
"""
from datetime import datetime, timezone
from typing import Optional

# ── Las etapas ───────────────────────────────────────────────────────────────
RECIBIDO = "recibido"
NORMALIZADO = "normalizado"
DEDUPLICADO = "deduplicado"
FILTRADO = "filtrado"
INVESTIGADO = "investigado"      # fase posterior: aún inalcanzable
AGRUPADO = "agrupado"            # fase posterior: aún inalcanzable
SIGNIFICATIVO = "significativo"
ALERTADO = "alertado"
DESCARTADO = "descartado"

ETAPAS = (RECIBIDO, NORMALIZADO, DEDUPLICADO, FILTRADO, INVESTIGADO,
          AGRUPADO, SIGNIFICATIVO, ALERTADO, DESCARTADO)

# Transiciones PERMITIDAS. Es una lista blanca, no una negra: un estado nuevo que
# nadie haya conectado a propósito no se alcanza por descuido.
#
# `descartado` y `alertado` son finales. Que descartado sea terminal es lo que impide
# el fallo más caro de un sistema así: que un evento ya rechazado vuelva a entrar por
# otro camino y acabe generando la señal que su filtro había impedido.
#
# LA INVESTIGACIÓN VA DESPUÉS DE LA SIGNIFICANCIA, Y ES UNA DESVIACIÓN DELIBERADA
#
# El orden declarado en la especificación era `filtrado → investigado → significativo`:
# investigar y luego decidir si importa. Se cambió por lo contrario, y el motivo es el
# dinero: investigar antes de saber si algo te toca obliga a leer TODO lo que pasa el
# filtro. Medido sobre una vuelta real, eso son 46 llamadas a un modelo en vez de 1.
#
# Las dos etapas siguen significando cosas DISTINTAS, que es lo que hace que la
# desviación no sea una fusión encubierta:
#
#   SIGNIFICATIVO  el scoring dice que te toca lo bastante como para gastar recursos
#                  en entenderlo. Es una decisión sobre TI y tu cartera.
#   INVESTIGADO    la IA ya ha leído la fuente y ha producido una lectura válida. Es un
#                  hecho sobre el DOCUMENTO, y ocurre o no ocurre.
#
# Un evento significativo que todavía no se ha investigado —porque el presupuesto del
# día se agotó— se queda en `significativo`, que es exactamente lo que significa:
# pendiente de investigación. No hay estado nuevo porque no hace falta uno.
_TRANSICIONES = {
    RECIBIDO: (NORMALIZADO, DESCARTADO),
    NORMALIZADO: (DEDUPLICADO, DESCARTADO),
    DEDUPLICADO: (FILTRADO, DESCARTADO),
    FILTRADO: (SIGNIFICATIVO, DESCARTADO),
    SIGNIFICATIVO: (INVESTIGADO, ALERTADO, DESCARTADO),
    # Investigado puede alertar directamente: ya se sabe qué dice el documento, que es
    # lo que faltaba para que la alerta valiera algo.
    INVESTIGADO: (ALERTADO, DESCARTADO),
    AGRUPADO: (SIGNIFICATIVO, DESCARTADO),
    ALERTADO: (),
    DESCARTADO: (),
}

# ── Niveles de alerta ────────────────────────────────────────────────────────
# Solo IMPORTANT y CRITICAL interrumpen visualmente. INFO y WATCH se guardan y se
# consultan; interrumpir por todo es la forma más rápida de que dejes de mirar.
INFO, WATCH, IMPORTANT, CRITICAL = "INFO", "WATCH", "IMPORTANT", "CRITICAL"
NIVELES = (INFO, WATCH, IMPORTANT, CRITICAL)
INTERRUMPEN = (IMPORTANT, CRITICAL)

# Umbrales de relevancia (0-100) para cada nivel. Son DECISIONES, no hechos: están
# aquí para poder discutirlas en un sitio en vez de repartidas por el código.
UMBRAL_WATCH, UMBRAL_IMPORTANT, UMBRAL_CRITICAL = 40, 65, 85

# ── Tipos de evento ──────────────────────────────────────────────────────────
# Se declaran todos los previstos aunque la fase 0.5 solo produzca INSIDER y
# CORPORATIVO: el tipo viaja a Mongo, y ampliar el enum después obligaría a migrar.
NOTICIA, SOCIAL, RESULTADOS = "NOTICIA", "SOCIAL", "RESULTADOS"
FUNDAMENTAL, TECNICO, INSIDER = "FUNDAMENTAL", "TECNICO", "INSIDER"
MACRO, CARTERA, CAMBIO_TESIS = "MACRO", "CARTERA", "CAMBIO_TESIS"
CORPORATIVO = "CORPORATIVO"
TIPOS = (NOTICIA, SOCIAL, RESULTADOS, FUNDAMENTAL, TECNICO, INSIDER,
         MACRO, CARTERA, CAMBIO_TESIS, CORPORATIVO)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def crear(fuente: str, externo_id: str, titulo: str, url: Optional[str] = None,
          symbol: Optional[str] = None, tipo: Optional[str] = None,
          tier: int = 4, publicado_en: Optional[str] = None,
          crudo: Optional[dict] = None, recibido_en: Optional[str] = None) -> Optional[dict]:
    """Un evento recién recibido, o None si le falta lo mínimo para existir.

    `id` se compone como `fuente:externo_id` y es la CLAVE de deduplicación. Que sea
    determinista es lo que hace el worker idempotente: reprocesar el mismo feed dos
    veces —un reinicio, un solape de ciclos— reescribe el mismo documento en vez de
    crear un segundo.

    Se rechaza sin fuente, sin id externo o sin título. Un evento sin origen no se
    puede auditar, y uno sin título no se puede enseñar: en los dos casos guardarlo
    solo ensuciaría la colección.
    """
    fuente = (fuente or "").strip().lower()
    externo_id = (externo_id or "").strip()
    titulo = (titulo or "").strip()
    if not fuente or not externo_id or not titulo:
        return None
    if tipo is not None and tipo not in TIPOS:
        return None
    return {
        "id": f"{fuente}:{externo_id}",
        "fuente": fuente,
        "externo_id": externo_id,
        "tier": int(tier),
        "symbol": (symbol or "").upper() or None,
        "tipo": tipo,
        "titulo": titulo,
        # `resumen` nace en None y en la fase 0.5 se queda así: no hay LLM, así que no
        # hay prosa generada. El campo existe para la fase siguiente; la pantalla
        # enseña el título y nada más. Un resumen inventado sería peor que ninguno.
        "resumen": None,
        "url": url or None,
        "publicado_en": publicado_en,
        "recibido_en": recibido_en or _ahora(),
        "etapa": RECIBIDO,
        "historial": [{"etapa": RECIBIDO, "cuando": recibido_en or _ahora()}],
        "relevancia": None,
        "nivel_alerta": None,
        "motivo_descarte": None,
        "afecta_cartera": False,
        "afecta_watchlist": False,
        "afecta_tesis": False,
        # Lo que dijo la fuente, tal cual. Ocupa poco y es lo único que permite
        # rehacer el análisis el día que cambien las reglas sin volver a pedir nada.
        "crudo": crudo or {},
    }


def puede_avanzar(desde: str, hacia: str) -> bool:
    """¿Es válida esta transición? Lista blanca; lo no declarado no pasa."""
    return hacia in _TRANSICIONES.get(desde, ())


def avanzar(evento: dict, etapa: str, motivo: Optional[str] = None,
            cuando: Optional[str] = None) -> dict:
    """Mueve el evento de etapa y lo deja anotado. Devuelve un objeto NUEVO.

    No muta a propósito: el que llama suele tener el documento que acaba de leer de
    Mongo, y decide él si escribe. Mutarlo dejaría el objeto en memoria adelantado
    respecto de la base de datos ante cualquier fallo de escritura.

    Una transición inválida devuelve el evento SIN TOCAR en vez de lanzar. El worker
    procesa lotes: una excepción aquí tumbaría el ciclo entero por un evento raro,
    y el resto del lote no tiene la culpa.
    """
    if not isinstance(evento, dict):
        return evento
    actual = evento.get("etapa")
    if not puede_avanzar(actual, etapa):
        return evento
    nuevo = dict(evento)
    nuevo["etapa"] = etapa
    paso = {"etapa": etapa, "cuando": cuando or _ahora()}
    if motivo:
        paso["motivo"] = motivo
        if etapa == DESCARTADO:
            nuevo["motivo_descarte"] = motivo
    nuevo["historial"] = list(evento.get("historial") or []) + [paso]
    return nuevo


def nivel_de(relevancia: Optional[float]) -> Optional[str]:
    """El nivel de alerta que corresponde a una relevancia, o None si no hay nota.

    None y 0 son cosas distintas: None es «no se ha evaluado» y 0 es «se evaluó y no
    importa». Devolver INFO para un evento sin evaluar lo colaría en la lista de
    consultables como si alguien lo hubiera mirado.
    """
    if relevancia is None:
        return None
    if relevancia >= UMBRAL_CRITICAL:
        return CRITICAL
    if relevancia >= UMBRAL_IMPORTANT:
        return IMPORTANT
    if relevancia >= UMBRAL_WATCH:
        return WATCH
    return INFO


def interrumpe(evento: dict) -> bool:
    """¿Este evento merece robar la atención del usuario?

    Solo si YA está en `significativo`, `investigado` o `alertado` Y su nivel interrumpe.
    Las dos condiciones: un evento con relevancia alta que el filtro descartó por otra
    razón —un duplicado, una fuente caída— no puede colarse por la puerta de atrás.

    `investigado` está en la lista porque investigar no rebaja nada: un 8-K que merecía
    interrumpirte lo sigue mereciendo después de leerlo, y con más motivo, porque ahora
    se sabe qué dice.
    """
    if not isinstance(evento, dict):
        return False
    if evento.get("etapa") not in (SIGNIFICATIVO, INVESTIGADO, ALERTADO):
        return False
    return evento.get("nivel_alerta") in INTERRUMPEN


# Qué campos de `crudo` puede ver el navegador. Lista BLANCA, no negra: `crudo` guarda
# lo que dijo la fuente tal cual, y una fuente futura puede meter ahí un documento entero
# o un identificador que no queremos publicar. Con lista negra, cada fuente nueva sería
# una fuga potencial que nadie recordaría revisar.
#
# Son todos escalares pequeños y son los que la pantalla necesita para explicar un evento
# de resultados: cuándo era, cuándo es, y qué cifras hay.
_DETALLE_PUBLICO = ("suceso", "trimestre", "fecha", "fecha_anterior", "adelanta",
                    "momento", "eps_estimado", "eps_real", "diferencia_eps",
                    "ingresos_estimados", "ingresos_reales", "formulario",
                    # Lo que distingue un registro de otro cuando una empresa presenta
                    # catorce Form 4 el mismo día: sin esto, catorce filas idénticas en
                    # pantalla y ninguna forma de saber que son documentos distintos.
                    "accession", "fecha_registro")


def para_api(evento: dict) -> dict:
    """El evento tal como sale por la API: sin `crudo` completo ni historial.

    `crudo` puede ser un filing entero y no le sirve de nada al navegador. Sale solo un
    `detalle` con los campos de la lista blanca, que es lo que la pantalla necesita para
    contar qué pasó —«los resultados se movieron del 28 al 4»— sin publicar el resto.

    El historial se resume en su último paso. Los dos siguen enteros en Mongo: lo que se
    ahorra es ancho de banda, no trazabilidad.
    """
    if not isinstance(evento, dict):
        return {}
    fuera = {"crudo", "historial", "_id"}
    salida = {k: v for k, v in evento.items() if k not in fuera}
    crudo = evento.get("crudo") or {}
    detalle = {k: crudo[k] for k in _DETALLE_PUBLICO if crudo.get(k) is not None}
    salida["detalle"] = detalle or None
    hist = evento.get("historial") or []
    salida["ultimo_paso"] = hist[-1] if hist else None
    salida["pasos"] = len(hist)
    return salida
