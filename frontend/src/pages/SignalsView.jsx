import React, { useState, useEffect, useRef, useMemo } from "react";
import { Bell, BellSlash, Trash, Plus, X, UploadSimple, ArrowClockwise, Lightning, Bank } from "@phosphor-icons/react";
import { toast } from "sonner";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
const authHeaders = () => {
  const token = localStorage.getItem("inveria_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// ── sub-tabs ───────────────────────────────────────────────────────────────────
const GRUPOS = [
  { key: "ideas_javi", label: "Cartera",   icon: Lightning },
  { key: "cimientos",  label: "Cimientos", icon: Bank },
];
const grupoOf = (e) => e.grupo || "ideas_javi"; // entradas antiguas → Cartera

// ── helpers ──────────────────────────────────────────────────────────────────
const fmtP = (v) => (v != null && v !== "" ? `$${Number(v).toFixed(2)}` : "—");
const fmtPct = (v) => (v != null ? `${Number(v).toFixed(2)}%` : "—");

const CUR_SYM = { USD: "$", EUR: "€", GBP: "£", CHF: "CHF ", JPY: "¥" };
const fmtCur = (v, divisa) => {
  if (v == null || v === "") return "—";
  const n = Number(v).toFixed(2);
  const sym = CUR_SYM[divisa];
  return sym ? `${sym}${n}` : `${n}${divisa ? " " + divisa : ""}`;
};

// Caída necesaria para que el precio alcance un nivel de compra (negativo = aún tiene que bajar)
const caida = (price, level) =>
  price == null || level == null || price === 0 ? null : ((level - price) / price) * 100;
// Distancia (potencial) hasta el nivel de venta / objetivo
const distancia = (price, target) =>
  price == null || target == null || price === 0 ? null : ((target - price) / price) * 100;

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

const RIESGO_STYLE = {
  BAJO:  { bg: "bg-green-100 dark:bg-green-900/40",  text: "text-green-700 dark:text-green-300" },
  MEDIO: { bg: "bg-yellow-100 dark:bg-yellow-900/40", text: "text-yellow-700 dark:text-yellow-300" },
  ALTO:  { bg: "bg-red-100 dark:bg-red-900/40",       text: "text-red-600 dark:text-red-400" },
};

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
      className={`p-1 rounded transition-colors ${active ? "text-[#c9a14a] hover:text-yellow-600" : "text-neutral-300 hover:text-neutral-500"}`}
    >
      {active ? <Bell size={14} weight="fill" /> : <BellSlash size={14} />}
    </button>
  );
}

// Celda "Caída necesaria": muestra ALCANZADO (verde) si el precio ya está en/por debajo del nivel,
// si no el % que aún tiene que caer, coloreado por proximidad.
function CaidaCell({ price, level }) {
  if (level == null) return <span className="text-neutral-300">—</span>;
  const v = caida(price, level);
  if (v == null) return <span className="text-neutral-300">—</span>;
  if (v >= 0) {
    return <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase bg-green-200 dark:bg-green-800/60 text-green-800 dark:text-green-200">Alcanzado</span>;
  }
  const near = v > -10;
  const cls = near
    ? "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300"
    : "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300";
  return <span className={`px-2 py-0.5 rounded text-[11px] font-mono font-semibold ${cls}`}>{v.toFixed(2)}%</span>;
}

// ── EditableCell ──────────────────────────────────────────────────────────────
function EditableCell({ value, onChange, isNumber = true, placeholder = "—", className = "", format }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef(null);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);

  const commit = () => {
    setEditing(false);
    const parsed = isNumber ? (draft === "" ? null : parseFloat(draft)) : draft;
    if (parsed !== value) onChange(parsed);
  };

  if (editing) return (
    <input
      ref={inputRef}
      className={`w-full bg-white dark:bg-neutral-800 border border-blue-400 rounded px-1 py-0.5 text-sm outline-none ${className}`}
      type={isNumber ? "number" : "text"}
      step="0.01"
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
  const headers = lines[0].split(sep).map((h) => h.trim().toLowerCase().replace(/[\s\-\/áéíóú]+/g, "_"));

  const map = {
    symbol: ["symbol", "ticker", "ticker_isin", "simbolo", "accion"],
    name:   ["name", "nombre", "empresa", "accion"],
    mercado: ["mercado", "market", "bolsa"],
    deseado: ["deseado", "objetivo", "target", "nivel_deseado", "nivel_deseado_venta"],
    nivel1:  ["nivel1", "nivel_1", "nivel 1", "n1", "compra1"],
    nivel2:  ["nivel2", "nivel_2", "nivel 2", "n2", "compra2"],
    nivel3:  ["nivel3", "nivel_3", "nivel 3", "n3", "compra3"],
    nivel4:  ["nivel4", "nivel_4", "nivel 4", "n4", "compra4"],
    nivel5:  ["nivel5", "nivel_5", "nivel 5", "nivel_5_extra", "n5"],
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
      riesgo: str("riesgo").toUpperCase(),
      sector: str("sector"),
      posibles_ganancias: num("posibles_ganancias"),
      active: true,
    });
  }
  return rows;
}

// ── Empty form states ───────────────────────────────────────────────────────────
const EMPTY = { symbol: "", name: "", mercado: "", deseado: "", nivel1: "", nivel2: "", nivel3: "", nivel4: "", nivel5: "", riesgo: "", sector: "", posibles_ganancias: "", notes: "" };
const EMPTY_CIM = { symbol: "", name: "", divisa: "", nivel1: "", nivel2: "", nivel3: "", nivel4: "", bz: "", deseado: "", objetivo_5a: "" };

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
    { key: "riesgo",   label: "Riesgo",      placeholder: "MEDIO" },
    { key: "sector",   label: "Sector",      placeholder: "TECH" },
    { key: "posibles_ganancias", label: "Posibles Ganancias %", placeholder: "25.5" },
  ],
  cimientos: [
    { key: "symbol",      label: "Ticker *",   placeholder: "KO" },
    { key: "name",        label: "Nombre",     placeholder: "Coca-Cola Co" },
    { key: "divisa",      label: "Divisa",     placeholder: "USD" },
    { key: "nivel1",      label: "Nivel 1 (25%)", placeholder: "80" },
    { key: "nivel2",      label: "Nivel 2 (50%)", placeholder: "70" },
    { key: "nivel3",      label: "Nivel 3 (75%)", placeholder: "60" },
    { key: "nivel4",      label: "Nivel 4 (100%)", placeholder: "50" },
    { key: "bz",          label: "BZ %",       placeholder: "25" },
    { key: "deseado",     label: "Venta / Protección", placeholder: "90" },
    { key: "objetivo_5a", label: "Objetivo 5 años", placeholder: "100" },
  ],
};
const NUM_KEYS = new Set(["deseado", "nivel1", "nivel2", "nivel3", "nivel4", "nivel5", "posibles_ganancias", "bz", "objetivo_5a"]);

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
  const [newEntry, setNewEntry] = useState(EMPTY);

  const isCim = grupo === "cimientos";
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
      const data = await r.json();
      if (lastLocalEditRef.current <= startedAt) setEntries(data);
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
        .then((r) => r.json())
        .then((data) => { if (lastLocalEditRef.current <= startedAt) setEntries(data); })
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
    setNewEntry(g === "cimientos" ? EMPTY_CIM : EMPTY);
  };

  const updateField = async (id, field, value) => {
    setSaving((s) => ({ ...s, [id]: true }));
    try {
      const r = await fetch(`${API}/api/signals/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ [field]: value }),
      });
      if (!r.ok) throw new Error();
      const updated = await r.json();
      lastLocalEditRef.current = Date.now();
      setEntries((prev) => prev.map((e) => e.id === id ? { ...e, ...updated } : e));
    } catch { toast.error("Error al guardar"); }
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
      if (!r.ok) throw new Error();
      const created = await r.json();
      lastLocalEditRef.current = Date.now();
      setEntries((prev) => [...prev, created]);
      setShowAdd(false); setNewEntry(isCim ? EMPTY_CIM : EMPTY);
      toast.success(`${created.symbol} añadido`);
    } catch { toast.error("Error al añadir"); }
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

  // ── render ──────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-4 sm:py-6 space-y-4 sm:space-y-6">

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            {isCim ? "🏛️ Cimientos de Cartera" : "📋 Cartera"}
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
            {isCim
              ? "Núcleo defensivo: zonas de compra escalonadas (25→100%) con caída necesaria y objetivo a 5 años."
              : "Activa la 🔔 en cada nivel para recibir alerta por Telegram y email cuando el precio lo alcance."}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={fetchEntries} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors">
            <ArrowClockwise size={14} /> Refrescar
          </button>
          {!isCim && (
            <button onClick={() => setShowImport(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors">
              <UploadSimple size={14} /> Importar Excel
            </button>
          )}
          <button onClick={() => { setNewEntry(isCim ? EMPTY_CIM : EMPTY); setShowAdd(true); }} className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#1a3a32] hover:bg-[#0e2820] text-white text-sm font-medium transition-colors">
            <Plus size={14} weight="bold" /> Añadir acción
          </button>
        </div>
      </div>

      {/* Sub-tabs */}
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
                active ? "bg-[#1a3a32] text-white" : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-800 dark:hover:text-neutral-200"
              }`}
            >
              <Icon size={15} weight="bold" />
              {g.label}
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded-full ${active ? "bg-white/20" : "bg-neutral-100 dark:bg-neutral-800"}`}>{countOf(g.key)}</span>
            </button>
          );
        })}
      </div>

      {/* Legend */}
      {isCim ? (
        <div className="flex flex-wrap gap-4 text-xs text-neutral-500">
          <span className="flex items-center gap-1"><Bell size={12} weight="fill" className="text-[#c9a14a]" /> Alerta activa</span>
          <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase bg-green-200 dark:bg-green-800/60 text-green-800 dark:text-green-200">Alcanzado</span> Precio ya en la zona</span>
          <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-100 dark:bg-amber-900/40 text-amber-700 inline-block">‹10%</span> Caída cercana</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-blue-100 dark:bg-blue-900/40 border border-blue-300 inline-block"></span> Venta / Protección</span>
        </div>
      ) : (
        <div className="flex flex-wrap gap-4 text-xs text-neutral-500">
          <span className="flex items-center gap-1"><Bell size={12} weight="fill" className="text-[#c9a14a]" /> Alerta activa</span>
          <span className="flex items-center gap-1"><BellSlash size={12} className="text-neutral-300" /> Alerta inactiva</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-blue-100 dark:bg-blue-900/40 border border-blue-300 inline-block"></span> Nivel Deseado / Venta</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-50 dark:bg-green-900/20 border border-green-200 inline-block"></span> Niveles de Compra</span>
        </div>
      )}

      {/* Import panel */}
      {showImport && !isCim && (
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
        <div className="rounded-xl border border-[#1a3a32]/30 bg-[#f5f3ef] dark:bg-neutral-900 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-[#0e1f1a] dark:text-neutral-200">➕ Nueva acción · {isCim ? "Cimientos" : "Cartera"}</p>
            <button onClick={() => setShowAdd(false)}><X size={16} /></button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {ADD_FIELDS[grupo].map(({ key, label, placeholder }) => (
              <div key={key} className="flex flex-col gap-1">
                <label className="text-xs text-neutral-500">{label}</label>
                <input
                  className="border border-neutral-200 dark:border-neutral-600 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-neutral-800 outline-none focus:border-[#1a3a32] focus:ring-1 focus:ring-[#1a3a32]/20"
                  placeholder={placeholder}
                  value={newEntry[key] ?? ""}
                  onChange={(e) => setNewEntry((p) => ({ ...p, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={addEntry} className="px-4 py-2 rounded-lg bg-[#1a3a32] hover:bg-[#0e2820] text-white text-sm font-medium">Guardar</button>
            <button onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-lg border border-neutral-300 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800">Cancelar</button>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && <div className="text-center py-16 text-neutral-400">Cargando señales…</div>}

      {/* Empty */}
      {!loading && visible.length === 0 && (
        <div className="text-center py-16 text-neutral-400">
          <p className="text-4xl mb-3">{isCim ? "🏛️" : "📋"}</p>
          <p className="text-lg font-medium">Sin acciones todavía</p>
          <p className="text-sm mt-1">{isCim ? "Añade una acción a Cimientos" : "Añade una acción o importa desde Excel"}</p>
        </div>
      )}

      {/* ════════════════ CIMIENTOS ════════════════ */}
      {!loading && isCim && visible.length > 0 && <CimientosView entries={visible} saving={saving} updateField={updateField} deleteEntry={deleteEntry} setSymbol={setSymbol} />}

      {/* ════════════════ IDEAS JAVI ════════════════ */}
      {!loading && !isCim && visible.length > 0 && <IdeasView entries={visible} saving={saving} updateField={updateField} deleteEntry={deleteEntry} setSymbol={setSymbol} />}

      <p className="text-xs text-neutral-400 text-center pb-2">
        🔔 Alertas solo en horario de mercado (9:30-16:00 ET) · 1 vez al día por nivel · Telegram + Email · Haz clic en cualquier valor para editarlo
      </p>
    </div>
  );
}

// ── IDEAS JAVI view (cartera editable de niveles 1-5) ───────────────────────────
function IdeasView({ entries, saving, updateField, deleteEntry, setSymbol }) {
  return (
    <>
      {/* MOBILE CARDS */}
      <div className="lg:hidden space-y-3">
        {entries.map((e) => (
          <div key={e.id} className={`rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-4 space-y-3 ${!e.active ? "opacity-50" : ""}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-[#1a3a32] dark:text-blue-400 cursor-pointer text-lg" onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</span>
                  {e.mercado && <span className="text-[10px] font-mono bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded">{e.mercado}</span>}
                  <RiesgoBadge value={e.riesgo} />
                </div>
                <p className="text-sm text-neutral-500 mt-0.5">{e.name || "—"}</p>
                {e.sector && <p className="text-xs text-neutral-400">{e.sector}</p>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <div className="text-right">
                  <p className="text-xs text-neutral-400">Precio actual</p>
                  <p className="font-mono font-bold text-[#0e1f1a] dark:text-neutral-100">{fmtP(e.last_price)}</p>
                  <ExtendedBadge entry={e} />
                </div>
                <button onClick={() => deleteEntry(e.id)} className="text-neutral-300 hover:text-red-500 text-xl p-1"><Trash size={16} /></button>
              </div>
            </div>
            <div className="flex items-center justify-between bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2">
              <div>
                <p className="text-[10px] text-blue-500 uppercase font-mono font-bold">Deseado / Venta</p>
                <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} className="font-mono font-bold text-blue-700 dark:text-blue-300 text-sm" />
              </div>
              <div className="flex items-center gap-1">
                {e.posibles_ganancias != null && <span className="text-xs text-green-600 font-bold">{fmtPct(e.posibles_ganancias)}</span>}
                <BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", !e.alert_deseado)} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[1,2,3,4,5].map((n) => {
                const val = e[`nivel${n}`];
                const alertKey = `alert_nivel${n}`;
                const alertOn = e[alertKey] !== false;
                if (val == null) return null;
                return (
                  <div key={n} className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-2">
                    <div className="flex items-center justify-between mb-0.5">
                      <p className="text-[9px] text-green-600 uppercase font-mono font-bold">Nivel {n}</p>
                      <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
                    </div>
                    <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)} className="font-mono font-bold text-green-800 dark:text-green-300 text-sm" />
                  </div>
                );
              })}
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
              <th className="px-3 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap w-10 bg-neutral-100 dark:bg-neutral-800">⚡</th>
              <th className="px-3 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800">Acción</th>
              <th className="px-3 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800">Mdo.</th>
              <th className="px-3 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap text-right bg-neutral-100 dark:bg-neutral-800">Precio actual</th>
              <th className="px-3 py-3 text-xs whitespace-nowrap text-right bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 font-bold border-l border-blue-200 dark:border-blue-800">🎯 Deseado / Venta</th>
              {[1,2,3,4,5].map((n) => (
                <th key={n} className="px-3 py-3 text-xs whitespace-nowrap text-right bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 font-bold border-l border-green-200 dark:border-green-800">Nivel {n}{n === 5 ? " ⭐" : ""}</th>
              ))}
              <th className="px-3 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800 border-l border-neutral-200">Riesgo</th>
              <th className="px-3 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800">Sector</th>
              <th className="px-3 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap text-right bg-neutral-100 dark:bg-neutral-800">📈 Ganancia</th>
              <th className="px-3 py-3 w-8 bg-neutral-100 dark:bg-neutral-800"></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, idx) => (
              <tr key={e.id} className={`border-t border-neutral-100 dark:border-neutral-800 transition-colors group ${!e.active ? "opacity-40" : ""} ${idx % 2 === 0 ? "bg-white dark:bg-neutral-900" : "bg-neutral-50 dark:bg-neutral-800/40"} hover:bg-amber-50/60 dark:hover:bg-neutral-700/40`}>
                <td className="px-3 py-2.5 text-center">
                  <input type="checkbox" checked={e.active} onChange={(ev) => updateField(e.id, "active", ev.target.checked)} className="w-4 h-4 cursor-pointer accent-[#1a3a32]" title={e.active ? "Monitorización activa" : "Monitorización pausada"} />
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-[#1a3a32] dark:text-emerald-400 cursor-pointer hover:underline text-sm" onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</span>
                    {saving[e.id] && <span className="text-[10px] text-neutral-400 animate-pulse">·</span>}
                  </div>
                  <p className="text-[11px] text-neutral-500 dark:text-neutral-400 truncate max-w-[130px] font-medium">{e.name}</p>
                </td>
                <td className="px-3 py-2.5">
                  <span className="text-[11px] font-mono font-semibold bg-neutral-200 dark:bg-neutral-700 px-2 py-0.5 rounded text-neutral-700 dark:text-neutral-300">{e.mercado || "—"}</span>
                </td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  <span className="font-mono font-bold text-neutral-900 dark:text-white text-sm">{fmtP(e.last_price)}</span>
                  <ExtendedBadge entry={e} />
                </td>
                <td className="px-3 py-2.5 bg-blue-50 dark:bg-blue-900/20 border-l border-blue-100 dark:border-blue-900">
                  <div className="flex items-center justify-end gap-1">
                    <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} className="font-mono text-sm font-bold text-blue-800 dark:text-blue-200" />
                    <BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", !e.alert_deseado)} />
                  </div>
                </td>
                {[1,2,3,4,5].map((n) => {
                  const val = e[`nivel${n}`];
                  const alertKey = `alert_nivel${n}`;
                  const alertOn = e[alertKey] !== false;
                  return (
                    <td key={n} className="px-3 py-2.5 bg-green-50 dark:bg-green-900/10 border-l border-green-100 dark:border-green-900">
                      <div className="flex items-center justify-end gap-1">
                        <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)} className="font-mono text-sm font-semibold text-green-900 dark:text-green-300" />
                        <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
                      </div>
                    </td>
                  );
                })}
                <td className="px-3 py-2.5 whitespace-nowrap border-l border-neutral-100 dark:border-neutral-800"><RiesgoBadge value={e.riesgo} /></td>
                <td className="px-3 py-2.5 whitespace-nowrap max-w-[150px] truncate">
                  <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">{e.sector || "—"}</span>
                </td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  {e.posibles_ganancias != null ? (
                    <span className="inline-block font-bold text-white bg-green-600 dark:bg-green-700 font-mono text-xs px-2 py-0.5 rounded-full">+{fmtPct(e.posibles_ganancias)}</span>
                  ) : <span className="text-neutral-400">—</span>}
                </td>
                <td className="px-3 py-2.5 text-center">
                  <button onClick={() => deleteEntry(e.id)} className="text-neutral-300 hover:text-red-500 transition-colors p-1 opacity-0 group-hover:opacity-100" title="Eliminar"><Trash size={14} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── CIMIENTOS view (núcleo de cartera con caída necesaria y objetivo) ───────────
function CimientosView({ entries, saving, updateField, deleteEntry, setSymbol }) {
  const LEVELS = [
    { n: 1, pct: "25%" },
    { n: 2, pct: "50%" },
    { n: 3, pct: "75%" },
    { n: 4, pct: "100%" },
  ];
  return (
    <>
      {/* MOBILE CARDS */}
      <div className="lg:hidden space-y-3">
        {entries.map((e) => {
          const dist = distancia(e.last_price, e.deseado);
          return (
            <div key={e.id} className={`rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-4 space-y-3 ${!e.active ? "opacity-50" : ""}`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-[#1a3a32] dark:text-blue-400 cursor-pointer text-lg" onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</span>
                    {e.divisa && <span className="text-[10px] font-mono bg-amber-100 dark:bg-amber-900/40 text-amber-700 px-1.5 py-0.5 rounded">{e.divisa}</span>}
                  </div>
                  <p className="text-sm text-neutral-500 mt-0.5">{e.name || "—"}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <div className="text-right">
                    <p className="text-xs text-neutral-400">Precio actual</p>
                    <p className="font-mono font-bold text-[#0e1f1a] dark:text-neutral-100">{fmtCur(e.last_price, e.divisa)}</p>
                    <ExtendedBadge entry={e} />
                  </div>
                  <button onClick={() => deleteEntry(e.id)} className="text-neutral-300 hover:text-red-500 text-xl p-1"><Trash size={16} /></button>
                </div>
              </div>
              {/* Niveles de compra con caída necesaria */}
              <div className="grid grid-cols-2 gap-2">
                {LEVELS.map(({ n, pct }) => {
                  const val = e[`nivel${n}`];
                  const alertKey = `alert_nivel${n}`;
                  const alertOn = e[alertKey] !== false;
                  return (
                    <div key={n} className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-2">
                      <div className="flex items-center justify-between mb-0.5">
                        <p className="text-[9px] text-green-600 uppercase font-mono font-bold">Nivel {n} · {pct}</p>
                        <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
                      </div>
                      <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)} format={(x) => fmtCur(x, e.divisa)} className="font-mono font-bold text-green-800 dark:text-green-300 text-sm" />
                      <div className="mt-1"><CaidaCell price={e.last_price} level={val} /></div>
                    </div>
                  );
                })}
              </div>
              {/* Venta/protección + objetivo */}
              <div className="flex items-center justify-between bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2">
                <div>
                  <p className="text-[10px] text-blue-500 uppercase font-mono font-bold">Venta / Protección</p>
                  <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} format={(x) => fmtCur(x, e.divisa)} className="font-mono font-bold text-blue-700 dark:text-blue-300 text-sm" />
                </div>
                <div className="flex items-center gap-2">
                  {dist != null && <span className={`text-xs font-bold ${dist >= 0 ? "text-green-600" : "text-red-500"}`}>{dist >= 0 ? "+" : ""}{dist.toFixed(2)}%</span>}
                  <BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", !e.alert_deseado)} />
                </div>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-neutral-400">BZ: <EditableCell value={e.bz} onChange={(v) => updateField(e.id, "bz", v)} format={(x) => x == null ? "—" : `${Number(x).toFixed(0)}%`} className="font-mono font-semibold text-neutral-700 dark:text-neutral-300" /></span>
                <span className="text-neutral-400">Objetivo 5a: <EditableCell value={e.objetivo_5a} onChange={(v) => updateField(e.id, "objetivo_5a", v)} format={(x) => fmtCur(x, e.divisa)} className="font-mono font-semibold text-neutral-700 dark:text-neutral-300" /></span>
              </div>
              {saving[e.id] && <p className="text-[10px] text-neutral-400 animate-pulse">guardando…</p>}
            </div>
          );
        })}
      </div>

      {/* DESKTOP TABLE */}
      <div className="hidden lg:block rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-x-auto shadow-sm">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left border-b-2 border-neutral-200 dark:border-neutral-700">
              <th className="px-2 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap w-10 bg-neutral-100 dark:bg-neutral-800">⚡</th>
              <th className="px-2 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800">Nombre</th>
              <th className="px-2 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap bg-neutral-100 dark:bg-neutral-800">Divisa</th>
              <th className="px-2 py-3 font-bold text-neutral-700 dark:text-neutral-200 text-xs whitespace-nowrap text-right bg-neutral-100 dark:bg-neutral-800">Precio</th>
              {LEVELS.map(({ n, pct }) => (
                <th key={n} className="px-2 py-3 text-xs whitespace-nowrap text-right bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 font-bold border-l border-green-200 dark:border-green-800" title="Precio del nivel · debajo: caída necesaria para alcanzarlo">Nivel {n}<span className="block text-[9px] font-normal opacity-70">{pct}</span></th>
              ))}
              <th className="px-2 py-3 text-xs whitespace-nowrap text-right bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 font-bold border-l border-amber-200">BZ</th>
              <th className="px-2 py-3 text-xs whitespace-nowrap text-right bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 font-bold border-l border-blue-200" title="Nivel de venta/protección · debajo: distancia a objetivo">🛡️ Venta<span className="block text-[9px] font-normal opacity-70">/ protección</span></th>
              <th className="px-2 py-3 text-xs whitespace-nowrap text-right bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 font-bold border-l border-neutral-200">🎯 Obj. 5a</th>
              <th className="px-2 py-3 w-8 bg-neutral-100 dark:bg-neutral-800"></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, idx) => {
              const dist = distancia(e.last_price, e.deseado);
              return (
                <tr key={e.id} className={`border-t border-neutral-100 dark:border-neutral-800 transition-colors group ${!e.active ? "opacity-40" : ""} ${idx % 2 === 0 ? "bg-white dark:bg-neutral-900" : "bg-neutral-50 dark:bg-neutral-800/40"} hover:bg-amber-50/60 dark:hover:bg-neutral-700/40`}>
                  <td className="px-2 py-2.5 text-center">
                    <input type="checkbox" checked={e.active} onChange={(ev) => updateField(e.id, "active", ev.target.checked)} className="w-4 h-4 cursor-pointer accent-[#1a3a32]" title={e.active ? "Monitorización activa" : "Monitorización pausada"} />
                  </td>
                  <td className="px-2 py-2.5 whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-[#1a3a32] dark:text-emerald-400 cursor-pointer hover:underline text-sm" onClick={() => setSymbol && setSymbol(e.symbol)}>{e.symbol}</span>
                      {saving[e.id] && <span className="text-[10px] text-neutral-400 animate-pulse">·</span>}
                    </div>
                    <p className="text-[11px] text-neutral-500 dark:text-neutral-400 truncate max-w-[150px] font-medium">{e.name}</p>
                  </td>
                  <td className="px-2 py-2.5">
                    <EditableCell value={e.divisa} onChange={(v) => updateField(e.id, "divisa", (v || "").toUpperCase())} isNumber={false} placeholder="—" className="text-[11px] font-mono font-semibold text-neutral-700 dark:text-neutral-300" />
                  </td>
                  <td className="px-2 py-2.5 text-right whitespace-nowrap">
                    <span className="font-mono font-bold text-neutral-900 dark:text-white text-sm">{fmtCur(e.last_price, e.divisa)}</span>
                    <ExtendedBadge entry={e} />
                  </td>
                  {LEVELS.map(({ n }) => {
                    const val = e[`nivel${n}`];
                    const alertKey = `alert_nivel${n}`;
                    const alertOn = e[alertKey] !== false;
                    return (
                      <td key={n} className="px-2 py-2.5 bg-green-50 dark:bg-green-900/10 border-l border-green-100 dark:border-green-900">
                        <div className="flex items-center justify-end gap-1">
                          <EditableCell value={val} onChange={(v) => updateField(e.id, `nivel${n}`, v)} format={(x) => fmtCur(x, e.divisa)} className="font-mono text-sm font-semibold text-green-900 dark:text-green-300" />
                          <BellToggle active={alertOn} onClick={() => updateField(e.id, alertKey, !alertOn)} />
                        </div>
                        {val != null && <div className="text-right mt-1"><CaidaCell price={e.last_price} level={val} /></div>}
                      </td>
                    );
                  })}
                  <td className="px-2 py-2.5 text-right bg-amber-50 dark:bg-amber-900/10 border-l border-amber-100">
                    <EditableCell value={e.bz} onChange={(v) => updateField(e.id, "bz", v)} format={(x) => x == null ? "—" : `${Number(x).toFixed(0)}%`} className="font-mono text-sm font-semibold text-amber-700 dark:text-amber-300" />
                  </td>
                  <td className="px-2 py-2.5 bg-blue-50 dark:bg-blue-900/20 border-l border-blue-100 dark:border-blue-900">
                    <div className="flex items-center justify-end gap-1">
                      <EditableCell value={e.deseado} onChange={(v) => updateField(e.id, "deseado", v)} format={(x) => fmtCur(x, e.divisa)} className="font-mono text-sm font-bold text-blue-800 dark:text-blue-200" />
                      <BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", !e.alert_deseado)} />
                    </div>
                    {dist != null && (
                      <div className={`text-right mt-1 font-mono text-[11px] font-bold ${dist >= 0 ? "text-green-600 dark:text-green-400" : "text-red-500"}`}>{dist >= 0 ? "+" : ""}{dist.toFixed(2)}%</div>
                    )}
                  </td>
                  <td className="px-2 py-2.5 text-right border-l border-neutral-100 dark:border-neutral-800">
                    <EditableCell value={e.objetivo_5a} onChange={(v) => updateField(e.id, "objetivo_5a", v)} format={(x) => fmtCur(x, e.divisa)} className="font-mono text-sm font-semibold text-neutral-700 dark:text-neutral-300" />
                  </td>
                  <td className="px-2 py-2.5 text-center">
                    <button onClick={() => deleteEntry(e.id)} className="text-neutral-300 hover:text-red-500 transition-colors p-1 opacity-0 group-hover:opacity-100" title="Eliminar"><Trash size={14} /></button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
