import React from "react";
import { TriangleAlert as AlertTriangle, Plus, Minus, Sparkles } from "lucide-react";
import { fmtHace } from "../lib/format";
import { titularVivo } from "../lib/tesisVivo";
import HistorialTesis from "./HistorialTesis";
import { Boton } from "./base/Boton";

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
 *
 * Es la pieza destacada de la ficha (`iv-destacada`): lo que hay que leer sí o sí.
 */
function Lista({ titulo, items, tono }) {
  if (!items?.length) return null;
  const Icono = tono === "sube" ? Plus : Minus;
  const color = tono === "sube" ? "text-sube bg-sube/[0.12]" : "text-baja bg-baja/[0.12]";
  return (
    <div className="min-w-0">
      <p className="iv-etiqueta mb-2.5">{titulo} <span className="iv-cifra text-tinta-3">· {items.length}</span></p>
      <ul className="space-y-2" aria-label={titulo}>
        {items.map((s, i) => (
          <li key={i} className="text-[13.5px] text-tinta leading-snug flex gap-2.5">
            <span className={`w-[18px] h-[18px] rounded-[6px] inline-flex items-center justify-center shrink-0 mt-px ${color}`} aria-hidden="true">
              <Icono className="w-3 h-3" strokeWidth={2.5} />
            </span>
            <span>{s.texto}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

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
  const hayListas = tesis.a_favor?.length > 0 || tesis.en_contra?.length > 0;

  return (
    <section className="iv-destacada shadow-panel" data-testid="tesis">
      <div className="p-5 sm:p-7">
        <div className="flex items-baseline gap-3 flex-wrap mb-3">
          <h3 className="text-[13px] font-medium text-marca">Qué está pasando</h3>
          {generadoEn && (
            <span
              className="text-[12px] text-tinta-3 ml-auto"
              title="Cuándo se calculó el análisis. La cotización de arriba va en vivo; esto es una foto de ese momento."
              data-testid="tesis-antiguedad"
            >
              calculado {fmtHace(generadoEn)}
            </span>
          )}
        </div>

        <p className="text-[19px] sm:text-[22px] leading-[1.3] font-semibold tracking-[-0.02em] text-tinta text-pretty max-w-[34ch] sm:max-w-[46ch]" data-testid="tesis-titular">
          {titular}
        </p>

        {(tesis.parrafos || []).map((p, i) => (
          <p key={i} className="text-[14.5px] text-tinta-2 leading-relaxed mt-3 max-w-[68ch]">
            {p}
          </p>
        ))}

        {/* Comprobaciones binarias, cada una con el dato que la sostiene dentro del texto. */}
        {hayListas && (
          <div className="grid sm:grid-cols-2 gap-x-8 gap-y-5 mt-6 pt-5 border-t border-suave">
            <Lista titulo="A favor" items={tesis.a_favor} tono="sube" />
            <Lista titulo="En contra" items={tesis.en_contra} tono="baja" />
          </div>
        )}

        {/* Lo que recorta la fiabilidad. Uno solo, el más grave: la precedencia la
            resuelve el backend. Aquí vive también el aviso de datos degradados, que
            antes era una barra aparte diciendo lo mismo con otras palabras. */}
        {limita && (
          <p
            className="text-[13px] text-aviso leading-snug mt-5 rounded-iv bg-aviso/[0.08] border border-aviso/15 px-3.5 py-2.5 flex gap-2.5"
            data-testid="tesis-limita-confianza"
          >
            <AlertTriangle className="w-4 h-4 shrink-0 mt-px" strokeWidth={1.75} aria-hidden="true" />
            <span>{limita.texto}</span>
          </p>
        )}

        {/* El historial va DEBAJO de la tesis de hoy y cerrado: lo que se viene a ver al
            abrir una acción es qué pasa ahora. Y va aquí dentro, no en un panel aparte,
            porque es la misma tesis en otro momento. */}
        <HistorialTesis symbol={symbol || tesis.symbol} />
      </div>

      {/* Acción secundaria: la IA amplía lo de arriba, no lo sustituye. */}
      {onAnalizar && (
        <div className="px-5 sm:px-7 py-4 border-t border-suave bg-tinta/[0.02] flex items-center gap-x-4 gap-y-3 flex-wrap rounded-b-iv-lg">
          <Boton
            variante="secundario"
            onClick={onAnalizar}
            ocupado={loadingAnalysis}
            data-testid="btn-analisis-ia"
            className="shrink-0"
          >
            <Sparkles className="w-4 h-4 text-marca" strokeWidth={1.75} aria-hidden="true" />
            {loadingAnalysis
              ? "Analizando…"
              : tieneAnalisis
                ? "Rehacer análisis IA"
                : "Ampliar con IA"}
          </Boton>
          <span className="text-[13px] text-tinta-3 min-w-0 flex-1 basis-56">
            Añade juicio, causa del movimiento, chartista y riesgos. Lo de arriba ya está calculado.
          </span>
        </div>
      )}
    </section>
  );
}
