import React, { useState, useEffect } from "react";
import { TrendUp, TrendDown, Buildings, Bell, X, Check, Heart } from "@phosphor-icons/react";
import { fmtPrice, fmtPct, fmtNum } from "../lib/format";
import { api } from "../lib/api";
import { toast } from "sonner";

export default function QuoteHeader({ quote }) {
  const [alertOpen, setAlertOpen] = useState(false);
  const [alertPrice, setAlertPrice] = useState("");
  const [alertDir, setAlertDir] = useState("below");
  const [saving, setSaving] = useState(false);
  const [inWatch, setInWatch] = useState(false);
  const [watchBusy, setWatchBusy] = useState(false);

  const sym = quote?.symbol;
  // ¿La acción actual ya está en la watchlist? (para pintar el corazón lleno/vacío)
  useEffect(() => {
    let ok = true;
    if (!sym) return;
    api.watchlist.symbols()
      .then((list) => { if (ok) setInWatch(Array.isArray(list) && list.map((s) => (s || "").toUpperCase()).includes(sym.toUpperCase())); })
      .catch(() => {});
    return () => { ok = false; };
  }, [sym]);

  const toggleWatch = async () => {
    if (!sym || watchBusy) return;
    setWatchBusy(true);
    const next = !inWatch;
    setInWatch(next);  // optimista
    try {
      if (next) {
        await api.watchlist.add(sym);
        toast.success(`${sym} añadida a tu watchlist · se pre-analizará sola`);
      } else {
        await api.watchlist.remove(sym);
        toast.success(`${sym} quitada de la watchlist`);
      }
    } catch (err) {
      setInWatch(!next);  // revierte si falla
      toast.error(err?.response?.data?.detail || "No se pudo actualizar la watchlist");
    } finally {
      setWatchBusy(false);
    }
  };

  if (!quote) return null;
  const up = (quote.change ?? 0) >= 0;
  const Color = up ? "text-sube" : "text-baja";
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
    <section data-testid="quote-header" className="iv-panel p-6 animate-fade-up">
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div className="flex items-start gap-4 min-w-0">
          <div className="w-14 h-14 rounded-md bg-marca text-marca-tinta flex items-center justify-center font-mono font-bold text-lg shrink-0">
            {/* `?.` a propósito: un quote sin symbol tumbaba la vista ENTERA con un
                TypeError, y el usuario solo veía "algo se ha roto". Aunque el Dashboard ya
                garantiza que el symbol viene del servidor, un dato raro debe degradar lo
                que toca, no llevarse la pantalla por delante. */}
            {(quote.symbol || "—").slice(0, 3)}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 data-testid="quote-symbol" className="font-heading font-bold text-2xl md:text-3xl text-tinta">
                {quote.symbol}
              </h2>
              <span className="text-[10px] uppercase tracking-[0.2em] text-tinta-3 border border-linea rounded-full px-2 py-0.5">
                {quote.exchange || "NASDAQ"}
              </span>
              <span className="text-[10px] uppercase tracking-[0.2em] text-tinta-3">
                {quote.currency}
              </span>
              <button
                onClick={toggleWatch}
                disabled={watchBusy}
                title={inWatch ? "Quitar de la watchlist" : "Añadir a la watchlist (se pre-analiza sola)"}
                aria-label={inWatch ? "Quitar de la watchlist" : "Añadir a la watchlist"}
                className={`flex items-center justify-center w-7 h-7 rounded-full border transition-all disabled:opacity-50 ${
                  inWatch
                    ? "border-baja text-baja bg-baja/10"
                    : "border-linea text-tinta-3 hover:border-baja hover:text-baja"
                }`}
              >
                <Heart size={15} weight={inWatch ? "fill" : "regular"} />
              </button>
            </div>
            <p data-testid="quote-name" className="text-sm text-tinta-3 mt-1 truncate max-w-md">
              {quote.name}
            </p>
            {quote.sector && (
              <p className="text-xs text-tinta-3 mt-1 flex items-center gap-1">
                <Buildings size={12} />
                {quote.sector} · {quote.industry}
              </p>
            )}
          </div>
        </div>

        <div className="text-right flex flex-col items-end gap-2">
          <p data-testid="quote-price" className="font-mono font-semibold text-3xl md:text-4xl text-tinta leading-none">
            ${fmtPrice(quote.price)}
          </p>
          <div className={`font-mono text-sm flex items-center justify-end gap-1 ${Color}`}>
            <TrendIcon size={14} weight="bold" />
            <span data-testid="quote-change">
              {up ? "+" : ""}{fmtPrice(quote.change)} ({fmtPct(quote.change_percent)})
            </span>
          </div>
          {/* Solo se avisa cuando el precio NO viene de la fuente en directo. En condiciones
              normales no aparece nada: un sello de "en directo" permanente se vuelve ruido y
              se deja de mirar, justo hasta el día en que importa. */}
          {quote.precio_en_directo === false && (
            <span data-testid="quote-fuente"
                  title="Finnhub no respondió (cuota) y el precio viene de la fuente de respaldo, que puede ir con retraso. Se corrige solo en unos segundos."
                  className="font-mono text-[10px] uppercase tracking-wider text-aviso bg-aviso/15 rounded px-1.5 py-0.5">
              ⚠ precio de respaldo
            </span>
          )}
          {(() => {
            // Pre-market / after-hours: precio y % fuera de sesión (como en la watchlist).
            const st = quote.market_state;
            const extPx = st === "PRE" ? quote.pre_market_price : st === "POST" ? quote.post_market_price : null;
            if (extPx == null) return null;
            const extPct = quote.extended_change_percent;
            const extUp = (extPct ?? 0) >= 0;
            return (
              <div className={`font-mono text-xs flex items-center justify-end gap-1.5 ${extUp ? "text-sube" : "text-baja"}`}>
                <span className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-fondo text-tinta-3">
                  {st === "PRE" ? "PRE-MARKET" : "AFTER-HOURS"}
                </span>
                <span>${fmtPrice(extPx)}{extPct != null ? ` (${fmtPct(extPct)})` : ""}</span>
              </div>
            );
          })()}
          {/* Quick alert button */}
          <button
            onClick={() => { setAlertOpen((o) => !o); setAlertPrice(fmtPrice(quote.price)); }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-mono border transition-all ${
              alertOpen
                ? "bg-marca text-marca-tinta border-marca"
                : "border-linea text-tinta-3 hover:border-marca hover:text-tinta"
            }`}
          >
            <Bell size={12} weight={alertOpen ? "fill" : "regular"} />
            Alerta de precio
          </button>
        </div>
      </div>

      {/* Inline alert form */}
      {alertOpen && (
        <form onSubmit={createAlert} className="mt-4 p-4 bg-fondo rounded-lg border border-linea flex flex-wrap items-end gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono mb-1.5">Dirección</p>
            <div className="flex gap-1">
              {[{ v: "below", label: "≤ cae a" }, { v: "above", label: "≥ sube a" }].map(({ v, label }) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setAlertDir(v)}
                  className={`px-3 py-1.5 text-xs font-mono rounded border transition-all ${
                    alertDir === v
                      ? "bg-marca text-marca-tinta border-marca"
                      : "border-linea text-tinta-3 hover:border-marca"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono mb-1.5">Precio objetivo</p>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={alertPrice}
              onChange={(e) => setAlertPrice(e.target.value)}
              className="w-32 bg-white border border-linea rounded-md px-3 py-1.5 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-marca"
              placeholder="0.00"
            />
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-marca text-marca-tinta rounded-md text-xs font-mono hover:bg-tinta transition-colors disabled:opacity-50"
            >
              <Check size={12} />
              {saving ? "Guardando…" : "Crear alerta"}
            </button>
            <button
              type="button"
              onClick={() => setAlertOpen(false)}
              className="flex items-center gap-1 px-3 py-1.5 border border-linea text-tinta-3 rounded-md text-xs font-mono hover:border-marca transition-colors"
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
            <p data-testid={`stat-${s.label}`} className="font-mono text-base text-tinta mt-1">{s.value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
