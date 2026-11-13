import React from "react";
import { cn } from "@/lib/utils";

/* FranjaDias · un horizonte de N días leído de un vistazo
   ─────────────────────────────────────────────────────────────────────────────
   Una pista horizontal de «hoy» a «+N días» con una marca por día y un punto por
   cada fecha con eventos. Sirve para ver la FORMA del periodo (todo junto la semana
   que viene, o repartido) antes de leer la lista. No sustituye a la lista: es
   decorativa para el lector de pantalla (`aria-hidden`), la información está debajo.

   `eventos`: [{ offset, etiquetas: ["NVDA", …], tono: "marca" | "neutro" }]
   `offset` en días desde hoy; lo que cae fuera del horizonte se pega al borde.
   Las etiquetas solo se ven a partir de `sm`: en móvil el punto lleva el recuento. */

const TONO_PUNTO = {
  marca: "bg-marca border-marca shadow-[0_0_0_3px_rgb(var(--iv-intencion)/0.18)]",
  neutro: "bg-superficie border-tinta-2",
  // Fechas ya pasadas (se pegan a «Hoy»): presentes pero apagadas.
  pasado: "bg-superficie border-tinta-3 opacity-60",
};

const TONO_ETIQUETA = {
  marca: "text-marca",
  neutro: "text-tinta-2",
  pasado: "text-tinta-3 opacity-70",
};

export default function FranjaDias({ dias, eventos = [], className }) {
  const n = Math.max(1, dias || 1);
  const pos = (offset) => `${(Math.min(Math.max(offset, 0), n) / n) * 100}%`;
  // Con 60 días una marca por día es ruido: se dibuja una por semana.
  const paso = n > 31 ? 7 : 1;
  const marcas = [];
  for (let d = 0; d <= n; d += paso) marcas.push(d);

  return (
    <div aria-hidden="true" className={cn("select-none", className)}>
      <div className="relative h-[76px] sm:h-[92px] mx-1.5">
        {/* Pista */}
        <div className="absolute left-0 right-0 bottom-[26px] h-px bg-tinta/[0.12]" />
        {/* Tramo de hoy al último evento, en luz de intención muy baja */}
        {eventos.length > 0 && (
          <div
            className="absolute left-0 bottom-[25px] h-[3px] rounded-full bg-marca/25"
            style={{ width: pos(Math.max(...eventos.map((e) => e.offset))) }}
          />
        )}
        {/* Marcas de día */}
        {marcas.map((d) => (
          <span
            key={d}
            className={cn("absolute bottom-[22px] w-px -translate-x-1/2",
              d === 0 ? "h-[9px] bg-tinta-2" : "h-[5px] bg-tinta/[0.18]")}
            style={{ left: pos(d) }}
          />
        ))}
        {/* Eventos */}
        {eventos.map((e) => {
          const tono = TONO_PUNTO[e.tono] ? e.tono : "neutro";
          const izquierda = e.offset / n;
          // Cerca de los bordes, la etiqueta se ancla hacia dentro para no salirse.
          const ancla = izquierda < 0.08 ? "left-0" : izquierda > 0.92 ? "right-0" : "left-1/2 -translate-x-1/2";
          return (
            <div key={e.offset} className="absolute bottom-[21px] -translate-x-1/2" style={{ left: pos(e.offset) }}>
              <div className={cn("hidden sm:flex absolute bottom-[18px] flex-col items-center gap-0.5", ancla,
                                 izquierda < 0.08 && "items-start", izquierda > 0.92 && "items-end")}>
                {e.etiquetas.slice(0, 3).map((t) => (
                  <span key={t} className={cn("iv-cifra text-[11px] font-semibold leading-none whitespace-nowrap",
                                              TONO_ETIQUETA[tono])}>
                    {t}
                  </span>
                ))}
                {e.etiquetas.length > 3 && (
                  <span className="iv-cifra text-[10.5px] text-tinta-3 leading-none">+{e.etiquetas.length - 3}</span>
                )}
              </div>
              <span className={cn("block w-[11px] h-[11px] rounded-full border-2", TONO_PUNTO[tono])} />
              {e.etiquetas.length > 1 && (
                <span className="sm:hidden absolute bottom-[16px] left-1/2 -translate-x-1/2 iv-cifra text-[10.5px] text-tinta-2 leading-none">
                  {e.etiquetas.length}
                </span>
              )}
            </div>
          );
        })}
        {/* Eje */}
        <div className="absolute left-0 right-0 bottom-0 flex justify-between text-[11.5px] text-tinta-3 leading-none">
          <span className="text-tinta-2 font-medium">Hoy</span>
          {n >= 14 && <span className="iv-cifra">+{Math.round(n / 2)} d</span>}
          <span className="iv-cifra">+{n} d</span>
        </div>
      </div>
    </div>
  );
}
