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
    server._invalidar_signals_hot()
    return server, estado


async def _hot(server, docs, monkeypatch, limit=5, max_pct=None):
    monkeypatch.setattr(server, "db", _DB(docs))
    server._invalidar_signals_hot()
    extra = {} if max_pct is None else {"max_pct": max_pct}
    return await server.hot_signals(limit=limit, _user="test", **extra)


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
    server._invalidar_signals_hot()
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
    # Y no se solapan: BAJISTA es una tendencia comprobada, y su estado derivado es el que
    # veta. Cada función pregunta sobre un dominio distinto — `no_verificable` sobre
    # tendencias, `hay_veto` sobre estados de acción— y pasarle a una el valor de la otra
    # es un error de categoría: `no_verificable("NO_COMPRAR")` responde «no lo reconozco»,
    # que es exactamente lo correcto y el motivo de que el fallo sea cerrado.
    assert veto_compra.hay_veto("NO_COMPRAR") is True
    assert veto_compra.no_verificable("NO_COMPRAR") is True
    assert veto_compra.hay_veto("BAJISTA") is False


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
async def test_no_se_pregunta_por_los_candidatos_que_el_limite_descarta(entorno, monkeypatch):
    """El ajuste de rendimiento: ordenar y recortar ANTES de consultar la tendencia.

    Antes se preguntaba por los 30 candidatos del 10% y solo después se recortaba a 5:
    25 lecturas de histórico que se tiraban. La portada llama a este endpoint dentro de su
    `gather`, así que ese trabajo bloqueaba la respuesta entera.
    """
    server, estado = entorno
    estado["defecto"] = "BAJISTA"
    docs = [_entrada(f"T{i:02d}", nivel1=round(100 - i * 0.1, 2)) for i in range(30)]
    r = await _hot(server, docs, monkeypatch, limit=5)
    assert len(r) == 5
    assert len(estado["consultas"]) == 5, estado["consultas"]
    # Y son exactamente los cinco que se devuelven, no otros cinco.
    assert sorted(estado["consultas"]) == sorted(x["symbol"] for x in r)


@pytest.mark.anyio
async def test_recortar_antes_no_cambia_lo_que_se_devuelve(entorno, monkeypatch):
    """La garantía que hace seguro el cambio: el veto no toca `pct_away`, la única clave
    de ordenación. Se compara contra el orden calculado a mano sobre los mismos datos."""
    server, estado = entorno
    estado["defecto"] = "ALCISTA"
    docs = [_entrada("A", nivel1=95.0), _entrada("B", nivel1=99.5),
            _entrada("C", nivel1=98.0), _entrada("D", nivel1=101.0)]
    r = await _hot(server, docs, monkeypatch, limit=3)
    esperado = sorted(
        [("A", 5.0), ("B", 0.5025), ("C", 2.0408), ("D", 0.9901)], key=lambda x: x[1])[:3]
    assert [x["symbol"] for x in r] == [s for s, _ in esperado]


@pytest.mark.anyio
async def test_el_veto_sigue_aplicandose_a_lo_que_si_se_devuelve(entorno, monkeypatch):
    """Recortar antes no puede dejar sin vetar lo que sí se enseña."""
    server, estado = entorno
    estado["defecto"] = "BAJISTA"
    docs = [_entrada(f"T{i:02d}", nivel1=round(100 - i * 0.1, 2)) for i in range(30)]
    r = await _hot(server, docs, monkeypatch, limit=5)
    assert all(x["action"] is None for x in r)
    assert all(x["vetado_por_tendencia"] is True for x in r)


@pytest.mark.anyio
async def test_las_ventas_no_gastan_hueco_de_consulta_ni_en_el_recorte(entorno, monkeypatch):
    server, estado = entorno
    estado["defecto"] = "BAJISTA"
    docs = [_entrada("V1", deseado=100.1), _entrada("V2", deseado=100.2),
            _entrada("C1", nivel1=99.9)]
    r = await _hot(server, docs, monkeypatch, limit=3)
    assert estado["consultas"] == ["C1"]
    assert len(r) == 3


def test_la_portada_pide_por_distancia_y_no_por_cantidad():
    """`/hoy` pedía 50 filas del 10% y descartaba todo lo que superara el 4%. Con una
    lectura de histórico por candidato, esa banda dejó de ser solo memoria: era tiempo de
    respuesta. Ahora el umbral que se pide ES el que la portada aplica.

    Y NO se recorta por cercanía: el límite que viaja es el tope de seguridad, no una
    selección. Quien elige las tarjetas es `hoy.tarjeta_nivel` por urgencia."""
    import hoy as _hoy
    hoy_endpoint = _cuerpo("dashboard_hoy")
    assert "_candidatos_calientes(_HOY_MAX_CANDIDATOS_NIVEL, hoy.UMBRAL_NIVEL_PCT)" \
        in hoy_endpoint
    assert "hot_signals(limit=50" not in SRV
    assert "hot_signals(limit=_HOY_MAX_TARJETAS" not in SRV, (
        "el tope de TARJETAS no puede usarse como tope de CANDIDATOS: recortaría por "
        "cercanía y borraría una tarjeta lejana con zona fuerte")
    assert _hoy.UMBRAL_NIVEL_PCT == 4.0
    # La portada ya no pasa por el endpoint: pide los candidatos SIN vetar y resuelve la
    # tendencia solo de las tarjetas que sobreviven al ranking.
    assert "hot_signals(" not in hoy_endpoint


# ── El umbral de distancia: se pide lo que se va a pintar ──────────────────

@pytest.mark.anyio
async def test_un_candidato_al_6_por_ciento_no_se_consulta_para_hoy(entorno, monkeypatch):
    """La banda 4-10% se traía, costaba una lectura de histórico cada fila y `hoy.py` la
    tiraba en `tarjeta_nivel`. Con el umbral de la portada ni siquiera entra."""
    import hoy
    server, estado = entorno
    estado["defecto"] = "BAJISTA"
    r = await _hot(server, [_entrada("LEJOS", nivel1=94.0)], monkeypatch,
                   limit=200, max_pct=hoy.UMBRAL_NIVEL_PCT)
    assert r == []
    assert estado["consultas"] == []


@pytest.mark.anyio
async def test_un_candidato_al_3_por_ciento_si_se_consulta(entorno, monkeypatch):
    import hoy
    server, estado = entorno
    estado["defecto"] = "BAJISTA"
    r = await _hot(server, [_entrada("CERCA", nivel1=97.0)], monkeypatch,
                   limit=200, max_pct=hoy.UMBRAL_NIVEL_PCT)
    assert estado["consultas"] == ["CERCA"]
    assert _de(r, "CERCA")["action"] is None


@pytest.mark.anyio
async def test_el_umbral_por_defecto_sigue_siendo_el_10(entorno, monkeypatch):
    """Ningún otro consumidor cambia de comportamiento: quien no pida umbral recibe el de
    siempre."""
    import server as _srv
    server, estado = entorno
    assert _srv._HOT_MAX_PCT_POR_DEFECTO == 10.0
    r = await _hot(server, [_entrada("SEIS", nivel1=94.0)], monkeypatch, limit=200)
    assert [x["symbol"] for x in r] == ["SEIS"]


@pytest.mark.anyio
async def test_dentro_del_umbral_vienen_TODOS_sin_recortar_por_cercania(entorno, monkeypatch):
    """El punto de la opción elegida. Un candidato al 3,5% con zona fuerte puede mandar
    sobre uno al 0,5% sin ella: la urgencia de `tarjeta_nivel` suma hasta 60 por la fuerza
    del motor y 15 por tener posición. Recortando a los 10 más cercanos habría
    desaparecido en silencio."""
    import hoy
    server, estado = entorno
    estado["defecto"] = "ALCISTA"
    docs = [_entrada(f"C{i:02d}", nivel1=round(100 - i * 0.2, 2)) for i in range(18)]
    r = await _hot(server, docs, monkeypatch, limit=200, max_pct=hoy.UMBRAL_NIVEL_PCT)
    dentro = [d for d in docs if abs(100 - d["nivel1"]) / d["nivel1"] * 100 <= 4.0]
    assert len(r) == len(dentro) > 10, f"{len(r)} devueltos de {len(dentro)} dentro del 4%"
    # El más lejano dentro del umbral sigue estando: es el que un recorte a 10 habría
    # borrado, y es justo el que puede traer la zona fuerte.
    assert r[-1]["pct_away"] == max(x["pct_away"] for x in r)


def test_tarjeta_nivel_conserva_su_seleccion_por_urgencia():
    """La selección NO se ha movido al servidor. `hoy.py` sigue siendo quien decide, y su
    urgencia sigue sumando la fuerza de la zona y la posición abierta."""
    codigo = _codigo(os.path.join(_BACKEND, "hoy.py"))
    assert 'urgencia = BASE["nivel"] + max(0, (UMBRAL_NIVEL_PCT - distancia) * 20)' in codigo
    assert "urgencia += min(60, fuerza * 0.6)" in codigo
    assert "urgencia += 15" in codigo
    assert "if distancia is None or distancia > UMBRAL_NIVEL_PCT:" in codigo
    # Y el servidor no ha aprendido a ordenar tarjetas.
    hot = _cuerpo("hot_signals")
    for ajeno in ("fuerza", "urgencia", "tiene_posicion", "UMBRAL_NIVEL_PCT"):
        assert ajeno not in hot, ajeno


def test_la_cache_distingue_los_parametros():
    """Con una sola clave, una lista acotada al 4% se serviría a quien pidió el 10%. Antes
    el error era de CANTIDAD; con `max_pct` pasaría a ser de CONTENIDO."""
    import server as _srv
    assert _srv._clave_signals_hot(5, 10.0) != _srv._clave_signals_hot(5, 4.0)
    assert _srv._clave_signals_hot(5, 4.0) != _srv._clave_signals_hot(200, 4.0)
    assert '_cache._store.pop("signals_hot", None)' not in SRV, (
        "las invalidaciones tienen que tirar TODAS las variantes")
    assert SRV.count("_invalidar_signals_hot()") >= 7


@pytest.mark.anyio
async def test_invalidar_tira_todas_las_variantes(entorno, monkeypatch):
    server, estado = entorno
    docs = [_entrada("X", nivel1=99.0)]
    await _hot(server, docs, monkeypatch, limit=5, max_pct=10.0)
    await _hot(server, docs, monkeypatch, limit=200, max_pct=4.0)
    assert [k for k in server._cache._store if k.startswith("signals_hot")]
    server._invalidar_signals_hot()
    assert [k for k in server._cache._store if k.startswith("signals_hot")] == []


def test_el_recorte_precede_a_la_consulta_en_el_codigo():
    """Fija el orden, que es donde vive la corrección: primero se calcula y se recorta,
    después se cruza con la tendencia. Ahora son dos funciones, y el orden lo impone el
    endpoint al llamarlas."""
    hot = _cuerpo("hot_signals")
    assert hot.index("_candidatos_calientes") < hot.index("_vetar_calientes")
    # El cálculo de candidatos no toca la red.
    calc = _cuerpo("_candidatos_calientes")
    for ajeno in ("tendencia_de", "veto_compra", "estado_accion", "asyncio.gather"):
        assert ajeno not in calc, ajeno
    assert "return results[:limit]" in calc
    # Y el veto trabaja sobre lo que se le pasa, no sobre todo lo calculado.
    veta = _cuerpo("_vetar_calientes")
    assert "compras = [r for r in items" in veta


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
    server._invalidar_signals_hot()
    await server.hot_signals(limit=5, _user="test")
    assert db.signal_entries.escrituras == []
    assert db.signal_entries.docs[0]["nivel1"] == 99.0
    assert db.signal_entries.docs[0]["nivel2"] == 95.0


# ── 10-11 · Arquitectura y alcance ──────────────────────────────────────────

def test_las_fronteras_del_veto_siguen_donde_estaban():
    """El ajuste es de RENDIMIENTO. Ni la autoridad ni la semántica del veto se mueven, y
    el umbral de distancia es cosa del endpoint: ningún módulo de dominio lo conoce."""
    for fichero in ("tendencia.py", "estado_accion.py", "hoy.py", "signal_table.py",
                    "cartera_api.py", "veto_compra.py"):
        codigo = _codigo(os.path.join(_BACKEND, fichero))
        assert "max_pct" not in codigo, fichero
        assert "_HOT_MAX_PCT_POR_DEFECTO" not in codigo, fichero
    op = _codigo(os.path.join(_BACKEND, "opportunities.py"))
    assert "_potential_score" in op
    assert "/opportunities/score/{symbol}" in SRV


def test_la_regla_sigue_centralizada():
    assert '"NO_COMPRAR"' not in SRV
    # El cruce vive ahora en `_vetar_calientes`, que es lo que permite aplicarlo tanto al
    # endpoint entero como solo a las tarjetas que la portada va a pintar.
    veta = _cuerpo("_vetar_calientes")
    assert "veto_compra.hay_veto" in veta
    assert "estado_accion.evaluar" in veta
    assert "market_data.tendencia_de" in veta


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
