"""Portfolio management — transactions, positions, P&L calculations, PDF parsing."""
import asyncio
import json
import logging
import os
import re
import uuid
import io
import pdfplumber
from datetime import datetime, timezone
from typing import Optional, List
from groq import AsyncGroq
import market_data
import degiro_parser

logger = logging.getLogger("inveria.portfolio")


PDF_PARSE_PROMPT = """Eres un experto en parseo de extractos de operaciones de brokers (DEGIRO, Trade Republic, Interactive Brokers, etc.).
Te paso el TEXTO EXTRAÍDO de un PDF de un broker. Identifica TODOS los movimientos y devuélvelos en JSON.

REGLAS:
- Responde ÚNICAMENTE con un JSON válido (sin markdown, sin texto extra), con esta estructura:
{
  "transactions": [
    {"date": "YYYY-MM-DD", "symbol": "AAPL", "action": "BUY"|"SELL", "shares": número, "price": número, "currency": "USD"|"EUR"|"GBP", "fees": número, "broker": "DEGIRO"}
  ],
  "cash_events": [
    {"date": "YYYY-MM-DD", "type": "FEE"|"DIVIDEND"|"DIVIDEND_TAX"|"DEPOSIT"|"WITHDRAWAL"|"INTEREST"|"FX_FEE"|"CONNECTIVITY"|"MARKET_DATA"|"OTHER", "amount": número, "currency": "EUR"|"USD", "description": "texto breve original", "symbol": "ticker si aplica o null"}
  ]
}

REGLAS TRANSACTIONS (solo COMPRAS/VENTAS de acciones/ETFs):
- Convierte nombres de empresas a tickers (ej: "Apple Inc"→AAPL, "Tesla"→TSLA, "Iberdrola"→IBE.MC).
- Convierte precios europeos (1.234,56) a (1234.56).
- "fees" es la comisión específica de esa operación (no incluyas otros costes).
- action es BUY (compra) o SELL (venta).

REGLAS CASH_EVENTS (todo lo demás):
- "FEE": comisión genérica de transacción no asociada a compra/venta
- "DIVIDEND": ingreso de dividendos (amount POSITIVO)
- "DIVIDEND_TAX": retención fiscal sobre dividendo (amount NEGATIVO)
- "DEPOSIT": ingreso de dinero a la cuenta (POSITIVO)
- "WITHDRAWAL": retirada de dinero (NEGATIVO)
- "INTEREST": intereses pagados o cobrados
- "FX_FEE": comisión de cambio de divisa (NEGATIVO, típicamente DEGIRO 0.25%)
- "CONNECTIVITY": "Comisión de conectividad" / "Exchange connection fee" (NEGATIVO, típicamente 2.50€/año por mercado)
- "MARKET_DATA": cargo por datos en tiempo real / market data fee (NEGATIVO)
- "OTHER": cualquier otro coste/ingreso no clasificado

IMPORTANTE:
- amount: signo según naturaleza (gastos NEGATIVOS, ingresos POSITIVOS).
- Si no encuentras nada de un tipo, deja la lista vacía.
- Incluye TODOS los eventos detectables, incluso si parecen menores.
"""


def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


async def parse_pdf_with_ai(pdf_bytes: bytes) -> dict:
    """Extract transactions + cash events from broker PDF.
    Strategy:
    1. Try DEGIRO regex parser first (instant, no AI quota needed)
    2. Fall back to Groq AI for non-DEGIRO formats
    Returns: {transactions, cash_events, debug, warning} structure."""
    debug = {"pages_total": 0, "pages_kept": 0, "chunks": 0, "chunks_ok": 0, "chunks_failed": 0, "first_error": None, "parser": None}

    # Extract text per page
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t)
    debug["pages_total"] = len(pages)
    if not pages:
        return {"transactions": [], "cash_events": [], "debug": debug,
                "warning": "No se pudo extraer texto del PDF (¿escaneado/imagen?)."}

    full_text = "\n".join(pages)

    # --- Try DEGIRO regex parser first (instant, no AI quota) ---
    if degiro_parser.is_degiro_transactions(full_text):
        debug["parser"] = "degiro_transactions"
        try:
            txs = await degiro_parser.parse_transactions_pdf(full_text)
            return {"transactions": txs, "cash_events": [], "debug": debug, "warning": None}
        except Exception as e:
            logger.exception(f"DEGIRO transactions parse failed: {e}")
            debug["first_error"] = f"DEGIRO parser: {str(e)[:200]}"

    if degiro_parser.is_degiro_account(full_text):
        debug["parser"] = "degiro_account"
        try:
            events = await degiro_parser.parse_account_pdf(full_text)
            return {"transactions": [], "cash_events": events, "debug": debug, "warning": None}
        except Exception as e:
            logger.exception(f"DEGIRO account parse failed: {e}")
            debug["first_error"] = f"DEGIRO parser: {str(e)[:200]}"

    debug["parser"] = "ai"

    # --- Fallback: AI parsing for unknown formats ---

    # Permissive page filter: keep page if it has a date OR a monetary amount.
    # Many DEGIRO/IBKR pages have only one of the two (e.g. summary tables).
    date_re = re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b|\b\d{4}[-/.]\d{2}[-/.]\d{2}\b")
    money_re = re.compile(r"\d+[.,]\d{2}|EUR|USD|GBP|\$|€|£", re.I)
    filtered = [p for p in pages if date_re.search(p) or money_re.search(p)]
    if not filtered:
        # If filter eats everything, fall back to all pages (better safe than empty)
        filtered = pages
    pages = filtered
    debug["pages_kept"] = len(pages)

    # Cap total text to ~150k chars to bound Groq calls (≈25 chunks max, ~3 min on free tier).
    # Larger PDFs are unusual; truncating is preferable to silently timing out.
    MAX_TOTAL = 150_000
    total = 0
    capped = []
    for p in pages:
        if total + len(p) > MAX_TOTAL:
            break
        capped.append(p)
        total += len(p)
    pages = capped

    # Build chunks of ~6,000 chars each (~1,500 tokens input).
    CHUNK_SIZE = 6000
    chunks = []
    current = ""
    for page_text in pages:
        if len(current) + len(page_text) > CHUNK_SIZE and current:
            chunks.append(current)
            current = page_text
        else:
            current += "\n" + page_text
    if current:
        chunks.append(current)
    debug["chunks"] = len(chunks)

    # Process chunks SERIALLY (sem=1) to stay under Groq's free-tier TPM limit (30k TPM).
    sem = asyncio.Semaphore(1)

    async def _bounded(c):
        async with sem:
            try:
                r = await _parse_chunk(c)
                debug["chunks_ok"] += 1
                return r
            except Exception as e:
                debug["chunks_failed"] += 1
                if debug["first_error"] is None:
                    debug["first_error"] = f"{type(e).__name__}: {str(e)[:200]}"
                logger.warning(f"Chunk parse failed: {type(e).__name__}: {str(e)[:200]}")
                return {"transactions": [], "cash_events": []}

    chunk_results = await asyncio.gather(*[_bounded(c) for c in chunks])

    all_transactions = []
    all_cash_events = []
    for result in chunk_results:
        all_transactions.extend(result.get("transactions", []))
        all_cash_events.extend(result.get("cash_events", []))

    # Dedupe transactions (same date + symbol + action + shares + price)
    seen = set()
    deduped_tx = []
    for tx in all_transactions:
        k = (tx.get("date"), (tx.get("symbol") or "").upper(), tx.get("action"), tx.get("shares"), tx.get("price"))
        if k in seen:
            continue
        seen.add(k)
        deduped_tx.append(tx)

    # Dedupe cash events
    seen_ce = set()
    deduped_ce = []
    for ev in all_cash_events:
        k = (ev.get("date"), ev.get("type"), ev.get("amount"), ev.get("description", "")[:50])
        if k in seen_ce:
            continue
        seen_ce.add(k)
        deduped_ce.append(ev)

    # Build a user-facing warning if we got nothing useful
    warning = None
    if not deduped_tx and not deduped_ce:
        if debug["chunks_failed"] > 0:
            warning = (
                f"No se extrajo nada. {debug['chunks_failed']}/{debug['chunks']} chunks fallaron. "
                f"Primer error: {debug['first_error'] or 'desconocido'}. "
                "Posible causa: límite de Groq alcanzado. Intenta de nuevo en 1 minuto."
            )
        else:
            warning = (
                "El PDF se procesó pero no se reconocieron transacciones ni movimientos. "
                "El formato puede no estar soportado. Comparte una línea de ejemplo del PDF."
            )

    return {"transactions": deduped_tx, "cash_events": deduped_ce, "debug": debug, "warning": warning}


async def _parse_chunk(text: str) -> dict:
    """Parse a single chunk of PDF text via Groq, with automatic model fallback
    when a daily/per-minute rate limit is hit."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY no configurada")

    # max_retries=0: fail fast on rate-limit so our model fallback chain can take over.
    # Without this, the Groq SDK auto-retries with 40s+ backoff and burns our timeout.
    client = AsyncGroq(api_key=api_key, timeout=25.0, max_retries=0)
    # Try models in order of preference. All have been verified available on Groq.
    # 1. llama-3.1-8b-instant: ~500k TPD (highest daily allowance, smaller=cheaper per call)
    # 2. openai/gpt-oss-20b: separate quota pool, different family
    # 3. llama-3.3-70b-versatile: more accurate but lower TPD (100k)
    models = ["llama-3.1-8b-instant", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
    last_error: Optional[Exception] = None
    completion = None
    for model in models:
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": PDF_PARSE_PROMPT},
                    {"role": "user", "content": f"TEXTO DEL PDF (fragmento):\n\n{text}\n\nDevuelve solo el JSON."},
                ],
                max_tokens=3500,
                temperature=0.2,
            )
            break  # success
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            # Only fall back on rate-limit / quota errors. Other errors propagate.
            if "rate limit" not in msg and "429" not in msg and "tpd" not in msg and "tpm" not in msg:
                raise
            logger.info(f"Model {model} rate-limited; trying next")
            continue
    if completion is None:
        raise last_error or RuntimeError("All Groq models exhausted")
    out = (completion.choices[0].message.content or "").strip()
    if "<think>" in out:
        end = out.find("</think>")
        if end != -1:
            out = out[end + len("</think>"):].strip()
    if out.startswith("```"):
        out = out.strip("`")
        if out.lower().startswith("json"):
            out = out[4:]
        out = out.strip()
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        start = out.find("{")
        end = out.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(out[start : end + 1])
        else:
            return {"transactions": [], "cash_events": []}
    return {
        "transactions": data.get("transactions", []),
        "cash_events": data.get("cash_events", []),
    }


def aggregate_cash_events(events):
    """Group cash events by type with totals."""
    by_type = {}
    total_fees = 0.0
    total_dividends = 0.0
    total_dividends_tax = 0.0
    total_deposits = 0.0
    total_withdrawals = 0.0
    for ev in events:
        t = (ev.get("type") or "OTHER").upper()
        amt = _safe_float(ev.get("amount"))
        b = by_type.setdefault(t, {"type": t, "count": 0, "total": 0.0, "items": []})
        b["count"] += 1
        b["total"] += amt
        b["items"].append(ev)
        if t in ("FEE", "FX_FEE", "CONNECTIVITY", "MARKET_DATA", "OTHER") and amt < 0:
            total_fees += amt
        elif t == "DIVIDEND":
            total_dividends += amt
        elif t == "DIVIDEND_TAX":
            total_dividends_tax += amt
        elif t == "DEPOSIT":
            total_deposits += amt
        elif t == "WITHDRAWAL":
            total_withdrawals += amt
    for v in by_type.values():
        v["total"] = round(v["total"], 2)
    return {
        "summary": {
            "total_fees": round(total_fees, 2),  # ya negativo
            "total_dividends_gross": round(total_dividends, 2),
            "total_dividends_tax": round(total_dividends_tax, 2),
            "total_dividends_net": round(total_dividends + total_dividends_tax, 2),
            "total_deposits": round(total_deposits, 2),
            "total_withdrawals": round(total_withdrawals, 2),
            "net_cash_flow": round(total_fees + total_dividends + total_dividends_tax, 2),
        },
        "by_type": list(by_type.values()),
    }


def compute_positions(transactions: List[dict]) -> dict:
    """Aggregate transactions into open positions + realized P&L.

    Uses average-cost method:
    - BUY adds shares at cost
    - SELL removes shares at average cost, generates realized P&L
    """
    positions = {}  # symbol -> {shares, avg_cost, currency, last_broker}
    realized_total = 0.0
    realized_by_symbol = {}
    trades_history = []  # closed trades

    # Sort by date
    sorted_tx = sorted(transactions, key=lambda t: t.get("date", ""))

    for tx in sorted_tx:
        symbol = tx["symbol"].upper().strip()
        shares = float(tx["shares"])
        price = float(tx["price"])
        fees = float(tx.get("fees") or 0)
        action = tx["action"].upper()
        currency = tx.get("currency", "USD")

        pos = positions.setdefault(symbol, {
            "symbol": symbol,
            "shares": 0.0,
            "total_cost": 0.0,
            "avg_cost": 0.0,
            "currency": currency,
            "broker": tx.get("broker"),
        })

        if action == "BUY":
            pos["total_cost"] += shares * price + fees
            pos["shares"] += shares
            pos["avg_cost"] = pos["total_cost"] / pos["shares"] if pos["shares"] > 0 else 0
        elif action == "SELL":
            if pos["shares"] <= 0:
                continue  # nothing to sell
            sell_qty = min(shares, pos["shares"])
            realized = (price - pos["avg_cost"]) * sell_qty - fees
            realized_total += realized
            realized_by_symbol[symbol] = realized_by_symbol.get(symbol, 0) + realized
            trades_history.append({
                "symbol": symbol,
                "shares": sell_qty,
                "buy_avg_cost": round(pos["avg_cost"], 4),
                "sell_price": round(price, 4),
                "realized_pnl": round(realized, 2),
                "currency": currency,
                "date": tx.get("date"),
            })
            # reduce position
            pos["total_cost"] -= pos["avg_cost"] * sell_qty
            pos["shares"] -= sell_qty
            if pos["shares"] <= 0.0001:
                pos["shares"] = 0
                pos["total_cost"] = 0
                pos["avg_cost"] = 0

    # Keep only positions with shares > 0
    open_positions = [p for p in positions.values() if p["shares"] > 0]

    return {
        "open_positions": open_positions,
        "realized_pnl_total": round(realized_total, 2),
        "realized_pnl_by_symbol": {k: round(v, 2) for k, v in realized_by_symbol.items()},
        "trades_history": sorted(trades_history, key=lambda t: t.get("date") or "", reverse=True),
    }


def hydrate_with_live_prices(positions_data: dict) -> dict:
    """Add live quote info and unrealized P&L to open positions."""
    enriched = []
    unrealized_total = 0.0
    total_value = 0.0
    total_cost = 0.0
    for pos in positions_data["open_positions"]:
        quote = None
        try:
            quote = market_data.get_quote(pos["symbol"])
        except Exception:
            quote = None
        current_price = quote["price"] if quote else pos["avg_cost"]
        market_value = current_price * pos["shares"]
        cost = pos["avg_cost"] * pos["shares"]
        unrealized = market_value - cost
        unrealized_pct = (unrealized / cost * 100) if cost > 0 else 0
        day_change = ((quote.get("change_percent") if quote else 0) or 0) / 100 * market_value

        unrealized_total += unrealized
        total_value += market_value
        total_cost += cost

        enriched.append({
            **pos,
            "current_price": round(current_price, 2),
            "market_value": round(market_value, 2),
            "cost": round(cost, 2),
            "unrealized_pnl": round(unrealized, 2),
            "unrealized_pnl_pct": round(unrealized_pct, 2),
            "day_change_pct": quote.get("change_percent") if quote else None,
            "day_change_value": round(day_change, 2),
            "name": quote.get("name") if quote else pos["symbol"],
            "sector": quote.get("sector") if quote else None,
        })

    summary = {
        "total_market_value": round(total_value, 2),
        "total_cost_basis": round(total_cost, 2),
        "unrealized_pnl": round(unrealized_total, 2),
        "unrealized_pnl_pct": round((unrealized_total / total_cost * 100) if total_cost > 0 else 0, 2),
        "realized_pnl": positions_data["realized_pnl_total"],
        "total_pnl": round(unrealized_total + positions_data["realized_pnl_total"], 2),
        "day_change_value": round(sum(p["day_change_value"] for p in enriched if p["day_change_value"]), 2),
        "open_positions_count": len(enriched),
    }

    return {
        "summary": summary,
        "positions": sorted(enriched, key=lambda p: p["market_value"], reverse=True),
        "trades_history": positions_data["trades_history"],
        "realized_pnl_by_symbol": positions_data["realized_pnl_by_symbol"],
    }
