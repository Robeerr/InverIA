"""Telegram notifications via Bot API (one-way push to user's chat).

Setup:
1. User creates a bot via @BotFather → gets TELEGRAM_BOT_TOKEN
2. User starts the bot (sends any message to it) so it can reply
3. User opens https://api.telegram.org/bot<TOKEN>/getUpdates → gets chat.id
4. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars

No SDK dependency — plain HTTP via requests.
"""
import asyncio
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger("inveria.telegram")

API_BASE = "https://api.telegram.org"


def _esc_md(text: str) -> str:
    """Escape Telegram MarkdownV2 reserved characters."""
    if not text:
        return ""
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _send_sync(token: str, chat_id: str, text: str, parse_mode: str = "MarkdownV2") -> tuple[bool, Optional[str]]:
    try:
        r = requests.post(
            f"{API_BASE}/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if r.status_code == 200:
            return True, None
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return False, d.get("description") or f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:200]


def _creds_for_group(grupo: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Devuelve (token, chat_id) del bot según el grupo de la señal.
    'cimientos' usa su propio bot; si no está configurado, cae al bot por defecto.
    Cualquier otro grupo (Cartera / ideas_javi) usa el bot por defecto."""
    if grupo == "cimientos":
        token = os.environ.get("TELEGRAM_BOT_TOKEN_CIMIENTOS") or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID_CIMIENTOS") or os.environ.get("TELEGRAM_CHAT_ID")
        return token, chat_id
    return os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")


async def send_message(text: str, parse_mode: str = "MarkdownV2", grupo: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Send a plain notification through the bot for `grupo`. Returns (ok, error_message)."""
    token, chat_id = _creds_for_group(grupo)
    if not token or not chat_id:
        which = "de Cimientos" if grupo == "cimientos" else "por defecto"
        return False, f"Bot de Telegram {which} no configurado en el servidor (token/chat_id)."
    return await asyncio.to_thread(_send_sync, token, chat_id, text, parse_mode)


def format_alert_message(symbol: str, target: float, direction: str, current_price: float, change_pct) -> str:
    """Build a clean MarkdownV2 alert message."""
    dir_emoji = "🟢" if direction == "above" else "🔴"
    dir_word = "POR ENCIMA" if direction == "above" else "POR DEBAJO"
    op = "≥" if direction == "above" else "≤"
    change_str = f"{'+' if (change_pct or 0) >= 0 else ''}{change_pct}%" if change_pct is not None else "—"
    msg = (
        f"{dir_emoji} *Alerta InverIA · {_esc_md(symbol)}*\n\n"
        f"Precio actual: *${_esc_md(str(current_price))}* \\({_esc_md(change_str)}\\)\n"
        f"Cruzó tu objetivo {dir_word} {op} *${_esc_md(str(target))}*"
    )
    return msg


async def send_alert(symbol: str, target: float, direction: str, current_price: float, change_pct) -> tuple[bool, Optional[str]]:
    """Send a formatted price-alert notification."""
    return await send_message(format_alert_message(symbol, target, direction, current_price, change_pct))


async def send_test(grupo: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Manual test notification (al bot del grupo indicado)."""
    nombre = "Cimientos" if grupo == "cimientos" else "Cartera"
    text = (
        f"✅ *InverIA · Test {_esc_md(nombre)}*\n\n"
        "Telegram funcionando correctamente\\.\n"
        f"Aquí recibirás las alertas de *{_esc_md(nombre)}* en tiempo real\\."
    )
    return await send_message(text, grupo=grupo)
