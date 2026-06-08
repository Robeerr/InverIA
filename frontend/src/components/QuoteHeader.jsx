import React from "react";
import { TrendUp, TrendDown, Buildings, Star, StarHalf } from "@phosphor-icons/react";
import { fmtPrice, fmtPct, fmtNum } from "../lib/format";
import { Button } from "../components/ui/button";

export default function QuoteHeader({ quote, inWatchlist, onToggleWatchlist }) {
  if (!quote) return null;
  const up = (quote.change ?? 0) >= 0;
  const Color = up ? "text-[#4a7c59]" : "text-[#d85c41]";
  const TrendIcon = up ? TrendUp : TrendDown;

  return (
    <section data-testid="quote-header" className="card-flat p-6 animate-fade-up">
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div className="flex items-start gap-4 min-w-0">
          <div className="w-14 h-14 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center font-mono font-bold text-lg shrink-0">
            {quote.symbol.slice(0, 3)}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 data-testid="quote-symbol" className="font-heading font-bold text-2xl md:text-3xl text-[#0e1f1a]">
                {quote.symbol}
              </h2>
              <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] border border-[#e5e0d8] rounded-full px-2 py-0.5">
                {quote.exchange || "NASDAQ"}
              </span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">
                {quote.currency}
              </span>
            </div>
            <p data-testid="quote-name" className="text-sm text-[#5c6b66] mt-1 truncate max-w-md">
              {quote.name}
            </p>
            {quote.sector && (
              <p className="text-xs text-[#5c6b66] mt-1 flex items-center gap-1">
                <Buildings size={12} />
                {quote.sector} · {quote.industry}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-end gap-6">
          <div className="text-right">
            <p data-testid="quote-price" className="font-mono font-semibold text-3xl md:text-4xl text-[#0e1f1a] leading-none">
              ${fmtPrice(quote.price)}
            </p>
            <div className={`mt-2 font-mono text-sm flex items-center justify-end gap-1 ${Color}`}>
              <TrendIcon size={14} weight="bold" />
              <span data-testid="quote-change">
                {up ? "+" : ""}{fmtPrice(quote.change)} ({fmtPct(quote.change_percent)})
              </span>
            </div>
          </div>
          <Button
            data-testid="watchlist-toggle"
            onClick={onToggleWatchlist}
            variant="outline"
            size="icon"
            className="border-[#e5e0d8] hover:bg-[#e5e0d8]"
            title={inWatchlist ? "Quitar de watchlist" : "Añadir a watchlist"}
          >
            {inWatchlist ? <Star size={18} weight="fill" className="text-[#1a3a32]" /> : <StarHalf size={18} />}
          </Button>
        </div>
      </div>

      <div className="divider-soft mt-6 mb-4" />

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {[
          { label: "Apertura", value: `$${fmtPrice(quote.open)}` },
          { label: "Anterior", value: `$${fmtPrice(quote.previous_close)}` },
          { label: "Máx. Día", value: `$${fmtPrice(quote.day_high)}` },
          { label: "Mín. Día", value: `$${fmtPrice(quote.day_low)}` },
          { label: "Volumen", value: fmtNum(quote.volume) },
          { label: "Cap. Mercado", value: `$${fmtNum(quote.market_cap)}` },
        ].map((s) => (
          <div key={s.label}>
            <p className="label-small">{s.label}</p>
            <p data-testid={`stat-${s.label}`} className="font-mono text-base text-[#0e1f1a] mt-1">{s.value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
