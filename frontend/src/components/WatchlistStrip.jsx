import React from "react";
import { useSignals } from "../hooks/useSignals";
import { fmtPrice } from "../lib/format";

// Tira de watchlist (estilo terminal): tus acciones de Cartera en una fila horizontal
// scrollable, con precio y cambio del día. Toca una para cargarla al instante. Mobile-first.
export default function WatchlistStrip({ symbol, setSymbol, vertical = false, className = "" }) {
  const { data: signals } = useSignals();
  const entries = React.useMemo(() => {
    const arr = Array.isArray(signals) ? signals : (signals?.items || signals?.entries || []);
    // Únicas por símbolo, orden por ticker.
    const seen = new Set();
    const out = [];
    for (const e of arr) {
      const s = (e.symbol || "").toUpperCase();
      if (!s || seen.has(s)) continue;
      seen.add(s);
      out.push(e);
    }
    return out.sort((a, b) => (a.symbol || "").localeCompare(b.symbol || ""));
  }, [signals]);

  if (!entries.length) return null;

  const wrapCls = vertical
    ? `flex flex-col gap-1.5 ${className}`
    : `flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 no-scrollbar ${className}`;

  return (
    <div className={wrapCls}>
      {vertical && <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-1 px-1">Watchlist</p>}
      {entries.map((e) => {
        const s = (e.symbol || "").toUpperCase();
        const active = s === (symbol || "").toUpperCase();
        const chg = e.daily_change_percent;
        const chgColor = chg == null ? "#5c6b66" : chg >= 0 ? "#4a7c59" : "#d85c41";
        return (
          <button
            key={s}
            onClick={() => setSymbol?.(s)}
            className={`rounded-lg border px-3 py-1.5 text-left transition-colors ${vertical ? "w-full" : "shrink-0"}`}
            style={{
              borderColor: active ? "#1a3a32" : "#e5e0d8",
              background: active ? "#1a3a32" : "white",
              minWidth: vertical ? undefined : 92,
            }}
          >
            <p className="font-mono font-bold text-xs" style={{ color: active ? "#f5f3ef" : "#0e1f1a" }}>{s}</p>
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-[11px]" style={{ color: active ? "#cdd8d2" : "#5c6b66" }}>
                {e.last_price != null ? `$${fmtPrice(e.last_price)}` : "—"}
              </span>
              {chg != null && (
                <span className="font-mono text-[10px] font-semibold" style={{ color: active ? (chg >= 0 ? "#8fd6a6" : "#f0a598") : chgColor }}>
                  {chg >= 0 ? "+" : ""}{chg}%
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
