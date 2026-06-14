"""Background worker to evaluate price alerts and send emails via Resend + Telegram."""
import asyncio
import logging
import os
from datetime import datetime, timezone, date, time
from zoneinfo import ZoneInfo
import resend
import market_data
import telegram_notifier

logger = logging.getLogger("alerts_worker")

CHECK_INTERVAL = 60  # seconds
EASTERN = ZoneInfo("America/New_York")


def is_market_open() -> bool:
    """True only during regular US market hours: Mon-Fri 9:30-16:00 ET."""
    now = datetime.now(EASTERN)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return time(9, 30) <= now.time() <= time(16, 0)


def _build_email_html(symbol: str, target: float, direction: str, current_price: float, change_pct):
    dir_text = "POR ENCIMA" if direction == "above" else "POR DEBAJO"
    color = "#4a7c59" if direction == "above" else "#d85c41"
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f3ef;padding:24px;font-family:Arial,sans-serif;color:#0e1f1a;">
      <tr><td>
        <table width="100%" max-width="560" align="center" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e5e0d8;border-radius:8px;padding:32px;">
          <tr><td>
            <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#5c6b66;margin:0 0 8px 0;">InverIA · Alerta de precio</p>
            <h1 style="font-size:24px;margin:0 0 4px 0;color:#0e1f1a;">{symbol} alcanzó tu nivel</h1>
            <p style="font-size:14px;color:#5c6b66;margin:0 0 24px 0;">El precio actual cruzó tu alerta {dir_text} de <strong>${target}</strong>.</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e0d8;border-radius:6px;padding:16px;background:#f5f3ef;">
              <tr>
                <td style="font-family:'Courier New',monospace;font-size:32px;font-weight:bold;color:{color};">${current_price}</td>
                <td align="right" style="font-family:'Courier New',monospace;font-size:14px;color:{color};">{('+' if (change_pct or 0) >= 0 else '')}{change_pct}%</td>
              </tr>
            </table>
            <p style="font-size:12px;color:#5c6b66;margin:24px 0 0 0;">La alerta se reactivará automáticamente mañana si el precio sigue en ese nivel.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
    """


async def send_alert_email(symbol: str, target: float, direction: str, current_price: float, change_pct):
    """Send a price alert email via Resend.
    Returns (ok: bool, error_message: Optional[str])."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY no configurada; saltando email")
        return False, "RESEND_API_KEY no configurada en el servidor."
    resend.api_key = api_key
    recipient = os.environ.get("ALERT_RECIPIENT_EMAIL")
    sender = (
        os.environ.get("ALERT_FROM_EMAIL")
        or os.environ.get("SENDER_EMAIL")
        or "onboarding@resend.dev"
    )
    if not recipient:
        return False, "ALERT_RECIPIENT_EMAIL no configurada en el servidor."
    params = {
        "from": f"InverIA <{sender}>",
        "to": [recipient],
        "subject": f"InverIA · {symbol} ${current_price} ({'≥' if direction == 'above' else '≤'} ${target})",
        "html": _build_email_html(symbol, target, direction, current_price, change_pct),
    }
    try:
        await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Email enviado: {symbol} {direction} {target}")
        return True, None
    except Exception as e:
        err = str(e)
        logger.exception(f"Error enviando email: {err}")
        if "domain is not verified" in err.lower() or "not verified" in err.lower():
            return False, (
                f"El dominio del remitente ({sender}) no está verificado en Resend. "
                "Cambia la variable ALERT_FROM_EMAIL a 'onboarding@resend.dev' en Render, "
                "o verifica tu dominio en https://resend.com/domains"
            )
        if "you can only send testing emails" in err.lower() or "restricted" in err.lower():
            return False, (
                "Con 'onboarding@resend.dev' solo puedes enviar al email registrado en Resend. "
                "Asegúrate de que ALERT_RECIPIENT_EMAIL coincida con tu cuenta Resend."
            )
        return False, f"Resend: {err[:200]}"


async def evaluate_alerts(db):
    """Check active alerts during market hours only.
    Each alert fires at most once per trading day — resets automatically the next day."""
    if not is_market_open():
        return

    today = date.today().isoformat()  # "YYYY-MM-DD" in server local time (UTC on Render)

    # Only check alerts not yet triggered today (triggered:True means permanently dismissed)
    cursor = db.alerts.find({"triggered": False, "last_triggered_date": {"$ne": today}})
    alerts = await cursor.to_list(500)
    if not alerts:
        return

    by_symbol = {}
    for a in alerts:
        by_symbol.setdefault(a["symbol"], []).append(a)

    for symbol, items in by_symbol.items():
        quote = market_data.get_quote(symbol)
        if not quote:
            continue
        price = quote["price"]
        change_pct = quote.get("change_percent")
        for a in items:
            target = float(a["target_price"])
            fired = (
                (a["direction"] == "above" and price >= target)
                or (a["direction"] == "below" and price <= target)
            )
            if fired:
                # Mark triggered for today only — alert resets automatically tomorrow
                await db.alerts.update_one(
                    {"id": a["id"]},
                    {"$set": {
                        "last_triggered_date": today,
                        "triggered_at": datetime.now(timezone.utc).isoformat(),
                        "triggered_price": price,
                    }},
                )
                await asyncio.gather(
                    send_alert_email(symbol, target, a["direction"], price, change_pct),
                    telegram_notifier.send_alert(symbol, target, a["direction"], price, change_pct),
                    return_exceptions=True,
                )


async def alerts_worker_loop(db):
    logger.info("Alerts worker arrancado")
    while True:
        try:
            await evaluate_alerts(db)
        except Exception as e:
            logger.exception(f"Error en ciclo de alertas: {e}")
        await asyncio.sleep(CHECK_INTERVAL)
