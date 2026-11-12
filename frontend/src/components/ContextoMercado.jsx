import React from "react";
import { Activity, LayoutGrid, Thermometer } from "lucide-react";
import CabeceraBloque from "@/components/base/CabeceraBloque";

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
 */

/* Futuros y Miedo/Codicia no llevan caja propia: en «Hoy» son bloques dentro del mismo
   panel de mercado que la lectura del régimen (lo monta HoyView), separados por un
   filete. Tres cajas apiladas para tres datos del mismo tema eran tres bordes que no
   separaban nada. */
export function MarketFuturesBar({ futures }) {
  if (!futures?.items?.length) return null;
  return (
    <section className="p-5 sm:p-6" aria-label="Futuros a la apertura">
      <CabeceraBloque icono={Activity}
                      derecha={<span className="iv-etiqueta">a la apertura</span>}>
        Futuros
      </CabeceraBloque>
      {/* Una tabla de tres filas, sin cabecera: nombre a la izquierda, variación a la
          derecha en dígitos tabulares. Se leen en vertical de un vistazo. */}
      <ul className="mt-3">
        {futures.items.map((f) => {
          const up = (f.change_percent ?? 0) >= 0;
          return (
            <li key={f.symbol} className="flex items-baseline justify-between gap-3 py-1.5">
              <span className="text-[13.5px] text-tinta-2">{f.label}</span>
              <span className={`iv-cifra text-[13.5px] font-medium ${up ? "text-sube" : "text-baja"}`}>
                {f.change_percent != null ? `${up ? "+" : ""}${f.change_percent}%` : "—"}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// Termómetro Miedo/Codicia del mercado: 0 = pánico, 100 = euforia.
export function FearGreedBar({ data }) {
  if (!data || data.score == null) return null;
  const s = data.score;
  // La escala tiene CUATRO peldaños y la paleta semántica tenía tres colores, así que
  // el peldaño intermedio existe como token —`--iv-alerta`— y el termómetro conserva
  // sus cuatro tramos sin excepciones escritas a mano (todos ≥ 4,5:1 como texto).
  const color = s < 25 ? "rgb(var(--iv-baja))" : s < 45 ? "rgb(var(--iv-alerta))"
    : s <= 55 ? "rgb(var(--iv-aviso))" : "rgb(var(--iv-sube))";
  return (
    <section className="p-5 sm:p-6" aria-label="Miedo / Codicia">
      <CabeceraBloque icono={Thermometer}
                      derecha={data.vix != null && <span className="iv-cifra text-[12px] text-tinta-3">VIX {data.vix}</span>}>
        Miedo / Codicia
      </CabeceraBloque>
      {/* La cifra y su palabra son el dato; la barra solo sitúa la aguja, por eso va
          fina y atenuada: a tope de saturación competía con las subidas y bajadas. */}
      <p className="mt-3 flex items-baseline gap-2.5">
        <span className="iv-cifra-hero text-[30px] leading-none" style={{ color }}>{s}</span>
        <span className="text-[14px] font-medium" style={{ color }}>{data.label}</span>
        <span className="iv-cifra text-[12px] text-tinta-3 ml-auto">/100</span>
      </p>
      <div className="relative h-1.5 rounded-full mt-3 opacity-75" aria-hidden="true"
           style={{ background: "linear-gradient(90deg,rgb(var(--iv-baja)),rgb(var(--iv-aviso)),rgb(var(--iv-sube)))" }}>
        <div className="absolute top-1/2 -translate-y-1/2 w-[3px] h-3.5 bg-tinta rounded-full ring-2 ring-superficie"
             style={{ left: `calc(${s}% - 1.5px)` }} />
      </div>
      <div className="flex justify-between mt-1.5 text-[11.5px] text-tinta-3" aria-hidden="true">
        <span>Pánico</span><span>Euforia</span>
      </div>
      {data.advice && <p className="text-[13px] text-tinta-2 mt-3 leading-relaxed text-pretty">{data.advice}</p>}
    </section>
  );
}

// Sectores: variación del día por sector, para leer el mercado de un vistazo.
export function SectorHeatmap({ data, onPick }) {
  const sectors = data?.sectors;
  if (!Array.isArray(sectors) || !sectors.length) return null;
  // Barras DIVERGENTES desde un eje central: la longitud dice cuánto y el lado dice
  // hacia dónde, que es justo lo que un mosaico de baldosas teñidas obligaba a leer
  // número a número. Escala fija de ±3 % (como el mosaico anterior), para que un día
  // tranquilo se VEA tranquilo en vez de estirarse hasta los bordes.
  const ancho = (chg) => `${(Math.min(3, Math.abs(chg)) / 3) * 50}%`;
  // Sin `onPick` (así se monta en «Hoy») la fila no hace nada al pulsarla, así que no
  // es un botón: un botón que no responde promete una acción que no existe.
  const Fila = onPick ? "button" : "div";
  return (
    <section className="iv-panel p-5 sm:p-6" aria-labelledby="sectores-hoy">
      <CabeceraBloque icono={LayoutGrid} como="h2" id="sectores-hoy"
                      derecha={<span className="iv-etiqueta">variación del día</span>}>
        Sectores hoy
      </CabeceraBloque>
      <ul className="mt-3">
        {sectors.map((s) => {
          const up = s.change_percent >= 0;
          return (
            <li key={s.symbol}>
              <Fila
                {...(onPick ? { type: "button", onClick: () => onPick(s.symbol) } : {})}
                title={`${s.sector} (${s.symbol})`}
                className={`w-full grid grid-cols-[minmax(0,1fr)_minmax(72px,112px)_60px] items-center gap-3 py-[7px] text-left${
                  onPick ? " rounded-md hover:bg-tinta/[0.04] transition-colors duration-150 motion-reduce:transition-none" : ""}`}
              >
                <span className="text-[13px] text-tinta-2 truncate">{s.sector}</span>
                <span className="relative h-1.5 rounded-full bg-tinta/[0.06]" aria-hidden="true">
                  <span className="absolute top-[-3px] bottom-[-3px] left-1/2 w-px bg-tinta/20" />
                  <span className={`absolute top-0 bottom-0 rounded-full ${up ? "left-1/2 bg-sube/80" : "right-1/2 bg-baja/80"}`}
                        style={{ width: ancho(s.change_percent) }} />
                </span>
                <span className={`iv-cifra text-[13px] font-medium text-right ${up ? "text-sube" : "text-baja"}`}>
                  {up ? "+" : ""}{s.change_percent.toFixed(2)}%
                </span>
              </Fila>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
