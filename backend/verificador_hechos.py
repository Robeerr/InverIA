"""¿Lo que dice cada HECHO está en el texto que recibió el modelo?

QUÉ COMPRUEBA

Las ANCLAS de cada hecho —cifras con su escala («1.914 millones», «53 %»), fechas y
nombres propios o términos citados— y si aparecen en el texto que se le envió al modelo.
Los hechos se escriben en español y los documentos de la SEC están en inglés, así que se
comparan VALORES, no cadenas: «1.914 millones» casa con «$1,914 million», «964.700
millones» con «$964.7 billion» y «26 de octubre de 2026» con «October 26, 2026».

QUÉ NO COMPRUEBA

Que el hecho esté bien CONTADO. Encontrar las cifras de un hecho en el texto no garantiza
que digan lo mismo: el modelo puede haber cruzado dos cifras ciertas. Esto es un detector
de lo que NO aparece, no un certificado de exactitud. Un «no localizado» hay que mirarlo;
un «localizado» no exime de leer.

Tampoco mira la confianza ni toca la lectura: no reescribe, no puntúa, no borra. Devuelve
un informe que se guarda al lado.
"""
import re
import unicodedata

VERSION = 1

LOCALIZADO = "localizado"            # todas las anclas decisivas aparecen
PARCIAL = "parcial"                  # unas sí y otras no
NO_LOCALIZADO = "no_localizado"      # ninguna aparece
SOLO_DEBILES = "solo_anclas_debiles"  # solo números pequeños o años: no deciden
SIN_ANCLAS = "sin_anclas"            # nada comprobable mecánicamente

_MESES_ES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
             "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
             "noviembre": 11, "diciembre": 12}
_MESES_EN = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
             "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
             "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
             "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}

_ES = "|".join(_MESES_ES)
_EN = "|".join(sorted(_MESES_EN, key=len, reverse=True))
_FECHA_ES = re.compile(rf"\b(\d{{1,2}})\s+de\s+({_ES})\s+(?:de|del)\s+(\d{{4}})\b", re.I)
_MES_ANO_ES = re.compile(rf"\b({_ES})\s+(?:de|del)\s+(\d{{4}})\b", re.I)
_FECHA_EN_MDY = re.compile(rf"\b({_EN})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I)
_FECHA_EN_DMY = re.compile(rf"\b(\d{{1,2}})\s+({_EN})\.?,?\s+(\d{{4}})\b", re.I)
_FECHA_EN_MY = re.compile(rf"\b({_EN})\.?,?\s+(\d{{4}})\b", re.I)
_FECHA_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_FECHA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

#: Un número del HECHO: cifras con puntos y comas, sin una letra pegada delante
#: («FY30», «Q3» no son cifras que buscar).
_NUM_HECHO = re.compile(r"(?<![A-Za-z\d])(\d+(?:[.,]\d+)*)(?!\d)")
#: Un número del DOCUMENTO, en formato estadounidense.
_NUM_TEXTO = re.compile(r"(?<![A-Za-z\d.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d])")

_ESCALA_ES = re.compile(
    r"^\s*(mil\s+millones|miles\s+de\s+millones|millones|mill[oó]n|billones|bill[oó]n|mil)\b",
    re.I)
_ESCALA_EN = re.compile(r"^\s?(trillion|billion|million|thousand)\b|^(bn|mm|b|m)\b", re.I)
_PORCENTAJE = re.compile(r"^\s*(%|por\s*ciento|percent|per\s*cent)", re.I)

_FACTOR_ES = {"mil millones": 1e9, "miles de millones": 1e9, "millones": 1e6,
              "millon": 1e6, "billones": 1e12, "billon": 1e12, "mil": 1e3}
_FACTOR_EN = {"trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3,
              "bn": 1e9, "b": 1e9, "mm": 1e6, "m": 1e6}

#: Palabras que en un hecho escrito en español van con mayúscula y NO son nombres que
#: se puedan buscar en un documento en inglés.
_NO_NOMBRES = {
    "el", "la", "los", "las", "un", "una", "se", "su", "sus", "del", "al", "en", "con",
    "por", "para", "sin", "tras", "según", "durante", "cada", "este", "esta", "estos",
    "estas", "no", "si", "y", "o", "de", "a", "serie", "clase", "estados", "unidos",
    "formulario", "anexo", "anexos", "ley", "consejo", "comisión", "acuerdo", "acuerdos",
    "ingresos", "beneficio", "flujo", "margen", "objetivo", "compromiso", "previsión",
    "proyección", "pico", "completada", "tratamiento", "gobernanza", "condiciones",
    "partes", "fecha", "ecuación", "representa", "registro", "junta", "presidente",
    "director", "directora", "consejero", "sociedad", "compañía", "empresa", "grupo",
    "trimestre", "ejercicio", "fiscal", "dólares", "acciones", "acción",
}


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKC", texto or "")


def _igual(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


# ── Las anclas de un hecho ───────────────────────────────────────────────────

def _valores(token: str) -> set:
    """Los valores que puede significar una cifra escrita por el modelo.

    El modelo escribe en español («1.914», «4,500» = 4,5) pero a veces copia el formato
    del documento («4,500» = cuatro mil quinientos). Cuando la cifra es ambigua se prueban
    las dos lecturas: un falso «no localizado» es peor que una coincidencia doble.
    """
    valores = set()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", token):
        valores.add(float(token.replace(".", "").replace(",", ".")))
    elif re.fullmatch(r"\d+,\d+", token):
        valores.add(float(token.replace(",", ".")))
    elif re.fullmatch(r"\d+", token):
        valores.add(float(token))
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", token):
        valores.add(float(token.replace(",", "")))
    elif re.fullmatch(r"\d+\.\d+", token):
        valores.add(float(token))
    return valores


def _es_año(valor: float, token: str) -> bool:
    return token.isdigit() and len(token) == 4 and 1900 <= valor <= 2100


def _cifras_del_hecho(hecho: str, ocupado: list) -> list:
    anclas = []
    for m in _NUM_HECHO.finditer(hecho):
        if any(a <= m.start() < b for a, b in ocupado):
            continue
        token = m.group(1).rstrip(".,")
        valores = _valores(token)
        if not valores:
            continue
        despues = hecho[m.end():m.end() + 30]
        antes = hecho[max(0, m.start() - 2):m.start()]
        escala = None
        e = _ESCALA_ES.match(despues)
        if e:
            clave = unicodedata.normalize("NFKD", re.sub(r"\s+", " ", e.group(1).lower()))
            clave = "".join(c for c in clave if not unicodedata.combining(c))
            escala = _FACTOR_ES.get(clave)
        porcentaje = bool(_PORCENTAJE.match(despues))
        dinero = "$" in antes or bool(re.match(r"^\s*(?:millones\s+de\s+)?d[oó]lares", despues, re.I))
        decimal = bool(re.search(r"[.,]", token))
        valor = min(valores)
        fuerte = (porcentaje or escala is not None or dinero or decimal
                  or (max(valores) >= 100 and not _es_año(valor, token)))
        anclas.append({"tipo": "cifra", "texto": hecho[m.start():m.end()].strip(),
                       "valores": sorted(valores), "escala": escala,
                       "porcentaje": porcentaje, "fuerte": fuerte})
    return anclas


def _fechas_del_hecho(hecho: str):
    anclas, ocupado = [], []
    for m in _FECHA_ES.finditer(hecho):
        anclas.append({"tipo": "fecha", "texto": m.group(0), "fuerte": True,
                       "fecha": (int(m.group(3)), _MESES_ES[m.group(2).lower()],
                                 int(m.group(1)))})
        ocupado.append((m.start(), m.end()))
    for m in _MES_ANO_ES.finditer(hecho):
        if any(a <= m.start() < b for a, b in ocupado):
            continue
        anclas.append({"tipo": "fecha", "texto": m.group(0), "fuerte": True,
                       "fecha": (int(m.group(2)), _MESES_ES[m.group(1).lower()])})
        ocupado.append((m.start(), m.end()))
    return anclas, ocupado


def _parece_ingles(texto: str) -> bool:
    if re.search(r"[áéíóúñ¿¡ÁÉÍÓÚÑ]", texto) or not re.search(r"[A-Za-z]", texto):
        return False
    palabras = re.findall(r"[A-Za-z]+", texto.lower())
    return not any(p in _NO_NOMBRES for p in palabras)


def _nombres_del_hecho(hecho: str) -> list:
    """Términos citados en inglés y nombres propios. Los acrónimos no: «IA», «BPA» o
    «EE. UU.» son españoles y no estarían en el documento."""
    anclas, vistos = [], set()

    def añadir(tipo, texto):
        texto = texto.strip(" .,;:'\"’”")
        clave = texto.lower()
        if len(texto) >= 3 and clave not in vistos:
            vistos.add(clave)
            anclas.append({"tipo": tipo, "texto": texto, "fuerte": True})

    for m in re.finditer(r"[\"“'‘«]([^\"”'’»]{3,80})[\"”'’»]", hecho):
        if _parece_ingles(m.group(1)):
            añadir("termino", m.group(1))
    for m in re.finditer(r"\(([^()]{2,80})\)", hecho):
        if re.search(r"[A-Z]", m.group(1)) and _parece_ingles(m.group(1)):
            añadir("termino", m.group(1))

    palabras = list(re.finditer(r"[A-Z][\w&.\-]*", hecho))
    secuencias, actual = [], []
    for p in palabras:
        if actual and re.fullmatch(r"\s*(?:&\s*)?", hecho[actual[-1].end():p.start()]):
            actual.append(p)
        else:
            if actual:
                secuencias.append(actual)
            actual = [p]
    if actual:
        secuencias.append(actual)
    for sec in secuencias:
        validas = [p for p in sec
                   if p.group(0).lower().strip(".") not in _NO_NOMBRES
                   and not re.fullmatch(r"[A-Z.]{1,6}", p.group(0))]
        if not validas:
            continue
        al_principio = sec[0].start() == 0
        if len(validas) == 1 and (al_principio or len(validas[0].group(0)) < 4):
            continue
        añadir("nombre", hecho[validas[0].start():validas[-1].end()])
    return anclas


def anclas_de(hecho: str) -> list:
    hecho = _normalizar(hecho)
    fechas, ocupado = _fechas_del_hecho(hecho)
    return fechas + _cifras_del_hecho(hecho, ocupado) + _nombres_del_hecho(hecho)


# ── El texto, indexado una sola vez ──────────────────────────────────────────

def indexar(texto: str) -> dict:
    texto = _normalizar(texto)
    numeros = []
    for m in _NUM_TEXTO.finditer(texto):
        valor = float(m.group(1).replace(",", ""))
        despues = texto[m.end():m.end() + 16]
        e = _ESCALA_EN.match(despues)
        factor = _FACTOR_EN.get((e.group(1) or e.group(2)).lower()) if e else None
        numeros.append((valor, valor * factor if factor else None, m.start()))
    fechas = {}

    def apuntar(clave, pos):
        fechas.setdefault(clave, pos)

    for m in _FECHA_EN_MDY.finditer(texto):
        mes = _MESES_EN[m.group(1).lower()]
        apuntar((int(m.group(3)), mes, int(m.group(2))), m.start())
        apuntar((int(m.group(3)), mes), m.start())
    for m in _FECHA_EN_DMY.finditer(texto):
        mes = _MESES_EN[m.group(2).lower()]
        apuntar((int(m.group(3)), mes, int(m.group(1))), m.start())
        apuntar((int(m.group(3)), mes), m.start())
    for m in _FECHA_EN_MY.finditer(texto):
        apuntar((int(m.group(2)), _MESES_EN[m.group(1).lower()]), m.start())
    for m in _FECHA_NUM.finditer(texto):
        mes, dia = int(m.group(1)), int(m.group(2))
        if 1 <= mes <= 12 and 1 <= dia <= 31:
            apuntar((int(m.group(3)), mes, dia), m.start())
            apuntar((int(m.group(3)), mes), m.start())
    for m in _FECHA_ISO.finditer(texto):
        mes, dia = int(m.group(2)), int(m.group(3))
        if 1 <= mes <= 12 and 1 <= dia <= 31:
            apuntar((int(m.group(1)), mes, dia), m.start())
            apuntar((int(m.group(1)), mes), m.start())
    plano = re.sub(r"\s+", " ", texto).lower()
    # Posiciones de `plano` a `texto`: el fragmento se recorta del texto original.
    return {"texto": texto, "plano": plano, "numeros": numeros, "fechas": fechas}


def _buscar_cifra(ancla: dict, indice: dict):
    escala = ancla.get("escala")
    for valor, escalado, pos in indice["numeros"]:
        for c in ancla["valores"]:
            if escala is not None:
                if escalado is not None and _igual(escalado, c * escala):
                    return pos, "escalado"
                if _igual(valor, c):
                    return pos, "cifra"
            else:
                if _igual(valor, c):
                    return pos, "cifra"
                if escalado is not None and _igual(escalado, c):
                    return pos, "escalado"
    return None, None


def _buscar_nombre(ancla: dict, indice: dict):
    frase = re.sub(r"\s+", " ", ancla["texto"]).lower()
    pos = indice["plano"].find(frase)
    if pos >= 0:
        return _posicion_en_texto(indice, frase), "frase"
    palabras = [p for p in re.findall(r"[a-z0-9&\-]{3,}", frase)]
    if palabras and all(re.search(rf"\b{re.escape(p)}\b", indice["plano"]) for p in palabras):
        return _posicion_en_texto(indice, palabras[0]), "palabras"
    return None, None


def _posicion_en_texto(indice: dict, trozo: str):
    m = re.search(re.escape(trozo).replace(r"\ ", r"\s+"), indice["texto"], re.I)
    return m.start() if m else None


def _fragmento(texto: str, posiciones: list, ancho: int = 160):
    """El trozo del texto donde se concentran las anclas encontradas."""
    posiciones = [p for p in posiciones if p is not None]
    if not posiciones:
        return None
    centro = max(posiciones, key=lambda c: sum(1 for p in posiciones if abs(p - c) <= 200))
    ini, fin = max(0, centro - ancho), min(len(texto), centro + ancho)
    trozo = re.sub(r"\s+", " ", texto[ini:fin]).strip()
    return ("…" if ini > 0 else "") + trozo + ("…" if fin < len(texto) else "")


def verificar_uno(hecho: str, indice: dict) -> dict:
    anclas = anclas_de(hecho)
    posiciones = []
    for a in anclas:
        if a["tipo"] == "cifra":
            pos, como = _buscar_cifra(a, indice)
        elif a["tipo"] == "fecha":
            pos = indice["fechas"].get(a["fecha"])
            como = "fecha" if pos is not None else None
        else:
            pos, como = _buscar_nombre(a, indice)
        a["encontrada"] = como is not None
        a["como"] = como
        if como is not None and a["fuerte"]:
            posiciones.append(pos)
    decisivas = [a for a in anclas if a["fuerte"]]
    if not anclas:
        estado = SIN_ANCLAS
    elif not decisivas:
        estado = SOLO_DEBILES
    elif all(a["encontrada"] for a in decisivas):
        estado = LOCALIZADO
    elif any(a["encontrada"] for a in decisivas):
        estado = PARCIAL
    else:
        estado = NO_LOCALIZADO
    return {
        "hecho": hecho,
        "estado": estado,
        "anclas": [{k: a[k] for k in ("tipo", "texto", "fuerte", "encontrada", "como")}
                   for a in anclas],
        "fragmento": _fragmento(indice["texto"], posiciones),
    }


def verificar(hechos, texto: str) -> dict:
    """El informe de una investigación: cada hecho con su estado, y el recuento."""
    indice = indexar(texto)
    detalle = []
    for i, hecho in enumerate(hechos or []):
        r = verificar_uno(str(hecho or ""), indice)
        r["indice"] = i
        detalle.append(r)
    cuenta = {e: 0 for e in (LOCALIZADO, PARCIAL, NO_LOCALIZADO, SOLO_DEBILES, SIN_ANCLAS)}
    for r in detalle:
        cuenta[r["estado"]] += 1
    return {"version": VERSION, "hechos": len(detalle), "recuento": cuenta,
            "no_localizados": [r["indice"] for r in detalle if r["estado"] == NO_LOCALIZADO],
            "detalle": detalle}
