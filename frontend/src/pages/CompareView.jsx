import React from "react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import { Plus, X, Scales } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { api } from "../lib/api";
import { fmtPrice, fmtPct, fmtNum } from "../lib/format";

const COLORS = ["#1a3a32", "#d85c41", "#4a7c59", "#c9a14a", "#5c6b66", "#7a4e8c"];

export default function CompareView() {
  const [symbols, setSymbols] = React.useState(["AAPL", "MSFT", "NVDA"]);
  const [input, setInput] = React.useState("");
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    if (symbols.length === 0) {
      setData(null);
      return;
    }
    setLoading(true);
    try {
      const res = await api.compare(symbols);
      setData(res);
    } catch (e) {
      // noop
    } finally {
      setLoading(false);
    }
  }, [symbols]);

  React.useEffect(() => {
    load();
  }, [load]);

  const addSymbol = (e) => {
    e.preventDefault();
    const s = input.trim().toUpperCase();
    if (s && !symbols.includes(s) && symbols.length < 6) {
      setSymbols([...symbols, s]);
      setInput("");
    }
  };

  const removeSymbol = (s) => {
    setSymbols(symbols.filter((x) => x !== s));
  };

  // Build normalized chart data (% change from first)
  const chartData = React.useMemo(() => {
    if (!data) return [];
    const series = {};
    let allDates = new Set();
    (data.items || []).forEach((item) => {
      if (!item.candles || item.candles.length === 0) return;
      const first = item.candles[0].close;
      series[item.symbol] = {};
      item.candles.forEach((c) => {
        const date = c.date.split("T")[0];
        series[item.symbol][date] = ((c.close - first) / first) * 100;
        allDates.add(date);
      });
    });
    const sortedDates = Array.from(allDates).sort();
    return sortedDates.map((d) => {
      const point = { date: d };
      Object.keys(series).forEach((s) => {
        point[s] = series[s][d];
      });
      return point;
    });
  }, [data]);

  return (
    <div data-testid="compare-view" className="space-y-6">
      <section className="card-flat p-6">
        <div className="flex items-center gap-2 mb-2">
          <Scales size={20} weight="bold" className="text-[#1a3a32]" />
          <h2 className="font-heading font-bold text-2xl text-[#0e1f1a]">Comparador Multi-Acción</h2>
        </div>
        <p className="text-sm text-[#5c6b66] mb-4">
          Compara hasta 6 acciones lado a lado · Rendimiento relativo en los últimos 3 meses.
        </p>
        <form onSubmit={addSymbol} className="flex gap-2 mb-4">
          <Input
            data-testid="compare-input"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="Añadir ticker (ej: TSLA)"
            className="bg-white border-[#e5e0d8] font-mono"
            maxLength={6}
          />
          <Button
            data-testid="compare-add"
            type="submit"
            disabled={!input || symbols.length >= 6}
            className="bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono"
          >
            <Plus size={16} weight="bold" className="mr-1" />
            Añadir
          </Button>
        </form>
        <div className="flex flex-wrap gap-2">
          {symbols.map((s, i) => (
            <div
              key={s}
              data-testid={`compare-tag-${s}`}
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full border"
              style={{ borderColor: COLORS[i], color: COLORS[i], background: `${COLORS[i]}10` }}
            >
              <span className="font-mono font-semibold text-sm">{s}</span>
              <button onClick={() => removeSymbol(s)} className="hover:opacity-70">
                <X size={12} weight="bold" />
              </button>
            </div>
          ))}
        </div>
      </section>

      {loading && <div className="card-flat p-6 text-center text-[#5c6b66]">Cargando comparación...</div>}

      {data && (
        <>
          {/* Comparison table */}
          <section className="card-flat p-6 overflow-x-auto">
            <h3 className="font-heading font-semibold text-lg text-[#0e1f1a] mb-4">Tabla Comparativa</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[#5c6b66] font-mono text-[10px] uppercase tracking-[0.15em] border-b border-[#e5e0d8]">
                  <th className="py-2">Ticker</th>
                  <th className="py-2 text-right">Precio</th>
                  <th className="py-2 text-right">Var. Día</th>
                  <th className="py-2 text-right">P/E</th>
                  <th className="py-2 text-right">Cap. Mercado</th>
                  <th className="py-2 text-right">RSI</th>
                  <th className="py-2 text-right">52W Alto</th>
                  <th className="py-2 text-right">52W Bajo</th>
                </tr>
              </thead>
              <tbody>
                {(data.items || []).map((item) => {
                  if (item.error) {
                    return (
                      <tr key={item.symbol} className="border-b border-[#f0ebe1]">
                        <td className="py-3 font-mono font-semibold">{item.symbol}</td>
                        <td className="py-3 text-[#d85c41] text-sm" colSpan={7}>{item.error}</td>
                      </tr>
                    );
                  }
                  const q = item.quote;
                  const up = (q.change ?? 0) >= 0;
                  return (
                    <tr key={item.symbol} data-testid={`compare-row-${item.symbol}`} className="border-b border-[#f0ebe1] hover:bg-[#f5f3ef]">
                      <td className="py-3 font-mono font-semibold text-[#0e1f1a]">{item.symbol}</td>
                      <td className="py-3 text-right font-mono">${fmtPrice(q.price)}</td>
                      <td className={`py-3 text-right font-mono ${up ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                        {fmtPct(q.change_percent)}
                      </td>
                      <td className="py-3 text-right font-mono">{q.pe_ratio ?? "—"}</td>
                      <td className="py-3 text-right font-mono">${fmtNum(q.market_cap)}</td>
                      <td className="py-3 text-right font-mono">{item.indicators?.rsi ?? "—"}</td>
                      <td className="py-3 text-right font-mono">${fmtPrice(q.high_52w)}</td>
                      <td className="py-3 text-right font-mono">${fmtPrice(q.low_52w)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          {/* Normalized chart */}
          {chartData.length > 0 && (
            <section className="card-flat p-6">
              <h3 className="font-heading font-semibold text-lg text-[#0e1f1a] mb-1">Rendimiento Relativo</h3>
              <p className="text-xs text-[#5c6b66] mb-4">Variación % desde hace 3 meses (base 0)</p>
              <div className="h-[420px]" style={{ minHeight: 420 }}>
                <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={420}>
                  <LineChart data={chartData}>
                    <CartesianGrid stroke="#e5e0d8" strokeDasharray="3 3" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 10, fill: "#5c6b66", fontFamily: "IBM Plex Mono" }}
                      tickFormatter={(d) => new Date(d).toLocaleDateString("es-ES", { day: "2-digit", month: "short" })}
                      minTickGap={40}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "#5c6b66", fontFamily: "IBM Plex Mono" }}
                      tickFormatter={(v) => `${v.toFixed(0)}%`}
                      width={56}
                      orientation="right"
                    />
                    <Tooltip
                      contentStyle={{ background: "white", border: "1px solid #e5e0d8", borderRadius: 6, fontFamily: "IBM Plex Mono", fontSize: 12 }}
                      formatter={(v, name) => [`${v?.toFixed(2)}%`, name]}
                    />
                    <Legend wrapperStyle={{ fontFamily: "IBM Plex Mono", fontSize: 11 }} />
                    {symbols.map((s, i) => (
                      <Line
                        key={s}
                        type="monotone"
                        dataKey={s}
                        stroke={COLORS[i]}
                        strokeWidth={2}
                        dot={false}
                        isAnimationActive={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
