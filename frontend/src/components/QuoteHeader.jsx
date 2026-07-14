import React, { useState } from "react";
import { TrendUp, TrendDown, Buildings, Bell, X, Check } from "@phosphor-icons/react";
import { fmtPrice, fmtPct, fmtNum } from "../lib/format";
import { api } from "../lib/api";
import { toast } from "sonner";

export default function QuoteHeader({ quote }) {
  const [alertOpen, setAlertOpen] = useState(false);
  const [alertPrice, setAlertPrice] = useState("");
  const [alertDir, setAlertDir] = useState("below");
  const [saving, setSaving] = useState(false);

  if (!quote) return null;
  const up = (quote.change ?? 0) >= 0;
  const Color = up ? "text-[#4a7c59]" : "text-[#d85c41]";
  const TrendIcon = up ? TrendUp : TrendDown;

  const createAlert = async (e) => {
    e.preventDefault();
    const price = parseFloat(alertPrice);
    if (!price || price <= 0) { toast.error("Introduce un precio válido"); return; }
    setSaving(true);
    try {
      await api.alerts.create({ symbol: quote.symbol, target_price: price, direction: alertDir });
      toast.success(`Alerta creada: ${quote.symbol} ${alertDir === "below" ? "≤" : "≥"} $${fmtPrice(price)}`);
      setAlertOpen(false);
      setAlertPrice("");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Error al crear la alerta");
    } finally {
      setSaving(false);
    }
  };

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

        <div className="text-right flex flex-col items-end gap-2">
          <p data-testid="quote-price" className="font-mono font-semibold text-3xl md:text-4xl text-[#0e1f1a] leading-none">
            ${fmtPrice(quote.price)}
          </p>
          <div className={`font-mono text-sm flex items-center justify-end gap-1 ${Color}`}>
            <TrendIcon size={14} weight="bold" />
            <span data-testid="quote-change">
              {up ? "+" : ""}{fmtPrice(quote.change)} ({fmtPct(quote.change_percent)})
            </span>
          </div>
          {(() => {
            // Pre-market / after-hours: precio y % fuera de sesión (como en la watchlist).
            const st = quote.market_state;
            const extPx = st === "PRE" ? quote.pre_market_price : st === "POST" ? quote.post_market_price : null;
            if (extPx == null) return null;
            const extPct = quote.extended_change_percent;
            const extUp = (extPct ?? 0) >= 0;
            return (
              <div className={`font-mono text-xs flex items-center justify-end gap-1.5 ${extUp ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                <span className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-[#f0ece3] text-[#5c6b66]">
                  {st === "PRE" ? "PRE-MARKET" : "AFTER-HOURS"}
                </span>
                <span>${fmtPrice(extPx)}{extPct != null ? ` (${extUp ? "+" : ""}${fmtPct(extPct)})` : ""}</span>
              </div>
            );
          })()}
          {/* Quick alert button */}
          <button
            onClick={() => { setAlertOpen((o) => !o); setAlertPrice(fmtPrice(quote.price)); }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono border transition-all ${
              alertOpen
                ? "bg-[#1a3a32] text-[#f5f3ef] border-[#1a3a32]"
                : "border-[#e5e0d8] text-[#5c6b66] hover:border-[#1a3a32] hover:text-[#0e1f1a]"
            }`}
          >
            <Bell size={12} weight={alertOpen ? "fill" : "regular"} />
            Alerta de precio
          </button>
        </div>
      </div>

      {/* Inline alert form */}
      {alertOpen && (
        <form onSubmit={createAlert} className="mt-4 p-4 bg-[#f5f3ef] rounded-lg border border-[#e5e0d8] flex flex-wrap items-end gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-1.5">Dirección</p>
            <div className="flex gap-1">
              {[{ v: "below", label: "≤ cae a" }, { v: "above", label: "≥ sube a" }].map(({ v, label }) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setAlertDir(v)}
                  className={`px-3 py-1.5 text-xs font-mono rounded border transition-all ${
                    alertDir === v
                      ? "bg-[#1a3a32] text-[#f5f3ef] border-[#1a3a32]"
                      : "border-[#e5e0d8] text-[#5c6b66] hover:border-[#1a3a32]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-1.5">Precio objetivo</p>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={alertPrice}
              onChange={(e) => setAlertPrice(e.target.value)}
              className="w-32 bg-white border border-[#e5e0d8] rounded-md px-3 py-1.5 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a32]"
              placeholder="0.00"
            />
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-[#1a3a32] text-[#f5f3ef] rounded-md text-xs font-mono hover:bg-[#0e1f1a] transition-colors disabled:opacity-50"
            >
              <Check size={12} />
              {saving ? "Guardando…" : "Crear alerta"}
            </button>
            <button
              type="button"
              onClick={() => setAlertOpen(false)}
              className="flex items-center gap-1 px-3 py-1.5 border border-[#e5e0d8] text-[#5c6b66] rounded-md text-xs font-mono hover:border-[#1a3a32] transition-colors"
            >
              <X size={12} />
              Cancelar
            </button>
          </div>
        </form>
      )}

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
