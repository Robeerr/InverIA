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

import intel_earnings as earnings
import intel_eventos as ev
import intel_pipeline as pl
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

    async def count_documents(self, filtro=None):
        return len([d for d in self.docs if _casa(d, filtro)])

    async def find_one(self, filtro=None, proyeccion=None):
        for d in self.docs:
            if _casa(d, filtro):
                return dict(d)
        return None

    async def update_one(self, filtro, update, upsert=False):
        self.escrituras += 1
        doc = next((d for d in self.docs if _casa(d, filtro)), None)
        if doc is None:
            if not upsert:
                return
            doc = dict(filtro)
            doc.update(update.get("$setOnInsert") or {})
            self.docs.append(doc)
        doc.update(update.get("$set") or {})
        # `$inc` con notación de punto, que es como se acumulan los motivos de descarte.
        for campo, n in (update.get("$inc") or {}).items():
            destino, clave = doc, campo
            if "." in campo:
                raiz, clave = campo.split(".", 1)
                destino = doc.setdefault(raiz, {})
            destino[clave] = (destino.get(clave) or 0) + n


def _casa(doc, filtro):
    """Igualdad, más los dos operadores que el worker usa: `$in` y `$ne`.

    Se implementan porque si no el falso MIENTE: una consulta con `$in` no casaría con
    nada y el test pasaría por no encontrar documentos, no por que el código acierte. Es
    justo el fallo que un doble de pruebas tiene que evitar, y este ya lo cometió una vez.
    """
    for k, v in (filtro or {}).items():
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v and actual not in v["$in"]:
                return False
            if "$ne" in v and actual == v["$ne"]:
                return False
            if not ({"$in", "$ne"} >= set(v)):
                raise NotImplementedError(f"el Mongo falso no entiende {set(v)}")
        elif actual != v:
            return False
    return True


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
    """Eventos crudos como los devolvería `intel_sec.parsear_submissions`."""
    return [ev.crear(fuente="sec", externo_id=f"8-K:{s}-0001",
                     titulo=f"8-K · Hecho relevante — {s}", symbol=s,
                     tipo=ev.CORPORATIVO, tier=1) for s in symbols]


@pytest.fixture
def configurada(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "InverIA/1.0 x@y.z")


def _con_feed(monkeypatch, crudos, falla=None, mod=None):
    """Sustituye la recolección de una fuente. `recolectar` es la interfaz que el worker
    usa para TODAS, así que parchearla prueba el mismo camino que corre en producción."""
    async def recolectar(contexto=None):
        if falla:
            raise RuntimeError(falla)
        return list(crudos)
    monkeypatch.setattr(mod or sec, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)


async def _no_dormir(_s):
    return None


def _ciclo(db, mod=None):
    return asyncio.run(w.ciclo(db, mod or sec))


# ── Sin configurar: cero peticiones, cero eventos ────────────────────────────

def test_sin_SEC_USER_AGENT_no_se_hace_NI_UNA_peticion(monkeypatch):
    """No es que la petición falle: es que no se intenta. Si `recolectar` llegara a
    llamarse, este test explota."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    async def prohibido(*_a, **_k):
        raise AssertionError("se ha tocado la red sin identificación")
    monkeypatch.setattr(sec, "recolectar", prohibido)

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

    async def revienta(_db, _mod):
        vueltas["n"] += 1
        if vueltas["n"] >= 3:
            raise _Parar()
        raise RuntimeError("algo rarísimo")
    monkeypatch.setattr(w, "ciclo", revienta)
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

    async def ciclo(_db, _mod):
        orden.append(("ciclo", None))
        raise _Parar()
    monkeypatch.setattr(w, "dormir", dormir)
    monkeypatch.setattr(w, "ciclo", ciclo)
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


# ── Los contadores del periodo de prueba ─────────────────────────────────────
# La pregunta que tienen que contestar es «¿esto funciona?», y para eso hacen falta los
# cuatro números en la misma frase: leídos, nuevos, descartados y GUARDADOS. Con solo los
# tres primeros, «procesados 40» convive perfectamente con una base de datos vacía.

def test_el_ultimo_ciclo_dice_cuantos_se_GUARDARON(configurada, monkeypatch):
    _con_feed(monkeypatch, _feed("NVDA", "TSLA"))
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db)
    c = db[w.COL_SALUD].docs[0]["ultimo_ciclo"]
    assert c["recibidos"] == 2 and c["nuevos"] == 2
    assert c["descartados"] == 1 and c["significativos"] == 1
    # Los dos descartados y significativos se guardan igual: el descarte también es
    # historia. Lo que cuenta `guardados` es lo que de verdad se escribió.
    assert c["guardados"] == 2


def test_los_contadores_se_ACUMULAN_entre_ciclos(configurada, monkeypatch):
    """El acumulado es lo que sostiene un periodo de prueba. Si se reescribiera en cada
    vuelta, mirar la pantalla el martes no diría nada de lo que pasó el lunes."""
    db = _DB(cartera=[("NVDA", 12)])
    for i in range(3):
        _con_feed(monkeypatch, _feed(f"NVDA{i}" if i else "NVDA"))
        _ciclo(db)
    a = w._acumulado(db[w.COL_SALUD].docs[0])
    assert a["ciclos"] == 3 and a["recibidos"] == 3 and a["nuevos"] == 3


def test_el_acumulado_SOBREVIVE_a_un_reinicio(configurada, monkeypatch):
    """Vive en Mongo, no en memoria: un despliegue a media tarde no puede borrar la
    evidencia de que el sistema llevaba días funcionando."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db)
    antes = w._acumulado(db[w.COL_SALUD].docs[0])["recibidos"]
    _con_feed(monkeypatch, _feed("AMD"))       # otro proceso, misma base de datos
    _ciclo(db)
    assert w._acumulado(db[w.COL_SALUD].docs[0])["recibidos"] == antes + 1


def test_los_motivos_de_descarte_tambien_se_acumulan(configurada, monkeypatch):
    """Sin esto, un filtro que se está comiendo todo se ve igual que un mercado tranquilo
    en cuanto pasa un ciclo vacío por encima."""
    db = _DB(watchlist=["NVDA"])
    for i in range(2):
        _con_feed(monkeypatch, _feed(f"TSLA{i}"))
        _ciclo(db)
    assert w._acumulado(db[w.COL_SALUD].docs[0])["por_motivo"]["fuera_de_universo"] == 2


def test_cuando_empezo_a_vigilar_NO_se_pisa(configurada, monkeypatch):
    """`vigilando_desde` va en `$setOnInsert`. Si se reescribiera, el periodo de prueba
    diría siempre «desde hace cinco minutos»."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db)
    desde = db[w.COL_SALUD].docs[0]["vigilando_desde"]
    _ciclo(db)
    assert db[w.COL_SALUD].docs[0]["vigilando_desde"] == desde


def test_los_fallos_tambien_cuentan_como_ciclo(configurada, monkeypatch):
    """Un ciclo que falla ES un ciclo. Contar solo los buenos daría una tasa de éxito
    del 100 % sobre un connector que no ha conseguido conectarse nunca."""
    _con_feed(monkeypatch, [], falla="timeout")
    db = _DB()
    _ciclo(db)
    a = w._acumulado(db[w.COL_SALUD].docs[0])
    assert a["ciclos"] == 1 and a["fallos"] == 1


# ── La comprobación a demanda ────────────────────────────────────────────────

def test_comprobar_ahora_devuelve_la_cadena_ENTERA(configurada, monkeypatch):
    """Los cinco pasos en orden. Es lo que permite distinguir una fuente caída de un
    filtro agresivo de un mercado tranquilo, que a ojos de un radar vacío son idénticos."""
    _con_feed(monkeypatch, _feed("NVDA", "TSLA"))
    db = _DB(cartera=[("NVDA", 12)])
    r = asyncio.run(w.comprobar_ahora(db, fuentes=[sec]))["fuentes"][0]
    c = r["cadena"]
    assert c["leidos_de_la_fuente"] == 2
    assert c["ya_conocidos"] == 0
    assert c["nuevos_tras_deduplicar"] == 2
    assert c["descartados_al_filtrar"] == 1
    assert c["significativos"] == 1
    assert c["escritos_en_esta_vuelta"] == 2


def test_comprobar_ahora_LEE_DE_VUELTA_lo_que_hay_en_mongo(configurada, monkeypatch):
    """Que el ciclo diga que guardó dos cosas y que la colección tenga dos cosas son dos
    afirmaciones distintas. Solo la segunda cierra la cadena."""
    _con_feed(monkeypatch, _feed("NVDA", "TSLA"))
    db = _DB(cartera=[("NVDA", 12)])
    r = asyncio.run(w.comprobar_ahora(db, fuentes=[sec]))["fuentes"][0]
    assert r["guardados_unicos"] == len(db[w.COL_EVENTOS].docs) == 2


def test_comprobar_ahora_usa_EL_MISMO_ciclo_que_el_bucle(configurada, monkeypatch):
    """Si tuviera su propia versión «de prueba», estaría verificando un código que en
    producción no se ejecuta: el semáforo en verde sobre un sistema roto."""
    llamadas = []

    async def espia(db, mod):
        llamadas.append(mod)
        return {"estado": sec.ONLINE, "recibidos": 0, "nuevos": 0, "descartados": 0,
                "significativos": [], "escritos": 0, "por_motivo": {}}
    monkeypatch.setattr(w, "ciclo", espia)
    asyncio.run(w.comprobar_ahora(_DB(), fuentes=[sec]))
    assert len(llamadas) == 1


def test_comprobar_ahora_sin_configurar_dice_la_verdad(configurada, monkeypatch):
    """Sin identificación no se toca la red, tampoco cuando la comprobación la pides tú.
    Y lo dice: NO_CONFIGURADA, no un error genérico."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    r = asyncio.run(w.comprobar_ahora(_DB(watchlist=["NVDA"]), fuentes=[sec]))["fuentes"][0]
    assert r["estado"] == sec.NO_CONFIGURADA and r["guardados_unicos"] == 0


def test_comprobar_ahora_con_la_fuente_caida_NO_dice_que_todo_va_bien(configurada, monkeypatch):
    _con_feed(monkeypatch, [], falla="SEC respondió 403")
    r = asyncio.run(w.comprobar_ahora(_DB(cartera=[("NVDA", 12)]),
                                      fuentes=[sec]))["fuentes"][0]
    assert r["estado"] == "error" and "403" in r["error"]
    assert r["cadena"]["leidos_de_la_fuente"] == 0


# ── «Ya conocido» no es «descartado», tampoco en los acumulados ──────────────

def test_la_segunda_vuelta_cuenta_YA_CONOCIDOS_y_no_descartes(configurada, monkeypatch):
    """El caso real de producción: el feed devuelve lo mismo cada cinco minutos. Si eso
    contara como descarte, la tasa de descarte subiría sin parar y parecería que el filtro
    se ha vuelto loco, cuando lo que pasa es que la deduplicación va bien."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db)
    r = _ciclo(db)                                   # el mismo feed, otra vez
    assert r["repetidos"] == 1 and r["descartados"] == 0
    c = db[w.COL_SALUD].docs[0]["ultimo_ciclo"]
    assert c["repetidos"] == 1 and c["descartados"] == 0


def test_los_ya_conocidos_se_acumulan_APARTE(configurada, monkeypatch):
    _con_feed(monkeypatch, _feed("NVDA", "TSLA"))
    db = _DB(cartera=[("NVDA", 12)])
    for _ in range(3):
        _ciclo(db)
    a = w._acumulado(db[w.COL_SALUD].docs[0])
    assert a["recibidos"] == 6          # 2 por vuelta, tres vueltas
    assert a["repetidos"] == 4          # las dos vueltas siguientes, dos cada una
    assert a["nuevos"] == 2
    assert a["descartados"] == 1        # TSLA, una sola vez: la primera


def test_guardados_UNICOS_no_son_escrituras(configurada, monkeypatch):
    """Tres vueltas sobre el mismo feed escriben una vez y reescriben cero, porque los
    repetidos ni siquiera vuelven a `guardar`. Los únicos se cuentan en la colección,
    que es la cifra que no se puede inflar reprocesando."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    for _ in range(3):
        _ciclo(db)
    r = asyncio.run(w.comprobar_ahora(db, fuentes=[sec]))["fuentes"][0]
    assert r["guardados_unicos"] == 1
    assert w._acumulado(db[w.COL_SALUD].docs[0])["escrituras"] == 1


# ── El cambio de significado de los contadores ───────────────────────────────

def test_los_contadores_VIEJOS_se_reinician_una_vez(configurada, monkeypatch):
    """La v1 sumaba los repetidos dentro de `descartados`. Arrastrar esos números sobre la
    v2 daría una cifra mezclada que no mide ninguna de las dos cosas — y nadie podría
    saberlo mirándola, que es lo peor que le puede pasar a un diagnóstico."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    db[w.COL_SALUD].docs.append({"fuente": sec.FUENTE, "contadores_v": 1,
                                 "acum_recibidos": 129, "acum_descartados": 129,
                                 "acum_ciclos": 3, "vigilando_desde": "2026-09-01T00:00:00Z"})
    _ciclo(db)
    a = w._acumulado(db[w.COL_SALUD].docs[0])
    assert a["ciclos"] == 1 and a["recibidos"] == 1     # cuenta solo desde el reinicio
    assert a["desde"] != "2026-09-01T00:00:00Z"


def test_el_reinicio_NO_borra_ningun_evento(configurada, monkeypatch):
    """Los documentos guardados siguen siendo válidos: lo que caducó es una estadística,
    no la evidencia. El radar tiene que seguir enseñando lo mismo."""
    _con_feed(monkeypatch, _feed("NVDA"))
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db)
    db[w.COL_SALUD].docs[0]["contadores_v"] = 1        # como si viniera de la versión vieja
    _ciclo(db)
    assert len(db[w.COL_EVENTOS].docs) == 1


def test_el_reinicio_ocurre_UNA_sola_vez(configurada, monkeypatch):
    """Si se repitiera en cada vuelta, el acumulado diría siempre «una vuelta» y el
    periodo de prueba no acumularía nunca."""
    _con_feed(monkeypatch, _feed("NVDA", "TSLA"))
    db = _DB(cartera=[("NVDA", 12)])
    db[w.COL_SALUD].docs.append({"fuente": sec.FUENTE, "contadores_v": 1, "acum_ciclos": 9})
    for _ in range(3):
        _ciclo(db)
    assert w._acumulado(db[w.COL_SALUD].docs[0])["ciclos"] == 3


# ── Dos fuentes, no una ──────────────────────────────────────────────────────

@pytest.fixture
def con_finnhub(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "x")


def _resultados(*filas):
    """Eventos crudos como los devolvería `intel_earnings.construir`."""
    return earnings.construir(list(filas))


def _fila(symbol="NVDA", date="2026-10-28", quarter=3, year=2026,
          eps_estimate=1.10, eps_actual=None):
    return {"symbol": symbol, "date": date, "quarter": quarter, "year": year,
            "eps_estimate": eps_estimate, "eps_actual": eps_actual, "hour": "amc"}


def test_las_dos_fuentes_pasan_por_EL_MISMO_ciclo(configurada, con_finnhub, monkeypatch):
    """El bucle no sabe de qué fuente se trata: le pide `recolectar` y trata a todas
    igual. Es lo que hace que añadir una tercera no toque el worker."""
    _con_feed(monkeypatch, _feed("NVDA"), mod=sec)
    _con_feed(monkeypatch, _resultados(_fila()), mod=earnings)
    db = _DB(cartera=[("NVDA", 12)])
    for mod in (sec, earnings):
        assert _ciclo(db, mod)["estado"] == mod.ONLINE
    fuentes = {d["fuente"] for d in db[w.COL_EVENTOS].docs}
    assert fuentes == {"sec", "earnings"}


def test_cada_fuente_lleva_SUS_PROPIOS_contadores(configurada, con_finnhub, monkeypatch):
    """Sumarlas escondería lo que hace falta ver: con SEC leyendo cada cinco minutos y
    resultados cada seis horas, un total conjunto lo dominaría la primera y una caída de
    la segunda pasaría desapercibida."""
    _con_feed(monkeypatch, _feed("NVDA", "AMD"), mod=sec)
    _con_feed(monkeypatch, _resultados(_fila()), mod=earnings)
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db, sec)
    _ciclo(db, earnings)
    por_fuente = {d["fuente"]: w._acumulado(d) for d in db[w.COL_SALUD].docs}
    assert por_fuente["sec"]["recibidos"] == 2
    assert por_fuente["earnings"]["recibidos"] == 1


def test_una_fuente_caida_NO_arrastra_a_la_sana(configurada, con_finnhub, monkeypatch):
    """El motivo de que haya un bucle por fuente. Con uno compartido, o se espera la hora
    de castigo de la que falla o se machaca a la que va bien."""
    _con_feed(monkeypatch, [], falla="Finnhub 429", mod=earnings)
    _con_feed(monkeypatch, _feed("NVDA"), mod=sec)
    db = _DB(cartera=[("NVDA", 12)])
    assert _ciclo(db, earnings)["estado"] == "error"
    assert _ciclo(db, sec)["estado"] == sec.ONLINE
    assert len(db[w.COL_EVENTOS].docs) == 1


def test_sin_clave_de_finnhub_resultados_queda_apagada_y_sec_sigue(configurada, monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    _con_feed(monkeypatch, _feed("NVDA"), mod=sec)
    db = _DB(cartera=[("NVDA", 12)])
    assert _ciclo(db, earnings)["estado"] == earnings.NO_CONFIGURADA
    assert _ciclo(db, sec)["estado"] == sec.ONLINE


# ── El cambio de fecha, de punta a punta ─────────────────────────────────────

def test_las_fechas_conocidas_salen_de_MONGO(con_finnhub, monkeypatch):
    """El connector es puro y no consulta nada: la fecha anterior se la inyecta el
    worker, igual que a SEC le inyecta la tabla de tickers."""
    _con_feed(monkeypatch, _resultados(_fila()), mod=earnings)
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db, earnings)
    assert asyncio.run(w._fechas_conocidas(db)) == {"NVDA:2026Q3": "2026-10-28"}


def test_un_CAMBIO_DE_FECHA_entra_como_evento_nuevo(con_finnhub, monkeypatch):
    """La cadena entera: se guarda la fecha, cambia, y el worker la reconoce como
    movimiento en vez de tratarla como un anuncio repetido."""
    _con_feed(monkeypatch, _resultados(_fila(date="2026-10-28")), mod=earnings)
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db, earnings)

    # La empresa mueve la fecha. El worker relee las fechas conocidas y se lo pasa al
    # connector, que ahora sí puede decir «antes era el 28».
    async def recolectar(contexto=None):
        return earnings.construir([_fila(date="2026-11-04")],
                                  (contexto or {}).get("fechas_conocidas"))
    monkeypatch.setattr(earnings, "recolectar", recolectar)
    r = _ciclo(db, earnings)

    assert r["nuevos"] == 1 and r["repetidos"] == 0
    movido = [d for d in db[w.COL_EVENTOS].docs
              if (d.get("crudo") or {}).get("suceso") == earnings.CAMBIO_FECHA]
    assert len(movido) == 1
    assert movido[0]["crudo"]["fecha_anterior"] == "2026-10-28"
    # Y el anuncio original SIGUE ahí: son dos momentos distintos, no una corrección.
    assert len(db[w.COL_EVENTOS].docs) == 2


def test_el_mismo_calendario_dos_veces_NO_inventa_un_cambio(con_finnhub, monkeypatch):
    """El riesgo evidente de esta fuente: leer el calendario cada seis horas y creerse
    que la fecha se mueve en cada vuelta."""
    async def recolectar(contexto=None):
        return earnings.construir([_fila()], (contexto or {}).get("fechas_conocidas"))
    monkeypatch.setattr(earnings, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    db = _DB(cartera=[("NVDA", 12)])
    for _ in range(4):
        _ciclo(db, earnings)
    assert len(db[w.COL_EVENTOS].docs) == 1


def test_la_fecha_de_PUBLICACION_no_cuenta_como_fecha_de_calendario(con_finnhub, monkeypatch):
    """Su `fecha` es cuándo se publicó, no una fecha prevista. Si contara como tal, la
    vuelta siguiente compararía contra ella e inventaría un cambio que nunca ocurrió.

    Se parte de la fecha ya conocida para que la fila produzca SOLO el evento de
    publicación: es el caso que aísla lo que se quiere probar."""
    filas = earnings.construir([_fila(eps_actual=1.35)], {"NVDA:2026Q3": "2026-10-28"})
    assert [e["crudo"]["suceso"] for e in filas] == [earnings.PUBLICADO]
    _con_feed(monkeypatch, filas, mod=earnings)
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db, earnings)
    assert len(db[w.COL_EVENTOS].docs) == 1
    assert asyncio.run(w._fechas_conocidas(db)) == {}


def test_publicar_no_borra_la_fecha_de_calendario_que_ya_habia(con_finnhub, monkeypatch):
    """El caso completo: se anuncia, se publica, y la fecha del calendario sigue siendo
    la del anuncio. Es lo que impide que la vuelta siguiente vea un cambio fantasma."""
    async def recolectar(contexto=None):
        return earnings.construir([_fila(eps_actual=1.35)],
                                  (contexto or {}).get("fechas_conocidas"))
    monkeypatch.setattr(earnings, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db, earnings)                                   # programado + publicado
    assert asyncio.run(w._fechas_conocidas(db)) == {"NVDA:2026Q3": "2026-10-28"}
    r = _ciclo(db, earnings)                               # otra vuelta, mismo calendario
    assert r["nuevos"] == 0                                # ni cambio ni anuncio nuevos


def test_comprobar_ahora_informa_DE_CADA_fuente(configurada, con_finnhub, monkeypatch):
    _con_feed(monkeypatch, _feed("NVDA"), mod=sec)
    _con_feed(monkeypatch, _resultados(_fila()), mod=earnings)
    r = asyncio.run(w.comprobar_ahora(_DB(cartera=[("NVDA", 12)])))
    assert [f["fuente"] for f in r["fuentes"]] == ["sec", "earnings"]
    assert all("cadena" in f and "acumulado" in f for f in r["fuentes"])


# ── El repaso tras cambiar la fórmula ────────────────────────────────────────
# Cambiar los pesos no reescribe lo ya guardado. Sin repaso, la lista mezclaría notas de
# dos fórmulas —un 95 de la v1 junto a un 80 de la v2— y nadie podría saberlo mirándolas.

def _guardado(db, **campos):
    doc = {"id": "sec:x", "fuente": "sec", "symbol": "NVDA", "tier": 1,
           "titulo": "8-K", "etapa": ev.SIGNIFICATIVO, "relevancia": 95,
           "relevancia_v": 1, "nivel_alerta": ev.CRITICAL, "historial": [],
           "afecta_cartera": True, "afecta_watchlist": True, "afecta_tesis": False,
           "crudo": {"suceso": "8-K"}}
    doc.update(campos)
    db[w.COL_EVENTOS].docs.append(doc)
    return doc


def test_el_repaso_recalcula_las_notas_VIEJAS():
    db = _DB(cartera=[("NVDA", 12)])
    _guardado(db)
    r = asyncio.run(w.repuntuar_pendientes(db))
    assert r == {"revisados": 1, "cambiados": 1}
    d = db[w.COL_EVENTOS].docs[0]
    assert d["relevancia"] == 80 and d["nivel_alerta"] == ev.IMPORTANT
    assert d["relevancia_v"] == pl.RELEVANCIA_V


def test_el_repaso_es_IDEMPOTENTE():
    """Cada evento lleva su versión, así que la segunda vuelta no encuentra nada. Si no,
    reescribiría la colección entera en cada arranque para siempre."""
    db = _DB(cartera=[("NVDA", 12)])
    _guardado(db)
    asyncio.run(w.repuntuar_pendientes(db))
    assert asyncio.run(w.repuntuar_pendientes(db))["revisados"] == 0


def test_el_repaso_se_CURA_SOLO_si_el_proceso_muere_a_mitad():
    """Lo que quede sin sellar se repasa en la vuelta siguiente. No hace falta recordar
    por dónde iba: el propio documento lo dice."""
    db = _DB(cartera=[("NVDA", 12)])
    _guardado(db, id="sec:a")
    _guardado(db, id="sec:b")
    db[w.COL_EVENTOS].docs[1]["relevancia_v"] = pl.RELEVANCIA_V   # como si ya se hubiera hecho
    assert asyncio.run(w.repuntuar_pendientes(db))["revisados"] == 1


def test_el_repaso_NO_TOCA_los_descartados():
    """`descartado` es terminal: es la puerta que impide que algo ya rechazado vuelva a
    entrar. Y su motivo no depende de la nota — quien no está en tu universo sigue sin
    estarlo con cualquier fórmula."""
    db = _DB(cartera=[("NVDA", 12)])
    _guardado(db, etapa=ev.DESCARTADO, motivo_descarte="fuera_de_universo", relevancia=95)
    assert asyncio.run(w.repuntuar_pendientes(db))["revisados"] == 0
    assert db[w.COL_EVENTOS].docs[0]["relevancia"] == 95


def test_lo_que_ya_no_llega_al_umbral_VUELVE_a_filtrado_y_queda_anotado():
    """La única marcha atrás del sistema, y por eso está escrita a mano y fuera del
    pipeline: un retroceso en el camino normal sí sería el fallo que las transiciones
    existen para impedir. Queda en el historial como recalibración."""
    db = _DB()      # ni en cartera ni en watchlist: la nota se desploma
    _guardado(db, tier=4, crudo={"suceso": "4"})
    asyncio.run(w.repuntuar_pendientes(db))
    d = db[w.COL_EVENTOS].docs[0]
    assert d["relevancia"] < pl.UMBRAL_SIGNIFICATIVO
    assert d["etapa"] == ev.FILTRADO
    assert d["historial"][-1]["motivo"] == "recalibrado"


def test_lo_que_estaba_en_filtrado_puede_SUBIR_a_significativo():
    db = _DB(cartera=[("NVDA", 12)])
    _guardado(db, etapa=ev.FILTRADO, relevancia=10, nivel_alerta=ev.INFO)
    asyncio.run(w.repuntuar_pendientes(db))
    assert db[w.COL_EVENTOS].docs[0]["etapa"] == ev.SIGNIFICATIVO


def test_un_evento_ya_ALERTADO_no_retrocede_por_el_repaso():
    """Ya te avisó. Devolverlo a la lista de pendientes reescribiría la historia."""
    db = _DB(cartera=[("NVDA", 12)])
    _guardado(db, etapa=ev.ALERTADO)
    asyncio.run(w.repuntuar_pendientes(db))
    assert db[w.COL_EVENTOS].docs[0]["etapa"] == ev.ALERTADO


def test_el_repaso_lo_lanza_UNA_SOLA_fuente(configurada, con_finnhub, monkeypatch):
    """Si lo hicieran las dos, dos workers se pisarían escribiendo los mismos documentos
    en el mismo instante."""
    llamadas = []

    async def espia(db, limite=2000):
        llamadas.append(True)
        return {"revisados": 0, "cambiados": 0}
    monkeypatch.setattr(w, "repuntuar_pendientes", espia)
    monkeypatch.setattr(w, "dormir", _no_dormir)

    async def para(_db, _mod):
        raise _Parar()
    monkeypatch.setattr(w, "ciclo", para)
    for mod in w.FUENTES:
        with pytest.raises(_Parar):
            asyncio.run(w.worker_loop(_DB(), mod, retraso_inicial=0))
    assert len(llamadas) == 1


def test_si_el_repaso_falla_el_worker_ARRANCA_igual(configurada, monkeypatch):
    """Un repaso es mantenimiento. Que impidiera vigilar sería cambiar un número feo por
    dejar de mirar el mercado."""
    async def revienta(*_a, **_k):
        raise RuntimeError("Mongo no responde")
    monkeypatch.setattr(w, "repuntuar_pendientes", revienta)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    vueltas = []

    async def ciclo(_db, _mod):
        vueltas.append(True)
        raise _Parar()
    monkeypatch.setattr(w, "ciclo", ciclo)
    with pytest.raises(_Parar):
        asyncio.run(w.worker_loop(_DB(), w.FUENTES[0], retraso_inicial=0))
    assert vueltas == [True]


# ── Vigilancia por CIK: cursores, rotación y fallos ──────────────────────────

def _tabla(*pares):
    return sec.construir_tabla([{"cik_str": c, "ticker": t} for t, c in pares])


def test_los_cursores_se_INYECTAN_desde_mongo(configurada, monkeypatch):
    """El connector es puro respecto a la base de datos: no la consulta, la recibe. La
    misma frontera que con la tabla de tickers y las fechas de resultados."""
    visto = {}

    async def recolectar(contexto=None):
        visto.update(contexto or {})
        return []
    monkeypatch.setattr(sec, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    db = _DB(cartera=[("NVDA", 12)])
    db[w.COL_CURSORES].docs.append({"cik": 1045810, "ultimo_accession": "000104581026000042"})
    _ciclo(db, sec)
    assert visto["cursores"]["1045810"]["ultimo_accession"] == "000104581026000042"
    assert visto["cartera"] == {"NVDA"} and "salida" in visto


def test_los_cursores_se_GUARDAN_tras_escribir_los_eventos(configurada, monkeypatch):
    """En ese orden. Si se guardaran antes y la escritura fallara, la vuelta siguiente
    daría esos registros por vistos y se perderían para siempre."""
    async def recolectar(contexto=None):
        contexto["salida"]["cursores"] = {
            "1045810": {"cik": 1045810, "ultimo_accession": "000104581026000042"}}
        return _feed("NVDA")
    monkeypatch.setattr(sec, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db, sec)
    assert db[w.COL_CURSORES].docs[0]["ultimo_accession"] == "000104581026000042"
    assert len(db[w.COL_EVENTOS].docs) == 1


def test_tras_un_429_se_guardan_los_cursores_de_lo_YA_consultado(configurada, monkeypatch):
    """El ciclo se corta, pero las empresas que sí contestaron no hay que releerlas."""
    async def recolectar(contexto=None):
        contexto["salida"]["cursores"] = {"1": {"cik": 1, "ultimo_accession": "aaa"}}
        raise sec.LimiteSec("SEC respondió 429")
    monkeypatch.setattr(sec, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    db = _DB(cartera=[("NVDA", 12)])
    r = _ciclo(db, sec)
    assert r["estado"] == "error" and "429" in r["error"]
    assert db[w.COL_CURSORES].docs[0]["ultimo_accession"] == "aaa"


def test_un_403_degrada_la_fuente_sin_cascada(configurada, monkeypatch):
    """Se anota una vez, se espera, y no se reintenta contra una puerta cerrada."""
    async def recolectar(contexto=None):
        raise sec.LimiteSec("SEC respondió 403")
    monkeypatch.setattr(sec, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db, sec)
    salud = db[w.COL_SALUD].docs[0]
    assert salud["estado"] == sec.ERROR and salud["espera_s"] > 0
    assert db[w.COL_EVENTOS].docs == []          # y NO se fabrica ningún evento


def test_un_timeout_no_se_confunde_con_un_limite(configurada, monkeypatch):
    _con_feed(monkeypatch, [], falla="timeout leyendo submissions", mod=sec)
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db, sec)
    assert db[w.COL_SALUD].docs[0]["estado"] == sec.DEGRADADA


def test_el_fallo_de_UN_CIK_no_impide_guardar_el_resto(configurada, monkeypatch):
    """La vuelta sigue: el resto de tus empresas no tiene la culpa. Y el fallo se
    informa, para que no desaparezca en silencio."""
    async def recolectar(contexto=None):
        contexto["salida"]["fallos"] = [{"cik": 99, "symbol": "AMD", "error": "timeout"}]
        contexto["salida"]["consultados"] = 2
        return _feed("NVDA")
    monkeypatch.setattr(sec, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    db = _DB(cartera=[("NVDA", 12)])
    r = _ciclo(db, sec)
    assert r["estado"] == sec.ONLINE and len(db[w.COL_EVENTOS].docs) == 1
    assert r["fallos_por_objetivo"][0]["symbol"] == "AMD"


def test_la_VUELTA_persiste_para_que_rote_de_verdad(configurada, monkeypatch):
    """Si se reiniciara a cero en cada arranque, el turno 0 del seguimiento se miraría
    siempre y los demás nunca."""
    vueltas = []

    async def recolectar(contexto=None):
        vueltas.append(contexto["vuelta"])
        return []
    monkeypatch.setattr(sec, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    db = _DB(cartera=[("NVDA", 12)])
    for _ in range(3):
        _ciclo(db, sec)
    assert vueltas == [0, 1, 2]


def test_la_vuelta_SOBREVIVE_a_un_reinicio(configurada, monkeypatch):
    """Vive en Mongo, no en memoria: un despliegue no puede volver a empezar la rotación."""
    async def recolectar(contexto=None):
        return []
    monkeypatch.setattr(sec, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    db = _DB(cartera=[("NVDA", 12)])
    _ciclo(db, sec)
    assert db[w.COL_SALUD].docs[0]["vuelta"] == 1     # otro proceso, misma base de datos


def test_earnings_NO_recibe_cursores_ni_vuelta(configurada, con_finnhub, monkeypatch):
    """Son cosa de SEC. Metérselos a todas las fuentes ensuciaría el contrato genérico."""
    visto = {}

    async def recolectar(contexto=None):
        visto.update(contexto or {})
        return []
    monkeypatch.setattr(earnings, "recolectar", recolectar)
    monkeypatch.setattr(w, "dormir", _no_dormir)
    _ciclo(_DB(cartera=[("NVDA", 12)]), earnings)
    assert "cursores" not in visto and "vuelta" not in visto
    assert "fechas_conocidas" in visto


# ── Migración de identificadores ─────────────────────────────────────────────

def _evento_sec(db, id_, externo, **extra):
    doc = {"id": id_, "fuente": "sec", "externo_id": externo, "symbol": "NVDA",
           "etapa": ev.SIGNIFICATIVO, "relevancia": 80, "relevancia_v": 2,
           "nivel_alerta": ev.IMPORTANT, "historial": [], "crudo": {"suceso": "8-K"},
           "afecta_cartera": True, "afecta_watchlist": True, "afecta_tesis": False}
    doc.update(extra)
    db[w.COL_EVENTOS].docs.append(doc)
    return doc


def test_los_ids_YA_canonicos_solo_se_sellan(configurada):
    """El feed Atom daba la forma sin guiones, así que los 44 eventos guardados ya están
    bien. La migración no puede tocarlos: solo marca que se han revisado."""
    db = _DB()
    _evento_sec(db, "sec:8-K:000104581026000042", "8-K:000104581026000042")
    r = asyncio.run(w.migrar_ids_sec(db))
    assert r == {"revisados": 1, "renombrados": 0, "conflictos": 0}
    d = db[w.COL_EVENTOS].docs[0]
    assert d["id"] == "sec:8-K:000104581026000042" and d["sec_id_v"] == w.SEC_ID_V


def test_un_id_CON_GUIONES_se_canoniza():
    db = _DB()
    _evento_sec(db, "sec:8-K:0001045810-26-000042", "8-K:0001045810-26-000042")
    r = asyncio.run(w.migrar_ids_sec(db))
    assert r["renombrados"] == 1
    d = db[w.COL_EVENTOS].docs[0]
    assert d["id"] == "sec:8-K:000104581026000042"
    assert d["externo_id"] == "8-K:000104581026000042"


def test_la_migracion_es_IDEMPOTENTE():
    db = _DB()
    _evento_sec(db, "sec:8-K:000104581026000042", "8-K:000104581026000042")
    asyncio.run(w.migrar_ids_sec(db))
    assert asyncio.run(w.migrar_ids_sec(db))["revisados"] == 0


def test_la_migracion_NO_PIERDE_ni_duplica_eventos():
    db = _DB()
    for i in range(5):
        _evento_sec(db, f"sec:8-K:00010458102600004{i}", f"8-K:00010458102600004{i}")
    antes = {d["id"] for d in db[w.COL_EVENTOS].docs}
    asyncio.run(w.migrar_ids_sec(db))
    assert len(db[w.COL_EVENTOS].docs) == 5
    assert {d["id"] for d in db[w.COL_EVENTOS].docs} == antes


def test_si_el_id_canonico_YA_EXISTE_no_se_fusiona_nada():
    """Dos documentos del mismo registro es raro, pero fusionarlos automáticamente es más
    peligroso que dejar uno de más y verlo en el diagnóstico."""
    db = _DB()
    _evento_sec(db, "sec:8-K:000104581026000042", "8-K:000104581026000042",
                sec_id_v=w.SEC_ID_V)
    _evento_sec(db, "sec:8-K:0001045810-26-000042", "8-K:0001045810-26-000042")
    r = asyncio.run(w.migrar_ids_sec(db))
    assert r["conflictos"] == 1 and r["renombrados"] == 0
    assert len(db[w.COL_EVENTOS].docs) == 2       # ninguno se borra


def test_la_migracion_NO_toca_los_eventos_de_earnings():
    db = _DB()
    db[w.COL_EVENTOS].docs.append({"id": "earnings:NVDA:2026Q3:2026-10-28",
                                   "fuente": "earnings", "externo_id": "NVDA:2026Q3"})
    assert asyncio.run(w.migrar_ids_sec(db))["revisados"] == 0
    assert db[w.COL_EVENTOS].docs[0]["id"] == "earnings:NVDA:2026Q3:2026-10-28"


def test_la_migracion_se_lanza_al_arrancar_y_UNA_sola_vez(configurada, con_finnhub, monkeypatch):
    llamadas = []

    async def espia(db, limite=5000):
        llamadas.append(True)
        return {"revisados": 0, "renombrados": 0, "conflictos": 0}
    monkeypatch.setattr(w, "migrar_ids_sec", espia)
    monkeypatch.setattr(w, "repuntuar_pendientes", espia)
    monkeypatch.setattr(w, "dormir", _no_dormir)

    async def para(_db, _mod):
        raise _Parar()
    monkeypatch.setattr(w, "ciclo", para)
    for mod in w.FUENTES:
        with pytest.raises(_Parar):
            asyncio.run(w.worker_loop(_DB(), mod, retraso_inicial=0))
    assert len(llamadas) == 2        # migración + repaso, y solo de la primera fuente
