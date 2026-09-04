"""Un campo declarado en `signal_table` pero no en la API se descarta EN SILENCIO.

QUÉ PASÓ

`categoria_degiro` —la letra A-D del modelo de margen de DEGIRO— se añadió a las listas
blancas de `signal_table` y a `_make_entry`. Todo correcto por ese lado. Pero no se declaró
en `SignalEntryUpdate`, y Pydantic descarta los campos que no conoce sin decir nada: el
PATCH salía con 200, la pantalla no daba error, y el valor no llegaba a la base de datos.
Desde fuera parecía que el desplegable "no hacía nada".

Es la peor forma de fallo: sin excepción, sin log, sin código de error. Y ya había pasado
antes en esta misma casa —un campo nuevo que la capa de datos aceptaba y la API tiraba—,
así que aquí no se prueba EL campo: se prueba la correspondencia entera.

Ejecutar:  cd backend && pytest tests/test_campos_no_se_pierden.py -v
"""
import pytest

import server
import signal_table


@pytest.mark.parametrize("nombre,campos,modelo", [
    ("ALLOWED_UPDATE", signal_table.ALLOWED_UPDATE, server.SignalEntryUpdate),
    ("ALLOWED_CREATE", signal_table.ALLOWED_CREATE, server.SignalEntryCreate),
])
def test_todo_lo_que_la_capa_de_datos_acepta_la_api_lo_declara(nombre, campos, modelo):
    """Si `signal_table` guarda un campo, la API tiene que poder recibirlo.

    Al revés no hace falta: la API puede declarar cosas que la capa de datos filtra a
    propósito —`forzar` es el ejemplo, y tiene su propio test de que NO se persiste—.
    """
    faltan = [c for c in campos if c not in modelo.model_fields]
    assert not faltan, (
        f"{nombre} acepta {faltan}, pero {modelo.__name__} no los declara: Pydantic los "
        f"descartaría en silencio y el PATCH devolvería 200 sin guardar nada.")


def test_la_categoria_de_degiro_esta_en_los_dos_lados():
    """El caso concreto que motivó el test, por si alguien reordena las listas."""
    assert "categoria_degiro" in signal_table.ALLOWED_UPDATE
    assert "categoria_degiro" in signal_table.ALLOWED_CREATE
    assert "categoria_degiro" in server.SignalEntryUpdate.model_fields
    assert "categoria_degiro" in server.SignalEntryCreate.model_fields


def test_no_se_confunde_con_el_campo_riesgo():
    """`riesgo` es la clasificación del inversor del usuario y `categoria_degiro` la del
    bróker. Son dos columnas distintas en la misma tabla y se parecen demasiado."""
    entrada = signal_table._make_entry("TEST", riesgo="alto", categoria_degiro="d")
    assert entrada["riesgo"] == "ALTO"
    assert entrada["categoria_degiro"] == "D"


def test_la_categoria_se_normaliza_a_una_letra():
    """Llega de un desplegable, pero también del importador y de la API."""
    assert signal_table._make_entry("T", categoria_degiro=" c ")["categoria_degiro"] == "C"
    assert signal_table._make_entry("T", categoria_degiro="")["categoria_degiro"] == ""
    assert signal_table._make_entry("T")["categoria_degiro"] == ""


def test_el_sector_de_DEGIRO_va_aparte_del_sector_propio():
    """Son dos datos distintos y machacar uno con el otro pierde el primero: `sector` lo
    rellena el proveedor y es la taxonomía del usuario —la que separa lo que él separa—,
    mientras que `sector_degiro` solo reproduce en qué saco mete el bróker cada acción para
    su límite de concentración, que agrupa mucho más grueso."""
    import signal_table
    assert "sector" in signal_table.ALLOWED_UPDATE
    assert "sector_degiro" in signal_table.ALLOWED_UPDATE
    assert "sector_degiro" in signal_table.ALLOWED_CREATE
    entry = signal_table._make_entry("AAA", sector="TECH GROWTH", sector_degiro="Technology")
    assert entry["sector"] == "TECH GROWTH" and entry["sector_degiro"] == "Technology"
