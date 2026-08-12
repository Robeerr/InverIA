"""Una alerta de COMPRA no puede salir solo porque el precio tocó un soporte.

EL AXIOMA QUE PROTEGE ESTE FICHERO

    Un soporte puede decirte dónde sería interesante comprar.
    Nunca puede decirte que debes comprar.

Antes de este veto, `signal_table` disparaba una alerta etiquetada COMPRA en cuanto el
precio cruzaba un nivel de la Cartera. Cero condiciones de tendencia: una búsqueda de
`sma200` o `tendencia` en todo el fichero devolvía cero coincidencias. Una acción en
caída libre generaba un mensaje que ponía COMPRA cada vez que atravesaba uno de sus
soportes — que es exactamente lo que hace una acción en caída libre.

POR QUÉ SE COMPRUEBA SOBRE EL CÓDIGO Y NO EJECUTANDO EL BUCLE

El disparo vive dentro de `signal_worker_loop`, que necesita Mongo, cotizaciones en
vivo y horario de mercado. Montar todo eso en un test probaría sobre todo el montaje.
Lo que hay que proteger es una propiedad de la FORMA del bucle —que el veto está, que
está antes del cooldown y que no alcanza a las ventas—, y eso se ve mejor en el orden
del código. Es el mismo criterio que ya sigue `test_coste_pagina_accion.py`.

La lógica de la regla en sí ya está probada aparte, en `test_tendencia.py`.
"""
import os
import re

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _fuente(nombre: str) -> str:
    with open(os.path.join(_AQUI, "..", nombre), encoding="utf-8") as f:
        return f.read()


SRC = _fuente("signal_table.py")


def _sin_comentarios(src: str) -> str:
    """El código que se ejecuta, sin docstrings ni comentarios.

    Necesario porque el propio texto que explica el veto menciona «COMPRA», «tendencia»
    y «venta», y sin quitarlo los tests estarían leyendo la explicación en vez del
    comportamiento.
    """
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    return re.sub(r"#.*", "", src)


CODIGO = _sin_comentarios(SRC)


def _bloque_compras() -> str:
    """El cuerpo del bucle de niveles de COMPRA, hasta que empieza el de ventas."""
    ini = CODIGO.index('for level_key, target in buy_levels.items():')
    fin = CODIGO.index('for level_key, target in sell_levels.items():')
    assert ini < fin
    return CODIGO[ini:fin]


def _bloque_ventas() -> str:
    ini = CODIGO.index('for level_key, target in sell_levels.items():')
    return CODIGO[ini:ini + 2500]


# ── El veto existe y está en el sitio correcto ───────────────────────────────

def test_las_compras_consultan_la_tendencia():
    assert "_contexto_alerta" in _bloque_compras()


def test_las_compras_paran_si_la_tendencia_no_es_valida():
    bloque = _bloque_compras()
    assert "hay_tendencia_valida" in bloque
    # `continue` inmediatamente después: la alerta no se emite, no se degrada.
    veto = bloque[bloque.index("hay_tendencia_valida"):]
    assert "continue" in veto[:400]


def test_el_veto_va_antes_del_cooldown():
    """Si se marcara el cooldown y luego se vetara, el nivel quedaría quemado por hoy:
    la alerta no saldría tampoco si la tendencia se arreglase en la misma sesión."""
    bloque = _bloque_compras()
    assert bloque.index("hay_tendencia_valida") < bloque.index("_set_cooldown")


def test_el_veto_va_antes_de_disparar():
    bloque = _bloque_compras()
    assert bloque.index("hay_tendencia_valida") < bloque.index("_fire_alert")


# ── Y NO alcanza a las ventas ────────────────────────────────────────────────

def test_las_ventas_no_exigen_tendencia_alcista():
    """Callarse ante una salida porque la acción ya no es alcista sería el error
    inverso, y más caro: es justo cuando hay que avisar."""
    ventas = _bloque_ventas()
    assert "hay_tendencia_valida" not in ventas
    assert "_contexto_alerta" not in ventas


# ── El volumen sigue siendo informativo ──────────────────────────────────────

def test_el_volumen_no_condiciona_el_disparo():
    """`vol_ratio` viaja en el mensaje, pero no filtra. Convertirlo en condición exige
    decidir a partir de qué ratio un rebote «tiene volumen», y ese número hay que
    medirlo antes de ponerlo a bloquear alertas."""
    bloque = _bloque_compras()
    assert "vol_ratio" in bloque, "debe seguir calculándose y viajando en la alerta"
    corte = bloque[bloque.index("vol_ratio"):bloque.index("_fire_alert")]
    for comparacion in ("vol_ratio <", "vol_ratio >", "vol_ratio ==", "vol_ratio is None and"):
        assert comparacion not in corte, f"'{comparacion}' convertiría el volumen en filtro"


# ── Una sola descarga, y con histórico suficiente ────────────────────────────

def test_el_contexto_pide_historico_largo_no_tres_meses():
    """Con «3M» son unas 126 sesiones: no hay 200 cierres, la tendencia saldría siempre
    SIN_DATOS y el veto quedaría inservible en silencio — bloqueando TODAS las alertas
    en vez de las de acciones bajistas."""
    cuerpo = CODIGO[CODIGO.index("async def _contexto_alerta"):]
    cuerpo = cuerpo[:cuerpo.index("\n\n\n")] if "\n\n\n" in cuerpo else cuerpo[:1800]
    assert '"1D"' in cuerpo
    assert '"3M"' not in cuerpo


def test_una_sola_descarga_por_alerta():
    """Tendencia y volumen salen del MISMO DataFrame. Dos llamadas a `get_stock_data`
    doblarían el coste de cada alerta sin aportar nada."""
    cuerpo = CODIGO[CODIGO.index("async def _contexto_alerta"):]
    cuerpo = cuerpo[:cuerpo.index("\n\n\n")] if "\n\n\n" in cuerpo else cuerpo[:1800]
    assert cuerpo.count("get_stock_data") == 1


def test_no_se_llama_a_finnhub_para_esto():
    """El veto se paga con histórico gratuito. Si alguien lo cambiara por una fuente con
    cuota, cada alerta pasaría a costar dinero."""
    cuerpo = CODIGO[CODIGO.index("async def _contexto_alerta"):]
    cuerpo = cuerpo[:cuerpo.index("\n\n\n")] if "\n\n\n" in cuerpo else cuerpo[:1800]
    assert "finnhub" not in cuerpo.lower()
