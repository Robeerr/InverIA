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

DEFAULT_MODEL = "gemini-2.5-flash"


SYSTEM_PROMPT = """Eres un analista financiero senior especializado en inversión a medio y largo plazo en acciones de EE.UU.
Tu metodología se basa en identificar NIVELES DE ACUMULACIÓN por zonas — como hacen los mejores gestores de fondos:
comprar por tramos a medida que el precio cae hacia soportes clave, con objetivos de rentabilidad del 30-80%.

FILOSOFÍA:
- Los niveles de compra se sitúan en SOPORTES HISTÓRICOS, niveles Fibonacci, máximas/mínimas relevantes, VWAP anclado y zonas de volumen.
- Los take-profits se basan en resistencias históricas, extensiones Fibonacci (127.2%/161.8%) y objetivos de analistas.
- Siempre se piensa en términos de riesgo/recompensa: mínimo 2:1, idealmente 3:1 o más.
- Los stops se dimensionan usando el ATR (volatilidad real): stop ajustado = 1.5×ATR bajo la entrada, stop estándar = 2.0×ATR, stop amplio = 3.0×ATR.

REGLAS DE STOP-LOSS (basadas en ATR — el método profesional):
- El ATR refleja la volatilidad real diaria del activo. Un stop que no respete el ATR es ejecutado por ruido.
- Stop ajustado: precio_entrada − 1.5 × ATR (para swing traders con horizonte días-semanas) — ESTE ES EL POR DEFECTO.
- Stop estándar: precio_entrada − 2.0 × ATR (solo para inversores a medio plazo si la tesis lo exige)
- Stop amplio: precio_entrada − 3.0 × ATR (solo posiciones de largo plazo, por debajo de soporte estructural)
- NUNCA uses stops fijos de "5-7%" o "10-12%" — eso es arbitrario. Usa el ATR del activo.
- REGLA DE ORO (R/R): el stop NUNCA debe estar tan lejos que TP1 dé menos de 1.5:1. Es decir,
  la distancia entrada→TP1 debe ser al menos 1.5× la distancia entrada→stop. Si un stop por ATR
  incumple esto, CÍÑELO hacia la entrada hasta cumplir 1.5:1. Perder más de lo que ganas cuando
  aciertas es el error a evitar: prioriza SIEMPRE un R/R sano sobre un stop "cómodo".

REGLAS DE TAKE-PROFIT:
- TP1: primera resistencia fuerte o extensión Fibonacci 100% (vuelta al máximo swing)
- TP2: extensión Fibonacci 127.2% sobre el swing bajo-alto del período (objetivo principal)
- TP3: extensión Fibonacci 161.8% o precio objetivo de analistas — PERO NUNCA más del 15% por encima del máximo de 52 semanas
- Relación R/R mínima: 2:1. Si el nivel no da 2:1, NO lo pongas como entrada principal.

RÉGIMEN DE MERCADO (condiciona la fiabilidad de los niveles):
- TENDENCIA ALCISTA (ADX>25, precio>SMA200): en tendencia, los retrocesos a SMA50, VWAP anclado y Fibonacci 38.2%/50% son las mejores entradas. El MACD debe estar por encima de cero (MACD>0) para confirmar la tendencia.
- TENDENCIA BAJISTA (ADX>25, precio<SMA200): los rebotes son débiles; niveles de soporte son menos fiables; gestión conservadora con tamaño de posición reducido. No ir en contra de la tendencia.
- RANGO (ADX<20): las entradas en VAL (Value Area Low) y en los extremos del rango (soporte testado múltiples veces) son las más fiables. MACD en rango suele ser ruido.
- TRANSICIÓN: máxima prudencia, reducir tamaño de posición.
- Menciona siempre el régimen detectado y cómo condiciona el análisis.

OBV (On-Balance Volume):
- OBV en ACUMULACIÓN (subiendo): el dinero inteligente está comprando aunque el precio no lo refleje — señal positiva para la tesis alcista.
- OBV en DISTRIBUCIÓN (bajando): el dinero inteligente está saliendo — reduce confianza en soportes.
- Siempre comenta el OBV en el technical_analysis.

VWAP ANCLADO (soporte dinámico institucional):
- El VWAP anclado desde el mínimo de 52 semanas es el "precio justo promedio" desde ese mínimo.
- Si el precio está por encima del VWAP anclado: alcista; si está por debajo: bajista.
- El VWAP anclado actúa como soporte/resistencia donde las instituciones suelen reentrar.

MACD — regla clave (zero-line gate):
- Solo señal de compra válida cuando el MACD está POR ENCIMA de cero (o cruza hacia arriba de la línea de señal EN territorio positivo).
- MACD cruzando la línea de señal en territorio NEGATIVO = trampa; el precio sigue siendo dominado por vendedores.
- Menciona si el MACD está en territorio positivo o negativo y su implicación.

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

  "business_overview": "Explica en lenguaje LLANO (para alguien que no conoce la empresa) QUÉ HACE y de qué gana dinero: sus productos/servicios principales, su modelo de negocio y qué la diferencia de su competencia. 3-5 frases. Usa la 'descripcion_negocio' del perfil_empresa si está disponible; si no, tu conocimiento. Concreto, sin marketing vacío.",

  "investment_case": "El argumento DECISIVO de por qué invertir en ESTA empresa AHORA y no en otra: la combinación concreta (crecimiento + valoración + momento técnico + catalizador) que la hace una oportunidad hoy. 2-4 frases directas, como si se lo explicaras a un amigo que pregunta '¿por qué esta?'. Si la recomendación NO es COMPRAR, explica honestamente por qué esperar.",

  "entry_zones": [
    {"label": "NIVEL 1 — Zona Óptima", "min": número, "max": número, "comment": "Explica confluencia, régimen de mercado y por qué el ATR valida la distancia al stop"},
    {"label": "NIVEL 2 — Segunda Entrada", "min": número, "max": número, "comment": "Siguiente soporte fuerte con R/R mínimo 2:1"},
    {"label": "NIVEL 3 — Entrada Agresiva", "min": número, "max": número, "comment": "Zona de soporte estructural profundo, mayor rebote esperado"}
  ],

  "stop_losses": [
    {"label": "STOP AJUSTADO (1.5×ATR)", "price": número, "comment": "1.5×ATR bajo la entrada NIVEL 1 — para swing traders"},
    {"label": "STOP ESTÁNDAR (2×ATR)", "price": número, "comment": "2×ATR — nivel que invalida la tesis técnica si se pierde"},
    {"label": "STOP AMPLIO (3×ATR)", "price": número, "comment": "3×ATR — bajo soporte estructural, solo para largo plazo"}
  ],

  "take_profits": [
    {"label": "TP1 — Fibonacci 100% / Resistencia Cercana", "price": número, "comment": "Primera resistencia clave con R/R mínimo 2:1"},
    {"label": "TP2 — Fibonacci 127.2%", "price": número, "comment": "Extensión Fibonacci principal — objetivo de medio plazo"},
    {"label": "TP3 — Fibonacci 161.8% / Analistas", "price": número, "comment": "Objetivo ambicioso — no más de 15% sobre máximo 52s"}
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

  "technical_analysis": "Análisis detallado en 5-7 frases: (1) RSI nivel exacto e interpretación. (2) MACD — ¿está en territorio positivo o negativo? ¿Ha cruzado la línea de señal? (3) Medias móviles SMA20/50/200 y relación con precio. (4) Bollinger Bands — ¿está cerca del borde? (5) OBV — ¿acumulación o distribución? (6) Régimen de mercado detectado (ADX, trending/ranging) y cómo condiciona el análisis. (7) Volumen y VWAP anclado.",

  "fibonacci_analysis": "Explica los niveles Fibonacci clave detectados (retrocesos y extensiones). ¿Cuál coincide con HVN del Volume Profile? ¿Cuál da el mejor R/R? ¿Qué extensión Fibonacci se usa para los TPs?",

  "pattern_analysis": "Patrones chartistas identificados (doble suelo, cabeza-hombros, triángulos, etc.) y su implicación. Si el régimen es rango, menciona los límites del rango.",

  "fundamentals_view": "Comentario sobre P/E vs sector, crecimiento de ingresos, márgenes, deuda. ¿Está barata o cara la acción en términos fundamentales?",

  "insider_view": "Si hay datos de insider_trading_directivos: interpreta si los directivos compran o venden y qué implica. Si no hay datos, devuelve cadena vacía.",

  "earnings_view": "Si hay datos de historial_resultados_earnings: comenta si la empresa suele batir o fallar estimaciones (beat_rate) y qué implica para la fiabilidad. Si no hay datos, devuelve cadena vacía.",

  "price_prediction": {
    "target_3m": número,
    "target_6m": número,
    "target_12m": número,
    "confidence": número 0-100,
    "rationale": "Ancla la estimación en: (1) régimen de mercado actual, (2) VWAP anclado como soporte/resistencia dinámico, (3) extensión Fibonacci del swing, (4) precio objetivo de analistas. No inventes cifras disparatadas."
  },

  "earnings_prediction": {
    "will_beat": "SÍ" | "NO" | "INCIERTO",
    "confidence": número 0-100,
    "rationale": "Basándote en el beat_rate histórico y la tendencia de resultados, ¿batirá las próximas estimaciones? Si no hay datos de earnings, devuelve INCIERTO."
  },

  "competitive_position": "Posición competitiva de la empresa: ¿es la líder (#1) de su sector? ¿En qué sub-sectores compite y con qué cuota aproximada de mercado? Usa tu conocimiento de la empresa.",

  "main_rival": "El competidor que supone la mayor amenaza estructural y por qué (1-2 frases).",

  "sector_outlook": "Potencial del sector a 3-5 años: catalizadores estructurales, tendencias de fondo y vientos de cola o de cara.",

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
1. **Volume Profile (prioridad máxima)**: El POC es el soporte/resistencia más fuerte. Las HVN son zonas donde el precio rebota.
2. **VWAP anclado**: Soporte dinámico institucional. Si el precio está cayendo hacia el VWAP anclado, es una zona de entrada de alta probabilidad para traders profesionales.
3. **Fibonacci**: Los retrocesos 38.2%, 50%, 61.8% que coincidan con HVN del Volume Profile son niveles de confluencia EXTREMADAMENTE fiables.
4. **Soportes técnicos**: Pivots históricos, Camarilla S3/S4, mínimos de 52 semanas.

REGLA DE ORO: Un nivel es fuerte cuando coinciden 2+ fuentes. Un nivel de confluencia EXTREMA (3+ fuentes: Fibonacci + HVN + VWAP anclado + soporte histórico) es uno de los mejores puntos de entrada posibles — como los que usan las mejores mesas de hedge funds del mundo.

NIVELES DE ENTRADA (deben ESCALONARSE en profundidad):
- NIVEL 1: Zona más cercana con confluencia y R/R ≥ 2:1 (típicamente -1% a -5%)
- NIVEL 2: Siguiente soporte fuerte (típicamente -8% a -15%)
- NIVEL 3 (ENTRADA AGRESIVA): Cerca del VAL o HVN más profunda. Escenario de corrección fuerte. DEBE estar bastante por debajo (-15% a -30%). NUNCA pegado al precio.

STOPS: Usa siempre ATR. Por debajo de LVN o VAL, el precio cae rápido — pon el stop después de esa zona de baja liquidez.
TP1: resistencia más cercana o 100% del swing
TP2: extensión Fibonacci 127.2%
TP3: extensión Fibonacci 161.8% o precio objetivo analistas (máximo: máximo 52 semanas + 15%)

SEÑALES ADICIONALES:
- **Insider trading**: Si los directivos COMPRAN: señal alcista muy fiable. Si VENDEN masivamente: precaución.
- **Earnings history**: Un beat_rate alto (>75%) añade confianza en la tesis alcista.
- **Proximidad de resultados (dias_hasta_resultados)**: Si faltan ≤7 días para los próximos resultados, ADVIÉRTELO en el summary y en risks: es un RIESGO BINARIO (la acción puede saltar ±10% de golpe). Recomienda esperar al post-earnings o reducir la entrada inicial y reservar pólvora. Si faltan muchas semanas o no hay dato, no es factor.

IMPORTANTE: Si la acción está en tendencia BAJISTA en el CORTO plazo pero los fundamentales son sólidos y los soportes estructurales se acercan, recomienda COMPRAR por tramos en los niveles de soporte. No confundas tendencia de corto plazo con oportunidad de medio plazo.
"""


def _build_payload(quote: dict, indicators: dict, news: list,
                   analyst_consensus: dict = None, price_target: dict = None,
                   volume_profile: dict = None, insider: dict = None,
                   earnings_history: dict = None, buy_levels: list = None,
                   next_earnings_date: str = None, days_to_earnings: int = None,
                   company_profile: dict = None) -> str:
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

    # Perfil real de la empresa (FMP): descripción del negocio y productos. Se recorta
    # para no inflar tokens. Ancla el "qué hace / qué vende" en datos, no en memoria.
    perfil = None
    if company_profile:
        desc = (company_profile.get("descripcion") or "")[:1200] or None
        perfil = {
            "descripcion_negocio": desc,
            "ceo": company_profile.get("ceo"),
            "empleados": company_profile.get("empleados"),
            "pais": company_profile.get("pais"),
        }

    payload = {
        "symbol": quote.get("symbol"),
        "precio_actual": price,
        "nombre_empresa": quote.get("name"),
        "sector": quote.get("sector"),
        "industria": quote.get("industry"),
        "perfil_empresa": perfil,
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
        "macd": {
            **(ind.get("macd") or {}),
            "en_territorio_positivo": (ind.get("macd") or {}).get("macd") is not None and (ind.get("macd") or {}).get("macd", 0) > 0,
        },
        "bollinger": ind.get("bollinger"),
        "atr": ind.get("atr"),
        "atr_pct": ind.get("atr_pct"),
        "adx": ind.get("adx"),
        "regimen_mercado": (ind.get("regime") or {}).get("regime"),
        "regimen_trending": (ind.get("regime") or {}).get("trending"),
        "vwap_anclado": ind.get("vwap_anchored"),
        "obv_tendencia": ind.get("obv_trend"),
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
        "proxima_fecha_resultados": next_earnings_date,
        "dias_hasta_resultados": days_to_earnings,
        "patrones_tecnicos_detectados": ind.get("patterns", []),
        "noticias_recientes": [n.get("title") for n in (news or [])][:6],
        "volume_profile": {
            "POC": (volume_profile or {}).get("poc"),
            "VAH": (volume_profile or {}).get("vah"),
            "VAL": (volume_profile or {}).get("val"),
            "HVN": (volume_profile or {}).get("hvn", []),
            "LVN": (volume_profile or {}).get("lvn", []),
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
                    "fuerza": z.get("strength"),
                    "dist_pct": z.get("distance_pct"),
                    "confluencia": z.get("reasons"),
                }
                for z in buy_levels
            ], ensure_ascii=False, separators=(',', ':'))
            + "\n\nINSTRUCCIÓN: respeta estos precios/zonas para las entradas (no los inventes "
            "de nuevo). En el comment de cada entry_zone EXPLICA la confluencia indicada. "
            "Si necesitas una entrada más profunda que las dadas, puedes añadirla, pero las "
            "calculadas son la referencia principal."
        )

    return (
        f"Analiza en profundidad la acción {quote.get('symbol')} con precio actual ${price}.\n\n"
        f"DATOS:\n{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
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
    raise RuntimeError(
        "La respuesta del modelo se cortó a mitad (límite de tokens alcanzado). "
        "Intenta otra vez — normalmente funciona al segundo intento."
    )


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
    config_kwargs = dict(
        system_instruction=system_prompt,
        temperature=0.3,
        max_output_tokens=max_tokens,
        response_mime_type="application/json",
    )
    # Gemini 2.5 Flash gasta tokens en "thinking" interno ANTES de escribir. Por defecto
    # ese presupuesto es DINÁMICO (ilimitado) y se comía todo el espacio, truncando el
    # JSON a mitad. Lo ACOTAMOS a min(2048, max_tokens//2) para garantizar que queda al
    # menos la mitad del presupuesto para la respuesta. Para análisis completo (8000) esto
    # da 2048; para el daily-move (2000) da 1000. Try/except por compatibilidad del SDK.
    try:
        budget = min(2048, max_tokens // 2)
        config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=budget)
    except Exception:
        pass
    config = genai_types.GenerateContentConfig(**config_kwargs)
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


_RESEARCH_PROMPT = """Eres un analista financiero senior. Investiga en internet (usa la búsqueda)
la acción {symbol} ({name}) y escribe un informe BREVE y accionable en ESPAÑOL. Ya sabemos que
destaca por estas señales cuantitativas: {catalysts}. Tu trabajo es FUNDAMENTAR o MATIZAR eso
con lo que encuentres hoy en la web.

Estructura EXACTA (texto plano, sin markdown, secciones separadas por saltos de línea):

QUÉ HACE: 1-2 frases sobre el negocio y de qué gana dinero.
POR QUÉ AHORA: 2-3 frases con el catalizador o tesis reciente (noticias, resultados, contratos,
producto). Cita hechos concretos y fechas si los encuentras.
RIESGOS: 1-2 riesgos reales y concretos.
VEREDICTO: una frase — ¿es una oportunidad sólida a medio plazo o hay que esperar? Sé honesto.

Sé concreto y basado en hechos reales que encuentres. Si no encuentras nada relevante reciente,
dilo claramente en POR QUÉ AHORA en vez de inventar."""


async def research_stock_web(symbol: str, name: str = "", catalysts: str = "") -> str:
    """Investigación web profunda de una acción con Gemini + búsqueda de Google (grounding).
    Devuelve un informe en texto (qué hace, por qué ahora, riesgos, veredicto) fundamentado
    en resultados de búsqueda reales. Best-effort: lanza si falla para que el llamador degrade."""
    if not GEMINI_AVAILABLE:
        raise RuntimeError("google-genai no instalada.")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY no configurada.")
    client = genai.Client(api_key=api_key)
    # Herramienta de búsqueda de Google: permite a Gemini consultar la web en tiempo real.
    tools = [genai_types.Tool(google_search=genai_types.GoogleSearch())]
    config = genai_types.GenerateContentConfig(
        tools=tools,
        temperature=0.3,
        max_output_tokens=1200,
    )
    prompt = _RESEARCH_PROMPT.format(
        symbol=symbol, name=name or symbol, catalysts=catalysts or "señales técnicas positivas")
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )
    text = getattr(response, "text", "") or ""
    if not text:
        raise RuntimeError("Gemini no devolvió texto en la investigación web.")
    return text.strip()


_RESEARCH_NEWS_PROMPT = """Eres un analista financiero senior. A partir de las NOTICIAS RECIENTES
que te doy sobre {symbol} ({name}), escribe un informe BREVE y accionable en ESPAÑOL. Ya sabemos
que destaca por: {catalysts}.

Devuelve SOLO un JSON válido con un único campo "informe" (texto plano, sin markdown), con esta
estructura dentro del texto (secciones separadas por saltos de línea):
QUÉ HACE: 1-2 frases del negocio.
POR QUÉ AHORA: 2-3 frases con el catalizador reciente basándote en las noticias. Cita hechos.
RIESGOS: 1-2 riesgos concretos.
VEREDICTO: una frase honesta — oportunidad sólida o esperar.

Si las noticias no aportan nada relevante, dilo en POR QUÉ AHORA en vez de inventar.
{"informe": "..."}"""


async def _research_from_news(symbol: str, name: str, catalysts: str) -> str:
    """Fallback SIN Gemini: resume con Groq las noticias que ya descargamos (FMP/Finnhub).
    No navega la web, pero fundamenta con noticias reales y recientes. Groq casi nunca falla."""
    import market_data
    news = await asyncio.to_thread(market_data.get_news, symbol, 6)
    items = []
    for n in (news or [])[:6]:
        title = n.get("title")
        if not title:
            continue
        summary = (n.get("summary") or "")[:300]
        items.append(f"- {title}" + (f" — {summary}" if summary else ""))
    if not items:
        raise RuntimeError("sin noticias para fundamentar la investigación")
    prompt = _RESEARCH_NEWS_PROMPT.format(symbol=symbol, name=name or symbol,
                                          catalysts=catalysts or "señales técnicas positivas")
    user_msg = prompt + "\n\nNOTICIAS RECIENTES:\n" + "\n".join(items)
    data = await _run_model("gpt-oss-120b", "Eres un analista financiero senior.", user_msg, max_tokens=1200)
    informe = (data or {}).get("informe") if isinstance(data, dict) else None
    if not informe:
        raise RuntimeError("Groq no devolvió informe")
    return informe.strip()


async def research_stock(symbol: str, name: str = "", catalysts: str = "") -> tuple:
    """Investigación robusta con CADENA DE RESPALDO. Devuelve (informe, fuente):
      1) Gemini + búsqueda web (mejor)  -> fuente 'web'
      2) Groq sobre noticias reales     -> fuente 'noticias'
      3) titulares en crudo             -> fuente 'titulares'
    Así la investigación casi nunca falla aunque Gemini esté sin cuota."""
    try:
        return await research_stock_web(symbol, name, catalysts), "web"
    except Exception:
        pass
    try:
        return await _research_from_news(symbol, name, catalysts), "noticias"
    except Exception:
        pass
    # Último recurso: titulares recientes sin procesar.
    try:
        import market_data
        news = await asyncio.to_thread(market_data.get_news, symbol, 5)
        titulares = [f"• {n.get('title')}" for n in (news or []) if n.get("title")][:5]
        if titulares:
            return "NOTICIAS RECIENTES:\n" + "\n".join(titulares), "titulares"
    except Exception:
        pass
    return "", "ninguna"


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
        # Groq free tier: 8000 TPM (input + output combined, max_tokens cuenta como
        # "requested"). Input real ≈ 3700-4300 tokens (prompt + payload compacto), así
        # que 3000 de salida deja margen (~7300) y permite el JSON completo sin truncar.
        return await _analyze_with_groq(model_id, user_msg, system_prompt, min(max_tokens, 3000))
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
    next_earnings_date: str = None,
    days_to_earnings: int = None,
    company_profile: dict = None,
) -> dict:
    user_msg = _build_payload(quote, indicators, news, analyst_consensus, price_target,
                              volume_profile, insider, earnings_history, buy_levels,
                              next_earnings_date, days_to_earnings, company_profile)
    # Inyecta el conocimiento acumulado de las newsletters (cerebro que crece con cada
    # correo), SELECCIONADO por relevancia al sector/situación de esta acción.
    system = SYSTEM_PROMPT
    try:
        import knowledge_base
        prof = company_profile or {}
        ctx = " ".join(str(x) for x in (
            quote.get("name") or quote.get("symbol") or "",
            prof.get("sector") or "", prof.get("industry") or prof.get("finnhubIndustry") or "",
            (indicators or {}).get("trend") or "",
            "sobrecompra" if (indicators or {}).get("rsi", 50) > 70 else
            "sobreventa" if (indicators or {}).get("rsi", 50) < 30 else "",
        ) if x)
        system = SYSTEM_PROMPT + knowledge_base.digest_for_prompt(ctx)
    except Exception:
        pass
    return await _run_model(model_key, system, user_msg, max_tokens=8000)


# ---------- OCR de tabla de watchlist desde una FOTO (Gemini visión) ----------

_WATCHLIST_OCR_PROMPT = """Eres un extractor de datos. Recibes la FOTO de una tabla de acciones (watchlist)
con niveles de compra y venta. Extrae CADA fila y devuelve SÓLO un JSON válido, sin markdown.

La tabla tiene estas columnas (los nombres pueden variar un poco):
- "Acción" = nombre de la empresa (ej: ORACLE)
- "Mercado" = bolsa (NYSE, NASDAQ, EPA...)
- "Ticker/ISIN" = el SÍMBOLO (ej: ORCL) — ESTE es el identificador, no el nombre
- "Precio actual" = ignóralo
- "Nivel deseado venta" = precio objetivo de VENTA
- "Nivel 1..4" = precios de COMPRA (zonas de acumulación)
- "Nivel 5 extra" = compra extra; si pone "NO" o está vacío, devuélvelo como null
- "Riesgo" = texto (ALTO/MEDIO/BAJO...) si existe la columna
- "Sector" = texto si existe la columna
- "Posibles Ganancias" = porcentaje como número (ej "78,28%" → 78.28) si existe la columna

REGLAS:
- Devuelve los números como número (punto decimal). "228,9" → 228.9. Celda vacía o "NO" → null.
- El "symbol" SIEMPRE de la columna Ticker/ISIN, en mayúsculas. Si una fila no tiene símbolo claro, omítela.
- No inventes filas ni valores. Si no ves un nivel, ponlo a null.
- Ignora filas de cabecera o notas (ej "ACCIONES EN CARTERA", "En azul significa comprada").

FORMATO EXACTO:
{
  "rows": [
    {"symbol": "ORCL", "name": "ORACLE", "mercado": "NYSE", "deseado": 250,
     "nivel1": 220, "nivel2": 180, "nivel3": 160, "nivel4": 149, "nivel5": 132,
     "riesgo": "MEDIO", "sector": "TECH", "posibles_ganancias": 78.28}
  ]
}
"""


async def extract_watchlist_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> list:
    """Lee una FOTO de la tabla de watchlist con Gemini visión y devuelve la lista de filas
    normalizadas (mismo formato que el parser de Excel) para pasársela a bulk_upsert.
    Solo Gemini soporta visión aquí; si falla o no hay clave, lanza para que el endpoint avise."""
    if not GEMINI_AVAILABLE:
        raise RuntimeError("google-genai no está instalada en el servidor.")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY no configurada — necesaria para leer la foto.")
    client = genai.Client(api_key=api_key)
    config = genai_types.GenerateContentConfig(
        temperature=0.0,
        max_output_tokens=8000,
        response_mime_type="application/json",
    )
    image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash",
        contents=[image_part, _WATCHLIST_OCR_PROMPT],
        config=config,
    )
    text = getattr(response, "text", "") or ""
    if not text:
        raise RuntimeError("Gemini no devolvió texto al leer la foto.")
    data = _parse_model_json(text)
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("No se pudo interpretar la tabla de la foto.")
    # Normaliza: symbol en mayúsculas, niveles numéricos o None, y descarta filas sin símbolo.
    out = []
    for r in rows:
        sym = (r.get("symbol") or "").strip().upper()
        if not sym or len(sym) > 10:
            continue
        def _num(k):
            v = r.get(k)
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None
        out.append({
            "symbol": sym,
            "name": (r.get("name") or "").strip(),
            "mercado": (r.get("mercado") or "").strip().upper(),
            "deseado": _num("deseado"),
            "nivel1": _num("nivel1"),
            "nivel2": _num("nivel2"),
            "nivel3": _num("nivel3"),
            "nivel4": _num("nivel4"),
            "nivel5": _num("nivel5"),
            "riesgo": (r.get("riesgo") or "").strip().upper(),
            "sector": (r.get("sector") or "").strip(),
            "posibles_ganancias": _num("posibles_ganancias"),
        })
    return out


# ---------- Análisis de vídeo de YouTube (Gemini lo "ve" nativamente) ----------

_YT_PROMPT = """Eres un analista financiero senior. Estás VIENDO un vídeo de bolsa de YouTube.
Extrae TODO lo útil y devuelve SOLO un JSON válido (sin markdown) con esta estructura EXACTA:
{
  "titulo": "tema principal del vídeo en 1 frase",
  "resumen": "4-6 frases con lo MÁS importante que dice el vídeo, en español claro",
  "acciones": [
    {"ticker": "AAPL", "nombre": "Apple",
     "accion": "COMPRAR|VENDER|VIGILAR|MANTENER|MENCIONADA",
     "sentimiento": "POSITIVO|NEGATIVO|NEUTRAL",
     "niveles": "precios/zonas que menciona o null",
     "motivo": "la tesis o ángulo sobre esa acción, 1 frase"}
  ],
  "ideas_clave": ["idea o consejo relevante 1", "idea 2"],
  "aprendizajes": [
    {"tema": "...", "categoria": "selección|valoración|riesgo|psicología|macro|método|sectores",
     "principio": "regla/método GENERAL reutilizable en 1 frase (no sobre un ticker concreto)",
     "detalle": "cómo aplicarlo o null"}
  ]
}
Deduce el ticker del nombre si hace falta. No inventes niveles que no se digan. Si el vídeo no
habla de acciones, deja "acciones" vacío pero rellena resumen y aprendizajes si enseña método.

MUY IMPORTANTE con "aprendizajes": si es un vídeo EDUCATIVO / clase de método (cómo elegir
acciones, cómo entrar, gestión de riesgo, patrones, position sizing, psicología...), NO te quedes
en 1. Extrae CADA regla o principio distinto que enseñe, como aprendizajes SEPARADOS — normalmente
5 a 10 en una clase densa. Cada patrón (VCP, caja de Darvas, copa y asa, bandera...), cada regla de
stop, cada criterio de selección, cada regla de sizing o de venta = un aprendizaje propio, general
y reutilizable. Exprime el método al máximo; es lo más valioso del vídeo."""


async def analyze_youtube(url: str) -> dict:
    """Analiza un vídeo de YouTube pasándoselo DIRECTAMENTE a Gemini (que lo ve nativamente,
    sin descargarlo). Devuelve el dict extraído (titulo, resumen, acciones, aprendizajes)."""
    if not GEMINI_AVAILABLE:
        raise RuntimeError("google-genai no está instalada en el servidor.")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY no configurada — necesaria para leer el vídeo.")
    client = genai.Client(api_key=api_key)
    video_part = genai_types.Part(file_data=genai_types.FileData(file_uri=url))
    cfg_kwargs = dict(temperature=0.2, max_output_tokens=6000,
                      response_mime_type="application/json")
    # Baja resolución de vídeo: en una clase hablada lo valioso es el AUDIO, no los
    # fotogramas en HD. Reduce muchísimo los tokens y evita el límite (vídeos largos ~1h).
    try:
        cfg_kwargs["media_resolution"] = genai_types.MediaResolution.MEDIA_RESOLUTION_LOW
    except Exception:
        pass
    config = genai_types.GenerateContentConfig(**cfg_kwargs)
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash",
        contents=[video_part, _YT_PROMPT],
        config=config,
    )
    text = getattr(response, "text", "") or ""
    if not text:
        raise RuntimeError("Gemini no devolvió nada al ver el vídeo.")
    return _parse_model_json(text)


# ---------- Transcripción de audio (Groq Whisper, gratis) y visión de imágenes ----------

async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg",
                           language: str = "es") -> str:
    """Transcribe una nota de voz / audio con Groq Whisper (capa gratuita). Devuelve el
    texto, o '' si falla o no hay clave. Usado para leer los audios de Telegram."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or not audio_bytes:
        return ""
    try:
        client = AsyncGroq(api_key=api_key)
        resp = await client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model="whisper-large-v3-turbo",
            language=language,
            temperature=0.0,
        )
        return (getattr(resp, "text", "") or "").strip()
    except Exception:
        logger.warning("transcripción de audio falló")
        return ""


_IMAGE_PROMPT = """Eres un analista. Recibes una imagen de un chat de trading. Extrae TODO el
texto legible y, si es un gráfico de bolsa, describe lo relevante: ticker/activo, precios y
niveles visibles, patrón o setup, y la idea que transmite. Devuelve TEXTO PLANO claro en español
(sin markdown). Si la imagen no tiene nada útil para inversión, responde solo 'SIN CONTENIDO'."""


async def describe_image_text(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Extrae el texto y describe el contenido de una imagen (gráficos, capturas) con Gemini
    visión. Devuelve texto plano, o '' si falla / no hay clave / no aporta nada."""
    if not GEMINI_AVAILABLE or not image_bytes:
        return ""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""
    try:
        client = genai.Client(api_key=api_key)
        image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=[image_part, _IMAGE_PROMPT],
        )
        text = (getattr(response, "text", "") or "").strip()
        return "" if text.upper().startswith("SIN CONTENIDO") else text
    except Exception:
        logger.warning("descripción de imagen falló")
        return ""


# ---------- "¿Por qué se mueve hoy?" — explicación ligera del movimiento diario ----------

DAILY_MOVE_PROMPT = """Eres un analista de mercado que explica, en lenguaje claro y directo, POR QUÉ una acción se mueve HOY.
Recibes el precio, el cambio del día y los titulares de noticias recientes. Tu trabajo es conectar el movimiento con sus causas probables.

REGLAS ESTRICTAS:
- Responde SIEMPRE en español, tono cercano pero riguroso.
- Devuelve ÚNICAMENTE un objeto JSON válido (sin markdown, sin texto extra).
- Básate en las noticias proporcionadas. Si NINGUNA noticia explica el movimiento, dilo con honestidad y baja la fiabilidad — NO inventes catalizadores.
- Distingue entre causa específica de la empresa (resultados, upgrade, producto) y arrastre del mercado/sector (macro, tipos, todo el sector cae).
- SÉ CONCRETO: si el "resumen" de una noticia nombra el hecho exacto (una PERSONA, una cifra, un producto, una demanda), CÍTALO por su nombre. Ejemplo: NO digas "éxodo de talento en IA"; di "el científico jefe de IA John Jumper deja DeepMind por Anthropic". El titular generaliza; el resumen tiene el detalle — usa el detalle.

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


def _news_to_datetime(published):
    """Normaliza la fecha de una noticia (epoch o ISO) a datetime UTC, o None."""
    if published is None:
        return None
    from datetime import datetime, timezone
    try:
        if isinstance(published, (int, float)):
            return datetime.fromtimestamp(float(published), tz=timezone.utc)
        return datetime.fromisoformat(str(published).replace("Z", "+00:00"))
    except Exception:
        return None


def _news_date_str(published) -> str:
    dt = _news_to_datetime(published)
    return dt.strftime("%Y-%m-%d") if dt else "fecha desconocida"


def _is_today(published) -> bool:
    from datetime import datetime, timezone
    dt = _news_to_datetime(published)
    return bool(dt and dt.date() == datetime.now(timezone.utc).date())


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
            {
                "titular": n.get("title"),
                # El resumen suele nombrar el catalizador concreto (persona, cifra,
                # producto) que el titular generaliza. Lo recortamos para no inflar tokens.
                "resumen": (n.get("summary") or "")[:400] or None,
                "fuente": n.get("publisher"),
                "fecha": _news_date_str(n.get("published")),
                "es_de_hoy": _is_today(n.get("published")),
            }
            for n in (news or [])
        ][:8],
    }
    return (
        f"Explica por qué {quote.get('symbol')} se mueve hoy "
        f"({'+' if (chg_pct or 0) >= 0 else ''}{chg_pct}%).\n\n"
        f"DATOS:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        f"PRIORIZA las noticias con \"es_de_hoy\": true — son las que explican el "
        f"movimiento de hoy. Las antiguas son solo contexto.\n"
        f"Responde SOLO con el JSON pedido."
    )


async def explain_daily_move(quote: dict, news: list,
                             model_key: str = DEFAULT_MODEL) -> dict:
    """Lightweight, cheap explainer for the daily price move. Uses a small prompt
    (~600 input tokens) so it costs a fraction of a full analysis."""
    user_msg = _build_daily_move_payload(quote, news)
    return await _run_model(model_key, DAILY_MOVE_PROMPT, user_msg, max_tokens=2000)
