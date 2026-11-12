import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  Bell, BellOff, Trash2, Plus, X, Upload, RefreshCw, Zap, Camera, Euro, ChevronDown,
  GitCompareArrows, SlidersHorizontal, FileSpreadsheet,
} from "lucide-react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { aNumero } from "../lib/format";
import { cn } from "@/lib/utils";
import RiesgoVenta from "../components/RiesgoVenta";
import CarteraCabecera from "../components/CarteraCabecera";
import Boton from "../components/base/Boton";
import Monograma from "../components/base/Monograma";
import CabeceraBloque from "../components/base/CabeceraBloque";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
const authHeaders = () => {
  const token = localStorage.getItem("inveria_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// ── sub-tabs ───────────────────────────────────────────────────────────────────
// Un solo grupo (la antigua pestaña "Cimientos" se eliminó por completo).
const GRUPOS = [
  { key: "ideas_javi", label: "Cartera", icon: Zap },
];
const grupoOf = (e) => e.grupo || "ideas_javi"; // entradas antiguas → Cartera

// ── helpers ──────────────────────────────────────────────────────────────────
const fmtP = (v) => (v != null && v !== "" ? `$${Number(v).toFixed(2)}` : "—");
const fmtPct = (v) => (v != null ? `${Number(v).toFixed(2)}%` : "—");

// ── estilos compartidos (solo presentación) ──────────────────────────────────
// Transición corta de color/borde; se apaga con «reducir movimiento».
const TRANS = "transition-colors duration-150 ease-salida motion-reduce:transition-none";
// Campo de formulario: capa de luz baja, borde translúcido, foco índigo.
const CAMPO = `h-10 w-full rounded-[10px] border border-suave bg-tinta/[0.04] px-3 text-[13.5px] text-tinta outline-none placeholder:text-tinta-3 hover:border-medio focus:border-marca/60 focus:bg-superficie ${TRANS}`;
const ICONO = "w-4 h-4";


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
    <div className="flex flex-col gap-0.5 iv-cifra text-[11.5px] leading-tight">
      {dailyPct != null && (
        <div title="Variación sesión regular vs cierre anterior">
          <span className={dayUp ? "text-sube" : "text-baja"}>{dayUp ? "+" : ""}{dailyPct.toFixed(2)}%</span>
          <span className="text-tinta-3"> hoy</span>
        </div>
      )}
      {ext && (
        <div title={`${ext.label === "PRE" ? "Pre-market" : "After-hours"} vs cierre regular`}>
          <span className="text-tinta-3">{ext.label} ${Number(ext.price).toFixed(2)}</span>
          {ahPct != null && <span className={ahUp ? "text-sube" : "text-baja"}>{` (${ahUp ? "+" : ""}${ahPct.toFixed(2)}%)`}</span>}
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

/** Simbolo de la divisa en la que esta expresado un importe. */
const SIMBOLO_DIVISA = { USD: "$", EUR: "€", GBP: "£", CHF: "CHF", JPY: "¥" };

/** Importe con su divisa DELANTE.
 *
 *  El total de esta cabecera se suma en la moneda de cotizacion —dolares, para casi
 *  toda la cartera— pero se escribia sin simbolo, justo encima de un P&L convertido a
 *  euros. Dos magnitudes distintas, la misma pinta, y ningun sitio donde enterarse:
 *  quien mirase leia "Invertido 28.308" y lo daba por euros. El numero nunca estuvo
 *  mal; lo que faltaba era decir de que moneda es. */
const importe = (x, divisa) => {
  if (x == null) return "—";
  const cifra = eur0(x);
  if (!divisa) return cifra;
  const simbolo = SIMBOLO_DIVISA[divisa] || divisa;
  return simbolo.length === 1 ? `${simbolo}${cifra}` : `${cifra} ${simbolo}`;
};

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
  if (abs == null && !hayEur) return <span className="text-tinta-3">—</span>;

  const principal = hayEur ? eur.pnl_eur : aprox ? abs / tasa : abs;
  const principalPct = hayEur ? eur.pct_eur : pct;   // el % no cambia al convertir
  const up = principal >= 0;
  const color = up ? "text-sube" : "text-baja";
  const enEuros = hayEur || aprox;
  return (
    <span className="inline-flex flex-col items-end leading-tight"
          title={aprox
            ? "Aproximado: es el valor en euros de HOY de tu ganancia en dólares. Para saber lo que has ganado de verdad en euros hace falta el tipo de cambio del día de tu compra — regístrala en Ventas."
            : hayEur
              ? "Exacto: cada compra convertida al tipo de cambio de su fecha y el valor de hoy al de hoy."
              : undefined}>
      <span className={`iv-cifra font-medium whitespace-nowrap ${size === "sm" ? "text-[13.5px]" : "text-[15px]"} ${color}`}>
        {aprox && <span className="opacity-60">≈ </span>}
        {up ? "+" : "−"}{Math.abs(principal).toLocaleString("es-ES", { maximumFractionDigits: 0 })}
        {enEuros ? " €" : " $"}
        {principalPct != null && (
          <span className="text-[11.5px] opacity-80"> · {principalPct >= 0 ? "+" : "−"}{Math.abs(principalPct).toFixed(1)}%</span>
        )}
      </span>
      {/* La divisa original, en pequeño: sirve para cuadrar con la pantalla del bróker,
          que la muestra en dólares. */}
      {enEuros && abs != null && (
        <span className="iv-cifra text-[11.5px] text-tinta-3 mt-0.5">
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
/* Paleta CATEGORICA de sectores. Es la unica de la app que NO sale de los tokens,
   y a proposito: los tokens dicen un PAPEL —sube, baja, aviso— y un sector no tiene
   papel, solo hace falta distinguirlo del de al lado. Por eso son valores fijos.

   Fijos quiere decir que caen igual sobre el marfil del tema claro y sobre el
   verde-negro del oscuro, asi que son todos tonos MEDIOS y desaturados: un color
   vivo se apaga sobre papel o deslumbra sobre el fondo oscuro, y aqui tiene que
   funcionar en los dos sin cambiar.

   Se retira el par de morados (#7c3aed, #9333ea) y el azul de aviso (#2563eb):
   eran de la rampa por defecto y desentonaban con todo lo demas.

   Con el sistema «grafito e índigo» la paleta se rehace en tonos medios fríos que no
   se confunden con los tres colores que sí significan algo: ni verde, ni rojo, ni el
   índigo de la intención. `CarteraCabecera` usa los siete primeros: tienen que
   coincidir. */
// eslint-disable-next-line no-unused-vars
const SECTOR_COLORS = [
  "#6ea8fe",  // azul cielo
  "#c9a26b",  // arena
  "#b48cf2",  // lila
  "#4fc3cf",  // cian
  "#e389b9",  // rosa
  "#9fa8c9",  // lavanda gris
  "#7c8296",  // pizarra
  "#d4b483",  // trigo
];
/* `PortfolioSummary` se ha retirado: lo sustituye `CarteraCabecera`, que dice lo
   mismo mejor y con datos del servidor en vez de recalculados en el navegador.

     · El P&L salia de sumar coste y valor posicion a posicion en el cliente;
       ahora viene de `/cartera/resumen`, que es la MISMA fuente que usa la
       pagina de Operaciones. Tener dos sumas del mismo dinero calculadas en
       sitios distintos era una discrepancia esperando a ocurrir.
     · La diversificacion caia a "por numero de acciones" cuando faltaban
       posiciones valoradas, y cien acciones de 2 EUR pesaban mas que dos de 500.
       La nueva es siempre por VALOR.
     · Los avisos de divisas mezcladas y posiciones incompletas siguen, en el
       panel de senales, y tambien salen del servidor. */

// ── Correlación de la cartera (#22): detecta acciones que se mueven a la vez ─────
function corrNivel(avg) {
  if (avg == null) return { txt: "—", cls: "text-tinta-3" };
  if (avg < 0.3) return { txt: "Bien diversificada", cls: "text-sube" };
  if (avg < 0.5) return { txt: "Diversificación moderada", cls: "text-aviso" };
  if (avg < 0.7) return { txt: "Poco diversificada", cls: "text-aviso" };
  return { txt: "Muy correlacionada (riesgo de bloque)", cls: "text-baja" };
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
    <section id="bloque-correlacion" className="iv-panel p-5 sm:p-6 min-w-0 scroll-mt-24" aria-labelledby="correlacion-titulo" aria-busy={loading}>
      <CabeceraBloque icono={GitCompareArrows} como="h2" id="correlacion-titulo">
        Correlación <span className="text-tinta-3 font-normal">· concentración oculta</span>
      </CabeceraBloque>
      {!done && !loading && (
        <p className="text-[13px] text-tinta-2 mt-4 leading-relaxed">Mide si tus acciones se mueven a la vez (aunque sean de sectores distintos). Si están muy correlacionadas, una caída del mercado te afecta a todas por igual.</p>
      )}
      {loading && (
        <div className="mt-4 space-y-2.5" aria-hidden="true">
          <div className="iv-esqueleto h-10 w-24 rounded-md" />
          <div className="iv-esqueleto h-3 w-3/4 rounded" />
          <div className="iv-esqueleto h-3 w-1/2 rounded" />
        </div>
      )}
      {data?.message && <p className="text-[13px] text-tinta-2 mt-3">{data.message}</p>}
      {done && data && data.avg_corr != null && (
        <div className="space-y-4 mt-4">
          <div>
            <p className="text-[12.5px] text-tinta-3">Correlación media</p>
            <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 mt-1">
            <span className="iv-cifra-hero text-[44px] text-tinta">{data.avg_corr}</span>
            <span className={`text-[13.5px] font-medium ${nivel.cls}`}>{nivel.txt}</span>
            {/* De cuántas. Con 83 valores en la Cartera y un techo de 25, decir solo "25
                acciones" hace leer como veredicto de toda la cartera lo que es de una
                parte. Las abiertas entran primero, que es lo que hace que la cifra siga
                significando algo aunque no quepan todas. */}
            <span className="text-[12.5px] text-tinta-3">
              · {data.n} acciones
              {data.truncado && data.total ? ` de ${data.total}` : ""}
            </span>
            </div>
          </div>
          {data.truncado && (
            <p className="text-[12px] text-tinta-3 leading-snug">
              Se analizan hasta {data.n} valores, y entran primero tus{" "}
              {data.en_cartera} posición(es) abiertas: cada acción descarga un año de
              histórico. Las que solo vigilas pueden quedarse fuera.
            </p>
          )}
          {(data.high || []).length > 0 ? (
            <div className="pt-4 border-t border-suave">
              <p className="text-[12.5px] text-tinta-3 mb-2">Se mueven casi igual (riesgo de bloque)</p>
              <ul className="border-t border-suave">
                {data.high.slice(0, 6).map((p) => (
                  <li key={`${p.a}-${p.b}`} className="flex items-center justify-between gap-3 py-2 border-b border-suave text-[13px]">
                    <span className="iv-cifra text-tinta">{p.a} <span className="text-tinta-3">↔</span> {p.b}</span>
                    <span className="iv-cifra text-baja">{p.corr}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-[13px] text-sube">Ningún par se mueve en exceso al unísono. Buena señal.</p>
          )}
        </div>
      )}
      <Boton variante={done ? "secundario" : "primario"} tamano="sm" className="mt-5" onClick={run} ocupado={loading}>
        {loading ? "Calculando…" : done ? "Recalcular" : "Analizar"}
      </Boton>
    </section>
  );
}

const RIESGO_STYLE = {
  BAJO:  { bg: "bg-sube/12",  text: "text-sube" },
  MEDIO: { bg: "bg-aviso/12", text: "text-aviso" },
  ALTO:  { bg: "bg-baja/12",       text: "text-baja" },
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
      aria-label="Categoría de riesgo de DEGIRO"
      className={`h-7 bg-tinta/[0.04] border border-suave rounded-md pl-1.5 pr-0.5 text-[12px] iv-cifra font-semibold cursor-pointer hover:border-medio ${TRANS} ${CAT_TONO[v] || "text-tinta-3"}`}
    >
      <option value="">—</option>
      {["A", "B", "C", "D"].map((c) => <option key={c} value={c}>{c}</option>)}
    </select>
  );
}

function RiesgoBadge({ value }) {
  if (!value) return <span className="text-tinta-3">—</span>;
  const key = value.toUpperCase();
  const s = RIESGO_STYLE[key] || { bg: "bg-superficie-alt", text: "text-tinta-2" };
  // Sin pastilla de fondo: el color del texto ya dice el nivel, y una fila con
  // mercado + riesgo + categoría eran tres chips seguidos compitiendo entre sí.
  return (
    <span className={`text-[12.5px] font-medium ${s.text}`}>
      {value.charAt(0).toUpperCase() + value.slice(1).toLowerCase()}
    </span>
  );
}

function BellToggle({ active, onClick, title }) {
  const t = title || (active ? "Alerta activa — clic para desactivar" : "Alerta inactiva — clic para activar");
  return (
    <button
      onClick={onClick}
      title={t}
      aria-label={t}
      aria-pressed={active}
      className={`inline-flex items-center justify-center w-7 h-7 shrink-0 rounded-md active:scale-90 transition-[color,background-color,transform] duration-150 ease-salida motion-reduce:transition-none ${active ? "text-aviso hover:bg-aviso/10" : "text-tinta-3 hover:text-tinta hover:bg-tinta/[0.06]"}`}
    >
      {active
        ? <Bell className="w-3.5 h-3.5" fill="currentColor" strokeWidth={1.75} aria-hidden="true" />
        : <BellOff className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" />}
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
      className={`w-full min-w-[4.5rem] h-7 bg-superficie border border-marca/60 rounded-md px-1.5 text-[13px] iv-cifra text-tinta text-right outline-none ring-[3px] ring-marca/20 ${className}`}
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
      role="button"
      tabIndex={0}
      onClick={() => { setDraft(value ?? ""); setEditing(true); }}
      onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setDraft(value ?? ""); setEditing(true); } }}
      // Subrayado punteado tenue siempre visible: en el móvil no hay hover y sin él
      // nada dice que la cifra se puede tocar para editarla.
      className={`cursor-text select-none tabular-nums rounded-[5px] -mx-1 px-1 underline decoration-dotted decoration-tinta-3/40 underline-offset-[5px] hover:decoration-transparent hover:bg-tinta/[0.07] hover:shadow-[0_0_0_1px_var(--borde-medio)] ${TRANS} ${!value && value !== 0 ? "text-tinta-3" : ""} ${className}`}
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
  // El lienzo (ancho y márgenes) lo pone App: aquí solo el ritmo vertical.
  const abrirAnadir = () => { setNewEntry(EMPTY); setShowAdd(true); };
  return (
    <div className="space-y-6 sm:space-y-8">

      {/* ── LECTURA ─────────────────────────────────────────────────────────
          Patrimonio, señales, distribución y posiciones. Va ARRIBA porque es a lo
          que se entra: antes la pantalla abría directamente con la tabla de quince
          columnas, que sirve para editar y no para enterarse de nada. La correlación
          entra en la fila de riesgo, junto a salud y distribución: es la misma
          pregunta —¿cuánto me puede caer de golpe?— vista desde otro lado. */}
      <CarteraCabecera
        entries={entries}
        onAnadir={() => setShowAdd(true)}
        onImportar={() => setShowImport(true)}
        onAnalizarCorrelacion={() =>
          document.getElementById("bloque-correlacion")?.scrollIntoView({ behavior: "smooth" })}
        correlacion={!loading && visible.length >= 2 ? <CorrelationCard /> : null}
      />

      {/* ── EDICIÓN ─────────────────────────────────────────────────────────── */}
      <section aria-labelledby="niveles-titulo" className="space-y-4 pt-2 sm:pt-4">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div className="min-w-0">
            <h2 id="niveles-titulo" className="text-[18px] font-semibold tracking-[-0.02em] text-tinta flex items-center gap-2.5">
              <SlidersHorizontal className="w-[18px] h-[18px] text-tinta-3" strokeWidth={1.75} aria-hidden="true" />
              Niveles y alertas
              {!loading && (
                <span className="iv-cifra text-[12px] font-medium text-tinta-2 h-[22px] px-2 inline-flex items-center rounded-md bg-tinta/[0.06]">
                  {visible.length}
                </span>
              )}
            </h2>
            <p className="text-[13px] text-tinta-3 mt-1.5 max-w-[70ch] leading-relaxed">
              Aquí se edita: toca cualquier valor. Activa la{" "}
              <Bell className="inline w-3.5 h-3.5 text-aviso -mt-0.5" fill="currentColor" strokeWidth={1.75} aria-label="campana" />{" "}
              en cada nivel para recibir alerta por Telegram y email cuando el precio lo alcance.
            </p>
          </div>
          <div className="flex gap-2 flex-wrap shrink-0">
            <Boton variante="fantasma" onClick={fetchEntries} aria-label="Refrescar">
              <RefreshCw className={cn(ICONO, loading && "animate-spin motion-reduce:animate-none")} strokeWidth={1.75} aria-hidden="true" />
              <span className="hidden sm:inline">Refrescar</span>
            </Boton>
            <Boton variante="secundario" onClick={() => setShowImport(true)}>
              <FileSpreadsheet className={ICONO} strokeWidth={1.75} aria-hidden="true" /> Importar Excel
            </Boton>
            <Boton variante="secundario" onClick={() => imageInputRef.current?.click()} disabled={importing}>
              <Camera className={ICONO} strokeWidth={1.75} aria-hidden="true" /> {importing ? "Leyendo…" : "Importar foto"}
            </Boton>
            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; doImportImage(f); }}
            />
            <Boton onClick={abrirAnadir}>
              <Plus className={ICONO} strokeWidth={2} aria-hidden="true" /> Añadir acción
            </Boton>
          </div>
        </div>

        {/* Sub-tabs (solo si hay más de un grupo) */}
        {GRUPOS.length > 1 && (
        <div className="flex items-center gap-1 bg-tinta/[0.05] border border-suave rounded-[10px] p-[3px] w-fit">
          {GRUPOS.map((g) => {
            const Icon = g.icon;
            const active = grupo === g.key;
            return (
              <button
                key={g.key}
                onClick={() => switchGrupo(g.key)}
                data-testid={`signals-tab-${g.key}`}
                className={`flex items-center gap-1.5 h-8 px-3 rounded-[7px] text-[13px] font-medium ${TRANS} ${
                  active ? "bg-superficie text-tinta shadow-[0_0_0_1px_var(--borde-medio)]" : "text-tinta-3 hover:text-tinta"
                }`}
              >
                <Icon className="w-3.5 h-3.5" strokeWidth={1.75} />
                {g.label}
                <span className="iv-cifra text-[11px] text-tinta-3">{countOf(g.key)}</span>
              </button>
            );
          })}
        </div>
        )}

        {/* Leyenda: el color ya no distingue los grupos de columnas (lo hace la
            cabecera); aquí solo queda lo que un icono no dice por sí mismo. */}
        <ul className="flex flex-wrap gap-x-5 gap-y-2 text-[12.5px] text-tinta-3" aria-label="Leyenda">
          <li className="flex items-center gap-1.5"><Bell className="w-3.5 h-3.5 text-aviso" fill="currentColor" strokeWidth={1.75} aria-hidden="true" /> Alerta activa</li>
          <li className="flex items-center gap-1.5"><BellOff className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" /> Alerta inactiva</li>
          <li className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-info inline-block" aria-hidden="true"></span> Nivel Deseado / Venta</li>
          <li className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-tinta-2 inline-block" aria-hidden="true"></span> Niveles de Compra</li>
          <li className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-aviso inline-block" aria-hidden="true"></span> Próximo nivel en tocarse</li>
        </ul>

        {/* Import panel */}
        {showImport && (
          <section className="iv-panel p-5 sm:p-6 space-y-4" aria-labelledby="importar-titulo">
            <CabeceraBloque icono={Upload} como="h2" id="importar-titulo"
                            derecha={
                              <Boton variante="fantasma" tamano="icono" onClick={() => { setShowImport(false); setImportText(""); }} aria-label="Cerrar">
                                <X className={ICONO} strokeWidth={1.75} />
                              </Boton>
                            }>
              Importar desde Excel
            </CabeceraBloque>
            <p className="text-[13px] text-tinta-2 leading-relaxed">
              Abre tu Excel, selecciona todas las celdas incluyendo cabecera y pégalas aquí (Ctrl+V).<br />
              Columnas reconocidas: <code className="iv-cifra text-[12px] text-info">Acción, Mercado, Ticker/ISIN, Nivel Deseado/Venta, Nivel 1–5, Riesgo, Sector, Posibles Ganancias</code>
            </p>
            <textarea
              aria-label="Datos pegados desde Excel"
              className={`w-full h-40 p-3 rounded-iv border border-suave bg-tinta/[0.04] text-[13px] iv-cifra text-tinta resize-none outline-none placeholder:text-tinta-3 hover:border-medio focus:border-marca/60 ${TRANS}`}
              placeholder={"Acción\tMercado\tTicker/ISIN\tNivel Deseado/Venta\tNivel 1\tNivel 2\tNivel 3\tNivel 4\tNivel 5 EXTRA\tRiesgo\tSector\nORACLE\tNYSE\tORCL\t300\t220\t200\t180\t160\tNO\tMEDIO\tTECH"}
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
            />
            <div className="flex gap-2">
              <Boton onClick={doImport} disabled={importing || !importText.trim()}>
                {importing ? "Importando…" : "Importar"}
              </Boton>
              <Boton variante="secundario" onClick={() => { setShowImport(false); setImportText(""); }}>Cancelar</Boton>
            </div>
          </section>
        )}

        {/* Add panel */}
        {showAdd && (
          <section className="iv-destacada p-5 sm:p-6 space-y-5" aria-labelledby="anadir-titulo">
            <CabeceraBloque icono={Plus} como="h2" id="anadir-titulo"
                            derecha={
                              <Boton variante="fantasma" tamano="icono" onClick={() => setShowAdd(false)} aria-label="Cerrar">
                                <X className={ICONO} strokeWidth={1.75} />
                              </Boton>
                            }>
              Nueva acción · Cartera
            </CabeceraBloque>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-3 gap-y-4">
              {ADD_FIELDS[grupo].map(({ key, label, placeholder }) => (
                <div key={key} className="flex flex-col gap-1.5 min-w-0">
                  <label htmlFor={`nueva-${key}`} className="text-[12.5px] font-medium text-tinta-2">{label}</label>
                  <input
                    id={`nueva-${key}`}
                    className={CAMPO}
                    placeholder={placeholder}
                    value={newEntry[key] ?? ""}
                    onChange={(e) => setNewEntry((p) => ({ ...p, [key]: e.target.value }))}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Boton onClick={addEntry}>Guardar</Boton>
              <Boton variante="secundario" onClick={() => setShowAdd(false)}>Cancelar</Boton>
            </div>
          </section>
        )}

        {/* Loading · esqueleto con la forma de lo que viene, no un texto suelto */}
        {loading && (
          <div role="status" aria-live="polite" className="iv-panel overflow-hidden">
            <span className="sr-only">Cargando señales…</span>
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="flex items-center gap-4 px-5 py-4 border-b border-suave last:border-b-0" aria-hidden="true">
                <div className="iv-esqueleto w-8 h-8 rounded-[9px] shrink-0" />
                <div className="space-y-2 w-32">
                  <div className="iv-esqueleto h-3 w-16 rounded" />
                  <div className="iv-esqueleto h-2.5 w-24 rounded" />
                </div>
                <div className="flex-1 hidden sm:flex justify-end gap-6">
                  {[0, 1, 2, 3, 4].map((j) => <div key={j} className="iv-esqueleto h-3 w-14 rounded" />)}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty */}
        {!loading && visible.length === 0 && (
          <div className="rounded-iv-lg border border-dashed border-medio text-center py-14 px-6">
            <span className="mx-auto mb-4 w-11 h-11 rounded-iv bg-tinta/[0.05] border border-suave flex items-center justify-center">
              <Bell className="w-5 h-5 text-tinta-3" strokeWidth={1.75} aria-hidden="true" />
            </span>
            <p className="text-[14.5px] font-semibold text-tinta">Sin acciones todavía</p>
            <p className="text-[13px] text-tinta-3 mt-1">Añade una acción o importa desde Excel</p>
            <div className="flex justify-center gap-2 mt-5 flex-wrap">
              <Boton onClick={abrirAnadir}>
                <Plus className={ICONO} strokeWidth={2} aria-hidden="true" /> Añadir acción
              </Boton>
              <Boton variante="secundario" onClick={() => setShowImport(true)}>
                <Upload className={ICONO} strokeWidth={1.75} aria-hidden="true" /> Importar Excel
              </Boton>
            </div>
          </div>
        )}

        {/* ════════════════ CARTERA ════════════════ */}
        {!loading && visible.length > 0 && <IdeasView entries={visible} saving={saving} updateField={updateField} deleteEntry={deleteEntry} setSymbol={setSymbol} onVendido={fetchEntries} />}

        <p className="text-[12px] text-tinta-3 text-center pt-2 max-w-[80ch] mx-auto leading-relaxed">
          Alertas solo en horario de mercado (9:30-16:00 ET) · 1 vez al día por nivel · Telegram + Email · Haz clic en cualquier valor para editarlo
        </p>
      </section>
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
  const ETQ = "text-[12.5px] font-medium text-tinta-2";

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-[2px] flex items-end sm:items-center justify-center z-50 sm:p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={`Vender ${entry.symbol}`}
           className="iv-entra bg-superficie border border-medio shadow-flotante rounded-t-[20px] sm:rounded-iv-lg p-5 sm:p-6 w-full sm:max-w-md max-h-[92vh] overflow-y-auto"
           onClick={(ev) => ev.stopPropagation()}>
        {!res ? (
          <>
            <div className="flex items-center justify-between gap-3 mb-1">
              <div className="flex items-center gap-3 min-w-0">
                <Monograma symbol={entry.symbol} />
                <h3 className="font-semibold text-[18px] tracking-[-0.02em] text-tinta">Vender {entry.symbol}</h3>
              </div>
              <Boton variante="fantasma" tamano="icono" onClick={onClose} aria-label="Cerrar"><X className={ICONO} strokeWidth={1.75} /></Boton>
            </div>
            <p className="text-[13px] text-tinta-2 mt-3 mb-5">
              Tienes <b className="iv-cifra text-tinta font-medium">{tiene}</b> acciones a un precio medio de <b className="iv-cifra text-tinta font-medium">{fmtP(entry.compra)}</b> ({divisa}).
            </p>
            <div className="space-y-4">
              <label className="block">
                <span className={ETQ}>Acciones vendidas</span>
                <input type="number" step="any" value={acciones} onChange={(ev) => setAcciones(ev.target.value)}
                       placeholder={String(tiene)} className={`${CAMPO} iv-cifra mt-1.5`} />
              </label>
              <label className="block">
                <span className={ETQ}>Precio de venta ({divisa})</span>
                <input type="number" step="any" value={precio} onChange={(ev) => setPrecio(ev.target.value)}
                       placeholder={entry.last_price ? String(entry.last_price) : "0.00"} className={`${CAMPO} iv-cifra mt-1.5`} />
              </label>
              <label className="block">
                <span className={ETQ}>Fecha de la venta</span>
                <input type="date" value={fecha} onChange={(ev) => setFecha(ev.target.value)}
                       className={`${CAMPO} iv-cifra mt-1.5`} />
              </label>
              {!entry.fecha_compra && divisa !== "EUR" && (
                <p className="text-[12.5px] text-aviso bg-aviso/[0.08] border border-aviso/20 rounded-iv px-3 py-2.5 leading-snug">
                  Esta posición no tiene <b>fecha de compra</b>, así que la ganancia en euros
                  saldrá aproximada. Rellénala en la Cartera para que sea exacta.
                </p>
              )}
            </div>
            {/* ANTES del botón: la pregunta que resuelve solo sirve mientras la venta
                todavía se puede no hacer. Después ya no es una decisión, es un apunte. */}
            <div className="mt-4">
              <RiesgoVenta symbol={entry.symbol} acciones={aNumero(acciones) || undefined} />
            </div>
            <Boton tamano="lg" className="w-full mt-5" onClick={enviar} ocupado={enviando}>
              {enviando ? "Calculando…" : "Registrar venta"}
            </Boton>
          </>
        ) : (
          <>
            <h3 className="font-semibold text-[18px] tracking-[-0.02em] mb-4 text-tinta">
              Venta registrada · {res.acciones} {entry.symbol}
            </h3>
            <dl className="text-[13.5px] [&>div+div]:border-t [&>div+div]:border-suave">
              <div className="flex justify-between gap-3 py-2.5"><dt className="text-tinta-2">Ganancia en {res.divisa}</dt>
                <dd className={`iv-cifra font-medium ${res.ganancia_divisa >= 0 ? "text-sube" : "text-baja"}`}>
                  {res.ganancia_divisa >= 0 ? "+" : ""}{res.ganancia_divisa} ({res.ganancia_pct}%)</dd></div>
              <div className="flex justify-between items-baseline gap-3 py-3">
                <dt className="text-tinta font-medium">Ganancia en EUROS</dt>
                <dd className={`iv-cifra-hero text-[26px] ${(res.ganancia_eur ?? 0) >= 0 ? "!text-sube" : "!text-baja"}`}>
                  {eur(res.ganancia_eur)}</dd></div>
              {res.efecto_divisa_eur != null && (
                <div className="flex justify-between gap-3 py-2.5 text-[12.5px]">
                  <dt className="text-tinta-2">De eso, por el tipo de cambio</dt>
                  <dd className="iv-cifra text-tinta">{eur(res.efecto_divisa_eur)}</dd></div>
              )}
            </dl>
            {!res.exacto && (
              <p className="text-[12.5px] text-aviso bg-aviso/[0.08] border border-aviso/20 rounded-iv px-3 py-2.5 leading-snug mt-3">
                Aproximado: falta el tipo de cambio del día de la compra.
              </p>
            )}
            <p className="text-[13px] text-tinta-2 pt-3">Te quedan <b className="iv-cifra text-tinta font-medium">{res.acciones_restantes}</b> acciones.</p>
            <Boton variante="secundario" tamano="lg" className="w-full mt-5" onClick={onClose}>Cerrar</Boton>
          </>
        )}
      </div>
    </div>
  );
}

const fmtAcciones = (v) => v != null && v !== "" ? Number(v).toLocaleString("es-ES", { maximumFractionDigits: 2 }) : "—";
const TH = "h-11 px-3 text-[12px] font-medium text-tinta-3 whitespace-nowrap bg-superficie border-b border-medio";

/** Una celda de nivel: precio editable + campana, y debajo la distancia al precio.
 *  El SIGUIENTE en tocarse lleva un fondo ámbar suave y la marca ◀; el resto va en
 *  tinta neutra: un nivel de compra no es una subida, así que no se pinta de verde. */
function CeldaNivel({ e, n, nextN, updateField }) {
  const val = e[`nivel${n}`];
  const alertKey = `alert_nivel${n}`;
  const alertOn = e[alertKey] !== false;
  const d = nivelDist(e, n);
  const isNext = n === nextN;
  return (
    <td className={cn("px-1.5 py-2 align-middle", n === 1 && "border-l border-suave")}>
      <div className={cn("rounded-[9px] pl-2 pr-0.5 py-1 transition-colors duration-150",
                         isNext && "bg-aviso/[0.1] shadow-[inset_0_0_0_1px_rgb(var(--iv-aviso)/0.28)]")}>
        <div className="flex items-center justify-end gap-0.5">
          <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)}
                        className={cn("iv-cifra text-[13px] font-medium", isNext ? "text-aviso" : "text-tinta")} />
          <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
        </div>
        {d != null && (
          <p className={cn("iv-cifra text-[11px] text-right pr-[30px] leading-tight", isNext ? "text-aviso font-medium" : "text-tinta-3")}>
            {isNext ? "◀ " : ""}{d >= 0 ? "+" : ""}{d.toFixed(1)}%
          </p>
        )}
      </div>
    </td>
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
      {/* MÓVIL · una ficha por acción. Arriba quién es y a cuánto cotiza; debajo la
          posición en tres columnas; luego el objetivo; y los niveles PLEGADOS tras una
          línea que ya dice lo importante (cuál es el siguiente y a qué distancia). Con
          sesenta acciones, desplegarlos todos convertía la pantalla en un pergamino. */}
      <div className="lg:hidden space-y-3">
        {entries.map((e) => {
          const nextN = nextNivelKey(e);
          const niveles = [1, 2, 3, 4, 5].filter((n) => e[`nivel${n}`] != null);
          const dNext = nextN ? nivelDist(e, nextN) : null;
          return (
          <article key={e.id} aria-label={e.symbol}
                   className={cn("iv-panel overflow-hidden", !e.active && "opacity-50")}>
            {/* Cabecera: quién es · precio */}
            <div className="flex items-start justify-between gap-3 p-4 pb-3">
              <div className="flex items-start gap-3 min-w-0">
                <Monograma symbol={e.symbol} />
                <div className="min-w-0">
                  <button type="button" className={`text-[15px] font-semibold text-tinta leading-tight hover:text-marca ${TRANS}`}
                          onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</button>
                  <p className="text-[12.5px] text-tinta-3 truncate">{e.name || "—"}</p>
                </div>
              </div>
              <div className="text-right shrink-0">
                <p className="sr-only">Precio actual</p>
                <p className="iv-cifra font-medium text-tinta text-[15px] leading-tight">{fmtP(e.last_price)}</p>
                <ExtendedBadge entry={e} />
              </div>
            </div>
            {/* Metadatos en una línea: mercado · sector · riesgo · categoría DEGIRO */}
            <div className="flex items-center gap-x-2.5 gap-y-1 flex-wrap px-4 pb-3 text-[12px] text-tinta-3">
              {e.mercado && <span>{e.mercado}</span>}
              {e.sector && <span className="truncate max-w-[40%]">· {e.sector}</span>}
              {e.riesgo && <span>·</span>}
              <RiesgoBadge value={e.riesgo} />
              <span className="ml-auto flex items-center gap-1.5">
                <span>Cat.</span>
                <CategoriaDegiro value={e.categoria_degiro}
                                 onChange={(v) => updateField(e.id, "categoria_degiro", v)} />
              </span>
            </div>

            {/* Posición + P&L (#20) */}
            <dl className="grid grid-cols-[1fr_1fr_auto] gap-3 px-4 py-3 border-t border-suave bg-tinta/[0.02]">
              <div className="min-w-0">
                <dt className="text-[12px] text-tinta-3">Compra</dt>
                <dd className="mt-0.5"><EditableCell value={e.compra} onChange={(v) => updateField(e.id, "compra", v)} className="iv-cifra text-[13.5px] font-medium text-tinta" /></dd>
              </div>
              <div className="min-w-0">
                <dt className="text-[12px] text-tinta-3">Nº acc.</dt>
                <dd className="mt-0.5"><EditableCell value={e.acciones} onChange={(v) => updateField(e.id, "acciones", v)} format={fmtAcciones} className="iv-cifra text-[13.5px] font-medium text-tinta" /></dd>
              </div>
              <div className="text-right min-w-0">
                <dt className="text-[12px] text-tinta-3">P&amp;L</dt>
                <dd className="mt-0.5"><PnlText abs={pnlAbs(e)} pct={pnlPct(e)} eur={pnlEur.porSymbol[(e.symbol || "").toUpperCase()]} tasa={pnlEur.tasaUSD} /></dd>
              </div>
            </dl>

            {/* Deseado / venta */}
            <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-suave">
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-1.5 h-1.5 rounded-full bg-info shrink-0" aria-hidden="true" />
                <p className="text-[13px] text-tinta-2">Deseado / Venta</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {e.posibles_ganancias != null && <span className="iv-cifra text-[12px] text-sube">{fmtPct(e.posibles_ganancias)}</span>}
                <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} className="iv-cifra font-medium text-info text-[13.5px]" />
                {/* El estado que se NIEGA debe ser el mismo que se PINTA. Con `!e.alert_deseado`, una
                    fila antigua sin el campo (undefined) se veía encendida (undefined !== false) pero al
                    pulsar mandaba `!undefined` = true: seguía encendida y el primer clic no hacía nada. */}
                <BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", e.alert_deseado === false)} />
              </div>
            </div>

            {/* Niveles de compra: plegados tras su resumen. */}
            {niveles.length > 0 && (
              <details className="group/niv border-t border-suave">
                <summary className={`flex items-center justify-between gap-3 px-4 min-h-[48px] cursor-pointer list-none [&::-webkit-details-marker]:hidden active:bg-tinta/[0.03] ${TRANS}`}>
                  <span className="flex items-center gap-2 min-w-0 text-[13px]">
                    <span className="w-1.5 h-1.5 rounded-full bg-tinta-2 shrink-0" aria-hidden="true" />
                    <span className="text-tinta-2 whitespace-nowrap">Niveles<span className="hidden min-[400px]:inline"> de compra</span></span>
                    <span className="iv-cifra text-[12px] text-tinta-3">· {niveles.length}</span>
                  </span>
                  <span className="flex items-center gap-2 shrink-0">
                    {nextN && (
                      <span className="iv-cifra text-[12px] text-aviso">
                        ◀ N{nextN} {fmtP(e[`nivel${nextN}`])}{dNext != null ? ` · ${dNext >= 0 ? "+" : ""}${dNext.toFixed(1)}%` : ""}
                      </span>
                    )}
                    <ChevronDown className="w-4 h-4 text-tinta-3 transition-transform duration-200 ease-salida group-open/niv:rotate-180 motion-reduce:transition-none" strokeWidth={1.75} aria-hidden="true" />
                  </span>
                </summary>
                {/* Filas, no cajas. Precio y distancia alineados a la derecha en
                    columna para leerlos en vertical; el siguiente en tocarse, en ámbar
                    y con su marca ◀. */}
                <ul className="px-4 pb-3 grid sm:grid-cols-2 sm:gap-x-6">
                  {[1,2,3,4,5].map((n) => {
                    const val = e[`nivel${n}`];
                    const alertKey = `alert_nivel${n}`;
                    const alertOn = e[alertKey] !== false;
                    if (val == null) return null;
                    const d = nivelDist(e, n);
                    const isNext = n === nextN;
                    return (
                      <li key={n} className={cn("grid grid-cols-[4.5rem_1fr_auto_auto] items-center gap-x-3 min-h-[44px] -mx-2 px-2 rounded-[9px]",
                                                isNext && "bg-aviso/[0.1]")}>
                        <span className={cn("text-[12.5px] font-medium", isNext ? "text-aviso" : "text-tinta-3")}>Nivel {n}{isNext ? " ◀" : ""}</span>
                        <span className="text-right">
                          <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)}
                                        className={cn("iv-cifra font-medium text-[13.5px]", isNext ? "text-aviso" : "text-tinta")} />
                        </span>
                        <span className={cn("iv-cifra text-[12px] text-right w-14", isNext ? "text-aviso" : "text-tinta-3")}>
                          {d != null ? `${d >= 0 ? "+" : ""}${d.toFixed(1)}%` : ""}
                        </span>
                        <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
                      </li>
                    );
                  })}
                </ul>
              </details>
            )}

            {/* Acciones de la ficha, abajo y separadas: borrar no compite con el precio. */}
            <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-suave">
              <span className="text-[12px] text-tinta-3" aria-live="polite">
                {saving[e.id] && <span className="animate-pulse motion-reduce:animate-none">guardando…</span>}
              </span>
              <div className="flex items-center gap-1.5">
                {/* Solo tiene sentido vender lo que se tiene. Sin acciones, el botón
                    llevaría a un error del servidor en vez de a algo útil. */}
                {Number(e.acciones) > 0 && (
                  <Boton variante="secundario" tamano="sm" onClick={() => setVendiendo(e)} title="Registrar una venta">
                    <Euro className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" /> Vender
                  </Boton>
                )}
                <Boton variante="fantasma" tamano="icono" onClick={() => deleteEntry(e.id)} aria-label={`Eliminar ${e.symbol}`} title="Eliminar"
                       className="w-11 h-11 hover:text-baja hover:bg-baja/10">
                  <Trash2 className={ICONO} strokeWidth={1.75} />
                </Boton>
              </div>
            </div>
          </article>
          );
        })}
      </div>

      {/* ESCRITORIO · tabla con cabecera fija y las dos primeras columnas fijas. El
          contenedor tiene su propio alto y su propio desplazamiento: con sesenta filas
          la cabecera «Nivel 3» ya no estaba en pantalla cuando se editaba la fila 40. */}
      <div className="hidden lg:block iv-panel overflow-auto max-h-[calc(100vh-140px)] overscroll-contain">
        <table className="w-full text-[13px] border-separate border-spacing-0" style={{ minWidth: 1080 }}>
          <thead className="sticky top-0 z-30">
            <tr className="text-left">
              <th scope="col" title="Monitorización activa" className={cn(TH, "w-[44px] min-w-[44px] max-w-[44px] px-0 sticky left-0 z-40")}><Zap className="w-3.5 h-3.5 mx-auto" strokeWidth={1.75} aria-label="Monitorización activa" /></th>
              <th scope="col" className={cn(TH, "sticky left-11 z-40 border-r border-r-suave")}>Acción</th>
              <th scope="col" className={cn(TH, "text-right")}>Precio</th>
              <th scope="col" className={cn(TH, "text-right")} title="Nº de acciones · precio medio de compra">Posición</th>
              <th scope="col" className={cn(TH, "text-right")}>P&amp;L</th>
              <th scope="col" className={cn(TH, "text-right border-l border-l-suave")}>
                <span className="inline-flex items-center gap-1.5 text-info"><span className="w-1.5 h-1.5 rounded-full bg-info" aria-hidden="true" />Deseado</span>
              </th>
              {[1,2,3,4,5].map((n) => (
                <th key={n} scope="col" className={cn(TH, "text-right pr-[38px]", n === 1 && "border-l border-l-suave")}>Nivel {n}</th>
              ))}
              <th scope="col" className={cn(TH, "border-l border-l-suave")}>
                Riesgo <span className="text-tinta-3/80" title="Categoría de riesgo de DEGIRO (A-D). Determina cuánto margen libera vender esta acción.">· Cat.</span>
              </th>
              <th className={cn(TH, "w-10")}><span className="sr-only">Eliminar</span></th>
            </tr>
          </thead>
          <tbody>
            {/* Sector y Ganancia no salen aquí: son de SOLO LECTURA en esta tabla y con
                dieciocho columnas obligaban a scroll horizontal. Se siguen viendo en la
                vista de móvil y se editan en el formulario, así que no se pierde nada —y
                el sector sigue alimentando el modelo de riesgo igual, esté a la vista o
                no. */}
            {/* Sin cebreado ni columnas teñidas: filete entre filas y resalte al pasar. */}
            {entries.map((e) => {
              const nextN = nextNivelKey(e);
              // Fondo OPACO en las celdas fijas: translúcido dejaba ver por debajo lo
              // que pasa al lado al desplazarse a lo ancho.
              const FIJA = `bg-superficie group-hover:bg-[rgb(var(--iv-superficie-2))] ${TRANS}`;
              return (
              <tr key={e.id} className={cn("group [&>td]:border-b [&>td]:border-suave last:[&>td]:border-b-0 hover:bg-tinta/[0.025]", TRANS, !e.active && "opacity-40")}>
                {/* Las dos primeras columnas van fijas: la tabla tiene muchas columnas y
                    desborda a lo ancho, así que al desplazarse quedaban treinta filas de
                    precios y niveles sin saber de qué acción eran. */}
                <td className={cn("w-[44px] min-w-[44px] max-w-[44px] px-0 py-3 text-center sticky left-0 z-10", FIJA)}>
                  <input type="checkbox" checked={e.active} onChange={(ev) => updateField(e.id, "active", ev.target.checked)} className="w-4 h-4 cursor-pointer accent-marca align-middle" title={e.active ? "Monitorización activa" : "Monitorización pausada"} aria-label={`Monitorización de ${e.symbol}`} />
                </td>
                <td className={cn("pl-3 pr-4 py-3 whitespace-nowrap sticky left-11 z-10 border-r border-suave", FIJA)}>
                  <div className="flex items-center gap-3">
                    <Monograma symbol={e.symbol} tamano="sm" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <button type="button" className={`text-[13.5px] font-semibold text-tinta hover:text-marca leading-tight ${TRANS}`} onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</button>
                        {saving[e.id] && <span className="w-1.5 h-1.5 rounded-full bg-marca animate-pulse motion-reduce:animate-none" aria-label="guardando" />}
                      </div>
                      <p className="text-[12px] text-tinta-3 truncate max-w-[130px]" title={e.name || undefined}>
                        {[e.name, e.mercado].filter(Boolean).join(" · ") || "—"}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-3 text-right whitespace-nowrap">
                  <span className="iv-cifra font-medium text-tinta text-[13.5px]">{fmtP(e.last_price)}</span>
                  <ExtendedBadge entry={e} />
                </td>
                <td className="px-3 py-3 text-right whitespace-nowrap">
                  <div className="iv-cifra text-[13px] text-tinta">
                    <EditableCell value={e.acciones} onChange={(v) => updateField(e.id, "acciones", v)} isNumber format={fmtAcciones} className="iv-cifra text-[13px] text-tinta" />
                    <span className="text-tinta-3 text-[11.5px]"> acc.</span>
                  </div>
                  <div className="iv-cifra text-[12px] text-tinta-3 mt-0.5">
                    <span className="text-[11px]">a </span>
                    <EditableCell value={e.compra} onChange={(v) => updateField(e.id, "compra", v)} className="iv-cifra text-[12px] text-tinta-2" />
                  </div>
                </td>
                <td className="px-3 py-3 text-right whitespace-nowrap">
                  <PnlText abs={pnlAbs(e)} pct={pnlPct(e)} eur={pnlEur.porSymbol[(e.symbol || "").toUpperCase()]} tasa={pnlEur.tasaUSD} />
                </td>
                <td className="px-2 py-3 border-l border-suave">
                  <div className="flex items-center justify-end gap-0.5">
                    <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} className="iv-cifra text-[13px] font-medium text-info" />
                    {/* El estado que se NIEGA debe ser el mismo que se PINTA. Con `!e.alert_deseado`, una
                        fila antigua sin el campo (undefined) se veía encendida (undefined !== false) pero al
                        pulsar mandaba `!undefined` = true: seguía encendida y el primer clic no hacía nada. */}
                    <BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", e.alert_deseado === false)} />
                  </div>
                  {e.posibles_ganancias != null && (
                    <p className="iv-cifra text-[11px] text-sube text-right pr-[30px] leading-tight" title="Posibles ganancias">{fmtPct(e.posibles_ganancias)}</p>
                  )}
                </td>
                {[1,2,3,4,5].map((n) => (
                  <CeldaNivel key={n} e={e} n={n} nextN={nextN} updateField={updateField} />
                ))}
                <td className="px-3 py-3 whitespace-nowrap border-l border-suave">
                  <div className="flex items-center gap-2">
                    <span className="w-12"><RiesgoBadge value={e.riesgo} /></span>
                    <CategoriaDegiro value={e.categoria_degiro} onChange={(v) => updateField(e.id, "categoria_degiro", v)} />
                  </div>
                </td>
                <td className="px-2 py-3 text-center">
                  {/* Oculto hasta pasar por la fila, pero visible al llegar con el teclado. */}
                  <button onClick={() => deleteEntry(e.id)} aria-label={`Eliminar ${e.symbol}`}
                          className="inline-flex items-center justify-center w-8 h-8 rounded-md text-tinta-3 hover:text-baja hover:bg-baja/10 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-[color,background-color,opacity] duration-150 ease-salida motion-reduce:transition-none" title="Eliminar"><Trash2 className="w-3.5 h-3.5" strokeWidth={1.75} /></button>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {vendiendo && (
        <DialogoVenta entry={vendiendo} onClose={() => setVendiendo(null)} onHecho={onVendido} />
      )}
    </>
  );
}
