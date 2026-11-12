import React from "react";
import { cn } from "@/lib/utils";

/* Segmentado · elegir UNA opción entre pocas
   ─────────────────────────────────────────────────────────────────────────────
   Rango de un gráfico (1M · 3M · 1A · Todo), filtro por riesgo… Antes cada pantalla
   lo pintaba a su manera: unas con fondo índigo, otras con borde, otras con texto
   subrayado. Aquí es siempre lo mismo: un carril de luz baja y la opción elegida
   levantada un escalón (superficie + sombra corta), sin color de intención: elegir
   un filtro no es una acción principal.

   `opciones` admite cadenas o `{ valor, etiqueta }`. `mono` para cuando las
   opciones son cifras o códigos (1M, 3M) y deben alinearse como tales. */

export default function Segmentado({ opciones, valor, onCambio, etiqueta, mono = false,
                                     tamano = "md", disabled = false, className }) {
  const items = (opciones || []).map((o) => (typeof o === "string" ? { valor: o, etiqueta: o } : o));
  return (
    <div role="group" aria-label={etiqueta}
         className={cn("inline-flex items-center p-[3px] rounded-[10px] bg-tinta/[0.05] border border-suave",
                       className)}>
      {items.map((o) => {
        const activo = o.valor === valor;
        return (
          <button key={o.valor} type="button" onClick={() => onCambio?.(o.valor)}
                  aria-pressed={activo} disabled={disabled}
                  className={cn(
                    "relative rounded-[7px] font-medium whitespace-nowrap",
                    "transition-[color,background-color,box-shadow] duration-150 ease-salida motion-reduce:transition-none",
                    "disabled:opacity-40 disabled:pointer-events-none",
                    tamano === "sm" ? "h-7 px-2.5 text-[12px]" : "h-8 px-3 text-[13px]",
                    mono && "iv-cifra",
                    activo
                      ? "bg-superficie text-tinta shadow-[0_1px_2px_rgb(0_0_0/0.25),0_0_0_1px_var(--borde-medio)]"
                      : "text-tinta-3 hover:text-tinta"
                  )}>
            {o.etiqueta}
          </button>
        );
      })}
    </div>
  );
}
