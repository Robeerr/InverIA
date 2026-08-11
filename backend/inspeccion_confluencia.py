"""Inspección de la confluencia motor ↔ fuentes. SOLO LECTURA, SOLO MEDIR.

POR QUÉ EXISTE

Antes de decidir qué es «acuerdo alto» entre lo que dicen tus fuentes y lo que dice tu
motor, hay que saber qué distribución producen tus datos reales. Elegir los cortes a ojo
y ajustarlos después es la forma habitual de acabar con un umbral que nadie sabe por qué
está donde está.

Este script NO clasifica nada en producción, NO toca la UI y NO fija ningún umbral: barre
varios cortes candidatos y enseña cuántos casos caería cada uno, con ejemplos concretos
para poder juzgar si la clasificación tiene sentido.

QUÉ GARANTIZA

  - Solo lee. No hay un solo `insert`, `update`, `delete` ni `drop` en todo el fichero.
  - No abre red. No llama a Finnhub ni a `_score_ticker`: el veredicto del motor se lee
    de `acciones[].inveria`, que ya está guardado en cada mención desde la ingesta.
  - No importa nada de la lógica de producción salvo dos ayudantes de lectura, para no
    duplicar reglas que ya existen.

QUÉ NO PUEDE MEDIR, Y CONVIENE SABERLO

El tercer eje de la confluencia —«hay un nivel fuerte cerca»— necesita `buy_levels`, y
eso exige el motor sobre el histórico, o sea red. Queda fuera a propósito: este script
mide los dos ejes que están guardados, consenso de fuentes y veredicto del motor. El
tercero se añade cuando la confluencia se implemente dentro del servidor, donde esos
datos ya están calculados.

USO

    cd backend && python inspeccion_confluencia.py [días]

`días` por defecto 90, para ver una muestra amplia y no solo la última semana.
"""
import asyncio
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# ── Ayudantes de lectura reutilizados de producción ──────────────────────────
# Se importan en vez de copiarse: `_clean_source` resuelve el nombre real del editor
# —sin él, 40 correos de la misma newsletter cuentan como 40 fuentes— y `_is_sponsor`
# descarta los patrocinadores que se cuelan como si fueran ideas de inversión. Duplicar
# cualquiera de las dos aquí seria empezar a tener dos verdades.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import newsletter_ingest  # noqa: E402


def _clean_source_de_server():
    """`_clean_source` vive en server.py. Se importa tarde y con red de seguridad porque
    importar el servidor arrastra FastAPI y sus guardarraíles de arranque."""
    try:
        import server
        return server._clean_source
    except Exception as exc:                                    # pragma: no cover
        print(f"[aviso] no se pudo importar server ({exc}).")
        print("[aviso] las fuentes se contarán por el remitente en bruto, así que el")
        print("[aviso] número de fuentes distintas saldrá INFLADO. Trátalo como techo.")
        return lambda sender, subject: (sender or "?").strip()


# ── Análisis puro: sin Mongo, sin red, testeable ─────────────────────────────

def resumir_por_ticker(docs, limpiar_fuente):
    """De los documentos crudos a un resumen por ticker.

    Cada resumen lleva lo que hace falta para clasificar y nada más: cuántas fuentes
    DISTINTAS lo mencionan, cómo se reparte el sentimiento, y el veredicto del motor tal
    como quedó guardado. No se infiere nada que no esté.
    """
    acumulado = defaultdict(lambda: {
        "ticker": None, "nombre": "", "menciones": 0, "fuentes": set(),
        "positivos": 0, "negativos": 0, "neutros": 0,
        "score": None, "verdict": None, "motivos": [], "ultima": None,
    })

    for d in docs or []:
        d = d or {}
        ex = d.get("extracted") or {}
        fuente = limpiar_fuente(d.get("sender"), d.get("subject"))
        cuando = d.get("received_at")
        for a in (ex.get("acciones") or []):
            tk = (a.get("ticker") or "").strip().upper()
            if not tk:
                continue
            if newsletter_ingest._is_sponsor(a):
                continue
            r = acumulado[tk]
            r["ticker"] = tk
            r["menciones"] += 1
            r["fuentes"].add(fuente)
            sent = (a.get("sentimiento") or "").upper()
            if sent == "POSITIVO":
                r["positivos"] += 1
            elif sent == "NEGATIVO":
                r["negativos"] += 1
            else:
                r["neutros"] += 1
            if not r["nombre"] and a.get("nombre"):
                r["nombre"] = a["nombre"]
            if a.get("motivo"):
                r["motivos"].append(a["motivo"])
            # El veredicto del motor: el primero que aparezca con datos. Es una foto del
            # día en que llegó el correo; el servidor lo refresca en vivo, aquí no.
            inv = a.get("inveria") or {}
            if r["score"] is None and inv.get("score") is not None:
                r["score"] = inv.get("score")
                r["verdict"] = inv.get("verdict")
            if cuando and (r["ultima"] is None or cuando > r["ultima"]):
                r["ultima"] = cuando

    for r in acumulado.values():
        r["n_fuentes"] = len(r["fuentes"])
        r["fuentes"] = sorted(r["fuentes"])
    return dict(acumulado)


def tono_de_fuentes(r):
    """FAVORABLE / DESFAVORABLE / MIXTO / SIN_SENTIDO, mirando solo las menciones.

    MIXTO no es lo mismo que neutro: significa que unas fuentes lo ven bien y otras mal,
    y esa discrepancia es información. Machacarla en un promedio la perdería.
    """
    pos, neg = r["positivos"], r["negativos"]
    if pos and neg:
        return "MIXTO"
    if pos:
        return "FAVORABLE"
    if neg:
        return "DESFAVORABLE"
    return "SIN_SENTIDO"


def clasificar(r, corte):
    """Estado de confluencia de un ticker BAJO UN CORTE CONCRETO.

    `corte` llega como parámetro a propósito: este fichero no decide ningún umbral, solo
    permite comparar candidatos. Los estados son los cuatro acordados.

    LA REGLA QUE NO SE NEGOCIA: sin menciones no hay confluencia. Un ticker que tu motor
    puntúa alto y del que nadie ha hablado NO es un acuerdo, es una idea propia — y
    llamarlo confluencia sería fabricar una coincidencia que no existe.
    """
    if r["menciones"] == 0:
        return "SIN_FUENTES"

    tono = tono_de_fuentes(r)
    score = r["score"]

    # Sin veredicto del motor no se puede cruzar nada: falta una de las dos opiniones.
    if score is None:
        return "INSUFICIENTE"

    fuentes_bastantes = r["n_fuentes"] >= corte["min_fuentes"]
    motor_a_favor = score >= corte["score_alto"]
    motor_en_contra = score < corte["score_bajo"]

    if tono == "FAVORABLE" and fuentes_bastantes and motor_a_favor:
        return "ACUERDO"
    if tono == "FAVORABLE" and motor_en_contra:
        return "CHOQUE"
    if tono == "DESFAVORABLE" and motor_a_favor:
        return "CHOQUE"
    return "NEUTRAL"


# Cortes candidatos. No son propuestas: son sondas para ver cómo se mueve el reparto.
CORTES = [
    {"nombre": "laxo",      "min_fuentes": 1, "score_alto": 55, "score_bajo": 40},
    {"nombre": "medio",     "min_fuentes": 2, "score_alto": 65, "score_bajo": 45},
    {"nombre": "estricto",  "min_fuentes": 3, "score_alto": 70, "score_bajo": 50},
    {"nombre": "muy estricto", "min_fuentes": 3, "score_alto": 75, "score_bajo": 55},
]


def reparto(resumenes, corte):
    return Counter(clasificar(r, corte) for r in resumenes.values())


# ── Presentación ─────────────────────────────────────────────────────────────

def _hist(titulo, contador, total):
    print(f"\n{titulo}")
    print("─" * len(titulo))
    if not contador:
        print("  (nada)")
        return
    ancho = max(len(str(k)) for k in contador)
    for k, n in sorted(contador.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        pct = (n / total * 100) if total else 0
        print(f"  {str(k):<{ancho}}  {n:>4}  {pct:>5.1f}%  {'█' * min(40, n)}")


def _ejemplos(resumenes, corte, estado, cuantos=4):
    ejs = [r for r in resumenes.values() if clasificar(r, corte) == estado]
    ejs.sort(key=lambda r: (-r["n_fuentes"], -(r["score"] or 0)))
    print(f"\n  ── {estado} ({len(ejs)}) ──")
    if not ejs:
        print("     (ninguno)")
        return
    for r in ejs[:cuantos]:
        motivo = (r["motivos"][0][:90] + "…") if r["motivos"] else "—"
        print(f"     {r['ticker']:<6} {r['n_fuentes']} fuentes · "
              f"+{r['positivos']}/-{r['negativos']}/={r['neutros']} · "
              f"motor {r['score']} ({(r['verdict'] or '—')[:34]})")
        print(f"            fuentes: {', '.join(r['fuentes'][:4])}")
        print(f"            «{motivo}»")


def informe(resumenes, dias):
    total = len(resumenes)
    print("=" * 78)
    print(f"CONFLUENCIA MOTOR ↔ FUENTES · inspección de {dias} días")
    print("=" * 78)
    print(f"\nTickers distintos mencionados: {total}")
    print(f"Menciones totales:             {sum(r['menciones'] for r in resumenes.values())}")

    if not total:
        print("\nNo hay menciones en la ventana. Prueba con más días.")
        return

    _hist("1 · Fuentes DISTINTAS por ticker",
          Counter(r["n_fuentes"] for r in resumenes.values()), total)

    con_score = [r for r in resumenes.values() if r["score"] is not None]
    print(f"\n2 · Veredicto del motor")
    print("─" * 24)
    print(f"  con veredicto guardado: {len(con_score)} de {total} "
          f"({len(con_score)/total*100:.0f}%)")
    if con_score:
        tramos = Counter()
        for r in con_score:
            s = r["score"]
            tramos[f"{int(s)//10*10}-{int(s)//10*10+9}"] += 1
        _hist("   reparto del score", tramos, len(con_score))
        _hist("   veredicto literal",
              Counter((r["verdict"] or "—")[:38] for r in con_score), len(con_score))

    _hist("3 · Tono de las fuentes",
          Counter(tono_de_fuentes(r) for r in resumenes.values()), total)

    print("\n4 · Cuántos casos daría cada corte")
    print("─" * 34)
    encabezado = f"  {'corte':<14} {'fuentes':>7} {'alto':>5} {'bajo':>5}  "
    estados = ["ACUERDO", "CHOQUE", "NEUTRAL", "INSUFICIENTE", "SIN_FUENTES"]
    print(encabezado + "  ".join(f"{e:>12}" for e in estados))
    for c in CORTES:
        rep = reparto(resumenes, c)
        fila = f"  {c['nombre']:<14} {c['min_fuentes']:>7} {c['score_alto']:>5} {c['score_bajo']:>5}  "
        print(fila + "  ".join(f"{rep.get(e, 0):>12}" for e in estados))

    print("\n5 · Ejemplos concretos, corte a corte")
    print("─" * 36)
    for c in CORTES:
        print(f"\n▸ corte «{c['nombre']}» "
              f"(≥{c['min_fuentes']} fuentes · alto ≥{c['score_alto']} · bajo <{c['score_bajo']})")
        for estado in ("ACUERDO", "CHOQUE", "NEUTRAL"):
            _ejemplos(resumenes, c, estado)

    print("\n" + "=" * 78)
    print("Nada de esto se ha guardado ni ha cambiado ningún contrato.")
    print("=" * 78)


# ── Entrada ──────────────────────────────────────────────────────────────────

async def main(dias=90, limite=2000):
    from motor.motor_asyncio import AsyncIOMotorClient

    url = os.environ.get("MONGO_URL")
    if not url:
        print("Falta MONGO_URL. Ejecuta esto en el shell de Render.")
        return 1

    cliente = AsyncIOMotorClient(url)
    db = cliente[os.environ.get("DB_NAME", "inveria")]
    corte_fecha = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()

    # `find` y nada más. Este script no escribe.
    docs = await db.newsletter_summaries.find(
        {"received_at": {"$gte": corte_fecha}},
        {"_id": 0, "sender": 1, "subject": 1, "received_at": 1, "extracted": 1},
    ).sort("received_at", -1).to_list(limite)

    print(f"Leídos {len(docs)} documentos de los últimos {dias} días.\n")
    informe(resumir_por_ticker(docs, _clean_source_de_server()), dias)
    cliente.close()
    return 0


if __name__ == "__main__":
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    raise SystemExit(asyncio.run(main(d)))
