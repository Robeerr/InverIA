"""Ingesta de vídeos de YouTube → cerebro + Radar, usando Gemini.

Gemini (de Google) "ve" los vídeos de YouTube nativamente: le pasamos el enlace y él
analiza imagen + audio y devuelve el análisis. Así evitamos descargar el vídeo (que
YouTube bloquea a los servidores). Requiere GEMINI_API_KEY.

Nota: solo vídeos públicos de YouTube. Uso personal; no redistribuir.
"""
import logging
import re

logger = logging.getLogger("inveria.youtube")


def video_id(url: str):
    """Extrae el ID de 11 caracteres de cualquier forma de enlace de YouTube."""
    if not url:
        return None
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    m = re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip())
    return m.group(0) if m else None


def _normalize(url: str) -> str:
    vid = video_id(url)
    return f"https://www.youtube.com/watch?v={vid}" if vid else url


async def ingest_youtube(db, url: str) -> dict:
    """Analiza un vídeo con Gemini y mete picks + método en el cerebro/Radar. Devuelve
    feedback de lo conseguido."""
    import ai_analysis
    import newsletter_ingest
    if not video_id(url):
        return {"ok": False, "error": "No reconozco ese enlace de YouTube."}
    try:
        data = await ai_analysis.analyze_youtube(_normalize(url))
    except Exception as e:
        msg = str(e)
        logger.warning("youtube: Gemini no pudo con el vídeo (%s)", msg[:150])
        if "token count exceeds" in msg or "1048576" in msg:
            return {"ok": False, "error": "El vídeo es demasiado largo para procesarlo de una vez. "
                    "Usa '¿Falla? Pega la transcripción / texto a mano' (abre el vídeo en YouTube → "
                    "Mostrar transcripción → copia y pega)."}
        return {"ok": False, "error": f"Gemini no pudo leer el vídeo: {msg[:160]}"}
    if not isinstance(data, dict) or not (data.get("resumen") or data.get("acciones")):
        return {"ok": False, "error": "Gemini no sacó nada útil del vídeo."}
    fuente = f"YouTube › {(data.get('titulo') or video_id(url))}"[:80]
    r = await newsletter_ingest.store_extracted(db, fuente, data, "youtube")
    return {"ok": True, "via": "Gemini (vídeo)", **r}
