import React, { useState, useEffect, useRef, useMemo } from "react";
import { Bell, BellSlash, Trash, Plus, X, UploadSimple, ArrowClockwise, Lightning, Camera, CurrencyEur } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { aNumero } from "../lib/format";
import RiesgoVenta from "../components/RiesgoVenta";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
const authHeaders = () => {
  const token = localStorage.getItem("inveria_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// ── sub-tabs ───────────────────────────────────────────────────────────────────
// Un solo grupo (la antigua pestaña "Cimientos" se eliminó por completo).
const GRUPOS = [
  { key: "ideas_javi", label: "Cartera", icon: Lightning },
];
const grupoOf = (e) => e.grupo || "ideas_javi"; // entradas antiguas → Cartera

// ── helpers ──────────────────────────────────────────────────────────────────
const fmtP = (v) => (v != null && v !== "" ? `$${Number(v).toFixed(2)}` : "—");
const fmtPct = (v) => (v != null ? `${Number(v).toFixed(2)}%` : "—");


// Pre-market / after-hours info for an entry (from the quote the worker stores)
function extendedInfo(e) {
  const s = (e.market_state || "").toUpperCase();
  if ((s === "PRE" || s === "PREPRE") && e.pre_market_price != null) {
    return { label: "PRE", price: e.pre_market_price };
  }
  if ((s === "POST" || s === "POSTPOST") && e.post_market_price != null) {
    return { label: "AH", price: e.post_market_price };
  }
  return null;
}

function ExtendedBadge({ entry }) {
  const ext = extendedInfo(entry);
  // Daily change (regular session vs previous close) — always show when available
  const dailyPct = entry.daily_change_percent;
  if (!ext && dailyPct == null) return null;
  // El % extendido lo calcula el backend contra el último cierre regular (fiable).
  // Fallback al cálculo antiguo solo si el backend aún no lo trae.
  const base = entry.last_price;
  const ahPct =
    ext && entry.extended_change_percent != null
      ? entry.extended_change_percent
      : ext && base
      ? ((ext.price - base) / base) * 100
      : null;
  const ahUp = (ahPct ?? 0) >= 0;
  const dayUp = (dailyPct ?? 0) >= 0;
  return (
    <div className="flex flex-col gap-0.5">
      {dailyPct != null && (
        <div
          className={`text-[10px] font-mono ${dayUp ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}
          title="Variación sesión regular vs cierre anterior"
        >
          {dayUp ? "+" : ""}{dailyPct.toFixed(2)}% hoy
        </div>
      )}
      {ext && (
        <div
          className={`text-[10px] font-mono ${ahUp ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}
          title={`${ext.label === "PRE" ? "Pre-market" : "After-hours"} vs cierre regular`}
        >
          {ext.label} ${Number(ext.price).toFixed(2)}{ahPct != null ? ` (${ahUp ? "+" : ""}${ahPct.toFixed(2)}%)` : ""}
        </div>
      )}
    </div>
  );
}

// ── Posición / P&L (#20) ──────────────────────────────────────────────────────
const posCost = (e) => (Number(e.acciones) > 0 && Number(e.compra) > 0) ? Number(e.acciones) * Number(e.compra) : 0;
const posValue = (e) => (Number(e.acciones) > 0 && e.last_price != null) ? Number(e.acciones) * Number(e.last_price) : 0;
const pnlAbs = (e) => (Number(e.acciones) > 0 && Number(e.compra) > 0 && e.last_price != null) ? (Number(e.last_price) - Number(e.compra)) * Number(e.acciones) : null;
const pnlPct = (e) => (Number(e.compra) > 0 && e.last_price != null) ? ((Number(e.last_price) - Number(e.compra)) / Number(e.compra)) * 100 : null;
const eur0 = (x) => x == null ? "—" : x.toLocaleString("es-ES", { maximumFractionDigits: 0 });

// Distancia % del precio a un nivel de compra (negativo = el nivel está por debajo, aún sin tocar).
const nivelDist = (e, n) => {
  const px = Number(e.last_price), lv = Number(e[`nivel${n}`]);
  if (!px || !lv) return null;
  return ((lv - px) / px) * 100;
};
// Próximo nivel de compra en tocarse al caer = el más alto que aún está por debajo del precio.
const nextNivelKey = (e) => {
  const px = Number(e.last_price);
  if (!px) return null;
  let best = null, gap = Infinity;
  for (let n = 1; n <= 5; n++) {
    const lv = Number(e[`nivel${n}`]);
    if (!lv || lv > px) continue;
    if (px - lv < gap) { gap = px - lv; best = n; }
  }
  return best;
};

// Muestra el P&L en EUROS cuando el libro de operaciones lo sabe, y en la divisa original
// si no. Los euros son la cifra que de verdad importa: es lo que entra o sale de la cuenta.
// No basta con convertir el resultado en dólares al cambio de hoy — eso da un número que no
// corresponde a ninguna operación real. El libro convierte cada compra al cambio de SU día
// y el valor de hoy al de hoy, así que el euro entra en la cuenta como lo que es.
function PnlText({ abs, pct, size = "sm", eur = null, tasa = null }) {
  // Tres situaciones, y se distinguen a la vista porque no valen lo mismo:
  //
  //  1. EXACTO — hay compras registradas: cada una convertida al cambio de SU día. Es lo
  //     que de verdad ganaste en euros.
  //  2. APROXIMADO — sin libro todavía: se convierte la ganancia en dólares al cambio de
  //     HOY. No es lo que ganaste en euros (tu coste fue a otro cambio), es lo que esa
  //     ganancia vale hoy en euros. Se marca con ≈ para no confundirlas.
  //  3. Ni una cosa ni otra: se enseñan los dólares y ya.
  //
  // Antes solo existían 1 y 3, así que hasta importar la Cartera seguía en dólares — que
  // es justo lo que se pedía cambiar.
  const hayEur = eur && eur.pnl_eur != null;
  const aprox = !hayEur && abs != null && tasa > 0;
  if (abs == null && !hayEur) return <span className="text-neutral-300">—</span>;

  const principal = hayEur ? eur.pnl_eur : aprox ? abs / tasa : abs;
  const principalPct = hayEur ? eur.pct_eur : pct;   // el % no cambia al convertir
  const up = principal >= 0;
  const color = up ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400";
  const enEuros = hayEur || aprox;
  return (
    <span className="inline-flex flex-col items-end leading-tight"
          title={aprox
            ? "Aproximado: es el valor en euros de HOY de tu ganancia en dólares. Para saber lo que has ganado de verdad en euros hace falta el tipo de cambio del día de tu compra — regístrala en Ventas."
            : hayEur
              ? "Exacto: cada compra convertida al tipo de cambio de su fecha y el valor de hoy al de hoy."
              : undefined}>
      <span className={`font-mono font-bold ${size === "sm" ? "text-sm" : "text-base"} ${color}`}>
        {aprox && <span className="opacity-60">≈ </span>}
        {up ? "+" : "−"}{Math.abs(principal).toLocaleString("es-ES", { maximumFractionDigits: 0 })}
        {enEuros ? " €" : " $"}
        {principalPct != null && (
          <span className="text-[11px] font-semibold"> · {principalPct >= 0 ? "+" : "−"}{Math.abs(principalPct).toFixed(1)}%</span>
        )}
      </span>
      {/* La divisa original, en pequeño: sirve para cuadrar con la pantalla del bróker,
          que la muestra en dólares. */}
      {enEuros && abs != null && (
        <span className="font-mono text-[10px] text-neutral-500">
          {abs >= 0 ? "+" : "−"}${eur0(Math.abs(abs))}
        </span>
      )}
    </span>
  );
}

// Mapa symbol -> {pnl_eur, pct_eur} desde el libro de operaciones. Si una acción todavía no
// tiene compras registradas, no aparece y su fila cae al cálculo en dólares de siempre: así
// estrenar el libro no deja la Cartera llena de huecos.
function usePnlEnEuros() {
  const { data } = useQuery({
    queryKey: ["cartera", "resumen"],
    queryFn: api.cartera.resumen,
    staleTime: 60_000,
    retry: false,
  });
  return React.useMemo(() => {
    const porSymbol = {};
    for (const p of data?.posiciones || []) {
      if (p.symbol) porSymbol[p.symbol.toUpperCase()] = p;
    }
    // El cambio de hoy sirve para las acciones que AÚN no tienen compras registradas: sin
    // él su P&L se quedaría en dólares, que es justo lo que se quería cambiar.
    return { porSymbol, tasaUSD: data?.tasas?.USD || null };
  }, [data]);
}

// ── Resumen de cartera: P&L total (#20) + diversificación por sector (#21) ───────
// EXCEPCIÓN ANOTADA · Paleta CATEGÓRICA, no semántica. Estos ocho colores no
// significan «sube», «baja» ni «aviso»: solo tienen que distinguirse entre sí para
// separar sectores en el gráfico. La paleta de tokens tiene tres colores con
// significado y no puede dar ocho tonos distinguibles, así que se queda literal —
// misma categoría de excepción que el morado del gráfico de precios.
//
// Que vaya en JavaScript y no en clases tiene además una consecuencia buena: el
// remapeo de oscuro no la toca, y una leyenda de sectores DEBE conservar el mismo
// color en los dos temas o deja de poder compararse entre capturas.
const SECTOR_COLORS = ["#1a3a32", "#4a7c59", "#c9a14a", "#d85c41", "#2563eb", "#7c3aed", "#0891b2", "#9333ea"];
function PortfolioSummary({ entries }) {
  // El total en euros, igual que las filas: si una cosa va en euros y la otra en dólares
  // en la misma pantalla, el número grande deja de poder compararse con la suma de abajo.
  const { tasaUSD: tasaResumen } = usePnlEnEuros();
  // Solo posiciones COMPLETAS (acciones + precio de compra + precio actual). Antes bastaba
  // con tener acciones: una recién añadida sin last_price sumaba al coste pero 0 al valor,
  // y el total anunciaba un -100% falso.
  const conPos = entries.filter((e) => Number(e.acciones) > 0 && Number(e.compra) > 0 && e.last_price != null);
  const incompletas = entries.filter((e) => Number(e.acciones) > 0 && !(Number(e.compra) > 0 && e.last_price != null)).length;
  const totalCost = conPos.reduce((s, e) => s + posCost(e), 0);
  const totalValue = conPos.reduce((s, e) => s + posValue(e), 0);
  const totalPnl = conPos.length ? totalValue - totalCost : null;
  const totalPnlPct = totalCost > 0 && totalPnl != null ? (totalPnl / totalCost) * 100 : null;
  // Aviso de DIVISAS: sumar EUR con USD y etiquetarlo todo con "$" da un total sin sentido.
  const divisas = new Set(conPos.map((e) => (e.divisa || "").toUpperCase() || (/(\.MC|\.PA|\.DE|\.MI|\.AS)$/i.test(e.symbol || "") ? "EUR" : "USD")));
  const multiDivisa = divisas.size > 1;

  // Diversificación: por valor de mercado si hay posiciones; si no, por nº de acciones.
  const useValue = totalValue > 0;
  const bySector = {};
  for (const e of entries) {
    const sec = (e.sector || "Sin sector").trim() || "Sin sector";
    const w = useValue ? posValue(e) : 1;
    if (w > 0) bySector[sec] = (bySector[sec] || 0) + w;
  }
  const totalW = Object.values(bySector).reduce((s, v) => s + v, 0);
  const sectors = Object.entries(bySector)
    .map(([name, w]) => ({ name, pct: totalW > 0 ? (w / totalW) * 100 : 0 }))
    .sort((a, b) => b.pct - a.pct);
  const topPct = sectors[0]?.pct || 0;

  if (!entries.length) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-[minmax(0,320px)_1fr] gap-3">
      {/* P&L total */}
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-4">
        <p className="text-[11px] uppercase tracking-wide text-neutral-400 font-mono mb-1">Rendimiento de la cartera</p>
        {conPos.length === 0 ? (
          <p className="text-xs text-neutral-400 mt-2">Añade tu <b>precio de compra</b> y <b>nº de acciones</b> en cada acción para ver tu P&amp;L real.</p>
        ) : (
          <>
            <div className="flex items-baseline gap-2">
              <PnlText abs={totalPnl} pct={totalPnlPct} size="base" tasa={tasaResumen} />
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2 text-[11px] font-mono">
              <div><span className="text-neutral-400">Invertido</span><br /><b>{eur0(totalCost)}</b></div>
              <div><span className="text-neutral-400">Valor actual</span><br /><b>{eur0(totalValue)}</b></div>
            </div>
            {(incompletas > 0 || multiDivisa) && (
              <p className="text-[10px] text-aviso mt-2 leading-snug">
                {incompletas > 0 && <>⚠ {incompletas} posición{incompletas > 1 ? "es" : ""} sin precio de compra o sin cotización — no cuenta{incompletas > 1 ? "n" : ""} en el total. </>}
                {multiDivisa && <>⚠ Hay varias divisas ({[...divisas].join(", ")}): el total es una suma sin convertir.</>}
              </p>
            )}
          </>
        )}
      </div>
      {/* Diversificación */}
      <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-4">
        <div className="flex items-center justify-between mb-2">
          <p className="text-[11px] uppercase tracking-wide text-neutral-400 font-mono">Diversificación {useValue ? "(por valor)" : "(por nº acciones)"}</p>
          {topPct >= 40 && (
            <span className="text-[10px] font-bold text-baja bg-red-50 dark:bg-red-900/30 px-2 py-0.5 rounded-full">
              ⚠ Concentración alta: {topPct.toFixed(0)}% en {sectors[0].name}
            </span>
          )}
        </div>
        {sectors.length === 0 ? (
          <p className="text-xs text-neutral-400">Añade el <b>sector</b> a tus acciones para ver el reparto.</p>
        ) : (
          <>
            <div className="flex h-3 rounded-full overflow-hidden mb-2">
              {sectors.map((s, i) => (
                <div key={s.name} style={{ width: `${s.pct}%`, background: SECTOR_COLORS[i % SECTOR_COLORS.length] }} title={`${s.name}: ${s.pct.toFixed(0)}%`} />
              ))}
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
              {sectors.slice(0, 6).map((s, i) => (
                <span key={s.name} className="flex items-center gap-1 text-neutral-600 dark:text-neutral-300">
                  <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: SECTOR_COLORS[i % SECTOR_COLORS.length] }} />
                  {s.name} <b>{s.pct.toFixed(0)}%</b>
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Correlación de la cartera (#22): detecta acciones que se mueven a la vez ─────
function corrNivel(avg) {
  if (avg == null) return { txt: "—", cls: "text-neutral-400" };
  if (avg < 0.3) return { txt: "Bien diversificada", cls: "text-green-600 dark:text-green-400" };
  if (avg < 0.5) return { txt: "Diversificación moderada", cls: "text-aviso" };
  if (avg < 0.7) return { txt: "Poco diversificada", cls: "text-orange-500" };
  return { txt: "Muy correlacionada (riesgo de bloque)", cls: "text-red-600 dark:text-red-400" };
}

function CorrelationCard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/portfolio/correlation`, { headers: authHeaders() });
      setData(await r.json());
      setDone(true);
    } catch { toast.error("No se pudo calcular la correlación"); }
    finally { setLoading(false); }
  };

  const nivel = corrNivel(data?.avg_corr);
  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-4">
      <div className="flex items-center justify-between gap-2 mb-1">
        <p className="text-[11px] uppercase tracking-wide text-neutral-400 font-mono">🔗 Correlación (concentración oculta)</p>
        <button onClick={run} disabled={loading}
          className="px-2.5 py-1 rounded text-[11px] font-mono font-semibold bg-marca text-marca-tinta disabled:opacity-50">
          {loading ? "Calculando…" : done ? "Recalcular" : "Analizar"}
        </button>
      </div>
      {!done && !loading && (
        <p className="text-xs text-neutral-400">Mide si tus acciones se mueven a la vez (aunque sean de sectores distintos). Si están muy correlacionadas, una caída del mercado te afecta a todas por igual.</p>
      )}
      {data?.message && <p className="text-xs text-neutral-500 mt-1">{data.message}</p>}
      {done && data && data.avg_corr != null && (
        <div className="space-y-2 mt-1">
          <div className="flex items-baseline gap-2">
            <span className="font-mono font-bold text-lg text-neutral-900 dark:text-white">{data.avg_corr}</span>
            <span className={`text-xs font-semibold ${nivel.cls}`}>{nivel.txt}</span>
            {/* De cuántas. Con 83 valores en la Cartera y un techo de 25, decir solo "25
                acciones" hace leer como veredicto de toda la cartera lo que es de una
                parte. Las abiertas entran primero, que es lo que hace que la cifra siga
                significando algo aunque no quepan todas. */}
            <span className="text-[10px] text-neutral-400">
              · {data.n} acciones
              {data.truncado && data.total ? ` de ${data.total}` : ""}
            </span>
          </div>
          {data.truncado && (
            <p className="text-[10px] text-neutral-400 leading-snug">
              Se analizan hasta {data.n} valores, y entran primero tus{" "}
              {data.en_cartera} posición(es) abiertas: cada acción descarga un año de
              histórico. Las que solo vigilas pueden quedarse fuera.
            </p>
          )}
          {(data.high || []).length > 0 ? (
            <div>
              <p className="text-[10px] uppercase text-neutral-400 font-mono mb-1">Se mueven casi igual (riesgo de bloque)</p>
              <div className="flex flex-wrap gap-1.5">
                {data.high.slice(0, 6).map((p) => (
                  <span key={`${p.a}-${p.b}`} className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300">
                    {p.a} ↔ {p.b} · {p.corr}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-green-600 dark:text-green-400">✓ Ningún par se mueve en exceso al unísono. Buena señal.</p>
          )}
        </div>
      )}
    </div>
  );
}

const RIESGO_STYLE = {
  BAJO:  { bg: "bg-green-100 dark:bg-green-900/40",  text: "text-green-700 dark:text-green-300" },
  MEDIO: { bg: "bg-yellow-100 dark:bg-yellow-900/40", text: "text-yellow-700 dark:text-yellow-300" },
  ALTO:  { bg: "bg-red-100 dark:bg-red-900/40",       text: "text-red-600 dark:text-red-400" },
};

// La letra A-D del modelo de MARGEN de DEGIRO, que NO es el campo `riesgo` de al lado.
// `riesgo` es la clasificación de tu inversor; esta la publica el bróker junto a cada
// producto y determina cuánto riesgo le asigna su modelo — una categoría D computa al 100%
// de su valor, así que venderla libera todo y comprarla se lo come todo.
//
// Se teclea a mano porque no hay API que la sirva. Sin ella el simulador de margen no puede
// reproducir el riesgo real y se calla, que es exactamente lo que estaba pasando.
const CAT_TONO = { A: "text-sube", B: "text-tinta-2", C: "text-aviso", D: "text-baja" };

function CategoriaDegiro({ value, onChange }) {
  const v = (value || "").toUpperCase();
  return (
    <select
      value={v}
      onChange={(ev) => onChange(ev.target.value || null)}
      title="Categoría de riesgo de DEGIRO (A-D). Sale junto al nombre del producto en la pantalla de la orden. Determina cuánto margen libera vender esta acción."
      className={`bg-transparent border border-linea rounded px-1 py-0.5 text-xs font-mono font-bold ${CAT_TONO[v] || "text-tinta-3"}`}
    >
      <option value="">—</option>
      {["A", "B", "C", "D"].map((c) => <option key={c} value={c}>{c}</option>)}
    </select>
  );
}

function RiesgoBadge({ value }) {
  if (!value) return <span className="text-neutral-400">—</span>;
  const key = value.toUpperCase();
  const s = RIESGO_STYLE[key] || { bg: "bg-neutral-100", text: "text-neutral-600" };
  return (
    <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold uppercase ${s.bg} ${s.text}`}>
      {value}
    </span>
  );
}

function BellToggle({ active, onClick, title }) {
  return (
    <button
      onClick={onClick}
      title={title || (active ? "Alerta activa — clic para desactivar" : "Alerta inactiva — clic para activar")}
      className={`p-1 rounded transition-colors ${active ? "text-aviso hover:text-yellow-600" : "text-neutral-300 hover:text-neutral-500"}`}
    >
      {active ? <Bell size={14} weight="fill" /> : <BellSlash size={14} />}
    </button>
  );
}

// ── EditableCell ──────────────────────────────────────────────────────────────
function EditableCell({ value, onChange, isNumber = true, placeholder = "—", className = "", format }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef(null);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);

  const commit = () => {
    setEditing(false);
    // `aNumero` y no parseFloat: en el móvil se teclea 560,67 y parseFloat corta en la
    // coma y devuelve 560 — un nivel equivocado guardado sin decir nada.
    const parsed = isNumber ? aNumero(draft) : draft;
    if (parsed !== value) onChange(parsed);
  };

  if (editing) return (
    <input
      ref={inputRef}
      className={`w-full bg-white dark:bg-neutral-800 border border-blue-400 rounded px-1 py-0.5 text-sm outline-none ${className}`}
      // NUNCA type="number": el teclado numérico de un teléfono en español ofrece coma, y
      // ese campo la descarta —el valor llega vacío y el nivel no se puede escribir—.
      // `inputMode="decimal"` da el mismo teclado sin la validación del navegador.
      type="text"
      inputMode={isNumber ? "decimal" : "text"}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") { setEditing(false); setDraft(value ?? ""); } }}
    />
  );

  const display = format ? format(value) : (isNumber ? fmtP(value) : (value || placeholder));
  return (
    <span
      onClick={() => { setDraft(value ?? ""); setEditing(true); }}
      className={`cursor-pointer hover:underline hover:text-blue-600 dark:hover:text-blue-400 select-none ${!value && value !== 0 ? "text-neutral-400" : ""} ${className}`}
      title="Clic para editar"
    >
      {display}
    </span>
  );
}

// ── parseExcel helper ─────────────────────────────────────────────────────────
function parseExcelText(text) {
  const lines = text.trim().split("\n").filter(Boolean);
  if (lines.length < 2) return [];
  const sep = lines[0].includes("\t") ? "\t" : ",";
  const headers = lines[0].split(sep).map((h) => h.trim().toLowerCase().replace(/[\s\-/áéíóú]+/g, "_"));

  const map = {
    // OJO: "accion" va SOLO en name, no en symbol. En el Excel la columna "Acción"
    // es el NOMBRE (ORACLE) y "Ticker/ISIN" es el SÍMBOLO (ORCL). Si "accion" estuviera
    // también en symbol, al ser la primera columna se cogería "ORACLE" como ticker.
    symbol: ["ticker_isin", "ticker", "symbol", "simbolo"],
    name:   ["name", "nombre", "empresa", "accion", "acci_n"],
    mercado: ["mercado", "market", "bolsa"],
    deseado: ["deseado", "objetivo", "target", "nivel_deseado", "nivel_deseado_venta"],
    nivel1:  ["nivel1", "nivel_1", "nivel 1", "n1", "compra1"],
    nivel2:  ["nivel2", "nivel_2", "nivel 2", "n2", "compra2"],
    nivel3:  ["nivel3", "nivel_3", "nivel 3", "n3", "compra3"],
    nivel4:  ["nivel4", "nivel_4", "nivel 4", "n4", "compra4"],
    nivel5:  ["nivel5", "nivel_5", "nivel 5", "nivel_5_extra", "n5"],
    venta1:  ["venta1", "venta_1", "venta 1", "v1"],
    venta2:  ["venta2", "venta_2", "venta 2", "v2"],
    venta3:  ["venta3", "venta_3", "venta 3", "v3"],
    riesgo:  ["riesgo", "risk"],
    sector:  ["sector"],
    posibles_ganancias: ["posibles_ganancias", "ganancias", "ganancia", "upside", "potencial"],
  };

  const colIndex = {};
  for (const [field, aliases] of Object.entries(map)) {
    for (let i = 0; i < headers.length; i++) {
      if (aliases.some((a) => headers[i].includes(a.replace(/ /g, "_")))) {
        colIndex[field] = i;
        break;
      }
    }
  }

  const rows = [];
  for (let r = 1; r < lines.length; r++) {
    const cols = lines[r].split(sep).map((c) => c.trim().replace(/^"|"$/g, "").replace(",", ".").replace("%", ""));
    const symbol = colIndex.symbol != null ? cols[colIndex.symbol]?.toUpperCase() : null;
    if (!symbol || symbol.length > 10) continue;
    const num = (key) => {
      if (colIndex[key] == null) return null;
      const v = parseFloat(cols[colIndex[key]]);
      return isNaN(v) ? null : v;
    };
    const str = (key) => colIndex[key] != null ? (cols[colIndex[key]] || "") : "";
    rows.push({
      symbol,
      name: str("name"),
      mercado: str("mercado"),
      deseado: num("deseado"),
      nivel1: num("nivel1"),
      nivel2: num("nivel2"),
      nivel3: num("nivel3"),
      nivel4: num("nivel4"),
      nivel5: num("nivel5"),
      venta1: num("venta1"),
      venta2: num("venta2"),
      venta3: num("venta3"),
      riesgo: str("riesgo").toUpperCase(),
      sector: str("sector"),
      posibles_ganancias: num("posibles_ganancias"),
      active: true,
    });
  }
  return rows;
}

// ── Empty form states ───────────────────────────────────────────────────────────
const EMPTY = { symbol: "", name: "", mercado: "", deseado: "", nivel1: "", nivel2: "", nivel3: "", nivel4: "", nivel5: "", venta1: "", venta2: "", venta3: "", riesgo: "", sector: "", posibles_ganancias: "", notes: "", compra: "", acciones: "" };

// Configuración de campos del formulario "Añadir" por grupo
const ADD_FIELDS = {
  ideas_javi: [
    { key: "symbol",   label: "Ticker *",    placeholder: "AAPL" },
    { key: "name",     label: "Nombre",      placeholder: "Apple" },
    { key: "mercado",  label: "Mercado",     placeholder: "NASDAQ" },
    { key: "deseado",  label: "Deseado/Venta", placeholder: "200" },
    { key: "nivel1",   label: "Nivel 1",     placeholder: "180" },
    { key: "nivel2",   label: "Nivel 2",     placeholder: "170" },
    { key: "nivel3",   label: "Nivel 3",     placeholder: "160" },
    { key: "nivel4",   label: "Nivel 4",     placeholder: "150" },
    { key: "nivel5",   label: "Nivel 5 Extra", placeholder: "140" },
    { key: "compra",   label: "Precio compra", placeholder: "155.20" },
    { key: "acciones", label: "Nº acciones",   placeholder: "10" },
    // Sin esto no se puede saber el tipo de cambio del día que compraste, y la ganancia
    // en euros al vender sale aproximada en vez de exacta.
    { key: "fecha_compra", label: "Fecha compra", placeholder: "2025-01-15" },
    { key: "riesgo",   label: "Riesgo",      placeholder: "MEDIO" },
    { key: "sector",   label: "Sector",      placeholder: "TECH" },
    // Aparte del anterior: aquí va cómo agrupa DEGIRO, que es mucho más grueso. Solo se
    // usa para el límite de concentración sectorial de su modelo de margen. Vacío = se
    // usa el sector de al lado.
    { key: "sector_degiro", label: "Sector DEGIRO", placeholder: "= el de al lado" },
    { key: "posibles_ganancias", label: "Posibles Ganancias %", placeholder: "25.5" },
  ],
};
const NUM_KEYS = new Set(["deseado", "nivel1", "nivel2", "nivel3", "nivel4", "nivel5", "venta1", "venta2", "venta3", "posibles_ganancias", "bz", "objetivo_5a", "compra", "acciones"]);

// ── Main component ────────────────────────────────────────────────────────────
export default function SignalsView({ setSymbol }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState({});
  const [grupo, setGrupo] = useState("ideas_javi");
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  // Se puede llegar aquí con el formulario ya abierto (/cartera?nueva=1). Lo usa el botón
  // «Nueva acción» de la portada: mandar a la Cartera y que ahí haya que buscar el botón
  // otra vez convierte un atajo en un desvío.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("nueva") === "1") {
      setNewEntry(EMPTY);
      setShowAdd(true);
    }
  }, []);
  const [newEntry, setNewEntry] = useState(EMPTY);
  const imageInputRef = useRef(null);

  // Memoizado: el polling de 30s reescribe `entries`; sin esto, filtrar y contar se
  // recalculaba en cada render (y countOf se llamaba 2× por render, re-filtrando todo).
  const visible = useMemo(() => entries.filter((e) => grupoOf(e) === grupo), [entries, grupo]);
  const counts = useMemo(() => {
    const c = {};
    for (const e of entries) { const g = grupoOf(e); c[g] = (c[g] || 0) + 1; }
    return c;
  }, [entries]);
  const countOf = (g) => counts[g] || 0;

  // Marca de la última mutación local (editar/añadir/borrar). Un poll que arrancó
  // ANTES de una edición no debe pisar el estado local más nuevo.
  const lastLocalEditRef = useRef(0);

  const fetchEntries = async () => {
    setLoading(true);
    const startedAt = Date.now();
    try {
      const r = await fetch(`${API}/api/signals`, { headers: authHeaders() });
      // Sin este chequeo, un 401/500 devolvía {detail:"..."} y setEntries(objeto) hacía que
      // entries.filter lanzara y toda la Cartera cayera en el ErrorBoundary.
      if (!r.ok) {
        if (r.status === 401) {
          localStorage.removeItem("inveria_token");
          localStorage.removeItem("inveria_user");
          window.location.href = "/";
        } else {
          toast.error("No se pudieron cargar las señales");
        }
        return;
      }
      const data = await r.json();
      if (lastLocalEditRef.current <= startedAt) setEntries(Array.isArray(data) ? data : []);
    } catch { toast.error("No se pudieron cargar las señales"); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    fetchEntries();
    // Refresh silencioso cada 30s. Se salta si la pestaña está oculta (evita spam de
    // requests a un backend dormido) y descarta respuestas anteriores a una edición local.
    const id = setInterval(() => {
      if (document.hidden) return;
      const startedAt = Date.now();
      fetch(`${API}/api/signals`, { headers: authHeaders() })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => { if (Array.isArray(data) && lastLocalEditRef.current <= startedAt) setEntries(data); })
        .catch(() => {});
    }, 30000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Al cambiar de pestaña, cerrar paneles y resetear el formulario al esquema correcto
  const switchGrupo = (g) => {
    setGrupo(g);
    setShowAdd(false);
    setShowImport(false);
    setNewEntry(EMPTY);
  };

  // Guarda un campo y CUENTA por qué no se pudo, si no se pudo.
  //
  // Antes cualquier fallo se convertía en "Error al guardar", a secas: el servidor
  // explicaba y la pantalla tiraba la explicación. Ahora sale lo que diga el servidor y el
  // genérico solo queda para cuando no dice nada.
  //
  // Editar un nivel ya NO pasa por la puerta de tendencia: mantener el plan de una acción
  // que ya está en tu Cartera no autoriza ninguna compra. El veto sigue en el alta, que es
  // donde se incorpora una acción nueva — ver addEntry.
  const updateField = async (id, field, value) => {
    setSaving((s) => ({ ...s, [id]: true }));
    try {
      const r = await fetch(`${API}/api/signals/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ [field]: value }),
      });
      if (!r.ok) {
        const cuerpo = await r.json().catch(() => null);
        const detalle = cuerpo?.detail;
        throw new Error(typeof detalle === "string" ? detalle : detalle?.mensaje || "");
      }
      const updated = await r.json();
      lastLocalEditRef.current = Date.now();
      setEntries((prev) => prev.map((e) => e.id === id ? { ...e, ...updated } : e));
    } catch (e) {
      toast.error(e?.message || "Error al guardar");
    }
    finally { setSaving((s) => ({ ...s, [id]: false })); }
  };

  const deleteEntry = async (id) => {
    if (!window.confirm("¿Eliminar esta entrada?")) return;
    try {
      await fetch(`${API}/api/signals/${id}`, { method: "DELETE", headers: authHeaders() });
      lastLocalEditRef.current = Date.now();
      setEntries((prev) => prev.filter((e) => e.id !== id));
      toast.success("Eliminado");
    } catch { toast.error("Error al eliminar"); }
  };

  const addEntry = async () => {
    if (!newEntry.symbol.trim()) { toast.error("El símbolo es obligatorio"); return; }
    const num = (k) => newEntry[k] ? parseFloat(newEntry[k]) : null;
    const payload = { symbol: newEntry.symbol.trim().toUpperCase(), grupo, active: true };
    for (const { key } of ADD_FIELDS[grupo]) {
      if (key === "symbol") continue;
      if (NUM_KEYS.has(key)) payload[key] = num(key);
      else if (key === "divisa" || key === "mercado" || key === "riesgo") payload[key] = (newEntry[key] || "").toUpperCase();
      else payload[key] = newEntry[key] || "";
    }
    try {
      const r = await fetch(`${API}/api/signals`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(payload) });
      // HAY DOS 409 DISTINTOS y confundirlos es el peor final posible.
      //
      // Uno es el duplicado: el símbolo ya está en la Cartera. El otro es el VETO de
      // tendencia sobre un alta con niveles de compra. Tratarlos igual —como se hacía—
      // cerraba el formulario diciendo "ya estaba en tu Cartera" cuando en realidad el
      // alta se había RECHAZADO: un rechazo leído como éxito, y la acción sin dar de alta
      // sin que nadie se enterara. Por eso el servidor manda el del veto estructurado.
      if (r.status === 409) {
        const cuerpo = await r.json().catch(() => null);
        const detalle = cuerpo?.detail;
        if (detalle?.error === "vetado_por_tendencia") {
          toast.warning(`${detalle.symbol}: no se ha dado de alta. ${detalle.mensaje}`,
                        { duration: 12000 });
          return;   // el formulario se queda abierto: no se ha guardado nada
        }
        toast(`${payload.symbol} ya estaba en tu Cartera`);
        setShowAdd(false); setNewEntry(EMPTY);
        return;
      }
      if (!r.ok) {
        const cuerpo = await r.json().catch(() => null);
        const detalle = cuerpo?.detail;
        throw new Error(typeof detalle === "string" ? detalle : detalle?.mensaje || "");
      }
      const created = await r.json();
      lastLocalEditRef.current = Date.now();
      setEntries((prev) => [...prev, created]);
      setShowAdd(false); setNewEntry(EMPTY);
      toast.success(`${created.symbol} añadido`);
    } catch (e) { toast.error(e?.message || "Error al añadir"); }
  };

  const doImport = async () => {
    const rows = parseExcelText(importText);
    if (!rows.length) { toast.error("No se detectaron filas. Comprueba el formato."); return; }
    setImporting(true);
    try {
      const r = await fetch(`${API}/api/signals/bulk`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ rows }) });
      if (!r.ok) throw new Error();
      const { created, updated } = await r.json();
      toast.success(`Importado: ${created} nuevas, ${updated} actualizadas`);
      setShowImport(false); setImportText(""); fetchEntries();
    } catch { toast.error("Error al importar"); }
    finally { setImporting(false); }
  };

  // Importar desde FOTO: sube la imagen, Gemini lee la tabla y hace el upsert.
  // Respeta el estado manual (campanas/activo) igual que la importación por texto.
  const doImportImage = async (file) => {
    if (!file) return;
    setImporting(true);
    toast.info("Leyendo la foto… (puede tardar unos segundos)");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch(`${API}/api/signals/import-image`, { method: "POST", headers: { ...authHeaders() }, body: fd });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || "Error al leer la foto");
      }
      const { created, updated } = await r.json();
      toast.success(`Foto importada: ${created} nuevas, ${updated} actualizadas`);
      setShowImport(false); fetchEntries();
    } catch (e) { toast.error(e.message || "No se pudo leer la foto"); }
    finally { setImporting(false); }
  };

  // ── render ──────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-4 sm:py-6 space-y-4 sm:space-y-6">

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            📋 Cartera
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
            Activa la 🔔 en cada nivel para recibir alerta por Telegram y email cuando el precio lo alcance.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={fetchEntries} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors">
            <ArrowClockwise size={14} /> Refrescar
          </button>
          <button onClick={() => setShowImport(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors">
            <UploadSimple size={14} /> Importar Excel
          </button>
          <button onClick={() => imageInputRef.current?.click()} disabled={importing} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors disabled:opacity-50">
            <Camera size={14} /> {importing ? "Leyendo…" : "Importar foto"}
          </button>
          <input
            ref={imageInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; doImportImage(f); }}
          />
          <button onClick={() => { setNewEntry(EMPTY); setShowAdd(true); }} className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-marca hover:bg-marca/90 text-marca-tinta text-sm font-medium transition-colors">
            <Plus size={14} weight="bold" /> Añadir acción
          </button>
        </div>
      </div>

      {/* Sub-tabs (solo si hay más de un grupo) */}
      {GRUPOS.length > 1 && (
      <div className="flex items-center gap-1 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg p-1 w-fit">
        {GRUPOS.map((g) => {
          const Icon = g.icon;
          const active = grupo === g.key;
          return (
            <button
              key={g.key}
              onClick={() => switchGrupo(g.key)}
              data-testid={`signals-tab-${g.key}`}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                active ? "bg-marca text-marca-tinta" : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-800 dark:hover:text-neutral-200"
              }`}
            >
              <Icon size={15} weight="bold" />
              {g.label}
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded-full ${active ? "bg-white/20" : "bg-neutral-100 dark:bg-neutral-800"}`}>{countOf(g.key)}</span>
            </button>
          );
        })}
      </div>
      )}

      {/* Resumen de cartera: P&L total + diversificación (#20 + #21) */}
      {!loading && visible.length > 0 && <PortfolioSummary entries={visible} />}

      {/* Correlación de la cartera (#22) */}
      {!loading && visible.length >= 2 && <CorrelationCard />}

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-neutral-500">
        <span className="flex items-center gap-1"><Bell size={12} weight="fill" className="text-aviso" /> Alerta activa</span>
        <span className="flex items-center gap-1"><BellSlash size={12} className="text-neutral-300" /> Alerta inactiva</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-blue-100 dark:bg-blue-900/40 border border-blue-300 inline-block"></span> Nivel Deseado / Venta</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-50 dark:bg-green-900/20 border border-green-200 inline-block"></span> Niveles de Compra</span>
      </div>

      {/* Import panel */}
      {showImport && (
        <div className="rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-blue-800 dark:text-blue-200">📥 Importar desde Excel</p>
            <button onClick={() => { setShowImport(false); setImportText(""); }}><X size={16} className="text-blue-600" /></button>
          </div>
          <p className="text-xs text-blue-600 dark:text-blue-400">
            Abre tu Excel, selecciona todas las celdas incluyendo cabecera y pégalas aquí (Ctrl+V).<br />
            Columnas reconocidas: <code>Acción, Mercado, Ticker/ISIN, Nivel Deseado/Venta, Nivel 1–5, Riesgo, Sector, Posibles Ganancias</code>
          </p>
          <textarea
            className="w-full h-40 p-3 rounded-lg border border-blue-300 dark:border-blue-700 bg-white dark:bg-neutral-900 text-sm font-mono resize-none outline-none"
            placeholder={"Acción\tMercado\tTicker/ISIN\tNivel Deseado/Venta\tNivel 1\tNivel 2\tNivel 3\tNivel 4\tNivel 5 EXTRA\tRiesgo\tSector\nORACLE\tNYSE\tORCL\t300\t220\t200\t180\t160\tNO\tMEDIO\tTECH"}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
          />
          <div className="flex gap-2">
            <button onClick={doImport} disabled={importing || !importText.trim()} className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium">
              {importing ? "Importando…" : "Importar"}
            </button>
            <button onClick={() => { setShowImport(false); setImportText(""); }} className="px-4 py-2 rounded-lg border border-neutral-300 text-sm hover:bg-neutral-100">Cancelar</button>
          </div>
        </div>
      )}

      {/* Add panel */}
      {showAdd && (
        <div className="rounded-xl border border-marca/30 bg-fondo p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-tinta">➕ Nueva acción · Cartera</p>
            <button onClick={() => setShowAdd(false)}><X size={16} /></button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {ADD_FIELDS[grupo].map(({ key, label, placeholder }) => (
              <div key={key} className="flex flex-col gap-1">
                <label className="text-xs text-neutral-500">{label}</label>
                <input
                  className="border border-neutral-200 dark:border-neutral-600 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-neutral-800 outline-none focus:border-marca focus:ring-1 focus:ring-marca/20"
                  placeholder={placeholder}
                  value={newEntry[key] ?? ""}
                  onChange={(e) => setNewEntry((p) => ({ ...p, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={addEntry} className="px-4 py-2 rounded-lg bg-marca hover:bg-marca/90 text-marca-tinta text-sm font-medium">Guardar</button>
            <button onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-lg border border-neutral-300 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800">Cancelar</button>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && <div className="text-center py-16 text-neutral-400">Cargando señales…</div>}

      {/* Empty */}
      {!loading && visible.length === 0 && (
        <div className="text-center py-16 text-neutral-400">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-lg font-medium">Sin acciones todavía</p>
          <p className="text-sm mt-1">Añade una acción o importa desde Excel</p>
        </div>
      )}

      {/* ════════════════ CARTERA ════════════════ */}
      {!loading && visible.length > 0 && <IdeasView entries={visible} saving={saving} updateField={updateField} deleteEntry={deleteEntry} setSymbol={setSymbol} onVendido={fetchEntries} />}

      <p className="text-xs text-neutral-400 text-center pb-2">
        🔔 Alertas solo en horario de mercado (9:30-16:00 ET) · 1 vez al día por nivel · Telegram + Email · Haz clic en cualquier valor para editarlo
      </p>
    </div>
  );
}

// ── IDEAS JAVI view (cartera editable de niveles 1-5) ───────────────────────────

// ── Registrar una VENTA ejecutada ────────────────────────────────────────────
// Distinto de venta1/2/3, que son precios OBJETIVO. Esto es una venta ya hecha, y calcula
// lo que se ha ganado DE VERDAD en euros usando el tipo de cambio del día de la compra y el
// del día de la venta — no el de hoy, que daría un número que no ocurrió.
function DialogoVenta({ entry, onClose, onHecho }) {
  const [acciones, setAcciones] = React.useState("");
  const [precio, setPrecio] = React.useState("");
  const [fecha, setFecha] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [enviando, setEnviando] = React.useState(false);
  const [res, setRes] = React.useState(null);
  const tiene = Number(entry?.acciones) || 0;
  const divisa = (entry?.divisa || "USD").toUpperCase();

  const enviar = async () => {
    const n = parseFloat(acciones), p = parseFloat(precio);
    if (!n || n <= 0) return toast.error("¿Cuántas acciones has vendido?");
    if (n > tiene) return toast.error(`Solo tienes ${tiene} acciones de ${entry.symbol}.`);
    if (!p || p <= 0) return toast.error("¿A qué precio las has vendido?");
    setEnviando(true);
    try {
      const r = await fetch(`${API}/api/signals/${entry.id}/vender`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ acciones: n, precio_venta: p, fecha }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "No se pudo registrar la venta");
      setRes(d);
      onHecho?.();
    } catch (err) { toast.error(err.message); }
    finally { setEnviando(false); }
  };

  const eur = (x) => x == null ? "—" : `${x >= 0 ? "+" : ""}${Number(x).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-neutral-900 rounded-xl p-5 w-full max-w-md" onClick={(ev) => ev.stopPropagation()}>
        {!res ? (
          <>
            <div className="flex items-center justify-between mb-1">
              <h3 className="font-bold text-lg text-tinta">Vender {entry.symbol}</h3>
              <button onClick={onClose} className="text-neutral-400 hover:text-neutral-600"><X size={18} /></button>
            </div>
            <p className="text-xs text-neutral-500 mb-4">
              Tienes <b>{tiene}</b> acciones a un precio medio de <b>{fmtP(entry.compra)}</b> ({divisa}).
            </p>
            <div className="space-y-3">
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider text-neutral-500">Acciones vendidas</span>
                <input type="number" step="any" value={acciones} onChange={(ev) => setAcciones(ev.target.value)}
                       placeholder={String(tiene)} className="w-full mt-1 border rounded px-2 py-1.5 font-mono dark:bg-neutral-800 dark:border-neutral-700" />
              </label>
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider text-neutral-500">Precio de venta ({divisa})</span>
                <input type="number" step="any" value={precio} onChange={(ev) => setPrecio(ev.target.value)}
                       placeholder={entry.last_price ? String(entry.last_price) : "0.00"} className="w-full mt-1 border rounded px-2 py-1.5 font-mono dark:bg-neutral-800 dark:border-neutral-700" />
              </label>
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider text-neutral-500">Fecha de la venta</span>
                <input type="date" value={fecha} onChange={(ev) => setFecha(ev.target.value)}
                       className="w-full mt-1 border rounded px-2 py-1.5 font-mono dark:bg-neutral-800 dark:border-neutral-700" />
              </label>
              {!entry.fecha_compra && divisa !== "EUR" && (
                <p className="text-[11px] text-aviso bg-aviso/10 rounded px-2 py-1.5 leading-snug">
                  Esta posición no tiene <b>fecha de compra</b>, así que la ganancia en euros
                  saldrá aproximada. Rellénala en la Cartera para que sea exacta.
                </p>
              )}
            </div>
            {/* ANTES del botón: la pregunta que resuelve solo sirve mientras la venta
                todavía se puede no hacer. Después ya no es una decisión, es un apunte. */}
            <div className="mt-3">
              <RiesgoVenta symbol={entry.symbol} acciones={aNumero(acciones) || undefined} />
            </div>
            <button onClick={enviar} disabled={enviando}
                    className="w-full mt-4 bg-marca text-marca-tinta rounded-lg py-2 font-semibold disabled:opacity-60">
              {enviando ? "Calculando…" : "Registrar venta"}
            </button>
          </>
        ) : (
          <>
            <h3 className="font-bold text-lg mb-3 text-tinta">
              Venta registrada · {res.acciones} {entry.symbol}
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-neutral-500">Ganancia en {res.divisa}</span>
                <span className={`font-mono font-bold ${res.ganancia_divisa >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {res.ganancia_divisa >= 0 ? "+" : ""}{res.ganancia_divisa} ({res.ganancia_pct}%)</span></div>
              <div className="flex justify-between items-baseline border-t pt-2 dark:border-neutral-700">
                <span className="text-neutral-500 font-semibold">Ganancia en EUROS</span>
                <span className={`font-mono font-bold text-lg ${(res.ganancia_eur ?? 0) >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {eur(res.ganancia_eur)}</span></div>
              {res.efecto_divisa_eur != null && (
                <div className="flex justify-between text-xs">
                  <span className="text-neutral-500">De eso, por el tipo de cambio</span>
                  <span className="font-mono">{eur(res.efecto_divisa_eur)}</span></div>
              )}
              {!res.exacto && (
                <p className="text-[11px] text-aviso bg-aviso/10 rounded px-2 py-1.5 leading-snug">
                  Aproximado: falta el tipo de cambio del día de la compra.
                </p>
              )}
              <p className="text-xs text-neutral-500 pt-1">Te quedan <b>{res.acciones_restantes}</b> acciones.</p>
            </div>
            <button onClick={onClose} className="w-full mt-4 border rounded-lg py-2 dark:border-neutral-700">Cerrar</button>
          </>
        )}
      </div>
    </div>
  );
}

function IdeasView({ entries, saving, updateField, deleteEntry, setSymbol, onVendido }) {
  // El hook va AQUÍ, en el componente que pinta las filas. Estaba en SignalsView, que es
  // quien monta la página pero no dibuja la tabla: `pnlEur` no existía en este ámbito y la
  // vista reventaba con "pnlEur is not defined".
  const pnlEur = usePnlEnEuros();
  // Posición sobre la que se está registrando una venta (null = diálogo cerrado).
  const [vendiendo, setVendiendo] = React.useState(null);
  return (
    <>
      {/* MOBILE CARDS */}
      <div className="lg:hidden space-y-3">
        {entries.map((e) => (
          <div key={e.id} className={`rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-4 space-y-3 ${!e.active ? "opacity-50" : ""}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-marca cursor-pointer text-lg" onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</span>
                  {e.mercado && <span className="text-[10px] font-mono bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded">{e.mercado}</span>}
                  <RiesgoBadge value={e.riesgo} />
                  <CategoriaDegiro value={e.categoria_degiro}
                                   onChange={(v) => updateField(e.id, "categoria_degiro", v)} />
                </div>
                <p className="text-sm text-neutral-500 mt-0.5">{e.name || "—"}</p>
                {e.sector && <p className="text-xs text-neutral-400">{e.sector}</p>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <div className="text-right">
                  <p className="text-xs text-neutral-400">Precio actual</p>
                  <p className="font-mono font-bold text-tinta">{fmtP(e.last_price)}</p>
                  <ExtendedBadge entry={e} />
                </div>
                {/* Solo tiene sentido vender lo que se tiene. Sin acciones, el botón
                    llevaría a un error del servidor en vez de a algo útil. */}
                {Number(e.acciones) > 0 && (
                  <button onClick={() => setVendiendo(e)} title="Registrar una venta"
                          className="flex items-center gap-1 text-[11px] font-semibold border border-sube text-sube hover:bg-sube hover:text-marca-tinta rounded px-2 py-1 transition-colors">
                    <CurrencyEur size={13} weight="bold" /> Vender
                  </button>
                )}
                <button onClick={() => deleteEntry(e.id)} className="text-neutral-300 hover:text-red-500 text-xl p-1"><Trash size={16} /></button>
              </div>
            </div>
            {/* Posición + P&L (#20) */}
            <div className="flex items-center justify-between bg-neutral-50 dark:bg-neutral-800/40 border border-neutral-200 dark:border-neutral-700 rounded-lg px-3 py-2">
              <div className="flex gap-4">
                <div>
                  <p className="text-[9px] text-neutral-400 uppercase font-mono">Compra</p>
                  <EditableCell value={e.compra} onChange={(v) => updateField(e.id, "compra", v)} className="font-mono text-sm font-semibold" />
                </div>
                <div>
                  <p className="text-[9px] text-neutral-400 uppercase font-mono">Nº acc.</p>
                  <EditableCell value={e.acciones} onChange={(v) => updateField(e.id, "acciones", v)} format={(v) => v != null && v !== "" ? Number(v).toLocaleString("es-ES", { maximumFractionDigits: 2 }) : "—"} className="font-mono text-sm font-semibold" />
                </div>
              </div>
              <div className="text-right">
                <p className="text-[9px] text-neutral-400 uppercase font-mono">P&amp;L</p>
                <PnlText abs={pnlAbs(e)} pct={pnlPct(e)} eur={pnlEur.porSymbol[(e.symbol || "").toUpperCase()]} tasa={pnlEur.tasaUSD} />
              </div>
            </div>
            <div className="flex items-center justify-between bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2">
              <div>
                <p className="text-[10px] text-blue-500 uppercase font-mono font-bold">Deseado / Venta</p>
                <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} className="font-mono font-bold text-blue-700 dark:text-blue-300 text-sm" />
              </div>
              <div className="flex items-center gap-1">
                {e.posibles_ganancias != null && <span className="text-xs text-green-600 font-bold">{fmtPct(e.posibles_ganancias)}</span>}
                {/* El estado que se NIEGA debe ser el mismo que se PINTA. Con `!e.alert_deseado`, una
    fila antigua sin el campo (undefined) se veía encendida (undefined !== false) pero al
    pulsar mandaba `!undefined` = true: seguía encendida y el primer clic no hacía nada. */}
<BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", e.alert_deseado === false)} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {(() => { const nextN = nextNivelKey(e); return [1,2,3,4,5].map((n) => {
                const val = e[`nivel${n}`];
                const alertKey = `alert_nivel${n}`;
                const alertOn = e[alertKey] !== false;
                if (val == null) return null;
                const d = nivelDist(e, n);
                const isNext = n === nextN;
                return (
                  <div key={n} className={`bg-green-50 dark:bg-green-900/20 rounded-lg p-2 ${isNext ? "border-2 border-aviso" : "border border-green-200 dark:border-green-800"}`}>
                    <div className="flex items-center justify-between mb-0.5">
                      <p className="text-[9px] text-green-600 uppercase font-mono font-bold">Nivel {n}{isNext ? " ◀" : ""}</p>
                      <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
                    </div>
                    <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)} className="font-mono font-bold text-green-800 dark:text-green-300 text-sm" />
                    {d != null && <p className="text-[9px] font-mono text-neutral-400 mt-0.5">{d >= 0 ? "+" : ""}{d.toFixed(1)}%</p>}
                  </div>
                );
              }); })()}
            </div>
            {saving[e.id] && <p className="text-[10px] text-neutral-400 animate-pulse">guardando…</p>}
          </div>
        ))}
      </div>

      {/* DESKTOP TABLE */}
      <div className="hidden lg:block rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-x-auto shadow-sm">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left border-b-2 border-neutral-200 dark:border-neutral-700">
              <th className="px-2 py-2.5 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap w-10 bg-neutral-100 dark:bg-neutral-800">⚡</th>
              <th className="px-2 py-2.5 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800">Acción</th>
              <th className="px-2 py-2.5 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800">Mdo.</th>
              <th className="px-2 py-2.5 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap text-right bg-neutral-100 dark:bg-neutral-800">Precio</th>
              <th className="px-2 py-2.5 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap text-right bg-neutral-100 dark:bg-neutral-800">Compra</th>
              <th className="px-2 py-2.5 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap text-right bg-neutral-100 dark:bg-neutral-800">Acc.</th>
              <th className="px-2 py-2.5 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap text-right bg-neutral-100 dark:bg-neutral-800">P&amp;L</th>
              <th className="px-2 py-2.5 text-xs whitespace-nowrap text-right bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 font-bold border-l border-blue-200 dark:border-blue-800">Deseado</th>
              {[1,2,3,4,5].map((n) => (
                <th key={n} className="px-2 py-2.5 text-xs whitespace-nowrap text-right bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 font-bold border-l border-green-200 dark:border-green-800">N{n}{n === 5 ? "⭐" : ""}</th>
              ))}
              <th className="px-2 py-2.5 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800 border-l border-neutral-200">Riesgo</th>
              <th title="Categoría de riesgo de DEGIRO (A-D). Determina cuánto margen libera vender esta acción." className="px-2 py-2.5 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800">Cat.</th>
              <th className="px-2 py-2.5 w-8 bg-neutral-100 dark:bg-neutral-800"></th>
            </tr>
          </thead>
          <tbody>
            {/* Sector y Ganancia no salen aquí: son de SOLO LECTURA en esta tabla y con
                dieciocho columnas obligaban a scroll horizontal. Se siguen viendo en la
                vista de móvil y se editan en el formulario, así que no se pierde nada —y
                el sector sigue alimentando el modelo de riesgo igual, esté a la vista o
                no. */}
            {entries.map((e, idx) => (
              <tr key={e.id} className={`border-t border-neutral-100 dark:border-neutral-800 transition-colors group ${!e.active ? "opacity-40" : ""} ${idx % 2 === 0 ? "bg-white dark:bg-neutral-900" : "bg-neutral-50 dark:bg-neutral-800/40"} hover:bg-amber-50/60 dark:hover:bg-neutral-700/40`}>
                <td className="px-2 py-2.5 text-center">
                  <input type="checkbox" checked={e.active} onChange={(ev) => updateField(e.id, "active", ev.target.checked)} className="w-4 h-4 cursor-pointer accent-marca" title={e.active ? "Monitorización activa" : "Monitorización pausada"} />
                </td>
                <td className="px-2 py-2.5 whitespace-nowrap">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-marca cursor-pointer hover:underline text-sm" onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</span>
                    {saving[e.id] && <span className="text-[10px] text-neutral-400 animate-pulse">·</span>}
                  </div>
                  <p className="text-[11px] text-neutral-500 dark:text-neutral-400 truncate max-w-[104px] font-medium">{e.name}</p>
                </td>
                <td className="px-2 py-2.5">
                  <span className="text-[11px] font-mono font-semibold bg-neutral-200 dark:bg-neutral-700 px-2 py-0.5 rounded text-neutral-700 dark:text-neutral-300">{e.mercado || "—"}</span>
                </td>
                <td className="px-2 py-2.5 text-right whitespace-nowrap">
                  <span className="font-mono font-bold text-neutral-900 dark:text-white text-sm">{fmtP(e.last_price)}</span>
                  <ExtendedBadge entry={e} />
                </td>
                <td className="px-2 py-2.5 text-right whitespace-nowrap">
                  <EditableCell value={e.compra} onChange={(v) => updateField(e.id, "compra", v)} className="font-mono text-sm text-neutral-700 dark:text-neutral-300" />
                </td>
                <td className="px-2 py-2.5 text-right whitespace-nowrap">
                  <EditableCell value={e.acciones} onChange={(v) => updateField(e.id, "acciones", v)} isNumber format={(v) => v != null && v !== "" ? Number(v).toLocaleString("es-ES", { maximumFractionDigits: 2 }) : "—"} className="font-mono text-sm text-neutral-700 dark:text-neutral-300" />
                </td>
                <td className="px-2 py-2.5 text-right whitespace-nowrap">
                  <PnlText abs={pnlAbs(e)} pct={pnlPct(e)} eur={pnlEur.porSymbol[(e.symbol || "").toUpperCase()]} tasa={pnlEur.tasaUSD} />
                </td>
                <td className="px-2 py-2.5 bg-blue-50 dark:bg-blue-900/20 border-l border-blue-100 dark:border-blue-900">
                  <div className="flex items-center justify-end gap-1">
                    <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} className="font-mono text-sm font-bold text-blue-800 dark:text-blue-200" />
                    {/* El estado que se NIEGA debe ser el mismo que se PINTA. Con `!e.alert_deseado`, una
    fila antigua sin el campo (undefined) se veía encendida (undefined !== false) pero al
    pulsar mandaba `!undefined` = true: seguía encendida y el primer clic no hacía nada. */}
<BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", e.alert_deseado === false)} />
                  </div>
                </td>
                {(() => { const nextN = nextNivelKey(e); return [1,2,3,4,5].map((n) => {
                  const val = e[`nivel${n}`];
                  const alertKey = `alert_nivel${n}`;
                  const alertOn = e[alertKey] !== false;
                  const d = nivelDist(e, n);
                  const isNext = n === nextN;
                  return (
                    <td key={n} className={`px-2 py-2.5 border-l border-green-100 dark:border-green-900 ${isNext ? "bg-aviso/15" : "bg-green-50 dark:bg-green-900/10"}`}>
                      <div className="flex items-center justify-end gap-1">
                        <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)} className="font-mono text-sm font-semibold text-green-900 dark:text-green-300" />
                        <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
                      </div>
                      {d != null && <p className={`text-[9px] font-mono text-right mt-0.5 ${isNext ? "text-aviso font-bold" : "text-neutral-400"}`}>{isNext ? "◀ " : ""}{d >= 0 ? "+" : ""}{d.toFixed(1)}%</p>}
                    </td>
                  );
                }); })()}
                <td className="px-2 py-2.5 whitespace-nowrap border-l border-neutral-100 dark:border-neutral-800"><RiesgoBadge value={e.riesgo} /></td>
                <td className="px-2 py-2.5 whitespace-nowrap"><CategoriaDegiro value={e.categoria_degiro} onChange={(v) => updateField(e.id, "categoria_degiro", v)} /></td>
                <td className="px-2 py-2.5 text-center">
                  <button onClick={() => deleteEntry(e.id)} className="text-neutral-300 hover:text-red-500 transition-colors p-1 opacity-0 group-hover:opacity-100" title="Eliminar"><Trash size={14} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {vendiendo && (
        <DialogoVenta entry={vendiendo} onClose={() => setVendiendo(null)} onHecho={onVendido} />
      )}
    </>
  );
}
