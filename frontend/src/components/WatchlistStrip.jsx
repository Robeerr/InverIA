import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useSignals } from "../hooks/useSignals";
import { fmtPrice } from "../lib/format";
import { api } from "../lib/api";

// Precarga: al dejar el ratón sobre una acción, pedimos su dashboard para que el backend lo
// deje cacheado. Cuando se hace clic, la respuesta ya está lista y la carga es inmediata.
// Guardas para no disparar peticiones de más:
//   - 180 ms de espera: pasar el ratón por encima de camino a otro sitio no cuenta.
//   - una sola vez por símbolo y sesión: el backend ya lo sirve de caché a partir de ahí.
//   - nada en pantallas táctiles (no hay hover: se dispararía en el propio toque, sin ganar
//     nada y gastando datos del móvil).
// Debe coincidir con el timeframe inicial del Dashboard (pages/Dashboard.jsx). Si difieren,
// la precarga calienta una clave de caché que nadie pide después.
const TIMEFRAME_DASHBOARD = "1D";
const yaPrecargados = new Set();
const hayHover = typeof window !== "undefined"
  && window.matchMedia?.("(hover: hover)").matches;

function usePrecarga() {
  const queryClient = useQueryClient();
  const timer = React.useRef(null);
  const cancelar = React.useCallback(() => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
  }, []);
  const precargar = React.useCallback((sym) => {
    if (!hayHover || !sym || yaPrecargados.has(sym)) return;
    cancelar();
    timer.current = setTimeout(() => {
      yaPrecargados.add(sym);
      // prefetchQuery y no api.dashboard() a secas: la respuesta se guarda en la MISMA
      // caché de react-query, con la MISMA clave, que luego lee el Dashboard.
      queryClient.prefetchQuery({
        queryKey: ["dashboard", sym, TIMEFRAME_DASHBOARD],
        queryFn: ({ signal }) => api.dashboard(sym, TIMEFRAME_DASHBOARD, signal),
        staleTime: 60_000,
      }).catch(() => yaPrecargados.delete(sym));
    }, 180);
  }, [cancelar, queryClient]);
  React.useEffect(() => cancelar, [cancelar]);
  return { precargar, cancelar };
}

const pct = (v) => `${v >= 0 ? "+" : ""}${v}%`;

/**
 * Tu watchlist como una cinta horizontal encima de la ficha.
 *
 * Antes era una columna lateral de 60 tarjetas que duplicaba el rail y empujaba la
 * ficha a un lado. Ahora es una cinta de una línea, con desplazamiento lateral (flechas
 * en escritorio, gesto en móvil) y la acción abierta levantada y a la vista. Orden: la
 * más cerca de su zona de compra primero.
 */
export default function WatchlistStrip({ symbol, setSymbol, className = "" }) {
  const { data: signals } = useSignals();
  const { precargar, cancelar } = usePrecarga();
  const carril = React.useRef(null);
  const [bordes, setBordes] = React.useState({ izq: false, der: false });

  const entries = React.useMemo(() => {
    const arr = Array.isArray(signals) ? signals : (signals?.items || signals?.entries || []);
    // Distancia (%) del precio a su zona de compra más cercana: los niveles de compra están
    // por DEBAJO del precio (compras en caídas). Cuanto menor, más cerca de entrar.
    const distBuy = (e) => {
      const px = Number(e.last_price);
      if (!px) return Infinity;
      const niveles = ["nivel1", "nivel2", "nivel3", "nivel4", "nivel5"]
        .map((k) => Number(e[k])).filter((v) => v > 0);
      if (!niveles.length) return Infinity;
      const below = niveles.filter((v) => v <= px);
      if (below.length) return ((px - Math.max(...below)) / px) * 100;   // aún por encima
      return ((px - Math.max(...niveles)) / px) * 100;                    // ya dentro/por debajo (negativo)
    };
    const seen = new Set();
    const out = [];
    for (const e of arr) {
      const s = (e.symbol || "").toUpperCase();
      if (!s || seen.has(s)) continue;
      seen.add(s);
      out.push({ ...e, _distBuy: distBuy(e) });
    }
    return out.sort((a, b) => a._distBuy - b._distBuy);
  }, [signals]);

  const medir = React.useCallback(() => {
    const el = carril.current;
    if (!el) return;
    setBordes({ izq: el.scrollLeft > 4, der: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
  }, []);

  // La acción abierta, a la vista: si es la 40.ª de la lista no puede quedar fuera.
  const activo = (symbol || "").toUpperCase();
  React.useEffect(() => {
    const el = carril.current;
    if (!el) return;
    const btn = el.querySelector('[aria-current="true"]');
    if (btn) {
      const izq = btn.offsetLeft - el.clientWidth / 2 + btn.clientWidth / 2;
      el.scrollTo({ left: Math.max(0, izq) });
    }
    medir();
  }, [activo, entries.length, medir]);

  if (!entries.length) return null;

  const desplazar = (dir) => {
    const el = carril.current;
    if (!el) return;
    el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: "smooth" });
  };

  const mascara = bordes.izq && bordes.der
    ? "linear-gradient(90deg, transparent, #000 48px, #000 calc(100% - 48px), transparent)"
    : bordes.der ? "linear-gradient(90deg, #000 calc(100% - 48px), transparent)"
      : bordes.izq ? "linear-gradient(90deg, transparent, #000 48px)" : undefined;

  const flecha = "hidden sm:inline-flex items-center justify-center w-8 h-8 rounded-[9px] shrink-0 text-tinta-3 " +
    "hover:text-tinta hover:bg-tinta/[0.06] disabled:opacity-30 disabled:pointer-events-none " +
    "transition-colors duration-150 ease-salida motion-reduce:transition-none";

  return (
    <nav aria-label="Tu watchlist" className={`flex items-center gap-1.5 min-w-0 ${className}`}>
      <span className="iv-etiqueta shrink-0 hidden md:block pr-2">Watchlist</span>
      <button type="button" className={flecha} onClick={() => desplazar(-1)} disabled={!bordes.izq} aria-label="Ver anteriores">
        <ChevronLeft className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" />
      </button>
      <div
        ref={carril}
        onScroll={medir}
        className="flex gap-1 overflow-x-auto no-scrollbar min-w-0 flex-1 scroll-smooth motion-reduce:scroll-auto py-1 -my-1"
        style={{ maskImage: mascara, WebkitMaskImage: mascara }}
      >
        {entries.map((e) => {
          const s = (e.symbol || "").toUpperCase();
          const active = s === activo;
          const chg = e.daily_change_percent;
          // Pre-market / after-hours. Fuera de esas franjas market_state viene REGULAR o
          // vacío y no se muestra nada: durante la sesión el precio YA es el de mercado.
          const estado = e.market_state;
          const extPrecio = estado === "PRE" ? e.pre_market_price
            : estado === "POST" ? e.post_market_price : null;
          const extChg = e.extended_change_percent;
          return (
            <button
              key={s}
              type="button"
              onClick={() => setSymbol?.(s)}
              onMouseEnter={() => precargar(s)}
              onMouseLeave={cancelar}
              onFocus={() => precargar(s)}
              aria-current={active ? "true" : undefined}
              title={extPrecio != null
                ? `${estado === "PRE" ? "Pre-apertura" : "Después del cierre"}: $${fmtPrice(extPrecio)}${extChg != null ? ` (${pct(extChg)})` : ""}`
                : undefined}
              className={`shrink-0 text-left rounded-[10px] px-3 py-1.5 min-h-[44px] sm:min-h-0 border
                          transition-[background-color,border-color] duration-150 ease-salida motion-reduce:transition-none ${
                active
                  ? "bg-superficie border-medio shadow-panel"
                  : "border-transparent hover:bg-tinta/[0.05]"
              }`}
            >
              <span className="flex items-baseline gap-2 whitespace-nowrap">
                <span className={`text-[13px] font-semibold tracking-[-0.01em] ${active ? "text-tinta" : "text-tinta-2"}`}>{s}</span>
                {chg != null && (
                  <span className={`iv-cifra text-[12px] ${chg >= 0 ? "text-sube" : "text-baja"}`}>{pct(chg)}</span>
                )}
              </span>
              <span className="flex items-baseline gap-1.5 whitespace-nowrap iv-cifra text-[11.5px] text-tinta-3 mt-0.5">
                {e.last_price != null ? `$${fmtPrice(e.last_price)}` : "—"}
                {extPrecio != null && (
                  <>
                    <span className="font-sans text-[11px]">{estado === "PRE" ? "pre" : "post"}</span>
                    <span className={extChg == null ? "" : extChg >= 0 ? "text-sube" : "text-baja"}>
                      {extChg != null ? pct(extChg) : `$${fmtPrice(extPrecio)}`}
                    </span>
                  </>
                )}
              </span>
            </button>
          );
        })}
      </div>
      <button type="button" className={flecha} onClick={() => desplazar(1)} disabled={!bordes.der} aria-label="Ver siguientes">
        <ChevronRight className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" />
      </button>
    </nav>
  );
}
