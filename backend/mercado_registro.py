"""La foto diaria de los insumos de decisión. El dato que mañana ya no se puede tomar.

POR QUÉ ESTE MÓDULO ES EL PRIMERO DEL LABORATORIO, Y NO UN AGENTE

Todo el aprendizaje que queremos —¿funciona este filtro?, ¿mejora esta regla?, ¿en qué
régimen falla?— se responde comparando lo que el sistema VEÍA en una fecha con lo que
pasó DESPUÉS. Sin lo primero no hay experimento posible, solo opinión.

Y lo primero caduca. Los precios se pueden recuperar del histórico, pero el resto de lo
que InverIA mira no: la nota del consenso de analistas de hoy, el PER de hoy, la fuerza
relativa de hoy, la zona de compra que el motor calculaba hoy. Las fuentes sirven el
ÚLTIMO valor, no el de hace tres meses. Cada día que no se anota es un día que no se
podrá estudiar nunca.

Por eso esto va antes que cualquier agente: un agente que razone sobre datos que no
existen produce narrativa, no evidencia.

LO QUE ESTE MÓDULO NO HACE

No puntúa, no decide, no llama a ningún modelo y no gasta ni una petición de red. Se
engancha donde el dashboard YA se ha construido y anota lo que ya estaba calculado. Si
tuviera que pedir datos, el coste de la foto dependería del tamaño del universo y
acabaríamos recortando la muestra para pagar menos — que es como se arruina un dataset.

LA HONESTIDAD DE LO QUE SE PUEDE APRENDER CON ESTO

Esta foto permite estudiar decisiones NUESTRAS: qué veíamos, qué dijimos y qué pasó
luego. NO convierte a InverIA en una plataforma de backtesting de factores sobre el
mercado entero — para eso haría falta un histórico punto-en-el-tiempo de fundamentales
que incluyera las empresas desaparecidas, y no lo tenemos. Un backtest de factores con
los datos de hoy mediría un mercado sin quiebras, que es el sesgo de supervivencia de
manual. Esa limitación está escrita aquí para que nadie construya encima creyendo otra
cosa.

UNA FOTO POR SÍMBOLO Y DÍA

El dashboard se reconstruye varias veces al día. La primera foto de cada día manda: es
la que corresponde al momento en que el sistema decidió. Reescribirla con la de la tarde
daría un dato «del día» que en realidad es de la hora de cierre, y al cruzarlo con una
decisión de la mañana estaríamos mirando el futuro.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("inveria.mercado")

COLECCION = "mercado_fotos"

#: Versión del FORMATO de la foto. Misma convención que `RELEVANCIA_V`, `PROMPT_V` y
#: `TESIS_V`: si algún día cambia qué se anota, las fotos viejas no son comparables con
#: las nuevas y hay que poder saberlo sin adivinar.
FOTO_V = 1


def _num(v):
    """Un número, o None. Nunca un cero de relleno.

    `or 0` convierte «no lo sabíamos» en «valía cero», y al estudiarlo después no hay
    forma de distinguirlos. Es la misma regla que `calibracion.py` defiende para los
    umbrales: un dato que no está no puede producir una afirmación sobre sí mismo.
    """
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n != n else n          # NaN fuera: no es un número


def _dia(cuando: Optional[str] = None) -> str:
    if cuando:
        return cuando[:10]
    return datetime.now(timezone.utc).date().isoformat()


def foto(dashboard: Optional[dict]) -> Optional[dict]:
    """Lo que el sistema veía de un símbolo. Pura: no toca red ni base de datos.

    QUÉ SE ANOTA Y POR QUÉ ESO

    Los insumos que ya alimentan una decisión hoy, cada uno por separado y sin agregar.
    No se calcula ningún total: `separacion.py` existe precisamente para impedir que
    calidad, valoración y tendencia se fundan en un número donde un 60 puede significar
    «cara pero líder» o «barata pero muerta». Una foto con un total heredaría ese defecto
    y además lo congelaría en el histórico.

    Se anota también `tesis_huella` para poder unir esta foto con la versión de la tesis
    que estaba vigente, sin duplicar su contenido.
    """
    if not isinstance(dashboard, dict) or not dashboard:
        return None
    symbol = (dashboard.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    ind = dashboard.get("indicators") or {}
    quote = dashboard.get("quote") or {}
    regimen = ind.get("regime") or {}
    sma = ind.get("sma") or {}
    niveles = dashboard.get("buy_levels") or []
    mejor = niveles[0] if niveles and isinstance(niveles[0], dict) else {}
    rs = ((dashboard.get("relative_strength") or {}).get("6m")) or {}
    consenso = ((dashboard.get("analyst") or {}).get("consensus")) or {}
    mercado = dashboard.get("market_regime") or {}
    salud = dashboard.get("data_health") or {}

    return {
        "symbol": symbol,
        "foto_v": FOTO_V,
        "precio": _num(quote.get("price")),
        "cambio_pct": _num(quote.get("change_percent")),
        "tecnico": {
            "rsi": _num(ind.get("rsi")),
            "atr_pct": _num(ind.get("atr_pct")),
            "sma20": _num(sma.get("20")),
            "sma50": _num(sma.get("50")),
            "sma200": _num(sma.get("200")),
            "maximo_52s": _num(ind.get("high_52w")),
            "minimo_52s": _num(ind.get("low_52w")),
            "obv": ind.get("obv_trend"),
            "regimen": regimen.get("regime"),
            "adx": _num(regimen.get("adx")),
        },
        "zona_de_compra": {
            "precio": _num(mejor.get("price")),
            "fuerza": _num(mejor.get("strength")),
            "distancia_pct": _num(mejor.get("distance_pct")),
            "etiqueta": mejor.get("label"),
            # Las razones son NOMBRES y son lo que hace comparable una zona con otra.
            "razones": [str(r) for r in (mejor.get("reasons") or [])],
            "cuantas_zonas": len(niveles),
        },
        "fuerza_relativa": {
            "accion_pct": _num(rs.get("accion_pct")),
            "indice_pct": _num(rs.get("indice_pct")),
            "diferencia_pp": _num(rs.get("diferencia_pp")),
        },
        "consenso": {"etiqueta": consenso.get("label"), "nota": _num(consenso.get("score"))},
        "mercado": {"semaforo": mercado.get("light"),
                    "dist_sma200_pct": _num(mercado.get("dist_sma200_pct"))},
        # De dónde salieron los datos y si venían degradados. Una foto tomada con la
        # fuente de respaldo no vale lo mismo, y sin esto no habría forma de saberlo.
        "origen": {"fuente": salud.get("source"), "degradado": bool(salud.get("degraded"))},
        "tesis_huella": None,      # lo rellena quien registra, que es quien la conoce
    }


async def guardar(db, dashboard: Optional[dict], tesis_huella: str = None,
                  cuando: str = None) -> dict:
    """Anota la foto del día si todavía no hay ninguna. NUNCA lanza.

    LA PRIMERA DEL DÍA MANDA

    Se escribe con `$setOnInsert`: si ya existe la foto de hoy, esta llamada no la toca.
    Es la diferencia entre «lo que veíamos cuando decidimos» y «lo último que vimos», y
    solo la primera sirve para estudiar una decisión sin mirar el futuro.

    Cuelga del camino que construye el dashboard, así que un fallo aquí no puede dejar
    sin página a quien abre una acción. Mismo criterio que el registro de la tesis.
    """
    f = foto(dashboard)
    if f is None:
        return {"accion": "nada", "motivo": "sin_datos"}
    dia = _dia(cuando)
    f["tesis_huella"] = tesis_huella
    f["tomada_en"] = cuando or datetime.now(timezone.utc).isoformat()
    try:
        r = await db[COLECCION].update_one(
            {"symbol": f["symbol"], "dia": dia},
            {"$setOnInsert": {**f, "dia": dia}}, upsert=True)
        creada = bool(getattr(r, "upserted_id", None))
        return {"accion": "creada" if creada else "ya_estaba",
                "symbol": f["symbol"], "dia": dia}
    except Exception as e:
        logger.warning("mercado: no se pudo anotar la foto de %s: %s",
                       f["symbol"], str(e)[:120])
        return {"accion": "nada", "motivo": "error", "error": str(e)[:200]}


async def historial(db, symbol: str, limite: int = 90) -> list:
    """Las fotos de un símbolo, la más reciente primero. Solo lectura."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return []
    docs = await db[COLECCION].find({"symbol": symbol}, {"_id": 0}).sort(
        "dia", -1).limit(limite).to_list(limite)
    return docs


async def cobertura(db) -> dict:
    """Cuánto histórico llevamos acumulado. Es la única métrica honesta del laboratorio
    mientras no haya suficiente muestra: cuántos días y cuántos símbolos hay ANOTADOS.

    Contar conceptos aprendidos o documentos ingeridos no diría nada; los días de
    historia sí, porque son exactamente lo que limita qué se puede estudiar.
    """
    try:
        total = await db[COLECCION].count_documents({})
        dias = await db[COLECCION].distinct("dia")
        simbolos = await db[COLECCION].distinct("symbol")
    except Exception as e:
        return {"error": str(e)[:200], "fotos": None}
    dias = sorted(d for d in dias if d)
    return {
        "fotos": total,
        "dias": len(dias),
        "simbolos": len(simbolos),
        "desde": dias[0] if dias else None,
        "hasta": dias[-1] if dias else None,
        "foto_v": FOTO_V,
    }
