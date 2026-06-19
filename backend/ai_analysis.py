"""AI analysis service supporting Groq + Google Gemini (both free) + premium via emergentintegrations."""
import asyncio
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

try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    genai_types = None


# (provider, model_id, is_free)
MODEL_MAP = {
    "gpt-oss-120b": ("groq", "openai/gpt-oss-120b", True),
    "llama-3.3-70b": ("groq", "llama-3.3-70b-versatile", True),
    "gemini-2.5-flash": ("google_free", "gemini-2.5-flash", True),
    "gpt-5.2": ("openai", "gpt-5.2", False),
    "claude-sonnet-4.5": ("anthropic", "claude-sonnet-4-5-20250929", False),
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

  "insider_view": "Si hay datos de insider_trading_directivos: interpreta si los directivos compran o venden y qué implica. Si no hay datos, devuelve cadena vacía.",

  "earnings_view": "Si hay datos de historial_resultados_earnings: comenta si la empresa suele batir o fallar estimaciones (beat_rate) y qué implica para la fiabilidad. Si no hay datos, devuelve cadena vacía.",

  "price_prediction": {
    "target_3m": número (precio estimado a 3 meses),
    "target_6m": número (precio estimado a 6 meses),
    "target_12m": número (precio estimado a 12 meses),
    "confidence": número 0-100,
    "rationale": "1-2 frases justificando la proyección. Ancla la estimación en el precio objetivo de analistas, la tendencia, los fundamentales y el Volume Profile. No inventes cifras disparatadas."
  },

  "earnings_prediction": {
    "will_beat": "SÍ" | "NO" | "INCIERTO",
    "confidence": número 0-100,
    "rationale": "Basándote en el beat_rate histórico y la tendencia de resultados, ¿batirá las próximas estimaciones? Si no hay datos de earnings, devuelve INCIERTO."
  },

  "competitive_position": "Posición competitiva de la empresa: ¿es la líder (#1) de su sector? ¿En qué sub-sectores compite y con qué cuota aproximada de mercado? Usa tu conocimiento de la empresa. Si no la conoces bien, dilo con honestidad en vez de inventar.",

  "main_rival": "El competidor que supone la mayor amenaza estructural y por qué (1-2 frases). Si la empresa es la #1, indica igualmente su rival más relevante.",

  "sector_outlook": "Potencial del sector a 3-5 años: catalizadores estructurales, tendencias de fondo y vientos de cola o de cara que afectarán a la empresa.",

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

CÓMO CALCULAR LOS NIVELES (prioridad de fuentes, de mayor a menor fiabilidad):
1. **Volume Profile (prioridad máxima)**: El POC es el soporte/resistencia más fuerte. Las HVN son zonas donde el precio rebota. Úsalos como base para los niveles de entrada.
2. **Fibonacci**: Los retrocesos 38.2%, 50%, 61.8% que coincidan con HVN del Volume Profile son niveles de confluencia EXTREMADAMENTE fiables — ponlos como NIVEL 1 o NIVEL 2.
3. **Soportes técnicos**: Pivots históricos del gráfico como confirmación adicional.

REGLA DE ORO: Un nivel es fuerte cuando coinciden 2+ fuentes (ej: retroceso 61.8% + HVN del Volume Profile + soporte técnico = nivel de compra muy alto).

NIVELES DE ENTRADA (deben ESCALONARSE en profundidad — acumulación por tramos, NO los tres pegados al precio actual):
- NIVEL 1: Zona más cercana por debajo del precio actual con confluencia HVN + Fibonacci (típicamente -1% a -5%)
- NIVEL 2: Siguiente soporte fuerte o retroceso Fibonacci 50%/61.8% (típicamente -8% a -15%)
- NIVEL 3 (ENTRADA AGRESIVA PROFUNDA): cerca del VAL (Value Area Low) o de la HVN más profunda. Representa un escenario de corrección fuerte donde la acción está claramente infravalorada. DEBE estar bastante por debajo del precio (típicamente -15% a -30%). NUNCA pongas el NIVEL 3 pegado al precio actual: su función es capturar una caída profunda hacia soporte estructural.

STOPS: por debajo de la LVN o del VAL (el precio cae rápido al perder esas zonas)
TP1: primera HVN, POC (si está por encima) o resistencia técnica cercana
TP2: VAH del Value Area o retroceso Fibonacci 50%/61.8%
TP3: objetivo ambicioso PERO REALISTA. Usa la extensión Fibonacci 127.2%/161.8% o el precio objetivo de analistas, PERO NUNCA un valor que supere de forma absurda el máximo de 52 semanas (más de ~10-15% por encima del máximo histórico es irreal). Si la extensión Fibonacci da un valor disparatado, limita el TP3 al máximo de 52 semanas o al precio objetivo de los analistas.

SEÑALES ADICIONALES (úsalas para ajustar confianza y recomendación):
- **Insider trading**: Si los directivos COMPRAN sus propias acciones (net_shares positivo), es una de las señales alcistas más fiables — sube la confianza. Si VENDEN masivamente, precaución.
- **Earnings history**: Un beat_rate alto (>75%) indica una empresa que suele superar expectativas — mayor fiabilidad de la tesis alcista. Un beat_rate bajo añade riesgo.

IMPORTANTE: Si la acción está en tendencia BAJISTA en el CORTO plazo pero los fundamentales son sólidos, recomienda COMPRAR por tramos en los niveles de soporte. No confundas tendencia de corto plazo con oportunidad de medio plazo.
"""


def _build_payload(quote: dict, indicators: dict, news: list,
                   analyst_consensus: dict = None, price_target: dict = None,
                   volume_profile: dict = None, insider: dict = None,
                   earnings_history: dict = None, buy_levels: list = None) -> str:
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
        "crecimiento_ventas_yoy_pct": quote.get("revenue_growth"),
        "crecimiento_eps_yoy_pct": quote.get("eps_growth"),
        "market_cap_millones": round(quote.get("market_cap", 0) / 1e6, 0) if quote.get("market_cap") else None,
        "dividendo_yield": quote.get("dividend_yield"),
        "beta": quote.get("beta"),
        "consenso_analistas_wall_street": analyst_consensus,
        "precio_objetivo_analistas": price_target,
        "insider_trading_directivos": insider,
        "historial_resultados_earnings": earnings_history,
        "patrones_tecnicos_detectados": ind.get("patterns", []),
        "noticias_recientes": [n.get("title") for n in (news or [])][:6],
        "volume_profile": {
            "POC_punto_de_control": (volume_profile or {}).get("poc"),
            "VAH_value_area_high": (volume_profile or {}).get("vah"),
            "VAL_value_area_low": (volume_profile or {}).get("val"),
            "HVN_zonas_alto_volumen": (volume_profile or {}).get("hvn", []),
            "LVN_zonas_bajo_volumen": (volume_profile or {}).get("lvn", []),
            "descripcion": (
                "El POC es el precio con mayor volumen negociado histórico — soporte/resistencia más fuerte. "
                "Las HVN son zonas de alto volumen (el precio rebota). "
                "Las LVN son zonas de bajo volumen (el precio las atraviesa rápido). "
                "El Value Area (VAL-VAH) contiene el 70% del volumen total — zona de equilibrio."
            ) if volume_profile else "No disponible",
        } if volume_profile else None,
    }

    # Zonas de compra ya calculadas por el motor de confluencia (deterministas).
    levels_block = ""
    if buy_levels:
        levels_block = (
            "\n\nZONAS DE COMPRA YA CALCULADAS POR CONFLUENCIA (úsalas como BASE OBLIGATORIA "
            "para entry_zones y key_levels.support — están ordenadas de más cercana a más "
            "profunda y cada una trae su fuerza 0-100 y los métodos que coinciden):\n"
            + json.dumps([
                {
                    "nivel": z.get("label"),
                    "precio": z.get("price"),
                    "zona": [z.get("zone_low"), z.get("zone_high")],
                    "fuerza_0_100": z.get("strength"),
                    "distancia_pct": z.get("distance_pct"),
                    "confluencia": z.get("reasons"),
                }
                for z in buy_levels
            ], ensure_ascii=False, indent=2)
            + "\n\nINSTRUCCIÓN: respeta estos precios/zonas para las entradas (no los inventes "
            "de nuevo). En el comment de cada entry_zone EXPLICA la confluencia indicada. "
            "Si necesitas una entrada más profunda que las dadas, puedes añadirla, pero las "
            "calculadas son la referencia principal."
        )

    return (
        f"Analiza en profundidad la acción {quote.get('symbol')} con precio actual ${price}.\n\n"
        f"DATOS COMPLETOS:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        f"{levels_block}\n\n"
        f"Genera el análisis completo con todos los niveles operativos. "
        f"Usa los niveles Fibonacci y soportes técnicos proporcionados como base para los precios. "
        f"Rellena OBLIGATORIAMENTE risks (mínimo 4), catalysts (mínimo 3) y key_levels con valores reales. "
        f"Responde SOLO con JSON válido."
    )


def _repair_truncated_json(text: str):
    """Best-effort repair of JSON truncated mid-output (e.g. hit the token limit):
    close any open string, then close open arrays/objects so json.loads can parse
    whatever complete fields were produced. Returns a candidate string or None."""
    start = text.find("{")
    if start == -1:
        return None
    s = text[start:]
    in_str = False
    escape = False
    stack = []
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack:
            stack.pop()
    repaired = s
    if in_str:
        repaired += '"'
    # Drop dangling separators left by the cut (",", ":", or an orphan "key")
    repaired = repaired.rstrip()
    while repaired and repaired[-1] in ",:":
        repaired = repaired[:-1].rstrip()
        if repaired and repaired[-1] == '"':
            # remove the orphan key string that had no value
            depth = 0
            for j in range(len(repaired) - 1, -1, -1):
                if repaired[j] == '"' and (j == 0 or repaired[j - 1] != "\\"):
                    depth += 1
                    if depth == 2:
                        repaired = repaired[:j].rstrip().rstrip(",").rstrip()
                        break
    for closer in reversed(stack):
        repaired += closer
    return repaired


def _parse_model_json(content: str) -> dict:
    """Clean and parse a model's text response into a dict, tolerating
    <think> blocks, ```json fences, surrounding prose and truncated output."""
    text = (content or "").strip()
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
        raise RuntimeError("El modelo devolvió una respuesta vacía. Intenta otra vez o cambia de modelo.")
    # 1) Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2) Substring between first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            pass
    # 3) Repair truncated JSON (token limit hit mid-output)
    repaired = _repair_truncated_json(text)
    if repaired:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
    raise RuntimeError(f"No se pudo parsear el JSON del modelo. Inicio: {text[:100]}")


async def _analyze_with_groq(model_id: str, user_msg: str,
                             system_prompt: str = SYSTEM_PROMPT,
                             max_tokens: int = 3000) -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY no configurada")
    client = AsyncGroq(api_key=api_key)

    async def _call(use_json_format: bool):
        kwargs = dict(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=max_tokens,
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
    return _parse_model_json(content)


async def _analyze_with_gemini_free(model_id: str, user_msg: str,
                                    system_prompt: str = SYSTEM_PROMPT,
                                    max_tokens: int = 16384) -> dict:
    """Google Gemini via the free AI Studio API (GEMINI_API_KEY)."""
    if not GEMINI_AVAILABLE:
        raise RuntimeError(
            "La librería google-genai no está instalada en el servidor. "
            "Añádela a requirements.txt y vuelve a desplegar."
        )
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY no configurada. Crea una key gratis en "
            "https://aistudio.google.com/apikey y añádela en Render."
        )
    client = genai.Client(api_key=api_key)
    config = genai_types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.3,
        # Gemini 2.5 Flash spends part of the budget on internal "thinking",
        # so give plenty of headroom for thinking + the full JSON answer.
        max_output_tokens=max_tokens,
        response_mime_type="application/json",
    )
    # SDK call is synchronous — run off the event loop
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model_id,
        contents=user_msg,
        config=config,
    )
    text = getattr(response, "text", "") or ""
    if not text:
        raise RuntimeError(
            "Gemini no devolvió texto (posible límite de tokens agotado en 'thinking'). "
            "Intenta otra vez o usa GPT-OSS 120B."
        )
    return _parse_model_json(text)


async def _analyze_with_emergent(provider: str, model_id: str, user_msg: str,
                                 system_prompt: str = SYSTEM_PROMPT) -> dict:
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
        system_message=system_prompt,
    ).with_model(provider, model_id)
    response = await chat.send_message(UserMessage(text=user_msg))
    return _parse_model_json(str(response))


async def _run_model(model_key: str, system_prompt: str, user_msg: str,
                     max_tokens: int = 3000) -> dict:
    """Dispatch a single JSON-returning completion to whichever provider backs
    `model_key`, using a custom system prompt. Shared by the full analysis and
    the lightweight '¿por qué se mueve hoy?' explainer."""
    provider, model_id, _is_free = MODEL_MAP.get(model_key, MODEL_MAP[DEFAULT_MODEL])
    if provider == "groq":
        return await _analyze_with_groq(model_id, user_msg, system_prompt, max_tokens)
    if provider == "google_free":
        return await _analyze_with_gemini_free(model_id, user_msg, system_prompt, max_tokens)
    return await _analyze_with_emergent(provider, model_id, user_msg, system_prompt)


async def analyze_stock(
    quote: dict,
    indicators: dict,
    news: list,
    model_key: str = DEFAULT_MODEL,
    analyst_consensus: dict = None,
    price_target: dict = None,
    sentiment_score: float = None,
    volume_profile: dict = None,
    insider: dict = None,
    earnings_history: dict = None,
    buy_levels: list = None,
) -> dict:
    user_msg = _build_payload(quote, indicators, news, analyst_consensus, price_target,
                              volume_profile, insider, earnings_history, buy_levels)
    return await _run_model(model_key, SYSTEM_PROMPT, user_msg, max_tokens=5000)


# ---------- "¿Por qué se mueve hoy?" — explicación ligera del movimiento diario ----------

DAILY_MOVE_PROMPT = """Eres un analista de mercado que explica, en lenguaje claro y directo, POR QUÉ una acción se mueve HOY.
Recibes el precio, el cambio del día y los titulares de noticias recientes. Tu trabajo es conectar el movimiento con sus causas probables.

REGLAS ESTRICTAS:
- Responde SIEMPRE en español, tono cercano pero riguroso.
- Devuelve ÚNICAMENTE un objeto JSON válido (sin markdown, sin texto extra).
- Básate en las noticias proporcionadas. Si NINGUNA noticia explica el movimiento, dilo con honestidad y baja la fiabilidad — NO inventes catalizadores.
- Distingue entre causa específica de la empresa (resultados, upgrade, producto) y arrastre del mercado/sector (macro, tipos, todo el sector cae).

ESTRUCTURA JSON EXACTA:
{
  "veredicto": "SUBE" | "BAJA" | "PLANO",
  "titular": "Una frase corta (máx 12 palabras) que resuma la causa principal del movimiento de hoy.",
  "factores": [
    "Factor 1: causa concreta con el dato si lo hay",
    "Factor 2: otra causa o contexto relevante",
    "Factor 3: opcional"
  ],
  "resumen": "2-4 frases explicando el movimiento, enlazando precio + noticias + contexto de mercado.",
  "tipo_movimiento": "ESPECÍFICO_EMPRESA" | "SECTOR_MERCADO" | "MIXTO" | "SIN_CATALIZADOR_CLARO",
  "fiabilidad": "ALTA" | "MEDIA" | "BAJA"
}

La fiabilidad es ALTA solo si una noticia clara justifica el movimiento; MEDIA si es plausible pero indirecto; BAJA si no hay noticia que lo explique (movimiento técnico o ruido de mercado).
"""


def _build_daily_move_payload(quote: dict, news: list) -> str:
    price = quote.get("price")
    chg = quote.get("change")
    chg_pct = quote.get("change_percent")
    payload = {
        "symbol": quote.get("symbol"),
        "nombre_empresa": quote.get("name"),
        "sector": quote.get("sector"),
        "industria": quote.get("industry"),
        "precio_actual": price,
        "cambio_hoy_usd": chg,
        "cambio_hoy_pct": chg_pct,
        "cierre_anterior": quote.get("previous_close"),
        "apertura": quote.get("open"),
        "maximo_dia": quote.get("day_high"),
        "minimo_dia": quote.get("day_low"),
        "volumen_hoy": quote.get("volume"),
        "volumen_promedio": quote.get("avg_volume"),
        "noticias_recientes": [
            {"titular": n.get("title"), "fuente": n.get("publisher")}
            for n in (news or [])
        ][:8],
    }
    return (
        f"Explica por qué {quote.get('symbol')} se mueve hoy "
        f"({'+' if (chg_pct or 0) >= 0 else ''}{chg_pct}%).\n\n"
        f"DATOS:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        f"Responde SOLO con el JSON pedido."
    )


async def explain_daily_move(quote: dict, news: list,
                             model_key: str = DEFAULT_MODEL) -> dict:
    """Lightweight, cheap explainer for the daily price move. Uses a small prompt
    (~600 input tokens) so it costs a fraction of a full analysis."""
    user_msg = _build_daily_move_payload(quote, news)
    return await _run_model(model_key, DAILY_MOVE_PROMPT, user_msg, max_tokens=900)
