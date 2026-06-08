"""Backend tests for InverIA stock analysis app."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://market-insights-294.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- Health ----------
def test_health(s):
    r = s.get(f"{API}/", timeout=30)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- Quote ----------
@pytest.mark.parametrize("sym", ["AAPL", "TSLA", "NVDA"])
def test_quote_valid(s, sym):
    r = s.get(f"{API}/quote/{sym}", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("symbol", "").upper() == sym
    assert isinstance(d.get("price"), (int, float))
    assert d["price"] > 0


def test_quote_invalid(s):
    r = s.get(f"{API}/quote/INVALIDXYZ", timeout=30)
    assert r.status_code == 404


# ---------- Chart ----------
def test_chart_aapl_1y(s):
    r = s.get(f"{API}/chart/AAPL?timeframe=1Y", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["symbol"] == "AAPL"
    assert d["timeframe"] == "1Y"
    assert isinstance(d["candles"], list)
    assert len(d["candles"]) > 50
    c = d["candles"][0]
    for k in ("date", "open", "high", "low", "close"):
        assert k in c


@pytest.mark.parametrize("tf", ["1D", "1W", "1M", "3M", "5Y"])
def test_chart_timeframes(s, tf):
    r = s.get(f"{API}/chart/AAPL?timeframe={tf}", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["candles"], list)
    assert len(d["candles"]) > 0


# ---------- Indicators ----------
def test_indicators(s):
    r = s.get(f"{API}/indicators/AAPL", timeout=60)
    assert r.status_code == 200
    d = r.json()
    for k in ("rsi", "macd", "bollinger", "sma", "ema", "fibonacci", "support_resistance", "patterns"):
        assert k in d, f"missing key {k}"


# ---------- News ----------
def test_news(s):
    r = s.get(f"{API}/news/AAPL", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["symbol"] == "AAPL"
    assert isinstance(d["items"], list)


# ---------- Popular ----------
def test_popular(s):
    r = s.get(f"{API}/market/popular", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d, list)
    assert len(d) >= 6  # allow some Yahoo flakiness
    for q in d:
        assert "symbol" in q and "price" in q


# ---------- Watchlist CRUD ----------
def test_watchlist_flow(s):
    # cleanup
    s.delete(f"{API}/watchlist/TEST_NVDA", timeout=15)
    s.delete(f"{API}/watchlist/NVDA", timeout=15)

    r = s.post(f"{API}/watchlist", json={"symbol": "NVDA"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["symbol"] == "NVDA"
    assert d["quote"]["symbol"] == "NVDA"

    # duplicate
    r2 = s.post(f"{API}/watchlist", json={"symbol": "NVDA"}, timeout=30)
    assert r2.status_code == 409

    # list
    r3 = s.get(f"{API}/watchlist", timeout=30)
    assert r3.status_code == 200
    syms = [it["symbol"] for it in r3.json()]
    assert "NVDA" in syms

    # delete
    r4 = s.delete(f"{API}/watchlist/NVDA", timeout=30)
    assert r4.status_code == 200

    # delete non-existent
    r5 = s.delete(f"{API}/watchlist/NVDA", timeout=30)
    assert r5.status_code == 404


def test_watchlist_invalid_symbol(s):
    r = s.post(f"{API}/watchlist", json={"symbol": "INVALIDXYZ"}, timeout=30)
    assert r.status_code == 404


# ---------- Alerts CRUD ----------
def test_alerts_flow(s):
    r = s.post(f"{API}/alerts", json={"symbol": "AAPL", "target_price": 999.0, "direction": "above"}, timeout=30)
    assert r.status_code == 200, r.text
    alert = r.json()
    assert alert["symbol"] == "AAPL"
    assert alert["direction"] == "above"
    aid = alert["id"]

    r2 = s.get(f"{API}/alerts", timeout=30)
    assert r2.status_code == 200
    ids = [a["id"] for a in r2.json()]
    assert aid in ids

    # invalid direction
    r3 = s.post(f"{API}/alerts", json={"symbol": "AAPL", "target_price": 100, "direction": "sideways"}, timeout=30)
    assert r3.status_code == 400

    r4 = s.delete(f"{API}/alerts/{aid}", timeout=30)
    assert r4.status_code == 200

    r5 = s.delete(f"{API}/alerts/{aid}", timeout=30)
    assert r5.status_code == 404


# ---------- AI Analyze ----------
@pytest.mark.parametrize("model", ["gpt-5.2", "claude-sonnet-4.5", "gemini-3-flash"])
def test_analyze_models(s, model):
    r = s.post(f"{API}/analyze", json={"symbol": "AAPL", "model": model}, timeout=180)
    assert r.status_code == 200, f"{model}: {r.status_code} {r.text[:300]}"
    d = r.json()
    a = d.get("analysis", {})
    required = ["recommendation", "confidence", "entry_zone", "stop_loss",
                "take_profit_1", "take_profit_2", "key_levels"]
    for k in required:
        assert k in a, f"{model} missing {k}: {a}"
    assert a["recommendation"] in ("COMPRAR", "VENDER", "MANTENER")
    assert "min" in a["entry_zone"] and "max" in a["entry_zone"]
    assert "support" in a["key_levels"] and "resistance" in a["key_levels"]


def test_analyze_invalid_symbol(s):
    r = s.post(f"{API}/analyze", json={"symbol": "INVALIDXYZ", "model": "gpt-5.2"}, timeout=30)
    assert r.status_code == 404


# ---------- Analyst consensus (Finnhub) ----------
def test_analyst_consensus(s):
    r = s.get(f"{API}/analyst/AAPL", timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["symbol"] == "AAPL"
    consensus = d.get("consensus")
    assert consensus is not None, f"missing consensus: {d}"
    for k in ("breakdown", "score", "period", "total_analysts"):
        assert k in consensus, f"consensus missing {k}: {consensus}"
    # breakdown must contain expected keys
    bd = consensus["breakdown"]
    for k in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
        assert k in bd, f"breakdown missing {k}"
    assert isinstance(consensus["total_analysts"], int)
    assert consensus["total_analysts"] > 0
    pt = d.get("price_target")
    # NOTE: Finnhub free tier returns 403 on /stock/price-target so price_target may be None.
    # We accept None but if present, verify expected fields.
    if pt is not None:
        for k in ("target_mean", "target_high", "target_low"):
            assert k in pt, f"price_target missing {k}"


# ---------- Sentiment (Alpha Vantage; may be rate-limited) ----------
def test_sentiment_graceful(s):
    r = s.get(f"{API}/sentiment/AAPL", timeout=60)
    # Must NOT 500 even if AV daily cap exceeded
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["symbol"] == "AAPL"
    assert "items" in d and isinstance(d["items"], list)
    assert "average_score" in d
    assert "label" in d


# ---------- Backtest ----------
def test_backtest_valid(s):
    # use realistic levels around AAPL current price - get quote first
    q = s.get(f"{API}/quote/AAPL", timeout=30).json()
    price = q["price"]
    payload = {
        "symbol": "AAPL",
        "entry_min": round(price * 0.95, 2),
        "entry_max": round(price * 0.98, 2),
        "stop_loss": round(price * 0.90, 2),
        "take_profit_1": round(price * 1.05, 2),
        "take_profit_2": round(price * 1.10, 2),
        "direction": "long",
        "lookback_days": 252,
    }
    r = s.post(f"{API}/backtest", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("total_trades", "wins", "losses", "win_rate", "total_return_pct", "trades"):
        assert k in d, f"backtest missing {k}: {d.keys()}"
    assert isinstance(d["trades"], list)
    assert isinstance(d["total_trades"], int)


def test_backtest_invalid_direction(s):
    r = s.post(f"{API}/backtest", json={
        "symbol": "AAPL", "entry_min": 100, "entry_max": 110,
        "stop_loss": 90, "take_profit_1": 120, "direction": "sideways"
    }, timeout=30)
    assert r.status_code == 400


# ---------- Compare ----------
def test_compare_multi(s):
    r = s.post(f"{API}/compare", json={"symbols": ["AAPL", "MSFT", "NVDA"]}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "items" in d
    assert len(d["items"]) == 3
    syms = [it["symbol"] for it in d["items"]]
    assert syms == ["AAPL", "MSFT", "NVDA"]
    for it in d["items"]:
        assert "quote" in it and it["quote"] is not None
        assert "indicators" in it
        assert "candles" in it and isinstance(it["candles"], list)
        assert len(it["candles"]) > 0


# ---------- History ----------
def test_history_all(s):
    r = s.get(f"{API}/history", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d and isinstance(d["items"], list)


def test_history_by_symbol(s):
    # Ensure at least one analyze exists for AAPL (created by earlier analyze tests)
    r = s.get(f"{API}/history/AAPL", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["symbol"] == "AAPL"
    assert isinstance(d["items"], list)
    # All items must be for AAPL
    for it in d["items"]:
        assert it["symbol"] == "AAPL"


# ---------- Analyze enrichment (analyst + price_target in response) ----------
def test_analyze_includes_analyst_fields(s):
    r = s.post(f"{API}/analyze", json={"symbol": "AAPL", "model": "gpt-5.2"}, timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "analyst_consensus" in d
    assert "price_target" in d
    # sentiment_score may be None due to AV rate limits
    assert "sentiment_score" in d


# ---------- Test email (Resend) ----------
def test_send_test_email(s):
    r = s.post(f"{API}/alerts/test-email", json={}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
