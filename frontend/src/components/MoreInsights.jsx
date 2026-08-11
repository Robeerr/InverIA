import React, { useEffect, useState } from "react";
import { ArrowFatRight } from "@phosphor-icons/react";
import { api } from "../lib/api";

// Alternativa sectorial: otra acción del mismo sector con mejor potencial. Solo si hay datos.

export function AlternativePanel({ symbol, onPick }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    let a = true;
    if (!symbol) return;
    api.alternativa(symbol).then((x) => { if (a) setD(x); }).catch(() => {});
    return () => { a = false; };
  }, [symbol]);
  if (!d || !(d.alternativas || []).length) return null;
  return (
    <section className="iv-panel p-5 animate-fade-up">
      <div className="flex items-center gap-2 mb-1">
        <ArrowFatRight size={18} weight="fill" className="text-aviso" />
        <h3 className="font-heading font-semibold text-base text-tinta">Alternativa en {d.grupo || d.sector}</h3>
      </div>
      <p className="text-[11px] text-tinta-3 mb-3">
        {d.industry && d.grupo === d.industry
          ? `Del mismo sector (${d.industry}) con mejor potencial que ${d.symbol}:`
          : `Del mismo sector con mejor potencial que ${d.symbol}:`}
      </p>
      <div className="space-y-2">
        {d.alternativas.map((a) => (
          <button key={a.symbol} onClick={() => onPick?.(a.symbol)}
            className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md border border-linea hover:border-aviso text-left transition-colors">
            <div className="min-w-0">
              <p className="font-mono font-bold text-sm text-tinta">{a.symbol}</p>
              <p className="text-[10px] text-tinta-3 truncate max-w-[160px]">{a.name}</p>
            </div>
            <div className="text-right shrink-0">
              <span className="text-sm font-mono font-bold text-sube">{a.potential_score} pts</span>
              {typeof a.revenue_growth === "number" && <p className="text-[10px] text-tinta-3">ventas +{Math.round(a.revenue_growth)}%</p>}
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
