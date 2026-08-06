"""Tests del presupuesto de tiempo de la cotización.

Caso real medido en producción (MRVL, 06/08/2026): la cotización tardó 8.696 ms y se llevó
ella sola el total de la carga; todo lo demás iba por debajo de 1 s. La causa era que
`t.fast_info` de yfinance iba SIN tope mientras el resto del camino sí lo tenía (Finnhub
2,5 s, `.info` 3 s). yfinance abre red ahí y se cuelga cuando Yahoo estrangula.

El precio ya viene de Finnhub: los fundamentales (PER, beta, capitalización) son adorno y no
deben retrasar lo que el usuario está esperando ver.

Ejecutar:  cd backend && pytest tests/ -v
"""
import re
import os
import time

import pytest

pytest.importorskip("pandas")
import market_data as md  # noqa: E402

_RUTA = os.path.join(os.path.dirname(__file__), "..", "market_data.py")


def test_el_enriquecimiento_tiene_un_tope_corto():
    assert md._ENRICH_TIMEOUT <= 2.5, (
        f"{md._ENRICH_TIMEOUT}s es demasiado: sumado al tope de Finnhub deja la cotización "
        "por encima de lo que nadie espera mirando una pantalla en blanco."
    )


def test_una_llamada_colgada_no_bloquea_la_cotizacion():
    """El caso de los 8,7 s: si yfinance se cuelga, se devuelve el valor por defecto."""
    def colgado():
        time.sleep(30)
        return ({"no": "deberia"}, {"llegar": "aqui"})

    t0 = time.time()
    r = md._call_with_timeout(colgado, md._ENRICH_TIMEOUT, ({}, {}))
    tardado = time.time() - t0
    assert r == ({}, {}), "debería rendirse y devolver el valor por defecto"
    assert tardado < md._ENRICH_TIMEOUT + 1.0, f"tardó {tardado:.1f}s: el tope no se aplica"


def test_si_responde_a_tiempo_se_conservan_los_fundamentales():
    """El tope no debe costar datos cuando la fuente va bien."""
    r = md._call_with_timeout(lambda: ({"last_volume": 10}, {"trailingPE": 20}),
                              md._ENRICH_TIMEOUT, ({}, {}))
    assert r[0]["last_volume"] == 10 and r[1]["trailingPE"] == 20


def test_fast_info_ya_no_se_llama_sin_tope():
    """Regresión: `fast = t.fast_info` suelto es exactamente lo que causó los 8,7 s.
    Debe ir dentro del bloque con presupuesto."""
    with open(_RUTA, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"def get_quote\(ticker.*?(?=\ndef )", src, re.S)
    assert m, "no se encontró get_quote"
    cuerpo = m.group(0)
    # Cualquier uso de fast_info dentro de get_quote debe estar en la función acotada.
    for linea in cuerpo.splitlines():
        if "fast_info" in linea and not linea.strip().startswith("#"):
            assert "_enriquecer" in cuerpo, "fast_info debe usarse dentro de _enriquecer()"
    assert "_call_with_timeout(_enriquecer" in cuerpo, (
        "el enriquecimiento debe pasar por _call_with_timeout")


def test_get_quote_fast_no_toca_los_fundamentales():
    """La vía rápida (watchlist, websocket, worker) solo necesita el precio. Si tocara
    .info arrastraría el mismo problema a todas las listas."""
    with open(_RUTA, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"def get_quote_fast\(ticker.*?(?=\ndef )", src, re.S)
    cuerpo = m.group(0)
    assert "fast_info" not in cuerpo and "_get_info_cached" not in cuerpo


# ── El 429 de Finnhub ────────────────────────────────────────────────────────
# Medido con MRVL: la cotización tardaba 6,6 s en FALLAR. Desglose: ~1 s de la primera
# llamada + 5 s de `time.sleep(5)` + ~0,6 s del reintento. Dormir en el camino de una
# petición del usuario bloquea un hilo y retrasa la pantalla, y el reintento gasta otra
# llamada de la cuota que acaba de agotarse — teniendo un respaldo que funciona.

def _sleeps_largos(ruta, umbral=3.0):
    """Llamadas REALES a time.sleep(n) con n >= umbral, vía árbol sintáctico.

    Buscar el texto no vale: los comentarios y docstrings de estos módulos MENCIONAN
    time.sleep(5) para explicar por qué se quitó, y darían un falso positivo.
    """
    import ast
    with open(ruta, encoding="utf-8") as fh:
        arbol = ast.parse(fh.read())
    fuera = []
    for n in ast.walk(arbol):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nombre = (f.attr if isinstance(f, ast.Attribute) else
                  f.id if isinstance(f, ast.Name) else "")
        if nombre != "sleep" or not n.args:
            continue
        a = n.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, (int, float)) and a.value >= umbral:
            fuera.append((n.lineno, a.value))
    return fuera


def test_no_se_duerme_esperando_a_finnhub():
    """Regresión: ni market_data ni external_data deben dormir ante un 429."""
    for fichero in ("market_data.py", "external_data.py"):
        ruta = os.path.join(os.path.dirname(__file__), "..", fichero)
        encontrados = _sleeps_largos(ruta)
        assert not encontrados, (
            f"{fichero}: sleep largo en el camino de la petición, líneas {encontrados}")


def test_todas_las_esperas_del_limitador_van_acotadas():
    """acquire() sin max_wait bloquea hasta 60 s. En cualquier camino que sirva a un
    usuario eso es una pantalla congelada."""
    for fichero in ("external_data.py", "server.py"):
        ruta = os.path.join(os.path.dirname(__file__), "..", fichero)
        with open(ruta, encoding="utf-8") as fh:
            codigo = fh.read()
        sueltas = re.findall(r"limiter\(\)\.acquire\(\s*\)", codigo)
        assert not sueltas, f"{fichero}: {len(sueltas)} acquire() sin max_wait"


def test_sin_hueco_external_data_degrada_como_un_429(monkeypatch):
    """Si no hay cuota se devuelve un 429 sintético: así el llamador degrada por el camino
    que ya existe, sin tener que distinguir 'sin cuota' de 'el proveedor dijo que no'."""
    import external_data as ed

    class _LimSinHueco:
        def acquire(self, max_wait=None):
            return False

    monkeypatch.setattr(ed._md, "get_finnhub_limiter", lambda: _LimSinHueco())
    t0 = time.time()
    r = ed._finnhub_get("/quote", {"symbol": "AAPL"})
    assert r.status_code == 429
    assert time.time() - t0 < 0.5, "no debería esperar nada si no hay hueco"
