"""Tests del libro de operaciones (lotes.py).

Aquí no vale "parece razonable": son euros que van a una declaración de la renta. Cada
número esperado está calculado a mano en el propio test para que se pueda comprobar de un
vistazo sin fiarse de la implementación.

Ejecutar:  cd backend && pytest tests/test_lotes.py -v
"""
import pytest

import lotes


def _compra(fecha, acciones, precio, comision=0.0, tasa=None, nivel=None, orden="a"):
    c = lotes.nueva_compra("FN", acciones, precio, fecha=fecha, comision=comision,
                           tasa=tasa, nivel=nivel)
    c["created_at"] = f"{fecha}T00:00:0{orden}"   # desempate estable entre mismas fechas
    return c


def _venta(fecha, acciones, precio, comision=0.0, tasa=None):
    v = lotes.nueva_venta("FN", acciones, precio, fecha=fecha, comision=comision, tasa=tasa)
    v["created_at"] = f"{fecha}T12:00:00"
    return v


# ── El caso que motivó todo esto ─────────────────────────────────────────────
# "Tengo 5 acciones de FN y he vendido 1": 3 compradas a 80 y 2 a 120, vendo 1 a 130.
#   FIFO consume la de 80  -> 130 - 80  = +50  (+62,5%)
#   LIFO consume la de 120 -> 130 - 120 = +10  (+8,33%)
# Seis veces de diferencia sobre la MISMA operación: por eso se muestran las dos.

_COMPRAS_FN = [_compra("2026-01-10", 3, 80.0), _compra("2026-03-05", 2, 120.0)]


def test_fifo_consume_la_compra_mas_antigua():
    r = lotes.reproducir(_COMPRAS_FN, [_venta("2026-06-01", 1, 130.0)], lotes.FIFO)
    v = r["ventas"][0]
    assert v["coste_divisa"] == 80.0
    assert v["ganancia_divisa"] == 50.0
    assert v["pct"] == 62.5
    assert v["lotes"][0]["fecha_compra"] == "2026-01-10"


def test_lifo_consume_la_compra_mas_reciente():
    r = lotes.reproducir(_COMPRAS_FN, [_venta("2026-06-01", 1, 130.0)], lotes.LIFO)
    v = r["ventas"][0]
    assert v["coste_divisa"] == 120.0
    assert v["ganancia_divisa"] == 10.0
    assert round(v["pct"], 2) == 8.33
    assert v["lotes"][0]["fecha_compra"] == "2026-03-05"


def test_los_dos_metodos_se_devuelven_juntos_y_etiquetados():
    """Un numero suelto sin decir de que metodo es invita a meterlo en la declaracion."""
    comp = lotes.comparar_metodos(_COMPRAS_FN, [_venta("2026-06-01", 1, 130.0)])
    assert comp["oficial"] == lotes.FIFO
    assert comp["fifo"]["ventas"][0]["ganancia_divisa"] == 50.0
    assert comp["lifo"]["ventas"][0]["ganancia_divisa"] == 10.0
    assert not comp["coinciden"]
    assert "37.2" in comp["nota_fiscal"], "debe citar la norma que lo obliga"


def test_lo_que_queda_abierto_depende_del_metodo():
    """Tras vender parte, FIFO y LIFO dejan lotes DISTINTOS vivos, y por tanto un precio
    medio distinto. Es la consecuencia que se olvida al mirar solo la ganancia."""
    fifo = lotes.reproducir(_COMPRAS_FN, [_venta("2026-06-01", 1, 130.0)], lotes.FIFO)
    lifo = lotes.reproducir(_COMPRAS_FN, [_venta("2026-06-01", 1, 130.0)], lotes.LIFO)
    assert fifo["acciones_abiertas"] == lifo["acciones_abiertas"] == 4
    # FIFO deja 2@80 + 2@120 = 400 -> medio 100. LIFO deja 3@80 + 1@120 = 360 -> medio 90.
    assert fifo["precio_medio"] == 100.0
    assert lifo["precio_medio"] == 90.0


# ── Ventas que cruzan varios lotes ───────────────────────────────────────────

def test_una_venta_puede_consumir_varios_lotes():
    r = lotes.reproducir(_COMPRAS_FN, [_venta("2026-06-01", 4, 130.0)], lotes.FIFO)
    v = r["ventas"][0]
    # 3@80 + 1@120 = 360 de coste; ingreso 4*130 = 520 -> +160
    assert v["coste_divisa"] == 360.0
    assert v["ganancia_divisa"] == 160.0
    assert len(v["lotes"]) == 2
    assert r["acciones_abiertas"] == 1


def test_vender_la_posicion_entera_la_deja_a_cero():
    r = lotes.reproducir(_COMPRAS_FN, [_venta("2026-06-01", 5, 130.0)], lotes.FIFO)
    assert r["acciones_abiertas"] == 0
    assert r["abiertos"] == []
    assert r["precio_medio"] is None
    # 240 + 240 = 480 de coste; 650 de ingreso -> +170
    assert r["ventas"][0]["ganancia_divisa"] == 170.0


def test_varias_ventas_seguidas_no_reutilizan_el_mismo_lote():
    """El fallo clasico de un emparejador: cada venta vuelve a mirar los lotes originales
    y consume dos veces las mismas acciones, inflando la ganancia."""
    ventas = [_venta("2026-06-01", 2, 130.0), _venta("2026-07-01", 2, 140.0)]
    r = lotes.reproducir(_COMPRAS_FN, ventas, lotes.FIFO)
    assert r["acciones_abiertas"] == 1
    # 1ª: 2@80 = 160 -> 260-160 = +100. 2ª: 1@80 + 1@120 = 200 -> 280-200 = +80
    assert r["ventas"][0]["ganancia_divisa"] == 100.0
    assert r["ventas"][1]["ganancia_divisa"] == 80.0
    assert r["ganancia_realizada_divisa"] == 180.0


def test_una_venta_no_puede_consumir_compras_posteriores():
    """Vender en marzo no puede gastar acciones compradas en junio: daria una ganancia
    imposible y ademas dejaria la posicion descuadrada."""
    r = lotes.reproducir(_COMPRAS_FN, [_venta("2026-02-01", 1, 130.0)], lotes.FIFO)
    v = r["ventas"][0]
    assert v["lotes"][0]["fecha_compra"] == "2026-01-10"   # la de marzo aun no existia
    assert v["sin_cubrir"] == 0


def test_vender_mas_de_lo_comprado_se_avisa_en_vez_de_fallar():
    """Puede ser simplemente que falte meter una compra vieja. Mejor ensenar el descuadre
    que negarse a registrar la venta y perder el dato."""
    r = lotes.reproducir(_COMPRAS_FN, [_venta("2026-06-01", 8, 130.0)], lotes.FIFO)
    assert r["ventas"][0]["sin_cubrir"] == 3
    assert r["acciones_sin_cubrir"] == 3
    assert r["acciones_abiertas"] == 0


# ── Comisiones ───────────────────────────────────────────────────────────────

def test_las_comisiones_suman_al_coste_y_restan_del_ingreso():
    """Es como se calcula la ganancia patrimonial de verdad. Sin ellas el numero sale
    inflado y nunca cuadra con el broker."""
    compras = [_compra("2026-01-10", 10, 100.0, comision=2.0)]
    r = lotes.reproducir(compras, [_venta("2026-06-01", 10, 110.0, comision=3.0)], lotes.FIFO)
    v = r["ventas"][0]
    assert v["coste_divisa"] == 1002.0          # 1000 + 2
    assert v["ingreso_divisa"] == 1097.0        # 1100 - 3
    assert v["ganancia_divisa"] == 95.0         # y no 100
    assert v["comisiones_totales"] == 5.0


def test_la_comision_de_compra_se_reparte_al_vender_solo_una_parte():
    """Vender la mitad debe cargar la mitad de la comision de compra, no toda ni ninguna."""
    compras = [_compra("2026-01-10", 10, 100.0, comision=2.0)]
    r = lotes.reproducir(compras, [_venta("2026-06-01", 5, 110.0, comision=1.0)], lotes.FIFO)
    v = r["ventas"][0]
    assert v["coste_divisa"] == 501.0           # 500 + 1 (la mitad de los 2)
    assert v["ganancia_divisa"] == 48.0         # 549 - 501
    # Y la mitad de la comisión sigue viva en el lote abierto.
    assert r["coste_abierto_divisa"] == 501.0


# ── Euros ────────────────────────────────────────────────────────────────────
# Convenio: la tasa es divisa por 1 EUR (1,10 = un euro son 1,10 dolares). Se DIVIDE.

def test_la_ganancia_en_euros_usa_el_cambio_de_cada_fecha():
    """Ganar en dolares y ganar menos en euros es real: si el euro se fortalece, cada dolar
    que recuperas vale menos euros que los que pusiste."""
    compras = [_compra("2026-01-10", 10, 100.0, tasa=1.00)]   # 1000 $ = 1000 €
    ventas = [_venta("2026-06-01", 10, 110.0, tasa=1.10)]     # 1100 $ = 1000 €
    r = lotes.reproducir(compras, ventas, lotes.FIFO)
    v = r["ventas"][0]
    assert v["ganancia_divisa"] == 100.0    # +100 $
    assert v["ganancia_eur"] == 0.0         # y 0 € : el euro se comio la subida
    assert v["exacto"] is True


def test_se_dice_cuanto_de_la_diferencia_es_el_euro():
    compras = [_compra("2026-01-10", 10, 100.0, tasa=1.00)]
    ventas = [_venta("2026-06-01", 10, 110.0, tasa=1.10)]
    v = lotes.reproducir(compras, ventas, lotes.FIFO)["ventas"][0]
    # Sin efecto divisa la ganancia habria sido 100/1,10 = 90,91 €. Real: 0 €.
    assert v["efecto_divisa_eur"] == pytest.approx(-90.91, abs=0.01)


def test_sin_tipo_de_cambio_no_se_inventa_una_cifra_en_euros():
    """Un numero aproximado sin avisar es peor que no darlo: acaba en una declaracion."""
    compras = [_compra("2026-01-10", 10, 100.0, tasa=None)]
    ventas = [_venta("2026-06-01", 10, 110.0, tasa=1.10)]
    v = lotes.reproducir(compras, ventas, lotes.FIFO)["ventas"][0]
    assert v["ganancia_eur"] is None
    assert v["exacto"] is False
    assert v["ganancia_divisa"] == 100.0, "lo que SI se sabe debe seguir estando"


def test_el_porcentaje_en_euros_es_distinto_del_de_dolares():
    compras = [_compra("2026-01-10", 10, 100.0, tasa=1.00)]
    ventas = [_venta("2026-06-01", 10, 130.0, tasa=1.20)]
    v = lotes.reproducir(compras, ventas, lotes.FIFO)["ventas"][0]
    assert v["pct"] == 30.0                                  # +30% en dolares
    # 1300/1,20 = 1083,33 € contra 1000 € -> +8,33%
    assert v["pct_eur"] == pytest.approx(8.33, abs=0.01)


# ── Ganancia latente (la Cartera) ────────────────────────────────────────────

def test_la_ganancia_latente_va_en_euros_al_cambio_de_hoy():
    compras = [_compra("2026-01-10", 10, 100.0, tasa=1.00)]   # coste 1000 €
    estado = lotes.reproducir(compras, [], lotes.FIFO)
    val = lotes.valorar_abierto(estado, precio_actual=120.0, tasa_hoy=1.20)
    assert val["valor_divisa"] == 1200.0
    assert val["pnl_divisa"] == 200.0        # +200 $
    assert val["valor_eur"] == 1000.0        # 1200/1,20
    assert val["pnl_eur"] == 0.0             # 0 € : el euro se lo comio


def test_sin_posicion_abierta_no_hay_latente():
    estado = lotes.reproducir(_COMPRAS_FN, [_venta("2026-06-01", 5, 130.0)], lotes.FIFO)
    val = lotes.valorar_abierto(estado, precio_actual=200.0, tasa_hoy=1.10)
    assert val["acciones"] == 0 and val["pnl_eur"] is None


def test_un_precio_actual_ausente_no_rompe_la_cartera():
    estado = lotes.reproducir(_COMPRAS_FN, [], lotes.FIFO)
    for malo in (None, "", "n/d"):
        val = lotes.valorar_abierto(estado, precio_actual=malo, tasa_hoy=1.1)
        assert val["pnl_eur"] is None


# ── Detección del nivel de compra ────────────────────────────────────────────

_ENTRY = {"symbol": "FN", "deseado": 250.0, "nivel1": 220.0, "nivel2": 200.0,
          "nivel3": 180.0, "nivel4": 160.0, "nivel5": None}


def test_una_compra_en_un_nivel_se_reconoce():
    d = lotes.detectar_nivel(180.0, _ENTRY)
    assert d["nivel"] == "nivel3"
    assert d["nivel_etiqueta"] == "Nivel 3"
    assert d["desvio_pct"] == 0.0


def test_se_admite_el_hueco_normal_entre_la_orden_y_la_ejecucion():
    d = lotes.detectar_nivel(179.5, _ENTRY)       # -0,28%
    assert d["nivel"] == "nivel3"
    assert d["desvio_pct"] == pytest.approx(-0.28, abs=0.01)


def test_una_compra_lejos_de_todo_no_se_atribuye_a_ningun_nivel():
    """Inventar un nivel es peor que dejarlo en blanco: falsea el historial de que los
    niveles funcionan."""
    assert lotes.detectar_nivel(195.0, _ENTRY)["nivel"] is None


def test_con_niveles_juntos_gana_el_mas_cercano():
    """Con 180 y 178, el primero que cumpla la tolerancia puede no ser el que se toco."""
    entry = {"nivel1": 180.0, "nivel2": 178.0}
    assert lotes.detectar_nivel(178.2, entry)["nivel"] == "nivel2"
    assert lotes.detectar_nivel(179.9, entry)["nivel"] == "nivel1"


def test_los_niveles_vacios_no_estorban():
    assert lotes.detectar_nivel(100.0, {"nivel1": None, "nivel2": 0, "nivel3": ""})["nivel"] is None
    assert lotes.detectar_nivel(100.0, {})["nivel"] is None
    assert lotes.detectar_nivel(None, _ENTRY)["nivel"] is None


# ── Validación de entrada ────────────────────────────────────────────────────

@pytest.mark.parametrize("acciones,precio", [(0, 100), (-1, 100), (5, 0), (5, -10)])
def test_no_se_admiten_operaciones_imposibles(acciones, precio):
    with pytest.raises(ValueError):
        lotes.nueva_compra("FN", acciones, precio)
    with pytest.raises(ValueError):
        lotes.nueva_venta("FN", acciones, precio)


def test_no_se_admite_una_comision_negativa():
    with pytest.raises(ValueError):
        lotes.nueva_compra("FN", 1, 100, comision=-1)


def test_el_metodo_desconocido_falla_claro():
    with pytest.raises(ValueError):
        lotes.reproducir([], [], "PROMEDIO")


# ── Estabilidad ──────────────────────────────────────────────────────────────

def test_dos_compras_del_mismo_dia_dan_siempre_el_mismo_resultado():
    """Sin desempate estable, una cifra que baila entre recargas de pagina no vale nada."""
    compras = [_compra("2026-01-10", 1, 100.0, orden="1"),
               _compra("2026-01-10", 1, 200.0, orden="2")]
    for _ in range(5):
        r = lotes.reproducir(list(reversed(compras)), [_venta("2026-06-01", 1, 300.0)],
                             lotes.FIFO)
        assert r["ventas"][0]["coste_divisa"] == 100.0


def test_reproducir_no_modifica_lo_que_recibe():
    """El libro es la verdad: si reproducirlo lo altera, el segundo calculo miente."""
    compras = [_compra("2026-01-10", 3, 80.0)]
    ventas = [_venta("2026-06-01", 1, 130.0)]
    copia_c = [dict(c) for c in compras]
    lotes.reproducir(compras, ventas, lotes.FIFO)
    lotes.reproducir(compras, ventas, lotes.LIFO)
    assert compras == copia_c
    assert all("_libres" not in c for c in compras)


def test_sin_tipos_de_cambio_el_total_en_euros_es_desconocido_y_no_cero():
    """Un 0 se lee como "no has ganado nada", que es una afirmacion; lo cierto es que no se
    sabe. Ademas hacia que FIFO y LIFO, con resultados distintos, parecieran identicos."""
    r = lotes.reproducir(_COMPRAS_FN, [_venta("2026-06-01", 1, 130.0)], lotes.FIFO)
    assert r["ganancia_realizada_eur"] is None
    assert r["ganancia_realizada_divisa"] == 50.0
    assert r["todo_exacto"] is False


def test_la_diferencia_entre_metodos_se_ve_aunque_falten_los_cambios():
    comp = lotes.comparar_metodos(_COMPRAS_FN, [_venta("2026-06-01", 1, 130.0)])
    assert comp["diferencia_divisa"] == 40.0     # 50 - 10
    assert comp["diferencia_eur"] is None
    assert not comp["coinciden"]


def test_cuando_hay_un_solo_lote_los_dos_metodos_coinciden():
    compras = [_compra("2026-01-10", 10, 100.0, tasa=1.1)]
    comp = lotes.comparar_metodos(compras, [_venta("2026-06-01", 5, 120.0, tasa=1.1)])
    assert comp["coinciden"]
    assert comp["diferencia_divisa"] == 0.0


# ── Reconstruir los lotes desde las campanitas ───────────────────────────────
# Convenio de la Cartera: la campanita de un nivel de compra se APAGA cuando ese nivel ya
# se ha comprado. Eso convierte un ajuste de interfaz en el unico registro que existe de en
# que niveles se entro, y permite reconstruir los lotes en vez de guardar un precio medio.

def _pos(acciones, compra, **niveles):
    """Posicion de Cartera. `n1=(220, False)` = Nivel 1 a 220 con la campanita APAGADA."""
    e = {"symbol": "FN", "acciones": acciones, "compra": compra}
    for k, (precio, alerta) in niveles.items():
        i = k[1:]
        e[f"nivel{i}"] = precio
        e[f"alert_nivel{i}"] = alerta
    return e


def test_la_campanita_apagada_marca_el_nivel_como_comprado():
    e = _pos(10, 100, n1=(220.0, False), n2=(200.0, True), n3=(180.0, False))
    comprados = [n["nivel"] for n in lotes.niveles_comprados(e)]
    assert comprados == ["nivel1", "nivel3"], "solo los apagados, de mas caro a mas barato"


def test_una_campanita_que_nunca_se_toco_no_cuenta_como_comprada():
    """None significa "sin tocar", que no es lo mismo que apagada a proposito."""
    e = {"symbol": "FN", "nivel1": 220.0, "alert_nivel1": None, "nivel2": 200.0}
    assert lotes.niveles_comprados(e) == []


def test_con_dos_niveles_comprados_el_reparto_es_EXACTO():
    """Dos incognitas (las acciones de cada nivel) y dos datos (total y precio medio):
    solucion unica. No es una estimacion."""
    # 3 acciones a 200 + 7 a 100 = 1300 sobre 10 -> precio medio 130.
    e = _pos(10, 130.0, n1=(200.0, False), n2=(100.0, False))
    plan = lotes.plan_importacion(e)
    assert plan["exacto"] is True
    assert len(plan["lotes"]) == 2
    a, b = plan["lotes"]
    assert a["nivel"] == "nivel1" and a["acciones"] == 3.0 and a["precio"] == 200.0
    assert b["nivel"] == "nivel2" and b["acciones"] == 7.0 and b["precio"] == 100.0
    # Y el reparto reproduce el precio medio del que se partio.
    coste = sum(l["acciones"] * l["precio"] for l in plan["lotes"])
    assert coste / 10 == pytest.approx(130.0)


def test_con_un_solo_nivel_va_todo_ahi_al_precio_medio():
    """Se usa el precio MEDIO y no el del nivel: la ejecucion real casi nunca cae justo
    en el nivel, y el medio es el coste que de verdad se pago."""
    e = _pos(10, 178.5, n3=(180.0, False))
    plan = lotes.plan_importacion(e)
    assert plan["exacto"] is True
    assert plan["lotes"] == [{"nivel": "nivel3", "nivel_etiqueta": "Nivel 3",
                              "acciones": 10.0, "precio": 178.5}]


def test_con_tres_o_mas_niveles_se_estima_y_se_dice():
    """Hay varios repartos que dan el mismo precio medio. Presentar uno como si fuera EL
    bueno falsearia la ganancia de cada venta futura, asi que se marca como no exacto."""
    e = _pos(9, 200.0, n1=(220.0, False), n2=(200.0, False), n3=(180.0, False))
    plan = lotes.plan_importacion(e)
    assert plan["exacto"] is False
    assert len(plan["lotes"]) == 3
    # Aqui el medio real (200) coincide con la media de los niveles, asi que el reparto mas
    # equilibrado que la reproduce ES el equitativo.
    assert all(l["acciones"] == pytest.approx(3.0) for l in plan["lotes"])
    assert "Revisalo" in plan["motivo"].replace("í", "i")


def test_si_el_precio_medio_no_encaja_entre_los_niveles_se_dice(monkeypatch):
    """Puede pasar con una comision grande o un nivel editado despues de comprar. Un
    reparto con acciones negativas seria peor que admitir que no se puede."""
    e = _pos(10, 300.0, n1=(200.0, False), n2=(100.0, False))   # medio fuera del rango
    plan = lotes.plan_importacion(e)
    assert plan["exacto"] is False
    assert len(plan["lotes"]) == 1
    assert "no queda entre" in plan["motivo"]


def test_sin_campanitas_apagadas_se_cae_al_precio_medio():
    e = _pos(10, 130.0, n1=(200.0, True), n2=(100.0, True))
    plan = lotes.plan_importacion(e)
    assert plan["exacto"] is True and len(plan["lotes"]) == 1
    assert plan["lotes"][0]["nivel"] is None


def test_una_posicion_sin_datos_no_propone_nada():
    assert lotes.plan_importacion({"symbol": "FN"})["lotes"] == []
    assert lotes.plan_importacion({"symbol": "FN", "acciones": 10})["lotes"] == []


def test_el_nivel_deseado_no_cuenta_como_compra():
    """En esta Cartera la columna se llama "Deseado / Venta": es objetivo de VENTA."""
    e = {"symbol": "FN", "acciones": 10, "compra": 130.0,
         "deseado": 250.0, "alert_deseado": False,
         "nivel1": 200.0, "alert_nivel1": False, "nivel2": 100.0, "alert_nivel2": False}
    assert [n["nivel"] for n in lotes.niveles_comprados(e)] == ["nivel1", "nivel2"]


# ── Las campanitas se mueven solas ───────────────────────────────────────────
# Convenio en los DOS sentidos: apagada mientras queden acciones de ese nivel, encendida en
# cuanto se vende la ultima. Un nivel libre vuelve a ser un aviso util — es un sitio donde
# volverias a entrar — y dejarlo apagado silencia justo esa senal.

def _abierto(nivel, acciones):
    return {"nivel": nivel, "acciones_abiertas": acciones}


def test_al_vender_un_nivel_entero_se_enciende_su_campanita():
    entry = {"alert_nivel1": False, "alert_nivel2": False}
    compras = [{"nivel": "nivel1"}, {"nivel": "nivel2"}]
    abiertos = [_abierto("nivel2", 5)]          # del nivel1 no queda nada
    assert lotes.estado_niveles(entry, compras, abiertos) == {"alert_nivel1": True}


def test_vender_solo_una_parte_del_nivel_no_lo_enciende():
    """Sigue comprado: encenderlo avisaria de entrar donde ya estas."""
    entry = {"alert_nivel1": False}
    compras = [{"nivel": "nivel1"}]
    assert lotes.estado_niveles(entry, compras, [_abierto("nivel1", 2)]) == {}


def test_al_comprar_en_un_nivel_se_apaga_su_campanita():
    """El mismo convenio al reves. Si al comprar hubiera que apagarla a mano, una campanita
    encendida podria significar dos cosas y eso es peor que no automatizar nada."""
    entry = {"alert_nivel3": True}
    compras = [{"nivel": "nivel3"}]
    assert lotes.estado_niveles(entry, compras, [_abierto("nivel3", 4)]) == {"alert_nivel3": False}


def test_un_nivel_que_nunca_se_compro_no_se_toca():
    """Su campanita la has puesto tu a mano: pisarla seria deshacer algo deliberado."""
    entry = {"alert_nivel1": False, "alert_nivel4": False}
    compras = [{"nivel": "nivel1"}]                    # nivel4 no aparece en el libro
    cambios = lotes.estado_niveles(entry, compras, [_abierto("nivel1", 3)])
    assert "alert_nivel4" not in cambios


def test_solo_se_devuelve_lo_que_cambia():
    """Reescribir lo que ya esta bien genera escrituras y ruido para nada."""
    entry = {"alert_nivel1": False}
    compras = [{"nivel": "nivel1"}]
    assert lotes.estado_niveles(entry, compras, [_abierto("nivel1", 3)]) == {}


def test_dos_compras_en_el_mismo_nivel_cuentan_juntas():
    """Se puede entrar dos veces al mismo nivel en fechas distintas. Mientras quede algo de
    cualquiera de las dos, el nivel sigue comprado."""
    entry = {"alert_nivel2": False}
    compras = [{"nivel": "nivel2"}, {"nivel": "nivel2"}]
    abiertos = [_abierto("nivel2", 0), _abierto("nivel2", 1)]
    assert lotes.estado_niveles(entry, compras, abiertos) == {}


def test_las_compras_fuera_de_niveles_no_encienden_nada():
    entry = {"alert_nivel1": True}
    compras = [{"nivel": None}]
    assert lotes.estado_niveles(entry, compras, []) == {}


def test_con_tres_o_mas_niveles_el_reparto_reproduce_tu_precio_medio():
    """El fallo que se vio en produccion: repartir a partes iguales daba el coste de la
    media de los NIVELES (166,20 $) en vez del que se pago de verdad (142,43 $). El total de
    acciones y el precio medio son datos ciertos; un reparto que no los reproduce esta mal."""
    e = _pos(30, 142.43, n1=(200.0, False), n2=(170.0, False), n3=(150.0, False),
             n4=(140.0, False), n5=(120.0, False))
    plan = lotes.plan_importacion(e)
    assert len(plan["lotes"]) == 5
    acciones = sum(l["acciones"] for l in plan["lotes"])
    coste = sum(l["acciones"] * l["precio"] for l in plan["lotes"])
    assert acciones == pytest.approx(30.0), "el total de acciones no puede cambiar"
    assert coste / acciones == pytest.approx(142.43, abs=0.01), "debe cuadrar tu medio"


def test_el_reparto_carga_mas_donde_compraste_mas_barato():
    """Si tu medio esta por debajo de la media de los niveles, es que compraste mas abajo."""
    e = _pos(30, 130.0, n1=(200.0, False), n2=(150.0, False), n3=(100.0, False))
    plan = lotes.plan_importacion(e)
    por_precio = {l["precio"]: l["acciones"] for l in plan["lotes"]}
    assert por_precio[100.0] > por_precio[200.0]


def test_si_la_media_es_inalcanzable_se_dice_en_vez_de_colar_negativos():
    """Un reparto con acciones negativas es imposible; mejor admitirlo."""
    e = _pos(10, 500.0, n1=(200.0, False), n2=(150.0, False), n3=(100.0, False))
    plan = lotes.plan_importacion(e)
    assert all(l["acciones"] > 0 for l in plan["lotes"])
    assert "no se puede llegar a" in plan["motivo"]


def test_el_reparto_de_tres_o_mas_sigue_marcado_como_no_exacto():
    """Reproduce tu media, pero no es el unico reparto que lo hace: sigue habiendo que
    revisarlo, y decir 'exacto' invitaria a no hacerlo."""
    e = _pos(30, 142.43, n1=(200.0, False), n2=(150.0, False), n3=(100.0, False))
    assert lotes.plan_importacion(e)["exacto"] is False
