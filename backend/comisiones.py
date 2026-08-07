"""Estimación de las comisiones del bróker cuando no se conocen las reales.

Por qué existe
--------------
Las comisiones suman al coste al comprar y restan al ingreso al vender, así que sin ellas
la ganancia sale inflada y nunca cuadra con el extracto. Pero pedirlas a mano en cada
operación tiene un problema práctico: si no las tienes delante, el campo se queda vacío y
entonces el número que se enseña es optimista SIN avisar.

Estimarlas con la tarifa pública es mejor que dejarlas en cero: se acerca mucho más a la
realidad, y queda marcado como estimación para que se pueda corregir con el extracto.

Lo que NO hace
--------------
No hay conexión con el bróker: esto no lee tu cuenta. Es la tarifa publicada aplicada al
importe de la operación. Si tienes condiciones distintas, o el bróker cambia precios, hay
que ajustar las constantes de abajo o meter la comisión a mano.

La tarifa de DEGIRO (consultada 08/2026)
-----------------------------------------
  · Acciones de EE.UU. y España: 1 € de comisión + 1 € de tramitación = 2 € por operación.
  · Conversión de divisa: AutoFX (la opción por defecto) 0,25% del importe. El cambio
    MANUAL no es gratis: 10 € + 0,25%, así que solo compensa moviendo mucho de golpe.
  · Conectividad: hasta 2,50 €/año por mercado. NO se incluye aquí: es un coste anual de la
    cuenta, no de la operación, y repartirlo entre operaciones daría una cifra inventada
    distinta según cuántas hagas.

Fuentes: https://www.degiro.es/tarifas/calcular-comisiones
"""
import logging

logger = logging.getLogger(__name__)

#: Comisión fija por operación, EN EUROS (1 € comisión + 1 € tramitación).
COMISION_FIJA_EUR = 2.0

#: Conversión de divisa. DEGIRO lo llama AutoFX y es la opción por defecto. Es el coste que
#: más pasa desapercibido: no aparece como "comisión" en ningún sitio, va incorporado al
#: tipo de cambio que te aplican.
FX_AUTO_PCT = 0.0025

#: El cambio MANUAL no es gratis: es 10 € + el mismo 0,25%. Solo compensa moviendo mucho
#: dinero de golpe, porque los 10 € son fijos por cambio y no por operación.
FX_MANUAL_FIJO_EUR = 10.0

#: Divisas que no llevan conversión (la cuenta es en euros).
SIN_CONVERSION = {"EUR"}


def estimar(importe_divisa: float, divisa: str = "USD", tasa: float = None,
            fx_manual: bool = False) -> dict:
    """Comisión estimada de UNA operación, en la divisa de la operación.

    `importe_divisa` es el bruto (acciones × precio).
    `tasa` son unidades de divisa por 1 EUR, para pasar los 2 € fijos a la divisa.
    `fx_manual` a True si cambias la divisa a mano: son 10 € MÁS el mismo 0,25%.

    Devuelve el desglose además del total, porque un número suelto no se puede comprobar
    contra el extracto y acabaría aceptándose sin mirar.
    """
    divisa = (divisa or "USD").strip().upper() or "USD"
    try:
        importe_divisa = abs(float(importe_divisa or 0))
    except (TypeError, ValueError):
        importe_divisa = 0.0

    # Los 2 € fijos, expresados en la divisa de la operación. Sin tipo de cambio no se
    # puede convertir: se devuelve solo lo que sí se sabe, en vez de suponer una paridad.
    if divisa in SIN_CONVERSION:
        fija = COMISION_FIJA_EUR
    elif tasa and float(tasa) > 0:
        fija = COMISION_FIJA_EUR * float(tasa)
    else:
        fija = None

    conversion = 0.0
    if divisa not in SIN_CONVERSION:
        conversion = importe_divisa * FX_AUTO_PCT
        # El manual lleva ADEMÁS 10 € fijos. Tenerlo como "sin coste" hacía que la opción
        # cara pareciera la barata.
        if fx_manual and fija is not None:
            conversion += FX_MANUAL_FIJO_EUR * (1.0 if divisa in SIN_CONVERSION else (tasa or 1.0))

    total = None if fija is None else round(fija + conversion, 4)
    return {
        "total": total,
        "fija": round(fija, 4) if fija is not None else None,
        "conversion_divisa": round(conversion, 4),
        "divisa": divisa,
        "estimada": True,
        "detalle": _detalle(fija, conversion, divisa, fx_manual),
    }


def _detalle(fija, conversion, divisa, fx_manual) -> str:
    partes = []
    if fija is not None:
        partes.append(f"{COMISION_FIJA_EUR:.2f} € de comisión y tramitación")
    if divisa not in SIN_CONVERSION:
        partes.append(
            f"{FX_MANUAL_FIJO_EUR:.0f} € + {FX_AUTO_PCT * 100:.2f}% de cambio manual"
            if fx_manual else
            f"{FX_AUTO_PCT * 100:.2f}% de conversión de divisa (AutoFX)")
    if not partes:
        return "Sin comisión estimada."
    return "Estimado con la tarifa pública de DEGIRO: " + " + ".join(partes) + "."
