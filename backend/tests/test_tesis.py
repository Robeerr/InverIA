"""La tesis determinista: qué dice, qué calla y de dónde sale cada cifra.

Existe porque al abrir una acción no había ni una frase en lenguaje normal: `analysis`
solo llega cuando se pulsa «Análisis completo IA», así que en frío la página estaba
muda. La tesis describe lo que los campos ya dicen, sin IA y sin espera.

Lo que estos tests protegen, por orden de importancia:

  1. Que ninguna cifra sea inventada. Cada afirmación numérica registra la RUTA del
     campo del que sale, y aquí se resuelve esa ruta contra el dashboard de origen y
     se compara el valor. Buscar números en el texto no valdría: el «2» de «media de
     200 sesiones» pasaría por dato verificado sin serlo.
  2. Que un campo ausente NO produzca una afirmación sobre sí mismo, aunque pueda
     intuirse desde otro. `regime` se calcula a partir del ADX; si `adx` es None, la
     tesis no puede citar ningún ADX.
  3. Que describa y no recomiende. Recomendar es del motor y de la IA; si esta capa
     opinara, acabaría contradiciéndolos con otra lógica escrita en otro sitio.
"""
import pytest

import tesis


# ── Dashboard de referencia ──────────────────────────────────────────────────
def dash(**cambios):
    """Un dashboard con la forma REAL que ensambla _construir_dashboard."""
    base = {
        "symbol": "AAPL",
        "quote": {"price": 213.64, "previous_close": 211.95, "change_percent": 0.8},
        "indicators": {
            "price": 213.64,
            "rsi": 61.0,
            "atr_pct": 1.9,
            "obv_trend": "subiendo",
            "vwap_anchored": 205.10,
            "sma": {"20": 210.4, "50": 204.8, "200": 191.2},
            "high_52w": 220.5, "low_52w": 164.1,
            "regime": {"regime": "tendencia_alcista", "adx": 31.0, "trending": True,
                       "ranging": False, "direction": "alcista"},
            "salida_10w": {"sma": 204.8, "por_encima": True, "distancia_pct": 4.3,
                           "senal": "mantener", "recien_perdida": False},
        },
        "buy_levels": [
            # `label` lo escribe SIEMPRE el motor (levels_engine numera de cerca a lejos).
            # Estaba ausente en esta fixture y por eso no se notaba que la tesis lo ignoraba.
            {"price": 178.40, "zone_low": 177.0, "zone_high": 179.5, "strength": 78,
             "distance_pct": -16.5, "label": "NIVEL 1",
             "reasons": ["SMA200", "Fibonacci 38,2%", "VWAP anclado"]},
            {"price": 165.0, "strength": 45, "distance_pct": -22.8, "label": "NIVEL 2",
             "reasons": ["Mínimo previo"]},
        ],
        "relative_strength": {"6m": {"accion_pct": 22.1, "indice_pct": 9.7,
                                     "diferencia_pp": 12.4, "supera": True}},
        "market_regime": {"light": "verde", "label": "Mercado sano", "dist_sma200_pct": 4.2},
        "data_health": {"source": "yfinance", "degraded": False},
        "analyst": {"consensus": {"label": "Compra moderada", "score": 78}},
    }
    for ruta, valor in cambios.items():
        partes = ruta.split(".")
        d = base
        for p in partes[:-1]:
            d = d[p]
        if valor is tesis:          # centinela para BORRAR una clave
            d.pop(partes[-1], None)
        else:
            d[partes[-1]] = valor
    return base


BORRAR = tesis  # legibilidad: dash(**{"indicators.rsi": BORRAR})


def texto_completo(t):
    return " ".join([t["titular"], *t["parrafos"],
                     *[s["texto"] for s in t["a_favor"] + t["en_contra"]],
                     (t["limita_confianza"] or {}).get("texto", "")]).lower()


# ── 1 · Trazabilidad auditable ───────────────────────────────────────────────
def test_cada_afirmacion_numerica_se_resuelve_contra_el_dashboard():
    """El test que impide inventar: se coge la ruta que la tesis dice haber usado, se
    resuelve contra el dashboard de origen y se compara el valor."""
    d = dash()
    t = tesis.redactar(d)
    assert t["afirmaciones"], "sin afirmaciones registradas no hay nada que auditar"
    for a in t["afirmaciones"]:
        real = tesis._leer(d, a["campo_origen"])
        assert real is not None, f"la ruta {a['campo_origen']} no existe en el dashboard"
        assert real == a["valor"], (
            f"{a['campo_origen']}: la tesis dice {a['valor']} y el dashboard trae {real}")


def test_las_senales_tambien_llevan_su_campo_de_origen():
    d = dash()
    t = tesis.redactar(d)
    for s in t["a_favor"] + t["en_contra"]:
        assert s["campo_origen"], f"señal sin origen: {s['texto']}"
        assert tesis._leer(d, s["campo_origen"]) == s["valor"]


def test_campos_usados_existen_todos_en_el_dashboard():
    d = dash()
    t = tesis.redactar(d)
    assert t["campos_usados"]
    for ruta in t["campos_usados"]:
        assert tesis._leer(d, ruta) is not None, f"{ruta} declarado y no existe"


def _origenes(t):
    """Todas las rutas que la tesis dice estar usando para sostener algo."""
    rutas = {a["campo_origen"] for a in t["afirmaciones"]}
    rutas |= {s["campo_origen"] for s in t["a_favor"] + t["en_contra"]}
    if t["limita_confianza"]:
        rutas.add(t["limita_confianza"]["campo_origen"])
    return rutas


def test_campos_usados_solo_lista_rutas_que_sostienen_algo():
    """`campos_usados` no es el registro de lo que se ha leído, sino el respaldo de lo
    que se afirma. Un campo consultado y descartado no puede aparecer aquí: quien
    audite la tesis leería la lista como «esto es lo que sustenta el texto»."""
    t = tesis.redactar(dash())
    sobrantes = set(t["campos_usados"]) - _origenes(t)
    assert not sobrantes, f"declarados sin sostener nada: {sorted(sobrantes)}"


def test_campos_usados_no_se_deja_ninguna_ruta_que_sostenga_texto():
    """El control en la otra dirección. Si una frase se escribe sin registrar su ruta,
    la lista queda corta y la auditoría deja de ser completa."""
    d = dash()
    t = tesis.redactar(d)
    presentes = {r for r in _origenes(t) if tesis._leer(d, r) is not None}
    assert presentes - set(t["campos_usados"]) == set()


@pytest.mark.parametrize("ruta,valor", [
    ("indicators.rsi", 55.0),         # neutro: se lee siempre y no dice nada
    ("indicators.high_52w", 900.0),   # lejísimos del máximo: no genera frase
])
def test_un_campo_leido_pero_no_citado_no_se_declara_usado(ruta, valor):
    """Los dos casos reales que inflaban la lista: ambos se consultan en toda tesis y
    solo hablan en su caso extremo."""
    t = tesis.redactar(dash(**{ruta: valor}))
    assert ruta not in t["campos_usados"]
    assert ruta not in _origenes(t)


@pytest.mark.parametrize("ruta", [
    "indicators.regime.regime",   # «Tendencia alcista»
    "indicators.obv_trend",       # «entra dinero: el volumen acompaña»
    "buy_levels[0].reasons",      # «donde coinciden SMA200 + …»
])
def test_las_frases_no_numericas_tambien_registran_su_ruta(ruta):
    """Tres frases que se escriben sin citar cifra. Sin ruta registrada saldrían en el
    texto sin respaldo auditable y desaparecerían de `campos_usados`."""
    d = dash()
    t = tesis.redactar(d)
    assert ruta in _origenes(t)
    assert ruta in t["campos_usados"]
    for a in t["afirmaciones"]:
        if a["campo_origen"] == ruta:
            assert tesis._leer(d, a["campo_origen"]) == a["valor"]


def test_el_indice_del_nivel_citado_es_el_correcto():
    """Se cita `buy_levels[i]`, no «el mejor nivel». Si el índice estuviera mal, la
    auditoría compararía contra otra zona y la tesis mentiría sin que se notara."""
    d = dash()
    t = tesis.redactar(d)
    rutas = [a["campo_origen"] for a in t["afirmaciones"] if a["campo_origen"].startswith("buy_levels")]
    assert rutas, "la tesis debería citar la zona más sólida"
    # La de fuerza 78 es la primera de la lista.
    assert all(r.startswith("buy_levels[0]") for r in rutas), rutas


def test_es_determinista():
    d = dash()
    assert tesis.redactar(d) == tesis.redactar(d)


def test_no_lleva_marca_de_tiempo():
    """Pedido explícitamente: la función es pura. El timestamp lo pone el servidor."""
    t = tesis.redactar(dash())
    assert "generada_en" not in t and "generado_en" not in t


# ── 2 · Un dato ausente no produce afirmaciones sobre sí mismo ───────────────
def test_sin_adx_no_se_cita_ningun_adx_aunque_el_regimen_lo_implique():
    """El caso pedido. `regime` se DERIVA del ADX, así que la tentación es escribir
    «con fuerza» igual. Pero afirmar sobre un dato que no está es inventarlo, y el
    usuario no puede distinguir una cifra medida de una deducida."""
    d = dash(**{"indicators.regime.adx": None})
    t = tesis.redactar(d)
    assert "adx" not in texto_completo(t)
    assert not any(a["campo_origen"] == "indicators.regime.adx" for a in t["afirmaciones"])
    assert "indicators.regime.adx" not in t["campos_usados"]
    # Y sigue diciendo lo que SÍ sabe: el régimen es otro campo y no es None.
    assert "tendencia alcista" in texto_completo(t)


@pytest.mark.parametrize("ruta,rastro", [
    ("indicators.atr_pct", "al día"),
    ("indicators.obv_trend", "dinero"),
    ("indicators.rsi", "rsi"),
    ("indicators.high_52w", "máximo anual"),
    ("quote.change_percent", "hoy"),
])
def test_un_campo_a_none_no_deja_rastro_en_el_texto(ruta, rastro):
    t = tesis.redactar(dash(**{ruta: None}))
    assert rastro not in texto_completo(t), f"con {ruta}=None sigue apareciendo '{rastro}'"
    assert ruta not in t["campos_usados"]


def test_sin_vwap_no_se_afirma_sobre_el_vwap():
    """Aparte de la lista de arriba porque "VWAP anclado" también es una de las RAZONES
    de un nivel —otro campo distinto—, así que buscar la palabra en el texto daría un
    falso positivo. Lo que hay que comprobar es que no queda ninguna afirmación NI señal
    apoyada en `indicators.vwap_anchored`."""
    t = tesis.redactar(dash(**{"indicators.vwap_anchored": None}))
    origenes = [a["campo_origen"] for a in t["afirmaciones"]] + \
               [s["campo_origen"] for s in t["a_favor"] + t["en_contra"]]
    assert "indicators.vwap_anchored" not in origenes
    assert "indicators.vwap_anchored" not in t["campos_usados"]


def test_un_campo_borrado_se_comporta_igual_que_uno_a_none():
    """None y ausente son el mismo caso: no hay dato."""
    a = tesis.redactar(dash(**{"indicators.rsi": None}))
    b = tesis.redactar(dash(**{"indicators.rsi": BORRAR}))
    assert a == b


def test_sin_sma200_no_se_afirma_nada_sobre_la_media_de_200():
    """Ojo al matiz: DECIR que el dato falta sí está permitido, y es lo que hace
    `limita_confianza`. Lo prohibido es afirmar algo SOBRE su valor."""
    t = tesis.redactar(dash(**{"indicators.sma.200": None}))
    afirmado = " ".join([t["titular"], *t["parrafos"],
                         *[s["texto"] for s in t["a_favor"] + t["en_contra"]]]).lower()
    assert "200 sesiones" not in afirmado
    origenes = [a["campo_origen"] for a in t["afirmaciones"]] + \
               [s["campo_origen"] for s in t["a_favor"] + t["en_contra"]]
    assert "indicators.sma.200" not in origenes
    # Y sí se dice que falta, que es información honesta y no una afirmación sobre el valor.
    assert "200 sesiones" in t["limita_confianza"]["texto"].lower()


# ── 3 · Describe, no recomienda ─────────────────────────────────────────────
@pytest.mark.parametrize("consejo", [
    "deberías", "debes ", "conviene", "recomend", "te sugerimos",
    "hay que comprar", "hay que vender", "compra ahora", "vende ahora",
])
def test_no_da_consejos(consejo):
    """Recomendar es del motor y de la IA. Si esta capa opinara, acabaría
    contradiciéndolos con otra lógica escrita en otro sitio.

    Se buscan CONSEJOS, no la palabra "compra" suelta: "zona de compra" es el nombre
    del nivel (`buy_levels`) y "Consenso de analistas: Compra moderada" es una etiqueta
    de terceros citada. Ninguna de las dos dice al usuario qué hacer.
    """
    assert consejo not in texto_completo(tesis.redactar(dash()))


def test_no_se_dirige_al_usuario_en_segunda_persona():
    """Otra forma del mismo control, menos dependiente de una lista de palabras."""
    texto = texto_completo(tesis.redactar(dash()))
    for marca in (" deberías", " podrías", " tienes que", " te interesa"):
        assert marca not in texto


# ── Situaciones ─────────────────────────────────────────────────────────────
def test_tendencia_alcista_con_fuerza():
    t = tesis.redactar(dash())
    txt = texto_completo(t)
    assert "tendencia alcista" in txt and "con fuerza" in txt and "adx 31" in txt


def test_tendencia_sin_fuerza_cuando_el_adx_es_bajo():
    t = tesis.redactar(dash(**{"indicators.regime.adx": 15.0}))
    assert "sin mucha fuerza" in texto_completo(t)


def test_lateral():
    t = tesis.redactar(dash(**{"indicators.regime.regime": "rango"}))
    assert "lateral" in texto_completo(t) and "mandan los niveles" in texto_completo(t)


def test_transicion():
    t = tesis.redactar(dash(**{"indicators.regime.regime": "transicion"}))
    assert "transición" in texto_completo(t)


def test_transicion_cita_el_adx_cuando_existe():
    """En transición el ADX es el dato más informativo —dice cuánto le falta para ser
    tendencia— y antes se callaba porque la plantilla solo contemplaba tendencias."""
    d = dash(**{"indicators.regime.regime": "transicion",
                "indicators.regime.adx": 21.0})
    t = tesis.redactar(d)
    assert "está en transición: ni tendencia clara ni rango definido (adx 21)" in \
        texto_completo(t)
    assert any(a["campo_origen"] == "indicators.regime.adx" for a in t["afirmaciones"])
    assert "indicators.regime.adx" in t["campos_usados"]


def test_en_transicion_el_adx_no_se_convierte_en_conclusion_de_tendencia():
    """Se cita desnudo. «En transición con fuerza» sería una conclusión sobre la
    dirección que el régimen precisamente dice no tener."""
    t = tesis.redactar(dash(**{"indicators.regime.regime": "transicion",
                               "indicators.regime.adx": 31.0}))
    texto = texto_completo(t)
    assert "con fuerza" not in texto and "sin mucha fuerza" not in texto


def test_en_transicion_sin_adx_no_se_menciona_el_adx():
    """La regla de siempre: un dato ausente no produce una afirmación sobre sí mismo."""
    t = tesis.redactar(dash(**{"indicators.regime.regime": "transicion",
                               "indicators.regime.adx": None}))
    assert "adx" not in texto_completo(t)
    assert "indicators.regime.adx" not in t["campos_usados"]
    assert "transición" in texto_completo(t)


def test_acaba_de_perder_la_media_de_10_semanas_va_siempre_en_contra():
    """Es la señal de salida del método, no un matiz."""
    t = tesis.redactar(dash(**{"indicators.salida_10w.recien_perdida": True}))
    contras = " ".join(s["texto"].lower() for s in t["en_contra"])
    assert "acaba de perder la media de 10 semanas" in contras


@pytest.mark.parametrize("rsi,donde,palabra", [
    (75.0, "en_contra", "sobrecompra"),
    (22.0, "a_favor", "sobreventa"),
])
def test_rsi_extremo(rsi, donde, palabra):
    t = tesis.redactar(dash(**{"indicators.rsi": rsi}))
    assert any(palabra in s["texto"].lower() for s in t[donde])


def test_rsi_normal_no_genera_senal():
    t = tesis.redactar(dash(**{"indicators.rsi": 55.0}))
    assert "rsi" not in texto_completo(t)


def test_la_zona_citada_es_la_mas_fuerte_no_la_primera():
    d = dash(**{"buy_levels": [
        {"price": 200.0, "strength": 30, "distance_pct": -5.0, "reasons": ["Mínimo previo"]},
        {"price": 180.0, "strength": 85, "distance_pct": -15.0, "reasons": ["SMA200"]},
    ]})
    t = tesis.redactar(d)
    assert "180.00" in " ".join(t["parrafos"])
    assert any(a["campo_origen"] == "buy_levels[1].price" for a in t["afirmaciones"])


def test_todas_las_rutas_del_nivel_usan_el_indice_realmente_elegido():
    """Tres zonas y la más sólida es la ÚLTIMA. Si alguna ruta se quedara en [0], la
    auditoría compararía la fuerza de una zona contra el precio de otra y cuadraría
    sin ser cierta: cada campo existiría, pero no todos serían del mismo nivel."""
    d = dash(**{"buy_levels": [
        {"price": 205.0, "strength": 20, "distance_pct": -4.0, "reasons": ["Mínimo previo"]},
        {"price": 195.0, "strength": 55, "distance_pct": -8.7, "reasons": ["SMA50"]},
        {"price": 178.40, "strength": 91, "distance_pct": -16.5,
         "reasons": ["SMA200", "Fibonacci 38,2%", "VWAP anclado"]},
    ]})
    t = tesis.redactar(d)

    rutas = [a["campo_origen"] for a in t["afirmaciones"]
             if a["campo_origen"].startswith("buy_levels")]
    assert rutas, "la tesis debería citar la zona más sólida"
    assert all(r.startswith("buy_levels[2]") for r in rutas), rutas

    # Y cada valor citado es el de ESA zona, no el de otra que también existiera.
    for a in t["afirmaciones"]:
        if a["campo_origen"].startswith("buy_levels"):
            assert tesis._leer(d, a["campo_origen"]) == a["valor"]

    parrafos = " ".join(t["parrafos"])
    assert "178.40" in parrafos and "fuerza 91/100" in parrafos
    assert "205.00" not in parrafos and "195.00" not in parrafos


# ── Qué limita la confianza ─────────────────────────────────────────────────
def test_datos_degradados_es_lo_primero_que_limita():
    t = tesis.redactar(dash(**{"data_health": {"degraded": True, "note": "fuente de respaldo"}}))
    assert "respaldo" in t["limita_confianza"]["texto"]
    assert t["limita_confianza"]["campo_origen"] == "data_health.degraded"


def test_los_datos_degradados_se_describen_sin_aconsejar():
    """Decía «Trátalo con cautela», que es un consejo sobre cómo actuar y no una
    descripción del dato. El estado se cuenta; qué hacer con él, no."""
    t = tesis.redactar(dash(**{"data_health": {"degraded": True, "note": "fuente de respaldo"}}))
    texto = t["limita_confianza"]["texto"].lower()
    assert "respaldo" in texto and "retraso" in texto
    for consejo in ("cautela", "trátalo", "cuidado", "precaución", "ten en cuenta"):
        assert consejo not in texto, f"sigue aconsejando: '{consejo}'"


@pytest.mark.parametrize("escenario", [
    {"data_health": {"degraded": True, "note": "fuente de respaldo"}},
    {"market_regime": {"light": "rojo", "label": "Mercado en riesgo"}},
    {"indicators.sma.200": None},
    {"buy_levels": []},
    {"indicators.regime.regime": "indeterminado"},
])
def test_ninguna_limitacion_da_un_consejo(escenario):
    """La regla de «describe, no recomienda» también rige aquí: es el bloque donde más
    tienta rematar con una instrucción."""
    t = tesis.redactar(dash(**escenario))
    texto = t["limita_confianza"]["texto"].lower()
    for consejo in ("deberías", "debes ", "conviene", "recomend", "cautela",
                    "trátalo", "evita ", "no compres"):
        assert consejo not in texto, f"{escenario}: '{consejo}' es un consejo"


def test_sin_sma200_lo_dice_como_limite():
    t = tesis.redactar(dash(**{"indicators.sma.200": None}))
    assert "histórico corto" in t["limita_confianza"]["texto"].lower()


def test_regimen_indeterminado_limita():
    t = tesis.redactar(dash(**{"indicators.regime.regime": "indeterminado"}))
    assert "régimen" in t["limita_confianza"]["texto"].lower()


def test_sin_zonas_lo_dice():
    t = tesis.redactar(dash(**{"buy_levels": []}))
    assert "zonas de confluencia" in t["limita_confianza"]["texto"]


def test_mercado_en_riesgo_limita():
    t = tesis.redactar(dash(**{"market_regime": {"light": "rojo", "label": "Mercado en riesgo"}}))
    assert "mercado en riesgo" in t["limita_confianza"]["texto"].lower()


def test_con_todo_bien_no_se_inventa_un_limite():
    """Un aviso permanente deja de leerse: es decoración."""
    assert tesis.redactar(dash())["limita_confianza"] is None


def test_solo_se_da_un_limite_el_mas_grave():
    d = dash(**{"data_health": {"degraded": True, "note": "x"},
                "indicators.sma.200": None, "buy_levels": []})
    lim = tesis.redactar(d)["limita_confianza"]
    assert isinstance(lim, dict) and lim["campo_origen"] == "data_health.degraded"


# ── Casos sin datos ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("entrada", [None, {}, [], "", 0, {"symbol": "X"}])
def test_sin_dashboard_no_hay_tesis(entrada):
    assert tesis.redactar(entrada) is None


def test_sin_precio_no_hay_tesis():
    """Sin precio no hay nada que describir. Preferible a una frase vacía con aspecto
    de análisis."""
    assert tesis.redactar(dash(**{"quote.price": None})) is None


def test_con_solo_el_precio_tampoco():
    """Eso no es una tesis: es un dato que ya está en la cabecera."""
    assert tesis.redactar({"symbol": "X", "quote": {"price": 100.0}}) is None


def test_un_dashboard_a_medias_no_revienta():
    t = tesis.redactar({"symbol": "X", "quote": {"price": 100.0},
                        "indicators": {"regime": {"regime": "rango"}}})
    assert t and t["titular"]
    assert t["parrafos"]


def test_las_listas_estan_siempre_aunque_vacias():
    """Que el frontend no tenga que defenderse de un None por cada campo."""
    t = tesis.redactar({"symbol": "X", "quote": {"price": 100.0},
                        "indicators": {"regime": {"regime": "rango"}}})
    for clave in ("parrafos", "a_favor", "en_contra", "afirmaciones", "campos_usados"):
        assert isinstance(t[clave], list)


# ── El lector de rutas, que es de quien depende la auditoría ────────────────
@pytest.mark.parametrize("ruta,esperado", [
    ("quote.price", 213.64),
    ("indicators.regime.adx", 31.0),
    ("buy_levels[0].strength", 78),
    ("buy_levels[1].price", 165.0),
    ("relative_strength.6m.supera", True),
])
def test_el_lector_de_rutas_resuelve_bien(ruta, esperado):
    assert tesis._leer(dash(), ruta) == esperado


@pytest.mark.parametrize("ruta", [
    "no.existe", "quote.no_existe", "buy_levels[9].price",
    "quote.price.demasiado_hondo", "indicators.sma.999",
])
def test_el_lector_de_rutas_devuelve_none_sin_reventar(ruta):
    assert tesis._leer(dash(), ruta) is None


# ── El nivel se nombra, no solo se cotiza ────────────────────────────────────
def test_la_zona_mas_solida_se_cita_por_su_nombre():
    """Un precio suelto no se puede cruzar con el panel de niveles. Con FORM eso hizo que
    «la zona más sólida está en 95.55» y «entrada 109.36» parecieran dos recomendaciones
    en conflicto, cuando eran el escalón 3 y el borde del escalón 1 del MISMO plan."""
    t = tesis.redactar(dash())
    parrafos = " ".join(t["parrafos"])
    assert "es el NIVEL 1, en 178.40" in parrafos, parrafos
    assert any(a["campo_origen"] == "buy_levels[0].label" for a in t["afirmaciones"])
    assert "buy_levels[0].label" in t["campos_usados"]


def test_el_nombre_es_el_del_nivel_realmente_elegido():
    """Si la más sólida no es la primera, el nombre citado tiene que ser el suyo."""
    d = dash(**{"buy_levels": [
        {"price": 200.0, "strength": 30, "distance_pct": -5.0, "label": "NIVEL 1"},
        {"price": 180.0, "strength": 85, "distance_pct": -15.0, "label": "NIVEL 2",
         "reasons": ["SMA200"]},
    ]})
    t = tesis.redactar(d)
    assert "es el NIVEL 2, en 180.00" in " ".join(t["parrafos"])
    assert not any(a["campo_origen"] == "buy_levels[0].label" for a in t["afirmaciones"])


def test_sin_etiqueta_no_se_inventa_el_numero_de_peldano():
    """La regla de siempre: un dato ausente no produce una afirmación sobre sí mismo."""
    d = dash(**{"buy_levels": [
        {"price": 178.40, "strength": 78, "distance_pct": -16.5, "reasons": ["SMA200"]},
    ]})
    t = tesis.redactar(d)
    parrafos = " ".join(t["parrafos"])
    assert "está en 178.40" in parrafos
    assert "NIVEL" not in parrafos
    assert "buy_levels[0].label" not in t["campos_usados"]
