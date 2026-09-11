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
import html
import os
import re
import time
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
        return CON_INFORMACION if investigacion.get("hay_informacion") else SIN_INFORMACION
    return PENDIENTE if merece_investigacion(evento) else NO_INVESTIGABLE


# ── El texto del documento ───────────────────────────────────────────────────

_ETIQUETAS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
#: `\xa0` es el espacio duro al que se decodifica `&#160;`. Sin meterlo aquí, el
#: colapsado de espacios lo respeta y el documento sigue lleno de huecos sueltos entre
#: palabras — más limpio que `&#160;`, pero igual de inútil para el modelo.
_ESPACIOS = re.compile(r"[ \t\r\f\v\xa0\u2007\u202f]+")
_SALTOS = re.compile(r"\n{3,}")


def texto_del_documento(bruto: str, maximo: int = None) -> str:
    """Del HTML de la SEC al texto plano.

    LAS ENTIDADES SE DECODIFICAN TODAS, Y ESO NO ES COSMÉTICO

    La primera versión traía una tabla escrita a mano con diez entidades. Los filings de
    la SEC usan las NUMÉRICAS —`&#160;`, `&#8217;`, `&#167;`— y esas no estaban, así que
    al modelo le llegaba un texto plagado de `&#160;` entre palabra y palabra.

    Se vio en el documento real de SEDG: cientos de `&#160;` ocupando tokens, ensuciando
    las frases y compitiendo con el contenido por el espacio del recorte. `html.unescape`
    es de la biblioteca estándar y las cubre todas, incluidas las que aún no existen en
    ningún filing que hayamos visto.

    EL ORDEN IMPORTA: primero se quitan las etiquetas y DESPUÉS se decodifica. Al revés,
    un `&lt;script&gt;` escrito en el texto se convertiría en una etiqueta de verdad.

    Se recorta por el final: un 8-K pone lo suyo delante y los anexos detrás.
    """
    maximo = MAX_CARACTERES if maximo is None else maximo
    texto = _ETIQUETAS.sub(" ", bruto or "")
    texto = html.unescape(texto)
    texto = _ESPACIOS.sub(" ", texto)
    texto = _SALTOS.sub("\n\n", texto)
    texto = "\n".join(l.strip() for l in texto.splitlines())
    texto = _SALTOS.sub("\n\n", texto).strip()
    return texto[:maximo]


# ── Descarga del documento primario ──────────────────────────────────────────

TIMEOUT_DESCARGA = int(os.environ.get("INTEL_INVESTIGACION_TIMEOUT", 20))

#: Cuánto se descarga como mucho. Un 8-K son unos pocos kB; el tope frena el caso raro
#: del anexo enorme, que costaría memoria para acabar recortado a `MAX_CARACTERES`.
MAX_BYTES = int(os.environ.get("INTEL_INVESTIGACION_MAX_BYTES", 2_000_000))

#: Cuánto del texto enviado se guarda como evidencia. No es el documento entero: es lo
#: justo para poder mirar QUÉ leyó el modelo y juzgar su lectura.
#:
#: Sin esto, la auditoría dice «3.989 caracteres» y no cuáles — y un «no permitía concluir
#: nada» es indistinguible de un modelo perezoso o de haberle mandado la portada de un 8-K
#: cuyo contenido está en el anexo.
MUESTRA_TEXTO = int(os.environ.get("INTEL_INVESTIGACION_MUESTRA", 2000))


async def descargar_documento(url: str) -> dict:
    """Baja el documento y devuelve TODO lo que hace falta para auditarlo.

    QUÉ SE DEVUELVE Y POR QUÉ

    No solo el texto: también el código HTTP, los bytes recibidos y el error literal si
    lo hubo. Sin eso, un evento que se queda sin investigar es indistinguible de uno que
    la SEC no sirvió — y son problemas distintos, uno se reintenta y el otro se mira.

    NO LANZA. Devuelve `ok: False` con el motivo, porque quien llama tiene que poder
    seguir con los demás eventos: que un documento no baje no puede tumbar la vuelta.
    """
    import intel_sec as sec
    if not (url or "").strip():
        return {"ok": False, "error": "el evento no tiene URL", "http": None,
                "bytes": 0, "ms": 0}
    if not sec.configurado():
        # Misma regla que el connector: la SEC exige identificarse, y bajar un documento
        # sin `User-Agent` sería saltarse su política por la puerta de atrás.
        return {"ok": False, "error": "SEC_USER_AGENT no configurado", "http": None,
                "bytes": 0, "ms": 0}
    import httpx
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DESCARGA,
                                     headers=sec._cabeceras()) as c:
            r = await c.get(url)
            ms = round((time.perf_counter() - t0) * 1000)
            contenido = r.content or b""
            if r.status_code != 200:
                return {"ok": False, "http": r.status_code, "bytes": len(contenido),
                        "ms": ms, "error": f"la SEC respondió {r.status_code}"}
            return {"ok": True, "http": 200, "bytes": len(contenido), "ms": ms,
                    "error": None,
                    "html": contenido[:MAX_BYTES].decode("utf-8", errors="replace")}
    except Exception as e:
        return {"ok": False, "http": None, "bytes": 0,
                "ms": round((time.perf_counter() - t0) * 1000),
                "error": f"{type(e).__name__}: {str(e)[:200]}"}


def parece_el_filing(texto: str, evento: dict) -> dict:
    """¿Lo descargado es de verdad el documento de ESTE evento?

    POR QUÉ NO BASTA CON QUE LA URL RESPONDA 200

    EDGAR sirve muchas cosas desde rutas parecidas: un índice, una portada, una página
    de error con código 200. Si se le manda al modelo un índice en vez del 8-K, contestará
    algo —los modelos casi siempre contestan algo— y ese algo parecerá una lectura del
    documento sin serlo. Es el fallo más difícil de detectar de toda la fase, porque no
    produce ningún error.

    Así que se buscan señales que DEBEN estar: el tipo de formulario y el número de
    registro. No es una prueba criptográfica, es un cotejo — y se devuelven las señales
    encontradas para poder mirarlas, en vez de un sí o un no que haya que creerse.
    """
    texto = texto or ""
    crudo = (evento or {}).get("crudo") or {}
    plano = re.sub(r"[^A-Za-z0-9]", "", texto).upper()
    forma = str(crudo.get("formulario") or crudo.get("suceso") or "").upper()
    accession = str(crudo.get("accession") or "")
    señales = {
        "menciona_el_formulario": bool(forma) and re.sub(r"[^A-Z0-9]", "", forma) in plano,
        "menciona_el_numero_de_registro": bool(accession) and accession in plano,
        "menciona_el_cik": bool(crudo.get("cik")) and str(crudo["cik"]).lstrip("0") in plano,
        "caracteres": len(texto),
    }
    # Con una sola señal basta: el número de registro no siempre aparece en el cuerpo del
    # documento, y el formulario a veces se escribe de formas raras. Exigir las tres
    # descartaría filings buenos, que es peor que colar uno dudoso — el resultado va
    # marcado y con su enlace.
    señales["ok"] = bool(señales["menciona_el_formulario"]
                         or señales["menciona_el_numero_de_registro"]
                         or señales["menciona_el_cik"])
    return señales


# ── La petición ──────────────────────────────────────────────────────────────

SISTEMA = """Eres un analista que lee documentos registrados ante la SEC y explica qué \
dicen. Escribes en español, para un inversor particular que ya tiene o sigue esa acción.

TU ÚNICA FUENTE ES EL DOCUMENTO QUE TE PASAN.

No uses lo que recuerdes de la empresa. No completes con contexto de mercado. No estimes \
el impacto en el precio, no recomiendes comprar ni vender y no des un veredicto \
operativo: nada de eso está en el documento y no es lo que se te pregunta.

LA PREGUNTA ES QUÉ HECHOS CONTIENE EL DOCUMENTO, NO SI SON IMPORTANTES.

`hay_informacion` es true si el documento afirma algo concreto y comprobable: una fecha, \
una cifra, una persona, una decisión, un acto convocado. Aunque su efecto sobre la \
inversión sea pequeño o nulo.

`hay_informacion` es false SOLO si no hay nada que leer: una portada sin cuerpo, un \
índice, una corrección administrativa, un duplicado, un documento vacío.

«Contiene información y su impacto parece bajo» es una conclusión correcta y frecuente. \
Dilo en `implicaciones`. Lo que no puedes hacer es inventar un hecho que no esté en el \
texto: un resumen inventado para no dejarlo vacío es el peor resultado posible.

Devuelve SOLO un objeto JSON con esta forma exacta:

{
  "hay_informacion": true|false,
  "resumen": "Dos o tres frases con lo que dice el documento. Vacío si no hay información.",
  "hechos": ["cada cifra o hecho concreto que aparezca EN EL DOCUMENTO, textual"],
  "implicaciones": ["qué cambiaría para quien tiene la acción SI lo que dice es cierto. Si no cambia nada relevante, dilo con esas palabras. Puede ir vacío: no inventes una implicación para rellenar."],
  "incertidumbres": ["qué NO dice el documento y haría falta saber"],
  "fuente": "el tipo de documento y su fecha, tal como aparecen en el texto",
  "confianza": 0-100
}

`incertidumbres` no es opcional cuando hay información: un documento que parece no dejar \
ninguna duda casi siempre es que no la has buscado.

`confianza` es cuánto de claro está el documento, no cuánto te convence lo que dice ni \
cuánto importa. Un documento nítido sobre algo menor tiene confianza alta."""


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
MAX_LISTA = 8
MAX_ITEM = 300


def _lista(valor) -> list:
    return [str(x).strip()[:MAX_ITEM] for x in (valor or [])
            if str(x or "").strip()][:MAX_LISTA]


def validar(bruto) -> dict:
    """Comprueba que la respuesta cumple el contrato. `{ok, motivo, investigacion}`.

    SI NO CUMPLE, LA INVESTIGACIÓN NO ES VÁLIDA

    Y no válida significa que el evento NO pasa a `investigado`: se queda pendiente y se
    puede reintentar. Marcarlo investigado con una respuesta rota sería peor que no haber
    llamado, porque además de no saber nada creeríamos que ya lo miramos.

    LO QUE SE PUEDE COMPROBAR Y LO QUE NO

    No se puede verificar mecánicamente que el modelo no se haya inventado un dato: eso
    exigiría entender el documento, que es lo que le hemos encargado a él. Lo que sí se
    puede es rechazar lo INCOHERENTE — decir que no hay información y a la vez dar un
    resumen es el patrón típico de un modelo que rellena por no dejar el hueco vacío, y
    aceptarlo convertiría la regla de «poder decir que no sé» en decorativa.
    """
    if not isinstance(bruto, dict):
        return {"ok": False, "motivo": SIN_RESPUESTA, "investigacion": None}
    if "hay_informacion" not in bruto:
        # El campo que decide todo lo demás. Sin él no hay contrato que cumplir.
        return {"ok": False, "motivo": SIN_RESPUESTA, "investigacion": None}

    hay = bool(bruto.get("hay_informacion"))
    resumen = str(bruto.get("resumen") or "").strip()
    hechos = _lista(bruto.get("hechos"))
    implicaciones = _lista(bruto.get("implicaciones"))
    incertidumbres = _lista(bruto.get("incertidumbres"))

    if not hay and (resumen or hechos or implicaciones):
        return {"ok": False, "motivo": CONTRADICTORIA, "investigacion": None}
    if hay and not resumen:
        # Dice que hay información y no la da. No es una respuesta.
        return {"ok": False, "motivo": VACIA, "investigacion": None}

    try:
        confianza = max(0, min(100, int(float(bruto.get("confianza")))))
    except (TypeError, ValueError):
        # Sin confianza declarada no se inventa una alta: la duda tiene que costar algo.
        confianza = 0
    return {"ok": True, "motivo": None, "investigacion": {
        "hay_informacion": hay,
        "resumen": resumen[:MAX_RESUMEN] or None,
        "hechos": hechos,
        "implicaciones": implicaciones,
        "incertidumbres": incertidumbres,
        "fuente": str(bruto.get("fuente") or "").strip()[:MAX_ITEM] or None,
        "confianza": confianza,
        "modelo": MODELO,
    }}


def aplicar(evento: dict, investigacion: dict, cuando: str = None) -> dict:
    """Deja la lectura sobre el evento y lo avanza a `investigado`. Objeto NUEVO.

    UN DOCUMENTO SIN CONTENIDO NO PRODUCE RESUMEN, PERO SÍ ES UNA INVESTIGACIÓN

    Si el modelo dijo que no hay información, `resumen` se queda a None y la pantalla
    sigue enseñando el titular con su «esto no lo ha interpretado nadie». Pero la etapa SÍ
    avanza: la IA leyó el documento y produjo un resultado válido, que es exactamente lo
    que significa `investigado`. Que el resultado sea «no dice nada» no lo hace menos
    resultado — y dejarlo en `significativo` haría que se volviera a pagar por él en cada
    vuelta.
    """
    if not isinstance(evento, dict) or not isinstance(investigacion, dict):
        return evento
    nuevo = dict(evento)
    nuevo["investigado_en"] = cuando or ev._ahora()
    nuevo["investigacion"] = investigacion
    if investigacion.get("hay_informacion"):
        nuevo["resumen"] = investigacion.get("resumen")
    # La lista blanca decide: si el evento no estaba en `significativo`, no se mueve.
    return ev.avanzar(nuevo, ev.INVESTIGADO, cuando=cuando)


# ── La investigación completa: UNA sola función ──────────────────────────────

async def investigar(evento: dict) -> dict:
    """Documento → texto → modelo → resultado validado. Con toda la auditoría.

    ES LA MISMA FUNCIÓN PARA EL BOTÓN Y PARA EL WORKER

    Dos caminos distintos —uno «manual» y otro «automático»— se separarían con el tiempo,
    y entonces validar el manual dejaría de decir nada sobre el automático. Aquí solo hay
    uno; lo que cambia es quién lo llama y con qué eventos.

    NO ESCRIBE NADA Y NO LANZA

    Devuelve qué pasó y qué habría que guardar. Persistir es cosa de quien tiene la base
    de datos. Y un fallo —de la SEC o del modelo— vuelve como `ok: False`, porque el
    evento NO puede quedar marcado como investigado si no se ha investigado.

    `llamada_al_modelo` dice si se llegó a gastar una llamada. Es lo que decide si el
    contador diario sube: un documento que no baja no consume cuota.
    """
    auditoria = {
        "symbol": (evento or {}).get("symbol"),
        "accession": ((evento or {}).get("crudo") or {}).get("accession"),
        "formulario": ((evento or {}).get("crudo") or {}).get("formulario"),
        "url": (evento or {}).get("url"),
        "http": None, "bytes_descargados": 0, "ms_descarga": 0,
        "caracteres_extraidos": 0, "caracteres_enviados": 0,
        "verificacion": None, "ms_modelo": 0, "error": None,
    }
    descarga = await descargar_documento((evento or {}).get("url"))
    auditoria.update(http=descarga.get("http"), bytes_descargados=descarga.get("bytes", 0),
                     ms_descarga=descarga.get("ms", 0))
    if not descarga.get("ok"):
        auditoria["error"] = descarga.get("error")
        return {"ok": False, "fase": "descarga", "llamada_al_modelo": False,
                "auditoria": auditoria, "investigacion": None}

    # Sin recortar todavía: primero se mide CUÁNTO texto tenía el documento, y luego se
    # manda solo lo que cabe. Recortar antes de contar haría que la auditoría dijera
    # siempre 12.000 caracteres y no se pudiera ver si un filing venía corto o vacío.
    texto = texto_del_documento(descarga.get("html"), maximo=MAX_BYTES)
    auditoria["caracteres_extraidos"] = len(texto)
    auditoria["verificacion"] = parece_el_filing(texto, evento)
    if not texto.strip():
        auditoria["error"] = "el documento no tenía texto extraíble"
        return {"ok": False, "fase": "extraccion", "llamada_al_modelo": False,
                "auditoria": auditoria, "investigacion": None}

    enviado = texto[:MAX_CARACTERES]
    auditoria["caracteres_enviados"] = len(enviado)
    # La evidencia. Se guarda con la investigación porque después ya no se puede
    # reconstruir: el evento pasa a `investigado` y no se vuelve a descargar.
    auditoria["muestra_del_texto"] = enviado[:MUESTRA_TEXTO]
    peticion = construir_peticion(evento, enviado)

    import ai_analysis
    t0 = time.perf_counter()
    try:
        bruto = await ai_analysis._run_model(
            peticion["modelo"], peticion["sistema"], peticion["usuario"], max_tokens=1200)
    except Exception as e:
        auditoria["ms_modelo"] = round((time.perf_counter() - t0) * 1000)
        auditoria["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        # La llamada no llegó a completarse, así que no cuenta contra el presupuesto: un
        # 429 o un corte de red no consumen tokens.
        return {"ok": False, "fase": "modelo", "llamada_al_modelo": False,
                "auditoria": auditoria, "investigacion": None}
    auditoria["ms_modelo"] = round((time.perf_counter() - t0) * 1000)

    r = validar(bruto)
    if not r["ok"]:
        auditoria["error"] = f"la respuesta no cumple el contrato: {r['motivo']}"
        # Sí cuenta: el modelo respondió, y eso ya se pagó. Que la respuesta no valga no
        # devuelve la cuota.
        return {"ok": False, "fase": "validacion", "llamada_al_modelo": True,
                "auditoria": auditoria, "investigacion": None, "respuesta_bruta": bruto}
    return {"ok": True, "fase": "completa", "llamada_al_modelo": True,
            "auditoria": auditoria, "investigacion": r["investigacion"]}


# ── El panorama: qué se investigaría, sin investigar nada ────────────────────

#: Los cinco estados, en el orden en que se leen: de lo que no llegó a lo que llegó del
#: todo. Se declara la tupla para que la pantalla no tenga que decidir el orden.
ESTADOS = (DESCARTADO_POR_FILTRO, NO_INVESTIGABLE, PENDIENTE,
           SIN_INFORMACION, CON_INFORMACION)

_NIVELES_ORDEN = (ev.CRITICAL, ev.IMPORTANT, ev.WATCH, ev.INFO)


def _por_nivel(eventos) -> dict:
    """Recuento por nivel, con todos los niveles presentes aunque valgan cero.

    Que un nivel con cero salga igualmente es lo que permite leer «no hay ningún
    CRÍTICO» en vez de tener que deducirlo de una ausencia.
    """
    conteo = {n: 0 for n in _NIVELES_ORDEN}
    conteo["sin_evaluar"] = 0
    for e in eventos or []:
        nivel = (e or {}).get("nivel_alerta")
        conteo[nivel if nivel in conteo else "sin_evaluar"] += 1
    return conteo


def panorama(eventos: list, gastadas_hoy: int = 0, tope: int = None) -> dict:
    """Qué pasaría si se investigara ahora mismo. NO investiga: solo cuenta y ordena.

    PARA QUÉ EXISTE

    La investigación cuesta dinero y llamadas, así que antes de encenderla hay que poder
    ver sobre los datos REALES cuántos eventos entrarían, cuáles y en qué orden. Un
    presupuesto que solo se puede comprobar gastándolo no es un presupuesto.

    Es una función pura sobre la lista que se le pase: no toca la red, no escribe nada y
    no mueve ninguna etapa.
    """
    eventos = [e for e in (eventos or []) if isinstance(e, dict)]
    por_estado = {estado: 0 for estado in ESTADOS}
    for e in eventos:
        estado = estado_de_investigacion(e)
        por_estado[estado] = por_estado.get(estado, 0) + 1

    reparto = a_investigar(eventos, gastadas_hoy=gastadas_hoy, tope=tope)
    # Todo lo que sigue en `significativo`, pase o no la puerta. Es lo que permite ver
    # que hay treinta WATCH esperando y que NO se investigan por diseño, en vez de que
    # desaparezcan del recuento sin explicación.
    sin_investigar = [e for e in eventos if e.get("etapa") == ev.SIGNIFICATIVO]
    return {
        "total_eventos": len(eventos),
        "por_estado": por_estado,
        "sin_investigar_por_nivel": _por_nivel(sin_investigar),
        # Solo los que pasan la puerta. WATCH e INFO salen a cero POR DISEÑO: la puerta
        # es `INTERRUMPEN`, y verlo a cero aquí junto al recuento de arriba es lo que
        # enseña dónde se corta.
        "pendientes_por_nivel": _por_nivel(reparto["elegidos"] + reparto["pendientes"]),
        "entrarian_en_el_presupuesto": len(reparto["elegidos"]),
        "quedarian_pendientes": len(reparto["pendientes"]),
        "elegidos": reparto["elegidos"],
        "pendientes": reparto["pendientes"],
        "motivos": reparto["motivos"],
        "presupuesto": {
            "tope_diario": TOPE_DIARIO if tope is None else tope,
            "gastadas_hoy": gastadas_hoy,
            "restante": reparto["presupuesto_restante"],
        },
        "niveles_que_pasan_la_puerta": list(ev.INTERRUMPEN),
    }


# ── Inspeccionar un documento SIN llamar al modelo ───────────────────────────

async def inspeccionar(evento: dict) -> dict:
    """Descarga y extrae, y ahí se para. CERO llamadas al modelo, cero cuota.

    PARA QUÉ

    Para poder mirar qué texto recibe —o recibió— el modelo sin volver a pagarlo. Cuando
    una lectura dice «no permitía concluir nada», hay dos explicaciones muy distintas: el
    documento no decía nada, o le mandamos el documento equivocado. Muchos 8-K son una
    carátula que remite a un anexo, y el contenido real está allí.

    Sin poder leer lo que leyó, esas dos cosas son indistinguibles — y una es un
    resultado correcto y la otra un fallo nuestro.

    Sirve también para eventos YA investigados, que es donde más falta hace: esos no se
    pueden relanzar, porque la idempotencia lo impide a propósito.
    """
    descarga = await descargar_documento((evento or {}).get("url"))
    salida = {
        "symbol": (evento or {}).get("symbol"),
        "url": (evento or {}).get("url"),
        "http": descarga.get("http"), "bytes": descarga.get("bytes", 0),
        "ms": descarga.get("ms", 0), "error": descarga.get("error"),
        "llamada_al_modelo": False,
    }
    if not descarga.get("ok"):
        return {**salida, "ok": False, "texto": None, "caracteres": 0,
                "verificacion": None}
    texto = texto_del_documento(descarga.get("html"), maximo=MAX_BYTES)
    return {**salida, "ok": True,
            "caracteres": len(texto),
            "caracteres_que_se_enviarian": min(len(texto), MAX_CARACTERES),
            "verificacion": parece_el_filing(texto, evento),
            # El texto ENTERO hasta el tope de envío: es lo que el modelo vería, ni más
            # ni menos. Recortarlo aquí a una muestra dejaría fuera justo la parte por la
            # que uno mira, que suele ser el final.
            "texto": texto[:MAX_CARACTERES]}
