import React from "react";
import { fmtPrice } from "../lib/format";

// Barra de señal inferior (estilo terminal): fija abajo, siempre visible con lo esencial
// del valor activo — precio, régimen, señal IA y niveles clave. Mobile-first (scroll horiz).
const RECO = {
  COMPRAR: { c: "rgb(var(--iv-sube))", label: "COMPRA" },
  VENDER: { c: "rgb(var(--iv-baja))", label: "VENTA" },
  MANTENER: { c: "rgb(var(--iv-aviso))", label: "MANTENER" },
};

function Chip({ label, value, color }) {
  return (
    <div className="flex flex-col leading-tight shrink-0">
      <span className="text-[8px] uppercase tracking-wider text-tinta-3">{label}</span>
      <span className="text-[11px] font-mono font-semibold" style={{ color: color || "rgb(var(--iv-tinta))" }}>{value}</span>
    </div>
  );
}

export default function BottomSignalBar({ symbol, quote, indicators, analysis }) {
  if (!quote) return null;
  const chg = quote.change_percent ?? quote.daily_change_percent;
  const reco = analysis?.recommendation ? (RECO[analysis.recommendation] || RECO.MANTENER) : null;
  const regime = indicators?.regime?.regime || indicators?.trend || "—";
  const regLight = indicators?.regime?.light;
  const regColor = regLight === "rojo" ? "rgb(var(--iv-baja))" : regLight === "amarillo" ? "rgb(var(--iv-aviso))"
    : regLight === "verde" ? "rgb(var(--iv-sube))" : "rgb(var(--iv-tinta-3))";

  return (
    <div className="iv-oscuro fixed bottom-0 left-0 right-0 z-40 bg-fondo border-t border-linea"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      <div className="max-w-[1480px] mx-auto flex items-center gap-4 px-3 py-2 overflow-x-auto no-scrollbar">
        <div className="flex flex-col leading-tight shrink-0">
          <span className="text-xs font-mono font-bold text-tinta">{symbol}</span>
          <span className="text-[11px] font-mono" style={{ color: chg == null ? "rgb(var(--iv-tinta-3))" : chg >= 0 ? "rgb(var(--iv-sube))" : "rgb(var(--iv-baja))" }}>
            ${fmtPrice(quote.price)} {chg != null ? `${chg >= 0 ? "+" : ""}${chg}%` : ""}
          </span>
        </div>
        <div className="w-px h-7 bg-linea shrink-0" />
        <Chip label="Régimen" value={regime} color={regColor} />
        {reco ? (
          <Chip label="Señal IA" value={reco.label} color={reco.c} />
        ) : (
          <Chip label="Señal IA" value="sin análisis" color="rgb(var(--iv-tinta-3))" />
        )}
        {analysis?.entry_zone?.min != null && <Chip label="Entrada" value={`$${fmtPrice(analysis.entry_zone.min)}`} color="rgb(var(--iv-info))" />}
        {analysis?.stop_loss != null && <Chip label="Stop" value={`$${fmtPrice(analysis.stop_loss)}`} color="rgb(var(--iv-baja))" />}
        {analysis?.take_profit_1 != null && <Chip label="TP1" value={`$${fmtPrice(analysis.take_profit_1)}`} color="rgb(var(--iv-sube))" />}
        {indicators?.salida_10w && (
          <Chip label="10 sem" value={indicators.salida_10w.por_encima ? "Mantener" : "Salida"}
            color={indicators.salida_10w.por_encima ? "rgb(var(--iv-sube))" : "rgb(var(--iv-baja))"} />
        )}
      </div>
    </div>
  );
}
