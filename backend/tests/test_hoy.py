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
        hoy.tarjeta_confluencia("AMD", "AMD", "choque", fuentes(),
                                {"score": 30, "verdict": "🔴 Tu motor la EVITA"}),
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
        hoy.tarjeta_confluencia("B", "B", "acuerdo_alto", fuentes(), {"score": 70},
                                distancia_nivel=-2, fuerza_nivel=70),
        hoy.tarjeta_nivel(caliente("C"), zona()),
        hoy.tarjeta_alerta({"symbol": "D", "action": "COMPRA", "level_label": "nivel1",
                            "target": 100, "price": 100, "diff_pct": 0}),
        hoy.tarjeta_ruptura(entrada("E"), posicion(),
                            {"salida_10w": {"recien_perdida": True, "sma": 90,
                                            "distancia_pct": -3}}),
        hoy.tarjeta_confluencia("F", "F", "choque", fuentes(),
                                {"score": 25, "verdict": "🔴 evita"}),
    ]
    orden = [t["symbol"] for t in hoy.ordenar_y_recortar(tarjetas, limite=10)]
    assert orden[0] == "E", "una ruptura con dinero dentro va primero"
    assert orden[1] == "D", "después la alerta que el usuario pidió"
    assert orden.index("C") < orden.index("F"), "un nivel cerca pesa más que un choque"
    assert orden.index("F") < orden.index("B"), "el choque pesa más que el acuerdo"
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
    # Y cuando no hay respaldo, se dice; no se finge que lo hay.
    assert "no tiene todavía una zona calculada" in sin["por_que"]


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


# ── Confluencia y divergencia ────────────────────────────────────────────────
def test_choque_cuando_las_fuentes_empujan_y_el_motor_frena():
    estado = hoy.confluencia(fuentes(positivos=3), {"score": 30, "verdict": "🔴 Tu motor la EVITA"})
    assert estado == "choque"


def test_choque_tambien_en_el_sentido_contrario():
    """Las fuentes desconfían y el motor puntúa alto. Igual de informativo."""
    estado = hoy.confluencia(fuentes(positivos=0, negativos=3), {"score": 72, "verdict": "🟢"})
    assert estado == "choque"


def test_acuerdo_alto_exige_dos_fuentes_precio_en_zona_y_nivel_fuerte():
    base = (fuentes(n=2), {"score": 70, "verdict": "🟢"})
    assert hoy.confluencia(*base, distancia_nivel=-2, fuerza_nivel=70) == "acuerdo_alto"
    # Una sola fuente no es consenso.
    assert hoy.confluencia(fuentes(n=1), base[1], distancia_nivel=-2, fuerza_nivel=70) == "acuerdo"
    # Lejos del nivel es una tesis, no una oportunidad de hoy.
    assert hoy.confluencia(*base, distancia_nivel=-20, fuerza_nivel=70) == "acuerdo"
    # Un nivel flojo no sostiene la máxima convicción.
    assert hoy.confluencia(*base, distancia_nivel=-2, fuerza_nivel=20) == "acuerdo"


def test_estados_parciales():
    assert hoy.confluencia(fuentes(), None) == "solo_fuentes"
    assert hoy.confluencia({}, {"score": 80}) == "solo_motor"
    # Un motor tibio y sin menciones no es nada que contar.
    assert hoy.confluencia({}, {"score": 50}) is None
    assert hoy.confluencia({}, None) is None


def test_el_choque_se_explica_con_las_dos_partes_enfrentadas():
    t = hoy.tarjeta_confluencia("AMD", "AMD", "choque", fuentes(menciones=4, positivos=3, n=2),
                                {"score": 30, "verdict": "🔴 Tu motor la EVITA"})
    assert "empujan" in t["que_pasa"]
    assert "4 menciones" in t["por_que"] and "30/100" in t["por_que"]
    assert t["tipo"] == "divergencia"


def test_el_acuerdo_sobre_algo_que_ya_tienes_no_sube():
    """Coincidir sobre una posición abierta no es una decisión pendiente."""
    t = hoy.tarjeta_confluencia("AMD", "AMD", "acuerdo_alto", fuentes(), {"score": 70},
                                distancia_nivel=-2, fuerza_nivel=70, tiene_posicion=True)
    assert t is None
    # Pero un CHOQUE sobre algo que tienes sí importa, y mucho.
    t2 = hoy.tarjeta_confluencia("AMD", "AMD", "choque", fuentes(),
                                 {"score": 25, "verdict": "🔴"}, tiene_posicion=True)
    assert t2 is not None


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
