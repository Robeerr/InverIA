import React from "react";
import { cn } from "@/lib/utils";

/* Medidor · una cifra sobre su escala, en una línea
   ─────────────────────────────────────────────────────────────────────────────
   El hermano compacto de `Rango`: cabe en una fila de tabla. Una pista de 4 px, zonas
   opcionales teñidas muy bajo (RSI < 30 y > 70, por ejemplo) y una marca vertical donde
   cae el valor. Sirve para leer «dónde está» de un vistazo al bajar por una columna,
   que es lo que una cifra suelta no da.

   Sin verde ni rojo por defecto: una posición en una escala no es una subida. Las zonas
   llevan su propio tono (`info`, `aviso`…) y hay que pedirlas.

   `zonas`: [{ desde, hasta, tono }] en las mismas unidades que `min`/`max`.
   `relleno`: pinta el tramo recorrido desde `min` (útil para puntuaciones).
   Si el valor no es un número, no se pinta: una marca inventada engaña. */

const TONO_ZONA = {
  neutro: "bg-tinta/[0.10]",
  marca: "bg-marca/25",
  info: "bg-info/25",
  aviso: "bg-aviso/25",
  sube: "bg-sube/25",
  baja: "bg-baja/25",
};

const TONO_MARCA = {
  neutro: "bg-tinta",
  marca: "bg-marca",
  info: "bg-info",
  aviso: "bg-aviso",
  sube: "bg-sube",
  baja: "bg-baja",
};

export default function Medidor({
  min = 0, max = 100, valor, zonas = [], relleno = false, tono = "neutro",
  etiqueta, className,
}) {
  const a = Number(min);
  const b = Number(max);
  const v = Number(valor);
  if (valor == null || ![a, b, v].every(Number.isFinite) || b <= a) return null;
  const pos = (x) => Math.max(0, Math.min(100, ((x - a) / (b - a)) * 100));
  const p = pos(v);

  return (
    <div className={cn("relative h-1 rounded-full bg-tinta/[0.08]", className)}
         role="img" aria-label={etiqueta}>
      {zonas.map((z, i) => (
        <span key={i} aria-hidden="true"
              className={cn("absolute inset-y-0", TONO_ZONA[z.tono] || TONO_ZONA.neutro,
                            pos(z.desde) === 0 && "rounded-l-full", pos(z.hasta) === 100 && "rounded-r-full")}
              style={{ left: `${pos(z.desde)}%`, width: `${pos(z.hasta) - pos(z.desde)}%` }} />
      ))}
      {relleno && (
        <span aria-hidden="true" className={cn("absolute inset-y-0 left-0 rounded-full opacity-70", TONO_MARCA[tono])}
              style={{ width: `${p}%` }} />
      )}
      <span aria-hidden="true"
            className={cn("absolute top-1/2 w-[3px] h-3 -translate-x-1/2 -translate-y-1/2 rounded-full",
                          "shadow-[0_0_0_2px_rgb(var(--iv-superficie))]", TONO_MARCA[tono] || TONO_MARCA.neutro)}
            style={{ left: `${p}%` }} />
    </div>
  );
}
