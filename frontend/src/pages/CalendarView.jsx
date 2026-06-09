import React from "react";
import { useNavigate } from "react-router-dom";
import { CalendarBlank, ArrowRight } from "@phosphor-icons/react";
import { API } from "../lib/api";
import axios from "axios";

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
  const navigate = useNavigate();
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [days, setDays] = React.useState(14);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("inveria_token");
      const headers = token ? { Authorization: `Bearer ${token}` } : {};

      // Fetch signals list to get the symbols
      const sigRes = await axios.get(`${API}/signals`, { headers });
      const entries = sigRes.data?.entries || sigRes.data || [];
      const syms = [...new Set(entries.map((e) => e.symbol).filter(Boolean))];

      if (!syms.length) {
        setData({ items: [] });
        return;
      }

      const symbolsParam = syms.join(",");
      console.log("[CalendarView] Buscando earnings para:", symbolsParam);
      const earningsRes = await axios.get(`${API}/calendar/earnings`, {
        headers,
        params: { days, symbols: symbolsParam },
      });
      console.log("[CalendarView] Respuesta Finnhub:", earningsRes.data);
      setData(earningsRes.data || { items: [] });
    } catch {
      setData({ items: [] });
    } finally {
      setLoading(false);
    }
  }, [days]);

  React.useEffect(() => { load(); }, [load]);

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
                className="grid grid-cols-[80px_1fr_120px_120px_24px] items-center gap-3 p-2 hover:bg-[#f5f3ef] rounded cursor-pointer"
                onClick={() => { setSymbol(it.symbol); navigate("/"); }}
              >
                <div className="w-12 h-12 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center font-mono font-bold text-xs">
                  {it.symbol.slice(0, 4)}
                </div>
                <div>
                  <p className="font-mono font-semibold text-sm text-[#0e1f1a]">{it.symbol}</p>
                  <p className="text-[10px] text-[#5c6b66]">Q{it.quarter} {it.year}</p>
                </div>
                <div>
                  <p className="font-mono text-[10px] uppercase text-[#5c6b66]">EPS estimado</p>
                  <p className="font-mono text-sm">{it.eps_estimate ?? "—"}</p>
                </div>
                <div>
                  <p className="font-mono text-[10px] uppercase text-[#5c6b66]">Momento</p>
                  <p className="font-mono text-xs">{hourLabel(it.hour)}</p>
                </div>
                <ArrowRight size={14} className="text-[#5c6b66]" />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
