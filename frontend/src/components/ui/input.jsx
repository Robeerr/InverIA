import * as React from "react"

import { cn } from "@/lib/utils"

/* Campo: superficie un escalón más alta, borde translúcido y, al enfocar, borde
   índigo con un halo de 3 px (lo pinta index.css para todos los campos). */
const Input = React.forwardRef(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-9 w-full rounded-[10px] border border-medio bg-superficie-alt px-3 py-1 text-base text-tinta " +
          "transition-[border-color,box-shadow] duration-150 ease-salida " +
          "file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground " +
          "placeholder:text-tinta-3 hover:border-linea-fuerte focus-visible:outline-none " +
          "disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className
      )}
      ref={ref}
      {...props} />
  );
})
Input.displayName = "Input"

export { Input }
