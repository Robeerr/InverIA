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
    /* Masthead editorial, no tarjeta. Es la cabecera de la pagina: va a sangre con
       el filete champan encima, igual que el veredicto de la portada.
       Se retira el cuadrado relleno con las tres primeras letras del ticker. Era el
       mismo gesto generico que se quito del rail —un cuadro de color de marca con
       algo dentro—, y ademas competia con el ticker que tenia al lado, que es el
       dato de verdad. El ticker sube a mono grande y manda el solo. */
    <section data-testid="quote-header" className="iv-veredicto animate-fade-up motion-reduce:animate-none">
      <div className="flex items-start justify-between gap-x-6 gap-y-4 flex-wrap">
        <div className="flex items-start gap-4 min-w-0 flex-1 basis-56">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              {/* `||` a proposito: un quote sin symbol tumbaba la vista ENTERA con un
                  TypeError, y el usuario solo veia "algo se ha roto". Aunque el Dashboard
                  ya garantiza que el symbol viene del servidor, un dato raro debe degradar
                  lo que toca, no llevarse la pantalla por delante. */}
              <h2 data-testid="quote-symbol" className="font-mono font-semibold text-2xl md:text-[28px] tracking-[0.01em] text-tinta leading-none">
                {quote.symbol || "—"}
              </h2>
              {/* Bolsa y divisa en una sola etiqueta, sin caja: son metadatos, no
                  controles, y el recuadro los hacía parecer pulsables. */}
              <span className="iv-etiqueta">
                {quote.exchange || "NASDAQ"}{quote.currency ? ` · ${quote.currency}` : ""}
              </span>
              <button
                onClick={toggleWatch}
                disabled={watchBusy}
                title={inWatch ? "Quitar de la watchlist" : "Añadir a la watchlist (se pre-analiza sola)"}
                aria-label={inWatch ? "Quitar de la watchlist" : "Añadir a la watchlist"}
                aria-pressed={inWatch}
                className={`flex items-center justify-center w-8 h-8 rounded-full border transition-colors duration-150
                            motion-reduce:transition-none active:scale-95 disabled:opacity-50 ${
                  inWatch
                    ? "border-baja/50 text-baja bg-baja/10"
                    : "border-linea text-tinta-3 hover:border-baja/60 hover:text-baja"
                }`}
              >
                <Heart size={15} weight={inWatch ? "fill" : "regular"} aria-hidden="true" />
              </button>
            </div>
            <p data-testid="quote-name" className="text-apoyo text-tinta-2 mt-1.5 truncate max-w-md">
              {quote.name}
            </p>
            {quote.sector && (
              <p className="text-etiqueta text-tinta-3 mt-1 flex items-center gap-1.5">
                <Buildings size={12} aria-hidden="true" className="shrink-0" />
                <span className="truncate">{quote.sector} · {quote.industry}</span>
              </p>
            )}
          </div>
        </div>

        <div className="text-right flex flex-col items-end gap-2 min-w-0 max-w-full">
          {/* Tamaño fluido y cifras tabulares: con siete dígitos el precio se encoge en
              vez de salirse por la derecha en el móvil, y no baila al llegar cada tick. */}
          <p data-testid="quote-price" className="iv-cifra font-semibold text-[clamp(32px,8vw,48px)] text-tinta leading-none tracking-[-0.02em] break-all">
            ${fmtPrice(quote.price)}
          </p>
          <div className={`iv-cifra text-apoyo font-medium flex items-center justify-end gap-1 ${Color}`}>
            <TrendIcon size={14} weight="bold" aria-hidden="true" />
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
              precio de respaldo
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
              <div className={`iv-cifra text-etiqueta flex items-center justify-end gap-1.5 ${extUp ? "text-sube" : "text-baja"}`}>
                <span className="iv-etiqueta">
                  {st === "PRE" ? "PRE-MARKET" : "AFTER-HOURS"}
                </span>
                <span>${fmtPrice(extPx)}{extPct != null ? ` (${fmtPct(extPct)})` : ""}</span>
              </div>
            );
          })()}
          {/* Quick alert button */}
          <button
            onClick={() => { setAlertOpen((o) => !o); setAlertPrice(fmtPrice(quote.price)); }}
            aria-expanded={alertOpen}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-iv text-etiqueta font-mono border
                        transition-colors duration-150 motion-reduce:transition-none ${
              alertOpen
                ? "bg-marca/10 text-marca border-marca/50"
                : "border-linea text-tinta-2 hover:border-marca/50 hover:text-tinta"
            }`}
          >
            <Bell size={12} weight={alertOpen ? "fill" : "regular"} aria-hidden="true" />
            Alerta de precio
          </button>
        </div>
      </div>

      {/* Inline alert form */}
      {alertOpen && (
        <form onSubmit={createAlert} className="mt-4 p-4 bg-superficie rounded-iv border border-linea flex flex-wrap items-end gap-3">
          <div>
            <p className="iv-etiqueta mb-1.5">Dirección</p>
            <div className="flex gap-1">
              {[{ v: "below", label: "≤ cae a" }, { v: "above", label: "≥ sube a" }].map(({ v, label }) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setAlertDir(v)}
                  aria-pressed={alertDir === v}
                  className={`px-3 py-1.5 text-etiqueta font-mono rounded border transition-colors duration-150 motion-reduce:transition-none ${
                    alertDir === v
                      ? "bg-marca/10 text-marca border-marca/50"
                      : "border-linea text-tinta-2 hover:border-marca/50"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label htmlFor="alerta-precio" className="iv-etiqueta mb-1.5 block">Precio objetivo</label>
            <input
              id="alerta-precio"
              type="number"
              step="0.01"
              min="0.01"
              inputMode="decimal"
              value={alertPrice}
              onChange={(e) => setAlertPrice(e.target.value)}
              className="w-32 bg-superficie border border-linea rounded-iv px-3 py-1.5 iv-cifra text-base sm:text-apoyo focus:outline-none focus:ring-2 focus:ring-marca"
              placeholder="0.00"
            />
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-marca text-marca-tinta rounded-iv text-etiqueta font-mono font-semibold
                         hover:brightness-110 active:scale-[0.97] transition-[filter,transform] duration-150
                         motion-reduce:transition-none disabled:opacity-50"
            >
              <Check size={12} aria-hidden="true" />
              {saving ? "Guardando…" : "Crear alerta"}
            </button>
            <button
              type="button"
              onClick={() => setAlertOpen(false)}
              className="flex items-center gap-1 px-3 py-1.5 border border-linea text-tinta-2 rounded-iv text-etiqueta font-mono
                         hover:border-linea-marcada hover:text-tinta transition-colors duration-150 motion-reduce:transition-none"
            >
              <X size={12} aria-hidden="true" />
              Cancelar
            </button>
          </div>
        </form>
      )}

      {/* Los datos del día como una lista de definición: rótulo arriba, cifra tabular
          debajo, todas a la misma altura de línea para que la fila se lea de un tirón. */}
      <dl className="mt-6 pt-4 border-t border-linea grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-4 gap-y-3">
        {[
          { label: "Apertura", value: `$${fmtPrice(quote.open)}` },
          { label: "Anterior", value: `$${fmtPrice(quote.previous_close)}` },
          { label: "Máx. Día", value: `$${fmtPrice(quote.day_high)}` },
          { label: "Mín. Día", value: `$${fmtPrice(quote.day_low)}` },
          { label: "Volumen", value: fmtNum(quote.volume) },
          { label: "Cap. Mercado", value: `$${fmtNum(quote.market_cap)}` },
        ].map((s) => (
          <div key={s.label} className="min-w-0">
            <dt className="iv-etiqueta">{s.label}</dt>
            <dd data-testid={`stat-${s.label}`} className="iv-cifra text-cuerpo text-tinta mt-0.5 truncate" title={s.value}>{s.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
