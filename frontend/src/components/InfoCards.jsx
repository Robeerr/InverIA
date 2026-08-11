import React from "react";
import { Newspaper, ArrowSquareOut, Warning, Lightning, Users, ChartLineUp, Crosshair } from "@phosphor-icons/react";
import { fmtPrice, fmtNum } from "../lib/format";

export function PricePredictionCard({ analysis, quote }) {
  const pp = analysis?.price_prediction;
  const ep = analysis?.earnings_prediction;
  const hasPP = pp && (pp.target_3m != null || pp.target_6m != null || pp.target_12m != null);
  const hasEP = ep && ep.will_beat;
  if (!hasPP && !hasEP) return null;
  const current = quote?.price;
  const conf = Math.max(0, Math.min(100, pp?.confidence || 0));
  const confColor = conf >= 70 ? "bg-sube" : conf >= 40 ? "bg-aviso" : "bg-baja";

  const Cell = ({ label, val }) => {
    const d = current && val ? ((val - current) / current) * 100 : null;
    return (
      <div className="bg-fondo border border-linea rounded-md px-2 py-3 text-center">
        <p className="text-[10px] uppercase tracking-wider text-tinta-3">{label}</p>
        <p className="font-mono font-bold text-lg text-tinta mt-1">{val != null ? `$${fmtPrice(val)}` : "—"}</p>
        {d != null && (
          <p className={`font-mono text-[11px] mt-0.5 ${d >= 0 ? "text-sube" : "text-baja"}`}>
            {d >= 0 ? "+" : ""}{d.toFixed(1)}%
          </p>
        )}
      </div>
    );
  };

  const beatStyle = {
    "SÍ":  { bg: "bg-sube/10", text: "text-sube", label: "Batirá ✓" },
    "SI":  { bg: "bg-sube/10", text: "text-sube", label: "Batirá ✓" },
    "NO":  { bg: "bg-baja/10", text: "text-baja", label: "No batirá" },
  };
  const beat = hasEP ? (beatStyle[(ep.will_beat || "").toUpperCase()] || { bg: "bg-tinta-3/10", text: "text-tinta-3", label: "Incierto" }) : null;

  return (
    <section data-testid="price-prediction" className="iv-panel p-6 animate-fade-up">
      <div className="flex items-center gap-2 mb-3">
        <Crosshair size={18} weight="bold" className="text-marca" />
        <h3 className="font-heading font-semibold text-lg text-tinta">Predicciones IA</h3>
      </div>

      {hasPP && (
        <>
          <div className="flex items-center justify-between mb-2">
            <p className="label-small">Precio objetivo estimado</p>
            <span className="font-mono text-[11px] text-tinta-3">Confianza {conf}%</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Cell label="3 meses" val={pp.target_3m} />
            <Cell label="6 meses" val={pp.target_6m} />
            <Cell label="12 meses" val={pp.target_12m} />
          </div>
          <div className="h-1.5 bg-linea rounded-full overflow-hidden mt-3">
            <div className={`h-full ${confColor} transition-all`} style={{ width: `${conf}%` }} />
          </div>
          {pp.rationale && (
            <p className="text-xs text-tinta-3 mt-3 leading-relaxed border-l-2 border-marca pl-3">{pp.rationale}</p>
          )}
        </>
      )}

      {hasEP && (
        <div className={`${hasPP ? "mt-4 pt-4 border-t border-linea" : ""}`}>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="label-small">Próximos resultados (earnings)</p>
            <span className={`inline-flex px-2 py-0.5 rounded text-[11px] font-mono font-semibold ${beat.bg} ${beat.text}`}>
              {beat.label}{ep.confidence ? ` · ${ep.confidence}%` : ""}
            </span>
          </div>
          {ep.rationale && <p className="text-xs text-tinta-3 mt-2 leading-relaxed">{ep.rationale}</p>}
        </div>
      )}

      <p className="text-[10px] text-tinta-3 mt-3">Proyecciones estimadas por IA, no garantizadas. Solo educativo.</p>
    </section>
  );
}

export function NewsFeed({ news }) {
  if (!news || news.length === 0) {
    return (
      <section data-testid="news-feed" className="iv-panel p-6">
        <div className="flex items-center gap-2 mb-3">
          <Newspaper size={18} weight="bold" className="text-marca" />
          <h3 className="font-heading font-semibold text-lg text-tinta">Noticias</h3>
        </div>
        <p className="text-sm text-tinta-3">Sin noticias disponibles.</p>
      </section>
    );
  }

  return (
    <section data-testid="news-feed" className="iv-panel p-6 animate-fade-up">
      <div className="flex items-center gap-2 mb-4">
        <Newspaper size={18} weight="bold" className="text-marca" />
        <h3 className="font-heading font-semibold text-lg text-tinta">Noticias Recientes</h3>
      </div>
      <div className="space-y-3 max-h-[360px] overflow-y-auto pr-1">
        {news.map((n, i) => (
          <a
            key={i}
            data-testid={`news-item-${i}`}
            href={n.url}
            target="_blank"
            rel="noreferrer"
            className="group block p-3 bg-fondo border border-linea rounded-md hover:border-marca transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm text-tinta leading-snug group-hover:text-marca line-clamp-2">
                {n.title}
              </p>
              <ArrowSquareOut size={14} className="text-tinta-3 mt-0.5 shrink-0" />
            </div>
            <p className="text-[10px] text-tinta-3 mt-1 uppercase tracking-wider">
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
    <section data-testid="fundamentals" className="iv-panel p-6 animate-fade-up">
      <h3 className="font-heading font-semibold text-lg text-tinta mb-3">
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
          <div key={label} className="bg-fondo border border-linea rounded-md px-3 py-2">
            <p className="label-small">{label}</p>
            <p className="font-mono text-sm text-tinta mt-1">{val}</p>
          </div>
        ))}
      </div>
      {quote.description && (
        <>
          <div className="divider-soft my-4" />
          <p className="text-xs text-tinta-3 leading-relaxed">{quote.description}</p>
        </>
      )}
      {analysis?.fundamentals_view && (
        <div className="mt-3 p-3 bg-fondo border border-linea rounded-md">
          <p className="label-small mb-1">Visión IA</p>
          <p className="text-xs text-tinta leading-relaxed">{analysis.fundamentals_view}</p>
        </div>
      )}
      {analysis?.insider_view && (
        <div className="mt-3 p-3 bg-fondo border border-linea rounded-md">
          <p className="label-small mb-1">Insider Trading (directivos)</p>
          <p className="text-xs text-tinta leading-relaxed">{analysis.insider_view}</p>
        </div>
      )}
      {analysis?.earnings_view && (
        <div className="mt-3 p-3 bg-fondo border border-linea rounded-md">
          <p className="label-small mb-1">Historial de Resultados</p>
          <p className="text-xs text-tinta leading-relaxed">{analysis.earnings_view}</p>
        </div>
      )}
    </section>
  );
}

export function MarketSignalsCard({ insider, earningsHistory }) {
  if (!insider && !earningsHistory) return null;
  const isBuy = insider && insider.net_shares > 0;
  return (
    <section data-testid="market-signals" className="iv-panel p-6 animate-fade-up">
      <h3 className="font-heading font-semibold text-lg text-tinta mb-3">
        Señales de Mercado
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {insider && (
          <div data-testid="insider-card" className="border border-linea rounded-md p-4">
            <div className="flex items-center gap-2 mb-3">
              <Users size={14} weight="bold" className="text-marca" />
              <p className="label-small">Insider Trading (6 meses)</p>
            </div>
            <div className={`inline-flex px-2 py-1 rounded text-[11px] font-mono font-semibold mb-3 ${isBuy ? "bg-sube/10 text-sube" : "bg-baja/10 text-baja"}`}>
              {insider.signal}
            </div>
            <div className="flex gap-4 mb-3">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-tinta-3">Compras</p>
                <p className="font-mono text-sm text-sube font-semibold">{insider.buy_transactions}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-tinta-3">Ventas</p>
                <p className="font-mono text-sm text-baja font-semibold">{insider.sell_transactions}</p>
              </div>
            </div>
            <div className="space-y-1 max-h-[140px] overflow-y-auto pr-1">
              {(insider.recent || []).map((t, i) => (
                <div key={i} className="flex items-center justify-between text-[11px] border-b border-linea py-1">
                  <span className="text-tinta-3 truncate max-w-[120px]">{t.name || "—"}</span>
                  <span className={`font-mono ${(t.shares || 0) >= 0 ? "text-sube" : "text-baja"}`}>
                    {(t.shares || 0) >= 0 ? "+" : ""}{fmtNum(t.shares)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        {earningsHistory && (
          <div data-testid="earnings-card" className="border border-linea rounded-md p-4">
            <div className="flex items-center gap-2 mb-3">
              <ChartLineUp size={14} weight="bold" className="text-marca" />
              <p className="label-small">Historial Resultados (EPS)</p>
            </div>
            <div className="inline-flex px-2 py-1 rounded text-[11px] font-mono font-semibold mb-3 bg-marca/10 text-marca">
              Bate estimaciones {earningsHistory.beat_rate}% ({earningsHistory.beats}/{earningsHistory.total})
            </div>
            <div className="space-y-1">
              {(earningsHistory.quarters || []).map((q, i) => {
                const beat = q.actual != null && q.estimate != null && q.actual >= q.estimate;
                return (
                  <div key={i} className="flex items-center justify-between text-[11px] border-b border-linea py-1">
                    <span className="text-tinta-3">{q.period}</span>
                    <span className="font-mono text-tinta">
                      ${q.actual ?? "—"} <span className="text-tinta-3">vs ${q.estimate ?? "—"}</span>
                    </span>
                    <span className={`font-mono ${beat ? "text-sube" : "text-baja"}`}>
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

export function RisksCatalystsCard({ analysis }) {
  if (!analysis) return null;
  return (
    <section data-testid="risks-catalysts" className="iv-panel p-6 animate-fade-up">
      <h3 className="font-heading font-semibold text-lg text-tinta mb-3">
        Riesgos y Catalizadores
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Warning size={14} weight="bold" className="text-baja" />
            <p className="label-small">Riesgos</p>
          </div>
          <ul className="space-y-1.5">
            {(analysis.risks || []).map((r, i) => (
              <li key={i} className="text-xs text-tinta pl-3 border-l-2 border-baja">
                {r}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Lightning size={14} weight="bold" className="text-sube" />
            <p className="label-small">Catalizadores</p>
          </div>
          <ul className="space-y-1.5">
            {(analysis.catalysts || []).map((c, i) => (
              <li key={i} className="text-xs text-tinta pl-3 border-l-2 border-sube">
                {c}
              </li>
            ))}
          </ul>
        </div>
      </div>
      {analysis.technical_analysis && (
        <div className="mt-4 p-3 bg-fondo border border-linea rounded-md">
          <p className="label-small mb-1">Análisis Técnico Detallado</p>
          <p className="text-xs text-tinta leading-relaxed">{analysis.technical_analysis}</p>
        </div>
      )}
      {(analysis.fibonacci_analysis || analysis.pattern_analysis) && (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          {analysis.fibonacci_analysis && (
            <div className="p-3 bg-fondo border border-linea rounded-md">
              <p className="label-small mb-1">Fibonacci</p>
              <p className="text-xs text-tinta leading-relaxed">{analysis.fibonacci_analysis}</p>
            </div>
          )}
          {analysis.pattern_analysis && (
            <div className="p-3 bg-fondo border border-linea rounded-md">
              <p className="label-small mb-1">Patrones Técnicos</p>
              <p className="text-xs text-tinta leading-relaxed">{analysis.pattern_analysis}</p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
