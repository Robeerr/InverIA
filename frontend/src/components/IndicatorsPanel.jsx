import React from "react";
import { ChartBar, Pulse, ArrowsHorizontal, Triangle } from "@phosphor-icons/react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { fmtPrice } from "../lib/format";

function rsiTone(v) {
  if (v == null) return "text-[#5c6b66]";
  if (v >= 70) return "text-[#d85c41]";
  if (v <= 30) return "text-[#4a7c59]";
  return "text-[#0e1f1a]";
}
function rsiLabel(v) {
  if (v == null) return "—";
  if (v >= 70) return "Sobrecomprado";
  if (v <= 30) return "Sobrevendido";
  return "Neutro";
}

function macdTone(v) {
  if (v == null) return "text-[#5c6b66]";
  return v > 0 ? "text-[#4a7c59]" : "text-[#d85c41]";
}

export default function IndicatorsPanel({ indicators, analysis }) {
  if (!indicators) return null;
  const { rsi, macd, bollinger, sma, ema, fibonacci, support_resistance, patterns } = indicators;

  return (
    <section data-testid="indicators-panel" className="card-flat p-6 animate-fade-up">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center">
          <ChartBar size={18} weight="bold" />
        </div>
        <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">
          Indicadores Técnicos
        </h3>
      </div>

      <Tabs defaultValue="momentum">
        <TabsList className="bg-[#f5f3ef] border border-[#e5e0d8] grid grid-cols-4 mb-4">
          <TabsTrigger value="momentum" data-testid="tab-momentum">Momentum</TabsTrigger>
          <TabsTrigger value="trend" data-testid="tab-trend">Tendencia</TabsTrigger>
          <TabsTrigger value="levels" data-testid="tab-levels">Niveles</TabsTrigger>
          <TabsTrigger value="patterns" data-testid="tab-patterns">Patrones</TabsTrigger>
        </TabsList>

        <TabsContent value="momentum" className="space-y-3">
          <Row icon={<Pulse size={14} weight="bold" />} label="RSI (14)" testId="rsi" value={
            <span className={`font-mono ${rsiTone(rsi)}`}>
              {rsi ?? "—"} <span className="text-[10px] uppercase ml-1">{rsiLabel(rsi)}</span>
            </span>
          } />
          <Row label="MACD" testId="macd" value={
            <span className={`font-mono ${macdTone(macd?.macd)}`}>{fmtPrice(macd?.macd)}</span>
          } />
          <Row label="Signal" testId="macd-signal" value={<span className="font-mono">{fmtPrice(macd?.signal)}</span>} />
          <Row label="Histograma" testId="macd-hist" value={
            <span className={`font-mono ${macdTone(macd?.histogram)}`}>{fmtPrice(macd?.histogram)}</span>
          } />
        </TabsContent>

        <TabsContent value="trend" className="space-y-3">
          <Row label="SMA 20" value={<span className="font-mono">${fmtPrice(sma?.["20"])}</span>} />
          <Row label="SMA 50" value={<span className="font-mono">${fmtPrice(sma?.["50"])}</span>} />
          <Row label="SMA 200" value={<span className="font-mono">${fmtPrice(sma?.["200"])}</span>} />
          <Row label="EMA 12" value={<span className="font-mono">${fmtPrice(ema?.["12"])}</span>} />
          <Row label="EMA 26" value={<span className="font-mono">${fmtPrice(ema?.["26"])}</span>} />
          <div className="divider-soft my-2" />
          <Row icon={<ArrowsHorizontal size={14} weight="bold" />} label="Bollinger Sup." value={<span className="font-mono text-[#d85c41]">${fmtPrice(bollinger?.upper)}</span>} />
          <Row label="Bollinger Med." value={<span className="font-mono">${fmtPrice(bollinger?.middle)}</span>} />
          <Row label="Bollinger Inf." value={<span className="font-mono text-[#4a7c59]">${fmtPrice(bollinger?.lower)}</span>} />
        </TabsContent>

        <TabsContent value="levels" className="space-y-3">
          <h4 className="label-small">Soportes</h4>
          {(support_resistance?.supports || []).map((s, i) => (
            <Row key={`s-${i}`} label={`S${i + 1}`} value={<span className="font-mono text-[#4a7c59]">${fmtPrice(s)}</span>} />
          ))}
          {(support_resistance?.supports || []).length === 0 && (
            <p className="text-xs text-[#5c6b66]">Sin soportes detectados.</p>
          )}
          <div className="divider-soft my-2" />
          <h4 className="label-small">Resistencias</h4>
          {(support_resistance?.resistances || []).map((s, i) => (
            <Row key={`r-${i}`} label={`R${i + 1}`} value={<span className="font-mono text-[#d85c41]">${fmtPrice(s)}</span>} />
          ))}
          {(support_resistance?.resistances || []).length === 0 && (
            <p className="text-xs text-[#5c6b66]">Sin resistencias detectadas.</p>
          )}
          <div className="divider-soft my-2" />
          <h4 className="label-small">Fibonacci (52sem)</h4>
          {Object.entries(fibonacci || {}).map(([k, v]) => (
            <Row key={k} label={`Fib ${k}%`} value={<span className="font-mono">${fmtPrice(v)}</span>} />
          ))}
        </TabsContent>

        <TabsContent value="patterns" className="space-y-2">
          {(patterns || []).length > 0 ? (
            (patterns || []).map((p, i) => (
              <div key={i} data-testid={`pattern-${i}`} className="flex items-center gap-2 px-3 py-2 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
                <Triangle size={14} weight="bold" className="text-[#1a3a32]" />
                <span className="text-sm text-[#0e1f1a]">{p}</span>
              </div>
            ))
          ) : (
            <p className="text-xs text-[#5c6b66]">Sin patrones detectados actualmente.</p>
          )}
          {analysis?.pattern_analysis && (
            <div className="mt-3 p-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
              <p className="label-small mb-1">Visión IA</p>
              <p className="text-xs text-[#0e1f1a] leading-relaxed">{analysis.pattern_analysis}</p>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </section>
  );
}

function Row({ icon, label, value, testId }) {
  return (
    <div data-testid={testId} className="flex items-center justify-between py-1.5 border-b border-[#f0ebe1] last:border-0">
      <span className="text-xs text-[#5c6b66] flex items-center gap-1.5">
        {icon}
        {label}
      </span>
      <span className="text-sm">{value}</span>
    </div>
  );
}
