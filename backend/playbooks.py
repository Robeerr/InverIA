"""Qué estrategia gobierna una señal. Infraestructura, sin comportamiento todavía.

POR QUÉ EXISTE ANTES DE QUE SIRVA PARA NADA

Un playbook es una estrategia completa: universo, selección, setup, gatillo, entrada,
stop, salida y tamaño, cada uno con su backtest. Hoy no tenemos ninguno validado. Este
módulo no los implementa: reserva el sitio y, sobre todo, impide de antemano el error
que ya cometimos una vez.

Ese error tiene nombre y está en producción: `_potential_score` suma en un mismo número
puntos por valoración barata y puntos por momentum — los dos factores que la literatura
describe como negativamente correlacionados, porque una acción barata suele serlo
PORQUE ha caído. El resultado es un número donde un 60 puede significar «cara pero
líder» o «barata pero muerta», y las dos cosas se presentan igual.

Aquí se prohíbe que eso vuelva a pasar por construcción, no por disciplina.

LAS TRES COSAS QUE NO SON LO MISMO

  `playbook`            El CARRIL. Qué estrategia se hace cargo de la señal. Es
                        enrutamiento técnico, no un certificado: que ponga
                        LEADER_PULLBACK NO significa que la señal cumpla las condiciones
                        de ese playbook, porque su SETUP y su TRIGGER todavía no están
                        definidos ni calibrados.

  `playbook_observado`  La CLASIFICACIÓN, y solo cuando se puede justificar con
                        información disponible EN LA FECHA de la señal. Es lo único que
                        puede entrar en el experimento D. Hoy vale UNKNOWN siempre, sin
                        excepción, porque no hay definición contra la que comprobar.

  `playbook_inferido`   Que el carril se rellenó por retrocompatibilidad y no porque
                        nadie lo decidiera. Un documento histórico sin campo no se
                        convierte en una señal clasificada por el hecho de leerlo.

Mezclar la primera con la segunda es la forma silenciosa de contaminar el experimento:
se etiquetan mil señales antiguas como LEADER_PULLBACK, se miden sus resultados y se
concluye algo sobre un playbook que ninguna de ellas siguió.

NADA DE ETIQUETAR HACIA ATRÁS CON DATOS DE HOY

Una señal solo se puede clasificar con lo que se sabía cuando se emitió. Mirar cómo
acabó —o incluso mirar su SMA200 de hoy en vez de la de aquel día— convierte el
experimento en una profecía cumplida.
"""
from typing import Optional

# ── Los cuatro nombres ───────────────────────────────────────────────────────
LEADER_PULLBACK = "LEADER_PULLBACK"
BREAKOUT = "BREAKOUT"
RECOVERY = "RECOVERY"
VALUE_MEAN_REVERSION = "VALUE_MEAN_REVERSION"

# Valor reservado para «no clasificado». No es un playbook: es su ausencia.
NO_OBSERVADO = "UNKNOWN"

DECLARADOS = (LEADER_PULLBACK, BREAKOUT, RECOVERY, VALUE_MEAN_REVERSION)

# Solo uno puede emitir señales. Los otros tres existen como hipótesis con nombre para
# que el día que se definan no haya que reescribir el enrutamiento — y para que quede
# escrito que NO están validados.
ACTIVOS = (LEADER_PULLBACK,)

# Qué le falta a cada hipótesis antes de poder activarse. Está aquí y no en un documento
# aparte para que quien intente añadirlo a ACTIVOS lea primero por qué no lo está.
HIPOTESIS = {
    BREAKOUT: ("Necesita un detector de bases o consolidaciones que no existe, y decidir "
               "qué volumen confirma una ruptura. Ninguna de las dos cosas está medida."),
    RECOVERY: ("No tiene ni definición operativa: «recupera la estructura» no es una "
               "condición comprobable todavía."),
    VALUE_MEAN_REVERSION: ("Opera en un horizonte de trimestres a años que nuestro "
                           "histórico no cubre. Es una familia distinta, no una variante "
                           "de LEADER_PULLBACK, y no puede compartir score con él."),
}


# ── Qué puede y qué no ───────────────────────────────────────────────────────

def esta_declarado(nombre: Optional[str]) -> bool:
    return nombre in DECLARADOS


def puede_emitir_senal(nombre: Optional[str]) -> bool:
    """¿Este playbook puede producir una señal hoy?

    Solo los activos. Un nombre desconocido tampoco: fallo cerrado, igual que en
    `tendencia.py`. Si alguien inventa un playbook y olvida activarlo, la respuesta
    segura es que no emita nada, no que emita sin control.
    """
    return nombre in ACTIVOS


def motivo_de_inactividad(nombre: Optional[str]) -> Optional[str]:
    """Por qué este playbook no puede emitir, o None si sí puede.

    Existe para que un rechazo se pueda registrar con su causa. «Playbook inactivo» a
    secas obliga a leer el código para saber qué falta.
    """
    if puede_emitir_senal(nombre):
        return None
    if nombre in HIPOTESIS:
        return HIPOTESIS[nombre]
    return f"'{nombre}' no es un playbook declarado."


# ── Los campos que lleva una señal ───────────────────────────────────────────

def campos_de_senal(playbook: str = LEADER_PULLBACK) -> dict:
    """Los campos de trazabilidad de una señal NUEVA.

    Función pura: devuelve el diccionario y no escribe en ningún sitio. Quien persista
    decide dónde.

    `playbook_observado` sale UNKNOWN incluso para una señal nueva. No es un descuido:
    clasificar exige comprobar el SETUP y el TRIGGER del playbook, y ninguno de los dos
    está definido. El día que lo estén, esta función podrá comprobarlos; hoy afirmar que
    una señal «es» LEADER_PULLBACK sería una etiqueta sin verificación detrás.
    """
    if not puede_emitir_senal(playbook):
        raise ValueError(
            f"El playbook '{playbook}' no puede emitir señales: "
            f"{motivo_de_inactividad(playbook)}"
        )
    return {
        "playbook": playbook,
        "playbook_observado": NO_OBSERVADO,
        "playbook_inferido": False,
    }


def campos_por_compatibilidad(doc: Optional[dict]) -> dict:
    """Los campos de un documento HISTÓRICO que no los tiene.

    Rellena el carril para que el código que espera el campo funcione, y deja constancia
    de que fue una inferencia. `playbook_observado` sigue siendo UNKNOWN: es exactamente
    la distinción que impide que mil señales antiguas entren en el experimento
    disfrazadas de LEADER_PULLBACK.
    """
    d = dict(doc or {})
    if d.get("playbook") in DECLARADOS:
        d.setdefault("playbook_observado", NO_OBSERVADO)
        d.setdefault("playbook_inferido", False)
        return d
    d["playbook"] = LEADER_PULLBACK
    d["playbook_inferido"] = True
    d["playbook_observado"] = NO_OBSERVADO
    return d


# ── El experimento D ─────────────────────────────────────────────────────────

def apto_para_experimento(doc: Optional[dict]) -> bool:
    """¿Esta señal puede entrar en el experimento D?

    Solo si está OBSERVADA: clasificada de verdad y con información de su fecha. Un
    carril rellenado por compatibilidad no cuenta, y un UNKNOWN tampoco.

    Hoy esto devuelve False para todo lo que hay, y así debe ser: no tenemos ni una sola
    señal clasificada. Que el filtro esté escrito antes de que haya nada que filtrar es
    el objetivo — cuando lleguen los datos, la puerta ya estará puesta.
    """
    d = doc or {}
    if d.get("playbook_inferido"):
        return False
    obs = d.get("playbook_observado")
    return obs in DECLARADOS and obs != NO_OBSERVADO


def agrupar_por_observado(docs) -> dict:
    """Las señales agrupadas por su playbook OBSERVADO, para comparar poblaciones.

    Lo que no se puede clasificar cae en NO_OBSERVADO y se cuenta aparte, no se reparte.
    Un grupo «resto» que se ignora en silencio es la forma más fácil de que el
    experimento mida otra cosa distinta de la que dice medir.
    """
    grupos = {nombre: [] for nombre in DECLARADOS}
    grupos[NO_OBSERVADO] = []
    for doc in docs or []:
        if apto_para_experimento(doc):
            grupos[(doc or {}).get("playbook_observado")].append(doc)
        else:
            grupos[NO_OBSERVADO].append(doc)
    return grupos
