import React, { useEffect, useState, useCallback } from "react";
import { Radar, ArrowClockwise, Newspaper, ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Color del veredicto del motor sobre cada acción.
function verdictStyle(inv) {
  const v = inv?.verdict || "";
  if (v.startsWith("🟢")) return { c: "#4a7c59", label: v };
  if (v.startsWith("🔴")) return { c: "#d85c41", label: v };
  if (v.startsWith("🟡")) return { c: "#c9a14a", label: v };
  if (v.startsWith("🟠")) return { c: "#c9843a", label: v };
  return null;
}

function StockCard({ row, onPick }) {
  const vs = verdictStyle(row.inveria);
  return (
    <div
      onClick={() => onPick(row.ticker)}
      className="card-flat p-4 cursor-pointer card-hover hover:shadow-md transition-all"
      data-testid={`radar-stock-${row.ticker}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <p className="font-mono font-bold text-base text-[#0e1f1a]">{row.ticker}</p>
          {row.nombre && <p className="text-[10px] text-[#5c6b66] truncate max-w-[160px]">{row.nombre}</p>}
        </div>
        <span
          className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold shrink-0"
          style={{ background: "#1a3a3214", color: "#1a3a32", border: "1px solid #1a3a3240" }}
          title="Número de newsletters distintas que la mencionan"
        >
          {row.n_fuentes} {row.n_fuentes === 1 ? "fuente" : "fuentes"}
        </span>
      </div>

      {vs && (
        <p className="text-[10px] font-mono mb-2" style={{ color: vs.c }}>
          {vs.label}{row.inveria?.score != null ? ` · score ${row.inveria.score}` : ""}
        </p>
      )}

      {row.angulos?.length > 0 && (
        <ul className="space-y-1 mb-2">
          {row.angulos.slice(0, 2).map((a, i) => (
            <li key={i} className="text-[11px] text-[#5c6b66] leading-snug">• {a}</li>
          ))}
        </ul>
      )}

      <div className="flex items-center justify-between text-[10px] text-[#5c6b66]">
        <span>{row.menciones} menci{row.menciones === 1 ? "ón" : "ones"}</span>
        <span className="flex items-center gap-1 text-[#1a3a32] font-mono">Analizar <ArrowRight size={10} weight="bold" /></span>
      </div>
    </div>
  );
}

export default function RadarView({ setSymbol }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("acciones");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.radar(14));
    } catch (e) {
      toast.error("No se pudo cargar el Radar");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const pick = (sym) => { setSymbol?.(sym); window.location.hash = ""; };

  const acciones = data?.acciones || [];
  const info = data?.informacion || [];

  return (
    <div className="space-y-4">
      <section className="card-flat p-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Radar size={22} weight="fill" className="text-[#1a3a32]" />
              <h2 className="font-heading font-bold text-2xl text-[#0e1f1a]">Radar</h2>
            </div>
            <p className="text-sm text-[#5c6b66]">
              Toda la inteligencia de tus {data?.total_newsletters ?? 0} newsletters recibidas
              (últimos 14 días), contrastada con tu motor.
            </p>
          </div>
          <button onClick={load} disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 text-sm hover:bg-neutral-50 transition-colors disabled:opacity-50">
            <ArrowClockwise size={14} className={loading ? "animate-spin" : ""} /> Refrescar
          </button>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 mt-4 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg p-1 w-fit">
          <button onClick={() => setTab("acciones")}
            className={`px-4 py-2 rounded-md text-sm font-medium ${tab === "acciones" ? "bg-[#1a3a32] text-white" : "text-[#5c6b66]"}`}>
            📈 Acciones ({acciones.length})
          </button>
          <button onClick={() => setTab("info")}
            className={`px-4 py-2 rounded-md text-sm font-medium ${tab === "info" ? "bg-[#1a3a32] text-white" : "text-[#5c6b66]"}`}>
            📰 Información ({info.length})
          </button>
        </div>
      </section>

      {loading ? (
        <div className="card-flat p-8 text-center text-[#5c6b66]">Cargando el Radar…</div>
      ) : tab === "acciones" ? (
        acciones.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {acciones.map((r) => <StockCard key={r.ticker} row={r} onPick={pick} />)}
          </div>
        ) : (
          <div className="card-flat p-8 text-center text-[#5c6b66]">
            Aún no hay acciones recopiladas. Llegarán a medida que se procesen tus newsletters.
          </div>
        )
      ) : (
        info.length > 0 ? (
          <div className="space-y-3">
            {info.map((it, i) => (
              <div key={i} className="card-flat p-4">
                <div className="flex items-center gap-2 mb-1">
                  <Newspaper size={14} className="text-[#1a3a32]" />
                  <p className="font-semibold text-sm text-[#0e1f1a]">{it.titulo}</p>
                </div>
                <p className="text-[13px] text-[#0e1f1a] leading-relaxed">{it.resumen}</p>
                <p className="text-[10px] text-[#5c6b66] mt-2 font-mono uppercase tracking-wider">{it.fuente}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="card-flat p-8 text-center text-[#5c6b66]">Sin información acumulada todavía.</div>
        )
      )}
    </div>
  );
}
