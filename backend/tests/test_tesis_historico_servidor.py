"""Dónde se registra la tesis, y dónde NO.

LO QUE HAY QUE PROTEGER

El histórico solo se escribe desde el camino frío —`_construir_dashboard`—, nunca desde
`_refrescar_cotizacion`. El motivo es medido, no estético: el refresco vuelve a redactar
LA MISMA tesis con otro precio, y `server` lo hace a propósito para que la cabecera y la
frase no enseñen dos precios distintos. Registrar ahí llenaría el histórico de versiones
idénticas en conclusiones.

La huella ya lo evitaría por sí sola. Tener las dos barreras significa que un error en la
normalización no puede inundar la colección, que es un fallo del que no se vuelve: las
filas de más ya estarían escritas.

ESTOS TESTS LEEN EL CÓDIGO, Y SE DICE POR QUÉ

Ejecutar `_construir_dashboard` de verdad exige montar mercado, indicadores, niveles y
media docena de fuentes externas —`test_dashboard_dependencias` hace eso y le cuesta un
fichero entero—. Lo que aquí se protege no es el cálculo sino DÓNDE está puesta una
llamada, y eso se ve mejor en el árbol sintáctico que a través de seis capas de dobles.
Lo que sí se prueba contra valores —la huella, las versiones, la tolerancia a fallos—
está en `test_tesis_registro.py`.
"""
import ast
import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import tesis_registro as tr

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server.py")
with open(RUTA, encoding="utf-8") as f:
    ARBOL = ast.parse(f.read())


def _funcion(nombre):
    for nodo in ast.walk(ARBOL):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"`{nombre}` ya no existe en server.py: revisa este test")


def _llamadas(nodo, modulo="tesis_registro"):
    """Nombres de las funciones de `modulo` llamadas dentro de ese nodo."""
    fuera = []
    for hijo in ast.walk(nodo):
        if (isinstance(hijo, ast.Call) and isinstance(hijo.func, ast.Attribute)
                and isinstance(hijo.func.value, ast.Name)
                and hijo.func.value.id == modulo):
            fuera.append(hijo.func.attr)
    return fuera


# ── Quién escribe ────────────────────────────────────────────────────────────

def test_el_camino_FRIO_registra_la_tesis():
    assert "guardar_si_cambia" in _llamadas(_funcion("_construir_dashboard"))


def test_el_registro_va_DESPUES_de_cachear_el_dashboard():
    """Son dos viajes a Mongo. Delante del `_cache.set` los pagaba la respuesta: si
    Mongo iba lento, la página tardaba más y tardaba más en quedar disponible para los
    demás. El histórico es lo secundario, así que va detrás.

    Se comprueba por posición en el cuerpo de la función, que es lo que de verdad
    determina quién espera a quién.
    """
    cold = _funcion("_construir_dashboard")
    registro = [n.lineno for n in ast.walk(cold)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "guardar_si_cambia"]
    cacheo = [n.lineno for n in ast.walk(cold)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == "set" and isinstance(n.func.value, ast.Name)
              and n.func.value.id == "_cache"]
    assert registro and cacheo
    assert min(registro) > max(cacheo), "guardar el histórico no puede retrasar la página"


def test_el_refresco_de_cotizacion_NO_registra_NADA():
    """El que vuelve a redactar la misma tesis con otro precio."""
    assert _llamadas(_funcion("_refrescar_cotizacion")) == []


def test_solo_hay_UN_sitio_en_todo_el_servidor_que_escriba():
    """Dos puntos de escritura acabarían divergiendo, y uno de los dos se olvidaría de
    que el refresco no debe registrar."""
    escrituras = [n for n in ast.walk(ARBOL)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and isinstance(n.func.value, ast.Name)
                  and n.func.value.id == "tesis_registro"
                  and n.func.attr == "guardar_si_cambia"]
    assert len(escrituras) == 1


def test_el_registro_va_dentro_de_un_TRY():
    """El histórico es un extra; los datos de la acción son la pantalla. Un fallo de
    Mongo no puede dejar sin página a quien abre una acción.

    `guardar_si_cambia` ya se traga sus propios errores —hay un test que lo prueba con
    valores—, pero este comprueba la segunda red: si alguien la quitara de dentro, el
    `try` de fuera sigue ahí.
    """
    cold = _funcion("_construir_dashboard")
    dentro_de_try = [n for t in ast.walk(cold) if isinstance(t, ast.Try)
                     for n in ast.walk(t)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == "guardar_si_cambia"]
    assert dentro_de_try, "el registro de la tesis tiene que ir dentro de un try"


# ── Quién lee ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nombre", ["tesis_versiones", "tesis_version"])
def test_los_endpoints_del_historico_son_GET(nombre):
    fn = _funcion(nombre)
    metodos = [d.func.attr for d in fn.decorator_list
               if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
    assert metodos == ["get"], f"{nombre} no puede dejar de ser una lectura"


@pytest.mark.parametrize("nombre", ["tesis_versiones", "tesis_version"])
def test_consultar_el_historico_NO_ESCRIBE(nombre):
    """Mirar la pantalla no puede cambiar lo que la pantalla enseña."""
    usadas = set(_llamadas(_funcion(nombre)))
    assert usadas <= {"historial", "version"}, usadas


def test_las_funciones_de_LECTURA_del_modulo_no_escriben():
    """Comprobado sobre el código del propio módulo: ninguna de las tres consultas
    llama a `insert_one` ni a `update_one`."""
    arbol = ast.parse(inspect.getsource(tr))
    for nombre in ("vigente", "historial", "version"):
        fn = next(n for n in ast.walk(arbol)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == nombre)
        llamadas = {h.func.attr for h in ast.walk(fn)
                    if isinstance(h, ast.Call) and isinstance(h.func, ast.Attribute)}
        assert not llamadas & {"insert_one", "update_one", "delete_one", "replace_one"}


# ── El índice que sostiene la concurrencia ───────────────────────────────────

def test_el_historico_tiene_TECHO():
    """`?limite=999999` viajaba tal cual al `.limit()` de Mongo. Mismo patrón que
    `TECHO_EVENTOS` para la lista de eventos."""
    with open(RUTA, encoding="utf-8") as f:
        fuente = f.read()
    assert "TECHO_VERSIONES_TESIS = 200" in fuente
    cuerpo = fuente[fuente.index("async def tesis_versiones"):]
    cuerpo = cuerpo[:cuerpo.index("@api_router")]
    assert "min(int(limite" in cuerpo and "TECHO_VERSIONES_TESIS" in cuerpo


def test_existe_el_indice_UNICO_que_impide_dos_versiones_iguales():
    """Sin él, dos procesos que redactan el mismo símbolo a la vez escriben dos
    «versión 2» y el histórico deja de ser una línea."""
    with open(RUTA, encoding="utf-8") as f:
        fuente = f.read()
    i = fuente.index("tesis_registro.COLECCION].create_index")
    trozo = fuente[i:i + 200]
    assert '("symbol", 1)' in trozo and '("version", -1)' in trozo
    assert "unique=True" in trozo


# ── La foto diaria del laboratorio ───────────────────────────────────────────

def test_el_camino_frio_anota_la_FOTO_del_dia():
    assert "guardar" in _llamadas(_funcion("_construir_dashboard"), "mercado_registro")


def test_la_foto_va_DESPUES_de_cachear_y_dentro_del_TRY():
    """Igual que el registro de la tesis: el histórico es lo secundario, y un fallo de
    Mongo no puede dejar sin página a quien abre una acción."""
    cold = _funcion("_construir_dashboard")
    foto = [n.lineno for n in ast.walk(cold)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "mercado_registro"]
    cacheo = [n.lineno for n in ast.walk(cold)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == "set" and isinstance(n.func.value, ast.Name)
              and n.func.value.id == "_cache"]
    assert foto and min(foto) > max(cacheo)
    dentro = [n for t in ast.walk(cold) if isinstance(t, ast.Try) for n in ast.walk(t)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and isinstance(n.func.value, ast.Name)
              and n.func.value.id == "mercado_registro"]
    assert dentro


def test_el_refresco_de_cotizacion_TAMPOCO_anota_fotos():
    assert _llamadas(_funcion("_refrescar_cotizacion"), "mercado_registro") == []


@pytest.mark.parametrize("nombre", ["laboratorio_cobertura", "laboratorio_fotos"])
def test_los_endpoints_del_laboratorio_son_GET_y_no_escriben(nombre):
    fn = _funcion(nombre)
    metodos = [d.func.attr for d in fn.decorator_list
               if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
    assert metodos == ["get"]
    assert set(_llamadas(fn, "mercado_registro")) <= {"cobertura", "historial"}


def test_la_foto_tiene_indice_UNICO_por_simbolo_y_dia():
    """Es lo que hace que la PRIMERA del día mande. Sin él, dos construcciones del mismo
    dashboard podrían dejar dos fotos del mismo día."""
    with open(RUTA, encoding="utf-8") as f:
        fuente = f.read()
    i = fuente.index("mercado_registro.COLECCION].create_index")
    trozo = fuente[i:i + 200]
    assert '("symbol", 1)' in trozo and '("dia", -1)' in trozo and "unique=True" in trozo


# ── El laboratorio ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("nombre", ["laboratorio_panorama", "laboratorio_experimentos"])
def test_consultar_el_laboratorio_es_GET_y_no_escribe(nombre):
    fn = _funcion(nombre)
    metodos = [d.func.attr for d in fn.decorator_list
               if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
    assert metodos == ["get"]
    assert set(_llamadas(fn, "laboratorio")) <= {"panorama", "experimentos"}


def test_ejecutar_un_experimento_es_POST_y_es_el_UNICO_que_escribe():
    """Escribe en el histórico y descarga decenas de series: lo dispara una persona, no
    un bucle. Mismo criterio que «Investigar ahora»."""
    fn = _funcion("laboratorio_experimento_distancia")
    metodos = [d.func.attr for d in fn.decorator_list
               if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
    assert metodos == ["post"]

    # El invariante NO es «solo hay un escritor»: son dos desde que existe el
    # diagnóstico, y serán más. Lo que tiene que seguir siendo cierto es que TODO el que
    # escribe en el histórico sea un POST — nunca un GET, nunca un bucle.
    escritores = []
    for nodo in ast.walk(ARBOL):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "guardar_experimento" not in _llamadas(nodo, "laboratorio"):
            continue
        escritores.append(nodo.name)
        metodos = [d.func.attr for d in nodo.decorator_list
                   if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
        assert metodos == ["post"], f"{nodo.name} escribe y no es un POST"
    assert escritores, "si ya nadie registra experimentos, este guardián no vigila nada"


def test_NINGUN_worker_ejecuta_el_experimento_por_su_cuenta():
    """No hay bucle que lo lance. Cuando sepamos cuánto tarda y cuánto aporta repetirlo,
    se decidirá si merece un horario — hoy no lo sabemos."""
    lanzamientos = []
    for nodo in ast.walk(ARBOL):
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "create_task"):
            lanzamientos += [n.func.attr for n in ast.walk(nodo)
                             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "guardar_experimento" not in lanzamientos
    assert "laboratorio_experimento_distancia" not in lanzamientos


def test_el_laboratorio_NO_llama_a_ningun_modelo():
    """Todo el cálculo es determinista. Un experimento que dependiera de un LLM no sería
    reproducible, y un resultado que no se puede repetir no es evidencia."""
    import inspect as _i
    import laboratorio
    fuente = _i.getsource(laboratorio)
    for prohibido in ("_run_model", "ai_analysis", "genai", "openai", "gemini"):
        assert prohibido not in fuente, prohibido


def test_el_DIAGNOSTICO_tambien_es_POST_y_no_lo_lanza_ningun_worker():
    fn = _funcion("laboratorio_experimento_distribucion")
    metodos = [d.func.attr for d in fn.decorator_list
               if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
    assert metodos == ["post"]
    lanzamientos = []
    for nodo in ast.walk(ARBOL):
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "create_task"):
            lanzamientos += [n.func.attr for n in ast.walk(nodo)
                             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "ficha_distribucion" not in lanzamientos
