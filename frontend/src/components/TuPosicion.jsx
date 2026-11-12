import React from "react";
import { Wallet } from "lucide-react";
import { fmtPrice, fmtNum, fmtPct } from "../lib/format";
import { posicionDe } from "../lib/posicion";
import CabeceraBloque from "./base/CabeceraBloque";

/**
 * Tu posición en esta acción: el bloque 04 de la arquitectura.
 *
 * No cuesta NADA. `/signals` ya se pide una vez por sesión y se comparte entre
 * páginas; la página de acción hasta ahora calculaba la fila del símbolo abierto en
 * un `useState` que no leía nadie. El dato estaba en memoria y se tiraba.
 *
 * Va en la columna de «tu dinero», junto al simulador de margen: un nivel a un 5% no
 * significa lo mismo si tienes dinero dentro que si no.
 *
 * Si no hay posición no se pinta nada. Tener la acción en la tabla de seguimiento con
 * unos niveles apuntados NO es tener dinero dentro; la distinción vive en
 * `posicionDe()`, que devuelve null en ese caso.
 */
export default function TuPosicion({ signals, symbol, quote }) {
  const pos = posicionDe(signals, symbol, quote?.price);
  if (!pos) return null;

  const gana = pos.plAbs != null && pos.plAbs >= 0;
  const tono = pos.plAbs == null ? "text-tinta-3" : gana ? "text-sube" : "text-baja";

  // El latente es la cifra que se viene a mirar y va grande; lo demás es desglose en
  // filas, con la cifra alineada a la derecha en dígitos tabulares. Si una cifra de
  // siete dígitos no cabe junto a su rótulo, baja de línea en vez de salirse.
  return (
    <section className="iv-panel p-5" data-testid="tu-posicion" aria-labelledby="tu-posicion-titulo">
      <CabeceraBloque icono={Wallet} como="h3" id="tu-posicion-titulo"
        derecha={<span className="iv-cifra text-[12px] text-tinta-3">{fmtNum(pos.acciones)} acc.</span>}>
        Tu posición
      </CabeceraBloque>

      <p className="iv-etiqueta mt-4">
        Latente{pos.divisa ? ` · ${pos.divisa}` : ""}
      </p>
      {pos.plAbs != null ? (
        <div data-testid="tu-posicion-pl" className="mt-1.5 flex items-baseline gap-x-2.5 gap-y-1 flex-wrap">
          <p className={`iv-cifra-hero text-[32px] leading-none tracking-[-0.04em] break-all ${tono}`}>
            {gana ? "+" : "−"}${fmtPrice(Math.abs(pos.plAbs))}
          </p>
          {pos.plPct != null && (
            <p className={`iv-cifra text-[13px] font-medium ${tono}`}>{fmtPct(pos.plPct)}</p>
          )}
        </div>
      ) : (
        <p className="text-[13px] text-tinta-3 mt-1.5">Sin precio actual para calcular el latente.</p>
      )}

      <dl className="mt-4 divide-y divide-suave border-t border-suave">
        <Fila etiqueta="Acciones" valor={fmtNum(pos.acciones)} />
        <Fila etiqueta="Precio medio" valor={`$${fmtPrice(pos.compra)}`} />
        <Fila etiqueta="Invertido" valor={`$${fmtPrice(pos.invertido)}`} />
        {pos.valor != null && <Fila etiqueta="Valor ahora" valor={`$${fmtPrice(pos.valor)}`} />}
      </dl>

      {/* Los peldaños que tienes apuntados. No se marca ninguno como comprado: la
          tabla guarda el precio MEDIO, no qué nivel se ejecutó, y deducirlo sería
          inventar un dato que no existe. */}
      {pos.niveles.length > 0 && (
        <div className="mt-3 pt-3.5 border-t border-suave">
          <p className="iv-etiqueta mb-2">Tus niveles</p>
          <ul className="grid grid-cols-2 gap-1.5">
            {pos.niveles.map((n) => (
              <li key={n.etiqueta} className="flex items-baseline justify-between gap-2 rounded-iv-sm bg-tinta/[0.04] px-2.5 py-1.5 min-w-0">
                <span className="text-[12px] text-tinta-3 whitespace-nowrap">{n.etiqueta}</span>
                <span className="iv-cifra text-[12.5px] text-tinta truncate">${fmtPrice(n.precio)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {pos.notas && (
        <p className="mt-3 text-[13px] text-tinta-3 leading-snug italic">{pos.notas}</p>
      )}
    </section>
  );
}

function Fila({ etiqueta, valor }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 py-2">
      <dt className="text-[13px] text-tinta-3">{etiqueta}</dt>
      <dd className="iv-cifra text-[13px] text-tinta ml-auto text-right break-all">{valor}</dd>
    </div>
  );
}
