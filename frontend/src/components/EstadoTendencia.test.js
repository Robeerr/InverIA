/**
 * Niveles o motivo, nunca los dos.
 *
 * La contradicción que este fichero impide es concreta: un «No comprar» con la lista de
 * zonas de compra debajo. Sería peor que cualquiera de las dos cosas por separado,
 * porque el usuario elegiría la mitad que le apetezca.
 *
 * Se comprueba sobre el código fuente, que es el patrón de este proyecto (no hay
 * `@testing-library`). Aquí además es lo adecuado: lo que se protege es que el render
 * sea EXCLUYENTE, y eso es una propiedad de la forma del componente.
 */
const fs = require("fs");
const path = require("path");

const PANEL = fs.readFileSync(path.join(__dirname, "EstadoTendencia.jsx"), "utf8");
const DASHBOARD = fs.readFileSync(path.join(__dirname, "..", "pages", "Dashboard.jsx"), "utf8");

/** El código sin comentarios: aquí se examina lo que se ejecuta, no lo que se explica. */
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const PANEL_COD = sinComentarios(PANEL);
const DASH_COD = sinComentarios(DASHBOARD);

describe("el panel de estado", () => {
  test("no aparece cuando la acción pasa el filtro de tendencia", () => {
    // SIN_EVALUAR significa «pasa el primer filtro»: ahí mandan los niveles de siempre.
    expect(PANEL_COD).toContain('estado === "SIN_EVALUAR"');
    expect(PANEL_COD).toContain("return null");
  });

  test("distingue NO_COMPRAR de EN_SEGUIMIENTO con colores distintos", () => {
    // Pintarlos igual convertiría «vigila esto» en «olvídate de esto».
    expect(PANEL_COD).toContain('estado === "NO_COMPRAR"');
    expect(PANEL_COD).toContain("border-baja");
    expect(PANEL_COD).toContain("border-aviso");
  });

  test("las clases de color son literales, no construidas", () => {
    // Tailwind genera el CSS leyendo el código: `border-${tono}` no existe en ningún
    // fichero, no se emite, y el elemento sale sin color sin que falle nada.
    expect(PANEL_COD).not.toMatch(/(border|text|bg)-\$\{/);
  });

  test("enseña los soportes como estructura, sin plan ni etiqueta de compra", () => {
    expect(PANEL_COD).toContain("soportes");
    for (const prohibido of ["entry_zone", "en_plan", "stop", "take_profit", "NIVEL"]) {
      expect(PANEL_COD).not.toContain(prohibido);
    }
  });
});

describe("el dashboard elige uno u otro", () => {
  test("es un ternario, no dos bloques independientes", () => {
    const trozo = DASH_COD.slice(DASH_COD.indexOf("zonasOcultas ?"));
    expect(trozo).toContain("<EstadoTendencia");
    expect(trozo).toContain("<TradingLevels");
    // Un solo `<TradingLevels` en todo el fichero: si apareciera fuera del ternario,
    // podría renderizarse a la vez que el motivo.
    expect(DASH_COD.match(/<TradingLevels/g)).toHaveLength(1);
    expect(DASH_COD.match(/<EstadoTendencia/g)).toHaveLength(1);
  });

  test("el estado se lee del servidor, no se deduce en el cliente", () => {
    // Deducirlo aquí sería duplicar la regla de tendencia en React, que es justo lo que
    // `tendencia.py` existe para evitar.
    expect(DASH_COD).toContain("datos?.zonas_ocultas_por_tendencia");
    expect(DASH_COD).not.toContain("sma200");
  });

  test("el análisis de IA arrastra el estado", () => {
    // Sin esto, pulsar «Ampliar con IA» sobre una acción bajista devolvería el panel de
    // niveles que el dashboard ya había ocultado.
    expect(DASH_COD).toContain("res.zonas_ocultas_por_tendencia");
  });
});
