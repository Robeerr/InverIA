"""Tests de la credencial del WebSocket de precio en vivo.

Se quedó abierto en todas las rondas anteriores de seguridad porque los WebSocket no
aparecen al listar las rutas HTTP. No es un endpoint inocuo: cada conexión arranca un bucle
REST cada 15s (4 llamadas/min por símbolo) contra nuestra cuota de Finnhub, así que sin
autenticar cualquiera podía abrir conexiones para decenas de símbolos y dejar la app seca.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import re

import pytest

_RUTA = os.path.join(os.path.dirname(__file__), "..", "server.py")


def _fuente():
    with open(_RUTA, encoding="utf-8") as fh:
        return fh.read()


def test_el_websocket_valida_la_credencial():
    src = _fuente()
    m = re.search(r"@api_router\.websocket\(\"/ws/quote/\{symbol\}\"\)\s*\n"
                  r"async def ws_quote\((.*?)\):(.*?)(?=\n@|\n# ----------)", src, re.S)
    assert m, "no se encontró el endpoint ws_quote"
    firma, cuerpo = m.group(1), m.group(2)
    assert "token" in firma, "el WebSocket debe recibir un token (query param)"
    assert "auth.get_current_user(token)" in cuerpo, "no se valida la credencial"


def test_se_rechaza_ANTES_de_arrancar_el_bucle_de_cuota():
    """El orden importa: si se aceptara la conexión y se cerrara después, el bucle REST
    ya habría arrancado y el gasto de cuota estaría hecho."""
    src = _fuente()
    m = re.search(r"async def ws_quote\(.*?\):(.*?)(?=\n@|\n# ----------)", src, re.S)
    cuerpo = m.group(1)
    pos_cierre = cuerpo.find("websocket.close(code=1008)")
    pos_connect = cuerpo.find("_quote_manager.connect")
    assert pos_cierre != -1, "falta el cierre por credencial inválida"
    assert pos_connect != -1, "falta la conexión al manager"
    assert pos_cierre < pos_connect, "se rechaza DESPUÉS de conectar: la cuota ya se gastó"
    assert "return" in cuerpo[pos_cierre:pos_connect], "tras cerrar hay que salir"


def test_el_frontend_manda_el_token():
    ruta = os.path.join(os.path.dirname(__file__), "..", "..",
                        "frontend", "src", "pages", "Dashboard.jsx")
    with open(ruta, encoding="utf-8") as fh:
        src = fh.read()
    assert "ws/quote/${symbol}?token=" in src, "el frontend no manda el token en la URL"
    assert "encodeURIComponent(tok)" in src, "el token debe ir escapado en la URL"


def test_el_frontend_no_reintenta_si_le_rechazan_la_credencial():
    """Con 1008 no hay nada que reintentar: serían 5 intentos y ~1 minuto para acabar igual."""
    ruta = os.path.join(os.path.dirname(__file__), "..", "..",
                        "frontend", "src", "pages", "Dashboard.jsx")
    with open(ruta, encoding="utf-8") as fh:
        src = fh.read()
    assert "ev?.code === 1008" in src, "no se distingue el rechazo de credencial de una caída"


@pytest.mark.parametrize("token", ["", "basura", "a.b.c"])
def test_los_tokens_invalidos_se_rechazan(token):
    pytest.importorskip("jose", reason="requiere python-jose")
    os.environ.setdefault("JWT_SECRET", "test-secret-para-el-test")
    import auth
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(token)
    assert exc.value.status_code == 401


def test_un_token_valido_se_acepta():
    pytest.importorskip("jose", reason="requiere python-jose")
    os.environ.setdefault("JWT_SECRET", "test-secret-para-el-test")
    import auth
    assert auth.get_current_user(auth.create_access_token({"sub": "rober"})) == "rober"
