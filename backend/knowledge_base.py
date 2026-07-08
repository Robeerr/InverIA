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
            # Si no hay coincidencia exacta de tema, busca un principio casi idéntico ya
            # guardado (mismo significado, otras palabras) para reforzarlo en vez de crear
            # un duplicado. Evita que "gestión de stops" y "uso de stop-loss" se separen.
            if not existing:
                simk = _find_similar_key(cat, principio)
                if simk:
                    k = simk
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


def _sim(a: set, b: set) -> float:
    """Similitud de Jaccard entre dos conjuntos de palabras (0..1)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_SIM_THRESHOLD = 0.6   # a partir de aquí dos principios se consideran "lo mismo"


def _find_similar_key(cat: str, principio: str):
    """Busca en el cache un principio de la MISMA categoría casi idéntico al dado.
    Devuelve su _key para reforzarlo, o None. Usa _ALL (memoria), sin tocar la BD."""
    toks = _tokens(principio)
    if not toks or not _ALL:
        return None
    ncat = _norm(cat)
    best_key, best_sim = None, _SIM_THRESHOLD
    for p in _ALL:
        if _norm(p.get("categoria") or "") != ncat:
            continue
        sim = _sim(toks, _tokens(p.get("principio") or ""))
        if sim >= best_sim:
            best_sim, best_key = sim, _key(p.get("categoria") or "", p.get("tema") or "")
    return best_key


async def dedupe_semantic(db, threshold: float = _SIM_THRESHOLD) -> dict:
    """Fusiona principios casi idénticos ya guardados (mismo significado, otras palabras),
    dentro de la misma categoría: se queda el más reforzado, le suma los refuerzos de los
    demás, conserva el texto más completo y borra los duplicados. Reconstruye el cache."""
    try:
        docs = await db.investing_knowledge.find({}).to_list(4000)
    except Exception:
        return {"fusiones": 0, "eliminados": 0, "restantes": 0}
    by_cat = {}
    for d in docs:
        by_cat.setdefault(_norm(d.get("categoria") or ""), []).append(d)

    fusiones, eliminados = 0, 0
    for _cat, items in by_cat.items():
        items.sort(key=lambda d: d.get("refuerzos", 1), reverse=True)
        used = [False] * len(items)
        for i in range(len(items)):
            if used[i]:
                continue
            rep = items[i]
            ti = _tokens(rep.get("principio") or "")
            ref = rep.get("refuerzos", 1)
            mejor = rep.get("principio") or ""
            detalle = rep.get("detalle") or ""
            fuentes = set(rep.get("fuentes") or [])
            borrar = []
            for j in range(i + 1, len(items)):
                if used[j]:
                    continue
                if _sim(ti, _tokens(items[j].get("principio") or "")) >= threshold:
                    used[j] = True
                    ref += items[j].get("refuerzos", 1)
                    cand = items[j].get("principio") or ""
                    if len(cand) > len(mejor):
                        mejor = cand
                    detalle = detalle or (items[j].get("detalle") or "")
                    fuentes |= set(items[j].get("fuentes") or [])
                    borrar.append(items[j]["_id"])
            if borrar:
                try:
                    await db.investing_knowledge.update_one(
                        {"_id": rep["_id"]},
                        {"$set": {"principio": mejor, "detalle": detalle,
                                  "refuerzos": ref, "fuentes": list(fuentes)}})
                    await db.investing_knowledge.delete_many({"_id": {"$in": borrar}})
                    fusiones += 1
                    eliminados += len(borrar)
                except Exception:
                    logger.warning("dedupe: fallo fusionando un cluster")
    await rebuild_cache(db)
    restantes = await db.investing_knowledge.count_documents({})
    return {"fusiones": fusiones, "eliminados": eliminados, "restantes": restantes}


_DEDUP_LLM_PROMPT = """Te doy una lista NUMERADA de principios de inversión de la misma categoría.
Tu tarea: agrupar los que expresan LA MISMA idea, aunque estén redactados con distintas palabras.
Devuelve SOLO JSON válido (sin markdown): {"grupos": [[1,5,9],[2,7]]}, donde cada sublista son los
números (empezando en 1) de principios que son DUPLICADOS entre sí.
REGLAS ESTRICTAS:
- Agrupa únicamente si de verdad significan lo MISMO (misma recomendación accionable).
- Principios sobre aspectos DISTINTOS NO se agrupan, aunque compartan tema (p.ej. "poner stop por ATR"
  y "subir el stop para proteger ganancias" son DISTINTOS: no los agrupes).
- Los principios sin duplicado no aparecen en la respuesta.
- No inventes números fuera del rango de la lista."""


async def _llm_clusters(principios: list) -> list:
    """Pide al LLM que agrupe principios equivalentes. Devuelve lista de grupos de
    índices base-0 validados. Ante cualquier error, devuelve [] (no fusiona nada)."""
    import ai_analysis
    listado = "\n".join(f"{i+1}. {p}" for i, p in enumerate(principios))
    try:
        data = await ai_analysis._run_model(
            "gpt-oss-120b", _DEDUP_LLM_PROMPT, listado, max_tokens=1500)
    except Exception:
        return []
    grupos = []
    for g in (data or {}).get("grupos") or []:
        # Valida: índices en rango, únicos, grupo de 2+.
        idx = sorted({int(x) - 1 for x in g if isinstance(x, (int, float))
                      and 1 <= int(x) <= len(principios)})
        if len(idx) >= 2:
            grupos.append(idx)
    return grupos


async def dedupe_semantic_llm(db) -> dict:
    """Dedup SEMÁNTICO con LLM (entiende paráfrasis). Por cada categoría, pide al modelo
    que agrupe principios equivalentes y funde cada grupo (conserva el más reforzado,
    suma refuerzos, texto más completo, une fuentes). Pasada puntual. Reconstruye cache."""
    try:
        docs = await db.investing_knowledge.find({}).to_list(4000)
    except Exception:
        return {"fusiones": 0, "eliminados": 0, "restantes": 0}
    by_cat = {}
    for d in docs:
        by_cat.setdefault(_norm(d.get("categoria") or ""), []).append(d)

    fusiones, eliminados = 0, 0
    for _cat, items in by_cat.items():
        if len(items) < 2:
            continue
        principios = [i.get("principio") or "" for i in items]
        grupos = await _llm_clusters(principios)
        usados = set()
        for grupo in grupos:
            grupo = [j for j in grupo if j not in usados]
            if len(grupo) < 2:
                continue
            # Representante: el de más refuerzos del grupo.
            grupo.sort(key=lambda j: items[j].get("refuerzos", 1), reverse=True)
            rep = items[grupo[0]]
            ref = rep.get("refuerzos", 1)
            mejor = rep.get("principio") or ""
            detalle = rep.get("detalle") or ""
            fuentes = set(rep.get("fuentes") or [])
            borrar = []
            for j in grupo[1:]:
                usados.add(j)
                ref += items[j].get("refuerzos", 1)
                cand = items[j].get("principio") or ""
                if len(cand) > len(mejor):
                    mejor = cand
                detalle = detalle or (items[j].get("detalle") or "")
                fuentes |= set(items[j].get("fuentes") or [])
                borrar.append(items[j]["_id"])
            usados.add(grupo[0])
            if borrar:
                try:
                    await db.investing_knowledge.update_one(
                        {"_id": rep["_id"]},
                        {"$set": {"principio": mejor, "detalle": detalle,
                                  "refuerzos": ref, "fuentes": list(fuentes)}})
                    await db.investing_knowledge.delete_many({"_id": {"$in": borrar}})
                    fusiones += 1
                    eliminados += len(borrar)
                except Exception:
                    logger.warning("dedupe-llm: fallo fusionando un cluster")
    await rebuild_cache(db)
    restantes = await db.investing_knowledge.count_documents({})
    return {"fusiones": fusiones, "eliminados": eliminados, "restantes": restantes}


async def maintenance_loop(db, interval_seconds: int = 7 * 24 * 3600,
                           initial_delay: int = 24 * 3600):
    """Mantenimiento periódico del cerebro: ejecuta el dedup semántico con LLM cada
    ~semana, solo, para consolidar los principios que van entrando con las newsletters.
    Espera un margen inicial para no dispararse en cada redeploy (gastaría tokens)."""
    import asyncio
    await asyncio.sleep(initial_delay)
    while True:
        try:
            res = await dedupe_semantic_llm(db)
            logger.info("mantenimiento cerebro (dedup LLM semanal): %s", res)
        except Exception:
            logger.exception("mantenimiento cerebro: dedup semanal falló")
        await asyncio.sleep(interval_seconds)


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
