"""El veto estructural aplicado a lo que dice la IA. Solo en la frontera de salida.

EL CONTRATO

    La tendencia es la autoridad.
    La IA puede recomendar, pero no puede autorizar una compra que la estructura ha vetado.
    El veto se aplica justo antes de mostrar o ejecutar, no contamina lo generado.

Tres frases, y las tres importan por separado.

QUIÉN MANDA

`tendencia.py` decide la dirección y `estado_accion.py` la traduce a estado. Este módulo
no clasifica nada: recibe el estado ya decidido y lo aplica. Si algún día la regla de
elegibilidad cambia, cambia allí y aquí no se toca ni una línea — que es la razón de que
`hay_veto` mire un estado y no un precio contra una media.

POR QUÉ AL SERVIR Y NO AL GUARDAR

El veredicto del Chartista se cachea hasta 4 horas (`CHARTIST_TTL`), y el histórico del
que sale la tendencia, 15 minutos. Sellar el veto dentro del objeto cacheado guardaría
una tendencia de hace cuatro horas junto a un veredicto que se sigue sirviendo: se
cambiaría una contradicción entre módulos por otra entre momentos. Aplicándolo al servir,
un veredicto viejo se entrega siempre con la estructura de ahora.

Y hay un motivo más, este de implementación: `_TTLCache.get` devuelve el valor GUARDADO,
no una copia. Mutar el objeto servido reescribiría la caché para todos los lectores
siguientes, y el veredicto original se perdería sin que fallara nada. Por eso las dos
funciones de degradación construyen diccionarios nuevos y no tocan los que reciben. No es
higiene: es la única forma de que «no contamina lo generado» sea cierto.

QUÉ SE DEGRADA Y QUÉ NO

Se va lo que AUTORIZA: la acción de compra, los niveles de entrada, el gatillo que la
dispara, la invalidación y el objetivo. Se queda todo lo que DESCRIBE: el veredicto en
prosa, la lectura por timeframe, el patrón, el sentido y la explicación pedagógica. Una
acción en tendencia bajista se puede estudiar; lo que no se puede es comprarla porque lo
diga un modelo.
"""
from typing import Optional

import tendencia

# El único estado que veta. Se escribe una vez y se compara contra él en vez de repetir
# la cadena por ahí: si mañana `EN_SEGUIMIENTO` también tuviera que bloquear, cambia aquí
# y no en cinco sitios que nadie recordaría revisar.
ESTADO_BLOQUEANTE = "NO_COMPRAR"

# Los campos del plan del Chartista que dejan de tener sentido bajo un veto. `por_que` NO
# está: es la explicación del razonamiento, y el usuario aprende igual de un plan que no
# puede ejecutar. `gatillo` sí, porque describe el evento que ACTIVA la compra.
_ACCIONABLES = ("niveles_entrada", "gatillo", "invalidacion", "objetivo")

# Los campos de la Cartera que expresan una intención de COMPRA. `deseado` y `venta1..3`
# quedan fuera a propósito: son objetivos de VENTA, y el veto es sobre comprar. Lo dice ya
# `cartera_api._actualizar_precio_nivel` — «`deseado` es el objetivo de VENTA y una compra
# no debe moverlo»— y aquí se respeta la misma frontera.
CAMPOS_NIVEL = ("nivel1", "nivel2", "nivel3", "nivel4", "nivel5")

# El estado que `tendencia.py` emite cuando NO HA PODIDO comprobar la dirección: menos de
# 200 cierres, o el histórico no cargó. Se nombra aquí para que los consumidores no
# escriban la cadena a mano, igual que con `ESTADO_BLOQUEANTE`.
TENDENCIA_NO_VERIFICABLE = "SIN_DATOS"

MOTIVO_NO_VERIFICABLE = (
    "No se ha podido comprobar en qué tendencia está esta acción — hacen falta 200 "
    "sesiones de histórico y no se han podido leer. No se presenta como compra algo que "
    "no se ha podido verificar."
)


def hay_veto(estado: Optional[str]) -> bool:
    """¿Bloquea este estado una compra?

    Se compara contra el estado y no contra la tendencia a propósito: la traducción de
    dirección a estado ya la hizo `estado_accion`, y repetirla aquí sería la segunda
    implementación de una regla que tiene dueño.
    """
    return estado == ESTADO_BLOQUEANTE


def no_verificable(estado_tendencia: Optional[str]) -> bool:
    """¿Se ha podido comprobar la dirección de esta acción?

    NO es lo mismo que `hay_veto`, y por eso son dos funciones y no una:

        NO_COMPRAR  → se comprobó, y la estructura dice que no.
        SIN_DATOS   → no se pudo comprobar. No dice nada.

    Los dos acaban ocultando una compra, pero por motivos distintos y con explicaciones
    distintas. Fundirlos haría que «no lo sé» se leyera como «está bajista», que es una
    afirmación sobre el mercado que nadie ha hecho.

    Nótese que `estado_accion` traduce SIN_DATOS a EN_SEGUIMIENTO —vigílalo, no es un
    rechazo—, así que `hay_veto` devuelve False aquí. Correcto para el estado de la acción;
    insuficiente para etiquetar una proximidad como compra. De ahí esta segunda pregunta.

    QUÉ CUENTA COMO NO VERIFICABLE

    Todo lo que no sea uno de los estados que `tendencia.py` sabe producir, más SIN_DATOS,
    que es el que ese módulo emite precisamente cuando no ha podido comprobar nada. Un
    None, una excepción que el llamador ha traducido a este estado, una cadena vacía o una
    etiqueta que nadie ha mapeado: todas significan lo mismo aquí — no lo sé — y ninguna
    puede autorizar una compra.

    LA COMPROBACIÓN CONTRA `tendencia.ESTADOS` NO ES DECORATIVA

    Sin ella quedaba un hueco entre dos capas. `estado_accion.evaluar` mapea cualquier
    estado desconocido a SIN_DATOS —o sea, LO RECONOCE como no comprobable— y devuelve
    EN_SEGUIMIENTO, que no veta. Pero esta función solo miraba `""` y SIN_DATOS, así que
    una etiqueta desconocida se colaba entre las dos y salía como COMPRA.

    No era alcanzable: `market_data.tendencia_de` solo devuelve los cuatro estados o
    SIN_DATOS ante cualquier fallo. Pero una capa defensiva que depende de que nadie añada
    un estado nuevo no está defendiendo nada — está esperando. Se cierra preguntando al
    dueño de la lista en vez de mantener aquí una copia de qué estados existen.
    """
    if not isinstance(estado_tendencia, str):
        return True
    if estado_tendencia not in tendencia.ESTADOS:
        return True
    return estado_tendencia == TENDENCIA_NO_VERIFICABLE


def degradar_analisis(analisis: dict, estado: Optional[str]) -> dict:
    """La recomendación de la IA de /analyze, sin permiso de compra.

    COMPRAR pasa a MANTENER. VENDER no se toca: el veto es sobre comprar, y convertir una
    venta en un mantener sería inventarse una opinión que nadie ha dado.

    `confidence` tampoco se toca. Mide cuánta seguridad tiene el modelo en su lectura, y
    esa lectura sigue siendo la que era — el que no manda es él, pero no por eso ha dejado
    de estar seguro. Recortarla mezclaría dos cosas distintas.
    """
    if not isinstance(analisis, dict) or not hay_veto(estado):
        return analisis
    if (analisis.get("recommendation") or "").strip().upper() != "COMPRAR":
        return analisis
    # Copia: el llamador puede estar sirviendo un objeto que también persiste o cachea.
    salida = dict(analisis)
    salida["recommendation"] = "MANTENER"
    # Lo que dijo el modelo se conserva. Sin esto, la degradación sería indistinguible de
    # un MANTENER genuino y no habría forma de auditar cuántas veces actuó el veto.
    salida["recomendacion_ia"] = "COMPRAR"
    salida["vetado_por_tendencia"] = True
    return salida


def degradar_chartista(veredicto: dict, estado: Optional[str],
                       motivo: Optional[str] = None) -> dict:
    """El veredicto del Chartista, sin plan de compra ejecutable.

    Devuelve SIEMPRE un objeto nuevo cuando hay veto, con un `plan` nuevo dentro. El
    original queda intacto porque suele ser el que vive en la caché, y mutarlo lo
    reescribiría para todos los lectores siguientes.

    Los accionables se retiran SIEMPRE que hay veto, no solo cuando la acción es COMPRAR.
    Un plan con acción ESPERAR puede traer `niveles_entrada` poblados, y la pantalla
    ofrece «Añadir a Cartera» mirando esa lista y no la acción: dejarlos sería permitir
    que se persista un plan de compra sobre una acción vetada por la puerta de al lado.
    El verbo, en cambio, solo se reescribe cuando dice COMPRAR — si el modelo ya decía
    ESPERAR o EVITAR, no hay nada que corregir.
    """
    if not isinstance(veredicto, dict) or not hay_veto(estado):
        return veredicto

    salida = dict(veredicto)
    salida["vetado_por_tendencia"] = True
    if motivo:
        salida["veto_motivo"] = motivo

    plan = veredicto.get("plan")
    if not isinstance(plan, dict):
        return salida

    plan_nuevo = dict(plan)
    if (plan_nuevo.get("accion") or "").strip().upper() == "COMPRAR":
        plan_nuevo["accion"] = "ESPERAR"
        plan_nuevo["accion_ia"] = "COMPRAR"
    for campo in _ACCIONABLES:
        if campo == "niveles_entrada":
            # Lista vacía y no `None`: la pantalla recorre este campo y comprueba su
            # longitud. Cambiarle el tipo obligaría a defenderse en cada lectura.
            plan_nuevo[campo] = []
        else:
            plan_nuevo[campo] = None
    salida["plan"] = plan_nuevo
    return salida


def niveles_de_compra_en(payload: dict) -> list:
    """Qué niveles de compra trae este payload de Cartera, si es que trae alguno.

    Existe para que los endpoints no tengan que saber CUÁLES son los campos de compra ni
    qué cuenta como «traer un nivel». Las dos cosas son la misma decisión que ya toma este
    módulo en el plan del Chartista, y repartirla por `server.py` sería tenerla dos veces.

    `None` NO cuenta, y es el matiz que más importa. En un PATCH, `nivel1: null` BORRA el
    nivel — `SignalEntryUpdate` usa `exclude_unset`, así que un nulo enviado es un nulo
    querido. Borrar un nivel de una acción vetada es exactamente lo que el veto persigue,
    no lo que debe impedir; bloquearlo dejaría al usuario sin poder retirar un plan de
    compra sobre una acción que acaba de girarse en contra.

    El cero tampoco cuenta: no es un precio de compra, es un campo vacío mal escrito.
    """
    if not isinstance(payload, dict):
        return []
    presentes = []
    for campo in CAMPOS_NIVEL:
        valor = payload.get(campo)
        if valor is None:
            continue
        try:
            if float(valor) > 0:
                presentes.append(campo)
        except (TypeError, ValueError):
            continue
    return presentes
