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
    if evento.get("etapa") not in (ev.SIGNIFICATIVO, ev.ALERTADO):
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


def a_investigar(eventos: list, gastadas_hoy: int = 0,
                 tope: int = None) -> tuple:
    """Cuáles se investigan en esta vuelta, y por qué se queda fuera el resto.

    El tope se aplica DESPUÉS de la puerta y por orden de relevancia: si un día entran
    treinta eventos importantes, se investigan los veinte que más te tocan y se dice que
    quedan diez sin investigar. Cortar por orden de llegada dejaría fuera al más grave
    por haber llegado el último.
    """
    tope = TOPE_DIARIO if tope is None else tope
    quedan = max(0, tope - max(0, gastadas_hoy))
    elegibles, descartados = [], {}
    for e in eventos or []:
        motivo = motivo_para_no_investigar(e)
        if motivo:
            descartados[motivo] = descartados.get(motivo, 0) + 1
        else:
            elegibles.append(e)
    elegibles.sort(key=lambda e: (-(e.get("relevancia") or 0),
                                  str(e.get("recibido_en") or "")))
    sin_presupuesto = max(0, len(elegibles) - quedan)
    if sin_presupuesto:
        descartados["sin_presupuesto"] = sin_presupuesto
    return elegibles[:quedan], descartados


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
    """Deja la lectura sobre el evento. Devuelve un objeto NUEVO, como `ev.avanzar`.

    UN DOCUMENTO SIN CONTENIDO NO PRODUCE RESUMEN

    Si el modelo dijo `sin_informacion`, `resumen` se queda a None y la pantalla sigue
    enseñando el titular con su «esto no lo ha interpretado nadie». Se marca que ya se
    miró —para no volver a pagar por ello— pero no se rellena el hueco.

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
    return nuevo
