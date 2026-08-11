/**
 * La alternativa sectorial, ahora con el desglose de su puntuación.
 *
 * Lo que se protege es la razón por la que esto no fue un copiar y pegar: la fila era un
 * `<button>` que navega, y `<Score>` renderiza otro botón por dentro. Un botón dentro de
 * otro es HTML inválido y el comportamiento del clic queda indefinido.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const PANEL = leer("components/MoreInsights.jsx");
const PANEL_COD = sinComentarios(PANEL);

/** El cuerpo del `map` de alternativas, que es donde vive la fila. */
const FILA = PANEL_COD.slice(PANEL_COD.indexOf("d.alternativas.map"),
                             PANEL_COD.indexOf("</section>"));

describe("no hay botones anidados", () => {
  test("la fila es un contenedor, no un botón", () => {
    expect(FILA).toMatch(/<div\s+key=\{a\.symbol\}/);
    expect(FILA).not.toMatch(/<button\s+key=\{a\.symbol\}/);
  });

  test("solo hay un `<button>` escrito a mano en la fila: el de navegar", () => {
    // El otro lo pone `<Score>`, y queda como hermano, no dentro.
    expect((FILA.match(/<button/g) || [])).toHaveLength(1);
  });

  test("el botón de navegar y el Score son hermanos", () => {
    const iBoton = FILA.indexOf("<button");
    const iCierre = FILA.indexOf("</button>");
    const iScore = FILA.indexOf("<Score");
    expect(iBoton).toBeLessThan(iCierre);
    expect(iCierre).toBeLessThan(iScore);
  });

  test("ya no hace falta parar la propagación aquí", () => {
    // Con la fila convertida en div, abrir el desglose no dispara la navegación.
    expect(FILA).not.toContain("stopPropagation");
  });
});

describe("navegar sigue funcionando", () => {
  test("el botón conserva su onPick", () => {
    expect(FILA).toContain("onClick={() => onPick?.(a.symbol)}");
  });

  test("el símbolo y el nombre siguen ahí", () => {
    expect(FILA).toContain("{a.symbol}");
    expect(FILA).toContain("{a.name}");
  });

  test("y el hover del borde se conserva en el contenedor", () => {
    expect(FILA).toContain("hover:border-aviso");
  });
});

describe("el desglose, con el mismo componente que Oportunidades", () => {
  test("usa `<Score>` y no una implementación propia", () => {
    // Así el rótulo «ver desglose ▾» y el panel salen idénticos, sin coherencia a mano.
    expect(PANEL_COD).toContain('import Score from "./Score"');
    expect(FILA).toContain("<Score symbol={a.symbol}>");
  });

  test("no reimplementa el rótulo ni el desglose", () => {
    for (const propio of ["ver desglose", "ocultar ▴", "componentes", "multiplicador"]) {
      expect(PANEL_COD).not.toContain(propio);
    }
  });

  test("no llama al endpoint del desglose por su cuenta", () => {
    // La petición la hace `<Score>`, bajo demanda y una sola vez por fila.
    expect(PANEL_COD).not.toContain("desgloseScore");
  });

  test("sigue pidiendo solo la alternativa al montar", () => {
    expect(PANEL_COD).toContain("api.alternativa(symbol)");
    expect((PANEL_COD.match(/api\./g) || [])).toHaveLength(1);
  });
});

describe("lo que no cambia", () => {
  test("el verde del score es fijo en esta vista", () => {
    // Una alternativa se enseña PORQUE supera a la que estás mirando: aquí el verde es
    // correcto por definición, y no hace falta la escala por tramos de Oportunidades.
    expect(FILA).toContain("text-sube");
    expect(FILA).not.toContain("psColor");
  });

  test("el número y el crecimiento de ventas siguen apareciendo", () => {
    expect(FILA).toContain("{a.potential_score} pts");
    expect(FILA).toContain("a.revenue_growth");
  });

  test("el panel sigue oculto cuando no hay alternativas", () => {
    expect(PANEL_COD).toContain("if (!d || !(d.alternativas || []).length) return null;");
  });
});

describe("la carrera entre escaneos queda documentada", () => {
  test("está dicha en el fichero, no resuelta a escondidas", () => {
    expect(PANEL).toContain("CARRERA CONOCIDA");
  });
});
