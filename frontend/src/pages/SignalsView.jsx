import React, { useState, useEffect, useRef } from "react";
import { Bell, BellSlash, Trash, Plus, X, UploadSimple, ArrowClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

// ── helpers ──────────────────────────────────────────────────────────────────
const fmtP = (v) => (v != null && v !== "" ? `$${Number(v).toFixed(2)}` : "—");
const fmtPct = (v) => (v != null ? `${Number(v).toFixed(2)}%` : "—");

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

// ── EditableCell ──────────────────────────────────────────────────────────────
function EditableCell({ value, onChange, isNumber = true, placeholder = "—", className = "" }) {
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

  return (
    <span
      onClick={() => { setDraft(value ?? ""); setEditing(true); }}
      className={`cursor-pointer hover:underline hover:text-blue-600 dark:hover:text-blue-400 select-none ${!value && value !== 0 ? "text-neutral-400" : ""} ${className}`}
      title="Clic para editar"
    >
      {isNumber ? fmtP(value) : (value || placeholder)}
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

// ── Empty form state ──────────────────────────────────────────────────────────
const EMPTY = { symbol: "", name: "", mercado: "", deseado: "", nivel1: "", nivel2: "", nivel3: "", nivel4: "", nivel5: "", riesgo: "", sector: "", posibles_ganancias: "", notes: "" };

// ── Main component ────────────────────────────────────────────────────────────
export default function SignalsView({ setSymbol }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState({});
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newEntry, setNewEntry] = useState(EMPTY);

  const fetchEntries = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/signals`);
      setEntries(await r.json());
    } catch { toast.error("No se pudieron cargar las señales"); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchEntries(); }, []);

  const updateField = async (id, field, value) => {
    setSaving((s) => ({ ...s, [id]: true }));
    try {
      const r = await fetch(`${API}/api/signals/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });
      if (!r.ok) throw new Error();
      const updated = await r.json();
      setEntries((prev) => prev.map((e) => e.id === id ? { ...e, ...updated } : e));
    } catch { toast.error("Error al guardar"); }
    finally { setSaving((s) => ({ ...s, [id]: false })); }
  };

  const deleteEntry = async (id) => {
    if (!window.confirm("¿Eliminar esta entrada?")) return;
    try {
      await fetch(`${API}/api/signals/${id}`, { method: "DELETE" });
      setEntries((prev) => prev.filter((e) => e.id !== id));
      toast.success("Eliminado");
    } catch { toast.error("Error al eliminar"); }
  };

  const addEntry = async () => {
    if (!newEntry.symbol.trim()) { toast.error("El símbolo es obligatorio"); return; }
    const num = (k) => newEntry[k] ? parseFloat(newEntry[k]) : null;
    const payload = {
      symbol: newEntry.symbol.trim().toUpperCase(),
      name: newEntry.name, mercado: newEntry.mercado.toUpperCase(),
      deseado: num("deseado"), nivel1: num("nivel1"), nivel2: num("nivel2"),
      nivel3: num("nivel3"), nivel4: num("nivel4"), nivel5: num("nivel5"),
      riesgo: newEntry.riesgo.toUpperCase(), sector: newEntry.sector,
      posibles_ganancias: num("posibles_ganancias"), notes: newEntry.notes, active: true,
    };
    try {
      const r = await fetch(`${API}/api/signals`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!r.ok) throw new Error();
      const created = await r.json();
      setEntries((prev) => [...prev, created]);
      setShowAdd(false); setNewEntry(EMPTY);
      toast.success(`${created.symbol} añadido`);
    } catch { toast.error("Error al añadir"); }
  };

  const doImport = async () => {
    const rows = parseExcelText(importText);
    if (!rows.length) { toast.error("No se detectaron filas. Comprueba el formato."); return; }
    setImporting(true);
    try {
      const r = await fetch(`${API}/api/signals/bulk`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rows }) });
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
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">📋 Acciones en Cartera</h1>
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
          <button onClick={() => setShowAdd(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#1a3a32] hover:bg-[#0e2820] text-white text-sm font-medium transition-colors">
            <Plus size={14} weight="bold" /> Añadir acción
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-neutral-500">
        <span className="flex items-center gap-1"><Bell size={12} weight="fill" className="text-[#c9a14a]" /> Alerta activa</span>
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
        <div className="rounded-xl border border-[#1a3a32]/30 bg-[#f5f3ef] dark:bg-neutral-900 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-[#0e1f1a] dark:text-neutral-200">➕ Nueva acción</p>
            <button onClick={() => setShowAdd(false)}><X size={16} /></button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
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
            ].map(({ key, label, placeholder }) => (
              <div key={key} className="flex flex-col gap-1">
                <label className="text-xs text-neutral-500">{label}</label>
                <input
                  className="border border-neutral-200 dark:border-neutral-600 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-neutral-800 outline-none focus:border-[#1a3a32] focus:ring-1 focus:ring-[#1a3a32]/20"
                  placeholder={placeholder}
                  value={newEntry[key]}
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
      {!loading && entries.length === 0 && (
        <div className="text-center py-16 text-neutral-400">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-lg font-medium">Sin acciones todavía</p>
          <p className="text-sm mt-1">Añade una acción o importa desde Excel</p>
        </div>
      )}

      {/* ── MOBILE CARDS ── */}
      {!loading && entries.length > 0 && (
        <div className="lg:hidden space-y-3">
          {entries.map((e) => (
            <div key={e.id} className={`rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-4 space-y-3 ${!e.active ? "opacity-50" : ""}`}>
              {/* Top row */}
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
                  </div>
                  <button onClick={() => deleteEntry(e.id)} className="text-neutral-300 hover:text-red-500 text-xl p-1"><Trash size={16} /></button>
                </div>
              </div>
              {/* Deseado */}
              <div className="flex items-center justify-between bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2">
                <div>
                  <p className="text-[10px] text-blue-500 uppercase font-mono font-bold">Deseado / Venta</p>
                  <p className="font-mono font-bold text-blue-700 dark:text-blue-300">{fmtP(e.deseado)}</p>
                </div>
                <div className="flex items-center gap-1">
                  {e.posibles_ganancias != null && <span className="text-xs text-green-600 font-bold">{fmtPct(e.posibles_ganancias)}</span>}
                  <BellToggle active={e.alert_deseado !== false} onClick={() => updateField(e.id, "alert_deseado", !e.alert_deseado)} />
                </div>
              </div>
              {/* Niveles */}
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
                      <p className="font-mono font-bold text-green-800 dark:text-green-300 text-sm">{fmtP(val)}</p>
                    </div>
                  );
                })}
              </div>
              {saving[e.id] && <p className="text-[10px] text-neutral-400 animate-pulse">guardando…</p>}
            </div>
          ))}
        </div>
      )}

      {/* ── DESKTOP TABLE ── */}
      {!loading && entries.length > 0 && (
        <div className="hidden lg:block rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-neutral-50 dark:bg-neutral-800/80 text-left">
                <th className="px-3 py-2.5 font-semibold text-neutral-600 dark:text-neutral-300 text-xs whitespace-nowrap w-10">⚡</th>
                <th className="px-3 py-2.5 font-semibold text-neutral-600 dark:text-neutral-300 text-xs whitespace-nowrap">Acción</th>
                <th className="px-3 py-2.5 font-semibold text-neutral-600 dark:text-neutral-300 text-xs whitespace-nowrap">Mdo.</th>
                <th className="px-3 py-2.5 font-semibold text-neutral-600 dark:text-neutral-300 text-xs whitespace-nowrap text-right">Precio actual</th>
                {/* Deseado */}
                <th className="px-3 py-2.5 text-xs whitespace-nowrap text-right bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 font-semibold">
                  <div className="flex items-center justify-end gap-1">Nivel Deseado<span className="text-[9px] text-neutral-400">/ Venta</span></div>
                </th>
                {/* Niveles 1-5 */}
                {[1,2,3,4,5].map((n) => (
                  <th key={n} className="px-3 py-2.5 text-xs whitespace-nowrap text-right bg-green-50 dark:bg-green-900/10 text-green-700 dark:text-green-400 font-semibold">
                    Nivel {n}{n === 5 ? " Extra" : ""}
                  </th>
                ))}
                <th className="px-3 py-2.5 font-semibold text-neutral-600 dark:text-neutral-300 text-xs whitespace-nowrap">Riesgo</th>
                <th className="px-3 py-2.5 font-semibold text-neutral-600 dark:text-neutral-300 text-xs whitespace-nowrap">Sector</th>
                <th className="px-3 py-2.5 font-semibold text-neutral-600 dark:text-neutral-300 text-xs whitespace-nowrap text-right">Posibles Ganancias</th>
                <th className="px-3 py-2.5 w-8"></th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, idx) => (
                <tr
                  key={e.id}
                  className={`border-t border-neutral-100 dark:border-neutral-800 transition-colors ${!e.active ? "opacity-40" : ""} ${idx % 2 === 0 ? "bg-white dark:bg-neutral-900" : "bg-neutral-50/50 dark:bg-neutral-800/30"} hover:bg-blue-50/40 dark:hover:bg-neutral-800/60`}
                >
                  {/* Toggle activo */}
                  <td className="px-3 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={e.active}
                      onChange={(ev) => updateField(e.id, "active", ev.target.checked)}
                      className="w-4 h-4 cursor-pointer accent-[#1a3a32]"
                      title={e.active ? "Monitorización activa" : "Monitorización pausada"}
                    />
                  </td>

                  {/* Acción */}
                  <td className="px-3 py-2 whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="font-bold text-[#1a3a32] dark:text-blue-400 cursor-pointer hover:underline text-sm"
                        onClick={() => setSymbol && setSymbol(e.symbol)}
                      >
                        {e.symbol}
                      </span>
                      {saving[e.id] && <span className="text-[10px] text-neutral-400 animate-pulse">·</span>}
                    </div>
                    <p className="text-[11px] text-neutral-400 truncate max-w-[120px]">{e.name}</p>
                  </td>

                  {/* Mercado */}
                  <td className="px-3 py-2">
                    <span className="text-[11px] font-mono bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded text-neutral-600 dark:text-neutral-400">
                      {e.mercado || "—"}
                    </span>
                  </td>

                  {/* Precio actual */}
                  <td className="px-3 py-2 text-right font-mono font-bold text-[#0e1f1a] dark:text-neutral-100 whitespace-nowrap">
                    {fmtP(e.last_price)}
                  </td>

                  {/* Deseado */}
                  <td className="px-3 py-2 bg-blue-50/60 dark:bg-blue-900/10">
                    <div className="flex items-center justify-end gap-1">
                      <EditableCell
                        value={e.deseado}
                        onChange={(v) => updateField(e.id, "deseado", v)}
                        className="font-mono text-sm font-semibold text-blue-700 dark:text-blue-300"
                      />
                      <BellToggle
                        active={e.alert_deseado !== false}
                        onClick={() => updateField(e.id, "alert_deseado", !e.alert_deseado)}
                      />
                    </div>
                  </td>

                  {/* Nivel 1-5 */}
                  {[1,2,3,4,5].map((n) => {
                    const val = e[`nivel${n}`];
                    const alertKey = `alert_nivel${n}`;
                    const alertOn = e[alertKey] !== false;
                    return (
                      <td key={n} className="px-3 py-2 bg-green-50/40 dark:bg-green-900/5">
                        <div className="flex items-center justify-end gap-1">
                          <EditableCell
                            value={val}
                            onChange={(v) => updateField(e.id, `nivel${n}`, v)}
                            className="font-mono text-sm text-green-800 dark:text-green-400"
                          />
                          <BellToggle
                            active={alertOn}
                            onClick={() => updateField(e.id, alertKey, !alertOn)}
                          />
                        </div>
                      </td>
                    );
                  })}

                  {/* Riesgo */}
                  <td className="px-3 py-2 whitespace-nowrap">
                    <RiesgoBadge value={e.riesgo} />
                  </td>

                  {/* Sector */}
                  <td className="px-3 py-2 text-xs text-neutral-600 dark:text-neutral-400 whitespace-nowrap max-w-[140px] truncate">
                    {e.sector || "—"}
                  </td>

                  {/* Posibles ganancias */}
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {e.posibles_ganancias != null ? (
                      <span className="font-bold text-green-600 dark:text-green-400 font-mono text-sm">
                        {fmtPct(e.posibles_ganancias)}
                      </span>
                    ) : <span className="text-neutral-400">—</span>}
                  </td>

                  {/* Delete */}
                  <td className="px-3 py-2 text-center">
                    <button onClick={() => deleteEntry(e.id)} className="text-neutral-300 hover:text-red-500 transition-colors p-1" title="Eliminar">
                      <Trash size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-neutral-400 text-center pb-2">
        🔔 Alertas comprobadas cada 60s · Telegram + Email · 1h cooldown por nivel · Haz clic en cualquier precio para editarlo
      </p>
    </div>
  );
}
