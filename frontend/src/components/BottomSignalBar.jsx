import React from "react";
import { Gauge } from "lucide-react";
import { fmtPrice, fmtPct } from "../lib/format";
import CabeceraBloque from "./base/CabeceraBloque";

/**
 * Lectura rápida del valor abierto: precio, régimen, señal IA y niveles clave.
 *
 * Dos formas con los mismos datos:
 *   · `como="barra"` (por defecto): barra fija abajo, solo en móvil, con vidrio y
 *     desplazamiento lateral. En el móvil la cabecera se va con el scroll y esto la
 *     mantiene a mano.
 *   · `como="panel"`: pieza de la columna derecha en escritorio, a la altura del
 *     gráfico. Ahí la barra fija sobraba: tapaba el pie y repetía lo que ya se ve.
 */
const RECO = {
  COMPRAR: { tono: "sube", label: "Compra" },
  VENDER: { tono: "baja", label: "Venta" },
  MANTENER: { tono: "aviso", label: "Mantener" },
};

const TEXTO = {
  sube: "text-sube", baja: "text-baja", aviso: "text-aviso", info: "text-info",
  neutro: "text-tinta-3", tinta: "text-tinta",
};
const PUNTO = {
  sube: "bg-sube", baja: "bg-baja", aviso: "bg-aviso", info: "bg-info", neutro: "bg-tinta-3", tinta: "bg-tinta",
};

/** «tendencia_bajista» → «Tendencia bajista». El dato llega en clave del motor. */
function legible(regimen) {
  if (!regimen || regimen === "—") return "—";
  const t = String(regimen).replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function leer({ quote, indicators, analysis }) {
  const chg = quote.change_percent ?? quote.daily_change_percent;
  const reco = analysis?.recommendation ? (RECO[analysis.recommendation] || RECO.MANTENER) : null;
  const regime = indicators?.regime?.regime || indicators?.trend || "—";
  const regLight = indicators?.regime?.light;
  const regTono = regLight === "rojo" ? "baja" : regLight === "amarillo" ? "aviso" : regLight === "verde" ? "sube" : "neutro";
  const niveles = [
    analysis?.entry_zone?.min != null && { label: "Entrada", value: `$${fmtPrice(analysis.entry_zone.min)}`, tono: "info" },
    analysis?.stop_loss != null && { label: "Stop", value: `$${fmtPrice(analysis.stop_loss)}`, tono: "baja" },
    analysis?.take_profit_1 != null && { label: "TP1", value: `$${fmtPrice(analysis.take_profit_1)}`, tono: "sube" },
  ].filter(Boolean);
  const s10 = indicators?.salida_10w;
  return { chg, reco, regime, regTono, niveles, s10 };
}

function Fila({ etiqueta, children }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="text-[13px] text-tinta-3">{etiqueta}</dt>
      <dd className="text-[13px] font-medium text-right min-w-0">{children}</dd>
    </div>
  );
}

function ConPunto({ tono, children }) {
  return (
    <span className={`inline-flex items-center gap-2 ${TEXTO[tono]}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${PUNTO[tono]}`} aria-hidden="true" />
      {children}
    </span>
  );
}

function Panel({ symbol, quote, indicators, analysis, className = "" }) {
  const { reco, regime, regTono, niveles, s10 } = leer({ quote, indicators, analysis });
  return (
    <section className={`iv-panel p-5 ${className}`} aria-label={`Lectura rápida de ${symbol}`}>
      <CabeceraBloque icono={Gauge} como="h3">Lectura rápida</CabeceraBloque>
      <dl className="mt-2 divide-y divide-suave">
        <Fila etiqueta="Régimen"><ConPunto tono={regTono}><span className="text-tinta">{legible(regime)}</span></ConPunto></Fila>
        <Fila etiqueta="Señal IA">
          {reco
            ? <ConPunto tono={reco.tono}>{reco.label}</ConPunto>
            : <span className="text-tinta-3 font-normal">Sin análisis</span>}
        </Fila>
        {s10 && (
          <Fila etiqueta="Media 10 semanas">
            <ConPunto tono={s10.por_encima ? "sube" : "baja"}>{s10.por_encima ? "Mantener" : "Salida"}</ConPunto>
          </Fila>
        )}
      </dl>
      {niveles.length > 0 && (
        <dl className="mt-3 grid grid-cols-3 gap-2">
          {niveles.map((n) => (
            <div key={n.label} className="rounded-iv bg-tinta/[0.04] px-3 py-2.5 min-w-0">
              <dt className="iv-etiqueta">{n.label}</dt>
              <dd className={`iv-cifra text-[13px] font-medium mt-1 truncate ${TEXTO[n.tono]}`}>{n.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

export default function BottomSignalBar({ symbol, quote, indicators, analysis, como = "barra", className = "" }) {
  if (!quote) return null;
  if (como === "panel") {
    return <Panel symbol={symbol} quote={quote} indicators={indicators} analysis={analysis} className={className} />;
  }

  const { chg, reco, regime, regTono, niveles, s10 } = leer({ quote, indicators, analysis });
  const item = "flex flex-col leading-tight shrink-0 gap-1";
  return (
    <div className={`lg:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-suave ${className}`}
      role="region" aria-label={`Resumen de ${symbol}`}
      style={{
        paddingBottom: "env(safe-area-inset-bottom)",
        background: "var(--vidrio, rgb(var(--iv-fondo) / 0.85))",
        backdropFilter: "blur(16px) saturate(1.4)",
        WebkitBackdropFilter: "blur(16px) saturate(1.4)",
      }}>
      <div className="flex items-center gap-5 px-4 h-16 overflow-x-auto no-scrollbar">
        <div className={item}>
          <span className="text-[13px] font-semibold text-tinta tracking-[-0.01em]">{symbol}</span>
          {/* El % con el mismo formato que la cabecera (dos decimales). */}
          <span className={`iv-cifra text-[12px] whitespace-nowrap ${chg == null ? "text-tinta-3" : chg >= 0 ? "text-sube" : "text-baja"}`}>
            ${fmtPrice(quote.price)} {chg != null ? fmtPct(chg) : ""}
          </span>
        </div>
        <div className="w-px h-8 bg-tinta/10 shrink-0" aria-hidden="true" />
        <div className={item}>
          <span className="iv-etiqueta">Régimen</span>
          <span className="text-[12px] font-medium whitespace-nowrap"><ConPunto tono={regTono}><span className="text-tinta">{legible(regime)}</span></ConPunto></span>
        </div>
        <div className={item}>
          <span className="iv-etiqueta">Señal IA</span>
          <span className="text-[12px] font-medium whitespace-nowrap">
            {reco ? <ConPunto tono={reco.tono}>{reco.label}</ConPunto> : <span className="text-tinta-3">sin análisis</span>}
          </span>
        </div>
        {niveles.map((n) => (
          <div key={n.label} className={item}>
            <span className="iv-etiqueta">{n.label}</span>
            <span className={`iv-cifra text-[12px] font-medium whitespace-nowrap ${TEXTO[n.tono]}`}>{n.value}</span>
          </div>
        ))}
        {s10 && (
          <div className={item}>
            <span className="iv-etiqueta">10 sem</span>
            <span className="text-[12px] font-medium whitespace-nowrap">
              <ConPunto tono={s10.por_encima ? "sube" : "baja"}>{s10.por_encima ? "Mantener" : "Salida"}</ConPunto>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
