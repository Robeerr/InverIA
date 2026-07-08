"""Capa 3 — Ingesta de newsletters premium.

El usuario se suscribe (con su tarjeta) a una newsletter de pago y reenvía esos correos
a un buzón que POSTea aquí. Este módulo LEE el correo, extrae con IA lo accionable
(acciones recomendadas, dirección compra/venta, niveles, tesis, lo importante) y le
reenvía al usuario un RESUMEN destilado a su email — para que no tenga que leer nada.

Legal: solo procesamos correos que el propio usuario recibe y reenvía (contenido al que
está suscrito legítimamente). No rascamos webs de pago.
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger("inveria.newsletter")

try:
    import resend
except ImportError:
    resend = None


_EXTRACT_PROMPT = """Eres un analista financiero senior. Te doy el TEXTO de una newsletter de bolsa
a la que el usuario está suscrito (puede ser una lista de titulares de artículos, un resumen de
mercado, o análisis). Extrae la MÁXIMA información útil y devuelve un JSON válido (sin markdown).

Estructura EXACTA:
{
  "titulo": "título o tema principal de la newsletter (1 frase)",
  "resumen": "3-5 frases con lo MÁS importante que dice, en español claro",
  "acciones": [
    {"ticker": "AAPL", "nombre": "Apple",
     "accion": "COMPRAR|VENDER|VIGILAR|MANTENER|MENCIONADA",
     "sentimiento": "POSITIVO|NEGATIVO|NEUTRAL",
     "niveles": "precios/zonas que menciona si los hay, o null",
     "motivo": "el ángulo/tesis del artículo o mención, 1 frase (traduce al español)"}
  ],
  "ideas_clave": ["idea o consejo relevante 1", "idea 2"],
  "aprendizajes": [
    {"tema": "Rotación de sectores",
     "categoria": "selección|valoración|riesgo|psicología|macro|método|sectores",
     "principio": "regla/método GENERAL y reutilizable en 1 frase (NO sobre un ticker concreto)",
     "detalle": "matiz o cómo aplicarlo, 1 frase, o null"}
  ]
}

REGLAS IMPORTANTES:
- Extrae TODAS las acciones que aparezcan, AUNQUE sean solo titulares de artículos o menciones
  (no solo recomendaciones explícitas). Si un titular habla de una empresa, inclúyela con
  accion="MENCIONADA" y el ángulo en "motivo".
- MUCHAS newsletters son LISTAS de titulares de artículos con el ticker pegado al autor. Ejemplo
  (formato Seeking Alpha "Stock Ideas" / "Tech Daily"):
    "Lumentum: The Pullback Before The Breakout — Pythia Research • LITE
     Netflix: Forget Subscriber Growth, AI Is The New Narrative — Ryan Canady • NFLX
     MercadoLibre: Scaling Ahead Of A Rotation Trade — Gary Alexander • MELI
     Navitas: Too Cheap To Ignore Anymore — By Uttam Dey"
  → De AHÍ debes extraer TODAS: LITE (Lumentum), NFLX (Netflix), MELI (MercadoLibre),
    NVTS (Navitas)... El ticker suele venir tras "•"; si no, dedúcelo del nombre de la empresa
    del titular. El "motivo" es el ángulo del titular traducido al español.
- ALGUNAS newsletters son de ANÁLISIS NARRATIVO (prosa), no listas. La empresa se menciona
  dentro del texto, a veces solo por su nombre en negrita. DEBES extraerla igual. Ejemplo:
    "🚨 EN VIGILANCIA: Rotación, JFROG y +
     ...el sector de software que se beneficia de la IA. ¿Un claro ejemplo? JFrog. JFrog se
     dedica a gestionar y proteger código..."
  → De AHÍ extrae JFrog con ticker FROG, accion="VIGILAR", motivo="Software que se beneficia
    de la IA; más código generado por agentes = más demanda de gestión/seguridad".
- SECCIONES DE VIGILANCIA / WATCHLIST: si el texto tiene un apartado tipo "EN VIGILANCIA",
  "En el radar", "Vigilando", "Watchlist", "Seguimiento", TODAS las empresas nombradas ahí son
  accion="VIGILAR" (el autor las está siguiendo para entrar/salir). Es la información MÁS
  importante de una newsletter premium: no te dejes ninguna, aunque solo se cite el nombre.
- Deduce el ticker del nombre si no viene explícito (Micron→MU, Adobe→ADBE, Intel→INTC,
  Affirm→AFRM, Palantir→PLTR, JFrog→FROG, Datadog→DDOG, CrowdStrike→CRWD, Snowflake→SNOW,
  MongoDB→MDB, Cloudflare→NET, ServiceNow→NOW, Nvidia→NVDA). Si de verdad no sabes el ticker,
  omite esa acción.
- Ignora publicidad: "Subscribe", "Register Now", "Featured", "Darse de baja", "Top Stocks H2".
- NO incluyas empresas que aparecen SOLO como PATROCINADOR o ANUNCIO del newsletter. Casi todos
  los boletines llevan un bloque publicitario pagado por una marca (ej. "Oracle NetSuite",
  "Brought to you by...", "Sponsored by...", "Patrocinado por...", "Together with...",
  "This is a paid advertisement", un producto B2B con CTA tipo "download the guide / KPI checklist /
  book a demo / free report"). Eso NO es una idea de inversión: es publicidad. NO lo pongas en
  "acciones" aunque se mencione un nombre de empresa cotizada. Solo incluye una empresa si el
  contenido EDITORIAL (un titular, análisis o comentario de mercado) habla de ella como oportunidad,
  riesgo o noticia — no si es quien paga el anuncio.
- Ignora el envoltorio de reenvío ("---------- Forwarded message ----------", "From:", "Date:").
- No inventes niveles de precio que no aparezcan. Sé fiel al contenido.
- "aprendizajes": extrae el MÉTODO y la SABIDURÍA de inversión GENERAL que enseña el correo
  (cómo valorar una empresa, cómo detectar buenas oportunidades, cómo gestionar el riesgo,
  cómo leer una rotación de sectores, qué mirar antes de entrar/salir, psicología...). Deben ser
  principios REUTILIZABLES que sigan siendo útiles dentro de un año, NO comentarios sobre un
  ticker concreto ni sobre el mercado de esta semana. Si el correo no enseña método, deja la
  lista vacía. Ejemplos de buen "principio": "El dinero rota del hardware de IA hacia el software
  que se beneficia de la IA", "No comprar en máximos sin stop; limitar cada posición al 5% de la
  cartera", "Una empresa mejora si su producto se vuelve más necesario cuando crece su mercado"."""


# Señales típicas de que una "acción" extraída es en realidad el patrocinador/anuncio
# del newsletter, no una idea editorial. Se usa como red de seguridad tras la extracción IA.
_SPONSOR_RE = re.compile(
    r"(?i)(patrocin|sponsor|brought to you|together with|paid (advert|promotion)|"
    r"anuncio|publicidad|advertisement|book a demo|download the (guide|report|whitepaper)|"
    r"kpi (guide|checklist|gu[íi]a)|free (guide|report|trial)|netsuite)"
)


def _is_sponsor(a: dict) -> bool:
    """True si la acción huele a patrocinador/anuncio (no es una idea de inversión real)."""
    blob = " ".join(str(a.get(k) or "") for k in ("motivo", "nombre", "niveles"))
    return bool(_SPONSOR_RE.search(blob))


# Traza de diagnóstico: guarda el resultado de los últimos procesados en memoria para
# poder inspeccionar por qué no llegó un email sin acceso a los logs de Render.
_LAST_RUNS: list = []


def _trace(**info):
    info["at"] = datetime.now(timezone.utc).isoformat()
    _LAST_RUNS.insert(0, info)
    del _LAST_RUNS[8:]  # conserva solo los 8 más recientes


def _html_to_text(body: str) -> str:
    """Convierte HTML de email a texto plano legible (suficiente para la IA)."""
    if not body:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", body)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


async def _extract(subject: str, text: str) -> dict:
    """Extrae lo accionable con Groq (robusto, sin depender de Gemini). Devuelve dict.

    Los correos PREMIUM de análisis (el Diamante) son largos y en prosa: el JSON de
    salida se puede truncar (Groq gratis capa la salida a ~3000 tokens) y fallar el
    parseo. Por eso reintentamos con el cuerpo cada vez más recortado — así siempre
    sale algo y llega el email, aunque sea con menos detalle."""
    import ai_analysis
    # Recortes decrecientes: primero el correo entero, luego cada vez menos cuerpo para
    # dejar más presupuesto de salida y evitar la truncación del JSON.
    last_err = None
    for cap in (12000, 7000, 4000):
        body = (text or "")[:cap]
        user_msg = f"ASUNTO: {subject}\n\nTEXTO DE LA NEWSLETTER:\n{body}"
        try:
            return await ai_analysis._run_model(
                "gpt-oss-120b", _EXTRACT_PROMPT, user_msg, max_tokens=2800)
        except Exception as e:
            last_err = e
            logger.warning("newsletter: extracción falló con cap=%d (%s), reintento",
                           cap, str(e)[:120])
    raise last_err if last_err else RuntimeError("extracción falló")


async def _score_ticker(symbol: str):
    """Cruza un ticker que menciona la newsletter con TU motor: calcula el score de
    potencial y devuelve un veredicto (verde/amarillo/rojo). Así no te fías de lo que
    diga la newsletter a ciegas, sino de si coincide con tus datos. None si no hay datos."""
    import asyncio
    import external_data
    import market_data
    import opportunities
    try:
        quote = await asyncio.to_thread(market_data.get_quote, symbol)
        if not quote or not quote.get("price"):
            return None
        m = await asyncio.to_thread(external_data.finnhub_basic_financials, symbol) or {}
        trends = await asyncio.to_thread(external_data.finnhub_recommendation_trends, symbol)
        cons = external_data.aggregate_recommendation(trends)
        price = quote.get("price")
        high52 = quote.get("high_52w") or m.get("high_52w")
        dist = ((price - high52) / high52 * 100) if (high52 and price) else None
        pot, val_label, mom_label = opportunities._potential_score(
            m.get("revenue_growth"), m.get("eps_growth"),
            quote.get("pe_ratio") or m.get("pe_ratio"), dist,
            cons.get("score") if cons else None,
            m.get("return_26w"), m.get("return_52w"), m.get("rel_strength_52w"),
        )
        if mom_label.startswith("⚠"):
            verdict = "🔴 Tu motor la EVITA (tendencia bajista / peor que el mercado)"
        elif pot >= 65:
            verdict = "🟢 Coincide con tu motor (score alto)"
        elif pot >= 45:
            verdict = "🟡 Neutral para tu motor"
        else:
            verdict = "🟠 Floja para tu motor (score bajo)"
        return {"score": pot, "valuation": val_label, "momentum": mom_label, "verdict": verdict}
    except Exception:
        return None


def _build_email_html(data: dict, subject: str) -> str:
    acciones = data.get("acciones") or []
    ideas = data.get("ideas_clave") or []
    acc_rows = ""
    color = {"COMPRAR": "#4a7c59", "VENDER": "#d85c41", "VIGILAR": "#c9a14a",
             "MANTENER": "#5c6b66", "MENCIONADA": "#1F6FB5"}
    for a in acciones:
        c = color.get((a.get("accion") or "").upper(), "#5c6b66")
        niveles = f" · Niveles: {a['niveles']}" if a.get("niveles") else ""
        # Sentimiento de la newsletter sobre la empresa (habla bien / mal / neutral).
        sent = (a.get("sentimiento") or "").upper()
        sent_html = ""
        if sent == "POSITIVO":
            sent_html = '<span style="color:#4a7c59;font-size:12px;font-weight:600;"> 👍 la ven bien</span>'
        elif sent == "NEGATIVO":
            sent_html = '<span style="color:#d85c41;font-size:12px;font-weight:600;"> 👎 la ven mal</span>'
        inv = a.get("inveria")
        veredicto_html = ""
        if inv and inv.get("verdict"):
            extra = f" · score {inv.get('score')}" if inv.get("score") is not None else ""
            veredicto_html = (
                f'<p style="margin:6px 0 0 0;font-size:12px;font-weight:600;color:#1a3a32;'
                f'background:#eef2f0;padding:4px 8px;border-radius:4px;display:inline-block;">'
                f'{inv["verdict"]}{extra}</p>'
            )
        acc_rows += f"""
        <div style="border-left:3px solid {c};padding:8px 12px;margin:8px 0;background:#faf9f6;border-radius:4px;">
          <b style="color:#0e1f1a;">{a.get('ticker','')}</b> <span style="color:#5c6b66;">{a.get('nombre','')}</span>
          <span style="color:{c};font-weight:600;font-size:12px;"> · {a.get('accion','')}</span>{sent_html}{niveles}
          <p style="margin:4px 0 0 0;font-size:13px;color:#0e1f1a;">{a.get('motivo','')}</p>
          {veredicto_html}
        </div>"""
    ideas_html = "".join(f'<li style="margin:4px 0;font-size:13px;color:#0e1f1a;">{i}</li>' for i in ideas)
    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#5c6b66;margin:0 0 4px 0;">InverIA · Resumen de newsletter</p>
      <h1 style="font-size:20px;color:#0e1f1a;margin:0 0 12px 0;">📩 {data.get('titulo') or subject}</h1>
      <p style="font-size:14px;color:#0e1f1a;line-height:1.5;">{data.get('resumen','')}</p>
      {'<p style="margin:16px 0 6px 0;font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#1a3a32;">Acciones mencionadas</p>' + acc_rows if acc_rows else ''}
      {'<p style="margin:16px 0 6px 0;font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#1a3a32;">Ideas clave</p><ul style="margin:0;padding-left:18px;">' + ideas_html + '</ul>' if ideas_html else ''}
      <p style="font-size:11px;color:#5c6b66;margin:20px 0 0 0;border-top:1px solid #e5e0d8;padding-top:8px;">
        Resumen automático de una newsletter a la que estás suscrito. Fuente: {subject}. Verifica antes de operar.
      </p>
    </div>"""


async def _send_summary(data: dict, subject: str) -> tuple:
    if resend is None:
        return False, "resend no instalada"
    api_key = os.environ.get("RESEND_API_KEY")
    recipient = os.environ.get("ANALYST_RECIPIENT_EMAIL") or os.environ.get("ALERT_RECIPIENT_EMAIL")
    if not api_key or not recipient:
        return False, "RESEND_API_KEY o destino no configurados"
    resend.api_key = api_key
    sender = os.environ.get("ALERT_FROM_EMAIL") or os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"
    n = len(data.get("acciones") or [])
    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": f"InverIA Newsletter <{sender}>",
            "to": [recipient],
            "subject": f"📩 Resumen newsletter · {data.get('titulo') or subject}"[:120],
            "html": _build_email_html(data, subject),
        })
        return True, None
    except Exception as e:
        return False, str(e)[:200]


async def process_newsletter(db, subject: str, body_html: str, body_text: str = "",
                             sender: str = "") -> dict:
    """Procesa un correo de newsletter entrante: extrae lo accionable, lo guarda y
    reenvía el resumen destilado al usuario. Devuelve el resultado."""
    text = body_text.strip() if body_text and body_text.strip() else _html_to_text(body_html)
    # Repara mojibake del cuerpo (correos que llegan con UTF-8 mal decodificado como CP1252):
    # así la IA recibe texto limpio y todo lo guardado/enviado sale con acentos correctos.
    import knowledge_base
    text = knowledge_base.fix_mojibake(text)
    subject = knowledge_base.fix_mojibake(subject or "")
    if not text or len(text) < 40:
        _trace(subject=subject, sender=sender, stage="body",
               ok=False, error="cuerpo del email vacío o demasiado corto",
               text_len=len(text or ""))
        return {"ok": False, "error": "cuerpo del email vacío o demasiado corto"}
    try:
        data = await _extract(subject, text)
    except Exception as e:
        logger.exception("newsletter: extracción falló")
        _trace(subject=subject, sender=sender, stage="extract", ok=False, error=str(e)[:300])
        return {"ok": False, "error": f"extracción falló: {e}"}

    # CRUCE CON TU MOTOR: cada acción mencionada se pasa por el score + guardián de
    # tendencia, para que sepas si fiarte o no (verde/amarillo/rojo). Acotado a 6 tickers.
    acciones = data.get("acciones") or []
    # Red de seguridad: descarta patrocinadores/anuncios que la IA haya colado como acciones.
    filtradas = [a for a in acciones if not _is_sponsor(a)]
    if len(filtradas) != len(acciones):
        logger.info("newsletter: descartadas %d menciones de patrocinador/anuncio",
                    len(acciones) - len(filtradas))
        acciones = filtradas
        data["acciones"] = acciones
    for a in acciones[:6]:
        ticker = (a.get("ticker") or "").strip().upper()
        if ticker:
            a["inveria"] = await _score_ticker(ticker)

    doc = {
        "subject": subject,
        "sender": sender,
        "extracted": data,
        "raw_text": text[:12000],  # guardado para poder reprocesar aprendizajes en el futuro
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.newsletter_summaries.insert_one({**doc})
    except Exception:
        logger.warning("newsletter: no se pudo guardar en Mongo")

    # Alimenta el cerebro: acumula el MÉTODO/sabiduría que enseña este correo para que
    # el motor de análisis sea cada vez más listo (deduplicado por tema).
    try:
        import knowledge_base
        n_aprend = await knowledge_base.add_learnings(
            db, data.get("aprendizajes") or [], source=subject[:80])
        if n_aprend:
            logger.info("newsletter: +%d aprendizajes al cerebro", n_aprend)
    except Exception:
        logger.warning("newsletter: no se pudieron guardar aprendizajes")

    ok, err = await _send_summary(data, subject)
    _trace(subject=subject, sender=sender, stage="email", ok=ok, error=err,
           acciones=len(data.get("acciones") or []), titulo=data.get("titulo"),
           recipient=(os.environ.get("ANALYST_RECIPIENT_EMAIL")
                      or os.environ.get("ALERT_RECIPIENT_EMAIL") or "(sin destino)"),
           resend=bool(os.environ.get("RESEND_API_KEY")))
    return {"ok": ok, "error": err, "acciones": len(data.get("acciones") or []),
            "titulo": data.get("titulo")}


_LEARN_PROMPT = """Eres un analista financiero senior. Te doy el contenido (o un resumen) de una
newsletter de bolsa. Extrae SOLO el MÉTODO y la SABIDURÍA de inversión GENERAL y reutilizable que
enseña: cómo valorar empresas, cómo encontrar buenas oportunidades, gestión de riesgo, lectura de
rotación de sectores, qué mirar antes de entrar/salir, psicología. NADA sobre un ticker concreto ni
sobre el mercado de esta semana. Devuelve JSON válido (sin markdown):
{"aprendizajes": [{"tema": "...", "categoria": "selección|valoración|riesgo|psicología|macro|método|sectores",
  "principio": "regla general en 1 frase", "detalle": "cómo aplicarlo o null"}]}
Si no enseña método reutilizable, devuelve {"aprendizajes": []}."""


async def _extract_learnings(text: str) -> list:
    import ai_analysis
    data = await ai_analysis._run_model("gpt-oss-120b", _LEARN_PROMPT, text[:12000], max_tokens=1500)
    return (data or {}).get("aprendizajes") or []


async def backfill_knowledge(db, limit: int = 200) -> dict:
    """Reprocesa los correos YA guardados para poblar el cerebro con su método/sabiduría.
    Usa el texto crudo si está guardado; si no (correos antiguos), reconstruye un texto
    a partir de lo extraído (resumen + ideas + motivos). Devuelve un recuento."""
    import knowledge_base
    docs = await db.newsletter_summaries.find({}, {"_id": 0}).sort(
        "received_at", -1).to_list(limit)
    procesados, aprendidos = 0, 0
    for d in docs:
        ex = d.get("extracted") or {}
        raw = d.get("raw_text")
        if raw and len(raw) > 60:
            blob = raw
        else:
            partes = [ex.get("titulo") or d.get("subject") or "", ex.get("resumen") or ""]
            partes += ex.get("ideas_clave") or []
            partes += [a.get("motivo") or "" for a in (ex.get("acciones") or [])]
            blob = "\n".join(p for p in partes if p)
        if len(blob) < 60:
            continue
        try:
            aprend = await _extract_learnings(blob)
            n = await knowledge_base.add_learnings(db, aprend, source=(d.get("subject") or "")[:80])
            aprendidos += n
            procesados += 1
        except Exception:
            logger.warning("backfill: fallo procesando un correo")
    return {"correos_procesados": procesados, "aprendizajes_anadidos": aprendidos}
