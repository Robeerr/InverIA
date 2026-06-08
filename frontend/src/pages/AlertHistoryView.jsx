import React, { useEffect, useState, useCallback } from "react";
import { Bell, ArrowsClockwise, Trash, TrendUp, TrendDown } from "@phosphor-icons/react";
import { toast } from "sonner";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("es-ES", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function ActionBadge({ action }) {
  if (action === "COMPRA") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-700 border border-green-200">
        <TrendUp size={12} weight="bold" /> COMPRA
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700 border border-red-200">
      <TrendDown size={12} weight="bold" /> VENTA
    </span>
  );
}

function RiesgoBadge({ riesgo }) {
  const map = { BAJO: "bg-green-100 text-green-700 border-green-200", MEDIO: "bg-yellow-100 text-yellow-700 border-yellow-200", ALTO: "bg-red-100 text-red-700 border-red-200" };
  const cls = map[riesgo] || "bg-gray-100 text-gray-600 border-gray-200";
  if (!riesgo) return null;
  return <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-semibold border ${cls}`}>{riesgo}</span>;
}

export default function AlertHistoryView() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/alerts/history?limit=100`);
      if (!res.ok) throw new Error("Error " + res.status);
      const data = await res.json();
      setHistory(data);
    } catch (e) {
      toast.error("Error al cargar historial: " + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  const clearHistory = async () => {
    if (!window.confirm("¿Borrar todo el historial de alertas?")) return;
    try {
      await fetch(`${API}/api/alerts/history`, { method: "DELETE" });
      setHistory([]);
      toast.success("Historial borrado");
    } catch {
      toast.error("Error al borrar historial");
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#1a3a32] flex items-center justify-center">
            <Bell size={20} className="text-[#f5f3ef]" weight="bold" />
          </div>
          <div>
            <h2 className="font-heading font-bold text-xl text-[#0e1f1a]">Historial de Alertas</h2>
            <p className="text-xs text-[#5c6b66] mt-0.5">Registro de todas las alertas disparadas por el sistema</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadHistory}
            className="flex items-center gap-2 px-4 py-2 rounded-md border border-[#e5e0d8] bg-white text-[#0e1f1a] text-sm font-mono hover:bg-[#f5f3ef] transition-colors"
          >
            <ArrowsClockwise size={15} weight="bold" className={loading ? "animate-spin" : ""} />
            Actualizar
          </button>
          {history.length > 0 && (
            <button
              onClick={clearHistory}
              className="flex items-center gap-2 px-4 py-2 rounded-md border border-red-200 bg-white text-red-600 text-sm font-mono hover:bg-red-50 transition-colors"
            >
              <Trash size={15} weight="bold" />
              Borrar todo
            </button>
          )}
        </div>
      </div>

      {/* Stats summary */}
      {history.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Total alertas", value: history.length, color: "text-[#0e1f1a]" },
            { label: "Alertas compra", value: history.filter((h) => h.action === "COMPRA").length, color: "text-green-600" },
            { label: "Alertas venta", value: history.filter((h) => h.action === "VENTA").length, color: "text-red-600" },
            { label: "Acciones distintas", value: new Set(history.map((h) => h.symbol)).size, color: "text-[#1a3a32]" },
          ].map((s) => (
            <div key={s.label} className="card-flat p-4">
              <p className={`text-2xl font-heading font-bold ${s.color}`}>{s.value}</p>
              <p className="text-xs text-[#5c6b66] mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Table (desktop) */}
      {loading && history.length === 0 ? (
        <div className="card-flat p-12 text-center text-[#5c6b66]">Cargando historial...</div>
      ) : history.length === 0 ? (
        <div className="card-flat p-12 text-center">
          <Bell size={40} className="mx-auto text-[#c5bfb4] mb-3" />
          <p className="text-[#5c6b66] font-mono text-sm">No hay alertas disparadas todavía.</p>
          <p className="text-xs text-[#5c6b66] mt-1">Las alertas aparecerán aquí cuando el precio toque un nivel configurado.</p>
        </div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="card-flat overflow-x-auto hidden sm:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#e5e0d8] text-[#5c6b66] text-xs font-mono">
                  <th className="px-4 py-3 text-left">Fecha</th>
                  <th className="px-4 py-3 text-left">Acción</th>
                  <th className="px-4 py-3 text-left">Símbolo</th>
                  <th className="px-4 py-3 text-left">Nombre</th>
                  <th className="px-4 py-3 text-left">Mercado</th>
                  <th className="px-4 py-3 text-left">Riesgo</th>
                  <th className="px-4 py-3 text-right">Precio</th>
                  <th className="px-4 py-3 text-right">Objetivo</th>
                  <th className="px-4 py-3 text-right">Diferencia</th>
                  <th className="px-4 py-3 text-right">Ganancia est.</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id} className="border-b border-[#f0ece4] hover:bg-[#f9f7f3] transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-[#5c6b66] whitespace-nowrap">{fmtDate(h.fired_at)}</td>
                    <td className="px-4 py-3"><ActionBadge action={h.action} /></td>
                    <td className="px-4 py-3 font-mono font-semibold text-[#1a3a32]">{h.symbol}</td>
                    <td className="px-4 py-3 text-[#0e1f1a] text-sm">{h.name || "—"}</td>
                    <td className="px-4 py-3 text-xs font-mono text-[#5c6b66]">{h.mercado || "—"}</td>
                    <td className="px-4 py-3"><RiesgoBadge riesgo={h.riesgo} /></td>
                    <td className="px-4 py-3 text-right font-mono font-semibold text-[#0e1f1a]">
                      ${h.price != null ? Number(h.price).toFixed(2) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-[#5c6b66]">
                      ${h.target != null ? Number(h.target).toFixed(2) : "—"}
                    </td>
                    <td className={`px-4 py-3 text-right font-mono font-semibold ${h.diff_pct >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {h.diff_pct != null ? `${h.diff_pct > 0 ? "+" : ""}${Number(h.diff_pct).toFixed(2)}%` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-green-600">
                      {h.posibles_ganancias != null ? `+${Number(h.posibles_ganancias).toFixed(2)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="sm:hidden space-y-3">
            {history.map((h) => (
              <div key={h.id} className="card-flat p-4 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono font-bold text-[#1a3a32]">{h.symbol}</span>
                      <ActionBadge action={h.action} />
                      <RiesgoBadge riesgo={h.riesgo} />
                    </div>
                    <p className="text-xs text-[#5c6b66]">{h.name}</p>
                  </div>
                  <p className="text-[10px] font-mono text-[#5c6b66] whitespace-nowrap">{fmtDate(h.fired_at)}</p>
                </div>
                <div className="grid grid-cols-3 gap-3 text-center border-t border-[#f0ece4] pt-3">
                  <div>
                    <p className="text-[10px] text-[#5c6b66]">Precio</p>
                    <p className="font-mono font-semibold text-sm">${h.price != null ? Number(h.price).toFixed(2) : "—"}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-[#5c6b66]">Objetivo</p>
                    <p className="font-mono text-sm text-[#5c6b66]">${h.target != null ? Number(h.target).toFixed(2) : "—"}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-[#5c6b66]">Diferencia</p>
                    <p className={`font-mono font-semibold text-sm ${h.diff_pct >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {h.diff_pct != null ? `${h.diff_pct > 0 ? "+" : ""}${Number(h.diff_pct).toFixed(2)}%` : "—"}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
