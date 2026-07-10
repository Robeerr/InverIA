"""Ingesta de vídeos de YouTube → cerebro + Radar.

Pegas un enlace, el servidor saca la transcripción (subtítulos si los hay; si no,
descarga el audio y lo transcribe con Whisper) y extrae los picks + el método, igual
que un mensaje o newsletter. Devuelve un feedback de lo que ha conseguido del vídeo.

Nota: se ejecuta en TU backend (Render), que sí puede acceder a YouTube. Descargar de
YouTube es zona gris de sus términos; para uso personal es defendible. No redistribuir.
"""
import asyncio
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


def _captions(vid: str) -> str:
    """Transcripción por subtítulos (rápido). '' si el vídeo no tiene o falla."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return ""
    for langs in (["es"], ["en"], ["es", "en"], None):
        try:
            data = (YouTubeTranscriptApi.get_transcript(vid, languages=langs)
                    if langs else YouTubeTranscriptApi.get_transcript(vid))
            txt = " ".join(x.get("text", "") for x in data).strip()
            if txt:
                return txt
        except Exception:
            continue
    return ""


async def _audio_transcript(vid: str) -> str:
    """Fallback: descarga el audio con yt-dlp y lo transcribe con Whisper (Groq)."""
    try:
        import yt_dlp  # noqa: F401
        import ai_analysis
    except ImportError:
        return ""
    import os
    import tempfile

    def _download():
        tmp = tempfile.mkdtemp()
        out = os.path.join(tmp, "a.%(ext)s")
        opts = {"format": "bestaudio/best", "outtmpl": out, "quiet": True,
                "noplaylist": True, "no_warnings": True}
        try:
            import yt_dlp as y
            with y.YoutubeDL(opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={vid}"])
            for f in os.listdir(tmp):
                p = os.path.join(tmp, f)
                if os.path.getsize(p) < 24 * 1024 * 1024:  # límite Whisper ~25MB
                    with open(p, "rb") as fh:
                        return fh.read(), f
            return None, None
        except Exception:
            return None, None

    audio, fname = await asyncio.to_thread(_download)
    if not audio:
        return ""
    return await ai_analysis.transcribe_audio(audio, fname or "audio.m4a")


async def ingest_youtube(db, url: str) -> dict:
    """Procesa un vídeo: saca transcripción → picks + método → cerebro/Radar. Devuelve
    feedback de lo conseguido."""
    import newsletter_ingest
    vid = video_id(url)
    if not vid:
        return {"ok": False, "error": "No reconozco ese enlace de YouTube."}

    via = "subtítulos"
    text = await asyncio.to_thread(_captions, vid)
    if not text:
        via = "audio (Whisper)"
        text = await _audio_transcript(vid)
    if not text or len(text) < 60:
        return {"ok": False, "error": "No pude obtener la transcripción (sin subtítulos y sin poder bajar el audio). Prueba a pegarme el texto a mano."}

    r = await newsletter_ingest.ingest_message(
        db, f"YouTube › {vid}", text, tipo="youtube")
    return {
        "ok": True, "via": via, "chars": len(text),
        "titulo": r.get("titulo"), "resumen": r.get("resumen"),
        "tickers": r.get("tickers") or [], "acciones": r.get("acciones", 0),
        "aprendidos": r.get("aprendidos", 0),
    }
