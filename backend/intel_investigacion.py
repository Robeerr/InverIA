"""La fase de investigación: leer el documento y decir qué cambia. Sin red, sin base de datos.

QUÉ AÑADE, Y QUÉ NO

Hasta ahora un evento es un titular: «8-K · Hecho relevante — NVDA». Eso te dice que ha
pasado algo, no QUÉ ha pasado. Para saberlo hay que leer el documento, y eso es lo que
esta fase hace: descarga el registro, se lo da al modelo y guarda su lectura.

Lo que NO hace es decidir por ti. La salida es «qué dice» y «qué cambiaría si es cierto»,
no «compra» ni «vende». Un sistema que lee un 8-K y recomienda operar está haciendo dos
saltos —entender e invertir— y solo el primero se puede comprobar.

LA PUERTA ES EL PRESUPUESTO, Y NO ES NEGOCIABLE

Este proyecto ya se gastó 3,65 € en un día por dejar suelto un bucle con IA. Así que la
investigación NO se aplica a todo lo que entra: solo a lo que ya merecía interrumpirte.

Esa decisión ya está tomada y calibrada — es el `nivel_alerta` del scoring. Un Form 4 de
consolidación automática sale ATENCIÓN y no se investiga; un 8-K de una empresa que
llevas comprada sale IMPORTANTE y sí. La puerta no es un umbral nuevo: es el que ya
existe, reutilizado.

Con los datos reales medidos —13 valores en cartera, un 8-K por empresa y mes— eso son
del orden de UNA investigación al día. Y encima hay un tope diario duro, porque una
estimación no es un límite.

TRES REGLAS DE HONESTIDAD, Y LA MÁS IMPORTANTE ES LA PRIMERA

  1. PODER DECIR QUE NO SE SABE. Si el documento no permite concluir nada, la respuesta
     es `sin_informacion` y el evento se queda SIN resumen. Un resumen inventado es peor
     que ninguno: el titular al menos era verdad.

  2. LO QUE SE AFIRMA SALE DEL DOCUMENTO. El prompt lo exige y la validación rechaza la
     respuesta que se contradiga —decir que no hay información y a la vez dar veredicto—.
     No se puede comprobar mecánicamente que no invente; lo que sí se puede es no
     premiarlo y dejar el enlace al original siempre a la vista.

  3. LA INCERTIDUMBRE VIAJA CON EL DATO. `confianza` sale del modelo y se enseña. Un
     resumen sin confianza se lee como un hecho.

POR QUÉ ES UN MÓDULO PURO

Igual que `intel_pipeline`: aquí no hay red ni Mongo. Recibe un evento y un texto, y
devuelve qué preguntar y cómo interpretar la respuesta. Eso permite probar la puerta, el
prompt y la validación sin gastar un céntimo ni una llamada.
"""
import os
import re
from typing import Optional

import intel_eventos as ev

# ── La puerta ────────────────────────────────────────────────────────────────

#: Tope diario duro. La estimación son ~1 investigación al día; esto es el freno por si
#: la estimación se equivoca —una temporada de resultados, un día raro de mercado— y no
#: un objetivo a alcanzar. Que sea un número y no un cálculo es a propósito: un límite
#: que se calcula solo puede crecer solo.
TOPE_DIARIO = int(os.environ.get("INTEL_INVESTIGACION_TOPE", 20))

#: Cuánto texto del documento se le manda al modelo. Un 8-K típico son unos pocos miles
#: de caracteres; el tope existe para el caso raro del anexo de 200 páginas, que costaría
#: una fortuna en tokens para decir lo mismo que sus dos primeras páginas.
MAX_CARACTERES = int(os.environ.get("INTEL_INVESTIGACION_MAX_CHARS", 12000))

#: Modelo. La clave enruta por `ai_analysis.MODEL_MAP`, que ya prueba la key GRATIS de
#: Gemini primero y solo cae a la de pago si esa se agota.
MODELO = os.environ.get("INTEL_INVESTIGACION_MODELO", "gemini-2.5-flash")

SIN_URL, YA_INVESTIGADO, NO_INTERRUMPE, ETAPA = (
    "sin_url", "ya_investigado", "no_interrumpe", "etapa_no_valida")


def motivo_para_no_investigar(evento: dict) -> Optional[str]:
    """Por qué este evento NO se investiga, o None si sí.

    Devuelve el motivo en vez de un booleano porque el diagnóstico tiene que poder decir
    «de 42 eventos, 41 no se investigaron porque no interrumpían» — que es la diferencia
    entre una puerta que funciona y una que está rota.
    """
    if not isinstance(evento, dict):
        return ETAPA
    # SOLO desde significativo. `investigado` ya pasó por aquí, y `alertado` también:
    # los dos entran por `YA_INVESTIGADO` más abajo si hiciera falta, pero la etapa por
    # sí sola ya los excluye — y eso hace la puerta idempotente por construcción.
    if evento.get("etapa") != ev.SIGNIFICATIVO:
        return ETAPA
    # Ya tiene lectura. Volver a pagar por lo mismo es la forma más tonta de gastar.
    if (evento.get("resumen") or "").strip() or evento.get("investigado_en"):
        return YA_INVESTIGADO
    # LA PUERTA: solo lo que ya merecía interrumpirte. No es un umbral nuevo, es el del
    # scoring, que ya está calibrado y probado.
    if evento.get("nivel_alerta") not in ev.INTERRUMPEN:
        return NO_INTERRUMPE
    # Sin enlace no hay documento que leer, y sin documento la única fuente sería lo que
    # el modelo recuerde de su entrenamiento. Eso no es investigar: es preguntarle a un
    # modelo si le suena la empresa.
    if not (evento.get("url") or "").strip():
        return SIN_URL
    return None


def merece_investigacion(evento: dict) -> bool:
    return motivo_para_no_investigar(evento) is None


#: Orden de los niveles. Se declara aquí y no se deduce de `ev.NIVELES` porque el orden
#: de prioridad es una DECISIÓN, y dejarla implícita en el orden de una tupla la haría
#: cambiar sin querer el día que alguien añada un nivel en medio.
_PESO_NIVEL = {ev.CRITICAL: 3, ev.IMPORTANT: 2, ev.WATCH: 1, ev.INFO: 0}


def prioridad(evento: dict) -> tuple:
    """La clave de orden del presupuesto. Menor es antes.

    LOS CUATRO CRITERIOS, EN ORDEN Y CON SU MOTIVO

      1. NIVEL. Un crítico antes que un importante, siempre. Es lo que el sistema ya
         decidió sobre cuánto urge, y el presupuesto no puede contradecirlo.
      2. RELEVANCIA. A igual nivel, lo que más te toca.
      3. CARTERA antes que seguimiento. A igual nota, donde hay dinero dentro: perderse
         algo de una posición abierta cuesta más que perdérselo de una que solo miras.
      4. LO MÁS RECIENTE. El desempate final. Un documento de hace diez minutos puede
         cambiar una decisión de hoy; uno de hace tres días ya la ha cambiado o no.

    Se devuelve una tupla en vez de un número: un número obligaría a inventar pesos y a
    que dos criterios pudieran compensarse entre sí, y no deben — ningún grado de
    relevancia convierte un WATCH en más urgente que un CRITICAL.
    """
    evento = evento or {}
    return (
        -_PESO_NIVEL.get(evento.get("nivel_alerta"), -1),
        -(evento.get("relevancia") or 0),
        0 if evento.get("afecta_cartera") else 1,
        # Descendente por fecha: se invierte comparando al revés en el `sorted`, así que
        # aquí se guarda la cadena y se marca el sentido con el signo del resto.
        _al_reves(str(evento.get("recibido_en") or "")),
    )


class _al_reves(str):
    """Una cadena que ordena al revés. Para que «más reciente primero» quepa en la misma
    tupla que los demás criterios sin partir el `sorted` en dos pasadas."""

    def __lt__(self, otra):
        return str.__gt__(self, otra)

    def __gt__(self, otra):
        return str.__lt__(self, otra)


def a_investigar(eventos: list, gastadas_hoy: int = 0, tope: int = None) -> dict:
    """Reparte el presupuesto del día. Devuelve elegidos, PENDIENTES y motivos.

    LOS QUE NO CABEN NO SE PIERDEN NI SE DESCARTAN

    Salen en `pendientes` y se quedan en `significativo`, que es literalmente lo que son:
    eventos que merecen investigarse y todavía no se han investigado. La vuelta siguiente
    —o el día siguiente— los vuelve a coger, y como la puerta comprueba `investigado_en`,
    no se investigan dos veces.

    Marcarlos descartados habría sido el fallo grave: `descartado` es terminal, así que un
    evento importante que no cupo en el presupuesto de un martes no se miraría jamás.
    """
    tope = TOPE_DIARIO if tope is None else tope
    quedan = max(0, tope - max(0, gastadas_hoy))
    elegibles, motivos = [], {}
    for e in eventos or []:
        motivo = motivo_para_no_investigar(e)
        if motivo:
            motivos[motivo] = motivos.get(motivo, 0) + 1
        else:
            elegibles.append(e)
    elegibles.sort(key=prioridad)
    elegidos, pendientes = elegibles[:quedan], elegibles[quedan:]
    if pendientes:
        # Se cuenta aparte de los motivos de exclusión: no es una razón para NO
        # investigar, es un «todavía no».
        motivos["sin_presupuesto"] = len(pendientes)
    return {"elegidos": elegidos, "pendientes": pendientes, "motivos": motivos,
            "elegibles": len(elegibles), "presupuesto_restante": quedan}


# ── Los cinco estados que hay que poder distinguir ───────────────────────────

DESCARTADO_POR_FILTRO = "descartado_por_filtro"
PENDIENTE = "pendiente_de_investigacion"
NO_INVESTIGABLE = "no_investigable"
SIN_INFORMACION = "investigado_sin_informacion"
CON_INFORMACION = "investigado_con_informacion"


def estado_de_investigacion(evento: dict) -> str:
    """En cuál de los cinco estados está este evento.

    Existen como concepto separado de la etapa porque la etapa sola no los distingue:
    `investigado` cubre tanto «se leyó y no decía nada» como «se leyó y esto es lo que
    dice», y esas dos cosas piden pantallas distintas. Y `significativo` cubre «pendiente»
    y «no investigable», que piden explicaciones distintas.

    Sin esta distinción, un radar en silencio no se puede leer: no se sabría si es que no
    hay nada, si es que falta presupuesto o si es que nada de lo que entró era legible.
    """
    if not isinstance(evento, dict):
        return NO_INVESTIGABLE
    if evento.get("etapa") == ev.DESCARTADO:
        return DESCARTADO_POR_FILTRO
    if evento.get("etapa") == ev.INVESTIGADO:
        investigacion = evento.get("investigacion") or {}
        return SIN_INFORMACION if investigacion.get("sin_informacion") else CON_INFORMACION
    return PENDIENTE if merece_investigacion(evento) else NO_INVESTIGABLE


# ── El texto del documento ───────────────────────────────────────────────────

_ETIQUETAS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
_ESPACIOS = re.compile(r"[ \t\r\f\v]+")
_SALTOS = re.compile(r"\n{3,}")

_ENTIDADES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
              "&quot;": '"', "&#39;": "'", "&rsquo;": "'", "&ldquo;": '"',
              "&rdquo;": '"', "&mdash;": "—", "&ndash;": "–"}


def texto_del_documento(html: str, maximo: int = None) -> str:
    """Del HTML de la SEC al texto plano. Sin dependencias: los filings son HTML simple.

    Se recorta por el principio y no por el final: un 8-K pone lo importante en el
    Item 8.01 de la primera página, y los anexos van detrás. Si hay que cortar, se corta
    lo de atrás.
    """
    maximo = MAX_CARACTERES if maximo is None else maximo
    texto = _ETIQUETAS.sub(" ", html or "")
    for entidad, caracter in _ENTIDADES.items():
        texto = texto.replace(entidad, caracter)
    texto = _ESPACIOS.sub(" ", texto)
    texto = _SALTOS.sub("\n\n", texto)
    texto = "\n".join(l.strip() for l in texto.splitlines())
    texto = _SALTOS.sub("\n\n", texto).strip()
    return texto[:maximo]


# ── La petición ──────────────────────────────────────────────────────────────

SISTEMA = """Eres un analista que lee documentos registrados ante la SEC y explica qué \
dicen. Escribes en español, para un inversor particular que ya tiene o sigue esa acción.

TU ÚNICA FUENTE ES EL DOCUMENTO QUE TE PASAN.

No uses lo que recuerdes de la empresa. No completes con contexto de mercado. No estimes \
el impacto en el precio ni recomiendes comprar ni vender: eso no está en el documento y \
no es lo que se te pregunta.

SI EL DOCUMENTO NO PERMITE CONCLUIR NADA, DILO.

Muchos registros son trámites sin contenido: una nota de que se publicará un resultado, \
un cambio administrativo, un anexo. En ese caso pon `sin_informacion` a true y deja el \
resto vacío. Es la respuesta correcta y la esperada la mayoría de las veces. Un resumen \
inventado para no dejarlo vacío es el peor resultado posible.

Devuelve SOLO un objeto JSON con esta forma exacta:

{
  "sin_informacion": true|false,
  "resumen": "Dos o tres frases con lo que dice el documento. Vacío si sin_informacion.",
  "que_cambia": "Qué cambiaría para quien tiene la acción, SI lo que dice es cierto. \
Vacío si el documento no permite decirlo.",
  "hechos": ["cada cifra o hecho concreto que aparezca EN EL DOCUMENTO, textual"],
  "confianza": 0-100
}

`confianza` es cuánto de claro está el documento, no cuánto te convence lo que dice."""


def construir_peticion(evento: dict, documento: str) -> dict:
    """El par (sistema, usuario) que se le manda al modelo. Puro: no llama a nadie.

    Se le da el titular y el símbolo además del texto porque un 8-K no siempre dice de
    qué empresa es en el cuerpo, y sin eso el modelo tendría que adivinarlo.
    """
    evento = evento or {}
    detalle = evento.get("crudo") or {}
    usuario = (
        f"Valor: {evento.get('symbol') or '—'}\n"
        f"Tipo de registro: {detalle.get('formulario') or detalle.get('suceso') or '—'}\n"
        f"Fecha de registro: {detalle.get('fecha_registro') or evento.get('publicado_en') or '—'}\n"
        f"Titular: {evento.get('titulo') or '—'}\n\n"
        f"DOCUMENTO:\n{(documento or '').strip() or '(vacío)'}"
    )
    return {"sistema": SISTEMA, "usuario": usuario, "modelo": MODELO}


# ── La respuesta ─────────────────────────────────────────────────────────────

SIN_RESPUESTA, CONTRADICTORIA, VACIA = "sin_respuesta", "contradictoria", "vacia"

MAX_RESUMEN = 600
MAX_HECHOS = 8


def validar(bruto) -> dict:
    """Comprueba la respuesta del modelo. Devuelve `{ok, motivo, investigacion}`.

    LO QUE SE PUEDE COMPROBAR Y LO QUE NO

    No se puede verificar mecánicamente que el modelo no se haya inventado un dato: eso
    exigiría entender el documento, que es justo lo que le hemos encargado a él. Lo que sí
    se puede es rechazar lo INCOHERENTE, y no dejar pasar nada que se contradiga.

    La contradicción que importa: decir que no hay información y a la vez dar un resumen.
    Es el patrón típico de un modelo que rellena por no dejar el hueco vacío, y aceptarla
    convertiría la regla de «poder decir que no sé» en decorativa.
    """
    if not isinstance(bruto, dict):
        return {"ok": False, "motivo": SIN_RESPUESTA, "investigacion": None}

    sin_info = bool(bruto.get("sin_informacion"))
    resumen = str(bruto.get("resumen") or "").strip()
    que_cambia = str(bruto.get("que_cambia") or "").strip()

    if sin_info and (resumen or que_cambia):
        return {"ok": False, "motivo": CONTRADICTORIA, "investigacion": None}
    if not sin_info and not resumen:
        # Ni información ni la declaración de que no la hay. No es una respuesta.
        return {"ok": False, "motivo": VACIA, "investigacion": None}

    hechos = [str(h).strip()[:200] for h in (bruto.get("hechos") or [])
              if str(h or "").strip()][:MAX_HECHOS]
    try:
        confianza = max(0, min(100, int(float(bruto.get("confianza")))))
    except (TypeError, ValueError):
        # Sin confianza declarada no se inventa una alta: se asume la mínima, porque la
        # duda tiene que costar algo.
        confianza = 0
    return {"ok": True, "motivo": None, "investigacion": {
        "sin_informacion": sin_info,
        "resumen": resumen[:MAX_RESUMEN] or None,
        "que_cambia": que_cambia[:MAX_RESUMEN] or None,
        "hechos": hechos,
        "confianza": confianza,
        "modelo": MODELO,
    }}


def aplicar(evento: dict, investigacion: dict, cuando: str = None) -> dict:
    """Deja la lectura sobre el evento y lo avanza a `investigado`. Objeto NUEVO.

    UN DOCUMENTO SIN CONTENIDO NO PRODUCE RESUMEN, PERO SÍ ES UNA INVESTIGACIÓN

    Si el modelo dijo `sin_informacion`, `resumen` se queda a None y la pantalla sigue
    enseñando el titular con su «esto no lo ha interpretado nadie». Pero la etapa SÍ
    avanza: la IA leyó el documento y produjo un resultado válido, que es exactamente lo
    que significa `investigado`. Que el resultado sea «no dice nada» no lo hace menos
    resultado — y dejarlo en `significativo` haría que se volviera a pagar por él en cada
    vuelta.

    Es la regla número uno de este módulo, y es la única forma de que un resumen, cuando
    exista, signifique algo.
    """
    if not isinstance(evento, dict) or not isinstance(investigacion, dict):
        return evento
    nuevo = dict(evento)
    nuevo["investigado_en"] = cuando or ev._ahora()
    nuevo["investigacion"] = investigacion
    if not investigacion.get("sin_informacion"):
        nuevo["resumen"] = investigacion.get("resumen")
    # La lista blanca decide: si el evento no estaba en `significativo`, no se mueve.
    return ev.avanzar(nuevo, ev.INVESTIGADO, cuando=cuando)
