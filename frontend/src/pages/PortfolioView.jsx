import React, { useState, useEffect, useCallback } from "react";
import {
  Briefcase, UploadSimple, TrendUp, TrendDown, CurrencyEur,
  Receipt, ArrowClockwise, Trash, WarningCircle, CheckCircle,
  Coins, ArrowRight, Plus, X, ArrowDown, ArrowUp
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from "recharts";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
const PIE_COLORS = ["#1a3a32","#4a7c59","#c9a14a","#d85c41","#7a4e8c","#5c6b66","#6fb381","#a85d3c","#3a6b8a","#8a6b3a"];

const authHeaders = () => {
  const token = localStorage.getItem("inveria_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

function fmt(n, dec = 2) {
  if (n == null || isNaN(n)) return "—";
  return Number(n).toLocaleString("es-ES", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function fmtEur(n) { return n != null && !isNaN(n) ? `${fmt(n)} €` : "—"; }
function fmtPct(n) { return n != null && !isNaN(n) ? `${n > 0 ? "+" : ""}${fmt(n)}%` : "—"; }

function PnlBadge({ value, pct }) {
  if (value == null || isNaN(value)) return <span className="text-[#c5bfb4] font-mono text-xs">—</span>;
  const pos = value >= 0;
  return (
    <span className={`inline-flex items-center gap-1 font-mono font-semibold text-sm ${pos ? "text-green-600" : "text-red-500"}`}>
      {pos ? <TrendUp size={13} weight="bold" /> : <TrendDown size={13} weight="bold" />}
      {fmtEur(value)}
      {pct != null && <span className="text-xs opacity-75">({fmtPct(pct)})</span>}
    </span>
  );
}

function StatCard({ icon, label, value, sub, color = "text-[#0e1f1a]" }) {
  const Icon = icon;
  return (
    <div className="card-flat p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className="text-[#5c6b66]" />
        <p className="text-xs font-mono uppercase tracking-wider text-[#5c6b66]">{label}</p>
      </div>
      <p className={`font-heading font-bold text-2xl ${color}`}>{value}</p>
      {sub && <p className="text-xs text-[#5c6b66] mt-1 font-mono">{sub}</p>}
    </div>
  );
}

// ── Add/Sell Trade Modal ──────────────────────────────────────────────────────
function TradeModal({ open, onClose, onSaved, prefill = null }) {
  const today = new Date().toISOString().split("T")[0];
  const [form, setForm] = useState({
    ticker: "", action: "BUY", shares: "", total_eur: "", date_str: today, product: "",
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({
        ticker: prefill?.ticker || "",
        action: prefill?.action || "BUY",
        shares: prefill?.shares != null ? String(prefill.shares) : "",
        total_eur: "",
        date_str: today,
        product: prefill?.product || "",
      });
    }
    // eslint-disable-next-line
  }, [open, prefill?.ticker, prefill?.action]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.ticker || !form.shares || !form.total_eur) {
      toast.error("Rellena ticker, acciones y total"); return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/portfolio/trade`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          ticker: form.ticker.toUpperCase().trim(),
          action: form.action,
          shares: parseFloat(form.shares),
          total_eur: parseFloat(form.total_eur),
          date_str: form.date_str,
          product: form.product,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Error");
      }
      const isBuy = form.action === "BUY";
      toast.success(`${isBuy ? "✅ Compra" : "🔴 Venta"} de ${form.ticker.toUpperCase()} registrada`);
      onSaved();
      onClose();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;
  const isSell = form.action === "SELL";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-[#f5f3ef] rounded-xl border border-[#e5e0d8] shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#e5e0d8]">
          <div className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-md flex items-center justify-center ${isSell ? "bg-red-500" : "bg-[#1a3a32]"}`}>
              {isSell ? <ArrowUp size={14} className="text-white" weight="bold" /> : <ArrowDown size={14} className="text-white" weight="bold" />}
            </div>
            <h3 className="font-heading font-semibold text-[#0e1f1a]">
              {isSell ? "Registrar venta" : "Registrar compra"}
            </h3>
          </div>
          <button onClick={onClose} className="text-[#5c6b66] hover:text-[#0e1f1a] transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* BUY / SELL toggle */}
          <div className="flex rounded-lg border border-[#e5e0d8] overflow-hidden">
            {["BUY", "SELL"].map(a => (
              <button key={a} onClick={() => set("action", a)}
                className={`flex-1 py-2 text-sm font-mono font-semibold transition-colors
                  ${form.action === a
                    ? a === "BUY" ? "bg-[#1a3a32] text-[#f5f3ef]" : "bg-red-500 text-white"
                    : "bg-white text-[#5c6b66] hover:text-[#0e1f1a]"}`}>
                {a === "BUY" ? "▲ Compra" : "▼ Venta"}
              </button>
            ))}
          </div>

          <div>
            <label className="block text-xs font-mono text-[#5c6b66] uppercase tracking-wider mb-1">Ticker</label>
            <input type="text" value={form.ticker} onChange={e => set("ticker", e.target.value.toUpperCase())}
              placeholder="AAPL, NVDA, META..."
              className="w-full h-10 px-3 rounded-md border border-[#e5e0d8] bg-white font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a32]" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-mono text-[#5c6b66] uppercase tracking-wider mb-1">Nº acciones</label>
              <input type="number" min="0" step="any" value={form.shares} onChange={e => set("shares", e.target.value)}
                placeholder="10"
                className="w-full h-10 px-3 rounded-md border border-[#e5e0d8] bg-white font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a32]" />
            </div>
            <div>
              <label className="block text-xs font-mono text-[#5c6b66] uppercase tracking-wider mb-1">
                Total EUR {isSell ? "(ingresos)" : "(coste total)"}
              </label>
              <input type="number" min="0" step="any" value={form.total_eur} onChange={e => set("total_eur", e.target.value)}
                placeholder="1500.00"
                className="w-full h-10 px-3 rounded-md border border-[#e5e0d8] bg-white font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a32]" />
            </div>
          </div>

          {form.shares && form.total_eur && parseFloat(form.shares) > 0 && (
            <div className="px-3 py-2 rounded-md bg-[#f0ece4] border border-[#e5e0d8] text-xs font-mono text-[#5c6b66]">
              Precio por acción: <span className="font-semibold text-[#0e1f1a]">
                {fmtEur(parseFloat(form.total_eur) / parseFloat(form.shares))}
              </span>
            </div>
          )}

          <div>
            <label className="block text-xs font-mono text-[#5c6b66] uppercase tracking-wider mb-1">Fecha</label>
            <input type="date" value={form.date_str} onChange={e => set("date_str", e.target.value)}
              className="w-full h-10 px-3 rounded-md border border-[#e5e0d8] bg-white font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a32]" />
          </div>

          <div>
            <label className="block text-xs font-mono text-[#5c6b66] uppercase tracking-wider mb-1">Nombre empresa (opcional)</label>
            <input type="text" value={form.product} onChange={e => set("product", e.target.value)}
              placeholder="Apple Inc."
              className="w-full h-10 px-3 rounded-md border border-[#e5e0d8] bg-white font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#1a3a32]" />
          </div>
        </div>

        <div className="px-5 pb-5 flex gap-2">
          <button onClick={onClose}
            className="flex-1 h-10 rounded-md border border-[#e5e0d8] bg-white text-sm font-mono text-[#5c6b66] hover:bg-[#f5f3ef] transition-colors">
            Cancelar
          </button>
          <button onClick={submit} disabled={loading}
            className={`flex-1 h-10 rounded-md text-sm font-mono font-semibold text-white transition-colors disabled:opacity-50
              ${isSell ? "bg-red-500 hover:bg-red-600" : "bg-[#1a3a32] hover:bg-[#0e1f1a]"}`}>
            {loading
              ? <ArrowClockwise size={15} className="animate-spin mx-auto" />
              : isSell ? "Registrar venta" : "Registrar compra"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Upload Section ────────────────────────────────────────────────────────────
function UploadSection({ onUploaded }) {
  const [txFile, setTxFile] = useState(null);
  const [accFile, setAccFile] = useState(null);
  const [loading, setLoading] = useState(false);

  const upload = async () => {
    if (!txFile || !accFile) { toast.error("Selecciona ambos archivos CSV"); return; }
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("transactions_file", txFile);
      fd.append("account_file", accFile);
      const res = await fetch(`${API}/api/portfolio/upload-degiro`, {
        method: "POST", headers: authHeaders(), body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Error al procesar");
      }
      const data = await res.json();
      toast.success(`✅ ${data.trades_parsed} operaciones · ${data.events_parsed} movimientos importados`);
      onUploaded();
    } catch (e) { toast.error(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="card-flat p-5 border-2 border-dashed border-[#e5e0d8]">
      <div className="flex items-center gap-3 mb-4">
        <UploadSimple size={17} className="text-[#1a3a32]" weight="bold" />
        <div>
          <h3 className="font-heading font-semibold text-[#0e1f1a]">Importar desde DEGIRO</h3>
          <p className="text-xs text-[#5c6b66]">Las operaciones manuales se conservan</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {[{ label: "1. Transactions.csv", state: txFile, set: setTxFile }, { label: "2. Account.csv", state: accFile, set: setAccFile }].map(({ label, state, set: setFn }) => (
          <div key={label}>
            <label className="block text-xs font-mono text-[#5c6b66] uppercase tracking-wider mb-1">{label}</label>
            <label className={`flex items-center gap-2 p-3 rounded-lg border cursor-pointer transition-colors ${state ? "border-green-400 bg-green-50" : "border-[#e5e0d8] hover:bg-[#f5f3ef]"}`}>
              <UploadSimple size={13} className={state ? "text-green-600" : "text-[#5c6b66]"} />
              <span className={`text-sm font-mono truncate ${state ? "text-green-700" : "text-[#5c6b66]"}`}>{state ? state.name : "Seleccionar..."}</span>
              <input type="file" accept=".csv" className="hidden" onChange={e => setFn(e.target.files[0])} />
            </label>
          </div>
        ))}
      </div>
      <div className="flex items-start gap-2 p-3 rounded-lg bg-[#f5f3ef] border border-[#e5e0d8] mb-3">
        <WarningCircle size={13} className="text-[#c9a14a] mt-0.5 flex-shrink-0" />
        <p className="text-xs text-[#5c6b66] font-mono">DEGIRO → <b>Actividad → Transacciones</b> y <b>Actividad → Cuenta</b> → Exportar CSV</p>
      </div>
      <button onClick={upload} disabled={loading || !txFile || !accFile}
        className="w-full h-10 bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono font-semibold text-sm rounded-md transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
        {loading ? <><ArrowClockwise size={14} className="animate-spin" /> Procesando...</> : <><UploadSimple size={14} /> Importar</>}
      </button>
    </div>
  );
}

// ── Main View ─────────────────────────────────────────────────────────────────
export default function PortfolioView({ setSymbol }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("open");
  const [modal, setModal] = useState({ open: false, prefill: null });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/portfolio/degiro`, { headers: authHeaders() });
      const json = await res.json();
      setData(json);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openModal = (prefill = null) => setModal({ open: true, prefill });
  const closeModal = () => setModal({ open: false, prefill: null });

  const quickSell = (pos) => openModal({
    ticker: pos.ticker, action: "SELL", shares: pos.shares, product: pos.product,
  });

  const deleteAll = async () => {
    if (!window.confirm("¿Borrar toda la cartera (CSV + manuales)?")) return;
    await fetch(`${API}/api/portfolio/degiro`, { method: "DELETE", headers: authHeaders() });
    setData(null);
    toast.success("Cartera borrada");
  };

  if (loading) return <div className="card-flat p-12 text-center text-[#5c6b66] font-mono">Cargando cartera...</div>;

  // ── Empty state ──
  if (!data) return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#1a3a32] flex items-center justify-center">
            <Briefcase size={20} className="text-[#f5f3ef]" weight="bold" />
          </div>
          <div>
            <h2 className="font-heading font-bold text-xl text-[#0e1f1a]">Mi Cartera</h2>
            <p className="text-xs text-[#5c6b66]">Importa tus CSVs o añade operaciones manualmente</p>
          </div>
        </div>
        <button onClick={() => openModal()}
          className="flex items-center gap-2 px-4 py-2 rounded-md bg-[#1a3a32] text-[#f5f3ef] text-sm font-mono hover:bg-[#0e1f1a] transition-colors">
          <Plus size={14} weight="bold" /> Añadir operación
        </button>
      </div>
      <UploadSection onUploaded={load} />
      <TradeModal open={modal.open} prefill={modal.prefill} onClose={closeModal} onSaved={load} />
    </div>
  );

  const s = data.summary || {};
  const stats = data.stats || {};
  const openPos = data.open_positions || [];
  const closedTrades = data.closed_trades || [];
  const dividends = data.dividends_detail || [];

  const totalUnrealized = openPos.reduce((acc, p) => acc + (p.unrealized_pnl_eur || 0), 0);
  const totalCurrentValue = openPos.reduce((acc, p) => acc + (p.current_value_eur || p.total_cost_eur), 0);
  const totalPnl = (s.total_realized_pnl || 0) + totalUnrealized;

  const pieData = openPos.slice(0, 10).map(p => ({
    name: p.ticker, value: Math.max(p.current_value_eur || p.total_cost_eur, 0),
  }));

  return (
    <div className="space-y-6">
      <TradeModal open={modal.open} prefill={modal.prefill} onClose={closeModal} onSaved={load} />

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#1a3a32] flex items-center justify-center">
            <Briefcase size={20} className="text-[#f5f3ef]" weight="bold" />
          </div>
          <div>
            <h2 className="font-heading font-bold text-xl text-[#0e1f1a]">Mi Cartera</h2>
            <p className="text-xs text-[#5c6b66]">
              {data.updated_at ? new Date(data.updated_at).toLocaleString("es-ES") : "—"} · {s.total_trades} ops
            </p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => openModal()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md bg-[#1a3a32] text-[#f5f3ef] text-xs font-mono hover:bg-[#0e1f1a] transition-colors">
            <Plus size={13} weight="bold" /> Añadir operación
          </button>
          <button onClick={load}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-[#e5e0d8] bg-white text-xs font-mono hover:bg-[#f5f3ef] transition-colors">
            <ArrowClockwise size={13} /> Actualizar precios
          </button>
          <button onClick={deleteAll}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-red-200 bg-white text-xs font-mono text-red-600 hover:bg-red-50 transition-colors">
            <Trash size={13} /> Borrar todo
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard icon={Briefcase} label="Valor cartera" value={fmtEur(totalCurrentValue)} sub="posiciones abiertas" />
        <StatCard icon={CurrencyEur} label="Invertido" value={fmtEur(s.total_invested_eur)} sub={`${s.open_positions_count} pos.`} />
        <StatCard icon={totalPnl >= 0 ? TrendUp : TrendDown} label="P&L Total" value={fmtEur(totalPnl)}
          color={totalPnl >= 0 ? "text-green-600" : "text-red-500"} sub={`Realiz. ${fmtEur(s.total_realized_pnl)}`} />
        <StatCard icon={CheckCircle} label="Win Rate" value={`${s.win_rate}%`}
          sub={`${s.winning_trades}W / ${s.losing_trades}L`}
          color={s.win_rate >= 50 ? "text-green-600" : "text-red-500"} />
        <StatCard icon={Receipt} label="Comisiones" value={fmtEur(s.total_fees)} sub="total pagado" color="text-red-500" />
        <StatCard icon={Coins} label="Dividendos" value={fmtEur(s.total_dividends)}
          sub={`Saldo: ${fmtEur(stats.cash_balance)}`} color="text-green-600" />
      </div>

      {/* Tabs + Pie */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_260px] gap-6">
        <div className="card-flat">
          <div className="flex border-b border-[#e5e0d8] overflow-x-auto">
            {[
              { id: "open",      label: `Posiciones abiertas (${openPos.length})` },
              { id: "closed",    label: `Cerradas (${closedTrades.length})` },
              { id: "fees",      label: "Comisiones" },
              { id: "dividends", label: `Dividendos (${dividends.length})` },
            ].map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`px-4 py-3 text-xs font-mono whitespace-nowrap border-b-2 transition-colors
                  ${tab === t.id ? "border-[#1a3a32] text-[#0e1f1a] font-semibold" : "border-transparent text-[#5c6b66] hover:text-[#0e1f1a]"}`}>
                {t.label}
              </button>
            ))}
          </div>

          <div className="overflow-x-auto">
            {/* Open positions */}
            {tab === "open" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[#5c6b66] text-xs font-mono border-b border-[#e5e0d8]">
                    <th className="px-4 py-3 text-left">Acción</th>
                    <th className="px-4 py-3 text-right">Acciones</th>
                    <th className="px-4 py-3 text-right">Coste medio</th>
                    <th className="px-4 py-3 text-right">Precio actual</th>
                    <th className="px-4 py-3 text-right">Valor actual</th>
                    <th className="px-4 py-3 text-right">P&L no realiz.</th>
                    <th className="px-4 py-3 text-right">Invertido</th>
                    <th className="px-3 py-3 w-9"></th>
                  </tr>
                </thead>
                <tbody>
                  {openPos.map(p => (
                    <tr key={p.ticker} className="border-b border-[#f0ece4] hover:bg-[#f9f7f3] group">
                      <td className="px-4 py-3 cursor-pointer" onClick={() => setSymbol?.(p.ticker)}>
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono font-bold text-[#1a3a32]">{p.ticker}</span>
                          <ArrowRight size={10} className="text-[#c5bfb4]" />
                          <span className="text-xs text-[#5c6b66] truncate max-w-[100px]">{p.product}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm">{fmt(p.shares, 4)}</td>
                      <td className="px-4 py-3 text-right font-mono text-sm text-[#5c6b66]">{fmtEur(p.avg_cost_eur)}</td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        {p.current_price ? <span>${fmt(p.current_price)}</span> : <span className="text-[#c5bfb4]">—</span>}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm font-semibold">
                        {fmtEur(p.current_value_eur || p.total_cost_eur)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <PnlBadge value={p.unrealized_pnl_eur} pct={p.unrealized_pnl_pct} />
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm text-[#5c6b66]">{fmtEur(p.total_cost_eur)}</td>
                      {/* Quick sell button — visible on hover */}
                      <td className="px-2 py-3">
                        <button
                          onClick={() => quickSell(p)}
                          title={`Vender ${p.ticker}`}
                          className="opacity-0 group-hover:opacity-100 w-7 h-7 rounded-md bg-red-50 border border-red-200 text-red-500 hover:bg-red-500 hover:text-white transition-all flex items-center justify-center mx-auto"
                        >
                          <ArrowUp size={12} weight="bold" />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {openPos.length === 0 && (
                    <tr><td colSpan={8} className="px-4 py-10 text-center text-[#5c6b66] font-mono text-sm">No hay posiciones abiertas</td></tr>
                  )}
                </tbody>
              </table>
            )}

            {/* Closed trades */}
            {tab === "closed" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[#5c6b66] text-xs font-mono border-b border-[#e5e0d8]">
                    <th className="px-4 py-3 text-left">Acción</th>
                    <th className="px-4 py-3 text-left">F. compra</th>
                    <th className="px-4 py-3 text-left">F. venta</th>
                    <th className="px-4 py-3 text-right">Acc.</th>
                    <th className="px-4 py-3 text-right">Coste</th>
                    <th className="px-4 py-3 text-right">Ingresos</th>
                    <th className="px-4 py-3 text-right">P&L realiz.</th>
                  </tr>
                </thead>
                <tbody>
                  {closedTrades.map((ct, i) => (
                    <tr key={i} className="border-b border-[#f0ece4] hover:bg-[#f9f7f3]">
                      <td className="px-4 py-2.5 font-mono font-bold text-[#1a3a32]">{ct.ticker}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-[#5c6b66]">{ct.buy_date}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-[#5c6b66]">{ct.sell_date}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs">{fmt(ct.shares, 2)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-[#5c6b66]">{fmtEur(ct.buy_cost_total_eur)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-[#5c6b66]">{fmtEur(ct.sell_proceeds_eur)}</td>
                      <td className="px-4 py-2.5 text-right"><PnlBadge value={ct.realized_pnl_eur} pct={ct.realized_pnl_pct} /></td>
                    </tr>
                  ))}
                  {closedTrades.length === 0 && (
                    <tr><td colSpan={7} className="px-4 py-10 text-center text-[#5c6b66] font-mono text-sm">No hay operaciones cerradas</td></tr>
                  )}
                </tbody>
              </table>
            )}

            {/* Fees */}
            {tab === "fees" && (
              <div className="p-6 space-y-3">
                {[
                  { label: "Comisiones de transacción", value: stats.tx_fees, desc: "~€2 por operación" },
                  { label: "AutoFX (cambio de divisa)", value: stats.autofx_fees, desc: "0,25% por conversión USD→EUR" },
                  { label: "Datos de mercado en tiempo real", value: stats.market_data_fees, desc: "Nasdaq, NYSE" },
                  { label: "Conectividad con mercados", value: stats.connectivity_fees, desc: "Euronext, Xetra, LSE..." },
                  { label: "Impuestos de transacción", value: stats.tx_taxes, desc: "Francia, España" },
                  { label: "Comisiones de cierre", value: stats.closure_fees, desc: "" },
                  { label: "Comisiones de transferencia", value: stats.transfer_fees, desc: "" },
                ].map(item => (
                  <div key={item.label} className="flex items-center justify-between p-3 rounded-lg border border-[#e5e0d8] bg-[#f9f7f3]">
                    <div>
                      <p className="text-sm font-mono text-[#0e1f1a]">{item.label}</p>
                      {item.desc && <p className="text-xs text-[#5c6b66]">{item.desc}</p>}
                    </div>
                    <span className="font-mono font-semibold text-red-500">-{fmtEur(item.value)}</span>
                  </div>
                ))}
                <div className="flex items-center justify-between p-4 rounded-lg border-2 border-[#1a3a32] bg-[#f5f3ef] mt-2">
                  <span className="font-mono font-bold text-[#0e1f1a]">TOTAL COMISIONES</span>
                  <span className="font-mono font-bold text-red-600 text-lg">-{fmtEur(s.total_fees)}</span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg border border-green-200 bg-green-50">
                    <p className="text-xs font-mono text-[#5c6b66]">Total depósitos</p>
                    <p className="font-mono font-semibold text-green-700">+{fmtEur(stats.deposits)}</p>
                  </div>
                  <div className="p-3 rounded-lg border border-[#e5e0d8] bg-[#f9f7f3]">
                    <p className="text-xs font-mono text-[#5c6b66]">Intereses cobrados</p>
                    <p className="font-mono font-semibold text-[#0e1f1a]">{fmtEur(stats.interest)}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Dividends */}
            {tab === "dividends" && (
              dividends.length === 0
                ? <div className="p-12 text-center text-[#5c6b66] font-mono text-sm">No hay dividendos registrados</div>
                : <table className="w-full text-sm">
                    <thead>
                      <tr className="text-[#5c6b66] text-xs font-mono border-b border-[#e5e0d8]">
                        <th className="px-4 py-3 text-left">Fecha</th>
                        <th className="px-4 py-3 text-left">Acción</th>
                        <th className="px-4 py-3 text-right">Importe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dividends.map((d, i) => (
                        <tr key={i} className="border-b border-[#f0ece4] hover:bg-[#f9f7f3]">
                          <td className="px-4 py-2.5 font-mono text-xs text-[#5c6b66]">{d.date}</td>
                          <td className="px-4 py-2.5">
                            <span className="font-mono font-bold text-[#1a3a32]">{d.ticker || "—"}</span>
                            {d.product && <span className="text-xs text-[#5c6b66] ml-2">{d.product}</span>}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono font-semibold text-green-600">+{fmtEur(d.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 border-[#e5e0d8]">
                        <td colSpan={2} className="px-4 py-3 font-mono font-semibold text-[#0e1f1a]">Total dividendos</td>
                        <td className="px-4 py-3 text-right font-mono font-bold text-green-600">+{fmtEur(s.total_dividends)}</td>
                      </tr>
                      <tr>
                        <td colSpan={2} className="px-4 py-2 font-mono text-xs text-[#5c6b66]">Retención fiscal</td>
                        <td className="px-4 py-2 text-right font-mono text-xs text-red-500">-{fmtEur(stats.dividend_tax)}</td>
                      </tr>
                    </tfoot>
                  </table>
            )}
          </div>
        </div>

        {/* Pie chart */}
        {openPos.length > 0 && (
          <div className="card-flat p-5 flex flex-col">
            <h4 className="font-heading font-semibold text-sm text-[#0e1f1a] mb-0.5">Distribución</h4>
            <p className="text-xs text-[#5c6b66] mb-3">por valor actual de cartera</p>
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={75} innerRadius={40}>
                  {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={v => fmtEur(v)} />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-1.5 mt-2">
              {pieData.map((d, i) => (
                <div key={d.name} className="flex items-center justify-between text-xs font-mono">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                    <span className="text-[#0e1f1a] font-semibold">{d.name}</span>
                  </div>
                  <span className="text-[#5c6b66]">{fmtEur(d.value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Re-upload CSV */}
      <details className="card-flat">
        <summary className="px-5 py-4 cursor-pointer text-sm font-mono text-[#5c6b66] hover:text-[#0e1f1a] flex items-center gap-2 list-none">
          <UploadSimple size={13} /> Reimportar / actualizar con nuevo CSV de DEGIRO
        </summary>
        <div className="px-5 pb-5 pt-2">
          <UploadSection onUploaded={load} />
        </div>
      </details>
    </div>
  );
}
