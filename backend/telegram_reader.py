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

# El listado de TEMAS (topics) cambia de sitio según la versión de Telethon
# (functions.channels o functions.messages). Se resuelve dinámicamente probando ambas,
# para no depender de una ruta fija ni tumbar todo Telethon si no está.
def _resolve_forum_topics():
    try:
        from telethon.tl import functions
    except Exception:
        return None, None
    for modname, param in (("channels", "channel"), ("messages", "peer")):
        mod = getattr(functions, modname, None)
        cls = getattr(mod, "GetForumTopicsRequest", None) if mod else None
        if cls is not None:
            return cls, param
    return None, None


GetForumTopicsRequest, _FORUM_PARAM = _resolve_forum_topics()


def _msg_topic_id(message):
    """ID del tema (topic) al que pertenece un mensaje en un grupo con Temas, o None."""
    r = getattr(message, "reply_to", None)
    if r and getattr(r, "forum_topic", False):
        return getattr(r, "reply_to_top_id", None) or getattr(r, "reply_to_msg_id", None) or 1
    # En un foro, un mensaje sin reply_to pertenece al tema "General" (id 1).
    return None


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


# --- Cliente ÚNICO persistente ---
# Telethon NO tolera que la misma sesión se conecte/desconecte desde varios sitios:
# Telegram detecta la clave duplicada y la invalida. Por eso usamos UN solo cliente vivo,
# compartido por el login, el listado y el worker.
_shared = {"client": None, "phone": None, "handler_added": False}
_capture_claves: list = []


async def _get_shared_client(db):
    """Devuelve el cliente persistente conectado y autorizado, o None si no hay sesión
    válida (habría que hacer login)."""
    c = _shared.get("client")
    if c is not None:
        try:
            if c.is_connected() and await c.is_user_authorized():
                return c
        except Exception:
            pass
    if not TELETHON_AVAILABLE:
        return None
    cfg = await _load_cfg(db)
    session_str = cfg.get("session")
    api_id, api_hash = _api_creds()
    if not session_str or not api_id or not api_hash:
        return None
    c = TelegramClient(StringSession(session_str), api_id, api_hash)
    await c.connect()
    if not await c.is_user_authorized():
        await c.disconnect()
        _shared["client"] = None
        return None
    _shared["client"] = c
    return c


async def login_start(phone: str) -> dict:
    """Paso 1: pide a Telegram que envíe el código. Deja el cliente vivo (compartido)."""
    if not TELETHON_AVAILABLE:
        return {"ok": False, "error": "telethon no instalada en el servidor"}
    api_id, api_hash = _api_creds()
    if not api_id or not api_hash:
        return {"ok": False, "error": "Falta TELEGRAM_API_ID / TELEGRAM_API_HASH en Render"}
    # Cierra cualquier cliente previo para no duplicar conexiones.
    old = _shared.get("client")
    if old is not None:
        try:
            await old.disconnect()
        except Exception:
            pass
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
    except Exception as e:
        await client.disconnect()
        return {"ok": False, "error": f"No se pudo enviar el código: {e}"}
    _shared["client"] = client
    _shared["phone"] = phone
    _shared["phone_code_hash"] = sent.phone_code_hash
    _shared["handler_added"] = False
    return {"ok": True, "mensaje": "Código enviado. Míralo en Telegram."}


async def login_code(db, code: str, password: str = "") -> dict:
    """Paso 2: completa el login. NO desconecta: deja el cliente vivo y guarda la sesión."""
    client = _shared.get("client")
    phone = _shared.get("phone")
    if not client:
        return {"ok": False, "error": "No hay login en curso. Empieza por el paso del teléfono."}
    try:
        try:
            await client.sign_in(phone, code, phone_code_hash=_shared.get("phone_code_hash"))
        except SessionPasswordNeededError:
            if not password:
                return {"ok": False, "error": "Tienes verificación en 2 pasos: manda también tu contraseña."}
            await client.sign_in(password=password)
        await _save_cfg(db, session=client.session.save())
        me = await client.get_me()
        # El cliente ya autorizado queda como el compartido (vivo).
        return {"ok": True, "cuenta": getattr(me, "username", None) or getattr(me, "first_name", "?"),
                "mensaje": "Conectado. Ahora elige los temas."}
    except Exception as e:
        return {"ok": False, "error": f"Login falló: {e}"}


async def list_dialogs(db) -> dict:
    """Lista los canales/grupos que ve tu cuenta. Si un grupo tiene TEMAS (topics), los
    despliega uno a uno para que elijas solo los de los jefes e ignores el ruido. Cada
    elemento tiene una 'clave': 'chatid' (canal entero) o 'chatid/topicid' (un tema)."""
    client = await _get_shared_client(db)
    if not client:
        return {"ok": False, "error": "Sin sesión válida. Vuelve a hacer login (teléfono + código)."}
    cfg = await _load_cfg(db)
    activos = set(cfg.get("capture") or [])
    items = []
    if True:
        async for d in client.iter_dialogs():
            if not (d.is_channel or d.is_group):
                continue
            ent = d.entity
            es_foro = bool(getattr(ent, "forum", False)) and GetForumTopicsRequest is not None
            if es_foro:
                # Grupo con Temas: lista cada tema como elemento elegible.
                try:
                    kwargs = {_FORUM_PARAM: ent, "offset_date": 0, "offset_id": 0,
                              "offset_topic": 0, "limit": 100}
                    res = await client(GetForumTopicsRequest(**kwargs))
                    for t in res.topics:
                        title = getattr(t, "title", None) or f"Tema {t.id}"
                        clave = f"{d.id}/{t.id}"
                        items.append({
                            "id": clave, "nombre": f"{d.name} › {title}",
                            "tipo": "tema", "capturando": clave in activos,
                        })
                except Exception:
                    logger.warning("telegram: no se pudieron listar temas de %s", d.name)
                    clave = str(d.id)
                    items.append({"id": clave, "nombre": d.name or "(sin nombre)",
                                  "tipo": "grupo", "capturando": clave in activos})
            else:
                clave = str(d.id)
                items.append({
                    "id": clave, "nombre": d.name or "(sin nombre)",
                    "tipo": "canal" if d.is_channel and not d.is_group else "grupo",
                    "capturando": clave in activos,
                })
    return {"ok": True, "canales": items, "capturando_ahora": sorted(activos)}


async def set_capture(db, claves: list) -> dict:
    """Fija la lista blanca de temas/canales a capturar. Activa el lector al momento."""
    global _capture_claves
    limpio = [str(x) for x in (claves or []) if str(x).strip()]
    await _save_cfg(db, capture=limpio)
    _capture_claves = limpio
    await activate(db)  # asegura cliente + handler con la lista nueva
    return {"ok": True, "capturando": limpio}


def _parse_claves(claves):
    """Convierte claves en: set de chat_ids a escuchar y set de 'chatid/topicid' permitidos.
    Si una clave es solo 'chatid', se captura TODO ese chat."""
    chats, topics, chats_enteros = set(), set(), set()
    for k in claves or []:
        if "/" in str(k):
            cid, tid = str(k).split("/", 1)
            try:
                chats.add(int(cid)); topics.add(f"{int(cid)}/{int(tid)}")
            except ValueError:
                pass
        else:
            try:
                cid = int(k); chats.add(cid); chats_enteros.add(cid)
            except ValueError:
                pass
    return chats, topics, chats_enteros


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


# --- Activación del lector: registra el handler UNA vez sobre el cliente compartido ---
async def _handler(event):
    """Filtra dinámicamente por la lista blanca en memoria (_capture_claves) y procesa."""
    db = _shared.get("db")
    if db is None:
        return
    chats, topics, chats_enteros = _parse_claves(_capture_claves)
    try:
        cid = event.chat_id
        if cid not in chats:
            return
        if cid not in chats_enteros:
            tid = _msg_topic_id(event.message)
            if tid is None or f"{cid}/{tid}" not in topics:
                return  # tema no elegido → ruido, ignorar
        chat = await event.get_chat()
        name = getattr(chat, "title", None) or getattr(chat, "username", "?")
        await _process_message(db, _shared["client"], event.message, name)
    except Exception:
        logger.warning("telegram: fallo en el handler de mensaje")


async def activate(db):
    """Asegura el cliente compartido conectado y el handler registrado (una sola vez).
    El cliente vive dentro del event loop de FastAPI y recibe updates en segundo plano;
    no hace falta run_until_disconnected. Modo pasivo: solo lee."""
    global _capture_claves
    if not TELETHON_AVAILABLE:
        return
    _shared["db"] = db
    cfg = await _load_cfg(db)
    _capture_claves = cfg.get("capture") or _capture_claves
    if not cfg.get("session") or not _capture_claves:
        logger.info("telegram: sin sesión o sin temas elegidos; lector en espera")
        return
    client = await _get_shared_client(db)
    if not client:
        logger.warning("telegram: sin sesión válida; hace falta re-login")
        return
    if not _shared.get("handler_added"):
        client.add_event_handler(_handler, events.NewMessage())
        _shared["handler_added"] = True
    chats, topics, _ = _parse_claves(_capture_claves)
    logger.info("telegram: lector activo (%d chats, %d temas)", len(chats), len(topics))


# Compat: el lifespan sigue llamando a reader_worker_loop.
async def reader_worker_loop(db):
    await activate(db)


async def status(db) -> dict:
    cfg = await _load_cfg(db)
    api_id, api_hash = _api_creds()
    conectado = False
    c = _shared.get("client")
    try:
        conectado = bool(c and c.is_connected())
    except Exception:
        conectado = False
    ver = "?"
    try:
        import telethon as _t
        ver = getattr(_t, "__version__", "?")
    except Exception:
        pass
    return {
        "telethon_instalada": TELETHON_AVAILABLE,
        "telethon_version": ver,
        "temas_soportados": GetForumTopicsRequest is not None,
        "credenciales_api": bool(api_id and api_hash),
        "sesion_guardada": bool(cfg.get("session")),
        "cliente_conectado": conectado,
        "handler_activo": bool(_shared.get("handler_added")),
        "canales_capturando": cfg.get("capture") or [],
    }
