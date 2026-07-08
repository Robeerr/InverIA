"""Base de conocimiento de inversión — el "cerebro" que crece con cada newsletter.

Los correos de bolsa no solo dan tickers: enseñan MÉTODO (cómo valorar una empresa,
cómo detectar rotación de sectores, cómo gestionar el riesgo...). Este módulo acumula
esos aprendizajes, los deduplica por tema y los inyecta en el prompt del motor de análisis,
de forma que InverIA "sabe" cada vez más a medida que llegan más correos.

- Colección Mongo: investing_knowledge (un doc por principio, con contador de refuerzos).
- Cache en memoria (_DIGEST): texto compacto listo para inyectar en el system prompt.
  Se reconstruye al añadir aprendizajes y al arrancar el servidor.
"""
import logging
import re

logger = logging.getLogger("inveria.knowledge")

_CATEGORIAS = {"selección", "seleccion", "valoración", "valoracion", "riesgo",
               "psicología", "psicologia", "macro", "método", "metodo", "sectores"}

# Cache en memoria del digest inyectable. Módulo-level para que analyze_stock lo lea
# sin necesitar acceso a la BD.
_DIGEST = ""
_MAX_DIGEST_CHARS = 2600   # techo para no inflar el prompt del motor
_MAX_ITEMS = 40


def _norm(s: str) -> str:
    """Normaliza para deduplicar: minúsculas, sin tildes, sin puntuación, colapsado."""
    s = (s or "").lower().strip()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _key(categoria: str, tema: str) -> str:
    return f"{_norm(categoria)}::{_norm(tema)}"


async def add_learnings(db, aprendizajes: list, source: str = "") -> int:
    """Guarda/refuerza una lista de aprendizajes. Deduplica por (categoria, tema):
    si ya existe, incrementa el contador de refuerzos y conserva el principio más rico.
    Devuelve cuántos aprendizajes se procesaron."""
    if not aprendizajes:
        return 0
    n = 0
    for a in aprendizajes:
        tema = (a.get("tema") or "").strip()
        principio = (a.get("principio") or "").strip()
        if not tema or not principio:
            continue
        cat = (a.get("categoria") or "método").strip().lower()
        if cat not in _CATEGORIAS:
            cat = "método"
        detalle = (a.get("detalle") or "").strip()
        k = _key(cat, tema)
        try:
            existing = await db.investing_knowledge.find_one({"_key": k})
            if existing:
                # Conserva el principio más largo (suele ser el más completo).
                mejor = principio if len(principio) > len(existing.get("principio", "")) else existing["principio"]
                await db.investing_knowledge.update_one(
                    {"_key": k},
                    {"$set": {"principio": mejor,
                              "detalle": detalle or existing.get("detalle", "")},
                     "$inc": {"refuerzos": 1},
                     "$addToSet": {"fuentes": source} if source else {}},
                )
            else:
                await db.investing_knowledge.insert_one({
                    "_key": k, "categoria": cat, "tema": tema,
                    "principio": principio, "detalle": detalle,
                    "refuerzos": 1, "fuentes": [source] if source else [],
                })
            n += 1
        except Exception:
            logger.warning("knowledge: no se pudo guardar aprendizaje '%s'", tema)
    if n:
        await rebuild_cache(db)
    return n


async def rebuild_cache(db) -> str:
    """Reconstruye el digest inyectable desde Mongo. Prioriza los principios más
    reforzados (mencionados por más correos) y respeta el techo de caracteres."""
    global _DIGEST
    try:
        docs = await db.investing_knowledge.find(
            {}, {"_id": 0}
        ).sort("refuerzos", -1).to_list(_MAX_ITEMS)
    except Exception:
        return _DIGEST
    lines, total = [], 0
    for d in docs:
        ref = d.get("refuerzos", 1)
        mark = f" (×{ref})" if ref > 1 else ""
        line = f"- [{d.get('categoria')}] {d.get('principio')}{mark}"
        if total + len(line) > _MAX_DIGEST_CHARS:
            break
        lines.append(line)
        total += len(line)
    _DIGEST = "\n".join(lines)
    logger.info("knowledge: digest reconstruido (%d principios, %d chars)", len(lines), total)
    return _DIGEST


async def ensure_loaded(db):
    """Carga el cache al arrancar si está vacío."""
    if not _DIGEST:
        await rebuild_cache(db)


def digest_for_prompt() -> str:
    """Devuelve el bloque de conocimiento acumulado para añadir al system prompt del
    motor, o cadena vacía si aún no hay nada aprendido."""
    if not _DIGEST:
        return ""
    return (
        "\n\nCONOCIMIENTO ACUMULADO (principios de inversión aprendidos de las newsletters "
        "a las que el usuario está suscrito; aplícalos como criterio adicional en tu análisis, "
        "sin citar fuentes ni reproducir texto literal):\n" + _DIGEST
    )
