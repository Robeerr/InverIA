"""Tipos de cambio para calcular en EUROS lo ganado en operaciones hechas en otra divisa.

Por qué hace falta el cambio de LAS DOS fechas y no solo el de hoy: si compras a 1,05 y
vendes a 1,15 USD/EUR, cada dólar que recuperas vale MENOS euros que los que pusiste. Puedes
ganar en dólares y ganar bastante menos —o perder— en euros. Convertir el beneficio en
dólares al cambio de hoy no da lo que ingresaste; da un número que no corresponde a ninguna
operación real.

Convenio en todo el módulo: las tasas son "unidades de divisa por 1 EUR", que es como cotiza
EURUSD (1,08 = un euro son 1,08 dólares). Para pasar a euros se DIVIDE.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

#: Caché en memoria: {(divisa, fecha_iso o "hoy"): (tasa, timestamp)}
_cache: dict = {}
_TTL_HOY = 3600           # el cambio de hoy se refresca cada hora
_TTL_HISTORICO = 86400    # una fecha pasada ya no cambia; se guarda un día por si acaso


def _ticker_par(divisa: str) -> Optional[str]:
    """Par de Yahoo para la divisa dada. EUR no necesita conversión."""
    d = (divisa or "").strip().upper()
    if not d or d == "EUR":
        return None
    return f"EUR{d}=X"


def tasa_actual(divisa: str) -> Optional[float]:
    """Unidades de `divisa` por 1 EUR, ahora mismo. None si no se puede obtener."""
    par = _ticker_par(divisa)
    if par is None:
        return 1.0
    clave = (divisa.upper(), "hoy")
    hit = _cache.get(clave)
    if hit and (datetime.now(timezone.utc).timestamp() - hit[1]) < _TTL_HOY:
        return hit[0]
    try:
        import market_data
        t = market_data._ticker(par)
        df = market_data._call_with_timeout(
            lambda: t.history(period="5d", interval="1d"), 8.0, None)
        if df is None or df.empty:
            return None
        tasa = float(df["Close"].dropna().iloc[-1])
        if tasa <= 0:
            return None
        _cache[clave] = (tasa, datetime.now(timezone.utc).timestamp())
        return tasa
    except Exception as e:
        logger.warning("Tipo de cambio actual de %s falló: %s", divisa, str(e)[:120])
        return None


def edad_tasa_actual(divisa: str) -> Optional[int]:
    """Segundos desde que se consultó el cambio de hoy. None si no hay nada cacheado.

    Saber la EDAD de una cifra vale más que refrescarla más a menudo: un "1 € = 1,1563 USD"
    sin fecha se lee como si fuera de ahora mismo, y puede tener hasta una hora.
    """
    if (divisa or "").strip().upper() in ("", "EUR"):
        return 0
    hit = _cache.get((divisa.upper(), "hoy"))
    if not hit:
        return None
    return int(datetime.now(timezone.utc).timestamp() - hit[1])


def tasa_en_fecha(divisa: str, fecha: str) -> Optional[float]:
    """Unidades de `divisa` por 1 EUR en una fecha (YYYY-MM-DD).

    Si ese día no hubo mercado (fin de semana, festivo), se usa el ÚLTIMO cierre anterior:
    es el cambio que habría aplicado el banco, no una interpolación inventada.
    """
    par = _ticker_par(divisa)
    if par is None:
        return 1.0
    try:
        dia = datetime.fromisoformat(str(fecha)[:10]).date()
    except Exception:
        return None
    # HOY (o una fecha futura por un dedazo) no es una fecha pasada: su cambio todavía se
    # mueve. Cachearlo 24 h como si fuera histórico dejaba pegado el cierre de AYER —si la
    # primera consulta del día llegaba antes de que Yahoo publicara la vela— y ese valor se
    # escribía, permanentemente, en todas las operaciones registradas hasta el día
    # siguiente. Encima la propia pantalla enseñaba en el pie otro número distinto, el de
    # tasa_actual. Un solo "cambio de hoy" para todo.
    if dia >= datetime.now(timezone.utc).date():
        return tasa_actual(divisa)
    clave = (divisa.upper(), dia.isoformat())
    hit = _cache.get(clave)
    if hit and (datetime.now(timezone.utc).timestamp() - hit[1]) < _TTL_HISTORICO:
        return hit[0]
    try:
        import market_data
        t = market_data._ticker(par)
        # Ventana amplia hacia atrás para cubrir puentes largos, y un día hacia delante
        # para que la propia fecha entre en el rango.
        ini = (dia - timedelta(days=10)).isoformat()
        fin = (dia + timedelta(days=1)).isoformat()
        df = market_data._call_with_timeout(
            lambda: t.history(start=ini, end=fin, interval="1d"), 10.0, None)
        if df is None or df.empty:
            return None
        serie = df["Close"].dropna()
        if serie.empty:
            return None
        tasa = float(serie.iloc[-1])
        if tasa <= 0:
            return None
        _cache[clave] = (tasa, datetime.now(timezone.utc).timestamp())
        return tasa
    except Exception as e:
        logger.warning("Tipo de cambio de %s en %s falló: %s", divisa, fecha, str(e)[:120])
        return None


def a_euros(importe: float, divisa: str, tasa: float) -> Optional[float]:
    """Convierte un importe a euros. `tasa` = unidades de divisa por 1 EUR."""
    try:
        if importe is None or not tasa or tasa <= 0:
            return None
        return round(float(importe) / float(tasa), 2)
    except Exception:
        return None


def calcular_venta(acciones: float, precio_compra: float, precio_venta: float,
                   divisa: str, tasa_compra: float = None, tasa_venta: float = None) -> dict:
    """Resultado de una venta, en divisa original y en euros.

    Separa el resultado en dos partes que la gente suele confundir:
      • ganancia_divisa : lo que hizo la ACCIÓN.
      • efecto_divisa   : lo que aportó (o restó) el TIPO DE CAMBIO.
    La suma de ambas, en euros, es lo que de verdad entra en la cuenta.
    """
    d = (divisa or "USD").strip().upper() or "USD"
    coste = float(acciones) * float(precio_compra)
    ingreso = float(acciones) * float(precio_venta)
    ganancia = ingreso - coste
    out = {
        "divisa": d,
        "acciones": float(acciones),
        "coste_divisa": round(coste, 2),
        "ingreso_divisa": round(ingreso, 2),
        "ganancia_divisa": round(ganancia, 2),
        "ganancia_pct": round((precio_venta / precio_compra - 1) * 100, 2) if precio_compra else None,
        "tasa_compra": tasa_compra,
        "tasa_venta": tasa_venta,
        "exacto": bool(tasa_compra and tasa_venta),
    }
    if d == "EUR":
        out.update({"coste_eur": round(coste, 2), "ingreso_eur": round(ingreso, 2),
                    "ganancia_eur": round(ganancia, 2), "efecto_divisa_eur": 0.0,
                    "exacto": True})
        return out

    if tasa_compra and tasa_venta:
        coste_eur = a_euros(coste, d, tasa_compra)
        ingreso_eur = a_euros(ingreso, d, tasa_venta)
        out["coste_eur"] = coste_eur
        out["ingreso_eur"] = ingreso_eur
        out["ganancia_eur"] = round(ingreso_eur - coste_eur, 2)
        # Cuánto del resultado en euros viene SOLO del tipo de cambio: lo que habría salido
        # con el cambio congelado al de la compra, frente a lo que sale de verdad.
        sin_efecto = a_euros(ganancia, d, tasa_compra)
        out["efecto_divisa_eur"] = round(out["ganancia_eur"] - sin_efecto, 2)
    elif tasa_venta:
        # Solo tenemos el cambio de la venta: se convierte la ganancia a ese cambio y se
        # marca como NO exacto. Es una aproximación, y quien la lea debe saberlo.
        out["ganancia_eur"] = a_euros(ganancia, d, tasa_venta)
        out["coste_eur"] = a_euros(coste, d, tasa_venta)
        out["ingreso_eur"] = a_euros(ingreso, d, tasa_venta)
        out["efecto_divisa_eur"] = None
    else:
        out["ganancia_eur"] = out["coste_eur"] = out["ingreso_eur"] = None
        out["efecto_divisa_eur"] = None
    return out
