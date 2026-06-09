import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Fire, TrendUp, TrendDown, ArrowRight } from "@phosphor-icons/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import QuoteHeader from "../components/QuoteHeader";
import PriceChart from "../components/PriceChart";
import RecommendationPanel from "../components/RecommendationPanel";
import IndicatorsPanel from "../components/IndicatorsPanel";
import SidebarLists from "../components/SidebarLists";
import TradingLevels from "../components/TradingLevels";
import AnalystConsensusCard from "../components/AnalystConsensus";
import { NewsFeed, FundamentalsCard, RisksCatalystsCard } from "../components/InfoCards";
import { api } from "../lib/api";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

function HotSignals({ onPickSymbol }) {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/signals/hot?limit=5`)
      .then((r) => r.json())
      .then(setSignals)
      .catch(() => setSignals([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="card-flat p-4 animate-pulse">
      <div className="h-4 bg-[#e5e0d8] rounded w-1/3 mb-3" />
      <div className="space-y-2">{[1,2,3].map(i=><div key={i} className="h-10 bg-[#e5e0d8] rounded" />)}</div>
    </div>
  );
  if (signals.length === 0) return null;

  return (
    <div className="card-flat p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Fire size={18} weight="fill" className="text-orange-500" />
          <h3 className="font-heading font-semibold text-base text-[#0e1f1a]">Señales Calientes</h3>
          <span className="text-xs font-mono text-[#5c6b66]">· cercanas a un nivel</span>
        </div>
        <Link to="/signals" className="flex items-center gap-1 text-xs font-mono text-[#1a3a32] hover:underline">
          Ver todas <ArrowRight size={12} />
        </Link>
      </div>
      <div className="space-y-2">
        {signals.map((s) => (
          <button
            key={s.symbol}
            onClick={() => onPickSymbol(s.symbol)}
            className="w-full flex items-center gap-3 p-3 rounded-lg border border-[#e5e0d8] bg-white hover:bg-[#f5f3ef] transition-colors text-left"
          >
            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${s.action === "COMPRA" ? "bg-green-100" : "bg-red-100"}`}>
              {s.action === "COMPRA"
                ? <TrendUp size={16} weight="bold" className="text-green-600" />
                : <TrendDown size={16} weight="bold" className="text-red-600" />
              }
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold text-sm text-[#1a3a32]">{s.symbol}</span>
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${s.action === "COMPRA" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                  {s.action}
                </span>
                {s.riesgo && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold
                    ${s.riesgo === "BAJO" ? "bg-green-50 text-green-600 border-green-200" :
                      s.riesgo === "MEDIO" ? "bg-yellow-50 text-yellow-700 border-yellow-200" :
                      "bg-red-50 text-red-600 border-red-200"}`}>
                    {s.riesgo}
                  </span>
                )}
              </div>
              <p className="text-xs text-[#5c6b66] truncate">{s.name}</p>
            </div>
            <div className="text-right flex-shrink-0">
              <p className="font-mono font-semibold text-sm text-[#0e1f1a]">${Number(s.price).toFixed(2)}</p>
              <p className={`text-xs font-mono font-semibold ${s.pct_away < 2 ? "text-orange-500" : "text-[#5c6b66]"}`}>
                {s.pct_away < 0.5 ? "⚡ " : s.pct_away < 2 ? "🔥 " : ""}{s.pct_away.toFixed(2)}% del nivel
              </p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard({ symbol, setSymbol, model }) {
  const queryClient = useQueryClient();
  const [timeframe, setTimeframe] = useState("1Y");
  const [quote, setQuote] = useState(null);
  const [candles, setCandles] = useState([]);
  const [indicators, setIndicators] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analystData, setAnalystData] = useState(null);
  const [news, setNews] = useState([]);
  const [loadingQuote, setLoadingQuote] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [signalEntry, setSignalEntry] = useState(null);

  const { data: watchlist = [] } = useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist.list, staleTime: 60_000 });
  const { data: alerts = [] } = useQuery({ queryKey: ["alerts"], queryFn: api.alerts.list, staleTime: 60_000 });
  const { data: popular = [] } = useQuery({ queryKey: ["popular"], queryFn: api.popular, staleTime: 120_000 });

  const loadSymbolData = useCallback(async (sym, tf) => {
    setLoadingQuote(true);
    setAnalysis(null);
    try {
      const data = await api.dashboard(sym, tf);
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
    } catch (e) {
      toast.error("Error al cargar datos");
    } finally {
      setLoadingQuote(false);
    }
  }, []);

  const refreshTimeframe = useCallback(
    async (tf) => {
      setTimeframe(tf);
      try {
        const c = await api.chart(symbol, tf);
        setCandles(c.candles || []);
      } catch (e) {
        toast.error("Error al cargar el gráfico");
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
      if (res.quote) setQuote(res.quote);
      // Hydrate analyst data if available
      if (res.analyst_consensus || res.price_target) {
        setAnalystData({
          symbol,
          consensus: res.analyst_consensus,
          price_target: res.price_target,
        });
      }
      toast.success(`Análisis ${model} completado`);
    } catch (e) {
      const msg = e?.response?.data?.detail || "Error al generar análisis IA";
      toast.error(msg);
    } finally {
      setLoadingAnalysis(false);
    }
  }, [symbol, model]);

  useEffect(() => {
    loadSymbolData(symbol, timeframe);
    // Load signal entry for this symbol (for chart overlay)
    const token = localStorage.getItem("inveria_token");
    fetch(`${API}/api/signals`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => r.json())
      .then((entries) => {
        const match = entries.find((e) => e.symbol === symbol.toUpperCase());
        setSignalEntry(match || null);
      })
      .catch(() => setSignalEntry(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  // WebSocket for live price updates (~8s refresh). Falls back to 30s polling if WS fails.
  useEffect(() => {
    if (!symbol) return;
    let ws;
    let fallbackId;
    let closed = false;

    const startFallback = () => {
      if (fallbackId) return;
      fallbackId = setInterval(async () => {
        try { setQuote(await api.quote(symbol)); } catch {}
      }, 30000);
    };

    try {
      const base = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
      const wsBase = base.replace(/^https:\/\//, "wss://").replace(/^http:\/\//, "ws://");
      ws = new WebSocket(`${wsBase}/api/ws/quote/${symbol}`);
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          setQuote((prev) => prev ? { ...prev, ...data } : prev);
        } catch {}
      };
      // Suppress console errors — fallback to polling silently
      ws.onerror = () => {};
      ws.onclose = () => { if (!closed) startFallback(); };
    } catch {
      startFallback();
    }

    return () => {
      closed = true;
      clearInterval(fallbackId);
      if (ws) ws.close();
    };
  }, [symbol]);

  const handlePickSymbol = (sym) => setSymbol(sym);

  const inWatchlist = !!watchlist.find((w) => w.symbol === symbol);

  const handleToggleWatchlist = async () => {
    const exists = watchlist.find((w) => w.symbol === symbol);
    try {
      if (exists) {
        await api.watchlist.remove(symbol);
        toast.success(`${symbol} eliminado de watchlist`);
      } else {
        await api.watchlist.add(symbol);
        toast.success(`${symbol} añadido a watchlist`);
      }
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Error en watchlist");
    }
  };

  const handleAddAlert = async (payload) => {
    try {
      await api.alerts.add(payload);
      toast.success("Alerta creada — recibirás email cuando se dispare");
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Error al crear alerta");
    }
  };

  const handleRemoveAlert = async (id) => {
    try { await api.alerts.remove(id); queryClient.invalidateQueries({ queryKey: ["alerts"] }); } catch { toast.error("Error"); }
  };

  const handleRemoveSymbol = async (sym) => {
    try { await api.watchlist.remove(sym); queryClient.invalidateQueries({ queryKey: ["watchlist"] }); toast.success(`${sym} eliminado`); } catch { toast.error("Error"); }
  };

  return (
    <main data-testid="main-dashboard" className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4 sm:gap-6">
      <div className="space-y-4 sm:space-y-6 min-w-0 order-2 lg:order-1">
        <HotSignals onPickSymbol={handlePickSymbol} />
        {loadingQuote && !quote ? (
          <div className="card-flat p-8 text-center text-[#5c6b66]">Cargando datos...</div>
        ) : quote ? (
          <QuoteHeader quote={quote} inWatchlist={inWatchlist} onToggleWatchlist={handleToggleWatchlist} />
        ) : null}

        <TradingLevels
          quote={quote}
          analysis={analysis}
          analystConsensus={analystData?.consensus}
          priceTarget={analystData?.price_target}
        />

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6">
          <PriceChart
            candles={candles}
            timeframe={timeframe}
            setTimeframe={refreshTimeframe}
            analysis={analysis}
            indicators={indicators}
            signalEntry={signalEntry}
          />
          <RecommendationPanel
            analysis={analysis}
            isLoading={loadingAnalysis}
            onAnalyze={runAnalysis}
            model={model}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <AnalystConsensusCard data={analystData} />
          <IndicatorsPanel indicators={indicators} analysis={analysis} />
        </div>

        <FundamentalsCard quote={quote} analysis={analysis} />

        {analysis && <RisksCatalystsCard analysis={analysis} />}

        <NewsFeed news={news} />
      </div>

      <div className="order-1 lg:order-2 lg:hidden">
        <SidebarLists
          watchlist={watchlist}
          onPickSymbol={handlePickSymbol}
          onRemoveSymbol={handleRemoveSymbol}
          onAddCurrent={handleToggleWatchlist}
          currentSymbol={symbol}
          alerts={alerts}
          onAddAlert={handleAddAlert}
          onRemoveAlert={handleRemoveAlert}
          popular={popular}
          compact
        />
      </div>
      <div className="hidden lg:block order-2">
      <SidebarLists
        watchlist={watchlist}
        onPickSymbol={handlePickSymbol}
        onRemoveSymbol={handleRemoveSymbol}
        onAddCurrent={handleToggleWatchlist}
        currentSymbol={symbol}
        alerts={alerts}
        onAddAlert={handleAddAlert}
        onRemoveAlert={handleRemoveAlert}
        popular={popular}
      />
      </div>
    </main>
  );
}
