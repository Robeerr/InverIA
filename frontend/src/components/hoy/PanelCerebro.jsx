import React from "react";
import { Link } from "react-router-dom";
import Chip from "@/components/base/Chip";

/* PanelCerebro · qué han dicho tus fuentes desde la última visita
   ─────────────────────────────────────────────────────────────────────────────
   Compacto y en la barra lateral: es una novedad para curiosear, no una decisión.
   El número de menciones nuevas es la cifra, y los tickers nuevos son enlaces a su
   ficha. Cuando no hay nada, se dice con una frase, no con un hueco. */

export default function PanelCerebro({ cerebro }) {
  const c = cerebro || {};
  const hayNovedad = c.menciones_nuevas > 0 || (c.tickers_nuevos?.length || 0) > 0;
  return (
    <section className="iv-panel p-4" aria-labelledby="hoy-cerebro">
      <div className="flex items-baseline justify-between mb-2">
        <h2 id="hoy-cerebro" className="iv-etiqueta">Desde tu última visita</h2>
        <Link to="/cerebro" className="text-etiqueta text-marca hover:underline">el Cerebro</Link>
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
                <Link key={t} to={`/accion/${t}`}>
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
