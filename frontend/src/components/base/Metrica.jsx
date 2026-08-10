import React from "react";
import { cn } from "@/lib/utils";
import { tono as tonoDelSigno, SIN_DATO } from "@/lib/format";

/* Metrica · una cifra con su etiqueta
   ─────────────────────────────────────────────────────────────────────────────
   El bug que este componente existe para no repetir: hoy hay sitios donde un EPS
   negativo se pinta en VERDE. Pasa porque el color se decide con un
   `valor >= 0 ? verde : rojo` copiado de donde sí tenía sentido (la variación del
   día) a donde no lo tiene (una magnitud que simplemente es negativa).

   El color por signo solo es correcto cuando el número ES un cambio y subir es
   bueno. Así que aquí hay que elegirlo a propósito:

     tono="auto"      → el número es una variación y subir es bueno (precio, P&L).
     tono="ninguno"   → es una magnitud, no una dirección (EPS, PER, volumen).
                        Es el valor por DEFECTO: teñir de color hay que pedirlo.
     tono="invertido" → es una variación pero subir es MALO (deuda, gastos, riesgo).
     tono="sube" | "baja" | "aviso" | ... → forzado, cuando lo decide otra lógica.

   Que el defecto sea "sin color" es la mitad del arreglo: obliga a pensarlo una vez
   por métrica, en vez de heredar un verde que nadie decidió. */

const CLASES_TONO = {
  sube: "text-sube",
  baja: "text-baja",
  aviso: "text-aviso",
  info: "text-info",
  neutro: "text-tinta",
  ninguno: "text-tinta",
};

function resolverTono(tono, valorNumerico) {
  if (tono === "auto") return tonoDelSigno(valorNumerico);
  if (tono === "invertido") {
    const t = tonoDelSigno(valorNumerico);
    return t === "sube" ? "baja" : t === "baja" ? "sube" : "neutro";
  }
  return tono || "ninguno";
}

export default function Metrica({
  etiqueta,
  valor,
  sufijo,
  detalle,
  tono = "ninguno",
  valorNumerico,
  tamano = "md",
  ayuda,
  className,
}) {
  // El número que decide el color puede no ser el que se enseña: se muestra
  // "+2.40%" ya formateado, pero para el signo hace falta el número de verdad.
  const num = valorNumerico !== undefined ? valorNumerico : Number(valor);
  const claveTono = resolverTono(tono, num);
  const vacio = valor === null || valor === undefined || valor === "" || valor === SIN_DATO;

  const tamanos = {
    sm: "text-apoyo",
    md: "text-cuerpo",
    lg: "text-cifra",
  };

  return (
    <div className={cn("min-w-0", className)}>
      {etiqueta && (
        <p className="iv-etiqueta truncate" title={ayuda || undefined}>
          {etiqueta}
        </p>
      )}
      <p
        className={cn(
          "iv-cifra font-semibold mt-0.5",
          tamanos[tamano],
          // Un dato ausente nunca se tiñe: "—" en rojo parecería un valor malo.
          vacio ? "text-tinta-3" : CLASES_TONO[claveTono] || CLASES_TONO.ninguno
        )}
      >
        {vacio ? SIN_DATO : valor}
        {!vacio && sufijo && <span className="text-tinta-3 font-normal ml-0.5">{sufijo}</span>}
      </p>
      {detalle && <p className="text-apoyo text-tinta-3 mt-0.5 truncate">{detalle}</p>}
    </div>
  );
}
