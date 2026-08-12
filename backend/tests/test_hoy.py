"""Portada «Hoy»: qué sube, en qué orden y qué se queda fuera.

Estas reglas SON el producto. Si el orden está mal, la pantalla que existe para
contestar «¿qué merece mi atención?» en treinta segundos contesta otra cosa, y el
fallo no se ve en ninguna pantalla rota: se ve en que dejas de mirarla.

Se prueba el módulo puro, sin base de datos ni red: `hoy.py` recibe datos ya
calculados por otros y solo decide. Esa separación es la que permite que estos
tests sean rápidos y que la lógica financiera no se toque para pintar una portada.
"""
import hoy


# ── Datos de apoyo ───────────────────────────────────────────────────────────
def entrada(symbol="MRVL", **kw):
    return {"symbol": symbol, "name": kw.get("name", f"{symbol} Inc"), **kw}


def posicion(acciones=10, pnl_eur=250.0, **kw):
    return {"acciones": acciones, "pnl_eur": pnl_eur, **kw}


def caliente(symbol="MRVL", pct_away=1.8, target=178.4, price=181.6, **kw):
    return {"symbol": symbol, "name": f"{symbol} Inc", "pct_away": pct_away,
            "target": target, "price": price, "level_label": "nivel3",
            "action": "COMPRA", **kw}


def zona(strength=78, reasons=None, distance_pct=-1.8):
    return {"price": 178.4, "strength": strength, "distance_pct": distance_pct,
            "reasons": reasons if reasons is not None else
            ["SMA200", "Fibonacci 38,2%", "VWAP anclado"]}


def fuentes(menciones=4, positivos=3, negativos=0, n=2):
    return {"menciones": menciones, "positivos": positivos, "negativos": negativos,
            "fuentes": [f"Fuente {i}" for i in range(n)]}


# ── Las tres preguntas ───────────────────────────────────────────────────────
def test_toda_tarjeta_contesta_las_tres_preguntas():
    """Es el contrato de la portada. Una tarjeta a la que le falte una de las tres
    está enseñando un dato en vez de sostener una decisión."""
    tarjetas = [
        hoy.tarjeta_nivel(caliente(), zona()),
        hoy.tarjeta_alerta({"symbol": "AAPL", "action": "COMPRA", "level_label": "nivel2",
                            "target": 180, "price": 179.9, "diff_pct": 0.05}),
        hoy.tarjeta_ruptura(entrada(), posicion(),
                            {"salida_10w": {"recien_perdida": True, "sma": 176.2,
                                            "distancia_pct": -2.1}}),
        hoy.tarjeta_resultados({"symbol": "NVDA", "date": "2026-08-12", "dias": 2},
                               posicion()),
        hoy.tarjeta_confluencia("AMD", "AMD", "CHOQUE", fuentes()),
    ]
    for t in tarjetas:
        assert t is not None
        for campo in ("que_pasa", "por_que", "que_vigilar"):
            assert t[campo], f"{t['tipo']}: falta {campo}"
            assert len(t[campo]) > 10, f"{t['tipo']}: {campo} demasiado corto"


def test_cada_tarjeta_lleva_a_su_accion():
    t = hoy.tarjeta_nivel(caliente("NVDA"), zona())
    assert t["ruta"] == "/accion/NVDA"


# ── Precedencia ──────────────────────────────────────────────────────────────
def test_el_orden_pone_primero_lo_que_puede_costarte_dinero_hoy():
    tarjetas = [
        hoy.tarjeta_resultados({"symbol": "A", "dias": 1}, posicion()),
        hoy.tarjeta_confluencia("B", "B", "ACUERDO", fuentes()),
        hoy.tarjeta_nivel(caliente("C"), zona()),
        hoy.tarjeta_alerta({"symbol": "D", "action": "COMPRA", "level_label": "nivel1",
                            "target": 100, "price": 100, "diff_pct": 0}),
        hoy.tarjeta_ruptura(entrada("E"), posicion(),
                            {"salida_10w": {"recien_perdida": True, "sma": 90,
                                            "distancia_pct": -3}}),
        hoy.tarjeta_confluencia("F", "F", "CHOQUE", fuentes()),
    ]
    orden = [t["symbol"] for t in hoy.ordenar_y_recortar(tarjetas, limite=10)]
    assert orden[0] == "E", "una ruptura con dinero dentro va primero"
    assert orden[1] == "D", "después la alerta que el usuario pidió"
    assert orden.index("C") < orden.index("F"), "un nivel cerca pesa más que un choque"
    # Retirado `acuerdo_alto`, todas las coincidencias caen a BASE["confluencia"] y el
    # choque pasa a ir SIEMPRE por delante. Antes el +60 podía invertirlo; ese +60 lo
    # justificaba información de zona que ya no forma parte de la confluencia.
    assert orden.index("F") < orden.index("B"), "el choque pesa más que la coincidencia"
    assert orden[-1] == "A", "unos resultados a 1 día son lo menos urgente de la lista"


def test_mas_cerca_del_nivel_es_mas_urgente():
    lejos = hoy.tarjeta_nivel(caliente("X", pct_away=3.8), zona())
    cerca = hoy.tarjeta_nivel(caliente("Y", pct_away=0.4), zona())
    assert cerca["urgencia"] > lejos["urgencia"]


def test_un_nivel_con_respaldo_del_motor_pesa_mas_que_uno_escrito_a_mano():
    con = hoy.tarjeta_nivel(caliente("X"), zona(strength=85))
    sin = hoy.tarjeta_nivel(caliente("Y"), None)
    assert con["urgencia"] > sin["urgencia"]
    assert "fuerza 85/100" in con["por_que"]
    assert con["datos"]["motor_niveles"] == "confirma"


# ── Los dos motores, nombrados por separado ──────────────────────────────────
def test_sin_datos_del_motor_no_se_insinua_rechazo():
    """«El motor no tiene zona» se leía como «el motor lo descarta». Son cosas muy
    distintas y una de ellas es una recomendación que nadie ha hecho."""
    t = hoy.tarjeta_nivel(caliente("X"), None, motor_con_datos=False)
    assert t["datos"]["motor_niveles"] == "sin_datos"
    assert "Motor de niveles: sin datos todavía" in t["por_que"]
    assert "No es un rechazo ni una confirmación" in t["por_que"]


def test_se_distingue_sin_datos_de_sin_zona_en_este_precio():
    """Que el motor no haya calculado NADA y que haya calculado pero sus zonas caigan
    lejos son dos situaciones distintas; antes se leían igual."""
    sin_datos = hoy.tarjeta_nivel(caliente("X"), None, motor_con_datos=False)
    sin_zona = hoy.tarjeta_nivel(caliente("Y"), None, motor_con_datos=True)
    assert sin_datos["datos"]["motor_niveles"] == "sin_datos"
    assert sin_zona["datos"]["motor_niveles"] == "sin_zona"
    assert "ninguna cae en este precio" in sin_zona["por_que"]
    assert sin_datos["por_que"] != sin_zona["por_que"]


def test_la_tarjeta_de_niveles_nombra_el_motor_entero():
    """Nunca «el motor» a secas: hay dos y solo uno vive en la caché."""
    t = hoy.tarjeta_nivel(caliente("X"), zona(strength=78))
    assert "Motor de niveles" in t["por_que"]


# ── Máximo cinco, mínimo honesto ─────────────────────────────────────────────
def test_nunca_pasan_de_cinco():
    tarjetas = [hoy.tarjeta_nivel(caliente(f"S{i}", pct_away=0.5 + i * 0.1), zona())
                for i in range(12)]
    assert len(hoy.ordenar_y_recortar(tarjetas)) == 5


def test_si_solo_hay_dos_salen_dos():
    """El mínimo honesto es la mitad importante de la regla: una lista que siempre
    mide lo mismo deja de leerse en una semana."""
    tarjetas = [hoy.tarjeta_nivel(caliente("A"), zona()),
                hoy.tarjeta_nivel(caliente("B", pct_away=2.2), zona())]
    assert len(hoy.ordenar_y_recortar(tarjetas)) == 2


def test_un_dia_sin_nada_devuelve_una_lista_vacia_no_relleno():
    assert hoy.ordenar_y_recortar([]) == []
    assert hoy.ordenar_y_recortar([None, None]) == []


def test_una_tarjeta_por_ticker_y_el_resto_se_dobla_dentro():
    """Tres tarjetas del mismo ticker ocuparían la portada entera diciendo lo mismo."""
    tarjetas = [
        hoy.tarjeta_nivel(caliente("MRVL"), zona()),
        hoy.tarjeta_alerta({"symbol": "MRVL", "action": "COMPRA", "level_label": "nivel2",
                            "target": 170, "price": 171, "diff_pct": 0.6}),
        hoy.tarjeta_nivel(caliente("NVDA", pct_away=2.0), zona()),
    ]
    salida = hoy.ordenar_y_recortar(tarjetas)
    assert [t["symbol"] for t in salida] == ["MRVL", "NVDA"]
    mrvl = salida[0]
    assert mrvl["tipo"] == "alerta", "gana la de mayor precedencia"
    assert len(mrvl["tambien"]) == 1
    assert mrvl["tambien"][0]["tipo"] == "nivel", "lo que pierde no se tira: se dobla dentro"


# ── Filtros de entrada ───────────────────────────────────────────────────────
def test_un_nivel_lejano_no_es_de_hoy():
    """/signals/hot filtra al 10%, pero un 9% no es «hoy»: es «algún día»."""
    assert hoy.tarjeta_nivel(caliente(pct_away=9.0), zona()) is None
    assert hoy.tarjeta_nivel(caliente(pct_away=3.9), zona()) is not None


def test_sin_posicion_abierta_no_hay_ruptura_ni_resultados():
    indicadores = {"salida_10w": {"recien_perdida": True, "sma": 90, "distancia_pct": -3}}
    assert hoy.tarjeta_ruptura(entrada(), None, indicadores) is None
    assert hoy.tarjeta_ruptura(entrada(), posicion(acciones=0), indicadores) is None
    # Unos resultados de algo que no tienes son una noticia, no una decisión.
    assert hoy.tarjeta_resultados({"symbol": "A", "dias": 1}, posicion(acciones=0)) is None


def test_los_resultados_lejanos_no_suben():
    assert hoy.tarjeta_resultados({"symbol": "A", "dias": 9}, posicion()) is None
    assert hoy.tarjeta_resultados({"symbol": "A", "dias": 3}, posicion()) is not None


def test_sin_ruptura_reciente_no_hay_tarjeta():
    assert hoy.tarjeta_ruptura(entrada(), posicion(),
                               {"salida_10w": {"recien_perdida": False}}) is None
    assert hoy.tarjeta_ruptura(entrada(), posicion(), {}) is None


# ── Confluencia: ahora la clasifica `confluencia.py` ────────────────────────
# Los tests de clasificación viven en `test_confluencia.py`. `hoy.py` ya no clasifica:
# solo redacta la tarjeta a partir del estado que recibe. Aquí se prueba la redacción.

def test_solo_se_redactan_los_dos_estados_que_dicen_algo():
    """NEUTRAL, MIXTO, INSUFICIENTE y SIN_FUENTES no llegan a la portada: un texto por
    cada acción se convierte en ruido y entrena a no mirar cuando sí importa."""
    for estado in ("NEUTRAL", "MIXTO", "INSUFICIENTE", "SIN_FUENTES", "acuerdo_alto", ""):
        assert hoy.tarjeta_confluencia("X", "X", estado, fuentes()) is None, estado


def test_el_choque_se_explica_con_las_dos_partes_enfrentadas():
    t = hoy.tarjeta_confluencia("AMD", "AMD", "CHOQUE",
                                fuentes(menciones=4, positivos=3, n=2))
    assert t["tipo"] == "divergencia"
    texto = t["que_pasa"] + t["por_que"]
    assert "fuentes" in texto.lower()
    assert "tendencia" in texto.lower()


def test_el_choque_en_sentido_contrario_lo_dice_al_reves():
    t = hoy.tarjeta_confluencia("AMD", "AMD", "CHOQUE",
                                fuentes(menciones=4, positivos=0, negativos=3, n=2))
    assert "desconfían" in t["que_pasa"]


def test_la_coincidencia_no_habla_de_zona_ni_de_entrada():
    """`acuerdo_alto` decía «y el precio está en zona». Eso es información de ENTRADA y
    se retiró de la confluencia; el texto no puede seguir insinuándolo."""
    t = hoy.tarjeta_confluencia("X", "X", "ACUERDO", fuentes())
    todo = (t["que_pasa"] + t["por_que"] + t["que_vigilar"]).lower()
    for prohibido in ("en zona", "fuerza", "/100", "stop", "objetivo"):
        assert prohibido not in todo, prohibido


def test_la_coincidencia_sobre_algo_que_ya_tienes_no_sube():
    """Sobre lo que ya tienes, coincidir no es una decisión pendiente. El choque sí sube:
    ahí sigue habiendo algo que resolver."""
    assert hoy.tarjeta_confluencia("AMD", "AMD", "ACUERDO", fuentes(),
                                   tiene_posicion=True) is None
    assert hoy.tarjeta_confluencia("AMD", "AMD", "CHOQUE", fuentes(),
                                   tiene_posicion=True) is not None


def test_la_coincidencia_ya_no_recibe_veredicto_ni_niveles():
    """La firma es la garantía de que la confluencia no puede volver a mezclar zona."""
    import inspect
    params = set(inspect.signature(hoy.tarjeta_confluencia).parameters)
    assert params == {"symbol", "nombre", "estado", "fuentes", "tiene_posicion"}


# ── La alerta se explica como alerta ─────────────────────────────────────────
def test_una_alerta_disparada_lo_dice_en_el_titular():
    """El titular decía «ha tocado tu Nivel 3», que se lee igual que un nivel cercano.
    Una alerta saltada es otra cosa: es una promesa que el usuario pidió que se
    cumpliera, y eso es lo que exige una decisión."""
    t = hoy.tarjeta_alerta({"symbol": "FORM", "action": "COMPRA", "level_label": "nivel3",
                            "target": 115.0, "price": 115.0, "diff_pct": 0.0})
    assert "se ha disparado tu alerta de compra" in t["que_pasa"]
    assert "115.00" in t["que_pasa"]
    # El nivel baja a contexto, no desaparece.
    assert "Nivel 3" in t["por_que"]


def test_la_alerta_de_venta_no_se_llama_compra():
    t = hoy.tarjeta_alerta({"symbol": "X", "action": "VENTA", "level_label": "deseado",
                            "target": 10.0, "price": 10.0, "diff_pct": 0.0})
    assert "alerta de venta" in t["que_pasa"]


def test_la_tarjeta_de_alerta_no_habla_del_motor():
    """No tiene por qué: la alerta la puso el usuario y no depende de ningún motor.
    Mezclarlos era parte de la confusión."""
    t = hoy.tarjeta_alerta({"symbol": "X", "action": "COMPRA", "level_label": "nivel1",
                            "target": 10.0, "price": 10.0, "diff_pct": 0.0})
    texto = f"{t['que_pasa']} {t['por_que']} {t['que_vigilar']}"
    assert "motor" not in texto.lower()


# ── Línea de saludo ──────────────────────────────────────────────────────────
def test_el_saludo_cuenta_lo_que_de_verdad_ha_salido():
    """Si dijera «3 niveles cerca» y debajo hubiera uno, mentiría — y es lo primero
    que se lee. Por eso se construye contando las tarjetas finales."""
    tarjetas = hoy.ordenar_y_recortar([
        hoy.tarjeta_nivel(caliente("A"), zona()),
        hoy.tarjeta_nivel(caliente("B", pct_away=2.0), zona()),
        hoy.tarjeta_alerta({"symbol": "C", "action": "COMPRA", "level_label": "nivel1",
                            "target": 10, "price": 10, "diff_pct": 0}),
    ])
    r = hoy.resumen_de_saludo(tarjetas, {"tickers_nuevos": ["XYZ"]})
    assert r["total"] == 3
    assert "1 alerta saltada" in r["piezas"]
    assert "2 niveles cerca" in r["piezas"]
    assert "1 ticker nuevo en tus fuentes" in r["piezas"]


def test_el_saludo_usa_singular_y_plural_correctos():
    una = hoy.resumen_de_saludo([hoy.tarjeta_nivel(caliente("A"), zona())])
    assert "1 nivel cerca" in una["piezas"]


def test_un_dia_tranquilo_no_inventa_piezas():
    r = hoy.resumen_de_saludo([], {})
    assert r["piezas"] == []
    assert r["total"] == 0
