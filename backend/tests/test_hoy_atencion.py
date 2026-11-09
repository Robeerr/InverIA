"""Las posiciones «en pérdidas» de la portada, en los dos métodos.

La tarjeta «Tu cartera» de Hoy enseña sus cifras por media ponderada cuando el usuario tiene
puesto «Como en DEGIRO», pero la lista de posiciones en pérdidas de debajo seguía en FIFO:
AAOI salía con −661,86 € en Hoy y −843,18 € en Operaciones. Estos tests fijan que cada
posición viaja con las cifras de los dos métodos, para que la pantalla elija las mismas
que usa en el resto de la tarjeta.
"""
from hoy import posiciones_en_perdidas


def _pos(sym, pct, pnl, pct_pond=None, pnl_pond=None, acciones=10):
    p = {"symbol": sym, "acciones": acciones, "pct": pct, "pnl_eur": pnl}
    if pct_pond is not None:
        p["ponderada"] = {"pct": pct_pond, "pnl_eur": pnl_pond}
    return p


def test_cada_posicion_lleva_las_cifras_de_los_dos_metodos():
    (aaoi,) = posiciones_en_perdidas({"AAOI": _pos("AAOI", -56.05, -661.86, -61.08, -843.18)})
    assert aaoi["pnl_eur"] == -661.86
    assert aaoi["ponderada"] == {"pct": -61.08, "pnl_eur": -843.18}


def test_entra_si_pierde_lo_bastante_en_cualquiera_de_los_dos_metodos():
    # −5 % por FIFO no llega al umbral, pero −9 % por media ponderada sí: con el
    # interruptor puesto el usuario la vería en pérdidas en Operaciones y no aquí.
    filas = posiciones_en_perdidas({"X": _pos("X", -5.0, -50.0, -9.0, -90.0)})
    assert [f["symbol"] for f in filas] == ["X"]


def test_no_entra_si_no_pierde_en_ninguno():
    assert posiciones_en_perdidas({"X": _pos("X", -3.0, -30.0, -4.0, -40.0)}) == []


def test_una_posicion_vendida_entera_no_pide_atencion():
    assert posiciones_en_perdidas({"X": _pos("X", -30.0, -300.0, acciones=0)}) == []


def test_sin_media_ponderada_sigue_funcionando_como_antes():
    (x,) = posiciones_en_perdidas({"X": _pos("X", -20.0, -200.0)})
    assert x["ponderada"] is None
    assert x["pct"] == -20.0


def test_ordenadas_de_peor_a_menos_mala():
    filas = posiciones_en_perdidas({"A": _pos("A", -10.0, -1.0), "B": _pos("B", -40.0, -4.0)})
    assert [f["symbol"] for f in filas] == ["B", "A"]


def test_el_tope_no_deja_fuera_una_posicion_en_perdidas_del_metodo_elegido():
    # Ocho posiciones que solo pierden mucho por media ponderada, y Z que pierde un 9 %
    # por los dos. Recortar por la peor de las dos cifras dejaba fuera a Z, y con el
    # método de gestión la tarjeta «En pérdidas» salía vacía.
    pos = {f"P{i}": _pos(f"P{i}", -5.0, -5.0, -30.0 - i, -30.0) for i in range(8)}
    pos["Z"] = _pos("Z", -9.0, -9.0, -9.0, -9.0)
    filas = posiciones_en_perdidas(pos, maximo=4)
    simbolos = {f["symbol"] for f in filas}
    assert "Z" in simbolos
    assert len(filas) <= 8
