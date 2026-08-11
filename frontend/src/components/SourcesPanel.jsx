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
    <section className="iv-panel p-5 animate-fade-up">
      <div className="flex items-center gap-2 mb-3">
        <Users size={18} weight="fill" className="text-marca" />
        <h3 className="font-heading font-semibold text-base text-tinta">Tus fuentes sobre {data.symbol}</h3>
      </div>
      {/* El cruce con el motor, antes que las menciones sueltas: es lo que convierte
          «cuatro fuentes hablan de esto» en algo sobre lo que decidir. */}
      <Confluencia confluencia={data.confluencia} className="mb-3" />

      <div className="flex items-center gap-3 mb-3 text-[11px] font-semibold">
        <span className="text-tinta-3">{data.n} mención{data.n === 1 ? "" : "es"}</span>
        {data.positivos > 0 && <span className="text-sube">👍 {data.positivos}</span>}
        {data.negativos > 0 && <span className="text-baja">👎 {data.negativos}</span>}
      </div>
      <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
        {data.menciones.map((m, i) => {
          const c = m.sentimiento === "POSITIVO" ? "rgb(var(--iv-sube))"
            : m.sentimiento === "NEGATIVO" ? "rgb(var(--iv-baja))" : "rgb(var(--iv-tinta-3))";
          return (
            <div key={i} className="border-l-2 pl-3 py-0.5" style={{ borderColor: c }}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-marca truncate">{m.fuente}</span>
                <span className="text-[9px] text-tinta-3 font-mono shrink-0">{fecha(m.fecha)}</span>
              </div>
              {m.motivo && <p className="text-[12px] text-tinta leading-snug mt-0.5">{m.motivo}</p>}
              <div className="flex items-center gap-2 mt-0.5 text-[10px]">
                {m.accion && <span style={{ color: c }} className="font-semibold">{m.accion}</span>}
                {m.niveles && <span className="text-tinta-3">· {m.niveles}</span>}
                {m.inveria?.verdict && <span className="text-tinta-3 truncate">· motor: {m.inveria.verdict.slice(0, 24)}</span>}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-tinta-3 mt-3 leading-snug">Lo que dicen tus fuentes de pago, cruzado con el veredicto de tu motor. No es recomendación.</p>
    </section>
  );
}
