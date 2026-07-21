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
import mem
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


# Etiqueta legible + fiabilidad de cada fuente de investigación, para que sepas de dónde
# sale el análisis y cuánto fiarte.
_SOURCE_LABEL = {
    "web": ("🌐 Gemini + búsqueda web en vivo", "máxima — datos de internet en tiempo real"),
    "noticias": ("🤖 Groq sobre noticias reales (FMP/Finnhub)", "alta — noticias recientes, sin navegar la web"),
    "titulares": ("📰 Titulares recientes (sin análisis IA)", "básica — solo los titulares en crudo"),
    "ninguna": ("— sin investigación disponible", "—"),
}


def _earnings_warning_html(ew) -> str:
    """Chip de aviso de resultados próximos (riesgo binario)."""
    if not ew or ew.get("days") is None:
        return ""
    d = ew["days"]
    when = "HOY" if d == 0 else ("mañana" if d == 1 else f"en {d} días")
    return (
        '<p style="margin:8px 0 0 0;font-size:12px;font-weight:600;color:#d85c41;'
        'background:#d85c41/10;padding:4px 8px;border-radius:4px;display:inline-block;'
        'background-color:#fbe9e4;">'
        f'⚠ Resultados {when} — riesgo binario (gap ±10%). Considera esperar al post-earnings.</p>'
    )


def _regime_banner_html(regime) -> str:
    """Banner del estado del mercado al inicio del email."""
    if not regime or regime.get("light") in (None, "desconocido"):
        return ""
    colors = {"verde": ("#4a7c59", "#eef5f0"), "amarillo": ("#c9a14a", "#fbf5e7"), "rojo": ("#d85c41", "#fbe9e4")}
    fg, bg = colors.get(regime["light"], ("#5c6b66", "#f0f0f0"))
    return (
        f'<div style="background:{bg};border-left:3px solid {fg};padding:10px 12px;border-radius:6px;margin:0 0 16px 0;">'
        f'<b style="color:{fg};font-size:13px;">{regime.get("label","")}</b>'
        f'<p style="margin:4px 0 0 0;font-size:12px;color:#0e1f1a;">{regime.get("advice","")}</p></div>'
    )


def _research_block(research, source=None) -> str:
    """Bloque HTML con el informe de investigación y, sobre todo, DE QUÉ FUENTE viene
    (Gemini web / Groq+noticias / titulares) y su fiabilidad, para que sepas cuánto fiarte."""
    if not research and source in (None, "ninguna"):
        return ""
    import html as _html
    label, reliability = _SOURCE_LABEL.get(source or "ninguna", _SOURCE_LABEL["ninguna"])
    body = ""
    if research:
        safe = _html.escape(research).replace("\n", "<br>")
        body = f'<p style="margin:0 0 8px 0;font-size:13px;color:#0e1f1a;line-height:1.5;">{safe}</p>'
    return (
        '<div style="margin-top:12px;padding:12px;background:#eef2f0;border-radius:8px;">'
        '<p style="margin:0 0 6px 0;font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#1a3a32;">🔎 Investigación</p>'
        f'{body}'
        f'<p style="margin:0;font-size:11px;color:#5c6b66;border-top:1px solid #dfe5e2;padding-top:6px;">'
        f'<b>Fuente:</b> {_html.escape(label)} · <b>Fiabilidad:</b> {_html.escape(reliability)}</p>'
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
          {_earnings_warning_html(idea.get('earnings_warning'))}
          {_research_block(idea.get('research'), idea.get('research_source'))}
        </div>""")
    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#5c6b66;margin:0 0 4px 0;">InverIA · Analista Institucional</p>
      <h1 style="font-size:22px;color:#0e1f1a;margin:0 0 16px 0;">🎯 {len(ideas)} idea{'s' if len(ideas) != 1 else ''} destaca{'n' if len(ideas) != 1 else ''} hoy</h1>
      {_regime_banner_html((ideas[0] or {}).get('market_regime') if ideas else None)}
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

        # FILTRO DE RÉGIMEN DE MERCADO: en un mercado bajista (semáforo rojo) las compras
        # fallan más, así que somos más selectivos — menos ideas y solo las de máxima
        # convicción. En verde, comportamiento normal.
        try:
            import market_regime
            regime = market_regime.get_market_regime()
        except Exception:
            regime = None
        light = (regime or {}).get("light")
        max_alerts = _MAX_ALERTS_PER_SCAN
        min_conv = _CONVICTION_THRESHOLD
        if light == "rojo":
            max_alerts = 2
            min_conv = 80  # solo lo excepcional cuando el mercado está en riesgo
        elif light == "amarillo":
            max_alerts = 3

        fresh = []
        for c in candidates:
            if c["conviction"] < min_conv:
                continue
            if await _in_cooldown(db, c["symbol"]):
                continue
            c["market_regime"] = regime
            fresh.append(c)
            if len(fresh) >= max_alerts:
                break

        # AVISO DE EARNINGS: resultados próximos = riesgo binario (gap ±10% que salta
        # cualquier soporte). Una sola llamada bulk para todos los candidatos.
        if fresh:
            try:
                cal = await asyncio.to_thread(
                    external_data.finnhub_earnings_calendar, 21, [c["symbol"] for c in fresh])
                by_sym = {}
                for it in ((cal or {}).get("items") or []):
                    by_sym.setdefault(it.get("symbol"), it.get("date"))
                from datetime import date as _date
                today_d = datetime.now(timezone.utc).date()
                for c in fresh:
                    d = by_sym.get(c["symbol"])
                    if d:
                        try:
                            days = (_date.fromisoformat(d) - today_d).days
                            if 0 <= days <= 14:
                                c["earnings_warning"] = {"date": d, "days": days}
                        except Exception:
                            pass
            except Exception:
                pass

        # Capa 2 — INVESTIGACIÓN WEB PROFUNDA de cada candidata (best-effort). Fundamenta
        # los datos-señal con lo que hay HOY en internet (tesis, riesgos, catalizadores).
        # Si falla (p. ej. cuota de Gemini), la idea sale igual con sus razones cuantitativas.
        import ai_analysis  # perezoso: evita acoplar la carga del módulo a groq/gemini
        for c in fresh:
            try:
                informe, fuente = await ai_analysis.research_stock(
                    c["symbol"], c.get("name") or "", "; ".join(c.get("reasons") or []))
                c["research"] = informe or None
                c["research_source"] = fuente
            except Exception as e:
                logger.warning(f"daily_analyst: investigación falló para {c['symbol']}: {e}")
                c["research"] = None
                c["research_source"] = "ninguna"

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

        mem.trim()  # el barrido del universo crea muchos DataFrames: devuelve la RAM al SO
        return {
            "channel": "email" if email_ok else "telegram",
            "scanned": len(universe),
            "candidates": len(candidates),
            "new_ideas": len(fresh),
            "notified": sent,
            "ideas": fresh,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }



async def _top_screener_ideas(db, n: int, exclude: set):
    """Top-N del screener de crecimiento (mejor score), YA investigadas. Garantiza que el
    briefing diario SIEMPRE tenga investigación profunda, aunque no haya catalizadores hoy."""
    data = opportunities._screener_cache.get("data") or {}
    results = [r for r in (data.get("results") or []) if r.get("symbol") not in exclude]
    results = results[:n]
    if not results:
        return []
    import ai_analysis
    out = []
    for r in results:
        reasons = []
        if r.get("valuation"):
            reasons.append(f"⭐ Score {r.get('potential_score')} · {r['valuation']}")
        if r.get("momentum") and r["momentum"] != "neutra":
            reasons.append(r["momentum"])
        if r.get("analyst_consensus"):
            reasons.append(f"Analistas: {r['analyst_consensus']}")
        idea = {
            "symbol": r["symbol"], "name": r.get("name"), "price": r.get("price"),
            "change_percent": r.get("change_percent"), "conviction": r.get("potential_score"),
            "reasons": reasons or ["Destaca en el screener de crecimiento"],
        }
        try:
            informe, fuente = await ai_analysis.research_stock(
                idea["symbol"], idea.get("name") or "", "; ".join(reasons))
            idea["research"] = informe or None
            idea["research_source"] = fuente
        except Exception:
            idea["research"] = None
            idea["research_source"] = "ninguna"
        out.append(idea)
    return out


async def _recent_newsletters(db, hours: int = 48):
    """Resúmenes de newsletters recibidas en las últimas `hours` horas."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return await db.newsletter_summaries.find(
            {"received_at": {"$gte": cutoff}}, {"_id": 0}
        ).sort("received_at", -1).to_list(10)
    except Exception:
        return []


async def send_daily_digest(db) -> dict:
    """Briefing diario COMPLETO: (A) ideas con catalizador de hoy, (B) top del screener
    investigadas para que siempre haya análisis profundo, (C) lo extraído de tus
    newsletters recientes. Todo en un solo email."""
    today = datetime.now(EASTERN).date().isoformat()
    start = f"{today}T00:00:00+00:00"
    catalyst = await db.analyst_ideas.find(
        {"detected_at": {"$gte": start}}, {"_id": 0}
    ).sort("conviction", -1).to_list(20)

    # Garantiza investigación profunda diaria: si hay pocas ideas con catalizador,
    # completa con las mejores del screener (investigadas).
    exclude = {c["symbol"] for c in catalyst}
    screener = []
    if len(catalyst) < 3:
        screener = await _top_screener_ideas(db, 3 - len(catalyst), exclude)

    newsletters = await _recent_newsletters(db, hours=48)

    ok, err = await _send_briefing_email(catalyst, screener, newsletters, today)
    return {"date": today, "catalyst": len(catalyst), "screener": len(screener),
            "newsletters": len(newsletters), "sent": ok, "error": err}


async def _send_briefing_email(catalyst, screener, newsletters, market_date) -> tuple:
    if resend is None:
        return False, "librería resend no instalada"
    api_key = os.environ.get("RESEND_API_KEY")
    recipient = os.environ.get("ANALYST_RECIPIENT_EMAIL") or os.environ.get("ALERT_RECIPIENT_EMAIL")
    if not api_key or not recipient:
        return False, "RESEND_API_KEY o email de destino no configurados"
    resend.api_key = api_key
    sender = os.environ.get("ALERT_FROM_EMAIL") or os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"
    total = len(catalyst) + len(screener)
    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": f"InverIA Analista <{sender}>",
            "to": [recipient],
            "subject": f"InverIA · Briefing diario ({total} ideas) · {market_date}",
            "html": _build_briefing_html(catalyst, screener, newsletters, market_date),
        })
        return True, None
    except Exception as e:
        return False, str(e)[:200]


def _build_briefing_html(catalyst, screener, newsletters, market_date) -> str:
    def section(title, ideas):
        if not ideas:
            return ""
        return (f'<p style="margin:20px 0 8px 0;font-size:12px;text-transform:uppercase;'
                f'letter-spacing:0.12em;color:#1a3a32;font-weight:700;">{title}</p>'
                + _cards_html(ideas))
    nl_html = _newsletters_html(newsletters)
    has_any = catalyst or screener or newsletters
    intro = ("Hoy sin catalizadores fuertes, pero aquí tienes lo mejor del screener y tus newsletters."
             if not catalyst and has_any else
             "Tu resumen de hoy: ideas con catalizador, mejores del screener y tus newsletters.")
    if not has_any:
        intro = "Hoy no hay nada destacable ni newsletters nuevas. Ninguna señal también es información."
    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#5c6b66;margin:0 0 4px 0;">InverIA · Briefing diario</p>
      <h1 style="font-size:22px;color:#0e1f1a;margin:0 0 8px 0;">📊 {market_date}</h1>
      <p style="font-size:14px;color:#5c6b66;margin:0 0 4px 0;">{intro}</p>
      {section('🎯 Ideas con catalizador', catalyst)}
      {section('⭐ Mejores del screener (investigadas)', screener)}
      {nl_html}
      <p style="font-size:11px;color:#5c6b66;margin:24px 0 0 0;border-top:1px solid #e5e0d8;padding-top:8px;">
        Candidatas para tu análisis — no es recomendación de compra. Verifica en InverIA antes de operar.
      </p>
    </div>"""


def _newsletters_html(newsletters) -> str:
    if not newsletters:
        return ""
    blocks = []
    for nl in newsletters:
        d = nl.get("extracted") or {}
        acciones = d.get("acciones") or []
        acc = ", ".join(f"{a.get('ticker','')} ({a.get('accion','')})" for a in acciones) if acciones else "—"
        blocks.append(
            f'<div style="border-left:3px solid #6b5b95;padding:8px 12px;margin:8px 0;background:#faf9f6;border-radius:4px;">'
            f'<b style="color:#0e1f1a;font-size:13px;">{d.get("titulo") or nl.get("subject") or "Newsletter"}</b>'
            f'<p style="margin:4px 0;font-size:13px;color:#0e1f1a;">{d.get("resumen","")}</p>'
            f'<p style="margin:0;font-size:12px;color:#5c6b66;">Acciones: {acc}</p></div>'
        )
    return ('<p style="margin:20px 0 8px 0;font-size:12px;text-transform:uppercase;letter-spacing:0.12em;'
            'color:#6b5b95;font-weight:700;">📩 De tus newsletters</p>' + "".join(blocks))


def _cards_html(ideas) -> str:
    """Reutiliza el render de tarjetas del email de ideas."""
    # _build_email_html envuelve las tarjetas en un contenedor; extraemos solo las tarjetas
    # reusando la misma plantilla por idea.
    cards = []
    for idea in ideas:
        cp = idea.get("change_percent")
        chg = f"{'+' if (cp or 0) >= 0 else ''}{cp}%" if cp is not None else "—"
        chg_color = "#4a7c59" if (cp or 0) >= 0 else "#d85c41"
        reasons_html = "".join(
            f'<li style="margin:4px 0;color:#0e1f1a;font-size:14px;">{r}</li>' for r in idea["reasons"])
        cards.append(f"""
        <div style="border:1px solid #e5e0d8;border-radius:10px;padding:20px;margin:0 0 16px 0;background:#faf9f6;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;">
            <span style="font-size:20px;font-weight:700;color:#0e1f1a;">{idea['symbol']}</span>
            <span style="font-size:12px;color:#5c6b66;">Convicción {idea.get('conviction')}/100</span>
          </div>
          <p style="margin:2px 0 12px 0;color:#5c6b66;font-size:13px;">{idea.get('name') or ''}</p>
          <p style="margin:0 0 12px 0;font-size:16px;color:#0e1f1a;">
            ${idea.get('price')} <span style="color:{chg_color};font-size:13px;">({chg})</span>
          </p>
          <p style="margin:0 0 6px 0;font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#5c6b66;">Por qué destaca</p>
          <ul style="margin:0;padding-left:18px;">{reasons_html}</ul>
          {_research_block(idea.get('research'), idea.get('research_source'))}
        </div>""")
    return "".join(cards)


async def digest_loop(db):
    """Envía el resumen diario UNA vez al día, tras el cierre de mercado US (~16:10 ET
    ≈ 22:10 hora España). El 'ya enviado hoy' se guarda en Mongo para NO reenviar cuando
    Render redespliega (el bug de recibirlo 3 veces era por perder ese estado en memoria)."""
    logger.info("Digest diario del Analista arrancado")
    while True:
        try:
            now = datetime.now(EASTERN)
            past_close = now.hour * 60 + now.minute >= 16 * 60 + 10  # 16:10 ET
            is_weekday = now.weekday() < 5
            today = now.date().isoformat()
            if is_weekday and past_close:
                # Asegura que el doc existe, luego reclama el envío de HOY de forma atómica:
                # solo una ejecución (aunque haya varios reinicios/instancias) consigue
                # modified_count>0 y envía. El resto ve que ya está hecho y no reenvía.
                await db.analyst_config.update_one(
                    {"_id": "digest"}, {"$setOnInsert": {"last_sent_date": None}}, upsert=True)
                claim = await db.analyst_config.update_one(
                    {"_id": "digest", "last_sent_date": {"$ne": today}},
                    {"$set": {"last_sent_date": today}})
                if (claim.modified_count or 0) > 0:
                    res = await send_daily_digest(db)
                    if res.get("sent"):
                        logger.info(f"Digest diario enviado: {res['ideas']} ideas")
                    else:
                        # Falló el envío: libera la marca para reintentar en el próximo ciclo.
                        await db.analyst_config.update_one(
                            {"_id": "digest"}, {"$set": {"last_sent_date": None}})
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
