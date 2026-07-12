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

    // Zonas de compra (niveles del motor) como líneas de precio — solo las 3 más cercanas
    // al precio actual, con etiqueta corta, para no amontonar el eje.
    const px = data.length ? data[data.length - 1].close : null;
    const cercanas = (buyLevels || [])
      .filter((z) => z?.price != null)
      .sort((a, b) => (px != null ? Math.abs(a.price - px) - Math.abs(b.price - px) : 0))
      .slice(0, 3);
    cercanas.forEach((z, i) => {
      candleSeries.createPriceLine({
        price: z.price, color: z.tactical ? "#b8860b" : "#2563eb",
        lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true,
        title: `C${i + 1}`,
      });
    });

    // Soporte y resistencia más relevantes (1 de cada), etiqueta corta.
    const res = (lines?.levels || []).find((l) => l?.role === "resistencia" && l.price != null);
    const sop = (lines?.levels || []).find((l) => l?.role === "soporte" && l.price != null);
    if (res) candleSeries.createPriceLine({ price: res.price, color: "#d85c41", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "Res" });
    if (sop) candleSeries.createPriceLine({ price: sop.price, color: "#4a7c59", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "Sop" });

    // DIRECTRICES (Fase 2): líneas diagonales que unen los swings, como las dibuja un trader.
    // El backend las da en coordenadas de índice de vela; las mapeamos a la escala temporal
    // extendiendo la pendiente hasta la última vela.
    const idxTime = (i) => {
      const c = candles[i];
      return c && c.date ? Math.floor(new Date(c.date).getTime() / 1000) : null;
    };
    (lines?.trendlines || []).forEach((tl) => {
      const pts = tl.points || [];
      if (pts.length < 2) return;
      const a = pts[0], b = pts[1];
      const slope = (b.price - a.price) / ((b.index - a.index) || 1);
      const lastIdx = candles.length - 1;
      const tA = idxTime(a.index);
      const tB = idxTime(lastIdx);
      if (tA == null || tB == null || tB <= tA) return;
      const col = tl.kind === "resistencia" ? "#d85c41" : "#4a7c59";
      const seg = chart.addLineSeries({ color: col, lineWidth: 2, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      seg.setData([
        { time: tA, value: +a.price.toFixed(2) },
        { time: tB, value: +(a.price + slope * (lastIdx - a.index)).toFixed(2) },
      ]);
    });

    // PATRÓN DIBUJADO (Fase final): el backend normaliza la geometría de cualquier patrón
    // (arco de taza, neckline, directrices, objetivo, pivotes) a pattern_draw. Lo pintamos.
    const pd = lines?.pattern_draw;
    if (pd?.lines?.length) {
      // Color por tipo de línea (con fallback al sentido del patrón).
      const colorFor = (tipo) => {
        const t = (tipo || "").toLowerCase();
        if (t.includes("objetivo")) return "#2563eb";
        if (t.includes("invalid") || t.includes("stop")) return "#c0392b";
        if (t.includes("cuello") || t.includes("neck")) return "#d9a441";
        if (t.includes("resist") || t.includes("buy")) return "#d85c41";
        if (t.includes("sop")) return "#4a7c59";
        if (t.includes("base")) return "#8a958f";
        if (t.includes("arco") || t.includes("taza")) return "#7c5cbf";
        return pd.sentido === "bajista" ? "#c0392b" : pd.sentido === "alcista" ? "#1e7a3a" : "#5c6b66";
      };
      const dashed = (tipo) => {
        const t = (tipo || "").toLowerCase();
        return t.includes("objetivo") || t.includes("invalid") || t.includes("base") || t.includes("mitad");
      };
      pd.lines.forEach((ln) => {
        const raw = (ln.points || [])
          .map((p) => ({ time: idxTime(p.index), value: p.price }))
          .filter((p) => p.time != null && Number.isFinite(p.value));
        // Ordena por tiempo y elimina duplicados de tiempo (Lightweight lo exige).
        raw.sort((a, b) => a.time - b.time);
        const data = raw.filter((p, i) => i === 0 || p.time !== raw[i - 1].time);
        if (data.length < 2) return;
        const s = chart.addLineSeries({
          color: colorFor(ln.tipo), lineWidth: 2,
          lineStyle: dashed(ln.tipo) ? LineStyle.Dashed : LineStyle.Solid,
          priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        });
        s.setData(data);
      });
      // Marcadores de pivotes (P1, HI, C, V1…) sobre las velas.
      const mk = (pd.markers || [])
        .map((m) => ({ t: idxTime(m.index), label: m.label, sentido: pd.sentido }))
        .filter((m) => m.t != null && m.label)
        .sort((a, b) => a.t - b.t)
        .filter((m, i, arr) => i === 0 || m.t !== arr[i - 1].t);
      if (mk.length) {
        candleSeries.setMarkers(mk.map((m) => ({
          time: m.t, position: "aboveBar", shape: "circle",
          color: m.sentido === "bajista" ? "#c0392b" : "#1e7a3a", text: m.label,
        })));
      }
    }

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
      {lines?.pattern && (
        <div className="mt-2 flex items-start gap-2 text-[11px]">
          <span className={`px-1.5 py-0.5 rounded font-mono font-semibold ${lines.pattern.sentido === "alcista" ? "bg-[#e6f4ea] text-[#1e7a3a]" : lines.pattern.sentido === "bajista" ? "bg-[#fbe9e6] text-[#c0392b]" : "bg-[#f0ece3] text-[#5c6b66]"}`}>
            {lines.pattern.nombre}
          </span>
          <span className="text-[#5c6b66] flex-1">{lines.pattern.descripcion}</span>
        </div>
      )}
      <p className="text-[10px] text-[#8a958f] mt-2">Diagonales: directrices · Azul: zonas de compra · Verde/rojo punteado: soporte/resistencia · SMA 50 (azul) / 200 (dorado).</p>
    </div>
  );
}
