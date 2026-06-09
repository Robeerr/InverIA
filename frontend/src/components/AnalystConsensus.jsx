import React from "react";
import { Users } from "@phosphor-icons/react";

function Bar({ label, value, total, color }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] w-24">{label}</span>
      <div className="flex-1 h-3 bg-[#f5f3ef] rounded overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-[#0e1f1a] w-6 text-right">{value}</span>
    </div>
  );
}

export default function AnalystConsensusCard({ data }) {
  if (!data || !data.consensus) {
    return (
      <section data-testid="analyst-consensus-empty" className="card-flat p-6">
        <div className="flex items-center gap-2 mb-2">
          <Users size={18} weight="bold" className="text-[#1a3a32]" />
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Consenso Analistas</h3>
        </div>
        <p className="text-sm text-[#5c6b66]">Sin datos de analistas disponibles.</p>
      </section>
    );
  }

  const c = data.consensus;
  const b = c.breakdown;
  const total = c.total_analysts;
  const tone =
    c.score >= 60 ? "text-[#4a7c59]" : c.score >= 45 ? "text-[#0e1f1a]" : "text-[#d85c41]";

  return (
    <section data-testid="analyst-consensus" className="card-flat p-6 animate-fade-up">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Users size={18} weight="bold" className="text-[#1a3a32]" />
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Consenso Wall Street</h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">
          {c.period ? new Date(c.period + "T00:00:00").toLocaleDateString("es-ES", { month: "short", year: "numeric" }) : ""} · {total} analistas
        </span>
      </div>

      <div className="flex items-baseline gap-3 mb-4">
        <p data-testid="consensus-rating" className={`font-heading font-bold text-3xl ${tone}`}>{c.consensus}</p>
        <p className="font-mono text-sm text-[#5c6b66]">Score: <span className="text-[#0e1f1a] font-semibold">{c.score}/100</span></p>
      </div>

      <div className="space-y-2">
        <Bar label="Compra Fuerte" value={b.strong_buy} total={total} color="bg-[#4a7c59]" />
        <Bar label="Compra" value={b.buy} total={total} color="bg-[#4a7c59]/70" />
        <Bar label="Mantener" value={b.hold} total={total} color="bg-[#5c6b66]" />
        <Bar label="Venta" value={b.sell} total={total} color="bg-[#d85c41]/70" />
        <Bar label="Venta Fuerte" value={b.strong_sell} total={total} color="bg-[#d85c41]" />
      </div>
    </section>
  );
}
