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
    # Tras los tres experimentos el registro dice POR QUÉ no se invierte, y el argumento
    # ya no es la dispersión sino algo más fuerte: el efecto cambia de signo con el año.
    assert "acierto" in medido
    assert "signo" in medido and "régimen" in medido or "regímenes" in medido
    assert "ni el original ni el inverso" in medido


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


# ── Segunda hipótesis: la persistencia de la tendencia ──────────────────────
#
# Es de OTRA familia. Sobre «dónde está el precio respecto a un extremo» se gastaron tres
# experimentos para acabar en nada; medir lo mismo con otro nombre daría el mismo nada.

def _sube(n, paso=0.5, desde=100.0):
    return [{"close": desde + i * paso, "high": desde + i * paso,
             "date": f"2022-01-{(i % 28) + 1:02d}"} for i in range(n)]


def test_una_serie_que_SUBE_SIEMPRE_da_rachas_largas():
    obs = lab.observaciones_pendiente(_sube(200), "X")
    assert obs
    assert all(o["racha"] > 27 for o in obs)
    assert {o["tramo"] for o in obs} == {"27-999%"}


def test_una_serie_que_BAJA_da_racha_CERO():
    barras = [{"close": 200 - i * 0.5, "high": 200 - i * 0.5, "date": "2022-01-01"}
              for i in range(200)]
    obs = lab.observaciones_pendiente(barras, "X")
    assert obs and all(o["racha"] == 0 for o in obs)
    assert {o["tramo"] for o in obs} == {"0-1%"}


def test_la_racha_NO_mira_hacia_delante():
    """El mismo cuidado que en la otra hipótesis: la media del ancla usa las barras que
    terminan en ella y la racha mira hacia atrás. Si la racha viera el futuro, una serie
    que sube y luego se desploma daría rachas largas en el tramo final."""
    barras = _sube(150) + [{"close": 10, "high": 10, "date": "2023-01-01"}] * 60
    obs = lab.observaciones_pendiente(barras, "X")
    tardios = [o for o in obs if o["fecha"] == "2023-01-01"]
    assert tardios, "la serie tiene que producir observaciones en el tramo desplomado"
    assert all(o["racha"] == 0 for o in tardios)


def test_una_serie_CORTA_no_produce_observaciones():
    assert lab.observaciones_pendiente(_sube(lab.VENTANA_MEDIA), "X") == []
    assert lab.observaciones_pendiente([], "X") == []
    assert lab.observaciones_pendiente(None, "X") == []


def test_la_segunda_hipotesis_trae_las_LECCIONES_de_la_primera():
    """Mediana, cuartiles, amplitud, peso del 10% mejor Y corte por año desde la PRIMERA
    ejecución. El experimento 1 reportó solo medias y hicieron falta dos más para
    descubrir que mentían."""
    f = lab.ficha_pendiente([], universo=["AAPL"])
    r = f["resultado"]
    assert "por_periodo" in r
    assert all(k in r["tramos"][0] for k in
               ("mediana", "p25", "p75", "amplitud_intercuartil", "peso_del_10pct_mejor"))
    assert "MEDIANA" in f["metodo"]["direccion_esperada"]


def test_la_segunda_hipotesis_declara_que_la_MEDIA_no_es_la_de_produccion():
    """`tendencia.py` usa la de 200 sesiones diarias; aquí se usa la de 40 semanales, que
    cubre el mismo calendario pero suaviza distinto."""
    c = lab.ficha_pendiente([], universo=["AAPL"])["controles"]
    assert "aproximacion" in c
    assert "200 SESIONES" in c["aproximacion"] and "40 barras semanales" in c["aproximacion"]


def test_la_segunda_hipotesis_es_de_OTRA_familia():
    f = lab.ficha_pendiente([], universo=["AAPL"])
    assert f["hipotesis_id"] == "SMA200_PENDIENTE_SESIONES"
    assert f["hipotesis_id"] != "DISTANCIA_MAX_A_MAXIMO_52S"


def test_generalizar_los_tramos_NO_cambio_el_experimento_original():
    """La generalización se hizo con el valor de siempre por defecto: el experimento 1
    tiene que seguir dando exactamente lo mismo."""
    obs = _todos_los_tramos([8, 6, 4, 2, 1])
    assert lab.agregar(obs) == lab.agregar(obs, tramos=lab.TRAMOS)
    assert lab.distribucion(obs) == lab.distribucion(obs, tramos=lab.TRAMOS)


# ── El veredicto de una hipótesis nueva no es el de un diagnóstico ──────────
#
# `ficha_pendiente` reutilizó `veredicto_distribucion`, que diagnostica si un gradiente
# de MEDIAS ya encontrado vive en la cola. Aplicado a una hipótesis nueva devolvía «el
# efecto no es solo de cola» sobre algo que nunca había afirmado tener cola, y etiquetaba
# NO CONCLUYENTE lo que era un RECHAZO. Estos tests fijan la separación.

def _medianas(valores, n=lab.MUESTRA_MINIMA + 5):
    obs = []
    for (bajo, alto), med in zip(lab.TRAMOS_PENDIENTE, valores):
        obs += [{"tramo": f"{bajo}-{alto}%", "retorno_pct": med, "fecha": "2024-01-01",
                 "symbol": "X"}] * n
    return lab.distribucion(obs, tramos=lab.TRAMOS_PENDIENTE)


def test_si_las_medianas_siguen_la_direccion_fijada_se_VALIDA():
    v = lab.veredicto_direccion(_medianas([2, 5, 8, 11, 14]), creciente=True)
    assert v["estado"] == lab.VALIDADA and v["separacion_mediana_pp"] == 12.0


def test_si_NO_siguen_la_direccion_fijada_se_RECHAZA():
    """Los números REALES del primer intento: 10,29 → 9,56 → 10,30 → 13,70 → 5,79. Ni
    crecientes ni decrecientes, y con el peor tramo en el extremo."""
    v = lab.veredicto_direccion(_medianas([10.29, 9.56, 10.30, 13.70, 5.79]))
    assert v["estado"] == lab.RECHAZADA
    assert v["mejor_tramo"] == "13-27%" and v["peor_tramo"] == "27-999%"
    assert "hipótesis NUEVA" in v["conclusion"]


def test_una_curva_con_forma_de_U_INVERTIDA_no_valida_nada():
    """Aunque el dibujo sea sugerente. Verlo después de mirar los datos no es medirlo."""
    v = lab.veredicto_direccion(_medianas([5, 8, 12, 9, 4]))
    assert v["estado"] == lab.RECHAZADA


def test_sin_SEPARACION_no_se_concluye_aunque_el_orden_cuadre():
    v = lab.veredicto_direccion(_medianas([10.0, 10.1, 10.2, 10.3, 10.4]))
    assert v["estado"] == lab.NO_CONCLUYENTE


def test_el_veredicto_de_direccion_juzga_por_la_MEDIANA_no_por_la_media():
    """La lección de la hipótesis anterior. Un solo acierto enorme no puede decidir si
    una hipótesis se valida."""
    obs = []
    for i, (bajo, alto) in enumerate(lab.TRAMOS_PENDIENTE):
        vals = [10.0] * 25
        if i == 0:
            vals = vals + [100000.0]        # media altísima, mediana intacta
        obs += [{"tramo": f"{bajo}-{alto}%", "retorno_pct": v, "fecha": "2024-01-01",
                 "symbol": "X"} for v in vals]
    v = lab.veredicto_direccion(lab.distribucion(obs, tramos=lab.TRAMOS_PENDIENTE))
    assert v["estado"] == lab.NO_CONCLUYENTE       # las medianas no se mueven


def test_sin_muestra_el_veredicto_de_direccion_tampoco_concluye():
    v = lab.veredicto_direccion(_medianas([2, 5, 8, 11, 14], n=3))
    assert v["estado"] == lab.SIN_DATOS


def test_la_ficha_de_la_pendiente_usa_el_veredicto_de_DIRECCION():
    """Y no el del diagnóstico, que responde a otra pregunta."""
    import inspect
    fuente = inspect.getsource(lab.ficha_pendiente)
    assert "veredicto_direccion" in fuente
    assert "veredicto_distribucion(" not in fuente


# ── La auditoría del propio método ──────────────────────────────────────────
#
# `SEPARACION_MINIMA = 1.0` lo inventé yo. Es el listón que decide si dos tramos «se
# distinguen», y salió de que un punto porcentual parecía razonable. Si el azar lo supera
# rutinariamente con nuestra muestra, no filtra nada: cualquier validación futura sería
# ruido con formato de hallazgo. Es el error que `calibracion.py` existe para impedir,
# cometido dentro del módulo que vigila que no se cometa.

def _ruido(dias=40, por_tramo=6, semilla=7):
    """Observaciones SIN ninguna relación entre tramo y retorno."""
    import random
    r = random.Random(semilla)
    return [{"tramo": f"{b}-{a}%", "retorno_pct": round(r.gauss(10, 25), 2),
             "fecha": f"2024-{(d % 12) + 1:02d}-{(d % 28) + 1:02d}", "symbol": "X"}
            for d in range(dias) for b, a in lab.TRAMOS for _ in range(por_tramo)]


def test_barajar_conserva_el_RETORNO_y_la_FECHA_de_cada_observacion():
    """Lo único que viaja es la etiqueta del tramo. Si se moviera el retorno, se estaría
    midiendo otra cosa."""
    import random
    obs = _ruido(dias=5)
    barajada = lab.barajar_dentro_del_dia(obs, random.Random(1))
    assert len(barajada) == len(obs)
    assert (sorted((o["fecha"], o["retorno_pct"]) for o in barajada)
            == sorted((o["fecha"], o["retorno_pct"]) for o in obs))


def test_barajar_NO_mezcla_observaciones_de_FECHAS_distintas():
    """Barajar todo junto rompería que en una misma semana todas las acciones se mueven
    a la vez. Esa dependencia es real y es la que más infla el ruido: destruirla haría
    que el azar pareciera más manso y el listón saldría demasiado bajo."""
    import random
    obs = _ruido(dias=6)
    barajada = lab.barajar_dentro_del_dia(obs, random.Random(3))
    for fecha in {o["fecha"] for o in obs}:
        antes = sorted(o["tramo"] for o in obs if o["fecha"] == fecha)
        despues = sorted(o["tramo"] for o in barajada if o["fecha"] == fecha)
        assert antes == despues, "los tramos han cruzado de fecha"


def test_la_auditoria_es_DETERMINISTA():
    """Un listón que cambia con cada ejecución no es un listón."""
    obs = _ruido()
    assert lab.azar(obs, vueltas=25) == lab.azar(obs, vueltas=25)


def test_sobre_RUIDO_PURO_el_liston_de_1pp_no_filtra_nada():
    """El resultado que justifica la auditoría: sin ninguna relación real entre tramo y
    retorno, el azar produce separaciones muy por encima del punto porcentual."""
    d = lab.azar(_ruido(), vueltas=40)
    assert d["azar_p95"] > lab.SEPARACION_MINIMA
    assert d["veces_que_el_azar_supera_el_liston_pct"] > 50
    assert lab.veredicto_azar(d)["estado"] == lab.RECHAZADA


def test_el_veredicto_dice_A_CUANTO_habria_que_subirlo():
    """Decir «no vale» sin decir cuánto haría falta deja el problema donde estaba."""
    v = lab.veredicto_azar(lab.azar(_ruido(), vueltas=40))
    assert "Habría que subirlo" in v["conclusion"]
    assert "una vez de cada veinte" in v["conclusion"]


def test_el_veredicto_NO_invalida_los_rechazos_anteriores():
    """Rechazar por DIRECCIÓN no depende del listón: las medianas no seguían el orden
    fijado, y eso sigue siendo cierto suba o baje el umbral."""
    v = lab.veredicto_azar(lab.azar(_ruido(), vueltas=40))
    assert "rechazos anteriores siguen siendo válidos" in v["conclusion"]


def test_la_auditoria_NO_declara_ninguna_direccion_esperada():
    """No prueba una hipótesis: mide la herramienta. El resultado se acepta como salga."""
    f = lab.ficha_azar([], universo=["AAPL"])
    assert "Ninguna" in f["metodo"]["direccion_esperada"]
    assert f["tipo"] == "auditoria_del_metodo"
    assert f["hipotesis_id"] == "SEPARACION_MINIMA"


def test_la_auditoria_declara_que_NO_es_un_p_valor():
    """Las observaciones se solapan en el tiempo y barajar no lo arregla."""
    c = lab.ficha_azar([], universo=["AAPL"])["controles"]
    assert "no_es_un_p_valor" in c and "solapan" in c["no_es_un_p_valor"]
    assert "por_que_dentro_del_dia" in c


def test_sin_observaciones_la_auditoria_no_concluye():
    assert lab.ficha_azar([], universo=[])["estado"] == lab.SIN_DATOS


# ── El suelo de ruido manda sobre el número inventado ───────────────────────
#
# La auditoría del 15-09-2026 midió que el azar supera `SEPARACION_MINIMA = 1.0` el 100%
# de las veces: con nuestra muestra el ruido alcanza 8,26 pp una vez de cada veinte. Seis
# de las siete separaciones que habíamos discutido caben ENTERAS dentro de ese ruido.

def test_una_separacion_DENTRO_del_ruido_no_concluye_nada():
    """7,91 pp parecían mucho hasta saber que el azar llega a 8,26."""
    d = _medianas([2, 5, 8, 11, 14])              # 12 pp de separación
    assert lab.veredicto_direccion(d, umbral=20.0)["estado"] == lab.NO_CONCLUYENTE


def test_la_MISMA_separacion_concluye_o_no_segun_el_suelo():
    """El umbral no es un detalle: es lo que decide si hay hallazgo."""
    d = _medianas([2, 5, 8, 11, 14])
    assert lab.veredicto_direccion(d, umbral=5.0)["estado"] == lab.VALIDADA
    assert lab.veredicto_direccion(d, umbral=20.0)["estado"] == lab.NO_CONCLUYENTE


def test_si_el_umbral_NO_se_ha_medido_el_veredicto_lo_DICE():
    """Un umbral que nadie ha comprobado no puede presentarse como si lo hubieran
    comprobado."""
    v = lab.veredicto_direccion(_medianas([2, 5, 8, 11, 14]))
    assert v["umbral_medido"] is False
    assert "AVISO" in v["conclusion"] and "respaldo" in v["conclusion"]


def test_con_umbral_MEDIDO_no_hay_aviso():
    v = lab.veredicto_direccion(_medianas([2, 5, 8, 11, 14]), umbral=5.0)
    assert v["umbral_medido"] is True and "AVISO" not in v["conclusion"]


def test_el_suelo_de_ruido_se_MIDE_y_es_determinista():
    obs = _ruido()
    a = lab.umbral_de_ruido(obs, vueltas=30)
    assert a == lab.umbral_de_ruido(obs, vueltas=30)
    assert a > lab.SEPARACION_MINIMA, "sobre ruido puro el suelo tiene que superar el 1 pp"


def test_la_hipotesis_de_la_PENDIENTE_mide_su_propio_suelo():
    """Y no se apoya en el número inventado."""
    import inspect
    fuente = inspect.getsource(lab.ficha_pendiente)
    assert "umbral_de_ruido" in fuente and "umbral=suelo" in fuente


def test_el_respaldo_sigue_declarado_como_MALO():
    """Si alguien borra el aviso del docstring, el número vuelve a parecer medido."""
    import inspect
    fuente = inspect.getsource(lab)
    i = fuente.index("SEPARACION_MINIMA = 1.0")
    assert "me lo inventé" in fuente[max(0, i - 900):i]
    assert "8,26" in fuente[max(0, i - 900):i]


def test_la_SEPARACION_se_comprueba_ANTES_que_la_direccion():
    """Y cambia el veredicto de la segunda hipótesis, que es lo que importa aquí.

    Sus medianas —10,29 / 9,56 / 10,30 / 13,70 / 5,79— se separan 7,91 pp, y el suelo de
    ruido medido está en 8,26. Cabe entera dentro del azar.

    Con el listón inventado de 1 pp el veredicto era RECHAZADA: las medianas no seguían
    el orden fijado. Pero si la separación entera es ruido, ese «orden» no significa
    nada — una ordenación al azar se ve exactamente así. NO CONCLUYENTE es más honesto:
    no es que la hipótesis sea falsa, es que con esta muestra no se puede saber.
    """
    d = _medianas([10.29, 9.56, 10.30, 13.70, 5.79])
    assert lab.veredicto_direccion(d, umbral=1.0)["estado"] == lab.RECHAZADA
    assert lab.veredicto_direccion(d, umbral=8.26)["estado"] == lab.NO_CONCLUYENTE


def test_por_encima_del_suelo_SI_se_juzga_la_direccion():
    """La primera hipótesis: 16,08 pp de separación de MEDIAS, por encima de 8,26, y en
    la dirección contraria a la fijada. Ese rechazo sí sobrevive."""
    d = _medianas([8.66, 12.72, 12.87, 13.11, 24.74])
    assert lab.veredicto_direccion(d, creciente=False, umbral=8.26)["estado"] == lab.RECHAZADA


def test_el_veredicto_del_registro_sale_de_la_CABECERA_y_no_del_texto():
    """Una corrección que explica lo que corrige no puede clasificarse por las palabras
    que cita. El texto de la segunda hipótesis dice «NO CONCLUYENTE — se registró primero
    como RECHAZADA», y buscando en todo el párrafo el registro leía la segunda."""
    d = next(h for h in lab.hipotesis() if h["id"] == "SMA200_PENDIENTE_SESIONES")
    assert d["estado"] == lab.NO_CONCLUYENTE
    assert "RECHAZADA" in (d.get("medido") or "").upper(), \
        "el texto TIENE que seguir mencionando la palabra, o este test no prueba nada"


def test_la_primera_hipotesis_sigue_RECHAZADA():
    """Su separación de medias (16,08 pp) supera el suelo de ruido de 8,26 y va en la
    dirección contraria a la fijada. Ese rechazo sí se sostiene."""
    d = next(h for h in lab.hipotesis() if h["id"] == "DISTANCIA_MAX_A_MAXIMO_52S")
    assert d["estado"] == lab.RECHAZADA
    assert "8,26" in (d.get("medido") or ""), "el suelo medido tiene que quedar escrito"


def test_ninguna_hipotesis_MEDIDA_vuelve_a_la_cola_de_pendientes():
    """Ni rechazada ni no concluyente: las dos están medidas y no hay que repetirlas a
    ciegas."""
    for cual in ("DISTANCIA_MAX_A_MAXIMO_52S", "SMA200_PENDIENTE_SESIONES"):
        d = next(h for h in lab.hipotesis() if h["id"] == cual)
        assert d["estado"] != lab.LISTA and d["valor_actual"] is None


# ── Tercera hipótesis: ¿aguantan las zonas fuertes? ─────────────────────────
#
# La primera pregunta que hacemos donde el instrumento tiene una posibilidad real: el
# resultado es binario, hay miles de toques y el evento es local. Y afecta a algo que ya
# se enseña en pantalla — «Nivel fuerte (78/100)» nunca se ha comprobado.

def _toques(probs=(0.40, 0.55, 0.70), por_fecha=6, fechas=60, semilla=2):
    import random
    r = random.Random(semilla)
    regs = []
    for d in range(fechas):
        for cubo, p in zip(lab.CUBOS_FUERZA, probs):
            for _ in range(por_fecha):
                regs.append({"anchor": f"202{3 + d // 24}-{(d % 12) + 1:02d}-01",
                             "bucket": cubo, "held": r.random() < p,
                             "clean": r.random() < p})
    return regs


def test_un_nivel_que_NO_se_toco_no_cuenta():
    """No aguantó ni se rompió. Contarlo de cualquiera de las dos formas sería inventar
    el dato."""
    regs = _toques() + [{"anchor": "2024-01-01", "bucket": "fuerte", "held": None,
                         "clean": None}] * 50
    d = lab.aguante_por_cubo(regs)
    assert d["n"] == len(_toques()), "los no resueltos se han colado en la cuenta"


def test_si_las_fuertes_aguantan_MAS_se_valida():
    regs = _toques()
    v = lab.veredicto_aguante(lab.aguante_por_cubo(regs),
                              lab.azar_del_aguante(regs, vueltas=30))
    assert v["estado"] == lab.VALIDADA
    assert v["aguantes"]["fuerte"] > v["aguantes"]["debil"]
    assert v["rango_pp"] > v["suelo_de_ruido_pp"]


def test_si_el_orden_es_el_CONTRARIO_se_rechaza():
    """Sería un resultado grave: el número que la pantalla llama «fuerza» ordenaría las
    zonas al revés de lo bien que aguantan."""
    regs = _toques(probs=(0.75, 0.55, 0.35))
    v = lab.veredicto_aguante(lab.aguante_por_cubo(regs),
                              lab.azar_del_aguante(regs, vueltas=30))
    assert v["estado"] == lab.RECHAZADA
    assert "no ordena las zonas" in v["conclusion"]


def test_si_los_tres_cubos_aguantan_IGUAL_no_se_concluye():
    """La puntuación no queda demostrada, y tampoco desmentida."""
    regs = _toques(probs=(0.55, 0.55, 0.55))
    v = lab.veredicto_aguante(lab.aguante_por_cubo(regs),
                              lab.azar_del_aguante(regs, vueltas=30))
    assert v["estado"] == lab.NO_CONCLUYENTE
    # El texto cambió al añadir la cota superior: con muestra grande, «no concluyente»
    # ya no es un «no sé» a secas.
    assert "NO ordena las zonas" in v["conclusion"]


def test_sin_MUESTRA_en_algun_cubo_no_se_concluye():
    regs = _toques(por_fecha=1, fechas=3)
    v = lab.veredicto_aguante(lab.aguante_por_cubo(regs),
                              lab.azar_del_aguante(regs, vueltas=5))
    assert v["estado"] == lab.SIN_DATOS


def test_el_suelo_de_ruido_del_aguante_es_DETERMINISTA():
    regs = _toques()
    assert lab.azar_del_aguante(regs, vueltas=20) == lab.azar_del_aguante(regs, vueltas=20)


def test_barajar_el_aguante_respeta_la_FECHA():
    """En un mismo día el mercado entero empuja igual. Romper eso haría que el azar
    pareciera más manso y el suelo saldría bajo."""
    import inspect
    fuente = inspect.getsource(lab.azar_del_aguante)
    assert 'por_fecha.setdefault(r.get("anchor")' in fuente


def test_la_DIRECCION_esperada_no_la_elegi_yo():
    """Es lo que afirma el propio número que la pantalla enseña: si dice «Nivel fuerte
    (78/100)», las fuertes tienen que aguantar más."""
    f = lab.ficha_aguante(_toques(), universo=["AAPL"])
    assert "no la elegí yo" in f["metodo"]["direccion_esperada"]
    assert "ANTES" in f["metodo"]["direccion_esperada"]


def test_la_ficha_del_aguante_declara_POR_QUE_tiene_mas_fuerza():
    c = lab.ficha_aguante(_toques(), universo=["AAPL"])["controles"]
    assert "por_que_esta_pregunta_tiene_mas_fuerza" in c
    assert "binario" in c["por_que_esta_pregunta_tiene_mas_fuerza"]
    assert "solo_los_tocados" in c


def test_el_aguante_NO_reimplementa_el_backtest():
    """`backtest.py` lleva meses haciendo el walk-forward sin lookahead. Aquí solo se le
    pone la disciplina alrededor."""
    f = lab.ficha_aguante(_toques(), universo=["AAPL"])
    assert "backtest.backtest_universe" in f["metodo"]["motor"]

    # Se comprueba el HECHO, no la palabra: la primera versión buscaba «_walk_forward» en
    # el fichero y fallaba porque el docstring lo CITA para decir quién garantiza el
    # leakage. Lo que de verdad importa es que el laboratorio no pueda calcular zonas por
    # su cuenta — sin pandas ni `levels_engine` no hay forma de reimplementar el motor.
    import ast as _ast
    import inspect
    arbol = _ast.parse(inspect.getsource(lab))
    importados = set()
    for n in _ast.walk(arbol):
        if isinstance(n, _ast.Import):
            importados.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, _ast.ImportFrom) and n.module:
            importados.add(n.module.split(".")[0])
    assert not importados & {"pandas", "numpy", "levels_engine", "indicators"}, importados


# ── No saber por falta de muestra ≠ saber que es pequeño ────────────────────
#
# El experimento del aguante salió NO CONCLUYENTE con 1.136 toques y 0,8 pp de
# separación sobre un suelo de 5,7. Esa etiqueta se queda corta: con esa muestra, un
# efecto mayor que el suelo se habría visto. Es una cota superior, y es información.

def test_con_MUESTRA_GRANDE_el_veredicto_da_una_COTA_SUPERIOR():
    regs = _toques(probs=(0.55, 0.55, 0.55), por_fecha=6, fechas=60)
    v = lab.veredicto_aguante(lab.aguante_por_cubo(regs),
                              lab.azar_del_aguante(regs, vueltas=25))
    assert v["estado"] == lab.NO_CONCLUYENTE
    assert v["cota_superior_pp"] == v["suelo_de_ruido_pp"]
    assert "se habría visto" in v["conclusion"]
    assert "más pequeño que eso" in v["conclusion"]


def test_con_muestra_CORTA_no_se_acota_nada():
    """Ahí sí es un «no sé» a secas, y el veredicto no puede fingir otra cosa."""
    regs = _toques(probs=(0.55, 0.55, 0.55), por_fecha=1, fechas=25)
    v = lab.veredicto_aguante(lab.aguante_por_cubo(regs),
                              lab.azar_del_aguante(regs, vueltas=15))
    if v["estado"] == lab.NO_CONCLUYENTE:
        assert "tampoco se puede acotar" in v["conclusion"]


def test_el_hallazgo_queda_escrito_DONDE_VIVE_EL_NUMERO():
    """No en una tabla aparte. Quien lea `levels_engine` para tocar el score tiene que
    encontrarse con la medida delante."""
    import inspect
    import levels_engine
    fuente = inspect.getsource(levels_engine)
    i = fuente.index("strength = int(min(100")
    contexto = fuente[max(0, i - 2000):i]
    assert "MEDIDO el 15-09-2026" in contexto
    assert "88,0%" in contexto and "5,7 pp" in contexto
    assert "SATURA" in contexto, "hay que decir POR QUÉ no separó"


def test_se_dice_que_la_metrica_LIMPIA_no_estaba_pre_registrada():
    """Mirarla ahora sería elegir la métrica después de ver los datos."""
    import inspect
    import levels_engine
    fuente = inspect.getsource(levels_engine)
    assert "no estaba" in fuente and "pre-registrada" in fuente
    assert "Necesita su propio experimento" in fuente


# ── La réplica fuera de muestra ─────────────────────────────────────────────
#
# Cambiar de métrica al ver que la primera no separaba es cómo se fabrica un hallazgo
# falso. Por eso la segunda se mide sobre OTROS símbolos: dato nuevo para una pregunta
# ya formulada, no el mismo dato mirado dos veces.

def _toques_limpios(probs=(0.30, 0.45, 0.33), por_fecha=6, fechas=60, semilla=5):
    import random
    r = random.Random(semilla)
    return [{"anchor": f"2024-{(d % 12) + 1:02d}-01", "bucket": c,
             "held": True, "clean": r.random() < p}
            for d in range(fechas) for c, p in zip(lab.CUBOS_FUERZA, probs)
            for _ in range(por_fecha)]


def test_la_metrica_LIMPIA_se_mide_de_verdad_y_no_la_de_aguantar():
    """Con `held` a True en todos, la de aguantar no separaría nada. Si el experimento
    mirara esa, saldría plano pase lo que pase."""
    regs = _toques_limpios()
    d = lab.aguante_por_cubo(regs, metrica="clean")
    tasas = {c["cubo"]: c["aguante_pct"] for c in d["cubos"]}
    assert tasas["media"] > tasas["fuerte"], "la muestra tiene que reproducir el patrón"
    assert lab.aguante_por_cubo(regs, metrica="held")["cubos"][0]["aguante_pct"] == 100.0


def test_la_columna_de_limpio_NO_se_duplica_cuando_ya_es_la_metrica():
    """Repetir el mismo número en dos columnas los haría parecer dos medidas."""
    d = lab.aguante_por_cubo(_toques_limpios(), metrica="clean")
    assert all(c["aguante_limpio_pct"] is None for c in d["cubos"])
    d2 = lab.aguante_por_cubo(_toques_limpios(), metrica="held")
    assert all(c["aguante_limpio_pct"] is not None for c in d2["cubos"])


def test_la_replica_prueba_la_direccion_DEL_SCORE_y_no_la_que_se_vio():
    """Fijar como hipótesis lo que ya se ha visto es hacerse trampas al solitario."""
    f = lab.ficha_aguante_limpio(_toques_limpios(), universo=["X"])
    d = f["metodo"]["direccion_esperada"]
    assert "débil < media < fuerte" in d
    assert "NO «media es la mejor»" in d and "trampas" in d


def test_la_replica_declara_que_es_la_SEGUNDA_metrica_probada():
    """Dos intentos dan el doble de oportunidades a que algo salga por azar, y el
    resultado hay que leerlo con esa cifra delante."""
    c = lab.ficha_aguante_limpio(_toques_limpios(), universo=["X"])["controles"]
    assert "hipotesis_probadas" in c and "SEGUNDA" in c["hipotesis_probadas"]
    assert "fuera_de_muestra" in c and "dato nuevo" in c["fuera_de_muestra"]


def test_la_replica_es_OTRO_intento_de_la_misma_hipotesis():
    f = lab.ficha_aguante_limpio(_toques_limpios(), universo=["X"])
    assert f["hipotesis_id"] == "FUERZA_DE_LAS_ZONAS"
    assert f["tipo"] == "replica_fuera_de_muestra" and f["deriva_de"]


def test_si_la_replica_reproduce_el_patron_se_RECHAZA():
    """«Media es la mejor» no es la dirección del score, así que sale rechazada — y eso
    SÍ sería una réplica del patrón, que es lo que merecería mirarse."""
    f = lab.ficha_aguante_limpio(_toques_limpios(), universo=["X"])
    assert f["estado"] == lab.RECHAZADA
    assert f["resultado"]["ruido"]["observado_pp"] > f["resultado"]["ruido"]["azar_p95_pp"]


def test_si_la_replica_sale_PLANA_no_se_concluye():
    f = lab.ficha_aguante_limpio(_toques_limpios(probs=(0.35, 0.35, 0.35)), universo=["X"])
    assert f["estado"] == lab.NO_CONCLUYENTE
