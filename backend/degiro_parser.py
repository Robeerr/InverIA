"""DEGIRO-specific PDF parser using pure regex — no AI quota required.

Handles two file types from DEGIRO:
- Transactions.pdf: tabular trade history (BUY/SELL with quantities, prices, fees)
- Account.pdf: cash movements (deposits, fees, dividends, FX conversions, interest)

Uses Finnhub /search?q=ISIN to convert ISINs to tickers, with in-memory + Mongo cache.
"""
import asyncio
import os
import re
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests

logger = logging.getLogger("inveria.degiro")

# Optional Mongo collection for persistent ISIN cache (injected by server on startup)
_mongo_collection = None


def set_mongo_cache(collection):
    """Called by server.py to enable persistent ISIN→ticker caching across restarts."""
    global _mongo_collection
    _mongo_collection = collection

# Strict ISIN: 2 letters + 9 alphanumeric + 1 digit checksum (12 chars total)
ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")

# Transaction line: "DD-MM-YYYY HH:MM <product> <ISIN> <venue> <exch> <qty> <price> <ccy> <localVal> <ccy> <valEUR> <fxRate> <fee> <3rdFee> <totalEUR>"
TX_DATE_LINE = re.compile(r"^(\d{2}-\d{2}-\d{4})\s+(\d{2}:\d{2})\s+(.+)$", re.MULTILINE)
TX_NUM_BLOCK = re.compile(
    r"([A-Z0-9]+)\s+([A-Z0-9]+)\s+"  # venue exch
    r"(-?\d+)\s+"  # qty (signed)
    r"([\d.]+,\d+)\s+"  # price
    r"(\w{3})\s+"  # currency
    r"(-?[\d.]+,\d+)\s+"  # local value
    r"\w{3}\s+"  # ccy
    r"(-?[\d.]+,\d+)\s+"  # value EUR
    r"(\d+,\d+)\s+"  # FX rate
    r"(-?[\d.]+,\d+)\s+"  # fee
    r"(-?[\d.]+,\d+)\s+"  # 3rd party fee
    r"(-?[\d.]+,\d+)"  # total EUR
)

# Account statement line: "DD-MM-YYYY HH:MM DD-MM-YYYY [Product] [ISIN] <Description> [FX] <CCY> <Amount> <CCY> <Balance>"
ACC_LINE = re.compile(
    r"^(\d{2}-\d{2}-\d{4})\s+\d{2}:\d{2}\s+\d{2}-\d{2}-\d{4}\s+(.+)$",
    re.MULTILINE,
)
# Trailing numeric/currency block: <CCY> <amount> <CCY> <balance>
# amount and balance may contain thousands "." and decimal ","
ACC_TRAILING = re.compile(
    r"(\w{3})\s+(-?[\d.]+,\d+)\s+\w{3}\s+(-?[\d.]+,\d+)\s*$"
)
# Optional FX rate before the trailing block
ACC_FX = re.compile(r"\s(\d+,\d+)\s+\w{3}\s+(-?[\d.]+,\d+)\s+\w{3}\s+(-?[\d.]+,\d+)\s*$")

# Description-to-cash-event-type mapping (DEGIRO Spanish wording)
DESC_PATTERNS = [
    (re.compile(r"Costes de transacci[oó]n", re.I), "FEE"),
    (re.compile(r"Comisi[oó]n de conectividad", re.I), "CONNECTIVITY"),
    (re.compile(r"Comisi[oó]n de cambio|FX.*comisi[oó]n|Comisi[oó]n.*divisa", re.I), "FX_FEE"),
    (re.compile(r"Dividendo|Cup[oó]n", re.I), "DIVIDEND"),
    (re.compile(r"Retenci[oó]n", re.I), "DIVIDEND_TAX"),
    (re.compile(r"Inter[eé]s", re.I), "INTEREST"),
    (re.compile(r"Ingreso de cuenta|Dep[oó]sito|Ingreso del usuario|flatex Deposit|Deposit", re.I), "DEPOSIT"),
    (re.compile(r"Retirada de cuenta|Withdrawal|Flatex Withdrawal", re.I), "WITHDRAWAL"),
    (re.compile(r"Cash Sweep|Reembolso", re.I), None),  # internal — skip
    (re.compile(r"Cambio de Divisa|FX", re.I), None),  # FX conversion (not a fee) — skip
    (re.compile(r"Compra |Venta ", re.I), None),  # appears as trade detail — already in Transactions.pdf
    (re.compile(r"datos de mercado|market data", re.I), "MARKET_DATA"),
]


def _num(s: str) -> float:
    """European '1.234,56' → 1234.56"""
    return float(s.replace(".", "").replace(",", "."))


def _yyyymmdd(s: str) -> str:
    """DD-MM-YYYY → YYYY-MM-DD"""
    return f"{s[6:10]}-{s[3:5]}-{s[0:2]}"


# ---- Finnhub ISIN → ticker lookup with cache ----
_symbol_cache: dict = {}


def isin_to_ticker(isin: str, fallback_name: Optional[str] = None) -> Optional[str]:
    """Look up ticker for an ISIN via Finnhub /search. Caches results.
    Returns None if not found (caller can keep ISIN/name as symbol)."""
    if isin in _symbol_cache:
        return _symbol_cache[isin]
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return None
    _md.get_finnhub_limiter().acquire()
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/search",
            params={"q": isin, "token": key},
            timeout=6,
        )
        if r.status_code == 429:
            time.sleep(2)
            _md.get_finnhub_limiter().acquire()
            r = requests.get(
                "https://finnhub.io/api/v1/search",
                params={"q": isin, "token": key},
                timeout=6,
            )
        if r.status_code == 200:
            matches = (r.json() or {}).get("result", [])
            if matches:
                sym = matches[0].get("symbol")
                if sym:
                    _symbol_cache[isin] = sym
                    return sym
        # Fall back to name search
        if fallback_name:
            cleaned = re.sub(r"\s+(INC|CORP|CORPORATION|LTD|PLC|NV|SA|AG|CLASS [A-Z])\b", "", fallback_name, flags=re.I).strip()
            if cleaned:
                _md.get_finnhub_limiter().acquire()
                r = requests.get(
                    "https://finnhub.io/api/v1/search",
                    params={"q": cleaned, "token": key},
                    timeout=6,
                )
                if r.status_code == 200:
                    matches = (r.json() or {}).get("result", [])
                    if matches:
                        sym = matches[0].get("symbol")
                        if sym:
                            _symbol_cache[isin] = sym
                            return sym
    except Exception as e:
        logger.warning(f"ISIN lookup failed for {isin}: {e}")
    _symbol_cache[isin] = None
    return None


# ---- Public parsers ----
def _extract_tx_raw(text: str) -> list[dict]:
    """Stage 1: extract raw transactions without ticker lookup."""
    out = []
    for m in TX_DATE_LINE.finditer(text):
        date = m.group(1)
        rest = m.group(3)
        isin_m = ISIN_RE.search(rest)
        if not isin_m:
            continue
        isin = isin_m.group(1)
        product = rest[: isin_m.start()].strip()
        after = rest[isin_m.end():]
        nm = TX_NUM_BLOCK.search(after)
        if not nm:
            continue
        venue, exch, qty, price, ccy, lv, ve, fx, fee, fee3, total = nm.groups()
        try:
            qty_int = int(qty)
            shares = abs(qty_int)
            if shares == 0:
                continue
            out.append({
                "date": _yyyymmdd(date),
                "isin": isin,
                "product": product,
                "action": "BUY" if qty_int > 0 else "SELL",
                "shares": shares,
                "price": _num(price),
                "currency": ccy,
                "fees": round(abs(_num(fee)) + abs(_num(fee3)), 2),
                "fx_rate": _num(fx),
                "broker": "DEGIRO",
            })
        except Exception as e:
            logger.warning(f"Skip tx line: {e}")
            continue
    return out


def _extract_account_raw(text: str) -> list[dict]:
    """Stage 1: extract raw cash events without ticker lookup."""
    out = []
    for m in ACC_LINE.finditer(text):
        date = m.group(1)
        rest = m.group(2).strip()
        trailing = ACC_FX.search(rest)
        if trailing:
            amount = _num(trailing.group(2))
            desc_part = rest[: trailing.start()].strip()
        else:
            trailing = ACC_TRAILING.search(rest)
            if not trailing:
                continue
            amount = _num(trailing.group(2))
            desc_part = rest[: trailing.start()].strip()
        isin_in_desc = ISIN_RE.search(desc_part)
        if isin_in_desc:
            symbol_isin = isin_in_desc.group(1)
            desc_no_isin = (desc_part[: isin_in_desc.start()] + desc_part[isin_in_desc.end():]).strip()
        else:
            symbol_isin = None
            desc_no_isin = desc_part
        ev_type = "OTHER"
        skip = False
        for pat, t in DESC_PATTERNS:
            if pat.search(desc_no_isin):
                if t is None:
                    skip = True
                else:
                    ev_type = t
                break
        if skip:
            continue
        out.append({
            "date": _yyyymmdd(date),
            "type": ev_type,
            "amount": amount,
            "currency": trailing.group(1),
            "description": desc_no_isin[:160],
            "isin": symbol_isin,
            "broker": "DEGIRO",
        })
    return out


async def _resolve_isins_parallel(isin_products: list[tuple[str, Optional[str]]]) -> dict:
    """Resolve multiple ISIN→ticker pairs in parallel using a thread pool.
    Mongo cache is consulted first; misses go to Finnhub.
    Returns: dict[isin → ticker_or_None]"""
    if not isin_products:
        return {}

    # Step 1: load from Mongo cache (one batch query)
    isins = list({i for i, _ in isin_products if i})
    cached = {}
    if _mongo_collection is not None and isins:
        try:
            async for doc in _mongo_collection.find({"isin": {"$in": isins}}):
                cached[doc["isin"]] = doc.get("ticker")
                if doc.get("ticker"):
                    _symbol_cache[doc["isin"]] = doc["ticker"]
        except Exception as e:
            logger.warning(f"Mongo cache read failed: {e}")

    # Step 2: identify misses & run Finnhub lookups in parallel
    misses = [(i, p) for i, p in isin_products if i not in cached and i not in _symbol_cache]
    if misses:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [
                loop.run_in_executor(pool, isin_to_ticker, isin, prod)
                for isin, prod in misses
            ]
            results = await asyncio.gather(*futures, return_exceptions=True)
        for (isin, _), result in zip(misses, results):
            tk = result if isinstance(result, str) else None
            cached[isin] = tk
            # Write to Mongo (best effort)
            if _mongo_collection is not None:
                try:
                    await _mongo_collection.update_one(
                        {"isin": isin},
                        {"$set": {"isin": isin, "ticker": tk, "updated_at": time.time()}},
                        upsert=True,
                    )
                except Exception as e:
                    logger.warning(f"Mongo cache write failed for {isin}: {e}")

    # Merge with in-memory cache (covers items already known before this call)
    for i, _ in isin_products:
        if i not in cached and i in _symbol_cache:
            cached[i] = _symbol_cache[i]
    return cached


async def parse_transactions_pdf(text: str) -> list[dict]:
    """Parse a DEGIRO Transactions.pdf text. Returns transactions with tickers resolved
    in parallel via Finnhub /search (Mongo-cached)."""
    raw = _extract_tx_raw(text)
    if not raw:
        return []
    # Unique ISINs only (avoid duplicate lookups when same stock traded multiple times)
    seen = {}
    for tx in raw:
        seen.setdefault(tx["isin"], tx["product"])
    resolved = await _resolve_isins_parallel(list(seen.items()))
    # Attach symbol
    for tx in raw:
        tx["symbol"] = resolved.get(tx["isin"]) or tx["isin"]
    return raw


async def parse_account_pdf(text: str) -> list[dict]:
    """Parse a DEGIRO Account.pdf text. Returns cash_events with symbol enrichment
    for entries that reference a product."""
    raw = _extract_account_raw(text)
    if not raw:
        return []
    seen = {}
    for ev in raw:
        if ev.get("isin"):
            seen.setdefault(ev["isin"], None)
    resolved = await _resolve_isins_parallel(list(seen.items())) if seen else {}
    for ev in raw:
        ev["symbol"] = resolved.get(ev.get("isin")) if ev.get("isin") else None
        ev.pop("isin", None)
    return raw


def is_degiro_transactions(text: str) -> bool:
    """Quick heuristic to detect a DEGIRO Transactions.pdf."""
    return bool(
        re.search(r"Transactions from|Transacciones desde", text)
        or (re.search(r"DEGIRO", text, re.I) and re.search(r"AutoFX|Reference Exchange|Venue", text, re.I))
    )


def is_degiro_account(text: str) -> bool:
    """Quick heuristic to detect a DEGIRO Account.pdf."""
    return bool(
        re.search(r"Account statement from|Extracto de cuenta", text, re.I)
        or (re.search(r"DEGIRO", text, re.I) and re.search(r"Cambio de Divisa|Cash Sweep", text, re.I))
    )
