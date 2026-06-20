import React from "react";
import { Brain, ArrowUpRight, ArrowDownRight, Minus, Target, Shield, TrendUp, Lightning } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { fmtPrice } from "../lib/format";

const FREE_MODELS = [
  { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash (Recomendado)" },
  { id: "gpt-oss-120b", label: "GPT-OSS 120B" },
  { id: "llama-3.3-70b", label: "Llama 3.3 70B" },
];

function modelLabel(id) {
  return (FREE_MODELS.find((m) => m.id === id) || {}).label || id;
}

function ModelSelector({ model, setModel, disabled }) {
  if (!setModel) return null;
  return (
    <div className="mb-3">
      <label className="label-small mb-1 block">Modelo de IA (todos gratis)</label>
      <select
        data-testid="model-selector"
        value={model}
        onChange={(e) => setModel(e.target.value)}
        disabled={disabled}
        className="w-full bg-[#f5f3ef] border border-[#e5e0d8] rounded-md px-3 py-2 font-mono text-sm text-[#0e1f1a] focus:outline-none focus:border-[#1a3a32] disabled:opacity-50"
      >
        {FREE_MODELS.map((m) => (
          <option key={m.id} value={m.id}>{m.label}</option>
        ))}
      </select>
    </div>
  );
}

function RecPill({ rec }) {
  if (rec === "COMPRAR") {
    return (
      <span data-testid="recommendation-pill" className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-[#4a7c59] text-[#f5f3ef] font-mono text-xs font-bold uppercase tracking-wider">
        <ArrowUpRight size={14} weight="bold" /> COMPRAR
      </span>
    );
  }
  if (rec === "VENDER") {
    return (
      <span data-testid="recommendation-pill" className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-[#d85c41] text-[#f5f3ef] font-mono text-xs font-bold uppercase tracking-wider">
        <ArrowDownRight size={14} weight="bold" /> VENDER
      </span>
    );
  }
  return (
    <span data-testid="recommendation-pill" className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-[#5c6b66] text-[#f5f3ef] font-mono text-xs font-bold uppercase tracking-wider">
      <Minus size={14} weight="bold" /> MANTENER
    </span>
  );
}

function ConfidenceBar({ value }) {
  const v = Math.max(0, Math.min(100, value || 0));
  const color = v >= 70 ? "bg-[#4a7c59]" : v >= 40 ? "bg-[#c9a14a]" : "bg-[#d85c41]";
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1">
        <span className="label-small">Confianza</span>
        <span data-testid="confidence-value" className="font-mono text-sm font-semibold text-[#0e1f1a]">{v}%</span>
      </div>
      <div className="h-1.5 bg-[#e5e0d8] rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

export default function RecommendationPanel({ analysis, isLoading, onAnalyze, model, setModel }) {
  if (!analysis && !isLoading) {
    return (
      <section data-testid="recommendation-panel-empty" className="card-flat p-6">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-8 h-8 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center">
            <Brain size={18} weight="bold" />
          </div>
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">
            Análisis con IA
          </h3>
        </div>
        <p className="text-sm text-[#5c6b66] mb-4">
          Genera una recomendación de compra/venta con niveles precisos basada en los datos en vivo y análisis técnico.
        </p>
        <ModelSelector model={model} setModel={setModel} />
        <Button
          data-testid="run-analysis-btn"
          onClick={onAnalyze}
          className="w-full bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono"
        >
          <Lightning size={16} weight="bold" className="mr-2" />
          Generar análisis
        </Button>
      </section>
    );
  }

  if (isLoading) {
    return (
      <section data-testid="recommendation-loading" className="card-flat p-6">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-8 h-8 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center animate-pulse">
            <Brain size={18} weight="bold" />
          </div>
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">
            Generando análisis...
          </h3>
        </div>
        <div className="space-y-3">
          <div className="h-4 bg-[#e5e0d8] rounded animate-pulse" />
          <div className="h-4 bg-[#e5e0d8] rounded animate-pulse w-3/4" />
          <div className="h-20 bg-[#e5e0d8] rounded animate-pulse" />
          <div className="h-4 bg-[#e5e0d8] rounded animate-pulse" />
        </div>
        <p className="text-xs text-[#5c6b66] mt-4 text-center">
          {modelLabel(model)} está analizando datos técnicos y fundamentales...
        </p>
      </section>
    );
  }

  return (
    <section data-testid="recommendation-panel" className="card-flat p-6 animate-fade-up">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center">
            <Brain size={18} weight="bold" />
          </div>
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">
            Recomendación IA
          </h3>
        </div>
        <RecPill rec={analysis.recommendation} />
      </div>

      <ConfidenceBar value={analysis.confidence} />

      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div className="bg-[#f5f3ef] border border-[#e5e0d8] rounded-md px-2 py-2">
          <p className="label-small">Tendencia</p>
          <p data-testid="trend" className="font-mono text-xs font-semibold mt-1 text-[#0e1f1a]">{analysis.trend}</p>
        </div>
        <div className="bg-[#f5f3ef] border border-[#e5e0d8] rounded-md px-2 py-2">
          <p className="label-small">Horizonte</p>
          <p className="font-mono text-xs font-semibold mt-1 text-[#0e1f1a]">{analysis.timeframe?.replace("_", " ")}</p>
        </div>
        <div className="bg-[#f5f3ef] border border-[#e5e0d8] rounded-md px-2 py-2">
          <p className="label-small">R/R</p>
          <p data-testid="risk-reward" className="font-mono text-xs font-semibold mt-1 text-[#0e1f1a]">
            {analysis.risk_reward_ratio ? `1:${analysis.risk_reward_ratio}` : "—"}
          </p>
        </div>
      </div>

      <p data-testid="analysis-summary" className="text-sm text-[#0e1f1a] mt-4 leading-relaxed">
        {analysis.summary}
      </p>

      <div className="divider-soft my-5" />

      <h4 className="label-small mb-3">Niveles Operativos</h4>
      <div className="space-y-2">
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

      <div className="mt-5">
        <ModelSelector model={model} setModel={setModel} />
        <Button
          data-testid="rerun-analysis-btn"
          onClick={onAnalyze}
          variant="outline"
          className="w-full border-[#e5e0d8] hover:bg-[#e5e0d8] font-mono text-xs"
        >
          Re-analizar con {modelLabel(model)}
        </Button>
      </div>
    </section>
  );
}

function LevelRow({ icon, label, value, tone, testId }) {
  const colors = {
    buy: "text-[#4a7c59]",
    sell: "text-[#d85c41]",
    neutral: "text-[#0e1f1a]",
  };
  return (
    <div data-testid={testId} className="flex items-center justify-between py-2 px-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
      <span className={`flex items-center gap-2 text-xs ${colors[tone]} font-medium`}>
        {icon}
        {label}
      </span>
      <span className={`font-mono text-sm font-semibold ${colors[tone]}`}>{value}</span>
    </div>
  );
}
