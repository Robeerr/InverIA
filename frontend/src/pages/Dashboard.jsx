import React, { useEffect, useState, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import QuoteHeader from "../components/QuoteHeader";
import LightweightChart from "../components/LightweightChart";
import ChartistPanel from "../components/ChartistPanel";
import RecommendationPanel from "../components/RecommendationPanel";
import SourcesPanel from "../components/SourcesPanel";
import { AlternativePanel } from "../components/MoreInsights";
import WatchlistStrip from "../components/WatchlistStrip";
import BottomSignalBar from "../components/BottomSignalBar";
import IndicatorsPanel from "../components/IndicatorsPanel";
import TradingLevels from "../components/TradingLevels";
import WhyMovingCard from "../components/WhyMovingCard";
import BacktestCard from "../components/BacktestCard";
import AnalystConsensusCard from "../components/AnalystConsensus";
import { NewsFeed, FundamentalsCard, RisksCatalystsCard, MarketSignalsCard, InvestmentThesisCard, PricePredictionCard } from "../components/InfoCards";
import { api } from "../lib/api";
import { useSignals } from "../hooks/useSignals";

function MarketFuturesBar({ futures }) {
  if (!futures?.items?.length) return null;
  return (
    <div className="card-flat px-4 py-2.5 flex items-center gap-x-5 gap-y-1 flex-wrap">
      <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono">Futuros · apertura</span>
      {futures.items.map((f) => {
        const up = (f.change_percent ?? 0) >= 0;
        return (
          <div key={f.symbol} className="flex items-center gap-2">
            <span className="text-xs text-[#0e1f1a] font-medium">{f.label}</span>
            <span className={`font-mono text-xs font-semibold ${up ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
              {f.change_percent != null ? `${up ? "+" : ""}${f.change_percent}%` : "—"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function MarketRegimeBar({ regime }) {
  if (!regime || regime.light === "desconocido") return null;
  const styles = {
    verde:    { dot: "#4a7c59", bg: "bg-[#4a7c59]/8",  border: "border-[#4a7c59]/30", text: "text-[#4a7c59]" },
    amarillo: { dot: "#c9a14a", bg: "bg-[#c9a14a]/8",  border: "border-[#c9a14a]/30", text: "text-[#c9a14a]" },
    rojo:     { dot: "#d85c41", bg: "bg-[#d85c41]/10", border: "border-[#d85c41]/40", text: "text-[#d85c41]" },
  }[regime.light] || {};
  return (
    <div className={`card-flat px-4 py-2.5 flex items-center gap-3 flex-wrap ${regime.light === "rojo" ? "border " + styles.border : ""}`}>
      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: styles.dot }} />
      <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono">Mercado</span>
      <span className={`text-xs font-semibold ${styles.text}`}>{regime.label}</span>
      {regime.spy_price != null && (
        <span className="text-[11px] text-[#5c6b66] font-mono ml-auto">
          S&P {regime.dist_sma200_pct >= 0 ? "+" : ""}{regime.dist_sma200_pct}% vs SMA200
        </span>
      )}
    </div>
  );
}

// Aviso de frescura/origen de datos (#7): fuente de respaldo (Stooq) o datos con retraso.
function DataHealthBar({ health }) {
  if (!health || !health.degraded) return null;
  return (
    <div className="card-flat px-4 py-2 flex items-center gap-2 border border-[#c9a14a]/40 bg-[#c9a14a]/[0.06]">
      <span className="text-sm">⚠️</span>
      <span className="text-[11px] text-[#8a6508] leading-snug">
        <b>Datos de respaldo o con retraso</b>{health.note ? ` · ${health.note}` : ""}. El análisis puede no reflejar el precio en vivo — trátalo con cautela.
      </span>
    </div>
  );
}

// Termómetro Miedo/Codicia del mercado (#28): 0 = pánico, 100 = euforia.
function FearGreedBar({ data }) {
  if (!data || data.score == null) return null;
  const s = data.score;
  const color = s < 25 ? "#d85c41" : s < 45 ? "#e08a3c" : s <= 55 ? "#c9a14a" : "#4a7c59";
  return (
    <div className="card-flat px-4 py-2.5 flex items-center gap-3 flex-wrap">
      <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono shrink-0">Miedo / Codicia</span>
      <div className="flex items-center gap-2 min-w-[140px] flex-1">
        <div className="relative h-2 rounded-full flex-1 overflow-hidden" style={{ background: "linear-gradient(90deg,#d85c41,#c9a14a,#4a7c59)" }}>
          <div className="absolute top-1/2 -translate-y-1/2 w-1 h-3.5 bg-[#0e1f1a] rounded-full" style={{ left: `calc(${s}% - 2px)` }} />
        </div>
        <span className="font-mono font-bold text-sm shrink-0" style={{ color }}>{s}</span>
      </div>
      <span className="text-xs font-semibold shrink-0" style={{ color }}>{data.label}</span>
      {data.vix != null && <span className="text-[11px] text-[#5c6b66] font-mono shrink-0">VIX {data.vix}</span>}
      {data.advice && <span className="text-[11px] text-[#5c6b66] w-full sm:w-auto sm:ml-auto sm:max-w-[380px] leading-snug">{data.advice}</span>}
    </div>
  );
}

// Heatmap de sectores (#27): variación del día por sector, para leer el mercado de un vistazo.
function SectorHeatmap({ data, onPick }) {
  const sectors = data?.sectors;
  if (!Array.isArray(sectors) || !sectors.length) return null;
  const tone = (chg) => {
    const v = Math.max(-3, Math.min(3, chg)) / 3;  // normaliza a ±3%
    if (v >= 0) return `rgba(74,124,89,${0.12 + v * 0.55})`;   // verde
    return `rgba(216,92,65,${0.12 + Math.abs(v) * 0.55})`;      // rojo
  };
  return (
    <div className="card-flat px-4 py-3">
      <p className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono mb-2">Sectores hoy</p>
      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-1.5">
        {sectors.map((s) => (
          <button
            key={s.symbol}
            onClick={() => onPick && onPick(s.symbol)}
            title={`${s.sector} (${s.symbol})`}
            className="rounded-md px-2 py-1.5 text-left transition-transform hover:scale-[1.03]"
            style={{ background: tone(s.change_percent) }}
          >
            <div className="text-[11px] font-semibold text-[#0e1f1a] truncate leading-tight">{s.sector}</div>
            <div className="text-[12px] font-mono font-bold text-[#0e1f1a]">
              {s.change_percent >= 0 ? "+" : ""}{s.change_percent.toFixed(2)}%
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard({ symbol, setSymbol, model, setModel }) {
  const [timeframe, setTimeframe] = useState("1D");
  const [quote, setQuote] = useState(null);
  const [candles, setCandles] = useState([]);
  const [indicators, setIndicators] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analystData, setAnalystData] = useState(null);
  const [marketSignals, setMarketSignals] = useState(null);
  const [volumeProfile, setVolumeProfile] = useState(null);
  const [buyLevels, setBuyLevels] = useState(null);
  const [chartLines, setChartLines] = useState(null);
  const [marketRegime, setMarketRegime] = useState(null);
  const [dataHealth, setDataHealth] = useState(null);
  const [ctxOpen, setCtxOpen] = useState(false);  // contexto de mercado plegado en móvil
  const [news, setNews] = useState([]);
  const [loadingQuote, setLoadingQuote] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [signalEntry, setSignalEntry] = useState(null);

  // Señales (caché compartido entre páginas) y futuros (refresco 60s) vía react-query.
  const { data: signals } = useSignals();
  const { data: futures } = useQuery({
    queryKey: ["market-futures"],
    queryFn: api.marketFutures,
    refetchInterval: 60_000,
    staleTime: 60_000,
  });
  const { data: sentiment } = useQuery({
    queryKey: ["market-sentiment"],
    queryFn: api.marketSentiment,
    refetchInterval: 15 * 60_000,
    staleTime: 15 * 60_000,
  });
  const { data: heatmap } = useQuery({
    queryKey: ["market-heatmap"],
    queryFn: api.marketHeatmap,
    refetchInterval: 5 * 60_000,
    staleTime: 5 * 60_000,
  });

  // Contador de petición: descarta respuestas que llegan tarde tras cambiar de símbolo
  // (una petición lenta no debe pisar datos de un símbolo posterior).
  const reqId = useRef(0);

  const loadSymbolData = useCallback(async (sym, tf) => {
    const my = ++reqId.current;
    setLoadingQuote(true);
    setAnalysis(null);
    setMarketSignals(null);
    setVolumeProfile(null);
    setBuyLevels(null);
    setChartLines(null);
    setDataHealth(null);
    // 1 reintento rápido ante un fallo de red puntual.
    const fetchWithRetry = async () => {
      try {
        return await api.dashboard(sym, tf);
      } catch (e) {
        await new Promise((r) => setTimeout(r, 600));
        return await api.dashboard(sym, tf);
      }
    };
    try {
      const data = await fetchWithRetry();
      if (my !== reqId.current) return; // llegó tarde: ya cambiamos de símbolo
      if (!data?.quote) {
        toast.error(`No se encontró el símbolo ${sym}`);
        setQuote(null);
        return;
      }
      setQuote(data.quote);
      setCandles(data.candles || []);
      setIndicators(data.indicators);
      setNews(data.news || []);
      setAnalystData(data.analyst);
      // Niveles del motor (deterministas): disponibles ya al cargar, sin esperar a la IA.
      if (data.buy_levels) setBuyLevels(data.buy_levels);
      if (data.lines) setChartLines(data.lines);
      if (data.volume_profile) setVolumeProfile(data.volume_profile);
      if (data.market_regime) setMarketRegime(data.market_regime);
      setDataHealth(data.data_health || null);
    } catch (e) {
      if (my === reqId.current) {
        const st = e?.response?.status;
        if (st === 404) {
          setQuote(null);
          toast.error(`"${sym}" no existe. Revisa el símbolo (p.ej. AAPL, no APPL).`);
        } else {
          toast.error("Error al cargar datos. Inténtalo de nuevo.");
        }
      }
    } finally {
      if (my === reqId.current) setLoadingQuote(false);
    }
  }, []);

  const chartReqId = useRef(0);
  const refreshTimeframe = useCallback(
    async (tf) => {
      const my = ++chartReqId.current;
      setTimeframe(tf);
      try {
        const c = await api.chart(symbol, tf);
        if (my !== chartReqId.current) return; // respuesta obsoleta
        setCandles(c.candles || []);
        setChartLines(c.lines || null);
      } catch (e) {
        if (my === chartReqId.current) toast.error("Error al cargar el gráfico");
      }
    },
    [symbol]
  );

  const runAnalysis = useCallback(async () => {
    if (!symbol) return;
    setLoadingAnalysis(true);
    try {
      const res = await api.analyze(symbol, model);
      setAnalysis(res.analysis);
      if (res.indicators) setIndicators(res.indicators);
      // Merge quote without overwriting good fields with nulls — yfinance .info
      // sometimes returns an incomplete quote (missing P/E, EPS, beta...).
      if (res.quote) {
        setQuote((prev) => {
          if (!prev) return res.quote;
          const merged = { ...prev };
          for (const [k, v] of Object.entries(res.quote)) {
            if (v != null) merged[k] = v;
          }
          return merged;
        });
      }
      if (res.analyst_consensus || res.price_target) {
        setAnalystData({
          symbol,
          consensus: res.analyst_consensus,
          price_target: res.price_target,
        });
      }
      if (res.insider || res.earnings_history) {
        setMarketSignals({ insider: res.insider, earningsHistory: res.earnings_history });
      }
      if (res.volume_profile) setVolumeProfile(res.volume_profile);
      if (res.buy_levels) setBuyLevels(res.buy_levels);
      if (res.fellback) {
        toast.warning(`${res.requested_model} no disponible (límite o error) — análisis hecho con ${res.model}`);
      } else {
        toast.success(`Análisis completado (${res.model || model})`);
      }
    } catch (e) {
      const msg = e?.response?.data?.detail || "Error al generar análisis IA";
      toast.error(msg);
    } finally {
      setLoadingAnalysis(false);
    }
  }, [symbol, model]);

  useEffect(() => {
    loadSymbolData(symbol, timeframe);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  // Marca la entrada de señal del símbolo actual a partir del caché compartido.
  useEffect(() => {
    if (!symbol || !signals) { setSignalEntry(null); return; }
    setSignalEntry(signals.find((e) => e.symbol === symbol.toUpperCase()) || null);
  }, [symbol, signals]);

  // WebSocket for live tick-by-tick price updates (Finnhub trade stream).
  // Reconnects with exponential backoff (2s→4s→8s→16s→32s) before falling
  // back to 30s REST polling if all 5 attempts fail.
  useEffect(() => {
    if (!symbol) return;
    let ws;
    let closed = false;
    let retries = 0;
    const MAX_RETRIES = 5;
    const fallbackRef = { id: null };

    // Throttle ticks to one setState per animation frame.
    const pending = { data: null };
    let rafId = null;
    const flush = () => {
      rafId = null;
      if (!pending.data) return;
      const next = pending.data;
      pending.data = null;
      setQuote((prev) => (prev ? { ...prev, ...next } : prev));
    };
    const scheduleUpdate = (data) => {
      pending.data = { ...(pending.data || {}), ...data };
      if (rafId == null) rafId = requestAnimationFrame(flush);
    };

    const startFallback = () => {
      if (fallbackRef.id) return;
      fallbackRef.id = setInterval(async () => {
        try {
          const q = await api.quote(symbol);
          if (!closed) setQuote(q);
        } catch {}
      }, 30000);
    };

    const connect = () => {
      if (closed) return;
      try {
        const base = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
        const wsBase = base.replace(/^https:\/\//, "wss://").replace(/^http:\/\//, "ws://");
        ws = new WebSocket(`${wsBase}/api/ws/quote/${symbol}`);
        ws.onopen = () => { retries = 0; };
        ws.onmessage = (e) => {
          try { scheduleUpdate(JSON.parse(e.data)); } catch {}
        };
        ws.onerror = () => {};
        ws.onclose = () => {
          if (closed) return;
          if (retries < MAX_RETRIES) {
            const delay = Math.min(2000 * 2 ** retries, 32000);
            retries++;
            setTimeout(connect, delay);
          } else {
            startFallback();
          }
        };
      } catch {
        startFallback();
      }
    };

    connect();

    return () => {
      closed = true;
      if (rafId != null) cancelAnimationFrame(rafId);
      if (fallbackRef.id) clearInterval(fallbackRef.id);
      if (ws) ws.close();
    };
  }, [symbol]);


  return (
    <div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6 lg:flex lg:gap-5 lg:items-start">
      {/* Escritorio: watchlist como barra lateral izquierda (sticky). */}
      <aside className="hidden lg:block w-52 shrink-0 sticky top-4">
        <WatchlistStrip symbol={symbol} setSymbol={setSymbol} vertical />
      </aside>
      <main data-testid="main-dashboard" className="flex-1 min-w-0 space-y-4 sm:space-y-6">
      {/* Móvil: watchlist como tira horizontal arriba. */}
      <WatchlistStrip symbol={symbol} setSymbol={setSymbol} className="lg:hidden" />

      {/* Contexto de mercado — plegable en MÓVIL para llegar antes a la acción buscada.
          En escritorio siempre visible. El botón muestra un resumen compacto (semáforo +
          miedo/codicia) aunque esté plegado. */}
      <button
        onClick={() => setCtxOpen((o) => !o)}
        className="lg:hidden card-flat px-4 py-2.5 flex items-center gap-2 w-full text-left"
      >
        <span className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] font-mono">Mercado hoy</span>
        {marketRegime?.light && marketRegime.light !== "desconocido" && (
          <span className="w-2 h-2 rounded-full" style={{ background: marketRegime.light === "rojo" ? "#d85c41" : marketRegime.light === "amarillo" ? "#c9a14a" : "#4a7c59" }} />
        )}
        {sentiment?.score != null && (
          <span className="text-[11px] font-mono text-[#5c6b66]">M/C {sentiment.score}</span>
        )}
        <span className="ml-auto text-[11px] text-[#5c6b66]">{ctxOpen ? "ocultar ▲" : "ver ▼"}</span>
      </button>

      <div className={`${ctxOpen ? "block" : "hidden"} lg:block space-y-4 sm:space-y-6`}>
        <MarketFuturesBar futures={futures} />
        <MarketRegimeBar regime={marketRegime} />
        <FearGreedBar data={sentiment} />
        <SectorHeatmap data={heatmap} onPick={setSymbol} />
      </div>

      {loadingQuote && !quote ? (
        <div className="card-flat p-8 text-center text-[#5c6b66]">Cargando datos...</div>
      ) : quote ? (
        <QuoteHeader quote={quote} />
      ) : null}

      {quote && <DataHealthBar health={dataHealth} />}
      {quote && <WhyMovingCard symbol={symbol} model={model} />}

      <TradingLevels
        quote={quote}
        analysis={analysis}
        analystConsensus={analystData?.consensus}
        priceTarget={analystData?.price_target}
        volumeProfile={volumeProfile}
        buyLevels={buyLevels}
      />

      {quote && <BacktestCard symbol={symbol} />}

      {/* Móvil: flex-col con orden explícito → gráfico+Chartista, LUEGO la Recomendación IA
          (columna derecha), y por último Consenso/Indicadores. Antes la columna derecha
          quedaba enterrada al final y parecía no existir. Escritorio (xl): 2 columnas. */}
      <div className="flex flex-col xl:grid xl:grid-cols-[1fr_360px] xl:grid-rows-[auto_auto] gap-6">
        {/* A: gráfico + Chartista */}
        <div className="min-w-0 order-1 xl:col-start-1 xl:row-start-1">
          <LightweightChart
            candles={candles}
            indicators={indicators}
            buyLevels={buyLevels}
            lines={chartLines}
            timeframe={timeframe}
            setTimeframe={refreshTimeframe}
          />
          <div className="mt-4">
            <ChartistPanel symbol={symbol} />
          </div>
        </div>
        {/* B: columna derecha (Recomendación IA + Fuentes + Alternativa). En móvil va justo
            debajo del gráfico; en escritorio ocupa la 2ª columna a lo alto. */}
        <div className="space-y-4 order-2 xl:col-start-2 xl:row-start-1 xl:row-span-2">
          <RecommendationPanel
            analysis={analysis}
            isLoading={loadingAnalysis}
            onAnalyze={runAnalysis}
            model={model}
            setModel={setModel}
          />
          <SourcesPanel symbol={symbol} />
          <AlternativePanel symbol={symbol} onPick={setSymbol} />
        </div>
        {/* C: Consenso + Indicadores. En escritorio bajo el gráfico (col 1); en móvil al final. */}
        <div className="space-y-4 sm:space-y-6 order-3 xl:col-start-1 xl:row-start-2">
          <AnalystConsensusCard data={analystData} />
          <IndicatorsPanel indicators={indicators} analysis={analysis} />
        </div>
      </div>

      {analysis && <PricePredictionCard analysis={analysis} quote={quote} />}

      <FundamentalsCard quote={quote} analysis={analysis} />

      {marketSignals && (
        <MarketSignalsCard
          insider={marketSignals.insider}
          earningsHistory={marketSignals.earningsHistory}
        />
      )}

      {analysis && <InvestmentThesisCard analysis={analysis} />}

      {analysis && <RisksCatalystsCard analysis={analysis} />}

      <NewsFeed news={news} />

      {/* Espacio para que la barra de señal fija no tape el contenido */}
      {quote && <div className="h-16" />}
      <BottomSignalBar symbol={symbol} quote={quote} indicators={indicators} analysis={analysis} />
      </main>
    </div>
  );
}
