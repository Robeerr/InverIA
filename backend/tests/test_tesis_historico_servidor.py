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
    # Se guarda el TEXTO además del árbol: `ast.get_source_segment` lo necesita para
    # devolver el cuerpo de una función, y varios tests comprueban qué hay dentro.
    FUENTE = f.read()
ARBOL = ast.parse(FUENTE)


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


def test_solo_se_ESCRIBE_en_el_historico_desde_un_POST():
    """El invariante no es cuántos escritores hay —eran uno, luego dos, ahora la
    escritura vive en un ayudante compartido—. Es que a esa escritura solo se llegue
    desde un POST: nunca desde un GET, nunca desde un bucle.

    Se comprueba en dos tramos porque el refactor metió un intermediario: quién llama a
    `guardar_experimento`, y quién llama a ese.
    """
    escritores = [n.name for n in ast.walk(ARBOL)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and "guardar_experimento" in _llamadas(n, "laboratorio")]
    assert escritores, "si ya nadie registra experimentos, este guardián no vigila nada"

    for escritor in escritores:
        llamantes = [n for n in ast.walk(ARBOL)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                             and c.func.id == escritor for c in ast.walk(n))]
        # O el escritor ES el endpoint, o todos los que lo invocan son POST.
        propios = [d.func.attr for d in _funcion(escritor).decorator_list
                   if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
        if propios:
            assert propios == ["post"], f"{escritor} escribe y no es un POST"
            continue
        assert llamantes, f"nadie llama a {escritor}: entonces no debería escribir"
        for fn in llamantes:
            metodos = [d.func.attr for d in fn.decorator_list
                       if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
            assert metodos == ["post"], f"{fn.name} llega a la escritura y no es un POST"


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


def test_los_TRES_experimentos_comparten_el_mismo_cuerpo():
    """Los tres miden sobre las MISMAS observaciones y solo cambian cómo las agregan.
    Tres copias del cuerpo habrían divergido, y entonces el diagnóstico y el corte
    temporal dejarían de explicar el experimento que dicen explicar."""
    for nombre in ("laboratorio_experimento_distancia",
                   "laboratorio_experimento_distribucion",
                   "laboratorio_experimento_periodo"):
        fn = _funcion(nombre)
        llamadas = [n.func.id for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        assert "_experimento_distancia" in llamadas, nombre
        # Y ninguno baja datos por su cuenta.
        assert "get_stock_data" not in _llamadas(fn, "market_data")


def test_la_replica_corre_FUERA_de_tu_universo():
    """Si corriera sobre los mismos símbolos, sería el mismo dato mirado dos veces con
    otra métrica — justo lo que el experimento existe para no hacer."""
    fn = _funcion("laboratorio_experimento_aguante_limpio")
    cuerpo = ast.get_source_segment(FUENTE, fn)
    assert "opportunities.UNIVERSE" in cuerpo
    assert "not in mios" in cuerpo, "hay que EXCLUIR watchlist y cartera"
    assert "_simbolos_que_te_importan" in cuerpo


def test_la_replica_se_niega_si_no_queda_muestra_independiente():
    cuerpo = ast.get_source_segment(FUENTE, _funcion("laboratorio_experimento_aguante_limpio"))
    assert "len(universo) < 10" in cuerpo
    assert "SIN_DATOS" in cuerpo


def test_los_DOS_experimentos_de_aguante_usan_el_mismo_motor():
    """Medir con motores distintos haría los resultados incomparables."""
    for nombre in ("laboratorio_experimento_aguante",
                   "laboratorio_experimento_aguante_limpio"):
        cuerpo = ast.get_source_segment(FUENTE, _funcion(nombre))
        assert "backtest.backtest_universe" in cuerpo
        assert "VENTANA_AGUANTE" in cuerpo
