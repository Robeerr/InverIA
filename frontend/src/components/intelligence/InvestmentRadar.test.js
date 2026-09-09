/**
 * El radar no puede fingir actividad.
 *
 * Es la garantía más fácil de perder sin darse cuenta: basta con que alguien deje el
 * barrido girando siempre «porque queda mejor», y a partir de ahí la pantalla dice que el
 * sistema trabaja pase lo que pase.
 *
 * ESTOS TESTS LEEN EL CÓDIGO FUENTE, Y NO ES LO IDEAL
 *
 * El proyecto no tiene `@testing-library/react` instalado, y añadir una dependencia no se
 * hace por iniciativa propia. Así que aquí se comprueba la ESTRUCTURA —que las marcas salen
 * de la lista de eventos, que el barrido depende del estado real, que el latido va atado a
 * `escuchando`— en vez del DOM pintado. Lo que sí está probado de verdad, contra valores y
 * no contra texto, es la geometría y la lógica de estados, que viven en `lib/intelligence`
 * precisamente para poder probarse.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", "..", rel), "utf8");
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
     .replace(/(^|[^:])\/\/.*$/gm, "$1");

const RADAR = sinComentarios(leer("components/intelligence/InvestmentRadar.jsx"));
const HOOK = sinComentarios(leer("hooks/useRadarAnimacion.js"));
const TOKENS = leer("styles/tokens.css");

describe("nada se dibuja sin un dato detrás", () => {
  test("las marcas salen de los eventos recibidos y de ningún otro sitio", () => {
    // Si alguien generase posiciones de relleno, aquí aparecería un Math.random o un
    // array literal de ejemplo.
    expect(RADAR).toMatch(/for \(const ev of eventos \|\| \[\]\)/);
    expect(RADAR).not.toMatch(/Math\.random/);
  });

  test("un evento sin hora o sin tier NO se coloca", () => {
    // `continue` y no un valor por defecto: una posición inventada se lee como una hora
    // concreta, y sería un dato falso disfrazado de geometría.
    expect(RADAR).toMatch(/if \(!radio \|\| grados === null\) continue;/);
  });

  test("el ángulo lo calcula la función probada, no el índice del bucle", () => {
    expect(RADAR).toContain("anguloPorHora(ev.recibido_en, ahora)");
    expect(RADAR).not.toMatch(/i \* 30|index \* /);
  });
});

describe("el barrido depende del estado real", () => {
  test("solo se monta si de verdad gira", () => {
    // Un barrido parado y tenue seguiría sugiriendo un mecanismo en marcha.
    expect(RADAR).toMatch(/\{girando && \(/);
  });

  test("gira porque hay fuentes escuchando, no siempre", () => {
    expect(RADAR).toContain("useRadarAnimacion(activas > 0)");
    expect(RADAR).toContain("escuchando(fuentes)");
  });

  test("el hook exige las DOS condiciones", () => {
    // Actividad real y ausencia de `prefers-reduced-motion`. Si una de las dos se cayera,
    // esta línea dejaría de existir.
    expect(HOOK).toContain("const girando = Boolean(activo) && !quieto;");
  });

  test("la preferencia de movimiento se escucha, no se lee una vez", () => {
    // Se puede cambiar con la web abierta, y entonces hay que obedecerla al momento.
    expect(HOOK).toContain("prefers-reduced-motion: reduce");
    expect(HOOK).toMatch(/addEventListener\("change"/);
  });
});

describe("el latido significa exactamente una cosa", () => {
  test("solo lo lleva una fuente que está escuchando", () => {
    expect(RADAR).toMatch(/\{e\.escuchando && \([\s\S]{0,200}iv-radar-latido/);
  });

  test("y desaparece si el usuario ha pedido quietud", () => {
    // No es cortesía: el movimiento continuo marea a parte de la gente. Sin animación el
    // radar sigue diciendo lo mismo, porque el estado ya va en el color.
    const bloque = TOKENS.slice(TOKENS.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(bloque).toMatch(/\.iv-radar-latido \{ animation: none/);
  });
});

describe("accesibilidad", () => {
  test("el radar se describe con palabras, incluido cuando está apagado", () => {
    // Es un SVG: sin `aria-label` un lector de pantalla no dice absolutamente nada, y la
    // pantalla entera desaparece para quien lo use.
    expect(RADAR).toContain('role="img"');
    expect(RADAR).toMatch(/apagado: ninguna fuente está escuchando/);
  });
});
