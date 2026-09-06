"""Nada se define dos veces en el mismo fichero.

Python no avisa: la segunda definición pisa a la primera en silencio y lo que revienta es
otra cosa, a veces en otro fichero. Ha pasado dos veces en una tarde —una función `_pct`
que dejó de calcular lo que calculaba, y una constante `CARTERA` de un test que tumbó
cuatro pruebas ajenas— y las dos veces el rastro no llevaba al sitio del error.
"""
import ast
import os

_AQUI = os.path.dirname(__file__)
_RAIZ = os.path.join(_AQUI, "..")


def _ficheros():
    for carpeta in (_RAIZ, _AQUI):
        for n in sorted(os.listdir(carpeta)):
            if n.endswith(".py") and not n.startswith("."):
                yield os.path.join(carpeta, n)


def _repetidos(ruta):
    """Nombres definidos dos veces EN EL NIVEL SUPERIOR del módulo.

    Solo el nivel superior: dentro de una función reasignar es normal, y en una clase o un
    `if/else` de compatibilidad puede ser deliberado.
    """
    with open(ruta, encoding="utf-8") as f:
        arbol = ast.parse(f.read(), filename=ruta)
    vistos, repes = {}, set()
    for nodo in arbol.body:
        nombres = []
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres = [nodo.name]
        elif isinstance(nodo, ast.Assign):
            nombres = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
        for n in nombres:
            # Una constante que se reasigna a sí misma (`X = X + 1`) no cuenta como
            # definición nueva; lo que se busca son dos declaraciones independientes.
            if n in vistos:
                repes.add(n)
            vistos[n] = True
    return sorted(repes)


def test_ninguna_definicion_de_nivel_superior_esta_duplicada():
    fallos = {}
    for ruta in _ficheros():
        repes = _repetidos(ruta)
        if repes:
            fallos[os.path.basename(ruta)] = repes
    assert not fallos, f"definidos dos veces: {fallos}"
