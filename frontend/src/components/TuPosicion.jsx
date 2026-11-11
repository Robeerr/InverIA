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
  const tono = pos.plAbs == null ? "text-tinta-3" : gana ? "text-sube" : "text-baja";

  // Mismo lenguaje que «Tu cartera» en Hoy: el latente es la cifra que se viene a mirar
  // y va grande; lo demás es desglose en filas, con la cifra alineada a la derecha en
  // dígitos tabulares. Si una cifra de siete dígitos no cabe junto a su rótulo, baja de
  // línea en vez de salirse de la tarjeta.
  return (
    <section className="iv-panel p-5" data-testid="tu-posicion" aria-labelledby="tu-posicion-titulo">
      <div className="grid gap-x-8 gap-y-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="min-w-0">
          {/* La cabecera de sección ya dice «Tu posición»: aquí el rótulo nombra la cifra
              grande, para que no se lea como lo invertido ni como el valor. */}
          <h3 id="tu-posicion-titulo" className="sr-only">Tu posición</h3>
          <p className="iv-etiqueta">
            Latente{pos.divisa ? ` · ${pos.divisa}` : ""}
          </p>
          {pos.plAbs != null ? (
            <div data-testid="tu-posicion-pl" className="mt-2">
              <p className={`iv-cifra font-semibold text-cifra leading-none break-all ${tono}`}>
                {gana ? "+" : "−"}${fmtPrice(Math.abs(pos.plAbs))}
              </p>
              {pos.plPct != null && (
                <p className={`iv-cifra text-apoyo font-semibold mt-1.5 ${tono}`}>({fmtPct(pos.plPct)})</p>
              )}
            </div>
          ) : (
            <p className="text-apoyo text-tinta-3 mt-2">Sin precio actual para calcular el latente.</p>
          )}
        </div>

        <dl className="min-w-0 divide-y divide-linea md:border-l md:border-linea md:pl-8">
          <Fila etiqueta="Acciones" valor={fmtNum(pos.acciones)} />
          <Fila etiqueta="Precio medio" valor={`$${fmtPrice(pos.compra)}`} />
          <Fila etiqueta="Invertido" valor={`$${fmtPrice(pos.invertido)}`} />
          {pos.valor != null && <Fila etiqueta="Valor ahora" valor={`$${fmtPrice(pos.valor)}`} />}
        </dl>
      </div>

      {/* Los peldaños que tienes apuntados. No se marca ninguno como comprado: la
          tabla guarda el precio MEDIO, no qué nivel se ejecutó, y deducirlo sería
          inventar un dato que no existe. */}
      {pos.niveles.length > 0 && (
        <div className="mt-4 pt-3 border-t border-linea">
          <p className="iv-etiqueta mb-1.5">Tus niveles</p>
          <ul className="flex flex-wrap gap-x-5 gap-y-1">
            {pos.niveles.map((n) => (
              <li key={n.etiqueta} className="text-apoyo text-tinta-3 whitespace-nowrap">
                {n.etiqueta} <span className="iv-cifra text-tinta">${fmtPrice(n.precio)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {pos.notas && (
        <p className="mt-3 text-apoyo text-tinta-3 leading-snug italic max-w-[70ch]">{pos.notas}</p>
      )}
    </section>
  );
}

function Fila({ etiqueta, valor }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 py-1.5">
      <dt className="text-apoyo text-tinta-2">{etiqueta}</dt>
      <dd className="iv-cifra text-apoyo font-semibold text-tinta ml-auto text-right break-all">{valor}</dd>
    </div>
  );
}
