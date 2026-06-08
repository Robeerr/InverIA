import React from "react";
import { ClockCounterClockwise, CaretDown, CaretUp } from "@phosphor-icons/react";
import { api } from "../lib/api";
import { fmtPrice, fmtDate } from "../lib/format";

function RecBadge({ rec }) {
  const cls =
    rec === "COMPRAR"
      ? "bg-[#4a7c59] text-[#f5f3ef]"
      : rec === "VENDER"
      ? "bg-[#d85c41] text-[#f5f3ef]"
      : "bg-[#5c6b66] text-[#f5f3ef]";
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider ${cls}`}>
      {rec || "—"}
    </span>
  );
}

export default function HistoryView() {
  const [items, setItems] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [expanded, setExpanded] = React.useState(null);
  const [filterSymbol, setFilterSymbol] = React.useState("");

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const sym = filterSymbol.trim().toUpperCase();
      const res = await api.history(sym || undefined);
      setItems(res.items || []);
    } finally {
      setLoading(false);
    }
  }, [filterSymbol]);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div data-testid="history-view" className="space-y-6">
      <section className="card-flat p-6">
        <div className="flex items-center gap-2 mb-2">
          <ClockCounterClockwise size={20} weight="bold" className="text-[#1a3a32]" />
          <h2 className="font-heading font-bold text-2xl text-[#0e1f1a]">Historial de Análisis IA</h2>
        </div>
        <p className="text-sm text-[#5c6b66] mb-4">
          Todos tus análisis IA guardados · Filtra por ticker.
        </p>
        <div className="flex gap-2">
          <input
            data-testid="history-filter"
            value={filterSymbol}
            onChange={(e) => setFilterSymbol(e.target.value.toUpperCase())}
            placeholder="Filtrar por ticker (vacío = todos)"
            className="flex-1 bg-white border border-[#e5e0d8] rounded-md px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a32]"
          />
        </div>
      </section>

      {loading && <div className="card-flat p-6 text-center text-[#5c6b66]">Cargando...</div>}

      {!loading && items.length === 0 && (
        <div className="card-flat p-12 text-center">
          <p className="text-sm text-[#5c6b66]">No hay análisis guardados todavía. Genera uno desde el dashboard.</p>
        </div>
      )}

      <div className="space-y-3">
        {items.map((it) => {
          const r = it.result || {};
          const q = it.quote_snapshot || {};
          const isOpen = expanded === it.id;
          return (
            <div key={it.id} data-testid={`history-item-${it.id}`} className="card-flat">
              <button
                onClick={() => setExpanded(isOpen ? null : it.id)}
                className="w-full p-4 flex items-center gap-4 text-left hover:bg-[#f5f3ef] transition-colors rounded-md"
              >
                <div className="w-12 h-12 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center font-mono font-bold text-sm shrink-0">
                  {it.symbol.slice(0, 3)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono font-bold text-base text-[#0e1f1a]">{it.symbol}</span>
                    <RecBadge rec={r.recommendation} />
                    <span className="text-[10px] uppercase tracking-wider text-[#5c6b66]">
                      {it.model} · confianza {r.confidence ?? "—"}%
                    </span>
                  </div>
                  <p className="text-xs text-[#5c6b66] mt-1">
                    {fmtDate(it.created_at)} · Precio al momento: ${fmtPrice(q.price)}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="font-mono text-xs text-[#5c6b66]">SL → TP1</p>
                  <p className="font-mono text-sm font-semibold text-[#0e1f1a]">
                    ${fmtPrice(r.stop_loss)} → ${fmtPrice(r.take_profit_1)}
                  </p>
                </div>
                {isOpen ? <CaretUp size={16} /> : <CaretDown size={16} />}
              </button>

              {isOpen && (
                <div className="px-4 pb-4 pt-2 border-t border-[#e5e0d8] space-y-3">
                  {r.summary && <p className="text-sm text-[#0e1f1a]">{r.summary}</p>}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <Mini label="Tendencia" value={r.trend} />
                    <Mini label="Horizonte" value={r.timeframe?.replace("_", " ")} />
                    <Mini label="R/R" value={r.risk_reward_ratio ? `1:${r.risk_reward_ratio}` : "—"} />
                    <Mini label="Entrada" value={r.entry_zone ? `$${fmtPrice(r.entry_zone.min)}-${fmtPrice(r.entry_zone.max)}` : "—"} />
                    <Mini label="Stop Loss" value={`$${fmtPrice(r.stop_loss)}`} tone="sell" />
                    <Mini label="TP1" value={`$${fmtPrice(r.take_profit_1)}`} tone="buy" />
                    <Mini label="TP2" value={`$${fmtPrice(r.take_profit_2)}`} tone="buy" />
                    <Mini label="Confianza" value={`${r.confidence ?? "—"}%`} />
                  </div>
                  {r.technical_analysis && (
                    <div className="p-3 bg-[#f5f3ef] rounded text-xs text-[#0e1f1a] leading-relaxed">
                      {r.technical_analysis}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Mini({ label, value, tone }) {
  const color = tone === "buy" ? "text-[#4a7c59]" : tone === "sell" ? "text-[#d85c41]" : "text-[#0e1f1a]";
  return (
    <div className="bg-[#f5f3ef] border border-[#e5e0d8] rounded px-2 py-1.5">
      <p className="font-mono text-[9px] uppercase tracking-[0.15em] text-[#5c6b66]">{label}</p>
      <p className={`font-mono text-xs font-semibold ${color} mt-0.5`}>{value || "—"}</p>
    </div>
  );
}
