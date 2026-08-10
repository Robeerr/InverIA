"""Toda ruta HTTP exige sesión salvo las de una lista blanca explícita.

Este test existe porque la auditoría encontró 27 endpoints sin credencial que se habían
ido colando de uno en uno a lo largo del tiempo: nadie los abrió a propósito, simplemente
se añadía una ruta nueva copiando otra y la dependencia de auth no viajaba en la copia.
Entre ellos había cuatro de ESCRITURA (watchlist y alertas), o sea que cualquiera que
conociera la URL del backend podía modificar datos, y otros que publicaban el Cerebro
(destilado de un canal de pago), el track record y el historial.

La forma de que no vuelva a pasar no es revisarlo otra vez dentro de un año: es que la
ruta nueva sin auth no pase de CI. Por eso la lista blanca es explícita y este fichero
falla si alguien añade una ruta abierta sin justificarla aquí.

Se inspecciona el árbol de dependencias REAL de FastAPI, no el texto del fichero: un test
por expresión regular pasaría con código roto que casualmente contenga la cadena correcta.

Los WebSocket no son APIRoute y no salen aquí — precisamente así se escapó `/ws/quote`
en las rondas anteriores. Los cubre tests/test_ws_auth.py.

Ejecutar:  cd backend && pytest tests/ -v
"""
import re

import pytest

fastapi = pytest.importorskip("fastapi", reason="requiere fastapi")
from fastapi.routing import APIRoute  # noqa: E402

import auth  # noqa: E402
import server  # noqa: E402


# ── Lista blanca ──────────────────────────────────────────────────────────────
# Cada entrada necesita un motivo. Si añades una, escribe por qué puede ser pública.
RUTAS_PUBLICAS = {
    "/": "Health check de Render en la raíz del dominio.",
    "/api/": "Identificación del servicio; no devuelve datos.",
    "/api/health": "Sonda de vida de Render y del monitor de uptime.",
    "/api/auth/login": "Es la puerta: pedirle sesión no tendría sentido.",
}

# Ingesta y mantenimiento máquina-a-máquina: no usan JWT porque las llama un servicio (el
# conector de email, un enlace desde el móvil), no un navegador con sesión. Van con secreto
# compartido `INBOUND_SECRET`, y abajo se comprueba que la validación es a prueba de fallos.
RUTAS_POR_TOKEN = {
    "/api/inbound/news/ingest",
    "/api/telegram/status",
    "/api/telegram/login/start",
    "/api/telegram/login/code",
    "/api/telegram/dialogs",
    "/api/telegram/capture",
    "/api/inbound/newsletter",
    "/api/inbound/newsletter/backfill-knowledge",
    "/api/inbound/newsletter/dedupe-knowledge",
    "/api/inbound/newsletter/dedupe-knowledge-llm",
    "/api/inbound/newsletter/fix-encoding",
    "/api/inbound/newsletter/knowledge",
    "/api/inbound/newsletter/debug",
}


def _exige_sesion(route) -> bool:
    """¿El árbol de dependencias de esta ruta acaba llamando a get_current_user?

    Recursivo a propósito: la dependencia puede venir anidada dentro de otra, y mirar
    solo el primer nivel daría un falso negativo el día que alguien agrupe las auth.
    """
    pendientes = [route.dependant]
    vistos = set()
    while pendientes:
        dep = pendientes.pop()
        if id(dep) in vistos:
            continue
        vistos.add(id(dep))
        if getattr(dep, "call", None) is auth.get_current_user:
            return True
        pendientes.extend(getattr(dep, "dependencies", []) or [])
    return False


def _rutas_api():
    """Todas las rutas HTTP de la app, vengan de donde vengan.

    Hay que mirar `api_router` además de `app`: FastAPI monta el router de forma diferida,
    así que `app.routes` solo enseña una ruta y las 95 reales viven en el router. Recorrer
    solo `app.routes` daría un test que pasa siempre sin comprobar nada — el peor resultado
    posible para un test de seguridad.
    """
    vistas, rutas = set(), []
    for r in list(server.api_router.routes) + list(server.app.routes):
        if isinstance(r, APIRoute) and r.path not in vistas:
            vistas.add(r.path)
            rutas.append(r)
    return rutas


def test_ninguna_ruta_queda_abierta_sin_justificar():
    abiertas = []
    for route in _rutas_api():
        if route.path in RUTAS_PUBLICAS or route.path in RUTAS_POR_TOKEN:
            continue
        if not _exige_sesion(route):
            metodos = ",".join(sorted(route.methods - {"HEAD", "OPTIONS"}))
            abiertas.append(f"{metodos} {route.path}")
    assert not abiertas, (
        "Estas rutas no exigen sesión y no están en la lista blanca:\n  "
        + "\n  ".join(sorted(abiertas))
        + "\n\nAñade `_user: str = Depends(auth.get_current_user)` a la firma, o "
          "justifícalas en RUTAS_PUBLICAS si de verdad deben ser públicas."
    )


def test_las_rutas_de_escritura_exigen_sesion():
    """Separado del anterior para que el fallo se lea distinto: una lectura abierta filtra;
    una escritura abierta deja que un tercero te cambie los datos."""
    sin_auth = []
    for route in _rutas_api():
        if route.path in RUTAS_PUBLICAS or route.path in RUTAS_POR_TOKEN:
            continue
        if not (route.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if not _exige_sesion(route):
            sin_auth.append(f"{','.join(sorted(route.methods))} {route.path}")
    assert not sin_auth, "Escritura sin sesión:\n  " + "\n  ".join(sorted(sin_auth))


@pytest.mark.parametrize("ruta", sorted(RUTAS_POR_TOKEN))
def test_las_rutas_por_token_existen(ruta):
    """Que la lista blanca no se quede con entradas fantasma: una ruta que se renombra y
    se olvida aquí convierte la excepción en una puerta abierta para su sucesora."""
    assert any(r.path == ruta for r in _rutas_api()), f"{ruta} ya no existe: quítala de la lista"


@pytest.mark.parametrize("token", ["", "basura", "otro-secreto"])
def test_sin_INBOUND_SECRET_la_ingesta_deniega(monkeypatch, token):
    """A prueba de fallos, comprobado ejecutándolo: si la variable de entorno no está
    puesta, hay que DENEGAR. La alternativa —dejar pasar cuando no hay secreto— abriría
    los endpoints de ingesta justo el día que alguien se olvida de configurarla, que es
    exactamente cuando nadie está mirando."""
    monkeypatch.delenv("INBOUND_SECRET", raising=False)
    with pytest.raises(fastapi.HTTPException) as exc:
        server._check_inbound_token(token)
    assert exc.value.status_code == 401


def test_con_INBOUND_SECRET_solo_pasa_el_token_correcto(monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", "secreto-de-test")
    server._check_inbound_token("secreto-de-test")  # no lanza
    for malo in ("", "secreto-de-tes", "SECRETO-DE-TEST"):
        with pytest.raises(fastapi.HTTPException):
            server._check_inbound_token(malo)


def test_la_validacion_del_token_esta_en_un_solo_sitio():
    """Todas las rutas por token pasan por `_check_inbound_token`, ninguna se lo copia.

    Estaba duplicada literalmente en seis endpoints. Con la comprobación repetida, endurecerla
    —como se acaba de hacer con la comparación de tiempo constante— exige acordarse de los seis,
    y basta olvidar uno para que la mejora sea mentira. Con una sola copia, o están todos o no
    está ninguno.
    """
    with open(server.__file__, encoding="utf-8") as fh:
        src = fh.read()
    assert "if secret and token != secret" not in src, (
        "anti-patrón: valida solo cuando hay secreto y abre de par en par cuando no lo hay"
    )
    # Nadie fuera del helper vuelve a comparar el secreto a mano.
    assert len(re.findall(r"if not secret or token != secret", src)) == 0
    # Y el helper se usa al menos una vez por cada ruta que depende de él.
    usos = len(re.findall(r"_check_inbound_token\(token\)", src))
    assert usos >= 12, f"solo {usos} rutas llaman al validador; hay {len(RUTAS_POR_TOKEN)} por token"


def test_el_token_se_compara_en_tiempo_constante():
    """`!=` sobre cadenas sale antes cuanto antes difieran, y ese tiempo es medible. El
    secreto de ingesta no caduca ni se rota solo, así que hay intentos infinitos para
    adivinarlo carácter a carácter."""
    with open(server.__file__, encoding="utf-8") as fh:
        src = fh.read()
    assert "hmac.compare_digest" in src
    assert "if provided != secret" not in src, "el webhook de newsletter compara a mano"


def test_el_endpoint_de_sesion_actual_exige_sesion():
    """Centinela del propio mecanismo: si /auth/me pasara sin token, el test de arriba
    estaría midiendo algo que ya no protege nada."""
    ruta = next(r for r in _rutas_api() if r.path == "/api/auth/me")
    assert _exige_sesion(ruta)
