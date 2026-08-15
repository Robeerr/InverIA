"""El vigía avisa de un Gemini más nuevo. AVISA: no cambia el modelo.

Esa frontera es el motivo de que el módulo exista, así que se fija aquí: pase lo que
pase con el catálogo de Google, `ai_analysis.GEMINI_MODEL` no se toca. Cambiar de modelo
es poner una variable de entorno a mano, a propósito y de forma reversible.

Lo demás que se protege:

  · no se salta de familia (flash → pro sería multiplicar la factura; flash → flash-lite,
    bajar de calidad; ninguna de las dos es la pregunta que este vigía contesta)
  · no se empuja a un preview ni al alias `-latest`, que va por detrás
  · el mismo aviso no se repite semana tras semana
  · un aviso que NO llegó no se marca como dado

Ejecutar:  cd backend && pytest tests/test_vigia_modelo.py -v
"""
import asyncio

import pytest

import ai_analysis
import vigia_modelo

from test_cartera_api import _Coleccion


def _correr(coro):
    return asyncio.run(coro)


CATALOGO = [
    "models/gemini-3.5-flash",
    "models/gemini-3.6-flash",
    "models/gemini-3.7-flash",
    "models/gemini-4.0-pro",
    "models/gemini-3.9-flash-lite",
    "models/gemini-4.1-flash-preview",
    "models/gemini-flash-latest",
]


# ── Qué se considera "más nuevo" ─────────────────────────────────────────────

def test_propone_el_flash_mas_nuevo():
    assert vigia_modelo.mas_nuevo("gemini-3.6-flash", CATALOGO) == "gemini-3.7-flash"


def test_no_propone_nada_si_ya_estas_en_el_mas_nuevo():
    assert vigia_modelo.mas_nuevo("gemini-3.7-flash", CATALOGO) == ""


def test_no_salta_de_familia():
    """Con 4.0-pro y 3.9-flash-lite en el catálogo, desde flash sigue tocando 3.7-flash."""
    assert vigia_modelo.mas_nuevo("gemini-3.6-flash", CATALOGO) == "gemini-3.7-flash"
    assert vigia_modelo.mas_nuevo("gemini-3.5-flash-lite", CATALOGO) == "gemini-3.9-flash-lite"


def test_no_empuja_a_un_preview():
    """4.1-flash-preview es más alto que 3.7 y aun así no se propone: Google puede
    retirarlo sin avisar, y esto es producción."""
    assert vigia_modelo.mas_nuevo("gemini-3.6-flash", CATALOGO) != "gemini-4.1-flash-preview"


def test_el_alias_latest_no_cuenta_como_modelo():
    """En agosto de 2026 apuntaba a 3.5 con 3.7 publicado: seguirlo sería retroceder."""
    assert vigia_modelo.descomponer("gemini-flash-latest") is None


def test_compara_por_numero_y_no_por_texto():
    """'3.10' > '3.9' aunque como texto sea al revés."""
    assert vigia_modelo.mas_nuevo("gemini-3.9-flash",
                                  ["models/gemini-3.10-flash"]) == "gemini-3.10-flash"


# ── La frontera: avisar no es cambiar ────────────────────────────────────────

class _DBAvisos:
    def __init__(self, avisos=None):
        self.avisos_modelo = _Coleccion(avisos or [])


@pytest.fixture
def catalogo(monkeypatch):
    async def _listar():
        return CATALOGO
    monkeypatch.setattr(vigia_modelo, "_listar_modelos", _listar)
    monkeypatch.setattr(ai_analysis, "GEMINI_MODEL", "gemini-3.6-flash")


@pytest.fixture
def telegram(monkeypatch):
    enviados = []

    async def _enviar(texto, parse_mode="MarkdownV2", grupo=None):
        enviados.append(texto)
        return True, None

    monkeypatch.setattr(vigia_modelo.telegram_notifier, "send_message", _enviar)
    return enviados


def test_avisar_no_cambia_el_modelo(catalogo, telegram):
    """La frontera entera. Se comprueba DESPUÉS de un aviso real, que es cuando la
    tentación de "ya que estamos, lo pongo" tendría efecto."""
    db = _DBAvisos()
    r = _correr(vigia_modelo.comprobar(db))
    assert r["avisado"] is True and r["nuevo"] == "gemini-3.7-flash"
    assert ai_analysis.GEMINI_MODEL == "gemini-3.6-flash", (
        "el vigía avisa; cambiar el modelo es poner GEMINI_MODEL a mano")


def test_el_aviso_dice_como_cambiarlo(catalogo, telegram):
    _correr(vigia_modelo.comprobar(_DBAvisos()))
    assert "GEMINI_MODEL=gemini-3.7-flash" in telegram[0], (
        "un aviso sin el paso siguiente se pospone y no se actúa nunca")


def test_el_mismo_aviso_no_se_repite(catalogo, telegram):
    """Repetirlo cada semana enseña a ignorar a este bot, que también manda las alertas
    de nivel."""
    db = _DBAvisos()
    _correr(vigia_modelo.comprobar(db))
    r = _correr(vigia_modelo.comprobar(db))
    assert r["ya_avisado"] is True
    assert len(telegram) == 1


def test_un_aviso_que_no_salio_no_se_marca(catalogo, monkeypatch):
    """Marcarlo lo perdería para siempre: la semana que viene ya no se intentaría."""
    async def _falla(texto, parse_mode="MarkdownV2", grupo=None):
        return False, "Bot de Telegram no configurado en el servidor."

    monkeypatch.setattr(vigia_modelo.telegram_notifier, "send_message", _falla)
    db = _DBAvisos()
    r = _correr(vigia_modelo.comprobar(db))
    assert r["avisado"] is False and db.avisos_modelo.docs == []


def test_si_google_no_contesta_no_se_inventa_nada(monkeypatch, telegram):
    async def _revienta():
        raise RuntimeError("503")

    monkeypatch.setattr(vigia_modelo, "_listar_modelos", _revienta)
    monkeypatch.setattr(ai_analysis, "GEMINI_MODEL", "gemini-3.6-flash")
    r = _correr(vigia_modelo.comprobar(_DBAvisos()))
    assert r["nuevo"] == "" and r["avisado"] is False and telegram == []
