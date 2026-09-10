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
            resumen=None, relevancia=80, cartera=True, cuando="2026-09-09T10:00:00Z",
            **extra):
    e = ev.crear(fuente="sec", externo_id="8-K:1", titulo="8-K · Hecho relevante — NVDA",
                 url=url, symbol="NVDA", tipo=ev.CORPORATIVO, tier=1,
                 crudo={"suceso": "8-K", "formulario": "8-K",
                        "fecha_registro": "2026-09-09"})
    e.update(etapa=etapa, nivel_alerta=nivel, resumen=resumen, relevancia=relevancia,
             afecta_cartera=cartera, recibido_en=cuando)
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
    r = inv.a_investigar([_evento(nivel=ev.WATCH) for _ in range(41)] + [_evento()])
    assert r["motivos"][inv.NO_INTERRUMPE] == 41


# ── 2 · El presupuesto es PRIORIZADO, no por orden de llegada ────────────────

def test_hay_un_TOPE_DURO_al_dia():
    """Una estimación no es un límite. El tope existe para el día raro en que la
    estimación se equivoque, no como objetivo."""
    r = inv.a_investigar([_evento() for _ in range(50)], tope=20)
    assert len(r["elegidos"]) == 20 and len(r["pendientes"]) == 30


def test_lo_ya_gastado_HOY_cuenta():
    r = inv.a_investigar([_evento() for _ in range(10)], gastadas_hoy=18, tope=20)
    assert len(r["elegidos"]) == 2 and len(r["pendientes"]) == 8


def test_agotado_el_presupuesto_no_se_investiga_NADA():
    r = inv.a_investigar([_evento()], gastadas_hoy=20, tope=20)
    assert r["elegidos"] == [] and len(r["pendientes"]) == 1


def test_CRITICAL_antes_que_IMPORTANT_antes_que_WATCH():
    """El primer criterio, y el que no admite compensación: ningún grado de relevancia
    convierte un WATCH en más urgente que un CRITICAL."""
    eventos = [_evento(nivel=ev.WATCH, relevancia=99),
               _evento(nivel=ev.IMPORTANT, relevancia=50),
               _evento(nivel=ev.CRITICAL, relevancia=41)]
    ordenados = sorted(eventos, key=inv.prioridad)
    assert [e["nivel_alerta"] for e in ordenados] == [ev.CRITICAL, ev.IMPORTANT, ev.WATCH]


def test_a_IGUAL_NIVEL_manda_el_score():
    eventos = [_evento(relevancia=r) for r in (70, 95, 80)]
    assert [e["relevancia"] for e in sorted(eventos, key=inv.prioridad)] == [95, 80, 70]


def test_a_igual_score_CARTERA_antes_que_seguimiento():
    """Perderse algo de una posición abierta cuesta más que perdérselo de una que solo
    miras."""
    ordenados = sorted([_evento(cartera=False), _evento(cartera=True)],
                       key=inv.prioridad)
    assert [e["afecta_cartera"] for e in ordenados] == [True, False]


def test_el_ULTIMO_desempate_es_lo_mas_reciente():
    """Un documento de hace diez minutos puede cambiar una decisión de hoy; uno de hace
    tres días ya la ha cambiado o no."""
    viejo = _evento(cuando="2026-09-01T10:00:00Z")
    nuevo = _evento(cuando="2026-09-09T10:00:00Z")
    ordenados = sorted([viejo, nuevo], key=inv.prioridad)
    assert ordenados[0]["recibido_en"] == "2026-09-09T10:00:00Z"


def test_LOS_CUATRO_CRITERIOS_en_orden():
    """La cadena entera, de una vez: el nivel manda sobre el score, el score sobre la
    cartera y la cartera sobre la fecha."""
    esperado = [
        ("critico", ev.CRITICAL, 41, False, "2026-09-01T00:00:00Z"),
        ("importante_alto", ev.IMPORTANT, 90, False, "2026-09-01T00:00:00Z"),
        ("importante_bajo_cartera", ev.IMPORTANT, 70, True, "2026-09-01T00:00:00Z"),
        ("importante_bajo_watch", ev.IMPORTANT, 70, False, "2026-09-09T00:00:00Z"),
        ("importante_bajo_viejo", ev.IMPORTANT, 70, False, "2026-09-01T00:00:00Z"),
    ]
    eventos = [_evento(nivel=n, relevancia=r, cartera=c, cuando=f, externo=nombre)
               for nombre, n, r, c, f in esperado]
    for e, (nombre, *_) in zip(eventos, esperado):
        e["_nombre"] = nombre
    revueltos = [eventos[3], eventos[0], eventos[4], eventos[2], eventos[1]]
    assert [e["_nombre"] for e in sorted(revueltos, key=inv.prioridad)] == \
        [nombre for nombre, *_ in esperado]


# ── 3 · Lo que no cabe queda PENDIENTE, no descartado ────────────────────────

def test_lo_que_no_cabe_queda_PENDIENTE_y_no_descartado():
    """`descartado` es terminal: marcarlos así haría que un evento importante que no cupo
    en el presupuesto de un martes no se mirara jamás."""
    r = inv.a_investigar([_evento() for _ in range(30)], tope=5)
    assert len(r["pendientes"]) == 25
    for e in r["pendientes"]:
        assert e["etapa"] == ev.SIGNIFICATIVO      # siguen donde estaban
        assert inv.estado_de_investigacion(e) == inv.PENDIENTE


def test_NINGUN_evento_se_pierde():
    """La comprobación global: todo lo que entra sale por alguna de las tres puertas."""
    eventos = ([_evento() for _ in range(30)]
               + [_evento(nivel=ev.WATCH) for _ in range(10)]
               + [_evento(url="") for _ in range(5)])
    r = inv.a_investigar(eventos, tope=7)
    contados = len(r["elegidos"]) + len(r["pendientes"]) + \
        sum(n for m, n in r["motivos"].items() if m != "sin_presupuesto")
    assert contados == len(eventos)


def test_un_pendiente_se_recoge_en_la_VUELTA_SIGUIENTE():
    """Es el punto de dejarlos pendientes: mañana hay presupuesto otra vez."""
    eventos = [_evento(relevancia=r) for r in (95, 80)]
    hoy = inv.a_investigar(eventos, tope=1)
    assert [e["relevancia"] for e in hoy["elegidos"]] == [95]
    manana = inv.a_investigar(hoy["pendientes"], tope=1)
    assert [e["relevancia"] for e in manana["elegidos"]] == [80]


def test_lo_ya_investigado_NO_vuelve_a_entrar_al_presupuesto():
    """Idempotencia: la vuelta siguiente no puede volver a pagar por lo mismo."""
    e = _evento()
    investigado = inv.aplicar(e, {"resumen": "Algo concreto.", "sin_informacion": False})
    r = inv.a_investigar([investigado], tope=20)
    assert r["elegidos"] == [] and r["motivos"][inv.ETAPA] == 1


def test_el_tope_por_defecto_es_pequeño():
    """~1 investigación al día es lo estimado con datos reales. Un tope de mil no sería
    un freno."""
    assert 0 < inv.TOPE_DIARIO <= 50


# ── 3b · Los cinco estados que hay que poder distinguir ──────────────────────

def test_los_CINCO_ESTADOS_son_distinguibles():
    """La etapa sola no basta: `investigado` cubre «no decía nada» y «esto es lo que
    dice», y `significativo` cubre «pendiente» y «no investigable». Sin separarlos, un
    radar en silencio no se puede leer."""
    descartado = _evento(etapa=ev.DESCARTADO)
    pendiente = _evento()
    no_investigable = _evento(url="")
    sin_info = inv.aplicar(_evento(), {"sin_informacion": True, "resumen": None})
    con_info = inv.aplicar(_evento(), {"sin_informacion": False, "resumen": "Dice X."})

    assert inv.estado_de_investigacion(descartado) == inv.DESCARTADO_POR_FILTRO
    assert inv.estado_de_investigacion(pendiente) == inv.PENDIENTE
    assert inv.estado_de_investigacion(no_investigable) == inv.NO_INVESTIGABLE
    assert inv.estado_de_investigacion(sin_info) == inv.SIN_INFORMACION
    assert inv.estado_de_investigacion(con_info) == inv.CON_INFORMACION
    # Y son cinco valores distintos, no cuatro con un alias.
    assert len({inv.DESCARTADO_POR_FILTRO, inv.PENDIENTE, inv.NO_INVESTIGABLE,
                inv.SIN_INFORMACION, inv.CON_INFORMACION}) == 5


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


def test_la_investigacion_NO_toca_la_RELEVANCIA():
    """Leer un documento no cambia cuánto te toca: eso lo decide tu cartera, y ya lo
    decidió el scoring. Si la lectura pudiera subir la nota, la IA estaría opinando sobre
    tu exposición a partir de un texto que no sabe cuánto tienes."""
    despues = inv.aplicar(_evento(relevancia=80),
                          {"resumen": "algo", "sin_informacion": False})
    assert despues["relevancia"] == 80


def test_la_etapa_avanza_por_la_LISTA_BLANCA_y_no_a_mano():
    """`aplicar` no escribe la etapa: llama a `ev.avanzar`, que solo deja pasar las
    transiciones declaradas. Así la investigación no puede abrir un camino nuevo por su
    cuenta."""
    e = _evento()
    assert inv.aplicar(e, {"resumen": "x", "sin_informacion": False})["etapa"] == ev.INVESTIGADO
    # Desde una etapa que no lo permite, no se mueve.
    descartado = _evento(etapa=ev.DESCARTADO)
    assert inv.aplicar(descartado, {"resumen": "x"})["etapa"] == ev.DESCARTADO


def test_SIGNIFICATIVO_a_INVESTIGADO_es_el_flujo_completo():
    """El paso que pediste separado: significativo es «merece que gaste recursos»,
    investigado es «la IA ya leyó la fuente». Antes de investigar, el evento está
    pendiente; después, leído."""
    e = _evento()
    assert e["etapa"] == ev.SIGNIFICATIVO
    assert inv.estado_de_investigacion(e) == inv.PENDIENTE

    leido = inv.aplicar(e, {"sin_informacion": False, "resumen": "Compra de X por 2.000 M$."})
    assert leido["etapa"] == ev.INVESTIGADO
    assert inv.estado_de_investigacion(leido) == inv.CON_INFORMACION
    assert leido["historial"][-1]["etapa"] == ev.INVESTIGADO   # queda en el historial


def test_SIN_INFORMACION_tambien_avanza_a_investigado():
    """Que el resultado sea «no dice nada» no lo hace menos resultado: la IA leyó el
    documento. Dejarlo en `significativo` haría que se volviera a pagar por él en cada
    vuelta."""
    leido = inv.aplicar(_evento(), {"sin_informacion": True, "resumen": None})
    assert leido["etapa"] == ev.INVESTIGADO and leido["resumen"] is None
    assert inv.estado_de_investigacion(leido) == inv.SIN_INFORMACION


def test_la_salida_NO_recomienda_operar():
    """El prompt pide «qué dice» y «qué cambiaría», no «compra». Son dos saltos —entender
    e invertir— y solo el primero se puede comprobar contra el documento."""
    campos = inv.validar({"resumen": "x", "que_cambia": "y"})["investigacion"]
    for prohibido in ("recomendacion", "accion", "veredicto", "comprar", "vender"):
        assert prohibido not in campos


# ── 7 · El panorama: ver el presupuesto sin gastarlo ─────────────────────────
# Un presupuesto que solo se puede comprobar gastándolo no es un presupuesto.

def _mundo():
    """Un conjunto parecido al de producción: mucho trámite, poco importante."""
    return (
        [_evento(etapa=ev.DESCARTADO) for _ in range(20)]          # el filtro los tiró
        + [_evento(nivel=ev.WATCH) for _ in range(15)]             # no pasan la puerta
        + [_evento(nivel=ev.IMPORTANT, url="") for _ in range(2)]  # sin documento
        + [_evento(nivel=ev.CRITICAL, relevancia=95) for _ in range(3)]
        + [_evento(nivel=ev.IMPORTANT, relevancia=80) for _ in range(4)]
        + [inv.aplicar(_evento(), {"sin_informacion": True, "resumen": None})]
        + [inv.aplicar(_evento(), {"sin_informacion": False, "resumen": "Dice X."})]
    )


def test_el_panorama_cuenta_LOS_CINCO_estados():
    p = inv.panorama(_mundo(), tope=20)
    assert p["total_eventos"] == 46
    e = p["por_estado"]
    assert e[inv.DESCARTADO_POR_FILTRO] == 20
    assert e[inv.NO_INVESTIGABLE] == 17          # 15 WATCH + 2 sin url
    assert e[inv.PENDIENTE] == 7                 # 3 críticos + 4 importantes
    assert e[inv.SIN_INFORMACION] == 1
    assert e[inv.CON_INFORMACION] == 1
    assert sum(e.values()) == p["total_eventos"]  # ninguno se queda sin clasificar


def test_los_cinco_estados_SIEMPRE_salen_aunque_valgan_cero():
    """Un estado que desaparece del recuento cuando vale cero obliga a deducir su
    ausencia. Se enseña el cero."""
    p = inv.panorama([_evento()], tope=20)
    assert set(p["por_estado"]) == set(inv.ESTADOS)
    assert p["por_estado"][inv.CON_INFORMACION] == 0


def test_el_reparto_por_NIVEL_de_lo_que_sigue_sin_investigar():
    """Todo lo que sigue en `significativo`, pase o no la puerta. Es lo que enseña que
    hay quince WATCH esperando y que NO se investigan por diseño, en vez de que
    desaparezcan del recuento sin explicación."""
    p = inv.panorama(_mundo(), tope=20)
    n = p["sin_investigar_por_nivel"]
    assert n[ev.CRITICAL] == 3 and n[ev.IMPORTANT] == 6 and n[ev.WATCH] == 15
    assert n[ev.INFO] == 0                       # el nivel sale aunque valga cero


def test_WATCH_e_INFO_salen_a_CERO_entre_los_pendientes_por_diseño():
    """La puerta es `INTERRUMPEN`. Verlo a cero aquí, junto al recuento de arriba que sí
    los cuenta, es lo que enseña dónde se corta."""
    p = inv.panorama(_mundo(), tope=20)
    assert p["pendientes_por_nivel"][ev.WATCH] == 0
    assert p["pendientes_por_nivel"][ev.INFO] == 0
    assert p["niveles_que_pasan_la_puerta"] == list(ev.INTERRUMPEN)


def test_el_panorama_dice_cuantos_ENTRARIAN_y_cuantos_quedarian():
    p = inv.panorama(_mundo(), tope=5)
    assert p["entrarian_en_el_presupuesto"] == 5
    assert p["quedarian_pendientes"] == 2
    assert len(p["elegidos"]) == 5 and len(p["pendientes"]) == 2


def test_los_elegidos_salen_EN_ORDEN_de_prioridad():
    """Sin verlos ordenados habría que creerse el reparto."""
    p = inv.panorama(_mundo(), tope=5)
    niveles = [e["nivel_alerta"] for e in p["elegidos"]]
    assert niveles == [ev.CRITICAL] * 3 + [ev.IMPORTANT] * 2
    assert niveles == [e["nivel_alerta"] for e in sorted(p["elegidos"], key=inv.prioridad)]


def test_el_panorama_NO_investiga_ni_mueve_nada():
    """Es una vista. Si tocara una etapa, dejaría de poder usarse para decidir si
    encender la fase."""
    mundo = _mundo()
    antes = [(e["etapa"], e.get("resumen"), e.get("investigado_en")) for e in mundo]
    inv.panorama(mundo, tope=5)
    assert [(e["etapa"], e.get("resumen"), e.get("investigado_en")) for e in mundo] == antes


def test_el_panorama_dice_el_PRESUPUESTO_con_el_que_calcula():
    """El número no se puede leer sin saber contra qué tope se ha calculado."""
    p = inv.panorama(_mundo(), gastadas_hoy=3, tope=5)
    assert p["presupuesto"] == {"tope_diario": 5, "gastadas_hoy": 3, "restante": 2}
    assert p["entrarian_en_el_presupuesto"] == 2


def test_sin_eventos_el_panorama_no_inventa_nada():
    p = inv.panorama([], tope=20)
    assert p["total_eventos"] == 0 and p["elegidos"] == [] and p["pendientes"] == []
    assert all(v == 0 for v in p["por_estado"].values())


def test_el_panorama_aguanta_basura_en_la_lista():
    p = inv.panorama([None, "texto", {}, _evento()], tope=20)
    assert p["total_eventos"] == 2               # el dict vacío cuenta, los otros no


# ── 8 · El endpoint es de SOLO LECTURA ───────────────────────────────────────

def _cuerpo_del_endpoint() -> str:
    """El código de `intelligence_plan_investigacion`, sin comentarios ni docstring."""
    import ast
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server.py")
    arbol = ast.parse(open(ruta, encoding="utf-8").read())
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, (ast.AsyncFunctionDef, ast.FunctionDef))
                and nodo.name == "intelligence_plan_investigacion"):
            cuerpo = list(nodo.body)
            if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                    and isinstance(cuerpo[0].value, ast.Constant)):
                cuerpo = cuerpo[1:]          # fuera la docstring
            return "\n".join(ast.unparse(n) for n in cuerpo)
    raise AssertionError("el endpoint del panorama ha desaparecido")


def test_el_endpoint_NO_escribe_en_mongo():
    """Una vista que cambiara estados no serviría para decidir si encender la fase: al
    mirarla ya habría cambiado lo que se mira."""
    cuerpo = _cuerpo_del_endpoint()
    for escritura in ("update_one", "update_many", "insert_one", "insert_many",
                      "delete_one", "delete_many", "replace_one", "bulk_write"):
        assert escritura not in cuerpo, f"el panorama escribe: {escritura}"


def test_el_endpoint_NO_llama_a_ningun_modelo_ni_descarga_nada():
    """Lo que el usuario pidió explícitamente: ver el plan sin consumir cuota."""
    cuerpo = _cuerpo_del_endpoint()
    for prohibido in ("_run_model", "ai_analysis", "httpx", "construir_peticion",
                      "texto_del_documento", "aplicar("):
        assert prohibido not in cuerpo, f"el panorama ejecuta: {prohibido}"


def test_el_endpoint_DECLARA_que_no_ejecuta_nada():
    """Va en la respuesta, no solo en un comentario: quien lea el JSON tiene que poder
    saber que esto es una previsión y no algo que ya está corriendo."""
    cuerpo = _cuerpo_del_endpoint()
    assert "'ejecuta_investigaciones': False" in cuerpo
    assert "'contador_diario_implementado': False" in cuerpo
