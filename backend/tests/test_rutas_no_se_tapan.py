"""Ninguna ruta estática puede quedar tapada por otra con parámetro.

EL FALLO QUE ESTE FICHERO IMPIDE

FastAPI resuelve las rutas POR ORDEN DE REGISTRO. Una ruta con parámetro declarada
antes se traga cualquier ruta estática que comparta prefijo:

    @api_router.get("/analyst/{symbol}")   ← línea 3703
    @api_router.get("/analyst/ideas")      ← línea 4027, INALCANZABLE

`GET /api/analyst/ideas` devolvía el consenso de analistas del «símbolo» IDEAS:
`{"symbol": "IDEAS", "consensus": null, "price_target": null}`. Estuvo así desde que se
añadió.

POR QUÉ ES DIFÍCIL DE VER

No da 404 ni 500. Da **200 con un cuerpo con sentido**, solo que del endpoint
equivocado. Nada falla, nada se registra en el log, y el cliente recibe una respuesta
válida de otra cosa. Se descubrió por casualidad al intentar validar otra cosa distinta.

Por eso el test no comprueba el caso concreto sino la CLASE: cualquier ruta estática
registrada después de una con parámetro que la pueda capturar. Arreglar solo el que
apareció habría dejado la puerta abierta para el siguiente.
"""
import os
import re

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _rutas():
    """(método, ruta, nº de línea) en ORDEN DE REGISTRO, que es como FastAPI las resuelve."""
    with open(os.path.join(_AQUI, "..", "server.py"), encoding="utf-8") as f:
        lineas = f.readlines()
    patron = re.compile(r'@(?:api_router|app)\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']')
    fuera = []
    for i, linea in enumerate(lineas, 1):
        m = patron.search(linea)
        if m:
            fuera.append((m.group(1), m.group(2), i))
    return fuera


def _tapa(patron_ruta: str, estatica: str) -> bool:
    """¿La ruta `patron_ruta` capturaría una petición a `estatica`?

    Solo importa cuando el patrón tiene al menos un parámetro: dos rutas estáticas
    distintas nunca se pisan.
    """
    a = patron_ruta.strip("/").split("/")
    b = estatica.strip("/").split("/")
    if len(a) != len(b):
        return False
    if not any(seg.startswith("{") for seg in a):
        return False
    for seg_a, seg_b in zip(a, b):
        if seg_a.startswith("{"):
            continue          # un parámetro se come cualquier segmento
        if seg_a != seg_b:
            return False
    return True


def test_hay_rutas_que_analizar():
    """Centinela: si el patrón dejara de casar, el test de abajo pasaría en vacío."""
    assert len(_rutas()) > 40


def test_ninguna_ruta_estatica_queda_inalcanzable():
    rutas = _rutas()
    tapadas = []
    for i, (metodo, ruta, linea) in enumerate(rutas):
        if "{" in ruta:
            continue                      # solo nos preocupan las estáticas
        for metodo_prev, ruta_prev, linea_prev in rutas[:i]:
            if metodo_prev != metodo:
                continue                  # métodos distintos no colisionan
            if _tapa(ruta_prev, ruta):
                tapadas.append(
                    f"{metodo.upper()} {ruta} (línea {linea}) la captura "
                    f"{ruta_prev} (línea {linea_prev})"
                )
    assert not tapadas, (
        "Rutas inalcanzables — devolverán 200 con el cuerpo del endpoint equivocado:\n  "
        + "\n  ".join(tapadas)
        + "\nMueve la ruta estática POR ENCIMA de la que tiene parámetro."
    )


def test_el_caso_concreto_que_lo_destapo():
    """Ancla el arreglo que motivó el fichero, por si alguien reordena sin querer."""
    posiciones = {ruta: linea for metodo, ruta, linea in _rutas() if metodo == "get"}
    assert posiciones["/analyst/ideas"] < posiciones["/analyst/{symbol}"]


def test_el_detector_funciona():
    """Un test que solo pasa no demuestra que sepa fallar."""
    assert _tapa("/analyst/{symbol}", "/analyst/ideas") is True
    assert _tapa("/a/{x}/b", "/a/uno/b") is True
    # Distinta longitud, distinto prefijo, o las dos estáticas: no se pisan.
    assert _tapa("/analyst/{symbol}", "/analyst/ideas/extra") is False
    assert _tapa("/otro/{symbol}", "/analyst/ideas") is False
    assert _tapa("/analyst/ideas", "/analyst/ideas") is False


def test_la_ruta_de_estimar_comisiones_existe():
    """Se llama desde el aviso de ventas sin comisión; sin ruta, el botón daría 404."""
    assert ("post", "/cartera/estimar-comisiones") in {(m, r) for m, r, _ in _rutas()}


def test_la_ruta_de_agrupar_sector_existe():
    assert ("post", "/cartera/agrupar-sector") in {(m, r) for m, r, _ in _rutas()}


def test_la_ruta_de_compra_multinivel_no_la_tapa_la_de_borrar():
    """`/cartera/compras/multinivel` y `/cartera/compras/{id}` comparten prefijo; si la del
    id se registrara antes, «multinivel» se leería como un id."""
    rutas = [(m, r) for m, r, _ in _rutas()]
    assert ("post", "/cartera/compras/multinivel") in rutas
