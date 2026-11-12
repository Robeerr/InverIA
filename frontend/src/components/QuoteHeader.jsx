import React, { useState, useEffect } from "react";
import { Bell, Heart, Check, X, ArrowUpRight, ArrowDownRight, Moon } from "lucide-react";
import { fmtPrice, fmtPct, fmtNum } from "../lib/format";
import { api } from "../lib/api";
import { toast } from "sonner";
import Monograma from "./base/Monograma";
import Rango from "./base/Rango";
import Segmentado from "./base/Segmentado";
import { Boton } from "./base/Boton";

/** «1,234.56» → ["1,234", ".56"]: los céntimos van a menor tamaño, como en Cartera y Hoy. */
function partir(precio) {
  const t = fmtPrice(precio);
  const i = t.lastIndexOf(".");
  return i < 0 ? [t, ""] : [t.slice(0, i), t.slice(i)];
}

/**
 * Cabecera viva de la ficha: la cara de la acción y su precio como cifra héroe.
 *
 * Es lo único de la página que cambia en tiempo real (WebSocket), así que es la pieza
 * que manda: monograma + ticker + nombre a la izquierda, acciones discretas a la
 * derecha y, debajo, el precio a 44–64 px con la variación en una píldora de color.
 * La franja inferior es la sesión: el rango del día como barra (dónde está el precio
 * entre el mínimo y el máximo) y los datos de apertura, cierre anterior, volumen y
 * capitalización en columnas tabulares.
 */
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
  const Flecha = up ? ArrowUpRight : ArrowDownRight;
  const [entero, decimales] = partir(quote.price);

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

  // Pre-market / after-hours: precio y % fuera de sesión (como en la watchlist).
  const st = quote.market_state;
  const extPx = st === "PRE" ? quote.pre_market_price : st === "POST" ? quote.post_market_price : null;
  const extPct = quote.extended_change_percent;
  const extUp = (extPct ?? 0) >= 0;

  const hayRango = quote.day_low != null && quote.day_high != null && quote.price != null;
  const hay52 = quote.low_52w != null && quote.high_52w != null && quote.price != null;
  // Con barra de rango, el máximo y el mínimo del día ya se leen en sus extremos; sin
  // ella (falta algún dato) vuelven como columnas para no perderlos.
  const datos = [
    ...(hayRango ? [] : [
      { label: "Máx. Día", value: `$${fmtPrice(quote.day_high)}` },
      { label: "Mín. Día", value: `$${fmtPrice(quote.day_low)}` },
    ]),
    { label: "Apertura", value: `$${fmtPrice(quote.open)}` },
    { label: "Anterior", value: `$${fmtPrice(quote.previous_close)}` },
    { label: "Volumen", value: fmtNum(quote.volume) },
    { label: "Cap. Mercado", value: `$${fmtNum(quote.market_cap)}` },
  ];

  return (
    <section data-testid="quote-header" className="iv-panel overflow-hidden">
      <div className="p-5 sm:p-7">
        {/* Identidad */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3.5 min-w-0">
            <Monograma symbol={quote.symbol} tamano="lg" />
            <div className="min-w-0">
              <div className="flex items-baseline gap-2.5 flex-wrap">
                {/* `||` a propósito: un quote sin symbol tumbaba la vista ENTERA con un
                    TypeError. Un dato raro debe degradar lo que toca, no la pantalla. */}
                <h1 data-testid="quote-symbol" className="text-[22px] sm:text-[24px] font-semibold tracking-[-0.03em] text-tinta leading-none">
                  {quote.symbol || "—"}
                </h1>
                <span className="text-[12px] text-tinta-3 whitespace-nowrap">
                  {quote.exchange || "NASDAQ"}{quote.currency ? ` · ${quote.currency}` : ""}
                </span>
              </div>
              <p data-testid="quote-name" className="text-[13px] text-tinta-2 mt-1.5 truncate max-w-[56ch]">
                {quote.name}
                {quote.sector && (
                  <span className="text-tinta-3 hidden sm:inline"> · {quote.sector}{quote.industry ? ` · ${quote.industry}` : ""}</span>
                )}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={toggleWatch}
              disabled={watchBusy}
              title={inWatch ? "Quitar de la watchlist" : "Añadir a la watchlist (se pre-analiza sola)"}
              aria-label={inWatch ? "Quitar de la watchlist" : "Añadir a la watchlist"}
              aria-pressed={inWatch}
              className={`inline-flex items-center justify-center w-11 h-11 sm:w-9 sm:h-9 rounded-[10px] border
                          transition-[color,background-color,border-color] duration-150 ease-salida motion-reduce:transition-none
                          disabled:opacity-50 ${
                inWatch
                  ? "border-baja/30 text-baja bg-baja/10"
                  : "border-suave bg-tinta/[0.04] text-tinta-3 hover:text-tinta hover:bg-tinta/[0.08]"
              }`}
            >
              <Heart className="w-4 h-4" strokeWidth={1.75} fill={inWatch ? "currentColor" : "none"} aria-hidden="true" />
            </button>
            <Boton
              variante={alertOpen ? "secundario" : "contorno"}
              onClick={() => { setAlertOpen((o) => !o); setAlertPrice(fmtPrice(quote.price)); }}
              aria-expanded={alertOpen}
              aria-label="Alerta de precio"
              className="h-11 w-11 px-0 sm:h-9 sm:w-auto sm:px-3.5"
            >
              <Bell className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" />
              <span className="hidden sm:inline">Alerta de precio</span>
            </Boton>
          </div>
        </div>

        {/* Precio: la cifra héroe de la pantalla. Tamaño fluido y cifras tabulares: con
            siete dígitos se encoge en vez de salirse, y no baila al llegar cada tick. */}
        <div className="mt-6 sm:mt-8 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-x-10 gap-y-6">
        <div className="min-w-0">
        <div className="flex items-end gap-x-4 gap-y-3 flex-wrap">
          <p data-testid="quote-price" className="iv-cifra-hero text-[clamp(44px,7vw,64px)] leading-[0.95] tracking-[-0.045em] break-all">
            <span className="text-tinta-3 font-medium mr-[0.06em] text-[0.55em] align-[0.5em]">$</span>
            {entero}
            <span className="text-tinta-3 text-[0.55em] tracking-[-0.02em]">{decimales}</span>
          </p>
          <div className="flex items-center gap-2 pb-1 flex-wrap">
            <span
              data-testid="quote-change"
              className={`iv-cifra inline-flex items-center gap-1 h-7 px-2.5 rounded-[8px] text-[13px] font-medium ${
                up ? "bg-sube/[0.12] text-sube" : "bg-baja/[0.12] text-baja"
              }`}
            >
              <Flecha className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" />
              {up ? "+" : ""}{fmtPrice(quote.change)} ({fmtPct(quote.change_percent)})
            </span>
            <span className="text-[13px] text-tinta-3">hoy</span>
          </div>
        </div>

        {(extPx != null || quote.precio_en_directo === false) && (
          <div className="mt-3 flex items-center gap-x-4 gap-y-2 flex-wrap text-[13px]">
            {extPx != null && (
              <span className="inline-flex items-center gap-1.5 text-tinta-3">
                <Moon className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" />
                {st === "PRE" ? "Antes de la apertura" : "Después del cierre"}
                <span className="iv-cifra text-tinta ml-1">${fmtPrice(extPx)}</span>
                {extPct != null && (
                  <span className={`iv-cifra ${extUp ? "text-sube" : "text-baja"}`}>{fmtPct(extPct)}</span>
                )}
              </span>
            )}
            {/* Solo se avisa cuando el precio NO viene de la fuente en directo. Un sello de
                «en directo» permanente se vuelve ruido y se deja de mirar. */}
            {quote.precio_en_directo === false && (
              <span data-testid="quote-fuente"
                    title="Finnhub no respondió (cuota) y el precio viene de la fuente de respaldo, que puede ir con retraso. Se corrige solo en unos segundos."
                    className="inline-flex items-center h-[22px] px-2 rounded-md text-[12px] font-medium text-aviso bg-aviso/[0.12]">
                Precio de respaldo
              </span>
            )}
          </div>
        )}
        </div>

        {/* Dónde está el precio: en la sesión y en el año. Dos barras gemelas a la
            derecha del precio, en la misma pieza. */}
        {(hayRango || hay52) && (
          <div className="w-full lg:w-[340px] shrink-0 space-y-5">
            {hayRango && (
              <Rango etiqueta="Rango del día" min={quote.day_low} max={quote.day_high}
                     valor={quote.price} formato={(v) => `$${fmtPrice(v)}`} />
            )}
            {hay52 && (
              <Rango etiqueta="Rango 52 semanas" min={quote.low_52w} max={quote.high_52w}
                     valor={quote.price} formato={(v) => `$${fmtPrice(v)}`} />
            )}
          </div>
        )}
        </div>
      </div>

      {/* Alerta en línea: una franja de luz baja dentro de la pieza, no otra caja. */}
      {alertOpen && (
        <form onSubmit={createAlert}
              className="px-5 sm:px-7 py-4 bg-tinta/[0.03] border-t border-suave flex flex-wrap items-end gap-x-4 gap-y-3">
          <div>
            <p className="iv-etiqueta mb-1.5">Avisar cuando</p>
            <Segmentado
              etiqueta="Dirección de la alerta"
              opciones={[{ valor: "below", etiqueta: "≤ cae a" }, { valor: "above", etiqueta: "≥ sube a" }]}
              valor={alertDir}
              onCambio={setAlertDir}
            />
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
              className="w-36 h-[38px] bg-superficie-alt border border-medio rounded-iv px-3 iv-cifra text-base sm:text-[13px] text-tinta
                         focus:outline-none focus-visible:ring-2 focus-visible:ring-marca"
              placeholder="0.00"
            />
          </div>
          <div className="flex gap-2">
            <Boton type="submit" ocupado={saving}>
              <Check className="w-4 h-4" strokeWidth={2} aria-hidden="true" />
              {saving ? "Guardando…" : "Crear alerta"}
            </Boton>
            <Boton variante="fantasma" onClick={() => setAlertOpen(false)}>
              <X className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" />
              Cancelar
            </Boton>
          </div>
        </form>
      )}

      {/* La sesión: rango del día como barra y los datos en columnas tabulares. */}
      <div className={`border-t border-suave px-5 sm:px-7 py-4 sm:py-5 grid grid-cols-2 gap-x-6 gap-y-4 ${
        datos.length > 4 ? "sm:grid-cols-3 lg:grid-cols-6" : "sm:grid-cols-4"}`}>
        {datos.map((s) => (
          <dl key={s.label} className="min-w-0">
            <dt className="iv-etiqueta">{s.label}</dt>
            <dd data-testid={`stat-${s.label}`} className="iv-cifra text-[14.5px] text-tinta mt-1.5 truncate" title={s.value}>{s.value}</dd>
          </dl>
        ))}
      </div>
    </section>
  );
}
