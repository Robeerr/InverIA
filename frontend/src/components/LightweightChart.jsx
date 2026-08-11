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

// Opciones de aspecto según el modo. Fuera del componente para poder aplicarlas tanto al
// crear el gráfico como al cambiar de modo, sin duplicar la paleta en dos sitios.
function opcionesTema(dark) {
  return {
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
  };
}

function esOscuro() {
  return typeof document !== "undefined" && document.documentElement.classList.contains("dark");
}

// Gráfico PRO con TradingView Lightweight Charts (gratis): velas limpias + SMA + zonas de
// compra y niveles dibujados con líneas de precio.
//
// Se carga en diferido desde el Dashboard (React.lazy), así que la librería viaja en su
// propio fragmento y no retrasa el primer pintado de la página.
export default function LightweightChart({ candles, buyLevels, lines, timeframe, setTimeframe }) {
  const boxRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef([]);   // series de datos, para poder quitarlas sin tirar el gráfico

  // ── El gráfico se crea UNA vez ─────────────────────────────────────────────
  // Antes se creaba y destruía en cada cambio de velas, niveles, líneas… y también de los
  // indicadores, que ni siquiera se usaban aquí dentro: cada análisis de IA reconstruía el
  // gráfico entero para nada. Esa prop ya no se recibe. Recrearlo cuesta un reflow y pierde
  // el zoom y el desplazamiento que el
  // usuario tuviera puestos.
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    let chart;
    try {
      chart = createChart(el, { height: 460, crosshair: { mode: 1 }, autoSize: true,
                                ...opcionesTema(esOscuro()) });
    } catch (e) {
      return;
    }
    chartRef.current = chart;
    return () => {
      try { chart.remove(); } catch (e) {}
      chartRef.current = null;
      seriesRef.current = [];
    };
  }, []);

  // El modo oscuro se reaplica sobre el gráfico existente. Antes el aspecto solo se leía al
  // crearlo, así que al cambiar de modo el gráfico se quedaba con la paleta anterior hasta
  // que llegaran datos nuevos; ahora que ya no se recrea, haría falta esperar indefinidamente.
  useEffect(() => {
    const aplicar = () => { try { chartRef.current?.applyOptions(opcionesTema(esOscuro())); } catch (e) {} };
    const obs = new MutationObserver(aplicar);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  // ── Los datos se vuelven a pintar sobre el gráfico que ya existe ───────────
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    // Quita las series de la pasada anterior. Los indicadores NO entran aquí: no se usan en
    // este efecto, y tenerlos como dependencia repintaba el gráfico cada vez que el análisis
    // de IA devolvía indicadores nuevos. Por eso el componente ya ni los recibe.
    //
    // La limpieza va ANTES de comprobar si hay velas, y no después: al cambiar de acción
    // llegan velas vacías durante un instante, y saliendo antes de limpiar se quedaba en
    // pantalla el gráfico de la acción ANTERIOR bajo el ticker nuevo. Mientras el gráfico se
    // recreaba entero esto no se notaba; ahora que sobrevive, sí.
    for (const s of seriesRef.current) {
      try { chart.removeSeries(s); } catch (e) {}
    }
    seriesRef.current = [];
    if (!candles || !candles.length) return;
    const registrar = (s) => { seriesRef.current.push(s); return s; };

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

    const candleSeries = registrar(chart.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    }));
    candleSeries.setData(data);

    // Medias móviles
    if (data.length >= 60) {
      const s50 = registrar(chart.addLineSeries({ color: "#2563eb", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }));
      s50.setData(sma(data, 50));
    }
    if (data.length >= 200) {
      const s200 = registrar(chart.addLineSeries({ color: "#b8860b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }));
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

    // RESISTENCIA. Se queda, y es la única línea que sobrevive de `lines.levels`.
    //
    // El soporte que se dibujaba aquí al lado SÍ sobraba: competía con las zonas C1..C3
    // de arriba, que salen del motor de confluencia y llevan fuerza y razones detrás. Dos
    // opiniones sobre el mismo soporte, pintadas juntas y sin decir cuál manda, valen
    // menos que una buena.
    //
    // La resistencia no tiene ese problema porque no tiene competencia: `levels_engine`
    // solo calcula zonas de COMPRA —cero menciones a resistencias en todo el módulo—, así
    // que quitarla dejaría el gráfico sin techo. Es una asimetría real del producto:
    // InverIA sabe mucho mejor dónde comprar que dónde vender.
    const res = (lines?.levels || []).find((l) => l?.role === "resistencia" && l.price != null);
    if (res) candleSeries.createPriceLine({ price: res.price, color: "#d85c41", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "Res" });

    // DIRECTRICES (Fase 2): líneas diagonales que unen los swings, como las dibuja un trader.
    // El backend las da en coordenadas de índice de vela; las mapeamos a la escala temporal
    // extendiendo la pendiente hasta la última vela.
    const idxTime = (i) => {
      const c = candles[i];
      return c && c.date ? Math.floor(new Date(c.date).getTime() / 1000) : null;
    };
    // Directrices genéricas (soporte/resistencia diagonales): SOLO cuando no hay un patrón
    // con su propia geometría, para no ensuciar el gráfico con líneas redundantes.
    const hasPatternLines = !!lines?.pattern_draw?.lines?.length;
    if (!hasPatternLines) {
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
        const seg = registrar(chart.addLineSeries({ color: col, lineWidth: 2, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }));
        seg.setData([
          { time: tA, value: +a.price.toFixed(2) },
          { time: tB, value: +(a.price + slope * (lastIdx - a.index)).toFixed(2) },
        ]);
      });
    }

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
        const s = registrar(chart.addLineSeries({
          color: colorFor(ln.tipo), lineWidth: 2,
          lineStyle: dashed(ln.tipo) ? LineStyle.Dashed : LineStyle.Solid,
          priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        }));
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
  }, [candles, buyLevels, lines]);

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
        <div className="mt-2 space-y-1">
          <div className="flex items-start gap-2 text-[11px]">
            <span className={`px-1.5 py-0.5 rounded font-mono font-semibold ${lines.pattern.sentido === "alcista" ? "bg-[#e6f4ea] text-[#1e7a3a]" : lines.pattern.sentido === "bajista" ? "bg-[#fbe9e6] text-[#c0392b]" : "bg-[#f0ece3] text-[#5c6b66]"}`}>
              {lines.pattern.nombre}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-[#f0ece3] text-[#8a958f] text-[9px] font-mono uppercase tracking-wide shrink-0">auto</span>
            <span className="text-[#5c6b66] flex-1">{lines.pattern.descripcion}</span>
          </div>
          <p className="text-[10px] text-[#8a958f] italic">Detección automática por geometría (puede fallar). El veredicto fiable lo da el 🎯 Chartista IA de abajo.</p>
        </div>
      )}
      <p className="text-[10px] text-[#8a958f] mt-2">Diagonales: directrices · Azul: zonas de compra · Verde/rojo punteado: soporte/resistencia · SMA 50 (azul) / 200 (dorado).</p>
    </div>
  );
}
