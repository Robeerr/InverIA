"""Un Mongo sin primario no puede tumbar el arranque.

QUÉ PASÓ, Y POR QUÉ ESTE FICHERO EXISTE

El 14-09-2026 a las 11:49 el despliegue de Render murió así:

    pymongo.errors.ServerSelectionTimeoutError: No primary available for writes,
    Timeout: 5.0s, topology_type: ReplicaSetNoPrimary,
    servers: [...RSSecondary..., ...Unknown..., ...RSSecondary...]
    ERROR: Application startup failed. Exiting.
    ==> Exited with status 3

Atlas estaba en una elección: un nodo caído y dos secundarios, ningún primario. Crear un
índice es una ESCRITURA, y la primera del arranque reventó. Render reintentó y el segundo
arranque funcionó — pero hubo un despliegue caído por algo que dura segundos y que no
tenía nada que ver con el código desplegado.

LO QUE ESTOS TESTS FIJAN

  · que un fallo al crear índices NO impida arrancar. Ya existen de arranques
    anteriores y `create_index` es idempotente: no volver a crearlos no rompe nada;
  · que se reintente UNA vez, porque una elección se resuelve en decenas de segundos y
    el timeout salta a los cinco — ese reintento habría evitado la caída;
  · que la degradación sea VISIBLE. Sin los índices únicos, las garantías que dependen
    de ellos dejan de estar aseguradas por la base de datos, y eso no puede quedarse en
    un log que nadie lee.

SE LEE EL CÓDIGO Y NO SE EJECUTA EL ARRANQUE

Levantar el `lifespan` de verdad arrastra diecisiete workers, media docena de fuentes
externas y una conexión a Mongo. Lo que aquí se protege es la ESTRUCTURA —que la
creación de índices esté dentro de un try, que haya un reintento acotado, que el estado
salga por `/health`— y eso se ve mejor en el árbol sintáctico.
"""
import ast
import os
import sys

# Normalizada: una ruta con `..` dentro deja `server.__file__` sin resolver, y hay
# tests que derivan rutas del frontend a partir de él.
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

import pytest

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server.py")
with open(RUTA, encoding="utf-8") as f:
    FUENTE = f.read()
ARBOL = ast.parse(FUENTE)


def _funcion(nombre, arbol=None):
    for nodo in ast.walk(arbol or ARBOL):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"`{nombre}` ya no existe en server.py: revisa este test")


def _indices_en(nodo):
    return [n for n in ast.walk(nodo)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "create_index"]


def test_TODOS_los_indices_se_crean_por_UNA_sola_puerta():
    """El fallo de Render: la PRIMERA escritura sin primario mató el arranque entero.
    Basta con que un solo `create_index` quede fuera de la puerta protegida para que
    vuelva a pasar.

    Dos versiones equivocadas antes de esta, y las dos por mirar la forma en vez del
    efecto. La primera buscaba los `create_index` dentro del `try` y contaba veintidós
    fuera: viven en una función anidada y lo que el `try` envuelve es la LLAMADA. La
    segunda exigía que TODOS estuvieran en esa función, y señaló uno que ya estaba a
    salvo dentro de otro bloque protegido.

    Lo que importa no es dónde viven, sino que ninguno pueda tumbar el arranque.
    """
    lifespan = _funcion("lifespan")
    puerta = _funcion("_crear_indices", lifespan)
    todos = _indices_en(lifespan)
    assert todos, "si ya no se crean índices aquí, este guardián no vigila nada"

    # Protegido = dentro de la puerta común, O dentro de su propio try. La segunda forma
    # también vale y existe: el índice del cerebro vive en el bloque que carga la base de
    # conocimiento, que ya se traga sus errores. Exigir que TODOS estuvieran en la misma
    # función habría obligado a mover código que ya estaba bien.
    seguros = {n.lineno for n in _indices_en(puerta)}
    for t in ast.walk(lifespan):
        if isinstance(t, ast.Try):
            seguros |= {n.lineno for n in _indices_en(t)}

    sueltos = [n.lineno for n in todos if n.lineno not in seguros]
    assert not sueltos, f"índices sin proteger en las líneas {sueltos}"


def test_la_puerta_de_los_indices_SOLO_se_llama_dentro_de_un_try():
    lifespan = _funcion("lifespan")
    llamadas = [n for n in ast.walk(lifespan)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_crear_indices"]
    protegidas = [n for t in ast.walk(lifespan) if isinstance(t, ast.Try)
                  for n in ast.walk(t)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "_crear_indices"]
    assert llamadas and len(llamadas) == len(protegidas)


def test_el_arranque_SIGUE_aunque_los_indices_fallen():
    """No hay `raise` en el manejador: se registra y se continúa. Los índices ya existen
    de arranques anteriores y `create_index` es idempotente."""
    lifespan = _funcion("lifespan")
    for t in ast.walk(lifespan):
        llama = [n for n in ast.walk(t)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "_crear_indices"]
        if not isinstance(t, ast.Try) or not llama:
            continue
        for manejador in t.handlers:
            assert not [n for n in ast.walk(manejador) if isinstance(n, ast.Raise)], \
                "el manejador vuelve a lanzar: el arranque seguiría muriendo"


def test_se_REINTENTA_pero_no_indefinidamente():
    """Una elección de Atlas se resuelve en decenas de segundos y el timeout salta a los
    cinco: un reintento habría evitado la caída. Un bucle sin tope, en cambio, dejaría la
    aplicación sin arrancar mientras Mongo esté caído."""
    cuerpo = ast.get_source_segment(FUENTE, _funcion("lifespan"))
    assert "for intento in (1, 2)" in cuerpo, "el reintento tiene que estar acotado"
    assert "while True" not in cuerpo.split("opportunities.set_db")[0]


def test_la_espera_del_reintento_es_MAYOR_que_el_timeout_de_mongo():
    """Reintentar antes de que la elección termine solo gasta el intento."""
    import server
    assert server.ESPERA_REINTENTO_INDICES >= 10


def test_el_fallo_de_los_indices_SE_VE_desde_fuera():
    """Sin los índices únicos, las garantías que dependen de ellos —una foto por símbolo
    y día, una versión de tesis por número, un evento por id— dejan de estar aseguradas
    por Mongo. Eso no puede quedarse en un log."""
    salud = ast.get_source_segment(FUENTE, _funcion("health"))
    assert "_INDICES" in salud, "`/health` tiene que decir si los índices están puestos"


def test_el_estado_de_los_indices_empieza_SIN_SABERSE():
    """`None` mientras no se ha intentado. Un `True` por defecto diría que están puestos
    antes de haberlo comprobado."""
    import server
    assert hasattr(server, "_INDICES")


@pytest.mark.parametrize("unico", [
    "intel_eventos", "intel_cursores", "intel_uso_ia", "cartera_historico", "isin_map",
])
def test_los_indices_UNICOS_siguen_declarandose(unico):
    """El arreglo no puede haberse llevado por delante ninguna garantía: siguen todos,
    solo que ahora dentro del try."""
    assert f"db.{unico}.create_index" in FUENTE
