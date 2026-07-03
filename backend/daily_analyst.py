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

import external_data
import market_data
import opportunities
import telegram_notifier

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

        sent = 0
        for c in fresh:
            await db.analyst_ideas.insert_one({**c})
            if notify:
                ok, err = await telegram_notifier.send_message(_format_telegram(c))
                if ok:
                    sent += 1
                else:
                    logger.warning(f"daily_analyst: Telegram falló para {c['symbol']}: {err}")

        return {
            "scanned": len(universe),
            "candidates": len(candidates),
            "new_ideas": len(fresh),
            "notified": sent,
            "ideas": fresh,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


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
