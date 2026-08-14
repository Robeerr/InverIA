import React from "react";
import { Users } from "@phosphor-icons/react";

function Bar({ label, value, total, color }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-etiqueta uppercase tracking-[0.15em] text-tinta-3 w-24">{label}</span>
      <div className="flex-1 h-3 bg-fondo rounded overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-tinta w-6 text-right">{value}</span>
    </div>
  );
}

export default function AnalystConsensusCard({ data }) {
  if (!data || !data.consensus) {
    return (
      <section data-testid="analyst-consensus-empty" className="iv-panel p-6">
        <div className="flex items-center gap-2 mb-2">
          <Users size={18} weight="bold" className="text-marca" />
          <h3 className="font-heading font-semibold text-lg text-tinta">Consenso Analistas</h3>
        </div>
        <p className="text-sm text-tinta-3">Sin datos de analistas disponibles.</p>
      </section>
    );
  }

  const c = data.consensus;
  const b = c.breakdown;
  const total = c.total_analysts;
  const tone =
    c.score >= 60 ? "text-sube" : c.score >= 45 ? "text-tinta" : "text-baja";

  return (
    <section data-testid="analyst-consensus" className="iv-panel p-6 animate-fade-up">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Users size={18} weight="bold" className="text-marca" />
          <h3 className="font-heading font-semibold text-lg text-tinta">Consenso Wall Street</h3>
        </div>
        <span className="font-mono text-etiqueta uppercase tracking-[0.2em] text-tinta-3">
          {c.period ? new Date(c.period + "T00:00:00").toLocaleDateString("es-ES", { month: "short", year: "numeric" }) : ""} · {total} analistas
        </span>
      </div>

      <div className="flex items-baseline gap-3 mb-4">
        <p data-testid="consensus-rating" className={`font-heading font-bold text-3xl ${tone}`}>{c.consensus}</p>
        <p className="font-mono text-sm text-tinta-3">Score: <span className="text-tinta font-semibold">{c.score}/100</span></p>
      </div>

      <div className="space-y-2">
        <Bar label="Compra Fuerte" value={b.strong_buy} total={total} color="bg-sube" />
        <Bar label="Compra" value={b.buy} total={total} color="bg-sube/70" />
        <Bar label="Mantener" value={b.hold} total={total} color="bg-tinta-3" />
        <Bar label="Venta" value={b.sell} total={total} color="bg-baja/70" />
        <Bar label="Venta Fuerte" value={b.strong_sell} total={total} color="bg-baja" />
      </div>
    </section>
  );
}
