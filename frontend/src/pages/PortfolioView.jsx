import React, { useState, useEffect, useCallback } from "react";
import {
  Briefcase, UploadSimple, TrendUp, TrendDown, CurrencyEur,
  Receipt, ChartPie, ArrowClockwise, Trash, WarningCircle,
  CheckCircle, Coins, ArrowRight
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from "recharts";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

const PIE_COLORS = ["#1a3a32","#4a7c59","#c9a14a","#d85c41","#7a4e8c","#5c6b66","#6fb381","#a85d3c","#3a6b8a","#8a6b3a"];

function fmt(n, dec = 2) {
  if (n == null || isNaN(n)) return "—";
  return Number(n).toLocaleString("es-ES", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function fmtEur(n) { return n != null ? `${fmt(n)} €` : "—"; }
function fmtPct(n) { return n != null ? `${n > 0 ? "+" : ""}${fmt(n)}%` : "—"; }

function PnlBadge({ value, pct }) {
  const pos = value >= 0;
  return (
    <span className={`inline-flex items-center gap-1 font-mono font-semibold ${pos ? "text-green-600" : "text-red-500"}`}>
      {pos ? <TrendUp size={13} weight="bold" /> : <TrendDown size={13} weight="bold" />}
      {fmtEur(value)} {pct != null && <span className="text-xs opacity-80">({fmtPct(pct)})</span>}
    </span>
  );
}

function StatCard({ icon, label, value, sub, color = "text-[#0e1f1a]", testId }) {
  const Icon = icon;
  return (
    <div data-testid={testId} className="card-flat p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className="text-[#5c6b66]" />
        <p className="text-xs font-mono uppercase tracking-wider text-[#5c6b66]">{label}</p>
      </div>
      <p className={`font-heading font-bold text-2xl ${color}`}>{value}</p>
      {sub && <p className="text-xs text-[#5c6b66] mt-1 font-mono">{sub}</p>}
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
      const token = localStorage.getItem("inveria_token");
      const fd = new FormData();
      fd.append("transactions_file", txFile);
      fd.append("account_file", accFile);
      const res = await fetch(`${API}/api/portfolio/upload-degiro`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Error al procesar");
      }
      const data = await res.json();
      toast.success(`✅ ${data.trades_parsed} operaciones · ${data.events_parsed} movimientos importados`);
      onUploaded();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card-flat p-6 border-2 border-dashed border-[#e5e0d8]">
      <div className="flex items-center gap-3 mb-5">
        <UploadSimple size={20} className="text-[#1a3a32]" weight="bold" />
        <div>
          <h3 className="font-heading font-semibold text-[#0e1f1a]">Importar desde DEGIRO</h3>
          <p className="text-xs text-[#5c6b66] mt-0.5">Sube los 2 CSVs de DEGIRO — se procesan al instante sin IA</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
        <div>
          <label className="block text-xs font-mono text-[#5c6b66] uppercase tracking-wider mb-2">
            1. Transactions.csv
          </label>
          <label className={`flex items-center gap-2 p-3 rounded-lg border cursor-pointer transition-colors ${txFile ? "border-green-400 bg-green-50" : "border-[#e5e0d8] hover:bg-[#f5f3ef]"}`}>
            <UploadSimple size={16} className={txFile ? "text-green-600" : "text-[#5c6b66]"} />
            <span className={`text-sm font-mono truncate ${txFile ? "text-green-700" : "text-[#5c6b66]"}`}>
              {txFile ? txFile.name : "Seleccionar archivo..."}
            </span>
            <input type="file" accept=".csv" className="hidden" onChange={e => setTxFile(e.target.files[0])} />
          </label>
        </div>
        <div>
          <label className="block text-xs font-mono text-[#5c6b66] uppercase tracking-wider mb-2">
            2. Account.csv
          </label>
          <label className={`flex items-center gap-2 p-3 rounded-lg border cursor-pointer transition-colors ${accFile ? "border-green-400 bg-green-50" : "border-[#e5e0d8] hover:bg-[#f5f3ef]"}`}>
            <UploadSimple size={16} className={accFile ? "text-green-600" : "text-[#5c6b66]"} />
            <span className={`text-sm font-mono truncate ${accFile ? "text-green-700" : "text-[#5c6b66]"}`}>
              {accFile ? accFile.name : "Seleccionar archivo..."}
            </span>
            <input type="file" accept=".csv" className="hidden" onChange={e => setAccFile(e.target.files[0])} />
          </label>
        </div>
      </div>

      <div className="flex items-start gap-2 p-3 rounded-lg bg-[#f5f3ef] border border-[#e5e0d8] mb-4">
        <WarningCircle size={15} className="text-[#c9a14a] mt-0.5 flex-shrink-0" />
        <p className="text-xs text-[#5c6b66] font-mono">
          En DEGIRO web → <b>Actividad → Transacciones</b> → Exportar CSV &nbsp;|&nbsp;
          <b>Actividad → Cuenta</b> → Exportar CSV. Selecciona desde el inicio de tu cuenta.
        </p>
      </div>

      <button
        onClick={upload}
        disabled={loading || !txFile || !accFile}
        className="w-full h-11 bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono font-semibold text-sm rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {loading ? <><ArrowClockwise size={16} className="animate-spin" /> Procesando...</> : <><UploadSimple size={16} /> Importar cartera</>}
      </button>
    </div>
  );
}

// ── Main View ─────────────────────────────────────────────────────────────────
export default function PortfolioView({ setSymbol }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("open"); // open | closed | fees | dividends

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("inveria_token");
      const res = await fetch(`${API}/api/portfolio/degiro`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const json = await res.json();
      setData(json);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const deletePortfolio = async () => {
    if (!window.confirm("¿Borrar toda la cartera importada?")) return;
    const token = localStorage.getItem("inveria_token");
    await fetch(`${API}/api/portfolio/degiro`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    setData(null);
    toast.success("Cartera borrada");
  };

  if (loading) return <div className="card-flat p-12 text-center text-[#5c6b66] font-mono">Cargando cartera...</div>;

  if (!data) return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-[#1a3a32] flex items-center justify-center">
          <Briefcase size={20} className="text-[#f5f3ef]" weight="bold" />
        </div>
        <div>
          <h2 className="font-heading font-bold text-xl text-[#0e1f1a]">Mi Cartera DEGIRO</h2>
          <p className="text-xs text-[#5c6b66]">Importa tus CSVs para ver tu portfolio completo</p>
        </div>
      </div>
      <UploadSection onUploaded={load} />
    </div>
  );

  const s = data.summary || {};
  const stats = data.stats || {};
  const openPos = data.open_positions || [];
  const closedTrades = data.closed_trades || [];
  const dividends = data.dividends_detail || [];

  const totalUnrealized = openPos.reduce((acc, p) => acc + (p.unrealized_pnl_eur || 0), 0);
  const totalCurrentValue = openPos.reduce((acc, p) => acc + (p.current_value_eur || p.total_cost_eur), 0);
  const totalPnl = s.total_realized_pnl + totalUnrealized;

  // Pie chart data
  const pieData = openPos.slice(0, 10).map((p, i) => ({
    name: p.ticker, value: Math.max(p.current_value_eur || p.total_cost_eur, 0)
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#1a3a32] flex items-center justify-center">
            <Briefcase size={20} className="text-[#f5f3ef]" weight="bold" />
          </div>
          <div>
            <h2 className="font-heading font-bold text-xl text-[#0e1f1a]">Mi Cartera DEGIRO</h2>
            <p className="text-xs text-[#5c6b66]">
              Actualizado: {data.updated_at ? new Date(data.updated_at).toLocaleString("es-ES") : "—"} ·
              {s.total_trades} operaciones totales
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-[#e5e0d8] bg-white text-xs font-mono hover:bg-[#f5f3ef] transition-colors">
            <ArrowClockwise size={14} /> Actualizar precios
          </button>
          <button onClick={deletePortfolio} className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-red-200 bg-white text-xs font-mono text-red-600 hover:bg-red-50 transition-colors">
            <Trash size={14} /> Borrar
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard icon={Briefcase} label="Valor cartera" value={fmtEur(totalCurrentValue)} sub="posiciones abiertas" />
        <StatCard icon={CurrencyEur} label="Invertido" value={fmtEur(s.total_invested_eur)} sub={`${s.open_positions_count} posiciones`} />
        <StatCard
          icon={totalPnl >= 0 ? TrendUp : TrendDown}
          label="P&L Total"
          value={fmtEur(totalPnl)}
          color={totalPnl >= 0 ? "text-green-600" : "text-red-500"}
          sub={`Realiz. ${fmtEur(s.total_realized_pnl)}`}
        />
        <StatCard icon={CheckCircle} label="Win Rate" value={`${s.win_rate}%`}
          sub={`${s.winning_trades}W / ${s.losing_trades}L`}
          color={s.win_rate >= 50 ? "text-green-600" : "text-red-500"} />
        <StatCard icon={Receipt} label="Comisiones" value={fmtEur(s.total_fees)} sub="total pagado" color="text-red-500" />
        <StatCard icon={Coins} label="Dividendos" value={fmtEur(s.total_dividends)} sub={`Saldo: ${fmtEur(stats.cash_balance)}`} color="text-green-600" />
      </div>

      {/* Open positions + pie */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_280px] gap-6">
        {/* Tabs */}
        <div className="card-flat">
          <div className="flex border-b border-[#e5e0d8] overflow-x-auto">
            {[
              { id: "open", label: `Posiciones abiertas (${openPos.length})` },
              { id: "closed", label: `Operaciones cerradas (${closedTrades.length})` },
              { id: "fees", label: "Comisiones" },
              { id: "dividends", label: `Dividendos (${dividends.length})` },
            ].map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-4 py-3 text-xs font-mono whitespace-nowrap border-b-2 transition-colors ${tab === t.id ? "border-[#1a3a32] text-[#0e1f1a] font-semibold" : "border-transparent text-[#5c6b66] hover:text-[#0e1f1a]"}`}
              >
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
                  </tr>
                </thead>
                <tbody>
                  {openPos.map((p) => (
                    <tr key={p.ticker} className="border-b border-[#f0ece4] hover:bg-[#f9f7f3] cursor-pointer" onClick={() => setSymbol?.(p.ticker)}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-[#1a3a32]">{p.ticker}</span>
                          <ArrowRight size={11} className="text-[#c5bfb4]" />
                          <span className="text-xs text-[#5c6b66] truncate max-w-[120px]">{p.product}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right font-mono">{fmt(p.shares, 4)}</td>
                      <td className="px-4 py-3 text-right font-mono text-[#5c6b66]">{fmtEur(p.avg_cost_eur)}</td>
                      <td className="px-4 py-3 text-right font-mono">
                        {p.current_price ? `$${fmt(p.current_price)}` : <span className="text-[#c5bfb4]">—</span>}
                      </td>
                      <td className="px-4 py-3 text-right font-mono font-semibold">{fmtEur(p.current_value_eur || p.total_cost_eur)}</td>
                      <td className="px-4 py-3 text-right">
                        {p.unrealized_pnl_eur != null
                          ? <PnlBadge value={p.unrealized_pnl_eur} pct={p.unrealized_pnl_pct} />
                          : <span className="text-[#c5bfb4] font-mono text-xs">cargando...</span>}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-[#5c6b66]">{fmtEur(p.total_cost_eur)}</td>
                    </tr>
                  ))}
                  {openPos.length === 0 && (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-[#5c6b66] font-mono text-sm">No hay posiciones abiertas</td></tr>
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
                    <th className="px-4 py-3 text-left">Fecha compra</th>
                    <th className="px-4 py-3 text-left">Fecha venta</th>
                    <th className="px-4 py-3 text-right">Acc.</th>
                    <th className="px-4 py-3 text-right">Coste</th>
                    <th className="px-4 py-3 text-right">Ingresos</th>
                    <th className="px-4 py-3 text-right">P&L realiz.</th>
                  </tr>
                </thead>
                <tbody>
                  {closedTrades.map((ct, i) => (
                    <tr key={i} className="border-b border-[#f0ece4] hover:bg-[#f9f7f3]">
                      <td className="px-4 py-2.5">
                        <span className="font-mono font-bold text-[#1a3a32]">{ct.ticker}</span>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-[#5c6b66]">{ct.buy_date}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-[#5c6b66]">{ct.sell_date}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs">{fmt(ct.shares, 2)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-[#5c6b66]">{fmtEur(ct.buy_cost_total_eur)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-[#5c6b66]">{fmtEur(ct.sell_proceeds_eur)}</td>
                      <td className="px-4 py-2.5 text-right"><PnlBadge value={ct.realized_pnl_eur} pct={ct.realized_pnl_pct} /></td>
                    </tr>
                  ))}
                  {closedTrades.length === 0 && (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-[#5c6b66] font-mono text-sm">No hay operaciones cerradas</td></tr>
                  )}
                </tbody>
              </table>
            )}

            {/* Fees breakdown */}
            {tab === "fees" && (
              <div className="p-6 space-y-3">
                {[
                  { label: "Comisiones de transacción (€2/op)", value: stats.tx_fees, desc: `~${Math.round(stats.tx_fees / 2)} operaciones` },
                  { label: "AutoFX (cambio de divisa)", value: stats.autofx_fees, desc: "0,25% por conversión USD/EUR" },
                  { label: "Datos de mercado en tiempo real", value: stats.market_data_fees, desc: "Nasdaq, NYSE suscripciones" },
                  { label: "Conectividad con mercados", value: stats.connectivity_fees, desc: "Euronext, Xetra, LSE, etc." },
                  { label: "Impuestos de transacción", value: stats.tx_taxes, desc: "Francia, España" },
                  { label: "Comisiones de cierre", value: stats.closure_fees, desc: "" },
                  { label: "Comisiones de transferencia", value: stats.transfer_fees, desc: "" },
                ].map((item) => (
                  <div key={item.label} className="flex items-center justify-between p-3 rounded-lg border border-[#e5e0d8] bg-[#f9f7f3]">
                    <div>
                      <p className="text-sm font-mono text-[#0e1f1a]">{item.label}</p>
                      {item.desc && <p className="text-xs text-[#5c6b66]">{item.desc}</p>}
                    </div>
                    <span className="font-mono font-semibold text-red-500">-{fmtEur(item.value)}</span>
                  </div>
                ))}
                <div className="flex items-center justify-between p-4 rounded-lg border-2 border-[#1a3a32] bg-[#f5f3ef] mt-4">
                  <span className="font-mono font-bold text-[#0e1f1a]">TOTAL COMISIONES PAGADAS</span>
                  <span className="font-mono font-bold text-red-600 text-lg">-{fmtEur(s.total_fees)}</span>
                </div>
                <div className="grid grid-cols-2 gap-3 mt-2">
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
              <div>
                {dividends.length === 0 ? (
                  <div className="p-12 text-center text-[#5c6b66] font-mono text-sm">No hay dividendos registrados</div>
                ) : (
                  <table className="w-full text-sm">
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
                        <td colSpan={2} className="px-4 py-2 font-mono text-xs text-[#5c6b66]">Retención fiscal sobre dividendos</td>
                        <td className="px-4 py-2 text-right font-mono text-xs text-red-500">-{fmtEur(stats.dividend_tax)}</td>
                      </tr>
                      <tr>
                        <td colSpan={2} className="px-4 py-2 font-mono text-xs text-[#5c6b66]">Dividendo neto</td>
                        <td className="px-4 py-2 text-right font-mono text-xs font-semibold text-green-600">
                          +{fmtEur((s.total_dividends || 0) - (stats.dividend_tax || 0))}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Pie chart */}
        {openPos.length > 0 && (
          <div className="card-flat p-5">
            <h4 className="font-heading font-semibold text-sm text-[#0e1f1a] mb-1">Distribución</h4>
            <p className="text-xs text-[#5c6b66] mb-4">por valor actual de cartera</p>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} innerRadius={45}>
                  {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => fmtEur(v)} />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-1.5 mt-3">
              {pieData.map((d, i) => (
                <div key={d.name} className="flex items-center justify-between text-xs font-mono">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                    <span className="text-[#0e1f1a] font-semibold">{d.name}</span>
                  </div>
                  <span className="text-[#5c6b66]">{fmtEur(d.value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Re-upload */}
      <details className="card-flat">
        <summary className="px-5 py-4 cursor-pointer text-sm font-mono text-[#5c6b66] hover:text-[#0e1f1a] flex items-center gap-2">
          <UploadSimple size={14} /> Reimportar datos (actualizar con nuevo CSV)
        </summary>
        <div className="px-5 pb-5">
          <UploadSection onUploaded={load} />
        </div>
      </details>
    </div>
  );
}
