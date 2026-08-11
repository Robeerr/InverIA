import React from "react";
import { fmtPrice, fmtNum, fmtPct } from "../lib/format";
import { posicionDe } from "../lib/posicion";

/**
 * Tu posición en esta acción: el bloque 04 de la arquitectura.
 *
 * No cuesta NADA. `/signals` ya se pide una vez por sesión y se comparte entre
 * páginas; la página de acción hasta ahora calculaba la fila del símbolo abierto en
 * un `useState` que no leía nadie. El dato estaba en memoria y se tiraba.
 *
 * Va por encima de Niveles a propósito: un nivel a un 5% no significa lo mismo si
 * tienes dinero dentro que si no, así que hay que saberlo ANTES de leerlos.
 *
 * Si no hay posición no se pinta nada. Tener la acción en la tabla de seguimiento con
 * unos niveles apuntados NO es tener dinero dentro; la distinción vive en
 * `posicionDe()`, que devuelve null en ese caso.
 */
export default function TuPosicion({ signals, symbol, quote }) {
  const pos = posicionDe(signals, symbol, quote?.price);
  if (!pos) return null;

  const gana = pos.plAbs != null && pos.plAbs >= 0;
  const tono = pos.plAbs == null ? "text-[#5c6b66]" : gana ? "text-[#4a7c59]" : "text-[#d85c41]";

  return (
    <section className="card-flat px-4 py-3" data-testid="tu-posicion">
      <div className="flex items-baseline gap-2 mb-2.5">
        <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono">
          Tu posición
        </span>
        {pos.divisa && (
          <span className="text-[10px] text-[#5c6b66] font-mono">· {pos.divisa}</span>
        )}
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-2.5">
        <div className="flex flex-col gap-0.5">
          <span className="text-[9.5px] uppercase tracking-[0.14em] text-[#5c6b66] font-mono">Acciones</span>
          <span className="text-[13px] font-mono text-[#0e1f1a]">{fmtNum(pos.acciones)}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9.5px] uppercase tracking-[0.14em] text-[#5c6b66] font-mono">Precio medio</span>
          <span className="text-[13px] font-mono text-[#0e1f1a]">${fmtPrice(pos.compra)}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[9.5px] uppercase tracking-[0.14em] text-[#5c6b66] font-mono">Invertido</span>
          <span className="text-[13px] font-mono text-[#0e1f1a]">${fmtPrice(pos.invertido)}</span>
        </div>
        {pos.valor != null && (
          <div className="flex flex-col gap-0.5">
            <span className="text-[9.5px] uppercase tracking-[0.14em] text-[#5c6b66] font-mono">Valor ahora</span>
            <span className="text-[13px] font-mono text-[#0e1f1a]">${fmtPrice(pos.valor)}</span>
          </div>
        )}
        {pos.plAbs != null && (
          <div className="flex flex-col gap-0.5" data-testid="tu-posicion-pl">
            <span className="text-[9.5px] uppercase tracking-[0.14em] text-[#5c6b66] font-mono">Latente</span>
            <span className={`text-[13px] font-mono font-semibold ${tono}`}>
              {gana ? "+" : "−"}${fmtPrice(Math.abs(pos.plAbs))}
              {pos.plPct != null && <span className="ml-1.5">({fmtPct(pos.plPct)})</span>}
            </span>
          </div>
        )}
      </div>

      {/* Los peldaños que tienes apuntados. No se marca ninguno como comprado: la
          tabla guarda el precio MEDIO, no qué nivel se ejecutó, y deducirlo sería
          inventar un dato que no existe. */}
      {pos.niveles.length > 0 && (
        <div className="mt-3 pt-2.5 border-t border-[#e5e0d8] flex flex-wrap gap-x-4 gap-y-1">
          <span className="text-[9.5px] uppercase tracking-[0.14em] text-[#5c6b66] font-mono">
            Tus niveles
          </span>
          {pos.niveles.map((n) => (
            <span key={n.etiqueta} className="text-[12px] font-mono text-[#5c6b66]">
              {n.etiqueta} <span className="text-[#0e1f1a]">${fmtPrice(n.precio)}</span>
            </span>
          ))}
        </div>
      )}

      {pos.notas && (
        <p className="mt-2.5 text-[12px] text-[#5c6b66] leading-snug italic">{pos.notas}</p>
      )}
    </section>
  );
}
