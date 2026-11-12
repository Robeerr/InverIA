import React from "react";
import { Link } from "react-router-dom";
import { CalendarDays } from "lucide-react";
import { fmtEnDias, fmtPrice } from "@/lib/format";
import CabeceraBloque from "@/components/base/CabeceraBloque";
import Monograma from "@/components/base/Monograma";

const ENLACE = "text-[13px] font-medium text-tinta-2 hover:text-marca transition-colors duration-150 " +
  "motion-reduce:transition-none inline-flex items-center gap-1 min-h-[32px] shrink-0";

/* PanelAgenda · resultados en los próximos 7 días
   ─────────────────────────────────────────────────────────────────────────────
   Contexto, no decisión: por eso vive en la columna lateral y es compacto. Cada fila
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
    // Sin caja propia: comparte panel con Cerebro (lo monta HoyView).
    <section className="p-5 sm:p-6" aria-labelledby="hoy-agenda">
      <CabeceraBloque icono={CalendarDays} como="h2" id="hoy-agenda"
                      derecha={<Link to="/calendario" className={ENLACE}>Abrir <span aria-hidden="true">→</span></Link>}>
        Calendario <span className="font-normal text-tinta-3">· próximos 7 días</span>
      </CabeceraBloque>

      {lista.length > 0 ? (
        <ul className="mt-2">
          {lista.map((e) => {
            const hora = cuando(e.hour);
            const trimestre = e.quarter ? `Q${e.quarter}${e.year ? ` ${String(e.year).slice(-2)}` : ""}` : null;
            return (
              <li key={e.symbol} className="flex items-center justify-between gap-3 py-2">
                <div className="flex items-center gap-3 min-w-0">
                  <Monograma symbol={e.symbol} tamano="sm" />
                  <div className="min-w-0">
                    <Link to={`/accion/${e.symbol}`}
                          className="text-[13.5px] text-tinta hover:text-marca font-semibold leading-tight
                                     transition-colors duration-150 motion-reduce:transition-none">
                      {e.symbol}
                    </Link>
                    {(hora || trimestre) && (
                      <p className="text-etiqueta text-tinta-3 truncate">
                        {[trimestre, hora].filter(Boolean).join(" · ")}
                      </p>
                    )}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <p className="iv-cifra text-[13px] text-tinta">{fmtEnDias(e.date)}</p>
                  {e.eps_estimate != null && (
                    <p className="iv-cifra text-etiqueta text-tinta-3" title="BPA estimado">
                      BPA ${fmtPrice(e.eps_estimate)}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-[13px] text-tinta-3 mt-2 leading-relaxed">
          Ninguna de tus posiciones presenta resultados esta semana.
        </p>
      )}
    </section>
  );
}
