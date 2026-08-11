import React from "react";
import { fmtHace } from "../lib/format";
import { titularVivo } from "../lib/tesisVivo";

/**
 * La tesis determinista, en frío.
 *
 * Es el bloque 02 de la arquitectura y responde «qué está pasando y por qué» sin
 * pulsar nada ni esperar a ningún modelo. El backend la redacta dentro del propio
 * dashboard (`tesis.redactar`), así que llega en la misma respuesta que el precio.
 *
 * DOS RELOJES EN PANTALLA. La cabecera de arriba va en vivo por WebSocket y esta
 * tesis es una foto del momento en que se ensambló el dashboard, que puede tener
 * media hora si se sirvió de caché. Por eso el sello de antigüedad NO es decoración:
 * es lo que convierte esa discrepancia en información en vez de en un fallo aparente.
 *
 * El botón de IA vive aquí dentro, como acción secundaria, porque la IA AMPLÍA esta
 * tesis. Antes era una banda a ancho completo en mitad de la página, y con ella
 * apagada media pantalla no existía.
 */
export default function TesisPanel({
  tesis,
  quote,
  generadoEn,
  onAnalizar,
  loadingAnalysis,
  tieneAnalisis,
}) {
  if (!tesis) return null;

  const limita = tesis.limita_confianza;
  // El precio del titular sale del MISMO quote que la cabecera, no del que venia dentro
  // de la frase: el dashboard se sirve cacheado y ese precio puede tener media hora.
  const titular = titularVivo(tesis, quote);

  return (
    <section className="card-flat p-5 animate-fade-up" data-testid="tesis">
      <div className="flex items-baseline gap-3 flex-wrap mb-2">
        <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono">
          Qué está pasando
        </span>
        {generadoEn && (
          <span
            className="text-[10px] text-[#5c6b66] font-mono ml-auto"
            title="Cuándo se calculó el análisis. La cotización de arriba va en vivo; esto es una foto de ese momento."
            data-testid="tesis-antiguedad"
          >
            calculado {fmtHace(generadoEn)}
          </span>
        )}
      </div>

      <p className="text-[15px] leading-snug text-[#0e1f1a] font-medium" data-testid="tesis-titular">
        {titular}
      </p>

      {(tesis.parrafos || []).map((p, i) => (
        <p key={i} className="text-[13.5px] text-[#5c6b66] leading-relaxed mt-2">
          {p}
        </p>
      ))}

      {/* Comprobaciones binarias, cada una con el dato que la sostiene dentro del texto. */}
      {(tesis.a_favor?.length > 0 || tesis.en_contra?.length > 0) && (
        <div className="grid sm:grid-cols-2 gap-x-5 gap-y-1.5 mt-4">
          <div>
            {(tesis.a_favor || []).map((s, i) => (
              <p key={i} className="text-[12.5px] text-[#0e1f1a] leading-snug flex gap-1.5">
                <span className="text-[#4a7c59] font-bold shrink-0" aria-hidden="true">+</span>
                <span>{s.texto}</span>
              </p>
            ))}
          </div>
          <div>
            {(tesis.en_contra || []).map((s, i) => (
              <p key={i} className="text-[12.5px] text-[#0e1f1a] leading-snug flex gap-1.5">
                <span className="text-[#d85c41] font-bold shrink-0" aria-hidden="true">−</span>
                <span>{s.texto}</span>
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Lo que recorta la fiabilidad. Uno solo, el más grave: la precedencia la
          resuelve el backend. Aquí vive también el aviso de datos degradados, que
          antes era una barra aparte diciendo lo mismo con otras palabras. */}
      {limita && (
        <p
          className="text-[12.5px] text-[#8a6508] leading-snug mt-3 pt-3 border-t border-[#e5e0d8] flex gap-1.5"
          data-testid="tesis-limita-confianza"
        >
          <span className="shrink-0" aria-hidden="true">⚠️</span>
          <span>{limita.texto}</span>
        </p>
      )}

      {/* Acción secundaria: la IA amplía lo de arriba, no lo sustituye. */}
      {onAnalizar && (
        <div className="mt-4 pt-3 border-t border-[#e5e0d8] flex items-center gap-3 flex-wrap">
          <button
            onClick={onAnalizar}
            disabled={loadingAnalysis}
            data-testid="btn-analisis-ia"
            className="text-[12px] font-mono font-semibold text-[#1a3a32] hover:text-[#0e1f1a] disabled:opacity-50 underline underline-offset-4 decoration-[#1a3a32]/30"
          >
            {loadingAnalysis
              ? "Analizando…"
              : tieneAnalisis
                ? "🧠 Rehacer análisis IA"
                : "🧠 Ampliar con IA"}
          </button>
          <span className="text-[11px] text-[#5c6b66]">
            Añade juicio, causa del movimiento, chartista y riesgos. Lo de arriba ya está calculado.
          </span>
        </div>
      )}
    </section>
  );
}
