import React from "react";
import { Link } from "react-router-dom";
import { Brain } from "lucide-react";
import Chip from "@/components/base/Chip";
import CabeceraBloque from "@/components/base/CabeceraBloque";

const ENLACE = "text-[13px] font-medium text-tinta-2 hover:text-marca transition-colors duration-150 " +
  "motion-reduce:transition-none inline-flex items-center gap-1 min-h-[32px] shrink-0";

/* PanelCerebro · qué han dicho tus fuentes desde la última visita
   ─────────────────────────────────────────────────────────────────────────────
   Compacto y en la columna lateral: es una novedad para curiosear, no una decisión.
   El número de menciones nuevas es la cifra, y los tickers nuevos son enlaces a su
   ficha. Cuando no hay nada, se dice con una frase, no con un hueco. */

export default function PanelCerebro({ cerebro }) {
  const c = cerebro || {};
  const hayNovedad = c.menciones_nuevas > 0 || (c.tickers_nuevos?.length || 0) > 0;
  return (
    // Sin caja propia: comparte panel con el Calendario (lo monta HoyView).
    <section className="p-5 sm:p-6" aria-labelledby="hoy-cerebro">
      <CabeceraBloque icono={Brain} como="h2" id="hoy-cerebro"
                      derecha={<Link to="/cerebro" className={ENLACE}>Explorar <span aria-hidden="true">→</span></Link>}>
        Cerebro <span className="font-normal text-tinta-3">· desde tu última visita</span>
      </CabeceraBloque>

      {hayNovedad ? (
        <>
          <p className="text-[13px] text-tinta-2 mt-2 flex items-baseline gap-2">
            <span className="iv-cifra-hero text-[24px] leading-none">{c.menciones_nuevas}</span>
            {c.menciones_nuevas === 1 ? "mención nueva" : "menciones nuevas"} en tus fuentes.
          </p>
          {c.tickers_nuevos?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {c.tickers_nuevos.slice(0, 10).map((t) => (
                <Link key={t} to={`/accion/${t}`} className="rounded-md">
                  <Chip tono="marca">{t}</Chip>
                </Link>
              ))}
            </div>
          )}
        </>
      ) : (
        <p className="text-[13px] text-tinta-3 mt-2 leading-relaxed">
          Tus fuentes no han publicado nada nuevo desde la última vez que entraste.
        </p>
      )}
    </section>
  );
}
