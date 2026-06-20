import React from "react";
import { ArrowUpRight, ArrowDownRight, Minus, Target, Shield, TrendUp, TrendDown, Crosshair, Star } from "@phosphor-icons/react";
import { fmtPrice, fmtPct } from "../lib/format";

// Build the list of high-conviction price levels from the Volume Profile.
function buildVpLevels(vp) {
  if (!vp) return [];
  const levels = [];
  if (vp.poc) levels.push({ price: vp.poc, type: "POC" });
  if (vp.vah) levels.push({ price: vp.vah, type: "VAH" });
  if (vp.val) levels.push({ price: vp.val, type: "VAL" });
  (vp.hvn || []).forEach((h) => levels.push({ price: h, type: "HVN" }));
  return levels;
}

// Returns the matching VP level if `price` is within tolerance% of one — null otherwise.
function findConfluence(price, vpLevels, tolerancePct = 2) {
  if (!price || !vpLevels || !vpLevels.length) return null;
  let best = null;
  for (const lvl of vpLevels) {
    const diff = Math.abs((price - lvl.price) / price) * 100;
    if (diff <= tolerancePct && (!best || diff < best.diff)) {
      best = { ...lvl, diff };
    }
  }
  return best;
}

function ConfluenceBadge({ match }) {
  if (!match) return null;
  return (
    <span
      title={`Confluencia con ${match.type} del Volume Profile ($${fmtPrice(match.price)}) — zona donde más se ha negociado. Nivel de alta probabilidad.`}
      className="inline-flex items-center gap-1 bg-[#b8860b]/15 text-[#8a6508] rounded px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-wider"
    >
      <Star size={9} weight="fill" />
      Alta prob · {match.type}
    </span>
  );
}

// Color of the strength meter by score.
function strengthTone(s) {
  if (s >= 75) return { bar: "bg-[#4a7c59]", text: "text-[#4a7c59]", label: "Muy fuerte" };
  if (s >= 50) return { bar: "bg-[#c9a14a]", text: "text-[#8a6508]", label: "Fuerte" };
  return { bar: "bg-[#9aa39f]", text: "text-[#5c6b66]", label: "Moderado" };
}

// Confluence-engine buy zones: deterministic levels ranked by how many independent
// methods (Volume Profile + Fibonacci + pivots + SMAs) agree, each with a 0-100 score.
function SmartBuyLevels({ levels, current }) {
  if (!levels || !levels.length) return null;
  return (
    <div data-testid="smart-buy-levels" className="mb-5 p-4 bg-[#4a7c59]/[0.04] border border-[#4a7c59]/25 rounded-md">
      <div className="flex items-center gap-2 mb-3">
        <Crosshair size={14} weight="bold" className="text-[#4a7c59]" />
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#4a7c59]">
          Niveles de compra por confluencia · calculados sobre estructura real
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {levels.map((z, i) => {
          const tone = strengthTone(z.strength);
          const dist = z.distance_pct != null ? z.distance_pct
            : current && z.price ? ((z.price - current) / current) * 100 : null;
          return (
            <div key={i} data-testid={`smart-level-${i}`} className={`bg-white border rounded-md p-3 ${z.tactical ? "border-dashed border-[#b8860b]/50" : "border-[#e5e0d8]"}`}>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[10px] font-semibold text-[#1a3a32] uppercase tracking-wider">{z.label}</span>
                  {z.tactical && (
                    <span title="Entrada táctica: rellena un hueco grande entre niveles fuertes. Tamaño de posición menor — sirve para suavizar la entrada, no es un soporte estructural de roca." className="inline-flex items-center bg-[#b8860b]/15 text-[#8a6508] rounded px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-wider">Táctico</span>
                  )}
                  <span className="font-mono font-bold text-lg text-[#0e1f1a]">${fmtPrice(z.price)}</span>
                  {z.zone_low != null && z.zone_high != null && z.zone_low !== z.zone_high && (
                    <span className="font-mono text-[10px] text-[#5c6b66]">(${fmtPrice(z.zone_low)}–${fmtPrice(z.zone_high)})</span>
                  )}
                </div>
                {dist != null && (
                  <span className="font-mono text-[11px] text-[#5c6b66]">{dist >= 0 ? "+" : ""}{dist.toFixed(1)}%</span>
                )}
              </div>

              {/* Strength meter */}
              <div className="flex items-center gap-2 mt-2">
                <div className="flex-1 h-1.5 bg-[#e5e0d8] rounded-full overflow-hidden">
                  <div className={`h-full ${tone.bar} transition-all`} style={{ width: `${Math.max(0, Math.min(100, z.strength))}%` }} />
                </div>
                <span className={`font-mono text-[11px] font-semibold ${tone.text}`}>{z.strength}/100</span>
              </div>

              {/* Confluence reasons */}
              {Array.isArray(z.reasons) && z.reasons.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {z.reasons.map((r, j) => (
                    <span key={j} className="inline-flex items-center text-[9px] font-medium px-1.5 py-0.5 rounded bg-[#1a3a32]/[0.06] text-[#3a4a44]">
                      {r}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-[#5c6b66] mt-3 leading-relaxed">
        La fuerza mide cuántos métodos independientes coinciden en la misma zona (volumen real, Fibonacci, soportes históricos, medias).
        Cuantos más coinciden, más fiable es el nivel.
      </p>
    </div>
  );
}

function RecBig({ rec }) {
  if (rec === "COMPRAR") {
    return (
      <div data-testid="rec-big" className="bg-[#4a7c59] text-[#f5f3ef] px-5 py-3 rounded-md flex items-center gap-2">
        <ArrowUpRight size={28} weight="bold" />
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] opacity-80">Recomendación</p>
          <p className="font-heading font-bold text-2xl leading-none">COMPRAR</p>
        </div>
      </div>
    );
  }
  if (rec === "VENDER") {
    return (
      <div data-testid="rec-big" className="bg-[#d85c41] text-[#f5f3ef] px-5 py-3 rounded-md flex items-center gap-2">
        <ArrowDownRight size={28} weight="bold" />
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] opacity-80">Recomendación</p>
          <p className="font-heading font-bold text-2xl leading-none">VENDER</p>
        </div>
      </div>
    );
  }
  return (
    <div data-testid="rec-big" className="bg-[#5c6b66] text-[#f5f3ef] px-5 py-3 rounded-md flex items-center gap-2">
      <Minus size={28} weight="bold" />
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] opacity-80">Recomendación</p>
        <p className="font-heading font-bold text-2xl leading-none">MANTENER</p>
      </div>
    </div>
  );
}

function LevelCard({ icon, label, primary, sub, tone, testId }) {
  const colors = {
    buy: { bg: "bg-[#4a7c59]/10", text: "text-[#4a7c59]", border: "border-[#4a7c59]/30" },
    sell: { bg: "bg-[#d85c41]/10", text: "text-[#d85c41]", border: "border-[#d85c41]/30" },
    neutral: { bg: "bg-[#f5f3ef]", text: "text-[#0e1f1a]", border: "border-[#e5e0d8]" },
  };
  const c = colors[tone] || colors.neutral;
  return (
    <div data-testid={testId} className={`${c.bg} border ${c.border} rounded-md p-4`}>
      <div className={`flex items-center gap-1.5 ${c.text}`}>
        {icon}
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] font-medium">{label}</p>
      </div>
      <p className={`font-mono font-bold text-xl ${c.text} mt-2`}>{primary}</p>
      {sub && <p className="text-[11px] text-[#5c6b66] mt-1 font-mono">{sub}</p>}
    </div>
  );
}

export default function TradingLevels({ quote, analysis, analystConsensus, priceTarget, volumeProfile, buyLevels }) {
  if (!analysis) {
    return (
      <section data-testid="trading-levels-empty" className="card-flat p-6 border-2 border-dashed">
        <div className="flex items-center gap-2 mb-2">
          <Crosshair size={20} weight="bold" className="text-[#1a3a32]" />
          <h3 className="font-heading font-bold text-xl text-[#0e1f1a]">Niveles de Compra y Venta</h3>
        </div>
        <p className="text-sm text-[#5c6b66]">
          Genera un análisis IA para ver tus niveles operativos: zona de entrada, stop-loss, take-profits y consenso de analistas.
        </p>
      </section>
    );
  }

  const current = quote?.price;
  const vpLevels = buildVpLevels(volumeProfile);
  const hasVp = vpLevels.length > 0;
  const entryMid = analysis.entry_zone ? (analysis.entry_zone.min + analysis.entry_zone.max) / 2 : null;
  const distEntry = current && entryMid ? ((entryMid - current) / current) * 100 : null;
  const distSL = current && analysis.stop_loss ? ((analysis.stop_loss - current) / current) * 100 : null;
  const distTP1 = current && analysis.take_profit_1 ? ((analysis.take_profit_1 - current) / current) * 100 : null;
  const distTP2 = current && analysis.take_profit_2 ? ((analysis.take_profit_2 - current) / current) * 100 : null;
  const distTarget = current && priceTarget?.target_mean ? ((priceTarget.target_mean - current) / current) * 100 : null;

  return (
    <section data-testid="trading-levels" className="card-flat p-6 animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <Crosshair size={20} weight="bold" className="text-[#1a3a32]" />
            <h3 className="font-heading font-bold text-xl text-[#0e1f1a]">
              Niveles de Compra y Venta
            </h3>
          </div>
          <p className="text-sm text-[#5c6b66] mt-1">
            Plan operativo sugerido por IA · Precio actual: <span className="font-mono font-semibold text-[#0e1f1a]">${fmtPrice(current)}</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          {analystConsensus && (
            <div className="text-right">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">
                Consenso analistas ({analystConsensus.total_analysts})
              </p>
              <p className="font-heading font-semibold text-sm text-[#0e1f1a]">{analystConsensus.consensus}</p>
            </div>
          )}
          <RecBig rec={analysis.recommendation} />
        </div>
      </div>

      {/* Smart buy levels — confluence engine, ranked by strength */}
      <SmartBuyLevels levels={buyLevels} current={current} />

      {/* Volume Profile bar — the real high-volume price levels */}
      {hasVp && (
        <div data-testid="volume-profile-bar" className="mb-5 p-3 bg-[#b8860b]/5 border border-[#b8860b]/20 rounded-md">
          <div className="flex items-center gap-2 mb-2">
            <Star size={12} weight="fill" className="text-[#8a6508]" />
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#8a6508]">
              Volume Profile · niveles de alto volumen real ({volumeProfile.bars_analyzed || "—"} sesiones)
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            {volumeProfile.poc != null && (
              <div className="flex items-baseline gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-[#5c6b66]">POC</span>
                <span className="font-mono text-sm font-semibold text-[#8a6508]">${fmtPrice(volumeProfile.poc)}</span>
                <span className="text-[9px] text-[#5c6b66]">(más negociado)</span>
              </div>
            )}
            {volumeProfile.vah != null && (
              <div className="flex items-baseline gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-[#5c6b66]">VAH</span>
                <span className="font-mono text-sm font-semibold text-[#0e1f1a]">${fmtPrice(volumeProfile.vah)}</span>
              </div>
            )}
            {volumeProfile.val != null && (
              <div className="flex items-baseline gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-[#5c6b66]">VAL</span>
                <span className="font-mono text-sm font-semibold text-[#0e1f1a]">${fmtPrice(volumeProfile.val)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 4 main level cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {analysis.entry_zone && (
          <LevelCard
            testId="level-entry"
            icon={<Target size={14} weight="bold" />}
            label="Zona Entrada"
            primary={`$${fmtPrice(analysis.entry_zone.min)} - $${fmtPrice(analysis.entry_zone.max)}`}
            sub={distEntry != null ? `${distEntry >= 0 ? "+" : ""}${distEntry.toFixed(2)}% desde actual` : null}
            tone="neutral"
          />
        )}
        {analysis.stop_loss && (
          <LevelCard
            testId="level-sl"
            icon={<Shield size={14} weight="bold" />}
            label="Stop Loss"
            primary={`$${fmtPrice(analysis.stop_loss)}`}
            sub={distSL != null ? `${distSL >= 0 ? "+" : ""}${distSL.toFixed(2)}% riesgo` : null}
            tone="sell"
          />
        )}
        {analysis.take_profit_1 && (
          <LevelCard
            testId="level-tp1"
            icon={<TrendUp size={14} weight="bold" />}
            label="Take Profit 1"
            primary={`$${fmtPrice(analysis.take_profit_1)}`}
            sub={distTP1 != null ? `${distTP1 >= 0 ? "+" : ""}${distTP1.toFixed(2)}% potencial` : null}
            tone="buy"
          />
        )}
        {analysis.take_profit_2 && (
          <LevelCard
            testId="level-tp2"
            icon={<TrendUp size={14} weight="bold" />}
            label="Take Profit 2"
            primary={`$${fmtPrice(analysis.take_profit_2)}`}
            sub={distTP2 != null ? `${distTP2 >= 0 ? "+" : ""}${distTP2.toFixed(2)}% potencial` : null}
            tone="buy"
          />
        )}
      </div>

      {/* Multi-level lists: 3 entries, 3 SL, 3 TP */}
      {(analysis.entry_zones?.length || analysis.stop_losses?.length || analysis.take_profits?.length) && (
        <div className="mt-5 grid grid-cols-1 lg:grid-cols-3 gap-4">
          {analysis.entry_zones?.length > 0 && (
            <div data-testid="entry-zones-list" className="border border-[#e5e0d8] rounded-md p-4">
              <div className="flex items-center gap-2 mb-3">
                <Target size={14} weight="bold" className="text-[#1a3a32]" />
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">Zonas de Entrada</p>
              </div>
              <div className="space-y-2">
                {analysis.entry_zones.map((z, i) => {
                  const mid = z.min != null && z.max != null ? (z.min + z.max) / 2 : null;
                  const match = findConfluence(mid, vpLevels);
                  return (
                    <div key={i} data-testid={`entry-zone-${z.label}`} className={`bg-[#f5f3ef] border-l-2 px-3 py-2 ${match ? "border-[#b8860b]" : "border-[#1a3a32]"}`}>
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[10px] font-semibold text-[#1a3a32] uppercase">{z.label}</span>
                        <span className="font-mono text-sm font-semibold text-[#0e1f1a]">
                          ${fmtPrice(z.min)} - ${fmtPrice(z.max)}
                        </span>
                      </div>
                      {match && <div className="mt-1"><ConfluenceBadge match={match} /></div>}
                      {z.comment && <p className="text-[11px] text-[#5c6b66] mt-1 leading-snug">{z.comment}</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {analysis.stop_losses?.length > 0 && (
            <div data-testid="stop-losses-list" className="border border-[#e5e0d8] rounded-md p-4">
              <div className="flex items-center gap-2 mb-3">
                <Shield size={14} weight="bold" className="text-[#d85c41]" />
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">Stop Losses</p>
              </div>
              <div className="space-y-2">
                {analysis.stop_losses.map((s, i) => {
                  const d = current ? ((s.price - current) / current) * 100 : null;
                  return (
                    <div key={i} data-testid={`stop-loss-${s.label}`} className="bg-[#d85c41]/5 border-l-2 border-[#d85c41] px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[10px] font-semibold text-[#d85c41] uppercase">{s.label}</span>
                        <span className="font-mono text-sm font-semibold text-[#d85c41]">
                          ${fmtPrice(s.price)}
                          {d != null && <span className="text-[10px] text-[#5c6b66] ml-1">({d.toFixed(2)}%)</span>}
                        </span>
                      </div>
                      {s.comment && <p className="text-[11px] text-[#5c6b66] mt-1 leading-snug">{s.comment}</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {analysis.take_profits?.length > 0 && (
            <div data-testid="take-profits-list" className="border border-[#e5e0d8] rounded-md p-4">
              <div className="flex items-center gap-2 mb-3">
                <TrendUp size={14} weight="bold" className="text-[#4a7c59]" />
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">Take Profits</p>
              </div>
              <div className="space-y-2">
                {analysis.take_profits.map((t, i) => {
                  const d = current ? ((t.price - current) / current) * 100 : null;
                  return (
                    <div key={i} data-testid={`take-profit-${t.label}`} className="bg-[#4a7c59]/5 border-l-2 border-[#4a7c59] px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[10px] font-semibold text-[#4a7c59] uppercase">{t.label}</span>
                        <span className="font-mono text-sm font-semibold text-[#4a7c59]">
                          ${fmtPrice(t.price)}
                          {d != null && <span className="text-[10px] text-[#5c6b66] ml-1">({d >= 0 ? "+" : ""}{d.toFixed(2)}%)</span>}
                        </span>
                      </div>
                      {t.comment && <p className="text-[11px] text-[#5c6b66] mt-1 leading-snug">{t.comment}</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Support / Resistance bands */}
      {analysis.key_levels && (
        <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div data-testid="key-supports" className="border border-[#e5e0d8] rounded-md p-4">
            <div className="flex items-center gap-2 mb-3">
              <TrendDown size={14} weight="bold" className="text-[#4a7c59]" />
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">Soportes (compra)</p>
            </div>
            <div className="space-y-2">
              {(analysis.key_levels.support || []).map((s, i) => {
                const d = current ? ((s - current) / current) * 100 : null;
                const match = findConfluence(s, vpLevels);
                return (
                  <div key={i} className={`flex items-center justify-between gap-2 bg-[#4a7c59]/5 border-l-2 px-3 py-2 ${match ? "border-[#b8860b]" : "border-[#4a7c59]"}`}>
                    <span className="text-xs font-mono text-[#5c6b66]">S{i + 1}</span>
                    {match && <ConfluenceBadge match={match} />}
                    <span className="font-mono font-semibold text-[#4a7c59] ml-auto">${fmtPrice(s)}</span>
                    {d != null && <span className="font-mono text-[10px] text-[#5c6b66]">{d.toFixed(2)}%</span>}
                  </div>
                );
              })}
            </div>
          </div>
          <div data-testid="key-resistances" className="border border-[#e5e0d8] rounded-md p-4">
            <div className="flex items-center gap-2 mb-3">
              <TrendUp size={14} weight="bold" className="text-[#d85c41]" />
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">Resistencias (venta)</p>
            </div>
            <div className="space-y-2">
              {(analysis.key_levels.resistance || []).map((r, i) => {
                const d = current ? ((r - current) / current) * 100 : null;
                const match = findConfluence(r, vpLevels);
                return (
                  <div key={i} className={`flex items-center justify-between gap-2 bg-[#d85c41]/5 border-l-2 px-3 py-2 ${match ? "border-[#b8860b]" : "border-[#d85c41]"}`}>
                    <span className="text-xs font-mono text-[#5c6b66]">R{i + 1}</span>
                    {match && <ConfluenceBadge match={match} />}
                    <span className="font-mono font-semibold text-[#d85c41] ml-auto">${fmtPrice(r)}</span>
                    {d != null && <span className="font-mono text-[10px] text-[#5c6b66]">+{d.toFixed(2)}%</span>}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Analyst price target band */}
      {priceTarget && priceTarget.target_mean && (
        <div data-testid="price-target" className="mt-5 p-4 bg-[#1a3a32]/5 border border-[#1a3a32]/20 rounded-md">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">
                Objetivo Wall Street ({priceTarget.analysts_count} analistas)
              </p>
              <p className="font-mono font-bold text-2xl text-[#1a3a32] mt-1">
                ${fmtPrice(priceTarget.target_mean)}
                {distTarget != null && (
                  <span className={`text-sm ml-2 ${distTarget >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                    ({distTarget >= 0 ? "+" : ""}{distTarget.toFixed(1)}%)
                  </span>
                )}
              </p>
            </div>
            <div className="flex gap-4 text-right">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">Bajo</p>
                <p className="font-mono font-semibold text-[#d85c41]">${fmtPrice(priceTarget.target_low)}</p>
              </div>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">Mediana</p>
                <p className="font-mono font-semibold text-[#0e1f1a]">${fmtPrice(priceTarget.target_median)}</p>
              </div>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">Alto</p>
                <p className="font-mono font-semibold text-[#4a7c59]">${fmtPrice(priceTarget.target_high)}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Summary line */}
      {analysis.summary && (
        <p className="mt-5 text-sm text-[#0e1f1a] leading-relaxed border-l-2 border-[#1a3a32] pl-3">
          {analysis.summary}
        </p>
      )}
    </section>
  );
}
