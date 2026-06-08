import React from "react";
import { useNavigate } from "react-router-dom";
import { Briefcase, Upload, Plus, Trash, TrendUp, TrendDown, ChartPieSlice, X, ArrowRight, Wallet } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip as ReTooltip } from "recharts";
import { toast } from "sonner";
import { api } from "../lib/api";
import { fmtPrice, fmtPct, fmtDate } from "../lib/format";

const SECTOR_COLORS = ["#1a3a32", "#4a7c59", "#d85c41", "#c9a14a", "#7a4e8c", "#5c6b66", "#6fb381", "#a85d3c"];

function StatCard({ label, value, sub, tone, testId }) {
  const toneClass = tone === "buy" ? "text-[#4a7c59]" : tone === "sell" ? "text-[#d85c41]" : "text-[#0e1f1a]";
  return (
    <div data-testid={testId} className="card-flat p-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">{label}</p>
      <p className={`font-mono font-bold text-2xl mt-1 ${toneClass}`}>{value}</p>
      {sub && <p className={`font-mono text-xs mt-1 ${toneClass}`}>{sub}</p>}
    </div>
  );
}

function ManualTransactionForm({ onAdd }) {
  const [form, setForm] = React.useState({
    date: new Date().toISOString().slice(0, 10),
    symbol: "",
    action: "BUY",
    shares: "",
    price: "",
    currency: "USD",
    fees: "0",
    broker: "DEGIRO",
  });

  const submit = async (e) => {
    e.preventDefault();
    if (!form.symbol || !form.shares || !form.price) {
      toast.error("Completa símbolo, acciones y precio");
      return;
    }
    try {
      const tx = {
        ...form,
        symbol: form.symbol.toUpperCase(),
        shares: parseFloat(form.shares),
        price: parseFloat(form.price),
        fees: parseFloat(form.fees) || 0,
      };
      await api.portfolio.addTransactions([tx]);
      toast.success("Transacción añadida");
      setForm({ ...form, symbol: "", shares: "", price: "", fees: "0" });
      onAdd?.();
    } catch (e) {
      toast.error("Error al añadir");
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3" data-testid="manual-tx-form">
      <div className="grid grid-cols-2 gap-2">
        <Input data-testid="tx-symbol" placeholder="Ticker (AAPL)" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} className="font-mono" />
        <Select value={form.action} onValueChange={(v) => setForm({ ...form, action: v })}>
          <SelectTrigger data-testid="tx-action"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="BUY">Compra</SelectItem>
            <SelectItem value="SELL">Venta</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Input data-testid="tx-shares" type="number" step="0.0001" placeholder="Nº acciones" value={form.shares} onChange={(e) => setForm({ ...form, shares: e.target.value })} className="font-mono" />
        <Input data-testid="tx-price" type="number" step="0.0001" placeholder="Precio/acción" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className="font-mono" />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Input data-testid="tx-date" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="font-mono text-xs" />
        <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v })}>
          <SelectTrigger data-testid="tx-currency"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="USD">USD</SelectItem>
            <SelectItem value="EUR">EUR</SelectItem>
            <SelectItem value="GBP">GBP</SelectItem>
          </SelectContent>
        </Select>
        <Input data-testid="tx-fees" type="number" step="0.01" placeholder="Comisión" value={form.fees} onChange={(e) => setForm({ ...form, fees: e.target.value })} className="font-mono text-xs" />
      </div>
      <Button data-testid="tx-submit" type="submit" className="w-full bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono">
        <Plus size={14} weight="bold" className="mr-1" /> Añadir transacción
      </Button>
    </form>
  );
}

function PdfUploader({ onAdd }) {
  const [parsing, setParsing] = React.useState(false);
  const [parsed, setParsed] = React.useState(null);

  const handleFile = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    setParsing(true);
    setParsed(null);
    const allTx = [];
    const allCash = [];
    let processed = 0;
    let failed = 0;
    for (const file of files) {
      try {
        const res = await api.portfolio.uploadPdf(file);
        if (res.transactions) allTx.push(...res.transactions);
        if (res.cash_events) allCash.push(...res.cash_events);
        processed++;
        const txCount = res.transactions?.length || 0;
        const evCount = res.cash_events?.length || 0;
        if (txCount === 0 && evCount === 0 && res.warning) {
          toast.warning(`${file.name}: ${res.warning}`, { duration: 10000 });
        } else {
          toast.success(`${file.name}: ${txCount} ops + ${evCount} movimientos`);
        }
      } catch (err) {
        failed++;
        toast.error(`Error en ${file.name}: ${err?.response?.data?.detail?.slice(0, 120) || "error"}`);
      }
    }
    if (allTx.length === 0 && allCash.length === 0) {
      toast.error(`No se encontró nada en ${processed} PDF(s)`);
      setParsing(false);
      return;
    }
    setParsed({ transactions: allTx, cash_events: allCash });
    toast.success(`Total: ${allTx.length} operaciones + ${allCash.length} movimientos de ${processed} PDF(s)${failed ? ` (${failed} fallaron)` : ""}`);
    setParsing(false);
    // Reset input so re-uploading same files works
    e.target.value = "";
  };
  const updateRow = (i, field, val) => {
    const next = [...parsed.transactions];
    next[i] = { ...next[i], [field]: val };
    setParsed({ ...parsed, transactions: next });
  };

  const removeRow = (i) => setParsed({ ...parsed, transactions: parsed.transactions.filter((_, j) => j !== i) });

  const confirmAll = async () => {
    try {
      const txs = parsed.transactions.map((t) => ({
        ...t,
        shares: parseFloat(t.shares),
        price: parseFloat(t.price),
        fees: parseFloat(t.fees || 0),
        symbol: (t.symbol || "").toUpperCase(),
        action: (t.action || "BUY").toUpperCase(),
      })).filter((t) => t.symbol && t.shares && t.price);
      const promises = [];
      if (txs.length > 0) promises.push(api.portfolio.addTransactions(txs));
      if (parsed.cash_events && parsed.cash_events.length > 0) {
        promises.push(api.portfolio.addCashEvents(parsed.cash_events));
      }
      const results = await Promise.all(promises);
      const txCount = results[0]?.inserted || 0;
      const cashCount = txs.length > 0 ? (results[1]?.inserted || 0) : (results[0]?.inserted || 0);
      toast.success(`${txCount} operaciones y ${cashCount} movimientos guardados`);
      setParsed(null);
      onAdd?.();
    } catch (e) {
      toast.error("Error guardando");
    }
  };

  return (
    <div className="space-y-3">
      <details className="border border-[#e5e0d8] rounded-md p-3 bg-[#f5f3ef]" data-testid="degiro-guide">
        <summary className="cursor-pointer font-mono text-xs font-semibold text-[#1a3a32] uppercase tracking-wider">
          📋 ¿Qué archivo subir desde DEGIRO?
        </summary>
        <div className="mt-3 space-y-2 text-xs text-[#0e1f1a] leading-relaxed">
          <p className="font-semibold">Recomendado: "Informe de Transacciones" (Transactions Report)</p>
          <ol className="list-decimal list-inside space-y-1 ml-1">
            <li>Entra a tu cuenta DEGIRO en <span className="font-mono">trader.degiro.nl</span></li>
            <li>Menú lateral → <strong>"Estado"</strong> → <strong>"Informes"</strong> (o <em>"Activity"</em> → <em>"Reports"</em>)</li>
            <li>Selecciona <strong>"Informe de transacciones"</strong> (Transactions report)</li>
            <li>Elige el rango de fechas (ej: desde tu primera operación hasta hoy)</li>
            <li>Descarga en formato <strong>PDF</strong> y súbelo aquí</li>
          </ol>
          <p className="mt-2 font-semibold">También funciona:</p>
          <ul className="list-disc list-inside space-y-0.5 ml-1">
            <li><strong>"Informe Anual"</strong> (Annual report) — útil al final de año</li>
            <li><strong>"Estado de cuenta"</strong> (Account statement) — incluye también dividendos (la IA los filtra)</li>
            <li>Cualquier PDF de Trade Republic, IBKR, Revolut, etc. también funciona</li>
          </ul>
          <p className="mt-2 text-[#5c6b66] italic">
            💡 La IA detecta solo COMPRAS y VENTAS de acciones/ETFs. Ignora depósitos, dividendos y comisiones de inactividad.
          </p>
        </div>
      </details>
      <label className="block">
        <span className="text-xs text-[#5c6b66]">
          Sube uno o varios PDFs a la vez (ej: extracto 2024 + extracto 2025) — la IA extraerá todo y lo combinará
        </span>
        <input
          data-testid="pdf-upload"
          type="file"
          accept="application/pdf"
          multiple
          onChange={handleFile}
          disabled={parsing}
          className="mt-2 block w-full text-sm text-[#5c6b66] file:mr-3 file:py-2 file:px-4 file:rounded file:border-0 file:bg-[#1a3a32] file:text-[#f5f3ef] file:font-mono file:text-xs file:cursor-pointer hover:file:bg-[#0e1f1a]"
        />
      </label>
      {parsing && (
        <p className="text-sm text-[#5c6b66] flex items-center gap-2">
          <span className="inline-block w-3 h-3 border-2 border-[#1a3a32] border-t-transparent rounded-full animate-spin" />
          Analizando PDFs con IA, puede tardar 10-30s por archivo...
        </p>
      )}
      {parsed && (parsed.transactions.length > 0 || parsed.cash_events.length > 0) && (
        <div className="border border-[#e5e0d8] rounded-md p-3" data-testid="pdf-parsed-table">
          {parsed.transactions.length > 0 && (
            <>
              <p className="text-xs font-mono uppercase tracking-wider text-[#5c6b66] mb-2">
                {parsed.transactions.length} operaciones COMPRA/VENTA detectadas (edita si necesario):
              </p>
              <div className="max-h-[260px] overflow-y-auto space-y-2">
                {parsed.transactions.map((tx, i) => (
                  <div key={i} className="grid grid-cols-[1fr_60px_70px_80px_80px_30px] gap-1 items-center text-xs">
                    <Input className="h-8 font-mono text-xs" value={tx.symbol || ""} onChange={(e) => updateRow(i, "symbol", e.target.value.toUpperCase())} />
                    <Select value={tx.action || "BUY"} onValueChange={(v) => updateRow(i, "action", v)}>
                      <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="BUY">BUY</SelectItem>
                        <SelectItem value="SELL">SELL</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input className="h-8 font-mono text-xs" type="number" step="0.0001" value={tx.shares || ""} onChange={(e) => updateRow(i, "shares", e.target.value)} />
                    <Input className="h-8 font-mono text-xs" type="number" step="0.0001" value={tx.price || ""} onChange={(e) => updateRow(i, "price", e.target.value)} />
                    <Input className="h-8 font-mono text-xs" type="date" value={tx.date || ""} onChange={(e) => updateRow(i, "date", e.target.value)} />
                    <button onClick={() => removeRow(i)} className="text-[#d85c41]"><X size={14} /></button>
                  </div>
                ))}
              </div>
            </>
          )}
          {parsed.cash_events.length > 0 && (
            <div className="mt-3 pt-3 border-t border-[#e5e0d8]">
              <p className="text-xs font-mono uppercase tracking-wider text-[#5c6b66] mb-2">
                + {parsed.cash_events.length} movimientos detectados (dividendos, comisiones, etc.):
              </p>
              <div className="max-h-[140px] overflow-y-auto text-xs font-mono space-y-1">
                {parsed.cash_events.slice(0, 8).map((ev, i) => (
                  <div key={i} className="flex justify-between text-[#5c6b66]">
                    <span>{ev.date} · {ev.type}</span>
                    <span className={ev.amount >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}>
                      {ev.amount >= 0 ? "+" : ""}{ev.amount} {ev.currency}
                    </span>
                  </div>
                ))}
                {parsed.cash_events.length > 8 && <p className="text-[10px] italic">... y {parsed.cash_events.length - 8} más</p>}
              </div>
            </div>
          )}
          <Button onClick={confirmAll} className="w-full mt-3 bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono text-xs" data-testid="confirm-pdf-tx">
            Guardar todo
          </Button>
        </div>
      )}
    </div>
  );
}

export default function PortfolioView({ setSymbol }) {
  const navigate = useNavigate();
  const [data, setData] = React.useState(null);
  const [cashData, setCashData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [showAdd, setShowAdd] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const [d, ce] = await Promise.all([
        api.portfolio.get(),
        api.portfolio.cashEvents().catch(() => null),
      ]);
      setData(d);
      setCashData(ce);
    } catch (e) {
      toast.error("Error cargando cartera");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const handlePickSymbol = (s) => {
    setSymbol(s);
    navigate("/");
  };

  const removeAll = async () => {
    if (!window.confirm("¿Eliminar TODAS las transacciones? Esta acción no se puede deshacer.")) return;
    try {
      await api.portfolio.clearAll();
      toast.success("Cartera vaciada");
      load();
    } catch (e) { toast.error("Error"); }
  };

  const sectorData = React.useMemo(() => {
    if (!data?.positions) return [];
    const m = {};
    data.positions.forEach((p) => {
      const s = p.sector || "Otros";
      m[s] = (m[s] || 0) + p.market_value;
    });
    return Object.entries(m).map(([name, value]) => ({ name, value: parseFloat(value.toFixed(2)) }));
  }, [data]);

  if (loading && !data) {
    return <div className="card-flat p-8 text-center text-[#5c6b66]">Cargando cartera...</div>;
  }

  const s = data?.summary || {};
  const empty = (data?.transactions_count || 0) === 0;

  return (
    <div data-testid="portfolio-view" className="space-y-6">
      <section className="card-flat p-6 flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Briefcase size={20} weight="bold" className="text-[#1a3a32]" />
            <h2 className="font-heading font-bold text-2xl text-[#0e1f1a]">Mi Cartera</h2>
          </div>
          <p className="text-sm text-[#5c6b66] mt-1">
            {empty ? "Sube tu PDF de DEGIRO o añade operaciones manualmente." : `${data.transactions_count} transacciones · ${s.open_positions_count} posiciones abiertas`}
          </p>
        </div>
        <div className="flex gap-2">
          <Dialog open={showAdd} onOpenChange={setShowAdd}>
            <DialogTrigger asChild>
              <Button data-testid="open-add-tx" className="bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono">
                <Plus size={14} weight="bold" className="mr-1" /> Añadir operaciones
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader><DialogTitle>Añadir operaciones</DialogTitle></DialogHeader>
              <Tabs defaultValue="pdf">
                <TabsList className="grid grid-cols-2">
                  <TabsTrigger value="pdf" data-testid="tab-pdf"><Upload size={14} className="mr-1" /> Subir PDF (Auto-IA)</TabsTrigger>
                  <TabsTrigger value="manual" data-testid="tab-manual"><Plus size={14} className="mr-1" /> Manual</TabsTrigger>
                </TabsList>
                <TabsContent value="pdf" className="mt-4">
                  <PdfUploader onAdd={() => { load(); setShowAdd(false); }} />
                </TabsContent>
                <TabsContent value="manual" className="mt-4">
                  <ManualTransactionForm onAdd={() => { load(); }} />
                </TabsContent>
              </Tabs>
            </DialogContent>
          </Dialog>
          {!empty && (
            <Button onClick={removeAll} variant="outline" className="border-[#d85c41] text-[#d85c41] font-mono">
              <Trash size={14} weight="bold" className="mr-1" /> Vaciar
            </Button>
          )}
        </div>
      </section>

      {empty ? (
        <section className="card-flat p-12 text-center">
          <Wallet size={48} weight="duotone" className="text-[#1a3a32] mx-auto opacity-50" />
          <h3 className="font-heading font-bold text-xl mt-4 text-[#0e1f1a]">Tu cartera está vacía</h3>
          <p className="text-sm text-[#5c6b66] mt-2 max-w-md mx-auto">
            Sube el PDF de extracto de DEGIRO (o cualquier broker) y la IA extraerá todas tus operaciones automáticamente.
          </p>
          <Button onClick={() => setShowAdd(true)} className="mt-4 bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono">
            <Upload size={14} weight="bold" className="mr-1" /> Empezar
          </Button>
        </section>
      ) : (
        <>
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard testId="kpi-value" label="Valor Total" value={`$${fmtPrice(s.total_market_value)}`} sub={`Coste: $${fmtPrice(s.total_cost_basis)}`} />
            <StatCard testId="kpi-pnl-total" label="P&L Total" value={`${s.total_pnl >= 0 ? "+" : ""}$${fmtPrice(s.total_pnl)}`} tone={s.total_pnl >= 0 ? "buy" : "sell"} sub="Realizado + No realizado" />
            <StatCard testId="kpi-pnl-realized" label="P&L Realizado" value={`${s.realized_pnl >= 0 ? "+" : ""}$${fmtPrice(s.realized_pnl)}`} tone={s.realized_pnl >= 0 ? "buy" : "sell"} sub="Operaciones cerradas" />
            <StatCard testId="kpi-pnl-unrealized" label="P&L No Realizado" value={`${s.unrealized_pnl >= 0 ? "+" : ""}$${fmtPrice(s.unrealized_pnl)}`} tone={s.unrealized_pnl >= 0 ? "buy" : "sell"} sub={`${fmtPct(s.unrealized_pnl_pct)} sobre coste`} />
          </div>

          {/* Day change */}
          <div className="card-flat p-4 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66]">Variación hoy</span>
            <span className={`font-mono font-bold text-lg ${s.day_change_value >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
              {s.day_change_value >= 0 ? "+" : ""}${fmtPrice(s.day_change_value)}
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Positions table */}
            <section className="card-flat p-6 lg:col-span-2" data-testid="positions-table">
              <h3 className="font-heading font-semibold text-lg text-[#0e1f1a] mb-4">Posiciones Abiertas</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[#5c6b66] font-mono text-[10px] uppercase tracking-[0.15em] border-b border-[#e5e0d8]">
                      <th className="py-2">Ticker</th>
                      <th className="py-2 text-right">Acciones</th>
                      <th className="py-2 text-right">Coste medio</th>
                      <th className="py-2 text-right">Actual</th>
                      <th className="py-2 text-right">Valor</th>
                      <th className="py-2 text-right">P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.positions.map((p) => (
                      <tr key={p.symbol} data-testid={`pos-${p.symbol}`} className="border-b border-[#f0ebe1] hover:bg-[#f5f3ef] cursor-pointer" onClick={() => handlePickSymbol(p.symbol)}>
                        <td className="py-3">
                          <p className="font-mono font-semibold text-[#0e1f1a]">{p.symbol}</p>
                          <p className="text-[10px] text-[#5c6b66] truncate max-w-[140px]">{p.name}</p>
                        </td>
                        <td className="py-3 text-right font-mono">{p.shares}</td>
                        <td className="py-3 text-right font-mono text-[#5c6b66]">${fmtPrice(p.avg_cost)}</td>
                        <td className="py-3 text-right font-mono">${fmtPrice(p.current_price)}</td>
                        <td className="py-3 text-right font-mono font-semibold">${fmtPrice(p.market_value)}</td>
                        <td className={`py-3 text-right font-mono font-semibold ${p.unrealized_pnl >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                          {p.unrealized_pnl >= 0 ? "+" : ""}${fmtPrice(p.unrealized_pnl)}
                          <br/>
                          <span className="text-[10px] font-normal">{fmtPct(p.unrealized_pnl_pct)}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Sector pie */}
            {sectorData.length > 0 && (
              <section className="card-flat p-6" data-testid="sector-chart">
                <div className="flex items-center gap-2 mb-3">
                  <ChartPieSlice size={18} weight="bold" className="text-[#1a3a32]" />
                  <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Por Sector</h3>
                </div>
                <div className="h-[280px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={sectorData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={90} paddingAngle={2}>
                        {sectorData.map((entry, i) => (
                          <Cell key={i} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />
                        ))}
                      </Pie>
                      <ReTooltip formatter={(v) => `$${fmtPrice(v)}`} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-1 mt-2">
                  {sectorData.map((s, i) => (
                    <div key={s.name} className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full" style={{background: SECTOR_COLORS[i % SECTOR_COLORS.length]}} /> {s.name}</span>
                      <span className="font-mono text-[#5c6b66]">${fmtPrice(s.value)}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Realized PnL by symbol + Trades history */}
          {data.trades_history.length > 0 && (
            <section className="card-flat p-6" data-testid="trades-history">
              <h3 className="font-heading font-semibold text-lg text-[#0e1f1a] mb-3">Historial de Ventas (P&L Realizado)</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[#5c6b66] font-mono text-[10px] uppercase tracking-[0.15em] border-b border-[#e5e0d8]">
                      <th className="py-2">Fecha</th>
                      <th className="py-2">Ticker</th>
                      <th className="py-2 text-right">Acciones</th>
                      <th className="py-2 text-right">Compra</th>
                      <th className="py-2 text-right">Venta</th>
                      <th className="py-2 text-right">P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.trades_history.map((t, i) => (
                      <tr key={i} className="border-b border-[#f0ebe1]">
                        <td className="py-2 font-mono text-xs">{fmtDate(t.date)}</td>
                        <td className="py-2 font-mono font-semibold">{t.symbol}</td>
                        <td className="py-2 text-right font-mono">{t.shares}</td>
                        <td className="py-2 text-right font-mono">${fmtPrice(t.buy_avg_cost)}</td>
                        <td className="py-2 text-right font-mono">${fmtPrice(t.sell_price)}</td>
                        <td className={`py-2 text-right font-mono font-semibold ${t.realized_pnl >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                          {t.realized_pnl >= 0 ? "+" : ""}${fmtPrice(t.realized_pnl)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {/* Cash events / Costs section */}
          {cashData && cashData.events && cashData.events.length > 0 && (
            <section className="card-flat p-6" data-testid="cash-events-section">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">Costes y Movimientos de Caja</h3>
                <span className="text-xs text-[#5c6b66] font-mono">{cashData.events.length} eventos</span>
              </div>

              {/* Summary cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                <StatCard
                  testId="costs-fees"
                  label="Total Comisiones"
                  value={`${fmtPrice(cashData.summary.total_fees)} €`}
                  tone="sell"
                  sub="Conectividad + FX + otras"
                />
                <StatCard
                  testId="costs-dividends"
                  label="Dividendos Netos"
                  value={`+${fmtPrice(cashData.summary.total_dividends_net)} €`}
                  tone="buy"
                  sub={`Brutos: ${fmtPrice(cashData.summary.total_dividends_gross)} €`}
                />
                <StatCard
                  testId="costs-deposits"
                  label="Depósitos"
                  value={`+${fmtPrice(cashData.summary.total_deposits)} €`}
                />
                <StatCard
                  testId="costs-net"
                  label="Flujo Neto de Caja"
                  value={`${cashData.summary.net_cash_flow >= 0 ? "+" : ""}${fmtPrice(cashData.summary.net_cash_flow)} €`}
                  tone={cashData.summary.net_cash_flow >= 0 ? "buy" : "sell"}
                  sub="Dividendos − Comisiones"
                />
              </div>

              {/* Breakdown by type */}
              <p className="label-small mb-2">Desglose por categoría</p>
              <div className="space-y-1 mb-4">
                {cashData.by_type.sort((a, b) => Math.abs(b.total) - Math.abs(a.total)).map((t) => (
                  <div key={t.type} className="flex items-center justify-between p-2 bg-[#f5f3ef] border border-[#e5e0d8] rounded text-xs">
                    <span className="font-mono uppercase tracking-wider text-[#5c6b66]">{t.type} <span className="text-[10px]">({t.count})</span></span>
                    <span className={`font-mono font-semibold ${t.total >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                      {t.total >= 0 ? "+" : ""}{fmtPrice(t.total)} €
                    </span>
                  </div>
                ))}
              </div>

              {/* Detail list */}
              <details>
                <summary className="text-xs text-[#5c6b66] cursor-pointer font-mono uppercase tracking-wider">
                  Ver detalle ({cashData.events.length} movimientos)
                </summary>
                <div className="max-h-[300px] overflow-y-auto mt-3 space-y-1">
                  {cashData.events.map((ev, i) => (
                    <div key={i} className="grid grid-cols-[90px_100px_1fr_90px] gap-2 items-center text-xs py-1 border-b border-[#f0ebe1]">
                      <span className="font-mono text-[10px] text-[#5c6b66]">{fmtDate(ev.date)}</span>
                      <span className="font-mono text-[10px] uppercase text-[#1a3a32]">{ev.type}</span>
                      <span className="text-[#0e1f1a] truncate">{ev.description || ev.symbol || ""}</span>
                      <span className={`font-mono text-right ${ev.amount >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                        {ev.amount >= 0 ? "+" : ""}{fmtPrice(ev.amount)} {ev.currency || "€"}
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            </section>
          )}
        </>
      )}
    </div>
  );
}
