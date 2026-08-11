import React, { useEffect, useState, useCallback, useRef, useMemo, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import QuoteHeader from "../components/QuoteHeader";
import ChartistPanel from "../components/ChartistPanel";
import RecommendationPanel from "../components/RecommendationPanel";
import SourcesPanel from "../components/SourcesPanel";
import { AlternativePanel } from "../components/MoreInsights";
import WatchlistStrip from "../components/WatchlistStrip";
import BottomSignalBar from "../components/BottomSignalBar";
import IndicatorsPanel, { FuerzaRelativa } from "../components/IndicatorsPanel";
import TesisPanel from "../components/TesisPanel";
import EstadoTecnico from "../components/EstadoTecnico";
import TuPosicion from "../components/TuPosicion";
import TradingLevels from "../components/TradingLevels";
import WhyMovingCard from "../components/WhyMovingCard";
import BacktestCard from "../components/BacktestCard";
import AnalystConsensusCard from "../components/AnalystConsensus";
import { NewsFeed, FundamentalsCard, RisksCatalystsCard, MarketSignalsCard, PricePredictionCard } from "../components/InfoCards";
import { api } from "../lib/api";
import { useSignals } from "../hooks/useSignals";

// Aviso de origen de datos, SOLO como respaldo. Lo normal es que esto lo cuente
// `tesis.limita_confianza` dentro del bloque de tesis, que resuelve la precedencia
// (degradado > sin SMA200 > régimen > sin zonas > mercado en riesgo) y da un aviso y
// no cinco. Esta barra solo aparece si no hay tesis —sin precio no se redacta— para
// que un fallo de datos no se quede sin decir.
function DataHealthBar({ health }) {
  if (!health || !health.degraded) return null;
  return (
    <div className="card-flat px-4 py-2 flex items-center gap-2 border border-[#c9a14a]/40 bg-[#c9a14a]/[0.06]">
      <span className="text-sm">⚠️</span>
      <span className="text-[11px] text-[#8a6508] leading-snug">
        <b>Datos de respaldo o con retraso</b>{health.note ? ` · ${health.note}` : ""}.
      </span>
    </div>
  );
}

// Timeframe con el que se pide el dashboard. El endpoint devuelve TODO (cotización,
// indicadores, noticias, analistas…), así que pedirlo de nuevo solo por cambiar la escala
// del gráfico sería tirar el resto a la basura: los demás timeframes van por /chart.
// Debe coincidir con la precarga de WatchlistStrip.jsx o se calientan claves distintas.
const TIMEFRAME_BASE = "1D";

// lightweight-charts es la dependencia más pesada del paquete y no hace falta para pintar
// la cabecera con el precio, que es lo primero que se mira al entrar. Cargándola en
// diferido viaja en su propio fragmento: la página aparece antes y el gráfico se completa
// un instante después, en su hueco, sin mover nada de sitio.
const LightweightChart = React.lazy(() => import("../components/LightweightChart"));

// Reserva del alto exacto del gráfico (460 px del lienzo + controles) mientras carga. Sin
// esto, al aparecer empujaría hacia abajo todo lo que hubiera debajo.
function HuecoGrafico() {
  return (
    <div className="card-flat p-3" style={{ height: 516 }} aria-busy="true">
      <div className="h-full w-full rounded bg-[#f0ece3] dark:bg-[#132a24] animate-pulse" />
    </div>
  );
}

export default function Dashboard({ symbol, setSymbol, model, setModel }) {
  const [timeframe, setTimeframe] = useState(TIMEFRAME_BASE);
  const [runAllTrigger, setRunAllTrigger] = useState(0);  // #3 dispara los 3 análisis a la vez
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);

  // Datos que NO vienen del servidor sino que se superponen encima: los ticks del
  // WebSocket y lo que produce el análisis de IA. Van juntos en un solo objeto para poder
  // vaciarlos de golpe al cambiar de acción — si sobrevivieran al cambio, se vería el
  // análisis de AAPL rotulado como MSFT.
  const [parche, setParche] = useState({});
  const parchear = useCallback((campos) => setParche((p) => ({ ...p, ...campos })), []);
  // Espejo del parche en una ref: los callbacks (WebSocket, análisis) necesitan leer el
  // valor actual sin que eso los obligue a recrearse en cada tick. Se sincroniza más abajo,
  // con el parche YA vaciado si se acaba de cambiar de acción.
  const parcheRef = useRef(parche);

  // Señales (caché compartido entre páginas) y futuros (refresco 60s) vía react-query.
  const { data: signals } = useSignals();
  // Futuros, Miedo/Codicia y mapa sectorial se han ido a «Hoy»: son idénticos para las
  // quinientas acciones y abrían la página de UNA. Con ellos se van tres peticiones
  // automáticas de esta pantalla, incluida la única con refresco de 60 s.
  //
  // El régimen de mercado SÍ se queda —viaja dentro del propio dashboard, sin petición
  // propia— porque es el único que cambia cómo se lee esta acción: el motor de niveles
  // ajusta sus pesos con él. Se pinta como una cláusula dentro de EstadoTecnico.

  // ── Datos del servidor, vía react-query ────────────────────────────────────
  // El motivo de estar aquí: antes cada cambio de acción disparaba una carga completa,
  // aunque volvieras a una que acababas de mirar. React Query guarda la respuesta POR
  // SÍMBOLO, así que volver a una vista hace 5 minutos es instantáneo.
  //
  // A propósito SIN placeholderData/keepPreviousData: eso mostraría los datos de la acción
  // ANTERIOR bajo el ticker NUEVO mientras carga. En una app de bolsa eso no es un parpadeo
  // feo, es un precio incorrecto sobre el que alguien puede actuar. Mejor "cargando".
  // Cuando el símbolo ya está en caché no hay hueco que rellenar, que es el caso que importa.
  //
  // Cancelación, deduplicación de peticiones y descarte de respuestas que llegan tarde los
  // hace react-query: por eso desaparecen el AbortController y el contador de petición que
  // había aquí a mano.
  const esCancelada = (e) => e?.code === "ERR_CANCELED" || e?.name === "CanceledError";

  // La clave se normaliza a mayúsculas: el backend hace symbol.upper(), así que "aapl" y
  // "AAPL" son la misma respuesta, pero como claves distintas serían dos entradas de caché
  // y dos peticiones. El buscador ya normaliza, esto cubre el resto de caminos.
  const sym = (symbol || "").toUpperCase();

  const consultaDashboard = useQuery({
    queryKey: ["dashboard", sym, TIMEFRAME_BASE],
    queryFn: ({ signal }) => api.dashboard(sym, TIMEFRAME_BASE, signal),
    enabled: !!sym,
    staleTime: 60_000,        // dentro del minuto se sirve de caché sin ir al servidor
    gcTime: 30 * 60_000,      // y se conserva media hora para volver a la acción
    refetchOnWindowFocus: false,
    // Un reintento SOLO ante un fallo de red puntual. Insistir tras un 429 (cuota agotada)
    // la empeora, y saltar rápido entre acciones multiplicaba el efecto hasta tumbarlo todo.
    retry: (intentos, e) => {
      const st = e?.response?.status;
      if (esCancelada(e) || st === 404 || st === 429 || (st >= 500 && st < 600)) return false;
      return intentos < 1;
    },
    retryDelay: 600,
  });

  // El gráfico en su timeframe base sale del dashboard, que ya lo trae. Los demás se piden
  // aparte y se cachean por (símbolo, escala): antes cambiar de escala y volver recargaba.
  const consultaGrafico = useQuery({
    queryKey: ["chart", sym, timeframe],
    queryFn: ({ signal }) => api.chart(sym, timeframe, signal),
    enabled: !!sym && timeframe !== TIMEFRAME_BASE,
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });

  const datos = consultaDashboard.data;
  const grafico = timeframe === TIMEFRAME_BASE ? datos : consultaGrafico.data;

  // El semáforo de mercado es del MERCADO, no de la acción: se conserva el último conocido
  // para que no desaparezca la barra mientras carga la siguiente acción.
  const regimenRef = useRef(null);
  if (datos?.market_regime) regimenRef.current = datos.market_regime;
  const marketRegime = datos?.market_regime || regimenRef.current;

  // Vacía los parches al cambiar de acción. Va durante el render (no en un efecto) para que
  // no llegue a pintarse ni un fotograma con el análisis de la acción anterior.
  //
  // OJO al orden: hay que decidir `p` con el resultado de la COMPARACIÓN, no volviendo a
  // mirar la ref después de actualizarla. setParche({}) programa un re-render, pero ESTE
  // render sigue teniendo el `parche` viejo en la mano; si se leyera la ref ya actualizada
  // se daría por bueno y se pintaría un fotograma con el análisis de la acción anterior
  // bajo el ticker nuevo — el mismo fallo que ya costó arreglar en la carga a mano.
  const symbolParcheado = useRef(sym);
  const cambioDeAccion = symbolParcheado.current !== sym;
  if (cambioDeAccion) {
    symbolParcheado.current = sym;
    if (Object.keys(parche).length) setParche({});
  }
  const p = cambioDeAccion ? {} : parche;
  parcheRef.current = p;

  // Composición final: servidor debajo, parches encima.
  //
  // Los parches ENRIQUECEN una cotización del servidor; nunca la crean. Sin esta regla, un
  // tick del WebSocket que llegue antes que la respuesta del dashboard —cosa que pasa a
  // menudo al elegir una acción, porque el servidor manda su instantánea nada más
  // conectar— produciría un quote con solo {price, change, day_high…}: sin symbol, sin
  // name. Y QuoteHeader hace quote.symbol.slice(0, 3), que revienta la vista entera.
  //
  // La carga manual que había antes tenía esta guarda dentro del WebSocket
  // (`prev ? {...prev, ...next} : prev`); al reescribirla se perdió. Ponerla aquí, en el
  // único sitio donde se compone el quote, la hace válida para TODOS los parches
  // (WebSocket, respaldo REST y análisis de IA) en vez de repetirla en cada uno.
  const quote = useMemo(() => {
    if (!datos?.quote) return null;
    return p.quote ? { ...datos.quote, ...p.quote } : datos.quote;
  }, [datos?.quote, p.quote]);

  const candles = grafico?.candles || [];
  const chartLines = grafico?.lines || null;
  const indicators = p.indicators || datos?.indicators || null;
  const news = datos?.news || [];
  const analystData = p.analystData || datos?.analyst || null;
  const buyLevels = p.buyLevels || datos?.buy_levels || null;
  const volumeProfile = p.volumeProfile || datos?.volume_profile || null;
  const dataHealth = datos?.data_health || null;
  // Se lee siempre del servidor, incluso a null: si la acción anterior tenía Fuerza
  // Relativa y esta no (histórico corto), conservarla mostraría el dato de la anterior.
  const relativeStrength = datos?.relative_strength || null;
  // Igual que la fuerza relativa: SIEMPRE del servidor. La tesis es determinista y la
  // calcula el backend dentro del dashboard, así que no hay parche que la pueda pisar
  // ni sobrevivir a un cambio de ticker.
  const tesis = datos?.tesis || null;
  const generadoEn = datos?.generado_en || null;
  const analysis = p.analysis || null;
  const marketSignals = p.marketSignals || null;
  // `isPending` de una consulta desactivada (enabled:false) también es true en react-query
  // v5: sin el `!!symbol`, entrar sin acción seleccionada dejaría un "Cargando…" eterno.
  const loadingQuote = !!sym && consultaDashboard.isPending;

  // Errores → avisos. En un efecto y no en el render porque un toast es un efecto secundario.
  const errorDashboard = consultaDashboard.error;
  useEffect(() => {
    if (!errorDashboard || esCancelada(errorDashboard)) return;
    const st = errorDashboard?.response?.status;
    if (st === 404) {
      toast.error(`"${symbol}" no existe. Revisa el símbolo (p.ej. AAPL, no APPL).`);
    } else if (st === 429) {
      toast.error("Demasiadas consultas seguidas. Espera unos segundos antes de cambiar de acción.");
    } else {
      toast.error("Error al cargar datos. Inténtalo de nuevo.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [errorDashboard]);

  // 200 pero sin cotización NO significa que el símbolo no exista (eso da 404, arriba):
  // significa que las fuentes no contestaron a tiempo. Decir "no se encontró AAPL" mandaba
  // a corregir un símbolo correcto.
  useEffect(() => {
    if (datos && !datos.quote) {
      toast.error(`No se pudieron cargar los datos de ${symbol}. Las fuentes de datos no respondieron a tiempo — vuelve a intentarlo en unos segundos.`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datos]);

  useEffect(() => {
    if (consultaGrafico.error) toast.error("Error al cargar el gráfico");
  }, [consultaGrafico.error]);

  // El cambio de escala ya no dispara una petición a mano: basta con mover el estado, y
  // react-query se encarga (consultaGrafico depende de `timeframe`). Además ahora queda
  // cacheado, así que ir y volver entre 1D y 1Y es instantáneo la segunda vez.
  const refreshTimeframe = useCallback((tf) => setTimeframe(tf), []);

  const runAnalysis = useCallback(async () => {
    if (!symbol) return;
    setLoadingAnalysis(true);
    try {
      const res = await api.analyze(symbol, model);
      const nuevo = { analysis: res.analysis };
      if (res.indicators) nuevo.indicators = res.indicators;
      // Merge quote without overwriting good fields with nulls — yfinance .info
      // sometimes returns an incomplete quote (missing P/E, EPS, beta...).
      if (res.quote) {
        const soloLlenos = {};
        for (const [k, v] of Object.entries(res.quote)) {
          if (v != null) soloLlenos[k] = v;
        }
        nuevo.quote = { ...(parcheRef.current.quote || {}), ...soloLlenos };
      }
      if (res.analyst_consensus || res.price_target) {
        nuevo.analystData = {
          symbol,
          consensus: res.analyst_consensus,
          price_target: res.price_target,
        };
      }
      if (res.insider || res.earnings_history) {
        nuevo.marketSignals = { insider: res.insider, earningsHistory: res.earnings_history };
      }
      if (res.volume_profile) nuevo.volumeProfile = res.volume_profile;
      if (res.buy_levels) nuevo.buyLevels = res.buy_levels;
      // Una sola escritura: antes eran hasta siete setState seguidos, o sea siete pasadas
      // de render con el panel a medio rellenar.
      parchear(nuevo);
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
  }, [symbol, model, parchear]);

  // #3 Análisis completo: dispara los 3 (Recomendación + Chartista + ¿Por qué se mueve?) de un toque.
  const runAll = useCallback(() => {
    if (!symbol) return;
    runAnalysis();
    setRunAllTrigger((t) => t + 1);
  }, [symbol, runAnalysis]);

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
      parchear({ quote: { ...(parcheRef.current.quote || {}), ...next } });
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
          if (!closed) parchear({ quote: q });
        } catch {}
      }, 30000);
    };

    const connect = () => {
      if (closed) return;
      try {
        const base = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
        const wsBase = base.replace(/^https:\/\//, "wss://").replace(/^http:\/\//, "ws://");
        // El token va en la URL porque la API de WebSocket del navegador no deja poner
        // cabeceras. Sin él el backend cierra la conexión: cada una consume cuota de datos.
        const tok = localStorage.getItem("inveria_token") || "";
        ws = new WebSocket(`${wsBase}/api/ws/quote/${symbol}?token=${encodeURIComponent(tok)}`);
        ws.onopen = () => { retries = 0; };
        ws.onmessage = (e) => {
          try { scheduleUpdate(JSON.parse(e.data)); } catch {}
        };
        ws.onerror = () => {};
        ws.onclose = (ev) => {
          if (closed) return;
          // 1008 = el backend ha rechazado la credencial. Reintentar no va a arreglarlo:
          // serían 5 intentos y ~1 minuto para acabar igual. Se pasa directamente al
          // respaldo REST, que al dar 401 hace que la app te mande a iniciar sesión.
          if (ev?.code === 1008) { startFallback(); return; }
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
  }, [symbol, parchear]);


  return (
    <div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6 lg:flex lg:gap-5 lg:items-start">
      {/* Escritorio: watchlist como barra lateral izquierda (sticky). */}
      <aside className="hidden lg:block w-52 shrink-0 sticky top-4">
        <WatchlistStrip symbol={symbol} setSymbol={setSymbol} vertical />
      </aside>
      <main data-testid="main-dashboard" className="flex-1 min-w-0 space-y-4 sm:space-y-6">
      {/* Móvil: watchlist como tira horizontal arriba. */}
      <WatchlistStrip symbol={symbol} setSymbol={setSymbol} className="lg:hidden" />

      {/* ══ 01 · Cabecera viva ══
          Lo único de la página que cambia en tiempo real. Por eso va arriba y va solo:
          todo lo que hay debajo es una foto del momento en que se ensambló el dashboard. */}
      {loadingQuote && !quote ? (
        <div className="card-flat p-8 text-center text-[#5c6b66]">Cargando datos...</div>
      ) : quote ? (
        <QuoteHeader quote={quote} />
      ) : null}

      {/* ══ 02 · Tesis ══
          Interpretación determinista, disponible al abrir y sin pulsar nada. Lleva
          dentro el aviso de fiabilidad y el botón de IA como acción secundaria. */}
      <TesisPanel
        tesis={tesis}
        quote={quote}
        generadoEn={generadoEn}
        onAnalizar={quote ? runAll : null}
        loadingAnalysis={loadingAnalysis}
        tieneAnalisis={!!analysis}
      />

      {/* Respaldo: si no hubo tesis que redactar, el aviso de datos no puede perderse. */}
      {quote && !tesis && <DataHealthBar health={dataHealth} />}

      {/* ══ 03 · Estado técnico ══
          Régimen, ADX, ATR%, OBV, VWAP anclado y media de 10 semanas. Todo ya viajaba
          en la respuesta y no tenía una sola lectura en el frontend. */}
      <EstadoTecnico indicators={indicators} quote={quote} marketRegime={marketRegime} />

      {/* ══ 04 · Tu posición ══
          Antes de los niveles: un nivel al 5% no significa lo mismo con dinero dentro.
          Sale de /signals, que ya estaba cargado y no se cruzaba con el ticker abierto. */}
      <TuPosicion signals={signals} symbol={symbol} quote={quote} />

      {/* ══ 05 · Niveles ══ buy_levels es la autoridad única de zonas de compra. */}
      <TradingLevels
        quote={quote}
        analysis={analysis}
        analystConsensus={analystData?.consensus}
        priceTarget={analystData?.price_target}
        volumeProfile={volumeProfile}
        buyLevels={buyLevels}
      />

      {/* ══ 06 · Gráfico ══ Pegado a Niveles porque dibuja lo mismo. */}
      <Suspense fallback={<HuecoGrafico />}>
        <LightweightChart
          candles={candles}
          buyLevels={buyLevels}
          lines={chartLines}
          timeframe={timeframe}
          setTimeframe={refreshTimeframe}
        />
      </Suspense>

      {/* ══ 07 · Tus fuentes ══ Tu inteligencia propia, por encima de la de terceros. */}
      <SourcesPanel symbol={symbol} />

      {/* ══ 08 a 11 · Capa de IA ══
          Solo existe si la pides. Lo que aporta y la tesis no puede: juicio, causa del
          movimiento, síntesis multiescala y prospectiva. */}
      <RecommendationPanel
        analysis={analysis}
        isLoading={loadingAnalysis}
        onAnalyze={runAnalysis}
        model={model}
        setModel={setModel}
      />

      {analysis && <PricePredictionCard analysis={analysis} quote={quote} />}

      {quote && <WhyMovingCard symbol={symbol} model={model} runSignal={runAllTrigger} />}

      <ChartistPanel symbol={symbol} runSignal={runAllTrigger} />

      {analysis && <RisksCatalystsCard analysis={analysis} />}

      {marketSignals && (
        <MarketSignalsCard
          insider={marketSignals.insider}
          earningsHistory={marketSignals.earningsHistory}
        />
      )}

      {/* ══ 12 · Analistas y fundamentales ══ Opinión de terceros y marcha del negocio. */}
      <FuerzaRelativa rs={relativeStrength} />
      <AnalystConsensusCard data={analystData} />
      <FundamentalsCard quote={quote} analysis={analysis} />

      {/* ══ 13 · Noticias ══ */}
      <NewsFeed news={news} />

      {/* ══ 14 · Detalle ══
          Lo comprobable, después de lo interpretado. No se borra nada: baja de sitio. */}
      <IndicatorsPanel indicators={indicators} analysis={analysis} />
      <AlternativePanel symbol={symbol} onPick={setSymbol} />
      {quote && <BacktestCard symbol={symbol} />}

      {/* Espacio para que la barra de señal fija no tape el contenido */}
      {quote && <div className="h-16" />}
      <BottomSignalBar symbol={symbol} quote={quote} indicators={indicators} analysis={analysis} />
      </main>
    </div>
  );
}
