import React from "react";
import { cn } from "@/lib/utils";

/* Pestanas · varias vistas de lo mismo, una a la vez
   ─────────────────────────────────────────────────────────────────────────────
   Para listas largas que compiten por el mismo hueco (ventas, posiciones, por
   acción): apiladas, la última quedaba a varias pantallas de distancia. Rótulo en
   Geist 14/500 con el recuento en mono al lado; la activa en tinta plena con un filo
   índigo de 2 px debajo (es el «estás aquí», como el rail). Flechas izquierda/derecha
   para moverse con el teclado, como pide el patrón ARIA de pestañas.

   `pestanas`: [{ valor, etiqueta, cuenta }]. Cada panel debe llevar
   `id={`${id}-panel-${valor}`}` y `role="tabpanel"` (ver `propsPanel`). */

export function propsPanel(id, valor) {
  return { id: `${id}-panel-${valor}`, role: "tabpanel", "aria-labelledby": `${id}-tab-${valor}` };
}

export default function Pestanas({ id, pestanas, valor, onCambio, etiqueta, className }) {
  const refs = React.useRef({});
  const mover = (e, i) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const n = pestanas.length;
    const sig = pestanas[(i + (e.key === "ArrowRight" ? 1 : n - 1)) % n];
    onCambio?.(sig.valor);
    refs.current[sig.valor]?.focus();
  };
  return (
    <div role="tablist" aria-label={etiqueta}
         className={cn("flex items-end gap-1 sm:gap-2 border-b border-suave overflow-x-auto [scrollbar-width:none]", className)}>
      {pestanas.map((p, i) => {
        const activa = p.valor === valor;
        return (
          <button key={p.valor} type="button" role="tab"
                  ref={(el) => { refs.current[p.valor] = el; }}
                  id={`${id}-tab-${p.valor}`} aria-selected={activa}
                  aria-controls={`${id}-panel-${p.valor}`} tabIndex={activa ? 0 : -1}
                  onClick={() => onCambio?.(p.valor)} onKeyDown={(e) => mover(e, i)}
                  className={cn(
                    "relative inline-flex items-center gap-2 h-11 px-2.5 sm:px-3 -mb-px whitespace-nowrap rounded-t-md",
                    "text-[14px] font-medium transition-colors duration-150 ease-salida motion-reduce:transition-none",
                    activa ? "text-tinta" : "text-tinta-3 hover:text-tinta-2"
                  )}>
            {p.etiqueta}
            {p.cuenta != null && (
              <span className={cn("iv-cifra text-[11.5px] leading-none px-1.5 py-1 rounded-md",
                                  activa ? "bg-marca/15 text-marca" : "bg-tinta/[0.06] text-tinta-3")}>
                {p.cuenta}
              </span>
            )}
            <span aria-hidden="true"
                  className={cn("absolute left-2 right-2 -bottom-px h-[2px] rounded-full bg-marca origin-center",
                                "transition-[transform,opacity] duration-200 ease-salida motion-reduce:transition-none",
                                activa ? "scale-x-100 opacity-100" : "scale-x-50 opacity-0")} />
          </button>
        );
      })}
    </div>
  );
}
