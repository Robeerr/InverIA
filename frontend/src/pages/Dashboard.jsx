import React, { useEffect, useState, useCallback, useRef, useMemo, Suspense } from "react";
import { TriangleAlert as AlertTriangle, RotateCw } from "lucide-react";
import { Boton } from "../components/base/Boton";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import QuoteHeader from "../components/QuoteHeader";
import ChartistPanel from "../components/ChartistPanel";
import RecommendationPanel, { modelLabel } from "../components/RecommendationPanel";
import SourcesPanel from "../components/SourcesPanel";
import { AlternativePanel } from "../components/MoreInsights";
import WatchlistStrip from "../components/WatchlistStrip";
import BottomSignalBar from "../components/BottomSignalBar";
import IndicatorsPanel, { FuerzaRelativa } from "../components/IndicatorsPanel";
import TesisPanel from "../components/TesisPanel";
import EstadoTecnico from "../components/EstadoTecnico";
import TuPosicion from "../components/TuPosicion";
import SimuladorMargen from "../components/SimuladorMargen";
import EstadoTendencia from "../components/EstadoTendencia";
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
    <div className="rounded-iv px-4 py-3 flex items-start gap-2.5 bg-aviso/[0.08] border border-aviso/20" role="status">
      <AlertTriangle className="w-4 h-4 text-aviso shrink-0 mt-px" strokeWidth={1.75} aria-hidden="true" />
      <span className="text-[13px] text-aviso leading-snug">
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
    <div className="iv-panel p-3" style={{ height: 516 }} aria-busy="true" aria-label="Cargando el gráfico">
      <div className="h-full w-full rounded-iv iv-esqueleto" />
    </div>
  );
}

/** Esqueleto de la cabecera mientras llega la primera respuesta. Ocupa lo mismo que
 *  QuoteHeader (ticker a la izquierda, precio a la derecha, fila de datos del día), así
 *  que al llegar el precio no salta nada de sitio. */
function CabeceraCargando() {
  const barra = "rounded-iv-sm iv-esqueleto";
  return (
    <div className="iv-panel overflow-hidden" aria-busy="true" role="status">
      <span className="sr-only">Cargando datos…</span>
      <div className="p-5 sm:p-7">
        <div className="flex items-center gap-3.5">
          <div className="w-12 h-12 rounded-[14px] iv-esqueleto" />
          <div className="space-y-2">
            <div className={`${barra} h-6 w-24`} />
            <div className={`${barra} h-3.5 w-44`} />
          </div>
        </div>
        <div className="mt-6 sm:mt-8 flex items-end gap-4">
          <div className={`${barra} h-14 w-48`} />
          <div className={`${barra} h-7 w-32`} />
        </div>
      </div>
      <div className="border-t border-suave px-5 sm:px-7 py-4 sm:py-5 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-[minmax(0,1.6fr)_repeat(4,minmax(0,1fr))] gap-x-6 gap-y-4">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className={`space-y-2 ${i === 0 ? "col-span-2 sm:col-span-4 lg:col-span-1" : ""}`}>
            <div className={`${barra} h-3 w-16`} />
            <div className={`${barra} h-4 ${i === 0 ? "w-full" : "w-20"}`} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Cabecera de seccion de la ficha.
 *
 * La pagina ya venia ordenada en catorce bloques —lo dicen los comentarios «01 ·
 * Cabecera viva», «05 · Niveles»— pero ese orden NO se veia: por fuera era una pila
 * de paneles iguales, y el lector no tenia forma de saber que la parte de arriba
 * decide y la de abajo solo documenta. Aqui ese orden se hace visible: titular de
 * sección en Geist 18/600 con su nota en tinta-3 debajo, y aire entre secciones.
 *
 * `acento` se reserva al plan de entrada, que es la seccion por la que se entra a
 * esta pagina. Si lo llevaran todas no distinguiria ninguna.
 */
function Seccion({ titulo, nota, acento = false, icono: Icono, children, className = "" }) {
  return (
    <section className={className}>
      <header className="mb-3.5 sm:mb-4 flex items-end justify-between gap-4">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-[17px] sm:text-[18px] font-semibold tracking-[-0.02em] text-tinta leading-tight">
            {acento && (
              <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-marca shadow-[0_0_0_4px_rgb(var(--iv-intencion)/0.14)] mr-1" />
            )}
            {Icono && <Icono className="w-[18px] h-[18px] text-tinta-3" strokeWidth={1.75} aria-hidden="true" />}
            {titulo}
          </h2>
          {nota && <p className="text-[13px] text-tinta-3 mt-1">{nota}</p>}
        </div>
      </header>
      <div className="space-y-3 sm:space-y-4">{children}</div>
    </section>
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
  // Estado de tendencia: SIEMPRE del servidor, igual que la tesis. Es una decisión
  // determinista del backend y no puede quedar pisada por el parche de la IA ni
  // sobrevivir a un cambio de ticker.
  const estado = p.estado || datos?.estado || null;
  const estadoMotivo = p.estadoMotivo || datos?.estado_motivo || null;
  const zonasOcultas = p.zonasOcultas ?? datos?.zonas_ocultas_por_tendencia ?? false;
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
      // El estado viaja con el análisis: sin esto, pulsar «Ampliar con IA» sobre una
      // acción bajista devolvería el panel de niveles que el dashboard ya había ocultado.
      if (res.estado) { nuevo.estado = res.estado; nuevo.estadoMotivo = res.estado_motivo; }
      if (res.zonas_ocultas_por_tendencia !== undefined) nuevo.zonasOcultas = res.zonas_ocultas_por_tendencia;
      // Una sola escritura: antes eran hasta siete setState seguidos, o sea siete pasadas
      // de render con el panel a medio rellenar.
      parchear(nuevo);
      // Los `_label` y no `res.model`: ese es la clave INTERNA de routing, y decía
      // "gemini-2.5-flash" cuando el análisis lo había hecho gemini-3.6-flash. El nombre
      // legible lo da el backend, que es el único que sabe a qué modelo enruta cada clave.
      if (res.fellback) {
        toast.warning(`${res.requested_model_label || modelLabel(res.requested_model)} no disponible (límite o error) — análisis hecho con ${res.model_label || modelLabel(res.model)}`);
      } else {
        toast.success(`Análisis completado (${res.model_label || modelLabel(res.model || model)})`);
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
    <div className="max-w-[1440px] mx-auto px-4 sm:px-8 py-4 sm:py-6 iv-entra">
      {/* Tu watchlist como cinta encima de la ficha: antes era una columna de sesenta
          tarjetas que duplicaba el rail y estrechaba la página. */}
      <WatchlistStrip symbol={symbol} setSymbol={setSymbol} className="mb-4 sm:mb-5" />

      <main data-testid="main-dashboard" className="space-y-5 sm:space-y-6">
      {/* ══ 01 · Cabecera viva ══
          Lo único de la página que cambia en tiempo real. Por eso va arriba y va sola:
          todo lo que hay debajo es una foto del momento en que se ensambló el dashboard. */}
      {loadingQuote && !quote ? (
        <CabeceraCargando />
      ) : quote ? (
        <QuoteHeader quote={quote} />
      ) : sym && (consultaDashboard.isError || datos) && !esCancelada(errorDashboard) ? (
        // Sin cotización tras cargar: antes la página se quedaba en blanco debajo del
        // aviso flotante, que desaparece a los pocos segundos. El texto se queda.
        <div className="iv-panel p-6 sm:p-8 flex items-start gap-4" role="alert">
          <span className="w-10 h-10 rounded-[11px] bg-baja/10 text-baja inline-flex items-center justify-center shrink-0">
            <AlertTriangle className="w-[18px] h-[18px]" strokeWidth={1.75} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-[15px] font-semibold text-tinta">No se han podido cargar los datos de {sym}.</p>
            <p className="text-[13px] text-tinta-3 mt-1 max-w-[60ch]">
              Las fuentes de datos no han respondido a tiempo o el símbolo no existe. Vuelve a
              intentarlo en unos segundos.
            </p>
            <Boton
              variante="secundario"
              className="mt-4"
              onClick={() => consultaDashboard.refetch()}
              ocupado={consultaDashboard.isFetching}
            >
              <RotateCw className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" />
              {consultaDashboard.isFetching ? "Reintentando…" : "Reintentar"}
            </Boton>
          </div>
        </div>
      ) : null}

      {/* Dos columnas en escritorio: la lectura a la izquierda y, a la derecha, lo que es
          tuyo (la lectura rápida, tu posición y tu margen). En móvil la columna derecha
          cae entre el veredicto y el plan de entrada, donde se decide. */}
      <div className="grid gap-x-6 gap-y-10 lg:grid-cols-[minmax(0,1fr)_minmax(300px,352px)] xl:grid-cols-[minmax(0,1fr)_368px] items-start">

      <div className="min-w-0 space-y-10 lg:col-start-1">
      {/* ══ 02 · Gráfico ══ Justo debajo del precio: es lo primero que se mira después. */}
      <Suspense fallback={<HuecoGrafico />}>
        <LightweightChart
          candles={candles}
          buyLevels={buyLevels}
          lines={chartLines}
          timeframe={timeframe}
          setTimeframe={refreshTimeframe}
        />
      </Suspense>

      <Seccion titulo="Veredicto" nota="Lectura determinista, sin pulsar nada">
      {/* ══ 03 · Tesis ══
          Interpretación determinista, disponible al abrir y sin pulsar nada. Lleva
          dentro el aviso de fiabilidad y el botón de IA como acción secundaria. */}
      <TesisPanel
        tesis={tesis}
        symbol={sym}
        quote={quote}
        generadoEn={generadoEn}
        onAnalizar={quote ? runAll : null}
        loadingAnalysis={loadingAnalysis}
        tieneAnalisis={!!analysis}
      />

      {/* Respaldo: si no hubo tesis que redactar, el aviso de datos no puede perderse. */}
      {quote && !tesis && <DataHealthBar health={dataHealth} />}

      {/* ══ 04 · Estado técnico ══
          Régimen, ADX, ATR%, OBV, VWAP anclado y media de 10 semanas. */}
      <EstadoTecnico indicators={indicators} quote={quote} marketRegime={marketRegime} />
      </Seccion>
      </div>

      <aside className="min-w-0 space-y-4 lg:col-start-2 lg:row-start-1 lg:row-span-2" aria-label="Tu dinero en esta acción">
      {/* Lectura rápida: lo esencial de un vistazo. En móvil vive en la barra fija de
          abajo; en escritorio, aquí, a la altura del gráfico. */}
      <BottomSignalBar symbol={symbol} quote={quote} indicators={indicators} analysis={analysis} como="panel" className="hidden lg:block" />

      {/* ══ 05 · Tu posición ══
          Antes de los niveles: un nivel al 5% no significa lo mismo con dinero dentro.
          Sale de /signals, que ya estaba cargado y no se cruzaba con el ticker abierto. */}
      <TuPosicion signals={signals} symbol={symbol} quote={quote} />

      {/* ══ 05b · Impacto en el margen ══
          Comprar y vender mueven el margen libre en sentidos opuestos, y con una cuenta
          apalancada comprar lo mueve en la dirección peligrosa. Va pegado a tu posición
          porque es la misma conversación: tu dinero en esta acción. */}
      <SimuladorMargen symbol={sym} />
      </aside>

      <div className="min-w-0 space-y-10 sm:space-y-12 lg:col-start-1">
      <Seccion titulo="Plan de entrada" nota="Dónde comprar, y qué lo invalida" acento>
      {/* ══ 06 · Niveles ══ buy_levels es la autoridad única de zonas de compra.
          Sin tendencia alcista no se presentan: en su lugar va el motivo. Es un `o`, no
          un `y` — enseñar las dos cosas sería contradecirse en la misma pantalla. */}
      {zonasOcultas ? (
        <EstadoTendencia
          estado={estado}
          motivo={estadoMotivo}
          soportes={analysis?.key_levels?.support}
          symbol={symbol}
        />
      ) : (
        <TradingLevels
          quote={quote}
          analysis={analysis}
          analystConsensus={analystData?.consensus}
          priceTarget={analystData?.price_target}
          volumeProfile={volumeProfile}
          buyLevels={buyLevels}
        />
      )}
      </Seccion>

      {/* ══ 07 · Tus fuentes ══ Tu inteligencia propia, por encima de la de terceros.
          El panel no se pinta si no hay menciones; la sección se pliega con él. */}
      <Seccion titulo="Tus fuentes" nota="Tu inteligencia propia, antes que la de terceros" className="[&:not(:has(section))]:hidden">
      <SourcesPanel symbol={symbol} />
      </Seccion>

      <Seccion titulo="Análisis con IA" nota="Solo existe si lo pides">
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
      </Seccion>

      <Seccion titulo="Analistas y fundamentales" nota="Opinión de terceros y marcha del negocio">
      <div className="grid gap-3 sm:gap-4 xl:grid-cols-2 items-start">
        <AnalystConsensusCard data={analystData} />
        <div className="space-y-3 sm:space-y-4 min-w-0">
          <FuerzaRelativa rs={relativeStrength} />
        </div>
      </div>
      <FundamentalsCard quote={quote} analysis={analysis} />
      </Seccion>

      <Seccion titulo="Noticias">
      <NewsFeed news={news} />
      </Seccion>

      <Seccion titulo="Detalle" nota="Lo comprobable, después de lo interpretado">
      {/* ══ 14 · Detalle ══
          Lo comprobable, después de lo interpretado. No se borra nada: baja de sitio. */}
      <IndicatorsPanel indicators={indicators} analysis={analysis} />
      <AlternativePanel symbol={symbol} onPick={setSymbol} />
      {quote && <BacktestCard symbol={symbol} />}
      </Seccion>
      </div>
      </div>

      {/* Espacio para que la barra de señal fija (solo móvil) no tape el contenido */}
      {quote && <div className="h-20 lg:hidden" />}
      <BottomSignalBar symbol={symbol} quote={quote} indicators={indicators} analysis={analysis} />
      </main>
    </div>
  );
}
