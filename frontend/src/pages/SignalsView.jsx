import React, { useState, useEffect, useRef, useMemo } from "react";
import { Bell, BellSlash, Trash, Plus, X, UploadSimple, ArrowClockwise, Lightning, Camera, CurrencyEur, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { aNumero } from "../lib/format";
import RiesgoVenta from "../components/RiesgoVenta";
import CarteraCabecera from "../components/CarteraCabecera";

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

// ── estilos compartidos (solo presentación) ──────────────────────────────────
// Transición corta de color/borde; se apaga con «reducir movimiento».
const TRANS = "transition-colors duration-150 ease-out motion-reduce:transition-none";
const BOTON_SEC = `inline-flex items-center gap-1.5 px-3 py-2 rounded-iv border border-linea-fuerte text-sm text-tinta-2 hover:border-marca hover:text-marca active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none transition-[color,border-color,transform] duration-150 ease-out motion-reduce:transition-none`;
const BOTON_PRI = "inline-flex items-center gap-1.5 px-4 py-2 rounded-iv bg-marca text-marca-tinta text-sm font-semibold hover:bg-marca/90 active:scale-[0.98] disabled:opacity-50 transition-[background-color,transform] duration-150 ease-out motion-reduce:transition-none";


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
          className={`text-[11px] font-mono tabular-nums ${dayUp ? "text-sube" : "text-baja"}`}
          title="Variación sesión regular vs cierre anterior"
        >
          {dayUp ? "+" : ""}{dailyPct.toFixed(2)}% hoy
        </div>
      )}
      {ext && (
        <div
          className={`text-[11px] font-mono tabular-nums ${ahUp ? "text-sube" : "text-baja"}`}
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
      <span className={`font-mono tabular-nums font-bold ${size === "sm" ? "text-sm" : "text-base"} ${color}`}>
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
        <span className="font-mono tabular-nums text-[11px] text-tinta-2">
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

   Con el rediseño dark fintech la paleta se rehace sobre la marca nueva —naranja,
   verde neón, azul, rosa-rojo— en tonos medios que siguen viéndose en los dos temas.
   `CarteraCabecera` usa los siete primeros: tienen que coincidir. */
const SECTOR_COLORS = [
  "#f08c1a",  // naranja de la marca
  "#2fbf8a",  // verde
  "#4f8ff0",  // azul
  "#ef5a7a",  // rosa-rojo
  "#2bb3e6",  // celeste
  "#9b7bf0",  // violeta
  "#8a8fa3",  // pizarra
  "#e06aa8",  // rosa
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
    <section className="iv-panel p-5" aria-labelledby="correlacion-titulo" aria-busy={loading}>
      <div className="flex items-center justify-between gap-3 mb-1.5">
        <h2 id="correlacion-titulo" className="iv-etiqueta">Correlación (concentración oculta)</h2>
        <button onClick={run} disabled={loading}
          className={done ? `${BOTON_SEC} py-1.5 text-etiqueta` : `${BOTON_PRI} px-3 py-1.5 text-etiqueta`}>
          {loading ? "Calculando…" : done ? "Recalcular" : "Analizar"}
        </button>
      </div>
      {!done && !loading && (
        <p className="text-apoyo text-tinta-2 max-w-[75ch] leading-relaxed">Mide si tus acciones se mueven a la vez (aunque sean de sectores distintos). Si están muy correlacionadas, una caída del mercado te afecta a todas por igual.</p>
      )}
      {data?.message && <p className="text-apoyo text-tinta-2 mt-1">{data.message}</p>}
      {done && data && data.avg_corr != null && (
        <div className="space-y-3 mt-2">
          <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="iv-cifra font-bold text-2xl leading-none text-tinta">{data.avg_corr}</span>
            <span className={`text-sm font-semibold ${nivel.cls}`}>{nivel.txt}</span>
            {/* De cuántas. Con 83 valores en la Cartera y un techo de 25, decir solo "25
                acciones" hace leer como veredicto de toda la cartera lo que es de una
                parte. Las abiertas entran primero, que es lo que hace que la cifra siga
                significando algo aunque no quepan todas. */}
            <span className="text-etiqueta text-tinta-3">
              · {data.n} acciones
              {data.truncado && data.total ? ` de ${data.total}` : ""}
            </span>
          </div>
          {data.truncado && (
            <p className="text-etiqueta text-tinta-3 leading-snug max-w-[75ch]">
              Se analizan hasta {data.n} valores, y entran primero tus{" "}
              {data.en_cartera} posición(es) abiertas: cada acción descarga un año de
              histórico. Las que solo vigilas pueden quedarse fuera.
            </p>
          )}
          {(data.high || []).length > 0 ? (
            <div>
              <p className="iv-etiqueta mb-1.5">Se mueven casi igual (riesgo de bloque)</p>
              <ul className="flex flex-wrap gap-1.5">
                {data.high.slice(0, 6).map((p) => (
                  <li key={`${p.a}-${p.b}`} className="iv-cifra text-etiqueta px-2 py-0.5 rounded-iv-sm border border-baja/30 bg-baja/10 text-baja">
                    {p.a} ↔ {p.b} · {p.corr}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-apoyo text-sube">Ningún par se mueve en exceso al unísono. Buena señal.</p>
          )}
        </div>
      )}
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
      className={`bg-transparent border border-linea rounded-iv-sm px-1 py-0.5 text-xs font-mono font-bold cursor-pointer hover:border-linea-fuerte ${TRANS} ${CAT_TONO[v] || "text-tinta-3"}`}
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
    <span className={`iv-etiqueta font-semibold ${s.text}`}>
      {value}
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
      className={`p-1.5 -m-0.5 rounded-iv-sm active:scale-90 transition-[color,transform] duration-150 ease-out motion-reduce:transition-none ${active ? "text-aviso hover:text-aviso/80" : "text-tinta-3 hover:text-tinta"}`}
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
      className={`w-full min-w-[4.5rem] bg-superficie-alt border border-marca/60 rounded-iv-sm px-1.5 py-0.5 text-sm text-tinta outline-none ring-2 ring-marca/20 ${className}`}
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
      className={`cursor-pointer select-none tabular-nums underline decoration-dotted decoration-tinta-3/40 underline-offset-4 hover:decoration-current ${TRANS} ${!value && value !== 0 ? "text-tinta-3" : ""} ${className}`}
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

      {/* ── LECTURA ─────────────────────────────────────────────────────────
          Patrimonio, señales, distribución y posiciones. Va ARRIBA porque es a lo
          que se entra: antes la pantalla abría directamente con la tabla de quince
          columnas, que sirve para editar y no para enterarse de nada. */}
      <CarteraCabecera
        entries={entries}
        onAnadir={() => setShowAdd(true)}
        onImportar={() => setShowImport(true)}
        onAnalizarCorrelacion={() =>
          document.getElementById("bloque-correlacion")?.scrollIntoView({ behavior: "smooth" })}
      />

      {/* ── EDICIÓN ─────────────────────────────────────────────────────────── */}
      <div className="iv-seccion !mb-0 pt-2 sm:pt-4">
        <span className="iv-etiqueta tracking-[0.18em] text-tinta-2">Niveles y alertas</span>
        <span className="text-etiqueta text-tinta-3 whitespace-nowrap hidden sm:inline">
          Aquí se edita: toca cualquier valor
        </span>
      </div>

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-apoyo text-tinta-2 max-w-[62ch] leading-relaxed">
          Activa la <Bell size={13} weight="fill" className="inline text-aviso mb-px" aria-label="campana" /> en cada nivel para recibir alerta por Telegram y email cuando el precio lo alcance.
        </p>
        <div className="flex gap-2 flex-wrap">
          <button onClick={fetchEntries} className={BOTON_SEC}>
            <ArrowClockwise size={14} aria-hidden="true" className={loading ? "animate-spin motion-reduce:animate-none" : ""} /> Refrescar
          </button>
          <button onClick={() => setShowImport(true)} className={BOTON_SEC}>
            <UploadSimple size={14} aria-hidden="true" /> Importar Excel
          </button>
          <button onClick={() => imageInputRef.current?.click()} disabled={importing} className={BOTON_SEC}>
            <Camera size={14} aria-hidden="true" /> {importing ? "Leyendo…" : "Importar foto"}
          </button>
          <input
            ref={imageInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; doImportImage(f); }}
          />
          <button onClick={() => { setNewEntry(EMPTY); setShowAdd(true); }} className={BOTON_PRI}>
            <Plus size={14} weight="bold" aria-hidden="true" /> Añadir acción
          </button>
        </div>
      </div>

      {/* Sub-tabs (solo si hay más de un grupo) */}
      {GRUPOS.length > 1 && (
      <div className="flex items-center gap-1 bg-superficie border border-linea rounded-iv p-1 w-fit">
        {GRUPOS.map((g) => {
          const Icon = g.icon;
          const active = grupo === g.key;
          return (
            <button
              key={g.key}
              onClick={() => switchGrupo(g.key)}
              data-testid={`signals-tab-${g.key}`}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-iv text-sm font-medium transition-colors ${
                active ? "bg-marca text-marca-tinta" : "text-tinta-3 hover:text-tinta dark:hover:text-tinta"
              }`}
            >
              <Icon size={15} weight="bold" />
              {g.label}
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded-full ${active ? "bg-superficie/20" : "bg-superficie-alt"}`}>{countOf(g.key)}</span>
            </button>
          );
        })}
      </div>
      )}

      {/* Resumen de cartera: P&L total + diversificación (#20 + #21) */}

      {/* Correlación de la cartera (#22) */}
      <div id="bloque-correlacion" />
      {!loading && visible.length >= 2 && <CorrelationCard />}

      {/* Legend */}
      <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-etiqueta text-tinta-2" aria-label="Leyenda">
        <li className="flex items-center gap-1.5"><Bell size={12} weight="fill" className="text-aviso" aria-hidden="true" /> Alerta activa</li>
        <li className="flex items-center gap-1.5"><BellSlash size={12} className="text-tinta-3" aria-hidden="true" /> Alerta inactiva</li>
        <li className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-info/15 border border-info/50 inline-block" aria-hidden="true"></span> Nivel Deseado / Venta</li>
        <li className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-sube/15 border border-sube/50 inline-block" aria-hidden="true"></span> Niveles de Compra</li>
      </ul>

      {/* Import panel */}
      {showImport && (
        <section className="iv-panel border-info/40 p-5 space-y-3" aria-labelledby="importar-titulo">
          <div className="flex items-center justify-between">
            <h2 id="importar-titulo" className="text-sm font-semibold text-tinta">Importar desde Excel</h2>
            <button onClick={() => { setShowImport(false); setImportText(""); }} aria-label="Cerrar"
                    className={`p-1 rounded-iv-sm text-tinta-3 hover:text-tinta ${TRANS}`}><X size={16} /></button>
          </div>
          <p className="text-apoyo text-tinta-2 leading-relaxed">
            Abre tu Excel, selecciona todas las celdas incluyendo cabecera y pégalas aquí (Ctrl+V).<br />
            Columnas reconocidas: <code className="iv-cifra text-etiqueta text-info">Acción, Mercado, Ticker/ISIN, Nivel Deseado/Venta, Nivel 1–5, Riesgo, Sector, Posibles Ganancias</code>
          </p>
          <textarea
            aria-label="Datos pegados desde Excel"
            className={`w-full h-40 p-3 rounded-iv border border-linea bg-fondo text-sm font-mono text-tinta resize-none outline-none placeholder:text-tinta-3 focus:border-marca ${TRANS}`}
            placeholder={"Acción\tMercado\tTicker/ISIN\tNivel Deseado/Venta\tNivel 1\tNivel 2\tNivel 3\tNivel 4\tNivel 5 EXTRA\tRiesgo\tSector\nORACLE\tNYSE\tORCL\t300\t220\t200\t180\t160\tNO\tMEDIO\tTECH"}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
          />
          <div className="flex gap-2">
            {/* Antes: texto oscuro (marca-tinta) sobre un azul al 10 %, ilegible en oscuro. */}
            <button onClick={doImport} disabled={importing || !importText.trim()} className={BOTON_PRI}>
              {importing ? "Importando…" : "Importar"}
            </button>
            <button onClick={() => { setShowImport(false); setImportText(""); }} className={BOTON_SEC}>Cancelar</button>
          </div>
        </section>
      )}

      {/* Add panel */}
      {showAdd && (
        <section className="iv-panel border-marca/40 p-5 space-y-4" aria-labelledby="anadir-titulo">
          <div className="flex items-center justify-between">
            <h2 id="anadir-titulo" className="text-sm font-semibold text-tinta">Nueva acción · Cartera</h2>
            <button onClick={() => setShowAdd(false)} aria-label="Cerrar"
                    className={`p-1 rounded-iv-sm text-tinta-3 hover:text-tinta ${TRANS}`}><X size={16} /></button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-3 gap-y-3.5">
            {ADD_FIELDS[grupo].map(({ key, label, placeholder }) => (
              <div key={key} className="flex flex-col gap-1 min-w-0">
                <label htmlFor={`nueva-${key}`} className="text-etiqueta text-tinta-2">{label}</label>
                <input
                  id={`nueva-${key}`}
                  className={`border border-linea rounded-iv px-2.5 py-1.5 text-sm text-tinta bg-fondo outline-none placeholder:text-tinta-3 hover:border-linea-fuerte focus:border-marca focus:ring-2 focus:ring-marca/20 ${TRANS}`}
                  placeholder={placeholder}
                  value={newEntry[key] ?? ""}
                  onChange={(e) => setNewEntry((p) => ({ ...p, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={addEntry} className={BOTON_PRI}>Guardar</button>
            <button onClick={() => setShowAdd(false)} className={BOTON_SEC}>Cancelar</button>
          </div>
        </section>
      )}

      {/* Loading · esqueleto con la forma de lo que viene, no un texto suelto */}
      {loading && (
        <div role="status" aria-live="polite" className="space-y-3">
          <span className="sr-only">Cargando señales…</span>
          {[0, 1, 2].map((i) => (
            <div key={i} className="iv-panel p-5 space-y-3 animate-pulse motion-reduce:animate-none" aria-hidden="true">
              <div className="flex justify-between">
                <div className="h-4 w-24 rounded bg-superficie-alt" />
                <div className="h-4 w-16 rounded bg-superficie-alt" />
              </div>
              <div className="h-3 w-2/3 rounded bg-superficie-alt" />
            </div>
          ))}
          <p className="text-center text-etiqueta text-tinta-3" aria-hidden="true">Cargando señales…</p>
        </div>
      )}

      {/* Empty */}
      {!loading && visible.length === 0 && (
        <div className="rounded-iv-lg border border-dashed border-linea-fuerte text-center py-14 px-6">
          <p className="mb-3 flex justify-center"><Bell size={28} className="text-tinta-3" aria-hidden="true" /></p>
          <p className="text-cuerpo font-semibold text-tinta">Sin acciones todavía</p>
          <p className="text-apoyo text-tinta-3 mt-1">Añade una acción o importa desde Excel</p>
          <div className="flex justify-center gap-2 mt-4 flex-wrap">
            <button onClick={() => { setNewEntry(EMPTY); setShowAdd(true); }} className={BOTON_PRI}>
              <Plus size={14} weight="bold" aria-hidden="true" /> Añadir acción
            </button>
            <button onClick={() => setShowImport(true)} className={BOTON_SEC}>
              <UploadSimple size={14} aria-hidden="true" /> Importar Excel
            </button>
          </div>
        </div>
      )}

      {/* ════════════════ CARTERA ════════════════ */}
      {!loading && visible.length > 0 && <IdeasView entries={visible} saving={saving} updateField={updateField} deleteEntry={deleteEntry} setSymbol={setSymbol} onVendido={fetchEntries} />}

      <p className="text-etiqueta text-tinta-3 text-center pb-2 max-w-[80ch] mx-auto leading-relaxed">
        Alertas solo en horario de mercado (9:30-16:00 ET) · 1 vez al día por nivel · Telegram + Email · Haz clic en cualquier valor para editarlo
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
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={`Vender ${entry.symbol}`}
           className="iv-panel border-linea-fuerte p-5 w-full max-w-md max-h-[90vh] overflow-y-auto shadow-2xl" onClick={(ev) => ev.stopPropagation()}>
        {!res ? (
          <>
            <div className="flex items-center justify-between mb-1">
              <h3 className="font-bold text-lg text-tinta">Vender {entry.symbol}</h3>
              <button onClick={onClose} aria-label="Cerrar" className={`p-1 rounded-iv-sm text-tinta-3 hover:text-tinta ${TRANS}`}><X size={18} /></button>
            </div>
            <p className="text-xs text-tinta-2 mb-4">
              Tienes <b>{tiene}</b> acciones a un precio medio de <b>{fmtP(entry.compra)}</b> ({divisa}).
            </p>
            <div className="space-y-3">
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider text-tinta-2">Acciones vendidas</span>
                <input type="number" step="any" value={acciones} onChange={(ev) => setAcciones(ev.target.value)}
                       placeholder={String(tiene)} className="w-full mt-1 border rounded px-2 py-1.5 font-mono bg-superficie-alt border-linea" />
              </label>
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider text-tinta-2">Precio de venta ({divisa})</span>
                <input type="number" step="any" value={precio} onChange={(ev) => setPrecio(ev.target.value)}
                       placeholder={entry.last_price ? String(entry.last_price) : "0.00"} className="w-full mt-1 border rounded px-2 py-1.5 font-mono bg-superficie-alt border-linea" />
              </label>
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider text-tinta-2">Fecha de la venta</span>
                <input type="date" value={fecha} onChange={(ev) => setFecha(ev.target.value)}
                       className="w-full mt-1 border rounded px-2 py-1.5 font-mono bg-superficie-alt border-linea" />
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
                    className="w-full mt-4 bg-marca text-marca-tinta rounded-iv py-2 font-semibold disabled:opacity-60">
              {enviando ? "Calculando…" : "Registrar venta"}
            </button>
          </>
        ) : (
          <>
            <h3 className="font-bold text-lg mb-3 text-tinta">
              Venta registrada · {res.acciones} {entry.symbol}
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-tinta-2">Ganancia en {res.divisa}</span>
                <span className={`font-mono font-bold ${res.ganancia_divisa >= 0 ? "text-sube" : "text-baja"}`}>
                  {res.ganancia_divisa >= 0 ? "+" : ""}{res.ganancia_divisa} ({res.ganancia_pct}%)</span></div>
              <div className="flex justify-between items-baseline border-t pt-2 border-linea">
                <span className="text-tinta-2 font-semibold">Ganancia en EUROS</span>
                <span className={`font-mono font-bold text-lg ${(res.ganancia_eur ?? 0) >= 0 ? "text-sube" : "text-baja"}`}>
                  {eur(res.ganancia_eur)}</span></div>
              {res.efecto_divisa_eur != null && (
                <div className="flex justify-between text-xs">
                  <span className="text-tinta-2">De eso, por el tipo de cambio</span>
                  <span className="font-mono">{eur(res.efecto_divisa_eur)}</span></div>
              )}
              {!res.exacto && (
                <p className="text-[11px] text-aviso bg-aviso/10 rounded px-2 py-1.5 leading-snug">
                  Aproximado: falta el tipo de cambio del día de la compra.
                </p>
              )}
              <p className="text-xs text-tinta-2 pt-1">Te quedan <b>{res.acciones_restantes}</b> acciones.</p>
            </div>
            <button onClick={onClose} className="w-full mt-4 border rounded-iv py-2 border-linea">Cerrar</button>
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
      {/* Una sola superficie por acción. Antes cada dato iba en su propia caja
          rellena (posición, deseado, y una caja verde por nivel): seis o siete
          rectángulos de colores por tarjeta que pesaban todos lo mismo. Ahora las
          zonas se separan con filetes y el color queda solo en las cifras que lo
          llevan —azul el deseado, verde los niveles de compra, ámbar el siguiente. */}
      <div className="lg:hidden space-y-3">
        {entries.map((e) => (
          <article key={e.id} aria-label={e.symbol}
                   className={`iv-panel p-4 ${!e.active ? "opacity-50" : ""}`}>
            {/* Cabecera: quién es · precio · acciones */}
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-baseline gap-x-2 gap-y-1 flex-wrap">
                  <button type="button" className={`iv-cifra font-bold text-marca text-lg leading-none hover:underline underline-offset-4 ${TRANS}`}
                          onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</button>
                  {e.mercado && <span className="iv-etiqueta">{e.mercado}</span>}
                  <RiesgoBadge value={e.riesgo} />
                  <CategoriaDegiro value={e.categoria_degiro}
                                   onChange={(v) => updateField(e.id, "categoria_degiro", v)} />
                </div>
                <p className="text-apoyo text-tinta-2 mt-1.5 truncate">{e.name || "—"}</p>
                {e.sector && <p className="text-etiqueta text-tinta-3 truncate">{e.sector}</p>}
              </div>
              <div className="text-right shrink-0">
                <p className="text-etiqueta text-tinta-3">Precio actual</p>
                <p className="iv-cifra font-bold text-tinta text-base leading-tight">{fmtP(e.last_price)}</p>
                <ExtendedBadge entry={e} />
              </div>
            </div>

            {/* Posición + P&L (#20) */}
            <div className="mt-3 pt-3 border-t border-linea flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
              <dl className="flex gap-5 min-w-0">
                <div>
                  <dt className="iv-etiqueta">Compra</dt>
                  <dd><EditableCell value={e.compra} onChange={(v) => updateField(e.id, "compra", v)} className="iv-cifra text-sm font-semibold text-tinta" /></dd>
                </div>
                <div>
                  <dt className="iv-etiqueta">Nº acc.</dt>
                  <dd><EditableCell value={e.acciones} onChange={(v) => updateField(e.id, "acciones", v)} format={(v) => v != null && v !== "" ? Number(v).toLocaleString("es-ES", { maximumFractionDigits: 2 }) : "—"} className="iv-cifra text-sm font-semibold text-tinta" /></dd>
                </div>
              </dl>
              <dl className="text-right min-w-0 ml-auto">
                <dt className="iv-etiqueta">P&amp;L</dt>
                <dd><PnlText abs={pnlAbs(e)} pct={pnlPct(e)} eur={pnlEur.porSymbol[(e.symbol || "").toUpperCase()]} tasa={pnlEur.tasaUSD} /></dd>
              </dl>
            </div>

            {/* Deseado / venta */}
            <div className="mt-3 pt-3 border-t border-linea flex items-center justify-between gap-3">
              <div className="flex items-baseline gap-2.5 min-w-0">
                <p className="iv-etiqueta text-info">Deseado / Venta</p>
                <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} className="iv-cifra font-bold text-info text-sm" />
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {e.posibles_ganancias != null && <span className="iv-cifra text-etiqueta text-sube font-semibold">{fmtPct(e.posibles_ganancias)}</span>}
                {/* El estado que se NIEGA debe ser el mismo que se PINTA. Con `!e.alert_deseado`, una
    fila antigua sin el campo (undefined) se veía encendida (undefined !== false) pero al
    pulsar mandaba `!undefined` = true: seguía encendida y el primer clic no hacía nada. */}
<BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", e.alert_deseado === false)} />
              </div>
            </div>

            {/* Niveles de compra: filas, no cajas. Precio y distancia alineados a la
                derecha en columna para leerlos en vertical; el siguiente en tocarse,
                en ámbar y con su marca ◀. */}
            <div className="mt-3 pt-2 border-t border-linea">
              <ul className="grid sm:grid-cols-2 sm:gap-x-6">
                {(() => { const nextN = nextNivelKey(e); return [1,2,3,4,5].map((n) => {
                  const val = e[`nivel${n}`];
                  const alertKey = `alert_nivel${n}`;
                  const alertOn = e[alertKey] !== false;
                  if (val == null) return null;
                  const d = nivelDist(e, n);
                  const isNext = n === nextN;
                  return (
                    <li key={n} className={`grid grid-cols-[5.25rem_1fr_auto_auto] items-center gap-x-3 py-1.5 -mx-2 px-2 rounded-iv-sm ${isNext ? "bg-aviso/10" : ""}`}>
                      <span className={`iv-etiqueta font-semibold ${isNext ? "text-aviso" : "text-sube"}`}>Nivel {n}{isNext ? " ◀" : ""}</span>
                      <span className="text-right">
                        <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)} className="iv-cifra font-semibold text-sube text-sm" />
                      </span>
                      <span className={`iv-cifra text-etiqueta text-right w-14 ${isNext ? "text-aviso" : "text-tinta-3"}`}>
                        {d != null ? `${d >= 0 ? "+" : ""}${d.toFixed(1)}%` : ""}
                      </span>
                      <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
                    </li>
                  );
                }); })()}
              </ul>
            </div>

            {/* Acciones de la ficha, abajo y separadas: borrar no compite con el precio. */}
            <div className="mt-3 pt-3 border-t border-linea flex items-center justify-between gap-3">
              <span className="text-etiqueta text-tinta-3" aria-live="polite">
                {saving[e.id] && <span className="animate-pulse motion-reduce:animate-none">guardando…</span>}
              </span>
              <div className="flex items-center gap-2">
                {/* Solo tiene sentido vender lo que se tiene. Sin acciones, el botón
                    llevaría a un error del servidor en vez de a algo útil. */}
                {Number(e.acciones) > 0 && (
                  <button onClick={() => setVendiendo(e)} title="Registrar una venta"
                          className={`inline-flex items-center gap-1 text-etiqueta font-semibold border border-sube/60 text-sube hover:bg-sube/10 active:scale-[0.98] rounded-iv px-2.5 py-1.5 transition-[background-color,transform] duration-150 ease-out motion-reduce:transition-none`}>
                    <CurrencyEur size={13} weight="bold" aria-hidden="true" /> Vender
                  </button>
                )}
                <button onClick={() => deleteEntry(e.id)} aria-label={`Eliminar ${e.symbol}`} title="Eliminar"
                        className={`p-2 rounded-iv text-tinta-3 hover:text-baja hover:bg-baja/10 ${TRANS}`}><Trash size={16} /></button>
              </div>
            </div>
          </article>
        ))}
      </div>

      {/* DESKTOP TABLE */}
      <div className="hidden lg:block iv-panel overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left border-b border-linea-fuerte">
              <th scope="col" title="Monitorización activa" className="px-2 py-2.5 iv-etiqueta font-normal whitespace-nowrap w-10 bg-superficie sticky left-0 z-20"><Lightning size={13} className="mx-auto" aria-label="Monitorización activa" /></th>
              <th scope="col" className="px-3 py-2.5 iv-etiqueta font-normal whitespace-nowrap bg-superficie sticky left-10 z-20 border-r border-linea">Acción</th>
              <th scope="col" className="px-2 py-2.5 iv-etiqueta font-normal whitespace-nowrap">Mdo.</th>
              <th scope="col" className="px-2 py-2.5 iv-etiqueta font-normal whitespace-nowrap text-right">Precio</th>
              <th scope="col" className="px-2 py-2.5 iv-etiqueta font-normal whitespace-nowrap text-right">Compra</th>
              <th scope="col" className="px-2 py-2.5 iv-etiqueta font-normal whitespace-nowrap text-right">Acc.</th>
              <th scope="col" className="px-3 py-2.5 iv-etiqueta font-normal whitespace-nowrap text-right">P&amp;L</th>
              <th scope="col" className="px-2 py-2.5 iv-etiqueta font-semibold whitespace-nowrap text-right !text-info bg-info/[0.07] border-l border-info/20">Deseado</th>
              {[1,2,3,4,5].map((n) => (
                <th key={n} scope="col" className="px-2 py-2.5 iv-etiqueta font-semibold whitespace-nowrap text-right !text-sube bg-sube/[0.05] border-l border-sube/15">N{n}</th>
              ))}
              <th scope="col" className="px-2 py-2.5 iv-etiqueta font-normal whitespace-nowrap border-l border-linea">Riesgo</th>
              <th scope="col" title="Categoría de riesgo de DEGIRO (A-D). Determina cuánto margen libera vender esta acción." className="px-2 py-2.5 iv-etiqueta font-normal whitespace-nowrap">Cat.</th>
              <th className="px-2 py-2.5 w-8"><span className="sr-only">Eliminar</span></th>
            </tr>
          </thead>
          <tbody>
            {/* Sector y Ganancia no salen aquí: son de SOLO LECTURA en esta tabla y con
                dieciocho columnas obligaban a scroll horizontal. Se siguen viendo en la
                vista de móvil y se editan en el formulario, así que no se pierde nada —y
                el sector sigue alimentando el modelo de riesgo igual, esté a la vista o
                no. */}
            {/* Sin cebreado: con los tintes de Deseado y niveles, alternar fondos daba
                un damero. Filete entre filas y resalte al pasar por encima. */}
            {entries.map((e) => (
              <tr key={e.id} className={`border-t border-linea group bg-superficie hover:bg-superficie-alt ${TRANS} ${!e.active ? "opacity-40" : ""}`}>
                {/* Las dos primeras columnas van fijas: la tabla tiene quince columnas y
                    desborda a lo ancho, asi que al desplazarse quedaban treinta filas de
                    precios y niveles sin saber de que accion eran. El fondo va OPACO a
                    proposito —translucido dejaba ver por debajo lo que pasa al lado. */}
                <td className={`px-2 py-2.5 text-center sticky left-0 z-10 bg-superficie group-hover:bg-superficie-alt ${TRANS}`}>
                  <input type="checkbox" checked={e.active} onChange={(ev) => updateField(e.id, "active", ev.target.checked)} className="w-4 h-4 cursor-pointer accent-marca" title={e.active ? "Monitorización activa" : "Monitorización pausada"} aria-label={`Monitorización de ${e.symbol}`} />
                </td>
                <td className={`px-3 py-2.5 whitespace-nowrap sticky left-10 z-10 border-r border-linea bg-superficie group-hover:bg-superficie-alt ${TRANS}`}>
                  <div className="flex items-center gap-1.5">
                    <button type="button" className="iv-cifra font-bold text-marca hover:underline underline-offset-4 text-sm" onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</button>
                    {saving[e.id] && <span className="text-[11px] text-tinta-3 animate-pulse motion-reduce:animate-none" aria-label="guardando">·</span>}
                  </div>
                  <p className="text-[11px] text-tinta-3 truncate max-w-[110px]" title={e.name || undefined}>{e.name}</p>
                </td>
                <td className="px-2 py-2.5">
                  <span className="iv-etiqueta">{e.mercado || "—"}</span>
                </td>
                <td className="px-2 py-2.5 text-right whitespace-nowrap">
                  <span className="iv-cifra font-bold text-tinta text-sm">{fmtP(e.last_price)}</span>
                  <ExtendedBadge entry={e} />
                </td>
                <td className="px-2 py-2.5 text-right whitespace-nowrap">
                  <EditableCell value={e.compra} onChange={(v) => updateField(e.id, "compra", v)} className="iv-cifra text-sm text-tinta-2" />
                </td>
                <td className="px-2 py-2.5 text-right whitespace-nowrap">
                  <EditableCell value={e.acciones} onChange={(v) => updateField(e.id, "acciones", v)} isNumber format={(v) => v != null && v !== "" ? Number(v).toLocaleString("es-ES", { maximumFractionDigits: 2 }) : "—"} className="iv-cifra text-sm text-tinta-2" />
                </td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  <PnlText abs={pnlAbs(e)} pct={pnlPct(e)} eur={pnlEur.porSymbol[(e.symbol || "").toUpperCase()]} tasa={pnlEur.tasaUSD} />
                </td>
                <td className="px-2 py-2.5 bg-info/[0.05] border-l border-info/20">
                  <div className="flex items-center justify-end gap-1">
                    <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} className="iv-cifra text-sm font-bold text-info" />
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
                    <td key={n} className={`px-2 py-2.5 border-l border-sube/15 ${isNext ? "bg-aviso/10 shadow-[inset_0_0_0_1px_rgb(var(--iv-aviso)/0.35)]" : "bg-sube/[0.04]"}`}>
                      <div className="flex items-center justify-end gap-1">
                        <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)} className="iv-cifra text-sm font-semibold text-sube" />
                        <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
                      </div>
                      {d != null && <p className={`text-[11px] iv-cifra text-right mt-0.5 pr-7 ${isNext ? "text-aviso font-semibold" : "text-tinta-3"}`}>{isNext ? "◀ " : ""}{d >= 0 ? "+" : ""}{d.toFixed(1)}%</p>}
                    </td>
                  );
                }); })()}
                <td className="px-2 py-2.5 whitespace-nowrap border-l border-linea"><RiesgoBadge value={e.riesgo} /></td>
                <td className="px-2 py-2.5 whitespace-nowrap"><CategoriaDegiro value={e.categoria_degiro} onChange={(v) => updateField(e.id, "categoria_degiro", v)} /></td>
                <td className="px-2 py-2.5 text-center">
                  {/* Oculto hasta pasar por la fila, pero visible al llegar con el teclado. */}
                  <button onClick={() => deleteEntry(e.id)} aria-label={`Eliminar ${e.symbol}`}
                          className="text-tinta-3 hover:text-baja p-1 rounded-iv-sm opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-[color,opacity] duration-150 ease-out motion-reduce:transition-none" title="Eliminar"><Trash size={14} /></button>
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
