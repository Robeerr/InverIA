"""Cuánto RIESGO DE CARTERA retira una venta, según el modelo de margen de DEGIRO.

QUÉ PROBLEMA RESUELVE

Con perfil Trader, el «Margen libre» de DEGIRO no es caja: es el valor neto de liquidación
menos el RIESGO que su modelo asigna a la cartera. Vender mueve dinero de «cartera» a
«saldo» dentro del mismo lado de la resta, así que el movimiento en sí no explica nada: lo
único que mueve el margen es cuánto baja el riesgo. De ahí que vender 3.000 € de una acción
dispare el margen y vender 3.000 € de otra no lo mueva.

POR QUÉ ESTO NO ES REDUNDANTE CON DEGIRO

DEGIRO enseña un «Margin impact» en la pantalla de la orden. **Está mal.** Medido contra
una venta real de 15 MRVL el 21-08-2026:

    lo que predijo el ticket de DEGIRO ....       5,36 €   (error 99,6%)
    lo que predijo este modelo ............   1.199,00 €   (error  0,3%)
    lo que ocurrió de verdad .............   1.202,12 €

El usuario avisó dos veces de que ese preview no le cuadraba, y tenía razón. Ese caso está
congelado como test de regresión en tests/test_riesgo_cartera.py.

EL MODELO (Investment Portfolio Risk Handbook, 30-04-2024, perfil Trader)

    riesgo = MAX(evento, neto, sector, bruto)

    evento = máx sobre posiciones de  pct(categoría) × valor
    neto   = 25% × (V − D) + D + otros
    sector = 40% × mayor sector (sin D) + D + otros
    bruto  = 10% × (V − D) + D + otros
    otros  = 6,36% × (V − D)      ← riesgo de divisa de lo que no cotiza en euros

`D` es la suma de las posiciones en categoría D: el manual les añade el 100% de su valor a
los componentes neto, sectorial y bruto (no al de evento). Que sea un MÁXIMO y no una suma
es lo que produce el comportamiento que desconcierta: vender algo que NO marcaba el máximo
deja el máximo donde estaba y el margen no se mueve.

LO QUE NO SE SABE, Y CÓMO NO SE MIENTE CON ELLO

La categoría A-D la publica DEGIRO junto a cada producto, pero no hay API que la sirva, y
DEGIRO la revisa cada mes. Su taxonomía sectorial tampoco coincide con la de yfinance.

Por eso este módulo NO se cree a sí mismo: `calibrar()` compara su propio riesgo con el que
DEGIRO publica en el extracto de margen, y si no lo reproduce dentro de `TOLERANCIA` la
estimación se retira. Se prefiere un hueco visible a una cifra que ya no cuadra.

Aritmética pura: sin red, sin base de datos, sin fechas.
"""

from typing import List, Optional

# ── Parámetros del manual, perfil Trader, posiciones LARGAS ──────────────────
# Tabla «Trader / Long» del Investment Portfolio Risk Handbook.
PCT_CATEGORIA = {
    "A": 0.6250, "B": 0.8125, "C": 0.9900, "D": 1.0000,
    # E-I son bonos del Estado y fondos; J y «sin categoría», al 100%.
    "E": 0.0625, "F": 0.1250, "G": 0.1875, "H": 0.2500, "I": 0.3125,
    "J": 1.0000, "": 1.0000,
}
CATEGORIA_DESCONOCIDA = "A"   # ver `_pct`: solo se usa cuando la ficha no la tiene

P_NETO = 0.25       # sobre el neto de la categoría de inversión
P_SECTOR = 0.40     # sobre el neto del sector mayor
P_BRUTO = 0.10      # sobre el bruto de la cartera
P_DIVISA = 0.0636   # riesgo de divisa de lo que no cotiza en euros

# Hasta dónde puede desviarse nuestro riesgo del que publica DEGIRO para seguir dando una
# cifra. El 2% es holgado respecto a lo medido (0,83% con el extracto real) y estrecho
# respecto a lo que importa: un error del 2% sobre una venta de 3.000 € son 60 €, que no
# cambia ninguna decisión. Por encima, la estimación se retira.
TOLERANCIA = 0.02

# Suelo de incertidumbre. El error del modelo es un porcentaje del RIESGO TOTAL, no de la
# venta: medido a 0,45% sobre 10.564 € son ±48 €, y esos ±48 € están ahí tanto si la venta
# libera 1.200 € como si libera 175 €. Por eso el error RELATIVO de una estimación depende
# del tamaño de lo que se vende:
#
#     venta de MRVL   predijo 1.199 €, salieron 1.202 €   desvío   3 €   ( 0,3%)
#     venta de HOOD   predijo   134 €, salieron   175 €   desvío  41 €   (23,7%)
#
# Los dos casos caben en la misma banda absoluta. Dar el número sin la banda fue el error:
# parecía que el modelo había fallado en HOOD y no había fallado más que en MRVL.
ERROR_MINIMO = 0.005   # ni con una calibración perfecta se afina más que esto

# A partir de aquí la calibración se considera vieja: DEGIRO recategoriza los instrumentos
# una vez al mes, así que un extracto de hace más de eso puede describir otra cartera.
DIAS_CALIBRACION = 31

# Los que compiten por el máximo. `divisa` va aparte: es informativo y ya está
# sumado dentro de neto, sector y bruto.
COMPONENTES = ("evento", "neto", "sector", "bruto")
NOMBRES = {
    "evento": "tu mayor posición individual",
    "neto": "el peso total de la cartera",
    "sector": "tu concentración sectorial",
    "bruto": "el bruto de la cartera",
}

SIN_CALIBRAR = "SIN_CALIBRAR"
CALIBRACION_VIEJA = "CALIBRACION_VIEJA"
NO_CUADRA = "NO_CUADRA"
FALTAN_DATOS = "FALTAN_DATOS"
OK = "OK"


def _pct(pos: dict) -> float:
    """Porcentaje de riesgo de evento de una posición.

    Sin categoría se usa la A, que es la MÁS BAJA de las cuatro de acciones. Es deliberado:
    equivocarse por abajo hace que el componente de evento no mande cuando debería, y eso
    se detecta en la calibración; equivocarse por arriba inflaría el riesgo en silencio.
    """
    cat = (pos.get("categoria") or CATEGORIA_DESCONOCIDA).strip().upper()[:1]
    return PCT_CATEGORIA.get(cat, PCT_CATEGORIA[CATEGORIA_DESCONOCIDA])


def _es_d(pos: dict) -> bool:
    return (pos.get("categoria") or "").strip().upper()[:1] == "D"


def componentes(posiciones: List[dict]) -> dict:
    """Los cuatro componentes de riesgo, en euros, más el desglose que los explica."""
    vivas = [p for p in posiciones if (p.get("valor_eur") or 0) > 0]
    if not vivas:
        return {**{c: 0.0 for c in COMPONENTES}, "divisa": 0.0}

    total = sum(float(p["valor_eur"]) for p in vivas)
    d = sum(float(p["valor_eur"]) for p in vivas if _es_d(p))
    resto = total - d

    # Riesgo de divisa: solo lo que NO cotiza en euros. Las posiciones en categoría D ya
    # entran al 100% por otra vía; volver a cargarles la divisa sería contarlas dos veces.
    extranjero = sum(float(p["valor_eur"]) for p in vivas
                     if not _es_d(p) and (p.get("divisa") or "USD").upper() != "EUR")
    otros = P_DIVISA * extranjero

    por_sector = {}
    for p in vivas:
        if _es_d(p):
            continue
        s = (p.get("sector") or "").strip().upper()
        por_sector[s] = por_sector.get(s, 0.0) + float(p["valor_eur"])

    # El riesgo de divisa se suma a los tres componentes de cartera, no al evento.
    #
    # El manual lo PRESENTA de otra forma —lista los componentes desnudos y suma la divisa
    # al final— pero da el mismo resultado, porque max(a,b,c)+k == max(a+k, b+k, c+k). Se
    # hace así porque es como lo desglosa la propia aplicación de DEGIRO, que rotula las
    # líneas «Net investment, derivative risk AND OTHER RISKS». Cuadrar con lo que el
    # usuario ve en su pantalla vale más que cuadrar con la maquetación del PDF.
    return {
        "evento": max(_pct(p) * float(p["valor_eur"]) for p in vivas),
        "neto": P_NETO * resto + d + otros,
        "sector": (P_SECTOR * max(por_sector.values()) if por_sector else 0.0) + d + otros,
        "bruto": P_BRUTO * resto + d + otros,
        # Informativo, para poder enseñar el desglose: ya está DENTRO de los tres de
        # arriba, así que no se suma otra vez ni entra en el máximo.
        "divisa": otros,
    }


def riesgo(posiciones: List[dict]) -> tuple:
    """(riesgo, componente que manda, todos los componentes).

    El riesgo es el MÁXIMO, no la suma. Es la pieza que explica todo lo demás.
    """
    comps = componentes(posiciones)
    compiten = {k: v for k, v in comps.items() if k in COMPONENTES}
    dominante = max(compiten, key=compiten.get)
    return compiten[dominante], dominante, comps


def _dias_entre(desde: Optional[str], hasta: Optional[str]) -> Optional[int]:
    """Días entre dos fechas ISO. None si falta alguna o no se entienden."""
    from datetime import date
    try:
        a = date.fromisoformat((desde or "")[:10])
        b = date.fromisoformat((hasta or "")[:10])
    except (TypeError, ValueError):
        return None
    return (b - a).days


def calibrar(posiciones: List[dict], extracto: Optional[dict],
             hoy: Optional[str] = None) -> dict:
    """Compara nuestro riesgo con el que publica DEGIRO. Es el permiso para dar cifras.

    SE COMPARA LA PROPORCIÓN, NO LOS EUROS

    Comparar `riesgo_modelo` con `riesgo_degiro` en euros parece lo natural y obliga a
    volver a pegar el extracto casi a diario: la cartera se mueve con el mercado, el riesgo
    se mueve con ella, y el modelo declararía "ya no cuadro" cuando lo único que ha pasado
    es que era otro día.

    Lo que de verdad se está validando no son los euros: son las CATEGORÍAS y los SECTORES
    que el modelo supone. Eso se ve en la proporción riesgo/cartera, que no se inmuta ante
    una subida general de precios y solo cambia cuando cambia la composición o cuando
    DEGIRO recategoriza —una vez al mes—. Con la proporción, un extracto vale semanas.

    Hace falta que el extracto traiga también el valor de cartera; si no, se cae a comparar
    euros, que es peor pero mejor que no comparar nada.
    """
    nuestro, dominante, comps = riesgo(posiciones)
    vacio = {"estado": SIN_CALIBRAR, "nuestro_eur": round(nuestro, 2),
             "dominante": dominante, "componentes": comps}
    if not extracto or not extracto.get("riesgo_eur"):
        return vacio
    suyo = float(extracto["riesgo_eur"] or 0)
    if suyo <= 0:
        return vacio

    dias = _dias_entre(extracto.get("fecha"), hoy) if hoy else None
    base = {"nuestro_eur": round(nuestro, 2), "degiro_eur": round(suyo, 2),
            "dominante": dominante, "componentes": comps,
            "fecha": extracto.get("fecha"), "dias": dias}
    if dias is not None and dias > DIAS_CALIBRACION:
        return {"estado": CALIBRACION_VIEJA, **base}

    # Cuántas posiciones no tienen categoría. Importa para el diagnóstico: sin ella se
    # asume la más baja, así que el modelo se queda CORTO de forma sistemática — y el
    # mensaje debe mandar a rellenarlas, no a repegar un extracto que está bien.
    base["sin_categoria"] = sum(1 for p in posiciones
                                if not (p.get("categoria") or "").strip()
                                and (p.get("valor_eur") or 0) > 0)
    base["posiciones"] = sum(1 for p in posiciones if (p.get("valor_eur") or 0) > 0)

    nuestra_cartera = sum(float(p["valor_eur"]) for p in posiciones
                          if (p.get("valor_eur") or 0) > 0)
    su_cartera = float(extracto.get("valor_cartera_eur") or 0)
    if su_cartera > 0 and nuestra_cartera > 0:
        # Proporción contra proporción: inmune al vaivén diario de los precios.
        error = abs((nuestro / nuestra_cartera) - (suyo / su_cartera)) / (suyo / su_cartera)
        base["comparacion"] = "proporcion"
    else:
        error = abs(nuestro - suyo) / suyo
        base["comparacion"] = "euros"
    estado = OK if error <= TOLERANCIA else NO_CUADRA
    return {"estado": estado, "error": round(error, 4), **base}


def _motivo(clase_dominante: str, dom_despues: Optional[str], pct: float,
            es_d: bool, distinguible: bool = True) -> str:
    """Por qué esta venta libera mucho o poco. Una frase, con la causa concreta."""
    if not distinguible:
        return (f"Lo que marca tu riesgo es {NOMBRES[clase_dominante]}, y esta posición "
                f"apenas influye. Lo que liberaría queda por debajo de lo que este "
                f"cálculo puede distinguir, así que no se da una cifra.")
    if es_d:
        return ("DEGIRO clasifica esta acción en categoría D: le asigna el 100% de su "
                "valor como riesgo, así que venderla retira todo lo que vale.")
    if pct < 0.10:
        return (f"Esta posición no es lo que marca el riesgo de tu cartera: lo marca "
                f"{NOMBRES[clase_dominante]}. Al venderla ese factor sigue igual, así que "
                f"el margen apenas se mueve.")
    if dom_despues and dom_despues != clase_dominante:
        return (f"Hoy tu riesgo lo marca {NOMBRES[clase_dominante]}, y esta venta lo "
                f"reduce hasta que pasa a mandar {NOMBRES[dom_despues]}.")
    return (f"Tu riesgo lo marca {NOMBRES[clase_dominante]}, y esta posición forma parte "
            f"de él: venderla lo reduce en proporción.")


def estimar(posiciones: List[dict], symbol: str, acciones: Optional[float] = None,
            extracto: Optional[dict] = None, hoy: Optional[str] = None) -> dict:
    """Cuánto margen libre debería devolver vender `acciones` de `symbol`.

    `acciones` a None = vender la posición entera. Devuelve euros SOLO si la calibración
    contra el extracto de DEGIRO cuadra; si no, devuelve el motivo por el que no se puede.
    """
    sym = (symbol or "").strip().upper()
    posiciones = [dict(p) for p in (posiciones or []) if (p.get("symbol") or "").strip()]

    sin_valor = [p["symbol"] for p in posiciones if p.get("valor_eur") is None]
    if sin_valor:
        return {"estado": FALTAN_DATOS, "symbol": sym,
                "motivo": (f"No se puede estimar: {len(sin_valor)} posición"
                           f"{'es' if len(sin_valor) != 1 else ''} sin valorar "
                           f"({', '.join(sorted(sin_valor))}).")}

    cal = calibrar(posiciones, extracto, hoy)
    if cal["estado"] != OK:
        return {**cal, "symbol": sym, "motivo": _motivo_calibracion(cal)}

    vendida = next((p for p in posiciones if p["symbol"].strip().upper() == sym), None)
    if vendida is None or float(vendida["valor_eur"]) <= 0:
        return {"estado": FALTAN_DATOS, "symbol": sym,
                "motivo": f"{sym} no está entre tus posiciones abiertas."}

    valor = float(vendida["valor_eur"])
    total_acc = float(vendida.get("acciones") or 0)
    if acciones and total_acc > 0:
        # Venta PARCIAL: la posición encoge, no desaparece. Importa porque el máximo puede
        # no moverse hasta que la venta es lo bastante grande.
        parte = min(float(acciones), total_acc) / total_acc
    else:
        parte = 1.0
    importe = valor * parte

    r0, dom0, _ = riesgo(posiciones)
    resto = []
    for p in posiciones:
        if p is vendida:
            if parte >= 1.0:
                continue
            p = {**p, "valor_eur": valor - importe,
                 "acciones": total_acc * (1 - parte) if total_acc else None}
        resto.append(p)
    r1, dom1, _ = (riesgo(resto) if resto else (0.0, None, {}))

    retirado = r0 - r1
    pct = retirado / importe if importe else 0.0
    # La banda sale del error medido contra el extracto, aplicado al riesgo TOTAL: es la
    # incertidumbre en euros, y no encoge porque la venta sea pequeña.
    banda = max(cal.get("error") or 0.0, ERROR_MINIMO) * r0
    # Por debajo del doble de la banda, la cifra no distingue de cero. Decir "+30 € ± 50 €"
    # es peor que decir que no se sabe: invita a leer el 30.
    distinguible = retirado >= 2 * banda
    return {
        "estado": OK,
        "symbol": sym,
        "importe_eur": round(importe, 2),
        "acciones": round(total_acc * parte, 6) if total_acc else None,
        "margen_eur": round(retirado, 2),
        "incertidumbre_eur": round(banda, 2),
        "distinguible": distinguible,
        "pct_del_importe": round(pct, 4),
        "riesgo_antes_eur": round(r0, 2),
        "riesgo_despues_eur": round(r1, 2),
        "dominante_antes": dom0,
        "dominante_despues": dom1,
        "componentes_antes": {k: round(v, 2) for k, v in componentes(posiciones).items()},
        "componentes_despues": {k: round(v, 2) for k, v in componentes(resto).items()},
        "motivo": _motivo(dom0, dom1, pct, _es_d(vendida), distinguible),
        "calibracion": {"error": cal.get("error"), "fecha": cal.get("fecha"),
                        "degiro_eur": cal.get("degiro_eur")},
    }


def _eur(n) -> str:
    """10627.4 → «10.627». Punto para los miles, que es como se escribe en español.

    El formato `,.0f` de Python pone la coma inglesa, y «10,627 €» en español se lee como
    diez euros con seiscientas veintisiete milésimas. En un mensaje cuyo trabajo es que
    compares dos cifras, el separador no es cosmética.
    """
    return f"{n:,.0f}".replace(",", ".")


def _porcentaje(x) -> str:
    """0.039 → «3,9%». Coma decimal, por lo mismo que el punto en los miles.

    Y no se llama `_pct` porque ese nombre ya está cogido en este módulo por otra cosa
    —el porcentaje de riesgo de una posición— y definirlo dos veces no da error: la
    segunda pisa a la primera y todo el modelo empieza a llamar a la función equivocada.
    """
    return f"{x:.1%}".replace(".", ",")


def _motivo_calibracion(cal: dict) -> str:
    if cal["estado"] == SIN_CALIBRAR:
        return ("No se puede estimar todavía: falta el extracto de margen de DEGIRO. "
                "Cópialo desde «Available to trade» y se podrá comprobar si el modelo "
                "reproduce tu riesgo real.")
    if cal["estado"] == CALIBRACION_VIEJA:
        dias = cal.get("dias")
        return (f"Tu extracto de margen es de hace {dias} días y DEGIRO recategoriza los "
                f"instrumentos una vez al mes. Vuelve a copiarlo para seguir dando cifras."
                if dias else
                "Tu extracto de margen ha caducado. Vuelve a copiarlo.")
    faltan, total = cal.get("sin_categoria") or 0, cal.get("posiciones") or 0
    corto = (cal.get("nuestro_eur") or 0) < (cal.get("degiro_eur") or 0)
    # El porcentaje tiene que corresponder a lo que se compara. Cuando se comparan
    # PROPORCIONES riesgo/cartera —el caso normal— el error no sale de restar los dos
    # euros: 10.627 y 10.508 se llevan un 1,1%, y el mensaje anunciaba un 3,9%. Quien lo
    # leyera no podía comprobarlo y parecía una cuenta mal hecha. Se dice cuál es cada
    # cosa: los euros son de días distintos, y el porcentaje es el de la proporción.
    dias = cal.get("dias")
    recien = dias is not None and dias <= 1
    euros = (f"calcula {_eur(cal['nuestro_eur'])} € y DEGIRO dice "
             f"{_eur(cal['degiro_eur'])} €" if recien else
             f"calcula {_eur(cal['nuestro_eur'])} € y DEGIRO decía "
             f"{_eur(cal['degiro_eur'])} €")
    if cal.get("comparacion") == "proporcion":
        # La coletilla de los días solo vale si de verdad son días distintos: con el
        # extracto de hoy, decirlo es una explicación falsa de por qué el porcentaje no
        # sale de restar los euros.
        por_que = ("" if recien else
                   " Esas dos cifras son de días distintos, así que lo que se compara es "
                   "la proporción riesgo/cartera:")
        cuerpo = (f" En proporción al valor de la cartera la diferencia es del"
                  if recien else " ahí la diferencia es del")
        diferencia = (f"{euros}.{por_que}{cuerpo} {_porcentaje(cal['error'])}, "
                      f"por encima del {TOLERANCIA:.0%} admitido")
    else:
        diferencia = f"{euros}: un {_porcentaje(cal['error'])} de diferencia"
    # Quedarse CORTO con categorías sin rellenar tiene una explicación concreta, y mandar a
    # repegar el extracto en ese caso es mandar al sitio equivocado: el extracto está bien.
    if faltan and corto:
        return (f"Faltan las categorías de riesgo de DEGIRO: {faltan} de {total} "
                f"posiciones no la tienen. Sin ellas el modelo no sabe cuáles computan al "
                f"100% y se queda corto: {diferencia}. Ponlas en la Cartera, en la "
                f"columna «Cat.»: la letra sale junto al nombre del producto en la "
                f"pantalla de la orden de DEGIRO.")
    # Con el extracto RECIÉN copiado, mandar a copiarlo otra vez no es un consejo: es un
    # bucle. Si acabas de pegarlo y sigue sin cuadrar, el problema está en los datos que el
    # modelo usa, y se puede señalar cuál.
    if recien and corto:
        comps = cal.get("componentes") or {}
        dom = cal.get("dominante")
        techo = max((v for k, v in comps.items() if k in COMPONENTES), default=0.0)
        # DEGIRO por encima del MAYOR de los cuatro componentes solo puede significar que a
        # él le manda otro, calculado sobre datos distintos de los nuestros. Y el sospechoso
        # es el sector: la categoría se teclea de su propia pantalla y coincide, pero el
        # sector de tu Cartera es TU taxonomía —la que separa lo que tú separas— mientras
        # que DEGIRO agrupa con la suya, mucho más gruesa. Diez posiciones que para ti son
        # cinco cosas distintas pueden ser un solo sector para él, y entonces su
        # concentración sectorial dispara un riesgo que aquí no aparece.
        if cal["degiro_eur"] > techo * 1.02:
            # DOS sospechosos, y no se puede elegir entre ellos desde aquí. Se nombran los
            # dos y se dice cómo distinguirlos, que es mejor que acertar la mitad de las
            # veces: apuntar solo al sector mandaba al sitio equivocado en el caso real que
            # destapó esto —eran categorías D, que suman el 100% de su valor a los TRES
            # componentes a la vez y por eso pueden dejar la cifra de DEGIRO por encima de
            # todo lo que calculamos.
            return (f"El modelo se queda corto con un extracto recién copiado: "
                    f"{diferencia}. Aquí manda {NOMBRES.get(dom, dom)}, y la cifra de "
                    f"DEGIRO supera a los cuatro componentes que calculamos, así que hay "
                    f"riesgo que no vemos. Dos causas posibles: posiciones en CATEGORÍA D "
                    f"—computan el 100% de su valor y se suman a los tres componentes— o "
                    f"un SECTOR agrupado de otra forma, porque DEGIRO usa su clasificación "
                    f"y no la tuya. Se distinguen con tu «Margin statement»: despliega "
                    f"«Portfolio Risk» y resta la línea Gross de la Net; esa diferencia es "
                    f"el 15% de lo que NO es categoría D, así que te dice cuánta D tienes.")
        return (f"El modelo se queda corto con un extracto recién copiado: {diferencia}. "
                f"Aquí manda {NOMBRES.get(dom, dom)}. Compara los componentes con los de "
                f"tu «Margin statement»: el que no cuadre dice qué dato hay que revisar.")
    if recien:
        # Pasarse POR ARRIBA con el extracto al día tiene el sospechoso contrario: una
        # categoría D de más. La D carga el 100% del valor de la posición, así que basta
        # una mal puesta para inflar el riesgo muy por encima de lo real.
        dom = cal.get("dominante")
        return (f"El modelo se pasa por arriba con un extracto recién copiado: "
                f"{diferencia}. Aquí manda {NOMBRES.get(dom, dom)}. Revisa las categorías "
                f"de la columna «Cat.»: una D computa el 100% del valor de esa posición, "
                f"así que una sola mal puesta infla el riesgo de toda la cartera.")
    return (f"El modelo ya no reproduce tu riesgo real: {diferencia}. Suele pasar cuando "
            f"has comprado o vendido desde que copiaste el extracto, o cuando DEGIRO ha "
            f"recategorizado. Vuelve a copiarlo y se recalibra solo.")


# ── Simulador: comprar o vender, antes de decidir ────────────────────────────
#
# `estimar` contesta "si vendo esto, cuánto margen recupero", y vive dentro de los
# formularios de venta. Pero ahí ya has decidido. La pregunta útil es anterior y va en los
# dos sentidos, porque COMPRAR también mueve el margen —y con una cuenta apalancada lo
# mueve en la dirección peligrosa.

COMPRAR, VENDER = "comprar", "vender"
FALTA_CATEGORIA = "FALTA_CATEGORIA"


def _resultado(r0, r1, dom0, dom1, comps0, comps1, importe, cal, contexto):
    """El bloque común de una simulación, en los dos sentidos.

    `margen_eur` va CON SIGNO: positivo si la operación te devuelve margen (vender),
    negativo si te lo quita (comprar). Sin signo habría que deducirlo del contexto, y es
    exactamente el dato que no conviene tener que deducir.
    """
    cambio = r0 - r1
    banda = max(cal.get("error") or 0.0, ERROR_MINIMO) * max(r0, r1)
    return {
        "estado": OK,
        "margen_eur": round(cambio, 2),
        "incertidumbre_eur": round(banda, 2),
        "distinguible": abs(cambio) >= 2 * banda,
        "importe_eur": round(importe, 2),
        "pct_del_importe": round(cambio / importe, 4) if importe else 0.0,
        "riesgo_antes_eur": round(r0, 2),
        "riesgo_despues_eur": round(r1, 2),
        "dominante_antes": dom0,
        "dominante_despues": dom1,
        "componentes_antes": {k: round(v, 2) for k, v in comps0.items()},
        "componentes_despues": {k: round(v, 2) for k, v in comps1.items()},
        "calibracion": {"error": cal.get("error"), "fecha": cal.get("fecha"),
                        "degiro_eur": cal.get("degiro_eur")},
        **contexto,
    }


def simular(posiciones: List[dict], symbol: str, accion: str, importe: float,
            categoria: Optional[str] = None, sector: Optional[str] = None,
            extracto: Optional[dict] = None, hoy: Optional[str] = None) -> dict:
    """Qué le pasa a tu margen libre si compras o vendes `importe` euros de `symbol`.

    Al COMPRAR algo que no tienes hace falta su categoría A-D, y esa letra decide casi
    todo: mil euros de una categoría A cuestan ~314 € de margen y de una categoría D
    cuestan los mil. Si no se sabe, se devuelve el RANGO en vez de elegir una por el
    usuario — un rango honesto sirve para decidir; una letra inventada, no.
    """
    sym = (symbol or "").strip().upper()
    accion = (accion or "").strip().lower()
    if accion not in (COMPRAR, VENDER):
        return {"estado": FALTAN_DATOS, "motivo": "La operación debe ser comprar o vender."}
    try:
        importe = float(importe or 0)
    except (TypeError, ValueError):
        importe = 0.0
    if importe <= 0:
        return {"estado": FALTAN_DATOS, "symbol": sym,
                "motivo": "Falta el importe de la operación."}

    posiciones = [dict(p) for p in (posiciones or []) if (p.get("symbol") or "").strip()]
    sin_valor = [p["symbol"] for p in posiciones if p.get("valor_eur") is None]
    if sin_valor:
        return {"estado": FALTAN_DATOS, "symbol": sym,
                "motivo": (f"No se puede simular: {len(sin_valor)} posición"
                           f"{'es' if len(sin_valor) != 1 else ''} sin valorar "
                           f"({', '.join(sorted(sin_valor))}).")}

    cal = calibrar(posiciones, extracto, hoy)
    if cal["estado"] != OK:
        return {**cal, "symbol": sym, "motivo": _motivo_calibracion(cal)}

    actual = next((p for p in posiciones if p["symbol"].strip().upper() == sym), None)
    r0, dom0, comps0 = riesgo(posiciones)

    if accion == VENDER:
        if actual is None or float(actual["valor_eur"]) <= 0:
            return {"estado": FALTAN_DATOS, "symbol": sym,
                    "motivo": f"{sym} no está entre tus posiciones abiertas."}
        vendido = min(importe, float(actual["valor_eur"]))
        resto = []
        for p in posiciones:
            if p is actual:
                queda = float(p["valor_eur"]) - vendido
                if queda <= 0:
                    continue
                p = {**p, "valor_eur": queda}
            resto.append(p)
        r1, dom1, comps1 = (riesgo(resto) if resto else (0.0, None, componentes([])))
        res = _resultado(r0, r1, dom0, dom1, comps0, comps1, vendido, cal,
                         {"symbol": sym, "accion": VENDER,
                          "categoria": (actual.get("categoria") or "").upper() or None})
        res["motivo"] = _motivo(dom0, dom1, res["pct_del_importe"], _es_d(actual),
                                res["distinguible"])
        return res

    # ── COMPRAR ──────────────────────────────────────────────────────────────
    cat = (categoria or (actual or {}).get("categoria") or "").strip().upper()[:1]
    sec = (sector or (actual or {}).get("sector") or "").strip()

    def _con_categoria(c):
        nuevas = []
        visto = False
        for p in posiciones:
            if p is actual:
                visto = True
                p = {**p, "valor_eur": float(p["valor_eur"]) + importe, "categoria": c}
            nuevas.append(p)
        if not visto:
            nuevas.append({"symbol": sym, "valor_eur": importe, "sector": sec,
                           "categoria": c, "divisa": "USD"})
        return riesgo(nuevas)

    if cat in ("A", "B", "C", "D"):
        r1, dom1, comps1 = _con_categoria(cat)
        res = _resultado(r0, r1, dom0, dom1, comps0, comps1, importe, cal,
                         {"symbol": sym, "accion": COMPRAR, "categoria": cat,
                          "sector": sec})
        res["motivo"] = _motivo_compra(cat, res["pct_del_importe"], dom1, sec)
        return res

    # Sin categoría: el rango entre la más barata y la más cara, sin elegir por el usuario.
    coste = {}
    for c in ("A", "B", "C", "D"):
        r1, dom1, comps1 = _con_categoria(c)
        coste[c] = r0 - r1
    barata, cara = min(coste, key=lambda c: abs(coste[c])), max(coste, key=lambda c: abs(coste[c]))
    r1, dom1, comps1 = _con_categoria(cara)
    banda = max(cal.get("error") or 0.0, ERROR_MINIMO) * max(r0, r1)
    return {
        "estado": FALTA_CATEGORIA,
        "symbol": sym, "accion": COMPRAR, "sector": sec,
        "importe_eur": round(importe, 2),
        "incertidumbre_eur": round(banda, 2),
        "rango": {c: round(coste[c], 2) for c in ("A", "B", "C", "D")},
        "rango_min_eur": round(coste[barata], 2), "rango_min_cat": barata,
        "rango_max_eur": round(coste[cara], 2), "rango_max_cat": cara,
        "calibracion": {"error": cal.get("error"), "fecha": cal.get("fecha")},
        "motivo": (f"Falta la categoría de riesgo de {sym}, y esa letra decide casi todo: "
                   f"comprar {importe:,.0f} € te costaría entre "
                   f"{abs(coste[barata]):,.0f} € (categoría {barata}) y "
                   f"{abs(coste[cara]):,.0f} € (categoría {cara}) de margen. La letra sale "
                   f"en DEGIRO junto al nombre del producto, en la pantalla de la orden."),
    }


def _motivo_compra(cat: str, pct: float, dom_despues: Optional[str], sector: str) -> str:
    """Por qué esta compra cuesta mucho o poco margen."""
    if cat == "D":
        return ("DEGIRO clasifica esta acción en categoría D: le asigna el 100% de su "
                "valor como riesgo, así que comprarla te cuesta en margen todo lo que "
                "inviertas.")
    if abs(pct) > 0.5:
        return (f"Con esta compra pasa a mandar {NOMBRES.get(dom_despues, dom_despues)}, "
                f"y por eso se lleva buena parte de lo que inviertes.")
    return (f"Categoría {cat}. Lo que manda después es "
            f"{NOMBRES.get(dom_despues, dom_despues)}"
            + (f", y esta compra engorda {sector}." if sector else "."))
