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
        return {
            "timeframe": tf,
            "precio": round(float(px), 2) if px is not None else None,
            "patron": {"nombre": pat.get("nombre"), "sentido": pat.get("sentido")} if pat else None,
            "vela": {"nombre": cs.get("nombre"), "sentido": cs.get("sentido")} if cs else None,
            "resistencia": res.get("price") if res else None,
            "soporte": sop.get("price") if sop else None,
            "directrices": tls,
        }
    except Exception:
        return None


_PROMPT = """Eres un analista técnico senior enseñando a un inversor particular que NO es
analista. Tu trabajo: dar un VEREDICTO claro, honesto y PEDAGÓGICO sobre {symbol}.

Te doy la RADIOGRAFÍA GEOMÉTRICA real de cada timeframe (patrón candidato, directrices,
soporte/resistencia y precio), calculada por un algoritmo. Tú NO inventas niveles nuevos:
usas ESTOS precios reales. Tu valor es LEER el conjunto, CORREGIR el patrón si el algoritmo
se equivocó, y explicar QUÉ hacer y POR QUÉ.

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
    "gatillo": "El evento y PRECIO concreto que activa la entrada. Ej: 'Compra si rompe $X con volumen'. Si es ESPERAR, di qué esperas.",
    "entrada": <precio number o null>,
    "invalidacion": <precio number: dónde te has equivocado y sales, o null>,
    "objetivo": <precio number del siguiente objetivo lógico, o null>,
    "por_que": "2-3 frases explicando el PORQUÉ del plan, para que el usuario APRENDA el razonamiento (no solo el qué)."
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
    # Descarga y radiografía de todos los timeframes en paralelo (cada uno cachea 15 min).
    snaps = await asyncio.gather(*[asyncio.to_thread(_tf_snapshot, sym, tf) for tf in _TFS])
    snaps = [s for s in snaps if s]
    if not snaps:
        raise RuntimeError(f"No hay datos suficientes para analizar '{sym}'.")

    brain = ""
    try:
        pats = ", ".join(
            s["patron"]["nombre"] for s in snaps if s.get("patron")
        )
        brain = knowledge_base.digest_for_prompt(f"análisis técnico chartista patrones {pats} {sym}")
    except Exception:
        brain = ""
    if not brain.strip():
        brain = "(sin principios específicos; usa tu criterio técnico estándar)"

    user_msg = _PROMPT.format(
        symbol=sym,
        snapshots=json.dumps(snaps, ensure_ascii=False, indent=2),
        brain=brain,
    )
    verdict = await ai_analysis._analyze_with_gemini_free(
        "gemini-2.5-flash",
        user_msg,
        system_prompt="Eres un analista técnico senior, honesto y didáctico. Respondes SOLO con JSON válido.",
        max_tokens=4000,
    )
    verdict["snapshots"] = snaps
    return verdict
