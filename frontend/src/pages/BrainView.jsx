import React, { useEffect, useState, useCallback } from "react";
import { Brain, ArrowClockwise, TelegramLogo, Envelope, CaretDown, YoutubeLogo } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";

function YouTubeBox({ onDone }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [manual, setManual] = useState(false);
  const [texto, setTexto] = useState("");
  const [fuente, setFuente] = useState("");

  const go = async () => {
    if (!url.trim()) return;
    setBusy(true); setRes(null);
    try {
      const r = await api.youtubeIngest(url.trim());
      setRes(r);
      if (r.ok) { toast.success("Vídeo procesado"); onDone?.(); }
      else toast.error(r.error || "No se pudo procesar");
    } catch (e) { toast.error("Error procesando el vídeo"); }
    finally { setBusy(false); }
  };

  const goText = async () => {
    if (texto.trim().length < 60) return toast.error("Pega un texto más largo");
    setBusy(true); setRes(null);
    try {
      const r = await api.ingestText(texto.trim(), fuente.trim() || "Texto pegado");
      setRes(r);
      if (r.ok) { toast.success("Texto procesado"); setTexto(""); onDone?.(); }
    } catch (e) { toast.error("Error procesando el texto"); }
    finally { setBusy(false); }
  };

  return (
    <div className="iv-panel p-4">
      <div className="flex items-center gap-2 mb-2">
        <YoutubeLogo size={18} weight="fill" className="text-[#FF0000]" />
        <p className="text-sm font-semibold text-tinta">Añadir vídeo de YouTube</p>
      </div>
      <div className="flex gap-2">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://youtu.be/..."
          className="flex-1 px-3 py-2 rounded-iv border border-linea bg-superficie text-tinta text-sm min-w-0" />
        <button onClick={go} disabled={busy} className="px-4 py-2 rounded-iv bg-marca text-marca-tinta text-sm font-semibold disabled:opacity-50 shrink-0">
          {busy ? "Procesando…" : "Procesar"}
        </button>
      </div>
      {busy && <p className="text-etiqueta text-tinta-3 mt-2">Procesando y extrayendo ideas…</p>}

      <button onClick={() => setManual((v) => !v)} className="text-etiqueta text-tinta-3 underline mt-2">
        {manual ? "Ocultar" : "¿Falla? Pega la transcripción / texto a mano"}
      </button>
      {manual && (
        <div className="mt-2 space-y-2">
          <input value={fuente} onChange={(e) => setFuente(e.target.value)} placeholder="Fuente (ej. Vídeo JaviZone) — opcional"
            className="w-full px-3 py-2 rounded-iv border border-linea bg-superficie text-tinta text-sm" />
          <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={5} placeholder="Pega aquí la transcripción del vídeo, o cualquier texto (artículo, análisis)…"
            className="w-full px-3 py-2 rounded-iv border border-linea bg-superficie text-tinta text-sm" />
          <button onClick={goText} disabled={busy} className="w-full py-2 rounded-iv bg-marca text-marca-tinta text-sm font-semibold disabled:opacity-50">
            {busy ? "Procesando…" : "Procesar texto"}
          </button>
        </div>
      )}
      {res?.ok && (
        <div className="mt-3 border-l-2 border-sube pl-3 py-1">
          <p className="text-etiqueta font-semibold text-marca">Conseguido del vídeo (vía {res.via}):</p>
          {res.resumen && <p className="text-apoyo text-tinta leading-snug mt-1">{res.resumen}</p>}
          <div className="flex flex-wrap gap-1.5 mt-2 text-etiqueta">
            <span className="px-1.5 py-0.5 rounded-full bg-sube/8 text-sube font-semibold">{res.aprendidos} aprendizajes</span>
            <span className="px-1.5 py-0.5 rounded-full bg-info/8 text-info font-semibold">{res.acciones} picks</span>
            {(res.tickers || []).map((t) => (
              <span key={t} className="px-1.5 py-0.5 rounded-full bg-superficie-alt text-tinta-3 font-mono">{t}</span>
            ))}
          </div>
          {res.acciones === 0 && res.aprendidos === 0 && (
            <p className="text-etiqueta text-tinta-3 mt-1">Leyó el vídeo ({res.chars} caracteres) pero no encontró picks ni método reutilizable.</p>
          )}
        </div>
      )}
      {res && !res.ok && <p className="text-etiqueta text-baja mt-2">{res.error}</p>}
    </div>
  );
}

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
    <div className="iv-panel p-4 text-center">
      <p className="text-2xl font-bold font-mono" style={{ color: color || "rgb(var(--iv-tinta))" }}>{value}</p>
      <p className="text-etiqueta uppercase tracking-[0.15em] text-tinta-3 font-mono mt-1">{label}</p>
    </div>
  );
}

function ActivityItem({ a }) {
  const [open, setOpen] = useState(false);
  const principios = a.principios || [];
  const canOpen = principios.length > 0;
  return (
    <div className="iv-panel px-4 py-2.5">
      <button onClick={() => canOpen && setOpen((v) => !v)} className={`w-full flex items-start gap-2.5 text-left ${canOpen ? "cursor-pointer" : "cursor-default"}`}>
        {a.tipo === "telegram"
          ? <TelegramLogo size={16} weight="fill" className="text-[#229ED9] shrink-0 mt-0.5" />
          : <Envelope size={16} weight="fill" className="text-aviso shrink-0 mt-0.5" />}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-etiqueta font-semibold text-marca truncate">{a.fuente}</p>
            <span className="text-etiqueta text-tinta-3 shrink-0 font-mono">{fmtFecha(a.at)}</span>
          </div>
          <p className={`text-apoyo text-tinta-3 leading-snug mt-0.5 ${open ? "" : "line-clamp-2"}`}>{a.snippet || "(sin texto)"}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {a.aprendidos > 0 && (
            <span className="text-etiqueta font-bold text-sube bg-sube/8 px-1.5 py-0.5 rounded-full">+{a.aprendidos}</span>
          )}
          {canOpen && <CaretDown size={12} className={`text-tinta-3 transition-transform ${open ? "rotate-180" : ""}`} />}
        </div>
      </button>
      {open && (
        <div className="mt-2 pl-6 space-y-1.5 border-t border-linea pt-2">
          <p className="text-etiqueta uppercase tracking-wider text-tinta-3 font-mono">Aprendió:</p>
          {principios.map((p, i) => (
            <p key={i} className="text-apoyo text-tinta leading-snug flex gap-1.5">
              <span className="text-sube">•</span><span>{p}</span>
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function Principio({ p }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="iv-panel px-4 py-2.5">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-start justify-between gap-2 text-left">
        <div className="min-w-0">
          <span className="text-etiqueta uppercase tracking-wider font-mono text-marca bg-superficie-alt px-1.5 py-0.5 rounded">{p.categoria}</span>
          <p className="text-sm text-tinta leading-snug mt-1">{p.principio}</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {p.refuerzos > 1 && <span className="text-etiqueta font-mono font-bold text-sube">×{p.refuerzos}</span>}
          {p.detalle && <CaretDown size={13} className={`text-tinta-3 transition-transform ${open ? "rotate-180" : ""}`} />}
        </div>
      </button>
      {open && p.detalle && <p className="text-apoyo text-tinta-3 leading-relaxed mt-2">{p.detalle}</p>}
      {open && p.fuentes?.length > 0 && (
        <p className="text-etiqueta text-tinta-3 mt-1.5 truncate">Fuentes: {p.fuentes.join(" · ")}</p>
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
      <div className="iv-veredicto flex items-end justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <p className="iv-etiqueta tracking-[0.16em] text-tinta-3 mb-1">Entender</p>
          <h1 className="iv-verbo text-tinta">Cerebro</h1>
          <p className="text-cuerpo text-tinta-2 mt-3 max-w-[58ch]">
            Lo que InverIA aprende de tus fuentes. Lo que aporta método suma principios;
            el ruido pasa sin añadir nada.
          </p>
        </div>
        <button onClick={load} className="shrink-0 p-2 border border-linea text-tinta-2 hover:border-marca hover:text-marca transition-colors" title="Recargar">
          <ArrowClockwise size={16} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2.5">
        <Stat label="Principios" value={d.principios ?? "—"} color="rgb(var(--iv-marca))" />
        <Stat label="Capturas" value={totalCapturas} color="rgb(var(--iv-sube))" />
        <Stat label="Fuentes" value={fuentes.length} color="rgb(var(--iv-info))" />
      </div>

      {/* Cuatro pestañas. «Añadir» era antes un bloque fijo sobre el contenido: una
          caja de formulario que se veía en cada visita para una acción que se hace de
          vez en cuando, y que empujaba hacia abajo lo que sí se viene a leer. */}
      <div className="iv-seccion iv-seccion-acento">
        <span className="iv-etiqueta tracking-[0.18em] text-tinta-2">
          {{actividad: "Actividad", conocimiento: "Conocimiento",
            fuentes: "Fuentes", anadir: "Añadir al cerebro"}[tab]}
        </span>
      </div>

      <div className="flex gap-1.5 flex-wrap">
        {[["actividad", "Actividad"], ["conocimiento", "Conocimiento"],
          ["fuentes", "Fuentes"], ["anadir", "Añadir"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
            aria-pressed={tab === k}
            className={`px-3 py-1.5 text-etiqueta border transition-colors ${
              tab === k ? "bg-marca text-marca-tinta border-marca"
                        : "border-linea text-tinta-3 hover:border-linea-fuerte hover:text-tinta"}`}>
            {l}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="iv-panel p-8 text-center text-tinta-3 text-sm">Cargando…</div>
      ) : tab === "actividad" ? (
        <div className="space-y-1.5">
          <p className="text-etiqueta text-tinta-3 px-1">Cada mensaje/audio/foto que capta, en orden. Lo que aporta método suma principios; el ruido pasa sin añadir nada.</p>
          {actividad.length === 0 && <div className="iv-panel p-6 text-center text-xs text-tinta-3">Aún no ha capturado nada. Cuando llegue algo a tus fuentes, aparecerá aquí.</div>}
          {actividad.map((a, i) => <ActivityItem key={i} a={a} />)}
        </div>
      ) : tab === "conocimiento" ? (
        <div className="space-y-2">
          <div className="flex gap-1.5 flex-wrap">
            <button onClick={() => setCat(null)} className={`px-2.5 py-1 text-etiqueta border ${!cat ? "bg-marca text-marca-tinta border-marca" : "border-linea text-tinta-3"}`}>Todo</button>
            {Object.entries(cats).map(([c, n]) => (
              <button key={c} onClick={() => setCat(c)} className={`px-2.5 py-1 text-etiqueta border ${cat === c ? "bg-marca text-marca-tinta border-marca" : "border-linea text-tinta-3"}`}>{c} · {n}</button>
            ))}
          </div>
          <div className="space-y-1.5">
            {filtered.map((p, i) => <Principio key={i} p={p} />)}
            {filtered.length === 0 && <div className="iv-panel p-6 text-center text-xs text-tinta-3">Sin principios todavía.</div>}
          </div>
        </div>
      ) : tab === "anadir" ? (
        <div className="space-y-2">
          <p className="text-apoyo text-tinta-2 max-w-[62ch]">
            Pega un vídeo de YouTube o un texto y el cerebro extrae los principios que
            contenga. Lo que no aporta método no suma nada: no es un archivo, es un filtro.
          </p>
          <YouTubeBox onDone={load} />
        </div>
      ) : (
        <div className="space-y-1.5">
          <p className="text-etiqueta text-tinta-3 px-1">De dónde viene el conocimiento y cuánto aporta cada fuente.</p>
          {fuentes.map((f, i) => (
            <div key={i} className="iv-panel px-4 py-2.5 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm text-tinta truncate">{f.fuente}</p>
                <p className="text-etiqueta text-tinta-3">Última: {fmtFecha(f.ultima)}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm font-mono font-semibold text-sube">+{f.aprendidos}</p>
                <p className="text-etiqueta text-tinta-3">{f.capturas} capturas</p>
              </div>
            </div>
          ))}
          {fuentes.length === 0 && <div className="iv-panel p-6 text-center text-xs text-tinta-3">Sin fuentes activas todavía.</div>}
        </div>
      )}
    </div>
  );
}
