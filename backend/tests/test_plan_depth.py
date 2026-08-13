"""Tests de la profundidad máxima del plan de compra.

Caso real que lo motivó (MRVL, 27/07/2026, precio $186.38): el motor cogía los 3 primeros
niveles de confluencia sin mirar la profundidad, y salían a -3,8%, -13,1% y -46,5%. Como el
stop va por debajo de TODAS las entradas del plan, acababa en $78.95: un -57,7%. Eso no es un
stop, es perder media posición antes de reaccionar.

Ejecutar:  cd backend && pytest tests/ -v
"""
import os
import re

import pytest

_RUTA = os.path.join(os.path.dirname(__file__), "..", "server.py")

# Niveles reales que devolvió el motor para MRVL, con el precio de aquella sesión.
MRVL_PRECIO = 186.38
MRVL_NIVELES = [178.95, 161.80, 99.64, 85.85, 79.48, 69.56]


def _fuente():
    with open(_RUTA, encoding="utf-8") as fh:
        return fh.read()


def _filtrar(precio, niveles, max_depth):
    """Réplica del filtro de _deterministic_levels. Se replica en vez de importar server
    porque importarlo arrastra FastAPI, Mongo y todo el stack."""
    suelo = precio * (1 - max_depth)
    return [p for p in niveles if p >= suelo][:3]


def test_max_plan_depth_declarado_y_es_30_por_ciento():
    m = re.search(r'MAX_PLAN_DEPTH = float\(os\.environ\.get\("MAX_PLAN_DEPTH", "([\d.]+)"\)\)',
                  _fuente())
    assert m, "server.py ya no define MAX_PLAN_DEPTH"
    assert float(m.group(1)) == 0.30


def test_mrvl_excluye_el_nivel_de_menos_46_por_ciento():
    """El caso que destapó el fallo: el tercer nivel estaba a -46,5% y arrastraba el stop."""
    plan = _filtrar(MRVL_PRECIO, MRVL_NIVELES, 0.30)
    assert plan == [178.95, 161.80], f"el plan debería quedarse en 2 zonas, quedó {plan}"
    assert 99.64 not in plan


def test_el_stop_resultante_es_operativo():
    """Con el filtro, el stop cae en un rango usable en vez del -57,7% de antes."""
    plan = _filtrar(MRVL_PRECIO, MRVL_NIVELES, 0.30)
    deepest = min(plan)
    for atr in (6, 9, 12):
        stop = deepest - max(1.0 * atr, deepest * 0.015)
        caida = (stop / MRVL_PRECIO - 1) * 100
        assert -25 < caida < -15, f"con ATR={atr} el stop queda a {caida:.1f}%, fuera de rango"


def test_sin_filtro_el_stop_era_absurdo():
    """Documenta el comportamiento viejo, para que se vea por qué existe el filtro."""
    plan_viejo = MRVL_NIVELES[:3]          # lo que se hacía antes: los 3 primeros a pelo
    deepest = min(plan_viejo)              # 99.64
    stop = deepest - max(9.0, deepest * 0.015)
    assert (stop / MRVL_PRECIO - 1) * 100 < -50, "el caso viejo debería dar un stop atroz"


@pytest.mark.parametrize("max_depth,esperadas", [
    (0.10, 1),   # suelo 167,74 → solo el de -4,0%
    (0.20, 2),   # suelo 149,10 → -4,0% y -13,2% (el de -13,2% SÍ entra en un umbral del 20%)
    (0.30, 2),   # suelo 130,47 → los mismos dos
    (0.50, 3),   # suelo  93,19 → entra también el de -46,5%
])
def test_el_umbral_es_configurable(max_depth, esperadas):
    assert len(_filtrar(MRVL_PRECIO, MRVL_NIVELES, max_depth)) == esperadas


def test_hay_respaldo_si_ninguna_zona_pasa_el_filtro():
    """Si la acción ha subido tanto que no hay soporte dentro del suelo, no se devuelve None:
    se conserva la zona menos profunda para seguir dando un plan coherente."""
    src = _fuente()
    assert "Nos quedamos con la MENOS profunda" in src, (
        "Se ha perdido el respaldo: sin él, una acción disparada cae al flujo clásico, "
        "donde los números los inventa la IA."
    )


# ── La cuenta de la nota del plan ────────────────────────────────────────────
# Decia «el plan usa 3 de las 5 zonas» habiendo SEIS. Sumaba `len(ez) + descartadas`,
# donde `descartadas` son solo las que caen por PROFUNDIDAD, e ignoraba las que quedan
# fuera por el tope de tres escalones. Con FORM a $112.47, el NIVEL 4 —a -19,5%, dentro
# del 30%— no lo contaba nadie.
#
# Ademas la frase atribuia a la profundidad todas las exclusiones, cuando hay dos motivos.

FORM_PRECIO = 112.47
FORM_NIVELES = [110.84, 102.74, 95.55, 90.55, 70.24, 55.40]


def _sin_comentarios(src):
    """El codigo sin sus comentarios. Hace falta porque el comentario que explica POR QUE
    la cuenta vieja estaba mal la menciona, y buscarla sobre el fichero entero la daria
    por vigente. Lo que se protege es lo que se ejecuta."""
    return "\n".join(l.split("#")[0] for l in src.splitlines())


def _cuerpo_plan_nota():
    """El bloque que redacta la nota, ENTERO: las dos ramas.

    Acota desde el recuento hasta `entry_hi`, que es la primera linea del calculo. Si
    alguien sacara la rama de respaldo fuera de ese tramo, los tests de texto seguirian
    pasando sobre media funcion sin que nada avisara — por eso hay un test que comprueba
    que las dos ramas caen dentro."""
    src = _fuente()
    ini = src.index("con_precio = [z for z in buy_levels")
    return src[ini:src.index("entry_hi", ini)]


def test_el_acotador_abarca_las_dos_ramas():
    """Protege a los demas tests de este fichero: si el acotador se quedara corto,
    dejarian de mirar lo que creen que miran."""
    cuerpo = _cuerpo_plan_nota()
    assert "if respaldo:" in cuerpo
    assert "elif fuera > 0:" in cuerpo
    assert cuerpo.index("if respaldo:") < cuerpo.index("elif fuera > 0:")


def test_el_total_de_la_nota_son_todas_las_zonas_con_precio():
    """No `len(ez) + descartadas`: ese numero se dejaba fuera las excluidas por el tope."""
    cuerpo = _cuerpo_plan_nota()
    assert "len(con_precio)" in cuerpo
    assert "len(ez) + descartadas" not in _sin_comentarios(_fuente())


def test_form_la_nota_diria_tres_de_seis():
    """El caso real, calculado con la misma regla que usa el plan."""
    import levels_engine
    zonas = [{"price": p} for p in FORM_NIVELES]
    en_plan = len(levels_engine.indices_del_plan(FORM_PRECIO, zonas, 0.30))
    con_precio = len([z for z in zonas if z.get("price") is not None])
    assert (en_plan, con_precio) == (3, 6), f"la nota diria «{en_plan} de {con_precio}»"


def test_la_nota_nombra_los_DOS_motivos_de_exclusion():
    """Una zona puede quedar fuera por profundidad o por el tope de escalones. Decir solo
    lo primero es falso para NIVEL 4, que esta a -19,5% y aun asi no entra."""
    cuerpo = _cuerpo_plan_nota()
    assert "escalones como mucho" in cuerpo
    assert "bajo el precio" in cuerpo


def test_la_nota_aparece_tambien_si_solo_sobran_por_el_tope():
    """Antes el disparador era `if descartadas:`, asi que con seis zonas TODAS dentro del
    30% la nota no salia: se veian seis niveles, el plan usaba tres y nada lo explicaba."""
    cuerpo = _cuerpo_plan_nota()
    assert "if fuera > 0:" in cuerpo


@pytest.mark.parametrize("precio,niveles,esperado", [
    # Todas dentro del 30%: sobran por el tope. El caso que antes se quedaba mudo.
    (100.0, [95.0, 90.0, 85.0, 80.0], (3, 4)),
    # Mezcla: dos fuera por profundidad, una por el tope.
    (100.0, [95.0, 90.0, 85.0, 80.0, 60.0, 50.0], (3, 6)),
    # Menos de tres zonas: no sobra ninguna y la nota no debe salir.
    (100.0, [95.0, 90.0], (2, 2)),
])
def test_la_cuenta_cuadra_en_los_tres_repartos(precio, niveles, esperado):
    import levels_engine
    zonas = [{"price": p} for p in niveles]
    en_plan = len(levels_engine.indices_del_plan(precio, zonas, 0.30))
    assert (en_plan, len(zonas)) == esperado


# ── El plan de RESCATE: ninguna zona dentro del umbral ───────────────────────
#
# `indices_del_plan` devuelve la menos profunda AUNQUE quede bajo el suelo, para no dejar
# el plan sin niveles. La nota no sabia distinguir ese caso y escribia la frase normal:
# decia que se dejan fuera las que pasan del 30% mientras la unica que usaba estaba a
# -35%. Y con UNA sola zona no sobraba ninguna, asi que ni salia.

def _zona_cruda(precio, etiqueta="NIVEL"):
    return {"price": precio, "zone_low": precio * 0.99, "zone_high": precio * 1.01,
            "strength": 70, "reasons": ["soporte"], "label": etiqueta}


def _plan(precio_actual, precios):
    import server
    return server._deterministic_levels(
        {"price": precio_actual}, {"sma": {"50": 90.0, "200": 80.0}, "atr": 2.0},
        [_zona_cruda(p, f"NIVEL {i + 1}") for i, p in enumerate(precios)], None)


# 1-3 · La frase de respaldo dice la verdad sobre su propio plan

def test_el_respaldo_no_dice_que_deja_fuera_las_profundas():
    """El defecto exacto: la zona que USA tambien esta fuera del umbral."""
    nota = _plan(100.0, [65.0, 60.0, 55.0])["plan_nota"]
    assert "deja fuera las que están a más de un" not in nota
    assert "El plan usa" not in nota


def test_el_respaldo_dice_que_ha_rescatado_la_menos_profunda():
    nota = _plan(100.0, [65.0, 60.0, 55.0])["plan_nota"]
    assert "Ninguna zona de confluencia queda dentro del umbral" in nota
    assert "rescatado la zona menos profunda" in nota


def test_el_respaldo_advierte_de_la_distancia_del_stop():
    nota = _plan(100.0, [65.0, 60.0, 55.0])["plan_nota"]
    assert "El stop queda por debajo de esa zona" in nota
    assert "distancia de riesgo es elevada" in nota


# 4 · La variante silenciosa

def test_con_una_sola_zona_fuera_del_suelo_la_nota_SALE():
    """Antes era `None`: `fuera` valia 0 porque no sobraba ninguna. Un plan con el stop a
    -38% y ningun aviso."""
    r = _plan(100.0, [65.0])
    assert r["plan_nota"] is not None
    assert "Ninguna zona de confluencia queda dentro del umbral" in r["plan_nota"]


# 5-6 · La bandera se levanta cuando toca, y solo cuando toca

def test_respaldo_verdadero_solo_si_ninguna_sobrevive():
    import levels_engine
    zonas = [{"price": p} for p in (65.0, 60.0, 55.0)]
    idx, respaldo = levels_engine.indices_del_plan_detallado(100.0, zonas, 0.30)
    assert (idx, respaldo) == ([0], True)


def test_sobrar_por_el_tope_NO_es_rescatar():
    """Cuatro zonas dentro del suelo: sobra una por `MAX_ESCALONES`. Eso es una exclusion
    normal, no un rescate."""
    import levels_engine
    zonas = [{"price": p} for p in (95.0, 90.0, 85.0, 80.0)]
    idx, respaldo = levels_engine.indices_del_plan_detallado(100.0, zonas, 0.30)
    assert (idx, respaldo) == ([0, 1, 2], False)


def test_sin_zonas_con_precio_no_hay_rescate():
    """No haber salvado nada no es haber rescatado algo."""
    import levels_engine
    assert levels_engine.indices_del_plan_detallado(100.0, [], 0.30) == ([], False)
    assert levels_engine.indices_del_plan_detallado(
        100.0, [{"strength": 50}], 0.30) == ([], False)
    assert levels_engine.indices_del_plan_detallado(0.0, [{"price": 1.0}], 0.30) == ([], False)


# 7 · La fachada no cambia

@pytest.mark.parametrize("precio,niveles,max_depth", [
    (100.0, [95.0, 90.0, 85.0, 80.0], 0.30),
    (100.0, [65.0, 60.0, 55.0], 0.30),
    (100.0, [65.0], 0.30),
    (100.0, [], 0.30),
    (FORM_PRECIO, FORM_NIVELES, 0.30),
    (100.0, [95.0, 70.0, 50.0], 0.30),
])
def test_la_fachada_devuelve_los_mismos_indices(precio, niveles, max_depth):
    """`indices_del_plan` conserva firma y comportamiento: es la variante detallada sin su
    segundo valor. Si divergieran, `marcar_en_plan` y el plan pintarian cosas distintas."""
    import levels_engine
    zonas = [{"price": p} for p in niveles]
    assert levels_engine.indices_del_plan(precio, zonas, max_depth) == \
        levels_engine.indices_del_plan_detallado(precio, zonas, max_depth)[0]


# 8-10 · Los casos normales, byte a byte

_NOTA_NORMAL = (
    "El plan usa 3 de las 4 zonas de confluencia: se reparte en 3 escalones como mucho y "
    "deja fuera las que están a más de un 30% bajo el precio, que arrastrarían el stop "
    "hasta ahí. Todas siguen listadas como soportes."
)


def test_el_texto_normal_no_ha_cambiado_ni_un_byte():
    assert _plan(100.0, [95.0, 90.0, 85.0, 80.0])["plan_nota"] == _NOTA_NORMAL


def test_form_sigue_diciendo_tres_de_seis():
    nota = _plan(FORM_PRECIO, FORM_NIVELES)["plan_nota"]
    assert "El plan usa 3 de las 6 zonas de confluencia" in nota


def test_los_dos_motivos_siguen_nombrados_en_el_caso_normal():
    nota = _plan(100.0, [95.0, 90.0, 85.0, 80.0])["plan_nota"]
    assert "escalones como mucho" in nota
    assert "bajo el precio" in nota


# 11 · `en_plan` intacto

def test_marcar_en_plan_no_cambia():
    import levels_engine
    for niveles in ([95.0, 90.0, 85.0, 80.0], [65.0, 60.0, 55.0], [65.0], FORM_NIVELES):
        precio = FORM_PRECIO if niveles is FORM_NIVELES else 100.0
        zonas = [{"price": p} for p in niveles]
        levels_engine.marcar_en_plan(zonas, precio, 0.30)
        esperado = set(levels_engine.indices_del_plan(precio, zonas, 0.30))
        assert [i for i, z in enumerate(zonas) if z["en_plan"]] == sorted(esperado), niveles


# 12-13 · Esto es redaccion, no calculo

@pytest.mark.parametrize("precio,niveles", [
    (100.0, [95.0, 90.0, 85.0, 80.0]),
    (100.0, [65.0, 60.0, 55.0]),
    (100.0, [65.0]),
    (FORM_PRECIO, FORM_NIVELES),
])
def test_las_zonas_de_entrada_y_los_stops_no_dependen_de_la_nota(precio, niveles):
    """`entry_zones` y `stop_losses` salen de `ez`, y `ez` no ha cambiado. La bandera de
    respaldo solo entra en la frase."""
    r = _plan(precio, niveles)
    esperadas = [(z["min"], z["max"]) for z in r["entry_zones"]]
    stops = [s["price"] for s in r["stop_losses"]]
    # El plan lo determina la seleccion, que es la de siempre.
    import levels_engine
    idx = levels_engine.indices_del_plan(precio, [{"price": p} for p in niveles], 0.30)
    assert len(esperadas) == len(idx)
    assert stops == sorted(stops, reverse=True)
    assert min(s for s in stops) < min(lo for lo, _ in esperadas)
