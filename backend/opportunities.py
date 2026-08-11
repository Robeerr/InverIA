"""Daily opportunities scanner — analyzes a universe of stocks and detects buy signals."""
import asyncio
import gc
import mem
import logging
from datetime import datetime, timezone, timedelta
import market_data
import indicators as ind
import external_data

_log = logging.getLogger("inveria.opportunities")

# ---------- Persistent snapshot cache (MongoDB) ----------
# Survives server restarts: the last completed scan is stored in Mongo so a fresh
# boot can show data instantly (instead of a 2-3 min "warming" screen) while a new
# scan refreshes in the background. Set by server.py at startup via set_db().
_db = None


def set_db(db):
    global _db
    _db = db


async def _save_snapshot(kind: str, data: dict):
    """Persist the latest scan to Mongo (best-effort; never blocks the scan)."""
    if _db is None:
        return
    try:
        await _db.scan_snapshots.replace_one(
            {"_id": kind},
            {"_id": kind, "data": data, "saved_at": datetime.now(timezone.utc)},
            upsert=True,
        )
    except Exception as e:
        _log.warning("snapshot save failed (%s): %s", kind, e)


async def load_snapshots_into_cache():
    """At startup, hydrate the in-memory caches from the last persisted scan so the
    first user request returns data immediately. A background pre-warm then refreshes."""
    if _db is None:
        return
    mapping = {"daily": _cache, "screener": _screener_cache}
    for kind, cache in mapping.items():
        try:
            doc = await _db.scan_snapshots.find_one({"_id": kind})
            if doc and doc.get("data"):
                cache["data"] = doc["data"]
                saved = doc.get("saved_at")
                # pymongo devuelve datetimes naive (UTC): hazlos aware para poder
                # restarlos contra datetime.now(timezone.utc) sin TypeError.
                if saved is not None and saved.tzinfo is None:
                    saved = saved.replace(tzinfo=timezone.utc)
                cache["ts"] = saved
                _log.info("Loaded %s snapshot from Mongo (saved %s)", kind, saved)
        except Exception as e:
            _log.warning("snapshot load failed (%s): %s", kind, e)


UNIVERSE = [
    # Mega caps
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    # Large caps tech / growth
    "AMD", "AVGO", "ORCL", "CRM", "ADBE", "NFLX", "INTC", "QCOM", "TXN", "IBM", "CSCO", "AMAT",
    # Semiconductors / AI infrastructure
    "ARM", "SMCI", "ANET", "MRVL", "MU", "LRCX", "KLAC", "ON", "TSM", "ASML",
    # Cloud / SaaS / software
    "NOW", "SNOW", "DDOG", "NET", "PLTR", "CRWD", "PANW", "FTNT", "SHOP", "TEAM", "WDAY", "ZS", "MDB", "APP",
    # Internet / consumer-tech
    "UBER", "ABNB", "MELI", "BKNG", "SPOT", "PYPL", "SQ",
    # Fintech / brokers
    "COIN", "HOOD", "SOFI", "NU",
    # Finance
    "JPM", "V", "MA", "GS", "BAC", "MS", "AXP", "SCHW", "BLK",
    # Consumer / Retail
    "WMT", "COST", "MCD", "KO", "NKE", "DIS", "SBUX", "TGT", "HD", "LOW", "CMG", "LULU",
    # Health / biotech
    "JNJ", "UNH", "LLY", "ABBV", "MRK", "PFE", "TMO", "ISRG", "VRTX", "MRNA", "AMGN",
    # Industrial / EV / mobility
    "CAT", "DE", "BA", "GE", "RIVN", "RKLB",
    # Energy
    "XOM", "CVX", "COP", "SLB",
    # ETFs
    "SPY", "QQQ", "IWM", "DIA",
]


def _potential_score_detalle(rev_g, eps_g, pe, dist_52w, cons_score=None,
                             ret_26w=None, ret_52w=None, rel_strength=None,
                             net_margin=None, roe=None, debt_to_equity=None):
    """El score de potencial CON su desglose. Misma aritmética, mismos umbrales.

    Existe porque un score de 0 a 100 sin denominador no se puede discutir: la
    descomposición ya se hacía dentro de esta función y se tiraba al devolver solo la
    suma. Aquí se anota cada paso mientras se calcula, sin tocar un punto.

    EL SCORE NO ES UNA SUMA, Y EL DESGLOSE LO DICE

    Son tres etapas: se suman siete componentes, se multiplica por el guardián de
    tendencia (1,0 / 0,75 / 0,55) y se recorta a [0, 100]. Presentar el guardián como
    puntos negativos dentro de la suma sería mentir sobre la mecánica — y encima
    esconder justo lo que explica que una empresa con buenos fundamentales puntúe bajo.

    Los máximos suman 110, no 100. Es a propósito y por eso existe el recorte: se puede
    llegar al tope sin ser perfecto en todo. Normalizar a 100 para que «cuadre» haría
    que los números del desglose no correspondieran con los del cálculo.
    """
    score = 0.0
    componentes = []

    def _apunta(clave, etiqueta, puntos, maximo, detalle=None):
        componentes.append({"clave": clave, "etiqueta": etiqueta,
                            "puntos": round(puntos, 2), "maximo": maximo,
                            "detalle": detalle})
        return puntos

    # 1) Crecimiento de ventas — el motor del medio plazo. Hasta 30 pts (saturado a 60%).
    p = min(rev_g, 60) / 60 * 30 if (rev_g is not None and rev_g > 0) else 0.0
    score += _apunta("crecimiento_ventas", "Crecimiento de ventas", p, 30,
                     f"ingresos {rev_g:+.0f}% anual" if rev_g is not None else "sin dato")

    # 2) Crecimiento de EPS — que el crecimiento llegue al beneficio. Hasta 12 pts.
    p = min(eps_g, 50) / 50 * 12 if (eps_g is not None and eps_g > 0) else 0.0
    score += _apunta("crecimiento_eps", "Crecimiento del beneficio por acción", p, 12,
                     f"EPS {eps_g:+.0f}%" if eps_g is not None else "sin dato")

    # 3) Valoración vía PEG (PER / crecimiento). El "santo grial": barata PARA lo que crece.
    val_label = "sin datos"
    p, det = 0.0, "sin PER utilizable"
    if pe is not None and pe > 0 and rev_g and rev_g > 0:
        peg = pe / rev_g
        det = f"PEG {peg:.2f} (PER {pe:.0f} / crecimiento {rev_g:.0f}%)"
        if peg < 1:
            p = 22; val_label = "infravalorada (PEG<1)"
        elif peg < 1.5:
            p = 16; val_label = "precio atractivo (PEG<1.5)"
        elif peg < 2.5:
            p = 10; val_label = "valoración razonable"
        elif peg < 4:
            p = 4; val_label = "algo cara"
        else:
            val_label = "cara (PEG>4)"
    elif pe is not None and pe <= 0:
        val_label = "sin beneficios (PER negativo)"
        det = "PER negativo"
    score += _apunta("valoracion_peg", "Valoración (PEG)", p, 22, det)

    # 4) Punto de entrada según distancia a máximos de 52s. Hasta 14 pts.
    p, det = 0.0, "sin dato"
    if dist_52w is not None:
        if -20 <= dist_52w <= -8:
            p, det = 14, f"retroceso sano ({dist_52w:.0f}% del máximo)"
        elif -8 < dist_52w <= 0:
            p, det = 8, f"cerca de máximos ({dist_52w:.0f}%)"
        elif -35 <= dist_52w < -20:
            p, det = 9, f"corrección profunda ({dist_52w:.0f}%)"
        else:
            p, det = 3, f"muy lejos de máximos ({dist_52w:.0f}%)"
    score += _apunta("punto_de_entrada", "Punto de entrada", p, 14, det)

    # 5) Consenso de analistas (Wall Street). Hasta 14 pts. 100=strong buy, 50=hold.
    # Reescala 50→0 y 100→14 (por debajo de "mantener" no suma nada).
    p = max(0, (cons_score - 50) / 50) * 14 if cons_score is not None else 0.0
    score += _apunta("consenso_analistas", "Consenso de analistas", p, 14,
                     f"{cons_score:.0f}/100" if cons_score is not None else "sin dato")

    # 5b) CALIDAD (factor con prima demostrada: rentables y poco endeudadas baten +2-3%
    # anual). Hasta ~8 pts: margen neto, ROE y control de deuda. Distingue "crece Y gana
    # dinero de calidad" de "crece pero quema caja y está muy endeudada".
    p_margen = min(net_margin, 25) / 25 * 3 if (net_margin is not None and net_margin > 0) else 0.0
    p_roe = min(roe, 30) / 30 * 3 if (roe is not None and roe > 0) else 0.0
    p_deuda = 0.0
    if debt_to_equity is not None and debt_to_equity >= 0:
        if debt_to_equity < 0.5:
            p_deuda = 2
        elif debt_to_equity < 1.5:
            p_deuda = 1
    partes = []
    if net_margin is not None:
        partes.append(f"margen {net_margin:.0f}%")
    if roe is not None:
        partes.append(f"ROE {roe:.0f}%")
    if debt_to_equity is not None:
        partes.append(f"deuda/patrimonio {debt_to_equity:.1f}")
    score += _apunta("calidad", "Calidad del negocio", p_margen + p_roe + p_deuda, 8,
                     " · ".join(partes) or "sin datos")
    # El subdetalle va aparte: tres filas de 3, 3 y 2 puntos serían ruido en pantalla,
    # pero quien quiera abrirlo tiene la cuenta entera.
    componentes[-1]["sub"] = [
        {"clave": "margen_neto", "etiqueta": "Margen neto", "puntos": round(p_margen, 2), "maximo": 3},
        {"clave": "roe", "etiqueta": "Rentabilidad (ROE)", "puntos": round(p_roe, 2), "maximo": 3},
        {"clave": "deuda", "etiqueta": "Control de deuda", "puntos": round(p_deuda, 2), "maximo": 2},
    ]

    # 6) Momentum reciente (6 meses). Hasta 10 pts: premia que la acción YA suba.
    p, det = 0.0, "sin dato"
    if ret_26w is not None:
        det = f"{ret_26w:+.0f}% en 6 meses"
        if ret_26w >= 15:
            p = 10
        elif ret_26w >= 5:
            p = 6
        elif ret_26w >= -5:
            p = 3
    score += _apunta("momentum_reciente", "Momentum (6 meses)", p, 10, det)

    bruto = score

    # 7) GUARDIÁN DE TENDENCIA — penaliza value traps / sectores muertos.
    momentum_label = "neutra"
    multiplicador = 1.0
    motivo_mult = None
    down_year = ret_52w is not None and ret_52w < -10
    lagging = rel_strength is not None and rel_strength < -5
    if down_year and lagging:
        multiplicador = 0.55   # cae en el año Y va peor que el mercado: sector muerto
        momentum_label = "⚠ tendencia bajista y peor que el mercado"
        motivo_mult = "cae en el año y rinde peor que el mercado: sector rezagado"
    elif down_year:
        multiplicador = 0.75   # cae en el año: cuchillo cayendo → castigo moderado
        momentum_label = "⚠ en tendencia bajista (1 año)"
        motivo_mult = "cae en el año: cuchillo cayendo"
    elif ret_52w is not None and ret_52w >= 15 and (rel_strength is None or rel_strength >= 0):
        momentum_label = "tendencia alcista sólida"
    score *= multiplicador

    final = round(min(max(score, 0), 100), 1)
    return {
        "score": final,
        "val_label": val_label,
        "momentum_label": momentum_label,
        "componentes": componentes,
        "bruto": round(bruto, 2),
        "multiplicador": multiplicador,
        "motivo_multiplicador": motivo_mult,
        # Se dice cuando el recorte ha actuado: sin esto, un 100 podria ser un 100 justo
        # o un 118 recortado, y no son lo mismo.
        "recortado": bruto * multiplicador > 100,
    }


def _potential_score(rev_g, eps_g, pe, dist_52w, cons_score=None,
                     ret_26w=None, ret_52w=None, rel_strength=None,
                     net_margin=None, roe=None, debt_to_equity=None):
    """Score 0-100 de POTENCIAL a medio plazo. Combina, como haría un gestor: crecimiento,
    valoración/PEG, punto de entrada, consenso de analistas, MOMENTUM/fuerza relativa y
    CALIDAD (rentabilidad + poca deuda — factor con prima demostrada).
    Aplica un GUARDIÁN DE TENDENCIA: una empresa que crece pero cuya acción lleva meses
    cayendo y rinde peor que el mercado (sector rezagado / value trap) se penaliza fuerte,
    porque a corto/medio plazo no suele subir por muy buenos que sean sus fundamentales.
    Devuelve (score, etiqueta_valoracion, etiqueta_momentum).

    CONTRATO INTACTO: el calculo vive ahora en `_potential_score_detalle`, que ademas
    devuelve el desglose. Esta funcion es su envoltorio y da exactamente lo mismo que
    antes, para no tocar a ninguno de sus cuatro consumidores.
    """
    d = _potential_score_detalle(rev_g, eps_g, pe, dist_52w, cons_score=cons_score,
                                 ret_26w=ret_26w, ret_52w=ret_52w,
                                 rel_strength=rel_strength, net_margin=net_margin,
                                 roe=roe, debt_to_equity=debt_to_equity)
    return d["score"], d["val_label"], d["momentum_label"]


def _build_screener_reason(rev_g, dist_52w, change_pct, market_cap):
    """Generate a short human-readable explanation for a screener result."""
    parts = []
    if rev_g is not None:
        parts.append(f"ingresos +{rev_g}% anual")
    if dist_52w is not None:
        if dist_52w >= -5:
            parts.append("cerca de máximos históricos")
        elif dist_52w >= -15:
            parts.append(f"a {abs(dist_52w):.0f}% de sus máximos")
    if change_pct is not None and abs(change_pct) >= 1.5:
        word = "sube" if change_pct > 0 else "baja"
        parts.append(f"{word} {abs(change_pct):.1f}% hoy")
    if not parts:
        return "Supera los 7 filtros de calidad, momentum y crecimiento."
    return "Destaca por: " + ", ".join(parts) + "."


def _build_opportunity_reason(category, signals, rsi, change_pct, analyst_consensus):
    """Generate a short human-readable explanation for a daily opportunity."""
    cat_intro = {
        "OVERSOLD": "RSI en zona de sobreventa",
        "DIP": "Caída fuerte hoy",
        "VALUE": "Cerca de mínimos anuales",
        "MOMENTUM": "Momentum alcista",
        "BREAKOUT": "Rompiendo máximos anuales",
        "GENERAL": "Señales técnicas positivas",
    }.get(category, "Señal detectada")
    extras = []
    if rsi is not None:
        if rsi < 32:
            extras.append(f"RSI {rsi:.0f}")
        elif rsi > 60:
            extras.append(f"RSI {rsi:.0f} (fuerte)")
    if change_pct is not None and abs(change_pct) >= 2:
        extras.append(f"{'+' if change_pct > 0 else ''}{change_pct:.1f}% hoy")
    if analyst_consensus and analyst_consensus.lower() in ("strong buy", "buy"):
        extras.append("analistas recomiendan compra")
    if extras:
        return f"{cat_intro} · {', '.join(extras)}."
    if signals:
        return f"{cat_intro}. {signals[0]}."
    return cat_intro + "."


_cache = {"data": None, "ts": None}
_CACHE_TTL = timedelta(minutes=20)
_scan_lock = asyncio.Lock()


# ---------- Growth screener ----------
# Curated universe of growth / quality US names (NASDAQ-100 + popular growth mid-caps).
# Not the whole market, but where real growth opportunities tend to live, and scannable
# on a free-tier budget. The cheap filters discard most of these with no extra API calls.
GROWTH_UNIVERSE = [
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # Software / cloud (top names)
    "NOW", "CRWD", "DDOG", "NET", "PLTR", "APP", "SNOW", "ADBE", "CRM",
    # Semiconductors
    "AMD", "AVGO", "ARM", "ANET", "MU", "MRVL",
    # Internet / consumer-tech
    "NFLX", "UBER", "MELI", "BKNG", "SPOT", "DUOL",
    # Fintech
    "COIN", "HOOD", "SOFI", "NU",
    # Health / biotech
    "VRTX", "ISRG", "MRNA",
    # Consumer / industrial growth
    "CMG", "LULU", "AXON", "RKLB", "CELH",
]

# Human-readable labels for the filters (shown as chips in the UI). EPS-growth was
# dropped: Finnhub's free tier doesn't provide it reliably and a "EPS > 0" rule
# wrongly excludes top growth names (Snowflake, Cloudflare) that reinvest profits.
SCREENER_FILTERS = [
    "Market Cap > $2B",
    "Precio > $9",
    "Dividendo < 2% (crecimiento, no renta)",
    "Vol. medio > 200K",
    "A < 45% del máx. 52 sem.",
    "Ventas YoY > 12%",
]

_screener_cache = {"data": None, "ts": None}
_SCREENER_TTL = timedelta(hours=2)
_screener_lock = asyncio.Lock()

# Tope de finalistas a puntuar (fase cara). El screener de FMP puede devolver cientos;
# enriquecer cada uno cuesta llamadas, así que acotamos el universo total tras mezclar.
_MAX_DYNAMIC_UNIVERSE = 160


async def _build_dynamic_universe():
    """Universo DINÁMICO de candidatos = screener de mercado (FMP) + movers del día,
    con la lista curada como base/fallback. Así el buscador descubre empresas de TODO
    el mercado, no solo las que metimos a mano, pero degrada con elegancia si FMP falla.
    Deduplicado y acotado a _MAX_DYNAMIC_UNIVERSE para no disparar el coste de la fase cara."""
    try:
        screener = await asyncio.to_thread(external_data.fmp_stock_screener) or []
    except Exception:
        screener = []
    try:
        actives = await asyncio.to_thread(external_data.fmp_market_movers, "gainers", 30) or []
    except Exception:
        actives = []

    # La lista curada va PRIMERO: son nombres de calidad conocida y garantizan que el
    # buscador nunca queda vacío aunque FMP no responda.
    seen = set()
    universe = []
    for src in (GROWTH_UNIVERSE, screener, actives):
        for sym in src:
            if sym and sym not in seen:
                seen.add(sym)
                universe.append(sym)
    return universe[:_MAX_DYNAMIC_UNIVERSE]


def daily_cache_is_fresh() -> bool:
    """True si el snapshot de oportunidades en caché sigue dentro de su TTL.
    Permite saltarse el precalentado al arrancar cuando el snapshot hidratado
    desde Mongo aún es válido — evita el pico de memoria del escaneo en cada
    redeploy (clave para que el plan Starter de 512 MB no se quede corto)."""
    c = _cache
    return bool(c["data"] and c["ts"] and (datetime.now(timezone.utc) - c["ts"]) < _CACHE_TTL)


def screener_cache_is_fresh() -> bool:
    """True si el snapshot del screener en caché sigue dentro de su TTL."""
    c = _screener_cache
    return bool(c["data"] and c["ts"] and (datetime.now(timezone.utc) - c["ts"]) < _SCREENER_TTL)


def _passes_cheap_filters(q: dict) -> bool:
    """Filtros BARATOS (solo cotización, sin llamadas extra). Deliberadamente laxos: el
    ranking fino lo hace el score de potencial (que ya penaliza caras y value traps), así
    que aquí solo descartamos lo claramente no invertible y dejamos entrar MÁS candidatas.
    Sobre el dividendo: NO excluimos por pagarlo, sino por pagarlo ALTO. Un dividendo alto
    (>2%) delata a una empresa madura que ya no reinvierte en crecer (Coca-Cola, Exxon) —
    poco recorrido a medio plazo. Pero un dividendo simbólico (Microsoft ~0.7%, Broadcom
    ~1.2%) es compatible con crecimiento fuerte, así que esas SÍ entran. Tampoco exigimos
    estar pegado a máximos: los retrocesos sanos son justo las mejores entradas."""
    price = q.get("price")
    mcap = q.get("market_cap")
    dy = q.get("dividend_yield")
    avgvol = q.get("avg_volume")
    high52 = q.get("high_52w")
    if not price or price <= 9:
        return False
    if not mcap or mcap <= 2_000_000_000:
        return False
    if dy and dy >= 0.02:  # dividendo alto (≥2%) -> empresa madura, fuera
        return False
    if not avgvol or avgvol <= 200_000:
        return False
    if not high52 or high52 <= 0:
        return False
    # descarta solo lo muy roto: a más de 45% bajo su máximo de 52s (posible ruina)
    if (price - high52) / high52 * 100 <= -45:
        return False
    return True


async def _run_screener_scan():
    """Run the full two-phase screener scan and store it in cache. Holds the lock so
    only one scan runs at a time. Meant to be launched as a background task."""
    if _screener_lock.locked():
        return
    async with _screener_lock:
        # Marca todas las llamadas Finnhub de este escaneo como background: reservan
        # menos cuota y dejan pasar antes a las del usuario (dashboard).
        market_data.enter_finnhub_background()
        try:
            # Fase 0 — DESCUBRIR: universo dinámico de todo el mercado (FMP) + curada.
            universe = await _build_dynamic_universe()

            # Phase 1 — quotes only, apply the 5 cheap filters (no extra API calls)
            sem = asyncio.Semaphore(8)

            async def _get_quote(s):
                async with sem:
                    try:
                        return s, await asyncio.to_thread(market_data.get_quote, s)
                    except Exception:
                        return s, None

            quote_results = await asyncio.gather(*[_get_quote(s) for s in universe])
            finalists = [(s, q) for s, q in quote_results if q and _passes_cheap_filters(q)]

            # Phase 2 — enrich only finalists with growth metrics, apply the 2 growth filters
            sem2 = asyncio.Semaphore(3)

            async def _enrich(s, q):
                async with sem2:
                    try:
                        m = await asyncio.to_thread(external_data.finnhub_basic_financials, s) or {}
                    except Exception:
                        m = {}
                    try:
                        raw = await asyncio.to_thread(external_data.finnhub_recommendation_trends, s)
                        cons = external_data.aggregate_recommendation(raw)
                    except Exception:
                        cons = None
                    return s, q, m, cons

            enriched = await asyncio.gather(*[_enrich(s, q) for s, q in finalists])

            results = []
            for s, q, m, cons in enriched:
                rev_g = m.get("revenue_growth")
                # Revenue-growth filter is best-effort: exclude only when the metric IS
                # available and fails. If Finnhub doesn't return it, keep the stock (it
                # already passed the 5 quality/momentum filters) rather than dropping all.
                if rev_g is not None and rev_g <= 12:    # Ventas YoY > 12% (medio plazo)
                    continue
                price = q.get("price")
                high52 = q.get("high_52w")
                dist = ((price - high52) / high52 * 100) if (high52 and price) else None
                dist_r = round(dist, 1) if dist is not None else None
                rev_r = round(rev_g, 1) if rev_g is not None else None
                eps_g = m.get("eps_growth")
                eps_r = round(eps_g, 1) if eps_g is not None else None
                pe = q.get("pe_ratio") or m.get("pe_ratio")
                cp = q.get("change_percent")
                mc = q.get("market_cap")
                cons_score = cons.get("score") if cons else None
                cons_label = cons.get("consensus") if cons else None
                ret_26w = m.get("return_26w")
                ret_52w = m.get("return_52w")
                rel_str = m.get("rel_strength_52w")
                # Score de potencial: crecimiento + valoración + entrada + consenso + momentum
                # + calidad, con guardián de tendencia contra value traps / sectores muertos.
                pot_score, val_label, mom_label = _potential_score(
                    rev_g, eps_g, pe, dist, cons_score, ret_26w, ret_52w, rel_str,
                    net_margin=m.get("net_margin"), roe=m.get("roe"),
                    debt_to_equity=m.get("debt_to_equity"))
                reason = _build_screener_reason(rev_r, dist_r, cp, mc)
                results.append({
                    "symbol": s,
                    "name": q.get("name"),
                    "price": price,
                    "market_cap": mc,
                    "avg_volume": q.get("avg_volume"),
                    "revenue_growth": rev_r,
                    "eps_growth": eps_r,
                    "pe_ratio": round(pe, 1) if pe else None,
                    "dist_52w_high": dist_r,
                    "sector": q.get("sector"),
                    "industry": q.get("industry"),
                    "change_percent": cp,
                    "potential_score": pot_score,
                    "valuation": val_label,
                    "momentum": mom_label,
                    "return_52w": round(ret_52w, 1) if ret_52w is not None else None,
                    "analyst_consensus": cons_label,
                    "consensus_score": round(cons_score, 1) if cons_score is not None else None,
                    "reason": reason,
                })

            # Ordena por SCORE DE POTENCIAL (mejores oportunidades arriba): combina
            # crecimiento, valoración y punto de entrada — no solo el crecimiento bruto.
            results.sort(key=lambda x: x.get("potential_score") or 0, reverse=True)

            # AVISO DE EARNINGS en el top: resultados próximos = riesgo binario. Una sola
            # llamada bulk para los mejores 25 (donde el usuario mira de verdad).
            try:
                top_syms = [r["symbol"] for r in results[:25]]
                cal = await asyncio.to_thread(external_data.finnhub_earnings_calendar, 21, top_syms)
                edates = {}
                for it in ((cal or {}).get("items") or []):
                    edates.setdefault(it.get("symbol"), it.get("date"))
                from datetime import date as _date
                today_d = datetime.now(timezone.utc).date()
                for r in results[:25]:
                    d = edates.get(r["symbol"])
                    if d:
                        try:
                            days = (_date.fromisoformat(d) - today_d).days
                            if 0 <= days <= 14:
                                r["earnings_days"] = days
                        except Exception:
                            pass
            except Exception:
                pass

            # Semáforo de mercado para la cabecera del screener.
            try:
                import market_regime
                regime = market_regime.get_market_regime()
            except Exception:
                regime = None

            _screener_cache["data"] = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "universe_size": len(universe),
                "matches": len(results),
                "results": results,
                "filters": SCREENER_FILTERS,
                "market_regime": regime,
            }
            _screener_cache["ts"] = datetime.now(timezone.utc)
            await _save_snapshot("screener", _screener_cache["data"])
        except Exception:
            pass
        finally:
            mem.trim()  # devuelve al SO la RAM de los DataFrames del escaneo


async def scan_growth_screener(force_refresh: bool = False):
    """Non-blocking: return cached data immediately, and kick off a background scan when
    the cache is missing or stale. The first call returns a 'warming' placeholder and the
    client polls until results are ready — scanning 120 names would otherwise time out."""
    now = datetime.now(timezone.utc)
    fresh = (
        _screener_cache["data"]
        and _screener_cache["ts"]
        and (now - _screener_cache["ts"]) < _SCREENER_TTL
    )
    if fresh and not force_refresh:
        return _screener_cache["data"]

    # Need a (re)scan — launch it in the background so the request stays fast
    if not _screener_lock.locked():
        asyncio.create_task(_run_screener_scan())

    if _screener_cache["data"]:
        return _screener_cache["data"]  # stale but usable while the new scan runs

    return {
        "generated_at": now.isoformat(),
        "universe_size": len(GROWTH_UNIVERSE),
        "matches": 0,
        "results": [],
        "filters": SCREENER_FILTERS,
        "status": "warming",
    }


async def _analyze_one(symbol: str):
    try:
        quote = await asyncio.to_thread(market_data.get_quote, symbol)
        if not quote:
            return None
        df = await asyncio.to_thread(market_data.get_full_indicator_history, symbol)
        if df is None or df.empty:
            return None
        indicators_data = await asyncio.to_thread(ind.compute_all, df)
        consensus_raw = await asyncio.to_thread(external_data.finnhub_recommendation_trends, symbol)
        consensus = external_data.aggregate_recommendation(consensus_raw)

        # Signals scoring
        signals = []
        score = 0
        rsi_val = indicators_data.get("rsi")
        change_pct = quote.get("change_percent") or 0
        macd = indicators_data.get("macd") or {}
        sma20 = (indicators_data.get("sma") or {}).get("20")
        sma50 = (indicators_data.get("sma") or {}).get("50")
        price = quote.get("price")
        low_52w = quote.get("low_52w")
        high_52w = quote.get("high_52w")

        category = None

        # 1) Oversold (RSI < 30)
        if rsi_val is not None and rsi_val < 32:
            signals.append(f"RSI sobrevendido ({rsi_val})")
            score += 30
            category = "OVERSOLD"

        # 2) Big intraday drop (potential dip-buy)
        if change_pct <= -3:
            signals.append(f"Caída fuerte hoy ({change_pct:.2f}%)")
            score += 25
            if not category:
                category = "DIP"

        # 3) Strong momentum (RSI > 60 with price above MA20)
        if rsi_val is not None and 55 <= rsi_val <= 70 and sma20 and price and price > sma20:
            signals.append("Momentum alcista sano")
            score += 15
            if not category:
                category = "MOMENTUM"

        # 4) Golden cross / above MA50
        if sma20 and sma50 and sma20 > sma50 and price and price > sma50:
            signals.append("Tendencia alcista (SMA20 > SMA50)")
            score += 10

        # 5) Near 52w low (potential reversal)
        if low_52w and price and low_52w > 0:
            ratio = (price - low_52w) / low_52w
            if ratio < 0.10:
                signals.append(f"Cerca de mínimo 52w (+{ratio*100:.1f}%)")
                score += 20
                if not category:
                    category = "VALUE"

        # 6) MACD histogram positive turn
        if macd.get("histogram") is not None and macd.get("histogram") > 0 and macd.get("macd") and macd.get("macd") > macd.get("signal", 0):
            signals.append("MACD bullish")
            score += 10

        # 7) Analyst consensus — más peso cuanto más fuerte (respaldo profesional).
        cons_score = consensus.get("score", 0) if consensus else 0
        if cons_score >= 80:  # Comprar fuerte
            signals.append(f"Consenso analistas: {consensus['consensus']} ({consensus['total_analysts']} analistas)")
            score += 28
        elif cons_score >= 65:  # Comprar
            signals.append(f"Consenso analistas: {consensus['consensus']} ({consensus['total_analysts']} analistas)")
            score += 15

        # 8) New 52w high (breakout)
        if high_52w and price and price >= high_52w * 0.98:
            signals.append("Cerca de máximos 52w (breakout)")
            score += 12
            if not category:
                category = "BREAKOUT"

        if score < 20:
            return None

        # Find nearest support and resistance for quick levels
        sr = indicators_data.get("support_resistance") or {}
        supports = sr.get("supports") or []
        resistances = sr.get("resistances") or []

        cat = category or "GENERAL"
        cons_label = consensus["consensus"] if consensus else None
        return {
            "symbol": symbol,
            "name": quote.get("name"),
            "price": quote.get("price"),
            "change_percent": quote.get("change_percent"),
            "rsi": rsi_val,
            "category": cat,
            "score": score,
            "signals": signals,
            "reason": _build_opportunity_reason(cat, signals, rsi_val, quote.get("change_percent"), cons_label),
            "suggested_entry": price,
            "nearest_support": supports[0] if supports else None,
            "nearest_resistance": resistances[0] if resistances else None,
            "analyst_consensus": cons_label,
            "analysts_count": consensus["total_analysts"] if consensus else None,
            "consensus_score": cons_score or None,
            "market_cap": quote.get("market_cap"),
            "sector": quote.get("sector"),
        }
    except Exception:
        return None


_MAX_DAILY_UNIVERSE = 130


async def _build_daily_universe():
    """Universo del escaneo DIARIO (corto plazo) = lista curada + movers del día (gainers,
    losers y más activos de FMP). Los movers son descubrimiento oportuno: capturan la
    empresa que se mueve HOY aunque no esté en ninguna lista. Cada mover es una sola
    llamada barata; el análisis caro se acota a _MAX_DAILY_UNIVERSE símbolos en total."""
    movers = []
    for kind in ("gainers", "losers", "actives"):
        try:
            movers += await asyncio.to_thread(external_data.fmp_market_movers, kind, 20) or []
        except Exception:
            pass
    seen = set()
    universe = []
    for src in (UNIVERSE, movers):
        for sym in src:
            if sym and sym not in seen:
                seen.add(sym)
                universe.append(sym)
    return universe[:_MAX_DAILY_UNIVERSE]


async def scan_daily_opportunities(force_refresh: bool = False):
    now = datetime.now(timezone.utc)
    if not force_refresh and _cache["data"] and _cache["ts"] and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["data"]

    # If a scan is already running, return the previous (possibly stale) cache
    # instead of queueing — keeps the HTTP request fast and avoids proxy timeouts.
    if _scan_lock.locked():
        if _cache["data"]:
            return _cache["data"]
        # No cache yet — return a "warming" placeholder so the client can retry.
        return {
            "generated_at": now.isoformat(),
            "universe_size": len(UNIVERSE),
            "opportunities_found": 0,
            "top": [],
            "by_category": {},
            "status": "warming",
        }

    async with _scan_lock:
        # Re-check after acquiring lock (another coroutine may have just finished)
        now = datetime.now(timezone.utc)
        if not force_refresh and _cache["data"] and _cache["ts"] and (now - _cache["ts"]) < _CACHE_TTL:
            return _cache["data"]

        # Escaneo masivo de fondo: marca sus llamadas Finnhub como background para que
        # cedan cuota a las del usuario (dashboard) — igual que el screener.
        market_data.enter_finnhub_background()

        # Run analyses with limited concurrency. Each symbol loads ~2 años de datos en
        # un DataFrame + compute_all (pandas), así que sem=2 limita cuántos DataFrames
        # coexisten en memoria — pensado para que quepa holgado en 512 MB (plan Starter).
        # También respeta el límite de 60 llamadas/min de Finnhub free.
        universe = await _build_daily_universe()
        sem = asyncio.Semaphore(2)

        async def bounded(s):
            async with sem:
                return await _analyze_one(s)

        results = await asyncio.gather(*[bounded(s) for s in universe])
        items = [r for r in results if r is not None]
        # Ordena por score técnico y, a igualdad, por respaldo de analistas.
        items.sort(key=lambda x: (x["score"], x.get("consensus_score") or 0), reverse=True)

        # Group by category
        by_category = {}
        for it in items:
            by_category.setdefault(it["category"], []).append(it)

        data = {
            "generated_at": now.isoformat(),
            "universe_size": len(universe),
            "opportunities_found": len(items),
            "top": items[:15],
            "by_category": by_category,
        }
        _cache["data"] = data
        _cache["ts"] = now
        await _save_snapshot("daily", data)
        # Devuelve al SO la memoria de los DataFrames del escaneo cuanto antes.
        mem.trim()
        return data
