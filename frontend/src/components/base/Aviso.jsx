import React from "react";
import { TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

/* Aviso · algo de tus datos que hay que revisar
   ─────────────────────────────────────────────────────────────────────────────
   Antes cada aviso era su propia caja ámbar con su borde, su fondo y su icono a
   12 px: tres o cuatro seguidas convertían la pantalla en una pared amarilla. Ahora
   van como FILAS de un único panel (`AvisosPanel`), cada una con su icono en un
   cuadrado de luz ámbar, un titular que dice el problema en una frase y el detalle
   debajo en tinta-2. El color lo lleva el icono, no la caja entera.

   `acciones` va al pie de la fila: los botones que lo arreglan. */

export function Aviso({ titulo, children, acciones, tono = "aviso", icono: Icono = TriangleAlert, className }) {
  return (
    <div className={cn("flex gap-3.5 px-4 sm:px-5 py-4", className)}>
      <span aria-hidden="true"
            className={cn("flex items-center justify-center w-8 h-8 rounded-[9px] shrink-0",
                          tono === "baja" ? "bg-baja/10 text-baja" : "bg-aviso/10 text-aviso")}>
        <Icono className="w-4 h-4" strokeWidth={1.9} />
      </span>
      <div className="min-w-0 flex-1">
        {titulo && <p className="text-[14px] font-medium text-tinta leading-snug">{titulo}</p>}
        {children && <div className="text-[13px] text-tinta-2 leading-relaxed mt-1">{children}</div>}
        {acciones && <div className="mt-3 flex flex-wrap items-center gap-2">{acciones}</div>}
      </div>
    </div>
  );
}

/** Panel que agrupa varios `Aviso` con un rótulo y su recuento. */
export function AvisosPanel({ titulo, nota, children, className }) {
  const hijos = React.Children.toArray(children).filter(Boolean);
  if (!hijos.length) return null;
  return (
    <section className={cn("iv-panel overflow-hidden border-aviso/25", className)} aria-label={titulo}>
      <div className="flex items-center justify-between gap-3 flex-wrap px-4 sm:px-5 py-3 border-b border-suave bg-aviso/[0.04]">
        <p className="flex items-center gap-2 text-[13px] font-medium text-tinta-2">
          <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-aviso" />
          {titulo}
          <span className="iv-cifra text-[11.5px] leading-none px-1.5 py-1 rounded-md bg-aviso/15 text-aviso">{hijos.length}</span>
        </p>
        {nota && <p className="text-[12.5px] text-tinta-3">{nota}</p>}
      </div>
      <div className="divide-y divide-suave">{hijos}</div>
    </section>
  );
}

export default Aviso;
