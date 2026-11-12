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
      <div className="px-3 py-2.5 min-w-0 first:pl-0">
        <p className="iv-etiqueta">{label}</p>
        <p className="iv-cifra font-semibold text-cuerpo text-tinta mt-0.5 break-all">{val != null ? `$${fmtPrice(val)}` : "—"}</p>
        {d != null && (
          <p className={`iv-cifra text-etiqueta mt-0.5 ${d >= 0 ? "text-sube" : "text-baja"}`}>
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
    <section data-testid="price-prediction" className="iv-panel p-5">
      <div className="flex items-center gap-2 mb-3">
        <Crosshair size={18} weight="bold" className="text-marca" />
        <h3 className="text-[13px] font-medium text-tinta-2">Predicciones IA</h3>
      </div>

      {hasPP && (
        <>
          <div className="flex items-center justify-between mb-2">
            <p className="iv-etiqueta">Precio objetivo estimado</p>
            <span className="iv-cifra text-etiqueta text-tinta-3">Confianza {conf}%</span>
          </div>
          <div className="grid grid-cols-3 divide-x divide-linea border-y border-linea">
            <Cell label="3 meses" val={pp.target_3m} />
            <Cell label="6 meses" val={pp.target_6m} />
            <Cell label="12 meses" val={pp.target_12m} />
          </div>
          <div className="h-1.5 bg-linea rounded-full overflow-hidden mt-3" aria-hidden="true">
            <div className={`h-full ${confColor}`} style={{ width: `${conf}%` }} />
          </div>
          {pp.rationale && (
            <p className="text-apoyo text-tinta-2 mt-3 leading-relaxed max-w-[75ch]">{pp.rationale}</p>
          )}
        </>
      )}

      {hasEP && (
        <div className={`${hasPP ? "mt-4 pt-4 border-t border-linea" : ""}`}>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="iv-etiqueta">Próximos resultados (earnings)</p>
            <span className={`inline-flex px-2 py-0.5 rounded text-[11px] font-mono font-semibold ${beat.bg} ${beat.text}`}>
              {beat.label}{ep.confidence ? ` · ${ep.confidence}%` : ""}
            </span>
          </div>
          {ep.rationale && <p className="text-apoyo text-tinta-2 mt-2 leading-relaxed max-w-[75ch]">{ep.rationale}</p>}
        </div>
      )}

      <p className="text-etiqueta text-tinta-3 mt-3">Proyecciones estimadas por IA, no garantizadas. Solo educativo.</p>
    </section>
  );
}

export function NewsFeed({ news }) {
  if (!news || news.length === 0) {
    return (
      <section data-testid="news-feed" className="iv-panel p-5">
        <h3 className="text-[13px] font-medium text-tinta-2 flex items-center gap-2">
          <Newspaper size={16} weight="bold" className="text-tinta-3" aria-hidden="true" />
          Noticias
        </h3>
        <p className="text-apoyo text-tinta-3 mt-1">Sin noticias disponibles.</p>
      </section>
    );
  }

  // Lista con filetes, no una caja por titular: ocho recuadros con borde que se
  // iluminaban en naranja convertían la lectura de titulares en una rejilla de botones.
  return (
    <section data-testid="news-feed" className="iv-panel p-5">
      <h3 className="text-[13px] font-medium text-tinta-2 flex items-center gap-2 mb-2">
        <Newspaper size={16} weight="bold" className="text-tinta-3" aria-hidden="true" />
        Noticias recientes
        <span className="iv-cifra text-[12px] text-tinta-3 font-normal">· {news.length}</span>
      </h3>
      <ul className="divide-y divide-suave max-h-[420px] overflow-y-auto -mx-2 px-2" tabIndex={0} aria-label="Noticias recientes">
        {news.map((n, i) => (
          <li key={i}>
            <a
              data-testid={`news-item-${i}`}
              href={n.url}
              target="_blank"
              rel="noreferrer"
              className="group flex items-start justify-between gap-3 py-3 -mx-2 px-2 rounded-iv-sm
                         hover:bg-tinta/[0.04] transition-colors duration-150 motion-reduce:transition-none"
            >
              <span className="min-w-0">
                <span className="block text-[14px] font-medium text-tinta leading-snug group-hover:text-marca line-clamp-2
                                 transition-colors duration-150 motion-reduce:transition-none">
                  {n.title}
                </span>
                <span className="block text-[12px] text-tinta-3 mt-1">
                  {n.publisher || "—"}
                </span>
              </span>
              <ArrowSquareOut size={14} className="text-tinta-3 mt-0.5 shrink-0 group-hover:text-marca" aria-hidden="true" />
              <span className="sr-only">(se abre en otra pestaña)</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function FundamentalsCard({ quote, analysis }) {
  if (!quote) return null;
  return (
    <section data-testid="fundamentals" className="iv-panel p-5">
      <h3 className="text-[13px] font-medium text-tinta-2 mb-2">
        Fundamentales
      </h3>
      {/* Diez datos como tabla de dos columnas con filetes: rótulo a la izquierda y cifra
          tabular a la derecha. Antes eran diez cajas con borde, y la cifra arrancaba en un
          sitio distinto en cada una. */}
      <dl className="grid sm:grid-cols-2 gap-x-10">
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
          <div key={label} className="flex flex-wrap items-baseline justify-between gap-x-3 py-2.5 border-b border-suave">
            <dt className="text-[13px] text-tinta-3">{label}</dt>
            <dd className="iv-cifra text-[13.5px] text-tinta ml-auto text-right break-all">{val}</dd>
          </div>
        ))}
      </dl>
      {quote.description && (
        <p className="text-apoyo text-tinta-3 leading-relaxed mt-4 max-w-[80ch]">{quote.description}</p>
      )}
      {analysis?.fundamentals_view && (
        <div className="mt-4 pt-3 border-t border-linea">
          <p className="iv-etiqueta mb-1">Visión IA</p>
          <p className="text-apoyo text-tinta-2 leading-relaxed max-w-[75ch]">{analysis.fundamentals_view}</p>
        </div>
      )}
      {analysis?.insider_view && (
        <div className="mt-4 pt-3 border-t border-linea">
          <p className="iv-etiqueta mb-1">Insider Trading (directivos)</p>
          <p className="text-apoyo text-tinta-2 leading-relaxed max-w-[75ch]">{analysis.insider_view}</p>
        </div>
      )}
      {analysis?.earnings_view && (
        <div className="mt-4 pt-3 border-t border-linea">
          <p className="iv-etiqueta mb-1">Historial de Resultados</p>
          <p className="text-apoyo text-tinta-2 leading-relaxed max-w-[75ch]">{analysis.earnings_view}</p>
        </div>
      )}
    </section>
  );
}

export function MarketSignalsCard({ insider, earningsHistory }) {
  if (!insider && !earningsHistory) return null;
  const isBuy = insider && insider.net_shares > 0;
  return (
    <section data-testid="market-signals" className="iv-panel p-5">
      <h3 className="text-[13px] font-medium text-tinta-2 mb-3">
        Señales de Mercado
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {insider && (
          <div data-testid="insider-card" className="border border-linea rounded-iv p-4">
            <div className="flex items-center gap-2 mb-3">
              <Users size={14} weight="bold" className="text-marca" />
              <p className="iv-etiqueta">Insider Trading (6 meses)</p>
            </div>
            <div className={`inline-flex px-2 py-1 rounded text-[11px] font-mono font-semibold mb-3 ${isBuy ? "bg-sube/10 text-sube" : "bg-baja/10 text-baja"}`}>
              {insider.signal}
            </div>
            <div className="flex gap-4 mb-3">
              <div>
                <p className="iv-etiqueta">Compras</p>
                <p className="font-mono text-sm text-sube font-semibold">{insider.buy_transactions}</p>
              </div>
              <div>
                <p className="iv-etiqueta">Ventas</p>
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
          <div data-testid="earnings-card" className="border border-linea rounded-iv p-4">
            <div className="flex items-center gap-2 mb-3">
              <ChartLineUp size={14} weight="bold" className="text-marca" />
              <p className="iv-etiqueta">Historial Resultados (EPS)</p>
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
    <section data-testid="risks-catalysts" className="iv-panel p-5">
      <h3 className="text-[13px] font-medium text-tinta-2 mb-3">
        Riesgos y Catalizadores
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Warning size={14} weight="bold" className="text-baja" />
            <p className="iv-etiqueta">Riesgos</p>
          </div>
          <ul className="space-y-1.5">
            {(analysis.risks || []).map((r, i) => (
              <li key={i} className="text-apoyo text-tinta leading-snug pl-3 border-l-2 border-baja/60">
                {r}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Lightning size={14} weight="bold" className="text-sube" />
            <p className="iv-etiqueta">Catalizadores</p>
          </div>
          <ul className="space-y-1.5">
            {(analysis.catalysts || []).map((c, i) => (
              <li key={i} className="text-apoyo text-tinta leading-snug pl-3 border-l-2 border-sube/60">
                {c}
              </li>
            ))}
          </ul>
        </div>
      </div>
      {analysis.technical_analysis && (
        <div className="mt-4 p-3 bg-superficie-alt rounded-iv">
          <p className="iv-etiqueta mb-1">Análisis Técnico Detallado</p>
          <p className="text-apoyo text-tinta-2 leading-relaxed">{analysis.technical_analysis}</p>
        </div>
      )}
      {(analysis.fibonacci_analysis || analysis.pattern_analysis) && (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          {analysis.fibonacci_analysis && (
            <div className="p-3 bg-superficie-alt rounded-iv">
              <p className="iv-etiqueta mb-1">Fibonacci</p>
              <p className="text-apoyo text-tinta-2 leading-relaxed">{analysis.fibonacci_analysis}</p>
            </div>
          )}
          {analysis.pattern_analysis && (
            <div className="p-3 bg-superficie-alt rounded-iv">
              <p className="iv-etiqueta mb-1">Patrones Técnicos</p>
              <p className="text-apoyo text-tinta-2 leading-relaxed">{analysis.pattern_analysis}</p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
