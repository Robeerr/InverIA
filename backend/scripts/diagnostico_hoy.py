"""Qué está recibiendo /hoy de verdad, y por qué cada tarjeta acabó donde acabó.

    cd backend && python scripts/diagnostico_hoy.py [SYM SYM ...]

Se ejecuta contra la base de datos y las cachés REALES, no contra fixtures. Existe
porque los tests con datos inventados pasaban mientras la integración real estaba
incompleta: probaban la decisión, no lo que llega.

Responde a tres preguntas concretas:

  1. ¿La caché del motor está vacía, o /hoy lee mal algún campo?
  2. Si hay zonas calculadas, ¿por qué no se emparejan con el nivel que dispara?
  3. ¿Por qué las cinco tarjetas son del mismo tipo? ¿Qué NO ha disparado?

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

    # ── 1 · Estado de la caché del motor, símbolo a símbolo ───────────────────
    titulo("1 · CACHÉ DEL MOTOR (dashboard:{sym}:1D)")
    print("Si no hay entrada, el precalentado aún no ha pasado por ese símbolo.")
    print("El precalentado solo corre L-V de 12:00 a 22:00 UTC.")
    print(f"Ahora son las {datetime.now(timezone.utc).strftime('%H:%M')} UTC "
          f"({'DENTRO' if datetime.now(timezone.utc).weekday() < 5 and 12 <= datetime.now(timezone.utc).hour < 22 else 'FUERA'} de la ventana)\n")

    calientes = await server.hot_signals(limit=50, _user="diag")
    objetivo_por_sym = {c["symbol"]: c for c in calientes}

    for sym in simbolos:
        dash = server._dashboard_cacheado(sym)
        if not dash:
            print(f"  {sym:<6} SIN CACHÉ — la tarjeta no puede traer fuerza ni razones")
            continue

        niveles = server._niveles_del_motor(dash)
        salud = dash.get("data_health") or {}
        print(f"  {sym:<6} en caché · generado {dash.get('generado_en', '?')[:16]} · "
              f"{len(niveles)} zonas del motor · degradado: {bool(salud.get('degraded'))}")

        c = objetivo_por_sym.get(sym)
        objetivo = c.get("target") if c else None
        if objetivo:
            print(f"         tu nivel que dispara: {objetivo}  ({c.get('level_label')})")
        for z in niveles[:6]:
            precio = z.get("price")
            dist = (abs(precio - objetivo) / objetivo * 100) if (precio and objetivo) else None
            marca = ""
            if dist is not None:
                # _mejor_zona solo empareja si la zona está a menos del 3% del nivel.
                marca = "  <-- SE EMPAREJA" if dist <= 3 else f"  (a {dist:.1f}% de tu nivel: NO se empareja)"
            print(f"           zona {precio}  fuerza {z.get('strength')}  "
                  f"{', '.join((z.get('reasons') or [])[:3])}{marca}")
        if not niveles:
            print("           el motor no devolvió ninguna zona para este símbolo")

    # ── 2 · Qué NO ha disparado ──────────────────────────────────────────────
    titulo("2 · POR QUÉ TODAS LAS TARJETAS SON DEL MISMO TIPO")
    alertas = await server.db.alert_history.find(
        {"fired_at": {"$gte": corte}}, {"_id": 0}).to_list(50)
    resumen = await server.resumen_cartera(_user="diag")
    posiciones = {(p.get("symbol") or "").upper(): p
                  for p in (resumen.get("posiciones") or [])}
    abiertas = {s: p for s, p in posiciones.items() if (p.get("acciones") or 0) > 0}
    fuentes = await server._fuentes_por_ticker(14)
    con_veredicto = {t: f for t, f in fuentes.items() if f.get("inveria")}

    rupturas = []
    for sym in abiertas:
        ind = (server._dashboard_cacheado(sym).get("indicators") or {})
        if ((ind.get("salida_10w") or {}).get("recien_perdida")):
            rupturas.append(sym)

    cerca = [c for c in calientes
             if (c.get("pct_away") or 99) <= hoy_mod.UMBRAL_NIVEL_PCT]

    print(f"  Regla 1 · rupturas (posición abierta que pierde la media 10s) : {len(rupturas)}"
          + (f" -> {rupturas}" if rupturas else "  (por eso no hay tarjeta de este tipo)"))
    print(f"  Regla 2 · alertas disparadas desde hace 24 h                  : {len(alertas)}"
          + ("" if alertas else "  (por eso no hay tarjeta de este tipo)"))
    print(f"  Regla 3 · niveles a menos del {hoy_mod.UMBRAL_NIVEL_PCT}%                          : {len(cerca)}"
          f"  <-- las que ves")
    print(f"  Reglas 4 y 5 · tickers mencionados por tus fuentes (14 días)  : {len(fuentes)}")
    print(f"               de esos, con veredicto del motor guardado        : {len(con_veredicto)}")
    if not con_veredicto:
        print("               sin veredicto no puede haber choque ni coincidencia:")
        print("               el cruce necesita las DOS opiniones.")
    print(f"  Regla 6 · posiciones abiertas                                 : {len(abiertas)}")

    # ── 3 · Lo que devuelve /hoy, con su urgencia ────────────────────────────
    titulo("3 · LAS TARJETAS QUE SALEN, CON SU REGLA Y SU URGENCIA")
    datos = await server.dashboard_hoy(_user="diag")
    for i, t in enumerate(datos["importa_hoy"], 1):
        print(f"  {i}. {t['symbol']:<6} tipo={t['tipo']:<12} urgencia={t['urgencia']}")
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
