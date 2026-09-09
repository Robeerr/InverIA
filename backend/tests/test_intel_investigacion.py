"""La fase de investigación, probada sin gastar un céntimo.

LAS DOS COSAS QUE ESTE FICHERO PROTEGE

  1. EL PRESUPUESTO. Este proyecto ya quemó 3,65 € en un día por dejar suelto un bucle
     con IA. La puerta —solo se investiga lo que ya merecía interrumpirte— y el tope
     diario son lo que impide que vuelva a pasar, y los dos se prueban aquí.

  2. QUE PUEDA DECIR QUE NO SABE. Un documento sin contenido tiene que dejar el evento
     SIN resumen. Si el hueco se rellena con prosa de compromiso, un resumen deja de
     significar nada y la pantalla pasa a mentir en el sitio donde más se la cree.

Todo se prueba en memoria: la puerta, el prompt y la validación son puros a propósito,
para poder equivocarse aquí en vez de en producción y con la factura abierta.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import intel_eventos as ev
import intel_investigacion as inv


def _evento(nivel=ev.IMPORTANT, etapa=ev.SIGNIFICATIVO, url="https://sec.gov/x.htm",
            resumen=None, relevancia=80, **extra):
    e = ev.crear(fuente="sec", externo_id="8-K:1", titulo="8-K · Hecho relevante — NVDA",
                 url=url, symbol="NVDA", tipo=ev.CORPORATIVO, tier=1,
                 crudo={"suceso": "8-K", "formulario": "8-K",
                        "fecha_registro": "2026-09-09"})
    e.update(etapa=etapa, nivel_alerta=nivel, resumen=resumen, relevancia=relevancia)
    e.update(extra)
    return e


# ── 1 · La puerta: el presupuesto no es negociable ───────────────────────────

def test_se_investiga_lo_que_YA_merecia_interrumpirte():
    """La puerta no es un umbral nuevo: es el `nivel_alerta` del scoring, que ya está
    calibrado. Inventar un segundo criterio habría creado dos verdades sobre lo mismo."""
    assert inv.merece_investigacion(_evento(nivel=ev.IMPORTANT)) is True
    assert inv.merece_investigacion(_evento(nivel=ev.CRITICAL)) is True


def test_un_TRAMITE_no_se_investiga():
    """Un Form 4 de consolidación automática sale ATENCIÓN. Investigarlo sería pagar por
    leer un trámite, y son la inmensa mayoría de lo que entra."""
    e = _evento(nivel=ev.WATCH)
    assert inv.merece_investigacion(e) is False
    assert inv.motivo_para_no_investigar(e) == inv.NO_INTERRUMPE


def test_lo_ya_investigado_NO_se_paga_dos_veces():
    assert inv.motivo_para_no_investigar(_evento(resumen="ya está")) == inv.YA_INVESTIGADO
    assert inv.motivo_para_no_investigar(
        _evento(investigado_en="2026-09-09T10:00:00Z")) == inv.YA_INVESTIGADO


def test_sin_ENLACE_no_se_investiga():
    """Sin documento, la única fuente sería lo que el modelo recuerde de su
    entrenamiento. Eso no es investigar: es preguntarle si le suena la empresa."""
    assert inv.motivo_para_no_investigar(_evento(url="")) == inv.SIN_URL


def test_un_evento_DESCARTADO_no_se_investiga():
    """La puerta de atrás: algo que el filtro tiró no puede colarse por aquí y acabar
    con un análisis pagado."""
    assert inv.motivo_para_no_investigar(_evento(etapa=ev.DESCARTADO)) == inv.ETAPA
    assert inv.motivo_para_no_investigar(_evento(etapa=ev.FILTRADO)) == inv.ETAPA


def test_el_motivo_se_DEVUELVE_para_poder_contarlo():
    """El diagnóstico tiene que poder decir «de 42 eventos, 41 no se investigaron porque
    no interrumpían». Sin eso, una puerta rota se ve igual que un día tranquilo."""
    _, motivos = inv.a_investigar([_evento(nivel=ev.WATCH) for _ in range(41)]
                                 + [_evento()])
    assert motivos[inv.NO_INTERRUMPE] == 41


# ── 2 · El tope diario ───────────────────────────────────────────────────────

def test_hay_un_TOPE_DURO_al_dia():
    """Una estimación no es un límite. El tope existe para el día raro en que la
    estimación se equivoque, no como objetivo."""
    elegidos, motivos = inv.a_investigar([_evento() for _ in range(50)], tope=20)
    assert len(elegidos) == 20 and motivos["sin_presupuesto"] == 30


def test_lo_ya_gastado_HOY_cuenta():
    elegidos, _ = inv.a_investigar([_evento() for _ in range(10)],
                                   gastadas_hoy=18, tope=20)
    assert len(elegidos) == 2


def test_agotado_el_presupuesto_no_se_investiga_NADA():
    elegidos, motivos = inv.a_investigar([_evento()], gastadas_hoy=20, tope=20)
    assert elegidos == [] and motivos["sin_presupuesto"] == 1


def test_el_recorte_deja_fuera_lo_MENOS_relevante():
    """Cortar por orden de llegada dejaría fuera al más grave por haber llegado el
    último. Se corta por lo que menos te toca."""
    eventos = [_evento(relevancia=r) for r in (60, 95, 70, 85)]
    elegidos, _ = inv.a_investigar(eventos, tope=2)
    assert [e["relevancia"] for e in elegidos] == [95, 85]


def test_el_tope_por_defecto_es_pequeño():
    """~1 investigación al día es lo estimado con datos reales. Un tope de mil no sería
    un freno."""
    assert 0 < inv.TOPE_DIARIO <= 50


# ── 3 · El documento ─────────────────────────────────────────────────────────

def test_del_html_de_la_sec_sale_texto_legible():
    html = """<html><head><style>p{color:red}</style></head><body>
    <p>Item 8.01 &mdash; On September&nbsp;8, 2026, the Company announced</p>
    <script>var x=1;</script><p>a definitive agreement.</p></body></html>"""
    t = inv.texto_del_documento(html)
    assert "Item 8.01 — On September 8, 2026" in t
    assert "definitive agreement" in t
    assert "color:red" not in t and "var x" not in t     # estilo y script fuera


def test_se_corta_por_EL_FINAL_y_no_por_el_principio():
    """Un 8-K pone lo importante en la primera página y los anexos detrás. Cortar por
    delante tiraría justo lo que se quiere leer."""
    t = inv.texto_del_documento("<p>LO IMPORTANTE</p>" + "<p>anexo</p>" * 5000,
                                maximo=100)
    assert t.startswith("LO IMPORTANTE") and len(t) == 100


def test_un_documento_vacio_no_revienta():
    assert inv.texto_del_documento("") == ""
    assert inv.texto_del_documento(None) == ""


# ── 4 · La petición ──────────────────────────────────────────────────────────

def test_el_prompt_PROHIBE_recomendar_y_prohibe_rellenar():
    """Las dos prohibiciones que sostienen la fase: no saltar de entender a invertir, y
    no rellenar el hueco cuando el documento no dice nada."""
    s = inv.SISTEMA
    assert "recomiendes comprar ni vender" in s.lower()
    assert "no estimes el impacto en el precio" in s.lower()
    assert "TU ÚNICA FUENTE ES EL DOCUMENTO" in s
    assert "sin_informacion" in s


def test_la_peticion_lleva_el_valor_y_el_tipo_de_registro():
    """Un 8-K no siempre dice de qué empresa es en el cuerpo. Sin esto, el modelo
    tendría que adivinarlo — y adivinar es justo lo que no queremos."""
    p = inv.construir_peticion(_evento(), "Texto del filing.")
    assert "Valor: NVDA" in p["usuario"] and "8-K" in p["usuario"]
    assert "Texto del filing." in p["usuario"]


def test_un_documento_vacio_se_declara_vacio_en_la_peticion():
    """Mandar el hueco en blanco invitaría al modelo a rellenarlo de memoria."""
    assert "(vacío)" in inv.construir_peticion(_evento(), "")["usuario"]


def test_se_usa_el_enrutado_que_YA_prueba_la_key_gratis_primero():
    """`gemini-2.5-flash` es la clave de routing de `ai_analysis.MODEL_MAP`, que intenta
    la key GRATIS y solo cae a la de pago si esa se agota. No hay modelo nuevo ni
    proveedor nuevo."""
    import ai_analysis
    assert inv.MODELO in ai_analysis.MODEL_MAP


# ── 5 · Poder decir que no se sabe ───────────────────────────────────────────

def test_SIN_INFORMACION_deja_el_evento_sin_resumen():
    """La regla número uno. Muchos registros son trámites; rellenar el hueco haría que un
    resumen dejara de significar nada."""
    r = inv.validar({"sin_informacion": True, "resumen": "", "confianza": 90})
    assert r["ok"] is True
    e = inv.aplicar(_evento(), r["investigacion"])
    assert e["resumen"] is None
    assert e["investigado_en"]          # pero consta que ya se miró: no se paga dos veces


def test_decir_que_no_hay_informacion_Y_dar_resumen_se_RECHAZA():
    """El patrón típico de un modelo que rellena por no dejar el hueco vacío. Aceptarlo
    convertiría la regla de «poder decir que no sé» en decorativa."""
    r = inv.validar({"sin_informacion": True, "resumen": "La empresa ha anunciado algo."})
    assert r["ok"] is False and r["motivo"] == inv.CONTRADICTORIA


def test_una_respuesta_sin_nada_se_RECHAZA():
    """Ni información ni la declaración de que no la hay. No es una respuesta."""
    assert inv.validar({"sin_informacion": False, "resumen": "  "})["motivo"] == inv.VACIA
    assert inv.validar(None)["motivo"] == inv.SIN_RESPUESTA
    assert inv.validar("texto suelto")["motivo"] == inv.SIN_RESPUESTA


def test_una_respuesta_buena_se_guarda_entera():
    r = inv.validar({"sin_informacion": False,
                     "resumen": "Acuerdo definitivo de compra de X por 2.000 M$.",
                     "que_cambia": "Añade deuda y un negocio nuevo.",
                     "hechos": ["2.000 M$", "cierre previsto en Q1"],
                     "confianza": 85})
    assert r["ok"] is True
    i = r["investigacion"]
    assert i["confianza"] == 85 and len(i["hechos"]) == 2
    e = inv.aplicar(_evento(), i)
    assert e["resumen"].startswith("Acuerdo definitivo")


def test_SIN_CONFIANZA_declarada_se_asume_la_minima():
    """No se inventa una alta: la duda tiene que costar algo."""
    r = inv.validar({"resumen": "Algo pasó.", "confianza": "no sé"})
    assert r["investigacion"]["confianza"] == 0


def test_la_confianza_se_queda_entre_0_y_100():
    for entrada, esperado in ((150, 100), (-5, 0), (70.4, 70)):
        assert inv.validar({"resumen": "x", "confianza": entrada})["investigacion"]["confianza"] == esperado


def test_un_resumen_kilometrico_se_recorta():
    r = inv.validar({"resumen": "x" * 5000})
    assert len(r["investigacion"]["resumen"]) == inv.MAX_RESUMEN


# ── 6 · Aplicar no muta ni decide por ti ─────────────────────────────────────

def test_aplicar_NO_muta_el_original():
    """Igual que `ev.avanzar`: quien llama tiene el documento de Mongo y decide él si
    escribe. Mutarlo lo dejaría adelantado ante cualquier fallo de escritura."""
    e = _evento()
    inv.aplicar(e, {"resumen": "algo", "sin_informacion": False})
    assert e["resumen"] is None


def test_la_investigacion_NO_toca_la_relevancia_ni_la_etapa():
    """Leer un documento no cambia cuánto te toca: eso lo decide tu cartera. Y mover la
    etapa desde aquí saltaría la lista blanca de transiciones."""
    e = _evento(relevancia=80)
    despues = inv.aplicar(e, {"resumen": "algo", "sin_informacion": False})
    assert despues["relevancia"] == 80 and despues["etapa"] == e["etapa"]


def test_la_salida_NO_recomienda_operar():
    """El prompt pide «qué dice» y «qué cambiaría», no «compra». Son dos saltos —entender
    e invertir— y solo el primero se puede comprobar contra el documento."""
    campos = inv.validar({"resumen": "x", "que_cambia": "y"})["investigacion"]
    for prohibido in ("recomendacion", "accion", "veredicto", "comprar", "vender"):
        assert prohibido not in campos
