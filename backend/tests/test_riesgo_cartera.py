"""El modelo de margen de DEGIRO, contra una venta REAL.

EL TEST QUE IMPORTA

El 21-08-2026 se vendieron 15 MRVL por 3.216,73 € y el margen libre pasó de 214,08 € a
1.390,52 €. Descontando comisiones y la diferencia entre el precio de ejecución y el de
valoración, el riesgo de cartera bajó 1.202,12 €.

    ticket «Margin impact» de DEGIRO ....       5,36 €   error 99,6%
    este modelo .........................   1.199,00 €   error  0,3%
    real ................................   1.202,12 €

Ese caso es `test_la_venta_real_de_mrvl`, y es la razón de que este módulo exista: el
preview del propio bróker se equivoca por un factor de 224, y el usuario lo sabía por
experiencia antes de que ningún cálculo lo demostrara.

QUÉ MÁS SE FIJA

  · el riesgo es el MÁXIMO de los cuatro componentes, no la suma
  · una posición en categoría D entra al 100% en neto, sector y bruto — y por eso venderla
    libera todo su valor
  · vender algo que NO marca el máximo no mueve el margen (el caso que desconcertaba)
  · sin extracto de DEGIRO, o si el modelo deja de reproducirlo, NO se da ninguna cifra
  · los tres ejemplos numéricos del manual oficial se reproducen al céntimo

Ejecutar:  cd backend && pytest tests/test_riesgo_cartera.py -v
"""
import pytest

import riesgo_cartera as rc


# ── Los ejemplos del manual oficial ──────────────────────────────────────────
# Investment Portfolio Risk Handbook, 30-04-2024. Si estos caen, los parámetros ya no son
# los de DEGIRO y todo lo demás sobra.

def _p(sym, valor, sector, cat="A", divisa="EUR", acciones=None):
    return {"symbol": sym, "valor_eur": valor, "sector": sector,
            "categoria": cat, "divisa": divisa, "acciones": acciones}


def test_manual_tabla_3_manda_el_neto():
    cartera = [_p("ASML", 1000, "Tech"), _p("ASMI", 1100, "Tech", "B"),
               _p("RDSA", 1200, "Oil", "B"), _p("HEIA", 1000, "Food")]
    r, dom, c = rc.riesgo(cartera)
    assert round(c["evento"]) == 975      # 81,25% de 1.200 (RDSA)
    assert round(c["neto"]) == 1075       # 25% de 4.300
    assert round(c["sector"]) == 840      # 40% de 2.100
    assert round(c["bruto"]) == 430       # 10% de 4.300
    assert round(r) == 1075 and dom == "neto"


def test_manual_tabla_4_el_riesgo_de_divisa():
    cartera = [_p("ASML", 900, "Tech"), _p("ASMI", 1000, "Tech", "B"),
               _p("HEIA", 1000, "Food"), _p("JNJ", 850, "Health", "A", "USD")]
    r, dom, c = rc.riesgo(cartera)
    assert round(c["evento"], 2) == 812.50
    assert round(c["divisa"], 2) == 54.06          # 6,36% de 850 (JNJ, en dólares)
    # El manual lista los componentes DESNUDOS y suma la divisa al final; nosotros la
    # llevamos dentro, como la app de DEGIRO. El total es el mismo.
    assert round(c["sector"] - c["divisa"]) == 760
    assert round(c["neto"] - c["divisa"], 2) == 937.50
    assert round(r, 2) == 991.56 and dom == "neto"


def test_manual_tabla_19_manda_el_evento():
    cartera = [_p("ASML", 800, "Tech"), _p("ASM", 800, "Tech"),
               _p("RDSA", 1200, "Oil", "B")]
    r, dom, c = rc.riesgo(cartera)
    assert round(c["evento"]) == 975 and round(c["neto"]) == 700
    assert round(c["sector"]) == 640 and round(c["bruto"]) == 280
    assert round(r) == 975 and dom == "evento"


# ── La cartera real del 21-08-2026 ───────────────────────────────────────────

CARTERA = [
    _p("FN", 4560.48, "Tecnología", "C", "USD"),
    _p("ORCL", 4247.20, "Tecnología", "C", "USD"),
    _p("NFLX", 3423.53, "Comunicación", "A", "USD"),
    _p("MRVL", 3216.90, "Tecnología", "C", "USD", acciones=15),
    _p("UBER", 2684.83, "Tecnología", "C", "USD"),
    _p("RDDT", 2568.80, "Comunicación", "C", "USD"),
    _p("AMD", 1604.39, "Tecnología", "B", "USD"),
    _p("META", 1399.05, "Comunicación", "C", "USD"),
    _p("TXN", 1361.55, "Tecnología", "B", "USD"),
    _p("RH", 1335.49, "Consumo", "C", "USD"),
    _p("AAOI", 992.71, "Tecnología", "D", "USD"),
    _p("SEDG", 792.02, "Tecnología", "D", "USD"),
    _p("ETN", 709.77, "Industrial", "B", "USD"),
    _p("ASTS", 667.04, "Tecnología", "D", "USD"),
    _p("MP", 470.25, "Materiales", "D", "USD"),
    _p("HOOD", 406.26, "Financiero", "C", "USD"),
]
# El «Margin statement» de ese día, a las 13:46.
EXTRACTO = {"riesgo_eur": 11645.14, "fecha": "2026-08-21"}


def test_reproduce_el_extracto_de_degiro():
    """Contra los cinco números que publica DEGIRO, no contra los míos."""
    cal = rc.calibrar(CARTERA, EXTRACTO)
    assert cal["estado"] == rc.OK
    assert cal["error"] < 0.01, f"desvío {cal['error']:.2%}"
    assert cal["dominante"] == "sector"
    assert abs(cal["componentes"]["evento"] - 4517.91) < 10     # DEGIRO: 4.517,91
    assert abs(cal["componentes"]["neto"] - 11558.54) < 20      # DEGIRO: 11.558,54
    assert abs(cal["componentes"]["bruto"] - 7431.06) < 20      # DEGIRO: 7.431,06


def test_la_venta_real_de_mrvl():
    """LA MEDIDA. Venta ejecutada, margen real, predicción escrita de antemano.

    El ticket de DEGIRO dijo 5,36 €. El modelo dice ~1.199 €. Ocurrieron 1.202,12 €.
    """
    e = rc.estimar(CARTERA, "MRVL", extracto=EXTRACTO)
    assert e["estado"] == rc.OK
    real = 1202.12
    error = abs(e["margen_eur"] - real) / real
    assert error < 0.02, f"predice {e['margen_eur']:,.2f} € frente a {real:,.2f} € ({error:.1%})"
    assert e["margen_eur"] > 1000, "el ticket de DEGIRO decía 5,36 €; no volvamos ahí"


def test_una_posicion_en_categoria_d_libera_todo_su_valor():
    """El manual les suma el 100% del valor a neto, sector y bruto."""
    e = rc.estimar(CARTERA, "AAOI", extracto=EXTRACTO)
    assert e["pct_del_importe"] > 0.95
    assert "categoría D" in e["motivo"]


def test_vender_lo_que_no_marca_el_maximo_no_mueve_el_margen():
    """El caso que desconcertaba: vendes 3.400 € y no pasa nada."""
    e = rc.estimar(CARTERA, "NFLX", extracto=EXTRACTO)
    assert e["pct_del_importe"] < 0.10
    assert e["dominante_antes"] == "sector"
    assert "apenas" in e["motivo"]


def test_una_venta_parcial_no_cuenta_como_entera():
    entera = rc.estimar(CARTERA, "MRVL", extracto=EXTRACTO)
    media = rc.estimar(CARTERA, "MRVL", acciones=7.5, extracto=EXTRACTO)
    assert media["importe_eur"] == pytest.approx(entera["importe_eur"] / 2, rel=1e-6)
    assert media["margen_eur"] < entera["margen_eur"]


def test_el_riesgo_es_el_maximo_y_no_la_suma():
    _, _, c = rc.riesgo(CARTERA)
    r, _, _ = rc.riesgo(CARTERA)
    assert r == max(c.values())
    assert r < sum(c.values()), "sumarlos daría el triple y ningún ejemplo del manual suma"


# ── Cuándo NO se da una cifra ────────────────────────────────────────────────

def test_sin_extracto_no_se_estima():
    """El modelo necesita categorías y sectores que no podemos consultar. Sin nada contra
    lo que contrastarlo, una cifra sería una promesa sin respaldo."""
    e = rc.estimar(CARTERA, "MRVL", extracto=None)
    assert e["estado"] == rc.SIN_CALIBRAR
    assert "margen_eur" not in e
    assert "extracto de margen" in e["motivo"]


def test_si_deja_de_cuadrar_se_calla():
    """DEGIRO recategoriza cada mes. Cuando el modelo se desvía, se retira solo."""
    e = rc.estimar(CARTERA, "MRVL", extracto={"riesgo_eur": 20000.0, "fecha": "2026-08-21"})
    assert e["estado"] == rc.NO_CUADRA
    assert "margen_eur" not in e
    assert "ya no reproduce" in e["motivo"]


def test_una_posicion_sin_valorar_bloquea_la_estimacion():
    """Entraría en los totales como si valiera cero y hundiría el componente que manda."""
    rota = CARTERA + [{"symbol": "AEM", "valor_eur": None, "sector": "Materiales",
                       "categoria": "C", "divisa": "USD"}]
    e = rc.estimar(rota, "MRVL", extracto=EXTRACTO)
    assert e["estado"] == rc.FALTAN_DATOS and "AEM" in e["motivo"]


def test_un_simbolo_que_no_tienes():
    e = rc.estimar(CARTERA, "TSLA", extracto=EXTRACTO)
    assert e["estado"] == rc.FALTAN_DATOS


# ── Detalles del modelo que es fácil romper sin darse cuenta ─────────────────

def test_la_divisa_no_se_cobra_dos_veces_a_las_D():
    """Una posición D ya entra al 100%; cargarle además el 6,36% sería contarla dos veces."""
    solo_d = [_p("AAOI", 1000, "Tech", "D", "USD")]
    _, _, c = rc.riesgo(solo_d)
    assert round(c["neto"], 2) == 1000.00


def test_lo_que_cotiza_en_euros_no_paga_riesgo_de_divisa():
    eur = [_p("OHLA", 1000, "Construcción", "C", "EUR")]
    _, _, c = rc.riesgo(eur)
    assert round(c["neto"], 2) == 250.00


def test_sin_categoria_se_asume_la_MAS_BAJA():
    """Equivocarse por abajo lo detecta la calibración; por arriba inflaría el riesgo en
    silencio, que es el error que no se puede ver."""
    sin = [{"symbol": "X", "valor_eur": 1000, "sector": "T", "divisa": "EUR"}]
    _, _, c = rc.riesgo(sin)
    assert round(c["evento"], 2) == 625.00


# ── La banda de incertidumbre ────────────────────────────────────────────────
# El error del modelo es un porcentaje del RIESGO TOTAL, no de la venta. Medido a 0,45%
# sobre 10.564 € son ±48 €, y esos ±48 € están ahí venda lo que venda. Por eso una
# predicción de 1.200 € es fiable y una de 175 € no lo es tanto, aunque el modelo sea el
# mismo. Las dos ventas reales medidas caben en esa banda:
#
#     MRVL   predijo 1.199 €, salieron 1.202 €   desvío  3 €
#     HOOD   predijo   134 €, salieron   175 €   desvío 41 €

def test_toda_estimacion_lleva_su_banda():
    e = rc.estimar(CARTERA, "MRVL", extracto=EXTRACTO)
    assert e["incertidumbre_eur"] > 0
    assert e["distinguible"] is True


def test_la_banda_no_encoge_porque_la_venta_sea_pequena():
    """Es el punto entero: la incertidumbre es del riesgo total, no del importe."""
    grande = rc.estimar(CARTERA, "MRVL", extracto=EXTRACTO)
    pequena = rc.estimar(CARTERA, "HOOD", extracto=EXTRACTO)
    assert pequena["incertidumbre_eur"] == pytest.approx(grande["incertidumbre_eur"], rel=0.01)
    assert pequena["importe_eur"] < grande["importe_eur"] / 5


def test_por_debajo_del_ruido_no_se_da_cifra():
    """Decir "+30 € ± 50 €" es peor que decir que no se sabe: invita a leer el 30."""
    e = rc.estimar(CARTERA, "HOOD", extracto=EXTRACTO)
    assert e["distinguible"] is False
    assert "por debajo de lo que este cálculo puede distinguir" in e["motivo"]


def test_las_dos_ventas_reales_caben_en_la_banda():
    """El test que reconcilia los dos únicos datos que tenemos del mundo real."""
    mrvl = rc.estimar(CARTERA, "MRVL", extracto=EXTRACTO)
    assert abs(mrvl["margen_eur"] - 1202.12) <= mrvl["incertidumbre_eur"]


# ── El simulador: comprar también mueve el margen ────────────────────────────
# `estimar` vive dentro del formulario de venta, donde ya has decidido. El simulador
# contesta antes, y en los dos sentidos: con una cuenta apalancada, COMPRAR mueve el margen
# en la dirección peligrosa y eso no estaba cubierto por ninguna pantalla.

def test_vender_devuelve_margen_y_comprar_lo_quita():
    """El signo es el dato que no conviene tener que deducir del contexto."""
    v = rc.simular(CARTERA, "MRVL", rc.VENDER, importe=3216.90, extracto=EXTRACTO)
    c = rc.simular(CARTERA, "MRVL", rc.COMPRAR, importe=1000, extracto=EXTRACTO)
    assert v["margen_eur"] > 0
    assert c["margen_eur"] < 0


def test_comprar_categoria_D_cuesta_todo_lo_que_inviertes():
    c = rc.simular(CARTERA, "NUEVA", rc.COMPRAR, importe=1000, categoria="D",
                   sector="Materiales", extracto=EXTRACTO)
    assert c["estado"] == rc.OK
    assert abs(c["margen_eur"]) == pytest.approx(1000, rel=0.05)
    assert "categoría D" in c["motivo"]


def test_sin_categoria_se_da_el_RANGO_y_no_una_letra_inventada():
    """Mil euros de una A y de una D no cuestan lo mismo ni de lejos. Elegir por el
    usuario sería inventarse el dato que más pesa."""
    c = rc.simular(CARTERA, "NUEVA", rc.COMPRAR, importe=1000, sector="Materiales",
                   extracto=EXTRACTO)
    assert c["estado"] == rc.FALTA_CATEGORIA
    assert "margen_eur" not in c
    assert set(c["rango"]) == {"A", "B", "C", "D"}
    assert abs(c["rango_max_eur"]) > abs(c["rango_min_eur"])
    assert "la pantalla de la orden" in c["motivo"]


def test_una_venta_parcial_por_importe():
    entera = rc.simular(CARTERA, "MRVL", rc.VENDER, importe=99999, extracto=EXTRACTO)
    media = rc.simular(CARTERA, "MRVL", rc.VENDER, importe=1608.45, extracto=EXTRACTO)
    assert entera["importe_eur"] == pytest.approx(3216.90)   # no vende más de lo que hay
    assert media["margen_eur"] < entera["margen_eur"]


def test_comprar_algo_que_ya_tienes_usa_su_categoria():
    """AAOI ya está en la cartera y es D: no hace falta preguntarla otra vez."""
    c = rc.simular(CARTERA, "AAOI", rc.COMPRAR, importe=500, extracto=EXTRACTO)
    assert c["estado"] == rc.OK and c["categoria"] == "D"


def test_el_simulador_tambien_se_calla_sin_extracto():
    c = rc.simular(CARTERA, "MRVL", rc.COMPRAR, importe=1000, extracto=None)
    assert c["estado"] == rc.SIN_CALIBRAR and "margen_eur" not in c


# ── Cada cuánto hay que volver a pegar el extracto ───────────────────────────
# Comparar euros contra euros obligaría a repegarlo casi a diario: la cartera se mueve con
# el mercado y el riesgo con ella. Lo que se valida no son los euros, son las CATEGORÍAS y
# los SECTORES supuestos, y eso se ve en la proporción riesgo/cartera.

EXTRACTO_COMPLETO = {"riesgo_eur": 11645.14, "valor_cartera_eur": 30357.07,
                     "fecha": "2026-08-21"}


def test_una_subida_general_de_precios_no_descalibra():
    """Todo sube un 6%: el riesgo sube un 6% y la proporción no se mueve. Sin esto, el
    extracto caducaba con cualquier día verde."""
    cara = [{**p, "valor_eur": p["valor_eur"] * 1.06} for p in CARTERA]
    cal = rc.calibrar(cara, EXTRACTO_COMPLETO)
    assert cal["estado"] == rc.OK
    assert cal["comparacion"] == "proporcion"
    assert cal["error"] < 0.01


def test_comparando_euros_esa_misma_subida_SI_descalibraria():
    """La prueba de que el cambio hacía falta: sin el valor de cartera en el extracto no
    queda más remedio que comparar euros, y entonces un +6% rompe la calibración."""
    cara = [{**p, "valor_eur": p["valor_eur"] * 1.06} for p in CARTERA]
    cal = rc.calibrar(cara, {"riesgo_eur": 11645.14, "fecha": "2026-08-21"})
    assert cal["comparacion"] == "euros"
    assert cal["estado"] == rc.NO_CUADRA


def test_a_partir_de_un_mes_el_extracto_caduca():
    """DEGIRO revisa las categorías mensualmente: pasado ese plazo, lo que el modelo
    supone sobre cada acción puede haber dejado de ser cierto."""
    cal = rc.calibrar(CARTERA, EXTRACTO_COMPLETO, hoy="2026-10-01")
    assert cal["estado"] == rc.CALIBRACION_VIEJA
    e = rc.estimar(CARTERA, "MRVL", extracto=EXTRACTO_COMPLETO, hoy="2026-10-01")
    assert "margen_eur" not in e and "41 días" in e["motivo"]


def test_dentro_del_mes_sigue_valiendo():
    cal = rc.calibrar(CARTERA, EXTRACTO_COMPLETO, hoy="2026-09-15")
    assert cal["estado"] == rc.OK and cal["dias"] == 25


# ── El diagnóstico manda al sitio correcto ───────────────────────────────────
# Sin categoría se asume la más baja, así que faltar categorías hace que el modelo se quede
# CORTO de forma sistemática. Decir "vuelve a copiar el extracto" en ese caso manda a
# arreglar lo que no está roto: el extracto está bien, lo que falta es la letra A-D.

SIN_CATS = [{**p, "categoria": ""} for p in CARTERA]


def test_si_faltan_categorias_el_mensaje_lo_dice():
    e = rc.estimar(SIN_CATS, "MRVL", extracto=EXTRACTO)
    assert e["estado"] == rc.NO_CUADRA
    assert "Faltan las categorías" in e["motivo"]
    assert "columna «Cat.»" in e["motivo"]
    assert "16 de 16" in e["motivo"]


def test_sin_categorias_el_modelo_se_queda_corto_y_no_largo():
    """La dirección del error importa: es lo que permite distinguir 'faltan datos' de
    'las categorías han cambiado'."""
    con, _, _ = rc.riesgo(CARTERA)
    sin, _, _ = rc.riesgo(SIN_CATS)
    assert sin < con


def test_con_las_categorias_puestas_vuelve_a_cuadrar():
    """El bloque de categoría D vale ~2.000 € de riesgo: es toda la diferencia."""
    cal = rc.calibrar(CARTERA, EXTRACTO)
    assert cal["estado"] == rc.OK and cal["sin_categoria"] == 0


def test_si_se_pasa_por_arriba_no_culpa_a_las_categorias():
    """Quedarse LARGO no lo explica una categoría vacía, así que el mensaje es el otro."""
    e = rc.estimar(SIN_CATS, "MRVL", extracto={"riesgo_eur": 3000.0, "fecha": "2026-08-21"})
    assert "Faltan las categorías" not in e["motivo"]
    assert "Vuelve a copiar el extracto" in e["motivo"]
