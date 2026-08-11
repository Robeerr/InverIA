"""El endpoint del desglose: que no recalcule nada y que cuadre con lo que ya se ve.

El desglose lo produce el escaneo del screener y se guarda. Este endpoint lo sirve, y su
unica virtud es lo que NO hace: no recalcula, no abre red, y no engorda la respuesta de
/opportunities/screener — que se devuelve entera desde cache.

El test que mas importa es el de reconstruccion, y se hace CONTRA EL SCORE ALMACENADO en
`results`, sin volver a ejecutar el calculo. Recalcular para comprobar solo demostraria
que la funcion es determinista, no que lo servido corresponde con lo que el usuario ve.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import opportunities as op  # noqa: E402


# ── Una cache de screener falsa, con la forma exacta de la real ──────────────
def _cache_falsa():
    det = op._potential_score_detalle(
        45, 30, 18, -12, cons_score=80, ret_26w=20, ret_52w=-30,
        rel_strength=-20, net_margin=18, roe=22, debt_to_equity=0.3)
    return {
        "data": {
            "generated_at": "2026-08-11T13:00:00+00:00",
            "results": [
                {"symbol": "NVDA", "potential_score": det["score"],
                 "valuation": det["val_label"], "momentum": det["momentum_label"]},
                {"symbol": "SINDESGLOSE", "potential_score": 40.0},
            ],
        },
        "ts": None,
        "desgloses": {"NVDA": {
            "bruto": det["bruto"],
            "multiplicador": det["multiplicador"],
            "motivo_multiplicador": det["motivo_multiplicador"],
            "recortado": det["recortado"],
            "componentes": det["componentes"],
        }},
    }


@pytest.fixture
def cache(monkeypatch):
    falsa = _cache_falsa()
    monkeypatch.setattr(op, "_screener_cache", falsa)
    return falsa


# ── 1 · EL INVARIANTE, contra el score ALMACENADO ───────────────────────────
def test_el_desglose_reconstruye_el_score_guardado_en_results(cache):
    """Sin volver a llamar a `_potential_score`: se compara lo servido contra el numero
    que ya esta en la lista. Es lo que garantiza que la explicacion corresponde con lo
    que el usuario ve, y no solo que el calculo sea repetible."""
    servido = op.desglose_de("NVDA")
    almacenado = next(r for r in cache["data"]["results"] if r["symbol"] == "NVDA")

    d = servido["desglose"]
    suma = sum(c["puntos"] for c in d["componentes"])
    reconstruido = round(min(max(suma * d["multiplicador"], 0), 100), 1)

    assert servido["score"] == almacenado["potential_score"]
    assert reconstruido == almacenado["potential_score"]


def test_el_score_servido_sale_de_results_y_no_de_un_recalculo(cache):
    """Se retuerce el score almacenado. Si el endpoint recalculara, lo ignoraria."""
    cache["data"]["results"][0]["potential_score"] = 12.3
    assert op.desglose_de("NVDA")["score"] == 12.3


# ── 2 · Cero recalculo, cero red ────────────────────────────────────────────
def test_no_llama_al_calculo_del_score(monkeypatch, cache):
    def prohibido(*a, **kw):
        raise AssertionError("el endpoint ha recalculado el score")
    monkeypatch.setattr(op, "_potential_score", prohibido)
    monkeypatch.setattr(op, "_potential_score_detalle", prohibido)
    assert op.desglose_de("NVDA") is not None


def _codigo_endpoint():
    ruta = os.path.join(os.path.dirname(__file__), "..", "server.py")
    with open(ruta, encoding="utf-8") as fh:
        src = fh.read()
    ini = src.index('@api_router.get("/opportunities/score/{symbol}")')
    cuerpo = src[ini:src.index("\n@api_router", ini + 10)]
    cuerpo = re.sub(r'"""[\s\S]*?"""', "", cuerpo)
    return "\n".join(l.split("#")[0] for l in cuerpo.splitlines())


@pytest.mark.parametrize("caro", [
    "finnhub", "external_data", "market_data", "_potential_score",
    "scan_growth_screener", "await", "requests",
])
def test_el_endpoint_no_hace_nada_caro(caro):
    """Ni red, ni recalculo, ni disparar un escaneo. Solo leer memoria — por eso ni
    siquiera necesita ser asincrono por dentro."""
    assert caro not in _codigo_endpoint()


def test_el_endpoint_pide_sesion():
    assert "Depends(auth.get_current_user)" in _codigo_endpoint()


# ── 3 · El 404 dice por que ─────────────────────────────────────────────────
def test_simbolo_que_no_esta_en_el_escaneo(cache):
    assert op.desglose_de("ZZZZ") is None


def test_en_results_pero_sin_desglose_tambien_es_none(cache):
    """Puede pasar si el escaneo fallo a medias para ese simbolo."""
    assert op.desglose_de("SINDESGLOSE") is None


def test_el_404_explica_que_es_de_la_cache_y_que_se_recalculara():
    cuerpo = _codigo_endpoint()
    assert "404" in cuerpo
    assert "cache" in cuerpo and "proximo escaneo" in cuerpo


@pytest.mark.parametrize("entrada", ["", "   ", None])
def test_simbolo_vacio_no_revienta(cache, entrada):
    assert op.desglose_de(entrada) is None


def test_el_simbolo_se_normaliza_a_mayusculas(cache):
    assert op.desglose_de("nvda")["symbol"] == "NVDA"


# ── 4 · El contrato acordado ────────────────────────────────────────────────
def test_la_respuesta_tiene_las_cuatro_claves_y_no_mas(cache):
    assert set(op.desglose_de("NVDA")) == {"symbol", "score", "generado_en", "desglose"}


def test_el_desglose_no_duplica_valuation_ni_momentum(cache):
    """Ya viajan en el resultado del screener. Duplicarlos es como empiezan a divergir."""
    d = op.desglose_de("NVDA")["desglose"]
    assert "val_label" not in d and "valuation" not in d
    assert "momentum_label" not in d and "momentum" not in d


def test_los_puntos_conservan_dos_decimales(cache):
    """Con uno solo, la suma podria no reconstruir el score por redondeo."""
    for c in op.desglose_de("NVDA")["desglose"]["componentes"]:
        assert round(c["puntos"], 2) == c["puntos"]


def test_viaja_el_sello_de_cuando_se_calculo(cache):
    """Un desglose puede tener hasta 2 h. Sin sello, el lector no sabe de cuando es."""
    assert op.desglose_de("NVDA")["generado_en"] == "2026-08-11T13:00:00+00:00"


def test_el_multiplicador_y_su_motivo_viajan(cache):
    d = op.desglose_de("NVDA")["desglose"]
    assert d["multiplicador"] == 0.55
    assert d["motivo_multiplicador"]
    assert d["recortado"] is False


# ── 5 · /opportunities/screener no engorda ──────────────────────────────────
def test_los_desgloses_viven_FUERA_de_data(cache):
    """`data` es lo que /opportunities/screener devuelve entero. Meter siete componentes
    en cada resultado son unos 70 KB por carga, para algo que se abre dos o tres veces."""
    assert "desgloses" not in cache["data"]
    assert "desgloses" in cache


def test_ningun_resultado_del_screener_lleva_el_desglose(cache):
    for r in cache["data"]["results"]:
        assert "desglose" not in r and "componentes" not in r


def test_el_escaneo_guarda_los_desgloses_aparte():
    ruta = os.path.join(os.path.dirname(__file__), "..", "opportunities.py")
    with open(ruta, encoding="utf-8") as fh:
        src = fh.read()
    assert '_screener_cache["desgloses"] = desgloses' in src
    # Y el snapshot los persiste, para no quedarse ciego 2 h tras cada despliegue.
    assert 'extra={"desgloses": desgloses}' in src
    assert 'cache["desgloses"] = doc["desgloses"]' in src
