import React from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarBlank, ArrowRight, ArrowClockwise } from "@phosphor-icons/react";
import { api } from "../lib/api";
import { useSignals } from "../hooks/useSignals";

function dayLabel(dateStr) {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  return d.toLocaleDateString("es-ES", { weekday: "short", day: "2-digit", month: "short" });
}

function hourLabel(h) {
  if (!h) return "—";
  const map = { bmo: "Antes apertura", amc: "Tras cierre", dmh: "Durante sesión" };
  return map[h] || h;
}

export default function CalendarView({ setSymbol }) {
  const [days, setDays] = React.useState(14);
  const [refreshN, setRefreshN] = React.useState(0);

  // Señales desde el caché compartido (no se re-piden al cambiar "días").
  const { data: signals } = useSignals();
  const syms = React.useMemo(() => {
    const entries = Array.isArray(signals) ? signals : (signals?.items || signals?.entries || []);
    return [...new Set(entries.map((e) => e.symbol).filter(Boolean))];
  }, [signals]);

  // Mapa símbolo → grupo de Alertas (Cartera / Cimientos), para ver de qué pestaña sale
  // cada earnings (así identificas los que no recuerdas haber añadido).
  const symGroup = React.useMemo(() => {
    const entries = Array.isArray(signals) ? signals : (signals?.items || signals?.entries || []);
    const labels = { ideas_javi: "Cartera", cimientos: "Cimientos" };
    const m = {};
    entries.forEach((e) => {
      if (e.symbol) m[e.symbol.toUpperCase()] = labels[e.grupo || "ideas_javi"] || (e.grupo || "Cartera");
    });
    return m;
  }, [signals]);

  // Earnings de esos símbolos: el backend los trae en paralelo por símbolo.
  const earningsQuery = useQuery({
    queryKey: ["earnings", days, syms, refreshN],
    queryFn: () =>
      syms.length ? api.calendar.earnings(days, syms.join(","), refreshN > 0) : Promise.resolve({ items: [] }),
    enabled: signals !== undefined,
    staleTime: 5 * 60_000,
  });
  const data = earningsQuery.data;
  const loading = signals === undefined || earningsQuery.isFetching;

  const grouped = React.useMemo(() => {
    if (!data?.items) return [];
    const m = {};
    data.items.forEach((it) => {
      const k = it.date || "Sin fecha";
      (m[k] = m[k] || []).push(it);
    });
    return Object.entries(m).map(([date, items]) => ({ date, items }));
  }, [data]);

  return (
    <div data-testid="calendar-view" className="space-y-6">
      <section className="card-flat p-6">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
          <div>
            <div className="flex items-center gap-2">
              <CalendarBlank size={20} weight="bold" className="text-[#1a3a32]" />
              <h2 className="font-heading font-bold text-2xl text-[#0e1f1a]">Calendario de Resultados</h2>
            </div>
            <p className="text-sm text-[#5c6b66] mt-1">
              Próximos earnings de tus acciones en Señales.
            </p>
          </div>
          <button onClick={() => setRefreshN((n) => n + 1)} title="Recargar (datos frescos)"
            className="p-2 rounded-md border border-[#e5e0d8] text-[#1a3a32] mr-1">
            <ArrowClockwise size={16} weight="bold" className={loading ? "animate-spin" : ""} />
          </button>
          <select
            data-testid="days-select"
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value))}
            className="bg-white border border-[#e5e0d8] rounded text-xs px-2 py-1.5 font-mono"
          >
            <option value={7}>Próximos 7 días</option>
            <option value={14}>Próximos 14 días</option>
            <option value={30}>Próximos 30 días</option>
            <option value={60}>Próximos 60 días</option>
          </select>
        </div>
      </section>

      {loading && <div className="card-flat p-8 text-center text-[#5c6b66]">Cargando calendario...</div>}

      {!loading && data && grouped.length === 0 && (
        <div className="card-flat p-12 text-center">
          <p className="text-sm text-[#5c6b66]">Ninguna de tus señales tiene earnings en este período.</p>
        </div>
      )}

      {!loading && grouped.map(({ date, items }) => (
        <section key={date} className="card-flat p-4">
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a] capitalize mb-3">{dayLabel(date)}</h3>
          <div className="space-y-1">
            {items.map((it, i) => (
              <div
                key={`${it.symbol}-${i}`}
                data-testid={`earnings-${it.symbol}`}
                className="flex items-center gap-3 p-2 hover:bg-[#f5f3ef] rounded cursor-pointer"
                /* setSymbol ya navega a /accion/:symbol. El navigate("/") que había
                   aquí ahora llevaría a la portada, que es lo contrario de lo que
                   espera quien pulsa una fila del calendario. */
                onClick={() => setSymbol(it.symbol)}
              >
                <div className="w-11 h-11 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center font-mono font-bold text-xs shrink-0">
                  {it.symbol.slice(0, 4)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <p className="font-mono font-semibold text-sm text-[#0e1f1a]">{it.symbol}</p>
                    {symGroup[it.symbol?.toUpperCase()] && (
                      <span className="text-[8px] font-semibold px-1.5 py-0.5 rounded-full bg-[#1a3a32]/10 text-[#1a3a32]">
                        {symGroup[it.symbol.toUpperCase()]}
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-[#5c6b66] truncate">
                    Q{it.quarter} {it.year} · {hourLabel(it.hour)}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="font-mono text-[9px] uppercase text-[#5c6b66]">EPS est.</p>
                  <p className="font-mono text-sm text-[#0e1f1a]">{it.eps_estimate ?? "—"}</p>
                </div>
                <ArrowRight size={14} className="text-[#5c6b66] shrink-0" />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
