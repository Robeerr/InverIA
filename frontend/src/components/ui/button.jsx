import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

/* Botón de shadcn sobre el sistema «grafito e índigo»: radio de control (10 px),
   foco índigo y el mismo gesto de pulsar que `Boton` (se hunde un 2 %). */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] text-sm font-medium tracking-[-0.01em] " +
    "transition-[color,background-color,border-color,box-shadow,transform] duration-150 ease-salida " +
    "active:scale-[0.98] motion-reduce:active:scale-100 " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background " +
    "disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "iv-boton-brillo hover:brightness-[1.08]",
        destructive: "bg-baja/15 text-baja border border-baja/30 hover:bg-baja/25",
        outline: "border border-medio bg-transparent text-tinta hover:bg-tinta/[0.05]",
        secondary: "bg-tinta/[0.06] text-tinta border border-suave hover:bg-tinta/[0.1]",
        ghost: "text-tinta-2 hover:bg-tinta/[0.06] hover:text-tinta",
        link: "text-marca underline-offset-4 hover:underline active:scale-100",
      },
      size: {
        default: "h-9 px-3.5 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props} />
  );
})
Button.displayName = "Button"

export { Button, buttonVariants }
