"""El evento de inteligencia y sus ocho etapas.

LO QUE MÁS IMPORTA AQUÍ

No es que las transiciones funcionen: es que las transiciones INVÁLIDAS no ocurran.
Un sistema que vigila fuentes 24/7 y decide cuándo interrumpirte tiene un fallo caro
muy concreto —que algo ya descartado vuelva a entrar y acabe alertando—, y esa puerta
se cierra aquí.

El segundo bloque protege lo contrario: que un hueco sea visible. `investigado` y
`agrupado` están declaradas y NO se alcanzan todavía. Si algún día alguien las
conecta, debe ser a propósito.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import intel_eventos as ev


def _nuevo(**kw):
    base = dict(fuente="sec", externo_id="0000320193-26-000042",
                titulo="Form 4 · Venta de un directivo", symbol="nvda", tier=1)
    base.update(kw)
    return ev.crear(**base)


# ── Crear ────────────────────────────────────────────────────────────────────

def test_el_id_es_determinista_y_por_eso_el_worker_es_idempotente():
    """`fuente:externo_id`. Reprocesar el mismo feed —un reinicio, un solape de
    ciclos— tiene que reescribir el MISMO documento, no crear un segundo."""
    a, b = _nuevo(), _nuevo()
    assert a["id"] == b["id"] == "sec:0000320193-26-000042"


def test_el_symbol_se_guarda_en_mayusculas():
    assert _nuevo(symbol="nvda")["symbol"] == "NVDA"


def test_sin_origen_no_hay_evento():
    """Una afirmación sin fuente no se puede auditar después, y todo el valor del
    sistema está en poder preguntarle dentro de tres meses por qué dijo algo."""
    assert ev.crear(fuente="", externo_id="x", titulo="t") is None
    assert ev.crear(fuente="sec", externo_id="", titulo="t") is None
    assert ev.crear(fuente="sec", externo_id="x", titulo="  ") is None


def test_un_tipo_desconocido_no_se_guarda():
    """El tipo viaja a Mongo. Aceptar cualquier cadena obligaría a limpiar la
    colección el día que alguien escriba mal una constante."""
    assert _nuevo(tipo="LO_QUE_SEA") is None
    assert _nuevo(tipo=ev.INSIDER) is not None


def test_nace_en_recibido_y_sin_resumen():
    """`resumen` es None en la fase 0.5 y así se queda: no hay LLM, así que no hay
    prosa generada. Un resumen inventado sería peor que ninguno."""
    e = _nuevo()
    assert e["etapa"] == ev.RECIBIDO
    assert e["resumen"] is None
    assert e["relevancia"] is None and e["nivel_alerta"] is None


def test_guarda_lo_que_dijo_la_fuente_tal_cual():
    """Es lo único que permite rehacer el análisis el día que cambien las reglas sin
    volver a pedirle nada a la fuente."""
    e = _nuevo(crudo={"form": "4", "cik": "0000320193"})
    assert e["crudo"]["form"] == "4"


# ── Transiciones ─────────────────────────────────────────────────────────────

def test_el_camino_normal_llega_hasta_alertado():
    e = _nuevo()
    for etapa in (ev.NORMALIZADO, ev.DEDUPLICADO, ev.FILTRADO,
                  ev.SIGNIFICATIVO, ev.ALERTADO):
        e = ev.avanzar(e, etapa)
        assert e["etapa"] == etapa
    assert len(e["historial"]) == 6


def test_DESCARTADO_ES_TERMINAL():
    """El fallo más caro de un sistema así: que un evento ya rechazado vuelva a entrar
    por otro camino y acabe generando la señal que su filtro había impedido."""
    e = ev.avanzar(_nuevo(), ev.DESCARTADO, "fuera_de_universo")
    for destino in ev.ETAPAS:
        assert ev.avanzar(e, destino)["etapa"] == ev.DESCARTADO


def test_alertado_es_terminal():
    """Un evento no puede alertar dos veces."""
    e = _nuevo()
    for etapa in (ev.NORMALIZADO, ev.DEDUPLICADO, ev.FILTRADO,
                  ev.SIGNIFICATIVO, ev.ALERTADO):
        e = ev.avanzar(e, etapa)
    for destino in ev.ETAPAS:
        assert ev.avanzar(e, destino)["etapa"] == ev.ALERTADO


def test_no_se_pueden_saltar_etapas():
    """De recibido a significativo sin pasar el filtro sería colar un evento sin
    comprobar si te toca siquiera."""
    e = _nuevo()
    assert ev.avanzar(e, ev.SIGNIFICATIVO)["etapa"] == ev.RECIBIDO
    assert ev.avanzar(e, ev.ALERTADO)["etapa"] == ev.RECIBIDO


def test_una_transicion_invalida_no_lanza():
    """El worker procesa lotes: una excepción aquí tumbaría el ciclo entero por un
    evento raro, y el resto del lote no tiene la culpa."""
    e = ev.avanzar(_nuevo(), "etapa_inventada")
    assert e["etapa"] == ev.RECIBIDO


def test_avanzar_no_muta_el_original():
    """El que llama suele tener el documento recién leído de Mongo y decide él si
    escribe. Mutarlo lo dejaría adelantado ante cualquier fallo de escritura."""
    e = _nuevo()
    ev.avanzar(e, ev.NORMALIZADO)
    assert e["etapa"] == ev.RECIBIDO and len(e["historial"]) == 1


def test_el_motivo_del_descarte_queda_registrado():
    e = ev.avanzar(_nuevo(), ev.DESCARTADO, "fuera_de_universo")
    assert e["motivo_descarte"] == "fuera_de_universo"
    assert e["historial"][-1]["motivo"] == "fuera_de_universo"


# ── El hueco declarado ───────────────────────────────────────────────────────

def test_INVESTIGADO_se_alcanza_SOLO_desde_significativo():
    """La desviación deliberada del orden declarado. Investigar antes de saber si algo te
    toca obliga a leer todo lo que pasa el filtro: 46 llamadas a un modelo en vez de 1.

    Que solo se llegue desde `significativo` es lo que ata la investigación al scoring, y
    por tanto al presupuesto."""
    alcanzables = [d for d in ev.ETAPAS if ev.puede_avanzar(d, ev.INVESTIGADO)]
    assert alcanzables == [ev.SIGNIFICATIVO]


def test_significativo_e_investigado_NO_son_lo_mismo():
    """SIGNIFICATIVO es una decisión sobre TI: el scoring dice que te toca lo bastante
    como para gastar recursos. INVESTIGADO es un hecho sobre el DOCUMENTO: la IA ya lo
    leyó. Fundirlos haría imposible saber si algo está pendiente o es que no había nada
    que contar."""
    assert ev.SIGNIFICATIVO != ev.INVESTIGADO
    # Y no se puede volver: una vez leído, el documento está leído.
    assert ev.puede_avanzar(ev.INVESTIGADO, ev.SIGNIFICATIVO) is False


def test_un_evento_ya_investigado_SIGUE_interrumpiendo():
    """Investigar no rebaja nada: un 8-K que merecía interrumpirte lo sigue mereciendo
    después de leerlo, y con más motivo, porque ahora se sabe qué dice."""
    e = _nuevo()
    e["nivel_alerta"] = ev.IMPORTANT
    for etapa in (ev.NORMALIZADO, ev.DEDUPLICADO, ev.FILTRADO, ev.SIGNIFICATIVO,
                  ev.INVESTIGADO):
        e = ev.avanzar(e, etapa)
    assert e["etapa"] == ev.INVESTIGADO and ev.interrumpe(e) is True


def test_AGRUPADO_sigue_sin_alcanzarse():
    """Se declaró para que el hueco fuera visible y sigue vacío. Si alguien lo conecta,
    que sea a propósito y no por descuido."""
    alcanzables = [d for d in ev.ETAPAS if ev.puede_avanzar(d, ev.AGRUPADO)]
    assert alcanzables == [], f"agrupado ya es alcanzable desde {alcanzables}"


# ── Alertas ──────────────────────────────────────────────────────────────────

def test_solo_important_y_critical_interrumpen():
    """Interrumpir por todo es la forma más rápida de que dejes de mirar."""
    assert set(ev.INTERRUMPEN) == {ev.IMPORTANT, ev.CRITICAL}


def test_sin_evaluar_no_hay_nivel():
    """None y 0 son cosas distintas: None es «no se ha mirado» y 0 es «se miró y no
    importa». Devolver INFO para lo no evaluado lo colaría en la lista como si
    alguien lo hubiera revisado."""
    assert ev.nivel_de(None) is None
    assert ev.nivel_de(0) == ev.INFO


def test_los_umbrales_ordenan_de_menos_a_mas():
    assert ev.nivel_de(10) == ev.INFO
    assert ev.nivel_de(50) == ev.WATCH
    assert ev.nivel_de(70) == ev.IMPORTANT
    assert ev.nivel_de(95) == ev.CRITICAL


def test_una_relevancia_alta_NO_interrumpe_si_el_evento_fue_descartado():
    """La puerta de atrás: un evento con nota alta que el filtro tiró por otra razón
    —duplicado, fuente caída— no puede colarse igualmente."""
    e = _nuevo()
    e["relevancia"], e["nivel_alerta"] = 95, ev.CRITICAL
    e = ev.avanzar(e, ev.DESCARTADO, "duplicado")
    assert ev.interrumpe(e) is False


def test_interrumpe_exige_las_dos_condiciones():
    e = _nuevo()
    e["nivel_alerta"] = ev.CRITICAL
    assert ev.interrumpe(e) is False          # nivel sí, etapa no
    for etapa in (ev.NORMALIZADO, ev.DEDUPLICADO, ev.FILTRADO, ev.SIGNIFICATIVO):
        e = ev.avanzar(e, etapa)
    assert ev.interrumpe(e) is True
    e["nivel_alerta"] = ev.WATCH
    assert ev.interrumpe(e) is False          # etapa sí, nivel no


# ── Salida por la API ────────────────────────────────────────────────────────

def test_el_crudo_no_sale_por_la_api():
    """Puede ser un filing entero y no le sirve de nada al navegador. Sigue en Mongo
    para auditar."""
    e = ev.para_api(_nuevo(crudo={"texto": "x" * 5000}))
    assert "crudo" not in e and "historial" not in e


def test_la_api_resume_el_historial_en_su_ultimo_paso():
    e = ev.avanzar(_nuevo(), ev.NORMALIZADO)
    salida = ev.para_api(e)
    assert salida["ultimo_paso"]["etapa"] == ev.NORMALIZADO
    assert salida["pasos"] == 2


def test_la_api_saca_un_DETALLE_con_lista_blanca():
    """`crudo` no sale entero, pero la pantalla necesita poder contar qué pasó: «los
    resultados se movieron del 28 al 4» no se puede decir sin esos dos datos.

    Lista blanca y no negra: `crudo` guarda lo que dijo la fuente tal cual, y una fuente
    futura puede meter ahí un documento entero o un identificador que no queremos
    publicar. Con lista negra, cada fuente nueva sería una fuga que nadie recordaría
    revisar."""
    e = para_api_de({"suceso": "cambio_fecha", "fecha": "2026-11-04",
                     "fecha_anterior": "2026-10-28",
                     "texto_completo": "x" * 5000, "token_interno": "secreto"})
    assert e["detalle"]["fecha_anterior"] == "2026-10-28"
    assert "texto_completo" not in e["detalle"]
    assert "token_interno" not in e["detalle"]
    assert "crudo" not in e


def test_sin_nada_publicable_el_detalle_es_None():
    """None y un diccionario vacío se pintan distinto: None es «este evento no tiene
    detalle», y {} invitaría a dibujar una ficha vacía."""
    assert para_api_de({"texto_completo": "x"})["detalle"] is None
    assert ev.para_api(_nuevo())["detalle"] is None


def para_api_de(crudo):
    return ev.para_api(_nuevo(crudo=crudo))


def test_el_detalle_deja_DISTINGUIR_dos_registros_del_mismo_dia():
    """Una empresa puede presentar catorce Form 4 el mismo día —un directivo cada uno— y
    todos tienen el mismo título. Sin el número de registro y la fecha, la pantalla enseña
    catorce filas idénticas sin forma de saber que son documentos distintos."""
    e = ev.para_api(_nuevo(crudo={"suceso": "4", "accession": "000104581026000042",
                                  "fecha_registro": "2026-09-08", "cik": "1045810"}))
    assert e["detalle"]["accession"] == "000104581026000042"
    assert e["detalle"]["fecha_registro"] == "2026-09-08"
    # El CIK sigue sin salir: no es lista negra, es blanca.
    assert "cik" not in e["detalle"]
