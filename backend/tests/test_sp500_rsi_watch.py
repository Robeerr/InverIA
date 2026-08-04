"""Tests del vigía del RSI del S&P 500.

Dos cosas que importan aquí:
  • La HISTÉRESIS: sin ella, un RSI oscilando en 29,9/30,1 avisaría en cada ciclo.
  • Que un fallo de Telegram NO pierda el aviso (el bug que ya se corrigió en el vigilante
    del Chartista: guardaba el estado antes de enviar).

Ejecutar:  cd backend && pytest tests/ -v
"""
import asyncio

import pytest

pytest.importorskip("pandas")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import sp500_rsi_watch as w  # noqa: E402


class _Coleccion:
    """Sustituto mínimo de una colección de Mongo, con la semántica que usa el vigía."""

    def __init__(self):
        self.docs = {}

    async def find_one(self, filtro, *a, **k):
        return self.docs.get(filtro.get("_id"))

    async def update_one(self, filtro, cambio, upsert=False):
        _id = filtro.get("_id")
        doc = self.docs.get(_id)
        # Emula {"avisado": {"$ne": True}}: si ya está avisado, no casa.
        cond = filtro.get("avisado")
        if isinstance(cond, dict) and "$ne" in cond:
            if doc is not None and doc.get("avisado") == cond["$ne"]:
                return type("R", (), {"modified_count": 0, "upserted_id": None})()
        creado = doc is None
        if creado:
            if not upsert:
                return type("R", (), {"modified_count": 0, "upserted_id": None})()
            doc = {"_id": _id}
            self.docs[_id] = doc
        doc.update(cambio.get("$set", {}))
        return type("R", (), {"modified_count": 0 if creado else 1,
                              "upserted_id": _id if creado else None})()


class _DB:
    def __init__(self):
        self.market_rsi_state = _Coleccion()


def _serie(rsi_objetivo_bajo: bool, n=300):
    """Serie que acaba con RSI claramente bajo o claramente alto."""
    base = np.linspace(100, 140, n - 30)
    cola = np.linspace(140, 95, 30) if rsi_objetivo_bajo else np.linspace(120, 160, 30)
    precios = np.concatenate([base, cola])
    return pd.DataFrame({"Date": pd.bdate_range("2020-01-01", periods=n), "Close": precios})


@pytest.fixture
def entorno(monkeypatch):
    enviados = []

    async def _fake_send(text, parse_mode="Markdown", grupo=None):
        enviados.append(text)
        return True, None

    monkeypatch.setattr(w.telegram_notifier, "send_message", _fake_send)
    monkeypatch.setattr(w, "_historico_largo", lambda: None)   # sin red en los tests
    return enviados


def test_avisa_cuando_el_rsi_cae_por_debajo_del_umbral(entorno, monkeypatch):
    monkeypatch.setattr(w.market_data, "get_full_indicator_history", lambda s: _serie(True))
    db = _DB()
    assert asyncio.run(w.comprobar(db)) is True
    assert len(entorno) == 1
    assert "SOBREVENTA" in entorno[0]


def test_no_avisa_dos_veces_en_el_mismo_episodio(entorno, monkeypatch):
    """La histéresis: mientras no se rearme, no se repite el aviso por mucho que siga bajo."""
    monkeypatch.setattr(w.market_data, "get_full_indicator_history", lambda s: _serie(True))
    db = _DB()
    assert asyncio.run(w.comprobar(db)) is True
    for _ in range(5):
        assert asyncio.run(w.comprobar(db)) is False
    assert len(entorno) == 1, "solo debería haber UN aviso por episodio"


def test_se_rearma_al_recuperarse_y_vuelve_a_avisar(entorno, monkeypatch):
    db = _DB()
    monkeypatch.setattr(w.market_data, "get_full_indicator_history", lambda s: _serie(True))
    assert asyncio.run(w.comprobar(db)) is True
    # El RSI se recupera por encima del umbral de rearme.
    monkeypatch.setattr(w.market_data, "get_full_indicator_history", lambda s: _serie(False))
    asyncio.run(w.comprobar(db))
    assert db.market_rsi_state.docs["SPY"]["avisado"] is False
    # Nueva caída: debe volver a avisar.
    monkeypatch.setattr(w.market_data, "get_full_indicator_history", lambda s: _serie(True))
    assert asyncio.run(w.comprobar(db)) is True
    assert len(entorno) == 2


def test_no_avisa_con_el_rsi_alto(entorno, monkeypatch):
    monkeypatch.setattr(w.market_data, "get_full_indicator_history", lambda s: _serie(False))
    assert asyncio.run(w.comprobar(_DB())) is False
    assert entorno == []


def test_si_telegram_falla_el_aviso_NO_se_pierde(monkeypatch):
    """Regresión del bug que tuvo el vigilante del Chartista: marcaba 'avisado' antes de
    enviar, así que si Telegram fallaba el aviso se perdía para siempre."""
    intentos = []

    async def _falla(text, parse_mode="Markdown", grupo=None):
        intentos.append(text)
        return False, "boom"

    monkeypatch.setattr(w.telegram_notifier, "send_message", _falla)
    monkeypatch.setattr(w, "_historico_largo", lambda: None)
    monkeypatch.setattr(w.market_data, "get_full_indicator_history", lambda s: _serie(True))
    db = _DB()
    assert asyncio.run(w.comprobar(db)) is False
    assert db.market_rsi_state.docs["SPY"]["avisado"] is False, "debe quedar rearmado"
    # Al ciclo siguiente lo reintenta.
    assert asyncio.run(w.comprobar(db)) is False
    assert len(intentos) == 2


def test_sin_datos_no_rompe(entorno, monkeypatch):
    for valor in (None, pd.DataFrame(columns=["Date", "Close"])):
        monkeypatch.setattr(w.market_data, "get_full_indicator_history", lambda s, v=valor: v)
        assert asyncio.run(w.comprobar(_DB())) is False


def test_el_historial_cuenta_EPISODIOS_no_dias():
    """Una sobreventa que dura dos semanas es UN evento. Contar cada día inflaría la muestra
    y haría parecer la señal más fiable de lo que es."""
    n = 800
    p = list(np.linspace(100, 150, 400)) + list(np.linspace(150, 100, 60)) + \
        list(np.linspace(100, 160, n - 460))
    df = pd.DataFrame({"Date": pd.bdate_range("2015-01-01", periods=n), "Close": p})
    hist = w._historial_sobreventa(df, 30)
    assert hist is not None
    # La caída larga produce muchos días con RSI<30 pero debe contar como pocos episodios.
    assert hist["episodios"] <= 3, f"contó {hist['episodios']} episodios; parece contar días"


def test_el_mensaje_incluye_el_peor_caso():
    """El aviso no puede vender solo la parte buena: si históricamente hubo un episodio en
    el que siguió cayendo, tiene que decirlo."""
    hist = {"episodios": 5, "desde": "2005", "ultimo": "12/03/2020",
            "horizontes": {"3 meses": {"n": 5, "subieron": 4, "media": 8.0,
                                       "peor": -22.0, "mejor": 20.0}}}
    msg = w._formatear(27.0, 500.0, hist)
    assert "-22.0%" in msg
    assert "NO significa suelo" in msg


def test_el_mensaje_aguanta_sin_historial():
    msg = w._formatear(28.5, 500.0, None)
    assert "SOBREVENTA" in msg
    assert "No se pudo calcular el historial" in msg


# ── Régimen de tendencia ─────────────────────────────────────────────────────
# Medido sobre el S&P 500 diario 1950-2018 (212 episodios): a 3 meses subió el 77% de las
# veces por ENCIMA de la SMA200 y solo el 57% por debajo. Por eso el aviso lo distingue.

def test_detecta_el_regimen_de_tendencia():
    n = 400
    sube = pd.DataFrame({"Date": pd.bdate_range("2020-01-01", periods=n),
                         "Close": np.linspace(100, 200, n)})
    r = w._regimen(sube)
    assert r["sobre_sma200"] is True and r["dist_pct"] > 0

    baja = pd.DataFrame({"Date": pd.bdate_range("2020-01-01", periods=n),
                         "Close": np.linspace(200, 100, n)})
    r = w._regimen(baja)
    assert r["sobre_sma200"] is False and r["dist_pct"] < 0


def test_el_regimen_necesita_200_sesiones():
    corto = pd.DataFrame({"Date": pd.bdate_range("2020-01-01", periods=100),
                          "Close": np.linspace(100, 120, 100)})
    assert w._regimen(corto) is None


def test_el_historial_se_filtra_por_regimen():
    """Los episodios de tendencia sana y los de tendencia rota deben dar muestras
    DISTINTAS: si salieran iguales, el filtro no estaría aplicándose."""
    rng = np.random.default_rng(5)
    n = 3000
    p = [100.0]
    for i in range(1, n):
        d = rng.normal(0.0005, 0.009)
        if 700 < i < 780 or 1600 < i < 1900 or 2400 < i < 2460:
            d = rng.normal(-0.009, 0.013)
        p.append(p[-1] * (1 + d))
    df = pd.DataFrame({"Date": pd.bdate_range("2010-01-01", periods=n), "Close": p})
    arriba = w._historial_sobreventa(df, 30, sobre_sma200=True)
    abajo = w._historial_sobreventa(df, 30, sobre_sma200=False)
    total = w._historial_sobreventa(df, 30)
    assert arriba and abajo and total
    assert arriba["episodios"] != abajo["episodios"]
    assert arriba["episodios"] + abajo["episodios"] <= total["episodios"]


def test_el_mensaje_avisa_cuando_la_tendencia_esta_rota():
    hist = {"episodios": 158, "desde": "1950", "ultimo": "19/12/2018",
            "horizontes": {"3 meses": {"n": 155, "subieron": 89, "media": 2.4,
                                       "peor": -26.8, "mejor": 30.0}}}
    msg = w._formatear(27.4, 500.0, hist, {"sobre_sma200": False, "sma200": 550.0, "dist_pct": -8.7})
    assert "tendencia de fondo rota" in msg
    assert "acierta MUCHO menos" in msg

    msg2 = w._formatear(27.4, 500.0, hist, {"sobre_sma200": True, "sma200": 480.0, "dist_pct": 4.2})
    assert "tendencia de fondo sana" in msg2
