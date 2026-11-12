import React from "react";
import { cn } from "@/lib/utils";

/* Rango · dónde está un valor entre su mínimo y su máximo
   ─────────────────────────────────────────────────────────────────────────────
   Rango del día, rango de 52 semanas. Una pista fina con el tramo recorrido en luz
   y un punto donde está el precio; los extremos van debajo en cifras tabulares.
   Sin verde ni rojo: estar cerca del máximo no es «bueno» por sí solo.

   `formato` recibe el número y devuelve el texto de cada extremo. Si falta algún
   dato, no se pinta nada: una barra con un extremo inventado engaña. */

export default function Rango({ etiqueta, min, max, valor, formato = (v) => v, className }) {
  const a = Number(min);
  const b = Number(max);
  const v = Number(valor);
  if (![a, b, v].every(Number.isFinite) || b <= a) return null;
  const pct = Math.max(0, Math.min(100, ((v - a) / (b - a)) * 100));

  return (
    <div className={cn("min-w-0", className)}>
      {etiqueta && (
        <div className="flex items-baseline justify-between gap-3">
          <p className="iv-etiqueta">{etiqueta}</p>
          <p className="iv-cifra text-[12px] text-tinta-3">{Math.round(pct)}%</p>
        </div>
      )}
      <div
        className="relative h-1.5 mt-2.5 rounded-full bg-tinta/[0.08]"
        role="img"
        aria-label={`${etiqueta || "Rango"}: ${formato(v)} entre ${formato(a)} y ${formato(b)}`}
      >
        <div className="absolute inset-y-0 left-0 rounded-full bg-tinta/[0.22]" style={{ width: `${pct}%` }} />
        <span
          className="absolute top-1/2 w-3 h-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-tinta
                     shadow-[0_0_0_3px_rgb(var(--iv-superficie))]"
          style={{ left: `${pct}%` }}
          aria-hidden="true"
        />
      </div>
      <div className="flex justify-between gap-3 mt-2 iv-cifra text-[12px] text-tinta-3">
        <span>{formato(a)}</span>
        <span>{formato(b)}</span>
      </div>
    </div>
  );
}
