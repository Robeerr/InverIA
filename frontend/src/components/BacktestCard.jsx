import React from "react";
import { ChartLineUp, ShieldCheck, Spinner } from "@phosphor-icons/react";
import { Button } from "./ui/button";
import { api } from "../lib/api";

function rateTone(rate) {
  if (rate == null) return { text: "text-[#5c6b66]", bar: "bg-[#9aa39f]" };
  if (rate >= 70) return { text: "text-[#4a7c59]", bar: "bg-[#4a7c59]" };
  if (rate >= 55) return { text: "text-[#8a6508]", bar: "bg-[#c9a14a]" };
  return { text: "text-[#d85c41]", bar: "bg-[#d85c41]" };
}

function RateRow({ label, stat }) {
  const tone = rateTone(stat?.hold_rate);
  const rate = stat?.hold_rate;
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono text-[11px] text-[#3a4a44] w-28 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-[#e5e0d8] rounded-full overflow-hidden">
        <div className={`h-full ${tone.bar} transition-all`} style={{ width: `${rate ?? 0}%` }} />
      </div>
      <span className={`font-mono text-[11px] font-semibold w-20 text-right ${tone.text}`}>
        {rate != null ? `${rate}%` : "s/datos"}
        {stat?.n ? <span className="text-[#9aa39f] font-normal"> ({stat.n})</span> : null}
      </span>
      <span className="font-mono text-[10px] text-[#5c6b66] w-32 text-right shrink-0">
        {stat?.clean_hold_rate != null ? `limpio ${stat.clean_hold_rate}%` : ""}
        {stat?.avg_bounce_atr != null ? ` · ${stat.avg_bounce_atr}×ATR` : ""}
      </span>
    </div>
  );
}

export default function BacktestCard({ symbol }) {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState(null);
  const [scope, setScope] = React.useState("symbol"); // "symbol" | "universe"

  // Reset when symbol changes so stale results don't show under a new ticker.
  React.useEffect(() => { if (scope === "symbol") { setData(null); setErr(null); } }, [symbol, scope]);

  const run = async (which) => {
    setScope(which);
    setLoading(true);
    setErr(null);
    setData(null);
    try {
      const res = which === "universe"
        ? await api.backtestUniverse()
        : await api.backtest(symbol);
      if (res?.status === "running") {
        setErr("Backtest del universo en curso (es pesado). Vuelve a pulsar en un minuto.");
      } else if (res?.error || !res?.samples) {
        setErr(which === "universe"
          ? "No se pudo agregar el backtest del universo."
          : "Histórico insuficiente para backtestear esta acción.");
      } else {
        setData(res);
      }
    } catch (e) {
      setErr(e?.response?.data?.detail || "No se pudo ejecutar el backtest.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section data-testid="backtest-card" className="card-flat p-6">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-2">
        <div className="flex items-center gap-2">
          <ShieldCheck size={20} weight="bold" className="text-[#1a3a32]" />
          <h3 className="font-heading font-bold text-xl text-[#0e1f1a]">Fiabilidad histórica de los niveles</h3>
        </div>
        <div className="flex items-center gap-2">
          <Button
            data-testid="run-backtest"
            onClick={() => run("symbol")}
            disabled={loading || !symbol}
            variant="outline"
            className="border-[#e5e0d8] font-mono text-xs"
          >
            {loading && scope === "symbol" ? <Spinner size={14} weight="bold" className="mr-1 animate-spin" /> : <ChartLineUp size={14} weight="bold" className="mr-1" />}
            {loading && scope === "symbol" ? "Backtesteando…" : `Backtest ${symbol}`}
          </Button>
          <Button
            data-testid="run-backtest-universe"
            onClick={() => run("universe")}
            disabled={loading}
            variant="outline"
            className="border-[#1a3a32]/30 bg-[#1a3a32]/5 font-mono text-xs"
          >
            {loading && scope === "universe" ? <Spinner size={14} weight="bold" className="mr-1 animate-spin" /> : <ChartLineUp size={14} weight="bold" className="mr-1" />}
            {loading && scope === "universe" ? "Agregando…" : "Backtest del universo"}
          </Button>
        </div>
      </div>

      <p className="text-sm text-[#5c6b66] mb-4">
        Recorre los últimos años calculando los niveles con datos solo del pasado (sin trampa) y mide
        cuántas veces el precio <strong>rebotó</strong> al tocarlos. Así sabes qué fuerza es fiable de verdad.
      </p>

      {err && <p className="text-sm text-[#d85c41]">{err}</p>}

      {!data && !err && !loading && (
        <p className="text-xs text-[#5c6b66] italic">
          «Backtest {symbol}» valida los niveles de esta acción (pocas muestras). «Backtest del universo» agrega
          ~30 acciones para una cifra estadísticamente sólida (tarda 1-2 min, se cachea 24h).
        </p>
      )}

      {data && (
        <div className="space-y-4">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-3xl font-bold text-[#0e1f1a]">{data.overall?.hold_rate ?? "—"}%</span>
            <span className="text-sm text-[#5c6b66]">
              de los niveles tocados aguantaron · {data.samples} pruebas
              {data.symbols_tested ? ` · ${data.symbols_tested} acciones` : ""} · ventana {data.forward_window_days} días
            </span>
          </div>

          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] mb-2">Por fuerza del nivel</p>
            <div className="space-y-2">
              <RateRow label="Fuerte (≥75)" stat={data.by_strength?.fuerte} />
              <RateRow label="Media (50-74)" stat={data.by_strength?.media} />
              <RateRow label="Débil (<50)" stat={data.by_strength?.debil} />
            </div>
          </div>

          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] mb-2">Estructural vs táctico</p>
            <div className="space-y-2">
              <RateRow label="Estructural" stat={data.by_kind?.estructural} />
              <RateRow label="Táctico" stat={data.by_kind?.tactico} />
            </div>
          </div>

          {data.by_source && Object.keys(data.by_source).length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] mb-2">
                Edge real por metodología (ordenado por durabilidad)
              </p>
              <div className="space-y-1">
                {Object.entries(data.by_source).map(([src, st]) => (
                  <div key={src} className="flex items-center gap-3 text-[11px] font-mono">
                    <span className="text-[#3a4a44] w-32 shrink-0 truncate">{src}</span>
                    <div className="flex-1 h-1.5 bg-[#e5e0d8] rounded-full overflow-hidden">
                      <div className={`h-full ${rateTone(st.clean_hold_rate).bar}`} style={{ width: `${st.clean_hold_rate ?? 0}%` }} />
                    </div>
                    <span className={`w-28 text-right ${rateTone(st.clean_hold_rate).text}`}>
                      limpio {st.clean_hold_rate}%
                    </span>
                    <span className="text-[#5c6b66] w-24 text-right">{st.avg_bounce_atr}×ATR</span>
                    <span className="text-[#9aa39f] w-12 text-right">({st.n})</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-[10px] text-[#5c6b66] leading-relaxed">
            «Aguantó» = rebotó ≥1×ATR antes de romperse (tasa de rebote). «Limpio» = nunca se rompió por cierre en
            toda la ventana (durabilidad). «×ATR» = tamaño medio del rebote. La fuerza del nivel debería notarse
            sobre todo en «limpio» y en el tamaño del rebote, no tanto en la tasa de rebote simple.
          </p>
        </div>
      )}
    </section>
  );
}
