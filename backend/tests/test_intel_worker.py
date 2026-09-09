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
    r = asyncio.run(w.comprobar_ahora(db))
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
    r = asyncio.run(w.comprobar_ahora(db))
    assert r["guardados_unicos"] == len(db[w.COL_EVENTOS].docs) == 2


def test_comprobar_ahora_usa_EL_MISMO_ciclo_que_el_bucle(configurada, monkeypatch):
    """Si tuviera su propia versión «de prueba», estaría verificando un código que en
    producción no se ejecuta: el semáforo en verde sobre un sistema roto."""
    llamadas = []

    async def espia(db):
        llamadas.append(db)
        return {"estado": sec.ONLINE, "recibidos": 0, "nuevos": 0, "descartados": 0,
                "significativos": [], "escritos": 0, "por_motivo": {}}
    monkeypatch.setattr(w, "ciclo_sec", espia)
    asyncio.run(w.comprobar_ahora(_DB()))
    assert len(llamadas) == 1


def test_comprobar_ahora_sin_configurar_dice_la_verdad(configurada, monkeypatch):
    """Sin identificación no se toca la red, tampoco cuando la comprobación la pides tú.
    Y lo dice: NO_CONFIGURADA, no un error genérico."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    r = asyncio.run(w.comprobar_ahora(_DB(watchlist=["NVDA"])))
    assert r["estado"] == sec.NO_CONFIGURADA and r["guardados_unicos"] == 0


def test_comprobar_ahora_con_la_fuente_caida_NO_dice_que_todo_va_bien(configurada, monkeypatch):
    _con_feed(monkeypatch, [], falla="SEC respondió 403")
    r = asyncio.run(w.comprobar_ahora(_DB(cartera=[("NVDA", 12)])))
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
    r = asyncio.run(w.comprobar_ahora(db))
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
