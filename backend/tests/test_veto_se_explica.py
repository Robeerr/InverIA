"""Cuando el veto corta una edición, la pantalla lo DICE.

El veto de tendencia es una decisión de producto ("la estructura manda sobre la IA"), no
un error. Dar de alta una acción vetada CON niveles de compra se rechaza con un 409 que
lleva el motivo dentro:

    {"error": "vetado_por_tendencia", "symbol": ..., "mensaje": ...}

El alta trataba CUALQUIER 409 como "ya estaba en tu Cartera" —el otro 409 del endpoint— y
cerraba el formulario dando el alta por buena. Un rechazo leído como éxito, con la acción
sin dar de alta y sin que nadie se enterara. Es exactamente el fallo que ya había pasado en
ChartistPanel y por el que el servidor manda el motivo ESTRUCTURADO en vez de en prosa.

Que el motivo llegue no basta si nadie lo distingue. Eso es lo que se fija aquí.

Lo que este archivo NO pide es una salida en la pantalla: el escape del 409 es del
usuario, y otra frontera (test_veto_cartera) exige que ningún cliente lo envíe.

Ejecutar:  cd backend && pytest tests/test_veto_se_explica.py -v
"""
from pathlib import Path

import server

SRC = Path(server.__file__).resolve().parent.parent / "frontend/src"
CARTERA = (SRC / "pages/SignalsView.jsx").read_text(encoding="utf-8")


def _sin_comentarios(js: str) -> str:
    """Quita las líneas `//`.

    Sin esto, un test de ORDEN mide el orden de la prosa: el comentario de `addEntry`
    nombra "ya estaba en tu Cartera" mucho antes de que el código lo compruebe, y la
    aserción daba por bueno —o por malo— algo que no había leído.
    """
    return "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))


def _add_entry() -> str:
    i = CARTERA.index("const addEntry = async")
    return _sin_comentarios(CARTERA[i:CARTERA.index("\n  };", i)])


def _update_field() -> str:
    i = CARTERA.index("const updateField =")
    return _sin_comentarios(CARTERA[i:CARTERA.index("\n  const deleteEntry", i)])


def test_el_servidor_manda_el_motivo_estructurado():
    """La otra mitad del contrato. Si esto cambia, lo de la pantalla deja de valer."""
    src = Path(server.__file__).read_text(encoding="utf-8")
    assert '"error": "vetado_por_tendencia"' in src
    assert '"mensaje": est["motivo"]' in src


def test_el_alta_distingue_los_dos_409():
    cuerpo = _add_entry()
    assert "vetado_por_tendencia" in cuerpo, "el 409 del veto hay que reconocerlo"
    assert "detalle.mensaje" in cuerpo, "y hay que PINTAR el motivo que trae"
    assert cuerpo.index("vetado_por_tendencia") < cuerpo.index("ya estaba en tu Cartera"), (
        "el veto se comprueba ANTES: si no, un rechazo se lee como duplicado")


def test_un_alta_rechazada_no_cierra_el_formulario():
    """Cerrarlo diría "hecho" sobre algo que no se ha hecho."""
    cuerpo = _add_entry()
    veto = cuerpo[cuerpo.index("vetado_por_tendencia"):cuerpo.index("ya estaba en tu Cartera")]
    assert "toast.warning" in veto
    assert "setShowAdd(false)" not in veto


def test_la_pantalla_no_se_salta_el_veto_por_su_cuenta():
    """El escape del 409 existe, pero es del usuario y no de la pantalla: hay otra
    frontera (test_veto_cartera) que exige que ningún cliente lo envíe."""
    assert "forzar" not in CARTERA


def test_el_mensaje_generico_deja_de_ser_la_unica_respuesta():
    for cuerpo in (_update_field(), _add_entry()):
        assert "r.json()" in cuerpo, "hay que leer el cuerpo de la respuesta fallida"
        assert "throw new Error()" not in cuerpo, "eso descartaba lo que dijera el servidor"


def test_editar_un_nivel_ya_no_pasa_por_la_puerta():
    """El alcance nuevo, visto desde la pantalla: el PATCH no puede recibir un veto, así
    que tratarlo aquí sería código muerto guardando una frontera que ya no existe."""
    assert "vetado_por_tendencia" not in _update_field()
