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
    <div className="iv-panel px-4 py-2.5 flex items-center gap-x-5 gap-y-1 flex-wrap">
      <span className="iv-etiqueta">Futuros · apertura</span>
      {futures.items.map((f) => {
        const up = (f.change_percent ?? 0) >= 0;
        return (
          <div key={f.symbol} className="flex items-center gap-2">
            <span className="text-apoyo text-tinta font-medium">{f.label}</span>
            <span className={`iv-cifra text-apoyo font-semibold ${up ? "text-sube" : "text-baja"}`}>
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
  // La escala tiene CUATRO peldaños y la paleta semántica solo tres colores, así que
  // el naranja intermedio se queda como está: colapsarlo en `aviso` dejaría los tramos
  // 25-45 y 45-55 del mismo color y el termómetro perdería un peldaño de resolución.
  // Es una excepción anotada, no un descuido — y arrastra un defecto PREEXISTENTE:
  // #e08a3c da 2,67:1 sobre el blanco de claro, por debajo del 4,5:1 que necesita un
  // texto. Se arregla con un token propio, que no toca crear en esta tanda.
  const color = s < 25 ? "rgb(var(--iv-baja))" : s < 45 ? "#e08a3c"
    : s <= 55 ? "rgb(var(--iv-aviso))" : "rgb(var(--iv-sube))";
  return (
    <div className="iv-panel px-4 py-2.5 flex items-center gap-3 flex-wrap">
      <span className="iv-etiqueta shrink-0">Miedo / Codicia</span>
      <div className="flex items-center gap-2 min-w-[140px] flex-1">
        <div className="relative h-2 rounded-full flex-1 overflow-hidden" style={{ background: "linear-gradient(90deg,rgb(var(--iv-baja)),rgb(var(--iv-aviso)),rgb(var(--iv-sube)))" }}>
          <div className="absolute top-1/2 -translate-y-1/2 w-1 h-3.5 bg-tinta rounded-full" style={{ left: `calc(${s}% - 2px)` }} />
        </div>
        <span className="iv-cifra text-cuerpo font-bold shrink-0" style={{ color }}>{s}</span>
      </div>
      <span className="text-apoyo font-semibold shrink-0" style={{ color }}>{data.label}</span>
      {data.vix != null && <span className="iv-cifra text-etiqueta text-tinta-3 shrink-0">VIX {data.vix}</span>}
      {data.advice && <span className="text-apoyo text-tinta-3 w-full sm:w-auto sm:ml-auto sm:max-w-[380px] leading-snug">{data.advice}</span>}
    </div>
  );
}

// Heatmap de sectores: variación del día por sector, para leer el mercado de un vistazo.
export function SectorHeatmap({ data, onPick }) {
  const sectors = data?.sectors;
  if (!Array.isArray(sectors) || !sectors.length) return null;
  const tone = (chg) => {
    const v = Math.max(-3, Math.min(3, chg)) / 3;  // normaliza a ±3%
    // Con `rgba()` y las cifras a pelo, el mapa de sectores se quedaba con los verdes
    // y rojos CLAROS también en oscuro: son colores en línea y el remapeo solo actúa
    // sobre clases. El resultado era texto casi blanco sobre una baldosa pastel.
    if (v >= 0) return `rgb(var(--iv-sube) / ${0.12 + v * 0.55})`;
    return `rgb(var(--iv-baja) / ${0.12 + Math.abs(v) * 0.55})`;
  };
  return (
    <div className="iv-panel px-4 py-3">
      <p className="iv-etiqueta mb-2">Sectores hoy</p>
      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-1.5">
        {sectors.map((s) => (
          <button
            key={s.symbol}
            onClick={() => onPick && onPick(s.symbol)}
            title={`${s.sector} (${s.symbol})`}
            className="rounded-md px-2 py-1.5 text-left transition-transform hover:scale-[1.03]"
            style={{ background: tone(s.change_percent) }}
          >
            <div className="text-apoyo font-semibold text-tinta truncate leading-tight">{s.sector}</div>
            <div className="iv-cifra text-apoyo font-bold text-tinta">
              {s.change_percent >= 0 ? "+" : ""}{s.change_percent.toFixed(2)}%
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
