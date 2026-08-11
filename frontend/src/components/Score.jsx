import React, { useState } from "react";
import { api } from "../lib/api";

/**
 * El score de potencial, con su desglose bajo demanda.
 *
 * POR QUÉ EXISTE
 *
 * Un número de 0 a 100 sin denominador no se puede discutir. La descomposición ya se
 * calculaba dentro del motor y se tiraba; ahora el escaneo la guarda y este componente la
 * pide cuando alguien la abre.
 *
 * CERRADO SE VE EXACTAMENTE COMO ANTES
 *
 * El chip que envuelve es el mismo que ya había, con sus colores y su texto. Lo único que
 * se añade es que ahora se puede pulsar. Quien no lo abra no nota nada, y —lo que importa
 * de verdad— no se pide nada: la petición ocurre en el primer clic y solo una vez.
 *
 * AQUÍ NO SE CALCULA NADA
 *
 * Ni umbrales, ni sumas, ni reconstrucción del score. El backend manda los puntos, los
 * máximos, el multiplicador y su motivo; esto los pinta. Si esta pantalla recalculara,
 * habría dos verdades y ganaría la de aquí sin que nadie se enterase.
 */

function Barra({ puntos, maximo }) {
  const pct = maximo > 0 ? Math.max(0, Math.min(100, (puntos / maximo) * 100)) : 0;
  return (
    <div className="h-1 rounded-full bg-linea overflow-hidden w-full">
      <div className="h-full bg-marca/70" style={{ width: `${pct}%` }} />
    </div>
  );
}

function Componente({ c }) {
  return (
    <div className="py-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] text-tinta">{c.etiqueta}</span>
        <span className="text-[10.5px] font-mono text-tinta-3 shrink-0">
          {c.puntos} <span className="opacity-60">/ {c.maximo}</span>
        </span>
      </div>
      <div className="mt-1"><Barra puntos={c.puntos} maximo={c.maximo} /></div>
      {c.detalle && (
        <p className="text-[10px] text-tinta-3 mt-0.5 leading-snug">{c.detalle}</p>
      )}
    </div>
  );
}

export default function Score({ symbol, children }) {
  const [abierto, setAbierto] = useState(false);
  const [datos, setDatos] = useState(null);
  const [estado, setEstado] = useState("inicial");   // inicial | cargando | listo | vacio | error

  const alternar = async (e) => {
    // El chip vive dentro de una tarjeta que navega al pulsarla: sin esto, abrir el
    // desglose cambiaría de acción.
    e.stopPropagation();
    if (abierto) { setAbierto(false); return; }
    setAbierto(true);
    if (datos || estado === "cargando") return;      // una sola petición por tarjeta

    setEstado("cargando");
    try {
      const d = await api.desgloseScore(symbol);
      setDatos(d);
      setEstado("listo");
    } catch (err) {
      // 404 no es un fallo: el escaneo del screener aún no ha pasado por este símbolo.
      setEstado(err?.response?.status === 404 ? "vacio" : "error");
    }
  };

  const d = datos?.desglose;

  return (
    <div className="flex flex-col items-end shrink-0">
      <button
        type="button"
        onClick={alternar}
        data-testid={`score-${symbol}`}
        aria-expanded={abierto}
        title={abierto ? "Ocultar el desglose" : "Ver de dónde salen estos puntos"}
        aria-label={abierto
          ? `Ocultar el desglose de la puntuación de ${symbol}`
          : `Ver el desglose de la puntuación de ${symbol}`}
        className="text-left cursor-pointer group"
      >
        {children}
        {/* El chip no parecía pulsable: se veía como una etiqueta más. Este rótulo lo
            dice, y cambia con el estado para que se sepa que se puede volver a cerrar.
            Va aquí y no en la tarjeta porque depende de `abierto`. */}
        <span className="block text-[9px] text-tinta-3 mt-0.5 text-right
                         group-hover:text-marca transition-colors">
          {abierto ? "ocultar ▴" : "ver desglose ▾"}
        </span>
      </button>

      {abierto && (
        <div
          className="mt-2 w-full min-w-[220px] iv-panel p-3 text-left"
          onClick={(e) => e.stopPropagation()}
          data-testid={`score-desglose-${symbol}`}
        >
          {estado === "cargando" && (
            <p className="text-[11px] text-tinta-3">Cargando el desglose…</p>
          )}

          {estado === "vacio" && (
            <p className="text-[11px] text-tinta-3 leading-snug">
              El desglose no está en el escaneo actual. Se calculará en el próximo.
            </p>
          )}

          {estado === "error" && (
            <p className="text-[11px] text-baja leading-snug">
              No se ha podido cargar el desglose.
            </p>
          )}

          {estado === "listo" && d && (
            <>
              <div className="flex items-baseline justify-between gap-2 pb-1.5 mb-1 border-b border-linea">
                <span className="text-[9.5px] font-mono uppercase tracking-wider text-tinta-3">
                  De dónde salen los puntos
                </span>
                <span className="text-[10.5px] font-mono text-tinta-3">
                  {d.bruto} brutos
                </span>
              </div>

              {(d.componentes || []).map((c) => <Componente key={c.clave} c={c} />)}

              {/* El guardián de tendencia NO es un componente: multiplica la suma. Se
                  enseña aparte porque es lo que explica que una empresa con buenos
                  fundamentales acabe puntuando bajo. */}
              {d.multiplicador != null && d.multiplicador !== 1 && (
                <div className="mt-2 pt-2 border-t border-linea">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[11px] text-aviso font-medium">
                      Guardián de tendencia
                    </span>
                    <span className="text-[10.5px] font-mono text-aviso shrink-0">
                      ×{d.multiplicador}
                    </span>
                  </div>
                  {d.motivo_multiplicador && (
                    <p className="text-[10px] text-tinta-3 mt-0.5 leading-snug">
                      {d.motivo_multiplicador}
                    </p>
                  )}
                </div>
              )}

              {d.recortado && (
                <p className="text-[10px] text-tinta-3 mt-2 leading-snug">
                  La suma pasaba de 100 y se ha recortado al tope.
                </p>
              )}

              {datos.generado_en && (
                <p className="text-[9.5px] font-mono text-tinta-3 mt-2 pt-2 border-t border-linea">
                  del escaneo de las {new Date(datos.generado_en).toLocaleTimeString("es-ES",
                    { hour: "2-digit", minute: "2-digit" })}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
