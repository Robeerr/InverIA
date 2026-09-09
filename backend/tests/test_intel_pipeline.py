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


# ── Ya conocido NO es descartado ─────────────────────────────────────────────
# La distinción no es cosmética. El feed de la SEC devuelve los mismos 40 registros cada
# cinco minutos, así que en régimen normal casi todo lo que se lee ya lo teníamos. Contarlo
# como descarte daría una tasa de descarte del 90 % —un filtro aparentemente fuera de
# control— justo cuando lo que demuestra es que la deduplicación funciona.

def test_un_repetido_NO_cuenta_como_descartado():
    crudos = [_crudo(symbol="NVDA", externo_id="a")]
    r = pl.procesar(crudos, universo={"NVDA"}, ids_conocidos={"sec:a"}, cartera={"NVDA"})
    assert r["repetidos"] == 1
    assert r["descartados"] == 0        # el filtro no ha tumbado nada


def test_ya_conocido_NO_aparece_entre_los_motivos_del_filtro():
    """`por_motivo` responde «por qué tiró el filtro». Un repetido no llegó al filtro."""
    r = pl.procesar([_crudo(symbol="NVDA")], universo={"NVDA"},
                    ids_conocidos={"sec:a1"}, cartera={"NVDA"})
    assert pl.DUPLICADO not in r["por_motivo"]
    assert pl.DUPLICADO not in pl.MOTIVOS


def test_los_numeros_CUADRAN_entre_si():
    """recibidos = repetidos + nuevos, y nuevos = descartados + los que pasan. Sin esta
    aritmética los seis números de la pantalla no se pueden leer como una cadena."""
    crudos = [_crudo(symbol="NVDA", externo_id="a"),    # nuevo y significativo
              _crudo(symbol="TSLA", externo_id="b"),    # nuevo, lo tumba el filtro
              _crudo(symbol="NVDA", externo_id="ya")]   # ya conocido
    r = pl.procesar(crudos, universo={"NVDA"}, ids_conocidos={"sec:ya"}, cartera={"NVDA"})
    assert r["recibidos"] == 3
    assert r["repetidos"] == 1
    assert r["nuevos"] == 2
    assert r["descartados"] == 1
    assert r["recibidos"] == r["repetidos"] + r["nuevos"]
    # Los que pasan el filtro son los que se guardan menos los descartados.
    pasan = len(r["guardar"]) - r["descartados"]
    assert r["nuevos"] == r["descartados"] + pasan


def test_lo_ya_conocido_NO_se_reescribe(  ):
    """La consecuencia práctica de no ser un descarte: tampoco se guarda otra vez. Un
    evento que ya llegó a significativo no puede retroceder porque el feed lo repita."""
    r = pl.procesar([_crudo(symbol="NVDA", externo_id="a")], universo={"NVDA"},
                    ids_conocidos={"sec:a"}, cartera={"NVDA"})
    assert r["guardar"] == []


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


# ── La relevancia mide DOS ejes, no uno ──────────────────────────────────────
# La v1 medía solo cuánto te toca, y la escala se quedó con dos valores: todo lo de una
# acción tuya salía CRÍTICO y todo lo de una seguida salía ATENCIÓN. Un Form 4 de 200
# acciones pesaba igual que un 8-K de fusión.

def _puntuado(suceso=None, tier=1, tenencia="cartera"):
    e = ev.crear(fuente="x", externo_id="a", titulo="t", symbol="NVDA", tier=tier,
                 tipo=ev.CORPORATIVO, crudo={"suceso": suceso} if suceso else {})
    e = ev.avanzar(ev.avanzar(ev.avanzar(e, ev.NORMALIZADO), ev.DEDUPLICADO), ev.FILTRADO)
    # El worker mete los símbolos de la Cartera TAMBIÉN en la watchlist, así que el caso
    # real de una acción en cartera es estar en los dos conjuntos.
    kw = {"cartera": {"cartera": {"NVDA"}, "watchlist": {"NVDA"}},
          "watchlist": {"watchlist": {"NVDA"}},
          "ajena": {}}[tenencia]
    return pl.puntuar(e, **kw)


def test_cartera_y_watchlist_NO_se_suman():
    """Tener la acción ya implica seguirla. Sumar las dos daba 70 de salida a cualquier
    cosa que rozara tu cartera, y ahí se perdía toda la escala."""
    assert _puntuado(tenencia="cartera")["relevancia"] == \
        pl.PESO_CARTERA + pl.PESO_TIER[1] + pl.PESO_SUCESO_DESCONOCIDO
    # Y sigue pesando más que solo seguirla: la diferencia se conserva.
    assert _puntuado(tenencia="cartera")["relevancia"] > _puntuado(tenencia="watchlist")["relevancia"]


def test_la_CLASE_DE_SUCESO_cambia_la_nota():
    """Lo que faltaba: un eje para «qué clase de cosa es esto». Sin él, un trámite y un
    hecho relevante entran igual."""
    assert _puntuado("8-K")["relevancia"] > _puntuado("4")["relevancia"]
    assert _puntuado("publicado")["relevancia"] > _puntuado("programado")["relevancia"]


def test_el_suceso_lo_dice_LA_FUENTE_y_no_lo_adivinamos():
    """`crudo["suceso"]` lo escribe cada connector con su propio vocabulario. El pipeline
    no sabe qué es la SEC ni qué formularios existen."""
    assert pl.suceso_de({"crudo": {"suceso": "8-K"}}) == "8-K"
    assert pl.suceso_de({"crudo": {}}) is None
    assert pl.suceso_de(None) is None


def test_un_suceso_desconocido_ni_se_premia_ni_se_castiga():
    """Una fuente nueva no puede entrar desactivada ni desbocada mientras no se le
    asigne un peso."""
    intermedio = pl.PESO_SUCESO_DESCONOCIDO
    assert min(pl.PESO_SUCESO.values()) <= intermedio <= max(pl.PESO_SUCESO.values())
    assert pl.peso_del_suceso({"crudo": {"suceso": "algo_que_no_conocemos"}}) == intermedio
    assert pl.peso_del_suceso({"crudo": {}}) == intermedio


def test_un_TRAMITE_de_tu_cartera_no_te_interrumpe():
    """La mayoría de los Form 4 son consolidaciones automáticas de acciones. Sin leer el
    documento no se puede saber si este lo es, así que entra en la lista pero no llama a
    la puerta. Cuando haya fase de investigación, cambiará."""
    r = _puntuado("4", tier=1, tenencia="cartera")
    assert r["etapa"] == ev.SIGNIFICATIVO           # sale en la lista
    assert r["nivel_alerta"] not in ev.INTERRUMPEN  # pero no interrumpe


def test_un_HECHO_RELEVANTE_de_tu_cartera_SI_te_interrumpe():
    """Un 8-K la empresa está obligada a publicarlo: por definición es material."""
    assert _puntuado("8-K", tier=1, tenencia="cartera")["nivel_alerta"] in ev.INTERRUMPEN


def test_lo_de_una_accion_que_solo_SIGUES_nunca_interrumpe():
    """No hay dinero dentro. Merece estar en la lista, no sacarte de lo que estés
    haciendo."""
    for suceso in list(pl.PESO_SUCESO) + [None]:
        for tier in (1, 2):
            r = _puntuado(suceso, tier=tier, tenencia="watchlist")
            assert r["nivel_alerta"] not in ev.INTERRUMPEN, (suceso, tier)


def test_LA_MATRIZ_ENTERA_esta_fijada():
    """La tabla acordada, caso por caso. Es el test que se rompe si alguien mueve un peso
    sin darse cuenta de a quién deja de avisar."""
    esperado = {
        ("cartera", 1, "8-K"): (80, ev.IMPORTANT),
        ("cartera", 1, "4"): (60, ev.WATCH),
        ("cartera", 2, "publicado"): (75, ev.IMPORTANT),
        ("cartera", 2, "cambio_fecha"): (70, ev.IMPORTANT),
        ("cartera", 2, "programado"): (60, ev.WATCH),
        ("watchlist", 1, "8-K"): (60, ev.WATCH),
        ("watchlist", 1, "4"): (40, ev.WATCH),
        ("watchlist", 2, "publicado"): (55, ev.WATCH),
        ("watchlist", 2, "cambio_fecha"): (50, ev.WATCH),
        ("watchlist", 2, "programado"): (40, ev.WATCH),
    }
    for (tenencia, tier, suceso), (nota, nivel) in esperado.items():
        r = _puntuado(suceso, tier=tier, tenencia=tenencia)
        assert (r["relevancia"], r["nivel_alerta"]) == (nota, nivel), \
            f"{tenencia}/{tier}/{suceso} da {r['relevancia']} {r['nivel_alerta']}"


def test_NADA_llega_a_critico_todavia():
    """Decisión explícita. Para saber si un 8-K es una fusión o el nombramiento de un
    directivo hay que LEERLO, y eso es la fase de investigación. Repartir CRÍTICO por
    categoría sería volver al problema que esta recalibración arregla."""
    for tenencia in ("cartera", "watchlist"):
        for tier in (1, 2, 3, 4):
            for suceso in list(pl.PESO_SUCESO) + [None]:
                r = _puntuado(suceso, tier=tier, tenencia=tenencia)
                assert r["nivel_alerta"] != ev.CRITICAL, (tenencia, tier, suceso)


def test_la_nota_lleva_la_VERSION_de_la_formula():
    """Dos notas calculadas con reglas distintas no se pueden comparar, y nadie podría
    saberlo mirándolas. El sello es lo que permite repasarlas después."""
    assert _puntuado("8-K")["relevancia_v"] == pl.RELEVANCIA_V


def test_el_peso_de_TESIS_existe_pero_hoy_no_llega_a_nada():
    """`tesis` no lo pasa el worker y no hay ninguna colección de tesis por símbolo. Se
    conserva para la fase siguiente, pero no se puede contar con él para ningún umbral —
    y este test lo deja dicho en vez de que alguien lo asuma."""
    import inspect
    import intel_worker
    llamada = inspect.getsource(intel_worker.ciclo)
    assert "tesis=" not in llamada, "si ya se pasa tesis, actualiza este test y la fórmula"
