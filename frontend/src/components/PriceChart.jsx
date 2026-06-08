import React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
  Line,
} from "recharts";
import { fmtPrice } from "../lib/format";

const TIMEFRAMES = ["5M", "15M", "1H", "1D", "1W", "1M", "3M", "1Y", "5Y"];

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0].payload;
  return (
    <div className="card-flat p-3 text-xs font-mono shadow-md">
      <p className="text-[#5c6b66] mb-1">
        {new Date(d.date).toLocaleString("es-ES")}
      </p>
      <p>O: <span className="text-[#0e1f1a]">${fmtPrice(d.open)}</span></p>
      <p>H: <span className="text-[#4a7c59]">${fmtPrice(d.high)}</span></p>
      <p>L: <span className="text-[#d85c41]">${fmtPrice(d.low)}</span></p>
      <p>C: <span className="text-[#0e1f1a] font-semibold">${fmtPrice(d.close)}</span></p>
    </div>
  );
}

export default function PriceChart({
  candles,
  timeframe,
  setTimeframe,
  analysis,
  indicators,
  signalEntry,
}) {
  const data = candles || [];
  if (data.length === 0) {
    return (
      <div className="card-flat p-8 text-center text-[#5c6b66]">
        Sin datos para mostrar.
      </div>
    );
  }

  const closes = data.map((d) => d.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const padding = (max - min) * 0.05;
  const yDomain = [min - padding, max + padding];

  const supports = (analysis?.key_levels?.support) || (indicators?.support_resistance?.supports) || [];
  const resistances = (analysis?.key_levels?.resistance) || (indicators?.support_resistance?.resistances) || [];
  const entryMin = analysis?.entry_zone?.min;
  const entryMax = analysis?.entry_zone?.max;
  const stopLoss = analysis?.stop_loss;
  const tp1 = analysis?.take_profit_1;
  const tp2 = analysis?.take_profit_2;

  return (
    <section data-testid="price-chart" className="card-flat p-4 md:p-6 animate-fade-up">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">
            Gráfico de Precio
          </h3>
          <p className="text-xs text-[#5c6b66] mt-0.5">
            {signalEntry ? "Niveles de compra (azul) y venta (morado) · IA: zona entrada, SL y TPs" : "Zona de entrada, SL y Take Profits sugeridos por IA"}
          </p>
        </div>
        <div className="flex gap-1 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md p-1">
          {TIMEFRAMES.map((t) => (
            <button
              key={t}
              data-testid={`timeframe-${t}`}
              onClick={() => setTimeframe(t)}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-all ${
                t === timeframe
                  ? "bg-[#1a3a32] text-[#f5f3ef]"
                  : "text-[#5c6b66] hover:text-[#0e1f1a]"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="h-[420px] w-full" style={{ minHeight: 420 }}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={420}>
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
            <defs>
              <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#1a3a32" stopOpacity={0.18} />
                <stop offset="100%" stopColor="#1a3a32" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#e5e0d8" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#5c6b66", fontFamily: "IBM Plex Mono" }}
              tickFormatter={(d) => {
                const dt = new Date(d);
                if (["5M", "15M", "1H", "1D", "1W"].includes(timeframe)) {
                  return dt.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
                }
                return dt.toLocaleDateString("es-ES", { day: "2-digit", month: "short" });
              }}
              minTickGap={40}
            />
            <YAxis
              domain={yDomain}
              tick={{ fontSize: 10, fill: "#5c6b66", fontFamily: "IBM Plex Mono" }}
              tickFormatter={(v) => `$${v.toFixed(0)}`}
              width={56}
              orientation="right"
            />
            <Tooltip content={<CustomTooltip />} />

            {/* Entry zone */}
            {entryMin && entryMax && (
              <ReferenceArea
                y1={entryMin}
                y2={entryMax}
                fill="#4a7c59"
                fillOpacity={0.1}
                stroke="#4a7c59"
                strokeOpacity={0.3}
                strokeDasharray="3 3"
                label={{ value: "Zona de entrada", position: "insideTopLeft", fill: "#4a7c59", fontSize: 10 }}
              />
            )}

            {/* Stop loss */}
            {stopLoss && (
              <ReferenceLine
                y={stopLoss}
                stroke="#d85c41"
                strokeWidth={2}
                label={{ value: `SL: $${stopLoss}`, position: "right", fill: "#d85c41", fontSize: 11, fontWeight: "bold", fontFamily: "IBM Plex Mono" }}
              />
            )}

            {/* Take profits */}
            {tp1 && (
              <ReferenceLine
                y={tp1}
                stroke="#4a7c59"
                strokeWidth={2}
                label={{ value: `TP1: $${tp1}`, position: "right", fill: "#4a7c59", fontSize: 11, fontWeight: "bold", fontFamily: "IBM Plex Mono" }}
              />
            )}
            {tp2 && (
              <ReferenceLine
                y={tp2}
                stroke="#4a7c59"
                strokeWidth={2}
                strokeDasharray="2 2"
                label={{ value: `TP2: $${tp2}`, position: "right", fill: "#4a7c59", fontSize: 10, fontFamily: "IBM Plex Mono" }}
              />
            )}

            {/* Signal entry buy levels overlay */}
            {signalEntry && ["nivel1","nivel2","nivel3","nivel4","nivel5"].map((lk, i) => {
              const val = signalEntry[lk];
              if (!val) return null;
              return (
                <ReferenceLine
                  key={lk}
                  y={val}
                  stroke="#2563eb"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  label={{ value: `N${i+1} $${val}`, position: "insideTopRight", fill: "#2563eb", fontSize: 10, fontFamily: "IBM Plex Mono" }}
                />
              );
            })}
            {/* Signal entry sell/deseado level */}
            {signalEntry?.deseado && (
              <ReferenceLine
                y={signalEntry.deseado}
                stroke="#7c3aed"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                label={{ value: `Venta $${signalEntry.deseado}`, position: "insideTopRight", fill: "#7c3aed", fontSize: 10, fontFamily: "IBM Plex Mono" }}
              />
            )}

            <Area
              type="monotone"
              dataKey="close"
              stroke="#1a3a32"
              strokeWidth={2}
              fill="url(#priceFill)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
