import React, { useEffect, useState } from "react";
import { Users } from "@phosphor-icons/react";
import { api } from "../lib/api";

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
    <section className="card-flat p-5 animate-fade-up">
      <div className="flex items-center gap-2 mb-3">
        <Users size={18} weight="fill" className="text-[#1a3a32]" />
        <h3 className="font-heading font-semibold text-base text-[#0e1f1a]">Tus fuentes sobre {data.symbol}</h3>
      </div>
      <div className="flex items-center gap-3 mb-3 text-[11px] font-semibold">
        <span className="text-[#5c6b66]">{data.n} mención{data.n === 1 ? "" : "es"}</span>
        {data.positivos > 0 && <span className="text-[#4a7c59]">👍 {data.positivos}</span>}
        {data.negativos > 0 && <span className="text-[#d85c41]">👎 {data.negativos}</span>}
      </div>
      <div className="space-y-2">
        {data.menciones.map((m, i) => {
          const c = m.sentimiento === "POSITIVO" ? "#4a7c59" : m.sentimiento === "NEGATIVO" ? "#d85c41" : "#5c6b66";
          return (
            <div key={i} className="border-l-2 pl-3 py-0.5" style={{ borderColor: c }}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-[#1a3a32] truncate">{m.fuente}</span>
                <span className="text-[9px] text-[#8a958f] font-mono shrink-0">{fecha(m.fecha)}</span>
              </div>
              {m.motivo && <p className="text-[12px] text-[#0e1f1a] leading-snug mt-0.5">{m.motivo}</p>}
              <div className="flex items-center gap-2 mt-0.5 text-[10px]">
                {m.accion && <span style={{ color: c }} className="font-semibold">{m.accion}</span>}
                {m.niveles && <span className="text-[#5c6b66]">· {m.niveles}</span>}
                {m.inveria?.verdict && <span className="text-[#5c6b66] truncate">· motor: {m.inveria.verdict.slice(0, 24)}</span>}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-[#8a958f] mt-3 leading-snug">Lo que dicen tus fuentes de pago, cruzado con el veredicto de tu motor. No es recomendación.</p>
    </section>
  );
}
