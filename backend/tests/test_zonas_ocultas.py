"""Sin tendencia alcista, las zonas de compra no se presentan como oportunidades.

QUÉ SE PROTEGE

    Un soporte puede decirte dónde sería interesante comprar.
    Nunca puede decirte que debes comprar.

`levels_engine` calcula zonas por debajo del precio sin mirar hacia dónde va la acción,
así que una acción en caída libre tenía su lista de «zonas de compra» pintada igual que
una líder. El cálculo no cambia; lo que se retira es su interpretación.

Se comprueba sobre las funciones puras del servidor y sobre la FORMA del código, no
levantando la aplicación: `_construir_dashboard` y `/analyze` necesitan Mongo,
cotizaciones y claves de IA, y montarlos aquí probaría sobre todo el montaje.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _fuente(nombre: str) -> str:
    with open(os.path.join(_AQUI, "..", nombre), encoding="utf-8") as f:
        return f.read()


SRC = _fuente("server.py")


def _sin_comentarios(src: str) -> str:
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    return re.sub(r"#.*", "", src)


CODIGO = _sin_comentarios(SRC)


def _cuerpo(nombre_funcion: str) -> str:
    """El cuerpo de una función, hasta la siguiente definición de primer nivel."""
    ini = CODIGO.index(f"def {nombre_funcion}(")
    resto = CODIGO[ini:]
    m = re.search(r"\n(?:def |@api_router|@app\.)", resto[1:])
    return resto[: m.start() + 1] if m else resto


# ── La capa de presentación, comprobada de verdad ────────────────────────────
# Estas dos funciones son puras, así que aquí sí se ejecutan.

def _cargar_helpers():
    """Extrae las dos funciones puras sin importar `server` entero.

    Importar `server` arrastra FastAPI, Motor y las variables de entorno de producción.
    Lo que se prueba aquí no depende de nada de eso.
    """
    import estado_accion
    ns = {"estado_accion": estado_accion}
    for nombre in ("_aplicar_estado_tendencia", "_ocultar_plan_de_entrada"):
        exec(compile(_cuerpo(nombre), "<server>", "exec"), ns)
    return ns["_aplicar_estado_tendencia"], ns["_ocultar_plan_de_entrada"]


APLICAR, OCULTAR = _cargar_helpers()

ZONAS = [{"price": 90.0, "label": "NIVEL 1"}, {"price": 85.0, "label": "NIVEL 2"}]


def test_alcista_conserva_las_zonas():
    p = APLICAR({"buy_levels": list(ZONAS)}, 110, {"sma": {"50": 105, "200": 100}})
    assert p["buy_levels"] == ZONAS
    assert p["estado"] == "SIN_EVALUAR"
    assert "zonas_ocultas_por_tendencia" not in p


def test_bajista_vacia_las_zonas_y_lo_dice():
    p = APLICAR({"buy_levels": list(ZONAS)}, 90, {"sma": {"50": 95, "200": 100}})
    assert p["buy_levels"] == []
    assert p["estado"] == "NO_COMPRAR"
    assert p["zonas_ocultas_por_tendencia"] is True
    assert p["estado_motivo"]


def test_indefinida_tambien_oculta():
    p = APLICAR({"buy_levels": list(ZONAS)}, 110, {"sma": {"50": 95, "200": 100}})
    assert p["buy_levels"] == []
    assert p["estado"] == "EN_SEGUIMIENTO"


def test_sin_medias_oculta():
    p = APLICAR({"buy_levels": list(ZONAS)}, 110, {})
    assert p["buy_levels"] == []
    assert p["tendencia"] == "SIN_DATOS"


def test_nunca_hay_estado_negativo_con_zonas_debajo():
    """La contradicción que más daño haría: un NO_COMPRAR con la lista de zonas al lado.
    Sería peor que cualquiera de las dos cosas por separado."""
    for precio, sma in ((90, {"50": 95, "200": 100}), (110, {"50": 95, "200": 100}), (110, {})):
        p = APLICAR({"buy_levels": list(ZONAS)}, precio, {"sma": sma} if sma else {})
        if p["estado"] != "SIN_EVALUAR":
            assert p["buy_levels"] == [], p


# ── Qué se quita del análisis y qué se queda ─────────────────────────────────

def test_se_quita_el_plan_de_entrada():
    analisis = {"entry_zone": {"min": 1, "max": 2}, "entry_zones": [{}], "entry_avg": 1.5,
                "stop_loss": 0.9, "take_profit_1": 3, "risk_reward_ratio": 2.4,
                "key_levels": {"support": [90, 85], "resistance": [120]},
                "summary": "texto"}
    OCULTAR(analisis)
    for fuera in ("entry_zone", "entry_zones", "entry_avg", "stop_loss",
                  "take_profit_1", "risk_reward_ratio"):
        assert fuera not in analisis, fuera


def test_los_soportes_siguen_ahi_como_informacion_tecnica():
    """Lo que se oculta es la INTERPRETACIÓN como zona de compra, no el dato."""
    analisis = {"entry_zone": {"min": 1}, "key_levels": {"support": [90, 85]}, "summary": "t"}
    OCULTAR(analisis)
    assert analisis["key_levels"]["support"] == [90, 85]
    assert analisis["summary"] == "t"


def test_ocultar_aguanta_basura():
    assert OCULTAR(None) is None
    assert OCULTAR({}) == {}


# ── El cableado, comprobado sobre la forma ───────────────────────────────────

def test_el_dashboard_aplica_el_estado_antes_de_la_tesis():
    """La tesis se redacta sobre `result`. Si el estado se aplicara después, la frase
    «la zona de compra más sólida es…» seguiría señalando una lista ya vacía."""
    cuerpo = _cuerpo("_construir_dashboard")
    assert "_aplicar_estado_tendencia" in cuerpo
    assert cuerpo.index("_aplicar_estado_tendencia") < cuerpo.index("tesis.redactar")


def test_analyze_oculta_despues_de_los_niveles_deterministas():
    """Si se vaciaran las zonas ANTES, `_deterministic_levels` devolvería None, el flujo
    caería al clásico y los números los inventaría el modelo. Ocultar una zona calculada
    es seguro; no calcularla abre la puerta a una peor."""
    cuerpo = _cuerpo("analyze_stock_endpoint") if "def analyze_stock_endpoint(" in CODIGO \
        else CODIGO[CODIGO.index("_deterministic_levels(quote"):]
    assert cuerpo.index("_deterministic_levels(quote") < cuerpo.index("_aplicar_estado_tendencia")


def test_analyze_devuelve_las_zonas_ya_filtradas():
    """Leer `buy_levels` otra vez a pelo en el return es como se acaba enviando una lista
    de zonas junto a un NO_COMPRAR."""
    cola = CODIGO[CODIGO.index("respuesta = {\"buy_levels\""):]
    cola = cola[:cola.index("# ---------- ")] if "# ---------- " in cola else cola[:2000]
    assert '"buy_levels": respuesta["buy_levels"]' in cola
