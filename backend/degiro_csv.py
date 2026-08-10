"""Lector del CSV de Transacciones de DEGIRO.

Por qué este fichero y no Account.csv
--------------------------------------
Account.csv es el libro de CAJA: cada movimiento de dinero por separado (la retirada de
divisa, el ingreso, la comisión, el importe de la venta…). Reconstruir una operación desde
ahí obliga a volver a juntar cuatro apuntes y a adivinar cuáles van juntos.

Transactions.csv trae la operación entera en una fila, y con los datos que hasta ahora se
estaban ESTIMANDO: el tipo de cambio que te aplicaron de verdad, la comisión de AutoFX y la
de tramitación. Deja de hacer falta suponer nada.

El formato, verificado contra un fichero real (08/2026)
-------------------------------------------------------
Columnas: Date · Time · Product · ISIN · Reference exchange · Venue · Quantity · Price ·
(divisa) · Local value · (divisa) · Value EUR · Exchange rate · AutoFX Fee ·
Transaction and/or third party fees · Total EUR · Order ID

Detalles que hay que respetar o los números salen mal:

  · El separador DECIMAL es la coma: "214,2050" son 214,205 y no doscientos catorce mil.
    Abriendo el fichero con una hoja de cálculo en configuración inglesa se ve "2,142,050",
    que es la misma cifra mal interpretada. Comprobado: 2142,05 de importe entre 10 acciones
    da exactamente 214,205.

  · `Quantity` NEGATIVO es una VENTA. Es la única señal fiable: el signo del importe
    depende de si se mira desde la caja o desde la posición.

  · `Exchange rate` son unidades de divisa por 1 EUR (1,1563 = un euro son 1,1563 dólares),
    el mismo convenio que usa el resto de la aplicación. Verificado: 655,85 $ / 1,1563 =
    567,20 €, que es justo lo que pone la columna en euros.

  · Las comisiones vienen en EUROS aunque la operación sea en dólares. Se convierten con el
    tipo de cambio DE ESA FILA, que es el que se aplicó.
"""
import csv
import hashlib
import io
import logging
import re

logger = logging.getLogger(__name__)

#: Nombres posibles de cada columna. DEGIRO exporta en el idioma de la cuenta, así que se
#: aceptan varias formas en vez de dar por hecho el inglés.
_ALIAS = {
    "fecha": ("date", "fecha"),
    "hora": ("time", "hora"),
    "producto": ("product", "producto"),
    "isin": ("isin",),
    "cantidad": ("quantity", "número", "numero", "cantidad"),
    "precio": ("price", "precio"),
    "importe_local": ("local value", "valor local"),
    "tasa": ("exchange rate", "tipo de cambio"),
    "fee_fx": ("autofx fee", "comisión autofx", "comision autofx"),
    "fee_op": ("transaction and/or third party fees", "transaction and/or third",
               "costes de transacción", "costes de transaccion",
               "transaction costs", "costes de transacción y/o externos"),
    "orden": ("order id", "id orden", "orderid"),
}


def _normaliza(cabecera: str) -> str:
    return re.sub(r"\s+", " ", (cabecera or "").strip().lower())


def _numero(valor):
    """Convierte un número de DEGIRO a float. Devuelve None si no lo es.

    La coma es el separador DECIMAL. Se contempla también el punto por si una exportación
    en otro idioma lo usa: manda el ÚLTIMO separador que aparezca, que es siempre el
    decimal, y el otro se descarta como separador de miles.
    """
    if valor is None:
        return None
    s = str(valor).strip().replace(" ", "").replace(" ", "")
    if not s or s in ("-", "n/a"):
        return None
    if "," in s and "." in s:
        s = (s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".")
             else s.replace(",", ""))
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _fecha_iso(valor) -> str:
    """dd-mm-aaaa (lo que usa DEGIRO) → aaaa-mm-dd.

    Si viniera ya en ISO se deja tal cual. Confundir el día con el mes cambiaría el tipo de
    cambio aplicado y, con él, los euros de la operación.
    """
    s = (str(valor or "")).strip()
    m = re.match(r"^(\d{2})[-/](\d{2})[-/](\d{4})$", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    return s if m else ""


def _texto(contenido):
    """Decodifica el fichero. None si no se puede con ninguna codificación conocida."""
    if not isinstance(contenido, bytes):
        return contenido
    for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return None


def _dialecto(texto: str) -> str:
    """Separador de campos. Con decimales por coma, el fichero suele ir con punto y coma;
    pero DEGIRO también exporta con coma y los campos entrecomillados."""
    primera = texto.split("\n", 1)[0]
    return ";" if primera.count(";") > primera.count(",") else ","


def _indice_columnas(cabeceras: list) -> dict:
    """Posición de cada campo. Se busca por nombre y no por posición fija: DEGIRO ha movido
    columnas entre versiones, y leer por número daría precios donde van comisiones."""
    normalizadas = [_normaliza(h) for h in cabeceras]
    idx = {}
    for campo, alias in _ALIAS.items():
        for i, h in enumerate(normalizadas):
            if any(h == a or h.startswith(a) for a in alias):
                idx[campo] = i
                break
    # La divisa va en la columna SIN nombre justo detrás del precio.
    if "precio" in idx and idx["precio"] + 1 < len(normalizadas):
        if not normalizadas[idx["precio"] + 1]:
            idx["divisa"] = idx["precio"] + 1
    return idx


def leer(contenido: bytes) -> dict:
    """Convierte el CSV en operaciones normalizadas.

    Devuelve {"operaciones": [...], "productos": [...], "errores": [...]}. Las filas que no
    se entienden se informan en vez de descartarse en silencio: una operación que falta
    descuadra la posición y no habría forma de saber por qué.
    """
    texto = _texto(contenido)
    if texto is None:
        return {"operaciones": [], "productos": [], "errores": ["No se pudo leer el fichero."]}

    filas = list(csv.reader(io.StringIO(texto), delimiter=_dialecto(texto)))
    if not filas:
        return {"operaciones": [], "productos": [], "errores": ["El fichero está vacío."]}

    idx = _indice_columnas(filas[0])
    faltan = [c for c in ("fecha", "producto", "isin", "cantidad", "precio") if c not in idx]
    if faltan:
        return {"operaciones": [], "productos": [],
                "errores": [f"No parece el CSV de Transacciones de DEGIRO: faltan las "
                            f"columnas {', '.join(faltan)}."]}

    operaciones, errores, productos = [], [], {}
    for n, fila in enumerate(filas[1:], start=2):
        if not any((c or "").strip() for c in fila):
            continue
        try:
            op = _fila_a_operacion(fila, idx)
        except Exception as e:
            errores.append(f"Línea {n}: {e}")
            continue
        if op is None:
            continue
        operaciones.append(op)
    # Contador de repetición en la huella, como en los dividendos: DEGIRO parte una orden en
    # varias ejecuciones y dos pueden ser IDÉNTICAS hasta en la hora y el nº de orden (pasó
    # con 2×5 CRWV a 90,55 el mismo segundo). Sin esto, la segunda se pierde en silencio y
    # la posición descuadra en exactamente esas acciones.
    vistas = {}
    for op in operaciones:
        n = vistas.get(op["huella"], 0)
        vistas[op["huella"]] = n + 1
        if n:
            op["huella"] = hashlib.sha1(
                f"{op['huella']}|{n}".encode()).hexdigest()[:16]
    for op in operaciones:
        productos.setdefault(op["isin"], {"isin": op["isin"], "producto": op["producto"],
                                          "operaciones": 0})
        productos[op["isin"]]["operaciones"] += 1

    operaciones.sort(key=lambda o: (o["fecha"], o.get("hora") or ""))
    return {"operaciones": operaciones,
            "productos": sorted(productos.values(), key=lambda p: p["producto"]),
            "errores": errores}


def _celda(fila, idx, campo):
    i = idx.get(campo)
    return fila[i] if i is not None and i < len(fila) else None


def _fila_a_operacion(fila, idx):
    cantidad = _numero(_celda(fila, idx, "cantidad"))
    precio = _numero(_celda(fila, idx, "precio"))
    fecha = _fecha_iso(_celda(fila, idx, "fecha"))
    if cantidad is None or precio is None or not fecha:
        return None                      # cabecera repetida o fila de resumen
    if abs(cantidad) < 1e-9:
        return None
    if precio <= 0:
        # Operación REAL a precio cero: ampliaciones liberadas, splits, entregas de
        # derechos. Antes se devolvía None y desaparecía sin dejar rastro — ni en `errores`
        # ni en `descartadas`— y como las acciones sí entraban en el bróker, la venta
        # posterior salía SIN COSTE y su ingreso entero contaba como ganancia. Pasó con
        # OHLA: 205 acciones vendidas sin compra registrada. Se avisa lanzando el error,
        # que `leer()` recoge en `errores` con el número de línea.
        raise ValueError(
            f"{'venta' if cantidad < 0 else 'entrega/compra'} de {abs(cantidad):g} "
            f"a precio 0 (ampliación, split o entrega de derechos): no se importa sola, "
            f"mira si hay que meterla a mano")

    divisa = (str(_celda(fila, idx, "divisa") or "USD").strip().upper() or "USD")
    tasa = _numero(_celda(fila, idx, "tasa"))
    if divisa == "EUR":
        tasa = 1.0

    # Las comisiones vienen en EUROS aunque la operación sea en dólares; se pasan a la
    # divisa de la operación con el tipo de cambio DE ESTA FILA, que es el que se aplicó.
    fees_eur = 0.0
    for campo in ("fee_fx", "fee_op"):
        v = _numero(_celda(fila, idx, campo))
        if v:
            fees_eur += abs(v)
    comision = fees_eur * tasa if (tasa and divisa != "EUR") else fees_eur

    orden = (str(_celda(fila, idx, "orden") or "")).strip()
    hora = (str(_celda(fila, idx, "hora") or "")).strip()
    isin = (str(_celda(fila, idx, "isin") or "")).strip().upper()
    producto = (str(_celda(fila, idx, "producto") or "")).strip()

    return {
        # Huella para no importar dos veces la misma operación. Incluye la hora y el precio
        # porque una misma orden puede ejecutarse en varios trozos el mismo día, y el ID de
        # orden se repite en todos ellos.
        "huella": hashlib.sha1(
            f"{fecha}|{hora}|{isin}|{cantidad}|{precio}|{orden}".encode()).hexdigest()[:16],
        "fecha": fecha,
        "hora": hora,
        "producto": producto,
        "isin": isin,
        # El signo de la CANTIDAD es la única señal fiable del sentido: el del importe
        # depende de si se mira desde la caja o desde la posición.
        "tipo": "venta" if cantidad < 0 else "compra",
        "acciones": abs(cantidad),
        "precio": precio,
        "divisa": divisa,
        "tasa": tasa,
        "comision": round(comision, 4),
        "orden": orden,
    }


# ── Account.csv: dividendos ──────────────────────────────────────────────────
# El otro fichero de DEGIRO, el libro de CAJA. Para las compras y ventas no sirve (obliga a
# recomponer cada operación desde cuatro apuntes), pero es el ÚNICO sitio donde están los
# dividendos: Transactions.csv solo tiene operaciones de compraventa.
#
# Y son dinero de verdad: en una cartera con varios años y valores que reparten, explican
# buena parte de la diferencia entre lo que dice el bróker y lo que sale de las operaciones.

_COL_CUENTA = {
    "fecha": ("date", "fecha"),
    "producto": ("product", "producto"),
    "isin": ("isin",),
    "descripcion": ("description", "descripción", "descripcion"),
    "fx": ("fx", "tipo de cambio"),
    "cambio": ("change", "variación", "variacion"),
}

#: La retención se comprueba ANTES que el dividendo: su descripción contiene la palabra
#: "dividendo", así que al revés todas las retenciones se tomarían por dividendos y el
#: importe neto saldría inflado.
_RETENCION = ("retención del impuesto", "retencion del impuesto", "dividend tax",
              "withholding tax", "impuesto sobre dividendo")
_DIVIDENDO = ("dividendo", "dividend")
# Costes que SOLO viven en el Account.csv: intereses del dinero prestado (operar con saldo
# en negativo) y conectividad con mercados. Son lo que separa el total propio del Total P/L
# del bróker. Las comisiones de transacción NO: esas ya vienen por operación en el
# Transactions.csv y cogerlas también de aquí las contaría dos veces.
_COSTE = ("interés", "interes", "interest", "conectividad", "connectivity",
          "conexión", "conexion")


def _clasificar(descripcion: str):
    d = (descripcion or "").strip().lower()
    if any(t in d for t in _RETENCION):
        return "retencion"
    if any(t in d for t in _DIVIDENDO):
        return "dividendo"
    if "transac" in d:
        return None
    if any(t in d for t in _COSTE):
        return "coste"
    return None


def leer_cuenta(contenido) -> dict:
    """Extrae los DIVIDENDOS (y sus retenciones) del Account.csv.

    Todo lo demás del fichero se ignora a propósito: las compras, ventas y comisiones ya
    vienen mejor desde Transactions.csv, y cogerlas también de aquí las duplicaría.
    """
    texto = _texto(contenido)
    if texto is None:
        return {"dividendos": [], "errores": ["No se pudo leer el fichero."]}

    filas = list(csv.reader(io.StringIO(texto), delimiter=_dialecto(texto)))
    if not filas:
        return {"dividendos": [], "errores": ["El fichero está vacío."]}

    cabeceras = [_normaliza(h) for h in filas[0]]
    idx = {}
    for campo, alias in _COL_CUENTA.items():
        for i, h in enumerate(cabeceras):
            if any(h == a or h.startswith(a) for a in alias):
                idx[campo] = i
                break
    if "descripcion" not in idx or "cambio" not in idx:
        return {"dividendos": [],
                "errores": ["No parece el CSV de Cuenta (Account) de DEGIRO: falta la "
                            "columna de descripción o la de importe."]}
    # La columna "Change" lleva la DIVISA; el importe va en la de al lado, sin nombre.
    idx["divisa"] = idx["cambio"]
    idx["importe"] = idx["cambio"] + 1

    # Dos apuntes IDÉNTICOS el mismo día (mismo valor, importe y divisa) son posibles: un
    # pago partido, o dos posiciones del mismo valor. Sin distinguirlos, la huella colisiona
    # y el segundo se toma por duplicado y se pierde. Se lleva la cuenta de las repeticiones.
    vistas = {}
    dividendos, errores = [], []
    for n, fila in enumerate(filas[1:], start=2):
        if not any((c or "").strip() for c in fila):
            continue
        tipo = _clasificar(_celda(fila, idx, "descripcion"))
        if tipo is None:
            continue
        importe = _numero(_celda(fila, idx, "importe"))
        fecha = _fecha_iso(_celda(fila, idx, "fecha"))
        if importe is None or not fecha:
            errores.append(f"Línea {n}: dividendo sin importe o sin fecha.")
            continue
        isin = (str(_celda(fila, idx, "isin") or "")).strip().upper()
        divisa = (str(_celda(fila, idx, "divisa") or "EUR")).strip().upper() or "EUR"
        base = f"{fecha}|{isin}|{tipo}|{importe}|{divisa}"
        vistas[base] = vistas.get(base, 0) + 1
        dividendos.append({
            # El orden de las filas dentro del fichero es estable entre exportaciones, así
            # que el contador tampoco cambia y la huella sigue sirviendo para no duplicar.
            "huella": hashlib.sha1(
                f"{base}|{vistas[base]}".encode()).hexdigest()[:16],
            "fecha": fecha,
            "producto": (str(_celda(fila, idx, "producto") or "")).strip(),
            "isin": isin,
            "tipo": tipo,
            # La retención llega ya en negativo en el fichero; se respeta el signo para que
            # sumar dividendos y retenciones dé el neto sin tener que acordarse de restar.
            "importe": importe,
            "divisa": divisa,
            "tasa": _numero(_celda(fila, idx, "fx")),
        })

    dividendos.sort(key=lambda d: d["fecha"])
    return {"dividendos": dividendos, "errores": errores}


def resumen_dividendos(dividendos: list) -> dict:
    brutos = [d for d in dividendos if d["tipo"] == "dividendo"]
    retenciones = [d for d in dividendos if d["tipo"] == "retencion"]
    fechas = sorted(d["fecha"] for d in dividendos if d["fecha"])
    return {
        "total": len(dividendos),
        "cobros": len(brutos),
        "retenciones": len(retenciones),
        "desde": fechas[0] if fechas else None,
        "hasta": fechas[-1] if fechas else None,
    }


def resumen(operaciones: list) -> dict:
    """Cifras de cabecera para enseñar antes de confirmar la importación."""
    compras = [o for o in operaciones if o["tipo"] == "compra"]
    ventas = [o for o in operaciones if o["tipo"] == "venta"]
    fechas = sorted(o["fecha"] for o in operaciones if o["fecha"])
    return {
        "total": len(operaciones),
        "compras": len(compras),
        "ventas": len(ventas),
        "desde": fechas[0] if fechas else None,
        "hasta": fechas[-1] if fechas else None,
        "comisiones": round(sum(o["comision"] for o in operaciones), 2),
    }
