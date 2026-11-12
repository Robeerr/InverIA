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
    <section className="iv-panel p-5 sm:p-6" aria-labelledby="fuentes-titulo">
      {/* El recuento como cifra y una barra partida a favor / neutras / en contra: se lee
          el reparto antes de leer una sola mención. */}
      <div className="flex items-end justify-between gap-x-6 gap-y-3 flex-wrap">
        <div className="min-w-0">
          <h3 id="fuentes-titulo" className="text-[13px] font-medium text-tinta-2 flex items-center gap-2">
            <Users size={16} weight="fill" className="text-tinta-3" aria-hidden="true" />
            Tus fuentes sobre {data.symbol}
          </h3>
          <p className="mt-2 flex items-baseline gap-2">
            <span className="iv-cifra-hero text-[28px] leading-none tracking-[-0.035em]">{data.n}</span>
            <span className="text-[13px] text-tinta-3">{data.n === 1 ? "mención" : "menciones"}</span>
          </p>
        </div>
        <p className="text-[13px] flex items-center gap-x-4 gap-y-1 flex-wrap">
          {data.positivos > 0 && <span className="inline-flex items-center gap-1.5 text-sube"><span className="w-1.5 h-1.5 rounded-full bg-sube" aria-hidden="true" /><span className="iv-cifra">{data.positivos}</span> a favor</span>}
          {data.negativos > 0 && <span className="inline-flex items-center gap-1.5 text-baja"><span className="w-1.5 h-1.5 rounded-full bg-baja" aria-hidden="true" /><span className="iv-cifra">{data.negativos}</span> en contra</span>}
        </p>
      </div>
      {data.n > 0 && (
        <div className="mt-3 h-1.5 rounded-full overflow-hidden flex bg-tinta/[0.08]" aria-hidden="true">
          <div className="bg-sube" style={{ width: `${((data.positivos || 0) / data.n) * 100}%` }} />
          <div className="flex-1" />
          <div className="bg-baja" style={{ width: `${((data.negativos || 0) / data.n) * 100}%` }} />
        </div>
      )}
      {/* El cruce con el motor, antes que las menciones sueltas: es lo que convierte
          «cuatro fuentes hablan de esto» en algo sobre lo que decidir. */}
      <Confluencia confluencia={data.confluencia} className="mt-5 mb-2" />

      {/* Filas con filete en vez de una pila de bloques: el sentimiento lo marca el
          punto y el color de la acción, y la fuente pasa a gris para que el naranja
          no se repita veinte veces en el mismo panel. */}
      <ul
        className="divide-y divide-suave max-h-[420px] overflow-y-auto pr-1 -mx-1 px-1"
        tabIndex={0}
        aria-label={`Menciones de ${data.symbol} en tus fuentes`}
      >
        {data.menciones.map((m, i) => {
          const c = m.sentimiento === "POSITIVO" ? "rgb(var(--iv-sube))"
            : m.sentimiento === "NEGATIVO" ? "rgb(var(--iv-baja))" : "rgb(var(--iv-tinta-3))";
          return (
            <li key={i} className="py-3 first:pt-2">
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 min-w-0">
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: c }} aria-hidden="true" />
                  <span className="text-etiqueta font-medium text-tinta-2 truncate">{m.fuente}</span>
                </span>
                <span className="iv-cifra text-etiqueta text-tinta-3 shrink-0">{fecha(m.fecha)}</span>
              </div>
              {m.motivo && <p className="text-[14px] text-tinta leading-snug mt-1 pl-3.5">{m.motivo}</p>}
              {(m.accion || m.niveles) && (
                <p className="flex items-center gap-2 mt-0.5 pl-3.5 text-etiqueta flex-wrap">
                  {m.accion && <span style={{ color: c }} className="text-[12px] font-semibold">{String(m.accion).charAt(0) + String(m.accion).slice(1).toLowerCase()}</span>}
                  {m.niveles && <span className="text-tinta-3 iv-cifra">· {m.niveles}</span>}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-etiqueta text-tinta-3 mt-3 pt-3 border-t border-suave leading-snug">Lo que dicen tus fuentes de pago, cruzado con el veredicto de tu motor. No es recomendación.</p>
    </section>
  );
}
