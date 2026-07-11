import React, { useEffect, useRef } from "react";
import { createChart, ColorType, LineStyle } from "lightweight-charts";

const TIMEFRAMES = ["15M", "1H", "4H", "1D", "1W", "1M"];

function sma(data, period) {
  const out = [];
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    sum += data[i].close;
    if (i >= period) sum -= data[i - period].close;
    if (i >= period - 1) out.push({ time: data[i].time, value: +(sum / period).toFixed(2) });
  }
  return out;
}

// Gráfico PRO con TradingView Lightweight Charts (gratis): velas limpias + SMA + zonas de
// compra y niveles dibujados con líneas de precio. Fase 1 del rediseño.
export default function LightweightChart({ candles, indicators, buyLevels, lines, timeframe, setTimeframe }) {
  const boxRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    const el = boxRef.current;
    if (!el || !candles || !candles.length) return;
    const dark = typeof document !== "undefined" && document.documentElement.classList.contains("dark");

    let chart;
    try {
      chart = createChart(el, {
        height: 460,
        layout: {
          background: { type: ColorType.Solid, color: dark ? "#0e1f1a" : "#ffffff" },
          textColor: dark ? "#8fa39b" : "#5c6b66",
          fontFamily: "ui-monospace, monospace",
        },
        grid: {
          vertLines: { color: dark ? "#1a3a32" : "#f0ece3" },
          horzLines: { color: dark ? "#1a3a32" : "#f0ece3" },
        },
        rightPriceScale: { borderColor: dark ? "#1a3a32" : "#e5e0d8" },
        timeScale: { borderColor: dark ? "#1a3a32" : "#e5e0d8", timeVisible: true, secondsVisible: false },
        crosshair: { mode: 1 },
        autoSize: true,
      });
    } catch (e) {
      return;
    }
    chartRef.current = chart;

    // Velas
    const data = candles
      .filter((c) => c && c.close != null)
      .map((c) => ({
        time: Math.floor(new Date(c.date).getTime() / 1000),
        open: c.open ?? c.close,
        high: c.high ?? c.close,
        low: c.low ?? c.close,
        close: c.close,
      }))
      .filter((c) => Number.isFinite(c.time));

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    candleSeries.setData(data);

    // Medias móviles
    if (data.length >= 60) {
      const s50 = chart.addLineSeries({ color: "#2563eb", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s50.setData(sma(data, 50));
    }
    if (data.length >= 200) {
      const s200 = chart.addLineSeries({ color: "#b8860b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s200.setData(sma(data, 200));
    }

    // Zonas de compra (niveles del motor) como líneas de precio
    (buyLevels || []).slice(0, 5).forEach((z, i) => {
      if (z?.price == null) return;
      candleSeries.createPriceLine({
        price: z.price, color: z.tactical ? "#b8860b" : "#2563eb",
        lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true,
        title: `Compra ${i + 1}`,
      });
    });

    // Soportes / resistencias del detector
    (lines?.levels || []).slice(0, 4).forEach((lv) => {
      if (lv?.price == null) return;
      candleSeries.createPriceLine({
        price: lv.price, color: lv.role === "resistencia" ? "#d85c41" : "#4a7c59",
        lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true,
        title: lv.role === "resistencia" ? "Resist." : "Soporte",
      });
    });

    chart.timeScale().fitContent();

    return () => { try { chart.remove(); } catch (e) {} chartRef.current = null; };
  }, [candles, buyLevels, lines, indicators]);

  return (
    <div className="card-flat p-3">
      <div className="flex items-center gap-1 mb-2 flex-wrap">
        {TIMEFRAMES.map((tf) => (
          <button key={tf} onClick={() => setTimeframe?.(tf)}
            className={`px-2 py-1 rounded text-[11px] font-mono font-semibold ${timeframe === tf ? "bg-[#1a3a32] text-white" : "bg-[#f0ece3] text-[#5c6b66]"}`}>
            {tf}
          </button>
        ))}
        <span className="text-[10px] text-[#8a958f] ml-auto">TradingView Lightweight</span>
      </div>
      <div ref={boxRef} style={{ width: "100%", height: 460 }} />
      <p className="text-[10px] text-[#8a958f] mt-2">Azul: zonas de compra · Verde/rojo punteado: soporte/resistencia · Líneas: SMA 50 (azul) / 200 (dorado).</p>
    </div>
  );
}
