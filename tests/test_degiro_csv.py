

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
