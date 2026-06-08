"""
degiro_csv_parser.py — Parser de CSVs de DEGIRO para InverIA
Procesa Transactions.csv y Account.csv sin IA, directo desde los datos estructurados.
Calcula P&L FIFO, comisiones, dividendos, posiciones abiertas y cerradas.

v2 — usa nombres de columna (DictReader) en vez de índices fijos para ser
     robusto ante diferencias entre exportaciones ES/EN y distintos formatos.
"""

import csv
import io
from collections import defaultdict, deque
from datetime import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_num(s):
    """
    Convierte número en formato europeo ('1.234,56' o '-1,79') o anglosajón
    ('1,234.56') a float. Devuelve 0.0 si el valor está vacío o no parseable.
    """
    if s is None:
        return 0.0
    s = str(s).strip().strip('"').strip()
    if s in ("", "-", "—", "n/a", "N/A"):
        return 0.0
    # Detect format: if last separator is comma → European; if last is dot → US
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")
    if last_comma > last_dot:
        # European: remove dots (thousand sep), replace comma with dot
        s = s.replace(".", "").replace(",", ".")
    else:
        # US/standard: remove commas (thousand sep)
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date(s):
    """dd-MM-yyyy o dd/MM/yyyy o yyyy-MM-dd → datetime."""
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except Exception:
            pass
    return None


def _detect_delimiter(content: str) -> str:
    """Detecta si el CSV usa ; o , como separador."""
    first_line = content.split("\n")[0]
    if first_line.count(";") > first_line.count(","):
        return ";"
    return ","


def _normalize_key(s: str) -> str:
    """Normaliza nombre de columna para búsqueda case-insensitive."""
    return s.lower().strip().replace(" ", "").replace("_", "").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")


def _find_col(row: dict, *candidates) -> str:
    """Busca el primer candidato que exista en el DictReader row (normalizado)."""
    norm_map = {_normalize_key(k): k for k in row.keys()}
    for c in candidates:
        key = _normalize_key(c)
        if key in norm_map:
            return row[norm_map[key]]
    return ""


# ── ISIN → Ticker map ─────────────────────────────────────────────────────────
ISIN_TO_TICKER = {
    "US0378331005": "AAPL", "US88160R1014": "TSLA", "US5949181045": "MSFT",
    "US0231351067": "AMZN", "US02079K3059": "GOOGL", "US30303M1027": "META",
    "US67066G1040": "NVDA", "US64110L1061": "NFLX", "US75734B1008": "RDDT",
    "US68389X1054": "ORCL", "US65339F1012": "NEE", "KYG3323L1005": "FN",
    "US5738741041": "MRVL", "US03823U1025": "AAOI", "US3463751087": "FORM",
    "US83417M1045": "SEDG", "US11135F1012": "AVGO", "US97785W1062": "WOLF",
    "US55608B1052": "MELI", "US09075V1026": "BKNG", "CA82509L1076": "SHOP",
    "US70450Y1038": "PTON", "US7475251036": "QCOM", "US4592001014": "IBM",
    "US90353T1007": "UBER", "US65290E1010": "NEX", "US74967X1037": "RH",
    "US4404521001": "HPQ", "US90184L1026": "TDC", "US78468R1014": "SSYS",
    "US02156V1098": "OKLO", "US78462F1030": "SPY", "US4642872422": "IVV",
    "US46090E1038": "IWM", "US43289P1066": "HIMX", "US92345Y1064": "VTI",
    "US9229087690": "VWO", "US9220427424": "VEA", "NL0010273215": "ASML",
    "US46120E6023": "QQQ", "US46138E1073": "QQEW", "US38150A1051": "GOOG",
    "US1491231015": "CELH", "US4810941030": "ISRG", "US7730171052": "ROKU",
    "US7561091049": "RBLX", "US7433151039": "PSNY", "US77468Y1001": "RKLB",
    "US7762161013": "RBBN", "US8490781020": "SMCI", "US87236Y1082": "TMDX",
    "US90187B4082": "UPST", "US9032661081": "UIPI", "US06558T1007": "BBAI",
    "US81752R1059": "SFIX", "US2003872064": "COIN", "US44107P1049": "HST",
    "US9314271084": "WRBY", "US44891N2080": "IBKR", "US7134481081": "PENN",
    "US8243481061": "SHOP", "US21874G1040": "CRWV",
}

PRODUCT_TO_TICKER = {
    "NVIDIA CORP": "NVDA", "NETFLIX INC": "NFLX",
    "META PLATFORMS INC CLASS A": "META", "META PLATFORMS INC. CLASS A": "META",
    "ORACLE CORP": "ORCL", "NEXTERA ENERGY INC": "NEE",
    "NEXTERA ENERGY INC.": "NEE", "FABRINET": "FN",
    "MARVELL TECHNOLOGY INC": "MRVL", "MARVELL TECHNOLOGY INC.": "MRVL",
    "APPLIED OPTOELECTRONICS INC": "AAOI", "APPLIED OPTOELECTRONICS INC.": "AAOI",
    "FORMFACTOR INC": "FORM", "FORMFACTOR INC.": "FORM",
    "SOLAREDGE TECHNOLOGIES INC": "SEDG", "SOLAREDGE TECHNOLOGIES INC.": "SEDG",
    "BROADCOM INC": "AVGO", "BROADCOM INC.": "AVGO",
    "WOLFSPEED INC": "WOLF", "WOLFSPEED INC.": "WOLF",
    "REDDIT INC CLASS A": "RDDT", "REDDIT INC. CLASS A": "RDDT",
    "SHOPIFY INC CLASS A": "SHOP", "SHOPIFY INC. CLASS A": "SHOP",
    "RH": "RH", "OKLO INC CLASS A": "OKLO", "OKLO INC. CLASS A": "OKLO",
    "UBER TECHNOLOGIES INC": "UBER", "UBER TECHNOLOGIES INC.": "UBER",
    "TESLA INC": "TSLA", "TESLA INC.": "TSLA",
    "AMAZON.COM INC": "AMZN", "AMAZON.COM INC.": "AMZN",
    "ALPHABET INC CLASS A": "GOOGL", "ALPHABET INC. CLASS A": "GOOGL",
    "MICROSOFT CORP": "MSFT", "MICROSOFT CORP.": "MSFT",
    "ADR ON HIMAX TECHNOLOGIES INC": "HIMX",
    "MERCADOLIBRE INC": "MELI", "MERCADOLIBRE INC.": "MELI",
    "NEXTPOWER INC CLASS A": "NEX",
    "TRANSMEDICS GROUP INC": "TMDX", "TRANSMEDICS GROUP INC.": "TMDX",
    "UPSTART HOLDINGS INC": "UPST", "UPSTART HOLDINGS INC.": "UPST",
    "ROBLOX CORP CLASS A": "RBLX", "ROBLOX CORP. CLASS A": "RBLX",
    "ROCKET LAB CORP": "RKLB", "ROCKET LAB CORP.": "RKLB",
    "SUPER MICRO COMPUTER INC": "SMCI", "SUPER MICRO COMPUTER INC.": "SMCI",
    "AST SPACEMOBILE INC CLASS A": "ASTS", "AST SPACEMOBILE INC. CLASS A": "ASTS",
    "AFFIRM HOLDINGS INC CLASS A": "AFRM", "AFFIRM HOLDINGS INC. CLASS A": "AFRM",
    "CARVANA CO CLASS A": "CVNA", "CARVANA CO. CLASS A": "CVNA",
    "COHERENT CORP": "COHR", "COHERENT CORP.": "COHR",
    "COREWEAVE INC CLASS A": "CRWV", "COREWEAVE INC. CLASS A": "CRWV",
    "COREWEAVE INC": "CRWV",
    "D-WAVE QUANTUM INC": "QBTS", "D-WAVE QUANTUM INC.": "QBTS",
    "DUOLINGO INC CLASS A": "DUOL", "DUOLINGO INC. CLASS A": "DUOL",
    "FERRARI NV": "RACE", "FORTINET INC": "FTNT", "FORTINET INC.": "FTNT",
    "MP MATERIALS CORP CLASS A": "MP", "MP MATERIALS CORP. CLASS A": "MP",
    "OUTSET MEDICAL INC": "OM", "OUTSET MEDICAL INC.": "OM",
    "PALANTIR TECHNOLOGIES INC CLASS A": "PLTR",
    "PALANTIR TECHNOLOGIES INC. CLASS A": "PLTR",
    "PLUG POWER INC": "PLUG", "PLUG POWER INC.": "PLUG",
    "RIGETTI COMPUTING INC": "RGTI", "RIGETTI COMPUTING INC.": "RGTI",
    "RUBRIK INC CLASS A": "RBRK", "RUBRIK INC. CLASS A": "RBRK",
    "TEMPUS AI INC CLASS A": "TEM", "TEMPUS AI INC. CLASS A": "TEM",
    "TRADE DESK INC CLASS A": "TTD", "TRADE DESK INC. CLASS A": "TTD",
    "UIPATH INC CLASS A": "PATH", "UIPATH INC. CLASS A": "PATH",
    "VERITONE INC": "VERI", "VERITONE INC.": "VERI",
    "IBERDROLA SA": "IBE.MC", "BYD CO LTD": "1211.HK",
    "LVMH MOET HENNESSY LOUIS VUITTON SE": "MC.PA",
    "OBRASCON HUARTE LAIN SA": "OHL.MC",
}


def _get_ticker(isin: str, product: str) -> str:
    if isin:
        isin = isin.strip()
        if isin in ISIN_TO_TICKER:
            return ISIN_TO_TICKER[isin]
    if product:
        # Try exact match (uppercase)
        key = product.upper().strip()
        if key in PRODUCT_TO_TICKER:
            return PRODUCT_TO_TICKER[key]
        # Try removing trailing punctuation and common suffixes
        key2 = key.rstrip(".").rstrip(",")
        if key2 in PRODUCT_TO_TICKER:
            return PRODUCT_TO_TICKER[key2]
    # Fallback: use ISIN (so buys and sells still match each other)
    return isin or product or "?"


# ── CSV Parsers ───────────────────────────────────────────────────────────────

def parse_transactions_csv(content: str) -> list:
    """
    Parsea Transactions.csv de DEGIRO usando DictReader (robusto ante cambios
    de formato ES/EN y ante posición de columnas).

    Columnas clave buscadas:
      - Fecha / Date
      - Producto / Product
      - Código ISIN / ISIN
      - Cantidad / Quantity
      - Precio / Price
      - Divisa precio / (price currency)
      - Tipo de cambio / Exchange rate
      - AutoFX
      - Comisiones de transacción / Transaction and/or third party fees / Fees
      - Total
      - ID Orden / Order ID
    """
    delimiter = _detect_delimiter(content)
    trades = []
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

    for row in reader:
        try:
            # ── Date ────────────────────────────────────────────────────────
            date_str = _find_col(row,
                "Fecha", "Date", "fecha", "date")
            date = _parse_date(date_str)
            if not date:
                continue

            # ── Product / ISIN ───────────────────────────────────────────────
            product = _find_col(row,
                "Producto", "Product", "producto", "product").strip()
            isin = _find_col(row,
                "Código ISIN", "ISIN", "Codigo ISIN", "codigo isin", "isin").strip()

            # ── Quantity ─────────────────────────────────────────────────────
            quantity = _parse_num(_find_col(row,
                "Cantidad", "Quantity", "cantidad", "quantity"))
            if quantity == 0:
                continue

            # ── Price (in stock currency) ────────────────────────────────────
            price = _parse_num(_find_col(row,
                "Precio", "Price", "precio", "price"))
            price_ccy = _find_col(row,
                "Divisa precio", "Currency", "divisa precio").strip() or "USD"

            # ── Exchange rate ─────────────────────────────────────────────────
            exchange_rate = _parse_num(_find_col(row,
                "Tipo de cambio", "Exchange rate", "tipo de cambio",
                "exchange rate", "exchangerate")) or 1.0

            # ── AutoFX fee ────────────────────────────────────────────────────
            autofx_fee = abs(_parse_num(_find_col(row,
                "AutoFX", "autofx", "Auto FX", "auto fx")))

            # ── Transaction fees ──────────────────────────────────────────────
            tx_fee = abs(_parse_num(_find_col(row,
                "Comisiones de transacción", "Comisiones de transaccion",
                "Transaction and/or third party fees", "Transaction fees",
                "Fees", "comisiones de transaccion", "comisiones")))

            # ── Total (all-in EUR, most important for cost calculation) ───────
            total_eur = _parse_num(_find_col(row,
                "Total", "total"))

            # ── Value EUR (trade value without fees) ──────────────────────────
            value_eur = abs(_parse_num(_find_col(row,
                "Valor", "Value", "valor", "value")))

            ticker = _get_ticker(isin, product)
            action = "BUY" if quantity > 0 else "SELL"
            shares = abs(quantity)

            # All-in cost/proceeds in EUR
            total_abs = abs(total_eur)

            # Fallback: if total is 0 or missing, reconstruct from value + fees
            if total_abs < 0.01:
                total_abs = value_eur + autofx_fee + tx_fee

            cost_per_share = total_abs / shares if shares else 0

            trades.append({
                "date": date,
                "date_str": date_str.strip(),
                "product": product,
                "isin": isin,
                "ticker": ticker,
                "action": action,
                "shares": shares,
                "price": price,
                "price_ccy": price_ccy,
                "value_eur": value_eur,
                "autofx_fee": autofx_fee,
                "tx_fee": tx_fee,
                "total_eur": total_abs,
                "cost_per_share": cost_per_share,
                "exchange_rate": exchange_rate,
            })
        except Exception:
            continue

    return trades


def parse_account_csv(content: str) -> list:
    """
    Parsea Account.csv de DEGIRO usando DictReader.
    """
    delimiter = _detect_delimiter(content)
    events = []
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

    for row in reader:
        try:
            date_str = _find_col(row, "Fecha", "Date", "fecha", "date")
            date = _parse_date(date_str)
            if not date:
                continue

            product = _find_col(row, "Producto", "Product", "producto", "product").strip()
            isin    = _find_col(row, "Código ISIN", "ISIN", "Codigo ISIN", "isin").strip()
            desc    = _find_col(row, "Descripción", "Description", "descripcion", "description").strip()

            # Change amount (may be in EUR or USD depending on row)
            change_ccy = _find_col(row, "Divisa", "Currency", "divisa", "currency").strip()
            change     = _parse_num(_find_col(row, "Variación", "Change", "variacion", "change"))
            balance    = _parse_num(_find_col(row, "Saldo", "Balance", "saldo", "balance"))
            balance_ccy = change_ccy  # same currency column for balance in most exports

            desc_lower = desc.lower()
            if desc_lower.startswith("compra ") or desc_lower.startswith("venta ") \
                    or desc_lower.startswith("buy ") or desc_lower.startswith("sell "):
                event_type = "TRADE"
            elif "costes de transacción" in desc_lower or "costes de transaccion" in desc_lower \
                    or "transaction costs" in desc_lower:
                event_type = "TX_FEE"
            elif "comisión tiempo real" in desc_lower or "comision tiempo real" in desc_lower \
                    or "real-time" in desc_lower:
                event_type = "MARKET_DATA"
            elif "comisión de conectividad" in desc_lower or "comision de conectividad" in desc_lower \
                    or "connectivity" in desc_lower:
                event_type = "CONNECTIVITY"
            elif "comisión cierre" in desc_lower or "closure fee" in desc_lower:
                event_type = "CLOSURE_FEE"
            elif "ingreso cambio de divisa" in desc_lower or "fx credit" in desc_lower:
                event_type = "FX_IN"
            elif "retirada cambio de divisa" in desc_lower or "fx debit" in desc_lower:
                event_type = "FX_OUT"
            elif ("dividendo" in desc_lower or "dividend" in desc_lower) \
                    and "retención" not in desc_lower and "retencion" not in desc_lower \
                    and "tax" not in desc_lower:
                event_type = "DIVIDEND"
            elif "retención del dividendo" in desc_lower or "retencion del dividendo" in desc_lower \
                    or "dividend tax" in desc_lower or "withholding" in desc_lower:
                event_type = "DIVIDEND_TAX"
            elif "impuesto de transacción" in desc_lower or "transaction tax" in desc_lower \
                    or "spanish transaction tax" in desc_lower:
                event_type = "TX_TAX"
            elif "flatex instant deposit" in desc_lower or "flatex deposit" in desc_lower \
                    or desc_lower.strip() == "ingreso" or "deposit" in desc_lower:
                event_type = "DEPOSIT"
            elif "flatex withdrawal" in desc_lower or "processed flatex withdrawal" in desc_lower \
                    or "withdrawal" in desc_lower:
                event_type = "WITHDRAWAL"
            elif "interés" in desc_lower or "interes" in desc_lower or "interest" in desc_lower:
                event_type = "INTEREST"
            elif "deslistamiento" in desc_lower or "delisting" in desc_lower:
                event_type = "DELISTING"
            elif "transferir" in desc_lower or "transfer" in desc_lower or "cash sweep" in desc_lower:
                event_type = "TRANSFER"
            elif "comisión por transferencia" in desc_lower or "transfer fee" in desc_lower:
                event_type = "TRANSFER_FEE"
            else:
                event_type = "OTHER"

            ticker = _get_ticker(isin, product) if (isin or product) else None

            events.append({
                "date": date,
                "date_str": date_str.strip(),
                "product": product,
                "isin": isin,
                "ticker": ticker,
                "description": desc,
                "event_type": event_type,
                "change_ccy": change_ccy,
                "change": change,
                "balance_ccy": balance_ccy,
                "balance": balance,
            })
        except Exception:
            continue

    return events


# ── FIFO P&L Calculator ───────────────────────────────────────────────────────

def calculate_portfolio(trades: list, events: list) -> dict:
    """
    Calcula posiciones abiertas, P&L realizado por símbolo y resumen global.
    Usa FIFO para calcular el coste base de cada venta.
    """
    # Sort trades by date ASC
    trades_sorted = sorted(trades, key=lambda x: (x["date"], x["date_str"]))

    # Per-ticker buy queues: deque of {shares, cost_per_share, date, ...}
    buy_queues = defaultdict(deque)
    # Per-ticker open position tracker
    open_positions = {}
    closed_trades = []

    for trade in trades_sorted:
        ticker = trade["ticker"]
        shares = trade["shares"]
        cost_per_share = trade["cost_per_share"]  # all-in EUR per share

        if trade["action"] == "BUY":
            buy_queues[ticker].append({
                "shares": shares,
                "cost_per_share": cost_per_share,
                "date": trade["date_str"],
            })
            if ticker not in open_positions:
                open_positions[ticker] = {
                    "ticker": ticker,
                    "product": trade["product"],
                    "isin": trade["isin"],
                    "shares": 0.0,
                    "total_cost": 0.0,
                }
            open_positions[ticker]["shares"] += shares
            open_positions[ticker]["total_cost"] += shares * cost_per_share

        elif trade["action"] == "SELL":
            queue = buy_queues[ticker]
            remaining_sell = shares
            sell_proceeds_per_share = cost_per_share  # all-in proceeds per share

            realized_pnl = 0.0
            buy_cost_total = 0.0
            matched_shares = 0.0
            first_buy_date = None

            while remaining_sell > 0.0001 and queue:
                lot = queue[0]
                if first_buy_date is None:
                    first_buy_date = lot["date"]

                take = min(lot["shares"], remaining_sell)
                buy_cost_total += take * lot["cost_per_share"]
                realized_pnl += take * (sell_proceeds_per_share - lot["cost_per_share"])
                matched_shares += take
                lot["shares"] -= take
                remaining_sell -= take
                if lot["shares"] < 0.0001:
                    queue.popleft()

            # Reduce open position cost proportionally
            if ticker in open_positions:
                pos = open_positions[ticker]
                sold_matched = matched_shares
                if pos["shares"] > 0.0001:
                    avg = pos["total_cost"] / pos["shares"]
                    pos["shares"] = max(0.0, pos["shares"] - sold_matched)
                    pos["total_cost"] = pos["shares"] * avg
                else:
                    pos["shares"] = 0.0
                    pos["total_cost"] = 0.0

            if matched_shares > 0.0001:
                sell_proceeds = matched_shares * sell_proceeds_per_share
                pnl_pct = (realized_pnl / buy_cost_total * 100) if buy_cost_total > 0 else 0
                closed_trades.append({
                    "ticker": ticker,
                    "product": trade["product"],
                    "sell_date": trade["date_str"],
                    "buy_date": first_buy_date or "?",
                    "shares": round(matched_shares, 4),
                    "sell_price_eur": round(sell_proceeds_per_share, 4),
                    "buy_cost_eur": round(buy_cost_total / matched_shares, 4),
                    "sell_proceeds_eur": round(sell_proceeds, 2),
                    "buy_cost_total_eur": round(buy_cost_total, 2),
                    "realized_pnl_eur": round(realized_pnl, 2),
                    "realized_pnl_pct": round(pnl_pct, 2),
                })

    # Build open positions list (only those with remaining shares)
    open_pos_list = []
    for ticker, pos in open_positions.items():
        if pos["shares"] > 0.01:
            avg_cost = pos["total_cost"] / pos["shares"]
            open_pos_list.append({
                "ticker": ticker,
                "product": pos["product"],
                "isin": pos["isin"],
                "shares": round(pos["shares"], 4),
                "avg_cost_eur": round(avg_cost, 4),
                "total_cost_eur": round(pos["total_cost"], 2),
            })

    # ── Stats from Account.csv ───────────────────────────────────────────────
    stats = {
        "tx_fees": 0.0,
        "autofx_fees": 0.0,
        "market_data_fees": 0.0,
        "connectivity_fees": 0.0,
        "tx_taxes": 0.0,
        "closure_fees": 0.0,
        "transfer_fees": 0.0,
        "dividends": 0.0,
        "dividend_tax": 0.0,
        "deposits": 0.0,
        "withdrawals": 0.0,
        "interest": 0.0,
        "cash_balance": 0.0,
    }
    dividends_detail = []
    last_eur_balance = None

    for ev in sorted(events, key=lambda x: x["date"]):
        t = ev["event_type"]
        change = ev["change"]
        ccy = ev["change_ccy"]
        if ccy != "EUR":
            continue

        if t == "TX_FEE":
            stats["tx_fees"] += abs(change)
        elif t == "MARKET_DATA":
            stats["market_data_fees"] += abs(change)
        elif t == "CONNECTIVITY":
            stats["connectivity_fees"] += abs(change)
        elif t == "CLOSURE_FEE":
            stats["closure_fees"] += abs(change)
        elif t == "TRANSFER_FEE":
            stats["transfer_fees"] += abs(change)
        elif t == "TX_TAX":
            stats["tx_taxes"] += abs(change)
        elif t == "DIVIDEND":
            stats["dividends"] += abs(change)
            dividends_detail.append({
                "date": ev["date_str"],
                "ticker": ev["ticker"],
                "product": ev["product"],
                "amount": round(abs(change), 2),
                "currency": ccy,
            })
        elif t == "DIVIDEND_TAX":
            stats["dividend_tax"] += abs(change)
        elif t == "DEPOSIT":
            stats["deposits"] += abs(change)
        elif t == "WITHDRAWAL":
            stats["withdrawals"] += abs(change)
        elif t == "INTEREST":
            stats["interest"] += change

        if ev.get("balance_ccy") == "EUR" and ev["balance"] != 0:
            last_eur_balance = ev["balance"]

    stats["autofx_fees"] = sum(t["autofx_fee"] for t in trades)
    stats["cash_balance"] = last_eur_balance or 0.0
    stats["total_fees"] = round(
        stats["tx_fees"] + stats["autofx_fees"] + stats["market_data_fees"] +
        stats["connectivity_fees"] + stats["tx_taxes"] + stats["closure_fees"] +
        stats["transfer_fees"], 2
    )

    # ── Aggregated realized P&L ──────────────────────────────────────────────
    total_realized = sum(ct["realized_pnl_eur"] for ct in closed_trades)
    total_invested = sum(p["total_cost_eur"] for p in open_pos_list)
    winning = sum(1 for ct in closed_trades if ct["realized_pnl_eur"] > 0)
    losing  = sum(1 for ct in closed_trades if ct["realized_pnl_eur"] < 0)
    win_rate = (winning / len(closed_trades) * 100) if closed_trades else 0

    return {
        "open_positions": sorted(open_pos_list, key=lambda x: x["total_cost_eur"], reverse=True),
        "closed_trades": sorted(closed_trades, key=lambda x: x["sell_date"], reverse=True),
        "dividends_detail": sorted(dividends_detail, key=lambda x: x["date"], reverse=True),
        "stats": {k: round(v, 2) for k, v in stats.items()},
        "summary": {
            "total_realized_pnl": round(total_realized, 2),
            "total_invested_eur": round(total_invested, 2),
            "total_trades": len(trades),
            "buy_trades": sum(1 for t in trades if t["action"] == "BUY"),
            "sell_trades": sum(1 for t in trades if t["action"] == "SELL"),
            "closed_positions": len(set(ct["ticker"] for ct in closed_trades)),
            "open_positions_count": len(open_pos_list),
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": round(win_rate, 1),
            "total_fees": stats["total_fees"],
            "total_dividends": round(stats["dividends"], 2),
            "net_deposits": round(stats["deposits"] - stats["withdrawals"], 2),
            "cash_balance": round(stats["cash_balance"], 2),
        }
    }
