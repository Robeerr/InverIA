import React from "react";

/**
 * Qué documentos leyó el modelo en una investigación, exactamente.
 *
 * POR QUÉ HACE FALTA
 *
 * Hasta la lectura de anexos, el modelo veía solo el documento principal del 8-K. Ahora
 * puede ver además hasta dos EX-99 —las notas de prensa—. Sin esta línea, una lectura con
 * anexo y otra sin él se ven iguales, y no se podría saber si una incertidumbre del
 * modelo es un hueco del documento o un anexo que no se descargó.
 *
 * LAS INVESTIGACIONES ANTERIORES LO DICEN, NO LO CALLAN
 *
 * Las hechas antes de este cambio no tienen el campo, y esa ausencia ES el dato: se
 * hicieron leyendo solo el principal. Se escribe, porque es lo que separa las dos etapas
 * de la muestra de `PROMPT_V = 2`.
 */
export default function DocumentosEnviados({ documentos, anexos, anterior = false }) {
  if (!documentos?.length) {
    if (!anterior) return null;
    return (
      <p className="mt-2 text-xs text-tinta-3" data-testid="documentos-anterior">
        Investigación anterior a la lectura de anexos: el modelo leyó solo el documento
        principal.
      </p>
    );
  }
  const total = documentos.reduce((s, d) => s + (d.caracteres_enviados || 0), 0);
  return (
    <div className="mt-2 text-xs text-tinta-3" data-testid="documentos-enviados">
      <p className="iv-etiqueta">Lo que leyó el modelo · {total} caracteres</p>
      <ul className="mt-1 space-y-0.5">
        {documentos.map((d) => (
          <li key={d.url || d.documento} className="flex flex-wrap gap-x-2">
            <span className="iv-cifra text-tinta-2">{d.tipo || "—"}</span>
            {d.url ? (
              <a href={d.url} target="_blank" rel="noopener noreferrer"
                 className="text-marca hover:underline break-all">{d.documento}</a>
            ) : <span>{d.documento}</span>}
            <span className="iv-cifra">
              {d.caracteres_enviados}
              {d.recortado && ` de ${d.caracteres_extraidos} · recortado`}
            </span>
          </li>
        ))}
      </ul>
      {/* Por qué no hay anexo, si no lo hay. «No había EX-99» y «no se pudo leer el
          índice» son cosas distintas, y solo la segunda es un problema nuestro. */}
      {documentos.length === 1 && anexos?.motivo && (
        <p className="mt-1">Sin anexos: {anexos.motivo}.</p>
      )}
      {!!anexos?.fallos?.length && (
        <p className="mt-1 text-baja">
          {anexos.fallos.length} anexo(s) no se pudieron descargar:{" "}
          {anexos.fallos.map((f) => `${f.tipo} (${f.error})`).join(", ")}.
        </p>
      )}
    </div>
  );
}
