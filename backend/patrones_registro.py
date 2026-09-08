"""Anotar cada patrón detectado y, más tarde, comprobar si acertó.

POR QUÉ EXISTE

`chart_lines` tiene diecinueve detectores y 3.000 líneas de geometría, y hasta ahora
NADIE medía si acertaban. El orden en que se preferían unos a otros —primero doble
suelo, luego triple, luego isla…— era una creencia razonable de quien lo escribió,
pero era una creencia: no había un solo dato detrás.

Eso convierte cualquier mejora en una discusión de opiniones. Se puede reordenar la
tabla de `_CANDIDATOS` y sonar convincente, y no habrá forma de saber si la pantalla
mejoró o empeoró. Este módulo es lo que rompe ese empate.

QUÉ MIDE, Y POR QUÉ ESO Y NO OTRA COSA

La pregunta NO es «¿subió la acción?». Un patrón bajista acierta cuando el precio
BAJA, y un patrón sin objetivo no promete nada. La pregunta es la única que el propio
patrón se hace:

    ¿llegó el precio al OBJETIVO antes de perder la INVALIDACIÓN?

Esos dos números los pone el detector, no yo. Así que esto no juzga el patrón con un
criterio de fuera: le toma la palabra y comprueba lo que él mismo prometió.

LO QUE ESTE MÓDULO NO HACE

No cambia ni un prior. Recoge y evalúa; reordenar la preferencia con esos datos es
una decisión posterior y consciente, cuando haya muestra suficiente. Mezclar las dos
cosas dejaría un sistema que se reordena solo con veinte observaciones y un sesgo de
mercado alcista, que es peor que la creencia que sustituye.

FECHAS

Todo en UTC e ISO 8601, como el resto del proyecto.
"""
from datetime import datetime, timezone
from typing import Optional

# Cuántas velas se espera como mucho a que el patrón se resuelva. Pasado eso se cierra
# como CADUCADO y no como fallo: un patrón que no llega a su objetivo ni pierde su
# stop en tres meses no se equivocó, es que no dijo nada aprovechable. Contarlo como
# fallo castigaría a los detectores prudentes y premiaría a los que prometen mucho.
VELAS_MAXIMAS = 60

# Muestra mínima antes de que un porcentaje de acierto signifique algo. Con menos, la
# cifra es ruido con formato de estadística — y el peligro no es que sea imprecisa,
# es que INVITA a reordenar los priors sobre nada.
MUESTRA_MINIMA = 20

ESTADOS = ("pendiente", "acierto", "fallo", "caducado")


def _objetivo_e_invalidacion(patron: dict) -> tuple[Optional[float], Optional[float]]:
    """Los dos números que el patrón promete, vengan como vengan.

    Cada detector los expone a su manera —la taza en `objetivo`/`pivote`, el
    hombro-cabeza-hombro dentro de `puntos.objetivo.target`— porque cada uno se
    escribió en su momento. Traducir aquí evita que el registro tenga que conocer
    diecinueve formatos, y sobre todo evita que cada detector tenga que cambiar para
    poder medirse.
    """
    if not isinstance(patron, dict):
        return None, None
    obj = patron.get("objetivo")
    if isinstance(obj, dict):
        # Forma del hombro-cabeza-hombro: {"ruptura": …, "target": {"price": …}}
        t = obj.get("target")
        obj = t.get("price") if isinstance(t, dict) else None
    inv = patron.get("invalidacion")
    if inv is None:
        # La taza no llama «invalidación» a su stop: lo describe como el mínimo del
        # asa. Se busca en los puntos antes de darlo por ausente.
        puntos = patron.get("puntos")
        if isinstance(puntos, list):
            p4 = next((p for p in puntos if p.get("label") == "P4"), None)
            inv = p4.get("price") if isinstance(p4, dict) else None
    try:
        obj = float(obj) if obj is not None else None
        inv = float(inv) if inv is not None else None
    except (TypeError, ValueError):
        return None, None
    return obj, inv


def ficha(patron: dict, symbol: str, timeframe: str, precio: float,
          cuando: Optional[str] = None) -> Optional[dict]:
    """La anotación de un patrón recién detectado, o None si no hay nada que medir.

    Se descarta el patrón sin objetivo o sin invalidación, y no por comodidad: sin
    esos dos números no existe la pregunta que este módulo contesta. Anotarlo igual
    llenaría la colección de filas que nunca se podrán resolver y que ensuciarían el
    porcentaje de acierto de su detector.
    """
    if not isinstance(patron, dict) or not symbol or not timeframe:
        return None
    try:
        precio = float(precio)
    except (TypeError, ValueError):
        return None
    if precio <= 0:
        return None
    obj, inv = _objetivo_e_invalidacion(patron)
    if obj is None or inv is None:
        return None
    sentido = (patron.get("sentido") or "").lower()
    if sentido not in ("alcista", "bajista"):
        return None
    # Coherencia: en un patrón alcista el objetivo va por encima y el stop por debajo.
    # Al revés no es un patrón raro, es un patrón mal construido, y medirlo daría una
    # estadística sobre un error de geometría en vez de sobre el detector.
    if sentido == "alcista" and not (obj > precio > inv):
        return None
    if sentido == "bajista" and not (obj < precio < inv):
        return None
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "tipo": patron.get("tipo"),
        "detector": patron.get("detector"),
        "confianza": patron.get("confianza"),
        "sentido": sentido,
        "precio_deteccion": round(precio, 4),
        "objetivo": round(obj, 4),
        "invalidacion": round(inv, 4),
        "detectado_en": cuando or datetime.now(timezone.utc).isoformat(),
        "estado": "pendiente",
        "velas_vistas": 0,
    }


def evaluar(registro: dict, velas: list) -> dict:
    """Resuelve una anotación con las velas POSTERIORES a su detección.

    Devuelve un registro nuevo; el original no se toca, porque suele venir de Mongo y
    quien llama decide si escribe.

    QUÉ SE MIRA, Y EN QUÉ ORDEN

    Máximo y mínimo de cada vela, en orden, y gana lo que ocurra ANTES. Mirar solo el
    cierre perdería el objetivo tocado a media sesión, que para un patrón con orden
    limitada puesta es exactamente lo que cuenta.

    EL EMPATE DENTRO DE UNA MISMA VELA SE RESUELVE EN CONTRA

    Si una vela toca objetivo e invalidación a la vez, se cuenta FALLO. Con datos
    diarios no se sabe cuál llegó primero, y suponer que fue el objetivo es el sesgo
    que hace que cualquier sistema parezca mejor de lo que es.
    """
    r = dict(registro)
    if r.get("estado") not in (None, "pendiente"):
        return r
    obj, inv = r.get("objetivo"), r.get("invalidacion")
    alcista = r.get("sentido") == "alcista"
    if obj is None or inv is None:
        r["estado"] = "caducado"
        return r
    for i, v in enumerate(velas[:VELAS_MAXIMAS], start=1):
        try:
            hi, lo = float(v.get("high")), float(v.get("low"))
        except (TypeError, ValueError, AttributeError):
            continue
        toca_obj = hi >= obj if alcista else lo <= obj
        toca_inv = lo <= inv if alcista else hi >= inv
        if toca_obj or toca_inv:
            r["estado"] = "fallo" if toca_inv else "acierto"
            r["velas_vistas"] = i
            r["resuelto_en"] = v.get("date") or v.get("time")
            return r
    r["velas_vistas"] = min(len(velas), VELAS_MAXIMAS)
    if r["velas_vistas"] >= VELAS_MAXIMAS:
        r["estado"] = "caducado"
    return r


def rendimiento(registros: list) -> list:
    """Acierto por detector, ordenado de mejor a peor. La respuesta a «¿cuál sirve?».

    Los CADUCADOS se excluyen del porcentaje pero se cuentan aparte: un detector que
    caduca el 80 % de las veces puede tener un acierto altísimo entre los pocos que
    resuelve y aun así no servir para nada. Fundir las dos cosas en un número lo
    escondería.

    `suficiente` no es decorativo: es lo que separa un dato de una anécdota, y es la
    única defensa contra reordenar los priors con quince observaciones.
    """
    por = {}
    for r in registros or []:
        d = r.get("detector") or r.get("tipo") or "desconocido"
        e = por.setdefault(d, {"detector": d, "acierto": 0, "fallo": 0,
                               "caducado": 0, "pendiente": 0})
        estado = r.get("estado")
        if estado in e:
            e[estado] += 1
    salida = []
    for e in por.values():
        resueltos = e["acierto"] + e["fallo"]
        e["resueltos"] = resueltos
        e["tasa"] = round(e["acierto"] / resueltos * 100, 1) if resueltos else None
        e["suficiente"] = resueltos >= MUESTRA_MINIMA
        salida.append(e)
    # Sin muestra suficiente van al final: que un detector con 2 de 2 encabece la
    # lista sería la forma más rápida de tomar una decisión mala con buena cara.
    salida.sort(key=lambda e: (e["suficiente"], e["tasa"] or -1, e["resueltos"]),
                reverse=True)
    return salida
