"""Entorno mínimo para que `import server` funcione en los tests.

server.py aborta al importarse si no hay MONGO_URL (a propósito: en producción arrancar sin
base de datos es peor que no arrancar). Eso dejaba el módulo entero fuera del alcance de los
tests, y por eso varios comprueban el CÓDIGO FUENTE con expresiones regulares en vez del
comportamiento — que es mucho peor test: pasa con código roto que casualmente contiene el
texto correcto.

Con estas variables el módulo se importa sin tocar nada externo: el cliente de Mongo de
Motor no abre conexión hasta la primera consulta, así que una URL falsa es inofensiva
mientras los tests no consulten la base de datos (no lo hacen).
"""
import asyncio
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/inveria_test")
os.environ.setdefault("DB_NAME", "inveria_test")
# Sin credenciales de proveedores: los tests no deben poder salir a Internet por accidente.
os.environ.setdefault("JWT_SECRET", "test-secret-no-usar-en-produccion")


@pytest.fixture(autouse=True)
def bucle_de_eventos_limpio():
    """Un bucle de eventos nuevo para cada test, y el anterior restaurado al terminar.

    Sin esto los tests se contaminan entre sí de una forma difícil de ver: `asyncio.run()`
    deja el hilo SIN bucle actual al acabar, así que un test que lo use hace fallar a
    cualquier test POSTERIOR que llame a `asyncio.get_event_loop()`. Y como cada fichero
    pasa por separado, el fallo solo aparece al ejecutar la suite entera y parece venir del
    test equivocado — el que falla no es el que rompe nada.
    """
    try:
        anterior = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        anterior = None
    bucle = asyncio.new_event_loop()
    asyncio.set_event_loop(bucle)
    try:
        yield bucle
    finally:
        try:
            bucle.close()
        except Exception:
            pass
        asyncio.set_event_loop(anterior)
