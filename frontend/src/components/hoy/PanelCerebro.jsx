import React from "react";
import { Link } from "react-router-dom";
import Chip from "@/components/base/Chip";

const ENLACE = "text-etiqueta text-marca underline-offset-4 decoration-marca/50 hover:underline " +
  "inline-flex items-center gap-1 py-1 shrink-0";

/* PanelCerebro · qué han dicho tus fuentes desde la última visita
   ─────────────────────────────────────────────────────────────────────────────
   Compacto y en la barra lateral: es una novedad para curiosear, no una decisión.
   El número de menciones nuevas es la cifra, y los tickers nuevos son enlaces a su
   ficha. Cuando no hay nada, se dice con una frase, no con un hueco. */

export default function PanelCerebro({ cerebro }) {
  const c = cerebro || {};
  const hayNovedad = c.menciones_nuevas > 0 || (c.tickers_nuevos?.length || 0) > 0;
  return (
    // Sin caja propia: comparte panel con el Calendario (lo monta HoyView).
    <section className="p-4 sm:px-5" aria-labelledby="hoy-cerebro">
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <h2 id="hoy-cerebro" className="font-heading text-cuerpo font-semibold text-tinta">
          Cerebro <span className="text-apoyo font-normal text-tinta-3">· desde tu última visita</span>
        </h2>
        <Link to="/cerebro" className={ENLACE}>
          Explorar <span aria-hidden="true">→</span>
        </Link>
      </div>

      {hayNovedad ? (
        <>
          <p className="text-apoyo text-tinta-2">
            <span className="iv-cifra text-cuerpo font-bold text-tinta">{c.menciones_nuevas}</span>{" "}
            {c.menciones_nuevas === 1 ? "mención nueva" : "menciones nuevas"} en tus fuentes.
          </p>
          {c.tickers_nuevos?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {c.tickers_nuevos.slice(0, 10).map((t) => (
                <Link key={t} to={`/accion/${t}`} className="rounded-full">

                  <Chip tono="marca">{t}</Chip>
                </Link>
              ))}
            </div>
          )}
        </>
      ) : (
        <p className="text-apoyo text-tinta-3">
          Tus fuentes no han publicado nada nuevo desde la última vez que entraste.
        </p>
      )}
    </section>
  );
}
