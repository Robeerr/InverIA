"""El pipeline: de materia prima a evento significativo.

DOS COSAS QUE ESTE FICHERO PROTEGE, Y TIRAN EN DIRECCIONES OPUESTAS

  1. QUE NO ENTRE RUIDO. El filtro es lo que hace sostenible vigilar un mercado
     entero: si deja pasar lo que no te toca, la fase siguiente —investigación con
     IA— se come el presupuesto. Este proyecto ya quemó 3,65 € en un día por no
     tener un filtro delante.

  2. QUE NO SE PIERDA NADA TUYO. Lo que sí te toca pero no merece interrumpirte se
     GUARDA en `filtrado`, no se descarta. Borrarlo impediría responder después
     «¿qué sabía InverIA de esto?», que es la pregunta que sostiene el track record.

Y una tercera que las une: el recuento por motivo. Sin él, un filtro demasiado
agresivo se ve exactamente igual que un mercado tranquilo.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import intel_eventos as ev
import intel_pipeline as pl


def _crudo(symbol="NVDA", externo_id="a1", tier=1, titulo="Form 4 · Venta"):
    return ev.crear(fuente="sec", externo_id=externo_id, titulo=titulo,
                    symbol=symbol, tier=tier, tipo=ev.INSIDER)


# ── Normalizar ───────────────────────────────────────────────────────────────

def test_normalizar_deja_el_symbol_canonico():
    e = pl.normalizar(_crudo(symbol=" nvda "))
    assert e["symbol"] == "NVDA" and e["etapa"] == ev.NORMALIZADO


def test_normalizar_colapsa_los_espacios_del_titulo():
    """Los feeds traen saltos de línea y tabulaciones dentro del título."""
    e = pl.normalizar(ev.crear(fuente="sec", externo_id="a",
                               titulo="Form 4  ·\n  Venta   de acciones", symbol="X"))
    assert e["titulo"] == "Form 4 · Venta de acciones"


def test_normalizar_no_reprocesa_lo_ya_avanzado():
    """Idempotencia: pasar dos veces por el pipeline no debe duplicar pasos."""
    e = pl.normalizar(_crudo())
    assert pl.normalizar(e) is e


# ── Deduplicar ───────────────────────────────────────────────────────────────

def test_lo_ya_visto_no_vuelve_a_entrar():
    a = pl.normalizar(_crudo(externo_id="a1"))
    b = pl.normalizar(_crudo(externo_id="a2"))
    nuevos, repetidos = pl.deduplicar([a, b], ids_conocidos={"sec:a1"})
    assert [x["externo_id"] for x in nuevos] == ["a2"]
    assert [x["externo_id"] for x in repetidos] == ["a1"]


def test_el_duplicado_DENTRO_del_mismo_lote_tambien_se_caza():
    """Un feed puede traer la misma entrada dos veces. Sin esto entrarían las dos."""
    a1, a2 = pl.normalizar(_crudo(externo_id="a1")), pl.normalizar(_crudo(externo_id="a1"))
    nuevos, repetidos = pl.deduplicar([a1, a2])
    assert len(nuevos) == 1 and len(repetidos) == 1


def test_un_repetido_NO_se_marca_descartado():
    """Reescribirlo como descartado pisaría un documento que quizá ya avanzó a
    significativo. Un evento procesado no retrocede porque su feed lo mencione otra
    vez."""
    a = pl.normalizar(_crudo())
    _, repetidos = pl.deduplicar([a], ids_conocidos={a["id"]})
    assert repetidos[0]["etapa"] != ev.DESCARTADO


# ── Filtrar ──────────────────────────────────────────────────────────────────

def test_solo_pasa_lo_que_toca_a_tu_universo():
    dentro = ev.avanzar(pl.normalizar(_crudo(symbol="NVDA")), ev.DEDUPLICADO)
    fuera = ev.avanzar(pl.normalizar(_crudo(symbol="TSLA", externo_id="b")), ev.DEDUPLICADO)
    pasan, desc = pl.filtrar([dentro, fuera], universo={"NVDA"})
    assert [p["symbol"] for p in pasan] == ["NVDA"]
    assert desc[0]["motivo_descarte"] == pl.FUERA_DE_UNIVERSO


def test_sin_symbol_se_descarta_con_su_propio_motivo():
    """Separado de «fuera de universo» para poder contarlos aparte: muchos eventos sin
    símbolo significan que el parseo de la fuente está fallando, no que no te toquen."""
    e = ev.avanzar(pl.normalizar(ev.crear(fuente="sec", externo_id="x", titulo="t")),
                   ev.DEDUPLICADO)
    _, desc = pl.filtrar([e], universo={"NVDA"})
    assert desc[0]["motivo_descarte"] == pl.SIN_SYMBOL


def test_un_universo_VACIO_no_deja_pasar_nada():
    """Deliberado: significa que aún no tienes cartera ni watchlist, NO que todo te
    interese. Dejar pasar todo ahí llenaría el radar de ruido el día que lo estrenas."""
    e = ev.avanzar(pl.normalizar(_crudo()), ev.DEDUPLICADO)
    pasan, desc = pl.filtrar([e], universo=set())
    assert pasan == [] and len(desc) == 1


# ── Puntuar ──────────────────────────────────────────────────────────────────

def test_tener_la_accion_pesa_mas_que_seguirla():
    """El mismo hecho cambia lo que puedes PERDER, no solo lo que te interesa."""
    base = ev.avanzar(pl.normalizar(_crudo()), ev.DEDUPLICADO)
    con_dinero = pl.puntuar(base, cartera={"NVDA"})
    solo_mirando = pl.puntuar(base, watchlist={"NVDA"})
    assert con_dinero["relevancia"] > solo_mirando["relevancia"]


def test_la_relevancia_es_PERSONAL():
    """La misma noticia vale poco para quien no tiene la acción y mucho para quien la
    lleva. Un sistema que puntuara «relevancia objetiva» mediría otra cosa."""
    e = ev.avanzar(pl.normalizar(_crudo()), ev.DEDUPLICADO)
    ajeno = pl.puntuar(e, cartera={"AAPL"}, watchlist={"MSFT"})
    propio = pl.puntuar(e, cartera={"NVDA"}, watchlist={"NVDA"}, tesis={"NVDA"})
    assert ajeno["relevancia"] < 40 <= propio["relevancia"]
    assert propio["afecta_cartera"] and propio["afecta_watchlist"] and propio["afecta_tesis"]
    assert not ajeno["afecta_cartera"]


def test_un_filing_de_la_sec_pesa_mas_que_un_tuit():
    """Los dos pueden DESCUBRIR una señal, pero no valen igual como evidencia. Es lo
    que impide que un rumor entre como si fuera un hecho."""
    sec = pl.puntuar(ev.avanzar(pl.normalizar(_crudo(tier=1)), ev.DEDUPLICADO), watchlist={"NVDA"})
    social = pl.puntuar(ev.avanzar(pl.normalizar(_crudo(tier=4, externo_id="b")), ev.DEDUPLICADO),
                        watchlist={"NVDA"})
    assert sec["relevancia"] > social["relevancia"]


def test_lo_que_te_toca_pero_no_urge_SE_GUARDA_en_filtrado():
    """No se descarta. Borrarlo impediría responder «¿qué sabía InverIA de esto?»,
    que es la pregunta que sostiene el track record. Descartar y no-alertar son
    cosas distintas."""
    # Por el flujo REAL: es `filtrar` quien avanza a `filtrado`, y `puntuar` solo
    # mueve a `significativo` si la nota llega. Montarlo a mano saltándose el filtro
    # probaría un camino que el worker nunca recorre.
    pasan, _ = pl.filtrar([ev.avanzar(pl.normalizar(_crudo(tier=4)), ev.DEDUPLICADO)],
                          universo={"NVDA"})
    r = pl.puntuar(pasan[0], watchlist={"NVDA"})
    assert r["relevancia"] < pl.UMBRAL_SIGNIFICATIVO
    assert r["etapa"] == ev.FILTRADO and r["etapa"] != ev.DESCARTADO


def test_la_nota_se_queda_entre_0_y_100():
    e = ev.avanzar(pl.normalizar(_crudo(tier=1)), ev.DEDUPLICADO)
    r = pl.puntuar(e, cartera={"NVDA"}, watchlist={"NVDA"}, tesis={"NVDA"})
    assert 0 <= r["relevancia"] <= 100


# ── El pipeline entero ───────────────────────────────────────────────────────

def test_procesar_hace_el_recorrido_completo():
    crudos = [_crudo(symbol="NVDA", externo_id="a"),
              _crudo(symbol="TSLA", externo_id="b"),      # fuera de universo
              _crudo(symbol="NVDA", externo_id="a")]      # duplicado en el lote
    r = pl.procesar(crudos, universo={"NVDA"}, cartera={"NVDA"})
    assert r["recibidos"] == 3 and r["nuevos"] == 2
    assert len(r["significativos"]) == 1
    assert r["significativos"][0]["symbol"] == "NVDA"


def test_procesar_cuenta_los_descartes_POR_MOTIVO():
    """Sin este recuento, un filtro demasiado agresivo se ve igual que un mercado
    tranquilo. Es lo que permite calibrarlo."""
    crudos = [_crudo(symbol="TSLA", externo_id="a"),
              _crudo(symbol="TSLA", externo_id="b"),
              _crudo(symbol="NVDA", externo_id="c")]
    r = pl.procesar(crudos, universo={"NVDA"}, ids_conocidos={"sec:c"}, cartera={"NVDA"})
    assert r["por_motivo"][pl.FUERA_DE_UNIVERSO] == 2
    assert r["por_motivo"][pl.DUPLICADO] == 1


def test_los_descartados_TAMBIEN_se_guardan():
    """El descarte también es historia: es lo que permite auditar el filtro después."""
    r = pl.procesar([_crudo(symbol="TSLA")], universo={"NVDA"})
    assert len(r["guardar"]) == 1
    assert r["guardar"][0]["etapa"] == ev.DESCARTADO


def test_procesar_es_IDEMPOTENTE():
    """La condición del worker: dos vueltas sobre el mismo feed no crean nada nuevo.
    Un reinicio de Render o un solape de ciclos no puede duplicar eventos."""
    crudos = [_crudo(symbol="NVDA", externo_id="a")]
    primera = pl.procesar(crudos, universo={"NVDA"}, cartera={"NVDA"})
    ids = {e["id"] for e in primera["guardar"]}
    segunda = pl.procesar(crudos, universo={"NVDA"}, ids_conocidos=ids, cartera={"NVDA"})
    assert segunda["nuevos"] == 0 and segunda["guardar"] == []


def test_UN_EVENTO_NO_GENERA_DOS_SENALES():
    """La condición que se pidió por escrito. Una vez procesado, su id queda conocido
    y ninguna vuelta posterior vuelve a marcarlo significativo."""
    crudos = [_crudo(symbol="NVDA", externo_id="unico")]
    r1 = pl.procesar(crudos, universo={"NVDA"}, cartera={"NVDA"})
    assert len(r1["significativos"]) == 1
    ids = {e["id"] for e in r1["guardar"]}
    for _ in range(5):
        r = pl.procesar(crudos, universo={"NVDA"}, ids_conocidos=ids, cartera={"NVDA"})
        assert r["significativos"] == []


def test_sin_entrada_no_se_fabrica_nada():
    """Si la fuente está caída y no llega nada, el pipeline no inventa eventos."""
    for vacio in ([], None):
        r = pl.procesar(vacio, universo={"NVDA"}, cartera={"NVDA"})
        assert r["guardar"] == [] and r["significativos"] == [] and r["recibidos"] == 0


def test_una_entrada_corrupta_no_tumba_el_lote():
    """Un feed real trae basura de vez en cuando, y el resto del lote no tiene culpa."""
    r = pl.procesar([None, "texto suelto", {}, _crudo(symbol="NVDA")],
                    universo={"NVDA"}, cartera={"NVDA"})
    assert len(r["significativos"]) == 1
