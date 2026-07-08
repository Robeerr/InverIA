import React, { useEffect, useState, useCallback } from "react";
import { ChartLineUp, ArrowClockwise, CheckCircle, XCircle, Clock } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Auto-examen honesto del sistema: ¿funcionaron las señales de COMPRA del motor?
// Lee /track-record (evalúa qué hizo el precio tras cada análisis) y lo muestra sin
// adornos: aciertos, fallos, abiertas, % de acierto y retorno medio.

const RES = {
  tp1: { c: "#4a7c59", label: "Acierto", Icon: CheckCircle },
  stop: { c: "#d85c41", label: "Fallo", Icon: XCircle },
  abierta: { c: "#c9a14a", label: "Abierta", Icon: Clock },
};

function Stat({ label, value, sub, color }) {
  return (
    <div className="card-flat p-4 text-center">
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-1">{label}</p>
      <p className="text-2xl font-bold font-mono" style={{ color: color || "#0e1f1a" }}>{value}</p>
      {sub && <p className="text-[10px] text-[#5c6b66] mt-0.5">{sub}</p>}
    </div>
  );
}

export default function TrackRecordView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(180);

  const load = useCallback(async (d) => {
    setLoading(true);
    try { setData(await api.trackRecord(d)); }
    catch (e) { toast.error("No se pudo cargar el track record"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(days); }, [load, days]);

  const s = data || {};
  const señales = s["señales"] || s.senales || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <ChartLineUp size={22} weight="bold" className="text-[#1a3a32] shrink-0" />
          <div className="min-w-0">
            <h1 className="font-heading font-bold text-lg text-[#0e1f1a] leading-tight">Track record del sistema</h1>
            <p className="text-[11px] text-[#5c6b66]">¿Funcionan las señales de COMPRA del motor? Sin autoengaño.</p>
          </div>
        </div>
        <button onClick={() => load(days)} className="shrink-0 p-2 rounded-md border border-[#e5e0d8] text-[#1a3a32]" title="Recargar">
          <ArrowClockwise size={16} weight="bold" className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Selector de periodo */}
      <div className="flex gap-1.5">
        {[90, 180, 365].map((d) => (
          <button key={d} onClick={() => setDays(d)}
            className={`px-3 py-1 rounded-full text-xs font-semibold border transition-colors ${
              days === d ? "bg-[#1a3a32] text-white border-[#1a3a32]" : "border-[#e5e0d8] text-[#5c6b66]"}`}>
            {d === 365 ? "1 año" : `${d} días`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="card-flat p-8 text-center text-[#5c6b66] text-sm">Evaluando señales…</div>
      ) : s.total === 0 ? (
        <div className="card-flat p-8 text-center">
          <p className="text-sm text-[#0e1f1a] font-semibold mb-1">Aún no hay señales que evaluar</p>
          <p className="text-xs text-[#5c6b66]">Cuando el motor genere análisis de COMPRA y pase algún tiempo, aparecerán aquí con su resultado real.</p>
        </div>
      ) : (
        <>
          {/* Resumen */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            <Stat label="% Acierto" value={s.win_rate != null ? `${s.win_rate}%` : "—"}
              sub={`${s.aciertos}✓ / ${s.fallos}✗`}
              color={s.win_rate == null ? "#5c6b66" : s.win_rate >= 55 ? "#4a7c59" : s.win_rate >= 45 ? "#c9a14a" : "#d85c41"} />
            <Stat label="Retorno medio" value={s.retorno_medio != null ? `${s.retorno_medio > 0 ? "+" : ""}${s.retorno_medio}%` : "—"}
              color={(s.retorno_medio || 0) > 0 ? "#4a7c59" : (s.retorno_medio || 0) < 0 ? "#d85c41" : "#5c6b66"} />
            <Stat label="Señales" value={s.total} sub={`últimos ${s.dias || days} días`} />
            <Stat label="Abiertas" value={s.abiertas} sub="aún en curso" color="#c9a14a" />
          </div>

          {/* Nota honesta */}
          <p className="text-[11px] text-[#5c6b66] leading-relaxed px-1">
            Acierto = el precio tocó el <b>take-profit</b> antes que el stop. Fallo = tocó el <b>stop</b> antes.
            El stop se cuenta primero (criterio conservador). Las <b>abiertas</b> aún no han tocado ninguno.
          </p>

          {/* Detalle */}
          <div className="space-y-1.5">
            {señales.map((r, i) => {
              const meta = RES[r.resultado] || RES.abierta;
              return (
                <div key={i} className="card-flat px-4 py-2.5 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <meta.Icon size={18} weight="fill" style={{ color: meta.c }} className="shrink-0" />
                    <div className="min-w-0">
                      <p className="font-mono font-bold text-sm text-[#0e1f1a]">{r.symbol}</p>
                      <p className="text-[10px] text-[#5c6b66]">{r.fecha} · entrada ${r.entrada}</p>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="text-[10px] font-semibold" style={{ color: meta.c }}>{meta.label}</span>
                    {r.retorno != null && (
                      <p className="text-sm font-mono font-semibold"
                        style={{ color: r.retorno > 0 ? "#4a7c59" : r.retorno < 0 ? "#d85c41" : "#5c6b66" }}>
                        {r.retorno > 0 ? "+" : ""}{r.retorno}%
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
