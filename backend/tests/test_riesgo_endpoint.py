"""El endpoint junta tres fuentes sin perder nada por el camino.

El modelo de margen necesita, por posición: valor, acciones, sector, categoría A-D y
divisa. Ninguna fuente las tiene todas — el valor sale del libro de operaciones, el sector
y la categoría de la ficha de la Cartera — así que la unión se hace en `server`, y si se
pierde una pieza el modelo cambia de respuesta en silencio.

Eso es lo que se prueba aquí: que la categoría llega, que sin extracto de DEGIRO el
endpoint se calla, y que con él da euros.

Ejecutar:  cd backend && pytest tests/test_riesgo_endpoint.py -v
"""
import pytest

import riesgo_cartera as rc


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _Coleccion:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, filtro=None, proj=None):
        docs = list(self.docs)

        class _C:
            async def to_list(self, n):
                return docs[:n]

            def sort(self, *a, **k):
                return self
        return _C()

    async def find_one(self, filtro=None, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in (filtro or {}).items()):
                return d
        return None


class _DB:
    def __init__(self, entries, extracto=None):
        self.signal_entries = _Coleccion(entries)
        self.margen_degiro = _Coleccion([extracto] if extracto else [])
        self.compras = _Coleccion()
        self.ventas = _Coleccion()
        self.ajustes = _Coleccion()
        self.precios_manuales = _Coleccion()
        self.dividendos = _Coleccion()


# Cuatro posiciones, no dos: con solo dos el riesgo lo marca el componente de EVENTO —la
# mayor posición individual— y el orden del ranking sale al revés. No es un fallo del
# modelo, es que una cartera de dos valores está concentradísima. La de verdad tiene 16.
FICHAS = [
    {"symbol": "FN", "last_price": 100.0, "sector": "Tecnología", "categoria_degiro": "C"},
    {"symbol": "ORCL", "last_price": 100.0, "sector": "Tecnología", "categoria_degiro": "C"},
    {"symbol": "NFLX", "last_price": 100.0, "sector": "Comunicación", "categoria_degiro": "A"},
    {"symbol": "AAOI", "last_price": 50.0, "sector": "Tecnología", "categoria_degiro": "D"},
]

POSICIONES = [
    {"symbol": "FN", "valor_eur": 4560.48, "acciones": 12, "sector": "Tecnología",
     "categoria": "C", "divisa": "USD"},
    {"symbol": "ORCL", "valor_eur": 4247.20, "acciones": 35, "sector": "Tecnología",
     "categoria": "C", "divisa": "USD"},
    {"symbol": "NFLX", "valor_eur": 3423.53, "acciones": 50, "sector": "Comunicación",
     "categoria": "A", "divisa": "USD"},
    {"symbol": "AAOI", "valor_eur": 992.71, "acciones": 9, "sector": "Tecnología",
     "categoria": "D", "divisa": "USD"},
]


def _resumen_falso():
    return {"posiciones": [{k: p[k] for k in ("symbol", "valor_eur", "acciones", "divisa")}
                           for p in POSICIONES]}


def _extracto_coherente():
    """El riesgo del extracto se calcula con el propio modelo, para que estos tests midan
    la FONTANERÍA del endpoint y no vuelvan a medir el modelo, que ya tiene los suyos."""
    riesgo, _, _ = rc.riesgo(POSICIONES)
    return {"id": "actual", "riesgo_eur": round(riesgo, 2), "fecha": "2026-08-21"}


@pytest.fixture
def entorno(monkeypatch):
    import server

    async def _resumen(db, precios):
        return _resumen_falso()

    monkeypatch.setattr(server.cartera_api, "resumen_cartera", _resumen)
    return server


@pytest.mark.anyio
async def test_la_categoria_y_la_divisa_llegan_al_modelo(entorno, monkeypatch):
    """Si se perdiera la categoría, AAOI dejaría de ser D y el resultado cambiaría sin
    que nada fallara: exactamente el tipo de error que no se ve."""
    monkeypatch.setattr(entorno, "db", _DB(FICHAS))
    pos = await entorno._posiciones_con_riesgo()
    por_sym = {p["symbol"]: p for p in pos}
    assert por_sym["AAOI"]["categoria"] == "D"
    assert por_sym["FN"]["categoria"] == "C"
    assert por_sym["FN"]["sector"] == "Tecnología"
    assert por_sym["FN"]["divisa"] == "USD"
    assert por_sym["FN"]["acciones"] == 12


@pytest.mark.anyio
async def test_sin_extracto_el_endpoint_se_calla(entorno, monkeypatch):
    monkeypatch.setattr(entorno, "db", _DB(FICHAS))
    r = await entorno.riesgo_de_vender("FN", _user="test")
    assert r["estado"] == rc.SIN_CALIBRAR
    assert "margen_eur" not in r


@pytest.mark.anyio
async def test_con_extracto_da_euros(entorno, monkeypatch):
    monkeypatch.setattr(entorno, "db", _DB(FICHAS, _extracto_coherente()))

    r = await entorno.riesgo_de_vender("AAOI", _user="test")
    assert r["estado"] == rc.OK
    assert r["margen_eur"] > 0
    # AAOI es categoría D: entra al 100% de su valor en los componentes neto, sectorial y
    # bruto, así que venderla los retira enteros. No llega al 100% del importe porque al
    # quitarla toma el relevo otro componente —aquí el de evento, la mayor posición— y ese
    # pone un suelo. Que el máximo se traslade así es justo lo que el modelo describe.
    assert r["pct_del_importe"] > 0.7
    assert r["dominante_antes"] == "sector"
    assert r["dominante_despues"] == "evento"


@pytest.mark.anyio
async def test_el_ranking_ordena_por_lo_que_libera_cada_euro(entorno, monkeypatch):
    """Es lo que DEGIRO no da: su pantalla solo calcula la orden que ya estás componiendo."""
    monkeypatch.setattr(entorno, "db", _DB(FICHAS, _extracto_coherente()))
    r = await entorno.ranking_de_riesgo(_user="test")
    assert r["estado"] == rc.OK
    pcts = [p["pct_del_importe"] for p in r["posiciones"]]
    assert pcts == sorted(pcts, reverse=True)
    assert r["posiciones"][0]["symbol"] == "AAOI", "la de categoría D libera más por euro"


# ── Acciones en vez de euros ─────────────────────────────────────────────────
# Una orden se teclea en ACCIONES, no en euros. El importe se deriva en el servidor, con el
# mismo precio que usa el modelo: si se cotizara aparte habría dos verdades sobre el mismo
# número y 15 acciones simuladas no valdrían lo mismo que 15 acciones vendidas.

@pytest.mark.anyio
async def test_simular_en_acciones_usa_el_precio_del_propio_modelo(entorno, monkeypatch):
    monkeypatch.setattr(entorno, "db", _DB(FICHAS, _extracto_coherente()))
    # AAOI: 992,71 € en 9 acciones. Tres acciones tienen que ser exactamente un tercio.
    r = await entorno.simular_margen("AAOI", accion="vender", acciones=3, _user="test")
    assert r["estado"] == rc.OK
    # abs=0.01 porque `importe_eur` se devuelve redondeado a céntimos.
    assert r["importe_eur"] == pytest.approx(992.71 / 3, abs=0.01)
    assert r["acciones"] == pytest.approx(3, rel=1e-4)


@pytest.mark.anyio
async def test_no_se_puede_vender_mas_de_lo_que_tienes(entorno, monkeypatch):
    """Y las acciones devueltas son las REALMENTE simuladas, no las pedidas."""
    monkeypatch.setattr(entorno, "db", _DB(FICHAS, _extracto_coherente()))
    r = await entorno.simular_margen("AAOI", accion="vender", acciones=999, _user="test")
    assert r["importe_eur"] == pytest.approx(992.71, abs=0.01)
    assert r["acciones"] == pytest.approx(9, rel=1e-3)


@pytest.mark.anyio
async def test_sin_cotizacion_no_se_inventa_la_conversion(entorno, monkeypatch):
    """Comprar algo que no tienes y que no cotiza: mejor decirlo que estimar el precio."""
    monkeypatch.setattr(entorno, "db", _DB(FICHAS, _extracto_coherente()))
    monkeypatch.setattr(entorno.market_data, "get_quote", lambda s: None)
    r = await entorno.simular_margen("TSLA", accion="comprar", acciones=10, _user="test")
    assert r["estado"] == rc.FALTAN_DATOS
    assert "acciones a euros" in r["motivo"]
