/**
 * Navegar y guardar son cosas distintas.
 *
 * EL BUG QUE CONGELA ESTE FICHERO
 *
 * `PaginaAccion` tenía un efecto para copiar el símbolo de la URL al estado. Lo hacía
 * llamando a `setSymbol`, que en esa ruta no es un `useState` sino `irAAccion` — y esa
 * además NAVEGA.
 *
 * Al pulsar un ticker había un render en el que el estado ya era el nuevo y `symbolUrl`
 * seguía siendo el viejo. El efecto veía la discrepancia y «sincronizaba» empujando la
 * URL DE VUELTA. Cada clic producía dos pushState:
 *
 *     pushState → /accion/AVGO      ← el clic
 *     pushState → /accion/INTC      ← el rebote del efecto
 *
 * Y la ruta se quedaba donde estaba. Rompía la watchlist y la alternativa sectorial a la
 * vez, porque no comparten componente: comparten `irAAccion`.
 *
 * POR QUÉ NO LO CAZÓ NINGÚN TEST
 *
 * Los que había comprobaban que el manejador existía y que la prop llegaba. Y era cierto:
 * el clic llegaba, `navigate()` se ejecutaba. Lo que fallaba era lo que pasaba DESPUÉS, y
 * eso solo se ve contando navegaciones o mirando quién puede provocarlas.
 */
const fs = require("fs");
const path = require("path");

const APP = fs.readFileSync(path.join(__dirname, "App.js"), "utf8");
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const APP_COD = sinComentarios(APP);

/** El cuerpo de una función de primer nivel. */
const cuerpoDe = (nombre) => {
  const i = APP_COD.indexOf(`function ${nombre}(`);
  const j = APP_COD.indexOf("\nfunction ", i + 10);
  return APP_COD.slice(i, j === -1 ? undefined : j);
};

describe("un efecto de sincronización no navega", () => {
  const PAGINA = cuerpoDe("PaginaAccion");

  test("el efecto usa el setter puro, no el que navega", () => {
    expect(PAGINA).toContain("sincronizar(sym)");
    expect(PAGINA).not.toMatch(/if \(sym && sym !== symbol\) setSymbol\(/);
  });

  test("y recibe los dos por separado, con nombres distintos", () => {
    // Que ambos se llamaran `setSymbol` es lo que escondió el problema: el nombre decía
    // «guarda» y la función además navegaba.
    expect(PAGINA).toContain("function PaginaAccion({ symbol, setSymbol, sincronizar,");
    expect(APP_COD).toContain("sincronizar={setSymbol}");
    expect(APP_COD).toContain("setSymbol={irAAccion}");
  });

  test("ningún efecto de la app llama a la función que navega", () => {
    // La regla, dicha una vez: navegar es consecuencia de una acción del usuario, nunca
    // de un render.
    for (const m of APP_COD.matchAll(/useEffect\(\(\) => \{([\s\S]*?)\n {2}\}, \[/g)) {
      expect(m[1]).not.toContain("irAAccion(");
    }
  });
});

describe("solo hay un sitio que navegue", () => {
  test("`navigate(` se llama únicamente dentro de irAAccion", () => {
    const irA = APP_COD.slice(APP_COD.indexOf("const irAAccion"),
                              APP_COD.indexOf("}, [navigate]);") + 15);
    const total = (APP_COD.match(/\bnavigate\(/g) || []).length;
    const dentro = (irA.match(/\bnavigate\(/g) || []).length;
    expect(total).toBe(dentro);
  });

  test("irAAccion sigue guardando Y navegando, en ese orden", () => {
    const irA = APP_COD.slice(APP_COD.indexOf("const irAAccion"),
                              APP_COD.indexOf("}, [navigate]);"));
    expect(irA.indexOf("setSymbol(sym)")).toBeLessThan(irA.indexOf("navigate("));
  });
});

describe("al cambiar de pantalla se vuelve al principio", () => {
  const IR = cuerpoDe("IrAlPrincipio");

  test("existe y está montado dentro del Router", () => {
    // Fuera del Router, `useLocation` reventaría; y montado en `App` en vez de en
    // `AppInner` quedaría fuera del BrowserRouter.
    expect(IR).toContain("window.scrollTo(0, 0)");
    expect(APP_COD).toContain("<IrAlPrincipio />");
    expect(cuerpoDe("AppInner")).toContain("<IrAlPrincipio />");
  });

  test("reacciona al cambio de ruta", () => {
    // `pathname` cambia también entre dos acciones: /accion/INTC → /accion/AVGO.
    expect(IR).toContain("const { pathname } = useLocation()");
    expect(IR).toMatch(/\}, \[pathname, tipo\]\)/);
  });

  test("NO salta al ir atrás", () => {
    // El navegador restaura la posición en un POP. Saltar al principio destruiría justo
    // lo que se espera del botón atrás: volver donde estabas.
    expect(IR).toContain('if (tipo === "POP") return;');
  });

  test("el salto es instantáneo, no suave", () => {
    // Animar dos pantallas mientras la siguiente se monta se ve como un tirón y retrasa
    // la lectura.
    expect(IR).not.toContain("smooth");
    expect(IR).not.toContain("behavior");
  });
});

describe("las pantallas siguen recibiendo lo que esperan", () => {
  test("la página de acción recibe el que navega para los clics", () => {
    // Watchlist y alternativa sectorial lo reciben por debajo como `setSymbol`/`onPick`.
    expect(APP_COD).toMatch(/<PaginaAccion[\s\S]*?setSymbol=\{irAAccion\}/);
  });

  test.each(["OpportunitiesView", "CalendarView", "SignalsView"])(
    "%s sigue navegando con irAAccion", (pantalla) => {
      expect(APP_COD).toMatch(new RegExp(`<${pantalla} setSymbol=\\{irAAccion\\}`));
    });

  test("la ficha se pinta con el símbolo de la URL, no con el del estado", () => {
    // Si usara el del estado, al navegar enseñaría la acción anterior un fotograma.
    expect(cuerpoDe("PaginaAccion")).toContain("symbol={(symbolUrl || symbol || \"\").toUpperCase()}");
  });
});
