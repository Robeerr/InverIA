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


def test_un_umbral_SIN_numero_es_una_hipotesis_y_no_una_regla():
    d = next(h for h in lab.hipotesis() if h["id"] == "DISTANCIA_MAX_A_MAXIMO_52S")
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
