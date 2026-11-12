import React, { useEffect, useState } from "react";
import { ArrowFatRight } from "@phosphor-icons/react";
import { api } from "../lib/api";
import Score from "./Score";
import Monograma from "./base/Monograma";

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
    <section className="iv-panel p-5 sm:p-6">
      <h3 className="text-[13px] font-medium text-tinta-2 flex items-center gap-2 mb-1">
        <ArrowFatRight size={16} weight="fill" className="text-tinta-3 shrink-0" aria-hidden="true" />
        Alternativa en {d.grupo || d.sector}
      </h3>
      <p className="text-[13px] text-tinta-3 mb-3">
        {d.industry && d.grupo === d.industry
          ? `Del mismo sector (${d.industry}) con mejor potencial que ${d.symbol}:`
          : `Del mismo sector con mejor potencial que ${d.symbol}:`}
      </p>
      <div className="divide-y divide-suave">
        {/* La fila NO es un botón: dentro hay dos zonas pulsables hermanas —navegar y
            desplegar el desglose— y un botón dentro de otro es HTML inválido. El hover
            del borde se conserva; en un div funciona igual. */}
        {d.alternativas.map((a) => (
          <div key={a.symbol}
            className="flex items-center justify-between gap-3 py-3 -mx-2 px-2 rounded-iv-sm hover:bg-tinta/[0.04] transition-colors duration-150 motion-reduce:transition-none">
            {/* `flex-1` y `self-stretch` no son adorno: sin ellos el boton se dimensiona
                a su contenido —el ticker y el nombre— y el resto de la fila queda muerto.
                Antes toda la fila era el boton, asi que pulsar en el hueco central
                navegaba; sin esto, deja de hacerlo y parece que no funciona. */}
            <button onClick={() => onPick?.(a.symbol)}
              className="flex-1 min-w-0 self-stretch text-left group cursor-pointer flex items-center gap-3"
              title={`Ver el análisis de ${a.symbol}`}>
              <Monograma symbol={a.symbol} tamano="sm" />
              <span className="min-w-0">
                <span className="block font-semibold text-[14px] text-tinta group-hover:text-marca transition-colors">{a.symbol}</span>
                <span className="block text-[12px] text-tinta-3 truncate max-w-[220px]">{a.name}</span>
              </span>
            </button>
            {/* Mismo componente que en Oportunidades, así que el rótulo «ver desglose ▾»
                y el desglose salen idénticos. El verde es fijo aquí a propósito: una
                alternativa se enseña PORQUE supera a la que estás mirando. */}
            <Score symbol={a.symbol}>
              <span className="iv-cifra text-apoyo font-bold text-sube">{a.potential_score} pts</span>
              {typeof a.revenue_growth === "number" && (
                <span className="block text-etiqueta text-tinta-3 text-right">ventas +{Math.round(a.revenue_growth)}%</span>
              )}
            </Score>
          </div>
        ))}
      </div>
    </section>
  );
}
