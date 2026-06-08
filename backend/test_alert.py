import os, requests
from dotenv import load_dotenv
load_dotenv()

token = os.environ.get("TELEGRAM_BOT_TOKEN")
chat_id = os.environ.get("TELEGRAM_CHAT_ID")

if not token or not chat_id:
    print("ERROR: TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados en .env")
    exit(1)

def send(msg):
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": msg, "parse_mode": "MarkdownV2", "disable_web_page_preview": True},
        timeout=10
    )
    print(r.status_code, r.json().get("description", "OK"))

# Test COMPRA
send(
    "🟢🟢🟢 *ALERTA DE COMPRA* 🟢🟢🟢\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "📌 *ORACLE \\(ORCL\\)*\n"
    "🏛️ NYSE · TECH · Riesgo MEDIO\n\n"
    "💰 *Precio actual: \\$221\\.50*\n"
    "🎯 *Nivel 1: \\$220\\.00*\n\n"
    "📊 Diferencia: *\\+0\\.68%*\n"
    "📈 Posible ganancia: *\\+39\\.39%*\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "⚡ _InverIA · Alerta automática_"
)

# Test VENTA
send(
    "🔴🔴🔴 *ALERTA DE VENTA* 🔴🔴🔴\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "📌 *ORACLE \\(ORCL\\)*\n"
    "🏛️ NYSE · TECH · Riesgo MEDIO\n\n"
    "💸 *Precio actual: \\$299\\.80*\n"
    "🏁 *Deseado / Venta: \\$300\\.00*\n\n"
    "📊 Diferencia: *\\-0\\.07%*\n"
    "📈 Ganancia realizada: *\\+39\\.39%*\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "⚡ _InverIA · Alerta automática_"
)
