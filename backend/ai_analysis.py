"""AI analysis service supporting Groq (free) + premium models via emergentintegrations."""
import json
import os
import uuid
from groq import AsyncGroq

# emergentintegrations is an Emergent-only library. In external deployments (Render, etc.)
# it's not available — premium models are then disabled but Groq models still work.
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    EMERGENT_AVAILABLE = True
except ImportError:
    EMERGENT_AVAILABLE = False
    LlmChat = None
    UserMessage = None


# Provider, model_id, is_free
MODEL_MAP = {
    "llama-3.3-70b": ("groq", "llama-3.3-70b-versatile", True),
    "gpt-oss-120b": ("groq", "openai/gpt-oss-120b", True),
    "gpt-5.2": ("openai", "gpt-5.2", False),
    "claude-sonnet-4.5": ("anthropic", "claude-sonnet-4-5-20250929", False),
    "gemini-3-flash": ("gemini", "gemini-3-flash-preview", False),
}

DEFAULT_MODEL = "gpt-oss-120b"


SYSTEM_PROMPT = """Eres un analista financiero senior especializado en análisis técnico y trading de acciones de EE.UU.
Tu tarea es analizar los datos técnicos proporcionados y dar una recomendación CLARA y ACCIONABLE con MÚLTIPLES niveles operativos.

REGLAS ESTRICTAS:
- Responde SIEMPRE en español.
- Devuelve UNICAMENTE un objeto JSON válido (sin markdown, sin texto extra), con esta estructura EXACTA:
{
  "recommendation": "COMPRAR" | "VENDER" | "MANTENER",
  "confidence": 0-100,
  "trend": "ALCISTA" | "BAJISTA" | "LATERAL",
  "summary": "Resumen ejecutivo en 2-3 frases.",
  "entry_zones": [
    {"label": "CONSERVADORA", "min": número, "max": número, "comment": "explicación breve"},
    {"label": "MODERADA", "min": número, "max": número, "comment": "explicación breve"},
    {"label": "AGRESIVA", "min": número, "max": número, "comment": "explicación breve"}
  ],
  "stop_losses": [
    {"label": "AJUSTADO", "price": número, "comment": "breve"},
    {"label": "ESTANDAR", "price": número, "comment": "breve"},
    {"label": "AMPLIO", "price": número, "comment": "breve"}
  ],
  "take_profits": [
    {"label": "TP1", "price": número, "comment": "breve"},
    {"label": "TP2", "price": número, "comment": "breve"},
    {"label": "TP3", "price": número, "comment": "breve (ambicioso)"}
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
  "technical_analysis": "Análisis detallado de RSI, MACD, Bollinger, medias móviles. 3-5 frases.",
  "pattern_analysis": "Patrones gráficos detectados y su implicación.",
  "fundamentals_view": "Comentario breve sobre P/E, sector, contexto.",
  "risks": ["riesgo 1", "riesgo 2", "riesgo 3"],
  "catalysts": ["catalizador 1", "catalizador 2"],
  "timeframe": "CORTO_PLAZO" | "MEDIO_PLAZO" | "LARGO_PLAZO"
}

REGLAS PARA LOS NIVELES:
- Las 3 zonas de entrada (CONSERVADORA/MODERADA/AGRESIVA): cada una con un par min/max diferente. CONSERVADORA cerca de soportes fuertes, AGRESIVA cerca del precio actual.
- Los 3 stop losses (AJUSTADO/ESTANDAR/AMPLIO): AJUSTADO < ESTANDAR < AMPLIO en distancia al precio actual.
- Los 3 take profits (TP1/TP2/TP3): TP1 más cercano y conservador, TP3 más ambicioso. Distintos precios.
- Si COMPRAR: stop_loss < precio_actual, take_profits > precio_actual.
- Si VENDER (short): stop_loss > precio_actual, take_profits < precio_actual.
- TP1/TP2 de relación riesgo/beneficio mínima de 1.5.
- entry_zone, stop_loss, take_profit_1, take_profit_2 son los valores "estándar" (compatibilidad): equivalen a la opción MODERADA / ESTANDAR / TP1 / TP2.
- NO inventes datos. Basa todo en los inputs.
"""


async def _analyze_with_groq(model_id: str, messages_payload: str) -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY no configurada")
    client = AsyncGroq(api_key=api_key)

    async def _call(use_json_format: bool):
        kwargs = dict(
            model=model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": messages_payload + "\n\nRESPONDE SOLO CON JSON VÁLIDO."},
            ],
            max_tokens=2200,
            temperature=0.4,
        )
        if use_json_format:
            kwargs["response_format"] = {"type": "json_object"}
        return await client.chat.completions.create(**kwargs)

    # First try with strict JSON mode; on failure, retry without it
    try:
        completion = await _call(use_json_format=True)
    except Exception:
        completion = await _call(use_json_format=False)

    content = completion.choices[0].message.content or ""
    text = content.strip()
    # Strip <think> blocks (reasoning models include them)
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
            return json.loads(text[start : end + 1])
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
            return json.loads(text[start : end + 1])
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

    payload = {
        "quote": quote,
        "indicators": indicators,
        "recent_news_titles": [n.get("title") for n in (news or [])][:5],
        "analyst_consensus": analyst_consensus,
        "analyst_price_targets": price_target,
        "news_sentiment_score": sentiment_score,
    }

    user_msg = (
        f"Analiza los siguientes datos en VIVO y devuelve la recomendación en JSON. "
        f"Precio actual ${quote.get('price')}.\n\n"
        f"DATOS:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        f"Responde SOLO con el JSON, sin markdown."
    )

    if provider == "groq":
        return await _analyze_with_groq(model_id, user_msg)
    return await _analyze_with_emergent(provider, model_id, user_msg)
