"""El menú del móvil no puede quedar atrapado dentro de la cabecera.

El cajón se pinta desde `Header.jsx`, que lleva `backdrop-blur`. Un backdrop-filter crea
BLOQUE CONTENEDOR para los descendientes `fixed`: el cajón dejaba de medirse contra la
pantalla y pasaba a medirse contra la cabecera, así que su fondo llegaba solo hasta el
logo y los enlaces se desbordaban sin fondo, escritos encima de la página.

Vive en pytest y no en la suite del frontend porque es una comprobación de CÓDIGO, no de
render: lo que hay que impedir es que alguien vuelva a poner el cajón en el árbol de la
cabecera sin portal. Un test de render con jsdom no lo vería — jsdom no aplica
backdrop-filter y el cajón "funcionaría" allí igual de mal que en el móvil.

Ejecutar:  cd backend && pytest tests/test_menu_movil.py -v
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "frontend/src"
RAIL = (SRC / "components/Rail.jsx").read_text(encoding="utf-8")
HEADER = (SRC / "components/Header.jsx").read_text(encoding="utf-8")


def _cajon() -> str:
    return RAIL[RAIL.index("export function RailCajon"):]


def test_el_cajon_sale_a_document_body():
    """Sin portal, cualquier `backdrop-filter`, `transform`, `filter` o `contain` de un
    ancestro vuelve a atraparlo."""
    cajon = _cajon()
    assert "createPortal(" in cajon
    assert "document.body," in cajon


def test_el_cajon_sigue_cubriendo_la_pantalla():
    """El síntoma era justo este: `fixed inset-0` medido contra la cabecera."""
    assert "fixed inset-0" in _cajon()


def test_la_cabecera_que_lo_pinta_sigue_teniendo_el_filtro():
    """Si un día se quita el blur, este test cae y avisa de que el portal ya no es
    obligatorio por ESTE motivo — no de que se pueda quitar sin pensar."""
    cabecera = HEADER[HEADER.index("<header"):]
    cabecera = cabecera[:cabecera.index(">")]
    assert "backdrop-blur" in cabecera
    assert "<RailCajon" in HEADER, "el cajón se pinta desde dentro de la cabecera"


def test_con_el_cajon_abierto_el_fondo_no_se_desplaza():
    """En el móvil, arrastrar sobre el velo movía la página de detrás."""
    cajon = _cajon()
    assert 'document.body.style.overflow = "hidden"' in cajon
    assert "document.body.style.overflow = previo" in cajon, "hay que devolverlo al cerrar"


def test_el_cajon_se_cierra_con_escape():
    assert re.search(r'e\.key === "Escape"', _cajon())
