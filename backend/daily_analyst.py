"""Analista Institucional — Capa 1.

Vigía que, durante el horario de mercado, rastrea el universo buscando CONFLUENCIA
DE CATALIZADORES de alta señal (los que usan los fondos serios, todos públicos):

  • Insiders comprando (directivos comprando SU propia acción — la señal nº1)
  • Upgrades de analistas (el consenso de Wall Street mejorando este mes)
  • Earnings recientes batidos
  • El score de potencial del motor (crecimiento + valoración + tendencia)

Solo avisa por Telegram cuando una acción reúne CONVICCIÓN ALTA y no se ha avisado
hace poco (cooldown), para que sea señal, no spam. Cada idea se guarda en histórico.

NO es una máquina de acertar: entrega candidatas MUY bien fundamentadas para que el
usuario decida. Las capas 2 (investigación web) y 3 (newsletters) se montan encima.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import os

import external_data
import market_data
import opportunities
import telegram_notifier

try:
    import resend
except ImportError:
    resend = None

logger = logging.getLogger("inveria.daily_analyst")

EASTERN = ZoneInfo("America/New_York")

# No volver a avisar de la misma acción en este nº de días (evita repetir la misma idea).
_COOLDOWN_DAYS = 7
# Umbral de convicción para disparar el aviso. Alto a propósito: preferimos pocas y buenas.
_CONVICTION_THRESHOLD = 65
# Cuántas ideas como mucho por barrido (evita avalancha si un día hay muchas señales).
_MAX_ALERTS_PER_SCAN = 4

_scan_lock = asyncio.Lock()


def is_market_open() -> bool:
    """True solo en horario regular de mercado US (L-V 9:30-16:00 ET)."""
    now = datetime.now(EASTERN)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return t.hour * 60 + t.minute >= 9 * 60 + 30 and t.hour * 60 + t.minute <= 16 * 60


def _detect_upgrade(trends) -> bool:
    """True si el consenso de analistas MEJORÓ este mes respecto al anterior.
    trends: lista de meses (index 0 = más reciente) con strongBuy/buy/hold/sell/strongSell."""
    if not trends or len(trends) < 2:
        return False
    def buy_score(m):
        return (m.get("strongBuy", 0) * 2) + m.get("buy", 0) - m.get("sell", 0) - (m.get("strongSell", 0) * 2)
    return buy_score(trends[0]) > buy_score(trends[1])


def _score_candidate(m, cons, insider, upgrade, earnings, quote):
    """Convicción 0-100 + lista de razones legibles. La CONVICCIÓN exige catalizador
    REAL (insiders/upgrade/beat), no solo un score alto — para eso está el screener."""
    reasons = []
    conviction = 0.0
    hard_catalyst = False

    # 1) Insiders comprando — la señal más fuerte.
    if insider and (insider.get("net_shares") or 0) > 0 and insider.get("buy_transactions", 0) >= 1:
        conviction += 35
        hard_catalyst = True
        reasons.append(f"🟢 Insiders comprando ({insider['buy_transactions']} compras)")

    # 2) Upgrade de analistas este mes.
    if upgrade:
        conviction += 25
        hard_catalyst = True
        cons_label = cons.get("consensus") if cons else None
        reasons.append(f"📈 Mejora de recomendación de analistas{f' → {cons_label}' if cons_label else ''}")

    # 3) Earnings recientes batidos.
    if earnings and earnings.get("quarters"):
        q0 = earnings["quarters"][0]
        if q0.get("actual") is not None and q0.get("estimate") is not None and q0["actual"] > q0["estimate"]:
            conviction += 15
            hard_catalyst = True
            sp = q0.get("surprise_percent")
            reasons.append(f"💥 Batió el último earnings{f' (+{sp}% sorpresa)' if sp else ''}")

    # 4) Score de potencial del motor (crecimiento + valoración + tendencia).
    rev_g = m.get("revenue_growth")
    pot, val_label, mom_label = opportunities._potential_score(
        rev_g, m.get("eps_growth"), quote.get("pe_ratio") or m.get("pe_ratio"),
        _dist_52w(quote, m), cons.get("score") if cons else None,
        m.get("return_26w"), m.get("return_52w"), m.get("rel_strength_52w"),
    )
    conviction += (pot / 100) * 30
    if pot >= 60:
        reasons.append(f"⭐ Score de potencial {pot} · {val_label}")
    # El guardián de tendencia: si está en clara tendencia bajista, NO la proponemos
    # aunque tenga catalizador — no vamos contra la tendencia.
    if mom_label.startswith("⚠"):
        return 0, [], False, pot

    return round(min(conviction, 100), 1), reasons, hard_catalyst, pot


def _dist_52w(quote, m):
    price = quote.get("price")
    high52 = quote.get("high_52w") or m.get("high_52w")
    if price and high52 and high52 > 0:
        return (price - high52) / high52 * 100
    return None


async def _analyze_symbol(symbol):
    """Reúne todas las señales de un símbolo y calcula su convicción. None si no aplica."""
    try:
        quote = await asyncio.to_thread(market_data.get_quote, symbol)
        if not quote or not quote.get("price"):
            return None
        m = await asyncio.to_thread(external_data.finnhub_basic_financials, symbol) or {}
        trends = await asyncio.to_thread(external_data.finnhub_recommendation_trends, symbol)
        cons = external_data.aggregate_recommendation(trends)
        insider = await asyncio.to_thread(external_data.finnhub_insider_transactions, symbol)
        earnings = await asyncio.to_thread(external_data.finnhub_earnings_surprises, symbol)
        upgrade = _detect_upgrade(trends)

        conviction, reasons, hard, pot = _score_candidate(m, cons, insider, upgrade, earnings, quote)
        if conviction < _CONVICTION_THRESHOLD or not hard:
            return None
        return {
            "symbol": symbol,
            "name": quote.get("name"),
            "price": quote.get("price"),
            "change_percent": quote.get("change_percent"),
            "sector": quote.get("sector"),
            "conviction": conviction,
            "potential_score": pot,
            "reasons": reasons,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        logger.exception(f"daily_analyst: fallo analizando {symbol}")
        return None


async def _in_cooldown(db, symbol) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_COOLDOWN_DAYS)).isoformat()
    doc = await db.analyst_ideas.find_one(
        {"symbol": symbol, "detected_at": {"$gte": cutoff}}, {"_id": 0, "symbol": 1}
    )
    return doc is not None


def _research_block(research) -> str:
    """Bloque HTML con el informe de investigación web (si existe)."""
    if not research:
        return ""
    import html as _html
    safe = _html.escape(research).replace("\n", "<br>")
    return (
        '<div style="margin-top:12px;padding:12px;background:#eef2f0;border-radius:8px;">'
        '<p style="margin:0 0 6px 0;font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#1a3a32;">🔎 Investigación</p>'
        f'<p style="margin:0;font-size:13px;color:#0e1f1a;line-height:1.5;">{safe}</p>'
        '</div>'
    )


def _build_email_html(ideas: list) -> str:
    """Email HTML con las ideas del analista (una o varias en un solo correo)."""
    cards = []
    for idea in ideas:
        cp = idea.get("change_percent")
        chg = f"{'+' if (cp or 0) >= 0 else ''}{cp}%" if cp is not None else "—"
        chg_color = "#4a7c59" if (cp or 0) >= 0 else "#d85c41"
        reasons_html = "".join(
            f'<li style="margin:4px 0;color:#0e1f1a;font-size:14px;">{r}</li>'
            for r in idea["reasons"]
        )
        cards.append(f"""
        <div style="border:1px solid #e5e0d8;border-radius:10px;padding:20px;margin:0 0 16px 0;background:#faf9f6;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;">
            <span style="font-size:20px;font-weight:700;color:#0e1f1a;">{idea['symbol']}</span>
            <span style="font-size:12px;color:#5c6b66;">Convicción {idea['conviction']}/100</span>
          </div>
          <p style="margin:2px 0 12px 0;color:#5c6b66;font-size:13px;">{idea.get('name') or ''}</p>
          <p style="margin:0 0 12px 0;font-size:16px;color:#0e1f1a;">
            ${idea['price']} <span style="color:{chg_color};font-size:13px;">({chg})</span>
          </p>
          <p style="margin:0 0 6px 0;font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#5c6b66;">Por qué destaca hoy</p>
          <ul style="margin:0;padding-left:18px;">{reasons_html}</ul>
          {_research_block(idea.get('research'))}
        </div>""")
    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#5c6b66;margin:0 0 4px 0;">InverIA · Analista Institucional</p>
      <h1 style="font-size:22px;color:#0e1f1a;margin:0 0 20px 0;">🎯 {len(ideas)} idea{'s' if len(ideas) != 1 else ''} destaca{'n' if len(ideas) != 1 else ''} hoy</h1>
      {''.join(cards)}
      <p style="font-size:12px;color:#5c6b66;margin:16px 0 0 0;">
        Candidatas para tu análisis — revísalas en InverIA antes de decidir. No es una recomendación de compra.
      </p>
    </div>"""


async def _send_email(ideas: list) -> tuple:
    """Envía las ideas por email (Resend). Devuelve (ok, error)."""
    if resend is None:
        return False, "librería resend no instalada"
    api_key = os.environ.get("RESEND_API_KEY")
    recipient = os.environ.get("ANALYST_RECIPIENT_EMAIL") or os.environ.get("ALERT_RECIPIENT_EMAIL")
    if not api_key or not recipient:
        return False, "RESEND_API_KEY o email de destino no configurados"
    resend.api_key = api_key
    sender = os.environ.get("ALERT_FROM_EMAIL") or os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"
    n = len(ideas)
    subject = (f"InverIA · {ideas[0]['symbol']} destaca (convicción {ideas[0]['conviction']})"
               if n == 1 else f"InverIA · {n} ideas del Analista hoy")
    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": f"InverIA Analista <{sender}>",
            "to": [recipient],
            "subject": subject,
            "html": _build_email_html(ideas),
        })
        return True, None
    except Exception as e:
        return False, str(e)[:200]


def _format_telegram(idea) -> str:
    esc = telegram_notifier._esc_md
    cp = idea.get("change_percent")
    chg = f"{'+' if (cp or 0) >= 0 else ''}{cp}%" if cp is not None else "—"
    lines = [
        f"🎯 *Analista InverIA · {esc(idea['symbol'])}*",
        f"_{esc(idea.get('name') or '')}_",
        "",
        f"Precio: *${esc(str(idea['price']))}* \\({esc(chg)}\\) · Convicción *{esc(str(idea['conviction']))}/100*",
        "",
        "*Por qué destaca hoy:*",
    ]
    for r in idea["reasons"]:
        lines.append(f"• {esc(r)}")
    lines.append("")
    lines.append(esc("Candidata para tu análisis — revísala en InverIA antes de decidir."))
    return "\n".join(lines)


async def scan(db, universe=None, notify: bool = True) -> dict:
    """Barrido completo: analiza el universo, filtra alta convicción + fuera de cooldown,
    avisa por Telegram y guarda en histórico. Devuelve el resumen."""
    if _scan_lock.locked():
        return {"status": "already_running"}
    async with _scan_lock:
        market_data.enter_finnhub_background()
        if universe is None:
            universe = opportunities.UNIVERSE
        sem = asyncio.Semaphore(3)

        async def bounded(s):
            async with sem:
                return await _analyze_symbol(s)

        results = await asyncio.gather(*[bounded(s) for s in universe])
        candidates = [r for r in results if r]
        candidates.sort(key=lambda x: x["conviction"], reverse=True)

        fresh = []
        for c in candidates:
            if await _in_cooldown(db, c["symbol"]):
                continue
            fresh.append(c)
            if len(fresh) >= _MAX_ALERTS_PER_SCAN:
                break

        # Capa 2 — INVESTIGACIÓN WEB PROFUNDA de cada candidata (best-effort). Fundamenta
        # los datos-señal con lo que hay HOY en internet (tesis, riesgos, catalizadores).
        # Si falla (p. ej. cuota de Gemini), la idea sale igual con sus razones cuantitativas.
        import ai_analysis  # perezoso: evita acoplar la carga del módulo a groq/gemini
        for c in fresh:
            try:
                c["research"] = await ai_analysis.research_stock_web(
                    c["symbol"], c.get("name") or "", "; ".join(c.get("reasons") or []))
            except Exception as e:
                logger.warning(f"daily_analyst: investigación web falló para {c['symbol']}: {e}")
                c["research"] = None

        for c in fresh:
            await db.analyst_ideas.insert_one({**c})

        # Entrega por EMAIL (canal preferido): un solo correo con todas las ideas nuevas.
        # Telegram queda como respaldo si el email no está configurado o falla.
        sent = 0
        email_ok = False
        if notify and fresh:
            email_ok, email_err = await _send_email(fresh)
            if email_ok:
                sent = len(fresh)
            else:
                logger.warning(f"daily_analyst: email falló ({email_err}); intento Telegram")
                for c in fresh:
                    ok, err = await telegram_notifier.send_message(_format_telegram(c))
                    if ok:
                        sent += 1
                    else:
                        logger.warning(f"daily_analyst: Telegram falló para {c['symbol']}: {err}")

        return {
            "channel": "email" if email_ok else "telegram",
            "scanned": len(universe),
            "candidates": len(candidates),
            "new_ideas": len(fresh),
            "notified": sent,
            "ideas": fresh,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


def _build_digest_html(ideas: list, market_date: str) -> str:
    """Email del RESUMEN DIARIO: recopila las ideas detectadas hoy. Si no hubo ninguna,
    lo dice con honestidad (mejor 'hoy nada destacable' que inventar señales)."""
    if not ideas:
        return f"""
        <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
          <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#5c6b66;margin:0 0 4px 0;">InverIA · Resumen diario</p>
          <h1 style="font-size:22px;color:#0e1f1a;margin:0 0 12px 0;">📊 {market_date}</h1>
          <p style="font-size:15px;color:#0e1f1a;">Hoy el Analista <b>no ha detectado ninguna acción</b> con confluencia de catalizadores de alta convicción.</p>
          <p style="font-size:13px;color:#5c6b66;">Ninguna señal fuerte es también información: no fuerza operaciones donde no las hay.</p>
        </div>"""
    # Reutiliza las tarjetas del email de ideas, con cabecera de resumen diario.
    body = _build_email_html(ideas)
    return body.replace("🎯", f"📊 Resumen diario · {market_date} —", 1)


async def send_daily_digest(db) -> dict:
    """Envía el resumen diario: todas las ideas detectadas HOY (hora del Este)."""
    today = datetime.now(EASTERN).date().isoformat()
    start = f"{today}T00:00:00+00:00"
    ideas = await db.analyst_ideas.find(
        {"detected_at": {"$gte": start}}, {"_id": 0}
    ).sort("conviction", -1).to_list(20)
    ok, err = await _send_email_digest(ideas, today)
    return {"date": today, "ideas": len(ideas), "sent": ok, "error": err}


async def _send_email_digest(ideas: list, market_date: str) -> tuple:
    if resend is None:
        return False, "librería resend no instalada"
    api_key = os.environ.get("RESEND_API_KEY")
    recipient = os.environ.get("ANALYST_RECIPIENT_EMAIL") or os.environ.get("ALERT_RECIPIENT_EMAIL")
    if not api_key or not recipient:
        return False, "RESEND_API_KEY o email de destino no configurados"
    resend.api_key = api_key
    sender = os.environ.get("ALERT_FROM_EMAIL") or os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"
    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": f"InverIA Analista <{sender}>",
            "to": [recipient],
            "subject": f"InverIA · Resumen diario ({len(ideas)} ideas) · {market_date}",
            "html": _build_digest_html(ideas, market_date),
        })
        return True, None
    except Exception as e:
        return False, str(e)[:200]


async def digest_loop(db):
    """Envía el resumen diario UNA vez al día, tras el cierre de mercado US (~16:10 ET
    ≈ 22:10 hora España). Comprueba cada 30 min y marca el día ya enviado para no repetir."""
    logger.info("Digest diario del Analista arrancado")
    last_sent_date = None
    while True:
        try:
            now = datetime.now(EASTERN)
            past_close = now.hour * 60 + now.minute >= 16 * 60 + 10  # 16:10 ET
            is_weekday = now.weekday() < 5
            today = now.date().isoformat()
            if is_weekday and past_close and last_sent_date != today:
                res = await send_daily_digest(db)
                if res.get("sent"):
                    last_sent_date = today
                    logger.info(f"Digest diario enviado: {res['ideas']} ideas")
                else:
                    logger.warning(f"Digest diario no enviado: {res.get('error')}")
            await asyncio.sleep(30 * 60)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("digest_loop: error")
            await asyncio.sleep(30 * 60)


async def worker_loop(db):
    """Corre durante el horario de mercado y hace un barrido cada ~2h. Fuera de mercado
    duerme. Diseñado para 'avisar cuando se vea una acción buena', sin spam."""
    logger.info("Analista Institucional arrancado")
    while True:
        try:
            if is_market_open():
                res = await scan(db)
                if res.get("new_ideas"):
                    logger.info(f"daily_analyst: {res['new_ideas']} ideas nuevas, {res.get('notified')} avisadas")
            await asyncio.sleep(2 * 60 * 60)  # cada 2 horas
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("daily_analyst: error en ciclo")
            await asyncio.sleep(10 * 60)
