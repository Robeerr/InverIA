import React from "react";
import { Users } from "@phosphor-icons/react";

function Bar({ label, value, total, color }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="grid grid-cols-[7.5rem_minmax(0,1fr)_2.5rem] items-center gap-3">
      <span className="iv-etiqueta whitespace-nowrap">{label}</span>
      <div className="h-1.5 bg-superficie-alt rounded-full overflow-hidden" aria-hidden="true">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="iv-cifra text-apoyo text-tinta text-right">{value}</span>
    </div>
  );
}

export default function AnalystConsensusCard({ data }) {
  if (!data || !data.consensus) {
    return (
      <section data-testid="analyst-consensus-empty" className="iv-panel p-5">
        <h3 className="font-heading text-cuerpo font-semibold text-tinta flex items-center gap-2">
          <Users size={16} weight="bold" className="text-tinta-3" aria-hidden="true" />
          Consenso Analistas
        </h3>
        <p className="text-apoyo text-tinta-3 mt-1">Sin datos de analistas disponibles.</p>
      </section>
    );
  }

  const c = data.consensus;
  const b = c.breakdown;
  const total = c.total_analysts;
  const tone =
    c.score >= 60 ? "text-sube" : c.score >= 45 ? "text-tinta" : "text-baja";

  return (
    <section data-testid="analyst-consensus" className="iv-panel p-5">
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-3">
        <h3 className="font-heading text-cuerpo font-semibold text-tinta flex items-center gap-2">
          <Users size={16} weight="bold" className="text-tinta-3" aria-hidden="true" />
          Consenso Wall Street
        </h3>
        <span className="iv-etiqueta">
          {c.period ? new Date(c.period + "T00:00:00").toLocaleDateString("es-ES", { month: "short", year: "numeric" }) : ""} · {total} analistas
        </span>
      </div>

      <div className="flex items-baseline gap-3 flex-wrap mb-4">
        <p data-testid="consensus-rating" className={`font-heading text-cifra ${tone}`}>{c.consensus}</p>
        <p className="text-apoyo text-tinta-3">Score: <span className="iv-cifra text-tinta font-semibold">{c.score}/100</span></p>
      </div>

      <div className="space-y-2.5">
        <Bar label="Compra Fuerte" value={b.strong_buy} total={total} color="bg-sube" />
        <Bar label="Compra" value={b.buy} total={total} color="bg-sube/70" />
        <Bar label="Mantener" value={b.hold} total={total} color="bg-tinta-3" />
        <Bar label="Venta" value={b.sell} total={total} color="bg-baja/70" />
        <Bar label="Venta Fuerte" value={b.strong_sell} total={total} color="bg-baja" />
      </div>
    </section>
  );
}
