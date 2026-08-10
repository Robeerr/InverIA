import React from "react";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

/* Chip · etiqueta corta de estado
   ─────────────────────────────────────────────────────────────────────────────
   La auditoría contó ~90 chips en la app resueltos con 12 implementaciones
   distintas: cada pantalla se inventaba su padding, su radio y su forma de teñir
   el fondo. El resultado es que "positivo" no se ve igual en la Cartera que en el
   Cerebro, y el usuario tiene que reaprender el código de color en cada pantalla.

   Tres ejes y nada más: tono (qué significa) × variante (cuánto pesa) × tamaño.
   Si hace falta un cuarto eje, casi siempre es que ese sitio no quería un chip. */

const chipVariants = cva(
  "inline-flex items-center gap-1 font-mono font-semibold whitespace-nowrap rounded-iv-sm border",
  {
    variants: {
      tono: {
        neutro: "[--c:var(--iv-neutro)]",
        marca: "[--c:var(--iv-marca)]",
        sube: "[--c:var(--iv-sube)]",
        baja: "[--c:var(--iv-baja)]",
        aviso: "[--c:var(--iv-aviso)]",
        info: "[--c:var(--iv-info)]",
      },
      variante: {
        // Suave es el que se usa el 90% de las veces: legible sin gritar.
        suave: "bg-[rgb(var(--c)/0.12)] text-[rgb(var(--c))] border-[rgb(var(--c)/0.28)]",
        // Sólido solo para lo que de verdad tiene que verse desde lejos.
        solido: "bg-[rgb(var(--c))] text-[rgb(var(--iv-marca-tinta))] border-transparent",
        // Contorno para cuando ya hay mucho color alrededor.
        contorno: "bg-transparent text-[rgb(var(--c))] border-[rgb(var(--c)/0.5)]",
      },
      tamano: {
        // 11px es el suelo de la escala. No hay un tamaño menor a propósito.
        sm: "text-etiqueta px-1.5 py-0.5",
        md: "text-apoyo px-2 py-1",
      },
    },
    defaultVariants: { tono: "neutro", variante: "suave", tamano: "sm" },
  }
);

export function Chip({ tono, variante, tamano, className, children, ...props }) {
  return (
    <span className={cn(chipVariants({ tono, variante, tamano }), className)} {...props}>
      {children}
    </span>
  );
}

export { chipVariants };
export default Chip;
