import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, ArrowUpRight, ArrowDownRight, Minus, Target, Shield, TrendUp, Lightning } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { fmtPrice } from "../lib/format";
import { api } from "../lib/api";
import { TierBadge } from "./ChartistPanel";

// El id "gemini-2.5-flash" es la clave INTERNA de routing: el backend la enruta a
// GEMINI_MODEL, que se cambia con una variable de entorno y sin desplegar. Por eso estas
// etiquetas son solo el RESPALDO para cuando /models no ha contestado todavía: escritas
// aquí, se quedan diciendo una versión vieja en cuanto alguien cambia esa variable.
const FREE_MODELS = [
  { id: "gemini-2.5-flash", label: "Gemini (Recomendado)" },
  { id: "gpt-oss-120b", label: "GPT-OSS 120B" },
  { id: "llama-3.3-70b", label: "Llama 3.3 70B" },
];

// Nombres reales, servidos por el backend. Es el único que sabe a qué modelo enruta cada
// clave. Cae al respaldo de arriba si la petición falla: quedarse sin selector por no
// poder poner el nombre exacto sería peor que enseñar uno genérico.
let _etiquetas = {};
export function useEtiquetasModelo() {
  const { data } = useQuery({
    queryKey: ["modelos"],
    queryFn: api.modelos,
    staleTime: 60 * 60_000,
    retry: false,
  });
  const etiquetas = React.useMemo(() => {
    const m = {};
    for (const x of data?.models || []) if (x?.value) m[x.value] = x.label;
    return m;
  }, [data]);
  // Fuera del render: `modelLabel` se llama desde un callback (el aviso tras analizar),
  // donde no hay hook que valga. Escribirlo en el render sería un efecto colateral.
  React.useEffect(() => { _etiquetas = etiquetas; }, [etiquetas]);
  return etiquetas;
}

export function modelLabel(id) {
  return _etiquetas[id] || (FREE_MODELS.find((m) => m.id === id) || {}).label || id;
}

function ModelSelector({ model, setModel, disabled }) {
  const etiquetas = useEtiquetasModelo();
  if (!setModel) return null;
  return (
    <div className="mb-3">
      <label htmlFor="selector-modelo-ia" className="iv-etiqueta mb-1.5 block">Modelo de IA (todos gratis)</label>
      <select
        id="selector-modelo-ia"
        data-testid="model-selector"
        value={model}
        onChange={(e) => setModel(e.target.value)}
        disabled={disabled}
        className="w-full bg-fondo border border-linea rounded-iv px-3 py-2 font-mono text-base sm:text-apoyo text-tinta focus:outline-none focus:border-marca disabled:opacity-50"
      >
        {FREE_MODELS.map((m) => (
          <option key={m.id} value={m.id}>{etiquetas[m.id] || m.label}</option>
        ))}
      </select>
    </div>
  );
}

function RecPill({ rec }) {
  if (rec === "COMPRAR") {
    return (
      <span data-testid="recommendation-pill" className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-sube text-marca-tinta font-mono text-xs font-bold uppercase tracking-wider">
        <ArrowUpRight size={14} weight="bold" /> COMPRAR
      </span>
    );
  }
  if (rec === "VENDER") {
    return (
      <span data-testid="recommendation-pill" className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-baja text-marca-tinta font-mono text-xs font-bold uppercase tracking-wider">
        <ArrowDownRight size={14} weight="bold" /> VENDER
      </span>
    );
  }
  return (
    <span data-testid="recommendation-pill" className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-tinta-3 text-marca-tinta font-mono text-xs font-bold uppercase tracking-wider">
      <Minus size={14} weight="bold" /> MANTENER
    </span>
  );
}

function ConfidenceBar({ value }) {
  const v = Math.max(0, Math.min(100, value || 0));
  const color = v >= 70 ? "bg-sube" : v >= 40 ? "bg-aviso" : "bg-baja";
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1">
        <span className="iv-etiqueta">Confianza</span>
        <span data-testid="confidence-value" className="iv-cifra text-apoyo font-semibold text-tinta">{v}%</span>
      </div>
      <div className="h-1.5 bg-linea rounded-full overflow-hidden" aria-hidden="true">
        <div className={`h-full ${color}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

export default function RecommendationPanel({ analysis, isLoading, onAnalyze, model, setModel }) {
  if (!analysis && !isLoading) {
    return (
      <section data-testid="recommendation-panel-empty" className="iv-panel p-5">
        <h3 className="font-heading text-cuerpo font-semibold text-tinta flex items-center gap-2">
          <Brain size={16} weight="bold" className="text-marca" aria-hidden="true" />
          Análisis con IA
        </h3>
        <p className="text-apoyo text-tinta-2 mt-1 mb-4 max-w-[64ch]">
          Genera una recomendación de compra/venta con niveles precisos basada en los datos en vivo y análisis técnico.
        </p>
        {/* Selector y botón en la misma fila en escritorio: el botón a todo el ancho
            pesaba más que el veredicto de arriba, y esto es una acción opcional. */}
        <div className="flex flex-col sm:flex-row sm:items-end gap-x-3">
          <div className="sm:flex-1 sm:max-w-sm">
            <ModelSelector model={model} setModel={setModel} />
          </div>
          <Button
            data-testid="run-analysis-btn"
            onClick={onAnalyze}
            className="w-full sm:w-auto mb-3 bg-marca text-marca-tinta font-mono font-semibold
                       hover:bg-marca hover:brightness-110 active:scale-[0.97]
                       transition-[filter,transform] duration-150 motion-reduce:transition-none"
          >
            <Lightning size={16} weight="bold" className="mr-2" aria-hidden="true" />
            Generar análisis
          </Button>
        </div>
      </section>
    );
  }

  if (isLoading) {
    return (
      <section data-testid="recommendation-loading" className="iv-panel p-5" aria-busy="true">
        <h3 className="font-heading text-cuerpo font-semibold text-tinta flex items-center gap-2 mb-4">
          <Brain size={16} weight="bold" className="text-marca animate-pulse motion-reduce:animate-none" aria-hidden="true" />
          Generando análisis...
        </h3>
        <div className="space-y-3" aria-hidden="true">
          <div className="h-4 bg-superficie-alt rounded animate-pulse motion-reduce:animate-none" />
          <div className="h-4 bg-superficie-alt rounded animate-pulse motion-reduce:animate-none w-3/4" />
          <div className="h-20 bg-superficie-alt rounded animate-pulse motion-reduce:animate-none" />
          <div className="h-4 bg-superficie-alt rounded animate-pulse motion-reduce:animate-none" />
        </div>
        <p className="text-etiqueta text-tinta-3 mt-4" role="status">
          {modelLabel(model)} está analizando datos técnicos y fundamentales...
        </p>
      </section>
    );
  }

  return (
    <section data-testid="recommendation-panel" className="iv-panel p-5 sm:p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="font-heading text-cuerpo font-semibold text-tinta flex items-center gap-2">
            <Brain size={16} weight="bold" className="text-marca" aria-hidden="true" />
            Recomendación IA
          </h3>
          {analysis._ai_tier && <TierBadge tier={analysis._ai_tier} model={analysis._ai_model} />}
        </div>
        <RecPill rec={analysis.recommendation} />
      </div>

      <ConfidenceBar value={analysis.confidence} />

      {/* Tres datos en una fila con filetes, sin una caja por dato. */}
      <dl className="mt-4 grid grid-cols-3 divide-x divide-linea border-y border-linea">
        <div className="pr-3 py-2.5 min-w-0">
          <dt className="iv-etiqueta">Tendencia</dt>
          <dd data-testid="trend" className="font-mono text-apoyo font-semibold mt-0.5 text-tinta truncate">{analysis.trend}</dd>
        </div>
        <div className="px-3 py-2.5 min-w-0">
          <dt className="iv-etiqueta">Horizonte</dt>
          <dd className="font-mono text-apoyo font-semibold mt-0.5 text-tinta truncate">{analysis.timeframe?.replace("_", " ")}</dd>
        </div>
        <div className="px-3 py-2.5 min-w-0">
          <dt className="iv-etiqueta">R/R</dt>
          <dd data-testid="risk-reward" className="iv-cifra text-apoyo font-semibold mt-0.5 text-tinta">
            {analysis.risk_reward_ratio ? `1:${analysis.risk_reward_ratio}` : "—"}
          </dd>
        </div>
      </dl>

      <p data-testid="analysis-summary" className="text-apoyo text-tinta-2 mt-4 leading-relaxed max-w-[70ch]">
        {analysis.summary}
      </p>

      <h4 className="iv-etiqueta mt-5 mb-1">Niveles operativos</h4>
      <div className="divide-y divide-linea">
        {analysis.entry_zone && (
          <LevelRow
            icon={<Target size={14} weight="bold" />}
            label="Zona Entrada"
            value={`$${fmtPrice(analysis.entry_zone.min)} - $${fmtPrice(analysis.entry_zone.max)}`}
            tone="neutral"
            testId="entry-zone"
          />
        )}
        {analysis.stop_loss && (
          <LevelRow
            icon={<Shield size={14} weight="bold" />}
            label="Stop Loss"
            value={`$${fmtPrice(analysis.stop_loss)}`}
            tone="sell"
            testId="stop-loss"
          />
        )}
        {analysis.take_profit_1 && (
          <LevelRow
            icon={<TrendUp size={14} weight="bold" />}
            label="Take Profit 1"
            value={`$${fmtPrice(analysis.take_profit_1)}`}
            tone="buy"
            testId="take-profit-1"
          />
        )}
        {analysis.take_profit_2 && (
          <LevelRow
            icon={<TrendUp size={14} weight="bold" />}
            label="Take Profit 2"
            value={`$${fmtPrice(analysis.take_profit_2)}`}
            tone="buy"
            testId="take-profit-2"
          />
        )}
      </div>

      <div className="mt-5 pt-4 border-t border-linea flex flex-col sm:flex-row sm:items-end gap-x-3">
        <div className="sm:flex-1 sm:max-w-sm">
          <ModelSelector model={model} setModel={setModel} />
        </div>
        <Button
          data-testid="rerun-analysis-btn"
          onClick={onAnalyze}
          variant="outline"
          className="w-full sm:w-auto mb-3 border-linea-fuerte hover:border-marca/60 hover:bg-marca/10 font-mono text-xs
                     transition-colors duration-150 motion-reduce:transition-none"
        >
          Re-analizar con {modelLabel(model)}
        </Button>
      </div>
    </section>
  );
}

function LevelRow({ icon, label, value, tone, testId }) {
  const colors = {
    buy: "text-sube",
    sell: "text-baja",
    neutral: "text-tinta",
  };
  return (
    <div data-testid={testId} className="flex flex-wrap items-center justify-between gap-x-3 py-2">
      <span className="flex items-center gap-2 text-apoyo text-tinta-2">
        <span className={colors[tone]} aria-hidden="true">{icon}</span>
        {label}
      </span>
      <span className={`iv-cifra text-apoyo font-semibold ml-auto text-right ${colors[tone]}`}>{value}</span>
    </div>
  );
}
