"""Libro de operaciones: compras por lotes, ventas emparejadas y ganancia REALIZADA.

Por qué un libro y no un saldo
------------------------------
Lo que había antes guardaba en la posición un precio medio y un número de acciones, y al
vender restaba. Eso no puede contestar a lo que de verdad se pregunta uno: "estas 3 que me
quedan, ¿de qué compra son?", "esta venta, ¿sobre qué coste?". Y en cuanto compras más
después de haber vendido, el precio medio cambia y recalcular una venta vieja con el precio
medio nuevo da una ganancia que nunca ocurrió.

Aquí las compras y las ventas se guardan tal como ocurrieron y NO se tocan. Todo lo demás
—lo que queda abierto, lo ganado, el precio medio— se deriva reproduciendo el libro. Eso
hace que corregir un error sea editar un apunte, no descuadrar la posición para siempre.

FIFO y LIFO
-----------
Se calculan LOS DOS sobre las mismas operaciones, porque contestan a preguntas distintas:

  · FIFO ("lo primero que compré es lo primero que vendo") es OBLIGATORIO en España para
    acciones cotizadas — artículo 37.2 de la Ley del IRPF. Es la cifra que va a la
    declaración y la que cuadra con lo que Hacienda considera tu ganancia. El coste medio
    ponderado, que usan casi todos los brókeres anglosajones, NO está admitido.

  · LIFO ("he vendido las últimas que compré") es como suele pensarlo uno cuando va
    promediando a la baja. Es útil para juzgar la operación, pero no vale para la renta.

Pueden diferir muchísimo: con 3 acciones a 80 $ y 2 a 120 $, vender 1 a 130 $ da +50 $ por
FIFO y +10 $ por LIFO. Por eso se muestran las dos etiquetadas, y nunca un número a secas.

Los euros
---------
Cada lote se convierte a euros al cambio de SU fecha, y lo ingresado al cambio del día de la
venta. Convertir el beneficio en dólares al cambio de hoy daría un número que no corresponde
a ninguna operación real: si compras a 1,05 y vendes a 1,15 USD/EUR, cada dólar que
recuperas vale menos euros que los que pusiste, y puedes ganar en dólares y perder en euros.

Las comisiones
--------------
Suman al coste en la compra y restan de lo ingresado en la venta, que es como se calcula la
ganancia patrimonial de verdad. Van por operación porque en DeGiro no son fijas: dependen
del mercado y del producto.
"""
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FIFO = "FIFO"
LIFO = "LIFO"
METODOS = (FIFO, LIFO)

#: Método con el que se lleva la GESTIÓN: lo que se ve por defecto, el precio medio de la
#: posición viva y qué campanitas quedan encendidas.
#:
#: Es LIFO y no FIFO porque describe cómo se opera esta cartera de verdad: se entra por
#: niveles según CAE el precio, así que la compra más reciente es siempre la más barata, y
#: al vender un nivel se está vendiendo esa. Con FIFO las campanitas se encenderían por el
#: extremo contrario —los niveles caros, comprados primero— y estarían diciendo justo lo
#: contrario de lo que pasó.
#:
#: OJO: esto NO cambia lo fiscal. FIFO se sigue calculando siempre y es el que hay que
#: llevar a la declaración (art. 37.2 LIRPF); lo que cambia es qué método se enseña primero
#: cuando la pregunta es "¿cuánto he ganado?" y no "¿qué declaro?".
METODO_GESTION = LIFO
METODO_FISCAL = FIFO

#: Tolerancia para dar por bueno que una compra se hizo "en" un nivel de la Cartera.
#: 1,5% cubre el hueco normal entre la orden y la ejecución sin llegar a atribuir a un nivel
#: una compra que se hizo claramente en otro sitio.
TOLERANCIA_NIVEL = 0.015


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hoy() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ── Un lote de compra ────────────────────────────────────────────────────────

def _divisa(divisa) -> str:
    return (divisa or "USD").strip().upper() or "USD"


def coste_lote(precio: float, acciones: float, comision: float = 0.0) -> float:
    """Lo que te costó de verdad, comisión incluida."""
    return acciones * precio + (comision or 0.0)


def detectar_nivel(precio: float, entry: dict) -> dict:
    """A qué nivel de la Cartera corresponde una compra hecha a `precio`.

    Devuelve {"nivel": "nivel3", "precio_nivel": 180.0, "desvio_pct": -0.4} o
    {"nivel": None} si no cae cerca de ninguno.

    Se elige el nivel MÁS CERCANO dentro de la tolerancia, no el primero que cumpla: con
    niveles juntos (180 y 178) el primero que cumpla puede no ser el que tocó.
    """
    if not entry or precio is None:
        return {"nivel": None}
    try:
        precio = float(precio)
    except (TypeError, ValueError):
        return {"nivel": None}
    if precio <= 0:
        return {"nivel": None}

    mejor = None
    candidatos = [(f"nivel{i}", f"Nivel {i}") for i in range(1, 6)]
    candidatos.append(("deseado", "Deseado"))
    for clave, etiqueta in candidatos:
        v = entry.get(clave)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        desvio = (precio - v) / v
        if abs(desvio) <= TOLERANCIA_NIVEL and (mejor is None or abs(desvio) < abs(mejor[2])):
            mejor = (clave, etiqueta, desvio, v)
    if mejor is None:
        return {"nivel": None}
    return {"nivel": mejor[0], "nivel_etiqueta": mejor[1],
            "precio_nivel": round(mejor[3], 4),
            "desvio_pct": round(mejor[2] * 100, 2)}


def niveles_comprados(entry: dict) -> list:
    """Niveles que ya están comprados, según la campanita apagada.

    Convenio de la Cartera: la alerta de un nivel de compra se apaga cuando ese nivel YA se
    ha comprado — deja de tener sentido avisar de algo que ya hiciste. Eso convierte un
    ajuste de la interfaz en el único registro que existe de en qué niveles entraste, así
    que se usa para reconstruir los lotes en vez de pedírtelo otra vez.

    `deseado` queda fuera a propósito: en esta Cartera es el nivel de VENTA (la columna se
    llama "Deseado / Venta"), no una compra.
    """
    out = []
    for i in range(1, 6):
        precio = entry.get(f"nivel{i}")
        if precio in (None, "", 0):
            continue
        try:
            precio = float(precio)
        except (TypeError, ValueError):
            continue
        if precio <= 0:
            continue
        # Solo False cuenta. None significa "nunca se tocó", que no es lo mismo que apagada.
        if entry.get(f"alert_nivel{i}") is False:
            out.append({"nivel": f"nivel{i}", "etiqueta": f"Nivel {i}", "precio": precio})
    # De más caro a más barato: es el orden en que se van tocando al caer, o sea el orden
    # cronológico probable de las compras.
    out.sort(key=lambda n: n["precio"], reverse=True)
    return out


def estado_niveles(entry: dict, compras: list, abiertos: list) -> dict:
    """Campanitas que hay que cambiar, mirando el libro COMPLETO y no solo lo abierto.

    La diferencia importa: un nivel del que ya no queda nada puede ser "vendido entero"
    (hay compras suyas en el libro → se enciende) o "nunca comprado" (no hay ninguna → no
    se toca, porque la campanita la habrás puesto tú).
    """
    con_compras = {c.get("nivel") for c in compras if c.get("nivel")}
    vivas = {}
    for lote in abiertos:
        nivel = lote.get("nivel")
        if nivel:
            vivas[nivel] = vivas.get(nivel, 0) + (lote.get("acciones_abiertas") or 0)

    cambios = {}
    for i in range(1, 6):
        clave = f"nivel{i}"
        if clave not in con_compras:
            continue                      # nunca comprado por el libro: no es asunto suyo
        deseado = not (vivas.get(clave, 0) > 1e-9)   # sin acciones vivas -> encendida
        if entry.get(f"alert_{clave}") is not deseado:
            cambios[f"alert_{clave}"] = deseado
    return cambios


def plan_importacion(entry: dict) -> dict:
    """Propone los lotes de una posición a partir de lo que ya hay en la Cartera.

    El problema: la Cartera guarda un precio MEDIO y un total de acciones, no las compras.
    Pero con las campanitas se sabe además EN QUÉ NIVELES se compró, y con eso el reparto
    deja de ser una invención en dos de los tres casos:

      · Un nivel  -> todo el paquete a ese nivel. Exacto.
      · Dos       -> hay dos incógnitas (las acciones de cada uno) y dos datos (el total y
                     el precio medio): sale una única solución. EXACTO, no estimado.
      · Tres o más-> queda indeterminado. Se propone un reparto proporcional y se marca
                     como estimación para que se corrija a mano.

    Devuelve siempre `exacto` para que la interfaz no presente una estimación como si fuera
    un dato: el reparto cambia la ganancia de cada venta futura.
    """
    total = entry.get("acciones")
    medio = entry.get("compra")
    try:
        total = float(total or 0)
        medio = float(medio or 0)
    except (TypeError, ValueError):
        total = medio = 0
    if total <= 0 or medio <= 0:
        return {"lotes": [], "exacto": False,
                "motivo": "La posición no tiene número de acciones o precio de compra."}

    niveles = niveles_comprados(entry)

    def _lote(nivel, acciones, precio):
        return {"nivel": (nivel or {}).get("nivel"),
                "nivel_etiqueta": (nivel or {}).get("etiqueta"),
                "acciones": round(acciones, 6), "precio": round(precio, 4)}

    if not niveles:
        return {"lotes": [_lote(None, total, medio)], "exacto": True,
                "motivo": ("Ningún nivel figura como comprado (todas las campanitas están "
                           "encendidas), así que se registra una sola compra al precio "
                           "medio que tienes.")}

    if len(niveles) == 1:
        # El precio medio ES el precio de esa compra; se usa él y no el del nivel, porque
        # la ejecución real casi nunca cae exactamente en el nivel.
        return {"lotes": [_lote(niveles[0], total, medio)], "exacto": True,
                "motivo": f"Solo {niveles[0]['etiqueta']} figura comprado: todo el paquete va ahí."}

    if len(niveles) == 2:
        p1, p2 = niveles[0]["precio"], niveles[1]["precio"]
        if abs(p1 - p2) < 1e-9:
            s1 = total / 2
        else:
            # s1*p1 + s2*p2 = total*medio  y  s1 + s2 = total
            s1 = total * (medio - p2) / (p1 - p2)
        s2 = total - s1
        if s1 < -1e-6 or s2 < -1e-6:
            # El precio medio cae FUERA del rango de los dos niveles: los datos no encajan
            # (una comisión grande, un nivel editado después de comprar…). Inventar un
            # reparto negativo sería peor que decirlo.
            return {"lotes": [_lote(None, total, medio)], "exacto": False,
                    "motivo": (f"Tu precio medio ({medio}) no queda entre {niveles[1]['etiqueta']} "
                               f"({p2}) y {niveles[0]['etiqueta']} ({p1}), así que no se puede "
                               "repartir. Se propone una sola compra al precio medio; "
                               "corrígela a mano si lo sabes.")}
        return {"lotes": [_lote(niveles[0], s1, p1), _lote(niveles[1], s2, p2)],
                "exacto": True,
                "motivo": (f"Con {niveles[0]['etiqueta']} y {niveles[1]['etiqueta']} comprados, "
                           "tu total de acciones y tu precio medio solo admiten un reparto "
                           "posible: este.")}

    # Tres o más: hay infinitas combinaciones, pero NO todas valen. El total de acciones y
    # tu precio medio son datos ciertos, y un reparto que no los reproduzca está mal aunque
    # "parezca razonable": a partes iguales el coste sale el de la media de los NIVELES, que
    # no es lo que pagaste. (Medido con una posición real: 166,20 $ en vez de 142,43 $.)
    #
    # Se parte del reparto a partes iguales y se desplaza lo MÍNIMO necesario para que el
    # precio medio cuadre. Entre los infinitos repartos válidos se elige el más cercano al
    # equitativo, que es la suposición más neutra que se puede hacer sin más información.
    #
    #   s_i = S/n + λ(p_i − p̄)   con   λ = S(media_real − p̄) / Σ(p_i − p̄)²
    n = len(niveles)
    precios = [x["precio"] for x in niveles]
    p_medio_niveles = sum(precios) / n
    varianza = sum((p - p_medio_niveles) ** 2 for p in precios)

    if varianza < 1e-9:
        reparto = [total / n] * n           # todos los niveles al mismo precio
    else:
        lam = total * (medio - p_medio_niveles) / varianza
        reparto = [total / n + lam * (p - p_medio_niveles) for p in precios]

    if any(x < -1e-6 for x in reparto):
        # Para cuadrar tu media harían falta acciones negativas en algún nivel: los datos no
        # encajan. Se vuelve al reparto equitativo y se dice que la media no cuadra, en vez
        # de colar un número imposible.
        reparto = [total / n] * n
        aviso = (f"Figuran {n} niveles comprados, pero con sus precios no se puede llegar a "
                 f"tu precio medio ({medio}). Se reparte a partes iguales: revísalo, porque "
                 "el reparto cambia la ganancia de cada venta.")
    else:
        aviso = (f"Figuran {n} niveles comprados. Con tres o más hay varios repartos posibles; "
                 "se ha elegido el más equilibrado de los que reproducen tu precio medio "
                 f"({medio}). Revísalo si sabes cuántas compraste en cada uno.")

    lotes = [_lote(x, r, x["precio"]) for x, r in zip(niveles, reparto)]
    return {"lotes": lotes, "exacto": False, "motivo": aviso}


def nueva_compra(symbol: str, acciones: float, precio: float, fecha: str = None,
                 comision: float = 0.0, divisa: str = "USD", tasa: float = None,
                 nivel: str = None, notas: str = "") -> dict:
    """Construye el apunte de una compra. No toca la base de datos."""
    acciones = float(acciones)
    precio = float(precio)
    if acciones <= 0:
        raise ValueError("El número de acciones debe ser mayor que cero.")
    if precio <= 0:
        raise ValueError("El precio de compra debe ser mayor que cero.")
    comision = float(comision or 0.0)
    if comision < 0:
        raise ValueError("La comisión no puede ser negativa.")
    return {
        "id": str(uuid.uuid4()),
        "tipo": "compra",
        "symbol": (symbol or "").strip().upper(),
        "fecha": (fecha or _hoy())[:10],
        "acciones": acciones,
        "precio": precio,
        "comision": comision,
        "divisa": _divisa(divisa),
        # En euros el cambio es 1: guardar otra cosa es guardar un error.
        "tasa": 1.0 if _divisa(divisa) == "EUR" else tasa,           # divisa por 1 EUR el día de la compra
        "nivel": nivel,         # "nivel3", "deseado"… o None si fue fuera de niveles
        "notas": notas or "",
        "created_at": _ahora(),
    }


def nueva_venta(symbol: str, acciones: float, precio: float, fecha: str = None,
                comision: float = 0.0, divisa: str = "USD", tasa: float = None,
                notas: str = "") -> dict:
    acciones = float(acciones)
    precio = float(precio)
    if acciones <= 0:
        raise ValueError("El número de acciones vendidas debe ser mayor que cero.")
    if precio <= 0:
        raise ValueError("El precio de venta debe ser mayor que cero.")
    comision = float(comision or 0.0)
    if comision < 0:
        raise ValueError("La comisión no puede ser negativa.")
    return {
        "id": str(uuid.uuid4()),
        "tipo": "venta",
        "symbol": (symbol or "").strip().upper(),
        "fecha": (fecha or _hoy())[:10],
        "acciones": acciones,
        "precio": precio,
        "comision": comision,
        "divisa": _divisa(divisa),
        # En euros el cambio es 1: guardar otra cosa es guardar un error.
        "tasa": 1.0 if _divisa(divisa) == "EUR" else tasa,
        "notas": notas or "",
        "created_at": _ahora(),
    }


# ── El emparejamiento ────────────────────────────────────────────────────────

def _orden(compras: list, metodo: str) -> list:
    """Compras en el orden en que se consumen.

    Se desempata por created_at: dos compras del MISMO día en un orden arbitrario darían
    resultados distintos entre ejecuciones, y una cifra que baila no vale para nada.
    """
    clave = lambda c: (str(c.get("fecha") or ""), str(c.get("created_at") or ""))  # noqa: E731
    orden = sorted(compras, key=clave)
    return orden if metodo == FIFO else list(reversed(orden))


def emparejar(compras: list, cantidad: float, metodo: str = FIFO) -> tuple:
    """Reparte `cantidad` acciones vendidas entre los lotes disponibles.

    Devuelve (consumos, sin_cubrir). `sin_cubrir` > 0 significa que se están vendiendo más
    acciones de las que constan compradas: se informa en vez de fallar, porque puede ser
    simplemente que falte meter una compra antigua, y es mejor enseñar el descuadre que
    negarse a registrar la venta.

    Los lotes NO se modifican: se devuelve cuánto se toma de cada uno.
    """
    restante = float(cantidad)
    consumos = []
    for c in _orden(compras, metodo):
        libres = float(c.get("_libres", c.get("acciones") or 0))
        if libres <= 1e-9 or restante <= 1e-9:
            continue
        toma = min(libres, restante)
        restante -= toma
        acciones_lote = float(c.get("acciones") or 0) or 1.0
        comision_prorrateada = float(c.get("comision") or 0.0) * (toma / acciones_lote)
        consumos.append({
            "compra_id": c.get("id"),
            "fecha_compra": c.get("fecha"),
            "acciones": round(toma, 6),
            "precio_compra": c.get("precio"),
            "comision_parte": round(comision_prorrateada, 4),
            "tasa_compra": tasa_de(c),
            "nivel": c.get("nivel"),
            "coste_divisa": round(toma * float(c.get("precio") or 0) + comision_prorrateada, 4),
            # Para descontar del lote EXACTO, no del primero que tenga el mismo id.
            "_k": c.get("_k"),
        })
    return consumos, round(max(restante, 0.0), 6)


def tasa_de(op: dict):
    """Cambio que hay que aplicar a una operación, mirando SU divisa.

    Un euro vale un euro: si la operación está denominada en EUR el cambio es 1, aunque el
    apunte guarde otro número. No es una preferencia, es aritmética, y por eso se impone al
    LEER y no solo al escribir: los apuntes ya guardados con un cambio equivocado se
    corrigen solos en cuanto se vuelven a mostrar, sin reescribir la base de datos.

    De dónde salía el error: la divisa de la operación y su tipo de cambio llegaban por
    caminos distintos —la ficha, el formulario, Yahoo— y nadie comprobaba que fueran
    coherentes. Dividir un importe en euros entre 1,1655 encoge el coste un 14% y convierte
    una posición plana recién comprada en una ganancia de tres cifras que nunca existió.
    """
    if (op.get("divisa") or "").strip().upper() == "EUR":
        return 1.0
    return op.get("tasa")


def _a_eur(importe: float, tasa) -> float:
    """La tasa es 'unidades de divisa por 1 EUR' (como cotiza EURUSD): se DIVIDE."""
    if tasa is None:
        return None
    try:
        tasa = float(tasa)
    except (TypeError, ValueError):
        return None
    if tasa <= 0:
        return None
    return importe / tasa


def resultado_venta(venta: dict, consumos: list) -> dict:
    """Ganancia de una venta ya emparejada, en la divisa original y en euros."""
    acciones = float(venta.get("acciones") or 0)
    precio = float(venta.get("precio") or 0)
    comision = float(venta.get("comision") or 0.0)
    tasa_venta = tasa_de(venta)

    bruto_divisa = acciones * precio
    ingreso_divisa = bruto_divisa - comision
    coste_divisa = sum(c["coste_divisa"] for c in consumos)
    ganancia_divisa = ingreso_divisa - coste_divisa

    ingreso_eur = _a_eur(ingreso_divisa, tasa_venta)
    # Cada lote a SU cambio: es lo que de verdad se pagó en euros.
    costes_eur = [_a_eur(c["coste_divisa"], c.get("tasa_compra")) for c in consumos]
    completo = all(x is not None for x in costes_eur) and ingreso_eur is not None
    coste_eur = sum(x for x in costes_eur if x is not None) if costes_eur else 0.0
    ganancia_eur = (ingreso_eur - coste_eur) if completo else None

    # Cuánto de la diferencia es el movimiento del euro y no la acción. Es la pregunta que
    # aparece sola en cuanto ves que ganaste en dólares y menos en euros.
    efecto_divisa_eur = None
    if completo:
        sin_efecto = _a_eur(ganancia_divisa, tasa_venta)
        if sin_efecto is not None:
            efecto_divisa_eur = ganancia_eur - sin_efecto

    pct_divisa = (ganancia_divisa / coste_divisa * 100) if coste_divisa else None
    pct_eur = (ganancia_eur / coste_eur * 100) if (completo and coste_eur) else None

    return {
        "acciones": round(acciones, 6),
        "precio_venta": precio,
        "comision_venta": round(comision, 4),
        "bruto_divisa": round(bruto_divisa, 2),
        "ingreso_divisa": round(ingreso_divisa, 2),
        "coste_divisa": round(coste_divisa, 2),
        "ganancia_divisa": round(ganancia_divisa, 2),
        "pct": round(pct_divisa, 2) if pct_divisa is not None else None,
        "ingreso_eur": round(ingreso_eur, 2) if ingreso_eur is not None else None,
        "coste_eur": round(coste_eur, 2) if completo else None,
        "ganancia_eur": round(ganancia_eur, 2) if ganancia_eur is not None else None,
        "pct_eur": round(pct_eur, 2) if pct_eur is not None else None,
        "efecto_divisa_eur": round(efecto_divisa_eur, 2) if efecto_divisa_eur is not None else None,
        # `exacto` marca si TODOS los cambios necesarios estaban disponibles. Sin esta marca
        # un total mezclaría cifras exactas con estimaciones y aparentaría una precisión
        # que no tiene.
        "exacto": bool(completo),
        "lotes": consumos,
        "comisiones_totales": round(comision + sum(c["comision_parte"] for c in consumos), 2),
    }


def reproducir(compras: list, ventas: list, metodo: str = FIFO) -> dict:
    """Reproduce el libro entero de UN símbolo y devuelve el estado y lo realizado.

    Las ventas se aplican en orden cronológico: vender antes de una compra posterior no
    puede consumirla, y hacerlo daría una ganancia imposible.
    """
    if metodo not in METODOS:
        raise ValueError(f"Método desconocido: {metodo}")

    # Copia de trabajo: la función no debe tocar lo que le pasan.
    lotes = []
    for c in sorted(compras, key=lambda x: (str(x.get("fecha") or ""),
                                            str(x.get("created_at") or ""))):
        d = dict(c)
        d["_libres"] = float(d.get("acciones") or 0)
        # Una llave propia, del reparto y no del dato. El descuento buscaba el lote por su
        # `id` y se quedaba con el PRIMERO que coincidiera: con dos lotes que compartan id
        # —o a los que les falte— toda la venta se le carga a uno y los demás se quedan
        # intactos, así que el libro deja de cuadrar sin que nada falle a la vista.
        d["_k"] = len(lotes)
        lotes.append(d)

    realizadas, descuadres = [], 0.0
    for v in sorted(ventas, key=lambda x: (str(x.get("fecha") or ""),
                                           str(x.get("created_at") or ""))):
        # Solo cuentan los lotes comprados en la fecha de la venta o antes.
        disponibles = [l for l in lotes if str(l.get("fecha") or "") <= str(v.get("fecha") or "")]
        consumos, sin_cubrir = emparejar(disponibles, float(v.get("acciones") or 0), metodo)
        por_k = {l["_k"]: l for l in lotes}
        for c in consumos:
            l = por_k.get(c.get("_k"))
            if l is not None:
                l["_libres"] = round(l["_libres"] - c["acciones"], 6)
        descuadres += sin_cubrir
        res = resultado_venta(v, consumos)
        res["sin_cubrir"] = sin_cubrir
        # Una venta que no tiene lotes que la cubran NO es exacta, por muchos tipos de
        # cambio que tenga: le falta la base de coste. Sin esto se colaba en el total
        # "exacto" de euros con coste 0 y su ingreso entero contaba como ganancia — el
        # Realizado salía hinchado y con pinta de cifra buena.
        if sin_cubrir > 1e-9:
            res["exacto"] = False
        # Cuántas quedaban vivas DESPUÉS de esta venta, y cuántas ventas hubo ANTES.
        #
        # Hacen falta las dos. Que una venta cierre la posición NO obliga a que los tres
        # métodos coincidan, como se decía aquí: solo lo obliga si además es la PRIMERA
        # venta. Con ventas anteriores, cada método dejó vivos lotes distintos —FIFO gastó
        # los viejos y LIFO los nuevos— así que las acciones que quedaban no eran las
        # mismas para uno que para otro, y su coste tampoco. Lo que coincide entonces es
        # el TOTAL de todas las ventas, no el de la última.
        res["abiertas_despues"] = round(sum(max(l["_libres"], 0.0) for l in lotes), 6)
        res["cierra_posicion"] = res["abiertas_despues"] <= 1e-9
        res["ventas_antes"] = len(realizadas)
        realizadas.append({**{k: val for k, val in v.items() if k != "_libres"}, **res,
                           "metodo": metodo})

    abiertos = []
    for l in lotes:
        if l["_libres"] > 1e-9:
            abierto = {k: val for k, val in l.items() if k not in ("_libres", "_k")}
            abierto["acciones_abiertas"] = round(l["_libres"], 6)
            parte = l["_libres"] / (float(l.get("acciones") or 0) or 1.0)
            abierto["coste_divisa"] = round(
                l["_libres"] * float(l.get("precio") or 0)
                + float(l.get("comision") or 0.0) * parte, 4)
            abierto["coste_eur"] = _a_eur(abierto["coste_divisa"], tasa_de(l))
            if abierto["coste_eur"] is not None:
                abierto["coste_eur"] = round(abierto["coste_eur"], 2)
            abiertos.append(abierto)

    acciones_abiertas = round(sum(a["acciones_abiertas"] for a in abiertos), 6)
    coste_abierto_divisa = round(sum(a["coste_divisa"] for a in abiertos), 2)
    costes_eur = [a["coste_eur"] for a in abiertos]
    coste_abierto_eur = (round(sum(costes_eur), 2)
                         if costes_eur and all(x is not None for x in costes_eur) else None)

    return {
        "metodo": metodo,
        "abiertos": abiertos,
        "acciones_abiertas": acciones_abiertas,
        "coste_abierto_divisa": coste_abierto_divisa,
        "coste_abierto_eur": coste_abierto_eur,
        # Precio medio de LO QUE QUEDA, que es lo que importa para juzgar la posición viva.
        # Depende del método: tras vender parte, FIFO y LIFO dejan lotes distintos abiertos.
        "precio_medio": (round(coste_abierto_divisa / acciones_abiertas, 4)
                         if acciones_abiertas > 1e-9 else None),
        "ventas": realizadas,
        "ganancia_realizada_divisa": round(sum(v["ganancia_divisa"] for v in realizadas), 2),
        # None, y NO 0, cuando ninguna venta tiene los tipos de cambio necesarios. Un 0 se
        # lee como "no has ganado nada", que es una afirmación; lo cierto es que no se sabe.
        # Además hacía que dos métodos con resultados distintos parecieran idénticos.
        "ganancia_realizada_eur": (
            round(sum(v["ganancia_eur"] for v in realizadas if v["ganancia_eur"] is not None), 2)
            if any(v["ganancia_eur"] is not None for v in realizadas) else None),
        "todo_exacto": all(v["exacto"] for v in realizadas) if realizadas else True,
        "acciones_sin_cubrir": round(descuadres, 6),
    }


def fechas_en_que_toco(velas: list, precio: float, max_fechas: int = 6) -> dict:
    """Cuándo el precio pasó por `precio`, según el histórico diario.

    Sirve para no tener que recordar la fecha de cada compra. Comprando por niveles, se
    entra cuando el precio LLEGA al nivel, así que el día en que la vela cubrió ese precio
    es una estimación mucho mejor que poner la de hoy — y la fecha decide el tipo de cambio
    con el que se calculan los euros.

    Devuelve la PRIMERA vez como estimación y cuántas veces ocurrió: si fueron varias, la
    estimación es ambigua y hay que decirlo en vez de elegir por el usuario.

    `velas` son diccionarios con date/high/low (los que ya sirve el gráfico).
    """
    try:
        precio = float(precio)
    except (TypeError, ValueError):
        return {"fecha": None, "toques": 0}
    if precio <= 0 or not velas:
        return {"fecha": None, "toques": 0}

    fechas = []
    for v in velas:
        try:
            alto = float(v.get("high"))
            bajo = float(v.get("low"))
        except (TypeError, ValueError):
            continue
        # La vela CUBRE el precio: ese día se pudo comprar ahí.
        if bajo <= precio <= alto:
            f = str(v.get("date") or "")[:10]
            if f:
                fechas.append(f)
    fechas.sort()
    return {
        "fecha": fechas[0] if fechas else None,
        "toques": len(fechas),
        "primera": fechas[0] if fechas else None,
        "ultima": fechas[-1] if fechas else None,
        # Las intermedias no ayudan a decidir y llenarían la pantalla.
        "otras": fechas[1:max_fechas] if len(fechas) > 1 else [],
    }


def media_ponderada(compras: list, ventas: list) -> dict:
    """Precio medio ponderado (PMP), que es lo que enseña DEGIRO — y casi todos los brókeres.

    Es un método DISTINTO de FIFO y LIFO, no una variante: no hay lotes. Todas las acciones
    valen lo mismo, la media, y al vender se retira a ese precio. Consecuencia que despista
    mucho: **vender no cambia tu precio medio**. Solo lo mueven las compras.

    Se comprobó con datos reales: con 25 acciones en 5 niveles (279/240/219/190,60/178) la
    media sale 221,32 $ y el bróker enseñaba 221,54 $ para las 15 que quedaban tras vender
    10. Ni FIFO (195,87 $) ni LIFO (246,00 $) se acercan; el PMP sí, porque no se movió.

    Está aquí SOLO para poder cuadrar las dos pantallas. No sirve para lo que se quiere
    saber de verdad —cuánto se ganó en cada nivel— porque bajo PMP los niveles dejan de
    existir: todas las acciones cuestan lo mismo. Y en España tampoco vale para la
    declaración, donde es obligatorio FIFO (art. 37.2 LIRPF).

    Se recorre en orden cronológico porque el orden importa: comprar barato DESPUÉS de una
    venta baja la media, y calcularlo de otra forma daría un número que nunca existió.
    """
    ops = sorted([{**c, "_t": "c"} for c in compras] + [{**v, "_t": "v"} for v in ventas],
                 key=lambda x: (str(x.get("fecha") or ""), str(x.get("created_at") or "")))
    media, cantidad, realizado, ventas_pmp = 0.0, 0.0, 0.0, []
    # La media EN EUROS se lleva en paralelo, cada compra a SU cambio. Sin ella la posición
    # abierta solo se puede valorar pasando la media en dólares al cambio de hoy, y eso
    # borra el efecto del euro: es la diferencia entre los -68 € que enseña el bróker y un
    # número inventado. Si a una compra le falta el cambio, la media en euros deja de
    # existir para siempre (arrastrarla a medias daría una cifra falsa sin avisar).
    media_eur, eur_completo = 0.0, True
    media_limpia = 0.0
    for op in ops:
        n = float(op.get("acciones") or 0)
        precio = float(op.get("precio") or 0)
        comision = float(op.get("comision") or 0.0)
        if op["_t"] == "c":
            # La media SIN comisiones, en paralelo. Es la que enseña el bróker: su "precio
            # medio" es un PRECIO —lo que pagaste por acción— y no un coste, así que no
            # lleva la comisión dentro. La de al lado sí la lleva, y debe llevarla: es la
            # que sirve para calcular lo que ganas. Son dos cifras distintas y las dos
            # hacen falta; la diferencia entre ellas es exactamente lo que te ha costado
            # operar, repartido por acción.
            media_limpia = (((cantidad * media_limpia + n * precio) / (cantidad + n))
                            if cantidad + n > 1e-9 else 0.0)
            coste = cantidad * media + n * precio + comision
            en_eur = _a_eur(n * precio + comision, tasa_de(op))
            if en_eur is None:
                eur_completo = False
            elif eur_completo:
                media_eur = ((cantidad * media_eur + en_eur) / (cantidad + n)
                             if cantidad + n > 1e-9 else 0.0)
            cantidad += n
            media = (coste / cantidad) if cantidad > 1e-9 else 0.0
        else:
            usadas = min(n, cantidad)
            ganancia = n * precio - comision - usadas * media
            realizado += ganancia
            # La misma cuenta EN EUROS. Antes solo salía en dólares, y esta es justo la
            # cifra que el bróker enseña para que cuadres: comparar "420,14 $" con los
            # "~300 €" de DEGIRO obliga a convertir a mano cada vez, que es exactamente lo
            # que hace que parezca que uno de los dos miente.
            #
            # El coste va al cambio de CADA compra (dentro de `media_eur`) y el ingreso al
            # del día de la venta: la diferencia entre las dos es el efecto del euro, y
            # borrarla usando un solo cambio daría un número que no es de nadie.
            ingreso_eur = _a_eur(n * precio - comision, tasa_de(op))
            coste_eur_v = (usadas * media_eur) if eur_completo else None
            ganancia_eur = (round(ingreso_eur - coste_eur_v, 2)
                            if ingreso_eur is not None and coste_eur_v is not None
                            else None)
            # La ficha de una venta usa la MISMA plantilla para los tres métodos, así que
            # un campo que falte aquí no se queda callado: sale como un hueco —el ingreso en
            # dólares aparecía en "—"— o dispara un aviso que no toca. Sin `exacto`, la
            # pantalla anunciaba "no se puede calcular la ganancia en euros" justo encima de
            # la ganancia en euros, ya calculada.
            ventas_pmp.append({"id": op.get("id"), "fecha": op.get("fecha"),
                               "acciones": n, "coste_divisa": round(usadas * media, 2),
                               "ingreso_divisa": round(n * precio - comision, 2),
                               "exacto": ganancia_eur is not None,
                               "ganancia_divisa": round(ganancia, 2),
                               "pct": (round(ganancia / (usadas * media) * 100, 2)
                                       if usadas * media else None),
                               "coste_eur": (round(coste_eur_v, 2)
                                             if coste_eur_v is not None else None),
                               "ingreso_eur": (round(ingreso_eur, 2)
                                               if ingreso_eur is not None else None),
                               "ganancia_eur": ganancia_eur,
                               "pct_eur": (round(ganancia_eur / coste_eur_v * 100, 2)
                                           if ganancia_eur is not None and coste_eur_v
                                           else None)})
            cantidad = max(0.0, cantidad - n)
            # La media NO se toca: es lo que define al método y lo que hace que la cifra del
            # bróker no se mueva al vender.
    return {
        "precio_medio": round(media, 4) if cantidad > 1e-9 else None,
        # El mismo precio medio SIN comisiones: el que cuadra con la pantalla del bróker.
        "precio_medio_sin_comision": round(media_limpia, 4) if cantidad > 1e-9 else None,
        "precio_medio_eur": (round(media_eur, 4)
                             if eur_completo and cantidad > 1e-9 else None),
        "acciones": round(cantidad, 6),
        "coste_divisa": round(cantidad * media, 2) if cantidad > 1e-9 else 0.0,
        "coste_eur": (round(cantidad * media_eur, 2)
                      if eur_completo and cantidad > 1e-9 else None),
        "ganancia_realizada_divisa": round(realizado, 2),
        "ventas": ventas_pmp,
    }


def valorar_ponderado(pmp: dict, precio_actual, tasa_hoy) -> dict:
    """Latente valorando la posición POR MEDIA PONDERADA, que es como lo hace el bróker.

    Misma forma que `valorar_abierto` para poder enseñar las dos y compararlas. La
    diferencia entre ambas no es un error de ninguna: FIFO/LIFO dejan vivos unos lotes
    concretos —los caros o los baratos— mientras que el PMP reparte el coste entre todas
    las acciones. Lo que una se apunta de más en el latente, la otra ya se lo apuntó en lo
    realizado; sumadas dan lo mismo.
    """
    n = pmp.get("acciones") or 0
    vacio = {"acciones": n, "valor_divisa": None, "coste_divisa": None, "pnl_divisa": None,
             "valor_eur": None, "coste_eur": None, "pnl_eur": None,
             "pct": None, "pct_eur": None}
    if n <= 1e-9 or precio_actual in (None, ""):
        return vacio
    try:
        precio_actual = float(precio_actual)
    except (TypeError, ValueError):
        return vacio

    valor_divisa = n * precio_actual
    coste_divisa = pmp.get("coste_divisa") or 0
    pnl_divisa = valor_divisa - coste_divisa
    valor_eur = _a_eur(valor_divisa, tasa_hoy)
    coste_eur = pmp.get("coste_eur")
    pnl_eur = (valor_eur - coste_eur) if (valor_eur is not None and coste_eur is not None) else None
    return {
        "acciones": n,
        "valor_divisa": round(valor_divisa, 2),
        "coste_divisa": round(coste_divisa, 2),
        "pnl_divisa": round(pnl_divisa, 2),
        "valor_eur": round(valor_eur, 2) if valor_eur is not None else None,
        "coste_eur": round(coste_eur, 2) if coste_eur is not None else None,
        "pnl_eur": round(pnl_eur, 2) if pnl_eur is not None else None,
        "pct": round(pnl_divisa / coste_divisa * 100, 2) if coste_divisa else None,
        "pct_eur": (round(pnl_eur / coste_eur * 100, 2)
                    if (pnl_eur is not None and coste_eur) else None),
    }


def valorar_abierto(estado: dict, precio_actual, tasa_hoy) -> dict:
    """Ganancia LATENTE (lo que llevas ganado sin vender) en divisa y en euros.

    El coste va al cambio de cada compra y el valor de hoy al cambio de hoy: así el número
    incluye el movimiento del euro, que es real aunque no lo hayas materializado. Es
    exactamente la diferencia entre lo que ingresarías vendiendo ahora y lo que pusiste.
    """
    n = estado.get("acciones_abiertas") or 0
    # `acciones` va SIEMPRE con el número real, tambien cuando no se puede valorar. Devolver
    # 0 aquí hacía que la Cartera enseñara "0 acciones" en posiciones que sí existen: quien
    # llama mezcla este resultado con el resto de la posición y el 0 pisaba el bueno.
    _sin_valorar = {"acciones": n, "valor_divisa": None, "coste_divisa": None,
                    "pnl_divisa": None, "valor_eur": None, "coste_eur": None,
                    "pnl_eur": None, "pct": None, "pct_eur": None}
    if n <= 1e-9 or precio_actual in (None, ""):
        return _sin_valorar
    try:
        precio_actual = float(precio_actual)
    except (TypeError, ValueError):
        return _sin_valorar

    valor_divisa = n * precio_actual
    coste_divisa = estado.get("coste_abierto_divisa") or 0
    pnl_divisa = valor_divisa - coste_divisa

    valor_eur = _a_eur(valor_divisa, tasa_hoy)
    coste_eur = estado.get("coste_abierto_eur")
    pnl_eur = (valor_eur - coste_eur) if (valor_eur is not None and coste_eur is not None) else None

    return {
        "acciones": n,
        "valor_divisa": round(valor_divisa, 2),
        "coste_divisa": round(coste_divisa, 2),
        "pnl_divisa": round(pnl_divisa, 2),
        "pct": round(pnl_divisa / coste_divisa * 100, 2) if coste_divisa else None,
        "valor_eur": round(valor_eur, 2) if valor_eur is not None else None,
        "coste_eur": coste_eur,
        "pnl_eur": round(pnl_eur, 2) if pnl_eur is not None else None,
        "pct_eur": (round(pnl_eur / coste_eur * 100, 2)
                    if (pnl_eur is not None and coste_eur) else None),
    }


def comparar_metodos(compras: list, ventas: list) -> dict:
    """FIFO y LIFO sobre las mismas operaciones, con la diferencia ya calculada.

    Se devuelven juntos y etiquetados a propósito: enseñar un solo número sin decir de qué
    método es invita a meterlo en la declaración, y solo FIFO vale para eso.
    """
    fifo = reproducir(compras, ventas, FIFO)
    lifo = reproducir(compras, ventas, LIFO)
    # La diferencia se mide sobre la DIVISA, que siempre se conoce, y en euros solo si los
    # dos lados la tienen. Compararlos por el importe en euros hacía que dos resultados
    # distintos parecieran iguales cuando faltaban los tipos de cambio.
    f_eur, l_eur = fifo["ganancia_realizada_eur"], lifo["ganancia_realizada_eur"]
    hay_eur = f_eur is not None and l_eur is not None
    dif_divisa = round(fifo["ganancia_realizada_divisa"] - lifo["ganancia_realizada_divisa"], 2)
    return {
        "fifo": fifo,
        "lifo": lifo,
        "diferencia_divisa": dif_divisa,
        "diferencia_eur": round(f_eur - l_eur, 2) if hay_eur else None,
        "coinciden": abs(dif_divisa) < 0.005 and (not hay_eur or abs(f_eur - l_eur) < 0.005),
        "oficial": FIFO,
        "nota_fiscal": (
            "FIFO es el método obligatorio en España para acciones cotizadas "
            "(art. 37.2 de la Ley del IRPF): es la cifra que va a tu declaración. LIFO se "
            "muestra solo como referencia de gestión."),
    }
