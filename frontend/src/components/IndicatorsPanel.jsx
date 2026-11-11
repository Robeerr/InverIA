import React from "react";
import { ChartBar, Pulse, ArrowsHorizontal, Triangle } from "@phosphor-icons/react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { fmtPrice } from "../lib/format";
import InfoDot from "./InfoDot";

function rsiTone(v) {
  if (v == null) return "text-tinta-3";
  if (v >= 70) return "text-baja";
  if (v <= 30) return "text-sube";
  return "text-tinta";
}
function rsiLabel(v) {
  if (v == null) return "—";
  if (v >= 70) return "Sobrecomprado";
  if (v <= 30) return "Sobrevendido";
  return "Neutro";
}

function macdTone(v) {
  if (v == null) return "text-tinta-3";
  return v > 0 ? "text-sube" : "text-baja";
}

// Fuerza Relativa frente al S&P 500. Va FUERA de las pestañas y siempre visible porque no es
// un indicador más para consultar: es el filtro de "¿esta acción lidera o va a rastras del
// mercado?", y esconderlo tras un clic lo convierte en algo que nadie mira.
// Se exporta porque la fuerza relativa NO es un indicador de detalle: compara la
// acción con el índice y va en el bloque de analistas, arriba. El panel de detalle
// dejó de pintarla para que no salga dos veces.
export function FuerzaRelativa({ rs }) {
  if (!rs?.ventanas) return null;
  // Los colores van por CLASE, no por style en línea: el remapeo de modo oscuro de index.css
  // funciona con selectores de clase (.dark .text-sube), así que un color en línea se lo
  // salta y se queda en 3,6:1 sobre el fondo oscuro — por debajo del mínimo legible.
  const tono = {
    "LÍDER":       { c: "text-sube", i: "▲" },
    "POR DELANTE": { c: "text-sube", i: "↗" },
    "POR DETRÁS":  { c: "text-aviso", i: "↘" },
    "REZAGADA":    { c: "text-baja", i: "▼" },
  }[rs.veredicto] || { c: "text-tinta-3", i: "" };
  const orden = ["1m", "3m", "6m"];
  // Panel como los demás de la sección, sin fondo teñido: el veredicto ya lleva el
  // color, y una franja rosa entera gritaba más que el propio consenso de analistas.
  return (
    <div data-testid="fuerza-relativa" className="iv-panel p-5">
      <div className="flex items-start justify-between flex-wrap gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h3 className="iv-etiqueta">Fuerza relativa vs S&amp;P 500</h3>
          <p className={`font-mono text-cuerpo font-bold mt-1 flex items-center gap-1.5 ${tono.c}`}>
            {tono.i && <span aria-hidden="true" className="text-apoyo">{tono.i}</span>}
            {rs.veredicto}
          </p>
        </div>
        <dl className="flex items-start gap-5">
          {orden.filter((k) => rs.ventanas[k]).map((k) => {
            const v = rs.ventanas[k];
            const col = v.diferencia_pp >= 0 ? "text-sube" : "text-baja";
            return (
              <div key={k} className="text-right">
                <dt className="iv-etiqueta">{k}</dt>
                <dd className={`iv-cifra text-apoyo font-semibold mt-0.5 whitespace-nowrap ${col}`}>
                  {v.diferencia_pp >= 0 ? "+" : ""}{v.diferencia_pp} pp
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
      <p className="text-etiqueta text-tinta-3 mt-3 leading-snug max-w-[80ch]">
        Diferencia de rentabilidad frente al índice. Positivo = la acción va por delante del
        mercado. Es una medida de calidad de la candidata, no una señal de entrada.
      </p>
    </div>
  );
}

export default function IndicatorsPanel({ indicators, analysis }) {
  if (!indicators) return null;
  const { rsi, macd, bollinger, sma, ema, fibonacci, support_resistance, patterns } = indicators;

  return (
    <section data-testid="indicators-panel" className="iv-panel p-5">
      <h3 className="font-heading text-cuerpo font-semibold text-tinta flex items-center gap-2 mb-3">
        <ChartBar size={16} weight="bold" className="text-tinta-3" aria-hidden="true" />
        Indicadores Técnicos
      </h3>

      <Tabs defaultValue="momentum">
        <TabsList className="bg-fondo border border-linea grid grid-cols-4 mb-3 w-full">
          <TabsTrigger value="momentum" data-testid="tab-momentum">Momentum</TabsTrigger>
          <TabsTrigger value="trend" data-testid="tab-trend">Tendencia</TabsTrigger>
          <TabsTrigger value="levels" data-testid="tab-levels">Niveles</TabsTrigger>
          <TabsTrigger value="patterns" data-testid="tab-patterns">Patrones</TabsTrigger>
        </TabsList>

        <TabsContent value="momentum" className="space-y-3">
          <Row icon={<Pulse size={14} weight="bold" />} label="RSI (14)" testId="rsi" info="RSI" value={
            <span className={`iv-cifra ${rsiTone(rsi)}`}>
              {rsi ?? "—"} <span className="iv-etiqueta ml-1 !text-current">{rsiLabel(rsi)}</span>
            </span>
          } />
          <Row label="MACD" testId="macd" info="MACD" value={
            <span className={`font-mono ${macdTone(macd?.macd)}`}>{fmtPrice(macd?.macd)}</span>
          } />
          <Row label="Signal" testId="macd-signal" info="Signal" value={<span className="font-mono">{fmtPrice(macd?.signal)}</span>} />
          <Row label="Histograma" testId="macd-hist" info="Histograma" value={
            <span className={`font-mono ${macdTone(macd?.histogram)}`}>{fmtPrice(macd?.histogram)}</span>
          } />
        </TabsContent>

        <TabsContent value="trend" className="space-y-3">
          <Row label="SMA 20" info="SMA" value={<span className="font-mono">${fmtPrice(sma?.["20"])}</span>} />
          <Row label="SMA 50" value={<span className="font-mono">${fmtPrice(sma?.["50"])}</span>} />
          <Row label="SMA 200" value={<span className="font-mono">${fmtPrice(sma?.["200"])}</span>} />
          <Row label="EMA 12" info="EMA" value={<span className="font-mono">${fmtPrice(ema?.["12"])}</span>} />
          <Row label="EMA 26" value={<span className="font-mono">${fmtPrice(ema?.["26"])}</span>} />
          <div className="divider-soft my-2" />
          <Row icon={<ArrowsHorizontal size={14} weight="bold" />} label="Bollinger Sup." info="Bollinger" value={<span className="font-mono text-baja">${fmtPrice(bollinger?.upper)}</span>} />
          <Row label="Bollinger Med." value={<span className="font-mono">${fmtPrice(bollinger?.middle)}</span>} />
          <Row label="Bollinger Inf." value={<span className="font-mono text-sube">${fmtPrice(bollinger?.lower)}</span>} />
        </TabsContent>

        <TabsContent value="levels" className="space-y-3">
          <h4 className="iv-etiqueta flex items-center gap-1.5 pt-1">Soportes <InfoDot term="Soporte" /></h4>
          {(support_resistance?.supports || []).map((s, i) => (
            <Row key={`s-${i}`} label={`S${i + 1}`} value={<span className="font-mono text-sube">${fmtPrice(s)}</span>} />
          ))}
          {(support_resistance?.supports || []).length === 0 && (
            <p className="text-apoyo text-tinta-3">Sinsoportes detectados.</p>
          )}
          <div className="divider-soft my-2" />
          <h4 className="iv-etiqueta flex items-center gap-1.5 pt-1">Resistencias <InfoDot term="Resistencia" /></h4>
          {(support_resistance?.resistances || []).map((s, i) => (
            <Row key={`r-${i}`} label={`R${i + 1}`} value={<span className="font-mono text-baja">${fmtPrice(s)}</span>} />
          ))}
          {(support_resistance?.resistances || []).length === 0 && (
            <p className="text-apoyo text-tinta-3">Sinresistencias detectadas.</p>
          )}
          <div className="divider-soft my-2" />
          <h4 className="iv-etiqueta flex items-center gap-1.5 pt-1">Fibonacci (52sem) <InfoDot term="Fibonacci" /></h4>
          {Object.entries(fibonacci || {}).map(([k, v]) => (
            <Row key={k} label={`Fib ${k}%`} value={<span className="font-mono">${fmtPrice(v)}</span>} />
          ))}
        </TabsContent>

        <TabsContent value="patterns" className="space-y-2">
          {(patterns || []).length > 0 ? (
            (patterns || []).map((p, i) => (
              <div key={i} data-testid={`pattern-${i}`} className="flex items-center gap-2 py-1.5 border-b border-linea last:border-0">
                <Triangle size={12} weight="bold" className="text-tinta-3 shrink-0" aria-hidden="true" />
                <span className="text-apoyo text-tinta">{p}</span>
              </div>
            ))
          ) : (
            <p className="text-apoyo text-tinta-3">Sin patrones detectados actualmente.</p>
          )}
          {analysis?.pattern_analysis && (
            <div className="mt-3 pt-3 border-t border-linea">
              <p className="iv-etiqueta mb-1">Visión IA</p>
              <p className="text-apoyo text-tinta-2 leading-relaxed max-w-[70ch]">{analysis.pattern_analysis}</p>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </section>
  );
}

function Row({ icon, label, value, testId, info }) {
  return (
    <div data-testid={testId} className="flex items-center justify-between gap-3 py-1.5 border-b border-linea last:border-0">
      <span className="text-apoyo text-tinta-2 flex items-center gap-1.5 min-w-0">
        {icon && <span className="text-tinta-3" aria-hidden="true">{icon}</span>}
        {label}
        {info && <InfoDot term={info} />}
      </span>
      <span className="text-apoyo iv-cifra text-right tabular-nums">{value}</span>
    </div>
  );
}
