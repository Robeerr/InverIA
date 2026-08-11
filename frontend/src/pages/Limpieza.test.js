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
