import React from "react";
import { Newspaper, ArrowSquareOut, Warning, Lightning } from "@phosphor-icons/react";
import { fmtPrice, fmtNum } from "../lib/format";

export function NewsFeed({ news }) {
  if (!news || news.length === 0) {
    return (
      <section data-testid="news-feed" className="card-flat p-6">
        <div className="flex items-center gap-2 mb-3">
          <Newspaper size={18} weight="bold" className="text-[#1a3a32]" />
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Noticias</h3>
        </div>
        <p className="text-sm text-[#5c6b66]">Sin noticias disponibles.</p>
      </section>
    );
  }

  return (
    <section data-testid="news-feed" className="card-flat p-6 animate-fade-up">
      <div className="flex items-center gap-2 mb-4">
        <Newspaper size={18} weight="bold" className="text-[#1a3a32]" />
        <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Noticias Recientes</h3>
      </div>
      <div className="space-y-3 max-h-[360px] overflow-y-auto pr-1">
        {news.map((n, i) => (
          <a
            key={i}
            data-testid={`news-item-${i}`}
            href={n.url}
            target="_blank"
            rel="noreferrer"
            className="group block p-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md hover:border-[#1a3a32] transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm text-[#0e1f1a] leading-snug group-hover:text-[#1a3a32] line-clamp-2">
                {n.title}
              </p>
              <ArrowSquareOut size={14} className="text-[#5c6b66] mt-0.5 shrink-0" />
            </div>
            <p className="text-[10px] text-[#5c6b66] mt-1 uppercase tracking-wider">
              {n.publisher || "—"}
            </p>
          </a>
        ))}
      </div>
    </section>
  );
}

export function FundamentalsCard({ quote, analysis }) {
  if (!quote) return null;
  return (
    <section data-testid="fundamentals" className="card-flat p-6 animate-fade-up">
      <h3 className="font-heading font-semibold text-lg text-[#0e1f1a] mb-3">
        Fundamentales
      </h3>
      <div className="grid grid-cols-2 gap-3">
        {[
          ["P/E", quote.pe_ratio ?? "—"],
          ["P/E Fwd", quote.forward_pe ?? "—"],
          ["EPS", quote.eps ? `$${fmtPrice(quote.eps)}` : "—"],
          ["Beta", quote.beta ?? "—"],
          ["Div. Yield", quote.dividend_yield != null ? `${(quote.dividend_yield * 100).toFixed(2)}%` : "—"],
          ["52W Alto", `$${fmtPrice(quote.high_52w)}`],
          ["52W Bajo", `$${fmtPrice(quote.low_52w)}`],
          ["Vol. Prom.", fmtNum(quote.avg_volume)],
        ].map(([label, val]) => (
          <div key={label} className="bg-[#f5f3ef] border border-[#e5e0d8] rounded-md px-3 py-2">
            <p className="label-small">{label}</p>
            <p className="font-mono text-sm text-[#0e1f1a] mt-1">{val}</p>
          </div>
        ))}
      </div>
      {quote.description && (
        <>
          <div className="divider-soft my-4" />
          <p className="text-xs text-[#5c6b66] leading-relaxed">{quote.description}</p>
        </>
      )}
      {analysis?.fundamentals_view && (
        <div className="mt-3 p-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
          <p className="label-small mb-1">Visión IA</p>
          <p className="text-xs text-[#0e1f1a] leading-relaxed">{analysis.fundamentals_view}</p>
        </div>
      )}
    </section>
  );
}

export function RisksCatalystsCard({ analysis }) {
  if (!analysis) return null;
  return (
    <section data-testid="risks-catalysts" className="card-flat p-6 animate-fade-up">
      <h3 className="font-heading font-semibold text-lg text-[#0e1f1a] mb-3">
        Riesgos y Catalizadores
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Warning size={14} weight="bold" className="text-[#d85c41]" />
            <p className="label-small">Riesgos</p>
          </div>
          <ul className="space-y-1.5">
            {(analysis.risks || []).map((r, i) => (
              <li key={i} className="text-xs text-[#0e1f1a] pl-3 border-l-2 border-[#d85c41]">
                {r}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Lightning size={14} weight="bold" className="text-[#4a7c59]" />
            <p className="label-small">Catalizadores</p>
          </div>
          <ul className="space-y-1.5">
            {(analysis.catalysts || []).map((c, i) => (
              <li key={i} className="text-xs text-[#0e1f1a] pl-3 border-l-2 border-[#4a7c59]">
                {c}
              </li>
            ))}
          </ul>
        </div>
      </div>
      {analysis.technical_analysis && (
        <div className="mt-4 p-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
          <p className="label-small mb-1">Análisis Técnico Detallado</p>
          <p className="text-xs text-[#0e1f1a] leading-relaxed">{analysis.technical_analysis}</p>
        </div>
      )}
    </section>
  );
}
