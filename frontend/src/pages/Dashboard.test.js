/**
 * La arquitectura de la página de acción, comprobada sobre el código.
 *
 * No hay `@testing-library/react` en el proyecto, así que se sigue el patrón que ya
 * usan `api.test.js` y `tokens.test.js`: leer la fuente y comprobar su FORMA. Para lo
 * que aquí se protege es además lo adecuado — son invariantes de arquitectura
 * («la tesis no cuelga de la IA», «no hay dos precios»), y esas se ven mejor en la
 * estructura del componente que en un render concreto con datos de mentira.
 */
const fs = require("fs");
const path = require("path");

const DASHBOARD = fs.readFileSync(path.join(__dirname, "Dashboard.jsx"), "utf8");
const ESTADO = fs.readFileSync(path.join(__dirname, "..", "components", "EstadoTecnico.jsx"), "utf8");
const TESIS = fs.readFileSync(path.join(__dirname, "..", "components", "TesisPanel.jsx"), "utf8");

/** El cuerpo del `return (...)` final, que es el árbol que se pinta. */
const RENDER = DASHBOARD.slice(DASHBOARD.lastIndexOf("  return (\n    <div className=\"max-w-[1480px]"));

/**
 * El código sin comentarios.
 *
 * Hace falta para las comprobaciones de «este campo no se lee»: los comentarios que
 * explican POR QUÉ no se lee mencionan el campo, y buscar sobre el fichero entero los
 * daría por infracciones. Lo que se protege es lo que se ejecuta.
 */
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const DASHBOARD_COD = sinComentarios(DASHBOARD);
const ESTADO_COD = sinComentarios(ESTADO);

describe("la tesis se pinta en frío", () => {
  test("el bloque existe en el árbol de render", () => {
    expect(RENDER).toContain("<TesisPanel");
  });

  test("NO cuelga de `analysis`: se pinta sin pulsar IA", () => {
    // El fallo que se protege: si se escribiera `{analysis && <TesisPanel …>}`, la
    // interpretación volvería a estar detrás del botón, que es justo lo que la Fase 3.1
    // vino a arreglar.
    const linea = RENDER.slice(RENDER.indexOf("<TesisPanel") - 120, RENDER.indexOf("<TesisPanel"));
    expect(linea).not.toMatch(/analysis\s*&&\s*$/);
    expect(RENDER).not.toContain("{analysis && <TesisPanel");
  });

  test("la tesis sale del servidor y nunca del parche de IA", () => {
    // `p.` es el parche (WebSocket + IA). Si la tesis saliera de ahí, sobreviviría al
    // cambio de ticker y se leería la tesis de AAPL bajo el rótulo de MSFT.
    expect(DASHBOARD).toContain("const tesis = datos?.tesis || null;");
    expect(DASHBOARD).not.toMatch(/const tesis\s*=\s*p\./);
    expect(DASHBOARD).toContain("const generadoEn = datos?.generado_en || null;");
  });

  test("lleva el sello de antigüedad, que es lo que explica los dos relojes", () => {
    expect(RENDER).toContain("generadoEn={generadoEn}");
    expect(TESIS).toContain("fmtHace");
  });

  test("el aviso de fiabilidad va dentro de la tesis, no en una barra aparte", () => {
    expect(TESIS).toContain("limita_confianza");
    // La barra de datos degradados solo queda como respaldo para cuando NO hay tesis.
    expect(RENDER).toContain("{quote && !tesis && <DataHealthBar");
  });
});

describe("cambiar de ticker no arrastra nada del anterior", () => {
  test("el parche se vacía durante el render al cambiar de acción", () => {
    expect(DASHBOARD).toContain("if (cambioDeAccion)");
    expect(DASHBOARD).toContain("setParche({})");
    expect(DASHBOARD).toContain("const p = cambioDeAccion ? {} : parche;");
  });

  test("la respuesta del servidor está cacheada POR SÍMBOLO", () => {
    // react-query con el símbolo en la clave: no hay forma de leer el dashboard de
    // otro ticker, y por tanto tampoco su tesis.
    expect(DASHBOARD).toContain('queryKey: ["dashboard", sym, TIMEFRAME_BASE]');
  });

  test("el análisis de IA sí vive en el parche, que es lo que se vacía", () => {
    expect(DASHBOARD).toContain("const analysis = p.analysis || null;");
  });
});

describe("fuente única de precio", () => {
  test("no se lee `indicators.price` en ninguna parte de la página", () => {
    // Es el cierre de la última vela diaria: durante la sesión difiere SIEMPRE de
    // quote.price, así que enseñar los dos sería mostrar dos precios de la misma acción.
    expect(DASHBOARD_COD).not.toMatch(/indicators\??\.price\b/);
    expect(ESTADO_COD).not.toMatch(/indicators\??\.price\b/);
  });

  test("la cabecera viva se alimenta de `quote`", () => {
    expect(RENDER).toContain("<QuoteHeader quote={quote} />");
  });

  test("el estado técnico compara contra quote.price, no contra el cierre diario", () => {
    expect(ESTADO).toContain("const precio = quote?.price;");
  });
});

describe("fuente única de zonas de compra", () => {
  test("solo `buy_levels` alimenta el bloque de niveles", () => {
    const bloque = RENDER.slice(RENDER.indexOf("<TradingLevels"), RENDER.indexOf("</Suspense>"));
    expect(bloque).toContain("buyLevels={buyLevels}");
    expect(bloque).not.toContain("support_resistance");
    expect(bloque).not.toContain("lines.levels");
  });

  test("la página no lee los otros dos sistemas de niveles", () => {
    expect(DASHBOARD_COD).not.toMatch(/support_resistance/);
    expect(DASHBOARD_COD).not.toMatch(/lines\.levels/);
  });

  test("buyLevels prefiere el parche de IA y cae al servidor, sin tercera vía", () => {
    expect(DASHBOARD).toContain("const buyLevels = p.buyLevels || datos?.buy_levels || null;");
  });
});

describe("los datos técnicos que estaban invisibles", () => {
  test.each([
    ["indicators.regime?.regime", /indicators\.regime\?\.regime/],
    ["regime.adx", /indicators\.regime\?\.adx/],
    ["atr_pct", /indicators\.atr_pct/],
    ["obv_trend", /indicators\.obv_trend/],
    ["vwap_anchored", /indicators\.vwap_anchored/],
    ["salida_10w", /indicators\.salida_10w/],
  ])("%s se lee en EstadoTecnico", (_, patron) => {
    expect(ESTADO).toMatch(patron);
  });

  test("`recien_perdida` tiene su propio aviso: es la señal de salida del método", () => {
    expect(ESTADO).toContain("salida?.recien_perdida");
  });

  test("el bloque está montado sin condicionar a la IA", () => {
    expect(RENDER).toContain("<EstadoTecnico indicators={indicators}");
    expect(RENDER).not.toContain("{analysis && <EstadoTecnico");
  });
});

describe("peticiones al abrir una acción", () => {
  // Las que dispara la propia página. El resto (fuentes, alternativa, chartista
  // cacheado) las hacen sus componentes y se cuentan aparte, en su propio fichero.
  test("el contexto de mercado ya no se pide aquí", () => {
    for (const llamada of ["api.marketFutures", "api.marketSentiment", "api.marketHeatmap"]) {
      expect(DASHBOARD_COD).not.toContain(llamada);
    }
  });

  test("solo quedan dos consultas propias: dashboard y gráfico", () => {
    const consultas = DASHBOARD_COD.match(/useQuery\(\{/g) || [];
    expect(consultas).toHaveLength(2);
  });

  test("la del gráfico solo se activa fuera de la escala base", () => {
    // Al abrir, el gráfico sale del propio dashboard: la segunda consulta no dispara.
    expect(DASHBOARD).toContain("enabled: !!sym && timeframe !== TIMEFRAME_BASE");
  });

  test("no se ha colado ninguna llamada nueva a la API en la página", () => {
    const llamadas = new Set((DASHBOARD_COD.match(/api\.[a-zA-Z]+/g) || []));
    expect([...llamadas].sort()).toEqual(["api.analyze", "api.chart", "api.dashboard", "api.quote"]);
  });
});

describe("la IA es una acción secundaria, no el interruptor de la página", () => {
  test("el botón vive dentro del bloque de tesis", () => {
    expect(RENDER).toContain("onAnalizar={quote ? runAll : null}");
    expect(TESIS).toContain("btn-analisis-ia");
  });

  test("ya no hay banda de «Análisis completo IA» a ancho completo", () => {
    expect(RENDER).not.toContain("🧠 {loadingAnalysis");
  });

  test("la tarjeta de tesis de la IA desaparece: la determinista es la única", () => {
    expect(DASHBOARD_COD).not.toContain("InvestmentThesisCard");
  });
});

/**
 * Requisito 10: contar lo que cuesta abrir una acción.
 *
 * La página no es la única que pide: cada panel montado dispara lo suyo desde su
 * propio `useEffect`. Este bloque recorre el árbol y fija el total, para que añadir un
 * panel que abra red sea una decisión visible en la revisión y no un descubrimiento
 * en la factura.
 */
describe("inventario de peticiones de una apertura", () => {
  const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");

  // Componentes que se montan SIN condición al abrir, y qué piden ellos solos.
  const AL_ABRIR = [
    ["pages/Dashboard.jsx", ["api.dashboard"]],                 // 01 · el grueso
    ["components/SourcesPanel.jsx", ["api.fuentes"]],           // 07 · Mongo, cacheado
    ["components/MoreInsights.jsx", ["api.alternativa"]],       // 14 · screener cacheado 2 h
    ["components/ChartistPanel.jsx", ["api.chartistCached"]],   // 10 · solo lee caché
    ["hooks/useSignals.js", ["api.signals"]],                   // 04 · Mongo, caché 60 s
  ];

  test.each(AL_ABRIR)("%s pide exactamente lo previsto", (fichero, esperadas) => {
    const src = sinComentarios(leer(fichero));
    for (const llamada of esperadas) expect(src).toContain(llamada);
  });

  test("el total de peticiones automáticas es 5 + WebSocket", () => {
    // Antes eran 8 + WebSocket: se han ido futuros, miedo/codicia y mapa sectorial.
    // Si algún día sube, que sea rompiendo este test.
    expect(AL_ABRIR).toHaveLength(5);
    expect(sinComentarios(leer("pages/Dashboard.jsx"))).toContain("new WebSocket(");
  });

  test("ninguna apertura llama a /analyze, que es quien trae las fuentes de pago", () => {
    // `insider` y `earnings_history` SÍ se leen en Dashboard.jsx — de la respuesta de
    // /analyze, que solo corre cuando pulsas. Lo que no puede pasar es que alguno de
    // estos componentes la dispare solo, y eso se ve en quién llama, no en qué se lee.
    // Los paneles que se montan solos no la mencionan siquiera.
    for (const [fichero] of AL_ABRIR.filter(([f]) => f !== "pages/Dashboard.jsx")) {
      const src = sinComentarios(leer(fichero));
      for (const cara of ["api.analyze", "api.whyMoving", "api.backtest"]) {
        expect(src).not.toContain(cara);
      }
    }
    // Y en la página, la única llamada a /analyze vive dentro del handler del botón.
    const dash = sinComentarios(leer("pages/Dashboard.jsx"));
    expect(dash.match(/api\.analyze/g) || []).toHaveLength(1);
    const runAnalysis = dash.slice(dash.indexOf("const runAnalysis"), dash.indexOf("const runAll"));
    expect(runAnalysis).toContain("api.analyze");
  });
});
