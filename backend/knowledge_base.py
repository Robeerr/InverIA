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
_DIGEST = ""            # digest genérico (top por refuerzos) — fallback sin contexto
_ALL: list = []         # TODOS los principios en memoria, para selección por relevancia
_MAX_DIGEST_CHARS = 2600   # techo para no inflar el prompt del motor
_MAX_ITEMS = 40

# Categorías "universales" (disciplina/gestión) que aplican a CUALQUIER operación: se
# reservan siempre un hueco en el digest, pase lo que pase con la relevancia al sector.
_UNIVERSAL = {"riesgo", "psicología", "psicologia", "método", "metodo"}
_STOPWORDS = {"para", "con", "los", "las", "una", "que", "del", "por", "sin", "the",
              "and", "sus", "más", "mas", "como", "este", "esta", "sobre", "entre",
              "puede", "debe", "hacia", "solo", "cada", "ante", "tras", "empresa",
              "acción", "accion", "mercado", "precio", "inversión", "inversion"}


def fix_mojibake(s: str) -> str:
    """Repara texto UTF-8 mal decodificado como Latin-1 (mojibake): 'selecciÃ³n' →
    'selección', 'Ã—4' → '×4', '15â€‘20' → '15‑20'. Solo actúa si detecta las marcas
    típicas del problema, para no romper texto ya correcto."""
    if not s or not isinstance(s, str):
        return s
    if not any(m in s for m in ("Ã", "â€", "Â", "Ã‚")):
        return s

    def _marks(t):
        return t.count("Ã") + t.count("â€") + t.count("Â")

    # El mojibake real suele venir de CP1252 (Windows) — que codifica '×', em‑dash,
    # espacios finos, etc. Se prueba CP1252 y, si no, Latin‑1.
    for enc in ("cp1252", "latin-1"):
        try:
            fixed = s.encode(enc, errors="strict").decode("utf-8", errors="strict")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if _marks(fixed) < _marks(s):
            return fixed
    return s


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
        tema = fix_mojibake((a.get("tema") or "").strip())
        principio = fix_mojibake((a.get("principio") or "").strip())
        if not tema or not principio:
            continue
        cat = fix_mojibake((a.get("categoria") or "método").strip().lower())
        if cat not in _CATEGORIAS:
            cat = "método"
        detalle = fix_mojibake((a.get("detalle") or "").strip())
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
    """Reconstruye el cache en memoria desde Mongo: la lista completa de principios
    (_ALL, para selección por relevancia) y el digest genérico (_DIGEST, fallback por
    refuerzos). Repara mojibake por si algún doc viejo lo tuviera."""
    global _DIGEST, _ALL
    try:
        docs = await db.investing_knowledge.find(
            {}, {"_id": 0}
        ).sort("refuerzos", -1).to_list(2000)
    except Exception:
        return _DIGEST
    _ALL = [{
        "categoria": fix_mojibake(d.get("categoria") or ""),
        "tema": fix_mojibake(d.get("tema") or ""),
        "principio": fix_mojibake(d.get("principio") or ""),
        "detalle": fix_mojibake(d.get("detalle") or ""),
        "refuerzos": d.get("refuerzos", 1),
    } for d in docs if d.get("principio")]
    _DIGEST = _build_digest(_ALL[:_MAX_ITEMS])
    logger.info("knowledge: cache reconstruido (%d principios en memoria)", len(_ALL))
    return _DIGEST


def _line(p: dict) -> str:
    ref = p.get("refuerzos", 1)
    mark = f" (×{ref})" if ref > 1 else ""
    return f"- [{p.get('categoria')}] {p.get('principio')}{mark}"


def _build_digest(items: list) -> str:
    """Une principios en texto respetando el techo de caracteres."""
    lines, total = [], 0
    for p in items:
        line = _line(p)
        if total + len(line) > _MAX_DIGEST_CHARS:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def _tokens(s: str) -> set:
    """Palabras significativas (sin tildes, sin stopwords, len>3) para medir solape."""
    return {w for w in _norm(s).split() if len(w) > 3 and w not in _STOPWORDS}


async def fix_existing_encoding(db) -> dict:
    """Repara el mojibake de los principios YA guardados (los del backfill inicial) y
    reconstruye el cache. Devuelve cuántos se corrigieron."""
    try:
        docs = await db.investing_knowledge.find({}).to_list(2000)
    except Exception:
        return {"revisados": 0, "corregidos": 0}
    corregidos = 0
    for d in docs:
        campos = {}
        for k in ("categoria", "tema", "principio", "detalle"):
            v = d.get(k)
            nv = fix_mojibake(v) if isinstance(v, str) else v
            if nv != v:
                campos[k] = nv
        if campos:
            # Si cambió la categoría/tema, recalcula la clave para no dejar duplicados sucios.
            cat = campos.get("categoria", d.get("categoria"))
            tema = campos.get("tema", d.get("tema"))
            campos["_key"] = _key(cat, tema)
            try:
                await db.investing_knowledge.update_one(
                    {"_id": d["_id"]}, {"$set": campos})
                corregidos += 1
            except Exception:
                pass
    await rebuild_cache(db)
    return {"revisados": len(docs), "corregidos": corregidos}


async def ensure_loaded(db):
    """Carga el cache al arrancar si está vacío."""
    if not _ALL:
        await rebuild_cache(db)


def _select_relevant(context: str) -> list:
    """Elige los principios más relevantes para el contexto (sector/situación de la
    acción): reserva un hueco para disciplina/gestión (universales, por refuerzos) y
    llena el resto con los que más solapan con el contexto. Sin contexto → top general."""
    if not _ALL:
        return []
    universal = [p for p in _ALL if p.get("categoria") in _UNIVERSAL]
    contextual = [p for p in _ALL if p.get("categoria") not in _UNIVERSAL]
    universal.sort(key=lambda p: p.get("refuerzos", 1), reverse=True)

    ctx = _tokens(context)
    if ctx:
        def rel(p):
            toks = _tokens(f"{p.get('tema','')} {p.get('principio','')} "
                           f"{p.get('detalle','')} {p.get('categoria','')}")
            return len(toks & ctx)
        # Relevancia primero; a igualdad, los más reforzados.
        contextual.sort(key=lambda p: (rel(p), p.get("refuerzos", 1)), reverse=True)
    else:
        contextual.sort(key=lambda p: p.get("refuerzos", 1), reverse=True)

    # ~1/3 disciplina universal + 2/3 relevantes al sector (intercalados, sin repetir).
    picked, seen = [], set()
    for p in universal[:8] + contextual[:24]:
        key = (p.get("categoria"), p.get("tema"))
        if key not in seen:
            seen.add(key)
            picked.append(p)
    return picked


def digest_for_prompt(context: str = "") -> str:
    """Bloque de conocimiento para el system prompt del motor. Si se pasa `context`
    (p.ej. nombre/sector/situación de la acción), selecciona los principios relevantes;
    si no, usa el digest genérico. Cadena vacía si aún no hay nada aprendido."""
    if not _ALL:
        return ""
    body = _build_digest(_select_relevant(context)) if context else _DIGEST
    if not body:
        return ""
    return (
        "\n\nCONOCIMIENTO ACUMULADO (principios de inversión aprendidos de las newsletters "
        "a las que el usuario está suscrito; aplícalos como criterio adicional en tu análisis, "
        "sin citar fuentes ni reproducir texto literal):\n" + body
    )
