import React from "react";
import { ArrowUpRight, ArrowDownRight, Minus, Target, Shield, TrendUp, TrendDown, Crosshair, Star } from "@phosphor-icons/react";
import { fmtPrice } from "../lib/format";
import InfoDot from "./InfoDot";

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
      className="inline-flex items-center gap-1 bg-aviso/15 text-aviso rounded px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-wider"
    >
      <Star size={9} weight="fill" />
      Alta prob · {match.type}
    </span>
  );
}

// ── Niveles de compra por confluencia ───────────────────────────────────────
//
// EL PROBLEMA QUE RESUELVE ESTA VERSIÓN
//
// El panel manejaba CUATRO dimensiones independientes con dos canales visuales, y las
// mezclaba. Con FORM a $112.47 el resultado apuntaba al revés que la operativa:
//
//   NIVEL 1 · a −1,4%  · fuerza 83  → barra a media asta   (por aquí se entra)
//   NIVEL 6 · a −50,7% · fuerza 100 → barra llena, verde   (otro ciclo de distancia)
//
// La barra medía FIABILIDAD y se leía como CONVENIENCIA. Y en verde, que en esta app
// significa «sube»: un soporte fiable a la mitad de precio no es una buena noticia.
//
// EL REPARTO NUEVO — un canal por dimensión, sin igualarlas:
//
//   cercanía   → posición. La lista ya venía ordenada por precio; el raíl la convierte
//                en un eje visible. −50,7% deja de ser una cifra y pasa a ser distancia.
//   confluencia→ texto. «Coinciden 6 métodos» discrimina mejor que «100/100», donde
//                tres niveles empatan. El número sigue en el InfoDot.
//   plan       → agrupación, el canal más fuerte, que estaba sin usar. Sale de `en_plan`,
//                que calcula el backend con la MISMA función que construye el plan.
//   origen     → el chip «Táctico», que ya estaba bien.
//
// Ningún dato nuevo y ninguna métrica inventada: se recolocan los que ya llegaban.

function Nivel({ z, estructural }) {
  const dist = z.distance_pct;
  const metodos = Array.isArray(z.reasons) ? z.reasons.length : 0;

  return (
    <div
      data-testid={`nivel-${z.label ? z.label.replace(/\s+/g, "-").toLowerCase() : "sin-etiqueta"}`}
      className="grid grid-cols-[64px_1fr] items-start border-b border-linea last:border-b-0"
    >
      {/* Raíl de distancia: la posición ES el eje de precios. */}
      <div className={`relative text-right pr-3 border-r-2 border-linea-fuerte font-mono tabular-nums
        ${estructural ? "py-1.5 text-[11px] text-tinta-3" : "py-2.5 text-[12px] text-tinta font-semibold"}`}>
        {dist != null ? `${dist >= 0 ? "+" : ""}${dist.toFixed(1)}%` : "—"}
        <span
          aria-hidden="true"
          className={`absolute rounded-full ${estructural ? "w-1.5 h-1.5 bg-linea-fuerte" : "w-2 h-2 bg-marca"}`}
          style={{ right: estructural ? -4 : -5, top: "50%", transform: "translateY(-50%)" }}
        />
      </div>

      <div className={`pl-4 min-w-0 ${estructural ? "py-1.5" : "py-2.5"}`}>
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="font-mono text-[10px] font-semibold text-tinta-3 uppercase tracking-wider">{z.label}</span>
          <span className={`font-mono font-bold text-tinta ${estructural ? "text-[13px]" : "text-[17px]"}`}>
            ${fmtPrice(z.price)}
          </span>
          {!estructural && z.zone_low != null && z.zone_high != null && z.zone_low !== z.zone_high && (
            <span className="font-mono text-[10px] text-tinta-3">(${fmtPrice(z.zone_low)}–${fmtPrice(z.zone_high)})</span>
          )}
          {z.tactical && (
            <span className="inline-flex items-center gap-0.5">
              <span className="inline-flex items-center bg-aviso/15 text-aviso rounded px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-wider">Táctico</span>
              <InfoDot term="Tactico" />
            </span>
          )}
          {z.rol && (
            <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-wider ${
              z.rol === "cercano"
                ? "bg-marca text-marca-tinta"
                : "bg-aviso/15 text-aviso border border-aviso/35"}`}>
              {z.rol === "cercano" ? "El más cercano" : "El más sólido"}
            </span>
          )}
        </div>

        {/* Confluencia contada, no medida con una barra. El número sigue accesible. */}
        {metodos > 0 && (
          <p className={`text-tinta-3 leading-snug ${estructural ? "text-[10.5px] mt-0.5" : "text-[11.5px] mt-1"}`}>
            <span className="font-semibold text-tinta">
              {metodos === 1 ? "1 método" : `Coinciden ${metodos} métodos`}
            </span>
            <span
              className="ml-1"
              title={`Fuerza ponderada ${z.strength}/100`}
            >
              {estructural ? "" : `: ${z.reasons.join(" · ")}`}
            </span>
          </p>
        )}
      </div>
    </div>
  );
}

function SmartBuyLevels({ levels }) {
  if (!levels || !levels.length) return null;

  // `en_plan` lo marca el backend. Si faltara —una respuesta vieja en caché— no se
  // adivina el corte replicando el umbral aquí: se cae a una sola lista sin agrupar.
  const hayPlan = levels.some((z) => typeof z.en_plan === "boolean");
  const plan = hayPlan ? levels.filter((z) => z.en_plan) : levels;
  const estructurales = hayPlan ? levels.filter((z) => !z.en_plan) : [];

  // Dos roles con nombre, y solo dos: son las dos preguntas que uno se hace, y el puente
  // con la tesis, que cita «la zona más sólida» por su NIVEL.
  const masSolido = levels.reduce(
    (mejor, z) => (mejor == null || (z.strength ?? 0) > (mejor.strength ?? 0) ? z : mejor), null);
  const marcar = (z) => ({
    ...z,
    rol: z === plan[0] ? "cercano" : z === masSolido ? "solido" : null,
  });
  const profundo = plan.length ? plan[plan.length - 1] : null;

  return (
    <div data-testid="smart-buy-levels" className="mb-5 p-4 bg-sube/[0.04] border border-sube/25 rounded-md">
      <div className="flex items-center gap-2 mb-1">
        <Crosshair size={14} weight="bold" className="text-sube" />
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-sube">
          Niveles de compra por confluencia · calculados sobre estructura real
        </p>
        <InfoDot term="Confluencia" />
      </div>

      <div className="mt-3">
        {hayPlan && (
          <div className="flex items-baseline gap-2 flex-wrap pb-1.5 mb-1 border-b border-sube/30">
            <span className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-sube">
              El plan · {plan.length} {plan.length === 1 ? "escalón" : "escalones"}
            </span>
            <span className="text-[11px] text-tinta-3 ml-auto">donde la compra se reparte</span>
          </div>
        )}
        {plan.map((z, i) => <Nivel key={z.label || i} z={marcar(z)} estructural={false} />)}
        {profundo?.zone_low != null && (
          <p className="text-[10.5px] text-tinta-3 mt-2">
            El stop del plan irá por debajo de ${fmtPrice(profundo.zone_low)}, la zona más profunda
            a la que se invita a comprar.
          </p>
        )}
      </div>

      {estructurales.length > 0 && (
        <div className="mt-4">
          <div className="flex items-baseline gap-2 flex-wrap pb-1.5 mb-1 border-b border-linea">
            <span className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-tinta-3">
              Soportes estructurales · fuera del plan
            </span>
            <span className="text-[11px] text-tinta-3 ml-auto">
              demasiado lejos: arrastrarían el stop hasta ahí
            </span>
          </div>
          {estructurales.map((z, i) => <Nivel key={z.label || i} z={marcar(z)} estructural />)}
        </div>
      )}

      <p className="text-[10px] text-tinta-3 mt-3 leading-relaxed">
        «Coinciden N métodos» es cuántas fuentes independientes señalan la misma zona (volumen real,
        Fibonacci, soportes históricos, medias). Cuantas más, más fiable es el nivel — pero la fiabilidad
        no dice nada de lo cerca que está: eso lo marca la distancia de la izquierda.
      </p>
    </div>
  );
}

function RecBig({ rec }) {
  if (rec === "COMPRAR") {
    return (
      <div data-testid="rec-big" className="bg-sube text-marca-tinta px-5 py-3 rounded-md flex items-center gap-2">
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
      <div data-testid="rec-big" className="bg-baja text-marca-tinta px-5 py-3 rounded-md flex items-center gap-2">
        <ArrowDownRight size={28} weight="bold" />
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] opacity-80">Recomendación</p>
          <p className="font-heading font-bold text-2xl leading-none">VENDER</p>
        </div>
      </div>
    );
  }
  return (
    <div data-testid="rec-big" className="bg-tinta-3 text-marca-tinta px-5 py-3 rounded-md flex items-center gap-2">
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
    buy: { bg: "bg-sube/10", text: "text-sube", border: "border-sube/30" },
    sell: { bg: "bg-baja/10", text: "text-baja", border: "border-baja/30" },
    neutral: { bg: "bg-fondo", text: "text-tinta", border: "border-linea" },
  };
  const c = colors[tone] || colors.neutral;
  return (
    <div data-testid={testId} className={`${c.bg} border ${c.border} rounded-md p-4`}>
      <div className={`flex items-center gap-1.5 ${c.text}`}>
        {icon}
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] font-medium">{label}</p>
      </div>
      <p className={`font-mono font-bold text-xl ${c.text} mt-2`}>{primary}</p>
      {sub && <p className="text-[11px] text-tinta-3 mt-1 font-mono">{sub}</p>}
    </div>
  );
}

export default function TradingLevels({ quote, analysis, analystConsensus, priceTarget, volumeProfile, buyLevels }) {
  const current = quote?.price;
  const vpLevels = buildVpLevels(volumeProfile);
  const hasVp = vpLevels.length > 0;
  const hasBuyLevels = Array.isArray(buyLevels) && buyLevels.length > 0;
  // Los niveles por confluencia (motor determinista) y el Volume Profile NO dependen de la IA:
  // se muestran ya al abrir la acción, sin gastar cuota. El plan de la IA (entrada/stop/TP,
  // recomendación) aparece cuando generas el análisis. Solo ocultamos todo si no hay NADA.
  if (!analysis && !hasBuyLevels && !hasVp && !priceTarget?.target_mean) return null;

  const entryMid = analysis?.entry_zone ? (analysis.entry_zone.min + analysis.entry_zone.max) / 2 : null;
  const distEntry = current && entryMid ? ((entryMid - current) / current) * 100 : null;
  const distSL = current && analysis?.stop_loss ? ((analysis.stop_loss - current) / current) * 100 : null;
  const distTP1 = current && analysis?.take_profit_1 ? ((analysis.take_profit_1 - current) / current) * 100 : null;
  const distTP2 = current && analysis?.take_profit_2 ? ((analysis.take_profit_2 - current) / current) * 100 : null;
  const distTarget = current && priceTarget?.target_mean ? ((priceTarget.target_mean - current) / current) * 100 : null;

  return (
    <section data-testid="trading-levels" className="iv-panel p-6 animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <Crosshair size={20} weight="bold" className="text-marca" />
            <h3 className="font-heading font-bold text-xl text-tinta">
              Niveles de Compra y Venta
            </h3>
          </div>
          <p className="text-sm text-tinta-3 mt-1">
            {analysis
              ? <>Plan operativo sugerido por IA · Precio actual: <span className="font-mono font-semibold text-tinta">${fmtPrice(current)}</span></>
              : <>Niveles por confluencia (motor, sin IA) · Precio actual: <span className="font-mono font-semibold text-tinta">${fmtPrice(current)}</span> · <span className="text-aviso">genera el análisis IA para el plan completo</span></>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {analystConsensus && (
            <div className="text-right">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">
                Consenso analistas ({analystConsensus.total_analysts})
              </p>
              <p className="font-heading font-semibold text-sm text-tinta">{analystConsensus.consensus}</p>
            </div>
          )}
          {analysis && <RecBig rec={analysis.recommendation} />}
        </div>
      </div>

      {/* Smart buy levels — confluence engine, ranked by strength */}
      <SmartBuyLevels levels={buyLevels} />

      {/* Volume Profile bar — the real high-volume price levels */}
      {hasVp && (
        <div data-testid="volume-profile-bar" className="mb-5 p-3 bg-aviso/5 border border-aviso/20 rounded-md">
          <div className="flex items-center gap-2 mb-2">
            <Star size={12} weight="fill" className="text-aviso" />
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-aviso">
              Volume Profile · niveles de alto volumen real ({volumeProfile.bars_analyzed || "—"} sesiones)
            </p>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            {volumeProfile.poc != null && (
              <div className="flex items-baseline gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-tinta-3 inline-flex items-center gap-1">POC <InfoDot term="POC" /></span>
                <span className="font-mono text-sm font-semibold text-aviso">${fmtPrice(volumeProfile.poc)}</span>
                <span className="text-[9px] text-tinta-3">(más negociado)</span>
              </div>
            )}
            {volumeProfile.vah != null && (
              <div className="flex items-baseline gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-tinta-3 inline-flex items-center gap-1">VAH <InfoDot term="VAH" /></span>
                <span className="font-mono text-sm font-semibold text-tinta">${fmtPrice(volumeProfile.vah)}</span>
                {current && Math.abs((volumeProfile.vah - current) / current) > 0.15 && (
                  <span className="text-[9px] text-tinta-3" title="Volumen acumulado hace meses, lejos del precio actual — contexto, no nivel accionable a corto plazo.">(histórico)</span>
                )}
              </div>
            )}
            {volumeProfile.val != null && (
              <div className="flex items-baseline gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-tinta-3 inline-flex items-center gap-1">VAL <InfoDot term="VAL" /></span>
                <span className="font-mono text-sm font-semibold text-tinta">${fmtPrice(volumeProfile.val)}</span>
                {current && Math.abs((volumeProfile.val - current) / current) > 0.15 && (
                  <span className="text-[9px] text-tinta-3" title="Volumen acumulado hace meses, lejos del precio actual — contexto, no nivel accionable a corto plazo.">(histórico)</span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 4 main level cards (solo con análisis IA) */}
      {analysis && (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {analysis.entry_zone && (
          <LevelCard
            testId="level-entry"
            icon={<Target size={14} weight="bold" />}
            label="Zona Entrada"
            primary={`$${fmtPrice(analysis.entry_zone.min)} - $${fmtPrice(analysis.entry_zone.max)}`}
            sub={
              // entry_avg es el precio medio si repartes la compra entre las 3 zonas, y es la
              // base real del R/R que se muestra abajo. Sin enseñarlo, el ratio salía de un
              // número que el usuario no veía por ninguna parte.
              analysis.entry_avg != null
                ? `Medio escalonando: $${fmtPrice(analysis.entry_avg)}`
                : distEntry != null ? `${distEntry >= 0 ? "+" : ""}${distEntry.toFixed(2)}% desde actual` : null
            }
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
      )}

      {/* Riesgo/recompensa y su base. El motor calcula rr_bajo cuando TP1 no llega al mínimo
          profesional (2:1); antes se calculaba y no lo leía nadie, así que el aviso honesto
          "este plan no compensa" se tiraba a la basura. */}
      {analysis?.risk_reward_ratio != null && (
        <div
          data-testid="level-rr"
          className={`mt-3 px-4 py-2.5 rounded-lg flex items-start gap-2.5 flex-wrap ${
            analysis.rr_bajo
              ? "border border-aviso/40 bg-aviso/[0.07]"
              : "bg-sube/[0.07]"
          }`}
        >
          <span className="text-sm leading-none mt-0.5">{analysis.rr_bajo ? "⚠️" : "✅"}</span>
          <div className="flex-1 min-w-[200px]">
            <span className="text-[11px] uppercase tracking-[0.18em] text-tinta-3 font-mono">
              Riesgo / Recompensa
            </span>
            <p className="text-[12px] leading-snug mt-0.5 text-tinta-2">
              <b className="font-mono text-sm">{analysis.risk_reward_ratio}:1</b>
              {analysis.entry_avg != null && (
                <> · calculado sobre la entrada media de <b className="font-mono">${fmtPrice(analysis.entry_avg)}</b></>
              )}
              {analysis.rr_bajo ? (
                <> — <b>por debajo del mínimo de 2:1</b>. Arriesgas casi tanto como puedes ganar:
                  necesitarías acertar más del 40% de las veces solo para no perder dinero.
                  Plantéate esperar a un precio mejor en vez de estrechar el stop.</>
              ) : (
                <> — cumple el mínimo profesional de 2:1.</>
              )}
            </p>
          </div>
        </div>
      )}

      {/* Multi-level lists: 3 entries, 3 SL, 3 TP */}
      {analysis && (analysis.entry_zones?.length || analysis.stop_losses?.length || analysis.take_profits?.length) && (
        <div className="mt-5 grid grid-cols-1 lg:grid-cols-3 gap-4">
          {analysis.entry_zones?.length > 0 && (
            <div data-testid="entry-zones-list" className="border border-linea rounded-md p-4">
              <div className="flex items-center gap-2 mb-3">
                <Target size={14} weight="bold" className="text-marca" />
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">Zonas de Entrada</p>
              </div>
              <div className="space-y-2">
                {analysis.entry_zones.map((z, i) => {
                  const mid = z.min != null && z.max != null ? (z.min + z.max) / 2 : null;
                  const match = findConfluence(mid, vpLevels);
                  return (
                    <div key={i} data-testid={`entry-zone-${z.label}`} className={`bg-fondo border-l-2 px-3 py-2 ${match ? "border-aviso" : "border-marca"}`}>
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[10px] font-semibold text-marca uppercase">{z.label}</span>
                        <span className="font-mono text-sm font-semibold text-tinta">
                          ${fmtPrice(z.min)} - ${fmtPrice(z.max)}
                        </span>
                      </div>
                      {match && <div className="mt-1"><ConfluenceBadge match={match} /></div>}
                      {z.comment && <p className="text-[11px] text-tinta-3 mt-1 leading-snug">{z.comment}</p>}
                    </div>
                  );
                })}
              </div>
              {/* Por qué el plan puede tener menos zonas que la lista de confluencia de
                  arriba. Sin esto, ver "NIVEL 3" arriba y solo dos zonas aquí parece un fallo. */}
              {analysis.plan_nota && (
                <p className="text-[11px] text-tinta-3 mt-2 leading-snug border-t border-linea pt-2">
                  {analysis.plan_nota}
                </p>
              )}
            </div>
          )}

          {analysis.stop_losses?.length > 0 && (
            <div data-testid="stop-losses-list" className="border border-linea rounded-md p-4">
              <div className="flex items-center gap-2 mb-3">
                <Shield size={14} weight="bold" className="text-baja" />
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">Stop Losses</p>
              </div>
              <div className="space-y-2">
                {analysis.stop_losses.map((s, i) => {
                  const d = current ? ((s.price - current) / current) * 100 : null;
                  return (
                    <div key={i} data-testid={`stop-loss-${s.label}`} className="bg-baja/5 border-l-2 border-baja px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[10px] font-semibold text-baja uppercase">{s.label}</span>
                        <span className="font-mono text-sm font-semibold text-baja">
                          ${fmtPrice(s.price)}
                          {d != null && <span className="text-[10px] text-tinta-3 ml-1">({d.toFixed(2)}%)</span>}
                        </span>
                      </div>
                      {s.comment && <p className="text-[11px] text-tinta-3 mt-1 leading-snug">{s.comment}</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {analysis.take_profits?.length > 0 && (
            <div data-testid="take-profits-list" className="border border-linea rounded-md p-4">
              <div className="flex items-center gap-2 mb-3">
                <TrendUp size={14} weight="bold" className="text-sube" />
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">Take Profits</p>
              </div>
              <div className="space-y-2">
                {analysis.take_profits.map((t, i) => {
                  const d = current ? ((t.price - current) / current) * 100 : null;
                  return (
                    <div key={i} data-testid={`take-profit-${t.label}`} className="bg-sube/5 border-l-2 border-sube px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[10px] font-semibold text-sube uppercase">{t.label}</span>
                        <span className="font-mono text-sm font-semibold text-sube">
                          ${fmtPrice(t.price)}
                          {d != null && <span className="text-[10px] text-tinta-3 ml-1">({d >= 0 ? "+" : ""}{d.toFixed(2)}%)</span>}
                        </span>
                      </div>
                      {t.comment && <p className="text-[11px] text-tinta-3 mt-1 leading-snug">{t.comment}</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Support / Resistance bands */}
      {analysis?.key_levels && (
        <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div data-testid="key-supports" className="border border-linea rounded-md p-4">
            <div className="flex items-center gap-2 mb-3">
              <TrendDown size={14} weight="bold" className="text-sube" />
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">Soportes (compra)</p>
            </div>
            <div className="space-y-2">
              {(analysis.key_levels.support || []).map((s, i) => {
                const d = current ? ((s - current) / current) * 100 : null;
                const match = findConfluence(s, vpLevels);
                return (
                  <div key={i} className={`flex items-center justify-between gap-2 bg-sube/5 border-l-2 px-3 py-2 ${match ? "border-aviso" : "border-sube"}`}>
                    <span className="text-xs font-mono text-tinta-3">S{i + 1}</span>
                    {match && <ConfluenceBadge match={match} />}
                    <span className="font-mono font-semibold text-sube ml-auto">${fmtPrice(s)}</span>
                    {d != null && <span className="font-mono text-[10px] text-tinta-3">{d.toFixed(2)}%</span>}
                  </div>
                );
              })}
            </div>
          </div>
          <div data-testid="key-resistances" className="border border-linea rounded-md p-4">
            <div className="flex items-center gap-2 mb-3">
              <TrendUp size={14} weight="bold" className="text-baja" />
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">Resistencias (venta)</p>
            </div>
            <div className="space-y-2">
              {(analysis.key_levels.resistance || []).map((r, i) => {
                const d = current ? ((r - current) / current) * 100 : null;
                const match = findConfluence(r, vpLevels);
                return (
                  <div key={i} className={`flex items-center justify-between gap-2 bg-baja/5 border-l-2 px-3 py-2 ${match ? "border-aviso" : "border-baja"}`}>
                    <span className="text-xs font-mono text-tinta-3">R{i + 1}</span>
                    {match && <ConfluenceBadge match={match} />}
                    <span className="font-mono font-semibold text-baja ml-auto">${fmtPrice(r)}</span>
                    {d != null && <span className="font-mono text-[10px] text-tinta-3">+{d.toFixed(2)}%</span>}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Analyst price target band */}
      {priceTarget && priceTarget.target_mean && (
        <div data-testid="price-target" className="mt-5 p-4 bg-marca/5 border border-marca/20 rounded-md">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">
                Objetivo Wall Street ({priceTarget.analysts_count} analistas)
              </p>
              <p className="font-mono font-bold text-2xl text-marca mt-1">
                ${fmtPrice(priceTarget.target_mean)}
                {distTarget != null && (
                  <span className={`text-sm ml-2 ${distTarget >= 0 ? "text-sube" : "text-baja"}`}>
                    ({distTarget >= 0 ? "+" : ""}{distTarget.toFixed(1)}%)
                  </span>
                )}
              </p>
            </div>
            <div className="flex gap-4 text-right">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">Bajo</p>
                <p className="font-mono font-semibold text-baja">${fmtPrice(priceTarget.target_low)}</p>
              </div>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">Mediana</p>
                <p className="font-mono font-semibold text-tinta">${fmtPrice(priceTarget.target_median)}</p>
              </div>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-tinta-3">Alto</p>
                <p className="font-mono font-semibold text-sube">${fmtPrice(priceTarget.target_high)}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Summary line */}
      {analysis?.summary && (
        <p className="mt-5 text-sm text-tinta leading-relaxed border-l-2 border-marca pl-3">
          {analysis.summary}
        </p>
      )}
    </section>
  );
}
