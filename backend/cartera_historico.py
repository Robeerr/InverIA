"""El valor de la cartera día a día, y qué se puede deducir de esa serie.

POR QUÉ NO EXISTÍA

InverIA sabía en todo momento cuánto vale tu cartera HOY, y nada más. Nadie guardaba
esa cifra, así que no había forma de dibujar cómo ha evolucionado ni de medir su
volatilidad: las dos cosas necesitan una serie, y una serie hay que empezar a
escribirla algún día. Este módulo es ese día.

Consecuencia honesta: los primeros gráficos estarán vacíos y la volatilidad no será
medible hasta dentro de un mes. No es un fallo, es lo que pasa cuando se empieza a
medir algo — y es infinitamente mejor que dibujar doce meses inventados.

EL ÍNDICE DE SALUD NO ES UN NÚMERO SUELTO

Se pidió un «78/100». Un número compuesto que no se puede abrir es exactamente la
métrica inventada que este proyecto lleva toda la vida evitando: nadie sabría si el
78 baja por concentración o por estructura, ni cuánto pesa cada cosa.

Así que `indice_salud` devuelve SIEMPRE sus componentes, cada uno con su nota, su
peso y la frase que lo explica. La pantalla enseña el número; el número se puede
abrir. Y los umbrales de más abajo son DECISIONES, no hechos del mercado: están
escritos con su motivo al lado para poder discutirlos.

COMPONENTES QUE NO ESTÁN, Y POR QUÉ

  · Liquidez. Haría falta el saldo en efectivo, y hoy solo entra pegado a mano en el
    extracto de margen: no es un dato que el sistema tenga, es uno que el usuario
    escribe a veces.
  · Volatilidad. Necesita la serie que este módulo empieza a guardar hoy. Aparece
    sola en cuanto haya `MINIMO_PARA_VOLATILIDAD` snapshots, y hasta entonces el
    índice se reparte entre los componentes que sí se pueden medir.
"""
from datetime import datetime, timezone
from typing import Optional

# Cuántos días hacen falta para que una volatilidad signifique algo. Con menos, la
# desviación de cuatro puntos no describe la cartera: describe cuatro días.
MINIMO_PARA_VOLATILIDAD = 20

# Días que se conservan. Dos años cubren de sobra cualquier gráfico de la pantalla y
# evitan que la colección crezca sin final.
DIAS_MAXIMOS = 730

# ── Umbrales. Son decisiones; el motivo va al lado de cada uno. ──────────────
# Concentración SECTORIAL. Por debajo de 20% no hay nada que avisar. A partir de 60%
# la cartera es una apuesta a un sector, se llame como se llame.
SECTOR_BIEN, SECTOR_MAL = 20.0, 60.0
# Concentración por POSICIÓN. Más estrecho que el sectorial a propósito: que un solo
# valor pese un 40% es más peligroso que que un sector pese un 40%, porque un sector
# al menos reparte entre varias empresas.
POSICION_BIEN, POSICION_MAL = 10.0, 40.0
# Volatilidad anualizada de la propia cartera. 15% es lo que ronda una cartera
# diversificada de acciones grandes; 60% es una cartera concentrada en crecimiento.
VOL_BIEN, VOL_MAL = 15.0, 60.0

SESIONES_ANO = 252


def _nota(valor: float, bien: float, mal: float) -> float:
    """0-100 interpolando entre dos umbrales, donde `bien` puede ser mayor o menor.

    Se satura en los extremos a propósito: pasar del 60% al 70% de concentración no
    empeora la nota porque ya estaba en cero — y seguir restando daría a un solo
    componente el poder de hundir el índice entero.
    """
    if valor is None:
        return None
    if bien < mal:                                   # menos es mejor
        if valor <= bien:
            return 100.0
        if valor >= mal:
            return 0.0
        return round((mal - valor) / (mal - bien) * 100, 1)
    if valor >= bien:                                # más es mejor
        return 100.0
    if valor <= mal:
        return 0.0
    return round((valor - mal) / (bien - mal) * 100, 1)


def snapshot(valor_eur: float, invertido_eur: float, realizado_eur: float = 0.0,
             posiciones: int = 0, cuando: Optional[str] = None) -> Optional[dict]:
    """La foto de un día. `dia` es la clave: un solo registro por fecha.

    Se guarda el valor Y lo invertido, no solo el primero. Sin el segundo no se puede
    distinguir una cartera que sube porque el mercado sube de una que sube porque has
    metido más dinero — y son cosas distintas que en un gráfico se ven igual.
    """
    try:
        valor = float(valor_eur)
        invertido = float(invertido_eur)
    except (TypeError, ValueError):
        return None
    if valor <= 0:
        return None
    ahora = datetime.now(timezone.utc) if cuando is None else None
    return {
        "dia": (cuando or ahora.date().isoformat())[:10],
        "valor_eur": round(valor, 2),
        "invertido_eur": round(invertido, 2),
        "realizado_eur": round(float(realizado_eur or 0), 2),
        "posiciones": int(posiciones or 0),
        "guardado_en": (ahora or datetime.now(timezone.utc)).isoformat(),
    }


def serie(snapshots: list) -> list:
    """Los snapshots ordenados por día y sin repetidos, listos para dibujar."""
    por_dia = {}
    for s in snapshots or []:
        d = (s or {}).get("dia")
        if d:
            por_dia[d] = s          # el último escrito de ese día manda
    return [por_dia[d] for d in sorted(por_dia)]


def volatilidad_anualizada(snapshots: list) -> Optional[float]:
    """Volatilidad de la cartera en %, o None si no hay serie suficiente.

    Sobre el rendimiento DIARIO del valor. Devolver None y no 0 es deliberado: cero
    afirmaría que la cartera no se mueve, y lo que pasa es que aún no lo sabemos.
    """
    s = serie(snapshots)
    if len(s) < MINIMO_PARA_VOLATILIDAD:
        return None
    rends = []
    for a, b in zip(s, s[1:]):
        va, vb = a.get("valor_eur"), b.get("valor_eur")
        if va and vb and va > 0:
            rends.append(vb / va - 1.0)
    if len(rends) < MINIMO_PARA_VOLATILIDAD - 1:
        return None
    media = sum(rends) / len(rends)
    var = sum((r - media) ** 2 for r in rends) / (len(rends) - 1)
    return round((var ** 0.5) * (SESIONES_ANO ** 0.5) * 100, 1)


def indice_salud(concentracion_sector: Optional[float],
                 concentracion_posicion: Optional[float],
                 pct_valor_en_tendencia: Optional[float],
                 volatilidad: Optional[float] = None) -> dict:
    """El índice, SIEMPRE con sus componentes al lado.

    Los pesos se renormalizan sobre lo que se ha podido medir. Así el índice existe
    desde el primer día con tres componentes y pasa a cuatro cuando hay serie, sin
    que el número dé un salto artificial por haber contado un cero donde no había
    dato. Un componente ausente NO puntúa cero: desaparece del reparto.
    """
    comps = [
        {"clave": "concentracion_sector", "nombre": "Concentración sectorial", "peso": 30,
         "valor": concentracion_sector, "unidad": "%",
         "nota": _nota(concentracion_sector, SECTOR_BIEN, SECTOR_MAL),
         "explica": "Cuánto pesa tu sector mayor. Una caída sectorial alcanza esa parte entera."},
        {"clave": "concentracion_posicion", "nombre": "Concentración por posición", "peso": 30,
         "valor": concentracion_posicion, "unidad": "%",
         "nota": _nota(concentracion_posicion, POSICION_BIEN, POSICION_MAL),
         "explica": "Cuánto pesa tu mayor posición. Un solo valor decidiendo el resultado."},
        {"clave": "estructura", "nombre": "Estructura", "peso": 25,
         "valor": pct_valor_en_tendencia, "unidad": "%",
         "nota": _nota(pct_valor_en_tendencia, 100.0, 40.0),
         "explica": "Qué parte de tu dinero está en acciones que NO están en tendencia bajista."},
        {"clave": "volatilidad", "nombre": "Volatilidad", "peso": 15,
         "valor": volatilidad, "unidad": "%",
         "nota": _nota(volatilidad, VOL_BIEN, VOL_MAL),
         "explica": ("Cuánto se mueve tu cartera, anualizado. Se calcula sobre el "
                     f"histórico diario: hacen falta {MINIMO_PARA_VOLATILIDAD} días.")},
    ]
    medibles = [c for c in comps if c["nota"] is not None]
    total_peso = sum(c["peso"] for c in medibles)
    for c in comps:
        c["medible"] = c["nota"] is not None
        c["peso_efectivo"] = 0
    # El peso EFECTIVO es el que de verdad se ha aplicado, que no es el nominal cuando
    # falta algún componente. Enseñarlo evita que el número parezca salir de un reparto
    # que no es el que se hizo.
    #
    # Se reparte por RESTO MAYOR y no redondeando cada uno por su cuenta: con 30/30/25
    # sobre 85, el redondeo simple da 35+35+29 = 99, y un reparto que no suma cien
    # parece un error de cálculo aunque el índice esté bien. El sobrante va al
    # componente cuya parte decimal se quedó más cerca de subir.
    if total_peso:
        exactos = [(c["peso"] / total_peso * 100, c) for c in medibles]
        for v, c in exactos:
            c["peso_efectivo"] = int(v)
        sobra = 100 - sum(c["peso_efectivo"] for c in medibles)
        for v, c in sorted(exactos, key=lambda x: x[0] - int(x[0]), reverse=True)[:sobra]:
            c["peso_efectivo"] += 1
    puntuacion = (round(sum(c["nota"] * c["peso"] for c in medibles) / total_peso)
                  if total_peso else None)
    return {
        "puntuacion": puntuacion,
        "etiqueta": _etiqueta(puntuacion),
        "componentes": comps,
        "medidos": len(medibles),
        "de": len(comps),
    }


def _etiqueta(p: Optional[int]) -> Optional[str]:
    """La palabra que acompaña al número. Es lo que se lee de un vistazo, así que los
    cortes están donde cambia lo que habría que HACER, no en múltiplos de diez."""
    if p is None:
        return None
    if p >= 75:
        return "Estable"
    if p >= 55:
        return "Aceptable"
    if p >= 35:
        return "Desequilibrada"
    return "Frágil"
