"""Semáforo de mercado — filtro de RÉGIMEN GLOBAL.

La evidencia es clara: las señales de compra en un mercado bajista tienen tasa de acierto
baja. Comprar la mejor acción mientras el S&P se desploma pierde igual. Por eso los
screeners profesionales SOLO compran cuando el mercado general está sano.

Este módulo mira el S&P 500 (SPY) frente a su media de 200 sesiones y su tendencia
reciente, y devuelve un semáforo 🟢/🟡/🔴 que el resto de la app usa para condicionar
la agresividad de las señales. Cacheado 1h (el régimen cambia despacio).
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger("inveria.market_regime")

_cache = {"data": None, "ts": None}
_TTL_SECONDS = 3600  # 1h


def _compute(df) -> dict:
    """Evalúa el régimen a partir del histórico diario de SPY."""
    closes = df["Close"].astype(float)
    price = float(closes.iloc[-1])
    sma200 = float(closes.tail(200).mean()) if len(closes) >= 200 else float(closes.mean())
    sma50 = float(closes.tail(50).mean()) if len(closes) >= 50 else sma200
    # Retorno a ~1 mes (21 sesiones) como proxy de momentum reciente.
    ret_1m = ((price / float(closes.iloc[-21]) - 1) * 100) if len(closes) >= 21 else 0.0
    above_200 = price > sma200
    above_50 = price > sma50
    dist_200 = round((price / sma200 - 1) * 100, 1)

    # Semáforo:
    # 🟢 sano: precio sobre SMA200 y SMA50 (o momentum claramente positivo)
    # 🔴 riesgo: precio bajo SMA200 (tendencia primaria bajista)
    # 🟡 transición: mezcla (sobre 200 pero bajo 50, o cerca del cruce)
    if above_200 and above_50:
        light = "verde"
        label = "Mercado sano — señales de compra fiables"
        advice = "Régimen alcista: las entradas en soporte funcionan mejor. Opera con normalidad."
    elif not above_200:
        light = "rojo"
        label = "Mercado en riesgo — reduce compras"
        advice = ("El S&P está por debajo de su media de 200 sesiones (tendencia primaria "
                  "bajista). Las señales de compra fallan más aquí. Reduce tamaño y sé selectivo.")
    else:
        light = "amarillo"
        label = "Mercado en transición — prudencia"
        advice = ("Señales mixtas (sobre la media de 200 pero perdiendo la de 50). Reduce "
                  "agresividad y espera confirmación.")

    return {
        "light": light,
        "label": label,
        "advice": advice,
        "spy_price": round(price, 2),
        "sma200": round(sma200, 2),
        "sma50": round(sma50, 2),
        "dist_sma200_pct": dist_200,
        "return_1m_pct": round(ret_1m, 1),
        "above_sma200": above_200,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def get_market_regime(force: bool = False) -> dict:
    """Devuelve el semáforo de mercado (cacheado 1h). Si SPY no está disponible, devuelve
    un estado 'desconocido' neutro para no bloquear la app."""
    import time as _time
    now = _time.time()
    if not force and _cache["data"] and _cache["ts"] and (now - _cache["ts"]) < _TTL_SECONDS:
        return _cache["data"]
    try:
        import market_data
        df = market_data.get_full_indicator_history("SPY")
        if df is None or df.empty or len(df) < 50:
            raise ValueError("sin histórico de SPY suficiente")
        data = _compute(df)
    except Exception as e:
        logger.warning(f"market_regime: no se pudo evaluar ({e})")
        data = {
            "light": "desconocido",
            "label": "Régimen de mercado no disponible",
            "advice": "No se pudo evaluar el estado del mercado ahora mismo.",
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
    _cache["data"] = data
    _cache["ts"] = now
    return data


# ── Termómetro Miedo/Codicia (#28) ───────────────────────────────────────────
_fg_cache = {"data": None, "ts": None}
_FG_TTL = 900  # 15 min


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def get_fear_greed(force: bool = False) -> dict:
    """Termómetro Miedo/Codicia (0=miedo extremo, 100=codicia extrema) a partir de señales
    reales: el VIX (índice del miedo), el momento del S&P vs su media de 125 sesiones y su
    retorno a ~1 mes. Cacheado 15 min. Pocos símbolos → coste de memoria mínimo."""
    import time as _time
    now = _time.time()
    if not force and _fg_cache["data"] and _fg_cache["ts"] and (now - _fg_cache["ts"]) < _FG_TTL:
        return _fg_cache["data"]
    try:
        import market_data
        vix = None
        try:
            q = market_data.get_quote("^VIX")
            vix = float(q["price"]) if q and q.get("price") is not None else None
        except Exception:
            vix = None
        df = market_data.get_full_indicator_history("SPY")
        if df is None or df.empty or len(df) < 30:
            raise ValueError("sin histórico de SPY")
        closes = df["Close"].astype(float)
        price = float(closes.iloc[-1])
        sma125 = float(closes.tail(125).mean()) if len(closes) >= 125 else float(closes.mean())
        mom_pct = (price / sma125 - 1) * 100
        ret_1m = ((price / float(closes.iloc[-21]) - 1) * 100) if len(closes) >= 21 else 0.0

        comps = []
        # VIX: ~12 (complacencia) → codicia; ~35 (pánico) → miedo. Peso alto (0.5).
        if vix is not None:
            comps.append((_clamp(110 - vix * 3), 0.5))
        # Momento del S&P vs SMA125: por encima = codicia, por debajo = miedo (0.3).
        comps.append((_clamp(50 + mom_pct * 4), 0.3))
        # Retorno a ~1 mes (0.2).
        comps.append((_clamp(50 + ret_1m * 4), 0.2))
        tw = sum(w for _, w in comps)
        score = round(sum(v * w for v, w in comps) / tw) if tw else 50

        if score < 25:
            label, tono = "Miedo extremo", "rojo"
            advice = "El mercado está en pánico. Históricamente es cuando aparecen las mejores oportunidades para comprar por niveles con calma — sin prisa y escalonando."
        elif score < 45:
            label, tono = "Miedo", "naranja"
            advice = "Hay miedo en el mercado. Buen momento para tener listas tus zonas de compra: los soportes profundos suelen ponerse a tiro."
        elif score <= 55:
            label, tono = "Neutral", "amarillo"
            advice = "Mercado en equilibrio, sin euforia ni pánico. Opera según tu plan."
        elif score <= 75:
            label, tono = "Codicia", "verde"
            advice = "Predomina la codicia. Cuidado con perseguir precios altos; espera retrocesos a soporte."
        else:
            label, tono = "Codicia extrema", "verde"
            advice = "Euforia en el mercado. Es cuando conviene ser más selectivo y no comprar caro: protege beneficios."

        data = {
            "score": int(score),
            "label": label,
            "tono": tono,
            "advice": advice,
            "vix": round(vix, 1) if vix is not None else None,
            "spy_mom_pct": round(mom_pct, 1),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning(f"fear_greed: no se pudo evaluar ({e})")
        data = {"score": None, "label": "No disponible", "tono": "amarillo",
                "advice": "", "computed_at": datetime.now(timezone.utc).isoformat()}
    _fg_cache["data"] = data
    _fg_cache["ts"] = now
    return data
