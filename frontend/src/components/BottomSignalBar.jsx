import React from "react";
import { fmtPrice } from "../lib/format";

// Barra de señal inferior (estilo terminal): fija abajo, siempre visible con lo esencial
// del valor activo — precio, régimen, señal IA y niveles clave. Mobile-first (scroll horiz).
const RECO = {
  COMPRAR: { c: "#4a7c59", label: "COMPRA" },
  VENDER: { c: "#d85c41", label: "VENTA" },
  MANTENER: { c: "#c9a14a", label: "MANTENER" },
};

function Chip({ label, value, color }) {
  return (
    <div className="flex flex-col leading-tight shrink-0">
      <span className="text-[8px] uppercase tracking-wider text-[#8fa39b]">{label}</span>
      <span className="text-[11px] font-mono font-semibold" style={{ color: color || "#f5f3ef" }}>{value}</span>
    </div>
  );
}

export default function BottomSignalBar({ symbol, quote, indicators, analysis }) {
  if (!quote) return null;
  const chg = quote.change_percent ?? quote.daily_change_percent;
  const reco = analysis?.recommendation ? (RECO[analysis.recommendation] || RECO.MANTENER) : null;
  const regime = indicators?.regime?.regime || indicators?.trend || "—";
  const regLight = indicators?.regime?.light;
  const regColor = regLight === "rojo" ? "#d85c41" : regLight === "amarillo" ? "#c9a14a"
    : regLight === "verde" ? "#4a7c59" : "#8fa39b";

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 bg-[#0e1f1a] border-t border-[#1a3a32]"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      <div className="max-w-[1480px] mx-auto flex items-center gap-4 px-3 py-2 overflow-x-auto no-scrollbar">
        <div className="flex flex-col leading-tight shrink-0">
          <span className="text-xs font-mono font-bold text-[#f5f3ef]">{symbol}</span>
          <span className="text-[11px] font-mono" style={{ color: chg == null ? "#8fa39b" : chg >= 0 ? "#8fd6a6" : "#f0a598" }}>
            ${fmtPrice(quote.price)} {chg != null ? `${chg >= 0 ? "+" : ""}${chg}%` : ""}
          </span>
        </div>
        <div className="w-px h-7 bg-[#1a3a32] shrink-0" />
        <Chip label="Régimen" value={regime} color={regColor} />
        {reco ? (
          <Chip label="Señal IA" value={reco.label} color={reco.c} />
        ) : (
          <Chip label="Señal IA" value="sin análisis" color="#8fa39b" />
        )}
        {analysis?.entry_zone?.min != null && <Chip label="Entrada" value={`$${fmtPrice(analysis.entry_zone.min)}`} color="#7db3f0" />}
        {analysis?.stop_loss != null && <Chip label="Stop" value={`$${fmtPrice(analysis.stop_loss)}`} color="#f0a598" />}
        {analysis?.take_profit_1 != null && <Chip label="TP1" value={`$${fmtPrice(analysis.take_profit_1)}`} color="#8fd6a6" />}
        {indicators?.salida_10w && (
          <Chip label="10 sem" value={indicators.salida_10w.por_encima ? "Mantener" : "Salida"}
            color={indicators.salida_10w.por_encima ? "#8fd6a6" : "#f0a598"} />
        )}
      </div>
    </div>
  );
}
