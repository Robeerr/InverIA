"""El productor del veredicto del motor está retirado, y no puede volver.

QUÉ ERA

`newsletter_ingest._score_ticker` calculaba, por cada ticker mencionado en un correo, un
veredicto 🟢🟡🟠🔴 a partir de `_potential_score` — el número que mezcla crecimiento,
valoración, punto de entrada, consenso, calidad y momentum. Lo guardaba en el campo
`inveria` de la mención, y un refresco en segundo plano lo recalculaba cada 30 minutos
para hasta 25 tickers del Radar.

POR QUÉ SE FUE

En el commit anterior la confluencia pasó a cruzar fuentes con la ELEGIBILIDAD
estructural, y el Radar y el panel de fuentes dejaron de pintar el veredicto. A partir de
ahí `inveria` se seguía calculando, guardando, propagando y emitiendo **sin que lo leyera
nadie**: tres llamadas a Finnhub por ticker para producir un campo muerto.

QUÉ SE PROTEGE AQUÍ

Que no vuelva ninguna de sus piezas, y —lo que más importa— que su retirada no se haya
llevado por delante la corrección del Radar: la confluencia se sigue calculando para
TODAS las acciones, no solo para las 25 primeras.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _codigo(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    return re.sub(r"#.*", "", src)


def _modulos():
    for nombre in sorted(os.listdir(_BACKEND)):
        if nombre.endswith(".py"):
            yield nombre, _codigo(os.path.join(_BACKEND, nombre))
    scripts = os.path.join(_BACKEND, "scripts")
    if os.path.isdir(scripts):
        for nombre in sorted(os.listdir(scripts)):
            if nombre.endswith(".py"):
                yield f"scripts/{nombre}", _codigo(os.path.join(scripts, nombre))


# ── El productor no existe ───────────────────────────────────────────────────

def test_score_ticker_no_existe_en_ninguna_parte():
    for nombre, codigo in _modulos():
        assert "_score_ticker" not in codigo, nombre


def test_nadie_escribe_el_campo_inveria():
    """Se comprueba como CAMPO y no como palabra: «inveria» es también el nombre de la
    aplicación y aparece en `getLogger("inveria.newsletter")`, en `DB_NAME` y en las
    contraseñas de desarrollo. Prohibir la palabra sería leer el nombre del proyecto."""
    for nombre, codigo in _modulos():
        for patron in (r'"inveria"\s*:', r"\[\s*[\"']inveria[\"']\s*\]\s*=",
                       r'\.get\(\s*["\']inveria["\']\s*\)'):
            assert not re.search(patron, codigo), f"{nombre}: {patron}"


def test_la_cache_del_veredicto_no_existe():
    for nombre, codigo in _modulos():
        assert "radar_score_" not in codigo, nombre


def test_el_refresco_en_segundo_plano_no_existe():
    for nombre, codigo in _modulos():
        assert "_refresh_bg" not in codigo, nombre


def test_newsletter_ingest_ya_no_depende_del_motor():
    """Al irse `_score_ticker` se fueron con ella sus cuatro imports locales. Que el
    módulo de ingesta ya no importe el motor de oportunidades es la señal de que la
    dependencia se cortó de verdad y no solo dejó de llamarse."""
    codigo = _codigo(os.path.join(_BACKEND, "newsletter_ingest.py"))
    for muerto in ("opportunities", "external_data", "market_data", "_potential_score",
                   "verdict"):
        assert muerto not in codigo, muerto


# ── Y la corrección del Radar sigue en pie ───────────────────────────────────

def test_la_confluencia_se_sigue_calculando_para_todas():
    """El invariante que la retirada podía romper: `top = acciones[:25]` desapareció con
    el refresco, y aplicarlo a la resolución de tendencias habría devuelto los elementos
    26 en adelante a `confluencia: None`."""
    codigo = _codigo(os.path.join(_BACKEND, "server.py"))
    assert "for item, tend in zip(acciones, tendencias)" in codigo
    assert "zip(top, tendencias)" not in codigo


def test_el_radar_devuelve_la_lista_entera():
    codigo = _codigo(os.path.join(_BACKEND, "server.py"))
    assert '"acciones": acciones,' in codigo
    assert "acciones[:25]" not in codigo


# ── El diagnóstico mide el eje correcto ──────────────────────────────────────

def test_el_diagnostico_mide_tendencia_y_no_veredictos():
    """Contar veredictos guardados explicaría la ausencia de tarjetas con una causa
    equivocada — manda a buscar donde no está. El cruce necesita la elegibilidad."""
    codigo = _codigo(os.path.join(_BACKEND, "scripts", "diagnostico_hoy.py"))
    assert "tendencia_de" in codigo
    assert "hay_tendencia_valida" in codigo
    assert "con_veredicto" not in codigo


# ── Las fronteras que no se tocan ────────────────────────────────────────────

def test_potential_score_sigue_vivo_para_los_rankings():
    """El commit 2 retira un CONSUMIDOR, no el score. Sus cuatro pantallas de ranking
    siguen congeladas a la espera de un `tendencia_score` medido."""
    op = _codigo(os.path.join(_BACKEND, "opportunities.py"))
    srv = _codigo(os.path.join(_BACKEND, "server.py"))
    assert "_potential_score" in op
    assert "potential_score" in srv
