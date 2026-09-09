import React from "react";
import { estadoDe } from "../../lib/intelligence";
import { fmtHace } from "../../lib/format";

/**
 * Una fuente, con su estado dicho en castellano y sin adornos.
 *
 * POR QUÉ ESTA FILA EXISTE APARTE DEL RADAR
 *
 * El radar dice DÓNDE está cada fuente y si late. Esto dice qué le pasa: hace cuánto habló,
 * qué entró en su última vuelta y, si falla, cuál es el error tal cual. Sin esta fila, un
 * punto apagado en el radar no se distingue de un punto que nunca ha existido.
 *
 * «SIN CONECTAR» NO ES UN ERROR
 *
 * Se pinta en gris de texto secundario y no en rojo, porque no hay nada roto: falta una
 * variable de entorno. El rojo se reserva para lo que de verdad ha fallado — si las dos
 * cosas se vieran igual, arreglar una configuración y perseguir una caída serían la misma
 * tarea a ojos del usuario.
 */
export default function RadarFuente({ fuente }) {
  const e = estadoDe(fuente);
  const ciclo = fuente.ultimo_ciclo;

  return (
    <div className="py-3 border-b border-linea last:border-0"
         data-testid={`radar-fuente-${fuente.fuente}`}>
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <span className="text-sm font-semibold text-tinta">{fuente.nombre}</span>
          {/* El tier es la fiabilidad de la fuente, no su velocidad. Va aquí porque es lo
              que decide cuánto pesa lo que dice. */}
          <span className="iv-etiqueta ml-2">Tier {fuente.tier}</span>
        </div>
        <span className={`iv-etiqueta whitespace-nowrap ${e.clase}`}>{e.etiqueta}</span>
      </div>

      <div className="mt-1.5 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs text-tinta-3">
        {fuente.actualizado_en
          ? <span>Última vuelta {fmtHace(fuente.actualizado_en)}</span>
          : <span>Todavía no ha dado ninguna vuelta</span>}
        <span className="iv-cifra">cada {Math.round((fuente.intervalo_s || 0) / 60)} min</span>
        {fuente.espera_s > 0 && (
          <span className="text-aviso">
            esperando {Math.round(fuente.espera_s / 60)} min antes de reintentar
          </span>
        )}
      </div>

      {/* El recuento de la última vuelta. Es lo que distingue «no ha pasado nada» de «mi
          filtro se lo ha comido todo»: sin estos números las dos cosas son un silencio. */}
      {ciclo && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs iv-cifra text-tinta-2">
          <span>{ciclo.recibidos ?? 0} leídos</span>
          <span>{ciclo.nuevos ?? 0} nuevos</span>
          <span className={ciclo.significativos ? "text-marca" : ""}>
            {ciclo.significativos ?? 0} te afectan
          </span>
          <span className="text-tinta-3">{ciclo.descartados ?? 0} descartados</span>
        </div>
      )}

      {/* El error, literal. Resumirlo o traducirlo a «algo ha ido mal» quitaría lo único
          que sirve para arreglarlo. */}
      {fuente.estado === "NO_CONFIGURADA" ? (
        <p className="mt-2 text-xs text-tinta-3">
          Falta su variable de entorno. Mientras no esté, esta fuente no hace ni una
          petición: no está fallando, está sin conectar.
        </p>
      ) : null}
    </div>
  );
}
