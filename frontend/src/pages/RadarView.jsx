import React, { useEffect, useState, useCallback } from "react";
import { Target, ArrowClockwise, ArrowRight, CaretDown } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Color del veredicto del motor sobre cada acción.
function verdictStyle(inv) {
  const v = inv?.verdict || "";
  if (v.startsWith("🟢")) return { c: "#4a7c59", short: "Coincide" };
  if (v.startsWith("🔴")) return { c: "#d85c41", short: "Evítala" };
  if (v.startsWith("🟡")) return { c: "#c9a14a", short: "Neutral" };
  if (v.startsWith("🟠")) return { c: "#c9843a", short: "Floja" };
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
          {row.nombre && <p className="text-[10px] text-[#5c6b66] truncate max-w-[150px]">{row.nombre}</p>}
        </div>
        {vs && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0"
            style={{ background: `${vs.c}18`, color: vs.c, border: `1px solid ${vs.c}40` }}>
            {vs.short}{row.inveria?.score != null ? ` ${row.inveria.score}` : ""}
          </span>
        )}
      </div>

      {/* Cuántas fuentes lo mencionan = fuerza del consenso */}
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-[11px] font-semibold text-[#1a3a32]">
          {row.n_fuentes} {row.n_fuentes === 1 ? "fuente" : "fuentes"}
        </span>
        <span className="text-[10px] text-[#5c6b66] truncate">· {row.fuentes.join(", ")}</span>
      </div>
      {/* Sentimiento de las fuentes: hablan bien/mal de la empresa */}
      {(row.positivos > 0 || row.negativos > 0) && (
        <div className="flex items-center gap-2 mb-1.5 text-[10px] font-semibold">
          {row.positivos > 0 && <span className="text-[#4a7c59]">👍 {row.positivos} la ven bien</span>}
          {row.negativos > 0 && <span className="text-[#d85c41]">👎 {row.negativos} la ven mal</span>}
        </div>
      )}

      {row.angulos?.length > 0 && (
        <p className="text-[11px] text-[#5c6b66] leading-snug line-clamp-2">{row.angulos[0]}</p>
      )}

      <div className="flex items-center justify-end text-[10px] text-[#1a3a32] font-mono mt-2">
        Analizar <ArrowRight size={10} weight="bold" className="ml-1" />
      </div>
    </div>
  );
}

function InfoRow({ item }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card-flat px-4 py-3">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-start justify-between gap-3 text-left">
        <div className="min-w-0">
          <p className="font-semibold text-sm text-[#0e1f1a] leading-snug">{item.titulo}</p>
          {!open && <p className="text-[11px] text-[#5c6b66] mt-0.5 line-clamp-1">{item.resumen}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[9px] font-mono uppercase tracking-wider text-[#5c6b66] hidden sm:inline">{item.fuente}</span>
          <CaretDown size={14} className={`text-[#5c6b66] transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>
      {open && <p className="text-[13px] text-[#0e1f1a] leading-relaxed mt-2">{item.resumen}</p>}
    </div>
  );
}

export default function RadarView({ setSymbol }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("acciones");

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await api.radar(14)); }
    catch (e) { toast.error("No se pudo cargar el Radar"); }
    finally { setLoading(false); }
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
              <Target size={22} weight="fill" className="text-[#1a3a32]" />
              <h2 className="font-heading font-bold text-2xl text-[#0e1f1a]">Radar</h2>
            </div>
            <p className="text-sm text-[#5c6b66]">
              Las acciones que mencionan tus {data?.total_newsletters ?? 0} newsletters, ordenadas
              por consenso y contrastadas con tu motor.
            </p>
          </div>
          <button onClick={load} disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 text-sm hover:bg-neutral-50 transition-colors disabled:opacity-50">
            <ArrowClockwise size={14} className={loading ? "animate-spin" : ""} /> Refrescar
          </button>
        </div>

        <div className="flex items-center gap-1 mt-4 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg p-1 w-fit">
          <button onClick={() => setTab("acciones")}
            className={`px-4 py-2 rounded-md text-sm font-medium ${tab === "acciones" ? "bg-[#1a3a32] text-white" : "text-[#5c6b66]"}`}>
            📈 Acciones ({acciones.length})
          </button>
          <button onClick={() => setTab("info")}
            className={`px-4 py-2 rounded-md text-sm font-medium ${tab === "info" ? "bg-[#1a3a32] text-white" : "text-[#5c6b66]"}`}>
            📰 Titulares ({info.length})
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
          <div className="card-flat p-8 text-center">
            <p className="text-[#0e1f1a] font-medium mb-1">Aún no hay acciones recopiladas</p>
            <p className="text-sm text-[#5c6b66]">
              Aparecerán solas a medida que lleguen newsletters con tickers. Las recibidas antes de
              la última actualización no los tienen guardados.
            </p>
          </div>
        )
      ) : (
        info.length > 0 ? (
          <div className="space-y-2">
            {info.map((it, i) => <InfoRow key={i} item={it} />)}
          </div>
        ) : (
          <div className="card-flat p-8 text-center text-[#5c6b66]">Sin titulares acumulados todavía.</div>
        )
      )}
    </div>
  );
}
