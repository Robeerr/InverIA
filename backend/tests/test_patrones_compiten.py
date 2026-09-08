"""El patrón que se dibuja es el que MEJOR encaja, no el que se comprobó antes.

QUÉ HABÍA

`detect_lines` elegía con una cascada de diecinueve `if pattern is None:` en fila:
ganaba el primero que respondiera. Así, un doble suelo que apenas pasaba sus filtros
se imponía siempre a una taza con asa de manual, solo por estar antes en la lista.
Los detectores no competían, y no había forma de saber cuál encajaba mejor porque
ninguno decía lo bien que encajaba: devolvían patrón o nada.

QUÉ PROTEGE ESTE FICHERO

Dos propiedades que tiran en direcciones opuestas y por eso hay que fijar las dos:

  1. COMPATIBILIDAD · mientras un detector no sepa puntuarse, el resultado tiene que
     ser el MISMO que daba la cascada. Sin esto, pasar a competición sería un cambio
     de comportamiento a ciegas sobre diecinueve detectores a la vez.
  2. COMPETENCIA · un detector que sí se puntúa y saca buena nota TIENE que poder
     adelantar a uno que iba por delante. Sin esto la migración no sirve de nada:
     habríamos cambiado la forma sin cambiar el resultado.

POR QUÉ LOS PRIORS SE COMPRUEBAN CONTRA EL ORDEN

El orden de la cascada era la única documentación de qué patrón se consideraba más
fiable. Al convertirlo en números, ese conocimiento pasa a los priors — y un prior
mal puesto reordenaría la preferencia sin que nadie lo note. Aquí se ata.
"""
import os
import ast
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import chart_lines


def _fuente():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "chart_lines.py"), encoding="utf-8") as f:
        return f.read()


def _candidatos():
    """(nombre, prior, techo) de la tabla, leídos del código."""
    src = _fuente()
    bloque = src[src.index("_CANDIDATOS = ["):]
    bloque = bloque[:bloque.index("\n    ]")]
    return [(m[0], float(m[1]), float(m[2])) for m in
            re.findall(r'\("(\w+)",\s*lambda:.*?,\s*([\d.]+),\s*([\d.]+)\)', bloque)]


# ── 1 · Compatibilidad ───────────────────────────────────────────────────────

def test_los_priors_bajan_siempre():
    """Es lo que reproduce la cascada. Con priors decrecientes y sin notas propias,
    el primero que responde es también el de prior más alto: gana igual que antes.
    Un prior fuera de orden cambiaría silenciosamente qué patrón se prefiere."""
    priors = [p for _, p, _ in _candidatos()]
    assert priors == sorted(priors, reverse=True), priors


def test_el_techo_nunca_queda_por_debajo_del_prior():
    """El techo acota lo que un detector puede reclamar. Si fuera menor que su prior,
    el propio detector se recortaría a sí mismo sin haber puntuado nada."""
    for nombre, prior, techo in _candidatos():
        assert techo >= prior, f"{nombre}: techo {techo} < prior {prior}"


def test_el_orden_de_la_cascada_se_conserva():
    """Los nombres, en el orden en que se comprobaban antes. Si alguien reordena la
    tabla creyendo que da igual, aquí se entera: el orden sigue decidiendo los
    empates, y los empates son el caso NORMAL mientras casi nadie se puntúa."""
    assert [n for n, _, _ in _candidatos()] == [
        "doble", "triple", "isla", "pipe", "bandera", "taza_asa", "taza_sin_asa",
        "base_plana", "hch", "diamante", "redondeado", "cuna", "triangulo",
        "canal", "rectangulo", "tres_valles", "directriz", "megafono", "hueco",
    ]


def test_a_igualdad_gana_el_que_iba_antes():
    """La comparación es `>` estricto y no `>=`. Con `>=`, el último en empatar se
    llevaría el patrón y el resultado cambiaría respecto de la cascada en todos los
    casos de empate — que hoy son casi todos."""
    codigo = _fuente()
    bloque = codigo[codigo.index("for _i, (_nombre, _fn, _prior, _techo)"):]
    bloque = bloque[:bloque.index("# El megáfono")]
    assert "_c > _mejor" in bloque
    assert "_c >= _mejor" not in bloque


# ── 2 · Competencia ──────────────────────────────────────────────────────────

def test_hay_detectores_que_pueden_adelantar():
    """Al menos uno tiene techo por encima del prior del primero. Si ninguno lo
    tuviera, la competición sería decorativa: nadie podría cambiar el resultado."""
    cands = _candidatos()
    prior_primero = cands[0][1]
    adelantan = [n for n, _, t in cands if t > prior_primero]
    assert adelantan, "ningún detector puede superar al primero de la cascada"


def test_la_taza_y_el_hch_se_puntuan_de_verdad():
    """Son los dos que ya han migrado. La comprobación es sobre el código y no sobre
    una detección real porque fabricar una taza válida exige 45+ velas con
    profundidad, asa y volumen coherentes: probaría sobre todo mi generador."""
    src = _fuente()
    for funcion in ("_detect_cup_handle", "_eval_hch"):
        assert funcion in src
    # La taza la emite en su return; el H&S la calcula en `_detect_head_shoulders`
    # a partir de lo que `_eval_hch` le devuelve.
    assert '"confianza": round(min(_cf, 0.98), 3)' in src
    assert '"confianza": round(min(_cf, 0.96), 3)' in src


def test_la_confianza_sale_de_medidas_ya_calculadas():
    """La nota no puede depender de datos nuevos: si costara otra pasada sobre las
    velas, puntuar diecinueve detectores multiplicaría el coste de la pantalla."""
    src = _fuente()
    cuerpo = src[src.index("    # ── Confianza ─"):]
    cuerpo = cuerpo[:cuerpo.index("return {")]
    for prohibido in ("for ", "while ", "_pivots(", "_atr(", "_linreg"):
        assert prohibido not in cuerpo, f"la confianza de la taza recalcula ({prohibido})"


# ── 3 · Robustez ─────────────────────────────────────────────────────────────

def test_un_detector_que_revienta_no_tumba_la_pantalla():
    """Con la cascada, una excepción dentro de un detector subía hasta el llamador y
    la ficha entera se quedaba sin líneas. Ahora ese candidato se descarta y los
    demás siguen compitiendo."""
    codigo = _fuente()
    bloque = codigo[codigo.index("for _i, (_nombre, _fn, _prior, _techo)"):]
    bloque = bloque[:bloque.index("# El megáfono")]
    assert "except Exception" in bloque and "continue" in bloque


def test_la_poda_no_puede_saltarse_a_nadie_que_pudiera_ganar():
    """La poda compara contra el TECHO de lo que queda, no contra su prior. Con el
    prior se saltaría a un detector capaz de puntuarse por encima —justo el caso que
    la competición existe para permitir."""
    codigo = _fuente()
    bloque = codigo[codigo.index("# Poda:"):]
    bloque = bloque[:bloque.index("try:")]
    assert "c[3]" in bloque, "la poda debe mirar el techo (4º campo), no el prior"


def test_sin_velas_no_revienta():
    for entrada in ([], [{"open": 1, "high": 1, "low": 1, "close": 1}]):
        r = chart_lines.detect_lines(entrada)
        assert isinstance(r, dict) and "pattern" in r


def test_el_patron_elegido_dice_quien_lo_encontro_y_con_cuanta_fe():
    """Sin estos dos campos no se puede medir nada después: no habría forma de
    preguntarle al histórico qué detector acierta más."""
    codigo = _fuente()
    assert '_cand["detector"] = _nombre' in codigo
    assert '_cand["confianza"] = round(_c, 3)' in codigo


# ── 4 · Cuántos se puntúan de verdad ─────────────────────────────────────────

def test_los_detectores_que_dicen_puntuarse_lo_hacen():
    """Un `techo` por encima del `prior` es una PROMESA: dice que ese detector sabe
    medirse. Si la promesa no se cumple, la tabla queda mintiendo —ese detector nunca
    alcanzará su techo— y nadie se entera, porque el resultado sigue siendo válido.

    Este test YA HA SERVIDO: cazó un canal con techo 0.91 y sin una sola línea de
    confianza. El cambio se había perdido a medias y el fallo era invisible.

    Se siguen DOS llamadas de profundidad porque varios detectores delegan su `return`
    en un ayudante, y uno encadena dos: `_detect_double` llama a `_scan_double`, que a
    su vez construye con `_build_double`, que es donde vive la nota. Mirar solo el
    cuerpo del primero daría falsos positivos en la mitad de la tabla.
    """
    src = _fuente()
    arbol = ast.parse(src)
    cuerpos = {n.name: n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)}

    def emite_confianza(nombre, profundidad=2):
        fn = cuerpos.get(nombre)
        if fn is None:
            return False
        for nodo in ast.walk(fn):
            if isinstance(nodo, ast.Constant) and nodo.value == "confianza":
                return True
        if profundidad <= 0:
            return False
        llamadas = {n.func.id for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        return any(emite_confianza(c, profundidad - 1) for c in llamadas if c in cuerpos)

    por_nombre = dict(re.findall(r'\("(\w+)",\s*lambda: (_detect_\w+)\(', src))
    incumplen = [n for n, prior, techo in _candidatos()
                 if techo > prior and not emite_confianza(por_nombre.get(n, ""))]
    assert not incumplen, f"prometen puntuarse y no lo hacen: {incumplen}"


def test_la_migracion_esta_completa_salvo_los_de_ultimo_recurso():
    """Los dieciséis detectores con estructura se puntúan. Los tres que no —directriz,
    megáfono y hueco— NO se puntúan a propósito, y esa decisión también se ata aquí.

    Puntuarlos no cambiaría ninguna decisión: van al final de la tabla, así que una
    nota alta solo podría reordenarlos entre ellos, y ese orden ya está dado. Lo único
    que añadiría es una cifra de confianza sobre un hallazgo que existe justamente
    porque no había nada mejor — confundiendo «encaja bien» con «es fiable».
    """
    migrados = [n for n, prior, techo in _candidatos() if techo > prior]
    sin_migrar = [n for n, prior, techo in _candidatos() if techo == prior]
    assert len(migrados) == 16, f"{len(migrados)} puntúan: {migrados}"
    assert sin_migrar == ["directriz", "megafono", "hueco"], sin_migrar


def test_el_techo_mide_el_RIGOR_no_la_belleza_de_la_figura():
    """La distinción que sostiene toda la tabla: el `techo` dice cuánto se puede fiar
    uno de ESE DETECTOR; la `confianza`, lo bien que encaja ESA figura concreta.

    Por eso `tres_valles` —tres swings, su propio código lo llama débil— tiene un
    margen corto: una instancia limpia merece distinguirse de una regular, pero no
    adelantar a un triángulo riguroso. Sin esta regla, la competición premiaría al
    detector más laxo, porque es el que más fácil encuentra figuras «perfectas».
    """
    por = {n: (prior, techo) for n, prior, techo in _candidatos()}
    prior_debil, techo_debil = por["tres_valles"]
    assert techo_debil - prior_debil <= 0.10, "un detector débil no puede ganar tanto margen"
    # Y no puede alcanzar a los rigurosos por muy bien que encaje su figura.
    for riguroso in ("doble", "triple", "hch", "taza_asa", "cuna", "triangulo"):
        assert techo_debil < por[riguroso][0], f"tres_valles podría adelantar a {riguroso}"
