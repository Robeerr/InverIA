import React from "react";

/**
 * El estado de confluencia entre tus fuentes y la elegibilidad estructural.
 *
 * Se pinta igual en los dos sitios donde aparece —el panel de fuentes de una acción y
 * las tarjetas del radar— para que el mismo estado no se lea de dos maneras. Toda la
 * clasificación la hace el backend (`confluencia.py`); aquí no se decide nada, ni se
 * recalcula un umbral, ni se deriva un estado de los números sueltos.
 *
 * DOS ESTADOS NO SE PINTAN, Y ES DELIBERADO
 *
 * `NEUTRAL` y `SIN_FUENTES` no tienen nada que contar: significan «no se ha cruzado
 * nada» y «nadie ha hablado de esto». El backend ya devuelve `texto: null` en ambos, y
 * un chip gris que dijera «neutral» en cada tarjeta se convertiría en ruido de fondo —
 * exactamente lo que hace que se deje de mirar la señal cuando sí aparece.
 *
 * QUÉ CAMBIÓ
 *
 * El cruce ya no es contra un score del motor con cortes en 65/45, sino contra la
 * ELEGIBILIDAD estructural que decide `tendencia.py`. `INSUFICIENTE` pasa de significar
 * «el motor no lo ha puntuado» a «no se puede clasificar la tendencia».
 *
 * EL CHOQUE NO ES «MALO»
 *
 * Va en tono de aviso y no en el rojo de «baja», que en esta app significa que el precio
 * cae. Un choque es que tus dos fuentes de criterio discrepan, y eso es información
 * valiosa: es el único caso donde la app puede evitarte una decisión mala en vez de
 * acompañarte en una buena.
 */

export const ESTILO = {
  ACUERDO:      { texto: "text-sube",   fondo: "bg-sube/10",   borde: "border-sube/30",   etiqueta: "Acuerdo" },
  CHOQUE:       { texto: "text-aviso",  fondo: "bg-aviso/10",  borde: "border-aviso/35",  etiqueta: "Choque" },
  MIXTO:        { texto: "text-tinta-2", fondo: "bg-linea/40", borde: "border-linea",     etiqueta: "Fuentes divididas" },
  INSUFICIENTE: { texto: "text-tinta-3", fondo: "bg-linea/30", borde: "border-linea",     etiqueta: "Sin tendencia" },
  NEUTRAL:      null,
  SIN_FUENTES:  null,
};

export default function Confluencia({ confluencia, compacto = false, className = "" }) {
  const estilo = confluencia ? ESTILO[confluencia.estado] : null;
  if (!estilo) return null;

  if (compacto) {
    // En las tarjetas del radar solo cabe la etiqueta. La frase completa va en el título
    // del elemento, para que se pueda leer sin abandonar la rejilla.
    return (
      <span
        title={confluencia.texto || estilo.etiqueta}
        data-testid={`confluencia-${confluencia.estado.toLowerCase()}`}
        className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9.5px] font-mono
          font-bold uppercase tracking-wider shrink-0 border
          ${estilo.fondo} ${estilo.texto} ${estilo.borde} ${className}`}
      >
        {estilo.etiqueta}
      </span>
    );
  }

  return (
    <div
      data-testid={`confluencia-${confluencia.estado.toLowerCase()}`}
      className={`rounded-md border px-3 py-2 ${estilo.fondo} ${estilo.borde} ${className}`}
    >
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className={`text-[9.5px] font-mono font-bold uppercase tracking-wider ${estilo.texto}`}>
          {estilo.etiqueta}
        </span>
        <span className="text-[9.5px] font-mono uppercase tracking-wider text-tinta-3">
          tendencia ↔ fuentes
        </span>
      </div>
      {confluencia.texto && (
        <p className="text-[12px] text-tinta leading-snug mt-1">{confluencia.texto}</p>
      )}
    </div>
  );
}
