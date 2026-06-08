import React, { useState, useEffect, useRef } from "react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "../components/ui/table";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL || "";

// ── helpers ─────────────────────────────────────────────────────────────────

const fmt = (v) =>
  v != null && v !== "" ? `$${Number(v).toFixed(2)}` : "—";

const fmtPrice = (v) =>
  v != null ? `$${Number(v).toFixed(2)}` : "—";

function priceBadge(price, buy, sell) {
  if (price == null) return null;
  const buys = [buy?.buy1, buy?.buy2, buy?.buy3].filter(Boolean);
  const sells = [sell?.sell1, sell?.sell2, sell?.sell3].filter(Boolean);
  const nearBuy = buys.some((b) => Math.abs(price - b) / b <= 0.02);
  const nearSell = sells.some((s) => Math.abs(price - s) / s <= 0.02);
  if (nearSell) return <span className="ml-2 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300">VENTA</span>;
  if (nearBuy) return <span className="ml-2 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">COMPRA</span>;
  return null;
}

// ── EditableCell ─────────────────────────────────────────────────────────────

function EditableCell({ value, onChange, placeholder = "—", isNumber = true, className = "" }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const commit = () => {
    setEditing(false);
    const parsed = isNumber ? (draft === "" ? null : parseFloat(draft)) : draft;
    if (parsed !== value) onChange(parsed);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        className={`w-full bg-white dark:bg-neutral-800 border border-blue-400 rounded px-1 py-0.5 text-sm outline-none ${className}`}
        type={isNumber ? "number" : "text"}
        step="0.01"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") { setEditing(false); setDraft(value ?? ""); }
        }}
      />
    );
  }

  return (
    <span
      onClick={() => { setDraft(value ?? ""); setEditing(true); }}
      className={`cursor-pointer hover:underline hover:text-blue-600 dark:hover:text-blue-400 select-none ${!value && value !== 0 ? "text-neutral-400" : ""} ${className}`}
      title="Haz clic para editar"
    >
      {isNumber ? fmt(value) : (value || placeholder)}
    </span>
  );
}

// ── parseExcel helper (client-side, sin librerías pesadas) ───────────────────
// Acepta CSV o TSV pegado desde Excel (Copiar → Pegar en el área de texto)

function parseExcelText(text) {
  const lines = text.trim().split("\n").filter(Boolean);
  if (lines.length < 2) return [];
  // Detectar separador
  const sep = lines[0].includes("\t") ? "\t" : ",";
  const headers = lines[0].split(sep).map((h) => h.trim().toLowerCase().replace(/[\s\-\/]+/g, "_"));

  const map = {
    symbol: ["symbol", "ticker", "simbolo", "accion"],
    name: ["name", "nombre", "empresa", "compania"],
    buy1: ["buy1", "compra1", "compra_1", "entrada1", "b1"],
    buy2: ["buy2", "compra2", "compra_2", "entrada2", "b2"],
    buy3: ["buy3", "compra3", "compra_3", "entrada3", "b3"],
    sell1: ["sell1", "venta1", "venta_1", "objetivo1", "s1", "tp1"],
    sell2: ["sell2", "venta2", "venta_2", "objetivo2", "s2", "tp2"],
    sell3: ["sell3", "venta3", "venta_3", "objetivo3", "s3", "tp3"],
    notes: ["notes", "notas", "comentario", "comentarios"],
  };

  const colIndex = {};
  for (const [field, aliases] of Object.entries(map)) {
    for (let i = 0; i < headers.length; i++) {
      if (aliases.some((a) => headers[i].includes(a))) {
        colIndex[field] = i;
        break;
      }
    }
  }

  const rows = [];
  for (let r = 1; r < lines.length; r++) {
    const cols = lines[r].split(sep).map((c) => c.trim().replace(/^"|"$/g, ""));
    const symbol = colIndex.symbol != null ? cols[colIndex.symbol]?.toUpperCase() : null;
    if (!symbol) continue;
    const num = (key) => {
      if (colIndex[key] == null) return null;
      const v = parseFloat(cols[colIndex[key]]?.replace(",", "."));
      return isNaN(v) ? null : v;
    };
    rows.push({
      symbol,
      name: colIndex.name != null ? cols[colIndex.name] || "" : "",
      buy1: num("buy1"), buy2: num("buy2"), buy3: num("buy3"),
      sell1: num("sell1"), sell2: num("sell2"), sell3: num("sell3"),
      notes: colIndex.notes != null ? cols[colIndex.notes] || "" : "",
      active: true,
    });
  }
  return rows;
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SignalsView({ setSymbol }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState({});
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newEntry, setNewEntry] = useState({ symbol: "", name: "", buy1: "", buy2: "", buy3: "", sell1: "", sell2: "", sell3: "", notes: "" });

  // ── fetch ──────────────────────────────────────────────────────────────────
  const fetchEntries = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/signals`);
      const data = await r.json();
      setEntries(data);
    } catch {
      toast.error("No se pudieron cargar las señales");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchEntries(); }, []);

  // ── update field ───────────────────────────────────────────────────────────
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
      setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...updated } : e)));
    } catch {
      toast.error("Error al guardar");
    } finally {
      setSaving((s) => ({ ...s, [id]: false }));
    }
  };

  // ── delete ─────────────────────────────────────────────────────────────────
  const deleteEntry = async (id) => {
    if (!window.confirm("¿Eliminar esta entrada?")) return;
    try {
      await fetch(`${API}/api/signals/${id}`, { method: "DELETE" });
      setEntries((prev) => prev.filter((e) => e.id !== id));
      toast.success("Entrada eliminada");
    } catch {
      toast.error("Error al eliminar");
    }
  };

  // ── add new ────────────────────────────────────────────────────────────────
  const addEntry = async () => {
    if (!newEntry.symbol.trim()) { toast.error("El símbolo es obligatorio"); return; }
    const payload = {
      symbol: newEntry.symbol.trim().toUpperCase(),
      name: newEntry.name,
      buy1: newEntry.buy1 ? parseFloat(newEntry.buy1) : null,
      buy2: newEntry.buy2 ? parseFloat(newEntry.buy2) : null,
      buy3: newEntry.buy3 ? parseFloat(newEntry.buy3) : null,
      sell1: newEntry.sell1 ? parseFloat(newEntry.sell1) : null,
      sell2: newEntry.sell2 ? parseFloat(newEntry.sell2) : null,
      sell3: newEntry.sell3 ? parseFloat(newEntry.sell3) : null,
      notes: newEntry.notes,
      active: true,
    };
    try {
      const r = await fetch(`${API}/api/signals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error();
      const created = await r.json();
      setEntries((prev) => [...prev, created]);
      setShowAdd(false);
      setNewEntry({ symbol: "", name: "", buy1: "", buy2: "", buy3: "", sell1: "", sell2: "", sell3: "", notes: "" });
      toast.success(`${created.symbol} añadido`);
    } catch {
      toast.error("Error al añadir");
    }
  };

  // ── import Excel ───────────────────────────────────────────────────────────
  const doImport = async () => {
    const rows = parseExcelText(importText);
    if (!rows.length) { toast.error("No se detectaron filas. Comprueba el formato."); return; }
    setImporting(true);
    try {
      const r = await fetch(`${API}/api/signals/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows }),
      });
      if (!r.ok) throw new Error();
      const { created, updated } = await r.json();
      toast.success(`Importado: ${created} nuevas, ${updated} actualizadas`);
      setShowImport(false);
      setImportText("");
      fetchEntries();
    } catch {
      toast.error("Error al importar");
    } finally {
      setImporting(false);
    }
  };

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-[1480px] mx-auto px-4 py-6 space-y-6">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            📋 Tabla de Señales
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
            Puntos de compra y venta. Haz clic en cualquier celda para editarla.
            Las alertas se envían automáticamente a Telegram y email cuando el precio toca un nivel.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowImport(true)}
            className="px-4 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 text-sm font-medium hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            📥 Importar Excel
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
          >
            + Añadir acción
          </button>
        </div>
      </div>

      {/* Import panel */}
      {showImport && (
        <div className="rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 p-4 space-y-3">
          <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
            📥 Importar desde Excel — abre tu Excel, selecciona las celdas incluyendo la cabecera y pégalas aquí (Ctrl+V)
          </p>
          <p className="text-xs text-blue-600 dark:text-blue-400">
            Columnas reconocidas: <code>symbol, name, buy1, buy2, buy3, sell1, sell2, sell3, notes</code> (en inglés o español).
            Si ya existe el símbolo, se actualizan sus niveles.
          </p>
          <textarea
            className="w-full h-40 p-3 rounded-lg border border-blue-300 dark:border-blue-700 bg-white dark:bg-neutral-900 text-sm font-mono resize-none outline-none"
            placeholder={"symbol\tname\tbuy1\tbuy2\tsell1\tsell2\nAAPL\tApple\t170\t165\t195\t205\nMSFT\tMicrosoft\t380\t370\t430\t450"}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              onClick={doImport}
              disabled={importing || !importText.trim()}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium"
            >
              {importing ? "Importando…" : "Importar"}
            </button>
            <button
              onClick={() => { setShowImport(false); setImportText(""); }}
              className="px-4 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Add panel */}
      {showAdd && (
        <div className="rounded-xl border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/20 p-4 space-y-3">
          <p className="text-sm font-semibold text-green-800 dark:text-green-200">➕ Nueva entrada</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
            {[
              { key: "symbol", label: "Ticker *", placeholder: "AAPL" },
              { key: "name", label: "Nombre", placeholder: "Apple" },
              { key: "buy1", label: "Compra 1", placeholder: "170.00" },
              { key: "buy2", label: "Compra 2", placeholder: "165.00" },
              { key: "buy3", label: "Compra 3", placeholder: "160.00" },
              { key: "sell1", label: "Venta 1", placeholder: "195.00" },
              { key: "sell2", label: "Venta 2", placeholder: "205.00" },
              { key: "sell3", label: "Venta 3", placeholder: "215.00" },
            ].map(({ key, label, placeholder }) => (
              <div key={key} className="flex flex-col gap-1">
                <label className="text-xs text-neutral-500">{label}</label>
                <input
                  className="border border-neutral-300 dark:border-neutral-600 rounded px-2 py-1.5 text-sm bg-white dark:bg-neutral-800 outline-none focus:border-blue-400"
                  placeholder={placeholder}
                  value={newEntry[key]}
                  onChange={(e) => setNewEntry((p) => ({ ...p, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-neutral-500">Notas</label>
            <input
              className="border border-neutral-300 dark:border-neutral-600 rounded px-2 py-1.5 text-sm bg-white dark:bg-neutral-800 outline-none focus:border-blue-400"
              placeholder="Notas opcionales..."
              value={newEntry.notes}
              onChange={(e) => setNewEntry((p) => ({ ...p, notes: e.target.value }))}
            />
          </div>
          <div className="flex gap-2">
            <button onClick={addEntry} className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-medium">
              Guardar
            </button>
            <button onClick={() => setShowAdd(false)} className="px-4 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800">
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="text-center py-16 text-neutral-400">Cargando señales…</div>
      ) : entries.length === 0 ? (
        <div className="text-center py-16 text-neutral-400">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-lg font-medium">Sin señales todavía</p>
          <p className="text-sm mt-1">Añade una acción o importa desde Excel</p>
        </div>
      ) : (
        <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-neutral-50 dark:bg-neutral-800/60">
                <TableHead className="w-12 text-center">⚡</TableHead>
                <TableHead>Ticker</TableHead>
                <TableHead>Nombre</TableHead>
                <TableHead className="text-right text-neutral-500 text-xs">Precio actual</TableHead>
                <TableHead className="bg-green-50 dark:bg-green-950/20 text-green-700 dark:text-green-400 text-xs text-right">Compra 1</TableHead>
                <TableHead className="bg-green-50 dark:bg-green-950/20 text-green-700 dark:text-green-400 text-xs text-right">Compra 2</TableHead>
                <TableHead className="bg-green-50 dark:bg-green-950/20 text-green-700 dark:text-green-400 text-xs text-right">Compra 3</TableHead>
                <TableHead className="bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-400 text-xs text-right">Venta 1</TableHead>
                <TableHead className="bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-400 text-xs text-right">Venta 2</TableHead>
                <TableHead className="bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-400 text-xs text-right">Venta 3</TableHead>
                <TableHead>Notas</TableHead>
                <TableHead className="w-10"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => (
                <TableRow
                  key={e.id}
                  className={`transition-colors ${!e.active ? "opacity-40" : ""} hover:bg-neutral-50 dark:hover:bg-neutral-800/40`}
                >
                  {/* Active toggle */}
                  <TableCell className="text-center">
                    <input
                      type="checkbox"
                      checked={e.active}
                      onChange={(ev) => updateField(e.id, "active", ev.target.checked)}
                      className="w-4 h-4 cursor-pointer accent-blue-600"
                      title={e.active ? "Monitorización activa" : "Monitorización pausada"}
                    />
                  </TableCell>

                  {/* Symbol */}
                  <TableCell>
                    <span
                      className="font-bold text-blue-600 dark:text-blue-400 cursor-pointer hover:underline"
                      onClick={() => setSymbol && setSymbol(e.symbol)}
                    >
                      {e.symbol}
                    </span>
                    {priceBadge(e.last_price, e, e)}
                    {saving[e.id] && <span className="ml-1 text-[10px] text-neutral-400 animate-pulse">guardando…</span>}
                  </TableCell>

                  {/* Name */}
                  <TableCell>
                    <EditableCell
                      value={e.name}
                      isNumber={false}
                      placeholder="Nombre"
                      onChange={(v) => updateField(e.id, "name", v)}
                    />
                  </TableCell>

                  {/* Live price */}
                  <TableCell className="text-right text-sm font-mono text-neutral-600 dark:text-neutral-400">
                    {fmtPrice(e.last_price)}
                  </TableCell>

                  {/* Buy levels */}
                  {["buy1", "buy2", "buy3"].map((k) => (
                    <TableCell key={k} className="bg-green-50/30 dark:bg-green-950/10 text-right">
                      <EditableCell
                        value={e[k]}
                        onChange={(v) => updateField(e.id, k, v)}
                        className="text-green-800 dark:text-green-400 font-mono text-sm"
                      />
                    </TableCell>
                  ))}

                  {/* Sell levels */}
                  {["sell1", "sell2", "sell3"].map((k) => (
                    <TableCell key={k} className="bg-red-50/30 dark:bg-red-950/10 text-right">
                      <EditableCell
                        value={e[k]}
                        onChange={(v) => updateField(e.id, k, v)}
                        className="text-red-800 dark:text-red-400 font-mono text-sm"
                      />
                    </TableCell>
                  ))}

                  {/* Notes */}
                  <TableCell className="max-w-[180px]">
                    <EditableCell
                      value={e.notes}
                      isNumber={false}
                      placeholder="Notas"
                      onChange={(v) => updateField(e.id, "notes", v)}
                      className="text-xs text-neutral-500"
                    />
                  </TableCell>

                  {/* Delete */}
                  <TableCell>
                    <button
                      onClick={() => deleteEntry(e.id)}
                      className="text-neutral-300 hover:text-red-500 transition-colors text-lg leading-none"
                      title="Eliminar"
                    >
                      ×
                    </button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <p className="text-xs text-neutral-400 text-center">
        ✅ Las alertas se comprueban cada 60 s. Se avisa por Telegram y email con 1h de cooldown por nivel.
        Haz clic en cualquier precio para editarlo directamente.
      </p>
    </div>
  );
}
