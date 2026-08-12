import React from "react";
import { Lightning, TrendDown, TrendUp, Sparkle, Pulse, Sun, ArrowRight, ArrowClockwise, Funnel, Fire, Target } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import Score from "../components/Score";
import { fmtPrice, fmtPct, fmtNum } from "../lib/format";
import MiniChart from "../components/MiniChart";
import RadarView from "./RadarView";

const CATEGORY_META = {
  OVERSOLD: { label: "Sobrevendidas (RSI<30)", icon: TrendDown, color: "var(--iv-sube)", desc: "RSI muy bajo, posible rebote técnico" },
  DIP: { label: "Caídas Fuertes (Compra el dip)", icon: TrendDown, color: "var(--iv-baja)", desc: "Cayendo hoy, oportunidad si fundamentales son sólidos" },
  VALUE: { label: "Cerca de Mínimos 52sem", icon: Sun, color: "var(--iv-aviso)", desc: "Cerca de mínimos anuales, valor potencial" },
  MOMENTUM: { label: "Momentum Alcista", icon: TrendUp, color: "var(--iv-sube)", desc: "Tendencia alcista sana en marcha" },
  BREAKOUT: { label: "Breakout / Máximos 52sem", icon: Sparkle, color: "var(--iv-marca)", desc: "Rompiendo máximos, fuerza relativa alta" },
  GENERAL: { label: "Señales Mixtas", icon: Pulse, color: "var(--iv-tinta-3)", desc: "Combinación de señales positivas" },
};

function OpportunityCard({ op, onPick }) {
  const meta = CATEGORY_META[op.category] || CATEGORY_META.GENERAL;
  const up = (op.change_percent ?? 0) >= 0;
  return (
    <div
      data-testid={`opportunity-${op.symbol}`}
      className="iv-panel p-4 hover:shadow-md transition-all cursor-pointer card-hover"
      onClick={() => onPick(op.symbol)}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-10 h-10 rounded-md bg-marca text-marca-tinta flex items-center justify-center font-mono font-bold text-xs shrink-0">
            {op.symbol.slice(0, 3)}
          </div>
          <div className="min-w-0">
            <p className="font-mono font-bold text-sm text-tinta">{op.symbol}</p>
            <p className="text-[10px] text-tinta-3 truncate max-w-[140px]">{op.name}</p>
          </div>
        </div>
        <span
          className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider"
          style={{ background: `rgb(${meta.color} / 0.08)`, color: `rgb(${meta.color})`, border: `1px solid rgb(${meta.color} / 0.25)` }}
        >
          Score {op.score}
        </span>
      </div>

      <div className="flex items-baseline justify-between mb-2">
        <p className="font-mono font-bold text-lg text-tinta">${fmtPrice(op.price)}</p>
        <p className={`font-mono text-xs ${up ? "text-sube" : "text-baja"}`}>
          {fmtPct(op.change_percent)}
        </p>
      </div>

      {op.reason && (
        <p className="text-[11px] text-tinta-3 italic mb-2 leading-snug">{op.reason}</p>
      )}
      <div className="space-y-1 mb-3">
        {op.signals.slice(0, 3).map((s, i) => (
          <p key={i} className="text-[11px] text-tinta flex items-start gap-1">
            <span className="text-marca mt-0.5">·</span>
            {s}
          </p>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-1 text-center mb-3 text-[10px] font-mono">
        <div className="bg-fondo border border-linea rounded px-1 py-1">
          <p className="text-tinta-3 uppercase text-[9px]">RSI</p>
          <p className="text-tinta font-semibold">{op.rsi ?? "—"}</p>
        </div>
        <div className="bg-sube/10 border border-sube/30 rounded px-1 py-1">
          <p className="text-tinta-3 uppercase text-[9px]">Soporte</p>
          <p className="text-sube font-semibold">${fmtPrice(op.nearest_support) || "—"}</p>
        </div>
        <div className="bg-baja/10 border border-baja/30 rounded px-1 py-1">
          <p className="text-tinta-3 uppercase text-[9px]">Resist.</p>
          <p className="text-baja font-semibold">${fmtPrice(op.nearest_resistance) || "—"}</p>
        </div>
      </div>

      <div className="flex items-center justify-between text-[10px] text-tinta-3">
        {op.analyst_consensus ? (
          <span
            className={`font-mono font-semibold ${
              (op.consensus_score ?? 0) >= 80
                ? "text-sube"
                : (op.consensus_score ?? 0) >= 65
                ? "text-aviso"
                : "text-tinta-3"
            }`}
            title={op.analysts_count ? `${op.analysts_count} analistas` : undefined}
          >
            {op.analyst_consensus}
            {op.analysts_count ? ` · ${op.analysts_count}` : ""}
          </span>
        ) : (
          <span>—</span>
        )}
        <span className="flex items-center gap-1 text-marca font-mono">
          Analizar <ArrowRight size={10} weight="bold" />
        </span>
      </div>
    </div>
  );
}

function ScreenerCard({ row, onPick, top }) {
  const dist = row.dist_52w_high;
  const distColor = dist == null ? "var(--iv-tinta-3)" : dist >= -5 ? "var(--iv-sube)" : dist >= -12 ? "var(--iv-aviso)" : "var(--iv-baja)";
  // Score de potencial: verde fuerte ≥70, ámbar 45-70, gris <45.
  const ps = row.potential_score;
  const psColor = ps == null ? "var(--iv-tinta-3)" : ps >= 70 ? "var(--iv-sube)" : ps >= 45 ? "var(--iv-aviso)" : "var(--iv-tinta-3)";
  return (
    <div
      data-testid={`screener-${row.symbol}`}
      className="iv-panel p-4 hover:shadow-md transition-all cursor-pointer card-hover relative"
      /* El naranja #e8890c pasa a `aviso` y NO se queda como excepción: no era un
         peldaño de una escala —no competía con ningún tramo contiguo, como sí pasa
         con «Floja» en el Radar—, sino un acento de «mira esto», que es justo el
         papel del token. En claro se ve ámbar oscuro en vez de naranja vivo. */
      style={top ? {
        border: "2px solid rgb(var(--iv-aviso))",
        boxShadow: "0 0 0 1px rgb(var(--iv-aviso) / 0.13)",
      } : undefined}
      onClick={() => onPick(row.symbol)}
    >
      {top && (
        /* `marca-tinta` y no blanco fijo: `aviso` es ámbar OSCURO en claro y ámbar
           BRILLANTE en oscuro, así que el blanco funcionaba en un tema y se perdía
           en el otro. El token de texto sobre fondo de acento cambia con él. */
        <span className="absolute -top-2 left-3 px-2 py-0.5 rounded-full text-[9px] font-bold text-marca-tinta bg-aviso shadow">
          ★ TOP SELECCIÓN
        </span>
      )}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-10 h-10 rounded-md bg-marca text-marca-tinta flex items-center justify-center font-mono font-bold text-xs shrink-0">
            {row.symbol.slice(0, 3)}
          </div>
          <div className="min-w-0">
            <p className="font-mono font-bold text-sm text-tinta">{row.symbol}</p>
            <p className="text-[10px] text-tinta-3 truncate max-w-[140px]">{row.name}</p>
            {row.fuentes && (
              <span className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-info/10 text-info border border-info/20"
                title={`Mencionada por tus fuentes: ${(row.fuentes.fuentes || []).join(", ")}`}>
                📣 Tus fuentes ({row.fuentes.menciones})
                {row.fuentes.positivos > 0 && ` 👍${row.fuentes.positivos}`}
                {row.fuentes.negativos > 0 && ` 👎${row.fuentes.negativos}`}
              </span>
            )}
          </div>
        </div>
        {ps != null && (
          /* El chip es el mismo de siempre; `Score` solo lo hace desplegable. Cerrado se
             ve igual y no pide nada: la peticion ocurre en el primer clic. */
          <Score symbol={row.symbol}>
            <span
              className="px-2 py-0.5 rounded-full text-[11px] font-mono font-bold"
              style={{ background: `rgb(${psColor} / 0.09)`, color: `rgb(${psColor})`, border: `1px solid rgb(${psColor} / 0.25)` }}
              title="Potencial a medio plazo: crecimiento + valoración + punto de entrada"
            >
              {ps} pts
            </span>
          </Score>
        )}
      </div>

      <div className="flex items-baseline justify-between mb-2">
        <p className="font-mono font-bold text-lg text-tinta">${fmtPrice(row.price)}</p>
        <span
          className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold"
          style={{ background: `rgb(${distColor} / 0.08)`, color: `rgb(${distColor})`, border: `1px solid rgb(${distColor} / 0.25)` }}
        >
          {dist != null ? `${dist}% máx.` : "—"}
        </span>
      </div>
      {row.valuation && (
        <p className="text-[10px] font-mono mb-1" style={{ color: `rgb(${psColor})` }}>
          {row.valuation}{row.pe_ratio ? ` · PER ${row.pe_ratio}` : ""}
        </p>
      )}
      {row.momentum && row.momentum !== "neutra" && (
        <p
          className="text-[10px] font-mono mb-1"
          style={{ color: row.momentum.startsWith("⚠") ? "rgb(var(--iv-baja))" : "rgb(var(--iv-sube))" }}
        >
          {row.momentum}{row.return_52w != null ? ` · ${row.return_52w > 0 ? "+" : ""}${row.return_52w}% 1a` : ""}
        </p>
      )}
      {row.analyst_consensus && (
        <p className="text-[10px] font-mono mb-1 text-tinta-3">
          Analistas: <span className="text-marca font-semibold">{row.analyst_consensus}</span>
          {row.consensus_score != null ? ` (${row.consensus_score})` : ""}
        </p>
      )}
      {row.reason && (
        <p className="text-[11px] text-tinta-3 italic mb-2 leading-snug">{row.reason}</p>
      )}
      {row.earnings_days != null && (
        <p className="text-[10px] font-mono mb-2 text-baja bg-baja/10 border border-baja/30 rounded px-2 py-1">
          ⚠ Resultados {row.earnings_days === 0 ? "HOY" : row.earnings_days === 1 ? "mañana" : `en ${row.earnings_days} días`} — riesgo binario
        </p>
      )}

      <div className="grid grid-cols-3 gap-1 text-center mb-3 text-[10px] font-mono">
        <div className="bg-sube/10 border border-sube/30 rounded px-1 py-1.5">
          <p className="text-tinta-3 uppercase text-[9px]">Ventas YoY</p>
          <p className="text-sube font-semibold">{row.revenue_growth != null ? `+${row.revenue_growth}%` : "—"}</p>
        </div>
        <div className="bg-sube/10 border border-sube/30 rounded px-1 py-1.5">
          <p className="text-tinta-3 uppercase text-[9px]">EPS YoY</p>
          <p className="text-sube font-semibold">{row.eps_growth != null ? `${row.eps_growth > 0 ? "+" : ""}${row.eps_growth}%` : "—"}</p>
        </div>
        <div className="bg-info/10 border border-info/30 rounded px-1 py-1.5">
          <p className="text-tinta-3 uppercase text-[9px]">Vol. medio</p>
          <p className="text-info font-semibold">{fmtNum(row.avg_volume)}</p>
        </div>
      </div>

      <MiniChart symbol={row.symbol} />

      <div className="flex items-center justify-between text-[10px] text-tinta-3 mt-2">
        <span className="truncate max-w-[150px]">{row.sector || "—"}</span>
        <span className="flex items-center gap-1 text-marca font-mono">
          Analizar <ArrowRight size={10} weight="bold" />
        </span>
      </div>
    </div>
  );
}

function MoversColumn({ title, icon: Icon, rows, color, onPick }) {
  return (
    <div className="iv-panel p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={16} weight="bold" style={{ color: `rgb(${color})` }} />
        <h3 className="font-heading font-semibold text-sm text-tinta">{title}</h3>
      </div>
      <div className="space-y-1 max-h-[520px] overflow-y-auto pr-1">
        {(rows || []).length === 0 && <p className="text-xs text-tinta-3 py-4 text-center">—</p>}
        {(rows || []).map((r) => {
          const pct = r.change_percent;
          return (
            <div
              key={r.symbol}
              onClick={() => onPick(r.symbol)}
              className="flex items-center justify-between gap-2 px-2 py-1.5 rounded hover:bg-fondo cursor-pointer"
            >
              <div className="min-w-0">
                <p className="font-mono font-semibold text-xs text-tinta">{r.symbol}</p>
                <p className="text-[10px] text-tinta-3 truncate max-w-[130px]">{r.name}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="font-mono text-xs text-tinta">${fmtPrice(r.price)}</p>
                <p className="font-mono text-[11px] font-semibold" style={{ color: `rgb(${color})` }}>
                  {pct != null ? `${pct >= 0 ? "+" : ""}${Number(pct).toFixed(2)}%` : "—"}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function OpportunitiesView({ setSymbol }) {
  const [mode, setMode] = React.useState("signals"); // "signals" | "screener"

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

  const TabButton = ({ id, icon: Icon, children }) => (
    <button
      onClick={() => setMode(id)}
      className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-mono border transition-all ${
        mode === id
          ? "bg-marca text-marca-tinta border-marca"
          : "bg-superficie text-tinta-3 border-linea hover:border-marca"
      }`}
    >
      <Icon size={15} weight="bold" />
      {children}
    </button>
  );

  return (
    <div data-testid="opportunities-view" className="space-y-6">
      {/* Mode tabs */}
      <div className="flex gap-2 flex-wrap">
        <TabButton id="signals" icon={Lightning}>Señales del día</TabButton>
        <TabButton id="screener" icon={Funnel}>Screener Crecimiento</TabButton>
        <TabButton id="movers" icon={Fire}>Movers del mercado</TabButton>
        <TabButton id="fuentes" icon={Target}>Tus fuentes</TabButton>
      </div>

      {/* ============ TUS FUENTES (antes /radar) ============ */}
      {mode === "fuentes" && <RadarView setSymbol={setSymbol} />}

      {/* ============ SIGNALS MODE ============ */}
      {mode === "signals" && (
        <>
          <section className="iv-panel p-6">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Lightning size={20} weight="fill" className="text-aviso" />
                  <h2 className="font-heading font-bold text-2xl text-tinta">Oportunidades del Día</h2>
                </div>
                <p className="text-sm text-tinta-3">
                  Escaneo de {data?.universe_size || 30} acciones · Detecta sobrecompras, caídas fuertes, momentum y breakouts.
                </p>
              </div>
              <Button
                data-testid="refresh-opportunities"
                onClick={() => load(true)}
                disabled={loading}
                variant="outline"
                className="border-linea font-mono text-xs"
              >
                <ArrowClockwise size={14} weight="bold" className="mr-1" />
                {loading ? "Escaneando..." : "Refrescar"}
              </Button>
            </div>
            {data?.generated_at && (
              <p className="text-[10px] text-tinta-3 mt-2 font-mono">
                Último escaneo: {new Date(data.generated_at).toLocaleString("es-ES")} · {data.opportunities_found} oportunidades detectadas
                {isStale(data) && <span className="text-aviso"> · actualizando datos…</span>}
              </p>
            )}
          </section>

          {data && (
            <div className="flex gap-2 flex-wrap" data-testid="category-filter">
              <button
                onClick={() => setFilter("ALL")}
                className={`px-3 py-1.5 rounded-full text-xs font-mono border transition-all ${
                  filter === "ALL"
                    ? "bg-marca text-marca-tinta border-marca"
                    : "bg-superficie text-tinta-3 border-linea hover:border-marca"
                }`}
              >
                Top 15 ({data.top?.length || 0})
              </button>
              {Object.entries(CATEGORY_META).map(([key, meta]) => {
                const count = data.by_category?.[key]?.length || 0;
                if (count === 0) return null;
                return (
                  <button
                    key={key}
                    data-testid={`filter-${key}`}
                    onClick={() => setFilter(key)}
                    className={`px-3 py-1.5 rounded-full text-xs font-mono border transition-all ${
                      filter === key
                        ? "text-marca-tinta border-transparent"
                        : "bg-superficie text-tinta-3 border-linea hover:border-current"
                    }`}
                    style={filter === key
                      ? { backgroundColor: `rgb(${meta.color})`, borderColor: `rgb(${meta.color})` }
                      : { color: `rgb(${meta.color})` }}
                  >
                    {meta.label} ({count})
                  </button>
                );
              })}
            </div>
          )}

          {filter !== "ALL" && CATEGORY_META[filter] && (
            <div className="bg-fondo border-l-4 px-4 py-2 rounded text-sm" style={{ borderColor: CATEGORY_META[filter].color }}>
              <p className="text-tinta font-medium">{CATEGORY_META[filter].label}</p>
              <p className="text-xs text-tinta-3 mt-0.5">{CATEGORY_META[filter].desc}</p>
            </div>
          )}

          {loading && !data && (
            <div className="iv-panel p-12 text-center">
              <p className="text-sm text-tinta-3">Escaneando el mercado... Esto puede tardar 10-20 segundos.</p>
            </div>
          )}

          {data?.status === "warming" && (
            <div className="iv-panel p-12 text-center" data-testid="opportunities-warming">
              <p className="text-sm text-tinta-3">Calentando el escáner... Se actualizará automáticamente en unos segundos.</p>
            </div>
          )}

          {data && data.status !== "warming" && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filtered.map((op) => (
                <OpportunityCard key={op.symbol} op={op} onPick={handlePick} />
              ))}
            </div>
          )}

          {data && data.status !== "warming" && filtered.length === 0 && (
            <div className="iv-panel p-12 text-center">
              <p className="text-sm text-tinta-3">Sin oportunidades en esta categoría hoy.</p>
            </div>
          )}
        </>
      )}

      {/* ============ SCREENER MODE ============ */}
      {mode === "screener" && (
        <>
          <section className="iv-panel p-6">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Funnel size={20} weight="fill" className="text-marca" />
                  <h2 className="font-heading font-bold text-2xl text-tinta">Screener de Crecimiento</h2>
                </div>
                <p className="text-sm text-tinta-3">
                  {screener?.universe_size || 120} acciones del mercado, ordenadas por <span className="font-semibold text-marca">potencial</span> (crecimiento + valoración + punto de entrada).
                </p>
              </div>
              <Button
                onClick={() => loadScreener(true)}
                disabled={screenerLoading}
                variant="outline"
                className="border-linea font-mono text-xs"
              >
                <ArrowClockwise size={14} weight="bold" className="mr-1" />
                {screenerLoading ? "Filtrando..." : "Refrescar"}
              </Button>
            </div>

            {/* Semáforo de mercado */}
            {screener?.market_regime && screener.market_regime.light !== "desconocido" && (() => {
              const rg = screener.market_regime;
              const c = { verde: "var(--iv-sube)", amarillo: "var(--iv-aviso)", rojo: "var(--iv-baja)" }[rg.light] || "var(--iv-tinta-3)";
              return (
                <div className="flex items-center gap-2 mt-4 px-3 py-2 rounded-lg" style={{ background: `rgb(${c} / 0.08)`, border: `1px solid rgb(${c} / 0.25)` }}>
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: `rgb(${c})` }} />
                  <span className="text-xs font-semibold" style={{ color: `rgb(${c})` }}>{rg.label}</span>
                  <span className="text-[11px] text-tinta-3 hidden sm:inline">— {rg.advice}</span>
                </div>
              );
            })()}

            {/* Filter chips */}
            {screener?.filters && (
              <div className="flex flex-wrap gap-2 mt-4">
                {screener.filters.map((f, i) => (
                  <span key={i} className="text-[10px] font-mono px-2 py-1 rounded-full border border-marca/30 bg-marca/5 text-marca">
                    {f}
                  </span>
                ))}
              </div>
            )}

            {screener?.generated_at && screener.status !== "warming" && (
              <p className="text-[10px] text-tinta-3 mt-3 font-mono">
                Último filtrado: {new Date(screener.generated_at).toLocaleString("es-ES")} · {screener.matches} resultados
                {isStale(screener) && <span className="text-aviso"> · actualizando datos…</span>}
              </p>
            )}
          </section>

          {(!screener || screener.status === "warming") ? (
            <div className="iv-panel p-12 text-center">
              <p className="text-sm text-tinta-3">
                {screenerLoading || screener?.status === "warming"
                  ? "Aplicando los 7 filtros sobre el universo de crecimiento… La primera vez tarda ~40s y se actualiza solo."
                  : "No se pudo cargar el screener. Pulsa «Refrescar» para reintentar."}
              </p>
            </div>
          ) : (screener.results || []).length > 0 ? (
            <>
              {(screener.sectores_calientes || []).length > 0 && (
                <div className="iv-panel p-3 mb-3 border-l-4 border-aviso">
                  <p className="text-[11px] text-tinta">
                    🔥 <b>El dinero va hacia:</b>{" "}
                    {screener.sectores_calientes.slice(0, 4).map((s, i) => (
                      <span key={s.sector}>{i > 0 ? " · " : ""}{s.sector}</span>
                    ))}
                  </p>
                  <p className="text-[10px] text-tinta-3 mt-0.5">Detectado en vivo (momentum + lo que dicen tus fuentes). Se actualiza solo; estos sectores pesan más en la Top Selección.</p>
                </div>
              )}
              {(screener.top_seleccion || []).length > 0 && (
                <div className="iv-panel p-4 mb-3 border-l-4 border-sube">
                  <p className="text-[11px] uppercase tracking-[0.15em] text-marca font-mono font-bold mb-2">⭐ Top Selección</p>
                  <div className="space-y-1.5">
                    {screener.top_seleccion.map((t) => (
                      <button key={t.symbol} onClick={() => handlePick(t.symbol)}
                        className="w-full flex items-center justify-between gap-2 text-left py-1">
                        <div className="min-w-0">
                          <span className="font-mono font-bold text-sm text-tinta">{t.symbol}</span>
                          <span className="text-[11px] text-tinta-3 ml-2">{t.motivo}</span>
                        </div>
                        <span className="shrink-0 text-xs font-mono font-bold text-sube">{t.potential_score} pts</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {(screener.con_fuentes || []).length > 0 && (
                <p className="text-[11px] text-info bg-info/10 border border-info/20 rounded-md px-3 py-2 mb-3">
                  📣 <b>{screener.con_fuentes.length}</b> de estas acciones las mencionan tus fuentes de pago — salen primero, marcadas.
                </p>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
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
            <div className="iv-panel p-12 text-center">
              <p className="text-sm text-tinta-3">Ninguna acción del universo cumple hoy los 7 filtros. Prueba a refrescar más tarde.</p>
            </div>
          )}
        </>
      )}

      {/* ============ MOVERS MODE ============ */}
      {mode === "movers" && (
        <>
          <section className="iv-panel p-6">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Fire size={20} weight="fill" className="text-baja" />
                  <h2 className="font-heading font-bold text-2xl text-tinta">Movers del Mercado</h2>
                </div>
                <p className="text-sm text-tinta-3">Mayores subidas, bajadas y más negociadas del mercado US hoy.</p>
              </div>
              <Button onClick={loadMovers} disabled={moversLoading} variant="outline" className="border-linea font-mono text-xs">
                <ArrowClockwise size={14} weight="bold" className="mr-1" />
                {moversLoading ? "Cargando..." : "Refrescar"}
              </Button>
            </div>
          </section>

          {moversLoading && !movers ? (
            <div className="iv-panel p-12 text-center"><p className="text-sm text-tinta-3">Cargando movers del mercado...</p></div>
          ) : movers && ((movers.gainers || []).length || (movers.losers || []).length || (movers.actives || []).length) ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <MoversColumn title="Mayores subidas" icon={TrendUp} rows={movers.gainers} color="var(--iv-sube)" onPick={handlePick} />
              <MoversColumn title="Mayores bajadas" icon={TrendDown} rows={movers.losers} color="var(--iv-baja)" onPick={handlePick} />
              <MoversColumn title="Más negociadas" icon={Pulse} rows={movers.actives} color="var(--iv-info)" onPick={handlePick} />
            </div>
          ) : (
            <div className="iv-panel p-12 text-center">
              <p className="text-sm text-tinta-3">No hay datos de movers. Requiere configurar <span className="font-mono">FMP_API_KEY</span> en el servidor.</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
