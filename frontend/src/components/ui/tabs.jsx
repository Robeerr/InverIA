import * as React from "react"
import * as TabsPrimitive from "@radix-ui/react-tabs"

import { cn } from "@/lib/utils"

/* Pestañas como control segmentado: un carril tenue y la activa como una pieza de
   luz que se levanta (fondo de superficie + sombra corta). */
const Tabs = TabsPrimitive.Root

const TabsList = React.forwardRef(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "inline-flex h-9 items-center justify-center rounded-[10px] bg-tinta/[0.05] p-[3px] text-tinta-3 border border-suave",
      className
    )}
    {...props} />
))
TabsList.displayName = TabsPrimitive.List.displayName

const TabsTrigger = React.forwardRef(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex items-center justify-center whitespace-nowrap rounded-[7px] px-3 h-full text-[13px] font-medium " +
        "transition-[color,background-color,box-shadow] duration-150 ease-salida " +
        "hover:text-tinta focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring " +
        "disabled:pointer-events-none disabled:opacity-50 " +
        "data-[state=active]:bg-superficie data-[state=active]:text-tinta " +
        "data-[state=active]:shadow-[0_1px_2px_rgb(0_0_0/0.25),0_0_0_1px_var(--borde-suave)]",
      className
    )}
    {...props} />
))
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName

const TabsContent = React.forwardRef(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      "mt-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      className
    )}
    {...props} />
))
TabsContent.displayName = TabsPrimitive.Content.displayName

export { Tabs, TabsList, TabsTrigger, TabsContent }
