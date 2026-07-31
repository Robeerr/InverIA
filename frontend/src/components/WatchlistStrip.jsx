import React from "react";
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
const yaPrecargados = new Set();
const hayHover = typeof window !== "undefined"
  && window.matchMedia?.("(hover: hover)").matches;

function usePrecarga() {
  const timer = React.useRef(null);
  const cancelar = React.useCallback(() => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
  }, []);
  const precargar = React.useCallback((sym) => {
    if (!hayHover || !sym || yaPrecargados.has(sym)) return;
    cancelar();
    timer.current = setTimeout(() => {
      yaPrecargados.add(sym);
      api.dashboard(sym).catch(() => yaPrecargados.delete(sym));  // reintentable si falla
    }, 180);
  }, [cancelar]);
  React.useEffect(() => cancelar, [cancelar]);
  return { precargar, cancelar };
}

// Tira de watchlist (estilo terminal): tus acciones de Cartera en una fila horizontal
// scrollable, con precio y cambio del día. Toca una para cargarla al instante. Mobile-first.
export default function WatchlistStrip({ symbol, setSymbol, vertical = false, className = "" }) {
  const { data: signals } = useSignals();
  const { precargar, cancelar } = usePrecarga();
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
      // El nivel de compra alcanzable más alto (el primero que tocaría al caer).
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
    // Orden: más cerca de su zona de compra primero (las "en zona" arriba).
    return out.sort((a, b) => a._distBuy - b._distBuy);
  }, [signals]);

  if (!entries.length) return null;

  const wrapCls = vertical
    ? `flex flex-col gap-1.5 ${className}`
    : `flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 no-scrollbar ${className}`;

  return (
    <div className={wrapCls}>
      {vertical && <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-1 px-1">Watchlist</p>}
      {entries.map((e) => {
        const s = (e.symbol || "").toUpperCase();
        const active = s === (symbol || "").toUpperCase();
        const chg = e.daily_change_percent;
        const chgColor = chg == null ? "#5c6b66" : chg >= 0 ? "#4a7c59" : "#d85c41";
        // Pre-market / after-hours. El backend ya lo calcula y lo guarda en cada entrada
        // (market_state + pre/post_market_price + extended_change_percent); aquí solo faltaba
        // pintarlo. Fuera de esas franjas market_state viene REGULAR o vacío y no se muestra
        // nada, que es lo correcto: durante la sesión el precio de arriba YA es el de mercado.
        const estado = e.market_state;
        const extPrecio = estado === "PRE" ? e.pre_market_price
          : estado === "POST" ? e.post_market_price : null;
        const extChg = e.extended_change_percent;
        // Colores EN LÍNEA, no por clase, a propósito: el fondo de la tarjeta también se pinta
        // en línea (`background: "white"`) y por tanto NO lo remapea el modo oscuro. Si el
        // texto sí se remapeara, quedaría claro sobre blanco — medido: 1,67:1, invisible.
        // Mientras la tarjeta tenga el fondo en línea, el texto debe ir igual.
        const extCol = extChg == null ? "#5c6b66" : active
          ? (extChg >= 0 ? "#8fd6a6" : "#f0a598")
          : (extChg >= 0 ? "#4a7c59" : "#d85c41");
        return (
          <button
            key={s}
            onClick={() => setSymbol?.(s)}
            onMouseEnter={() => precargar(s)}
            onMouseLeave={cancelar}
            onFocus={() => precargar(s)}
            className={`rounded-lg border px-3 py-1.5 text-left transition-colors ${vertical ? "w-full" : "shrink-0"}`}
            style={{
              borderColor: active ? "#1a3a32" : "#e5e0d8",
              background: active ? "#1a3a32" : "white",
              minWidth: vertical ? undefined : 92,
            }}
          >
            <p className="font-mono font-bold text-xs" style={{ color: active ? "#f5f3ef" : "#0e1f1a" }}>{s}</p>
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-[11px]" style={{ color: active ? "#cdd8d2" : "#5c6b66" }}>
                {e.last_price != null ? `$${fmtPrice(e.last_price)}` : "—"}
              </span>
              {chg != null && (
                <span className="font-mono text-[10px] font-semibold" style={{ color: active ? (chg >= 0 ? "#8fd6a6" : "#f0a598") : chgColor }}>
                  {chg >= 0 ? "+" : ""}{chg}%
                </span>
              )}
            </div>
            {extPrecio != null && (
              <div className="flex items-baseline gap-1 mt-0.5" title={estado === "PRE" ? "Pre-apertura" : "Después del cierre"}>
                <span className="font-mono text-[8px] uppercase tracking-wider px-1 rounded"
                      style={{ color: active ? "#e6c98a" : "#8a6508",
                               background: active ? "rgba(255,255,255,0.10)" : "rgba(201,161,74,0.18)" }}>
                  {estado === "PRE" ? "PRE" : "POST"}
                </span>
                <span className="font-mono text-[10px]" style={{ color: active ? "#cdd8d2" : "#5c6b66" }}>
                  ${fmtPrice(extPrecio)}
                </span>
                {extChg != null && (
                  <span className="font-mono text-[9px] font-semibold" style={{ color: extCol }}>
                    {extChg >= 0 ? "+" : ""}{extChg}%
                  </span>
                )}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
