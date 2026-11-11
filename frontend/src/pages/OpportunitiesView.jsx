import React from "react";
import { Lightning, TrendDown, TrendUp, Sparkle, Pulse, Sun, ArrowRight, ArrowClockwise, Funnel, Fire, Target, Star, Warning } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import Score from "../components/Score";
import { fmtPrice, fmtPct, fmtNum, SIN_DATO } from "../lib/format";
import { Cargando } from "../components/base/Estado";
import MiniChart from "../components/MiniChart";
import RadarView from "./RadarView";
import { useSearchParams } from "react-router-dom";

/* Oportunidades · rediseño en la línea de la pantalla Hoy
   ─────────────────────────────────────────────────────────────────────────────
   Las señales del día dejan de ser quince tarjetas iguales con un cuadro naranja que
   repetía el ticker: pasan a un único panel con filas, como una tabla de terminal.
   Cada fila lee de izquierda a derecha en el orden en que se decide —qué valor, por
   qué sale, a qué niveles está, a qué precio— y todas las cifras van en dígitos
   tabulares, alineadas a la derecha, para compararlas en vertical.

   El color se reserva para lo que significa algo: verde/rojo para la variación,
   naranja para el acento y la selección. Nada de esto cambia datos ni cálculos. */

const CATEGORY_META = {
  OVERSOLD: { label: "Sobrevendidas (RSI<30)", icon: TrendDown, color: "var(--iv-sube)", desc: "RSI muy bajo, posible rebote técnico" },
  DIP: { label: "Caídas Fuertes (Compra el dip)", icon: TrendDown, color: "var(--iv-baja)", desc: "Cayendo hoy, oportunidad si fundamentales son sólidos" },
  VALUE: { label: "Cerca de Mínimos 52sem", icon: Sun, color: "var(--iv-aviso)", desc: "Cerca de mínimos anuales, valor potencial" },
  MOMENTUM: { label: "Momentum Alcista", icon: TrendUp, color: "var(--iv-sube)", desc: "Tendencia alcista sana en marcha" },
  BREAKOUT: { label: "Breakout / Máximos 52sem", icon: Sparkle, color: "var(--iv-marca)", desc: "Rompiendo máximos, fuerza relativa alta" },
  GENERAL: { label: "Señales Mixtas", icon: Pulse, color: "var(--iv-tinta-3)", desc: "Combinación de señales positivas" },
};

/** Precio en dólares, o la raya sola si no hay dato. Antes salía «$—». */
const usd = (v) => {
  const p = fmtPrice(v);
  return p === SIN_DATO ? p : `$${p}`;
};

/** Transición común de hover/foco: solo color y fondo, corta y con salida suave. Nada
 *  se desplaza: en una lista larga, filas que saltan al pasar el ratón distraen. */
const TRANSICION = "transition-colors duration-150 ease-out motion-reduce:transition-none";

/** «Analizar →»: la misma llamada a la acción en filas y tarjetas. Se enciende en naranja
 *  cuando se pasa por encima del elemento entero (`group`). */
function Analizar() {
  return (
    <span className={`inline-flex items-center gap-1 iv-cifra text-etiqueta text-tinta-3 group-hover:text-marca group-focus-visible:text-marca ${TRANSICION}`}>
      Analizar
      <ArrowRight size={11} weight="bold" aria-hidden="true"
        className="transition-transform duration-150 ease-out [@media(hover:hover)]:group-hover:translate-x-0.5 motion-reduce:transition-none motion-reduce:translate-x-0" />
    </span>
  );
}

/** Un dato de la fila: rótulo y cifra. En móvil van en línea, unos tras otros; en
 *  escritorio se apilan con la cifra alineada a la derecha, como el desglose de Hoy. */
function Nivel({ etiqueta, titulo, children, className = "text-tinta" }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 lg:justify-between min-w-0">
      <dt className="iv-etiqueta" title={titulo}>{etiqueta}</dt>
      <dd className={`iv-cifra text-apoyo font-medium lg:ml-auto lg:text-right ${className}`}>{children}</dd>
    </div>
  );
}

function OpportunityCard({ op, onPick }) {
  const meta = CATEGORY_META[op.category] || CATEGORY_META.GENERAL;
  const up = (op.change_percent ?? 0) >= 0;
  const tonoConsenso = (op.consensus_score ?? 0) >= 80
    ? "text-sube"
    : (op.consensus_score ?? 0) >= 65
    ? "text-aviso"
    : "text-tinta-3";
  return (
    <li>
      <button
        type="button"
        data-testid={`opportunity-${op.symbol}`}
        onClick={() => onPick(op.symbol)}
        className={`group w-full text-left grid gap-x-4 gap-y-3 px-4 sm:px-5 py-4
                    grid-cols-[minmax(0,1fr)_auto]
                    lg:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_minmax(0,15rem)_minmax(0,8rem)] lg:gap-x-6
                    hover:bg-linea/25 focus-visible:bg-linea/25 active:bg-linea/40 focus-visible:outline-offset-[-2px] ${TRANSICION}`}
      >
        {/* Identidad: ticker, score y nombre. El punto de color dice la categoría. */}
        <div className="min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <span
              aria-hidden="true"
              title={meta.label}
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ background: `rgb(${meta.color})` }}
            />
            <span className={`iv-cifra text-cuerpo font-semibold text-tinta group-hover:text-marca ${TRANSICION}`}>
              {op.symbol}
            </span>
            <span className="iv-cifra text-etiqueta text-tinta-3 whitespace-nowrap">
              Score <span className="text-tinta-2 font-semibold">{op.score}</span>
            </span>
          </div>
          <p className="text-etiqueta text-tinta-3 truncate mt-0.5 pl-3.5">{op.name}</p>
          <span className="sr-only">Categoría: {meta.label}</span>
        </div>

        {/* Precio y variación. En móvil, arriba a la derecha; en escritorio, la última
            columna, alineada a la derecha como en un terminal. */}
        <div className="text-right lg:order-last min-w-0">
          <p className="iv-cifra text-cuerpo font-semibold text-tinta whitespace-nowrap leading-tight">
            ${fmtPrice(op.price)}
          </p>
          <p className={`iv-cifra text-apoyo font-medium ${up ? "text-sube" : "text-baja"}`}>
            {fmtPct(op.change_percent)}
          </p>
          <div className="hidden lg:block mt-1.5"><Analizar /></div>
        </div>

        {/* Lectura: el motivo y hasta tres señales. */}
        <div className="col-span-2 lg:col-span-1 min-w-0">
          {op.reason && (
            <p className="text-apoyo text-tinta-2 leading-snug">{op.reason}</p>
          )}
          {op.signals.length > 0 && (
            <ul className={`space-y-0.5 ${op.reason ? "mt-1.5" : ""}`}>
              {op.signals.slice(0, 3).map((s, i) => (
                <li key={i} className="text-apoyo text-tinta flex items-baseline gap-2 leading-snug">
                  <span aria-hidden="true" className="w-1 h-1 rounded-[1px] bg-marca/80 shrink-0 translate-y-[-2px]" />
                  <span className="min-w-0">{s}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Niveles: RSI, soporte, resistencia y consenso de analistas. */}
        <div className="col-span-2 lg:col-span-1 min-w-0 flex items-end justify-between gap-4">
          <dl className="flex flex-wrap gap-x-5 gap-y-1 lg:flex-col lg:gap-y-0.5 lg:w-full min-w-0">
            <Nivel etiqueta="RSI">{op.rsi ?? "—"}</Nivel>
            <Nivel etiqueta="Soporte"><span className="whitespace-nowrap">{usd(op.nearest_support)}</span></Nivel>
            <Nivel etiqueta="Resist." titulo="Resistencia"><span className="whitespace-nowrap">{usd(op.nearest_resistance)}</span></Nivel>
            <Nivel etiqueta="Analistas" className={op.analyst_consensus ? `font-semibold ${tonoConsenso}` : "text-tinta-3"}>
              {op.analyst_consensus ? (
                <span title={op.analysts_count ? `${op.analysts_count} analistas` : undefined}>
                  {op.analyst_consensus}
                  {op.analysts_count ? ` · ${op.analysts_count}` : ""}
                </span>
              ) : (
                "—"
              )}
            </Nivel>
          </dl>
          <div className="lg:hidden shrink-0"><Analizar /></div>
        </div>
      </button>
    </li>
  );
}

function ScreenerCard({ row, onPick, top }) {
  const dist = row.dist_52w_high;
  const distColor = dist == null ? "var(--iv-tinta-3)" : dist >= -5 ? "var(--iv-sube)" : dist >= -12 ? "var(--iv-aviso)" : "var(--iv-baja)";
  // Score de potencial: verde fuerte ≥70, ámbar 45-70, gris <45.
  const ps = row.potential_score;
  const psColor = ps == null ? "var(--iv-tinta-3)" : ps >= 70 ? "var(--iv-sube)" : ps >= 45 ? "var(--iv-aviso)" : "var(--iv-tinta-3)";
  const tonoCrec = (v) => (v == null ? "text-tinta-3" : v > 0 ? "text-sube" : v < 0 ? "text-baja" : "text-tinta");
  // La tarjeta entera navega, pero dentro vive el botón del desglose del score: por eso
  // no puede ser un <button> (no se anidan). Se hace pulsable con teclado a mano, y solo
  // cuando la tecla llega a la propia tarjeta, no al botón de dentro.
  const alTeclear = (e) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onPick(row.symbol);
    }
  };
  return (
    <div
      data-testid={`screener-${row.symbol}`}
      role="button"
      tabIndex={0}
      onKeyDown={alTeclear}
      className={`group relative flex flex-col p-4 sm:p-5 cursor-pointer min-w-0 ${TRANSICION} ${
        /* La Top Selección lleva el halo naranja de la app (`iv-destacada`) en vez de un
           borde doble propio: es el mismo gesto que marca «esto, primero» en Hoy. */
        top ? "iv-destacada" : "iv-panel hover:border-linea-fuerte"
      }`}
      onClick={() => onPick(row.symbol)}
    >
      {top && (
        <span className="absolute -top-2.5 left-4 inline-flex items-center gap-1 px-2 py-0.5 rounded-full iv-cifra text-etiqueta font-semibold tracking-wide text-marca-tinta bg-marca">
          <Star size={10} weight="fill" aria-hidden="true" />
          TOP SELECCIÓN
        </span>
      )}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={`iv-cifra text-cuerpo font-semibold text-tinta group-hover:text-marca ${TRANSICION}`}>{row.symbol}</p>
          <p className="text-etiqueta text-tinta-3 truncate">{row.name}</p>
          {row.fuentes && (
            <span className="inline-flex items-center gap-1 mt-1.5 px-1.5 py-0.5 rounded-iv-sm text-etiqueta font-semibold bg-info/10 text-info"
              title={`Mencionada por tus fuentes: ${(row.fuentes.fuentes || []).join(", ")}`}>
              Tus fuentes ({row.fuentes.menciones})
              {row.fuentes.positivos > 0 && ` · ${row.fuentes.positivos} a favor`}
              {row.fuentes.negativos > 0 && ` · ${row.fuentes.negativos} en contra`}
            </span>
          )}
        </div>
        {ps != null && (
          /* El chip es el mismo de siempre; `Score` solo lo hace desplegable. Cerrado se
             ve igual y no pide nada: la peticion ocurre en el primer clic. */
          <Score symbol={row.symbol}>
            <span
              className="px-2 py-0.5 rounded-full text-etiqueta font-mono font-bold tabular-nums"
              style={{ background: `rgb(${psColor} / 0.09)`, color: `rgb(${psColor})`, border: `1px solid rgb(${psColor} / 0.25)` }}
              title="Potencial a medio plazo: crecimiento + valoración + punto de entrada"
            >
              {ps} pts
            </span>
          </Score>
        )}
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 mt-3">
        <p className="iv-cifra text-titulo font-semibold text-tinta whitespace-nowrap">${fmtPrice(row.price)}</p>
        <span
          className="iv-cifra text-etiqueta font-semibold whitespace-nowrap"
          style={{ color: `rgb(${distColor})` }}
          title="Distancia al máximo de 52 semanas"
        >
          {dist != null ? `${dist}% máx.` : "—"}
        </span>
      </div>

      <div className="mt-2 space-y-0.5">
        {row.valuation && (
          <p className="iv-cifra text-etiqueta" style={{ color: `rgb(${psColor})` }}>
            {row.valuation}{row.pe_ratio ? ` · PER ${row.pe_ratio}` : ""}
          </p>
        )}
        {row.momentum && row.momentum !== "neutra" && (
          <p
            className="iv-cifra text-etiqueta"
            style={{ color: row.momentum.startsWith("⚠") ? "rgb(var(--iv-baja))" : "rgb(var(--iv-sube))" }}
          >
            {row.momentum}{row.return_52w != null ? ` · ${row.return_52w > 0 ? "+" : ""}${row.return_52w}% 1a` : ""}
          </p>
        )}
        {row.analyst_consensus && (
          <p className="iv-cifra text-etiqueta text-tinta-3">
            Analistas: <span className="text-marca font-semibold">{row.analyst_consensus}</span>
            {row.consensus_score != null ? ` (${row.consensus_score})` : ""}
          </p>
        )}
      </div>
      {row.reason && (
        <p className="text-apoyo text-tinta-2 mt-2 leading-snug">{row.reason}</p>
      )}
      {row.earnings_days != null && (
        <p className="flex items-start gap-1.5 iv-cifra text-etiqueta mt-2 text-baja bg-baja/10 rounded-iv-sm px-2 py-1.5">
          <Warning size={12} weight="bold" aria-hidden="true" className="shrink-0 mt-px" />
          <span>Resultados {row.earnings_days === 0 ? "HOY" : row.earnings_days === 1 ? "mañana" : `en ${row.earnings_days} días`} — riesgo binario</span>
        </p>
      )}

      {/* Crecimiento y volumen: tres cifras sin caja, separadas por filetes. */}
      <dl className="grid grid-cols-3 mt-3 pt-3 border-t border-linea divide-x divide-linea">
        <div className="min-w-0 pr-2">
          <dt className="iv-etiqueta truncate">Ventas YoY</dt>
          <dd className={`iv-cifra text-apoyo font-semibold mt-0.5 ${tonoCrec(row.revenue_growth)}`}>{row.revenue_growth != null ? `+${row.revenue_growth}%` : "—"}</dd>
        </div>
        <div className="min-w-0 px-2">
          <dt className="iv-etiqueta truncate">EPS YoY</dt>
          <dd className={`iv-cifra text-apoyo font-semibold mt-0.5 ${tonoCrec(row.eps_growth)}`}>{row.eps_growth != null ? `${row.eps_growth > 0 ? "+" : ""}${row.eps_growth}%` : "—"}</dd>
        </div>
        <div className="min-w-0 pl-2">
          <dt className="iv-etiqueta truncate">Vol. medio</dt>
          <dd className="iv-cifra text-apoyo font-semibold mt-0.5 text-tinta">{fmtNum(row.avg_volume)}</dd>
        </div>
      </dl>

      <div className="mt-3">
        <MiniChart symbol={row.symbol} />
      </div>

      <div className="flex items-center justify-between gap-3 mt-auto pt-2">
        <span className="text-etiqueta text-tinta-3 truncate min-w-0">{row.sector || "—"}</span>
        <Analizar />
      </div>
    </div>
  );
}

function MoversColumn({ title, icon: Icon, rows, color, porSigno = false, onPick }) {
  return (
    <section className="iv-panel overflow-hidden min-w-0" aria-label={title}>
      <div className="flex items-center gap-2 px-4 py-3 border-b border-linea">
        <Icon size={15} weight="bold" aria-hidden="true" style={{ color: `rgb(${color})` }} />
        <h3 className="font-heading font-semibold text-apoyo text-tinta">{title}</h3>
      </div>
      <div className="max-h-[520px] overflow-y-auto divide-y divide-linea">
        {(rows || []).length === 0 && <p className="text-apoyo text-tinta-3 py-6 text-center">—</p>}
        {(rows || []).map((r) => {
          const pct = r.change_percent;
          const tono = porSigno && pct != null
            ? (pct >= 0 ? "var(--iv-sube)" : "var(--iv-baja)")
            : color;
          return (
            <button
              type="button"
              key={r.symbol}
              onClick={() => onPick(r.symbol)}
              className={`group w-full text-left flex items-center justify-between gap-3 px-4 py-2 hover:bg-linea/25 focus-visible:bg-linea/25 focus-visible:outline-offset-[-2px] ${TRANSICION}`}
            >
              <div className="min-w-0">
                <p className={`iv-cifra font-semibold text-apoyo text-tinta group-hover:text-marca ${TRANSICION}`}>{r.symbol}</p>
                <p className="text-etiqueta text-tinta-3 truncate">{r.name}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="iv-cifra text-apoyo text-tinta whitespace-nowrap">${fmtPrice(r.price)}</p>
                <p className="iv-cifra text-etiqueta font-semibold" style={{ color: `rgb(${tono})` }}>
                  {pct != null ? `${pct >= 0 ? "+" : ""}${Number(pct).toFixed(2)}%` : "—"}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/** Pestaña de modo: texto con subrayado naranja cuando está activa, como las pestañas de
 *  un terminal. Antes eran cuatro botones-caja con el activo relleno de naranja. */
function TabButton({ id, mode, setMode, icon: Icon, children }) {
  const activa = mode === id;
  return (
    <button
      type="button"
      onClick={() => setMode(id)}
      aria-pressed={activa}
      className={`relative shrink-0 flex items-center gap-2 px-3 sm:px-4 py-2.5 text-apoyo font-medium whitespace-nowrap ${TRANSICION}
        after:absolute after:inset-x-3 sm:after:inset-x-4 after:-bottom-px after:h-0.5 after:rounded-full after:transition-colors after:duration-150
        ${activa
          ? "text-tinta after:bg-marca"
          : "text-tinta-3 hover:text-tinta after:bg-transparent hover:after:bg-linea-fuerte"}`}
    >
      <Icon size={15} weight="bold" aria-hidden="true" className={activa ? "text-marca" : ""} />
      {children}
    </button>
  );
}

/** Cabecera de cada modo: titular grande, entradilla y botón de refrescar, como en Hoy. */
function Cabecera({ titulo, children, accion, pie }) {
  return (
    <header className="iv-veredicto">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h2 className="iv-verbo text-tinta text-balance">{titulo}</h2>
          <p className="text-cuerpo text-tinta-2 mt-3 max-w-[62ch]">{children}</p>
        </div>
        <div className="shrink-0">{accion}</div>
      </div>
      {pie}
    </header>
  );
}

/** Panel de espera o de vacío: texto centrado y, si está cargando, la forma de lo que
 *  viene debajo para que la página no dé un salto al llegar los datos. */
function Aviso({ children, cargando = false, testId }) {
  return (
    <div className="iv-panel px-6 py-10 sm:py-12" data-testid={testId}>
      <p className="text-apoyo text-tinta-2 text-center max-w-[60ch] mx-auto">{children}</p>
      {cargando && <Cargando filas={3} className="mt-6 max-w-md mx-auto" />}
    </div>
  );
}

const BOTON_REFRESCAR = "border-linea font-mono text-xs";

// Los cuatro modos, en el orden en que se pintan. Fuera del componente porque
// también los valida la lectura de la URL.
const MODOS = ["signals", "screener", "movers", "fuentes"];

export default function OpportunitiesView({ setSymbol }) {
  /* El modo vive en la URL, no en estado local.
     ─────────────────────────────────────────────────────────────────────────
     Con `useState` esta pantalla tenía cuatro vistas y una sola dirección: no se
     podía enlazar a ninguna, ni marcarla, ni volver con el botón atrás. Y el
     enlace «Screener» del rail apuntaba aquí con `?modo=screener` sin que nadie
     leyera ese parámetro, así que navegaba y no pasaba nada.

     `signals` no se escribe en la URL: es el modo por defecto, y ensuciarla con
     el caso normal hace que compartir la dirección corriente parezca compartir
     un filtro. `replace` para que alternar pestañas no llene el historial. */
  const [params, setParams] = useSearchParams();
  const pedido = params.get("modo");
  const mode = MODOS.includes(pedido) ? pedido : "signals";
  const setMode = React.useCallback(
    (id) => setParams(id === "signals" ? {} : { modo: id }, { replace: true }),
    [setParams]
  );

  // --- Signals mode state ---
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [filter, setFilter] = React.useState("ALL");

  // --- Screener mode state ---
  const [screener, setScreener] = React.useState(null);
  const [screenerLoading, setScreenerLoading] = React.useState(false);

  // --- Movers mode state ---
  const [movers, setMovers] = React.useState(null);
  const [moversLoading, setMoversLoading] = React.useState(false);

  // True if a scan result is older than ~3 min (likely served from the persisted
  // snapshot after a restart while a fresh scan finishes in the background).
  const isStale = (d) => {
    if (!d?.generated_at) return false;
    return (Date.now() - new Date(d.generated_at).getTime()) > 3 * 60 * 1000;
  };

  const load = React.useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      const d = await api.opportunities(refresh);
      setData(d);
      if (d?.status === "warming") setTimeout(() => load(false), 8000);
      else if (isStale(d)) setTimeout(() => load(false), 90000); // pick up the fresh scan
    } catch (e) {
      // noop
    } finally {
      setLoading(false);
    }
  }, []);

  const loadScreener = React.useCallback(async (refresh = false) => {
    setScreenerLoading(true);
    try {
      const d = await api.opportunitiesScreener(refresh);
      setScreener(d);
      if (d?.status === "warming") setTimeout(() => loadScreener(false), 8000);
      else if (isStale(d)) setTimeout(() => loadScreener(false), 90000);
    } catch (e) {
      // noop
    } finally {
      setScreenerLoading(false);
    }
  }, []);

  const loadMovers = React.useCallback(async () => {
    setMoversLoading(true);
    try {
      setMovers(await api.marketMovers());
    } catch (e) {
      // noop
    } finally {
      setMoversLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  React.useEffect(() => {
    if (mode === "screener" && !screener) loadScreener();
  }, [mode, screener, loadScreener]);

  React.useEffect(() => {
    if (mode === "movers" && !movers) loadMovers();
  }, [mode, movers, loadMovers]);

  // setSymbol ya lleva a /accion/:symbol. El navigate("/") que había aquí ahora
  // llevaría a la portada en vez de a la acción que se acaba de elegir.
  const handlePick = (sym) => setSymbol(sym);

  const filtered = React.useMemo(() => {
    if (!data) return [];
    if (filter === "ALL") return data.top || [];
    return data.by_category?.[filter] || [];
  }, [data, filter]);

  const chipFiltro = (activo) =>
    /* Respuesta al pulsar: un 3 % de escala, 120 ms. Se ve que el filtro ha oído el clic
       antes de que cambie la lista. Sin movimiento con `prefers-reduced-motion`. */
    `inline-flex items-center gap-2 shrink-0 px-3 py-1.5 rounded-full text-apoyo border whitespace-nowrap
     transition-[color,background-color,border-color,transform] duration-150 ease-out active:scale-[0.97]
     motion-reduce:transition-none motion-reduce:active:scale-100 ${
      activo
        ? "bg-marca/10 border-marca/60 text-tinta"
        : "bg-transparent border-linea text-tinta-2 hover:border-linea-fuerte hover:text-tinta"
    }`;

  return (
    <div data-testid="opportunities-view" className="space-y-6 sm:space-y-8">
      {/* Mode tabs: una sola línea con filete inferior; en móvil se desliza en
          horizontal en vez de partirse en dos filas. */}
      <nav aria-label="Modos de Oportunidades"
           className="-mx-4 px-4 sm:mx-0 sm:px-0 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex border-b border-linea min-w-max sm:min-w-0">
          <TabButton id="signals" mode={mode} setMode={setMode} icon={Lightning}>Señales del día</TabButton>
          <TabButton id="screener" mode={mode} setMode={setMode} icon={Funnel}>Screener Crecimiento</TabButton>
          <TabButton id="movers" mode={mode} setMode={setMode} icon={Fire}>Movers del mercado</TabButton>
          <TabButton id="fuentes" mode={mode} setMode={setMode} icon={Target}>Tus fuentes</TabButton>
        </div>
      </nav>

      {/* ============ TUS FUENTES (antes /radar) ============ */}
      {mode === "fuentes" && <RadarView setSymbol={setSymbol} />}

      {/* ============ SIGNALS MODE ============ */}
      {mode === "signals" && (
        <>
          <Cabecera
            titulo="Oportunidades del día"
            accion={
              <Button
                data-testid="refresh-opportunities"
                onClick={() => load(true)}
                disabled={loading}
                variant="outline"
                className={BOTON_REFRESCAR}
              >
                <ArrowClockwise size={14} weight="bold" aria-hidden="true" className={`mr-1 ${loading ? "animate-spin motion-reduce:animate-none" : ""}`} />
                {loading ? "Escaneando..." : "Refrescar"}
              </Button>
            }
            pie={data?.generated_at && (
              <p className="iv-cifra text-etiqueta text-tinta-3 mt-3 flex flex-wrap gap-x-2 gap-y-0.5">
                <span>Último escaneo: {new Date(data.generated_at).toLocaleString("es-ES")}</span>
                <span aria-hidden="true" className="text-linea-marcada">·</span>
                <span>{data.opportunities_found} oportunidades detectadas</span>
                {isStale(data) && (
                  <>
                    <span aria-hidden="true" className="text-linea-marcada">·</span>
                    <span className="text-aviso">actualizando datos…</span>
                  </>
                )}
              </p>
            )}
          >
            Escaneo de {data?.universe_size || 30} acciones · Detecta sobrecompras, caídas fuertes, momentum y breakouts.
          </Cabecera>

          {data && (
            <div className="space-y-3">
              <div
                className="-mx-4 px-4 sm:mx-0 sm:px-0 flex gap-2 overflow-x-auto sm:flex-wrap sm:overflow-visible [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
                data-testid="category-filter"
              >
                <button type="button" onClick={() => setFilter("ALL")} aria-pressed={filter === "ALL"} className={chipFiltro(filter === "ALL")}>
                  Top 15
                  <span className="iv-cifra text-etiqueta text-tinta-3">{data.top?.length || 0}</span>
                </button>
                {Object.entries(CATEGORY_META).map(([key, meta]) => {
                  const count = data.by_category?.[key]?.length || 0;
                  if (count === 0) return null;
                  return (
                    <button
                      type="button"
                      key={key}
                      data-testid={`filter-${key}`}
                      onClick={() => setFilter(key)}
                      aria-pressed={filter === key}
                      className={chipFiltro(filter === key)}
                    >
                      <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: `rgb(${meta.color})` }} />
                      {meta.label}
                      <span className="iv-cifra text-etiqueta text-tinta-3">{count}</span>
                    </button>
                  );
                })}
              </div>

              {filter !== "ALL" && CATEGORY_META[filter] && (
                <p className="text-apoyo text-tinta-2">
                  <span className="text-tinta font-medium">{CATEGORY_META[filter].label}</span>
                  <span aria-hidden="true" className="text-linea-marcada"> — </span>
                  {CATEGORY_META[filter].desc}
                </p>
              )}
            </div>
          )}

          {loading && !data && (
            <Aviso cargando>Escaneando el mercado... Esto puede tardar 10-20 segundos.</Aviso>
          )}

          {data?.status === "warming" && (
            <Aviso cargando testId="opportunities-warming">
              Calentando el escáner... Se actualizará automáticamente en unos segundos.
            </Aviso>
          )}

          {data && data.status !== "warming" && filtered.length > 0 && (
            <div className="iv-panel overflow-hidden">
              {/* Cabecera de columnas, solo en escritorio: las filas ya llevan sus rótulos
                  en móvil, donde las columnas no existen. */}
              <div aria-hidden="true"
                   className="hidden lg:grid lg:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_minmax(0,15rem)_minmax(0,8rem)] gap-x-6 px-5 py-2.5 border-b border-linea bg-linea/15">
                <span className="iv-etiqueta">Valor</span>
                <span className="iv-etiqueta">Lectura</span>
                <span className="iv-etiqueta">Niveles</span>
                <span className="iv-etiqueta text-right">Precio</span>
              </div>
              <ol className="divide-y divide-linea">
                {filtered.map((op) => (
                  <OpportunityCard key={op.symbol} op={op} onPick={handlePick} />
                ))}
              </ol>
            </div>
          )}

          {data && data.status !== "warming" && filtered.length === 0 && (
            <Aviso>Sin oportunidades en esta categoría hoy.</Aviso>
          )}
        </>
      )}

      {/* ============ SCREENER MODE ============ */}
      {mode === "screener" && (
        <>
          <Cabecera
            titulo="Screener de crecimiento"
            accion={
              <Button
                onClick={() => loadScreener(true)}
                disabled={screenerLoading}
                variant="outline"
                className={BOTON_REFRESCAR}
              >
                <ArrowClockwise size={14} weight="bold" aria-hidden="true" className={`mr-1 ${screenerLoading ? "animate-spin motion-reduce:animate-none" : ""}`} />
                {screenerLoading ? "Filtrando..." : "Refrescar"}
              </Button>
            }
            pie={
              <>
                {/* Semáforo de mercado */}
                {screener?.market_regime && screener.market_regime.light !== "desconocido" && (() => {
                  const rg = screener.market_regime;
                  const c = { verde: "var(--iv-sube)", amarillo: "var(--iv-aviso)", rojo: "var(--iv-baja)" }[rg.light] || "var(--iv-tinta-3)";
                  return (
                    <div className="inline-flex items-start sm:items-center gap-2 mt-5 px-3 py-2 rounded-iv max-w-full" style={{ background: `rgb(${c} / 0.08)`, border: `1px solid rgb(${c} / 0.25)` }}>
                      <span aria-hidden="true" className="w-2 h-2 rounded-full shrink-0 mt-1 sm:mt-0" style={{ background: `rgb(${c})` }} />
                      <span className="text-apoyo min-w-0">
                        <span className="font-semibold" style={{ color: `rgb(${c})` }}>{rg.label}</span>
                        <span className="text-tinta-2 hidden sm:inline"> — {rg.advice}</span>
                      </span>
                    </div>
                  );
                })()}

                {/* Filter chips: los criterios del filtro, en neutro. Son informativos,
                    no pulsables, y no deben competir con la selección en naranja. */}
                {screener?.filters && (
                  <ul className="flex flex-wrap gap-1.5 mt-4" aria-label="Criterios del filtro">
                    {screener.filters.map((f, i) => (
                      <li key={i} className="iv-cifra text-etiqueta px-2 py-1 rounded-iv-sm border border-linea text-tinta-2">
                        {f}
                      </li>
                    ))}
                  </ul>
                )}

                {screener?.generated_at && screener.status !== "warming" && (
                  <p className="iv-cifra text-etiqueta text-tinta-3 mt-3 flex flex-wrap gap-x-2 gap-y-0.5">
                    <span>Último filtrado: {new Date(screener.generated_at).toLocaleString("es-ES")}</span>
                    <span aria-hidden="true" className="text-linea-marcada">·</span>
                    <span>{screener.matches} resultados</span>
                    {isStale(screener) && (
                      <>
                        <span aria-hidden="true" className="text-linea-marcada">·</span>
                        <span className="text-aviso">actualizando datos…</span>
                      </>
                    )}
                  </p>
                )}
              </>
            }
          >
            {screener?.universe_size || 120} acciones del mercado, ordenadas por <span className="font-semibold text-marca">potencial</span> (crecimiento + valoración + punto de entrada).
          </Cabecera>

          {(!screener || screener.status === "warming") ? (
            <Aviso cargando={screenerLoading || screener?.status === "warming"}>
              {screenerLoading || screener?.status === "warming"
                ? "Aplicando los 7 filtros sobre el universo de crecimiento… La primera vez tarda ~40s y se actualiza solo."
                : "No se pudo cargar el screener. Pulsa «Refrescar» para reintentar."}
            </Aviso>
          ) : (screener.results || []).length > 0 ? (
            <>
              {((screener.top_seleccion || []).length > 0 || (screener.sectores_calientes || []).length > 0) && (
                <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] items-start">
                  {(screener.top_seleccion || []).length > 0 && (
                    <section className="iv-panel overflow-hidden" aria-labelledby="top-seleccion">
                      <h3 id="top-seleccion" className="flex items-center gap-1.5 px-4 py-3 border-b border-linea iv-etiqueta text-marca font-semibold">
                        <Star size={12} weight="fill" aria-hidden="true" />
                        Top Selección
                      </h3>
                      <ul className="divide-y divide-linea">
                        {screener.top_seleccion.map((t) => (
                          <li key={t.symbol}>
                            <button type="button" onClick={() => handlePick(t.symbol)}
                              className={`group w-full flex items-baseline justify-between gap-3 text-left px-4 py-2.5 hover:bg-linea/25 focus-visible:bg-linea/25 focus-visible:outline-offset-[-2px] ${TRANSICION}`}>
                              <span className="min-w-0 flex flex-wrap items-baseline gap-x-2">
                                <span className={`iv-cifra font-semibold text-apoyo text-tinta group-hover:text-marca ${TRANSICION}`}>{t.symbol}</span>
                                <span className="text-etiqueta text-tinta-3">{t.motivo}</span>
                              </span>
                              <span className="shrink-0 iv-cifra text-apoyo font-semibold text-sube">{t.potential_score} pts</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {(screener.sectores_calientes || []).length > 0 && (
                    <section className="iv-panel p-4" aria-labelledby="sectores-calientes">
                      <h3 id="sectores-calientes" className="iv-etiqueta text-tinta-2 font-semibold">El dinero va hacia:</h3>
                      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-apoyo text-tinta font-medium">
                        {screener.sectores_calientes.slice(0, 4).map((s, i) => (
                          <li key={s.sector} className="flex items-baseline gap-3">
                            {i > 0 && <span aria-hidden="true" className="text-linea-marcada">·</span>}
                            {s.sector}
                          </li>
                        ))}
                      </ul>
                      <p className="text-etiqueta text-tinta-3 mt-2 leading-snug">Detectado en vivo (momentum + lo que dicen tus fuentes). Se actualiza solo; estos sectores pesan más en la Top Selección.</p>
                    </section>
                  )}
                </div>
              )}
              {(screener.con_fuentes || []).length > 0 && (
                <p className="flex items-center gap-2 text-apoyo text-tinta-2">
                  <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-info shrink-0" />
                  <span><b className="iv-cifra text-info">{screener.con_fuentes.length}</b> de estas acciones las mencionan tus fuentes de pago — salen primero, marcadas.</span>
                </p>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 lg:gap-5 pt-2">
                {/* Las mencionadas por tus fuentes flotan arriba (sin alterar el score). */}
                {[...screener.results]
                  .sort((a, b) => (b.fuentes ? 1 : 0) - (a.fuentes ? 1 : 0))
                  .map((row) => (
                    <ScreenerCard key={row.symbol} row={row} onPick={handlePick}
                      top={(screener.top_seleccion || []).some((t) => t.symbol === row.symbol)} />
                  ))}
              </div>
            </>
          ) : (
            <Aviso>Ninguna acción del universo cumple hoy los 7 filtros. Prueba a refrescar más tarde.</Aviso>
          )}
        </>
      )}

      {/* ============ MOVERS MODE ============ */}
      {mode === "movers" && (
        <>
          <Cabecera
            titulo="Movers del mercado"
            accion={
              <Button onClick={loadMovers} disabled={moversLoading} variant="outline" className={BOTON_REFRESCAR}>
                <ArrowClockwise size={14} weight="bold" aria-hidden="true" className={`mr-1 ${moversLoading ? "animate-spin motion-reduce:animate-none" : ""}`} />
                {moversLoading ? "Cargando..." : "Refrescar"}
              </Button>
            }
          >
            Mayores subidas, bajadas y más negociadas del mercado US hoy.
          </Cabecera>

          {moversLoading && !movers ? (
            <Aviso cargando>Cargando movers del mercado...</Aviso>
          ) : movers && ((movers.gainers || []).length || (movers.losers || []).length || (movers.actives || []).length) ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <MoversColumn title="Mayores subidas" icon={TrendUp} rows={movers.gainers} color="var(--iv-sube)" onPick={handlePick} />
              <MoversColumn title="Mayores bajadas" icon={TrendDown} rows={movers.losers} color="var(--iv-baja)" onPick={handlePick} />
              <MoversColumn title="Más negociadas" icon={Pulse} rows={movers.actives} color="var(--iv-info)" porSigno onPick={handlePick} />
            </div>
          ) : (
            <Aviso>No hay datos de movers. Requiere configurar <span className="font-mono">FMP_API_KEY</span> en el servidor.</Aviso>
          )}
        </>
      )}
    </div>
  );
}
