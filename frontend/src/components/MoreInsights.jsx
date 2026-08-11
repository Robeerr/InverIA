import React, { useEffect, useState } from "react";
import { ArrowFatRight } from "@phosphor-icons/react";
import { api } from "../lib/api";
import Score from "./Score";

// Alternativa sectorial: otra acción del mismo sector con mejor potencial. Solo si hay datos.
//
// El desglose sale de /opportunities/score/{symbol}, que lee la MISMA caché del escaneo
// de la que sale esta lista: los símbolos de `alternativas` son un subconjunto de
// `results`, así que están garantizados en `desgloses`. Es lectura pura, bajo demanda y
// sin coste externo.
//
// CARRERA CONOCIDA, no resuelta a propósito: si el escaneo se refresca entre cargar esta
// lista y abrir un desglose, el chip enseñaría el score anterior y el desglose el nuevo.
// La ventana es de horas, pasa igual en Oportunidades, y el desglose lleva el sello del
// escaneo del que sale.

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
        {/* La fila NO es un botón: dentro hay dos zonas pulsables hermanas —navegar y
            desplegar el desglose— y un botón dentro de otro es HTML inválido. El hover
            del borde se conserva; en un div funciona igual. */}
        {d.alternativas.map((a) => (
          <div key={a.symbol}
            className="flex items-start justify-between gap-2 px-3 py-2 rounded-md border border-linea hover:border-aviso transition-colors">
            <button onClick={() => onPick?.(a.symbol)}
              className="min-w-0 text-left group"
              title={`Ver el análisis de ${a.symbol}`}>
              <span className="block font-mono font-bold text-sm text-tinta group-hover:text-marca transition-colors">{a.symbol}</span>
              <span className="block text-[10px] text-tinta-3 truncate max-w-[160px]">{a.name}</span>
            </button>
            {/* Mismo componente que en Oportunidades, así que el rótulo «ver desglose ▾»
                y el desglose salen idénticos. El verde es fijo aquí a propósito: una
                alternativa se enseña PORQUE supera a la que estás mirando. */}
            <Score symbol={a.symbol}>
              <span className="text-sm font-mono font-bold text-sube">{a.potential_score} pts</span>
              {typeof a.revenue_growth === "number" && (
                <span className="block text-[10px] text-tinta-3 text-right">ventas +{Math.round(a.revenue_growth)}%</span>
              )}
            </Score>
          </div>
        ))}
      </div>
    </section>
  );
}
