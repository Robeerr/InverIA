"""Tests del lector del CSV de Transacciones de DEGIRO.

Los datos de abajo son filas REALES de una exportacion (08/2026), no inventadas. Importa
porque el formato tiene dos trampas que cambian los numeros sin dar error:

  · La coma es el separador DECIMAL. "214,2050" son 214,205 y no doscientos catorce mil.
  · Las comisiones vienen en EUROS aunque la operacion sea en dolares.

Ejecutar:  cd backend && pytest tests/test_degiro_csv.py -v
"""
import pytest

import degiro_csv


# Cabecera y filas tal como salen del fichero. Las columnas de divisa van sin nombre.
_CABECERA = ("Date,Time,Product,ISIN,Reference exchange,Venue,Quantity,Price,,"
             "Local value,,Value EUR,Exchange rate,AutoFX Fee,"
             "Transaction and/or third party fees,Total EUR,Order ID")

_FILAS = [
    # Venta de 5 SPACE EXPLORATION a 131,17 $ · cambio 1,1563 · comisiones 1,42 + 2,00 EUR
    '07-08-2026,21:55,SPACE EXPLORATION TECHNOLOGIES,US84615Q1031,NDQ,MSRP,-5,"131,1700",USD,'
    '"655,85",USD,"567,20","1,1563","-1,42","-2,00","563,78",08d08d3d-229b-4d9',
    # Venta de 3 FABRINET a 558,165 $
    '07-08-2026,21:34,FABRINET,KYG3323L1005,NSY,MSRP,-3,"558,1650",USD,'
    '"1674,50",USD,"1447,32","1,1570","-3,62","-2,00","1441,66",da95e5c5-7f0e',
    # Compra de 1 SANDISK a 1196,64 $
    '07-08-2026,16:42,SANDISK CORPORATION,US80004C2008,NDQ,SOHO,1,"1196,6400",USD,'
    '"-1196,64",USD,"-1035,52","1,1556","-2,59","-2,00","-1040,11",3afed157-37e1',
    # Compra de 5 SPACE EXPLORATION a 108,81 $
    '06-08-2026,18:35,SPACE EXPLORATION TECHNOLOGIES,US84615Q1031,NDQ,JNST,5,"108,8100",USD,'
    '"-544,05",USD,"-472,31","1,1519","-1,18","-2,00","-475,49",c34bbd56-09d5',
    # Venta de 10 MARVELL a 214,205 $  (la venta real de MRVL)
    '06-08-2026,18:09,MARVELL TECHNOLOGY,US5738741041,NDQ,CDED,-10,"214,2050",USD,'
    '"2142,05",USD,"1859,11","1,1522","-4,65","-2,00","1852,46",e7b777d4-c890',
]

_CSV = ("\n".join([_CABECERA] + _FILAS)).encode("utf-8")


@pytest.fixture
def leido():
    return degiro_csv.leer(_CSV)


# ── Lo esencial ──────────────────────────────────────────────────────────────

def test_se_leen_todas_las_operaciones(leido):
    assert len(leido["operaciones"]) == 5
    assert leido["errores"] == []


def test_la_coma_es_el_separador_decimal(leido):
    """La trampa del formato: abierto con una hoja de calculo inglesa, 214,2050 se ve como
    2.142.050. Tomarlo por bueno multiplicaria el precio por diez mil."""
    mrvl = [o for o in leido["operaciones"] if o["isin"] == "US5738741041"][0]
    assert mrvl["precio"] == pytest.approx(214.205)
    # Y cuadra con el importe del propio fichero: 2142,05 / 10 acciones.
    assert mrvl["precio"] * mrvl["acciones"] == pytest.approx(2142.05, abs=0.01)


def test_la_cantidad_negativa_es_una_venta(leido):
    """El signo del IMPORTE depende de si se mira desde la caja o desde la posicion; el de
    la cantidad no es ambiguo."""
    tipos = {o["isin"]: o["tipo"] for o in leido["operaciones"] if o["fecha"] == "2026-08-07"}
    assert tipos["US5738741041" if False else "US84615Q1031"] == "venta"
    compra = [o for o in leido["operaciones"] if o["isin"] == "US80004C2008"][0]
    assert compra["tipo"] == "compra" and compra["acciones"] == 1


def test_las_acciones_van_siempre_en_positivo(leido):
    assert all(o["acciones"] > 0 for o in leido["operaciones"])


def test_la_fecha_se_convierte_de_dia_mes_a_iso(leido):
    """07-08-2026 es 7 de AGOSTO. Confundir dia y mes cambiaria el tipo de cambio aplicado
    y, con el, los euros de la operacion."""
    assert leido["operaciones"][-1]["fecha"] == "2026-08-07"
    assert all(o["fecha"].startswith("2026-08-0") for o in leido["operaciones"])


# ── Tipo de cambio y comisiones ──────────────────────────────────────────────

def test_el_tipo_de_cambio_es_el_que_te_aplicaron(leido):
    """Deja de hacer falta estimarlo con el de mercado, que no es el que te cobraron."""
    spce = [o for o in leido["operaciones"]
            if o["isin"] == "US84615Q1031" and o["tipo"] == "venta"][0]
    assert spce["tasa"] == pytest.approx(1.1563)
    # El fichero dice 567,20 EUR para 655,85 USD: mismo convenio (divisa por 1 EUR).
    assert 655.85 / spce["tasa"] == pytest.approx(567.20, abs=0.01)


def test_las_comisiones_vienen_en_euros_y_se_pasan_a_la_divisa(leido):
    """Sumarlas tal cual a una operacion en dolares cobraria de menos: 3,42 EUR son 3,95 $."""
    spce = [o for o in leido["operaciones"]
            if o["isin"] == "US84615Q1031" and o["tipo"] == "venta"][0]
    # 1,42 de AutoFX + 2,00 de tramitacion = 3,42 EUR, a 1,1563
    assert spce["comision"] == pytest.approx(3.42 * 1.1563, abs=0.01)


def test_se_suman_las_dos_comisiones(leido):
    """AutoFX y tramitacion van en columnas distintas; quedarse con una deja fuera la mitad."""
    mrvl = [o for o in leido["operaciones"] if o["isin"] == "US5738741041"][0]
    assert mrvl["comision"] == pytest.approx((4.65 + 2.00) * 1.1522, abs=0.01)


def test_el_autofx_confirma_el_025_por_ciento():
    """Comprobacion cruzada de la tarifa que se venia estimando: 1,42 EUR sobre 567,20 EUR."""
    assert 1.42 / 567.20 == pytest.approx(0.0025, abs=0.0001)


# ── Identificacion y duplicados ──────────────────────────────────────────────

def test_se_listan_los_productos_para_emparejarlos(leido):
    """El fichero trae ISIN y nombre, no ticker: hay que emparejarlos con la Cartera."""
    isins = {p["isin"] for p in leido["productos"]}
    assert isins == {"US84615Q1031", "KYG3323L1005", "US80004C2008", "US5738741041"}
    spce = [p for p in leido["productos"] if p["isin"] == "US84615Q1031"][0]
    assert spce["operaciones"] == 2, "una compra y una venta"


def test_cada_operacion_lleva_huella_para_no_duplicar(leido):
    huellas = [o["huella"] for o in leido["operaciones"]]
    assert len(set(huellas)) == len(huellas)


def test_dos_ejecuciones_de_la_misma_orden_no_colisionan():
    """Una orden puede ejecutarse en varios trozos el mismo dia con el MISMO id: si la
    huella fuera solo el id, la segunda se tomaria por duplicada y se perderia."""
    filas = [
        '07-08-2026,10:00,X,US0000000001,NDQ,A,5,"100,0000",USD,"-500,00",USD,'
        '"-432,00","1,1563","-1,08","-2,00","-435,08",ORDEN-1',
        '07-08-2026,10:05,X,US0000000001,NDQ,A,5,"101,0000",USD,"-505,00",USD,'
        '"-436,00","1,1563","-1,09","-2,00","-439,09",ORDEN-1',
    ]
    r = degiro_csv.leer(("\n".join([_CABECERA] + filas)).encode())
    assert len(r["operaciones"]) == 2
    assert len({o["huella"] for o in r["operaciones"]}) == 2


# ── Robustez ─────────────────────────────────────────────────────────────────

def test_un_fichero_que_no_es_el_bueno_lo_dice():
    """Account.csv tiene otras columnas: mejor decirlo que importar medio fichero."""
    otro = b"Date,Time,Value date,Product,ISIN,Description,FX,Change,,Balance,,Order Id\n"
    r = degiro_csv.leer(otro)
    assert r["operaciones"] == []
    assert r["errores"] and "Transacciones" in r["errores"][0]


def test_las_filas_vacias_no_estorban():
    r = degiro_csv.leer(("\n".join([_CABECERA, "", _FILAS[0], ""])).encode())
    assert len(r["operaciones"]) == 1


def test_se_admite_punto_y_coma_como_separador():
    """DEGIRO exporta con uno u otro segun la configuracion."""
    cab = _CABECERA.replace(",", ";")
    fila = ('07-08-2026;21:55;MARVELL;US5738741041;NDQ;CDED;-10;214,2050;USD;'
            '2142,05;USD;1859,11;1,1522;-4,65;-2,00;1852,46;ID')
    r = degiro_csv.leer(("\n".join([cab, fila])).encode())
    assert len(r["operaciones"]) == 1
    assert r["operaciones"][0]["precio"] == pytest.approx(214.205)


def test_una_operacion_en_euros_no_lleva_conversion():
    fila = ('07-08-2026,10:00,IBERDROLA,ES0144580Y14,MAD,A,10,"12,5000",EUR,'
            '"-125,00",EUR,"-125,00","1,0000","0,00","-2,00","-127,00",ID')
    r = degiro_csv.leer(("\n".join([_CABECERA, fila])).encode())
    op = r["operaciones"][0]
    assert op["divisa"] == "EUR" and op["tasa"] == 1.0
    assert op["comision"] == pytest.approx(2.00)


def test_el_resumen_cuenta_compras_y_ventas(leido):
    r = degiro_csv.resumen(leido["operaciones"])
    assert r["total"] == 5 and r["compras"] == 2 and r["ventas"] == 3
    assert r["desde"] == "2026-08-06" and r["hasta"] == "2026-08-07"


@pytest.mark.parametrize("crudo,esperado", [
    ("214,2050", 214.205),
    ("1.234,56", 1234.56),      # miles con punto, decimal con coma
    ("1,234.56", 1234.56),      # al reves (exportacion en ingles)
    ("-2,00", -2.0),
    ("", None), ("-", None), (None, None), ("n/a", None),
])
def test_los_numeros_se_leen_bien(crudo, esperado):
    assert degiro_csv._numero(crudo) == (pytest.approx(esperado) if esperado is not None
                                         else None)


# ── Dividendos (Account.csv) ─────────────────────────────────────────────────
# Transactions.csv SOLO tiene compraventas. Los dividendos estan en el otro fichero, el de
# caja, y son dinero de verdad: en una cartera de varios anos explican buena parte de la
# diferencia entre lo que dice el broker y lo que sale de las operaciones.

_CAB_CUENTA = ("Date,Time,Value date,Product,ISIN,Description,FX,Change,,Balance,,Order Id")

_FILAS_CUENTA = [
    # Un dividendo de NextEra en dolares
    '15-06-2026,08:00,15-06-2026,NEXTERA ENERGY INC,US65339F1012,Dividendo,,USD,'
    '"12,50",USD,"1250,00",',
    # Su retencion en origen (el 15% de EE.UU.)
    '15-06-2026,08:00,15-06-2026,NEXTERA ENERGY INC,US65339F1012,'
    'Retención del impuesto sobre dividendo,,USD,"-1,88",USD,"1248,12",',
    # Un dividendo en euros
    '20-06-2026,08:00,20-06-2026,IBERDROLA SA,ES0144580Y14,Dividendo,,EUR,'
    '"31,00",EUR,"1279,12",',
    # Ruido que NO debe colarse: ya viene de Transactions.csv
    '07-08-2026,21:55,07-08-2026,SPACE EXPLORATION,US84615Q1031,Venta 5 Space Exploration,'
    ',USD,"655,85",USD,"655,85",08d08d',
    '07-08-2026,21:55,07-08-2026,SPACE EXPLORATION,US84615Q1031,'
    'Costes de transacción y/o externos de DEGIRO,,EUR,"-2,00",EUR,"-9951,43",',
]

_CSV_CUENTA = ("\n".join([_CAB_CUENTA] + _FILAS_CUENTA)).encode("utf-8")


def test_solo_se_cogen_los_dividendos_del_fichero_de_caja():
    """Las compras, ventas y comisiones ya vienen mejor de Transactions.csv: cogerlas
    tambien de aqui las duplicaria."""
    r = degiro_csv.leer_cuenta(_CSV_CUENTA)
    assert len(r["dividendos"]) == 3
    assert all(d["tipo"] in ("dividendo", "retencion") for d in r["dividendos"])


def test_la_retencion_se_distingue_del_dividendo():
    """Su descripcion CONTIENE la palabra "dividendo", asi que si se comprobara primero el
    dividendo todas las retenciones se tomarian por cobros y el neto saldria inflado."""
    r = degiro_csv.leer_cuenta(_CSV_CUENTA)
    tipos = [d["tipo"] for d in r["dividendos"] if d["isin"] == "US65339F1012"]
    assert sorted(tipos) == ["dividendo", "retencion"]


def test_la_retencion_conserva_su_signo_negativo():
    """Asi sumar dividendos y retenciones da el neto sin acordarse de restar."""
    r = degiro_csv.leer_cuenta(_CSV_CUENTA)
    nee = [d for d in r["dividendos"] if d["isin"] == "US65339F1012"]
    assert sum(d["importe"] for d in nee) == pytest.approx(10.62)   # 12,50 - 1,88


def test_se_lee_la_divisa_de_cada_dividendo():
    r = degiro_csv.leer_cuenta(_CSV_CUENTA)
    por_isin = {d["isin"]: d["divisa"] for d in r["dividendos"]}
    assert por_isin["US65339F1012"] == "USD"
    assert por_isin["ES0144580Y14"] == "EUR"


def test_cada_dividendo_lleva_huella_para_no_duplicar():
    r = degiro_csv.leer_cuenta(_CSV_CUENTA)
    huellas = [d["huella"] for d in r["dividendos"]]
    assert len(set(huellas)) == len(huellas)


def test_subir_el_fichero_de_transacciones_por_error_lo_dice():
    r = degiro_csv.leer_cuenta(_CSV.decode().encode())
    assert r["dividendos"] == []
    assert r["errores"] and "Cuenta" in r["errores"][0]


def test_el_resumen_separa_cobros_de_retenciones():
    r = degiro_csv.leer_cuenta(_CSV_CUENTA)
    res = degiro_csv.resumen_dividendos(r["dividendos"])
    assert res["cobros"] == 2 and res["retenciones"] == 1
    assert res["desde"] == "2026-06-15" and res["hasta"] == "2026-06-20"


def test_se_reconoce_el_fichero_en_ingles():
    """DEGIRO exporta en el idioma de la cuenta."""
    filas = ['15-06-2026,08:00,15-06-2026,APPLE INC,US0378331005,Dividend,,USD,'
             '"5,00",USD,"100,00",',
             '15-06-2026,08:00,15-06-2026,APPLE INC,US0378331005,Dividend Tax,,USD,'
             '"-0,75",USD,"99,25",']
    r = degiro_csv.leer_cuenta(("\n".join([_CAB_CUENTA] + filas)).encode())
    assert sorted(d["tipo"] for d in r["dividendos"]) == ["dividendo", "retencion"]


def test_dos_dividendos_identicos_el_mismo_dia_no_colisionan():
    """Un pago partido, o dos apuntes iguales el mismo dia. Sin distinguirlos, la huella
    colisiona, el segundo se toma por duplicado y ese dinero desaparece."""
    filas = ['15-06-2026,08:00,15-06-2026,NEE,US65339F1012,Dividendo,,USD,"12,50",USD,"1,00",',
             '15-06-2026,08:00,15-06-2026,NEE,US65339F1012,Dividendo,,USD,"12,50",USD,"1,00",']
    r = degiro_csv.leer_cuenta(("\n".join([_CAB_CUENTA] + filas)).encode())
    assert len(r["dividendos"]) == 2
    assert len({d["huella"] for d in r["dividendos"]}) == 2


def test_la_huella_es_estable_entre_exportaciones():
    """Si cambiara, reimportar duplicaria todo. El contador se apoya en el orden de las
    filas, que es el mismo cada vez que se exporta el mismo periodo."""
    a = degiro_csv.leer_cuenta(_CSV_CUENTA)["dividendos"]
    b = degiro_csv.leer_cuenta(_CSV_CUENTA)["dividendos"]
    assert [x["huella"] for x in a] == [x["huella"] for x in b]


def test_dos_ejecuciones_identicas_de_la_misma_orden_tienen_huellas_distintas():
    """DEGIRO parte una orden en varias ejecuciones y dos pueden ser IDÉNTICAS hasta en la
    hora y el nº de orden — pasó con 2×5 CRWV a 90,55 el mismo segundo (una con comisión y
    otra sin, pero la comisión no está en la huella). Sin contador, la segunda se pierde en
    silencio y la posición descuadra en exactamente esas acciones."""
    fila = ('03-09-2025,17:23,"COREWEAVE, INC. CLASS A",US21873S1087,NDQ,SOHO,5,'
            '"90,5500",USD,"-452,75",USD,"-387,66","1,1679","-0,97",{fee},'
            '"-388,63",51ad4a30-5811-4c41-a2df-9763dc2dc514')
    cabecera = ("Fecha,Hora,Producto,ISIN,Bolsa de,Centro de ejecución,Número,Precio,,"
                "Valor local,,Valor,Tipo de cambio,Tasa de cambio,"
                "Costes de transacción,Total,ID de orden")
    csv = "\n".join([cabecera, fila.format(fee=''), fila.format(fee='"-2,00"')])
    r = degiro_csv.leer(csv.encode())
    assert len(r["operaciones"]) == 2
    h1, h2 = (op["huella"] for op in r["operaciones"])
    assert h1 != h2
    # Y releer el MISMO fichero da las MISMAS huellas: es lo que evita duplicar al resubir.
    r2 = degiro_csv.leer(csv.encode())
    assert {op["huella"] for op in r2["operaciones"]} == {h1, h2}


def test_los_intereses_y_la_conectividad_se_clasifican_como_coste():
    """Son los costes que SOLO viven en el Account.csv y lo que separa el total propio del
    Total P/L del bróker, que sí los descuenta."""
    assert degiro_csv._clasificar("Interés") == "coste"
    assert degiro_csv._clasificar("Flatex Interest") == "coste"
    assert degiro_csv._clasificar("DEGIRO Costes de Conectividad con el Mercado 2025") == "coste"
    # Las comisiones de compraventa NO: ya vienen por operación en el Transactions.csv y
    # cogerlas también de aquí las contaría dos veces.
    assert degiro_csv._clasificar("Costes de transacción DEGIRO y/o costes de terceros") is None
    assert degiro_csv._clasificar("Dividendo") == "dividendo"


def test_una_fila_a_precio_cero_se_avisa_en_vez_de_desaparecer():
    """Ampliaciones liberadas, splits y entregas de derechos vienen a precio 0. Devolverlas
    como None las hacía desaparecer sin rastro ni en `errores`, y como las acciones SÍ
    entraban en el bróker, la venta posterior salía sin coste y su ingreso entero contaba
    como ganancia. Pasó con OHLA: 205 acciones vendidas sin compra registrada."""
    cabecera = ("Fecha,Hora,Producto,ISIN,Bolsa de,Centro de ejecución,Número,Precio,,"
                "Valor local,,Valor,Tipo de cambio,Tasa de cambio,"
                "Costes de transacción,Total,ID de orden")
    filas = [
        '14-01-2025,00:00,OBRASCON HUARTE LAIN SA,ES0642090932,MAD,,200,"0,0000",EUR,'
        '"0,00",EUR,"0,00",,"0,00",,"0,00",',
        '05-02-2025,10:05,OBRASCON HUARTE LAIN SA,ES0142090317,MAD,MESI,-200,"0,3610",EUR,'
        '"72,20",EUR,"72,20",,"0,00","-2,00","70,20",0e322f39',
    ]
    r = degiro_csv.leer("\n".join([cabecera] + filas).encode())
    assert len(r["operaciones"]) == 1               # solo la venta real
    assert len(r["errores"]) == 1                   # y la otra NO se calla
    assert "precio 0" in r["errores"][0]
    assert "200" in r["errores"][0]


def test_una_fila_de_cantidad_cero_sigue_siendo_ruido_silencioso():
    """Cabeceras repetidas y filas de resumen no son operaciones: esas sí se ignoran."""
    cabecera = ("Fecha,Hora,Producto,ISIN,Bolsa de,Centro de ejecución,Número,Precio,,"
                "Valor local,,Valor,Tipo de cambio,Tasa de cambio,"
                "Costes de transacción,Total,ID de orden")
    fila = ('14-01-2025,00:00,ALGO,ES0000000000,MAD,,0,"1,0000",EUR,"0,00",EUR,"0,00",,'
            '"0,00",,"0,00",')
    r = degiro_csv.leer("\n".join([cabecera, fila]).encode())
    assert r["operaciones"] == [] and r["errores"] == []
