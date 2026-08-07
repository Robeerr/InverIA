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
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/inveria_test")
os.environ.setdefault("DB_NAME", "inveria_test")
# Sin credenciales de proveedores: los tests no deben poder salir a Internet por accidente.
os.environ.setdefault("JWT_SECRET", "test-secret-no-usar-en-produccion")
