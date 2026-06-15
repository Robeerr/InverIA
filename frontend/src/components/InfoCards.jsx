import React from "react";
import { Newspaper, ArrowSquareOut, Warning, Lightning, Users, ChartLineUp, Crosshair, Target } from "@phosphor-icons/react";
import { fmtPrice, fmtNum } from "../lib/format";

export function PricePredictionCard({ analysis, quote }) {
  const pp = analysis?.price_prediction;
  const ep = analysis?.earnings_prediction;
  const hasPP = pp && (pp.target_3m != null || pp.target_6m != null || pp.target_12m != null);
  const hasEP = ep && ep.will_beat;
  if (!hasPP && !hasEP) return null;
  const current = quote?.price;
  const conf = Math.max(0, Math.min(100, pp?.confidence || 0));
  const confColor = conf >= 70 ? "bg-[#4a7c59]" : conf >= 40 ? "bg-[#c9a14a]" : "bg-[#d85c41]";

  const Cell = ({ label, val }) => {
    const d = current && val ? ((val - current) / current) * 100 : null;
    return (
      <div className="bg-[#f5f3ef] border border-[#e5e0d8] rounded-md px-2 py-3 text-center">
        <p className="text-[10px] uppercase tracking-wider text-[#5c6b66]">{label}</p>
        <p className="font-mono font-bold text-lg text-[#0e1f1a] mt-1">{val != null ? `$${fmtPrice(val)}` : "—"}</p>
        {d != null && (
          <p className={`font-mono text-[11px] mt-0.5 ${d >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
            {d >= 0 ? "+" : ""}{d.toFixed(1)}%
          </p>
        )}
      </div>
    );
  };

  const beatStyle = {
    "SÍ":  { bg: "bg-[#4a7c59]/10", text: "text-[#4a7c59]", label: "Batirá ✓" },
    "SI":  { bg: "bg-[#4a7c59]/10", text: "text-[#4a7c59]", label: "Batirá ✓" },
    "NO":  { bg: "bg-[#d85c41]/10", text: "text-[#d85c41]", label: "No batirá" },
  };
  const beat = hasEP ? (beatStyle[(ep.will_beat || "").toUpperCase()] || { bg: "bg-[#5c6b66]/10", text: "text-[#5c6b66]", label: "Incierto" }) : null;

  return (
    <section data-testid="price-prediction" className="card-flat p-6 animate-fade-up">
      <div className="flex items-center gap-2 mb-3">
        <Crosshair size={18} weight="bold" className="text-[#1a3a32]" />
        <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Predicciones IA</h3>
      </div>

      {hasPP && (
        <>
          <div className="flex items-center justify-between mb-2">
            <p className="label-small">Precio objetivo estimado</p>
            <span className="font-mono text-[11px] text-[#5c6b66]">Confianza {conf}%</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Cell label="3 meses" val={pp.target_3m} />
            <Cell label="6 meses" val={pp.target_6m} />
            <Cell label="12 meses" val={pp.target_12m} />
          </div>
          <div className="h-1.5 bg-[#e5e0d8] rounded-full overflow-hidden mt-3">
            <div className={`h-full ${confColor} transition-all`} style={{ width: `${conf}%` }} />
          </div>
          {pp.rationale && (
            <p className="text-xs text-[#5c6b66] mt-3 leading-relaxed border-l-2 border-[#1a3a32] pl-3">{pp.rationale}</p>
          )}
        </>
      )}

      {hasEP && (
        <div className={`${hasPP ? "mt-4 pt-4 border-t border-[#e5e0d8]" : ""}`}>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="label-small">Próximos resultados (earnings)</p>
            <span className={`inline-flex px-2 py-0.5 rounded text-[11px] font-mono font-semibold ${beat.bg} ${beat.text}`}>
              {beat.label}{ep.confidence ? ` · ${ep.confidence}%` : ""}
            </span>
          </div>
          {ep.rationale && <p className="text-xs text-[#5c6b66] mt-2 leading-relaxed">{ep.rationale}</p>}
        </div>
      )}

      <p className="text-[10px] text-[#5c6b66] mt-3">Proyecciones estimadas por IA, no garantizadas. Solo educativo.</p>
    </section>
  );
}

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
          ["Ventas YoY", quote.revenue_growth != null ? `${quote.revenue_growth > 0 ? "+" : ""}${quote.revenue_growth}%` : "—"],
          ["EPS YoY", quote.eps_growth != null ? `${quote.eps_growth > 0 ? "+" : ""}${quote.eps_growth}%` : "—"],
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
      {analysis?.insider_view && (
        <div className="mt-3 p-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
          <p className="label-small mb-1">Insider Trading (directivos)</p>
          <p className="text-xs text-[#0e1f1a] leading-relaxed">{analysis.insider_view}</p>
        </div>
      )}
      {analysis?.earnings_view && (
        <div className="mt-3 p-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
          <p className="label-small mb-1">Historial de Resultados</p>
          <p className="text-xs text-[#0e1f1a] leading-relaxed">{analysis.earnings_view}</p>
        </div>
      )}
    </section>
  );
}

export function MarketSignalsCard({ insider, earningsHistory }) {
  if (!insider && !earningsHistory) return null;
  const isBuy = insider && insider.net_shares > 0;
  return (
    <section data-testid="market-signals" className="card-flat p-6 animate-fade-up">
      <h3 className="font-heading font-semibold text-lg text-[#0e1f1a] mb-3">
        Señales de Mercado
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {insider && (
          <div data-testid="insider-card" className="border border-[#e5e0d8] rounded-md p-4">
            <div className="flex items-center gap-2 mb-3">
              <Users size={14} weight="bold" className="text-[#1a3a32]" />
              <p className="label-small">Insider Trading (6 meses)</p>
            </div>
            <div className={`inline-flex px-2 py-1 rounded text-[11px] font-mono font-semibold mb-3 ${isBuy ? "bg-[#4a7c59]/10 text-[#4a7c59]" : "bg-[#d85c41]/10 text-[#d85c41]"}`}>
              {insider.signal}
            </div>
            <div className="flex gap-4 mb-3">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[#5c6b66]">Compras</p>
                <p className="font-mono text-sm text-[#4a7c59] font-semibold">{insider.buy_transactions}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[#5c6b66]">Ventas</p>
                <p className="font-mono text-sm text-[#d85c41] font-semibold">{insider.sell_transactions}</p>
              </div>
            </div>
            <div className="space-y-1 max-h-[140px] overflow-y-auto pr-1">
              {(insider.recent || []).map((t, i) => (
                <div key={i} className="flex items-center justify-between text-[11px] border-b border-[#e5e0d8] py-1">
                  <span className="text-[#5c6b66] truncate max-w-[120px]">{t.name || "—"}</span>
                  <span className={`font-mono ${(t.shares || 0) >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                    {(t.shares || 0) >= 0 ? "+" : ""}{fmtNum(t.shares)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        {earningsHistory && (
          <div data-testid="earnings-card" className="border border-[#e5e0d8] rounded-md p-4">
            <div className="flex items-center gap-2 mb-3">
              <ChartLineUp size={14} weight="bold" className="text-[#1a3a32]" />
              <p className="label-small">Historial Resultados (EPS)</p>
            </div>
            <div className="inline-flex px-2 py-1 rounded text-[11px] font-mono font-semibold mb-3 bg-[#1a3a32]/10 text-[#1a3a32]">
              Bate estimaciones {earningsHistory.beat_rate}% ({earningsHistory.beats}/{earningsHistory.total})
            </div>
            <div className="space-y-1">
              {(earningsHistory.quarters || []).map((q, i) => {
                const beat = q.actual != null && q.estimate != null && q.actual >= q.estimate;
                return (
                  <div key={i} className="flex items-center justify-between text-[11px] border-b border-[#e5e0d8] py-1">
                    <span className="text-[#5c6b66]">{q.period}</span>
                    <span className="font-mono text-[#0e1f1a]">
                      ${q.actual ?? "—"} <span className="text-[#5c6b66]">vs ${q.estimate ?? "—"}</span>
                    </span>
                    <span className={`font-mono ${beat ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                      {q.surprise_percent != null ? `${q.surprise_percent > 0 ? "+" : ""}${q.surprise_percent}%` : (beat ? "✓" : "✗")}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export function InvestmentThesisCard({ analysis }) {
  if (!analysis) return null;
  const { competitive_position, main_rival, sector_outlook } = analysis;
  if (!competitive_position && !main_rival && !sector_outlook) return null;
  return (
    <section data-testid="investment-thesis" className="card-flat p-6 animate-fade-up">
      <div className="flex items-center gap-2 mb-3">
        <ChartLineUp size={18} weight="bold" className="text-[#1a3a32]" />
        <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Tesis de Inversión</h3>
      </div>
      <div className="space-y-3">
        {competitive_position && (
          <div className="p-3 bg-[#f5f3ef] border-l-2 border-[#1a3a32] rounded">
            <p className="label-small mb-1">Posición competitiva</p>
            <p className="text-xs text-[#0e1f1a] leading-relaxed">{competitive_position}</p>
          </div>
        )}
        {main_rival && (
          <div className="p-3 bg-[#d85c41]/5 border-l-2 border-[#d85c41] rounded">
            <p className="label-small mb-1">Rival principal · mayor amenaza</p>
            <p className="text-xs text-[#0e1f1a] leading-relaxed">{main_rival}</p>
          </div>
        )}
        {sector_outlook && (
          <div className="p-3 bg-[#4a7c59]/5 border-l-2 border-[#4a7c59] rounded">
            <p className="label-small mb-1">Potencial del sector (3-5 años)</p>
            <p className="text-xs text-[#0e1f1a] leading-relaxed">{sector_outlook}</p>
          </div>
        )}
      </div>
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
      {(analysis.fibonacci_analysis || analysis.pattern_analysis) && (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          {analysis.fibonacci_analysis && (
            <div className="p-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
              <p className="label-small mb-1">Fibonacci</p>
              <p className="text-xs text-[#0e1f1a] leading-relaxed">{analysis.fibonacci_analysis}</p>
            </div>
          )}
          {analysis.pattern_analysis && (
            <div className="p-3 bg-[#f5f3ef] border border-[#e5e0d8] rounded-md">
              <p className="label-small mb-1">Patrones Técnicos</p>
              <p className="text-xs text-[#0e1f1a] leading-relaxed">{analysis.pattern_analysis}</p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
