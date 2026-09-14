"""El laboratorio: que no aprenda en falso.

LO QUE ESTE FICHERO TIENE QUE DEMOSTRAR

Que el laboratorio prefiere decir «no lo sé» antes que concluir. Tres de los cuatro
estados finales son formas de no saber, y los tests comprueban que se alcanzan de
verdad: sin muestra, sin separación, y con la separación al revés de lo esperado.

Y que la medida no mira el futuro. El leakage aquí sería invisible —el máximo de 52
semanas incluyendo la barra del día es un error de una línea que no se ve al leer— así
que hay un test construido para que falle exactamente en ese caso.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest

import calibracion
import laboratorio as lab


# ── El registro de hipótesis sale del código, no de una tabla ────────────────

def test_las_hipotesis_se_leen_de_CALIBRACION():
    ids = {h["id"] for h in lab.hipotesis()}
    # Todas las constantes anotadas del módulo, ni una menos: si alguien añade un umbral
    # nuevo aparece aquí solo, sin tener que acordarse de registrarlo en otro sitio.
    declaradas = {n for n in dir(calibracion)
                  if n.isupper() and not n.startswith("_")}
    assert declaradas == ids, declaradas ^ ids
    assert "DISTANCIA_MAX_A_MAXIMO_52S" in ids


def test_cada_hipotesis_trae_QUE_MEDIR():
    """El docstring de `calibracion` ya declara qué habría que medir. Si se perdiera al
    leerlo, el registro sería una lista de nombres sin nada accionable."""
    for h in lab.hipotesis():
        assert h["titulo"] and h["titulo"] != h["id"]
        assert h.get("mide"), f"{h['id']} no dice qué medir"


def test_un_umbral_SIN_numero_y_SIN_medir_sigue_siendo_una_hipotesis():
    """Se cambió de `DISTANCIA_MAX_A_MAXIMO_52S` a otro umbral porque aquel YA se midió
    el 14-09-2026 y salió rechazado: usarlo aquí habría convertido este test en una
    comprobación de que el rechazo no se registra."""
    d = next(h for h in lab.hipotesis() if h["id"] == "ATR_MULTIPLO_STOP")
    assert d["valor_actual"] is None
    assert d["estado"] == lab.LISTA          # medible, pero todavía sin medir


def test_ponerle_un_numero_lo_convierte_en_REGLA_EN_VIGOR(monkeypatch):
    """El estado sale del valor REAL de la constante. Así el registro no puede decir que
    algo sigue sin medir mientras el código ya lo aplica."""
    monkeypatch.setattr(calibracion, "DISTANCIA_MAX_A_MAXIMO_52S", 25.0)
    d = next(h for h in lab.hipotesis() if h["id"] == "DISTANCIA_MAX_A_MAXIMO_52S")
    assert d["estado"] == lab.VALIDADA and d["valor_actual"] == 25.0


def test_lo_que_NO_se_puede_medir_dice_por_que():
    bloqueadas = [h for h in lab.hipotesis() if not h["medible_hoy"]]
    assert bloqueadas, "si todo fuera medible, esta distinción no protegería nada"
    for h in bloqueadas:
        assert len(h["por_que"]) > 20 and h["estado"] != lab.VALIDADA


def test_ninguna_hipotesis_pide_fundamentales_historicos():
    """La puerta cerrada con llave. Un backtest de factores con los datos de hoy mediría
    un mercado sin quiebras: sale bien y está mal."""
    for h in lab.hipotesis():
        if h["medible_hoy"]:
            assert "point-in-time" not in (h.get("bloqueado_por") or "")


# ── La medida no puede mirar el futuro ───────────────────────────────────────

def _serie(cierres, altos=None):
    altos = altos or cierres
    return [{"high": h, "close": c, "date": f"2020-01-{i:02d}"}
            for i, (h, c) in enumerate(zip(altos, cierres), start=1)]


def test_el_maximo_NO_incluye_la_barra_del_ancla():
    """El leakage invisible de este experimento. Se construye una serie donde el ancla
    ES el máximo de toda la historia: si entrara en su propio máximo, la distancia
    saldría 0; como no entra, sale positiva.

    Un `rolling().max()` de pandas incluye la barra actual por defecto, y ese detalle
    metería el máximo del día en la decisión del día.
    """
    n = lab.VENTANA + lab.HORIZONTE + 1
    cierres = [100.0] * n
    altos = [100.0] * n
    altos[lab.VENTANA] = 500.0                 # el ancla es un máximo histórico
    obs = lab.observaciones(_serie(cierres, altos))
    assert obs, "la serie tiene que producir al menos una observación"
    assert obs[0]["distancia_pct"] == 0.0      # el ancla no se mira a sí misma


def test_el_retorno_usa_SOLO_barras_posteriores():
    n = lab.VENTANA + lab.HORIZONTE + 1
    cierres = [100.0] * n
    cierres[lab.VENTANA + lab.HORIZONTE] = 110.0
    obs = lab.observaciones(_serie(cierres))
    assert obs[0]["retorno_pct"] == 10.0


def test_una_serie_CORTA_no_produce_ninguna_observacion():
    """Sin 52 semanas de calentamiento no hay máximo anual que calcular. Devolver algo
    sería inventarse el dato."""
    assert lab.observaciones(_serie([100.0] * (lab.VENTANA + lab.HORIZONTE - 1))) == []
    assert lab.observaciones([]) == []
    assert lab.observaciones(None) == []


def test_una_barra_ROTA_se_salta_sin_tumbar_la_serie():
    n = lab.VENTANA + lab.HORIZONTE * 3
    barras = _serie([100.0] * n)
    barras[lab.VENTANA] = {"high": None, "close": "roto", "date": "x"}
    assert isinstance(lab.observaciones(barras), list)


# ── Tres de los cuatro finales dicen «no lo sé» ──────────────────────────────

def _obs(tramo, retornos):
    return [{"tramo": tramo, "retorno_pct": r, "symbol": "X", "fecha": "d",
             "distancia_pct": 1} for r in retornos]


def _todos_los_tramos(medias, n=lab.MUESTRA_MINIMA):
    obs = []
    for (bajo, alto), media in zip(lab.TRAMOS, medias):
        obs += _obs(f"{bajo}-{alto}%", [media] * n)
    return obs


def test_sin_MUESTRA_suficiente_no_se_concluye():
    r = lab.agregar(_todos_los_tramos([5, 4, 3, 2, 1], n=lab.MUESTRA_MINIMA - 1))
    assert r["estado"] == lab.SIN_DATOS
    assert r["tramos_flacos"] and "mínimo" in r["conclusion"]


def test_si_los_tramos_NO_SE_DISTINGUEN_el_resultado_es_inconcluyente():
    r = lab.agregar(_todos_los_tramos([2.0, 2.1, 2.0, 1.9, 2.0]))
    assert r["estado"] == lab.NO_CONCLUYENTE


def test_si_la_direccion_es_la_CONTRARIA_la_hipotesis_se_RECHAZA():
    """Alejarse del máximo mejora el retorno: lo contrario de lo que se fijó antes de
    mirar. Es un resultado, y se registra como tal."""
    r = lab.agregar(_todos_los_tramos([1, 2, 3, 4, 8]))
    assert r["estado"] == lab.RECHAZADA


def test_solo_se_VALIDA_con_muestra_direccion_y_separacion():
    r = lab.agregar(_todos_los_tramos([8, 6, 4, 2, 1]))
    assert r["estado"] == lab.VALIDADA
    assert r["separacion_pp"] == 7.0
    assert all(t["n"] == lab.MUESTRA_MINIMA for t in r["tramos"])


def test_la_direccion_esperada_se_declara_ANTES_del_resultado():
    """Fijarla de antemano es lo que impide «probamos quinientas cosas y una salió»."""
    f = lab.ficha([], universo=["AAPL"])
    assert "ANTES" in f["metodo"]["direccion_esperada"]


# ── La ficha lleva su propio método ──────────────────────────────────────────

def test_el_experimento_declara_sus_SESGOS():
    c = lab.ficha([], universo=["AAPL"])["controles"]
    assert "supervivencia" in c and "leakage" in c and "solapamiento" in c
    assert "NO son" in c["solapamiento"]          # se dice que no son independientes
    assert "p-valor" in c["solapamiento"]         # y por eso no se calcula ninguno


def test_la_ficha_declara_la_RESOLUCION_y_el_universo():
    f = lab.ficha([], universo=["MSFT", "AAPL"])
    assert f["metodo"]["resolucion"] == lab.RESOLUCION
    assert f["metodo"]["universo"] == ["AAPL", "MSFT"]     # ordenado, reproducible
    assert f["metodo"]["simbolos"] == 2
    assert f["hipotesis_id"] == "DISTANCIA_MAX_A_MAXIMO_52S"


def test_sin_observaciones_la_ficha_sale_SIN_DATOS_y_no_falla():
    assert lab.ficha([], universo=[])["estado"] == lab.SIN_DATOS


# ── Persistencia: también lo que salió mal ───────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, c, o=1):
        self.docs.sort(key=lambda d: d.get(c) or "", reverse=o < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n=None):
        return list(self.docs[:n] if n else self.docs)


class _Col:
    def __init__(self):
        self.docs = []

    def find(self, f=None, p=None):
        return _Cursor(self.docs)

    async def count_documents(self, filtro=None):
        return len([d for d in self.docs
                    if all(d.get(k) == v for k, v in (filtro or {}).items())])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self):
        self._cols = {}

    def __getitem__(self, n):
        return self._cols.setdefault(n, _Col())

    def __getattr__(self, n):
        return self[n]


def test_un_experimento_RECHAZADO_tambien_se_guarda():
    """Saber que algo no funcionó evita repetirlo, y es la mitad del valor del
    laboratorio."""
    db = _DB()
    doc = lab.ficha(_todos_los_tramos([1, 2, 3, 4, 8]), universo=["AAPL"])
    assert doc["estado"] == lab.RECHAZADA
    assert asyncio.run(lab.guardar_experimento(db, doc))["ok"]
    assert db[lab.COL_EXPERIMENTOS].docs[0]["estado"] == lab.RECHAZADA


def test_se_CUENTAN_los_intentos_de_cada_hipotesis():
    """El control contra «probamos quinientas cosas y una salió espectacular»: si un id
    acumula intentos, su resultado hay que leerlo con esa cifra delante."""
    db = _DB()
    for _ in range(3):
        asyncio.run(lab.guardar_experimento(db, lab.ficha([], universo=["AAPL"])))
    assert [d["intento"] for d in db[lab.COL_EXPERIMENTOS].docs] == [1, 2, 3]


def test_un_fallo_de_MONGO_no_lanza():
    db = _DB()
    db[lab.COL_EXPERIMENTOS].insert_one = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("caído"))
    r = asyncio.run(lab.guardar_experimento(db, lab.ficha([], universo=["A"])))
    assert r["ok"] is False and r["motivo"] == "error"


def test_no_se_guarda_un_documento_VACIO():
    db = _DB()
    assert asyncio.run(lab.guardar_experimento(db, {}))["ok"] is False
    assert asyncio.run(lab.guardar_experimento(db, None))["ok"] is False
    assert db[lab.COL_EXPERIMENTOS].docs == []


# ── El panorama ──────────────────────────────────────────────────────────────

def test_el_panorama_NO_lleva_una_puntuacion_global():
    """Un «InverIA IQ» sumaría conocimiento leído, hipótesis abiertas y experimentos
    hechos, que no son la misma magnitud. Es el error que `separacion.py` documenta."""
    p = asyncio.run(lab.panorama(_DB()))
    plano = str(p).lower()
    for prohibido in ("iq", "puntuacion_global", "score_total", "nota_global"):
        assert prohibido not in plano


def test_el_panorama_REUTILIZA_la_base_de_conocimiento_existente():
    """No se ha creado una segunda memoria: el conocimiento sigue en
    `investing_knowledge`, la colección que alimentan newsletters, Telegram y YouTube."""
    p = asyncio.run(lab.panorama(_DB()))
    assert p["conocimiento"]["coleccion"] == "investing_knowledge"


def test_el_panorama_separa_lo_MEDIBLE_de_lo_bloqueado():
    p = asyncio.run(lab.panorama(_DB()))
    h = p["hipotesis"]
    assert h["total"] == len(lab.hipotesis())
    assert h["medibles_hoy"] + h["bloqueadas"] == h["total"]
    assert h["medibles_hoy"] > 0 and h["bloqueadas"] > 0


@pytest.mark.parametrize("estado", [lab.VALIDADA, lab.RECHAZADA, lab.SIN_DATOS,
                                    lab.NO_CONCLUYENTE])
def test_los_cuatro_finales_son_estados_legitimos(estado):
    assert estado in lab.FINALES


# ── El diagnóstico: centro o cola ────────────────────────────────────────────
#
# El experimento 1 salió RECHAZADO con un gradiente de medias de 16 pp y una tasa de
# acierto PLANA (59,7% a 65,4%, sin orden). Ganar las mismas veces y mucho más cuando se
# gana es dispersión, no ventaja. Estos tests protegen la herramienta que distingue las
# dos cosas.

def _dist(medias, n=lab.MUESTRA_MINIMA, año="2022", cola=None):
    """Observaciones con la media pedida por tramo. `cola` mete un valor enorme en el
    último tramo para simular el caso real: media alta con mediana igual."""
    obs = []
    for i, ((bajo, alto), media) in enumerate(zip(lab.TRAMOS, medias)):
        vals = [media] * n
        if cola is not None and i == len(lab.TRAMOS) - 1:
            vals = [media] * (n - 1) + [cola]
        obs += [{"tramo": f"{bajo}-{alto}%", "retorno_pct": v, "fecha": f"{año}-03-01",
                 "symbol": "X", "distancia_pct": 1} for v in vals]
    return obs


def test_la_MEDIANA_no_la_mueve_un_solo_acierto_enorme():
    """La propiedad que hace útil este diagnóstico. Si la mediana se moviera como la
    media, no distinguiría nada."""
    d = lab.distribucion(_dist([10, 10, 10, 10, 10], cola=1000))
    ultimo = d["tramos"][-1]
    assert ultimo["mediana"] == 10
    assert ultimo["media"] > 40                  # la media SÍ se dispara


def test_si_la_mediana_es_PLANA_el_efecto_vive_en_la_COLA():
    """El caso que se sospecha del experimento 1: medias muy separadas, medianas no."""
    v = lab.veredicto_distribucion(lab.distribucion(_dist([10, 10, 10, 10, 10], cola=3000)))
    assert v["estado"] == lab.RECHAZADA
    assert "COLA" in v["conclusion"]
    assert v["rango_mediana_pp"] < lab.SEPARACION_MINIMA <= v["rango_media_pp"]


def test_si_la_mediana_TAMBIEN_se_separa_no_se_concluye():
    """Entonces el efecto no es solo de cola, pero siguen en pie régimen y
    supervivencia: no se puede afirmar nada todavía."""
    v = lab.veredicto_distribucion(lab.distribucion(_dist([2, 6, 10, 14, 20])))
    assert v["estado"] == lab.NO_CONCLUYENTE
    assert "régimen" in v["conclusion"] and "supervivencia" in v["conclusion"]


def test_sin_separacion_en_NINGUNA_de_las_dos_no_hay_nada_que_explicar():
    v = lab.veredicto_distribucion(lab.distribucion(_dist([10, 10.2, 10.1, 10, 10.3])))
    assert v["estado"] == lab.NO_CONCLUYENTE
    assert "nada que explicar" in v["conclusion"]


def test_el_diagnostico_NO_puede_rehabilitar_la_hipotesis_original():
    """Ninguna combinación devuelve VALIDATED. Este experimento explica un rechazo; no
    lo reabre."""
    for medias in ([10] * 5, [2, 6, 10, 14, 20], [20, 14, 10, 6, 2], [10, 10.1, 10, 10, 10]):
        v = lab.veredicto_distribucion(lab.distribucion(_dist(medias)))
        assert v["estado"] != lab.VALIDADA


def test_se_publica_el_reparto_POR_AÑO_de_cada_tramo():
    """Si un tramo vive en un año concreto, lo que mide es ese año. Sin esta columna el
    confundido de régimen sería invisible."""
    obs = _dist([10] * 5, año="2022") + _dist([10] * 5, año="2024")
    d = lab.distribucion(obs)
    assert d["tramos"][0]["por_año"] == {"2022": lab.MUESTRA_MINIMA,
                                         "2024": lab.MUESTRA_MINIMA}


def test_se_publica_CUANTO_aporta_el_10_por_ciento_mejor():
    """Si un puñado de observaciones explica la media, la media no describe a nadie."""
    d = lab.distribucion(_dist([1] * 5, n=100, cola=100000))
    assert d["tramos"][-1]["peso_del_10pct_mejor"] > 90


def test_sin_MUESTRA_el_diagnostico_tampoco_concluye():
    v = lab.veredicto_distribucion(lab.distribucion(_dist([10] * 5, n=3)))
    assert v["estado"] == lab.SIN_DATOS


def test_el_diagnostico_es_el_SEGUNDO_intento_de_la_MISMA_hipotesis():
    """No abre una línea nueva: profundiza en la que ya se rechazó. Así el contador de
    intentos dice la verdad."""
    f = lab.ficha_distribucion([], universo=["AAPL"])
    assert f["hipotesis_id"] == "DISTANCIA_MAX_A_MAXIMO_52S"
    assert f["tipo"] == "diagnostico" and f["deriva_de"]


def test_el_diagnostico_declara_el_sesgo_que_MAS_importa():
    """La supervivencia no es uniforme entre tramos, y ese es el punto."""
    c = lab.ficha_distribucion([], universo=["AAPL"])["controles"]
    assert "NO es uniforme" in c["supervivencia"]
    assert "regimen" in c and "2022" in c["regimen"]


# ── El rechazo queda registrado donde vive la verdad ─────────────────────────

def test_la_hipotesis_MEDIDA_Y_RECHAZADA_ya_no_figura_como_pendiente():
    """Si volviera a la cola de «medible», alguien la repetiría."""
    d = next(h for h in lab.hipotesis() if h["id"] == "DISTANCIA_MAX_A_MAXIMO_52S")
    assert d["estado"] == lab.RECHAZADA
    assert d["valor_actual"] is None, "rechazar NO es poner el número al revés"
    assert "RECHAZADA" in (d.get("medido") or "").upper()


def test_el_rechazo_explica_por_que_NO_se_invierte_la_regla():
    d = next(h for h in lab.hipotesis() if h["id"] == "DISTANCIA_MAX_A_MAXIMO_52S")
    medido = (d.get("medido") or "").lower()
    assert "acierto" in medido and "dispersión" in medido
    assert "supervivencia" in medido


def test_un_umbral_con_NUMERO_manda_sobre_el_texto(monkeypatch):
    """El orden importa: si alguien le pone un número, el código YA lo aplica, diga lo
    que diga el docstring."""
    monkeypatch.setattr(calibracion, "DISTANCIA_MAX_A_MAXIMO_52S", 25.0)
    d = next(h for h in lab.hipotesis() if h["id"] == "DISTANCIA_MAX_A_MAXIMO_52S")
    assert d["estado"] == lab.VALIDADA


def test_se_publica_la_AMPLITUD_de_cada_tramo():
    """Responde al confundido de volatilidad: una acción que ha caído un 60% se mueve
    más en las dos direcciones, y eso infla la media sin ser ninguna ventaja."""
    obs = []
    for i, (bajo, alto) in enumerate(lab.TRAMOS):
        ancho = 5 + i * 20                       # los tramos lejanos, más anchos
        vals = [10 - ancho, 10, 10 + ancho] * 10
        obs += [{"tramo": f"{bajo}-{alto}%", "retorno_pct": v, "fecha": "2022-01-01",
                 "symbol": "X", "distancia_pct": 1} for v in vals]
    d = lab.distribucion(obs)
    amplitudes = [t["amplitud_intercuartil"] for t in d["tramos"]]
    assert amplitudes == sorted(amplitudes), "la amplitud tiene que crecer con el tramo"
    v = lab.veredicto_distribucion(d)
    assert v["amplitud_max_pp"] > v["amplitud_min_pp"]


def test_se_dice_si_el_tramo_que_MAS_GANA_es_tambien_el_MAS_ANCHO():
    """Si lo es, la explicación está ahí y no hace falta buscar más lejos."""
    obs = []
    for i, (bajo, alto) in enumerate(lab.TRAMOS):
        ancho = 5 + i * 20
        media = 10 + i * 5                       # el último gana más Y es el más ancho
        vals = [media - ancho, media, media + ancho] * 10
        obs += [{"tramo": f"{bajo}-{alto}%", "retorno_pct": v, "fecha": "2022-01-01",
                 "symbol": "X", "distancia_pct": 1} for v in vals]
    v = lab.veredicto_distribucion(lab.distribucion(obs))
    assert v["mas_ancho_es_el_de_mas_media"] is True


# ── El corte temporal ────────────────────────────────────────────────────────
#
# El diagnóstico dejó un escalón en el tramo 0-5% y no pudo decir si era de la distancia
# al máximo o del calendario. Cinco años que incluyen un mercado bajista y su
# recuperación bastan para que «estar en máximos» y «el año que todo cayó» sean casi lo
# mismo. Estos tests protegen la herramienta que los separa.

def _años(escalon_en, años=("2022", "2023", "2024"), n=lab.MUESTRA_MINIMA + 5):
    """Observaciones por año; el tramo 0-5% sale peor solo en los años indicados."""
    obs = []
    for año in años:
        for i, (bajo, alto) in enumerate(lab.TRAMOS):
            med = 3 if (i == 0 and año in escalon_en) else 10
            obs += [{"tramo": f"{bajo}-{alto}%", "retorno_pct": med,
                     "fecha": f"{año}-05-01", "symbol": "X", "distancia_pct": 1}] * n
    return obs


def test_si_el_escalon_solo_esta_en_UN_año_es_ese_año():
    v = lab.veredicto_periodo(lab.por_periodo(_años({"2022"})))
    assert v["estado"] == lab.RECHAZADA
    assert v["años_que_repiten"] == ["2022"]
    assert "es lo que pasó en esos años" in v["conclusion"]


def test_si_el_escalon_esta_en_TODOS_los_años_gana_credibilidad_pero_no_permiso():
    v = lab.veredicto_periodo(lab.por_periodo(_años({"2022", "2023", "2024"})))
    assert v["estado"] == lab.NO_CONCLUYENTE
    assert "credibilidad, no permiso" in v["conclusion"]
    assert "supervivencia" in v["conclusion"]


def test_un_año_a_MEDIAS_se_descarta_entero():
    """Un año con tramos flacos daría medianas sobre puñados que se leerían igual que
    las demás."""
    obs = _años({"2022"}) + [{"tramo": "0-5%", "retorno_pct": 50, "fecha": "2019-05-01",
                              "symbol": "X", "distancia_pct": 1}] * 3
    d = lab.por_periodo(obs)
    assert "2019" in [x["año"] for x in d["años_descartados"]]
    assert "2019" not in [f["año"] for f in d["años"]]
    assert d["años_descartados"][0]["n_por_tramo"], "hay que decir CUÁNTO faltaba"


def test_con_POCOS_AÑOS_no_se_concluye():
    v = lab.veredicto_periodo(lab.por_periodo(_años({"2022"}, años=("2022", "2023"))))
    assert v["estado"] == lab.SIN_DATOS
    assert str(lab.AÑOS_MINIMOS) in v["conclusion"]


def test_el_corte_temporal_TAMPOCO_puede_validar():
    """Confirmar que un patrón se repite lo hace más creíble, no lo convierte en regla:
    siguen en pie la supervivencia y el hecho de que cinco años son un solo ciclo."""
    for escalon in (set(), {"2022"}, {"2022", "2023"}, {"2022", "2023", "2024"}):
        v = lab.veredicto_periodo(lab.por_periodo(_años(escalon)))
        assert v["estado"] != lab.VALIDADA


def test_el_corte_temporal_es_OTRO_intento_de_la_misma_hipotesis():
    f = lab.ficha_periodo([], universo=["AAPL"])
    assert f["hipotesis_id"] == "DISTANCIA_MAX_A_MAXIMO_52S"
    assert f["tipo"] == "corte_temporal" and f["deriva_de"]


def test_el_corte_temporal_declara_que_cinco_años_son_UN_ciclo():
    c = lab.ficha_periodo([], universo=["AAPL"])["controles"]
    assert "un_solo_ciclo" in c and "UN" in c["un_solo_ciclo"]
    assert "no lo corrige" in c["supervivencia"]
