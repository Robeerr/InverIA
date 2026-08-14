import React, { useEffect, useState, useCallback } from "react";
import { Target, ArrowClockwise, ArrowRight, CaretDown } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";
import Confluencia from "../components/Confluencia";

function StockCard({ row, onPick }) {
  return (
    <div
      onClick={() => onPick(row.ticker)}
      className="iv-panel p-4 cursor-pointer card-hover hover:shadow-md transition-all"
      data-testid={`radar-stock-${row.ticker}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <p className="font-mono font-bold text-base text-tinta">{row.ticker}</p>
          {row.nombre && <p className="text-etiqueta text-tinta-3 truncate max-w-[150px]">{row.nombre}</p>}
        </div>
      </div>

      {/* El cruce fuentes ↔ elegibilidad. Va arriba porque, retirado el chip de
          veredicto del motor, es lo único que cruza las dos opiniones: el resto de la
          tarjeta son datos de las fuentes por separado. */}
      <Confluencia confluencia={row.confluencia} compacto className="mb-1.5" />

      {/* Cuántas fuentes lo mencionan = fuerza del consenso */}
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-etiqueta font-semibold text-marca">
          {row.n_fuentes} {row.n_fuentes === 1 ? "fuente" : "fuentes"}
        </span>
        <span className="text-etiqueta text-tinta-3 truncate">· {row.fuentes.join(", ")}</span>
      </div>
      {/* Sentimiento de las fuentes: hablan bien/mal de la empresa */}
      {(row.positivos > 0 || row.negativos > 0) && (
        <div className="flex items-center gap-2 mb-1.5 text-etiqueta font-semibold">
          {row.positivos > 0 && <span className="text-sube">👍 {row.positivos} la ven bien</span>}
          {row.negativos > 0 && <span className="text-baja">👎 {row.negativos} la ven mal</span>}
        </div>
      )}

      {row.angulos?.length > 0 && (
        <p className="text-etiqueta text-tinta-3 leading-snug line-clamp-2">{row.angulos[0]}</p>
      )}

      <div className="flex items-center justify-end text-etiqueta text-marca font-mono mt-2">
        Analizar <ArrowRight size={10} weight="bold" className="ml-1" />
      </div>
    </div>
  );
}

function InfoRow({ item }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="iv-panel px-4 py-3">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-start justify-between gap-3 text-left">
        <div className="min-w-0">
          <p className="font-semibold text-sm text-tinta leading-snug">{item.titulo}</p>
          {!open && <p className="text-etiqueta text-tinta-3 mt-0.5 line-clamp-1">{item.resumen}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-etiqueta font-mono uppercase tracking-wider text-tinta-3 hidden sm:inline">{item.fuente}</span>
          <CaretDown size={14} className={`text-tinta-3 transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>
      {open && <p className="text-apoyo text-tinta leading-relaxed mt-2">{item.resumen}</p>}
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
      <section className="iv-panel p-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Target size={22} weight="fill" className="text-marca" />
              <h2 className="font-heading font-bold text-2xl text-tinta">Radar</h2>
            </div>
            <p className="text-sm text-tinta-3">
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
            className={`px-4 py-2 rounded-md text-sm font-medium ${tab === "acciones" ? "bg-marca text-marca-tinta" : "text-tinta-3"}`}>
            📈 Acciones ({acciones.length})
          </button>
          <button onClick={() => setTab("info")}
            className={`px-4 py-2 rounded-md text-sm font-medium ${tab === "info" ? "bg-marca text-marca-tinta" : "text-tinta-3"}`}>
            📰 Titulares ({info.length})
          </button>
        </div>
      </section>

      {loading ? (
        <div className="iv-panel p-8 text-center text-tinta-3">Cargando el Radar…</div>
      ) : tab === "acciones" ? (
        acciones.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {acciones.map((r) => <StockCard key={r.ticker} row={r} onPick={pick} />)}
          </div>
        ) : (
          <div className="iv-panel p-8 text-center">
            <p className="text-tinta font-medium mb-1">Aún no hay acciones recopiladas</p>
            <p className="text-sm text-tinta-3">
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
          <div className="iv-panel p-8 text-center text-tinta-3">Sin titulares acumulados todavía.</div>
        )
      )}
    </div>
  );
}
