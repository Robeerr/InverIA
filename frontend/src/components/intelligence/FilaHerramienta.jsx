import React from "react";

/**
 * Una comprobación manual, como fila de panel.
 *
 * Las cuatro herramientas de diagnóstico (comprobar, sondear EDGAR, plan de
 * investigación, tabla de tickers) comparten forma: qué hace a la izquierda, el botón
 * que lo lanza a la derecha y, debajo, el resultado cuando lo hay. Antes cada una era un
 * bloque suelto con su propia cabecera de sección; juntas en un panel con filetes se leen
 * como lo que son —un cajón de herramientas— y no como cuatro secciones más de la página.
 *
 * Solo maqueta: el texto, el botón y el resultado los pone cada componente.
 */
export default function FilaHerramienta({ titulo, descripcion, accion, children, ...props }) {
  return (
    <div className="px-4 sm:px-5 py-4 min-w-0" {...props}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div className="min-w-0 max-w-[70ch]">
          {titulo && (
            <h3 className="text-apoyo font-semibold text-tinta">{titulo}</h3>
          )}
          <div className={`text-xs text-tinta-3 leading-relaxed ${titulo ? "mt-1" : ""}`}>
            {descripcion}
          </div>
        </div>
        {accion && <div className="shrink-0">{accion}</div>}
      </div>
      {children}
    </div>
  );
}
