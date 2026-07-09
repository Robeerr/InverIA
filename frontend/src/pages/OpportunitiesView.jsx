import React from "react";
import { useNavigate } from "react-router-dom";
import { Lightning, TrendDown, TrendUp, Sparkle, Pulse, Sun, ArrowRight, ArrowClockwise, Funnel, Fire } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { api } from "../lib/api";
import { fmtPrice, fmtPct, fmtNum } from "../lib/format";

const CATEGORY_META = {
  OVERSOLD: { label: "Sobrevendidas (RSI<30)", icon: TrendDown, color: "#4a7c59", desc: "RSI muy bajo, posible rebote técnico" },
  DIP: { label: "Caídas Fuertes (Compra el dip)", icon: TrendDown, color: "#d85c41", desc: "Cayendo hoy, oportunidad si fundamentales son sólidos" },
  VALUE: { label: "Cerca de Mínimos 52sem", icon: Sun, color: "#c9a14a", desc: "Cerca de mínimos anuales, valor potencial" },
  MOMENTUM: { label: "Momentum Alcista", icon: TrendUp, color: "#4a7c59", desc: "Tendencia alcista sana en marcha" },
  BREAKOUT: { label: "Breakout / Máximos 52sem", icon: Sparkle, color: "#1a3a32", desc: "Rompiendo máximos, fuerza relativa alta" },
  GENERAL: { label: "Señales Mixtas", icon: Pulse, color: "#5c6b66", desc: "Combinación de señales positivas" },
};

function OpportunityCard({ op, onPick }) {
  const meta = CATEGORY_META[op.category] || CATEGORY_META.GENERAL;
  const up = (op.change_percent ?? 0) >= 0;
  return (
    <div
      data-testid={`opportunity-${op.symbol}`}
      className="card-flat p-4 hover:shadow-md transition-all cursor-pointer card-hover"
      onClick={() => onPick(op.symbol)}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-10 h-10 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center font-mono font-bold text-xs shrink-0">
            {op.symbol.slice(0, 3)}
          </div>
          <div className="min-w-0">
            <p className="font-mono font-bold text-sm text-[#0e1f1a]">{op.symbol}</p>
            <p className="text-[10px] text-[#5c6b66] truncate max-w-[140px]">{op.name}</p>
          </div>
        </div>
        <span
          className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider"
          style={{ background: `${meta.color}15`, color: meta.color, border: `1px solid ${meta.color}40` }}
        >
          Score {op.score}
        </span>
      </div>

      <div className="flex items-baseline justify-between mb-2">
        <p className="font-mono font-bold text-lg text-[#0e1f1a]">${fmtPrice(op.price)}</p>
        <p className={`font-mono text-xs ${up ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
          {fmtPct(op.change_percent)}
        </p>
      </div>

      {op.reason && (
        <p className="text-[11px] text-[#5c6b66] italic mb-2 leading-snug">{op.reason}</p>
      )}
      <div className="space-y-1 mb-3">
        {op.signals.slice(0, 3).map((s, i) => (
          <p key={i} className="text-[11px] text-[#0e1f1a] flex items-start gap-1">
            <span className="text-[#1a3a32] mt-0.5">·</span>
            {s}
          </p>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-1 text-center mb-3 text-[10px] font-mono">
        <div className="bg-[#f5f3ef] border border-[#e5e0d8] rounded px-1 py-1">
          <p className="text-[#5c6b66] uppercase text-[9px]">RSI</p>
          <p className="text-[#0e1f1a] font-semibold">{op.rsi ?? "—"}</p>
        </div>
        <div className="bg-[#4a7c59]/10 border border-[#4a7c59]/30 rounded px-1 py-1">
          <p className="text-[#5c6b66] uppercase text-[9px]">Soporte</p>
          <p className="text-[#4a7c59] font-semibold">${fmtPrice(op.nearest_support) || "—"}</p>
        </div>
        <div className="bg-[#d85c41]/10 border border-[#d85c41]/30 rounded px-1 py-1">
          <p className="text-[#5c6b66] uppercase text-[9px]">Resist.</p>
          <p className="text-[#d85c41] font-semibold">${fmtPrice(op.nearest_resistance) || "—"}</p>
        </div>
      </div>

      <div className="flex items-center justify-between text-[10px] text-[#5c6b66]">
        {op.analyst_consensus ? (
          <span
            className={`font-mono font-semibold ${
              (op.consensus_score ?? 0) >= 80
                ? "text-[#4a7c59]"
                : (op.consensus_score ?? 0) >= 65
                ? "text-[#8a6508]"
                : "text-[#5c6b66]"
            }`}
            title={op.analysts_count ? `${op.analysts_count} analistas` : undefined}
          >
            {op.analyst_consensus}
            {op.analysts_count ? ` · ${op.analysts_count}` : ""}
          </span>
        ) : (
          <span>—</span>
        )}
        <span className="flex items-center gap-1 text-[#1a3a32] font-mono">
          Analizar <ArrowRight size={10} weight="bold" />
        </span>
      </div>
    </div>
  );
}

function ScreenerCard({ row, onPick }) {
  const dist = row.dist_52w_high;
  const distColor = dist == null ? "#5c6b66" : dist >= -5 ? "#4a7c59" : dist >= -12 ? "#c9a14a" : "#d85c41";
  // Score de potencial: verde fuerte ≥70, ámbar 45-70, gris <45.
  const ps = row.potential_score;
  const psColor = ps == null ? "#5c6b66" : ps >= 70 ? "#4a7c59" : ps >= 45 ? "#c9a14a" : "#5c6b66";
  return (
    <div
      data-testid={`screener-${row.symbol}`}
      className="card-flat p-4 hover:shadow-md transition-all cursor-pointer card-hover"
      onClick={() => onPick(row.symbol)}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-10 h-10 rounded-md bg-[#1a3a32] text-[#f5f3ef] flex items-center justify-center font-mono font-bold text-xs shrink-0">
            {row.symbol.slice(0, 3)}
          </div>
          <div className="min-w-0">
            <p className="font-mono font-bold text-sm text-[#0e1f1a]">{row.symbol}</p>
            <p className="text-[10px] text-[#5c6b66] truncate max-w-[140px]">{row.name}</p>
            {row.fuentes && (
              <span className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-[#229ED915] text-[#1a6a94] border border-[#229ED930]"
                title={`Mencionada por tus fuentes: ${(row.fuentes.fuentes || []).join(", ")}`}>
                📣 Tus fuentes ({row.fuentes.menciones})
                {row.fuentes.positivos > 0 && ` 👍${row.fuentes.positivos}`}
                {row.fuentes.negativos > 0 && ` 👎${row.fuentes.negativos}`}
              </span>
            )}
          </div>
        </div>
        {ps != null && (
          <div className="flex flex-col items-end shrink-0">
            <span
              className="px-2 py-0.5 rounded-full text-[11px] font-mono font-bold"
              style={{ background: `${psColor}18`, color: psColor, border: `1px solid ${psColor}40` }}
              title="Potencial a medio plazo: crecimiento + valoración + punto de entrada"
            >
              {ps} pts
            </span>
            <span className="text-[9px] text-[#5c6b66] mt-0.5">potencial</span>
          </div>
        )}
      </div>

      <div className="flex items-baseline justify-between mb-2">
        <p className="font-mono font-bold text-lg text-[#0e1f1a]">${fmtPrice(row.price)}</p>
        <span
          className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold"
          style={{ background: `${distColor}15`, color: distColor, border: `1px solid ${distColor}40` }}
        >
          {dist != null ? `${dist}% máx.` : "—"}
        </span>
      </div>
      {row.valuation && (
        <p className="text-[10px] font-mono mb-1" style={{ color: psColor }}>
          {row.valuation}{row.pe_ratio ? ` · PER ${row.pe_ratio}` : ""}
        </p>
      )}
      {row.momentum && row.momentum !== "neutra" && (
        <p
          className="text-[10px] font-mono mb-1"
          style={{ color: row.momentum.startsWith("⚠") ? "#d85c41" : "#4a7c59" }}
        >
          {row.momentum}{row.return_52w != null ? ` · ${row.return_52w > 0 ? "+" : ""}${row.return_52w}% 1a` : ""}
        </p>
      )}
      {row.analyst_consensus && (
        <p className="text-[10px] font-mono mb-1 text-[#5c6b66]">
          Analistas: <span className="text-[#1a3a32] font-semibold">{row.analyst_consensus}</span>
          {row.consensus_score != null ? ` (${row.consensus_score})` : ""}
        </p>
      )}
      {row.reason && (
        <p className="text-[11px] text-[#5c6b66] italic mb-2 leading-snug">{row.reason}</p>
      )}
      {row.earnings_days != null && (
        <p className="text-[10px] font-mono mb-2 text-[#d85c41] bg-[#d85c41]/10 border border-[#d85c41]/30 rounded px-2 py-1">
          ⚠ Resultados {row.earnings_days === 0 ? "HOY" : row.earnings_days === 1 ? "mañana" : `en ${row.earnings_days} días`} — riesgo binario
        </p>
      )}

      <div className="grid grid-cols-3 gap-1 text-center mb-3 text-[10px] font-mono">
        <div className="bg-[#4a7c59]/10 border border-[#4a7c59]/30 rounded px-1 py-1.5">
          <p className="text-[#5c6b66] uppercase text-[9px]">Ventas YoY</p>
          <p className="text-[#4a7c59] font-semibold">{row.revenue_growth != null ? `+${row.revenue_growth}%` : "—"}</p>
        </div>
        <div className="bg-[#4a7c59]/10 border border-[#4a7c59]/30 rounded px-1 py-1.5">
          <p className="text-[#5c6b66] uppercase text-[9px]">EPS YoY</p>
          <p className="text-[#4a7c59] font-semibold">{row.eps_growth != null ? `${row.eps_growth > 0 ? "+" : ""}${row.eps_growth}%` : "—"}</p>
        </div>
        <div className="bg-[#1F6FB5]/10 border border-[#1F6FB5]/30 rounded px-1 py-1.5">
          <p className="text-[#5c6b66] uppercase text-[9px]">Vol. medio</p>
          <p className="text-[#1F6FB5] font-semibold">{fmtNum(row.avg_volume)}</p>
        </div>
      </div>

      <div className="flex items-center justify-between text-[10px] text-[#5c6b66]">
        <span className="truncate max-w-[150px]">{row.sector || "—"}</span>
        <span className="flex items-center gap-1 text-[#1a3a32] font-mono">
          Analizar <ArrowRight size={10} weight="bold" />
        </span>
      </div>
    </div>
  );
}

function MoversColumn({ title, icon: Icon, rows, color, onPick }) {
  return (
    <div className="card-flat p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={16} weight="bold" style={{ color }} />
        <h3 className="font-heading font-semibold text-sm text-[#0e1f1a]">{title}</h3>
      </div>
      <div className="space-y-1 max-h-[520px] overflow-y-auto pr-1">
        {(rows || []).length === 0 && <p className="text-xs text-[#5c6b66] py-4 text-center">—</p>}
        {(rows || []).map((r) => {
          const pct = r.change_percent;
          return (
            <div
              key={r.symbol}
              onClick={() => onPick(r.symbol)}
              className="flex items-center justify-between gap-2 px-2 py-1.5 rounded hover:bg-[#f5f3ef] cursor-pointer"
            >
              <div className="min-w-0">
                <p className="font-mono font-semibold text-xs text-[#0e1f1a]">{r.symbol}</p>
                <p className="text-[10px] text-[#5c6b66] truncate max-w-[130px]">{r.name}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="font-mono text-xs text-[#0e1f1a]">${fmtPrice(r.price)}</p>
                <p className="font-mono text-[11px] font-semibold" style={{ color }}>
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
  const navigate = useNavigate();
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

  const handlePick = (sym) => {
    setSymbol(sym);
    navigate("/");
  };

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
          ? "bg-[#1a3a32] text-[#f5f3ef] border-[#1a3a32]"
          : "bg-white text-[#5c6b66] border-[#e5e0d8] hover:border-[#1a3a32]"
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
      </div>

      {/* ============ SIGNALS MODE ============ */}
      {mode === "signals" && (
        <>
          <section className="card-flat p-6">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Lightning size={20} weight="fill" className="text-[#c9a14a]" />
                  <h2 className="font-heading font-bold text-2xl text-[#0e1f1a]">Oportunidades del Día</h2>
                </div>
                <p className="text-sm text-[#5c6b66]">
                  Escaneo de {data?.universe_size || 30} acciones · Detecta sobrecompras, caídas fuertes, momentum y breakouts.
                </p>
              </div>
              <Button
                data-testid="refresh-opportunities"
                onClick={() => load(true)}
                disabled={loading}
                variant="outline"
                className="border-[#e5e0d8] font-mono text-xs"
              >
                <ArrowClockwise size={14} weight="bold" className="mr-1" />
                {loading ? "Escaneando..." : "Refrescar"}
              </Button>
            </div>
            {data?.generated_at && (
              <p className="text-[10px] text-[#5c6b66] mt-2 font-mono">
                Último escaneo: {new Date(data.generated_at).toLocaleString("es-ES")} · {data.opportunities_found} oportunidades detectadas
                {isStale(data) && <span className="text-[#c9a14a]"> · actualizando datos…</span>}
              </p>
            )}
          </section>

          {data && (
            <div className="flex gap-2 flex-wrap" data-testid="category-filter">
              <button
                onClick={() => setFilter("ALL")}
                className={`px-3 py-1.5 rounded-full text-xs font-mono border transition-all ${
                  filter === "ALL"
                    ? "bg-[#1a3a32] text-[#f5f3ef] border-[#1a3a32]"
                    : "bg-white text-[#5c6b66] border-[#e5e0d8] hover:border-[#1a3a32]"
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
                        ? "text-[#f5f3ef] border-transparent"
                        : "bg-white text-[#5c6b66] border-[#e5e0d8] hover:border-current"
                    }`}
                    style={filter === key ? { backgroundColor: meta.color, borderColor: meta.color } : { color: meta.color }}
                  >
                    {meta.label} ({count})
                  </button>
                );
              })}
            </div>
          )}

          {filter !== "ALL" && CATEGORY_META[filter] && (
            <div className="bg-[#f5f3ef] border-l-4 px-4 py-2 rounded text-sm" style={{ borderColor: CATEGORY_META[filter].color }}>
              <p className="text-[#0e1f1a] font-medium">{CATEGORY_META[filter].label}</p>
              <p className="text-xs text-[#5c6b66] mt-0.5">{CATEGORY_META[filter].desc}</p>
            </div>
          )}

          {loading && !data && (
            <div className="card-flat p-12 text-center">
              <p className="text-sm text-[#5c6b66]">Escaneando el mercado... Esto puede tardar 10-20 segundos.</p>
            </div>
          )}

          {data?.status === "warming" && (
            <div className="card-flat p-12 text-center" data-testid="opportunities-warming">
              <p className="text-sm text-[#5c6b66]">Calentando el escáner... Se actualizará automáticamente en unos segundos.</p>
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
            <div className="card-flat p-12 text-center">
              <p className="text-sm text-[#5c6b66]">Sin oportunidades en esta categoría hoy.</p>
            </div>
          )}
        </>
      )}

      {/* ============ SCREENER MODE ============ */}
      {mode === "screener" && (
        <>
          <section className="card-flat p-6">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Funnel size={20} weight="fill" className="text-[#1a3a32]" />
                  <h2 className="font-heading font-bold text-2xl text-[#0e1f1a]">Screener de Crecimiento</h2>
                </div>
                <p className="text-sm text-[#5c6b66]">
                  {screener?.universe_size || 120} acciones del mercado, ordenadas por <span className="font-semibold text-[#1a3a32]">potencial</span> (crecimiento + valoración + punto de entrada).
                </p>
              </div>
              <Button
                onClick={() => loadScreener(true)}
                disabled={screenerLoading}
                variant="outline"
                className="border-[#e5e0d8] font-mono text-xs"
              >
                <ArrowClockwise size={14} weight="bold" className="mr-1" />
                {screenerLoading ? "Filtrando..." : "Refrescar"}
              </Button>
            </div>

            {/* Semáforo de mercado */}
            {screener?.market_regime && screener.market_regime.light !== "desconocido" && (() => {
              const rg = screener.market_regime;
              const c = { verde: "#4a7c59", amarillo: "#c9a14a", rojo: "#d85c41" }[rg.light] || "#5c6b66";
              return (
                <div className="flex items-center gap-2 mt-4 px-3 py-2 rounded-lg" style={{ background: `${c}14`, border: `1px solid ${c}40` }}>
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: c }} />
                  <span className="text-xs font-semibold" style={{ color: c }}>{rg.label}</span>
                  <span className="text-[11px] text-[#5c6b66] hidden sm:inline">— {rg.advice}</span>
                </div>
              );
            })()}

            {/* Filter chips */}
            {screener?.filters && (
              <div className="flex flex-wrap gap-2 mt-4">
                {screener.filters.map((f, i) => (
                  <span key={i} className="text-[10px] font-mono px-2 py-1 rounded-full border border-[#1a3a32]/30 bg-[#1a3a32]/5 text-[#1a3a32]">
                    {f}
                  </span>
                ))}
              </div>
            )}

            {screener?.generated_at && screener.status !== "warming" && (
              <p className="text-[10px] text-[#5c6b66] mt-3 font-mono">
                Último filtrado: {new Date(screener.generated_at).toLocaleString("es-ES")} · {screener.matches} resultados
                {isStale(screener) && <span className="text-[#c9a14a]"> · actualizando datos…</span>}
              </p>
            )}
          </section>

          {(!screener || screener.status === "warming") ? (
            <div className="card-flat p-12 text-center">
              <p className="text-sm text-[#5c6b66]">
                {screenerLoading || screener?.status === "warming"
                  ? "Aplicando los 7 filtros sobre el universo de crecimiento… La primera vez tarda ~40s y se actualiza solo."
                  : "No se pudo cargar el screener. Pulsa «Refrescar» para reintentar."}
              </p>
            </div>
          ) : (screener.results || []).length > 0 ? (
            <>
              {(screener.con_fuentes || []).length > 0 && (
                <p className="text-[11px] text-[#1a6a94] bg-[#229ED910] border border-[#229ED925] rounded-md px-3 py-2 mb-3">
                  📣 <b>{screener.con_fuentes.length}</b> de estas acciones las mencionan tus fuentes de pago — salen primero, marcadas.
                </p>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Las mencionadas por tus fuentes flotan arriba (sin alterar el score). */}
                {[...screener.results]
                  .sort((a, b) => (b.fuentes ? 1 : 0) - (a.fuentes ? 1 : 0))
                  .map((row) => (
                    <ScreenerCard key={row.symbol} row={row} onPick={handlePick} />
                  ))}
              </div>
            </>
          ) : (
            <div className="card-flat p-12 text-center">
              <p className="text-sm text-[#5c6b66]">Ninguna acción del universo cumple hoy los 7 filtros. Prueba a refrescar más tarde.</p>
            </div>
          )}
        </>
      )}

      {/* ============ MOVERS MODE ============ */}
      {mode === "movers" && (
        <>
          <section className="card-flat p-6">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Fire size={20} weight="fill" className="text-[#d85c41]" />
                  <h2 className="font-heading font-bold text-2xl text-[#0e1f1a]">Movers del Mercado</h2>
                </div>
                <p className="text-sm text-[#5c6b66]">Mayores subidas, bajadas y más negociadas del mercado US hoy.</p>
              </div>
              <Button onClick={loadMovers} disabled={moversLoading} variant="outline" className="border-[#e5e0d8] font-mono text-xs">
                <ArrowClockwise size={14} weight="bold" className="mr-1" />
                {moversLoading ? "Cargando..." : "Refrescar"}
              </Button>
            </div>
          </section>

          {moversLoading && !movers ? (
            <div className="card-flat p-12 text-center"><p className="text-sm text-[#5c6b66]">Cargando movers del mercado...</p></div>
          ) : movers && ((movers.gainers || []).length || (movers.losers || []).length || (movers.actives || []).length) ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <MoversColumn title="Mayores subidas" icon={TrendUp} rows={movers.gainers} color="#4a7c59" onPick={handlePick} />
              <MoversColumn title="Mayores bajadas" icon={TrendDown} rows={movers.losers} color="#d85c41" onPick={handlePick} />
              <MoversColumn title="Más negociadas" icon={Pulse} rows={movers.actives} color="#1F6FB5" onPick={handlePick} />
            </div>
          ) : (
            <div className="card-flat p-12 text-center">
              <p className="text-sm text-[#5c6b66]">No hay datos de movers. Requiere configurar <span className="font-mono">FMP_API_KEY</span> en el servidor.</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
