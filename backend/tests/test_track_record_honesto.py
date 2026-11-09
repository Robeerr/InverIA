"""Tests del Track record honesto: duplicados, costes y la ventana del índice.

Por qué existen
---------------
El Track record decía "aporta valor sobre comprar SPY" con un retorno medio negativo, contaba
dos veces la misma señal cuando el análisis se regeneraba el mismo día y no restaba lo que
cuesta operar. Cada test fija una de esas tres trampas para que no vuelvan.
"""
from datetime import datetime

from track_record import (
    coste_ida_vuelta_pct,
    deduplicar_senales,
    evaluar_con_cierre,
    retorno_indice_en_ventana,
)


def _sig(fecha, entrada, **extra):
    return {"created": datetime.fromisoformat(fecha), "entry": entrada, **extra}


# ── Duplicados ───────────────────────────────────────────────────────────────

def test_el_mismo_analisis_regenerado_el_mismo_dia_cuenta_una_vez():
    sigs = [_sig("2026-10-04T15:00", 140.02), _sig("2026-10-04T09:00", 140.02)]
    assert len(deduplicar_senales(sigs)) == 1


def test_se_queda_con_la_version_mas_reciente_del_dia():
    sigs = [_sig("2026-10-04T09:00", 140.02, tp1=150), _sig("2026-10-04T15:00", 140.02, tp1=155)]
    assert deduplicar_senales(sigs)[0]["tp1"] == 155


def test_dias_distintos_son_senales_distintas():
    sigs = [_sig("2026-10-04T15:00", 140.02), _sig("2026-09-06T15:00", 149.30)]
    assert len(deduplicar_senales(sigs)) == 2


def test_mismo_dia_con_entrada_distinta_son_senales_distintas():
    # Un segundo análisis horas después con el precio movido es otra decisión real.
    sigs = [_sig("2026-10-04T09:00", 140.02), _sig("2026-10-04T15:00", 146.00)]
    assert len(deduplicar_senales(sigs)) == 2


# ── Costes ───────────────────────────────────────────────────────────────────

def test_coste_de_degiro_ida_y_vuelta_en_una_operacion_de_1000_euros():
    # 2 € por orden (compra y venta) = 0,4 %, más AutoFX 0,25 % al comprar y al vender = 0,5 %.
    assert coste_ida_vuelta_pct(1000) == 0.9


def test_las_operaciones_pequenas_pagan_mas_en_porcentaje():
    assert coste_ida_vuelta_pct(300) > coste_ida_vuelta_pct(3000)


# ── Momento del cierre ───────────────────────────────────────────────────────

def test_el_cierre_dice_en_que_vela_toco_el_objetivo():
    fut = [(105, 98, 104), (111, 106, 110), (130, 120, 125)]
    assert evaluar_con_cierre(100, 110, 90, fut) == ("tp1", 10.0, 1)


def test_una_senal_abierta_no_tiene_vela_de_cierre():
    fut = [(105, 96, 103), (107, 98, 105)]
    assert evaluar_con_cierre(100, 110, 90, fut) == ("abierta", 5.0, None)


# ── El índice en la MISMA ventana que la señal ───────────────────────────────

FECHAS = [datetime(2026, 9, d) for d in (1, 2, 3, 4, 5)]
CIERRES = [100.0, 102.0, 104.0, 90.0, 80.0]


def test_el_indice_se_mide_hasta_el_cierre_de_la_senal_no_hasta_hoy():
    # Señal del día 1 cerrada el día 3: el índice subió un 4 % (100 → 104), aunque
    # después se hundiera. Medirlo hasta hoy castigaba al índice con caídas ajenas.
    assert retorno_indice_en_ventana(FECHAS, CIERRES, datetime(2026, 9, 1, 12), datetime(2026, 9, 3)) == 4.0


def test_el_indice_empieza_en_el_ultimo_cierre_antes_de_la_senal():
    # La señal entra al precio del momento del análisis, y su propia vela siguiente ya
    # cuenta. Si el índice empezara en el cierre de esa vela, una señal cerrada en ella
    # se compararía siempre con un 0 %: se perdía justo el movimiento de ese día.
    assert retorno_indice_en_ventana(FECHAS, CIERRES, datetime(2026, 9, 1, 12), datetime(2026, 9, 2)) == 2.0


def test_una_senal_abierta_se_compara_con_el_indice_hasta_hoy():
    assert retorno_indice_en_ventana(FECHAS, CIERRES, datetime(2026, 9, 1, 12), None) == -20.0


def test_una_senal_anterior_a_todo_el_historico_empieza_en_la_primera_vela():
    assert retorno_indice_en_ventana(FECHAS, CIERRES, datetime(2026, 8, 1), datetime(2026, 9, 2)) == 2.0


def test_sin_datos_del_indice_no_inventa_un_retorno():
    assert retorno_indice_en_ventana([], [], datetime(2026, 9, 1), None) is None


# ── Una fila del Track record, de punta a punta ──────────────────────────────

def _fila():
    from track_record import construir_fila
    sig = _sig("2026-09-01T12:00", 100.0, tp1=110, tp2=120, sl=90)
    # La acción toca TP1 (110) el día 3 y después se hunde; el índice sube hasta el día 3.
    velas = {"fechas": FECHAS, "highs": [101, 105, 111, 100, 90],
             "lows": [99, 100, 104, 95, 85], "closes": [100, 104, 110, 96, 88]}
    return construir_fila("XYZ", sig, velas, FECHAS, CIERRES, coste_pct=0.9)


def test_la_fila_resta_los_costes_al_retorno():
    fila = _fila()
    assert fila["resultado"] == "tp1"
    assert fila["retorno_bruto"] == 10.0
    assert fila["retorno"] == 9.1


def test_la_fila_compara_con_el_indice_hasta_el_cierre_y_con_los_mismos_costes():
    # Índice del día 1 (100) al día 3 (104) = +4,0 %, menos el mismo 0,9 % de costes.
    assert _fila()["spy_retorno"] == 3.1


# ── Lo que se le dice al usuario ─────────────────────────────────────────────

def test_perder_menos_que_el_indice_no_se_presenta_como_ganar():
    # El caso real de la pantalla: motor −0,7 %, índice −2,5 %. Antes salía
    # "aporta valor sobre comprar SPY y esperar".
    from track_record import veredicto_benchmark
    assert veredicto_benchmark(-0.7, -2.5) == "pierde_menos_que_indice"


def test_veredictos_del_benchmark():
    from track_record import veredicto_benchmark
    assert veredicto_benchmark(3.0, 1.0) == "gana_y_bate"
    assert veredicto_benchmark(1.0, 3.0) == "gana_sin_batir"
    assert veredicto_benchmark(-3.0, -1.0) == "pierde_y_no_bate"
    assert veredicto_benchmark(None, 1.0) is None


# ── El cálculo completo, con una base de datos y un mercado de mentira ───────

class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, _n):
        return list(self.docs)


class _DB:
    def __init__(self, docs):
        self.analyses = self

        self._docs = docs

    def find(self, *_a, **_k):
        return _Cursor(self._docs)


def test_el_calculo_completo_descarta_duplicados_y_resta_costes(monkeypatch):
    import asyncio
    from datetime import timedelta, timezone

    import pandas as pd

    import market_data
    import track_record

    hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    dias = [(hoy - timedelta(days=10 - i)).replace(tzinfo=None) for i in range(10)]
    señal = (hoy - timedelta(days=10)).replace(hour=15)
    analisis = {"symbol": "XYZ", "created_at": señal.isoformat(),
                "quote_snapshot": {"price": 100.0},
                "result": {"recommendation": "COMPRAR", "take_profit_1": 110, "stop_loss": 90}}
    regenerado = {**analisis, "created_at": señal.replace(hour=18).isoformat()}

    def historia(sym):
        if sym == "SPY":
            return pd.DataFrame({"Date": dias, "High": [1] * 10, "Low": [1] * 10,
                                 "Close": [100.0] * 10})
        return pd.DataFrame({"Date": dias, "High": [101, 111] + [100] * 8,
                             "Low": [99] * 10, "Close": [100, 110] + [100] * 8})

    monkeypatch.setattr(market_data, "get_full_indicator_history", historia)
    r = asyncio.run(track_record.compute_track_record(_DB([regenerado, analisis]), days=30))

    assert r["total"] == 1
    assert r["duplicadas_descartadas"] == 1
    assert r["señales"][0]["retorno"] == 9.1
    assert r["costes"]["pct_ida_vuelta"] == 0.9
