/**
 * Leer un token desde JavaScript sin que el gráfico se quede a oscuras.
 *
 * El gráfico dibuja sobre un lienzo y su API recibe cadenas de color, no clases, así que
 * es el único sitio de la app que tiene que leer los tokens a mano. Lo que protege este
 * fichero es que una lectura fallida NUNCA produzca un color inválido: en el lienzo eso
 * no se ve como un color feo, se ve como una serie que no se dibuja.
 */
const fs = require("fs");
const path = require("path");

const { leerToken, RESPALDOS } = require("./tokens");

const CSS = fs.readFileSync(path.join(__dirname, "..", "styles", "tokens.css"), "utf8");

/** Los tokens del bloque `:root` (tema claro), que es de donde salen los respaldos. */
function tokensClaros() {
  const bloque = CSS.match(/:root \{([\s\S]*?)\n\}/m);
  const out = {};
  for (const m of bloque[1].matchAll(/(--iv-[\w-]+)\s*:\s*([^;]+);/g)) {
    const canales = m[2].trim().split(/[\s,]+/).map(Number);
    if (canales.length >= 3 && canales.every((n) => !isNaN(n))) {
      out[m[1]] = canales.slice(0, 3).join(" ");
    }
  }
  return out;
}

afterEach(() => {
  document.documentElement.style.cssText = "";
});

describe("lectura del token", () => {
  test("devuelve el valor declarado, en rgb() con comas", () => {
    document.documentElement.style.setProperty("--iv-sube", "10 20 30");
    expect(leerToken("--iv-sube")).toBe("rgb(10, 20, 30)");
  });

  test("acepta el triplete separado por comas además de por espacios", () => {
    document.documentElement.style.setProperty("--iv-baja", "1, 2, 3");
    expect(leerToken("--iv-baja")).toBe("rgb(1, 2, 3)");
  });

  test("usa comas y no espacios", () => {
    // La forma separada por espacios es CSS Color 4 y el lienzo la soportó más tarde.
    // No hay ninguna ventaja en arriesgarse.
    document.documentElement.style.setProperty("--iv-info", "4 5 6");
    expect(leerToken("--iv-info")).not.toMatch(/\d \d/);
  });
});

describe("respaldos: un color inválido deja la serie sin dibujar", () => {
  test("sin el token declarado se usa el respaldo", () => {
    // jsdom no aplica tokens.css, así que este es el caso real de `getComputedStyle`
    // devolviendo vacío: exactamente lo que puede pasar antes de que la hoja se aplique.
    expect(leerToken("--iv-sube")).toBe(`rgb(${RESPALDOS["--iv-sube"].split(" ").join(", ")})`);
  });

  test("un respaldo explícito gana al de la tabla", () => {
    expect(leerToken("--iv-sube", "9 9 9")).toBe("rgb(9, 9, 9)");
  });

  test("un token desconocido no revienta ni devuelve una cadena vacía", () => {
    const c = leerToken("--iv-no-existe");
    expect(c).toMatch(/^rgb\(\d+, \d+, \d+\)$/);
  });

  test("un triplete a medias cae al respaldo en vez de dar rgb(47, 107)", () => {
    document.documentElement.style.setProperty("--iv-sube", "47 107");
    expect(leerToken("--iv-sube")).toBe(`rgb(${RESPALDOS["--iv-sube"].split(" ").join(", ")})`);
  });

  test("siempre devuelve una cadena rgb() válida, pase lo que pase", () => {
    for (const entrada of ["", "   ", "no-es-un-color"]) {
      document.documentElement.style.setProperty("--iv-baja", entrada);
      expect(leerToken("--iv-baja")).toMatch(/^rgb\(-?\d+, -?\d+, -?\d+\)$/);
    }
  });
});

describe("los respaldos no se desincronizan de tokens.css", () => {
  // Están repetidos del fichero a propósito —JS no puede leer una hoja de estilos que
  // aún no se ha aplicado—, así que la duplicación se vigila aquí, igual que la de
  // `.iv-oscuro`.
  const CLARO = tokensClaros();

  test.each(Object.keys(RESPALDOS))("%s coincide con el tema claro", (nombre) => {
    expect(RESPALDOS[nombre]).toBe(CLARO[nombre]);
  });

  test("todo respaldo apunta a un token que existe", () => {
    for (const nombre of Object.keys(RESPALDOS)) {
      expect(CLARO[nombre]).toBeDefined();
    }
  });
});
