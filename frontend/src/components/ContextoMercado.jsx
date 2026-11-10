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

/* Futuros y Miedo/Codicia ya no llevan caja propia: en «Hoy» van como filas dentro del
   mismo panel que la lectura del régimen (lo monta HoyView). Tres cajas apiladas para
   tres datos del mismo tema eran tres bordes que no separaban nada. */
export function MarketFuturesBar({ futures }) {
  if (!futures?.items?.length) return null;
  return (
    <div className="px-4 py-3 sm:px-5 flex items-center gap-x-5 gap-y-1.5 flex-wrap">
      <span className="iv-etiqueta">Futuros · apertura</span>
      {futures.items.map((f) => {
        const up = (f.change_percent ?? 0) >= 0;
        return (
          <div key={f.symbol} className="flex items-baseline gap-2">
            <span className="text-apoyo text-tinta-2">{f.label}</span>
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
  // La escala tiene CUATRO peldaños y la paleta semántica tenía tres colores, así que
  // el naranja intermedio estaba escrito a mano en #e08a3c. Colapsarlo en `aviso`
  // habría dejado los tramos 25-45 y 45-55 del mismo color, perdiendo un peldaño de
  // resolución; dejarlo a mano arrastraba un defecto real: 2,67:1 sobre el blanco de
  // claro, por debajo del 4,5:1 que necesita un texto. Ahora ese peldaño EXISTE como
  // token —`--iv-alerta`, 6,25:1 en claro y 6,75:1 en oscuro— y el termómetro conserva
  // sus cuatro tramos sin excepciones escritas a mano.
  const color = s < 25 ? "rgb(var(--iv-baja))" : s < 45 ? "rgb(var(--iv-alerta))"
    : s <= 55 ? "rgb(var(--iv-aviso))" : "rgb(var(--iv-sube))";
  return (
    <div className="px-4 py-3 sm:px-5 flex items-center gap-x-3 gap-y-1.5 flex-wrap">
      <span className="iv-etiqueta shrink-0">Miedo / Codicia</span>
      {/* La barra, más fina y atenuada: el dato es la cifra y su palabra, el degradado
          solo sitúa la aguja. A tope de saturación competía con las subidas y bajadas. */}
      <div className="flex items-center gap-2.5 min-w-[120px] flex-1">
        <div className="relative h-1.5 rounded-full flex-1 opacity-70" aria-hidden="true"
             style={{ background: "linear-gradient(90deg,rgb(var(--iv-baja)),rgb(var(--iv-aviso)),rgb(var(--iv-sube)))" }}>
          <div className="absolute top-1/2 -translate-y-1/2 w-[3px] h-3.5 bg-tinta rounded-full ring-2 ring-superficie"
               style={{ left: `calc(${s}% - 1.5px)` }} />
        </div>
        <span className="iv-cifra text-cuerpo font-bold shrink-0 tabular-nums" style={{ color }}>{s}</span>
        <span className="text-apoyo font-semibold shrink-0" style={{ color }}>{data.label}</span>
      </div>
      {data.vix != null && <span className="iv-cifra text-etiqueta text-tinta-3 shrink-0">VIX {data.vix}</span>}
      {data.advice && <p className="text-apoyo text-tinta-3 w-full leading-snug">{data.advice}</p>}
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
    // Techo de opacidad en 0,40 (antes 0,67): con el verde a tope, el texto claro de la
    // baldosa se quedaba en ~3,4:1, por debajo de AA. La intensidad sigue ordenando.
    if (v >= 0) return `rgb(var(--iv-sube) / ${0.08 + v * 0.32})`;
    return `rgb(var(--iv-baja) / ${0.08 + Math.abs(v) * 0.32})`;
  };
  // Sin `onPick` (así se monta en «Hoy») la baldosa no hace nada al pulsarla, así que
  // no es un botón: un botón que no responde promete una acción que no existe.
  const Baldosa = onPick ? "button" : "div";
  return (
    <section className="iv-panel px-4 py-4 sm:px-5" aria-labelledby="sectores-hoy">
      <h2 id="sectores-hoy" className="iv-etiqueta mb-3">Sectores hoy</h2>
      <div className="grid grid-cols-2 min-[420px]:grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-1.5">
        {sectors.map((s) => (
          <Baldosa
            key={s.symbol}
            {...(onPick ? { type: "button", onClick: () => onPick(s.symbol) } : {})}
            title={`${s.sector} (${s.symbol})`}
            className={`rounded-iv-sm px-2.5 py-2 text-left flex items-baseline justify-between gap-2 min-w-0${
              onPick ? " transition-[filter] duration-150 hover:brightness-125 motion-reduce:transition-none" : ""}`}
            style={{ background: tone(s.change_percent) }}
          >
            <span className="text-apoyo text-tinta truncate leading-tight min-w-0">{s.sector}</span>
            <span className="iv-cifra text-apoyo font-semibold text-tinta shrink-0">
              {s.change_percent >= 0 ? "+" : ""}{s.change_percent.toFixed(2)}%
            </span>
          </Baldosa>
        ))}
      </div>
    </section>
  );
}
