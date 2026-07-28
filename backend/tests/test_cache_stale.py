"""Tests de servir-caducado-y-refrescar (_TTLCache.get_stale).

Sin esto, cada 5 minutos el siguiente que abriera un ticker pagaba la carga completa del
dashboard: 7 fuentes externas, hasta 8s cada una. Con esto solo la paga quien lo abre por
primera vez; el resto recibe la respuesta anterior al instante mientras se recalcula detrás.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import re


class _Reloj:
    """_TTLCache usa _time.time(); lo sustituimos para no dormir en los tests."""
    def __init__(self): self.ahora = 1000.0
    def time(self): return self.ahora
    def avanzar(self, s): self.ahora += s


def _cargar_cache_aislada():
    """Extrae _TTLCache del fuente y lo ejecuta aislado: importar server entero arrastra
    FastAPI, Mongo y los workers de fondo."""
    ruta = os.path.join(os.path.dirname(__file__), "..", "server.py")
    with open(ruta, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"^class _TTLCache:.*?(?=^_cache = )", src, re.S | re.M)
    assert m, "no se encontró _TTLCache en server.py"
    reloj = _Reloj()
    ns = {"_time": reloj}
    exec(m.group(0), ns)
    return ns["_TTLCache"](), reloj


def test_devuelve_fresco_dentro_del_ttl():
    c, reloj = _cargar_cache_aislada()
    c.set("k", "v", ttl=300)
    val, fresco = c.get_stale("k", max_age=1800)
    assert (val, fresco) == ("v", True)


def test_sirve_caducado_marcandolo_como_no_fresco():
    """El caso que da la sensación de instantáneo: pasado el TTL pero dentro del margen,
    se devuelve el valor viejo para no hacer esperar a nadie."""
    c, reloj = _cargar_cache_aislada()
    c.set("k", "v", ttl=300)
    reloj.avanzar(600)                      # caducado (>300) pero joven (<1800)
    val, fresco = c.get_stale("k", max_age=1800)
    assert val == "v", "debería seguir sirviéndose"
    assert fresco is False, "y avisar de que toca refrescar"


def test_descarta_lo_demasiado_viejo():
    c, reloj = _cargar_cache_aislada()
    c.set("k", "v", ttl=300)
    reloj.avanzar(2000)                     # supera max_age
    assert c.get_stale("k", max_age=1800) == (None, False)


def test_lo_demasiado_viejo_se_purga():
    """No basta con no devolverlo: hay que soltarlo o la caché acumula basura."""
    c, reloj = _cargar_cache_aislada()
    c.set("k", "v", ttl=300)
    reloj.avanzar(2000)
    c.get_stale("k", max_age=1800)
    assert "k" not in c._store


def test_clave_inexistente():
    c, _ = _cargar_cache_aislada()
    assert c.get_stale("no-existe", max_age=1800) == (None, False)


def test_get_normal_sigue_sin_devolver_caducados():
    """get() no debe heredar el comportamiento nuevo: hay sitios que dependen de que
    devuelva None cuando algo caduca."""
    c, reloj = _cargar_cache_aislada()
    c.set("k", "v", ttl=300)
    reloj.avanzar(600)
    assert c.get("k") is None


def test_existe_el_candado_anti_estampida():
    """Si el usuario cambia de ticker y vuelve, o tiene varias pestañas, no deben lanzarse
    N recálculos del mismo símbolo a la vez."""
    ruta = os.path.join(os.path.dirname(__file__), "..", "server.py")
    with open(ruta, encoding="utf-8") as fh:
        src = fh.read()
    assert "_refrescos_en_curso" in src
    assert "if cache_key in _refrescos_en_curso:" in src, "falta la guarda anti-estampida"
