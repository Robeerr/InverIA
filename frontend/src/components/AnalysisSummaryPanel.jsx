import React from "react";
import { fmtPrice } from "../lib/format";

// Panel consolidado estilo "terminal": señal + niveles clave + momentum + patrón,
// todo en una tarjeta junto al gráfico. Lee de los datos que ya existen (análisis,
// indicadores, niveles del motor, patrones del gráfico) y degrada con elegancia.
const RECO = {
  COMPRAR: { c: "#4a7c59", label: "COMPRA" },
  VENDER: { c: "#d85c41", label: "VENTA" },
  MANTENER: { c: "#c9a14a", label: "MANTENER" },
};

function Row({ label, value, color }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-[#e5e0d8] last:border-0">
      <span className="text-xs text-[#5c6b66]">{label}</span>
      <span className="text-sm font-mono font-semibold" style={{ color: color || "#0e1f1a" }}>{value}</span>
    </div>
  );
}

export default function AnalysisSummaryPanel({ analysis, indicators, buyLevels, lines, quote }) {
  const reco = analysis?.recommendation ? (RECO[analysis.recommendation] || RECO.MANTENER) : null;
  const conf = Math.max(0, Math.min(100, analysis?.confidence || 0));

  // Niveles clave: del análisis si existe; si no, los niveles del motor más cercanos.
  const price = quote?.price;
  const nearest = Array.isArray(buyLevels)
    ? [...buyLevels].filter((z) => z?.price != null).sort((a, b) => Math.abs(a.price - price) - Math.abs(b.price - price)).slice(0, 3)
    : [];

  // Momentum
  const rsi = indicators?.rsi;
  const rsiLabel = rsi == null ? "—" : rsi > 70 ? "sobrecompra" : rsi < 30 ? "sobreventa" : "neutro";
  const rsiColor = rsi == null ? "#5c6b66" : rsi > 70 ? "#d85c41" : rsi < 30 ? "#4a7c59" : "#5c6b66";
  const regime = indicators?.regime?.regime || indicators?.trend || analysis?.trend || "—";
  const vol = quote?.volume, avgVol = quote?.avg_volume;
  const volLabel = vol && avgVol ? (vol > avgVol * 1.3 ? "Alto" : vol < avgVol * 0.7 ? "Bajo" : "Normal") : "—";

  return (
    <section className="card-flat p-5 animate-fade-up" data-testid="analysis-summary">
      <h3 className="font-heading font-semibold text-base text-[#0e1f1a] mb-3">Resumen IA</h3>

      {/* Señal */}
      {reco ? (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono">Señal</span>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold" style={{ background: `${reco.c}18`, color: reco.c }}>
              {reco.label}
            </span>
          </div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-[#5c6b66]">Confianza</span>
            <span className="text-xs font-mono font-semibold text-[#0e1f1a]">{conf}%</span>
          </div>
          <div className="h-1.5 bg-[#e5e0d8] rounded-full overflow-hidden">
            <div className="h-full transition-all" style={{ width: `${conf}%`, background: reco.c }} />
          </div>
        </div>
      ) : (
        <p className="text-xs text-[#5c6b66] mb-4">Pulsa <b>Generar análisis</b> para la señal IA. Debajo tienes ya los niveles, patrón y momentum.</p>
      )}

      {/* Niveles clave */}
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-1">Niveles clave</p>
      <div className="mb-4">
        {analysis?.entry_zone?.min != null && <Row label="Entrada" value={`$${fmtPrice(analysis.entry_zone.min)}`} color="#2563eb" />}
        {analysis?.take_profit_1 != null && <Row label="TP1" value={`$${fmtPrice(analysis.take_profit_1)}`} color="#4a7c59" />}
        {analysis?.take_profit_2 != null && <Row label="TP2" value={`$${fmtPrice(analysis.take_profit_2)}`} color="#4a7c59" />}
        {analysis?.stop_loss != null && <Row label="Stop Loss" value={`$${fmtPrice(analysis.stop_loss)}`} color="#d85c41" />}
        {!analysis && nearest.map((z, i) => (
          <Row key={i} label={`Nivel ${i + 1}${z.tactical ? " · táct" : ""}`} value={`$${fmtPrice(z.price)}`} color={z.tactical ? "#b8860b" : "#2563eb"} />
        ))}
        {!analysis && nearest.length === 0 && <p className="text-xs text-[#5c6b66]">Sin niveles disponibles.</p>}
      </div>

      {/* Patrón */}
      {(lines?.pattern || lines?.candlestick) && (
        <>
          <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-1">Patrón</p>
          <div className="mb-4">
            {lines?.pattern && <Row label="📐 Estructura" value={lines.pattern.nombre} />}
            {lines?.candlestick && (
              <Row label="🕯️ Vela" value={lines.candlestick.nombre}
                color={lines.candlestick.sentido === "alcista" ? "#4a7c59" : lines.candlestick.sentido === "bajista" ? "#d85c41" : "#c9a14a"} />
            )}
          </div>
        </>
      )}

      {/* Momentum */}
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-1">Momentum</p>
      <div>
        <Row label="Tendencia" value={regime} />
        <Row label="Volumen" value={volLabel} />
        <Row label="RSI" value={rsi != null ? `${Math.round(rsi)} · ${rsiLabel}` : "—"} color={rsiColor} />
      </div>
    </section>
  );
}
