"""
degiro_csv_parser.py — Parser de CSVs de DEGIRO para InverIA
Procesa Transactions.csv y Account.csv sin IA, directo desde los datos estructurados.
Calcula P&L FIFO, comisiones, dividendos, posiciones abiertas y cerradas.
"""

import csv
import io
import re
from collections import defaultdict
from datetime import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_num(s):
    """Convierte número europeo '1.234,56' o '-1,79' a float."""
    if s is None:
        return 0.0
    s = str(s).strip().strip('"').strip()
    if s in ("", "-", "—"):
        return 0.0
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date(s):
    """dd-MM-yyyy → datetime."""
    try:
        return datetime.strptime(s.strip(), "%d-%m-%Y")
    except Exception:
        return None


def _norm_symbol(isin, product):
    """Intenta extraer el ticker del nombre del producto o devuelve el ISIN como fallback."""
    return isin or product or "?"


# ── ISIN → Ticker map (los más comunes en DEGIRO) ─────────────────────────────
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
    "US8243481061": "SHOP",
}

PRODUCT_TO_TICKER = {
    "NVIDIA CORP": "NVDA", "NETFLIX INC": "NFLX", "META PLATFORMS INC CLASS A": "META",
    "ORACLE CORP": "ORCL", "NEXTERA ENERGY INC": "NEE", "FABRINET": "FN",
    "MARVELL TECHNOLOGY INC": "MRVL", "APPLIED OPTOELECTRONICS INC": "AAOI",
    "FORMFACTOR INC": "FORM", "SOLAREDGE TECHNOLOGIES INC": "SEDG",
    "BROADCOM INC": "AVGO", "WOLFSPEED INC": "WOLF", "REDDIT INC CLASS A": "RDDT",
    "SHOPIFY INC CLASS A": "SHOP", "RH": "RH", "OKLO INC CLASS A": "OKLO",
    "UBER TECHNOLOGIES INC": "UBER", "TESLA INC": "TSLA", "AMAZON.COM INC": "AMZN",
    "ALPHABET INC CLASS A": "GOOGL", "MICROSOFT CORP": "MSFT",
    "ADR ON HIMAX TECHNOLOGIES INC": "HIMX", "MERCADOLIBRE INC": "MELI",
    "NEXTPOWER INC CLASS A": "NEX", "TRANSMEDICS GROUP INC": "TMDX",
    "UPSTART HOLDINGS INC": "UPST", "ROBLOX CORP CLASS A": "RBLX",
    "ROCKET LAB CORP": "RKLB", "SUPER MICRO COMPUTER INC": "SMCI",
    "AST SPACEMOBILE INC CLASS A": "ASTS", "AFFIRM HOLDINGS INC CLASS A": "AFRM",
    "CARVANA CO CLASS A": "CVNA", "COHERENT CORP": "COHR",
    "COREWEAVE INC CLASS A": "CRWV", "D-WAVE QUANTUM INC": "QBTS",
    "DUOLINGO INC CLASS A": "DUOL", "FERRARI NV": "RACE",
    "FORTINET INC": "FTNT", "MP MATERIALS CORP CLASS A": "MP",
    "OUTSET MEDICAL INC": "OM", "PALANTIR TECHNOLOGIES INC CLASS A": "PLTR",
    "PLUG POWER INC": "PLUG", "RIGETTI COMPUTING INC": "RGTI",
    "RUBRIK INC CLASS A": "RBRK", "TEMPUS AI INC CLASS A": "TEM",
    "TRADE DESK INC CLASS A": "TTD", "UIPATH INC CLASS A": "PATH",
    "VERITONE INC": "VERI", "CAI INC CLASS A": "CAI",
    "SHIFT PAYMENTS INC CLASS A": "SFT",
    "IBERDROLA SA": "IBE.MC", "BYD CO LTD": "1211.HK",
    "LVMH MOET HENNESSY LOUIS VUITTON SE": "MC.PA",
    "OBRASCON HUARTE LAIN SA": "OHL.MC",
}


def _get_ticker(isin, product):
    if isin and isin in ISIN_TO_TICKER:
        return ISIN_TO_TICKER[isin]
    if product:
        key = product.upper().strip()
        if key in PRODUCT_TO_TICKER:
            return PRODUCT_TO_TICKER[key]
    return isin or product or "?"


# ── CSV Parsers ───────────────────────────────────────────────────────────────

def parse_transactions_csv(content: str) -> list:
    """
    Parsea Transactions.csv de DEGIRO.
    Columnas: Date,Time,Product,ISIN,Reference exchange,Venue,Quantity,
              Price,[CCY],Local value,[CCY],Value EUR,Exchange rate,
              AutoFX Fee,Transaction fees EUR,Total EUR,Order ID
    """
    trades = []
    reader = csv.reader(io.StringIO(content))
    headers = next(reader, None)  # skip header
    for row in reader:
        if len(row) < 15:
            continue
        try:
            date = _parse_date(row[0])
            if not date:
                continue
            product = row[2].strip()
            isin = row[3].strip()
            quantity = _parse_num(row[6])  # positive=buy, negative=sell
            price = _parse_num(row[7])
            price_ccy = row[8].strip() if len(row) > 8 else "USD"
            local_value = _parse_num(row[9])
            value_eur = _parse_num(row[11])
            exchange_rate = _parse_num(row[12]) or 1.0
            autofx_fee = _parse_num(row[13])    # negative
            tx_fee = _parse_num(row[14])         # negative (€2)
            total_eur = _parse_num(row[15])      # negative=buy, positive=sell
            order_id = row[16].strip() if len(row) > 16 else ""

            if quantity == 0:
                continue

            ticker = _get_ticker(isin, product)
            action = "BUY" if quantity > 0 else "SELL"
            shares = abs(quantity)

            # Cost/proceeds in EUR (all-in including fees)
            total_abs = abs(total_eur)
            cost_per_share = total_abs / shares if shares else 0

            trades.append({
                "date": date,
                "date_str": row[0].strip(),
                "product": product,
                "isin": isin,
                "ticker": ticker,
                "action": action,
                "shares": shares,
                "price": price,
                "price_ccy": price_ccy,
                "value_eur": abs(value_eur),       # trade value without fees
                "autofx_fee": abs(autofx_fee),
                "tx_fee": abs(tx_fee),
                "total_eur": total_abs,             # all-in cost/proceeds
                "cost_per_share": cost_per_share,
                "exchange_rate": exchange_rate,
                "order_id": order_id,
            })
        except Exception:
            continue
    return trades


def parse_account_csv(content: str) -> list:
    """
    Parsea Account.csv de DEGIRO.
    Columnas: Date,Time,Value date,Product,ISIN,Description,FX,
              [CCY],Change,[CCY],Balance,Order Id
    """
    events = []
    reader = csv.reader(io.StringIO(content))
    next(reader, None)  # skip header
    for row in reader:
        if len(row) < 10:
            continue
        try:
            date = _parse_date(row[0])
            if not date:
                continue
            product = row[3].strip()
            isin = row[4].strip()
            desc = row[5].strip()
            change_ccy = row[7].strip() if len(row) > 7 else "EUR"
            change = _parse_num(row[8]) if len(row) > 8 else 0.0
            balance_ccy = row[9].strip() if len(row) > 9 else "EUR"
            balance = _parse_num(row[10]) if len(row) > 10 else 0.0

            # Classify description
            desc_lower = desc.lower()
            if desc_lower.startswith("compra ") or desc_lower.startswith("venta "):
                event_type = "TRADE"
            elif "costes de transacción" in desc_lower or "costes de transaccion" in desc_lower:
                event_type = "TX_FEE"
            elif "comisión tiempo real" in desc_lower or "comision tiempo real" in desc_lower:
                event_type = "MARKET_DATA"
            elif "comisión de conectividad" in desc_lower or "comision de conectividad" in desc_lower:
                event_type = "CONNECTIVITY"
            elif "comisión cierre" in desc_lower:
                event_type = "CLOSURE_FEE"
            elif "ingreso cambio de divisa" in desc_lower:
                event_type = "FX_IN"
            elif "retirada cambio de divisa" in desc_lower:
                event_type = "FX_OUT"
            elif "dividendo" in desc_lower and "retención" not in desc_lower and "retencion" not in desc_lower:
                event_type = "DIVIDEND"
            elif "retención del dividendo" in desc_lower or "retencion del dividendo" in desc_lower:
                event_type = "DIVIDEND_TAX"
            elif "impuesto de transacción" in desc_lower or "transaction tax" in desc_lower or "spanish transaction tax" in desc_lower:
                event_type = "TX_TAX"
            elif "flatex instant deposit" in desc_lower or "flatex deposit" in desc_lower or desc_lower == "ingreso":
                event_type = "DEPOSIT"
            elif "flatex withdrawal" in desc_lower or "processed flatex withdrawal" in desc_lower:
                event_type = "WITHDRAWAL"
            elif "interés" in desc_lower or "interes" in desc_lower or "interest income" in desc_lower:
                event_type = "INTEREST"
            elif "deslistamiento" in desc_lower:
                event_type = "DELISTING"
            elif "transferir" in desc_lower or "transfer" in desc_lower or "cash sweep" in desc_lower:
                event_type = "TRANSFER"
            elif "comisión por transferencia" in desc_lower:
                event_type = "TRANSFER_FEE"
            else:
                event_type = "OTHER"

            ticker = _get_ticker(isin, product) if (isin or product) else None

            events.append({
                "date": date,
                "date_str": row[0].strip(),
                "product": product,
                "isin": isin,
                "ticker": ticker,
                "description": desc,
                "event_type": event_type,
                "change_ccy": change_ccy,
                "change": change,       # positive=income, negative=expense
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
    Usa método FIFO para calcular el coste base de cada venta.
    """
    from collections import deque

    # Sort trades by date ASC
    trades_sorted = sorted(trades, key=lambda x: (x["date"], x["date_str"]))

    # Per-ticker buy queues: deque of (shares, cost_per_share)
    buy_queues = defaultdict(deque)
    open_positions = {}   # ticker -> {shares, total_cost, avg_cost}
    closed_trades = []    # list of realized P&L entries

    for trade in trades_sorted:
        ticker = trade["ticker"]
        shares = trade["shares"]
        cost_per_share = trade["cost_per_share"]

        if trade["action"] == "BUY":
            buy_queues[ticker].append({
                "shares": shares,
                "cost_per_share": cost_per_share,
                "date": trade["date_str"],
                "price": trade["price"],
                "price_ccy": trade["price_ccy"],
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
            sell_proceeds_per_share = cost_per_share  # cost_per_share for sell = proceeds per share

            realized_pnl = 0.0
            buy_cost_total = 0.0
            matched_shares = 0.0
            first_buy_date = None

            while remaining_sell > 0 and queue:
                lot = queue[0]
                if first_buy_date is None:
                    first_buy_date = lot["date"]

                if lot["shares"] <= remaining_sell:
                    # Use entire lot
                    matched = lot["shares"]
                    buy_cost_total += matched * lot["cost_per_share"]
                    realized_pnl += matched * (sell_proceeds_per_share - lot["cost_per_share"])
                    matched_shares += matched
                    remaining_sell -= matched
                    queue.popleft()
                else:
                    # Partial lot
                    matched = remaining_sell
                    buy_cost_total += matched * lot["cost_per_share"]
                    realized_pnl += matched * (sell_proceeds_per_share - lot["cost_per_share"])
                    matched_shares += matched
                    lot["shares"] -= matched
                    remaining_sell = 0

            # Update open position
            if ticker in open_positions:
                open_positions[ticker]["shares"] -= (shares - remaining_sell)
                sold = shares - remaining_sell
                if open_positions[ticker]["total_cost"] > 0 and open_positions[ticker]["shares"] > 0:
                    avg = open_positions[ticker]["total_cost"] / (open_positions[ticker]["shares"] + sold)
                    open_positions[ticker]["total_cost"] = open_positions[ticker]["shares"] * avg
                elif open_positions[ticker]["shares"] <= 0.001:
                    open_positions[ticker]["shares"] = 0
                    open_positions[ticker]["total_cost"] = 0

            sell_proceeds = shares * sell_proceeds_per_share
            pnl_pct = (realized_pnl / buy_cost_total * 100) if buy_cost_total > 0 else 0

            closed_trades.append({
                "ticker": ticker,
                "product": trade["product"],
                "sell_date": trade["date_str"],
                "buy_date": first_buy_date or "?",
                "shares": matched_shares,
                "sell_price_eur": sell_proceeds_per_share,
                "buy_cost_eur": buy_cost_total / matched_shares if matched_shares else 0,
                "sell_proceeds_eur": sell_proceeds,
                "buy_cost_total_eur": buy_cost_total,
                "realized_pnl_eur": round(realized_pnl, 2),
                "realized_pnl_pct": round(pnl_pct, 2),
            })

    # Clean up open positions (remove closed ones)
    open_pos_list = []
    for ticker, pos in open_positions.items():
        if pos["shares"] > 0.001:
            avg_cost = pos["total_cost"] / pos["shares"]
            open_pos_list.append({
                "ticker": ticker,
                "product": pos["product"],
                "isin": pos["isin"],
                "shares": round(pos["shares"], 4),
                "avg_cost_eur": round(avg_cost, 4),
                "total_cost_eur": round(pos["total_cost"], 2),
            })

    # ── Stats from Account.csv events ───────────────────────────────────────
    stats = {
        "tx_fees": 0.0,          # €2 por operación
        "autofx_fees": 0.0,       # Fee de cambio de divisa automático
        "market_data_fees": 0.0,  # Comisión tiempo real
        "connectivity_fees": 0.0, # Comisión conectividad
        "tx_taxes": 0.0,          # Impuesto transacciones (Francia/España)
        "closure_fees": 0.0,      # Comisión cierre posiciones
        "transfer_fees": 0.0,     # Comisión transferencia
        "dividends": 0.0,         # Dividendos cobrados
        "dividend_tax": 0.0,      # Retención sobre dividendos
        "deposits": 0.0,          # Ingresos a la cuenta
        "withdrawals": 0.0,       # Retiradas de la cuenta
        "interest": 0.0,          # Intereses
        "cash_balance": 0.0,      # Último saldo en EUR
    }
    dividends_detail = []
    last_eur_balance = None

    for ev in sorted(events, key=lambda x: x["date"]):
        t = ev["event_type"]
        change = ev["change"]
        ccy = ev["change_ccy"]

        # Only count EUR values for stats
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
            stats["interest"] += change  # can be positive or negative

        # Track latest EUR balance
        if ev["balance_ccy"] == "EUR" and ev["balance"] != 0:
            last_eur_balance = ev["balance"]

    # AutoFX fees come from Transactions.csv
    stats["autofx_fees"] = sum(t["autofx_fee"] for t in trades)
    stats["cash_balance"] = last_eur_balance or 0.0

    # Total fees
    stats["total_fees"] = round(
        stats["tx_fees"] + stats["autofx_fees"] + stats["market_data_fees"] +
        stats["connectivity_fees"] + stats["tx_taxes"] + stats["closure_fees"] +
        stats["transfer_fees"], 2
    )

    # ── Realized P&L aggregated by ticker ────────────────────────────────────
    realized_by_ticker = defaultdict(lambda: {"realized_pnl_eur": 0.0, "trades": 0})
    for ct in closed_trades:
        realized_by_ticker[ct["ticker"]]["realized_pnl_eur"] += ct["realized_pnl_eur"]
        realized_by_ticker[ct["ticker"]]["trades"] += 1

    total_realized = sum(ct["realized_pnl_eur"] for ct in closed_trades)
    total_invested = sum(p["total_cost_eur"] for p in open_pos_list)
    winning_trades = sum(1 for ct in closed_trades if ct["realized_pnl_eur"] > 0)
    losing_trades = sum(1 for ct in closed_trades if ct["realized_pnl_eur"] < 0)
    win_rate = (winning_trades / len(closed_trades) * 100) if closed_trades else 0

    return {
        "open_positions": sorted(open_pos_list, key=lambda x: x["total_cost_eur"], reverse=True),
        "closed_trades": sorted(closed_trades, key=lambda x: x["sell_date"], reverse=True),
        "realized_by_ticker": dict(realized_by_ticker),
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
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 1),
            "total_fees": stats["total_fees"],
            "total_dividends": round(stats["dividends"], 2),
            "net_deposits": round(stats["deposits"] - stats["withdrawals"], 2),
            "cash_balance": round(stats["cash_balance"], 2),
        }
    }
