"""Por qué cada tarjeta de /hoy acabó donde acabó.

    cd backend && python scripts/diagnostico_hoy.py [SYM SYM ...]

⚠️  LO QUE ESTE SCRIPT NO PUEDE RESPONDER

No puede decirte si la caché del motor de niveles del SERVICIO WEB está caliente.

La caché vive en la memoria del proceso (`_cache` en server.py). Ejecutar esto en la
Shell de Render arranca un proceso NUEVO, con su caché vacía, así que preguntarle por
la caché siempre respondería «vacía» — aunque el servicio web las tuviera todas.

La primera versión de este script sí lo preguntaba, e imprimía «SIN CACHÉ» para todos
los símbolos. Era un artefacto de la herramienta, y mandó a investigar donde no había
nada. Esa sección se ha eliminado en vez de arreglarla: no tiene arreglo desde aquí.

    Para saber qué está caliente, mira los logs del servicio web en Render:
        Dashboards precalentados (vuelta N): X de Y · SYM, SYM, SYM

Lo que sí responde, porque sale de Mongo —estado compartido entre procesos—:

  1. Qué regla ha disparado y cuál no, con sus conteos.
  2. Qué tarjetas salen, con su tipo y su urgencia.
  3. Cuántos de tus tickers mencionados tienen tendencia clasificable y cuántos son
     estructuralmente elegibles, que es lo que el cruce necesita de verdad.

No imprime ninguna credencial ni ningún dato personal más allá de tus propios
tickers y precios, que es exactamente lo que la pantalla ya te enseña.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
import hoy as hoy_mod  # noqa: E402


def titulo(t):
    print(f"\n{'─' * 78}\n{t}\n{'─' * 78}")


async def main(simbolos):
    corte = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # La sección que preguntaba por la caché del motor se ha eliminado a propósito:
    # desde este proceso siempre habría respondido "vacía". Ver la cabecera del fichero.
    titulo("1 · ESTADO DE LA CACHÉ DEL MOTOR DE NIVELES")
    print("  No se puede medir desde aquí: la caché vive en la memoria del servicio web")
    print("  y este script es otro proceso. Míralo en los logs de Render, buscando:")
    print("      Dashboards precalentados (vuelta N): X de Y · SYM, SYM, ...")
    print()
    print("  Lo que sí se ve aquí es si /hoy dice tener datos del motor por tarjeta,")
    print("  en la sección 3: campo motor_niveles (confirma / sin_zona / sin_datos).")

    calientes = await server.hot_signals(limit=50, _user="diag")

    # ── 2 · Qué NO ha disparado ──────────────────────────────────────────────
    titulo("2 · POR QUÉ TODAS LAS TARJETAS SON DEL MISMO TIPO")
    alertas = await server.db.alert_history.find(
        {"fired_at": {"$gte": corte}}, {"_id": 0}).to_list(50)
    resumen = await server.resumen_cartera(_user="diag")
    posiciones = {(p.get("symbol") or "").upper(): p
                  for p in (resumen.get("posiciones") or [])}
    abiertas = {s: p for s, p in posiciones.items() if (p.get("acciones") or 0) > 0}
    fuentes = await server._fuentes_por_ticker(14)
    # El cruce ya NO necesita un veredicto guardado: necesita la ELEGIBILIDAD, que decide
    # `tendencia.py`. Contar veredictos aquí explicaría la ausencia de tarjetas con una
    # causa equivocada, que es peor que no medir — manda a buscar donde no está.
    import market_data
    import tendencia as tendencia_mod
    estados = {t: await asyncio.to_thread(market_data.tendencia_de, t) for t in fuentes}
    clasificables = {t: e for t, e in estados.items() if e != "SIN_DATOS"}
    elegibles = {t: e for t, e in estados.items()
                 if tendencia_mod.hay_tendencia_valida(e)}

    cerca = [c for c in calientes
             if (c.get("pct_away") or 99) <= hoy_mod.UMBRAL_NIVEL_PCT]

    # La ruptura sale de `salida_10w`, que viaja dentro del dashboard cacheado. Desde
    # este proceso la caché está vacía, así que contarlas aquí daría SIEMPRE 0 y sería
    # otra respuesta falsa con aspecto de dato. Se dice, y punto.
    print( "  Regla 1 · rupturas (posición abierta que pierde la media 10s) : NO MEDIBLE aquí")
    print( "            depende del dashboard cacheado; míralo en la sección 3, que sí")
    print( "            recalcula, o en la propia portada")
    print(f"  Regla 2 · alertas disparadas desde hace 24 h                  : {len(alertas)}"
          + ("" if alertas else "  (por eso no hay tarjeta de este tipo)"))
    print(f"  Regla 3 · niveles a menos del {hoy_mod.UMBRAL_NIVEL_PCT}%                          : {len(cerca)}"
          f"  <-- las que ves")
    print(f"  Reglas 4 y 5 · tickers mencionados por tus fuentes (14 días)  : {len(fuentes)}")
    print(f"               de esos, con tendencia clasificable                : {len(clasificables)}")
    print(f"               de esos, estructuralmente elegibles (ALCISTA)      : {len(elegibles)}")
    if not clasificables:
        print("               sin tendencia clasificable no puede haber choque ni")
        print("               coincidencia: el cruce necesita las DOS opiniones.")
    elif not elegibles:
        print("               ninguna es elegible: los cruces posibles son CHOQUE, no")
        print("               coincidencia.")
    print(f"  Regla 6 · posiciones abiertas                                 : {len(abiertas)}")

    # ── 3 · Lo que devuelve /hoy, con su urgencia ────────────────────────────
    titulo("3 · LAS TARJETAS QUE SALEN, CON SU REGLA Y SU URGENCIA")
    datos = await server.dashboard_hoy(_user="diag")
    for i, t in enumerate(datos["importa_hoy"], 1):
        motor = (t.get("datos") or {}).get("motor_niveles", "-")
        print(f"  {i}. {t['symbol']:<6} tipo={t['tipo']:<12} urgencia={t['urgencia']:<5} motor_niveles={motor}")
        print(f"       {t['que_pasa']}")
        print(f"       porqué : {t['por_que'][:110]}")
        if t.get("tambien"):
            print(f"       también: {[x['tipo'] for x in t['tambien']]}")
        if t.get("aviso"):
            print(f"       aviso  : {t['aviso'][:80]}")

    print(f"\n  Base de urgencia por tipo: {hoy_mod.BASE}")
    print("  Dentro de 'nivel': +20 por cada punto porcentual más cerca del umbral,")
    print("  +0,6 por punto de fuerza del motor, +15 si tienes posición abierta.")

    titulo("4 · BLOQUE DE MERCADO")
    try:
        import market_regime
        r = market_regime.get_market_regime()
        print(f"  claves devueltas: {sorted(r.keys())}")
        print(f"  light={r.get('light')}  label={r.get('label')}")
    except Exception as e:
        print(f"  no se pudo evaluar: {e}")


if __name__ == "__main__":
    syms = [s.upper() for s in sys.argv[1:]] or ["COHR", "TEM", "FORM", "INTC", "NEE"]
    asyncio.run(main(syms))
