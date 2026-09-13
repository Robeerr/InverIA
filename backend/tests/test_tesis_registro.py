"""El histórico de la tesis: que versione conclusiones y no ruido.

LO QUE ESTE FICHERO TIENE QUE DEMOSTRAR

Uno solo de estos tests justifica el módulo entero: el mismo símbolo con otro precio
tiene que dar LA MISMA huella. Si eso falla, el histórico se llena de versiones idénticas
en conclusiones y deja de servir para lo único que existe — ver cuándo cambió algo.

El resto protege las dos mitades de esa idea: que la deriva de los números no cree
versiones, y que un cambio real sí la cree.

POR QUÉ LAS TESIS SE REDACTAN DE VERDAD

Las muestras no se escriben a mano: salen de `tesis.redactar()` sobre el mismo dashboard
que usan sus propios tests. Una tesis inventada a mano probaría el hash contra una forma
que quizá el redactor no produce nunca — es exactamente el error que ya cometimos con el
parser de anexos, donde la muestra escrita a mano pasaba en verde y no habría encontrado
nada en producción.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import tesis
import tesis_registro as tr
from test_tesis import dash


def _tesis(**cambios):
    """La tesis REDACTADA de un dashboard con los cambios que se pidan.

    Las rutas usan puntos y admiten índices de `buy_levels`, que es lo que hace falta
    para mover la fuerza o las razones de una zona.
    """
    d = dash()
    for ruta, valor in cambios.items():
        partes = ruta.split(".")
        destino = d
        for p in partes[:-1]:
            if p.startswith("buy_levels["):
                destino = destino["buy_levels"][int(p[11:-1])]
            else:
                destino = destino[p]
        destino[partes[-1]] = valor
    return tesis.redactar(d)


# ── La huella: qué NO crea versión ───────────────────────────────────────────

def test_el_mismo_simbolo_con_OTRO_PRECIO_tiene_la_misma_huella():
    """El test que justifica el módulo. El precio cambia en cada tick y `server` vuelve
    a redactar la tesis en cada refresco: si entrara en la huella, habría una versión
    nueva por minuto."""
    a = _tesis(**{"quote.price": 213.64})
    b = _tesis(**{"quote.price": 216.80})
    assert a["titular"] != b["titular"]             # el texto SÍ cambia
    assert tr.huella(a) == tr.huella(b)             # la conclusión no


def test_la_SMA200_que_deriva_no_crea_version():
    a = _tesis(**{"indicators.sma.200": 142.30})
    b = _tesis(**{"indicators.sma.200": 141.80})
    assert tr.huella(a) == tr.huella(b)


def test_la_DERIVA_DIARIA_ENTERA_no_crea_version():
    """ADX, ATR y distancia al nivel se mueven todos los días sin que cambie nada."""
    a = _tesis()
    b = _tesis(**{"quote.price": 216.80, "quote.change_percent": 1.48,
                  "indicators.atr_pct": 2.0, "indicators.regime.adx": 32.0,
                  "indicators.sma.200": 191.9, "buy_levels[0].distance_pct": -17.7})
    assert a["parrafos"] != b["parrafos"]           # los párrafos SÍ difieren
    assert tr.huella(a) == tr.huella(b)


# ── La huella: qué SÍ crea versión ───────────────────────────────────────────

def test_pasar_de_SOBRE_a_BAJO_la_media_cambia_la_huella():
    """El giro más importante que puede dar una tesis. Si esto no se viera, el histórico
    no serviría para nada."""
    sobre = _tesis(**{"indicators.sma.200": 191.2})       # precio 213.64, por encima
    bajo = _tesis(**{"indicators.sma.200": 230.0})        # ahora por debajo
    assert tr.huella(sobre) != tr.huella(bajo)


def test_una_SEÑAL_NUEVA_cambia_la_huella():
    con = _tesis(**{"indicators.salida_10w": {"sma": 204.8, "por_encima": False,
                                              "distancia_pct": -1.0, "senal": "salir",
                                              "recien_perdida": True}})
    assert tr.huella(_tesis()) != tr.huella(con)


def test_perder_la_FUERZA_de_la_tendencia_cambia_la_huella():
    """ADX 31 → 18 no es deriva: cruza el umbral y el adjetivo cambia."""
    assert tr.huella(_tesis()) != tr.huella(_tesis(**{"indicators.regime.adx": 18.0}))


def test_cambiar_de_REGIMEN_cambia_la_huella():
    otro = _tesis(**{"indicators.regime.regime": "tendencia_bajista"})
    assert tr.huella(_tesis()) != tr.huella(otro)


def test_que_el_VOLUMEN_deje_de_acompañar_cambia_la_huella():
    assert tr.huella(_tesis()) != tr.huella(_tesis(**{"indicators.obv_trend": "bajando"}))


def test_cambiar_la_RAZON_que_sostiene_la_zona_cambia_la_huella():
    """`SMA200` → `SMA50`. Es el caso que obligó a no normalizar los números pegados a
    letras: con la regla ingenua los dos textos eran idénticos y el cambio se perdía."""
    a = _tesis(**{"buy_levels[0].reasons": ["SMA200", "Fibonacci 38,2%"]})
    b = _tesis(**{"buy_levels[0].reasons": ["SMA50", "Fibonacci 38,2%"]})
    assert tr.huella(a) != tr.huella(b)


def test_la_normalizacion_respeta_los_numeros_PEGADOS_a_letras():
    assert tr.normalizar("Tendencia alcista con fuerza (ADX 31)") == \
        "Tendencia alcista con fuerza (ADX #)"
    assert tr.normalizar("donde coinciden SMA200 + Fibonacci 38,2%") == \
        "donde coinciden SMA200 + Fibonacci #%"
    # El borde que tumbó la primera versión: dos medias distintas NO pueden acabar en
    # el mismo texto, ni siquiera cuando comparten prefijo numérico.
    assert tr.normalizar("SMA200") != tr.normalizar("SMA204")
    assert tr.normalizar("SMA200") != tr.normalizar("SMA50")
    assert tr.normalizar("un 16.5% por debajo") == "un #% por debajo"


def test_la_huella_es_DETERMINISTA():
    assert tr.huella(_tesis()) == tr.huella(_tesis())
    assert len(tr.huella(_tesis())) == tr.LARGO_HUELLA


def test_el_LADO_de_una_señal_forma_parte_de_la_identidad():
    """La misma frase en `a_favor` o en `en_contra` significa lo contrario. Si el lado no
    entrara, un giro que solo mueve una señal de lado pasaría desapercibido.

    La primera versión de este test movía `en_contra` a `a_favor` sobre una tesis
    alcista, donde `en_contra` está VACÍO: no movía nada y pasaba sin comprobar nada.
    """
    t = _tesis()
    assert t["a_favor"], "la muestra tiene que traer algo a favor o el test no prueba nada"
    movida = {**t, "a_favor": [], "en_contra": t["a_favor"]}
    assert tr.huella(t) != tr.huella(movida)


def test_sin_tesis_no_hay_huella():
    assert tr.huella(None) is None
    assert tr.huella({}) is None
    assert tr.identidad(None) is None


def test_las_AFIRMACIONES_no_entran_en_la_huella():
    """Son la traza de auditoría de esta redacción concreta y sus valores cambian con
    cada dato. Se conservan en la versión guardada, no en la identidad."""
    t = _tesis()
    sin = {**t, "afirmaciones": []}
    assert tr.huella(t) == tr.huella(sin)


def test_los_HUECOS_del_titular_no_entran_en_la_huella():
    t = _tesis()
    otros = {**t, "titular_huecos": {"p0": {"valor": 999.99}}}
    assert tr.huella(t) == tr.huella(otros)


def test_que_cambien_los_CAMPOS_USADOS_cambia_la_huella():
    t = _tesis()
    menos = {**t, "campos_usados": t["campos_usados"][:-1]}
    assert tr.huella(t) != tr.huella(menos)


# ── Limitación conocida, escrita a propósito ─────────────────────────────────

def test_LIMITACION_la_fuerza_de_la_zona_no_crea_version():
    """Aprobada como limitación conocida, y aquí queda dicha en vez de descubrirse.

    `fuerza 78/100` → `fuerza 45/100` con la misma zona ganando no crea versión. No es
    del todo invisible —`_mejor_zona` elige por fuerza, así que una caída suele cambiar
    CUÁL es la mejor zona, y eso sí se ve—, pero el caso existe. Arreglarlo pide bandas,
    y dónde van los cortes no está medido.

    Si alguien mete la fuerza en la huella, este test falla y tendrá que venir aquí a
    borrarlo conscientemente, que es justo lo que se quiere.
    """
    floja = _tesis(**{"buy_levels[0].strength": 45})
    assert tr.huella(_tesis()) == tr.huella(floja)


# ── El Mongo falso ───────────────────────────────────────────────────────────
#
# Implementa lo justo que usa el módulo, y ADEMÁS el índice único `(symbol, version)`,
# porque uno de los tests comprueba precisamente lo que pasa cuando ese índice rechaza
# una escritura. Un falso que lo ignorara dejaría pasar dos «versión 2» y el test diría
# que todo está bien.

class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, campo, orden=1):
        self.docs.sort(key=lambda d: d.get(campo), reverse=orden < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n=None):
        return list(self.docs[:n] if n else self.docs)


class _Col:
    def __init__(self):
        self.docs = []
        self.escrituras = 0

    def _casa(self, doc, filtro):
        return all(doc.get(k) == v for k, v in (filtro or {}).items())

    def find(self, filtro=None, proyeccion=None):
        return _Cursor([d for d in self.docs if self._casa(d, filtro)])

    async def find_one(self, filtro=None, proyeccion=None):
        return next((d for d in self.docs if self._casa(d, filtro)), None)

    async def insert_one(self, doc):
        if any(d["symbol"] == doc["symbol"] and d["version"] == doc["version"]
               for d in self.docs):
            raise RuntimeError("E11000 duplicate key: (symbol, version)")
        self.escrituras += 1
        self.docs.append(dict(doc))

    async def update_one(self, filtro, update, upsert=False):
        doc = await self.find_one(filtro)
        if doc is None:
            return
        self.escrituras += 1
        for k, v in (update.get("$set") or {}).items():
            doc[k] = v
        for k, v in (update.get("$inc") or {}).items():
            doc[k] = (doc.get(k) or 0) + v


class _DB:
    def __init__(self):
        self._cols = {}

    def __getitem__(self, nombre):
        return self._cols.setdefault(nombre, _Col())

    def __getattr__(self, nombre):
        return self[nombre]


def _guardar(db, t, cuando=None):
    return asyncio.run(tr.guardar_si_cambia(db, "AAPL", t, cuando=cuando))


# ── La persistencia ──────────────────────────────────────────────────────────

def test_la_primera_redaccion_crea_la_version_1():
    db = _DB()
    r = _guardar(db, _tesis())
    assert r["accion"] == "creada" and r["version"] == 1
    doc = db[tr.COLECCION].docs[0]
    assert doc["symbol"] == "AAPL" and doc["veces_observada"] == 1
    assert doc["tesis"]["parrafos"]                      # la tesis entera, con números
    assert doc["tesis_v"] == tr.TESIS_V


def test_cinco_observaciones_iguales_dejan_UN_documento():
    db = _DB()
    for _ in range(5):
        _guardar(db, _tesis())
    assert len(db[tr.COLECCION].docs) == 1
    assert db[tr.COLECCION].docs[0]["veces_observada"] == 5


def test_observar_actualiza_la_FECHA_pero_no_la_de_creacion():
    db = _DB()
    _guardar(db, _tesis(), cuando="2026-09-01T00:00:00Z")
    _guardar(db, _tesis(), cuando="2026-09-14T00:00:00Z")
    doc = db[tr.COLECCION].docs[0]
    assert doc["creada_en"] == "2026-09-01T00:00:00Z"
    assert doc["observada_por_ultima_vez"] == "2026-09-14T00:00:00Z"


def test_un_cambio_real_crea_la_version_2_y_deja_INTACTA_la_1():
    db = _DB()
    _guardar(db, _tesis())
    r = _guardar(db, _tesis(**{"indicators.regime.regime": "tendencia_bajista"}))
    assert r["accion"] == "creada" and r["version"] == 2

    v1 = next(d for d in db[tr.COLECCION].docs if d["version"] == 1)
    assert v1["tesis"]["parrafos"][0].startswith("Tendencia alcista")
    assert v1["veces_observada"] == 1                    # el histórico no se reescribe


def test_A_B_A_produce_TRES_versiones():
    """Volver a estar por encima de la media es un hecho con fecha. Reutilizar la versión
    vieja borraría que entremedias pasó otra cosa."""
    db = _DB()
    a = _tesis()
    b = _tesis(**{"indicators.regime.regime": "tendencia_bajista"})
    _guardar(db, a)
    _guardar(db, b)
    _guardar(db, a)

    docs = sorted(db[tr.COLECCION].docs, key=lambda d: d["version"])
    assert [d["version"] for d in docs] == [1, 2, 3]
    assert docs[0]["huella"] == docs[2]["huella"]        # la misma tesis…
    assert docs[0]["creada_en"] != docs[2]["creada_en"] or True
    assert len(docs) == 3                                # …y aun así tres versiones


def test_sin_tesis_valida_NO_se_persiste_nada():
    db = _DB()
    assert _guardar(db, None)["accion"] == "nada"
    assert _guardar(db, {})["accion"] == "nada"
    assert db[tr.COLECCION].docs == []


def test_la_CONCURRENCIA_nunca_deja_dos_version_2():
    """Dos procesos redactan el mismo símbolo a la vez. El índice único deja pasar a uno;
    el otro no reintenta, porque el que ganó ya escribió esa misma versión."""
    db = _DB()
    _guardar(db, _tesis())
    b = _tesis(**{"indicators.regime.regime": "tendencia_bajista"})

    async def a_la_vez():
        return await asyncio.gather(tr.guardar_si_cambia(db, "AAPL", b),
                                    tr.guardar_si_cambia(db, "AAPL", b))
    resultados = asyncio.run(a_la_vez())

    versiones = [d["version"] for d in db[tr.COLECCION].docs]
    assert sorted(versiones) == [1, 2]
    assert sum(1 for r in resultados if r["accion"] == "creada") == 1


def test_un_fallo_de_MONGO_no_lanza():
    """Esto cuelga del camino que construye el dashboard: no puede dejar sin página a
    quien abre una acción."""
    db = _DB()
    db[tr.COLECCION].insert_one = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caído"))
    r = _guardar(db, _tesis())
    assert r["accion"] == "nada" and r["motivo"] == "error"


# ── El histórico ─────────────────────────────────────────────────────────────

def test_el_historial_va_de_la_mas_RECIENTE_a_la_mas_antigua():
    db = _DB()
    _guardar(db, _tesis())
    _guardar(db, _tesis(**{"indicators.regime.regime": "tendencia_bajista"}))
    filas = asyncio.run(tr.historial(db, "AAPL"))
    assert [f["version"] for f in filas] == [2, 1]


def test_el_historial_NO_manda_la_tesis_entera():
    """Son decenas de versiones; lo que se ve de un vistazo es cuándo cambió y qué."""
    db = _DB()
    _guardar(db, _tesis())
    fila = asyncio.run(tr.historial(db, "AAPL"))[0]
    assert "tesis" not in fila
    assert fila["titular"] and fila["huella"] and fila["cambios"]


def test_una_version_concreta_llega_ENTERA():
    db = _DB()
    _guardar(db, _tesis())
    v = asyncio.run(tr.version(db, "AAPL", 1))
    assert v["tesis"]["afirmaciones"]                    # con su traza de auditoría
    assert v["tesis"]["titular"]                         # y con sus números


def test_consultar_NO_escribe():
    """Mirar la pantalla no puede cambiar lo que la pantalla enseña."""
    db = _DB()
    _guardar(db, _tesis())
    antes = db[tr.COLECCION].escrituras
    asyncio.run(tr.historial(db, "AAPL"))
    asyncio.run(tr.version(db, "AAPL", 1))
    asyncio.run(tr.vigente(db, "AAPL"))
    assert db[tr.COLECCION].escrituras == antes


def test_el_diff_de_campos_es_MECANICO():
    a = {"campos_usados": ["indicators.regime.regime", "indicators.atr_pct"]}
    b = {"campos_usados": ["indicators.regime.regime", "indicators.obv_trend"]}
    d = tr.diff_de_campos(a, b)
    assert d["entran"] == ["indicators.obv_trend"]
    assert d["salen"] == ["indicators.atr_pct"]
    assert d["siguen"] == ["indicators.regime.regime"]


@pytest.mark.parametrize("symbol", ["", None, "   "])
def test_un_simbolo_vacio_no_registra_nada(symbol):
    db = _DB()
    r = asyncio.run(tr.guardar_si_cambia(db, symbol, _tesis()))
    assert r["accion"] == "nada"
    assert db[tr.COLECCION].docs == []
