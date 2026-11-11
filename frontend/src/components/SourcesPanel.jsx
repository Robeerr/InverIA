import React, { useEffect, useState } from "react";
import { Users } from "@phosphor-icons/react";
import { api } from "../lib/api";
import Confluencia from "./Confluencia";

// "Tus fuentes": qué han dicho tus jefes/newsletters de esta acción. Solo se muestra
// si hay menciones, para no ensuciar. Lee /fuentes/{symbol}.

function fecha(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString("es-ES", { day: "2-digit", month: "short" }); }
  catch { return ""; }
}

export default function SourcesPanel({ symbol }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    let alive = true;
    if (!symbol) return;
    api.fuentes(symbol).then((d) => { if (alive) setData(d); }).catch(() => {});
    return () => { alive = false; };
  }, [symbol]);

  if (!data || !data.n) return null; // sin menciones → no molesta

  return (
    <section className="iv-panel p-5" aria-labelledby="fuentes-titulo">
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-3">
        <h3 id="fuentes-titulo" className="font-heading text-cuerpo font-semibold text-tinta flex items-center gap-2">
          <Users size={16} weight="fill" className="text-tinta-3" aria-hidden="true" />
          Tus fuentes sobre {data.symbol}
        </h3>
        {/* El recuento, en una sola línea de apoyo junto al título: antes era otra fila
            entre el cruce y la lista. */}
        <p className="iv-cifra text-etiqueta flex items-center gap-x-3 gap-y-0.5 flex-wrap">
          <span className="text-tinta-3">{data.n} mención{data.n === 1 ? "" : "es"}</span>
          {data.positivos > 0 && <span className="text-sube font-semibold">{data.positivos} a favor</span>}
          {data.negativos > 0 && <span className="text-baja font-semibold">{data.negativos} en contra</span>}
        </p>
      </div>
      {/* El cruce con el motor, antes que las menciones sueltas: es lo que convierte
          «cuatro fuentes hablan de esto» en algo sobre lo que decidir. */}
      <Confluencia confluencia={data.confluencia} className="mb-3" />

      {/* Filas con filete en vez de una pila de bloques: el sentimiento lo marca el
          punto y el color de la acción, y la fuente pasa a gris para que el naranja
          no se repita veinte veces en el mismo panel. */}
      <ul
        className="divide-y divide-linea max-h-[420px] overflow-y-auto pr-1 -mx-1 px-1"
        tabIndex={0}
        aria-label={`Menciones de ${data.symbol} en tus fuentes`}
      >
        {data.menciones.map((m, i) => {
          const c = m.sentimiento === "POSITIVO" ? "rgb(var(--iv-sube))"
            : m.sentimiento === "NEGATIVO" ? "rgb(var(--iv-baja))" : "rgb(var(--iv-tinta-3))";
          return (
            <li key={i} className="py-2.5 first:pt-1">
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 min-w-0">
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: c }} aria-hidden="true" />
                  <span className="text-etiqueta font-medium text-tinta-2 truncate">{m.fuente}</span>
                </span>
                <span className="iv-cifra text-etiqueta text-tinta-3 shrink-0">{fecha(m.fecha)}</span>
              </div>
              {m.motivo && <p className="text-apoyo text-tinta leading-snug mt-1 pl-3.5">{m.motivo}</p>}
              {(m.accion || m.niveles) && (
                <p className="flex items-center gap-2 mt-0.5 pl-3.5 text-etiqueta flex-wrap">
                  {m.accion && <span style={{ color: c }} className="font-mono font-semibold tracking-wide">{m.accion}</span>}
                  {m.niveles && <span className="text-tinta-3 iv-cifra">· {m.niveles}</span>}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-etiqueta text-tinta-3 mt-3 pt-3 border-t border-linea leading-snug">Lo que dicen tus fuentes de pago, cruzado con el veredicto de tu motor. No es recomendación.</p>
    </section>
  );
}
