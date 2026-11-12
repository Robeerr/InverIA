import React from "react";
import { cn } from "@/lib/utils";

/* Monograma · la «cara» de un ticker en una lista
   ─────────────────────────────────────────────────────────────────────────────
   Las listas de producto financiero (bróker, banco) anclan cada fila con una pieza
   cuadrada a la izquierda: el ojo baja por la columna de monogramas y encuentra el
   valor sin leer. No hay logotipos en la app —y no se inventan—, así que la pieza
   lleva las letras del ticker en Geist Mono sobre una capa de luz.

   `tono` tiñe el filo y las letras cuando la fila lo pide (una alerta, una ruptura):
   es la misma disciplina que el resto del sistema, el color hay que pedirlo. */

const TONOS = {
  neutro: "text-tinta-2 bg-tinta/[0.05] border-suave",
  marca: "text-marca bg-marca/10 border-marca/25",
  sube: "text-sube bg-sube/10 border-sube/25",
  baja: "text-baja bg-baja/10 border-baja/25",
  aviso: "text-aviso bg-aviso/10 border-aviso/25",
  info: "text-info bg-info/10 border-info/25",
};

const TAMANOS = {
  sm: "w-8 h-8 rounded-[9px] text-[10.5px]",
  md: "w-10 h-10 rounded-[11px] text-[11.5px]",
};

/** «BRK.B» → «BRK», «SNOW» → «SNOW», «GOOGL» → «GOOG». Cuatro letras caben a 40 px. */
function letrasDe(symbol) {
  const base = String(symbol || "?").split(/[.\-:]/)[0].toUpperCase();
  return base.slice(0, 4);
}

export default function Monograma({ symbol, tono = "neutro", tamano = "md", className }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "iv-cifra inline-flex items-center justify-center shrink-0 border font-semibold tracking-[-0.04em] select-none",
        TAMANOS[tamano] || TAMANOS.md,
        TONOS[tono] || TONOS.neutro,
        className
      )}
    >
      {letrasDe(symbol)}
    </span>
  );
}
