import React, { useMemo, useState } from "react";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from "recharts";
import { fmtPrice } from "../lib/format";

// Marcos enfocados a swing trading (intradía → mensual). El 1D/1W son los clave.
const TIMEFRAMES = ["15M", "1H", "4H", "1D", "1W", "1M"];

// ── Technical indicator calculations ───────────────────────────────────────
function calcSMA(data, period) {
  const out = [];
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    sum += data[i].close;
    if (i >= period) sum -= data[i - period].close;
    out.push(i >= period - 1 ? sum / period : null);
  }
  return out;
}

function calcBB(data, period = 20, mult = 2) {
  const sma = calcSMA(data, period);
  return data.map((_, i) => {
    if (sma[i] == null) return { bbU: null, bbL: null };
    const slice = data.slice(Math.max(0, i - period + 1), i + 1).map((d) => d.close);
    const variance = slice.reduce((acc, v) => acc + (v - sma[i]) ** 2, 0) / slice.length;
    const std = Math.sqrt(variance);
    return { bbU: sma[i] + mult * std, bbL: sma[i] - mult * std };
  });
}

function calcRSI(data, period = 14) {
  if (data.length < period + 1) return data.map(() => null);
  const out = Array(data.length).fill(null);
  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const d = data[i].close - data[i - 1].close;
    if (d > 0) avgGain += d; else avgLoss -= d;
  }
  avgGain /= period;
  avgLoss /= period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < data.length; i++) {
    const d = data[i].close - data[i - 1].close;
    const gain = d > 0 ? d : 0;
    const loss = d < 0 ? -d : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

// ── Tooltip ─────────────────────────────────────────────────────────────────
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

// ── Overlay toggle pill ──────────────────────────────────────────────────────
function OverlayBtn({ label, color, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono border transition-all ${
        active
          ? "border-transparent text-white"
          : "border-[#e5e0d8] text-[#5c6b66] bg-transparent hover:border-[#1a3a32]"
      }`}
      style={active ? { backgroundColor: color } : {}}
    >
      <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: color }} />
      {label}
    </button>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
function PriceChart({ candles, timeframe, setTimeframe, analysis, indicators, signalEntry, buyLevels, lines }) {
  // Mostrar solo las ~110 velas más recientes: así cada vela es ANCHA y clara (como
  // TradingView), en vez de cientos apretadas que no se distinguen.
  const data = useMemo(() => (candles || []).slice(-110), [candles]);

  // Por defecto SIN medias móviles: las velas son las protagonistas (estilo TradingView,
  // mucho más limpio). El usuario las reactiva con los botones si las quiere.
  const [overlays, setOverlays] = useState({ sma20: false, sma50: false, sma200: false, bb: false, rsi: false });
  const [showLines, setShowLines] = useState(true);
  const toggle = (k) => setOverlays((p) => ({ ...p, [k]: !p[k] }));

  const hasVolume = useMemo(() => data.some((d) => d.volume > 0), [data]);

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

  // Compute indicator series only when their overlays are active.
  const chartData = useMemo(() => {
    if (!data.length) return [];
    const sma20v = overlays.sma20 ? calcSMA(data, 20) : null;
    const sma50v = overlays.sma50 ? calcSMA(data, 50) : null;
    const sma200v = overlays.sma200 ? calcSMA(data, 200) : null;
    const bbv = overlays.bb ? calcBB(data, 20, 2) : null;
    const rsiv = overlays.rsi ? calcRSI(data, 14) : null;
    return data.map((d, i) => ({
      ...d,
      sma20: sma20v?.[i] ?? undefined,
      sma50: sma50v?.[i] ?? undefined,
      sma200: sma200v?.[i] ?? undefined,
      bbU: bbv?.[i]?.bbU ?? undefined,
      bbL: bbv?.[i]?.bbL ?? undefined,
      rsi: rsiv?.[i] ?? undefined,
    }));
  }, [data, overlays]);

  // CandleShape: closure over priceDomain for coordinate math.
  // Recharts Bar always passes background = {x, y, width, height} to shape,
  // where background.y = chart top and background.height = full plot height.
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
      const color = isUp ? "#22c55e" : "#ef4444";  // verde/rojo más vivos para que resalten
      const bw = Math.max((width || 4) * 0.82, 2.5);
      const cx = (x || 0) + (width || 4) / 2;
      return (
        <g>
          <line x1={cx} y1={py(high)} x2={cx} y2={py(low)} stroke={color} strokeWidth={1.25} />
          <rect
            x={cx - bw / 2}
            y={Math.min(py(open), py(close))}
            width={bw}
            height={Math.max(Math.abs(py(close) - py(open)), 1.5)}
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

  // LEGIBILIDAD: con muchos niveles de compra, etiquetar todos satura el gráfico. Solo
  // etiquetamos los 3 MÁS CERCANOS al precio (los accionables); los profundos quedan como
  // líneas tenues sin texto. Jerarquía visual: destaca lo que importa, atenúa lo demás.
  const lastPrice = data.length ? data[data.length - 1].close : null;
  const labeledBuyIdx = (!Array.isArray(buyLevels) || lastPrice == null)
    ? new Set()
    : new Set(
        buyLevels
          .map((z, i) => ({ i, d: Math.abs((z?.price ?? 0) - lastPrice) }))
          .sort((a, b) => a.d - b.d)
          .slice(0, 3)
          .map((x) => x.i)
      );

  const xTickFmt = (d) => {
    const dt = new Date(d);
    // Intradía (15M/1H/4H) → hora; diario y mayor (1D/1W/1M) → fecha.
    return ["5M", "15M", "1H", "4H"].includes(timeframe)
      ? dt.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })
      : dt.toLocaleDateString("es-ES", { day: "2-digit", month: "short" });
  };

  return (
    <section data-testid="price-chart" className="card-flat p-4 md:p-6 animate-fade-up">
      {/* Header row: title + timeframe buttons */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div>
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Gráfico de Precio</h3>
          <p className="text-xs text-[#5c6b66] mt-0.5">
            {(Array.isArray(buyLevels) && buyLevels.length > 0) || signalEntry
              ? "Niveles de compra del motor (azul · tácticos en dorado) · IA: zona entrada, SL y TPs"
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

      {/* Indicator overlay toggles */}
      <div className="flex gap-1.5 flex-wrap mb-3">
        <OverlayBtn label="SMA20" color="#f59e0b" active={overlays.sma20} onClick={() => toggle("sma20")} />
        <OverlayBtn label="SMA50" color="#3b82f6" active={overlays.sma50} onClick={() => toggle("sma50")} />
        <OverlayBtn label="SMA200" color="#8b5cf6" active={overlays.sma200} onClick={() => toggle("sma200")} />
        <OverlayBtn label="Bollinger" color="#9ca3af" active={overlays.bb} onClick={() => toggle("bb")} />
        <OverlayBtn label="RSI" color="#f59e0b" active={overlays.rsi} onClick={() => toggle("rsi")} />
        <OverlayBtn label="Líneas IA" color="#4a7c59" active={showLines} onClick={() => setShowLines((v) => !v)} />
      </div>

      {/* Patrones detectados (Fase 2): estructura (triángulo, canal, C-H...) y VELA reciente */}
      {(lines?.pattern || lines?.candlestick) && (
        <div className="mb-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {lines?.pattern && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-[#1a3a32]/[0.06] border border-[#1a3a32]/20">
              <span className="text-base leading-none mt-0.5">📐</span>
              <div>
                <p className="text-[10px] uppercase tracking-[0.12em] text-[#5c6b66] font-mono">Patrón de estructura</p>
                <p className="text-sm font-semibold text-[#0e1f1a]">{lines.pattern.nombre}</p>
                <p className="text-xs text-[#5c6b66] leading-snug mt-0.5">{lines.pattern.descripcion}</p>
              </div>
            </div>
          )}
          {lines?.candlestick && (() => {
            const s = lines.candlestick.sentido;
            const col = s === "alcista" ? "#4a7c59" : s === "bajista" ? "#d85c41" : "#c9a14a";
            return (
              <div className="flex items-start gap-2 px-3 py-2 rounded-lg" style={{ background: `${col}12`, border: `1px solid ${col}33` }}>
                <span className="text-base leading-none mt-0.5">🕯️</span>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.12em] text-[#5c6b66] font-mono">Patrón de vela</p>
                  <p className="text-sm font-semibold" style={{ color: col }}>{lines.candlestick.nombre}</p>
                  <p className="text-xs text-[#5c6b66] leading-snug mt-0.5">{lines.candlestick.descripcion}</p>
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* Main price chart */}
      <div style={{ height: overlays.rsi ? 360 : 460 }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 8, right: 64, left: 0, bottom: 4 }} syncId="inveria-chart">
            <CartesianGrid stroke="#e5e0d8" strokeOpacity={0.4} strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#5c6b66", fontFamily: "IBM Plex Mono" }}
              tickFormatter={xTickFmt}
              minTickGap={50}
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

            {/* Volume */}
            {hasVolume && (
              <Bar yAxisId="vol" dataKey="volume" fill="#1a3a32" fillOpacity={0.18} isAnimationActive={false} maxBarSize={20} />
            )}

            {/* Candlesticks */}
            <Bar yAxisId="price" dataKey="high" shape={CandleShape} isAnimationActive={false} />

            {/* SMA overlays (medias suavizadas para no competir con las velas) */}
            {overlays.sma20 && (
              <Line yAxisId="price" type="monotone" dataKey="sma20" stroke="#f59e0b" strokeWidth={1.25} strokeOpacity={0.75} dot={false} isAnimationActive={false} connectNulls={false} />
            )}
            {overlays.sma50 && (
              <Line yAxisId="price" type="monotone" dataKey="sma50" stroke="#3b82f6" strokeWidth={1.25} strokeOpacity={0.75} dot={false} isAnimationActive={false} connectNulls={false} />
            )}
            {overlays.sma200 && (
              <Line yAxisId="price" type="monotone" dataKey="sma200" stroke="#8b5cf6" strokeWidth={1.25} strokeOpacity={0.75} dot={false} isAnimationActive={false} connectNulls={false} />
            )}

            {/* Bollinger Bands */}
            {overlays.bb && (
              <>
                <Line yAxisId="price" type="monotone" dataKey="bbU" stroke="#9ca3af" strokeWidth={1} strokeDasharray="4 2" dot={false} isAnimationActive={false} connectNulls={false} />
                <Line yAxisId="price" type="monotone" dataKey="bbL" stroke="#9ca3af" strokeWidth={1} strokeDasharray="4 2" dot={false} isAnimationActive={false} connectNulls={false} />
              </>
            )}

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
            {stopLoss && (
              <ReferenceLine
                yAxisId="price"
                y={stopLoss}
                stroke="#d85c41"
                strokeWidth={2}
                label={{ value: `SL $${stopLoss}`, position: "right", fill: "#d85c41", fontSize: 11, fontWeight: "bold", fontFamily: "IBM Plex Mono" }}
              />
            )}
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
            {/* Niveles de compra del MOTOR de confluencia (los mismos que la tarjeta).
                Coherencia total gráfico↔tarjeta. Los tácticos se pintan más tenues y
                punteados. Si no hay análisis cargado, cae al sistema de señales antiguo. */}
            {Array.isArray(buyLevels) && buyLevels.length > 0
              ? buyLevels.map((z, i) => {
                  const val = z?.price;
                  if (val == null) return null;
                  const tac = z?.tactical;
                  const labeled = labeledBuyIdx.has(i);
                  return (
                    <ReferenceLine
                      key={`bl-${i}`}
                      yAxisId="price"
                      y={val}
                      stroke={tac ? "#b8860b" : "#2563eb"}
                      strokeWidth={1}
                      strokeOpacity={labeled ? 0.85 : 0.2}
                      strokeDasharray={tac ? "2 4" : "4 3"}
                      label={labeled ? { value: `N${i + 1} $${val}${tac ? " ·táct" : ""}`, position: "insideTopRight", fill: tac ? "#b8860b" : "#2563eb", fontSize: 10, fontFamily: "IBM Plex Mono" } : undefined}
                    />
                  );
                })
              : signalEntry &&
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
            {/* Zonas de demanda (verde) / oferta (rojo) sombreadas — donde el precio ha
                reaccionado. Se pintan tenues detrás de las velas. */}
            {showLines && Array.isArray(lines?.zones) && lines.zones.map((z, i) => (
              <ReferenceArea
                key={`zone-${i}`}
                yAxisId="price"
                y1={z.low}
                y2={z.high}
                fill={z.role === "demanda" ? "#4a7c59" : "#d85c41"}
                fillOpacity={0.08}
                stroke="none"
              />
            ))}
            {/* Directrices diagonales de tendencia (detección algorítmica). Las S/R
                horizontales NO se pintan aquí: el motor ya dibuja los niveles N1-N6, así
                que solo añadimos lo que aporta valor nuevo — las líneas inclinadas. */}
            {showLines && Array.isArray(lines?.trendlines) && lines.trendlines.map((tl, i) => {
              const p = tl.points || [];
              if (p.length < 2 || !p[0].date || !p[1].date) return null;
              const col = tl.kind === "resistencia" ? "#d85c41" : "#4a7c59";
              return (
                <ReferenceLine
                  key={`auto-tl-${i}`}
                  yAxisId="price"
                  segment={[{ x: p[0].date, y: p[0].price }, { x: p[1].date, y: p[1].price }]}
                  stroke={col}
                  strokeWidth={1.5}
                  strokeOpacity={0.8}
                  label={{ value: `Directriz ${tl.direction}`, position: "insideBottomLeft", fill: col, fontSize: 9, fontFamily: "IBM Plex Mono" }}
                />
              );
            })}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* RSI subplot */}
      {overlays.rsi && (
        <div className="mt-2 border-t border-[#e5e0d8] pt-2">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono">RSI 14</span>
            <span className="text-[10px] text-[#5c6b66] font-mono">— sobrecompra &gt;70 · sobreventa &lt;30</span>
          </div>
          <div style={{ height: 110 }} className="w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 4, right: 64, left: 0, bottom: 4 }} syncId="inveria-chart">
                <CartesianGrid stroke="#e5e0d8" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" hide />
                <YAxis
                  yAxisId="rsi"
                  domain={[0, 100]}
                  ticks={[30, 50, 70]}
                  tick={{ fontSize: 9, fill: "#5c6b66", fontFamily: "IBM Plex Mono" }}
                  tickFormatter={(v) => `${v}`}
                  width={60}
                  orientation="right"
                />
                <Tooltip content={<></>} cursor={{ stroke: "#5c6b66", strokeWidth: 1, strokeDasharray: "3 3" }} />
                <ReferenceLine yAxisId="rsi" y={70} stroke="#d85c41" strokeDasharray="3 3" strokeWidth={1} />
                <ReferenceLine yAxisId="rsi" y={30} stroke="#4a7c59" strokeDasharray="3 3" strokeWidth={1} />
                <ReferenceLine yAxisId="rsi" y={50} stroke="#e5e0d8" strokeWidth={1} />
                <Line
                  yAxisId="rsi"
                  type="monotone"
                  dataKey="rsi"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  );
}

export default React.memo(PriceChart);
