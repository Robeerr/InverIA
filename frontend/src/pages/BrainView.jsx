import React, { useEffect, useState, useCallback } from "react";
import { Brain, ArrowClockwise, TelegramLogo, Envelope, CaretDown } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Apartado "Cerebro": ventana a lo que sabe y a lo que va capturando en tiempo real
// (Telegram + newsletters). Feed de actividad + conocimiento acumulado por categoría.

function fmtFecha(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("es-ES", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { return iso.slice(0, 16).replace("T", " "); }
}

function Stat({ label, value, color }) {
  return (
    <div className="card-flat p-4 text-center">
      <p className="text-2xl font-bold font-mono" style={{ color: color || "#0e1f1a" }}>{value}</p>
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mt-1">{label}</p>
    </div>
  );
}

function Principio({ p }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card-flat px-4 py-2.5">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-start justify-between gap-2 text-left">
        <div className="min-w-0">
          <span className="text-[9px] uppercase tracking-wider font-mono text-[#1a3a32] bg-[#e8efe9] px-1.5 py-0.5 rounded">{p.categoria}</span>
          <p className="text-sm text-[#0e1f1a] leading-snug mt-1">{p.principio}</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {p.refuerzos > 1 && <span className="text-[10px] font-mono font-bold text-[#4a7c59]">×{p.refuerzos}</span>}
          {p.detalle && <CaretDown size={13} className={`text-[#5c6b66] transition-transform ${open ? "rotate-180" : ""}`} />}
        </div>
      </button>
      {open && p.detalle && <p className="text-[12px] text-[#5c6b66] leading-relaxed mt-2">{p.detalle}</p>}
      {open && p.fuentes?.length > 0 && (
        <p className="text-[10px] text-[#8a958f] mt-1.5 truncate">Fuentes: {p.fuentes.join(" · ")}</p>
      )}
    </div>
  );
}

export default function BrainView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("actividad");
  const [cat, setCat] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await api.brain()); }
    catch (e) { toast.error("No se pudo cargar el cerebro"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const d = data || {};
  const actividad = d.actividad || [];
  const top = d.top || [];
  const fuentes = d.fuentes || [];
  const cats = d.por_categoria || {};
  const totalCapturas = fuentes.reduce((a, f) => a + (f.capturas || 0), 0);
  const filtered = cat ? top.filter((p) => p.categoria === cat) : top;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Brain size={24} weight="fill" className="text-[#1a3a32] shrink-0" />
          <div className="min-w-0">
            <h1 className="font-heading font-bold text-lg text-[#0e1f1a] leading-tight">Cerebro</h1>
            <p className="text-[11px] text-[#5c6b66]">Lo que InverIA aprende de tus fuentes (Telegram + newsletters).</p>
          </div>
        </div>
        <button onClick={load} className="shrink-0 p-2 rounded-md border border-[#e5e0d8] text-[#1a3a32]" title="Recargar">
          <ArrowClockwise size={16} weight="bold" className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2.5">
        <Stat label="Principios" value={d.principios ?? "—"} color="#1a3a32" />
        <Stat label="Capturas" value={totalCapturas} color="#4a7c59" />
        <Stat label="Fuentes" value={fuentes.length} color="#2563eb" />
      </div>

      <div className="flex gap-1.5">
        {[["actividad", "Actividad"], ["conocimiento", "Conocimiento"], ["fuentes", "Fuentes"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-3 py-1 rounded-full text-xs font-semibold border ${tab === k ? "bg-[#1a3a32] text-white border-[#1a3a32]" : "border-[#e5e0d8] text-[#5c6b66]"}`}>
            {l}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="card-flat p-8 text-center text-[#5c6b66] text-sm">Cargando…</div>
      ) : tab === "actividad" ? (
        <div className="space-y-1.5">
          <p className="text-[11px] text-[#5c6b66] px-1">Cada mensaje/audio/foto que capta, en orden. Lo que aporta método suma principios; el ruido pasa sin añadir nada.</p>
          {actividad.length === 0 && <div className="card-flat p-6 text-center text-xs text-[#5c6b66]">Aún no ha capturado nada. Cuando llegue algo a tus fuentes, aparecerá aquí.</div>}
          {actividad.map((a, i) => (
            <div key={i} className="card-flat px-4 py-2.5 flex items-start gap-2.5">
              {a.tipo === "telegram"
                ? <TelegramLogo size={16} weight="fill" className="text-[#229ED9] shrink-0 mt-0.5" />
                : <Envelope size={16} weight="fill" className="text-[#c9a14a] shrink-0 mt-0.5" />}
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[11px] font-semibold text-[#1a3a32] truncate">{a.fuente}</p>
                  <span className="text-[9px] text-[#8a958f] shrink-0 font-mono">{fmtFecha(a.at)}</span>
                </div>
                <p className="text-[12px] text-[#5c6b66] leading-snug line-clamp-2 mt-0.5">{a.snippet || "(sin texto)"}</p>
              </div>
              {a.aprendidos > 0 && (
                <span className="shrink-0 text-[10px] font-bold text-[#4a7c59] bg-[#4a7c5915] px-1.5 py-0.5 rounded-full">+{a.aprendidos}</span>
              )}
            </div>
          ))}
        </div>
      ) : tab === "conocimiento" ? (
        <div className="space-y-2">
          <div className="flex gap-1.5 flex-wrap">
            <button onClick={() => setCat(null)} className={`px-2.5 py-1 rounded-full text-[11px] border ${!cat ? "bg-[#1a3a32] text-white border-[#1a3a32]" : "border-[#e5e0d8] text-[#5c6b66]"}`}>Todo</button>
            {Object.entries(cats).map(([c, n]) => (
              <button key={c} onClick={() => setCat(c)} className={`px-2.5 py-1 rounded-full text-[11px] border ${cat === c ? "bg-[#1a3a32] text-white border-[#1a3a32]" : "border-[#e5e0d8] text-[#5c6b66]"}`}>{c} · {n}</button>
            ))}
          </div>
          <div className="space-y-1.5">
            {filtered.map((p, i) => <Principio key={i} p={p} />)}
            {filtered.length === 0 && <div className="card-flat p-6 text-center text-xs text-[#5c6b66]">Sin principios todavía.</div>}
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          <p className="text-[11px] text-[#5c6b66] px-1">De dónde viene el conocimiento y cuánto aporta cada fuente.</p>
          {fuentes.map((f, i) => (
            <div key={i} className="card-flat px-4 py-2.5 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm text-[#0e1f1a] truncate">{f.fuente}</p>
                <p className="text-[10px] text-[#5c6b66]">Última: {fmtFecha(f.ultima)}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm font-mono font-semibold text-[#4a7c59]">+{f.aprendidos}</p>
                <p className="text-[10px] text-[#5c6b66]">{f.capturas} capturas</p>
              </div>
            </div>
          ))}
          {fuentes.length === 0 && <div className="card-flat p-6 text-center text-xs text-[#5c6b66]">Sin fuentes activas todavía.</div>}
        </div>
      )}
    </div>
  );
}
