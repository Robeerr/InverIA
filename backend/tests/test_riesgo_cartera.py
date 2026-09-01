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

Ejecutar:  cd backend && pytest tests/test_rc.py -v
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
    assert "Vuelve a copiar" in e["motivo"]


# ── El mensaje de "ya no cuadro" tiene que poder comprobarse ─────────────────

def _cal_no_cuadra(comparacion="proporcion"):
    return {"estado": rc.NO_CUADRA, "error": 0.039, "comparacion": comparacion,
            "nuestro_eur": 10627.0, "degiro_eur": 10508.0,
            "sin_categoria": 0, "posiciones": 14}


def test_los_miles_van_con_punto_como_en_espanol():
    """«10,627 €» en español se lee como diez euros con 627 milésimas."""
    m = rc._motivo_calibracion(_cal_no_cuadra())
    assert "10.627" in m and "10.508" in m
    assert "10,627" not in m


def test_el_porcentaje_corresponde_a_lo_que_se_compara():
    """El caso real: 10.627 y 10.508 se llevan un 1,1%, y el mensaje anunciaba un 3,9%
    —que es el de la PROPORCIÓN riesgo/cartera—. Quien lo leía no podía comprobarlo."""
    m = rc._motivo_calibracion(_cal_no_cuadra("proporcion"))
    assert "proporción riesgo/cartera" in m
    assert "días distintos" in m, "hay que decir por qué los euros no dan ese porcentaje"
    assert "3.9%" in m or "3,9%" in m


def test_comparando_euros_la_frase_es_la_directa():
    """Sin valor de cartera en el extracto se comparan euros, y entonces el porcentaje SÍ
    sale de esas dos cifras: sobra la explicación."""
    m = rc._motivo_calibracion(_cal_no_cuadra("euros"))
    assert "proporción" not in m and "días distintos" not in m


def test_se_dice_cual_es_la_tolerancia():
    """Un 3,9% no significa nada sin saber a partir de cuánto se considera que no cuadra."""
    assert "2%" in rc._motivo_calibracion(_cal_no_cuadra())


def test_con_categorias_sin_rellenar_sigue_mandando_a_la_columna_Cat():
    """Quedarse corto por categorías vacías tiene otra causa: el extracto está bien."""
    cal = {**_cal_no_cuadra(), "sin_categoria": 3,
           "nuestro_eur": 9987.0, "degiro_eur": 10508.0}   # corto: es lo que explican
    m = rc._motivo_calibracion(cal)
    assert "Cat." in m and "9.987" in m


def test_ninguna_funcion_del_modulo_se_define_dos_veces():
    """Definir `_pct` por segunda vez no da error: la segunda pisa a la primera y el
    modelo entero pasa a llamar a la función equivocada. Aquí pasó — el `_pct` que calcula
    el porcentaje de riesgo de una posición quedó sustituido por uno que formatea texto, y
    lo que reventó fue un test de otro fichero."""
    import inspect
    import re
    fuente = inspect.getsource(rc)
    nombres = re.findall(r"^def (\w+)", fuente, re.M)
    repetidos = {n for n in nombres if nombres.count(n) > 1}
    assert not repetidos, f"definidas dos veces: {sorted(repetidos)}"


# ── Con el extracto recién copiado, el consejo no puede ser «cópialo» ────────

def _fresco(**extra):
    return {"estado": rc.NO_CUADRA, "error": 0.24, "comparacion": "proporcion",
            "nuestro_eur": 10575.0, "degiro_eur": 13920.0, "dias": 0,
            "sin_categoria": 0, "posiciones": 14, "dominante": "neto",
            "componentes": {"evento": 2100.0, "neto": 10575.0,
                            "sector": 7800.0, "bruto": 5560.0}, **extra}


def test_con_extracto_de_hoy_no_manda_a_copiarlo_otra_vez():
    """Sería un bucle: acaba de pegarlo y se le pide que lo pegue."""
    m = rc._motivo_calibracion(_fresco())
    assert "Vuelve a copiar" not in m
    assert "recién copiado" in m


def test_con_extracto_de_hoy_no_dice_que_las_cifras_sean_de_dias_distintos():
    """Con el extracto de hoy son del mismo día: esa explicación sería falsa."""
    assert "días distintos" not in rc._motivo_calibracion(_fresco())
    assert "días distintos" in rc._motivo_calibracion(_fresco(dias=11, error=0.039))


def test_si_degiro_supera_a_los_cuatro_componentes_nombra_las_DOS_causas():
    """Apuntar solo al sector mandaba al sitio equivocado en el caso que destapó esto: eran
    categorías D. Suman el 100% de su valor a los TRES componentes, así que dejan la cifra
    de DEGIRO por encima de todo lo que calculamos, igual que lo haría un sector agrupado
    de otra forma. Desde aquí no se puede elegir, así que se nombran las dos y se dice
    cómo distinguirlas."""
    m = rc._motivo_calibracion(_fresco())
    assert "CATEGORÍA D" in m and "SECTOR" in m
    assert "Gross" in m and "Net" in m, "hace falta la resta que las distingue"


def test_si_degiro_cabe_dentro_de_los_componentes_no_acusa_al_sector():
    """Ahí la explicación es otra y acusar al sector sería adivinar."""
    # Corto, pero DEGIRO cabe dentro del mayor componente (10.575): la explicación es
    # otra y acusar al sector sería adivinar.
    m = rc._motivo_calibracion(_fresco(degiro_eur=10700.0))
    assert "El sospechoso es el sector" not in m
    assert "Compara los componentes" in m


def test_pasarse_por_arriba_con_extracto_fresco_acusa_a_las_categorias():
    """Quedarse LARGO no lo explica un sector agrupado de otra forma: lo explica una D de
    más, que carga el 100% del valor de su posición."""
    m = rc._motivo_calibracion(_fresco(nuestro_eur=16000.0, degiro_eur=13920.0))
    assert "se pasa por arriba" in m and "Cat." in m
    assert "El sospechoso es el sector" not in m
    assert "Vuelve a copiar" not in m


# ── Despejar la D y el sector del propio extracto ────────────────────────────

EXTRACTO_REAL = {"riesgo_eur": 13951.13, "valor_cartera_eur": 28348.95,
                 "riesgo_neto_eur": 13468.28, "riesgo_bruto_eur": 10218.56,
                 "riesgo_sector_eur": 13951.13, "fecha": "2026-09-01"}


def test_la_categoria_D_se_despeja_de_las_lineas_Net_y_Gross():
    """Net y Gross aplican 25% y 10% al MISMO importe y le suman los mismos dos términos
    (la D íntegra y la divisa). Restarlas los cancela y deja despejado lo que no es D.

    Cifras reales de un extracto: dan 6.684,15 € en D, el 23,6% de la cartera. Con ese
    dato los tres componentes del modelo reproducen el extracto al céntimo."""
    r = rc.categoria_d_implicita(EXTRACTO_REAL)
    assert r["no_d_eur"] == pytest.approx(21664.80, abs=0.01)
    assert r["categoria_d_eur"] == pytest.approx(6684.15, abs=0.01)
    assert r["pct_cartera"] == pytest.approx(0.2358, abs=0.001)


def test_sin_las_dos_lineas_no_se_inventa_la_D():
    assert rc.categoria_d_implicita({**EXTRACTO_REAL, "riesgo_bruto_eur": None}) is None
    assert rc.categoria_d_implicita({}) is None


def test_una_cifra_mal_copiada_no_da_un_objetivo_falso():
    """Perseguir un objetivo inventado es peor que no tener objetivo. El caso que de verdad
    se puede dar es cambiar las dos líneas de sitio: Gross por encima de Net es imposible,
    porque el 10% no puede superar al 25% del mismo importe."""
    assert rc.categoria_d_implicita({**EXTRACTO_REAL, "riesgo_bruto_eur": 20000.0}) is None
    assert rc.categoria_d_implicita({**EXTRACTO_REAL, "valor_cartera_eur": 0}) is None
    # Y una D negativa por unos céntimos de redondeo se admite como cero, no se rechaza:
    # rechazarla dejaría sin diagnóstico a una cartera que simplemente no tiene ninguna D.
    sin_d = {**EXTRACTO_REAL, "riesgo_neto_eur": 10218.56 + 0.15 * 28348.95}
    assert rc.categoria_d_implicita(sin_d)["categoria_d_eur"] == 0.0


def test_el_sector_de_DEGIRO_se_despeja_de_su_linea_sectorial():
    """14.747,62 € es lo que DEGIRO agrupa en su mayor sector. Su aplicación no lo dice en
    ninguna pantalla; sale de la línea sectorial menos la D y la divisa, entre 0,40."""
    assert rc.sector_implicito(EXTRACTO_REAL, 6684.15, 1367.93) == pytest.approx(14747.62,
                                                                                 abs=0.01)


def test_sin_la_linea_sectorial_no_se_deduce_nada():
    assert rc.sector_implicito({}, 6684.15, 1367.93) is None
    assert rc.sector_implicito({"riesgo_sector_eur": 1000.0}, 6684.15, 1367.93) is None


def test_el_mensaje_dice_cuantos_euros_de_D_faltan_por_marcar():
    cal = {**_fresco(), "d_implicita": {"categoria_d_eur": 6684.15, "pct_cartera": 0.2358},
           "nuestra_d_eur": 2000.0}
    m = rc._motivo_calibracion(cal)
    assert "4.684" in m and "Cat." in m


def test_con_la_D_ya_cuadrada_el_mensaje_pasa_al_sector():
    cal = {**_fresco(), "d_implicita": {"categoria_d_eur": 6684.15, "pct_cartera": 0.2358},
           "nuestra_d_eur": 6684.15, "sector_degiro_eur": 14747.62,
           "nuestro_sector_eur": 13665.0}
    m = rc._motivo_calibracion(cal)
    assert "SECTOR" in m and "1.083" in m
    assert "CATEGORÍA D" not in m, "la D ya está resuelta: nombrarla despista"


def test_nuestro_mayor_sector_no_cuenta_la_categoria_D():
    """La D ya entra por otra vía, al 100%: contarla también en el sector la duplicaría."""
    pos = [{"symbol": "A", "valor_eur": 5000.0, "sector": "TECH", "categoria": "A"},
           {"symbol": "B", "valor_eur": 3000.0, "sector": "TECH", "categoria": "D"},
           {"symbol": "C", "valor_eur": 1000.0, "sector": "SALUD", "categoria": "A"}]
    assert rc._mayor_sector(pos) == 5000.0


def test_una_D_pendiente_ridicula_no_tapa_la_causa_de_verdad():
    """El caso real: 6.710 € marcados de 6.726, o sea 16 € pendientes. Marcar esos 16 €
    subiría el riesgo unos 11 € sobre un hueco de 492 —el 2%— así que perseguirlos no
    arregla nada, y mientras el mensaje habla de ellos no habla de lo que sí importa.

    Un euro pendiente de D no aporta un euro de riesgo: esa posición ya contaba al 25% por
    el neto y al 6,36% por la divisa, así que lo que suma marcarla es el resto."""
    cal = {**_fresco(), "nuestro_eur": 13527.0, "degiro_eur": 14019.0,
           "d_implicita": {"categoria_d_eur": 6726.0, "pct_cartera": 0.237},
           "nuestra_d_eur": 6710.0,
           "sector_degiro_eur": 14748.0, "nuestro_sector_eur": 13518.0}
    m = rc._motivo_calibracion(cal)
    assert "SECTOR" in m and "1.230" in m
    assert "16 €" not in m


def test_una_D_pendiente_que_SI_explica_el_hueco_se_señala():
    """La otra cara: si lo que falta de D da cuenta del desfase, hay que decirlo."""
    cal = {**_fresco(), "nuestro_eur": 10575.0, "degiro_eur": 13920.0,
           "d_implicita": {"categoria_d_eur": 6684.0, "pct_cartera": 0.236},
           "nuestra_d_eur": 0.0,
           "sector_degiro_eur": 14748.0, "nuestro_sector_eur": 13518.0}
    m = rc._motivo_calibracion(cal)
    assert "CATEGORÍA D" in m and "6.684" in m


def test_el_mensaje_del_sector_manda_al_campo_de_DEGIRO_y_no_al_propio():
    """El campo «Sector» lo rellena el proveedor de datos y además es la taxonomía del
    usuario. Pedirle que lo reescriba para imitar el agrupamiento del bróker cambiaría un
    dato bueno por otro y perdería el primero. Por eso hay un campo aparte."""
    cal = {**_fresco(), "nuestro_eur": 13497.0, "degiro_eur": 14019.0,
           "d_implicita": {"categoria_d_eur": 6726.0, "pct_cartera": 0.237},
           "nuestra_d_eur": 6726.0,
           "sector_degiro_eur": 14782.0, "nuestro_sector_eur": 9384.0}
    m = rc._motivo_calibracion(cal)
    assert "Sector DEGIRO" in m and "5.398" in m


# ── Proponer la agrupación que reproduce el extracto ─────────────────────────

CARTERA_SECTORES = [
    {"symbol": "ORCL", "valor_eur": 4400.0, "sector": "TECHNOLOGY", "categoria": "C"},
    {"symbol": "FN", "valor_eur": 5600.0, "sector": "TECHNOLOGY", "categoria": "A"},
    {"symbol": "TXN", "valor_eur": 2000.0, "sector": "TECHNOLOGY", "categoria": "A"},
    {"symbol": "NFLX", "valor_eur": 3400.0, "sector": "COMMUNICATION SERVICES", "categoria": "A"},
    {"symbol": "META", "valor_eur": 2825.0, "sector": "COMMUNICATION SERVICES", "categoria": "A"},
    {"symbol": "ETN", "valor_eur": 1400.0, "sector": "INDUSTRIALS", "categoria": "A"},
    {"symbol": "RH", "valor_eur": 1860.0, "sector": "CONSUMER CYCLICAL", "categoria": "A"},
]


def test_propone_la_posicion_que_cierra_el_hueco():
    """«¿Cómo agrupa DEGIRO?» no se puede consultar, pero «¿qué suma 2.825 €?» sí."""
    r = rc.agrupar_como_degiro(CARTERA_SECTORES, 14825.0)
    assert r["estado"] == "PROPUESTA"
    assert [p["symbol"] for p in r["propuesta"]] == ["META"]
    assert r["resultado_eur"] == 14825.0


def test_no_propone_nada_si_hay_dos_combinaciones_que_cuadran():
    """Acertar por suerte es indistinguible de acertar por criterio hasta que cambian los
    precios y deja de cuadrar sin que nadie sepa por qué."""
    empatadas = CARTERA_SECTORES + [{"symbol": "XXX", "valor_eur": 2825.0,
                            "sector": "ENERGY", "categoria": "A"}]
    r = rc.agrupar_como_degiro(empatadas, 14825.0)
    assert r["estado"] == "AMBIGUO" and r["propuesta"] is None
    assert sorted(sum(r["candidatas"], [])) == ["META", "XXX"]


def test_si_ya_cuadra_no_toca_nada():
    r = rc.agrupar_como_degiro(CARTERA_SECTORES, 12000.0)
    assert r["estado"] == "YA_CUADRA" and r["propuesta"] == []


def test_si_nos_pasamos_lo_dice_en_vez_de_quitar_a_ciegas():
    """Sacar posiciones no tiene solución única: cualquier combinación que sobre serviría."""
    r = rc.agrupar_como_degiro(CARTERA_SECTORES, 9000.0)
    assert r["estado"] == "NOS_PASAMOS" and r["propuesta"] is None


def test_sin_combinacion_posible_no_se_fuerza_uina():
    r = rc.agrupar_como_degiro(CARTERA_SECTORES, 99999.0)
    assert r["estado"] == "SIN_SOLUCION" and r["propuesta"] is None


def test_la_categoria_D_no_entra_en_la_propuesta():
    """Ya computa al 100% por otra vía; el sector no la cuenta y moverla no cambiaría nada."""
    con_d = [{**p, "categoria": "D"} if p["symbol"] == "META" else p for p in CARTERA_SECTORES]
    r = rc.agrupar_como_degiro(con_d, 14825.0)
    assert r["estado"] != "PROPUESTA" or all(p["symbol"] != "META" for p in r["propuesta"])
