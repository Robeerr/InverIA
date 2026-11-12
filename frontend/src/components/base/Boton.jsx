import React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

/* Boton · acción
   ─────────────────────────────────────────────────────────────────────────────
   `ui/button` (shadcn) ya existe en el proyecto y funciona, pero está atado a los
   tokens de shadcn (`bg-primary`, `text-primary-foreground`) y hay 99 botones
   escritos a pelo con `<button className="...">` que lo ignoran, sumando ~25
   combinaciones distintas de estilo para lo mismo.

   Este componente es el equivalente sobre los tokens de InverIA. No sustituye a
   `ui/button`: los sitios que ya lo usan siguen igual. Lo que sustituye son los
   botones crudos, uno por pantalla a medida que se migra.

   Detalles que resuelve y que a mano se olvidan casi siempre:
     · `type="button"` por defecto — un <button> dentro de un <form> envía el
       formulario si no se dice lo contrario, y eso ha sido un bug real más de una vez.
     · Estado ocupado con `aria-busy`, y deshabilitado mientras tanto.
     · Altura mínima de 32px, que es el mínimo cómodo para tocar en móvil. */

const botonVariants = cva(
  // Radio de control (10 px), no píldora: la píldora naranja era la firma de la
  // versión anterior. El principal es índigo sólido con un filo de luz arriba; al
  // pulsar, todos se hunden un 2 % (150 ms, curva de salida).
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] font-medium tracking-[-0.01em] " +
    "transition-[color,background-color,border-color,box-shadow,filter,transform] duration-150 ease-salida " +
    "active:scale-[0.98] motion-reduce:active:scale-100 " +
    "disabled:pointer-events-none disabled:opacity-50 [&_svg]:shrink-0",
  {
    variants: {
      variante: {
        primario: "iv-boton-brillo hover:brightness-[1.08]",
        secundario: "bg-tinta/[0.06] text-tinta border border-suave hover:bg-tinta/[0.1]",
        contorno: "bg-transparent text-tinta border border-medio hover:bg-tinta/[0.05]",
        fantasma: "bg-transparent text-tinta-2 hover:bg-tinta/[0.06] hover:text-tinta",
        peligro: "bg-baja/15 text-baja border border-baja/30 hover:bg-baja/25",
        enlace: "bg-transparent text-marca underline-offset-4 hover:underline p-0 h-auto active:scale-100",
      },
      tamano: {
        // Tamaños explícitos: tailwind-merge tomaría `text-apoyo` por un color y se
        // comería el color de la variante (o al revés).
        sm: "h-8 px-3 text-[13px]",
        md: "h-9 px-3.5 text-[13px]",
        lg: "h-11 px-5 text-[14.5px]",
        icono: "h-9 w-9 p-0",
      },
    },
    defaultVariants: { variante: "primario", tamano: "md" },
  }
);

export const Boton = React.forwardRef(function Boton(
  { variante, tamano, className, type = "button", ocupado = false, disabled,
    asChild = false, children, ...props },
  ref
) {
  // `asChild` para que un enlace pueda tener aspecto de botón sin dejar de ser un
  // enlace: un <button> que navega rompe abrir en pestaña nueva, el clic central y
  // el menú contextual, y eso en una app que se usa con el teclado se nota.
  const Comp = asChild ? Slot : "button";
  const propsDeBoton = asChild
    ? {}
    : { type, disabled: disabled || ocupado, "aria-busy": ocupado || undefined };

  return (
    <Comp
      ref={ref}
      className={cn(botonVariants({ variante, tamano }), className)}
      {...propsDeBoton}
      {...props}
    >
      {children}
    </Comp>
  );
});

export { botonVariants };
export default Boton;
