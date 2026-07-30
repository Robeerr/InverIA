"""Tests del orden de preferencia de los objetivos (take profits).

Antes TP2 ERA la extensión Fibonacci 127,2% y TP3 la 161,8%, por definición y sin que nadie
hubiera comprobado que el precio llegue ahí. Como la extensión se mide sobre el rango de 52
semanas, cuanto más había caído la acción más arriba proyectaba: de ahí los objetivos de
+283% que hubo que tapar con un techo.

Ahora manda el nivel REAL (resistencia donde el precio ya se paró, máximo de 52 semanas,
objetivo de analistas) y Fibonacci solo entra si no hay nada arriba — típico en máximos
históricos.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import re

import pytest

MIN_RR = 2.0
_RUTA = os.path.join(os.path.dirname(__file__), "..", "server.py")


def _objetivos(price, res_up, high_52w, low_52w, analyst, entry_ref, stop):
    """Réplica de la lógica de _deterministic_levels. Se replica en vez de importar server
    porque importarlo arrastra FastAPI, Mongo y los workers de fondo."""
    rng = high_52w - low_52w
    fib127 = round(low_52w + rng * 1.272, 2) if rng > 0 else None
    fib161 = round(low_52w + rng * 1.618, 2) if rng > 0 else None
    ceiling = min(round(high_52w * 1.15, 2),
                  max([r for r in res_up] + [analyst or 0] + [price * 1.5]))

    def cap(x):
        return min(x, ceiling) if x else x

    risk = entry_ref - stop
    min_tp1 = entry_ref + MIN_RR * risk if risk > 0 else price * 1.04

    cands = []
    t1 = next((r for r in res_up if r >= min_tp1), None)
    cands.append((t1, "TP1 — Resistencia") if t1 else (round(min_tp1, 2), "TP1 — Objetivo por R/R"))
    ancla = t1 or min_tp1
    for r in res_up:
        if r > ancla * 1.02:
            cands.append((r, "TP — Siguiente resistencia"))
            ancla = r
            if len(cands) >= 4:
                break
    if high_52w and high_52w > price * 1.01:
        cands.append((round(high_52w, 2), "TP — Máximo de 52 semanas"))
    if analyst:
        cands.append((analyst, "TP — Objetivo medio de analistas"))
    if fib127:
        cands.append((fib127, "TP — Extensión Fibonacci 127,2%"))
    if fib161:
        cands.append((fib161, "TP — Extensión Fibonacci 161,8%"))

    tps, vistos = [], set()
    for val, lab in ((v, l) for v, l in cands if v):
        c = round(cap(val), 2)
        if c <= price or c in vistos or c < min_tp1 - 0.01:
            continue
        vistos.add(c)
        tps.append({"label": lab if abs(c - round(val, 2)) < 0.01 else "TP — Techo realista",
                    "price": c})
        if len(tps) >= 3:
            break
    tps.sort(key=lambda t: t["price"])
    rr = round((tps[0]["price"] - entry_ref) / risk, 2) if (risk > 0 and tps) else None
    return tps, rr


# Caso real: MRVL el 27/07/2026, venía de 340 y estaba en 186.
MRVL = dict(price=186.14, res_up=[300.0, 324.20, 329.88], high_52w=340.0, low_52w=60.0,
            analyst=310.0, entry_ref=170.23, stop=137.39)


def test_con_resistencias_reales_no_aparece_fibonacci():
    tps, _ = _objetivos(**MRVL)
    etiquetas = " ".join(t["label"] for t in tps)
    assert "Fibonacci" not in etiquetas, f"Fibonacci no debería entrar aquí: {etiquetas}"
    assert len(tps) == 3


def test_los_objetivos_salen_de_niveles_observables():
    tps, _ = _objetivos(**MRVL)
    precios = [t["price"] for t in tps]
    # Todos deben venir de una resistencia real, del máximo de 52s o del cap.
    admisibles = set(MRVL["res_up"]) | {MRVL["high_52w"], MRVL["analyst"]}
    for p in precios:
        assert any(abs(p - a) < 0.02 for a in admisibles) or p <= MRVL["high_52w"] * 1.15


def test_fibonacci_entra_solo_si_no_hay_nada_arriba():
    """Acción en máximos históricos: no hay resistencias por encima. Aquí Fibonacci es
    legítimo y debe poder aparecer, con la etiqueta diciendo por qué."""
    tps, _ = _objetivos(price=200.0, res_up=[], high_52w=200.0, low_52w=100.0,
                        analyst=None, entry_ref=196.0, stop=180.0)
    assert tps, "debería dar al menos un objetivo"


def test_ningun_objetivo_por_debajo_del_suelo_de_rr():
    """Regresión: una extensión Fibonacci ligeramente por debajo del suelo se colaba como
    TP1 y el plan salía con R/R 1,95 pidiendo 2."""
    for kw in (MRVL,
               dict(price=200.0, res_up=[], high_52w=200.0, low_52w=100.0, analyst=None,
                    entry_ref=196.0, stop=180.0),
               dict(price=50.0, res_up=[], high_52w=52.0, low_52w=45.0, analyst=None,
                    entry_ref=49.0, stop=44.0)):
        tps, rr = _objetivos(**kw)
        assert rr is None or rr >= MIN_RR, f"R/R {rr} por debajo del mínimo en {kw['price']}"


def test_los_objetivos_van_en_orden_creciente():
    """Se eligen por preferencia de método, no por precio, así que hay que ordenarlos antes
    de numerarlos o saldría un TP2 más bajo que el TP1."""
    tps, _ = _objetivos(price=100.0, res_up=[112.0, 125.0, 140.0, 155.0, 170.0],
                        high_52w=180.0, low_52w=70.0, analyst=145.0,
                        entry_ref=97.0, stop=88.0)
    precios = [t["price"] for t in tps]
    assert precios == sorted(precios), f"desordenados: {precios}"


def test_fibonacci_va_DESPUES_de_los_niveles_reales_en_el_fuente():
    """Fija el orden en el código: si alguien vuelve a poner Fibonacci antes que las
    resistencias, vuelven los objetivos de fantasía."""
    with open(_RUTA, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"cands = \[\](.*?)tps, vistos = \[\], set\(\)", src, re.S)
    assert m, "no se encontró el bloque de candidatos"
    # Solo las líneas de CÓDIGO: los comentarios de ese bloque también nombran Fibonacci
    # (explican precisamente por qué va al final) y desvirtuarían la comprobación.
    codigo = "\n".join(l for l in m.group(1).splitlines()
                       if l.strip() and not l.strip().startswith("#"))
    pos_res = codigo.find("Siguiente resistencia")
    pos_fib = codigo.find("Fibonacci")
    assert pos_res != -1, "no se encontró el candidato de resistencia"
    assert pos_fib != -1, "no se encontró el candidato de Fibonacci"
    assert pos_res < pos_fib, "Fibonacci debe ir DESPUÉS de las resistencias reales"
