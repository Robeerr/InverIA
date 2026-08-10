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
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-iv font-medium " +
    "transition-colors disabled:pointer-events-none disabled:opacity-50 " +
    "[&_svg]:shrink-0",
  {
    variants: {
      variante: {
        primario: "bg-marca text-marca-tinta hover:bg-marca/90",
        secundario: "bg-superficie-alt text-tinta border border-linea-fuerte hover:bg-linea/40",
        contorno: "bg-transparent text-tinta border border-linea-fuerte hover:bg-superficie-alt",
        fantasma: "bg-transparent text-tinta-2 hover:bg-superficie-alt hover:text-tinta",
        peligro: "bg-baja text-marca-tinta hover:bg-baja/90",
        enlace: "bg-transparent text-marca underline-offset-4 hover:underline p-0 h-auto",
      },
      tamano: {
        sm: "h-8 px-3 text-apoyo",
        md: "h-9 px-4 text-apoyo",
        lg: "h-11 px-6 text-cuerpo",
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
