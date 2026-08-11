import React from "react";

/**
 * Contexto de mercado: futuros, miedo/codicia y mapa sectorial.
 *
 * Estaban definidos dentro de `Dashboard.jsx` y abrían la página de UNA acción, aunque
 * los tres son idénticos para las quinientas: no dicen nada del ticker que estás
 * mirando. Salen de ahí y se montan en «Hoy», que es la pantalla que sí trata del
 * mercado. No se pierde ninguno.
 *
 * El cuarto —el régimen— NO está aquí: es el único que cambia cómo se lee una acción
 * concreta, porque el motor de niveles ajusta sus pesos con él, así que viaja dentro
 * de `EstadoTecnico` como una cláusula más.
 *
 * Se mueven TAL CUAL, con los colores en línea que ya tenían. Armonizarlos con los
 * tokens del sistema es trabajo de la pasada de UX, no de esta reestructuración: un
 * cambio de sitio y un cambio de aspecto en el mismo commit son imposibles de revisar
 * por separado.
 */

export function MarketFuturesBar({ futures }) {
  if (!futures?.items?.length) return null;
  return (
    <div className="card-flat px-4 py-2.5 flex items-center gap-x-5 gap-y-1 flex-wrap">
      <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono">Futuros · apertura</span>
      {futures.items.map((f) => {
        const up = (f.change_percent ?? 0) >= 0;
        return (
          <div key={f.symbol} className="flex items-center gap-2">
            <span className="text-xs text-[#0e1f1a] font-medium">{f.label}</span>
            <span className={`font-mono text-xs font-semibold ${up ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
              {f.change_percent != null ? `${up ? "+" : ""}${f.change_percent}%` : "—"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// Termómetro Miedo/Codicia del mercado: 0 = pánico, 100 = euforia.
export function FearGreedBar({ data }) {
  if (!data || data.score == null) return null;
  const s = data.score;
  const color = s < 25 ? "#d85c41" : s < 45 ? "#e08a3c" : s <= 55 ? "#c9a14a" : "#4a7c59";
  return (
    <div className="card-flat px-4 py-2.5 flex items-center gap-3 flex-wrap">
      <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono shrink-0">Miedo / Codicia</span>
      <div className="flex items-center gap-2 min-w-[140px] flex-1">
        <div className="relative h-2 rounded-full flex-1 overflow-hidden" style={{ background: "linear-gradient(90deg,#d85c41,#c9a14a,#4a7c59)" }}>
          <div className="absolute top-1/2 -translate-y-1/2 w-1 h-3.5 bg-[#0e1f1a] rounded-full" style={{ left: `calc(${s}% - 2px)` }} />
        </div>
        <span className="font-mono font-bold text-sm shrink-0" style={{ color }}>{s}</span>
      </div>
      <span className="text-xs font-semibold shrink-0" style={{ color }}>{data.label}</span>
      {data.vix != null && <span className="text-[11px] text-[#5c6b66] font-mono shrink-0">VIX {data.vix}</span>}
      {data.advice && <span className="text-[11px] text-[#5c6b66] w-full sm:w-auto sm:ml-auto sm:max-w-[380px] leading-snug">{data.advice}</span>}
    </div>
  );
}

// Heatmap de sectores: variación del día por sector, para leer el mercado de un vistazo.
export function SectorHeatmap({ data, onPick }) {
  const sectors = data?.sectors;
  if (!Array.isArray(sectors) || !sectors.length) return null;
  const tone = (chg) => {
    const v = Math.max(-3, Math.min(3, chg)) / 3;  // normaliza a ±3%
    if (v >= 0) return `rgba(74,124,89,${0.12 + v * 0.55})`;   // verde
    return `rgba(216,92,65,${0.12 + Math.abs(v) * 0.55})`;      // rojo
  };
  return (
    <div className="card-flat px-4 py-3">
      <p className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono mb-2">Sectores hoy</p>
      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-1.5">
        {sectors.map((s) => (
          <button
            key={s.symbol}
            onClick={() => onPick && onPick(s.symbol)}
            title={`${s.sector} (${s.symbol})`}
            className="rounded-md px-2 py-1.5 text-left transition-transform hover:scale-[1.03]"
            style={{ background: tone(s.change_percent) }}
          >
            <div className="text-[11px] font-semibold text-[#0e1f1a] truncate leading-tight">{s.sector}</div>
            <div className="text-[12px] font-mono font-bold text-[#0e1f1a]">
              {s.change_percent >= 0 ? "+" : ""}{s.change_percent.toFixed(2)}%
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
