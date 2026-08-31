import React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { fmtEur, fmtPct } from "@/lib/format";

/* PanelCartera · el estado de tu dinero, de un vistazo
   ─────────────────────────────────────────────────────────────────────────────
   Antes la cartera era una de las cuatro cajas del mismo peso de la portada. Aquí
   sube a la barra lateral con jerarquía propia: el VALOR es la cifra grande —es lo
   que de verdad se mira—, y latente/realizado/invertido quedan como desglose. Las
   posiciones en pérdidas van debajo, porque son lo único de la cartera que puede
   pedir una decisión hoy.

   Ni un número se inventa: todo viene de `data.cartera` de `GET /hoy`. */

function Fila({ etiqueta, valor, num, tono = "ninguno", ayuda }) {
  const clave = tono === "auto"
    ? (num > 0 ? "text-sube" : num < 0 ? "text-baja" : "text-tinta")
    : "text-tinta";
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="iv-etiqueta" title={ayuda}>{etiqueta}</span>
      <span className={cn("iv-cifra text-apoyo font-semibold", clave)}>{valor}</span>
    </div>
  );
}

export default function PanelCartera({ cartera }) {
  const c = cartera || {};
  return (
    <section className="iv-panel p-4" aria-labelledby="hoy-cartera">
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <p className="iv-etiqueta tracking-[0.16em] text-tinta-3">Tu cartera</p>
        <Link to="/cartera" className="text-etiqueta text-marca hover:underline shrink-0">ver todo ›</Link>
      </div>
      {/* El rótulo dice QUÉ es la cifra grande. Sin él, «34.758 €» debajo de «Tu cartera»
          podía leerse como lo invertido, que es otro número y está tres líneas más abajo. */}
      <h2 id="hoy-cartera" className="text-apoyo text-tinta-2 mb-0.5">Valor actual</h2>

      {/* La cifra grande: el valor total. Es el número que se abre a mirar. */}
      <p className="iv-cifra text-cifra font-bold text-tinta leading-none">
        {fmtEur(c.valor_eur)}
      </p>
      <div className="flex items-center gap-3 mt-1.5">
        <span
          className={cn("iv-cifra text-apoyo font-semibold",
            c.latente_eur > 0 ? "text-sube" : c.latente_eur < 0 ? "text-baja" : "text-tinta-3")}
          title="Ganancia o pérdida no realizada de las posiciones abiertas, en euros"
        >
          {c.latente_eur != null ? `${c.latente_eur >= 0 ? "+" : ""}${fmtEur(c.latente_eur)}` : "—"} latente
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 mt-3 pt-3 border-t border-linea">
        <Fila etiqueta="Realizado" valor={c.realizado_eur != null ? fmtEur(c.realizado_eur) : "—"} num={c.realizado_eur} tono="auto"
              ayuda="Ganancia ya materializada en ventas" />
        <Fila etiqueta="Invertido" valor={c.invertido_eur != null ? fmtEur(c.invertido_eur) : "—"} />
      </div>

      {c.posiciones_sin_valorar > 0 && (
        <p className="text-etiqueta text-tinta-3 mt-2">
          {c.posiciones_sin_valorar} sin valorar · falta precio o tipo de cambio
        </p>
      )}

      {c.atencion?.length > 0 && (
        <div className="mt-3 pt-3 border-t border-linea">
          <p className="iv-etiqueta text-baja mb-1.5">En pérdidas</p>
          <div className="space-y-1">
            {c.atencion.map((p) => (
              <div key={p.symbol} className="flex items-center justify-between gap-2">
                <Link to={`/accion/${p.symbol}`} className="iv-cifra text-apoyo text-tinta hover:text-marca font-semibold">
                  {p.symbol}
                </Link>
                <span className="text-etiqueta text-tinta-3 truncate flex-1 min-w-0 mx-1">{p.motivo}</span>
                <span className="flex items-baseline gap-2 shrink-0">
                  <span className="iv-cifra text-apoyo text-baja font-semibold"
                        title="Rendimiento de la acción en su divisa, sin el ruido del tipo de cambio">
                    {fmtPct(p.pct)}
                  </span>
                  {p.pnl_eur != null && (
                    <span className="iv-cifra text-etiqueta text-tinta-3">{fmtEur(p.pnl_eur)}</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
