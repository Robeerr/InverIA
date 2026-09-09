"""El sondeo de EDGAR. Una medición que decide una arquitectura.

QUÉ PROTEGE ESTE FICHERO

El sondeo existe para tomar una decisión de diseño con datos reales en vez de con una
estimación. Eso solo sirve si la medición es honesta, y hay tres formas de que no lo sea:

  1. MEDIR LO QUE NO VIAJA. Con gzip, el JSON descomprimido puede ser cinco veces lo que
     de verdad se descargó. Usar esa cifra descartaría un diseño viable.
  2. PREGUNTAR CON CABECERAS INVENTADAS. Un `If-Modified-Since` con una fecha que no salió
     del servidor puede devolver un 304 que no demuestra nada sobre su caché.
  3. REDONDEAR EL VEREDICTO. Dos de tres no es que sí: bastaría una empresa que no cachea
     para que su JSON entero entrara en cada vuelta, y no sabríamos cuál.

Y una cuarta que no es de honestidad sino de alcance: que el sondeo escriba algo. Es una
medición previa a un cambio que todavía no está aprobado.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import intel_sec_sondeo as sondeo


def _resp(http=200, transferidos=180_000, descomprimidos=900_000, ms=340,
          etag='W/"abc"', last_modified="Tue, 09 Sep 2026 12:00:00 GMT",
          cache_control="max-age=0, no-cache"):
    return {"http": http, "ms": ms, "bytes_transferidos": transferidos,
            "content_length": transferidos, "bytes_descomprimidos": descomprimidos,
            "compresion": "gzip",
            "cache": {"etag": etag, "last_modified": last_modified,
                      "cache_control": cache_control, "age": None}}


def _caso(symbol="NVDA", cik=1045810, segunda=None, error=None):
    return {"symbol": symbol, "cik": cik, "url": "https://data.sec.gov/…",
            "primera": _resp(), "segunda": segunda, "error": error,
            "condicionales_enviadas": {"If-None-Match": 'W/"abc"'}}


def _con_304():
    return _caso(segunda=_resp(http=304, transferidos=400, descomprimidos=0, ms=90))


# ── Las cabeceras condicionales son EXACTAMENTE las que dio el servidor ──────

def test_se_repite_con_el_etag_y_la_fecha_QUE_DIO_EL_SERVIDOR():
    cond = sondeo.condicionales({"etag": 'W/"abc"',
                                 "last_modified": "Tue, 09 Sep 2026 12:00:00 GMT"})
    assert cond == {"If-None-Match": 'W/"abc"',
                    "If-Modified-Since": "Tue, 09 Sep 2026 12:00:00 GMT"}


def test_sin_cabeceras_de_cache_NO_se_inventa_ninguna():
    """Preguntar con una fecha que no salió del servidor podría devolver un 304 que no
    demuestra nada sobre su caché. Es la trampa más fácil de colar en una medición."""
    assert sondeo.condicionales({}) == {}
    assert sondeo.condicionales({"etag": None, "last_modified": None}) == {}


def test_si_solo_hay_una_de_las_dos_se_manda_esa():
    assert sondeo.condicionales({"etag": 'W/"x"'}) == {"If-None-Match": 'W/"x"'}
    assert sondeo.condicionales({"last_modified": "ayer"}) == {"If-Modified-Since": "ayer"}


# ── El veredicto no redondea ─────────────────────────────────────────────────

def test_las_TRES_con_304_apoyan_el_diseño():
    v = sondeo.veredicto([_con_304(), _con_304(), _con_304()])
    assert v["funciona"] is True and v["veredicto"] == "APOYA"


def test_DOS_DE_TRES_no_es_que_si():
    """Una sola empresa que no cachee descargaría su JSON entero en cada vuelta, y no
    sabríamos cuál hasta desplegarlo. El diseño se sostiene o no se sostiene."""
    v = sondeo.veredicto([_con_304(), _con_304(), _caso(segunda=_resp(http=200))])
    assert v["funciona"] is False and v["veredicto"] == "PARCIAL"


def test_ninguna_con_304_tumba_el_diseño():
    v = sondeo.veredicto([_caso(segunda=_resp(http=200))] * 3)
    assert v["funciona"] is False and v["veredicto"] == "NO_APOYA"


def test_si_no_llego_a_medirse_nada_NO_se_dice_que_falla():
    """«No pude medir» y «he medido y no funciona» son cosas distintas, y confundirlas
    descartaría el diseño por un fallo de red."""
    v = sondeo.veredicto([_caso(error="timeout")] * 3)
    assert v["veredicto"] == "SIN_DATOS" and v["funciona"] is False


def test_una_empresa_sin_medir_impide_el_APOYA():
    """Con dos medidas y una caída, el veredicto no puede ser que sí: falta un tercio de
    la evidencia."""
    v = sondeo.veredicto([_con_304(), _con_304(), _caso(error="timeout")])
    assert v["funciona"] is False


# ── La proyección usa lo que VIAJA, no lo que ocupa ──────────────────────────

def test_la_proyeccion_se_calcula_con_los_bytes_TRANSFERIDOS():
    """Con gzip, el JSON descomprimido es varias veces lo que se descargó. Usar esa cifra
    descartaría un diseño perfectamente viable por un factor de cinco."""
    p = sondeo.proyeccion([_con_304()] * 3, en_cartera=15, en_watchlist=36)
    assert p["bytes_medios_primera"] == 180_000      # y no 900.000
    assert p["bytes_medios_segunda"] == 400


def test_se_devuelven_LOS_DOS_escenarios_siempre():
    """El de «sin caché condicional» es el que hay que mirar si el sondeo sale mal.
    Tenerlo ya calculado evita decidir la arquitectura con una cifra de memoria."""
    p = sondeo.proyeccion([_con_304()] * 3, en_cartera=15, en_watchlist=36)
    assert p["mb_dia_con_condicional"] < p["mb_dia_sin_condicional"]
    # El orden de magnitud es el argumento entero: tres órdenes de diferencia.
    assert p["mb_dia_sin_condicional"] / p["mb_dia_con_condicional"] > 100


def test_los_dos_carriles_van_en_los_supuestos():
    """La cadencia no puede quedar implícita: es la mitad de la propuesta."""
    p = sondeo.proyeccion([_con_304()] * 3, en_cartera=15, en_watchlist=36)
    assert p["supuestos"]["cada_cartera_min"] == 5
    assert p["supuestos"]["cada_watchlist_min"] == 30
    assert p["peticiones_por_ciclo"] == 21.0


def test_sin_medidas_la_proyeccion_dice_None_y_no_cero():
    """Cero MB al día se leería como «no gasta nada», que es la conclusión contraria a
    «no lo he podido medir»."""
    p = sondeo.proyeccion([_caso(error="timeout")], en_cartera=15, en_watchlist=36)
    assert p["mb_dia_con_condicional"] is None


def test_la_carga_sobre_la_sec_se_expresa_como_porcentaje_de_su_limite():
    p = sondeo.proyeccion([_con_304()] * 3, en_cartera=15, en_watchlist=36)
    assert 0 < p["porcentaje_del_limite_sec"] < 5      # muy por debajo de las 10/s


# ── Alcance: esto MIDE, no cambia nada ───────────────────────────────────────

def test_el_sondeo_no_escribe_en_la_base_de_datos():
    """Es una medición previa a un cambio que todavía no está aprobado. Si tocara Mongo,
    dejaría de ser una prueba y pasaría a ser media migración."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "intel_sec_sondeo.py"), encoding="utf-8").read()
    for escritura in ("update_one", "insert_one", "delete_", "replace_one", "db["):
        assert escritura not in src, f"el sondeo escribe: {escritura}"


def test_el_sondeo_no_modifica_el_connector():
    """Solo lee de `intel_sec`: la identificación y la tabla de tickers. Medir con otras
    cabeceras sería medir algo distinto de lo que se va a construir."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "intel_sec_sondeo.py"), encoding="utf-8").read()
    assert "sec._cabeceras()" in src
    assert "sec." in src and "sec.FORMULARIOS =" not in src
    for mutacion in ("sec.INTERVALO =", "sec.URL_FEED =", "setattr(sec"):
        assert mutacion not in src


def test_sin_identificacion_no_se_sondea():
    """Misma regla que el connector: sin SEC_USER_AGENT no se toca la red, tampoco para
    medir."""
    import asyncio
    os.environ.pop("SEC_USER_AGENT", None)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        asyncio.run(sondeo.sondear([(1045810, "NVDA")]))


def test_son_seis_peticiones_y_no_mas():
    """Tres empresas, dos peticiones cada una. Sondear las 51 sería gastar peticiones en
    confirmar lo mismo diecisiete veces."""
    assert sondeo.CUANTOS == 3
