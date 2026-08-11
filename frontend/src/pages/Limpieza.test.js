/**
 * Que lo retirado no vuelva por la puerta de atrás.
 *
 * La limpieza de la Fase 3 quitó cosas que llevaban meses en pantalla, y la tentación
 * de restaurarlas aparece al tercer día, no al primero. Estos tests obligan a que
 * volver a ponerlas sea una decisión discutida y no un `git revert` distraído.
 *
 * Se comprueba sobre el código, como el resto de la suite del frontend: lo que se
 * protege es la FORMA del árbol de componentes, no un render concreto.
 */
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..");
const leer = (rel) => fs.readFileSync(path.join(SRC, rel), "utf8");
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

/** Todos los ficheros de código del frontend, sin tests. */
function todasLasFuentes() {
  const out = [];
  (function andar(dir) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) { if (e.name !== "node_modules") andar(p); continue; }
      if (/\.(js|jsx)$/.test(e.name) && !/\.test\.js$/.test(e.name)) out.push(p);
    }
  })(SRC);
  return out;
}

describe("la tesis de la IA no vuelve como tarjeta aparte", () => {
  test("InvestmentThesisCard ya no existe en ninguna parte", () => {
    // Narraba otra vez lo que narra `tesis.py`, con otra lógica y solo tras pulsar IA.
    // Si la IA aporta mejor prosa, enriquece el bloque 02; no abre un segundo relato.
    for (const f of todasLasFuentes()) {
      expect(fs.readFileSync(f, "utf8")).not.toContain("InvestmentThesisCard");
    }
  });
});

describe("un solo sistema de soportes en el gráfico", () => {
  const CHART = sinComentarios(leer("components/LightweightChart.jsx"));

  test("el soporte de lines.levels ya no se dibuja", () => {
    // Competía con las zonas del motor de confluencia, que llevan fuerza y razones.
    expect(CHART).not.toContain('role === "soporte"');
    expect(CHART).not.toContain('title: "Sop"');
  });

  test("la resistencia sigue dibujándose: no tiene sustituto", () => {
    // `levels_engine` solo produce zonas de COMPRA, así que quitarla dejaría el gráfico
    // sin techo. Es la única lectura de `lines.levels` que sobrevive.
    expect(CHART).toContain('role === "resistencia"');
    expect(CHART).toContain('title: "Res"');
  });

  test("las zonas de compra siguen saliendo de buy_levels", () => {
    expect(CHART).toContain("(buyLevels || [])");
  });
});

describe("el contexto de mercado no regresa a la página de acción", () => {
  const DASH = sinComentarios(leer("pages/Dashboard.jsx"));

  test.each(["MarketFuturesBar", "FearGreedBar", "SectorHeatmap"])(
    "%s no se monta en la acción", (componente) => {
      expect(DASH).not.toContain(componente);
    });

  test("pero siguen existiendo y montados en «Hoy»", () => {
    const contexto = leer("components/ContextoMercado.jsx");
    const hoy = leer("pages/HoyView.jsx");
    for (const c of ["MarketFuturesBar", "FearGreedBar", "SectorHeatmap"]) {
      expect(contexto).toContain(`export function ${c}`);
      expect(hoy).toContain(`<${c}`);
    }
  });
});

describe("no quedan exports huérfanos en lo que hemos tocado", () => {
  // Se comprueban solo los ficheros de la Fase 3: un barrido global sacaría
  // constantes de scaffolding ajenas a este trabajo.
  const TOCADOS = [
    "components/InfoCards.jsx",
    "components/ContextoMercado.jsx",
    "components/TesisPanel.jsx",
    "components/EstadoTecnico.jsx",
    "components/TuPosicion.jsx",
    "components/IndicatorsPanel.jsx",
    "lib/posicion.js",
  ];

  test.each(TOCADOS)("%s: todo lo que exporta tiene consumidor", (rel) => {
    const src = leer(rel);
    const nombres = [...src.matchAll(/^export\s+(?:function|const)\s+([A-Za-z_$][\w$]*)/gm)]
      .map((m) => m[1]);
    const propio = path.join(SRC, rel);
    for (const nombre of nombres) {
      const usos = todasLasFuentes()
        .filter((f) => f !== propio)
        .filter((f) => new RegExp(`\\b${nombre}\\b`).test(fs.readFileSync(f, "utf8")));
      const usoInterno = (src.match(new RegExp(`\\b${nombre}\\b`, "g")) || []).length > 1;
      expect(usos.length > 0 || usoInterno).toBe(true);
    }
  });
});

/**
 * El panel de niveles: cuatro dimensiones, cuatro canales.
 *
 * Con FORM a $112.47 el panel apuntaba al revés que la operativa: NIVEL 1 (por donde se
 * entra, a −1,4%) lucía barra a media asta con fuerza 83, y NIVEL 6 (a −50,7%) lucía
 * barra llena y verde con fuerza 100. La barra medía fiabilidad y se leía como
 * conveniencia. Estos tests fijan el reparto nuevo.
 */
describe("panel de niveles · un canal por dimensión", () => {
  const TL = sinComentarios(leer("components/TradingLevels.jsx"));

  test("la pertenencia al plan viene del backend, no se recalcula aquí", () => {
    // Replicar el 30% en React haría que la pantalla mintiera en silencio el día que
    // MAX_PLAN_DEPTH cambiara por variable de entorno.
    expect(TL).toContain("z.en_plan");
    expect(TL).not.toContain("0.30");
    expect(TL).not.toContain("MAX_PLAN_DEPTH");
  });

  test("sin en_plan no se adivina el corte: se cae a una lista sin agrupar", () => {
    expect(TL).toContain("const hayPlan = levels.some((z) => typeof z.en_plan === \"boolean\")");
  });

  test("la confluencia se cuenta en métodos, no se mide con una barra", () => {
    expect(TL).toContain("Coinciden ${metodos} métodos");
    // La barra de porcentaje desaparece; la fuerza ponderada queda en el title.
    expect(TL).not.toContain("width: `${Math.max(0, Math.min(100, z.strength))}%`");
    expect(TL).toContain("Fuerza ponderada ${z.strength}/100");
  });

  test("la cercanía se codifica con posición: hay raíl de distancia", () => {
    expect(TL).toContain("z.distance_pct");
    expect(TL).toContain("border-r-2");
  });

  test("los dos roles con nombre están, y son solo dos", () => {
    expect(TL).toContain("El más cercano");
    expect(TL).toContain("El más sólido");
    expect(TL).toContain('rol: z === plan[0] ? "cercano"');
  });

  test("los estructurales bajan de peso pero siguen visibles con su distancia", () => {
    expect(TL).toContain("Soportes estructurales");
    expect(TL).toContain("estructural");
    // Siguen recibiendo la distancia: no se esconden, se subordinan.
    expect(TL).toContain("estructurales.map");
  });

  test("no se inventa ninguna métrica nueva", () => {
    // Acotado al bloque del panel: más abajo, el plan de la IA pinta zonas con otra
    // forma (min/max/comment, que salen de `_deterministic_levels`) y no son buy_levels.
    const bloque = TL.slice(TL.indexOf("function Nivel("), TL.indexOf("function RecBig("));
    const campos = [...bloque.matchAll(/z\.([a-z_]+)/g)].map((m) => m[1]);
    const permitidos = new Set(["price", "zone_low", "zone_high", "strength",
      "distance_pct", "reasons", "label", "tactical", "en_plan", "rol"]);
    for (const c of new Set(campos)) expect(permitidos.has(c)).toBe(true);
  });
});
