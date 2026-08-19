"""Cuando el veto corta una edición, la pantalla lo DICE.

El veto de tendencia es una decisión de producto ("la estructura manda sobre la IA"), no
un error. Pero editar el precio de un nivel en la Cartera pasa por la puerta de tendencia,
y sobre una acción vetada el servidor responde 409 con el motivo dentro:

    {"error": "vetado_por_tendencia", "symbol": ..., "mensaje": ...}

La pantalla hacía `if (!r.ok) throw new Error()` y lo convertía todo en "Error al
guardar". El usuario veía un mensaje que no explicaba nada, sobre algo que no estaba roto.

Que el motivo llegue no basta si nadie lo pinta. Eso es lo que se fija aquí.

Lo que este archivo NO pide es una salida en la pantalla: el escape del 409 es del
usuario, y otra frontera (test_veto_cartera) exige que ningún cliente lo envíe.

Ejecutar:  cd backend && pytest tests/test_veto_se_explica.py -v
"""
from pathlib import Path

import server

SRC = Path(server.__file__).resolve().parent.parent / "frontend/src"
CARTERA = (SRC / "pages/SignalsView.jsx").read_text(encoding="utf-8")


def _update_field() -> str:
    i = CARTERA.index("const updateField =")
    return CARTERA[i:CARTERA.index("\n  const deleteEntry", i)]


def test_el_servidor_manda_el_motivo_estructurado():
    """La otra mitad del contrato. Si esto cambia, lo de la pantalla deja de valer."""
    src = Path(server.__file__).read_text(encoding="utf-8")
    assert '"error": "vetado_por_tendencia"' in src
    assert '"mensaje": est["motivo"]' in src


def test_la_pantalla_lee_el_motivo_en_vez_de_tirarlo():
    cuerpo = _update_field()
    assert "vetado_por_tendencia" in cuerpo, "el 409 del veto hay que reconocerlo"
    assert "detalle.mensaje" in cuerpo, "y hay que PINTAR el motivo que trae"


def test_la_pantalla_no_se_salta_el_veto_por_su_cuenta():
    """El escape del 409 existe, pero es del usuario y no de la pantalla: hay otra
    frontera (test_veto_cartera) que exige que ningún cliente lo envíe. Un "guardar
    igualmente" junto al aviso convertiría el veto en un trámite de un clic."""
    assert "vetado_por_tendencia" in _update_field()
    assert "toast.warning" in _update_field(), "se AVISA, no se guarda a escondidas"


def test_el_mensaje_generico_deja_de_ser_la_unica_respuesta():
    cuerpo = _update_field()
    assert "r.json()" in cuerpo, "hay que leer el cuerpo de la respuesta fallida"
    assert "throw new Error()" not in cuerpo, "eso descartaba lo que dijera el servidor"
