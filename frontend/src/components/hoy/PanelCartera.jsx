import React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { fmtEur, fmtPct } from "@/lib/format";
import { leerComoBroker } from "@/lib/preferencias";
import { perdidasSegunMetodo } from "@/lib/operaciones";
import { AlertTriangle, Minus, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import Monograma from "@/components/base/Monograma";

const ENLACE = "text-[13px] font-medium text-tinta-2 hover:text-marca transition-colors duration-150 " +
  "motion-reduce:transition-none inline-flex items-center gap-1 min-h-[32px] shrink-0";

/* PanelCartera · la métrica héroe de la portada
   ─────────────────────────────────────────────────────────────────────────────
   Abre la pantalla arriba a la izquierda, a lo ancho: el VALOR de la cartera es la
   cifra que se abre a mirar, y la única cifra héroe de la pantalla. A su derecha, el
   desglose en columna tabular; debajo, las posiciones en pérdidas como lista, que es
   lo único de la cartera que puede pedir una decisión hoy.

   Ni un número se inventa: todo viene de `data.cartera` de `GET /hoy`. */

/** Una fila del desglose: rótulo a la izquierda, cifra alineada a la derecha. Con todas
 *  las cifras en la misma columna derecha y en dígitos tabulares, los euros se comparan
 *  de un vistazo. Si no cabe en una línea (cifras de siete dígitos), la cifra baja. */
function Fila({ etiqueta, valor, num, tono = "ninguno", ayuda }) {
  const clave = tono === "auto"
    ? (num > 0 ? "text-sube" : num < 0 ? "text-baja" : "text-tinta")
    : "text-tinta";
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 py-2.5">
      <dt className="text-[13px] text-tinta-2" title={ayuda}>{etiqueta}</dt>
      <dd className={cn("iv-cifra text-[14px] font-medium ml-auto text-right", clave)}>{valor}</dd>
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

/** «19.632,03 €» → cifra grande + «€» pequeño. El símbolo a tamaño héroe pesaba como
 *  un dígito más; reducido, la cifra se lee de un golpe. No cambia el texto: es el
 *  mismo `fmtEur`, partido solo para pintarlo. */
function CifraEuros({ valor }) {
  const txt = fmtEur(valor);
  const m = typeof txt === "string" ? txt.match(/^(.*?)(\s?€)$/) : null;
  if (!m) return txt;
  return (
    <>
      {m[1]}
      <span className="text-[0.5em] font-medium text-tinta-3 ml-[0.14em] tracking-normal align-[0.62em]">€</span>
    </>
  );
}

export default function PanelCartera({ cartera }) {
  const base = cartera || {};
  const [comoBroker] = React.useState(leerComoBroker);
  // El valor de hoy no depende del método; lo demás, sí.
  const c = { ...base, ...cifrasSegunMetodo(base, comoBroker) };
  // Las pérdidas, en el MISMO método que las cifras de arriba. Antes iban siempre por el
  // de gestión y AAOI salía con un importe aquí y otro en Operaciones.
  const enPerdidas = perdidasSegunMetodo(base.atencion, comoBroker);
  const signoLatente = c.latente_eur > 0 ? "sube" : c.latente_eur < 0 ? "baja" : "neutro";
  const Flecha = signoLatente === "sube" ? TrendingUp : signoLatente === "baja" ? TrendingDown : Minus;

  return (
    <section className="iv-panel relative overflow-hidden p-5 sm:p-7 h-full flex flex-col" aria-labelledby="hoy-cartera">
      {/* Luz de esquina, muy baja: da profundidad a la pieza principal sin teñirla. */}
      <span aria-hidden="true"
            className="pointer-events-none absolute -top-28 -left-20 w-[460px] h-[280px] rounded-full
                       bg-marca/[0.08] blur-3xl" />

      <div className="relative flex items-center justify-between gap-2">
        <h2 id="hoy-cartera" className="flex items-center gap-2 text-[13px] font-medium text-tinta-2">
          <Wallet className="w-4 h-4 text-tinta-3" strokeWidth={1.75} aria-hidden="true" />
          Tu cartera
        </h2>
        <Link to="/cartera" className={ENLACE}>
          Ver cartera <span aria-hidden="true">→</span>
        </Link>
      </div>

      <div className="relative mt-4 sm:mt-5 flex flex-col md:flex-row md:items-end md:justify-between gap-x-10 gap-y-5">
        <div className="min-w-0">
          {/* El rótulo dice QUÉ es la cifra grande. Sin él, «34.758 €» debajo de «Tu
              cartera» podía leerse como lo invertido, que es otro número. */}
          <p className="iv-etiqueta">Valor actual</p>
          <p className="iv-cifra-hero text-[clamp(40px,4.6vw,60px)] mt-2 break-words">
            <CifraEuros valor={c.valor_eur} />
          </p>
          <p className="mt-3.5 flex flex-wrap items-center gap-2"
             title="Ganancia o pérdida no realizada de las posiciones abiertas, en euros">
            <span className={cn("iv-cifra inline-flex items-center gap-1.5 h-7 px-2 rounded-md text-[13px] font-medium",
                                signoLatente === "sube" ? "bg-sube/10 text-sube"
                                  : signoLatente === "baja" ? "bg-baja/10 text-baja" : "bg-tinta/5 text-tinta-3")}>
              <Flecha className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" />
              {c.latente_eur != null ? `${c.latente_eur >= 0 ? "+" : ""}${fmtEur(c.latente_eur)}` : "—"}
            </span>
            <span className="text-[13px] text-tinta-3">latente</span>
          </p>
        </div>

        <div className="md:w-[250px] md:shrink-0">
          <dl className="border-t border-suave md:border-t-0 [&>div+div]:border-t [&>div+div]:border-suave">
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
        </div>
      </div>

      {/* Las posiciones en pérdidas: lo único de la cartera que puede pedir una decisión
          hoy. Solo aparece si hay alguna. Importe y porcentaje alineados a la derecha, en
          dígitos tabulares; en dos columnas en escritorio para no estirar la pieza. */}
      {enPerdidas.length > 0 && (
        <section className="relative mt-6 pt-5 border-t border-suave" aria-labelledby="hoy-perdidas">
          <h3 id="hoy-perdidas" className="text-[12px] font-medium text-baja flex items-center gap-1.5 mb-1">
            <AlertTriangle className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" />
            En pérdidas
            <span className="iv-cifra text-tinta-3 font-normal">· {enPerdidas.length}</span>
          </h3>
          <ul className="grid md:grid-cols-2 md:gap-x-10">
            {enPerdidas.map((p) => (
              <li key={p.symbol} className="flex items-center justify-between gap-3 py-2.5 border-b border-suave
                                            last:border-b-0 md:[&:nth-last-child(2):nth-child(odd)]:border-b-0">
                <div className="flex items-center gap-3 min-w-0">
                  <Monograma symbol={p.symbol} tamano="sm" />
                  <div className="min-w-0">
                    <Link to={`/accion/${p.symbol}`}
                          className="text-[13.5px] font-semibold text-tinta hover:text-marca leading-tight
                                     transition-colors duration-150 motion-reduce:transition-none">
                      {p.symbol}
                    </Link>
                    {p.motivo && <p className="text-etiqueta text-tinta-3 truncate">{p.motivo}</p>}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  {p.pnl_eur != null && (
                    <p className="iv-cifra text-[13.5px] font-medium text-baja leading-tight">{fmtEur(p.pnl_eur)}</p>
                  )}
                  <p className="iv-cifra text-etiqueta text-baja mt-0.5"
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
