"""AI analysis service supporting Groq (free) + premium models via emergentintegrations."""
import json
import os
import uuid
from groq import AsyncGroq

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    EMERGENT_AVAILABLE = True
except ImportError:
    EMERGENT_AVAILABLE = False
    LlmChat = None
    UserMessage = None


MODEL_MAP = {
    "llama-3.3-70b": ("groq", "llama-3.3-70b-versatile", True),
    "gpt-oss-120b": ("groq", "openai/gpt-oss-120b", True),
    "gpt-5.2": ("openai", "gpt-5.2", False),
    "claude-sonnet-4.5": ("anthropic", "claude-sonnet-4-5-20250929", False),
    "gemini-3-flash": ("gemini", "gemini-3-flash-preview", False),
}

DEFAULT_MODEL = "gpt-oss-120b"


SYSTEM_PROMPT = """Eres un analista financiero senior especializado en inversión a medio y largo plazo en acciones de EE.UU.
Tu metodología se basa en identificar NIVELES DE ACUMULACIÓN por zonas — como hacen los mejores gestores de fondos:
comprar por tramos a medida que el precio cae hacia soportes clave, con objetivos de rentabilidad del 30-80%.

FILOSOFÍA:
- Los niveles de compra se sitúan en SOPORTES HISTÓRICOS, niveles Fibonacci, máximos/mínimos relevantes y zonas de volumen.
- Los take-profits se basan en resistencias históricas y objetivos de precio de analistas.
- Siempre se piensa en términos de riesgo/recompensa: mínimo 2:1, idealmente 3:1 o más.
- Los stops son amplios para no ser sacado por volatilidad normal.

REGLAS ESTRICTAS:
- Responde SIEMPRE en español.
- Devuelve ÚNICAMENTE un objeto JSON válido (sin markdown, sin texto extra).
- NUNCA dejes arrays vacíos: risks, catalysts, key_levels.support y key_levels.resistance deben tener siempre al menos 3 elementos cada uno.
- Los precios deben ser números reales basados en los datos recibidos, NO inventados.
- key_levels.support: niveles por DEBAJO del precio actual (zonas de compra).
- key_levels.resistance: niveles por ENCIMA del precio actual (zonas de toma de beneficios).

ESTRUCTURA JSON EXACTA:
{
  "recommendation": "COMPRAR" | "VENDER" | "MANTENER",
  "confidence": 0-100,
  "trend": "ALCISTA" | "BAJISTA" | "LATERAL",
  "horizon": "MEDIO_PLAZO (3-12 meses)",
  "summary": "Resumen ejecutivo en 2-3 frases explicando la tesis de inversión principal y por qué estos niveles son relevantes.",

  "entry_zones": [
    {"label": "NIVEL 1 — Zona Óptima", "min": número, "max": número, "comment": "Explica por qué este nivel es soporte clave (Fibonacci, histórico, etc.)"},
    {"label": "NIVEL 2 — Segunda Entrada", "min": número, "max": número, "comment": "Siguiente soporte si rompe el nivel 1"},
    {"label": "NIVEL 3 — Entrada Agresiva", "min": número, "max": número, "comment": "Zona de soporte fuerte, mayor rebote esperado"}
  ],

  "stop_losses": [
    {"label": "STOP AJUSTADO", "price": número, "comment": "Pérdida máxima del 5-7%, para operaciones de corto plazo"},
    {"label": "STOP ESTÁNDAR", "price": número, "comment": "Pérdida máxima del 10-12%, nivel clave que invalida la tesis"},
    {"label": "STOP AMPLIO", "price": número, "comment": "Pérdida máxima del 15-20%, solo para inversión a largo plazo"}
  ],

  "take_profits": [
    {"label": "TP1 — Conservador", "price": número, "comment": "Primera resistencia clave, rentabilidad del 15-25%"},
    {"label": "TP2 — Objetivo Principal", "price": número, "comment": "Resistencia fuerte, rentabilidad del 30-50%"},
    {"label": "TP3 — Objetivo Ambicioso", "price": número, "comment": "Máximo potencial, rentabilidad del 60-100%"}
  ],

  "entry_zone": {"min": número, "max": número},
  "stop_loss": número,
  "take_profit_1": número,
  "take_profit_2": número,
  "risk_reward_ratio": número,

  "key_levels": {
    "support": [número, número, número],
    "resistance": [número, número, número]
  },

  "technical_analysis": "Análisis detallado en 4-6 frases: RSI (nivel exacto e interpretación), MACD (señal y cruce), medias móviles (SMA20, SMA50, SMA200 y su relación con el precio), Bandas de Bollinger, volumen.",

  "fibonacci_analysis": "Explica los niveles Fibonacci clave detectados y cuál coincide mejor con los soportes técnicos.",

  "pattern_analysis": "Patrones chartistas identificados (doble suelo, cabeza-hombros, triángulos, etc.) y su implicación para el precio.",

  "fundamentals_view": "Comentario sobre P/E vs sector, crecimiento de ingresos, márgenes, deuda. ¿Está barata o cara la acción en términos fundamentales?",

  "risks": [
    "Riesgo específico 1 con impacto cuantificado si es posible",
    "Riesgo específico 2",
    "Riesgo específico 3",
    "Riesgo macroeconómico relevante"
  ],

  "catalysts": [
    "Catalizador 1 con fecha aproximada si se conoce",
    "Catalizador 2",
    "Catalizador 3"
  ],

  "timeframe": "MEDIO_PLAZO"
}

CÓMO CALCULAR LOS NIVELES (usa los datos Fibonacci y soportes históricos del input):
1. NIVEL 1 de entrada: cerca del retroceso Fibonacci 38.2% o soporte histórico más cercano por debajo del precio actual
2. NIVEL 2: retroceso Fibonacci 50% o segundo soporte histórico
3. NIVEL 3: retroceso Fibonacci 61.8% o soporte más fuerte
4. STOP: por debajo del soporte más cercano a la entrada elegida (margen del 3-5%)
5. TP1: resistencia más cercana por encima del precio actual
6. TP2: siguiente resistencia o extensión Fibonacci 127.2%
7. TP3: extensión Fibonacci 161.8% o precio objetivo de analistas

IMPORTANTE: Si la acción está en tendencia BAJISTA en el CORTO plazo pero los fundamentales son sólidos, recomienda COMPRAR por tramos en los niveles de soporte. No confundas tendencia de corto plazo con oportunidad de medio plazo.
"""


def _build_payload(quote: dict, indicators: dict, news: list,
                   analyst_consensus: dict = None, price_target: dict = None) -> str:
    ind = indicators or {}
    price = quote.get("price") or 0
    # Prefer yfinance 52w values; fallback to indicator-computed values
    high_52w = quote.get("high_52w") or ind.get("high_52w") or price * 1.3
    low_52w = quote.get("low_52w") or ind.get("low_52w") or price * 0.7

    # Fibonacci retracements from 52-week range (high → low, standard support levels)
    rng = high_52w - low_52w
    fib_levels = {
        "23.6% (soporte menor)": round(high_52w - rng * 0.236, 2),
        "38.2% (soporte moderado)": round(high_52w - rng * 0.382, 2),
        "50.0% (soporte clave)": round(high_52w - rng * 0.500, 2),
        "61.8% (soporte fuerte — golden ratio)": round(high_52w - rng * 0.618, 2),
        "78.6% (soporte muy fuerte)": round(high_52w - rng * 0.786, 2),
    }
    # Fibonacci extensions for take-profits
    fib_extensions = {
        "127.2% (objetivo conservador)": round(low_52w + rng * 1.272, 2),
        "161.8% (objetivo principal)": round(low_52w + rng * 1.618, 2),
        "200.0% (objetivo ambicioso)": round(low_52w + rng * 2.000, 2),
    }

    sr = ind.get("support_resistance") or {}
    sma = ind.get("sma") or {}

    payload = {
        "symbol": quote.get("symbol"),
        "precio_actual": price,
        "nombre_empresa": quote.get("name"),
        "sector": quote.get("sector"),
        "industria": quote.get("industry"),
        "rango_52_semanas": {"maximo": high_52w, "minimo": low_52w},
        "posicion_en_rango_52s": f"{round((price - low_52w) / rng * 100, 1)}% desde mínimo" if rng > 0 else "N/A",
        "fibonacci_retrocesos": fib_levels,
        "fibonacci_extensiones_objetivo": fib_extensions,
        "soportes_tecnicos": sr.get("supports", []),
        "resistencias_tecnicas": sr.get("resistances", []),
        "medias_moviles": {
            "SMA20": sma.get("20"),
            "SMA50": sma.get("50"),
            "SMA200": sma.get("200"),
            "precio_vs_SMA20": f"{round((price / sma['20'] - 1) * 100, 1)}%" if sma.get("20") else None,
            "precio_vs_SMA50": f"{round((price / sma['50'] - 1) * 100, 1)}%" if sma.get("50") else None,
            "precio_vs_SMA200": f"{round((price / sma['200'] - 1) * 100, 1)}%" if sma.get("200") else None,
        },
        "rsi": ind.get("rsi"),
        "macd": ind.get("macd"),
        "bollinger": ind.get("bollinger"),
        "volumen_promedio": quote.get("avg_volume"),
        "volumen_hoy": quote.get("volume"),
        "per": quote.get("pe_ratio"),
        "eps": quote.get("eps"),
        "market_cap_millones": round(quote.get("market_cap", 0) / 1e6, 0) if quote.get("market_cap") else None,
        "dividendo_yield": quote.get("dividend_yield"),
        "beta": quote.get("beta"),
        "consenso_analistas_wall_street": analyst_consensus,
        "precio_objetivo_analistas": price_target,
        "patrones_tecnicos_detectados": ind.get("patterns", []),
        "noticias_recientes": [n.get("title") for n in (news or [])][:6],
    }

    return (
        f"Analiza en profundidad la acción {quote.get('symbol')} con precio actual ${price}.\n\n"
        f"DATOS COMPLETOS:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        f"Genera el análisis completo con todos los niveles operativos. "
        f"Usa los niveles Fibonacci y soportes técnicos proporcionados como base para los precios. "
        f"Rellena OBLIGATORIAMENTE risks (mínimo 4), catalysts (mínimo 3) y key_levels con valores reales. "
        f"Responde SOLO con JSON válido."
    )


async def _analyze_with_groq(model_id: str, user_msg: str) -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY no configurada")
    client = AsyncGroq(api_key=api_key)

    async def _call(use_json_format: bool):
        kwargs = dict(
            model=model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=3000,
            temperature=0.3,
        )
        if use_json_format:
            kwargs["response_format"] = {"type": "json_object"}
        return await client.chat.completions.create(**kwargs)

    try:
        completion = await _call(use_json_format=True)
    except Exception:
        completion = await _call(use_json_format=False)

    content = completion.choices[0].message.content or ""
    text = content.strip()
    if "<think>" in text:
        end = text.find("</think>")
        if end != -1:
            text = text[end + len("</think>"):].strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    if not text:
        raise RuntimeError("Modelo devolvió respuesta vacía. Intenta otra vez o cambia de modelo.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start: end + 1])
        raise RuntimeError(f"No se pudo parsear JSON del modelo. Inicio: {text[:100]}")


async def _analyze_with_emergent(provider: str, model_id: str, user_msg: str) -> dict:
    if not EMERGENT_AVAILABLE:
        raise RuntimeError(
            "Modelos premium no disponibles en este despliegue. "
            "Usa GPT-OSS 120B o Llama 3.3 70B (ambos gratis)."
        )
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY no configurada")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"stock-analysis-{uuid.uuid4()}",
        system_message=SYSTEM_PROMPT,
    ).with_model(provider, model_id)
    response = await chat.send_message(UserMessage(text=user_msg))
    text = str(response).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start: end + 1])
        raise


async def analyze_stock(
    quote: dict,
    indicators: dict,
    news: list,
    model_key: str = DEFAULT_MODEL,
    analyst_consensus: dict = None,
    price_target: dict = None,
    sentiment_score: float = None,
) -> dict:
    provider, model_id, _is_free = MODEL_MAP.get(model_key, MODEL_MAP[DEFAULT_MODEL])
    user_msg = _build_payload(quote, indicators, news, analyst_consensus, price_target)

    if provider == "groq":
        return await _analyze_with_groq(model_id, user_msg)
    return await _analyze_with_emergent(provider, model_id, user_msg)
