"""La IA recomienda; autorizar es de la estructura.

EL CONTRATO QUE SE PROTEGE

    Tendencia = autoridad.
    La IA puede recomendar, pero no puede autorizar una compra que la estructura ha vetado.
    El veto se aplica justo antes de mostrar o ejecutar, no contamina lo generado.

Las tres frases se prueban por separado, porque se rompen por separado.

LA TERCERA ES LA QUE MÁS FÁCIL SE PIERDE

`_TTLCache.get` devuelve el objeto GUARDADO, no una copia. Un veto que mutara el
veredicto servido reescribiría la caché para todos los lectores siguientes y el original
se perdería sin que fallara nada — y peor: al levantarse la tendencia, el veredicto
seguiría degradado hasta que caducara la entrada, hasta 4 horas después. Por eso hay un
test que guarda una referencia al objeto original y comprueba que sigue intacto.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import estado_accion  # noqa: E402
import veto_compra  # noqa: E402

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_FRONT = os.path.join(_BACKEND, "..", "frontend", "src")


def _codigo(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"#.*", "", src)


SRV = _codigo(os.path.join(_BACKEND, "server.py"))


def _cuerpo(nombre: str, src: str = None) -> str:
    """El cuerpo de una función, hasta la siguiente definición de primer nivel."""
    src = SRV if src is None else src
    ini = src.index(f"def {nombre}(")
    resto = src[ini:]
    m = re.search(r"\n(?:def |async def |@api_router|@app\.)", resto[1:])
    return resto[: m.start() + 1] if m else resto


def _analisis(rec="COMPRAR"):
    return {"recommendation": rec, "confidence": 82, "summary": "…"}


def _veredicto(accion="COMPRAR"):
    return {
        "sentido": "alcista",
        "veredicto": "Tendencia sana, retroceso ordenado.",
        "por_timeframe": [{"tf": "1D", "lectura": "…"}],
        "plan": {
            "accion": accion,
            "gatillo": "Compra escalonada en los niveles de abajo",
            "niveles_entrada": [{"precio": 100.0, "porcentaje": 50, "motivo": "soporte 1D"}],
            "invalidacion": 90.0,
            "objetivo": 130.0,
            "por_que": "Los niveles salen de la geometría real.",
        },
    }


# ── 1 · Quién veta ───────────────────────────────────────────────────────────

def test_solo_no_comprar_veta():
    assert veto_compra.hay_veto("NO_COMPRAR") is True
    for otro in ("EN_SEGUIMIENTO", "SIN_EVALUAR", "", None, "ALCISTA"):
        assert veto_compra.hay_veto(otro) is False, otro


def test_el_veto_se_lee_del_estado_y_no_de_la_tendencia():
    """El módulo no traduce direcciones: recibe el estado que ya decidió `estado_accion`.
    Si tradujera, habría dos implementaciones de la misma regla."""
    codigo = _codigo(os.path.join(_BACKEND, "veto_compra.py"))
    for propio in ("sma", "precio >", "ALCISTA", "BAJISTA", "clasificar"):
        assert propio not in codigo, propio


def test_el_estado_bloqueante_coincide_con_los_de_estado_accion():
    """Un veto contra un estado que `estado_accion` no emite nunca sería un veto muerto."""
    assert veto_compra.ESTADO_BLOQUEANTE in estado_accion.ESTADOS


# ── 2 · NO_COMPRAR + COMPRAR ⇒ nunca queda una compra efectiva ───────────────

def test_la_recomendacion_de_compra_se_degrada_a_mantener():
    r = veto_compra.degradar_analisis(_analisis("COMPRAR"), "NO_COMPRAR")
    assert r["recommendation"] == "MANTENER"
    assert r["vetado_por_tendencia"] is True


def test_lo_que_dijo_el_modelo_se_conserva_para_poder_auditarlo():
    """Sin esto, un veto sería indistinguible de un MANTENER genuino."""
    r = veto_compra.degradar_analisis(_analisis("COMPRAR"), "NO_COMPRAR")
    assert r["recomendacion_ia"] == "COMPRAR"


def test_vender_no_se_toca():
    """El veto es sobre COMPRAR. Convertir una venta en un mantener sería inventarse una
    opinión que nadie ha dado."""
    r = veto_compra.degradar_analisis(_analisis("VENDER"), "NO_COMPRAR")
    assert r["recommendation"] == "VENDER"
    assert "vetado_por_tendencia" not in r


def test_sin_veto_la_recomendacion_pasa_intacta():
    for estado in ("EN_SEGUIMIENTO", "SIN_EVALUAR", None):
        r = veto_compra.degradar_analisis(_analisis("COMPRAR"), estado)
        assert r["recommendation"] == "COMPRAR", estado


def test_la_confianza_no_se_recorta():
    """Mide la seguridad del modelo en SU lectura, y esa lectura sigue siendo la que era.
    Que no mande no significa que haya dejado de estar seguro."""
    r = veto_compra.degradar_analisis(_analisis("COMPRAR"), "NO_COMPRAR")
    assert r["confidence"] == 82


def test_degradar_analisis_aguanta_basura():
    for basura in (None, [], "COMPRAR", 7):
        assert veto_compra.degradar_analisis(basura, "NO_COMPRAR") is basura


# ── 3 · NO_COMPRAR + Chartista COMPRAR ⇒ ESPERAR y sin accionables ──────────

def test_el_plan_de_compra_pasa_a_esperar():
    r = veto_compra.degradar_chartista(_veredicto("COMPRAR"), "NO_COMPRAR")
    assert r["plan"]["accion"] == "ESPERAR"
    assert r["plan"]["accion_ia"] == "COMPRAR"
    assert r["vetado_por_tendencia"] is True


def test_no_queda_ningun_dato_accionable():
    r = veto_compra.degradar_chartista(_veredicto("COMPRAR"), "NO_COMPRAR")
    plan = r["plan"]
    assert plan["niveles_entrada"] == []
    assert plan["gatillo"] is None
    assert plan["invalidacion"] is None
    assert plan["objetivo"] is None


def test_los_niveles_se_retiran_aunque_la_accion_no_fuera_comprar():
    """Un plan con acción ESPERAR puede traer niveles poblados, y la pantalla ofrece
    «Añadir a Cartera» mirando la LISTA y no la acción (`ChartistPanel.jsx`). Dejarlos
    permitiría persistir un plan de compra sobre una acción vetada por la puerta de al
    lado — que es exactamente lo que este contrato prohíbe."""
    r = veto_compra.degradar_chartista(_veredicto("ESPERAR"), "NO_COMPRAR")
    assert r["plan"]["niveles_entrada"] == []
    # El verbo, en cambio, no se reescribe: ya decía lo correcto.
    assert r["plan"]["accion"] == "ESPERAR"
    assert "accion_ia" not in r["plan"]


def test_lo_descriptivo_sobrevive():
    """Una acción en tendencia bajista se puede estudiar. Lo que no se puede es comprarla
    porque lo diga un modelo."""
    r = veto_compra.degradar_chartista(_veredicto("COMPRAR"), "NO_COMPRAR")
    assert r["veredicto"]
    assert r["sentido"] == "alcista"
    assert r["por_timeframe"]
    assert r["plan"]["por_que"]


def test_el_motivo_viaja_para_que_la_pantalla_lo_explique():
    r = veto_compra.degradar_chartista(_veredicto(), "NO_COMPRAR", "Está bajo su SMA200.")
    assert r["veto_motivo"] == "Está bajo su SMA200."


def test_sin_veto_el_veredicto_pasa_intacto():
    original = _veredicto("COMPRAR")
    for estado in ("EN_SEGUIMIENTO", "SIN_EVALUAR", None):
        assert veto_compra.degradar_chartista(original, estado) is original, estado


def test_degradar_chartista_aguanta_un_plan_que_no_es_dict():
    r = veto_compra.degradar_chartista({"sentido": "bajista", "plan": None}, "NO_COMPRAR")
    assert r["vetado_por_tendencia"] is True
    assert r["plan"] is None


# ── 4 · El veto NO contamina lo generado ─────────────────────────────────────

def test_el_veredicto_original_no_se_muta():
    """El invariante que sostiene «se aplica al servir». `_TTLCache.get` devuelve el objeto
    guardado por REFERENCIA: si el veto mutara, reescribiría la caché para todos."""
    original = _veredicto("COMPRAR")
    plan_original = original["plan"]
    veto_compra.degradar_chartista(original, "NO_COMPRAR")
    assert original["plan"] is plan_original
    assert original["plan"]["accion"] == "COMPRAR"
    assert original["plan"]["niveles_entrada"] == [{"precio": 100.0, "porcentaje": 50,
                                                    "motivo": "soporte 1D"}]
    assert original["plan"]["invalidacion"] == 90.0
    assert "vetado_por_tendencia" not in original


def test_el_analisis_original_no_se_muta():
    original = _analisis("COMPRAR")
    veto_compra.degradar_analisis(original, "NO_COMPRAR")
    assert original["recommendation"] == "COMPRAR"
    assert "vetado_por_tendencia" not in original


def test_degradar_dos_veces_da_lo_mismo():
    """Idempotencia: el mismo veredicto cacheado se sirve muchas veces mientras dure el
    veto, y cada lectura vuelve a degradarlo desde el original."""
    uno = veto_compra.degradar_chartista(_veredicto("COMPRAR"), "NO_COMPRAR")
    dos = veto_compra.degradar_chartista(uno, "NO_COMPRAR")
    assert dos["plan"]["accion"] == uno["plan"]["accion"] == "ESPERAR"
    assert dos["plan"]["niveles_entrada"] == []


# ── 5 · El endpoint: veta al servir y usa la autoridad existente ────────────

CHARTIST = _cuerpo("chartist_verdict")


def test_el_endpoint_pregunta_a_la_autoridad_existente():
    assert "market_data.tendencia_de" in CHARTIST
    assert "estado_accion.evaluar" in CHARTIST
    assert "veto_compra.degradar_chartista" in CHARTIST


def test_el_endpoint_no_reimplementa_la_clasificacion():
    for propio in ("sma200", "sma50", "clasificar(", "ALCISTA", "BAJISTA"):
        assert propio not in CHARTIST, propio


def test_chartist_py_no_clasifica_tendencia_por_su_cuenta():
    """El módulo calcula medias para la RADIOGRAFÍA que ve el modelo, y eso es legítimo.
    Lo que no puede es derivar de ellas un estado de elegibilidad."""
    codigo = _codigo(os.path.join(_BACKEND, "chartist.py"))
    for propio in ("hay_tendencia_valida", "NO_COMPRAR", "estado_accion", "veto_compra"):
        assert propio not in codigo, propio


def test_el_veto_va_despues_de_guardar_en_cache():
    """El orden ES el contrato. Si `degradar_chartista` corriera antes del `_cache.set`,
    lo guardado sería el veredicto ya degradado y la caché quedaría contaminada durante
    horas."""
    pos_cache = CHARTIST.index("_cache.set(key, result")
    pos_veto = CHARTIST.index("veto_compra.degradar_chartista")
    assert pos_cache < pos_veto


def test_lo_que_se_guarda_es_el_resultado_del_modelo():
    assert "_cache.set(key, result, ttl=1800)" in CHARTIST
    assert "_cache.set(key, salida" not in CHARTIST


def test_cached_only_sin_veredicto_no_gasta_una_lectura_de_historico():
    """La rama más frecuente del panel: una acción que el pre-cálculo no ha tocado. Sin
    veredicto no hay nada que vetar, y resolver la tendencia ahí serían cientos de
    lecturas de histórico al día para no decidir nada."""
    corte = CHARTIST.index('return {"cached": False}')
    assert "tendencia_de" not in CHARTIST[:corte]


def test_el_endpoint_sigue_devolviendo_el_marcador_de_precalculo():
    """Contrato que ya existía: `_precomputed` solo con `cached_only`."""
    assert '"_precomputed": True' in CHARTIST
    assert "cached_only and precomputado" in CHARTIST


# ── 6 · /analyze: degrada al servir, persiste lo generado ───────────────────

def _bloque_analyze() -> str:
    """El tramo de /analyze entre la persistencia y el `return`."""
    ini = SRV.index("await db.analyses.insert_one(doc)")
    fin = SRV.index('"zonas_ocultas_por_tendencia": respuesta.get(')
    return SRV[ini:fin]


def test_analyze_degrada_la_recomendacion():
    assert "veto_compra.degradar_analisis" in _bloque_analyze()


def test_analyze_persiste_antes_de_degradar():
    """En Mongo queda lo que dijo el modelo, íntegro. Lo que se degrada es lo que se
    enseña, no lo que se midió — y `track_record` sigue midiendo al modelo.

    Se mide sobre el fichero entero y no sobre el bloque: el bloque EMPIEZA en el
    `insert_one`, así que compararlos ahí dentro habría dado cierto siempre.
    """
    assert SRV.index("await db.analyses.insert_one(doc)") < \
        SRV.index("veto_compra.degradar_analisis")


def test_analyze_usa_el_estado_ya_calculado_y_no_lo_recalcula():
    bloque = _bloque_analyze()
    assert 'degradar_analisis(result, respuesta.get("estado"))' in bloque
    assert "tendencia_de" not in bloque


# ── 7 · El vigilante no notifica una compra vetada ──────────────────────────

VIGILANTE = _cuerpo("_chartist_vigilante")


def test_el_vigilante_aplica_el_mismo_veto():
    assert "market_data.tendencia_de" in VIGILANTE
    assert "veto_compra.degradar_chartista" in VIGILANTE


def test_el_vigilante_decide_sobre_el_veredicto_degradado():
    """El veto tiene que ir ANTES de leer la acción: si se leyera primero, `accion` sería
    COMPRAR y el aviso saldría igual."""
    pos_veto = VIGILANTE.index("veto_compra.degradar_chartista")
    pos_lectura = VIGILANTE.index('accion = (plan.get("accion")')
    assert pos_veto < pos_lectura


def test_el_vigilante_no_reimplementa_el_veto():
    assert "NO_COMPRAR" not in VIGILANTE


def test_el_estado_guardado_es_el_degradado():
    """`chartist_state` es contabilidad de avisos, no el veredicto generativo. Guardar
    COMPRAR mientras se veta rompería el aviso del día en que el veto se levante:
    `prev_accion` ya sería COMPRAR y la transición no dispararía nunca."""
    bloque = VIGILANTE[VIGILANTE.index("veto_compra.degradar_chartista"):]
    assert '"accion": accion' in bloque[:bloque.index("async def _guardar")]


# ── 8 · La pantalla no puede persistir una compra vetada ───────────────────

PANEL = _codigo(os.path.join(_FRONT, "components", "ChartistPanel.jsx"))


def test_el_boton_de_cartera_se_para_si_hay_veto():
    cuerpo = PANEL[PANEL.index("async function addToCartera"):]
    cuerpo = cuerpo[:cuerpo.index("api.signalsCreate")]
    assert "data?.vetado_por_tendencia" in cuerpo


def test_el_panel_no_clasifica_por_su_cuenta():
    for propio in ("NO_COMPRAR", "sma200", "ALCISTA"):
        assert propio not in PANEL, propio


def test_el_chartista_no_envia_forzar():
    """El escape del veto de Cartera tiene que ser una decisión EXPLÍCITA del usuario. Un
    escape que un automatismo puede activar solo no es un escape, es un agujero."""
    assert "forzar" not in PANEL


# ── 9 · Las fronteras siguen donde estaban ─────────────────────────────────

def test_no_se_ha_tocado_la_autoridad():
    """El veto es un CONSUMIDOR de `estado_accion`, no una segunda versión suya."""
    codigo = _codigo(os.path.join(_BACKEND, "estado_accion.py"))
    assert "veto_compra" not in codigo
    assert "COMPRAR_AHORA" not in codigo
    tend = _codigo(os.path.join(_BACKEND, "tendencia.py"))
    assert "veto_compra" not in tend


def test_las_cinco_fronteras_siguen_intactas():
    op = _codigo(os.path.join(_BACKEND, "opportunities.py"))
    assert "_potential_score" in op
    for muerto in ("tendencia_score", "calidad_score"):
        assert muerto not in _codigo(os.path.join(_BACKEND, "veto_compra.py")), muerto
    assert "/opportunities/score/{symbol}" in SRV
