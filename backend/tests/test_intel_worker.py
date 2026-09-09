"""El worker: la única pieza de Intelligence que toca la base de datos.

LO QUE ESTE FICHERO TIENE QUE DEMOSTRAR, Y POR QUÉ AQUÍ

Las reglas —qué es un duplicado, qué te toca, cuánto pesa— ya están probadas sin red en
`test_intel_pipeline.py`. Aquí queda lo que solo se puede romper CON base de datos, que
es precisamente la lista que se pidió por escrito:

  · idempotencia y reinicio: reprocesar el mismo feed no crea un segundo documento,
    y da igual en qué punto se cayera el proceso;
  · que un evento no genere dos señales, ni tras cinco vueltas;
  · que si SEC está desconectada NO se fabrique ningún evento — ni uno vacío, ni uno
    de relleno, ni uno «de prueba»;
  · que un error se anote y se espere, en vez de insistir;
  · que sin `SEC_USER_AGENT` no se haga NI UNA petición.

EL MONGO FALSO

Es de mentira a propósito: un Mongo real haría que estos tests dependieran de tener un
servidor levantado, y lo que se prueba aquí es la LÓGICA de escritura —el filtro del
`upsert`, qué campos se pisan y cuáles no—, que se ve igual de bien sobre diccionarios.
Implementa lo justo que el worker usa; si algún día usa más, el falso fallará en vez de
mentir.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import intel_eventos as ev
import intel_sec as sec
import intel_worker as w


# ── El Mongo falso ───────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _Col:
    def __init__(self):
        self.docs = []
        self.escrituras = 0

    def find(self, filtro=None, proyeccion=None):
        return _Cursor([d for d in self.docs if _casa(d, filtro)])

    async def find_one(self, filtro=None, proyeccion=None):
        for d in self.docs:
            if _casa(d, filtro):
                return dict(d)
        return None

    async def update_one(self, filtro, update, upsert=False):
        self.escrituras += 1
        for d in self.docs:
            if _casa(d, filtro):
                d.update(update.get("$set") or {})
                return
        if upsert:
            nuevo = dict(filtro)
            nuevo.update(update.get("$setOnInsert") or {})
            nuevo.update(update.get("$set") or {})
            self.docs.append(nuevo)


def _casa(doc, filtro):
    return all(doc.get(k) == v for k, v in (filtro or {}).items())


class _DB:
    def __init__(self, watchlist=(), cartera=()):
        self._cols = {}
        for s in watchlist:
            self["watchlist"].docs.append({"symbol": s})
        for s, acciones in cartera:
            self["signal_entries"].docs.append(
                {"symbol": s, "active": True, "acciones": acciones})

    def __getitem__(self, nombre):
        return self._cols.setdefault(nombre, _Col())

    def __getattr__(self, nombre):
        return self[nombre]


FEED_NVDA = [{"formulario": "8-K", "cik": "1045810"}]


def _feed(*symbols):
    """Eventos crudos como los devolvería `intel_sec.parsear_feed`."""
    return [ev.crear(fuente="sec", externo_id=f"8-K:{s}-0001",
                     titulo=f"8-K · Hecho relevante — {s}", symbol=s,
                     tipo=ev.CORPORATIVO, tier=1) for s in symbols]


@pytest.fixture
def configurada(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "InverIA/1.0 x@y.z")


def _con_feed(monkeypatch, crudos, falla=None):
    async def descargar(formulario="8-K", limite=40):
        if falla:
            raise RuntimeError(falla)
        # El worker pide los dos formularios; el feed de prueba se sirve una sola vez
        # para que el recuento no dependa de cuántos formularios se vigilen.
        return crudos if formulario == "8-K" else []
    monkeypatch.setattr(sec, "descargar", descargar)
    monkeypatch.setattr(w, "dormir", _no_dormir)


async def _no_dormir(_s):
    return None


def _ciclo(db):
    return asyncio.run(w.ciclo_sec(db))


# ── Sin configurar: cero peticiones, cero eventos ────────────────────────────

def test_sin_SEC_USER_AGENT_no_se_hace_NI_UNA_peticion(monkeypatch):
    """No es que la petición falle: es que no se intenta. Si `descargar` llegara a
    llamarse, este test explota."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    async def prohibido(*_a, **_k):
        raise AssertionError("se ha tocado la red sin identificación")
    monkeypatch.setattr(sec, "descargar", prohibido)

    r = _ciclo(_DB(watchlist=["NVDA"]))
    assert r["estado"] == sec.NO_CONFIGURADA


def test_sin_configurar_NO_se_fabrica_ningun_evento(monkeypatch):
    """La garantía que sostiene el radar: la pantalla solo puede pintar lo que de
    verdad ha entrado. Una fuente apagada produce cero documentos, no uno vacío."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    db = _DB(watchlist=["NVDA"])
    _ciclo(db)
    assert db[w.COL_EVENTOS].docs == []


def test_la_fuente_apagada_se_anota_apagada_y_no_rota(monkeypatch):
    """`NO_CONFIGURADA` no es un error. Pintarla como error diría que algo se ha roto
    cuando lo único que pasa es que no se ha conectado todavía."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    db = _DB()
    _ciclo(db)
    salud = db[w.COL_SALUD].docs[0]
    assert salud["estado"] == sec.NO_CONFIGURADA and salud["fallos"] == 0


# ── El camino bueno ──────────────────────────────────────────────────────────

def test_un_filing_tuyo_acaba_en_mongo(configurada, monkeypatch):
    """El vertical slice entero: SEC → pipeline → Mongo."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    r = _ciclo(db)
    assert r["estado"] == sec.ONLINE and len(r["significativos"]) == 1
    guardado = db[w.COL_EVENTOS].docs[0]
    assert guardado["symbol"] == "NVDA" and guardado["etapa"] == ev.SIGNIFICATIVO


def test_lo_que_no_es_tuyo_se_guarda_descartado_y_con_su_motivo(configurada, monkeypatch):
    """El descarte también es historia: es lo que permite auditar el filtro después y
    distinguir «no pasó nada» de «mi filtro se lo comió»."""
    _con_feed(monkeypatch, _feed("TSLA"))
    db = _DB(watchlist=["NVDA"])
    _ciclo(db)
    d = db[w.COL_EVENTOS].docs[0]
    assert d["etapa"] == ev.DESCARTADO and d["motivo_descarte"]


def test_tener_la_accion_pesa_mas_que_solo_seguirla(configurada, monkeypatch):
    """El worker tiene que distinguir «la llevo» de «la miro», porque la relevancia
    depende de cuánto dinero hay expuesto. Con `acciones` a 0 hay plan, no posición."""
    _con_feed(monkeypatch, _feed("NVDA"))
    con = _DB(cartera=[("NVDA", 12)])
    sin = _DB(cartera=[("NVDA", 0)])
    a, b = _ciclo(con), _ciclo(sin)
    assert a["guardar"][0]["afecta_cartera"] is True
    assert b["guardar"][0]["afecta_cartera"] is False
    assert b["guardar"][0]["afecta_watchlist"] is True


def test_el_universo_se_relee_en_cada_vuelta(configurada, monkeypatch):
    """Añades una acción a la watchlist y el siguiente ciclo ya la vigila, sin
    reiniciar el servicio. Cachear el universo obligaría a un despliegue."""
    _con_feed(monkeypatch, _feed("AMD"))
    db = _DB(watchlist=["NVDA"])
    assert _ciclo(db)["significativos"] == []
    db["watchlist"].docs.append({"symbol": "AMD"})
    db[w.COL_EVENTOS].docs.clear()
    assert len(_ciclo(db)["significativos"]) == 1


# ── Idempotencia y reinicios ─────────────────────────────────────────────────

def test_dos_vueltas_sobre_el_mismo_feed_no_crean_dos_documentos(configurada, monkeypatch):
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    for _ in range(4):
        _ciclo(db)
    assert len(db[w.COL_EVENTOS].docs) == 1


def test_UN_EVENTO_NO_GENERA_DOS_SENALES(configurada, monkeypatch):
    """La condición que se pidió por escrito, ahora contra la base de datos: el id ya
    escrito es el cursor, así que ninguna vuelta posterior vuelve a marcarlo
    significativo."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    assert len(_ciclo(db)["significativos"]) == 1
    for _ in range(5):
        assert _ciclo(db)["significativos"] == []


def test_un_reinicio_a_mitad_de_ciclo_no_pierde_ni_duplica(configurada, monkeypatch):
    """El cursor son los ids YA ESCRITOS, no los que se pretendía escribir. Si el
    proceso muere antes del `upsert`, el evento vuelve a entrar y se escribe: se
    reprocesa, que es gratis, en vez de perderse, que no lo es."""
    _con_feed(monkeypatch, _feed("NVDA", "AMD"))
    db = _DB(cartera=[("NVDA", 12), ("AMD", 4)])

    # Muere tras escribir el primero.
    real = db[w.COL_EVENTOS].update_one
    escritos = {"n": 0}

    async def muere(*a, **k):
        if escritos["n"] >= 1:
            raise RuntimeError("el proceso se ha caído")
        escritos["n"] += 1
        return await real(*a, **k)
    db[w.COL_EVENTOS].update_one = muere
    _ciclo(db)
    assert len(db[w.COL_EVENTOS].docs) == 1

    db[w.COL_EVENTOS].update_one = real          # arranca de nuevo
    _ciclo(db)
    ids = [d["id"] for d in db[w.COL_EVENTOS].docs]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_la_primera_vez_que_se_vio_no_cambia_al_releerlo(configurada, monkeypatch):
    """`recibido_en` va en `$setOnInsert`. Si se pisara en cada vuelta, «¿cuándo supo
    InverIA esto?» pasaría a responder «hace un minuto» para siempre, y ahí se cae el
    track record entero."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db)
    primero = db[w.COL_EVENTOS].docs[0]["recibido_en"]
    db[w.COL_EVENTOS].docs[0]["etapa"] = ev.ALERTADO      # como si ya hubiera alertado
    _ciclo(db)
    assert db[w.COL_EVENTOS].docs[0]["recibido_en"] == primero


def test_un_evento_ya_procesado_no_retrocede(configurada, monkeypatch):
    """Un repetido no se reescribe. Si se reescribiera, un evento que ya llegó a
    `alertado` volvería a `significativo` porque el feed lo menciona otra vez."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db)
    db[w.COL_EVENTOS].docs[0]["etapa"] = ev.ALERTADO
    _ciclo(db)
    assert db[w.COL_EVENTOS].docs[0]["etapa"] == ev.ALERTADO


# ── Errores, rate limiting y backoff ─────────────────────────────────────────

def test_un_fallo_de_la_sec_no_fabrica_eventos(configurada, monkeypatch):
    """Lo contrario sería un radar que se anima solo cuando la fuente está caída."""
    _con_feed(monkeypatch, [], falla="timeout")
    db = _DB(cartera=[("NVDA", 12)])
    r = _ciclo(db)
    assert r["estado"] == "error" and db[w.COL_EVENTOS].docs == []


def test_los_fallos_seguidos_se_CUENTAN_en_mongo(configurada, monkeypatch):
    """En Mongo y no en memoria: un reinicio de Render no puede borrar que la fuente
    lleva media hora fallando, porque entonces el backoff se reiniciaría con él."""
    _con_feed(monkeypatch, [], falla="timeout")
    db = _DB()
    for esperado in (1, 2, 3):
        assert _ciclo(db)["fallos"] == esperado
    assert db[w.COL_SALUD].docs[0]["fallos"] == 3


def test_un_ciclo_bueno_borra_la_cuenta_de_fallos(configurada, monkeypatch):
    """Si no se limpiara, un fallo aislado dejaría el connector castigado con una hora
    de espera para siempre."""
    _con_feed(monkeypatch, [], falla="timeout")
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db)
    _con_feed(monkeypatch, _feed("NVDA"))
    _ciclo(db)
    salud = db[w.COL_SALUD].docs[0]
    assert salud["fallos"] == 0 and salud["estado"] == sec.ONLINE and salud["error"] is None


def test_un_429_se_anota_como_rate_limited(configurada, monkeypatch):
    """Distinguirlo de una caída es lo que permite reaccionar distinto: a un 429 se le
    da tiempo, a una caída se le mira el log."""
    _con_feed(monkeypatch, [], falla="SEC respondió 429")
    db = _DB()
    _ciclo(db)
    assert db[w.COL_SALUD].docs[0]["estado"] == sec.LIMITADA


def test_con_fallos_ACUMULADOS_se_espera_mas_que_el_intervalo(configurada, monkeypatch):
    """Sin esto, un 403 por identificación mal puesta se reintentaría cada cinco
    minutos indefinidamente contra una puerta que no se va a abrir sola.

    Se parte de tres fallos ya anotados a propósito: con uno solo el backoff (60 s) es
    menor que el intervalo y no se notaría, así que el test no distinguiría entre un
    worker que aplica la espera y uno que la ignora."""
    _con_feed(monkeypatch, [], falla="SEC respondió 403")
    db = _DB()
    db[w.COL_SALUD].docs.append({"fuente": sec.FUENTE, "fallos": 3})
    esperas = []

    async def anotar(s):
        esperas.append(s)
        if len(esperas) >= 2:                # retraso inicial + la espera del fallo
            raise _Parar()
    monkeypatch.setattr(w, "dormir", anotar)
    with pytest.raises(_Parar):
        asyncio.run(w.worker_loop(db, intervalo=300, retraso_inicial=0))
    assert esperas[0] == 0                   # el retraso inicial
    # No se comprueba el valor exacto del backoff —eso es de `intel_sec`— sino que el
    # worker lo APLICA en vez de volver al intervalo normal.
    assert esperas[1] > 300


class _Parar(BaseException):
    """Cómo se sale de un `while True` desde un test.

    Hereda de `BaseException` A PROPÓSITO: el bucle atrapa `Exception` para sobrevivir a
    un ciclo que revienta, así que una excepción normal se la comería el propio worker y
    el test se quedaría girando para siempre. Que esto sea necesario es, de hecho, la
    prueba de que ese `except` está donde debe."""


# ── El bucle ─────────────────────────────────────────────────────────────────

def test_el_bucle_sobrevive_a_un_ciclo_que_explota(configurada, monkeypatch):
    """Un fallo inesperado no puede matar el worker: quedaría muerto hasta el próximo
    despliegue, en silencio y sin que nada lo diga."""
    vueltas = {"n": 0}

    async def revienta(_db):
        vueltas["n"] += 1
        if vueltas["n"] >= 3:
            raise _Parar()
        raise RuntimeError("algo rarísimo")
    monkeypatch.setattr(w, "ciclo_sec", revienta)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    with pytest.raises(_Parar):
        asyncio.run(w.worker_loop(_DB(), intervalo=1, retraso_inicial=0))
    assert vueltas["n"] == 3                 # siguió tras los dos primeros fallos


def test_el_bucle_espera_antes_de_la_primera_vuelta(configurada, monkeypatch):
    """Al arrancar hay quince workers más pidiendo cosas. Entrar a la vez que ellos
    sería competir por el mismo arranque sin ninguna necesidad."""
    orden = []

    async def dormir(s):
        orden.append(("dormir", s))

    async def ciclo(_db):
        orden.append(("ciclo", None))
        raise _Parar()
    monkeypatch.setattr(w, "dormir", dormir)
    monkeypatch.setattr(w, "ciclo_sec", ciclo)
    with pytest.raises(_Parar):
        asyncio.run(w.worker_loop(_DB(), intervalo=300, retraso_inicial=120))
    assert orden[0] == ("dormir", 120) and orden[1][0] == "ciclo"


# ── Aguante ──────────────────────────────────────────────────────────────────

def test_si_no_se_puede_leer_la_cartera_el_ciclo_sigue(configurada, monkeypatch):
    """Mongo puede tener un mal momento. Que el universo salga incompleto es peor que
    nada, pero mucho mejor que un worker que se cae y deja de vigilar."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])

    def revienta(*_a, **_k):
        raise RuntimeError("Mongo no responde")
    db["signal_entries"].find = revienta
    assert _ciclo(db)["estado"] == sec.ONLINE


def test_si_no_se_puede_leer_el_cursor_se_reprocesa_en_vez_de_perder(configurada, monkeypatch):
    """Ante la duda, conjunto vacío: se reprocesa todo y el `upsert` por id
    determinista evita que aparezca un duplicado."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db)

    original = db[w.COL_EVENTOS].find
    db[w.COL_EVENTOS].find = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caído"))
    _ciclo(db)
    db[w.COL_EVENTOS].find = original
    assert len(db[w.COL_EVENTOS].docs) == 1


def test_un_evento_sin_id_no_se_escribe(configurada, monkeypatch):
    """Sin id no hay filtro de `upsert`, así que escribirlo crearía un documento nuevo
    en cada vuelta para siempre."""
    db = _DB()
    asyncio.run(w._guardar(db, [None, {}, {"id": ""}, "texto suelto"]))
    assert db[w.COL_EVENTOS].docs == []
