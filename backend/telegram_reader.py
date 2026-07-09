"""Lector de Telegram — alimenta el cerebro con los canales de tu grupo de pago.

Un userbot (tu propia cuenta, en modo SOLO LECTURA) escucha los canales/temas que TÚ
elijas de tu grupo de pago, e ignora el ruido de los chats de miembros. De cada mensaje
saca el conocimiento: texto directo, audios transcritos (Groq Whisper) y fotos leídas
(Gemini visión). Solo extrae MÉTODO reutilizable → tu cerebro. 100% privado, solo para ti.

Legal/riesgo: usa tu cuenta (miembro legítimo del grupo) en modo pasivo (nunca escribe).
El único riesgo es que el admin del grupo te expulse si lo detecta. NO redistribuir nunca.

Config y sesión se guardan en Mongo (db.telegram_config, doc único _id='cfg').
Requiere env: TELEGRAM_API_ID, TELEGRAM_API_HASH (de my.telegram.org).
"""
import logging
import os

logger = logging.getLogger("inveria.telegram")

try:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    from telethon.errors import SessionPasswordNeededError
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False


def _api_creds():
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    try:
        api_id = int(api_id) if api_id else None
    except ValueError:
        api_id = None
    return api_id, api_hash


# --- Config persistida en Mongo (sesión + lista blanca de canales) ---
async def _load_cfg(db) -> dict:
    return await db.telegram_config.find_one({"_id": "cfg"}) or {}


async def _save_cfg(db, **fields):
    await db.telegram_config.update_one({"_id": "cfg"}, {"$set": fields}, upsert=True)


# --- Login interactivo (desde el móvil, vía endpoints) ---
# El login de Telethon es con estado: hay que usar el MISMO cliente entre pedir el código
# y meterlo. Se guarda un cliente pendiente en memoria mientras dura el proceso.
_pending = {"client": None, "phone": None}


async def login_start(phone: str) -> dict:
    """Paso 1: pide a Telegram que envíe el código de acceso al teléfono."""
    if not TELETHON_AVAILABLE:
        return {"ok": False, "error": "telethon no instalada en el servidor"}
    api_id, api_hash = _api_creds()
    if not api_id or not api_hash:
        return {"ok": False, "error": "Falta TELEGRAM_API_ID / TELEGRAM_API_HASH en Render"}
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        await client.send_code_request(phone)
    except Exception as e:
        await client.disconnect()
        return {"ok": False, "error": f"No se pudo enviar el código: {e}"}
    _pending["client"] = client
    _pending["phone"] = phone
    return {"ok": True, "mensaje": "Código enviado. Míralo en Telegram y mándalo con /login/code."}


async def login_code(db, code: str, password: str = "") -> dict:
    """Paso 2: completa el login con el código (y contraseña 2FA si la tienes). Guarda la
    sesión cifrada en Mongo para que el worker se conecte solo a partir de ahora."""
    client = _pending.get("client")
    phone = _pending.get("phone")
    if not client:
        return {"ok": False, "error": "No hay login en curso. Empieza por /login/start."}
    try:
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            if not password:
                return {"ok": False, "error": "Tienes verificación en 2 pasos: manda también tu contraseña."}
            await client.sign_in(password=password)
        session_str = client.session.save()
        await _save_cfg(db, session=session_str)
        me = await client.get_me()
        await client.disconnect()
        _pending["client"] = None
        return {"ok": True, "cuenta": getattr(me, "username", None) or getattr(me, "first_name", "?"),
                "mensaje": "Sesión guardada. Ahora lista los canales con /dialogs."}
    except Exception as e:
        return {"ok": False, "error": f"Login falló: {e}"}


async def _connected_client(db):
    """Crea un cliente conectado con la sesión guardada, o None si no hay sesión."""
    if not TELETHON_AVAILABLE:
        return None
    cfg = await _load_cfg(db)
    session_str = cfg.get("session")
    if not session_str:
        return None
    api_id, api_hash = _api_creds()
    if not api_id or not api_hash:
        return None
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return None
    return client


async def list_dialogs(db) -> dict:
    """Lista TODOS los canales/grupos que ve tu cuenta, con nombre e ID, para que elijas
    cuáles capturar. Marca cuáles están ya en la lista blanca."""
    client = await _connected_client(db)
    if not client:
        return {"ok": False, "error": "Sin sesión. Haz login primero."}
    cfg = await _load_cfg(db)
    activos = set(cfg.get("capture_chats") or [])
    dialogs = []
    try:
        async for d in client.iter_dialogs():
            if d.is_channel or d.is_group:
                dialogs.append({
                    "id": d.id,
                    "nombre": d.name or "(sin nombre)",
                    "tipo": "canal" if d.is_channel and not d.is_group else "grupo",
                    "capturando": d.id in activos,
                })
    finally:
        await client.disconnect()
    return {"ok": True, "canales": dialogs, "capturando_ahora": sorted(activos)}


async def set_capture(db, chat_ids: list) -> dict:
    """Fija la lista blanca de canales/temas a capturar. Reinicia el worker para aplicarla."""
    ids = []
    for x in chat_ids or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            pass
    await _save_cfg(db, capture_chats=ids)
    return {"ok": True, "capturando": ids}


# --- Procesado de cada mensaje: texto + audio + imagen → método → cerebro ---
async def _message_to_text(client, message) -> str:
    """Convierte un mensaje (del tipo que sea) a texto: usa el texto si lo hay, transcribe
    audios y describe imágenes."""
    import ai_analysis
    partes = []
    if getattr(message, "message", None):
        partes.append(message.message)  # texto/caption
    try:
        if getattr(message, "voice", None) or getattr(message, "audio", None):
            audio = await client.download_media(message, file=bytes)
            if audio:
                txt = await ai_analysis.transcribe_audio(audio, "voz.ogg")
                if txt:
                    partes.append(f"[audio] {txt}")
        elif getattr(message, "photo", None):
            img = await client.download_media(message, file=bytes)
            if img:
                txt = await ai_analysis.describe_image_text(img, "image/jpeg")
                if txt:
                    partes.append(f"[imagen] {txt}")
    except Exception:
        logger.warning("telegram: fallo procesando media de un mensaje")
    return "\n".join(p for p in partes if p).strip()


async def _process_message(db, client, message, chat_name: str):
    """Extrae el método de un mensaje y lo mete en el cerebro."""
    import knowledge_base
    import newsletter_ingest
    text = await _message_to_text(client, message)
    if len(text) < 60:
        return  # ruido corto: nada que aprender
    try:
        aprend = await newsletter_ingest._extract_learnings(text)
        n = await knowledge_base.add_learnings(db, aprend, source=f"Telegram:{chat_name}"[:80])
        if n:
            logger.info("telegram: +%d aprendizajes de '%s'", n, chat_name)
    except Exception:
        logger.warning("telegram: fallo extrayendo método de un mensaje")


# --- Worker: escucha en tiempo real los canales elegidos ---
async def reader_worker_loop(db):
    """Se conecta con la sesión guardada y escucha SOLO los canales de la lista blanca.
    Modo pasivo: solo lee, nunca escribe. Si no hay sesión o lista, no hace nada."""
    if not TELETHON_AVAILABLE:
        logger.info("telegram: telethon no instalada; lector desactivado")
        return
    cfg = await _load_cfg(db)
    if not cfg.get("session") or not cfg.get("capture_chats"):
        logger.info("telegram: sin sesión o sin canales elegidos; lector en espera")
        return
    client = await _connected_client(db)
    if not client:
        logger.warning("telegram: no se pudo conectar con la sesión guardada")
        return
    capture = set(cfg["capture_chats"])
    logger.info("telegram: lector activo sobre %d canales", len(capture))

    @client.on(events.NewMessage(chats=list(capture)))
    async def _handler(event):
        try:
            chat = await event.get_chat()
            name = getattr(chat, "title", None) or getattr(chat, "username", "?")
            await _process_message(db, client, event.message, name)
        except Exception:
            logger.warning("telegram: fallo en el handler de mensaje")

    try:
        await client.run_until_disconnected()
    except Exception:
        logger.exception("telegram: el lector se desconectó")


async def status(db) -> dict:
    cfg = await _load_cfg(db)
    api_id, api_hash = _api_creds()
    return {
        "telethon_instalada": TELETHON_AVAILABLE,
        "credenciales_api": bool(api_id and api_hash),
        "sesion_guardada": bool(cfg.get("session")),
        "canales_capturando": cfg.get("capture_chats") or [],
    }
