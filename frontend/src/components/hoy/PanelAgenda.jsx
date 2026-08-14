import React from "react";
import { Link } from "react-router-dom";
import { fmtEnDias, fmtPrice } from "@/lib/format";

/* PanelAgenda · resultados en los próximos 7 días
   ─────────────────────────────────────────────────────────────────────────────
   Contexto, no decisión: por eso vive en la barra lateral y es compacto. Cada fila
   trae lo que devuelve el calendario —cuándo, a qué hora (antes de la apertura /
   después del cierre), el trimestre y el BPA estimado—. El «vacío honesto»
   sustituye a la caja de «nada nuevo» que pesaba lo mismo que todo lo demás. */

/** `bmo`/`amc` → texto legible. Finnhub los manda así. */
function cuando(hour) {
  const h = (hour || "").toLowerCase();
  if (h === "bmo") return "antes de abrir";
  if (h === "amc") return "tras el cierre";
  if (h === "dmh") return "en sesión";
  return null;
}

export default function PanelAgenda({ eventos }) {
  const lista = eventos || [];
  return (
    <section className="iv-panel p-4" aria-labelledby="hoy-agenda">
      <div className="flex items-baseline justify-between mb-2">
        <h2 id="hoy-agenda" className="iv-etiqueta">Próximos 7 días</h2>
        <Link to="/calendario" className="text-etiqueta text-marca hover:underline">calendario</Link>
      </div>

      {lista.length > 0 ? (
        <div className="divide-y divide-linea -my-1">
          {lista.map((e) => {
            const hora = cuando(e.hour);
            const trimestre = e.quarter ? `Q${e.quarter}${e.year ? ` ${String(e.year).slice(-2)}` : ""}` : null;
            return (
              <div key={e.symbol} className="flex items-baseline justify-between gap-2 py-1.5">
                <div className="min-w-0">
                  <Link to={`/accion/${e.symbol}`} className="iv-cifra text-apoyo text-tinta hover:text-marca font-semibold">
                    {e.symbol}
                  </Link>
                  {(hora || trimestre) && (
                    <span className="text-etiqueta text-tinta-3 ml-2">
                      {[trimestre, hora].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </div>
                <div className="flex items-baseline gap-2 shrink-0">
                  {e.eps_estimate != null && (
                    <span className="iv-cifra text-etiqueta text-tinta-3" title="BPA estimado">
                      BPA ${fmtPrice(e.eps_estimate)}
                    </span>
                  )}
                  <span className="iv-cifra text-apoyo text-tinta-2">{fmtEnDias(e.date)}</span>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-apoyo text-tinta-3">
          Ninguna de tus posiciones presenta resultados esta semana.
        </p>
      )}
    </section>
  );
}
