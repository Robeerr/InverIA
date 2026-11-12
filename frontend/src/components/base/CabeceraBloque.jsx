import React from "react";
import { cn } from "@/lib/utils";

/* CabeceraBloque · el rótulo de un bloque dentro de un panel
   ─────────────────────────────────────────────────────────────────────────────
   Icono lucide a 16 px en tinta-3, rótulo en Geist 13/500 y, a la derecha, una nota o
   un enlace. Es el nivel por debajo del titular de sección: dice qué es el bloque sin
   competir con la cifra que viene debajo. `como` permite que sea el h2 del bloque
   cuando no hay otro titular. */

export default function CabeceraBloque({ icono: Icono, children, derecha, como: Etiqueta = "p", id, className }) {
  return (
    <div className={cn("flex items-center justify-between gap-3 min-h-[24px]", className)}>
      <Etiqueta id={id} className="flex items-center gap-2 text-[13px] font-medium text-tinta-2 min-w-0">
        {Icono && <Icono className="w-4 h-4 text-tinta-3 shrink-0" strokeWidth={1.75} aria-hidden="true" />}
        {children}
      </Etiqueta>
      {derecha}
    </div>
  );
}
