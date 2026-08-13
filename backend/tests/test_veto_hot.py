"""Estar cerca de tu nivel es un hecho. Llamarlo COMPRA es una autorización.

QUÉ SE CORRIGE

`/signals/hot` decidía `action` mirando SOLO qué campo estaba más cerca:

    best_action = "VENTA" if lk == "deseado" else "COMPRA"

Sin mirar la tendencia. Una acción en caída libre acercándose a un `nivel3` que
escribiste hace meses salía como COMPRA — y no solo por la API: la portada «Hoy» llama a
este endpoint con `limit=50` e imprime literalmente «· sería una compra» desde este campo
(`hoy.tarjeta_nivel`). El aviso llegaba a la primera pantalla que se mira cada mañana.

QUÉ SE CONSERVA, Y POR QUÉ

La tarjeta entera. «X está a un 2% de tu Nivel 3» sigue siendo verdad y sigue siendo útil:
te dice que el precio ha llegado donde esperabas. Lo único que se retira es el verbo que
lo convierte en un permiso. Con `action` a None, la coletilla de `hoy.py` desaparece sola
—hace `if accion`— y no hace falta tocar esa pantalla.

TRES COSAS QUE NO CAMBIAN

  · Las VENTAS. `deseado` es el único que las produce, y vender no se veta.
  · Los niveles GUARDADOS. Esto es presentación; tu tabla no se reescribe.
  · El orden ni el recorte a `limit`.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _codigo(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    return re.sub(r"#.*", "", src)


SRV = _codigo(os.path.join(_BACKEND, "server.py"))


def _cuerpo(nombre: str, src: str = None) -> str:
    src = SRV if src is None else src
    ini = src.index(f"def {nombre}(")
    resto = src[ini:]
    m = re.search(r"\n(?:def |async def |@api_router|@app\.)", resto[1:])
    return resto[: m.start() + 1] if m else resto


# ── Dobles ──────────────────────────────────────────────────────────────────

class _Coleccion:
    def __init__(self, docs):
        self.docs = docs
        self.escrituras = []

    def find(self, filtro, proyeccion=None):
        docs = self.docs

        class _Cursor:
            async def to_list(self, n):
                return list(docs)[:n]
        return _Cursor()

    async def update_one(self, *a, **k):
        self.escrituras.append(("update_one", a))

    async def insert_one(self, *a, **k):
        self.escrituras.append(("insert_one", a))


class _DB:
    def __init__(self, docs):
        self.signal_entries = _Coleccion(docs)


def _entrada(symbol, **campos):
    base = {"symbol": symbol, "name": symbol, "active": True, "last_price": 100.0}
    base.update(campos)
    return base


@pytest.fixture
def entorno(monkeypatch):
    import server

    estado = {"por_symbol": {}, "defecto": "ALCISTA", "consultas": []}

    def _tendencia_de(sym):
        estado["consultas"].append(sym)
        valor = estado["por_symbol"].get(sym, estado["defecto"])
        if isinstance(valor, Exception):
            raise valor
        return valor

    monkeypatch.setattr(server.market_data, "tendencia_de", _tendencia_de)
    server._cache._store.pop("signals_hot", None)
    return server, estado


async def _hot(server, docs, monkeypatch, limit=5):
    monkeypatch.setattr(server, "db", _DB(docs))
    server._cache._store.pop("signals_hot", None)
    return await server.hot_signals(limit=limit, _user="test")


def _de(resultados, symbol):
    return next(r for r in resultados if r["symbol"] == symbol)


# ── 1-3 · El candidato vetado conserva la tarjeta, pierde el verbo ──────────

@pytest.mark.anyio
async def test_un_candidato_de_compra_vetado_no_sale_como_compra(entorno, monkeypatch):
    server, estado = entorno
    estado["por_symbol"]["CAE"] = "BAJISTA"
    r = await _hot(server, [_entrada("CAE", nivel3=98.0)], monkeypatch)
    assert _de(r, "CAE")["action"] is None


@pytest.mark.anyio
async def test_el_hecho_descriptivo_sobrevive_entero(entorno, monkeypatch):
    """La tarjeta no desaparece: que el precio haya llegado a tu nivel sigue siendo
    verdad, y sigue siendo la información por la que escribiste ese número."""
    server, estado = entorno
    estado["por_symbol"]["CAE"] = "BAJISTA"
    item = _de(await _hot(server, [_entrada("CAE", nivel3=98.0)], monkeypatch), "CAE")
    assert item["price"] == 100.0
    assert item["target"] == 98.0
    assert item["level_label"] == "nivel3"
    assert item["pct_away"] == pytest.approx(2.04, abs=0.01)
    assert item["name"] == "CAE"


@pytest.mark.anyio
async def test_la_tarjeta_dice_por_que_no_es_una_compra(entorno, monkeypatch):
    import estado_accion
    server, estado = entorno
    estado["por_symbol"]["CAE"] = "BAJISTA"
    item = _de(await _hot(server, [_entrada("CAE", nivel3=98.0)], monkeypatch), "CAE")
    assert item["vetado_por_tendencia"] is True
    assert item["veto_motivo"] == estado_accion.evaluar("BAJISTA")["motivo"]


# ── 4 · Las ventas no se tocan ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_la_venta_sigue_siendo_venta_aunque_la_tendencia_vete(entorno, monkeypatch):
    """`deseado` es un objetivo de VENTA. El veto es sobre comprar: una acción en caída
    es justamente donde una orden de venta importa más."""
    server, estado = entorno
    estado["por_symbol"]["CAE"] = "BAJISTA"
    item = _de(await _hot(server, [_entrada("CAE", deseado=102.0)], monkeypatch), "CAE")
    assert item["action"] == "VENTA"
    assert "vetado_por_tendencia" not in item
    assert estado["consultas"] == []


@pytest.mark.anyio
async def test_una_venta_y_una_compra_en_la_misma_lista(entorno, monkeypatch):
    server, estado = entorno
    estado["por_symbol"] = {"CAE": "BAJISTA", "SUBE": "BAJISTA"}
    r = await _hot(server, [_entrada("CAE", nivel1=98.0),
                            _entrada("SUBE", deseado=101.0)], monkeypatch)
    assert _de(r, "CAE")["action"] is None
    assert _de(r, "SUBE")["action"] == "VENTA"


# ── 5 · Solo NO_COMPRAR veta ────────────────────────────────────────────────

@pytest.mark.anyio
async def test_una_tendencia_comprobada_no_bloqueante_deja_la_compra(entorno, monkeypatch):
    """ALCISTA e INDEFINIDA se COMPROBARON las dos. Que la segunda no sea una tendencia
    clara no es lo mismo que no haber podido mirar: hay 200 cierres y el precio y las
    medias no coinciden. Es información, no ausencia."""
    server, estado = entorno
    for tend in ("ALCISTA", "INDEFINIDA"):
        estado["por_symbol"]["X"] = tend
        item = _de(await _hot(server, [_entrada("X", nivel2=99.0)], monkeypatch), "X")
        assert item["action"] == "COMPRA", tend
        assert "vetado_por_tendencia" not in item, tend


# ── 6 · Lo no verificable tampoco se presenta como compra ──────────────────

@pytest.mark.anyio
async def test_un_error_de_lectura_nunca_produce_una_compra(entorno, monkeypatch):
    """La aserción explícita: pase lo que pase con `tendencia_de`, de aquí no sale una
    COMPRA. Fallo cerrado — no se presenta como compra lo que no se ha comprobado."""
    server, estado = entorno
    for fallo in (RuntimeError("histórico caído"), TimeoutError(), ValueError("vacío")):
        estado["por_symbol"]["ROTO"] = fallo
        item = _de(await _hot(server, [_entrada("ROTO", nivel1=99.0)], monkeypatch), "ROTO")
        assert item["action"] != "COMPRA", fallo
        assert item["action"] is None, fallo


@pytest.mark.anyio
async def test_sin_datos_tampoco_se_presenta_como_compra(entorno, monkeypatch):
    """`SIN_DATOS` es lo que emite `tendencia.py` con menos de 200 cierres. `estado_accion`
    lo traduce a EN_SEGUIMIENTO —vigílalo, no es un rechazo—, que es correcto para el
    estado de la acción pero insuficiente para etiquetar una proximidad como compra."""
    server, estado = entorno
    estado["por_symbol"]["NUEVA"] = "SIN_DATOS"
    item = _de(await _hot(server, [_entrada("NUEVA", nivel1=99.0)], monkeypatch), "NUEVA")
    assert item["action"] is None
    assert item["vetado_por_tendencia"] is True


@pytest.mark.anyio
async def test_lo_no_verificable_se_explica_distinto_del_veto(entorno, monkeypatch):
    """«No lo sé» y «está bajista» ocultan los dos la compra, pero no son lo mismo: la
    segunda es una afirmación sobre el mercado, y con el histórico caído nadie la ha
    hecho. Los dos motivos tienen que poder distinguirse."""
    import estado_accion
    import veto_compra
    server, estado = entorno
    estado["por_symbol"] = {"ROTO": RuntimeError("caído"), "BAJA": "BAJISTA"}
    r = await _hot(server, [_entrada("ROTO", nivel1=99.0),
                            _entrada("BAJA", nivel1=99.5)], monkeypatch)
    assert _de(r, "ROTO")["veto_motivo"] == veto_compra.MOTIVO_NO_VERIFICABLE
    assert _de(r, "BAJA")["veto_motivo"] == estado_accion.evaluar("BAJISTA")["motivo"]
    assert _de(r, "ROTO")["veto_motivo"] != _de(r, "BAJA")["veto_motivo"]


@pytest.mark.anyio
async def test_un_fallo_suelto_no_contamina_a_los_demas(entorno, monkeypatch):
    """El fallo de un símbolo no puede arrastrar al de al lado, ni tumbar el endpoint."""
    server, estado = entorno
    estado["por_symbol"] = {"ROTO": RuntimeError("caído"), "SANA": "ALCISTA",
                            "BAJA": "BAJISTA"}
    r = await _hot(server, [_entrada("ROTO", nivel1=99.0), _entrada("SANA", nivel1=99.2),
                            _entrada("BAJA", nivel1=99.4)], monkeypatch)
    assert _de(r, "ROTO")["action"] is None
    assert _de(r, "SANA")["action"] == "COMPRA"
    assert _de(r, "BAJA")["action"] is None


@pytest.mark.anyio
async def test_el_candidato_no_verificable_conserva_sus_datos(entorno, monkeypatch):
    """Igual que el vetado: la tarjeta entera se queda, solo se va el verbo."""
    server, estado = entorno
    estado["por_symbol"]["ROTO"] = RuntimeError("caído")
    item = _de(await _hot(server, [_entrada("ROTO", nivel3=98.0)], monkeypatch), "ROTO")
    assert item["price"] == 100.0
    assert item["target"] == 98.0
    assert item["level_label"] == "nivel3"
    assert item["pct_away"] == pytest.approx(2.04, abs=0.01)


@pytest.mark.anyio
async def test_un_error_no_borra_el_nivel_guardado(entorno, monkeypatch):
    server, estado = entorno
    estado["por_symbol"]["ROTO"] = RuntimeError("caído")
    db = _DB([_entrada("ROTO", nivel1=99.0)])
    monkeypatch.setattr(server, "db", db)
    server._cache._store.pop("signals_hot", None)
    await server.hot_signals(limit=5, _user="test")
    assert db.signal_entries.escrituras == []
    assert db.signal_entries.docs[0]["nivel1"] == 99.0


@pytest.mark.anyio
async def test_una_venta_no_verificable_sigue_siendo_venta(entorno, monkeypatch):
    """El fallo cerrado es sobre COMPRAR. Una venta ni siquiera pregunta por la tendencia,
    así que un histórico caído no puede afectarla."""
    server, estado = entorno
    estado["por_symbol"]["ROTO"] = RuntimeError("caído")
    item = _de(await _hot(server, [_entrada("ROTO", deseado=101.0)], monkeypatch), "ROTO")
    assert item["action"] == "VENTA"
    assert "vetado_por_tendencia" not in item


def test_no_verificable_y_veto_son_preguntas_distintas():
    """Sobre la función pura, para que la distinción no dependa del endpoint."""
    import veto_compra
    assert veto_compra.no_verificable("SIN_DATOS") is True
    assert veto_compra.no_verificable(None) is True
    assert veto_compra.no_verificable("") is True
    assert veto_compra.no_verificable(7) is True
    assert veto_compra.no_verificable("ALCISTA") is False
    assert veto_compra.no_verificable("INDEFINIDA") is False
    assert veto_compra.no_verificable("BAJISTA") is False
    # Y no se solapan: BAJISTA es verificable Y vetado; SIN_DATOS ni una cosa ni la otra.
    assert veto_compra.hay_veto("NO_COMPRAR") is True
    assert veto_compra.no_verificable("NO_COMPRAR") is False


# ── 7 · El coste se acota ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_solo_se_pregunta_por_los_candidatos_de_compra_cercanos(entorno, monkeypatch):
    """La Cartera puede tener 200 entradas. Preguntar por todas serían 200 lecturas de
    histórico para descartar casi todas por distancia."""
    server, estado = entorno
    estado["defecto"] = "ALCISTA"
    docs = [
        _entrada("CERCA", nivel1=99.0),      # dentro del 10%  → se pregunta
        _entrada("LEJOS", nivel1=40.0),      # al 150%         → ni entra en results
        _entrada("VENDE", deseado=101.0),    # es VENTA        → no se pregunta
        _entrada("SINNIVEL"),                # sin niveles     → ni entra
    ]
    await _hot(server, docs, monkeypatch, limit=10)
    assert estado["consultas"] == ["CERCA"]


# ── 8 · El orden y el recorte no cambian ────────────────────────────────────

@pytest.mark.anyio
async def test_el_orden_por_distancia_y_el_limite_se_conservan(entorno, monkeypatch):
    server, estado = entorno
    estado["defecto"] = "BAJISTA"
    docs = [_entrada("C", nivel1=95.0), _entrada("A", nivel1=99.5),
            _entrada("B", nivel1=98.0)]
    r = await _hot(server, docs, monkeypatch, limit=2)
    assert [x["symbol"] for x in r] == ["A", "B"]
    assert all(x["action"] is None for x in r)


# ── 9 · No se toca ni un nivel guardado ─────────────────────────────────────

@pytest.mark.anyio
async def test_no_se_escribe_nada_en_la_cartera(entorno, monkeypatch):
    """Un nivel escrito hace meses sigue donde estaba cuando la tendencia se gira. Esto
    es presentación; reescribir la tabla del usuario sería otra cosa y no está aprobada."""
    server, estado = entorno
    estado["defecto"] = "BAJISTA"
    db = _DB([_entrada("CAE", nivel1=99.0, nivel2=95.0)])
    monkeypatch.setattr(server, "db", db)
    server._cache._store.pop("signals_hot", None)
    await server.hot_signals(limit=5, _user="test")
    assert db.signal_entries.escrituras == []
    assert db.signal_entries.docs[0]["nivel1"] == 99.0
    assert db.signal_entries.docs[0]["nivel2"] == 95.0


# ── 10-11 · Arquitectura y alcance ──────────────────────────────────────────

def test_la_regla_sigue_centralizada():
    assert '"NO_COMPRAR"' not in SRV
    hot = _cuerpo("hot_signals")
    assert "veto_compra.hay_veto" in hot
    assert "estado_accion.evaluar" in hot


def test_hot_no_reimplementa_la_clasificacion():
    hot = _cuerpo("hot_signals")
    for propio in ("sma200", "sma50", "clasificar(", "BAJISTA", "ALCISTA"):
        assert propio not in hot, propio


def test_hoy_no_se_ha_tocado():
    """Con `action: None`, `hoy.tarjeta_nivel` deja de imprimir la coletilla por sí solo:
    hace `if accion`. Esa es la razón de elegir None y no una etiqueta nueva."""
    codigo = _codigo(os.path.join(_BACKEND, "hoy.py"))
    for ajeno in ("veto_compra", "NO_COMPRAR", "tendencia_de", "vetado_por_tendencia"):
        assert ajeno not in codigo, ajeno
    assert 'accion = (caliente.get("action") or "").lower()' in codigo
    assert 'f" · sería una {accion}" if accion else ""' in codigo
