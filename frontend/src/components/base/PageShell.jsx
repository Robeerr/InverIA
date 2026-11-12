import React from "react";
import { cn } from "@/lib/utils";

/* PageShell · el armazón de una pantalla
   ─────────────────────────────────────────────────────────────────────────────
   El mismo wrapper está copiado en ocho pantallas
   (`max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6`), a veces con anchos y
   paddings ligeramente distintos, que es la razón de que el contenido no quede
   alineado al cambiar de sección.

   Además resuelve dos cosas de accesibilidad que hoy faltan y que son gratis
   cuando hay un solo sitio donde ponerlas:
     · Un <main> de verdad, para que el salto de navegación funcione.
     · Un <h1> por pantalla. Hoy hay pantallas que empiezan directamente en <h3>
       porque el título se maquetó con un <div>, y un lector de pantalla no puede
       reconstruir el índice de la página. */

export default function PageShell({
  titulo,
  descripcion,
  acciones,
  ancho = "normal",
  className,
  children,
}) {
  const anchos = {
    normal: "max-w-[1440px]",
    estrecho: "max-w-[900px]",   // lectura larga: el texto no debe pasar de ~70 caracteres
    completo: "max-w-none",      // tablas muy anchas que ya gestionan su propio scroll
  };

  return (
    <main className={cn("mx-auto px-4 sm:px-8 py-5 sm:py-8 min-w-0 iv-entra", anchos[ancho], className)}>
      {(titulo || acciones) && (
        <header className="mb-7 sm:mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
          <div className="min-w-0">
            {titulo && (
              <h1 className="text-[26px] sm:text-[32px] leading-[1.1] font-semibold tracking-[-0.035em] text-tinta text-balance">
                {titulo}
              </h1>
            )}
            {descripcion && (
              <p className="text-cuerpo text-tinta-2 mt-2 max-w-[68ch] text-pretty">{descripcion}</p>
            )}
          </div>
          {acciones && <div className="flex flex-wrap items-center gap-2 shrink-0">{acciones}</div>}
        </header>
      )}
      {children}
    </main>
  );
}
