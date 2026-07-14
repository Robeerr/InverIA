"""Chartista IA — veredicto técnico multi-timeframe.

Combina LO MEJOR de dos mundos:
  1. GEOMETRÍA (chart_lines.py): niveles, directrices y patrón candidato EXACTOS por
     timeframe. Coordenadas reales, no inventadas.
  2. INTERPRETACIÓN (Gemini + cerebro): confirma/corrige el patrón, redacta el resumen
     multi-timeframe y da un plan accionable con precios anclados a la geometría.

El objetivo es PEDAGÓGICO: que el usuario (no analista) entienda CUÁNDO entrar, EN QUÉ
PRECIO y POR QUÉ — para aprender, no solo para obedecer.
"""
import asyncio
import json

import market_data
import chart_lines
import knowledge_base
import ai_analysis
import levels_engine


def _buy_zones(sym: str) -> list:
    """Zonas de compra por CONFLUENCIA (levels_engine): combina Volume Profile, Fibonacci,
    pivotes, SMA50/200 y swing lows sobre el DIARIO, rankeadas por fuerza. Es el mejor método
    de la casa (pesos validados empíricamente) y da niveles ESPACIADOS y reales para escalonar.
    Devuelve hasta 5 zonas con precio, banda, fuerza y el porqué. [] si falla."""
    try:
        df = market_data.get_stock_data(sym, timeframe="1D")
        if df is None or df.empty:
            return []
        candles = market_data.df_to_candles(df)
        closes = [c.get("close") for c in candles if c.get("close") is not None]
        if len(closes) < 30:
            return []
        px = closes[-1]
        sma = {"50": round(sum(closes[-50:]) / 50, 2) if len(closes) >= 50 else None,
               "200": round(sum(closes[-200:]) / 200, 2) if len(closes) >= 200 else None}
        zones = levels_engine.compute_buy_levels(df, None, px, sma) or []
        out = []
        for z in zones[:5]:
            motivo = " + ".join(z.get("reasons", [])[:3]) or z.get("label") or "confluencia"
            out.append({
                "precio": z.get("price"),
                "banda": [z.get("zone_low"), z.get("zone_high")],
                "fuerza_0a100": z.get("strength"),
                "distancia_pct": z.get("distance_pct"),
                "por_que": motivo,
            })
        return out
    except Exception:
        return []


def _silhouette(closes, buckets: int = 24) -> list:
    """Silueta normalizada 0-100 del precio (últimas ~60 velas remuestreadas a `buckets`
    puntos). Le da al modelo la FORMA real para que juzgue el patrón (U redondeada vs V
    puntiaguda, etc.) en vez de fiarse a ciegas del algoritmo."""
    seg = closes[-60:] if len(closes) >= 60 else closes[:]
    if len(seg) < buckets:
        pts = [float(x) for x in seg]
    else:
        size = len(seg) / buckets
        pts = []
        for i in range(buckets):
            a, b = int(i * size), int((i + 1) * size)
            chunk = seg[a:b] or [seg[min(a, len(seg) - 1)]]
            pts.append(sum(chunk) / len(chunk))
    lo, hi = min(pts), max(pts)
    rng = (hi - lo) or 1
    return [round((p - lo) / rng * 100) for p in pts]

# Timeframes que analizamos. De más rápido a más lento: el intradía marca el timing de
# entrada, el diario/semanal marca la tendencia de fondo.
_TFS = ["15M", "1H", "4H", "1D", "1W"]


def _tf_snapshot(sym: str, tf: str) -> dict | None:
    """Descarga velas de un timeframe y saca su radiografía geométrica: patrón candidato,
    directrices, niveles clave y dónde está el precio. Best-effort: None si no hay datos."""
    try:
        df = market_data.get_stock_data(sym, timeframe=tf)
        if df is None or df.empty:
            return None
        candles = market_data.df_to_candles(df)
        if not candles or len(candles) < 20:
            return None
        px = candles[-1].get("close")
        lines = chart_lines.detect_lines(candles, current_price=px)
        pat = lines.get("pattern")
        cs = lines.get("candlestick")
        levels = lines.get("levels", [])
        res = next((l for l in levels if l.get("role") == "resistencia"), None)
        sop = next((l for l in levels if l.get("role") == "soporte"), None)
        tls = []
        for tl in lines.get("trendlines", []):
            tls.append({"tipo": tl.get("kind"), "direccion": tl.get("direction")})
        closes = [c.get("close") for c in candles if c.get("close") is not None]
        # NIVELES REALES para anclar las compras escalonadas (nada inventado):
        # todos los soportes por DEBAJO del precio + las medias móviles (soporte dinámico).
        soportes = sorted({round(float(l["price"]), 2) for l in levels
                           if l.get("role") == "soporte" and l.get("price") and l["price"] < px},
                          reverse=True)[:4]
        sma50 = round(sum(closes[-50:]) / 50, 2) if len(closes) >= 50 else None
        sma200 = round(sum(closes[-200:]) / 200, 2) if len(closes) >= 200 else None
        # nivel del patrón (p.ej. soporte de la taza/directriz) si el patrón lo trae
        niv_patron = None
        if pat and pat.get("pivote"):
            niv_patron = round(float(pat["pivote"]), 2)
        return {
            "timeframe": tf,
            "precio": round(float(px), 2) if px is not None else None,
            "patron_candidato_algoritmo": {"nombre": pat.get("nombre"), "sentido": pat.get("sentido")} if pat else None,
            "vela": {"nombre": cs.get("nombre"), "sentido": cs.get("sentido")} if cs else None,
            "resistencia": res.get("price") if res else None,
            "soporte": sop.get("price") if sop else None,
            "soportes_reales": soportes,
            "sma50": sma50,
            "sma200": sma200,
            "nivel_patron": niv_patron,
            "directrices": tls,
            "forma_precio_0a100": _silhouette(closes),
        }
    except Exception:
        return None


_PROMPT = """Eres un analista técnico senior enseñando a un inversor particular que NO es
analista. Tu trabajo: dar un VEREDICTO claro, honesto y PEDAGÓGICO sobre {symbol}.

Te doy la RADIOGRAFÍA de cada timeframe: un `patron_candidato_algoritmo` (una PROPUESTA de
un algoritmo geométrico que SE EQUIVOCA A MENUDO), los niveles reales (soporte/resistencia,
directrices, precio) y `forma_precio_0a100` — la SILUETA real del precio normalizada de 0
(mínimo) a 100 (máximo), izquierda→derecha.

REGLA DE ORO: el patrón candidato NO es la verdad. TÚ decides el patrón MIRANDO la
`forma_precio_0a100`. Valídalo contra la definición real:
- Taza con asa: forma en "U" REDONDEADA y ancha (baja gradual, fondo plano largo, sube
  gradual), + una pequeña recaída final (asa). Si es una "V" puntiaguda (baja y sube de
  golpe), NO es taza — recházalo.
- Triángulo ascendente: máximos planos (~mismo techo) + mínimos SUBIENDO.
- Cuña descendente: máximos y mínimos ambos BAJANDO pero convergiendo, sesgo alcista.
- Doble suelo/techo: dos valles/picos al mismo nivel separados.
Si la forma no encaja LIMPIAMENTE con ningún patrón, dilo: "sin patrón claro" es una
respuesta VÁLIDA y honesta. No inventes un patrón para rellenar.

NO inventes niveles: usa los precios reales que te doy.

CÓMO OPERA EL USUARIO — MUY IMPORTANTE: compra ESCALONANDO por niveles (no todo de golpe).
El plan debe dar 2-3 NIVELES DE COMPRA, NO un solo precio.

De DÓNDE salen esos niveles (regla innegociable): usa las ZONAS DE COMPRA por confluencia
que te doy abajo (`zonas_de_compra`). Es el mejor método: combina Volume Profile, Fibonacci,
pivotes y medias sobre el DIARIO, ya rankeadas por FUERZA y bien ESPACIADAS. Elige 2-3 de
esas zonas (preferiendo las de más `fuerza_0a100`) para escalonar, con separación real entre
ellas (evita niveles pegados a <1%). Si `zonas_de_compra` está vacío, cae a los
`soportes_reales`/`sma200` de la radiografía diaria/semanal (NO a los intradía de 15M/1H).
NADA de precios inventados ni redondos al azar. Reparte el % (ej: 30/30/40, más peso a las
zonas más profundas/fuertes). En cada `motivo` cita la confluencia real (ej: "POC + Fib 61.8%",
"SMA200"). Si no hay ninguna zona real por debajo (acción en máximos sin estructura), deja
`niveles_entrada: []` y acción ESPERAR — mejor no forzar niveles aleatorios.

ZONAS DE COMPRA POR CONFLUENCIA (diario, rankeadas — úsalas para escalonar):
{zonas}

RADIOGRAFÍA POR TIMEFRAME:
{snapshots}

CONOCIMIENTO DE NUESTROS MAESTROS (aplica estos criterios al juzgar):
{brain}

Devuelve SOLO un JSON con esta estructura EXACTA (en ESPAÑOL, tono cercano y didáctico):
{{
  "por_timeframe": [
    {{"tf": "15M", "lectura": "1 frase: qué se ve y qué implica para el timing"}},
    ... uno por cada timeframe con datos ...
  ],
  "patron_principal": "El patrón que MANDA ahora mismo y en qué timeframe (corrige el del algoritmo si te parece mal, y di por qué en una coletilla)",
  "sentido": "alcista" | "bajista" | "neutro",
  "veredicto": "2-4 frases: la foto global. ¿Tendencia sana o rota? ¿Fase de acumulación, ruptura, o hay que esperar? Habla como a un principiante.",
  "plan": {{
    "accion": "COMPRAR" | "ESPERAR" | "EVITAR",
    "gatillo": "El evento/condición que activa el plan. Ej: 'Compra escalonada en los niveles de abajo' o, si es ESPERAR, qué esperas.",
    "niveles_entrada": [
      {{"precio": <number, un nivel REAL de la radiografía>, "porcentaje": <number, % de la posición a comprar aquí>, "motivo": "a qué nivel real corresponde (soporte 1D X / SMA200 / mínimo del patrón)"}}
      // 2-3 niveles ordenados de más cercano a más profundo; [] si no hay estructura real y toca ESPERAR
    ],
    "invalidacion": <precio number: bajo el nivel más profundo, donde la tesis se rompe y sales, o null>,
    "objetivo": <precio number del siguiente objetivo lógico, o null>,
    "por_que": "2-3 frases explicando el PORQUÉ del plan y por qué esos niveles (no otros), para que el usuario APRENDA el razonamiento."
  }},
  "para_aprender": "1 frase de enseñanza general que el usuario se pueda llevar de este caso (el concepto técnico detrás)."
}}

Sé HONESTO: si lo más sabio es esperar, di ESPERAR. No fuerces una compra. Precios siempre
coherentes con la radiografía (entrada cerca de soporte/ruptura, invalidación bajo soporte,
objetivo hacia resistencia)."""


async def analyze(symbol: str) -> dict:
    """Genera el veredicto del Chartista IA para un símbolo. Lanza RuntimeError si no hay
    datos suficientes o si el modelo falla (el endpoint traduce a HTTP)."""
    sym = symbol.upper()
    # Descarga y radiografía de todos los timeframes en paralelo (cada uno cachea 15 min) +
    # las zonas de compra por confluencia (el mejor método de la casa) para escalonar.
    snaps, zonas = await asyncio.gather(
        asyncio.gather(*[asyncio.to_thread(_tf_snapshot, sym, tf) for tf in _TFS]),
        asyncio.to_thread(_buy_zones, sym),
    )
    snaps = [s for s in snaps if s]
    if not snaps:
        raise RuntimeError(f"No hay datos suficientes para analizar '{sym}'.")

    brain = ""
    try:
        pats = ", ".join(
            s["patron_candidato_algoritmo"]["nombre"] for s in snaps if s.get("patron_candidato_algoritmo")
        )
        brain = knowledge_base.digest_for_prompt(f"análisis técnico chartista patrones {pats} {sym}")
    except Exception:
        brain = ""
    if not brain.strip():
        brain = "(sin principios específicos; usa tu criterio técnico estándar)"

    user_msg = _PROMPT.format(
        symbol=sym,
        zonas=json.dumps(zonas, ensure_ascii=False, indent=2) if zonas else "(sin zonas de confluencia; usa soportes diarios/semanales)",
        snapshots=json.dumps(snaps, ensure_ascii=False, indent=2),
        brain=brain,
    )
    verdict = await ai_analysis._analyze_with_gemini_free(
        ai_analysis.GEMINI_MODEL,
        user_msg,
        system_prompt="Eres un analista técnico senior, honesto y didáctico. Respondes SOLO con JSON válido.",
        max_tokens=16000,  # el veredicto (multi-TF + niveles escalonados + pedagógico) se cortaba a 8000
    )
    verdict["snapshots"] = snaps
    return verdict
