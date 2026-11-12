import React from "react";
import {
  ChevronRight, ArrowUpRight, RefreshCw, ScanLine, Filter, Flame, Star, TriangleAlert,
  TrendingUp, TrendingDown, Activity, Clock, Compass, Megaphone,
} from "lucide-react";
import { api } from "../lib/api";
import Score from "../components/Score";
import { fmtPrice, fmtPct, fmtNum, SIN_DATO } from "../lib/format";
import { Cargando } from "../components/base/Estado";
import Boton from "../components/base/Boton";
import Chip from "../components/base/Chip";
import Monograma from "../components/base/Monograma";
import Medidor from "../components/base/Medidor";
import Segmentado from "../components/base/Segmentado";
import CabeceraBloque from "../components/base/CabeceraBloque";
import Pestanas, { propsPanel } from "../components/base/Pestanas";
import MiniChart from "../components/MiniChart";
import RadarView from "./RadarView";
import { useSearchParams } from "react-router-dom";

/* Oportunidades · v2 («Grafito e índigo»)
   ─────────────────────────────────────────────────────────────────────────────
   Antes: un titular de cartel por modo, una fila de chips y una tabla de cuatro
   columnas donde cada fila era un bloque de doce líneas de texto en mono.

   Ahora la pantalla se lee como un producto financiero:
     1. Titular de página fijo y las cuatro vistas como `Pestanas` (con recuento).
     2. Una pieza héroe por vista: CUÁNTO ha salido (cifra grande) y, al lado, CÓMO se
        reparte. En Señales ese reparto es a la vez el filtro: cada tipo de señal es una
        fila con su barra proporcional, se pulsa y la lista de abajo cambia.
     3. La lista es una tabla de verdad en escritorio ancho: identidad + lectura a la
        izquierda, y a la derecha columnas numéricas con su medidor (score, RSI con sus
        zonas 30/70, la horquilla soporte–resistencia con el precio dentro), analistas
        y precio con la variación en píldora. Por debajo de 1280 px, la misma fila se
        convierte en ficha: la franja numérica pasa a una banda de luz de 2–4 celdas.

   Nada de esto cambia datos ni cálculos: los umbrales de color que había (consenso,
   distancia al máximo, potencial) siguen siendo los mismos. */

/* Categorías: paleta categórica fría. Verde/rojo quedan para la variación del precio;
   el índigo, para la intención (selección, foco). */
const CATEGORY_META = {
  OVERSOLD: { label: "Sobrevendidas (RSI<30)", icon: TrendingDown, color: "var(--iv-info)", desc: "RSI muy bajo, posible rebote técnico" },
  DIP: { label: "Caídas Fuertes (Compra el dip)", icon: TrendingDown, color: "var(--iv-alerta)", desc: "Cayendo hoy, oportunidad si fundamentales son sólidos" },
  VALUE: { label: "Cerca de Mínimos 52sem", icon: Compass, color: "var(--iv-aviso)", desc: "Cerca de mínimos anuales, valor potencial" },
  MOMENTUM: { label: "Momentum Alcista", icon: TrendingUp, color: "var(--iv-acento-2)", desc: "Tendencia alcista sana en marcha" },
  BREAKOUT: { label: "Breakout / Máximos 52sem", icon: ArrowUpRight, color: "var(--iv-intencion)", desc: "Rompiendo máximos, fuerza relativa alta" },
  GENERAL: { label: "Señales Mixtas", icon: Activity, color: "var(--iv-tinta-3)", desc: "Combinación de señales positivas" },
};

/** Precio en dólares, o la raya sola si no hay dato. Antes salía «$—». */
const usd = (v) => {
  const p = fmtPrice(v);
  return p === SIN_DATO ? p : `$${p}`;
};

const TRANSICION = "transition-colors duration-150 ease-salida motion-reduce:transition-none";

/** Ancho de lienzo para la tabla: por debajo de `xl` la fila se vuelve ficha. */
const COLUMNAS = "xl:grid-cols-[minmax(0,1fr)_4.5rem_6.5rem_10.5rem_8rem_7.5rem]";

/** Entrada escalonada sutil: solo las diez primeras filas, 30 ms entre una y otra. */
const escalon = (i) => (i < 10 ? { animationDelay: `${i * 30}ms` } : undefined);

/* ═════════════════════════════════ piezas ═════════════════════════════════ */

/** La cifra grande de cada vista. Geist tabular, 44–60 px; la unidad, al lado y baja. */
function CifraHeroe({ valor, unidad, testId }) {
  return (
    <p className="flex items-baseline gap-3 mt-4 min-w-0" data-testid={testId}>
      <span className="iv-cifra-hero text-[44px] sm:text-[60px] leading-none">{valor ?? SIN_DATO}</span>
      {unidad && <span className="text-[15px] sm:text-[17px] text-tinta-2 font-medium tracking-[-0.01em]">{unidad}</span>}
    </p>
  );
}

/** Línea de metadatos bajo la cifra: hora, recuento y el aviso de «actualizando». */
function Meta({ cuando, children, actualizando }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 mt-5 text-[12.5px] text-tinta-3">
      {cuando && (
        <span className="inline-flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" />
          <span className="iv-cifra">{cuando}</span>
        </span>
      )}
      {children}
      {actualizando && (
        <Chip tono="aviso">
          <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-current animate-pulse motion-reduce:animate-none" />
          actualizando datos…
        </Chip>
      )}
    </div>
  );
}

function Refrescar({ ocupado, onClick, texto, textoOcupado, testId }) {
  return (
    <Boton variante="secundario" tamano="sm" onClick={onClick} disabled={ocupado} data-testid={testId}
           className="h-9 sm:h-8">
      <RefreshCw className={`w-3.5 h-3.5 ${ocupado ? "animate-spin motion-reduce:animate-none" : ""}`}
                 strokeWidth={2} aria-hidden="true" />
      {ocupado ? textoOcupado : texto}
    </Boton>
  );
}

/** Panel de espera o de vacío, con la forma de una lista para que no haya salto. */
function Espera({ children, cargando = false, testId }) {
  return (
    <div className="iv-panel px-5 sm:px-7 py-8 sm:py-10" data-testid={testId}>
      <p className="text-[14.5px] text-tinta-2 max-w-[60ch]">{children}</p>
      {cargando && (
        <div className="mt-6 space-y-5" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-4">
              <span className="w-10 h-10 rounded-[11px] iv-esqueleto shrink-0" />
              <Cargando filas={2} alto="h-3" className="flex-1 max-w-lg" etiqueta="Cargando…" />
              <span className="hidden sm:block w-20 h-4 rounded-md iv-esqueleto" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Celda numérica: en ficha lleva su rótulo encima; en tabla, la cabecera lo dice. */
function Celda({ etiqueta, children, className = "" }) {
  return (
    <div className={`min-w-0 ${className}`}>
      <p className="iv-etiqueta xl:hidden">{etiqueta}</p>
      <div className="mt-1 xl:mt-0">{children}</div>
    </div>
  );
}

function Variacion({ pct }) {
  if (pct == null) return <span className="iv-cifra text-[12px] text-tinta-3">{SIN_DATO}</span>;
  const sube = pct >= 0;
  return (
    <Chip tono={sube ? "sube" : "baja"} className="iv-cifra">
      {sube ? <TrendingUp className="w-3 h-3" strokeWidth={2} aria-hidden="true" />
            : <TrendingDown className="w-3 h-3" strokeWidth={2} aria-hidden="true" />}
      {fmtPct(pct)}
    </Chip>
  );
}

/* ═══════════════════════════════ Señales ═══════════════════════════════ */

function OpportunityCard({ op, onPick, indice }) {
  const meta = CATEGORY_META[op.category] || CATEGORY_META.GENERAL;
  const tonoConsenso = (op.consensus_score ?? 0) >= 80
    ? "text-sube"
    : (op.consensus_score ?? 0) >= 65
    ? "text-aviso"
    : "text-tinta-2";
  const precio = (
    <>
      <p className="iv-cifra text-[15px] font-semibold text-tinta whitespace-nowrap leading-tight">${fmtPrice(op.price)}</p>
      <div className="mt-1.5"><Variacion pct={op.change_percent} /></div>
    </>
  );
  return (
    <li className="iv-entra" style={escalon(indice)}>
      <button
        type="button"
        data-testid={`opportunity-${op.symbol}`}
        onClick={() => onPick(op.symbol)}
        className={`group relative w-full text-left block xl:grid ${COLUMNAS} xl:items-center xl:gap-x-5
                    px-4 sm:px-6 py-5 xl:py-4 hover:bg-tinta/[0.035] focus-visible:bg-tinta/[0.035]
                    focus-visible:outline-offset-[-2px] ${TRANSICION}`}
      >
        {/* Identidad y lectura */}
        <div className="flex items-start gap-3.5 min-w-0">
          <Monograma symbol={op.symbol} />
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className={`text-[15px] font-semibold tracking-[-0.01em] text-tinta group-hover:text-marca ${TRANSICION}`}>
                    {op.symbol}
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[12px] text-tinta-3">
                    <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: `rgb(${meta.color})` }} />
                    {meta.label}
                  </span>
                </div>
                {/* El escáner a veces manda el ticker como nombre: no se repite. */}
                {op.name && op.name !== op.symbol && (
                  <p className="text-[12.5px] text-tinta-3 truncate mt-0.5">{op.name}</p>
                )}
              </div>
              <div className="text-right shrink-0 xl:hidden">{precio}</div>
            </div>
            {op.reason && (
              <p className="text-[13.5px] text-tinta-2 leading-snug mt-2.5">{op.reason}</p>
            )}
            {op.signals.length > 0 && (
              <ul className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5">
                {op.signals.slice(0, 3).map((s, i) => (
                  <li key={i} className="inline-flex items-center gap-1.5 text-[12.5px] text-tinta-3 leading-snug">
                    <span aria-hidden="true" className="w-1 h-1 rounded-full bg-tinta-3/70 shrink-0" />
                    {s}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Lectura numérica: banda de luz en ficha, columnas en tabla (`xl:contents`). */}
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-3.5 mt-4 ml-0 sm:ml-[54px] px-3.5 py-3 rounded-xl
                       bg-tinta/[0.035] xl:contents">
          <Celda etiqueta="Score">
            <p className="iv-cifra text-[14.5px] font-medium text-tinta">{op.score}</p>
            <Medidor valor={op.score} relleno className="mt-2 max-w-[72px]" etiqueta={`Score ${op.score} de 100`} />
          </Celda>
          <Celda etiqueta="RSI">
            <p className="iv-cifra text-[14.5px] font-medium text-tinta">{op.rsi ?? "—"}</p>
            <Medidor valor={op.rsi} className="mt-2 max-w-[96px]" etiqueta={`RSI ${op.rsi}`}
                     zonas={[{ desde: 0, hasta: 30, tono: "info" }, { desde: 70, hasta: 100, tono: "aviso" }]} />
          </Celda>
          <Celda etiqueta="Soporte · Resistencia">
            <p className="iv-cifra text-[13px] text-tinta whitespace-nowrap">
              <span title="Soporte">{usd(op.nearest_support)}</span>
              <span className="text-tinta-3"> – </span>
              <span title="Resistencia">{usd(op.nearest_resistance)}</span>
            </p>
            <Medidor min={op.nearest_support} max={op.nearest_resistance} valor={op.price} className="mt-2 max-w-[150px]"
                     etiqueta={`Precio entre soporte ${usd(op.nearest_support)} y resistencia ${usd(op.nearest_resistance)}`} />
          </Celda>
          <Celda etiqueta="Analistas">
            {op.analyst_consensus ? (
              <>
                <p className={`text-[13px] font-semibold lowercase first-letter:uppercase ${tonoConsenso}`}>{op.analyst_consensus}</p>
                {op.analysts_count ? <p className="iv-cifra text-[12px] text-tinta-3 mt-0.5">{op.analysts_count} analistas</p> : null}
              </>
            ) : (
              <p className="text-[13px] text-tinta-3">—</p>
            )}
          </Celda>
        </dl>

        <div className="hidden xl:flex items-center justify-end gap-3">
          <div className="text-right">{precio}</div>
          <ChevronRight className="w-4 h-4 text-tinta-3 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0
                                   transition-[opacity,transform] duration-150 ease-salida motion-reduce:transition-none"
                        strokeWidth={2} aria-hidden="true" />
        </div>
        <span className="sr-only">Categoría: {meta.label}. Analizar.</span>
      </button>
    </li>
  );
}

/** Cada tipo de señal como fila pulsable con barra proporcional: el reparto ES el filtro. */
function FilaFiltro({ activo, onClick, color, etiqueta, cuenta, max, testId }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={activo} data-testid={testId}
            className={`group relative w-full grid grid-cols-[minmax(0,1fr)_3rem_2rem] sm:grid-cols-[minmax(0,1fr)_6rem_2rem] items-center gap-3 h-11 sm:h-10 pl-3.5 pr-3 rounded-[10px] text-left
                        ${TRANSICION} ${activo ? "bg-tinta/[0.07] text-tinta" : "text-tinta-2 hover:bg-tinta/[0.04] hover:text-tinta"}`}>
      {activo && <span aria-hidden="true" className="absolute left-0 top-2 bottom-2 w-[2px] rounded-full bg-marca" />}
      <span className="flex items-center gap-2.5 min-w-0 text-[13.5px] font-medium">
        <span aria-hidden="true" className="w-2 h-2 rounded-[3px] shrink-0" style={{ background: color ? `rgb(${color})` : "rgb(var(--iv-tinta))" }} />
        <span className="truncate">{etiqueta}</span>
      </span>
      <div aria-hidden="true" className="h-1.5 rounded-full bg-tinta/[0.08] overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${max ? (cuenta / max) * 100 : 0}%`, background: color ? `rgb(${color})` : "rgb(var(--iv-tinta-2))" }} />
      </div>
      <span className="iv-cifra text-[13px] text-right text-tinta">{cuenta}</span>
    </button>
  );
}

/* ═══════════════════════════════ Screener ═══════════════════════════════ */

function Linea({ etiqueta, children, title }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 border-b border-suave last:border-0" title={title}>
      <dt className="text-[12.5px] text-tinta-3 shrink-0">{etiqueta}</dt>
      <dd className="iv-cifra text-[12.5px] text-right min-w-0">{children}</dd>
    </div>
  );
}

function ScreenerCard({ row, onPick, top, indice }) {
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
      style={escalon(indice)}
      className={`group relative flex flex-col p-5 cursor-pointer min-w-0 iv-entra transition-[border-color,box-shadow] duration-150 ease-salida motion-reduce:transition-none ${
        top ? "iv-destacada" : "iv-panel hover:border-medio"
      }`}
      onClick={() => onPick(row.symbol)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <Monograma symbol={row.symbol} tono={top ? "marca" : "neutro"} />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className={`text-[15px] font-semibold tracking-[-0.01em] text-tinta group-hover:text-marca ${TRANSICION}`}>{row.symbol}</p>
              {top && (
                <Chip tono="marca">
                  <Star className="w-3 h-3" fill="currentColor" strokeWidth={0} aria-hidden="true" />
                  Top selección
                </Chip>
              )}
            </div>
            <p className="text-[12.5px] text-tinta-3 truncate">{row.name}</p>
          </div>
        </div>
        {ps != null && (
          /* El chip es el mismo de siempre; `Score` solo lo hace desplegable. Cerrado se
             ve igual y no pide nada: la peticion ocurre en el primer clic. */
          <Score symbol={row.symbol}>
            <span
              className="inline-flex items-center h-6 px-2 rounded-md text-[12px] font-mono font-semibold tabular-nums"
              style={{ background: `rgb(${psColor} / 0.09)`, color: `rgb(${psColor})`, border: `1px solid rgb(${psColor} / 0.25)` }}
              title="Potencial a medio plazo: crecimiento + valoración + punto de entrada"
            >
              {ps} pts
            </span>
          </Score>
        )}
      </div>

      {row.fuentes && (
        <span className="self-start inline-flex items-center gap-1.5 mt-3 h-[22px] px-2 rounded-md text-[12px] font-medium bg-info/10 text-info"
          title={`Mencionada por tus fuentes: ${(row.fuentes.fuentes || []).join(", ")}`}>
          <Megaphone className="w-3 h-3" strokeWidth={2} aria-hidden="true" />
          Tus fuentes ({row.fuentes.menciones})
          {row.fuentes.positivos > 0 && ` · ${row.fuentes.positivos} a favor`}
          {row.fuentes.negativos > 0 && ` · ${row.fuentes.negativos} en contra`}
        </span>
      )}

      {/* Precio como protagonista de la tarjeta, con la distancia al máximo al lado. */}
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-1 mt-4">
        <p className="iv-cifra-hero text-[30px] leading-none whitespace-nowrap">
          <span className="text-tinta-3 text-[18px] align-top mr-0.5">$</span>{fmtPrice(row.price)}
        </p>
        <span
          className="iv-cifra text-[12px] font-medium whitespace-nowrap"
          style={{ color: `rgb(${distColor})` }}
          title="Distancia al máximo de 52 semanas"
        >
          {dist != null ? `${dist}% máx.` : "—"}
        </span>
      </div>

      {(row.valuation || (row.momentum && row.momentum !== "neutra") || row.analyst_consensus) && (
        <dl className="mt-4">
          {row.valuation && (
            <Linea etiqueta="Valoración">
              <span style={{ color: `rgb(${psColor})` }}>{row.valuation}{row.pe_ratio ? ` · PER ${row.pe_ratio}` : ""}</span>
            </Linea>
          )}
          {row.momentum && row.momentum !== "neutra" && (
            <Linea etiqueta="Tendencia">
              <span style={{ color: row.momentum.startsWith("⚠") ? "rgb(var(--iv-baja))" : "rgb(var(--iv-sube))" }}>
                {row.momentum}{row.return_52w != null ? ` · ${row.return_52w > 0 ? "+" : ""}${row.return_52w}% 1a` : ""}
              </span>
            </Linea>
          )}
          {row.analyst_consensus && (
            <Linea etiqueta="Analistas">
              <span className="text-tinta font-semibold">{row.analyst_consensus}</span>
              <span className="text-tinta-3">{row.consensus_score != null ? ` (${row.consensus_score})` : ""}</span>
            </Linea>
          )}
        </dl>
      )}
      {row.reason && (
        <p className="text-[13px] text-tinta-2 mt-3 leading-snug">{row.reason}</p>
      )}
      {row.earnings_days != null && (
        <p className="flex items-start gap-2 text-[12.5px] mt-3 text-baja bg-baja/[0.08] border border-baja/20 rounded-lg px-2.5 py-2">
          <TriangleAlert className="w-3.5 h-3.5 shrink-0 mt-px" strokeWidth={2} aria-hidden="true" />
          <span>Resultados {row.earnings_days === 0 ? "HOY" : row.earnings_days === 1 ? "mañana" : `en ${row.earnings_days} días`} — riesgo binario</span>
        </p>
      )}

      {/* Crecimiento y volumen: banda de luz con tres celdas. */}
      <dl className="grid grid-cols-3 gap-2 mt-4 px-3 py-2.5 rounded-xl bg-tinta/[0.035]">
        <div className="min-w-0">
          <dt className="iv-etiqueta truncate">Ventas YoY</dt>
          <dd className={`iv-cifra text-[13px] font-medium mt-0.5 ${tonoCrec(row.revenue_growth)}`}>{row.revenue_growth != null ? `+${row.revenue_growth}%` : "—"}</dd>
        </div>
        <div className="min-w-0">
          <dt className="iv-etiqueta truncate">EPS YoY</dt>
          <dd className={`iv-cifra text-[13px] font-medium mt-0.5 ${tonoCrec(row.eps_growth)}`}>{row.eps_growth != null ? `${row.eps_growth > 0 ? "+" : ""}${row.eps_growth}%` : "—"}</dd>
        </div>
        <div className="min-w-0">
          <dt className="iv-etiqueta truncate">Vol. medio</dt>
          <dd className="iv-cifra text-[13px] font-medium mt-0.5 text-tinta">{fmtNum(row.avg_volume)}</dd>
        </div>
      </dl>

      <MiniChart symbol={row.symbol} />

      <div className="flex items-center justify-between gap-3 mt-auto pt-3">
        <span className="text-[12.5px] text-tinta-3 truncate min-w-0">{row.sector || "—"}</span>
        <span className={`inline-flex items-center gap-1 text-[12.5px] font-medium text-tinta-3 group-hover:text-marca ${TRANSICION}`}>
          Analizar
          <ChevronRight className="w-3.5 h-3.5 transition-transform duration-150 ease-salida [@media(hover:hover)]:group-hover:translate-x-0.5 motion-reduce:transition-none"
                        strokeWidth={2} aria-hidden="true" />
        </span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════ Movers ═══════════════════════════════ */

function MoversColumn({ title, icon: Icon, rows, color, porSigno = false, onPick, className = "" }) {
  const lista = rows || [];
  const maxPct = Math.max(1, ...lista.map((r) => Math.abs(r.change_percent ?? 0)));
  return (
    <section className={`iv-panel overflow-hidden min-w-0 ${className}`} aria-label={title}>
      <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-3">
        <h3 className="flex items-center gap-2 text-[14px] font-semibold tracking-[-0.01em] text-tinta">
          <span className="grid place-items-center w-7 h-7 rounded-lg" style={{ background: `rgb(${color} / 0.12)`, color: `rgb(${color})` }}>
            <Icon className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" />
          </span>
          {title}
        </h3>
        <span className="iv-cifra text-[12px] text-tinta-3">{lista.length}</span>
      </div>
      <div className="max-h-[600px] overflow-y-auto pb-2">
        {lista.length === 0 && <p className="text-[13px] text-tinta-3 py-6 text-center">—</p>}
        {lista.map((r, i) => {
          const pct = r.change_percent;
          const tono = porSigno && pct != null
            ? (pct >= 0 ? "var(--iv-sube)" : "var(--iv-baja)")
            : color;
          return (
            <button
              type="button"
              key={r.symbol}
              onClick={() => onPick(r.symbol)}
              className={`group w-full text-left grid grid-cols-[1.25rem_auto_minmax(0,1fr)_auto] items-center gap-3 px-5 py-2.5 min-h-[52px]
                          hover:bg-tinta/[0.035] focus-visible:bg-tinta/[0.035] focus-visible:outline-offset-[-2px] ${TRANSICION}`}
            >
              <span className="iv-cifra text-[11.5px] text-tinta-3 text-right">{i + 1}</span>
              <Monograma symbol={r.symbol} tamano="sm" />
              <div className="min-w-0">
                <p className={`text-[13.5px] font-semibold text-tinta group-hover:text-marca ${TRANSICION}`}>{r.symbol}</p>
                <p className="text-[12px] text-tinta-3 truncate">{r.name}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="iv-cifra text-[13px] text-tinta whitespace-nowrap">${fmtPrice(r.price)}</p>
                <div className="flex items-center justify-end gap-2 mt-0.5">
                  <span aria-hidden="true" className="hidden sm:block w-10 h-1 rounded-full bg-tinta/[0.07] overflow-hidden">
                    <span className="block h-full rounded-full ml-auto" style={{ width: `${pct != null ? (Math.abs(pct) / maxPct) * 100 : 0}%`, background: `rgb(${tono} / 0.75)` }} />
                  </span>
                  <span className="iv-cifra text-[12px] font-medium" style={{ color: `rgb(${tono})` }}>
                    {pct != null ? `${pct >= 0 ? "+" : ""}${Number(pct).toFixed(2)}%` : "—"}
                  </span>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/* ═══════════════════════════════ pantalla ═══════════════════════════════ */

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
  // Solo presentación: en móvil se ve una columna de movers a la vez.
  const [columnaMovil, setColumnaMovil] = React.useState("gainers");

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

  const categorias = data
    ? Object.entries(CATEGORY_META).filter(([key]) => (data.by_category?.[key]?.length || 0) > 0)
    : [];
  const maxCategoria = Math.max(data?.top?.length || 0, ...categorias.map(([k]) => data.by_category[k].length));
  const screenerListo = screener && screener.status !== "warming";

  return (
    <div data-testid="opportunities-view" className="space-y-6 sm:space-y-8">
      {/* ── Titular de página ─────────────────────────────────────────────── */}
      <header className="min-w-0">
        <p className="text-[13px] text-tinta-3 flex items-center gap-1.5">
          Decidir <ChevronRight className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" /> Oportunidades
        </p>
        <h1 className="iv-verbo text-tinta mt-2">Oportunidades</h1>
        <p className="text-[14.5px] text-tinta-2 mt-2.5 max-w-[60ch] leading-relaxed">
          Lo que el mercado ofrece hoy: señales técnicas, crecimiento con buen punto de entrada y lo que más se mueve.
        </p>
      </header>

      <div className="-mx-4 px-4 sm:mx-0 sm:px-0">
        <Pestanas
          id="oportunidades"
          etiqueta="Modos de Oportunidades"
          valor={mode}
          onCambio={setMode}
          pestanas={[
            { valor: "signals", etiqueta: "Señales del día", cuenta: data && data.status !== "warming" ? data.opportunities_found : null },
            { valor: "screener", etiqueta: "Screener de crecimiento", cuenta: screenerListo ? screener.matches : null },
            { valor: "movers", etiqueta: "Movers del mercado" },
            { valor: "fuentes", etiqueta: "Tus fuentes" },
          ]}
        />
      </div>

      <div {...propsPanel("oportunidades", mode)} className="space-y-6 sm:space-y-8 min-w-0">
        {/* ============ TUS FUENTES (antes /radar) ============ */}
        {mode === "fuentes" && <RadarView setSymbol={setSymbol} />}

        {/* ============ SIGNALS MODE ============ */}
        {mode === "signals" && (
          <>
            <section className="iv-panel relative overflow-hidden" aria-labelledby="op-escaneo">
              <span aria-hidden="true"
                    className="pointer-events-none absolute -top-40 -left-32 w-[560px] h-[320px] rounded-full bg-marca/[0.08] blur-3xl" />
              <div className="relative grid lg:grid-cols-[minmax(0,1fr)_400px]">
                <div className="p-5 sm:p-7 min-w-0">
                  <CabeceraBloque icono={ScanLine} como="h2" id="op-escaneo"
                                  derecha={<Refrescar ocupado={loading} onClick={() => load(true)} testId="refresh-opportunities"
                                                      texto="Refrescar" textoOcupado="Escaneando..." />}>
                    Oportunidades del día
                  </CabeceraBloque>
                  <CifraHeroe valor={data?.status === "warming" ? SIN_DATO : data?.opportunities_found}
                              unidad={`oportunidades · de ${data?.universe_size || 30} acciones`} />
                  <p className="text-[14px] text-tinta-2 mt-3 max-w-[52ch]">
                    Escaneo de {data?.universe_size || 30} acciones · Detecta sobrecompras, caídas fuertes, momentum y breakouts.
                  </p>
                  {data?.generated_at && (
                    <Meta cuando={`Último escaneo: ${new Date(data.generated_at).toLocaleString("es-ES")}`}
                          actualizando={isStale(data)}>
                      <span className="sr-only">{data.opportunities_found} oportunidades detectadas</span>
                    </Meta>
                  )}
                </div>

                {/* Reparto por tipo de señal = filtro de la lista */}
                <div className="p-4 sm:p-5 border-t lg:border-t-0 lg:border-l border-suave min-w-0 bg-tinta/[0.015]">
                  <p className="text-[13px] font-medium text-tinta-2 px-1.5 mb-2">Por tipo de señal</p>
                  {data && data.status !== "warming" ? (
                    <div className="space-y-0.5" data-testid="category-filter" role="group" aria-label="Filtrar por tipo de señal">
                      <FilaFiltro activo={filter === "ALL"} onClick={() => setFilter("ALL")}
                                  etiqueta="Top 15" cuenta={data.top?.length || 0} max={maxCategoria} />
                      {categorias.map(([key, meta]) => (
                        <FilaFiltro key={key} testId={`filter-${key}`} activo={filter === key} onClick={() => setFilter(key)}
                                    color={meta.color} etiqueta={meta.label}
                                    cuenta={data.by_category[key].length} max={maxCategoria} />
                      ))}
                    </div>
                  ) : (
                    <Cargando filas={4} alto="h-8" className="px-1.5" />
                  )}
                </div>
              </div>
            </section>

            {loading && !data && (
              <Espera cargando>Escaneando el mercado... Esto puede tardar 10-20 segundos.</Espera>
            )}

            {data?.status === "warming" && (
              <Espera cargando testId="opportunities-warming">
                Calentando el escáner... Se actualizará automáticamente en unos segundos.
              </Espera>
            )}

            {data && data.status !== "warming" && (
              <section aria-labelledby="op-lista" className="space-y-4">
                <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-1">
                  <div className="min-w-0">
                    <h2 id="op-lista" className="text-[18px] font-semibold tracking-[-0.02em] text-tinta">
                      {filter === "ALL" ? "Top 15" : CATEGORY_META[filter]?.label}
                    </h2>
                    <p className="text-[13px] text-tinta-3 mt-0.5">
                      {filter !== "ALL" && CATEGORY_META[filter]
                        ? CATEGORY_META[filter].desc
                        : "Las mejores por score, de todas las categorías"}
                    </p>
                  </div>
                  <p className="iv-cifra text-[12.5px] text-tinta-3">{filtered.length} valores</p>
                </div>

                {filtered.length > 0 ? (
                  <div className="iv-panel">
                    {/* Cabecera de columnas, solo en tabla; fija bajo la barra superior. */}
                    <div aria-hidden="true"
                         className={`hidden xl:grid ${COLUMNAS} gap-x-5 px-6 h-10 items-center sticky top-14 z-10 rounded-t-[inherit]
                                     border-b border-suave bg-superficie/90 backdrop-blur text-[12px] text-tinta-3`}>
                      <span>Valor y lectura</span>
                      <span>Score</span>
                      <span>RSI</span>
                      <span>Soporte · Resistencia</span>
                      <span>Analistas</span>
                      <span className="text-right pr-7">Precio</span>
                    </div>
                    <ol className="divide-y divide-[color:var(--borde-suave)]">
                      {filtered.map((op, i) => (
                        <OpportunityCard key={op.symbol} op={op} onPick={handlePick} indice={i} />
                      ))}
                    </ol>
                  </div>
                ) : (
                  <Espera>Sin oportunidades en esta categoría hoy.</Espera>
                )}
              </section>
            )}
          </>
        )}

        {/* ============ SCREENER MODE ============ */}
        {mode === "screener" && (
          <>
            <section className="iv-panel relative overflow-hidden" aria-labelledby="op-screener">
              <span aria-hidden="true"
                    className="pointer-events-none absolute -top-40 -left-32 w-[560px] h-[320px] rounded-full bg-marca/[0.08] blur-3xl" />
              <div className="relative grid lg:grid-cols-[minmax(0,1fr)_420px]">
                <div className="p-5 sm:p-7 min-w-0">
                  <CabeceraBloque icono={Filter} como="h2" id="op-screener"
                                  derecha={<Refrescar ocupado={screenerLoading} onClick={() => loadScreener(true)}
                                                      texto="Refrescar" textoOcupado="Filtrando..." />}>
                    Screener de crecimiento
                  </CabeceraBloque>
                  <CifraHeroe valor={screenerListo ? screener.matches : SIN_DATO}
                              unidad={`resultados · de ${screener?.universe_size || 120} acciones`} />
                  <p className="text-[14px] text-tinta-2 mt-3 max-w-[56ch]">
                    {screener?.universe_size || 120} acciones del mercado, ordenadas por <span className="font-semibold text-marca">potencial</span> (crecimiento + valoración + punto de entrada).
                  </p>
                  {screener?.generated_at && screener.status !== "warming" && (
                    <Meta cuando={`Último filtrado: ${new Date(screener.generated_at).toLocaleString("es-ES")}`}
                          actualizando={isStale(screener)}>
                      <span className="sr-only">{screener.matches} resultados</span>
                    </Meta>
                  )}
                </div>

                <div className="p-5 sm:p-6 border-t lg:border-t-0 lg:border-l border-suave min-w-0 space-y-5 bg-tinta/[0.015]">
                  {/* Semáforo de mercado */}
                  {screener?.market_regime && screener.market_regime.light !== "desconocido" && (() => {
                    const rg = screener.market_regime;
                    const c = { verde: "var(--iv-sube)", amarillo: "var(--iv-aviso)", rojo: "var(--iv-baja)" }[rg.light] || "var(--iv-tinta-3)";
                    return (
                      <div>
                        <p className="text-[13px] font-medium text-tinta-2">Semáforo de mercado</p>
                        <div className="flex items-start gap-3 mt-2.5">
                          <span aria-hidden="true" className="relative grid place-items-center w-8 h-8 rounded-lg shrink-0" style={{ background: `rgb(${c} / 0.12)` }}>
                            <span className="w-2.5 h-2.5 rounded-full" style={{ background: `rgb(${c})`, boxShadow: `0 0 0 4px rgb(${c} / 0.18)` }} />
                          </span>
                          <p className="text-[13px] leading-snug min-w-0">
                            <span className="block font-semibold" style={{ color: `rgb(${c})` }}>{rg.label}</span>
                            <span className="block text-tinta-2 mt-0.5">{rg.advice}</span>
                          </p>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Los criterios del filtro, en neutro: informativos, no pulsables. */}
                  {screener?.filters && (
                    <div>
                      <p className="text-[13px] font-medium text-tinta-2">Criterios del filtro</p>
                      <ul className="flex flex-wrap gap-1.5 mt-2.5" aria-label="Criterios del filtro">
                        {screener.filters.map((f, i) => (
                          <li key={i} className="iv-cifra text-[11.5px] leading-none px-2 py-1.5 rounded-md bg-tinta/[0.05] border border-suave text-tinta-2">
                            {f}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {!screener && <Cargando filas={4} alto="h-6" />}
                </div>
              </div>
            </section>

            {(!screener || screener.status === "warming") ? (
              <Espera cargando={screenerLoading || screener?.status === "warming"}>
                {screenerLoading || screener?.status === "warming"
                  ? "Aplicando los 7 filtros sobre el universo de crecimiento… La primera vez tarda ~40s y se actualiza solo."
                  : "No se pudo cargar el screener. Pulsa «Refrescar» para reintentar."}
              </Espera>
            ) : (screener.results || []).length > 0 ? (
              <>
                {((screener.top_seleccion || []).length > 0 || (screener.sectores_calientes || []).length > 0) && (
                  <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] items-stretch">
                    {(screener.top_seleccion || []).length > 0 && (
                      <section className="iv-destacada overflow-hidden" aria-labelledby="top-seleccion">
                        <div className="px-5 pt-4 pb-2">
                          <h3 id="top-seleccion" className="flex items-center gap-2 text-[14px] font-semibold text-tinta">
                            <Star className="w-4 h-4 text-marca" fill="currentColor" strokeWidth={0} aria-hidden="true" />
                            Top Selección
                          </h3>
                        </div>
                        <ol className="pb-2">
                          {screener.top_seleccion.map((t, i) => (
                            <li key={t.symbol}>
                              <button type="button" onClick={() => handlePick(t.symbol)}
                                className={`group w-full grid grid-cols-[1.25rem_auto_minmax(0,1fr)_auto] items-center gap-3 text-left px-5 py-2.5 min-h-[52px]
                                            hover:bg-tinta/[0.04] focus-visible:bg-tinta/[0.04] focus-visible:outline-offset-[-2px] ${TRANSICION}`}>
                                <span className="iv-cifra text-[11.5px] text-tinta-3 text-right">{i + 1}</span>
                                <Monograma symbol={t.symbol} tamano="sm" tono="marca" />
                                <span className="min-w-0">
                                  <span className={`block text-[13.5px] font-semibold text-tinta group-hover:text-marca ${TRANSICION}`}>{t.symbol}</span>
                                  <span className="block text-[12.5px] text-tinta-3 leading-snug">{t.motivo}</span>
                                </span>
                                <span className="shrink-0 text-right">
                                  <span className="block iv-cifra text-[13.5px] font-semibold text-sube">{t.potential_score} pts</span>
                                  <Medidor valor={t.potential_score} relleno tono="sube" className="mt-1.5 w-14 ml-auto" />
                                </span>
                              </button>
                            </li>
                          ))}
                        </ol>
                      </section>
                    )}
                    {(screener.sectores_calientes || []).length > 0 && (
                      <section className="iv-panel p-5" aria-labelledby="sectores-calientes">
                        <h3 id="sectores-calientes" className="flex items-center gap-2 text-[14px] font-semibold text-tinta">
                          <Flame className="w-4 h-4 text-alerta" strokeWidth={1.75} aria-hidden="true" />
                          El dinero va hacia:
                        </h3>
                        <ol className="mt-3 space-y-1.5">
                          {screener.sectores_calientes.slice(0, 4).map((s, i) => (
                            <li key={s.sector} className="flex items-center gap-3 h-9 px-3 rounded-lg bg-tinta/[0.035]">
                              <span className="iv-cifra text-[11.5px] text-tinta-3">{i + 1}</span>
                              <span className="text-[13.5px] font-medium text-tinta">{s.sector}</span>
                            </li>
                          ))}
                        </ol>
                        <p className="text-[12.5px] text-tinta-3 mt-3 leading-snug">Detectado en vivo (momentum + lo que dicen tus fuentes). Se actualiza solo; estos sectores pesan más en la Top Selección.</p>
                      </section>
                    )}
                  </div>
                )}
                {(screener.con_fuentes || []).length > 0 && (
                  <p className="flex items-center gap-2.5 text-[13.5px] text-tinta-2">
                    <span className="grid place-items-center w-7 h-7 rounded-lg bg-info/10 text-info shrink-0">
                      <Megaphone className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" />
                    </span>
                    <span><b className="iv-cifra text-info">{screener.con_fuentes.length}</b> de estas acciones las mencionan tus fuentes de pago — salen primero, marcadas.</span>
                  </p>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 lg:gap-5">
                  {/* Las mencionadas por tus fuentes flotan arriba (sin alterar el score). */}
                  {[...screener.results]
                    .sort((a, b) => (b.fuentes ? 1 : 0) - (a.fuentes ? 1 : 0))
                    .map((row, i) => (
                      <ScreenerCard key={row.symbol} row={row} onPick={handlePick} indice={i}
                        top={(screener.top_seleccion || []).some((t) => t.symbol === row.symbol)} />
                    ))}
                </div>
              </>
            ) : (
              <Espera>Ninguna acción del universo cumple hoy los 7 filtros. Prueba a refrescar más tarde.</Espera>
            )}
          </>
        )}

        {/* ============ MOVERS MODE ============ */}
        {mode === "movers" && (
          <>
            <section className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3" aria-labelledby="op-movers">
              <div className="min-w-0">
                <h2 id="op-movers" className="flex items-center gap-2 text-[18px] font-semibold tracking-[-0.02em] text-tinta">
                  <Flame className="w-[18px] h-[18px] text-tinta-3" strokeWidth={1.75} aria-hidden="true" />
                  Movers del mercado
                </h2>
                <p className="text-[13.5px] text-tinta-3 mt-1">Mayores subidas, bajadas y más negociadas del mercado US hoy.</p>
              </div>
              <Refrescar ocupado={moversLoading} onClick={loadMovers} texto="Refrescar" textoOcupado="Cargando..." />
            </section>

            {moversLoading && !movers ? (
              <Espera cargando>Cargando movers del mercado...</Espera>
            ) : movers && ((movers.gainers || []).length || (movers.losers || []).length || (movers.actives || []).length) ? (
              <>
                <Segmentado
                  className="lg:hidden w-full [&>button]:flex-1"
                  etiqueta="Lista de movers"
                  valor={columnaMovil}
                  onCambio={setColumnaMovil}
                  opciones={[
                    { valor: "gainers", etiqueta: "Subidas" },
                    { valor: "losers", etiqueta: "Bajadas" },
                    { valor: "actives", etiqueta: "Negociadas" },
                  ]}
                />
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <MoversColumn title="Mayores subidas" icon={TrendingUp} rows={movers.gainers} color="var(--iv-sube)" onPick={handlePick}
                                className={columnaMovil === "gainers" ? "" : "hidden lg:block"} />
                  <MoversColumn title="Mayores bajadas" icon={TrendingDown} rows={movers.losers} color="var(--iv-baja)" onPick={handlePick}
                                className={columnaMovil === "losers" ? "" : "hidden lg:block"} />
                  <MoversColumn title="Más negociadas" icon={Activity} rows={movers.actives} color="var(--iv-info)" porSigno onPick={handlePick}
                                className={columnaMovil === "actives" ? "" : "hidden lg:block"} />
                </div>
              </>
            ) : (
              <Espera>No hay datos de movers. Requiere configurar <span className="font-mono">FMP_API_KEY</span> en el servidor.</Espera>
            )}
          </>
        )}
      </div>
    </div>
  );
}
