import React, { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import QuoteHeader from "../components/QuoteHeader";
import PriceChart from "../components/PriceChart";
import RecommendationPanel from "../components/RecommendationPanel";
import IndicatorsPanel from "../components/IndicatorsPanel";
import TradingLevels from "../components/TradingLevels";
import AnalystConsensusCard from "../components/AnalystConsensus";
import { NewsFeed, FundamentalsCard, RisksCatalystsCard, MarketSignalsCard, InvestmentThesisCard, PricePredictionCard } from "../components/InfoCards";
import { api } from "../lib/api";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

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

export default function Dashboard({ symbol, setSymbol, model, setModel }) {
  const [timeframe, setTimeframe] = useState("1Y");
  const [quote, setQuote] = useState(null);
  const [candles, setCandles] = useState([]);
  const [indicators, setIndicators] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analystData, setAnalystData] = useState(null);
  const [marketSignals, setMarketSignals] = useState(null);
  const [volumeProfile, setVolumeProfile] = useState(null);
  const [futures, setFutures] = useState(null);
  const [news, setNews] = useState([]);
  const [loadingQuote, setLoadingQuote] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [signalEntry, setSignalEntry] = useState(null);
  const signalsCache = useRef(null); // session-level cache to avoid re-fetching all signals on every symbol change

  const loadSymbolData = useCallback(async (sym, tf) => {
    setLoadingQuote(true);
    setAnalysis(null);
    setMarketSignals(null);
    setVolumeProfile(null);
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
    const token = localStorage.getItem("inveria_token");
    const findEntry = (entries) => {
      const match = entries.find((e) => e.symbol === symbol.toUpperCase());
      setSignalEntry(match || null);
    };
    if (signalsCache.current) {
      findEntry(signalsCache.current);
    } else {
      fetch(`${API}/api/signals`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
        .then((r) => r.json())
        .then((entries) => { signalsCache.current = entries; findEntry(entries); })
        .catch(() => setSignalEntry(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  // Index futures bar — refresh every 60s, independent of the selected symbol
  useEffect(() => {
    let id;
    const load = () => api.marketFutures().then(setFutures).catch(() => {});
    load();
    id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);

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


  return (
    <main data-testid="main-dashboard" className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6 space-y-4 sm:space-y-6">
      <MarketFuturesBar futures={futures} />

      {loadingQuote && !quote ? (
        <div className="card-flat p-8 text-center text-[#5c6b66]">Cargando datos...</div>
      ) : quote ? (
        <QuoteHeader quote={quote} />
      ) : null}

      <TradingLevels
        quote={quote}
        analysis={analysis}
        analystConsensus={analystData?.consensus}
        priceTarget={analystData?.price_target}
        volumeProfile={volumeProfile}
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
          setModel={setModel}
        />
      </div>

      {analysis && <PricePredictionCard analysis={analysis} quote={quote} />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AnalystConsensusCard data={analystData} />
        <IndicatorsPanel indicators={indicators} analysis={analysis} />
      </div>

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
    </main>
  );
}
