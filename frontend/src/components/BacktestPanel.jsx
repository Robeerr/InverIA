import React from "react";
import { Flask, ChartBar, CheckCircle, XCircle } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import { fmtPrice } from "../lib/format";

export default function BacktestPanel({ symbol, analysis }) {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [lookback, setLookback] = React.useState(252);

  const canRun = !!(analysis?.entry_zone?.min && analysis?.entry_zone?.max && analysis?.stop_loss && analysis?.take_profit_1);

  const run = async () => {
    if (!canRun) return;
    setLoading(true);
    setError(null);
    try {
      const direction = analysis.recommendation === "VENDER" ? "short" : "long";
      const res = await api.backtest({
        symbol,
        entry_min: analysis.entry_zone.min,
        entry_max: analysis.entry_zone.max,
        stop_loss: analysis.stop_loss,
        take_profit_1: analysis.take_profit_1,
        take_profit_2: analysis.take_profit_2,
        direction,
        lookback_days: lookback,
      });
      setData(res);
    } catch (e) {
      setError(e?.response?.data?.detail || "Error en backtest");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section data-testid="backtest-panel" className="card-flat p-6 animate-fade-up">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div className="flex items-center gap-2">
          <Flask size={18} weight="bold" className="text-[#1a3a32]" />
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Backtest de Niveles</h3>
        </div>
        <div className="flex items-center gap-2">
          <select
            data-testid="backtest-lookback"
            value={lookback}
            onChange={(e) => setLookback(parseInt(e.target.value))}
            className="bg-white border border-[#e5e0d8] rounded text-xs px-2 py-1 font-mono"
          >
            <option value={63}>3 meses</option>
            <option value={126}>6 meses</option>
            <option value={252}>1 año</option>
            <option value={504}>2 años</option>
          </select>
          <Button
            data-testid="run-backtest"
            onClick={run}
            disabled={!canRun || loading}
            className="bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono text-xs h-9"
          >
            {loading ? "Simulando..." : "Ejecutar Backtest"}
          </Button>
        </div>
      </div>

      {!canRun && (
        <p className="text-sm text-[#5c6b66]">
          Genera un análisis IA con niveles para poder simular su rendimiento histórico.
        </p>
      )}

      {error && <p className="text-sm text-[#d85c41]">{error}</p>}

      {data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            <Stat label="Operaciones" value={data.total_trades} testId="bt-trades" />
            <Stat
              label="Win Rate"
              value={`${data.win_rate}%`}
              tone={data.win_rate >= 50 ? "buy" : "sell"}
              testId="bt-winrate"
            />
            <Stat
              label="Retorno Total"
              value={`${data.total_return_pct >= 0 ? "+" : ""}${data.total_return_pct}%`}
              tone={data.total_return_pct >= 0 ? "buy" : "sell"}
              testId="bt-return"
            />
            <Stat label="Retorno Medio" value={`${data.avg_return_pct >= 0 ? "+" : ""}${data.avg_return_pct}%`} testId="bt-avg" />
          </div>

          <div className="grid grid-cols-3 gap-2 mb-4">
            <div className="bg-[#4a7c59]/10 border border-[#4a7c59]/30 rounded-md p-3 text-center">
              <CheckCircle size={16} weight="bold" className="text-[#4a7c59] mx-auto" />
              <p className="font-mono font-bold text-lg text-[#4a7c59] mt-1">{data.wins}</p>
              <p className="text-[10px] uppercase text-[#5c6b66]">Wins</p>
            </div>
            <div className="bg-[#d85c41]/10 border border-[#d85c41]/30 rounded-md p-3 text-center">
              <XCircle size={16} weight="bold" className="text-[#d85c41] mx-auto" />
              <p className="font-mono font-bold text-lg text-[#d85c41] mt-1">{data.losses}</p>
              <p className="text-[10px] uppercase text-[#5c6b66]">Losses</p>
            </div>
            <div className="bg-[#f5f3ef] border border-[#e5e0d8] rounded-md p-3 text-center">
              <ChartBar size={16} weight="bold" className="text-[#5c6b66] mx-auto" />
              <p className="font-mono font-bold text-lg text-[#0e1f1a] mt-1">{data.avg_bars_held}</p>
              <p className="text-[10px] uppercase text-[#5c6b66]">Días prom.</p>
            </div>
          </div>

          {data.trades.length > 0 && (
            <div>
              <p className="label-small mb-2">Últimas operaciones simuladas</p>
              <div className="max-h-[200px] overflow-y-auto space-y-1">
                {data.trades.map((t, i) => (
                  <div key={i} data-testid={`bt-trade-${i}`} className="flex items-center justify-between text-xs font-mono p-2 border border-[#e5e0d8] rounded">
                    <span className="text-[#5c6b66]">{new Date(t.entry_date).toLocaleDateString("es-ES")}</span>
                    <span>${fmtPrice(t.entry_price)} → ${fmtPrice(t.exit_price)}</span>
                    <span className={t.result === "WIN" ? "text-[#4a7c59]" : "text-[#d85c41]"}>
                      {t.return_pct >= 0 ? "+" : ""}{t.return_pct}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-[11px] text-[#5c6b66] mt-3 italic">
            * Backtest conservador: si el bar toca SL y TP1 el mismo día, se asume SL primero. Resultados pasados no garantizan rendimientos futuros.
          </p>
        </>
      )}
    </section>
  );
}

function Stat({ label, value, tone, testId }) {
  const toneClass = tone === "buy" ? "text-[#4a7c59]" : tone === "sell" ? "text-[#d85c41]" : "text-[#0e1f1a]";
  return (
    <div className="bg-[#f5f3ef] border border-[#e5e0d8] rounded-md p-3">
      <p className="label-small">{label}</p>
      <p data-testid={testId} className={`font-mono font-bold text-lg ${toneClass} mt-1`}>{value}</p>
    </div>
  );
}
