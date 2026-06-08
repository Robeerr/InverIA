import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import QuoteHeader from "../components/QuoteHeader";
import PriceChart from "../components/PriceChart";
import RecommendationPanel from "../components/RecommendationPanel";
import IndicatorsPanel from "../components/IndicatorsPanel";
import SidebarLists from "../components/SidebarLists";
import TradingLevels from "../components/TradingLevels";
import AnalystConsensusCard from "../components/AnalystConsensus";
import { NewsFeed, FundamentalsCard, RisksCatalystsCard } from "../components/InfoCards";
import { api } from "../lib/api";

export default function Dashboard({ symbol, setSymbol, model }) {
  const [timeframe, setTimeframe] = useState("1Y");
  const [quote, setQuote] = useState(null);
  const [candles, setCandles] = useState([]);
  const [indicators, setIndicators] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analystData, setAnalystData] = useState(null);
  const [news, setNews] = useState([]);
  const [loadingQuote, setLoadingQuote] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [watchlist, setWatchlist] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [popular, setPopular] = useState([]);

  const loadSymbolData = useCallback(async (sym, tf) => {
    setLoadingQuote(true);
    setAnalysis(null);
    try {
      const [q, c, ind, n, an] = await Promise.all([
        api.quote(sym).catch(() => null),
        api.chart(sym, tf).catch(() => ({ candles: [] })),
        api.indicators(sym).catch(() => null),
        api.news(sym).catch(() => ({ items: [] })),
        api.analyst(sym).catch(() => null),
      ]);
      if (!q) {
        toast.error(`No se encontró el símbolo ${sym}`);
        setQuote(null);
        return;
      }
      setQuote(q);
      setCandles(c.candles || []);
      setIndicators(ind);
      setNews(n.items || []);
      setAnalystData(an);
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

  const loadWatchlist = useCallback(async () => {
    try { setWatchlist(await api.watchlist.list()); } catch {}
  }, []);
  const loadAlerts = useCallback(async () => {
    try { setAlerts(await api.alerts.list()); } catch {}
  }, []);
  const loadPopular = useCallback(async () => {
    try { setPopular(await api.popular()); } catch {}
  }, []);

  useEffect(() => {
    loadSymbolData(symbol, timeframe);
    loadWatchlist();
    loadAlerts();
    loadPopular();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  useEffect(() => {
    if (!symbol) return;
    const id = setInterval(async () => {
      try {
        const q = await api.quote(symbol);
        setQuote(q);
      } catch {}
    }, 30000);
    return () => clearInterval(id);
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
      await loadWatchlist();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Error en watchlist");
    }
  };

  const handleAddAlert = async (payload) => {
    try {
      await api.alerts.add(payload);
      toast.success("Alerta creada — recibirás email cuando se dispare");
      await loadAlerts();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Error al crear alerta");
    }
  };

  const handleRemoveAlert = async (id) => {
    try { await api.alerts.remove(id); await loadAlerts(); } catch { toast.error("Error"); }
  };

  const handleRemoveSymbol = async (sym) => {
    try { await api.watchlist.remove(sym); await loadWatchlist(); toast.success(`${sym} eliminado`); } catch { toast.error("Error"); }
  };

  return (
    <main data-testid="main-dashboard" className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4 sm:gap-6">
      <div className="space-y-4 sm:space-y-6 min-w-0 order-2 lg:order-1">
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
