"""Ingesta de noticias de mercado → cerebro + Radar.

Cada pocas horas coge los titulares generales del mercado (Finnhub), extrae lo
accionable (tickers con su ángulo) y el método, y lo mete en el Radar y el cerebro
como una fuente más (etiquetada 'Noticias de mercado'). Deduplica por URL para no
reingerir lo mismo.
"""
import asyncio
import logging

logger = logging.getLogger("inveria.news")


async def ingest_general_news(db) -> dict:
    """Procesa los titulares nuevos del mercado (los no vistos antes)."""
    import external_data
    import newsletter_ingest
    noticias = await asyncio.to_thread(external_data.finnhub_general_news, 25)
    if not noticias:
        return {"nuevas": 0, "acciones": 0, "aprendidos": 0}

    cfg = await db.news_config.find_one({"_id": "cfg"}) or {}
    vistas = set(cfg.get("seen_urls") or [])
    nuevos = [n for n in noticias if n.get("url") and n["url"] not in vistas]
    if not nuevos:
        return {"nuevas": 0, "acciones": 0, "aprendidos": 0}

    blob = "\n".join(f"{n.get('title')}. {n.get('summary') or ''}".strip() for n in nuevos)
    r = await newsletter_ingest.ingest_message(db, "Noticias de mercado", blob, tipo="noticias")

    urls = (list(vistas) + [n["url"] for n in nuevos])[-400:]  # conserva las últimas 400
    try:
        await db.news_config.update_one({"_id": "cfg"}, {"$set": {"seen_urls": urls}}, upsert=True)
    except Exception:
        pass
    logger.info("noticias: %d nuevas → %d picks, %d aprendizajes",
                len(nuevos), r.get("acciones", 0), r.get("aprendidos", 0))
    return {"nuevas": len(nuevos), **r}


async def news_worker_loop(db, interval_seconds: int = 6 * 3600, initial_delay: int = 900):
    """Ingesta periódica de noticias (cada ~6 h). Espera un margen inicial tras arrancar."""
    await asyncio.sleep(initial_delay)
    while True:
        try:
            await ingest_general_news(db)
        except Exception:
            logger.exception("noticias: ciclo de ingesta falló")
        await asyncio.sleep(interval_seconds)
