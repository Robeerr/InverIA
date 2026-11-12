import React from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

/* Cascada · una suma que se lee como suma
   ─────────────────────────────────────────────────────────────────────────────
   Cuando una cifra es la suma de otras —realizado + latente + dividendos + costes =
   total— cinco tarjetas iguales en fila no lo dicen: parecen cinco datos sueltos del
   mismo peso. La cascada sí. Cada sumando es una fila con su barra, y la barra EMPIEZA
   donde acabó la anterior: el ojo ve subir y bajar el acumulado hasta el total, y ve
   de un vistazo qué sumando pesa más y en qué sentido.

   Solo pinta lo que recibe: no calcula ninguna cifra de negocio. Las barras son la
   posición acumulada de los mismos valores que se escriben a la derecha. Un sumando a
   `null` se escribe «—» y no mueve la barra (no se sabe, no es cero).

   Verde/rojo solo por el signo de cada paso. La ayuda de cada fila es un botón que
   despliega el texto debajo: `title` no existe en el móvil. */

function BotonAyuda({ etiqueta, abierta, onClick }) {
  return (
    <button type="button" onClick={onClick} aria-expanded={abierta}
            aria-label={`Qué significa ${etiqueta}`}
            className={cn("inline-flex items-center justify-center w-7 h-7 -my-1.5 rounded-md shrink-0",
                          "transition-colors duration-150 ease-salida motion-reduce:transition-none hover:bg-tinta/[0.06]",
                          abierta ? "text-marca" : "text-tinta-3 hover:text-tinta")}>
      <Info className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" />
    </button>
  );
}

const tonoDe = (v) => (v == null ? "text-tinta-3" : v >= 0 ? "text-sube" : "text-baja");

function Fila({ paso, desde, hasta, escala, formato, total = false }) {
  const [abierta, setAbierta] = React.useState(false);
  const { min, rango } = escala;
  const conBarra = paso.valor != null && rango > 0;
  const izq = conBarra ? ((Math.min(desde, hasta) - min) / rango) * 100 : 0;
  const ancho = conBarra ? (Math.abs(hasta - desde) / rango) * 100 : 0;
  const cero = rango > 0 ? ((0 - min) / rango) * 100 : 0;
  const sube = (paso.valor ?? 0) >= 0;

  return (
    <div className={cn("grid grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-[minmax(0,232px)_minmax(0,1fr)_minmax(132px,auto)] gap-x-5 gap-y-2 items-center",
                       total ? "pt-4 mt-1 border-t border-medio" : "py-3")}>
      <div className="min-w-0">
        <p className="flex items-center gap-1.5 min-w-0">
          {paso.marca && <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-marca shrink-0" />}
          <span className={cn("truncate", total ? "text-[14.5px] font-semibold text-tinta" : "text-[14px] font-medium text-tinta")}>
            {paso.etiqueta}
          </span>
          {paso.ayuda && <BotonAyuda etiqueta={paso.etiqueta} abierta={abierta} onClick={() => setAbierta((a) => !a)} />}
        </p>
        {paso.significa && <p className="text-[12.5px] text-tinta-3 mt-0.5 leading-snug">{paso.significa}</p>}
      </div>

      {/* Importe: columna derecha en escritorio; en el móvil, a la derecha del rótulo. */}
      <p className={cn("iv-cifra text-right whitespace-nowrap lg:order-2",
                       total ? "text-[20px] font-semibold" : "text-[15px] font-medium", tonoDe(paso.valor))}>
        {formato(paso.valor)}
      </p>

      <div className="col-span-2 lg:col-span-1 lg:order-1 min-w-0">
        <div className={cn("relative rounded-full bg-tinta/[0.045]", total ? "h-3" : "h-2")} aria-hidden="true">
          {rango > 0 && min < 0 && (
            <span className="absolute -top-1 -bottom-1 w-px bg-tinta/25" style={{ left: `${cero}%` }} />
          )}
          {conBarra && (
            <span className={cn("absolute inset-y-0 rounded-full min-w-[3px]",
                                sube ? (total ? "bg-sube" : "bg-sube/70") : (total ? "bg-baja" : "bg-baja/70"))}
                  style={{ left: `${izq}%`, width: `${ancho}%` }} />
          )}
        </div>
        {paso.sub && <p className="text-[12px] text-tinta-3 mt-1.5 leading-snug">{paso.sub}</p>}
      </div>

      {abierta && paso.ayuda && (
        <p className="col-span-2 lg:col-span-3 lg:order-3 text-[13px] text-tinta-2 leading-relaxed max-w-[80ch] rounded-iv bg-tinta/[0.035] px-3.5 py-3">
          {paso.ayuda}
        </p>
      )}
      {paso.extra && <div className="col-span-2 lg:col-span-3 lg:order-3">{paso.extra}</div>}
    </div>
  );
}

/** `pasos`: [{ id, etiqueta, significa, valor, sub, ayuda, marca, extra }]
 *  `total`: { etiqueta, significa, valor, sub, ayuda } — se pinta desde cero.
 *  `formato`: número → texto («—» para null). */
export default function Cascada({ pasos, total, formato, className }) {
  // Posición acumulada de cada paso: desde → hasta.
  let acc = 0;
  const tramos = pasos.map((p) => {
    const desde = acc;
    if (p.valor != null) acc += p.valor;
    return { p, desde, hasta: acc };
  });
  const puntos = [0, ...tramos.flatMap((t) => [t.desde, t.hasta])];
  if (total?.valor != null) puntos.push(total.valor);
  const min = Math.min(...puntos);
  const max = Math.max(...puntos);
  const escala = { min, rango: max - min };

  return (
    <div className={cn("[&>div+div:not(:last-child)]:border-t [&>div+div:not(:last-child)]:border-suave", className)}>
      {tramos.map(({ p, desde, hasta }) => (
        <Fila key={p.id} paso={p} desde={desde} hasta={hasta} escala={escala} formato={formato} />
      ))}
      {total && (
        <Fila paso={total} desde={0} hasta={total.valor ?? 0} escala={escala} formato={formato} total />
      )}
    </div>
  );
}
