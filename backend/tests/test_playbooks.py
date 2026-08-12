"""Los playbooks no se mezclan, y una etiqueta técnica no es una clasificación.

DOS COSAS DISTINTAS SE PROTEGEN AQUÍ

1. Que ningún score sume componentes de estrategias incompatibles. Ya cometimos ese
   error —`_potential_score` suma valoración barata y momentum en el mismo número— y
   este fichero existe para que no se repita por otro camino.

2. Que el carril técnico (`playbook`) no se confunda con la clasificación validada
   (`playbook_observado`). Confundirlos etiquetaría mil señales antiguas como
   LEADER_PULLBACK y el experimento D mediría un playbook que ninguna de ellas siguió.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import playbooks  # noqa: E402


# ── Qué puede emitir ─────────────────────────────────────────────────────────

def test_solo_leader_pullback_esta_activo():
    assert playbooks.ACTIVOS == (playbooks.LEADER_PULLBACK,)


def test_los_inactivos_no_pueden_emitir_senal():
    for hipotesis in (playbooks.BREAKOUT, playbooks.RECOVERY, playbooks.VALUE_MEAN_REVERSION):
        assert playbooks.puede_emitir_senal(hipotesis) is False, hipotesis
        with pytest.raises(ValueError):
            playbooks.campos_de_senal(hipotesis)


def test_un_playbook_desconocido_tampoco_emite():
    """Fallo cerrado, igual que en tendencia.py: si alguien inventa un playbook y olvida
    activarlo, que no emita nada es más seguro que que emita sin control."""
    assert playbooks.puede_emitir_senal("SCALPING") is False
    assert playbooks.puede_emitir_senal(None) is False


def test_cada_hipotesis_dice_que_le_falta():
    """Un «playbook inactivo» a secas obliga a leer el código para saber qué falta."""
    for hipotesis in (playbooks.BREAKOUT, playbooks.RECOVERY, playbooks.VALUE_MEAN_REVERSION):
        motivo = playbooks.motivo_de_inactividad(hipotesis)
        assert motivo and len(motivo) > 40, hipotesis
    assert playbooks.motivo_de_inactividad(playbooks.LEADER_PULLBACK) is None


# ── Carril ≠ clasificación ───────────────────────────────────────────────────

def test_una_senal_nueva_lleva_carril_pero_no_clasificacion():
    """El punto entero del módulo. Que ponga LEADER_PULLBACK no significa que la señal
    cumpla ese playbook: su SETUP y su TRIGGER ni siquiera están definidos."""
    c = playbooks.campos_de_senal()
    assert c["playbook"] == playbooks.LEADER_PULLBACK
    assert c["playbook_observado"] == playbooks.NO_OBSERVADO
    assert c["playbook_inferido"] is False


def test_hoy_no_se_puede_observar_nada():
    """Mientras SETUP y TRIGGER no existan, no hay nada contra lo que comprobar. Cuando
    este test empiece a estorbar será porque ya se han definido — y entonces habrá que
    cambiarlo a conciencia, no de pasada."""
    assert playbooks.campos_de_senal()["playbook_observado"] == playbooks.NO_OBSERVADO


def test_un_historico_sin_campo_queda_marcado_como_inferido():
    d = playbooks.campos_por_compatibilidad({"symbol": "AAPL"})
    assert d["playbook"] == playbooks.LEADER_PULLBACK
    assert d["playbook_inferido"] is True
    assert d["playbook_observado"] == playbooks.NO_OBSERVADO


def test_la_compatibilidad_no_pisa_un_campo_existente():
    d = playbooks.campos_por_compatibilidad(
        {"symbol": "AAPL", "playbook": playbooks.LEADER_PULLBACK})
    assert d["playbook_inferido"] is False


def test_la_compatibilidad_no_muta_el_original():
    original = {"symbol": "AAPL"}
    playbooks.campos_por_compatibilidad(original)
    assert "playbook" not in original


# ── El experimento no se contamina ───────────────────────────────────────────

def test_una_senal_inferida_no_entra_en_el_experimento():
    inferida = playbooks.campos_por_compatibilidad({"symbol": "AAPL"})
    assert playbooks.apto_para_experimento(inferida) is False


def test_una_senal_sin_observar_tampoco_entra():
    assert playbooks.apto_para_experimento(playbooks.campos_de_senal()) is False


def test_hoy_nada_es_apto_y_eso_es_correcto():
    """No tenemos ni una señal clasificada. Que el filtro esté puesto antes de que haya
    nada que filtrar es el objetivo, no un defecto."""
    docs = [playbooks.campos_de_senal(),
            playbooks.campos_por_compatibilidad({"symbol": "MSFT"}),
            {"symbol": "NVDA"}]
    assert not any(playbooks.apto_para_experimento(d) for d in docs)


def test_lo_no_clasificable_se_cuenta_aparte_no_se_reparte():
    """Un grupo «resto» que se ignora en silencio es la forma más fácil de que el
    experimento mida otra cosa distinta de la que dice medir."""
    docs = [playbooks.campos_por_compatibilidad({"symbol": "A"}),
            {"symbol": "B", "playbook_observado": playbooks.LEADER_PULLBACK},
            {"symbol": "C"}]
    grupos = playbooks.agrupar_por_observado(docs)
    assert len(grupos[playbooks.LEADER_PULLBACK]) == 1
    assert len(grupos[playbooks.NO_OBSERVADO]) == 2
    total = sum(len(v) for v in grupos.values())
    assert total == len(docs), "ninguna señal puede perderse por el camino"


# ── Ningún score cruzado ─────────────────────────────────────────────────────

def _fuente(nombre: str) -> str:
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", nombre)
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def _solo_codigo(src: str) -> str:
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    src = re.sub(r"#.*", "", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    return re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)


def test_el_modulo_no_puntua_nada():
    """`playbooks.py` enruta; no evalúa. Si aquí aparece un score, el módulo ha empezado
    a decidir y deja de ser infraestructura."""
    codigo = _solo_codigo(_fuente("playbooks.py")).lower()
    # Con límites de palabra: sin ellos, «rsi» casa dentro de «mean_reveRSIon» y «atr»
    # dentro de cualquier palabra que las contenga. Un test que falla por una coincidencia
    # de letras enseña a ignorarlo, que es peor que no tenerlo.
    for prohibido in ("score", "puntos", "umbral", "rsi", "atr", "sma"):
        assert not re.search(rf"\b{prohibido}\b", codigo), \
            f"'{prohibido}' no pertenece a este módulo"


def test_no_existe_ninguna_funcion_que_agregue_dos_playbooks():
    """La prohibición central: nada puede sumar o promediar resultados de estrategias
    distintas. `agrupar_por_observado` los SEPARA, que es lo contrario."""
    codigo = _solo_codigo(_fuente("playbooks.py"))
    for sospechoso in ("sum(", "mean(", "+=", "total_score", "combinar"):
        assert sospechoso not in codigo, f"'{sospechoso}' huele a mezcla de playbooks"


def test_el_modulo_no_toca_los_scores_existentes():
    """El commit 4 es infraestructura sin cambio de comportamiento: no importa ni
    `opportunities` ni `confluencia`."""
    codigo = _solo_codigo(_fuente("playbooks.py"))
    for modulo in ("opportunities", "confluencia", "newsletter_ingest", "server"):
        assert f"import {modulo}" not in codigo, modulo
