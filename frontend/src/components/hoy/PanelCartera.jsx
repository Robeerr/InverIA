import React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { fmtEur, fmtPct } from "@/lib/format";
import { leerComoBroker } from "@/lib/preferencias";
import { perdidasSegunMetodo } from "@/lib/operaciones";
import { AlertTriangle } from "lucide-react";

const ENLACE = "text-etiqueta text-marca underline-offset-4 decoration-marca/50 hover:underline " +
  "inline-flex items-center gap-1 py-1 shrink-0";

/* PanelCartera · el estado de tu dinero, de un vistazo
   ─────────────────────────────────────────────────────────────────────────────
   Antes la cartera era una de las cuatro cajas del mismo peso de la portada. Aquí
   sube a la barra lateral con jerarquía propia: el VALOR es la cifra grande —es lo
   que de verdad se mira—, y latente/realizado/invertido quedan como desglose. Las
   posiciones en pérdidas van debajo, porque son lo único de la cartera que puede
   pedir una decisión hoy.

   Ni un número se inventa: todo viene de `data.cartera` de `GET /hoy`. */

/** Una fila del desglose: rótulo a la izquierda, cifra alineada a la derecha. Con todas
 *  las cifras en la misma columna derecha y en dígitos tabulares, los euros se comparan
 *  de un vistazo — en la rejilla 2×2 de antes cada cifra empezaba en un sitio. Si no
 *  cabe en una línea (cifras de siete dígitos en la columna estrecha), la cifra baja. */
function Fila({ etiqueta, valor, num, tono = "ninguno", ayuda }) {
  const clave = tono === "auto"
    ? (num > 0 ? "text-sube" : num < 0 ? "text-baja" : "text-tinta")
    : "text-tinta";
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 py-1.5">
      <dt className="text-apoyo text-tinta-2" title={ayuda}>{etiqueta}</dt>
      <dd className={cn("iv-cifra text-apoyo font-semibold ml-auto text-right", clave)}>{valor}</dd>
    </div>
  );
}

/** Las cifras en el método que el usuario tiene elegido en Operaciones.
 *
 *  Con «Como en DEGIRO» puesto, Operaciones enseña media ponderada; la portada enseñaba
 *  LIFO al lado y parecía que los números no cuadraban. Ahora siguen el mismo interruptor.
 *  Si la respuesta no trae las cifras ponderadas —una portada cacheada de antes del
 *  despliegue— se usan las del método de gestión, que es lo que se enseñaba hasta ahora,
 *  y la etiqueta lo dice. */
function cifrasSegunMetodo(c, comoBroker) {
  const pond = c.ponderada || {};
  const usaPmp = comoBroker && pond.latente_eur != null && pond.realizado_eur != null;
  return usaPmp
    ? { latente_eur: pond.latente_eur, realizado_eur: pond.realizado_eur,
        invertido_eur: pond.invertido_eur ?? c.invertido_eur, metodo: "media ponderada · como DEGIRO" }
    : { latente_eur: c.latente_eur, realizado_eur: c.realizado_eur, invertido_eur: c.invertido_eur,
        metodo: c.metodo_gestion ? `por ${c.metodo_gestion.toUpperCase()}` : null };
}

export default function PanelCartera({ cartera }) {
  const base = cartera || {};
  const [comoBroker] = React.useState(leerComoBroker);
  // El valor de hoy no depende del método; lo demás, sí.
  const c = { ...base, ...cifrasSegunMetodo(base, comoBroker) };
  // Las pérdidas, en el MISMO método que las cifras de arriba. Antes iban siempre por el
  // de gestión y AAOI salía con un importe aquí y otro en Operaciones.
  const enPerdidas = perdidasSegunMetodo(base.atencion, comoBroker);
  return (
    // Un solo panel para todo el dinero —valor, desglose y posiciones en pérdidas—, sin
    // halos: en la portada solo brillan las decisiones urgentes, y así se ven antes. Las
    // pérdidas siguen en rojo, que es el color que aquí sí dice algo.
    <section className="iv-panel p-5" aria-labelledby="hoy-cartera">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="hoy-cartera" className="font-heading text-cuerpo font-semibold text-tinta">Tu cartera</h2>
        <Link to="/cartera" className={ENLACE}>
          Ver todo <span aria-hidden="true">→</span>
        </Link>
      </div>

      {/* El rótulo dice QUÉ es la cifra grande. Sin él, «34.758 €» debajo de «Tu cartera»
          podía leerse como lo invertido, que es otro número y está más abajo. */}
      <p className="iv-etiqueta mt-3">Valor actual</p>
      {/* La cifra protagonista de la portada, en degradado. Es el número que se abre a
          mirar, y la única cifra-héroe de la pantalla. */}
      <p className="iv-cifra-hero text-[clamp(32px,3vw,42px)] mt-1.5">
        {fmtEur(c.valor_eur)}
      </p>
      <p
        className={cn("iv-cifra text-apoyo font-semibold mt-2",
          c.latente_eur > 0 ? "text-sube" : c.latente_eur < 0 ? "text-baja" : "text-tinta-3")}
        title="Ganancia o pérdida no realizada de las posiciones abiertas, en euros"
      >
        {c.latente_eur != null ? `${c.latente_eur >= 0 ? "↗ +" : "↘ "}${fmtEur(c.latente_eur)}` : "—"}{" "}
        <span className="font-normal text-tinta-3">latente</span>
      </p>

      <dl className="mt-4 pt-2 border-t border-linea">
        <Fila etiqueta="Realizado" valor={c.realizado_eur != null ? fmtEur(c.realizado_eur) : "—"} num={c.realizado_eur} tono="auto"
              ayuda="Ganancia ya materializada en ventas" />
        <Fila etiqueta="Invertido" valor={c.invertido_eur != null ? fmtEur(c.invertido_eur) : "—"} />
      </dl>
      {/* En qué método van las cifras. Sin esto, comparar con Operaciones o con el
          bróker era adivinar por qué el realizado no coincidía. */}
      {c.metodo && (
        <p className="text-etiqueta text-tinta-3 mt-1"
           title="Cambia con el interruptor «Ver como en DEGIRO» de Operaciones">
          Cifras {c.metodo}
        </p>
      )}
      {c.posiciones_sin_valorar > 0 && (
        <p className="text-etiqueta text-tinta-3 mt-1">
          {c.posiciones_sin_valorar} sin valorar · falta precio o tipo de cambio
        </p>
      )}

      {/* Las posiciones en pérdidas: lo único de la cartera que puede pedir una decisión
          hoy. Solo aparece si hay alguna. Importe y porcentaje en la misma columna
          derecha, en dígitos tabulares, para leerlos en vertical como una tabla. */}
      {enPerdidas.length > 0 && (
        <section className="mt-4 pt-4 border-t border-linea" aria-labelledby="hoy-perdidas">
          <h3 id="hoy-perdidas" className="iv-etiqueta text-baja flex items-center gap-1.5 mb-2">
            <AlertTriangle className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" />
            En pérdidas
          </h3>
          <ul className="divide-y divide-linea">
            {enPerdidas.map((p) => (
              <li key={p.symbol} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <Link to={`/accion/${p.symbol}`}
                        className="iv-cifra text-apoyo font-semibold text-tinta hover:text-marca
                                   transition-colors duration-150 motion-reduce:transition-none">
                    {p.symbol}
                  </Link>
                  {p.motivo && <p className="text-etiqueta text-tinta-3 truncate">{p.motivo}</p>}
                </div>
                <div className="text-right shrink-0">
                  {p.pnl_eur != null && (
                    <p className="iv-cifra text-apoyo font-semibold text-baja leading-tight">{fmtEur(p.pnl_eur)}</p>
                  )}
                  <p className="iv-cifra text-etiqueta text-baja"
                     title="Rendimiento de la acción en su divisa, sin el ruido del tipo de cambio">
                    {fmtPct(p.pct)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
