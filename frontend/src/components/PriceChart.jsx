import React, { useMemo } from "react";
import {
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from "recharts";
import { fmtPrice } from "../lib/format";

const TIMEFRAMES = ["5M", "15M", "1H", "1D", "1W", "1M", "3M", "1Y", "5Y"];

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const up = d.close >= (d.open ?? d.close);
  return (
    <div className="card-flat p-3 text-xs font-mono shadow-md min-w-[130px]">
      <p className="text-[#5c6b66] mb-1.5 text-[10px]">
        {new Date(d.date).toLocaleString("es-ES")}
      </p>
      <div className="space-y-0.5">
        <p>A: <span className="text-[#0e1f1a]">${fmtPrice(d.open ?? d.close)}</span></p>
        <p>H: <span className="text-[#4a7c59]">${fmtPrice(d.high)}</span></p>
        <p>L: <span className="text-[#d85c41]">${fmtPrice(d.low)}</span></p>
        <p>C: <span className={`font-bold ${up ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>${fmtPrice(d.close)}</span></p>
        {d.volume > 0 && (
          <p className="text-[#5c6b66] mt-1 border-t border-[#e5e0d8] pt-1">
            Vol: {d.volume >= 1e6 ? `${(d.volume / 1e6).toFixed(1)}M` : `${(d.volume / 1e3).toFixed(0)}K`}
          </p>
        )}
      </div>
    </div>
  );
}

function PriceChart({ candles, timeframe, setTimeframe, analysis, indicators, signalEntry }) {
  const data = useMemo(() => candles || [], [candles]);

  const hasVolume = useMemo(() => data.some((d) => d.volume > 0), [data]);

  // Price axis domain from real OHLC range with small padding.
  const priceDomain = useMemo(() => {
    if (!data.length) return [0, 100];
    let lo = Infinity, hi = -Infinity;
    for (const d of data) {
      if (d.low != null && d.low < lo) lo = d.low;
      if (d.high != null && d.high > hi) hi = d.high;
    }
    const pad = (hi - lo) * 0.04;
    return [lo - pad, hi + pad];
  }, [data]);

  const maxVol = useMemo(() => {
    if (!hasVolume) return 1;
    return Math.max(...data.map((d) => d.volume || 0), 1);
  }, [data, hasVolume]);

  // CandleShape uses a closure over priceDomain.
  // Recharts Bar always passes `background = {x, y, width, height}` to the shape,
  // where background.y = top of chart plot area and background.height = full plot height.
  // Combined with priceDomain we get the linear pixel scale for any price value.
  const CandleShape = useMemo(() => {
    const [dMin, dMax] = priceDomain;
    const dRange = dMax - dMin || 1;
    return function CandleBar({ x, width, payload, background }) {
      if (!payload || !background?.height) return null;
      const H = background.height;
      const top = background.y ?? 0;
      const py = (v) => top + ((dMax - v) / dRange) * H;
      const open = payload.open ?? payload.close;
      const { high, low, close } = payload;
      if (high == null || low == null || close == null) return null;
      const isUp = close >= open;
      const color = isUp ? "#4a7c59" : "#d85c41";
      const bw = Math.max((width || 4) * 0.72, 1.5);
      const cx = (x || 0) + (width || 4) / 2;
      const yH = py(high);
      const yL = py(low);
      const yO = py(open);
      const yC = py(close);
      return (
        <g>
          {/* Wick */}
          <line x1={cx} y1={yH} x2={cx} y2={yL} stroke={color} strokeWidth={1} />
          {/* Body */}
          <rect
            x={cx - bw / 2}
            y={Math.min(yO, yC)}
            width={bw}
            height={Math.max(Math.abs(yC - yO), 1)}
            fill={color}
          />
        </g>
      );
    };
  }, [priceDomain]);

  if (!data.length) {
    return <div className="card-flat p-8 text-center text-[#5c6b66]">Sin datos para mostrar.</div>;
  }

  const entryMin = analysis?.entry_zone?.min;
  const entryMax = analysis?.entry_zone?.max;
  const stopLoss = analysis?.stop_loss;
  const tp1 = analysis?.take_profit_1;
  const tp2 = analysis?.take_profit_2;

  return (
    <section data-testid="price-chart" className="card-flat p-4 md:p-6 animate-fade-up">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Gráfico de Precio</h3>
          <p className="text-xs text-[#5c6b66] mt-0.5">
            {signalEntry
              ? "Niveles de compra (azul) y venta (morado) · IA: zona entrada, SL y TPs"
              : "Zona de entrada, SL y Take Profits sugeridos por IA"}
          </p>
        </div>
        <div className="flex gap-1 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md p-1 flex-wrap">
          {TIMEFRAMES.map((t) => (
            <button
              key={t}
              data-testid={`timeframe-${t}`}
              onClick={() => setTimeframe(t)}
              className={`px-2.5 py-1.5 text-xs font-mono rounded transition-all ${
                t === timeframe ? "bg-[#1a3a32] text-[#f5f3ef]" : "text-[#5c6b66] hover:text-[#0e1f1a]"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="h-[460px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 64, left: 0, bottom: 4 }}>
            <CartesianGrid stroke="#e5e0d8" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#5c6b66", fontFamily: "IBM Plex Mono" }}
              tickFormatter={(d) => {
                const dt = new Date(d);
                return ["5M", "15M", "1H", "1D", "1W"].includes(timeframe)
                  ? dt.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })
                  : dt.toLocaleDateString("es-ES", { day: "2-digit", month: "short" });
              }}
              minTickGap={40}
            />
            <YAxis
              yAxisId="price"
              domain={priceDomain}
              tick={{ fontSize: 10, fill: "#5c6b66", fontFamily: "IBM Plex Mono" }}
              tickFormatter={(v) => `$${v >= 1000 ? v.toFixed(0) : v.toFixed(2)}`}
              width={60}
              orientation="right"
            />
            {hasVolume && <YAxis yAxisId="vol" domain={[0, maxVol * 5]} hide />}

            <Tooltip
              content={<CustomTooltip />}
              cursor={{ stroke: "#5c6b66", strokeWidth: 1, strokeDasharray: "3 3" }}
            />

            {/* Volume bars — domain trick keeps them in the bottom ~20% of the chart */}
            {hasVolume && (
              <Bar
                yAxisId="vol"
                dataKey="volume"
                fill="#1a3a32"
                fillOpacity={0.18}
                isAnimationActive={false}
                maxBarSize={20}
              />
            )}

            {/* Candlesticks (wicks + bodies via custom shape with coordinate closure) */}
            <Bar
              yAxisId="price"
              dataKey="high"
              shape={CandleShape}
              isAnimationActive={false}
            />

            {/* IA entry zone */}
            {entryMin != null && entryMax != null && (
              <ReferenceArea
                yAxisId="price"
                y1={entryMin}
                y2={entryMax}
                fill="#4a7c59"
                fillOpacity={0.1}
                stroke="#4a7c59"
                strokeOpacity={0.3}
                strokeDasharray="3 3"
                label={{ value: "Zona entrada", position: "insideTopLeft", fill: "#4a7c59", fontSize: 10 }}
              />
            )}

            {/* IA stop loss */}
            {stopLoss && (
              <ReferenceLine
                yAxisId="price"
                y={stopLoss}
                stroke="#d85c41"
                strokeWidth={2}
                label={{ value: `SL $${stopLoss}`, position: "right", fill: "#d85c41", fontSize: 11, fontWeight: "bold", fontFamily: "IBM Plex Mono" }}
              />
            )}

            {/* IA take profits */}
            {tp1 && (
              <ReferenceLine
                yAxisId="price"
                y={tp1}
                stroke="#4a7c59"
                strokeWidth={2}
                label={{ value: `TP1 $${tp1}`, position: "right", fill: "#4a7c59", fontSize: 11, fontWeight: "bold", fontFamily: "IBM Plex Mono" }}
              />
            )}
            {tp2 && (
              <ReferenceLine
                yAxisId="price"
                y={tp2}
                stroke="#4a7c59"
                strokeWidth={2}
                strokeDasharray="2 2"
                label={{ value: `TP2 $${tp2}`, position: "right", fill: "#4a7c59", fontSize: 10, fontFamily: "IBM Plex Mono" }}
              />
            )}

            {/* Signal buy levels */}
            {signalEntry &&
              ["nivel1", "nivel2", "nivel3", "nivel4", "nivel5"].map((lk, i) => {
                const val = signalEntry[lk];
                if (!val) return null;
                return (
                  <ReferenceLine
                    key={lk}
                    yAxisId="price"
                    y={val}
                    stroke="#2563eb"
                    strokeWidth={1.5}
                    strokeDasharray="4 3"
                    label={{ value: `N${i + 1} $${val}`, position: "insideTopRight", fill: "#2563eb", fontSize: 10, fontFamily: "IBM Plex Mono" }}
                  />
                );
              })}

            {/* Signal sell / deseado level */}
            {signalEntry?.deseado && (
              <ReferenceLine
                yAxisId="price"
                y={signalEntry.deseado}
                stroke="#7c3aed"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                label={{ value: `Venta $${signalEntry.deseado}`, position: "insideTopRight", fill: "#7c3aed", fontSize: 10, fontFamily: "IBM Plex Mono" }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

export default React.memo(PriceChart);
