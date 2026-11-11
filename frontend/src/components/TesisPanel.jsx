import React from "react";
import { Warning } from "@phosphor-icons/react";
import { fmtHace } from "../lib/format";
import { titularVivo } from "../lib/tesisVivo";
import HistorialTesis from "./HistorialTesis";

/* ── Superficie ──────────────────────────────────────────────────────────────
   Estos bloques usan `iv-panel` y no `iv-panel`, y conviene saber por qué sigue
   importando aunque las dos ya se pinten igual.

   Cuando se escribió esto, `iv-panel` se remapeaba con `!important` a un pizarra
   azulado ajeno a la paleta, así que mezclarlas dentro de un componente dejaba
   texto de un mundo sobre la superficie de otro. Hoy ese bloque legado está
   repintado con los tokens y las dos resuelven al mismo verde, así que el riesgo
   ya no es visual: es que `iv-panel` no ADMITE opacidad (`bg-superficie/60`) ni
   se mueve si mañana cambia la escala de superficies. `iv-panel` sí.

   Las reglas `!important` siguen en pie porque están indexadas por valor hex y
   esos hex viven todavía en BrainView. Se borrarán con su reescritura.
   ────────────────────────────────────────────────────────────────────────── */

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
  symbol,
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
    <section className="iv-panel p-5 sm:p-6" data-testid="tesis">
      <div className="flex items-baseline gap-3 flex-wrap mb-2.5">
        <h3 className="iv-etiqueta">
          Qué está pasando
        </h3>
        {generadoEn && (
          <span
            className="iv-cifra text-etiqueta text-tinta-3 ml-auto"
            title="Cuándo se calculó el análisis. La cotización de arriba va en vivo; esto es una foto de ese momento."
            data-testid="tesis-antiguedad"
          >
            calculado {fmtHace(generadoEn)}
          </span>
        )}
      </div>

      <p className="text-[17px] leading-snug font-medium text-tinta text-pretty max-w-[62ch]" data-testid="tesis-titular">
        {titular}
      </p>

      {(tesis.parrafos || []).map((p, i) => (
        <p key={i} className="text-apoyo text-tinta-2 leading-relaxed mt-2 max-w-[70ch]">
          {p}
        </p>
      ))}

      {/* Comprobaciones binarias, cada una con el dato que la sostiene dentro del texto. */}
      {(tesis.a_favor?.length > 0 || tesis.en_contra?.length > 0) && (
        <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1.5 mt-4">
          <ul className="space-y-1" aria-label="A favor">
            {(tesis.a_favor || []).map((s, i) => (
              <li key={i} className="text-apoyo text-tinta leading-snug flex gap-2">
                <span className="iv-cifra text-sube font-bold shrink-0 w-3 text-center" aria-hidden="true">+</span>
                <span>{s.texto}</span>
              </li>
            ))}
          </ul>
          <ul className="space-y-1" aria-label="En contra">
            {(tesis.en_contra || []).map((s, i) => (
              <li key={i} className="text-apoyo text-tinta leading-snug flex gap-2">
                <span className="iv-cifra text-baja font-bold shrink-0 w-3 text-center" aria-hidden="true">−</span>
                <span>{s.texto}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Lo que recorta la fiabilidad. Uno solo, el más grave: la precedencia la
          resuelve el backend. Aquí vive también el aviso de datos degradados, que
          antes era una barra aparte diciendo lo mismo con otras palabras. */}
      {limita && (
        <p
          className="text-apoyo text-aviso leading-snug mt-4 rounded-iv bg-aviso/[0.07] px-3 py-2 flex gap-2"
          data-testid="tesis-limita-confianza"
        >
          <Warning size={14} weight="fill" className="shrink-0 mt-0.5" aria-hidden="true" />
          <span>{limita.texto}</span>
        </p>
      )}

      {/* El historial va DEBAJO de la tesis de hoy y cerrado: lo que se viene a ver al
          abrir una acción es qué pasa ahora. Y va aquí dentro, no en un panel aparte,
          porque es la misma tesis en otro momento — separarlo daría a entender que son
          dos cosas distintas. */}
      <HistorialTesis symbol={symbol || tesis.symbol} />

      {/* Acción secundaria: la IA amplía lo de arriba, no lo sustituye. */}
      {onAnalizar && (
        <div className="mt-4 pt-4 border-t border-linea flex items-center gap-x-3 gap-y-2 flex-wrap">
          <button
            onClick={onAnalizar}
            disabled={loadingAnalysis}
            data-testid="btn-analisis-ia"
            aria-busy={loadingAnalysis}
            className="shrink-0 text-etiqueta font-mono font-semibold px-3 py-1.5 rounded-iv border border-marca/50 text-marca
                       hover:bg-marca/10 active:scale-[0.97] disabled:opacity-50
                       transition-[background-color,transform] duration-150 motion-reduce:transition-none"
          >
            {loadingAnalysis
              ? "Analizando…"
              : tieneAnalisis
                ? "Rehacer análisis IA"
                : "Ampliar con IA"}
          </button>
          <span className="text-etiqueta text-tinta-3 min-w-0">
            Añade juicio, causa del movimiento, chartista y riesgos. Lo de arriba ya está calculado.
          </span>
        </div>
      )}
    </section>
  );
}
