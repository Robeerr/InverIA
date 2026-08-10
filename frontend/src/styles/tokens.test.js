/**
 * El contraste de la paleta se comprueba, no se estima.
 *
 * La app ya arrastró una vez este problema: en el modo oscuro había seis colores de
 * texto entre 1,87:1 y 3,39:1 —por debajo del mínimo legible— y justo en los paneles
 * que más se leen (Niveles de Trading, Chartista, Backtest). Se arreglaron a mano,
 * pero nada impedía que volviera a pasar al añadir el siguiente color.
 *
 * Este test lee tokens.css y falla si algún rol de texto baja de 4,5:1 sobre
 * cualquiera de las superficies de su tema. Cambiar un token y romper la legibilidad
 * deja de ser algo que se descubre en producción.
 */
const fs = require("fs");
const path = require("path");

const CSS = fs.readFileSync(path.join(__dirname, "tokens.css"), "utf8");

/** Extrae los tokens `--iv-*` de un bloque de selector concreto. */
function tokensDe(selector) {
  const re = new RegExp(`${selector}\\s*\\{([\\s\\S]*?)\\n\\}`, "m");
  const bloque = CSS.match(re);
  if (!bloque) throw new Error(`No se encontró el bloque ${selector} en tokens.css`);
  const tokens = {};
  for (const m of bloque[1].matchAll(/(--iv-[\w-]+)\s*:\s*([^;]+);/g)) {
    const canales = m[2].trim().split(/[\s,]+/).map(Number);
    if (canales.length >= 3 && canales.every((n) => !isNaN(n))) {
      tokens[m[1]] = canales.slice(0, 3);
    }
  }
  return tokens;
}

function luminancia([r, g, b]) {
  const f = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function ratio(a, b) {
  const la = luminancia(a);
  const lb = luminancia(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const ROLES_TEXTO = [
  "--iv-tinta", "--iv-tinta-2", "--iv-tinta-3",
  "--iv-sube", "--iv-baja", "--iv-aviso", "--iv-info", "--iv-marca",
];
const SUPERFICIES = ["--iv-fondo", "--iv-superficie", "--iv-superficie-2"];

const CLARO = tokensDe(":root");
const OSCURO = { ...CLARO, ...tokensDe("\\.dark") }; // .dark solo redefine; hereda el resto

describe.each([["claro", CLARO], ["oscuro", OSCURO]])("tema %s", (nombre, paleta) => {
  test.each(SUPERFICIES)("todos los roles de texto son legibles sobre %s", (superficie) => {
    // Se recogen todos los fallos antes de reventar: si hay tres roles por debajo,
    // conviene verlos de una vez y no arreglarlos de uno en uno.
    const bajos = [];
    for (const rol of ROLES_TEXTO) {
      expect(paleta[rol]).toBeDefined();
      const r = ratio(paleta[rol], paleta[superficie]);
      // 4,5:1 es el mínimo de WCAG AA para texto normal.
      if (r < 4.5) bajos.push(`${rol} → ${r.toFixed(2)}:1`);
    }
    expect(bajos).toEqual([]);
  });

  test("el texto sobre el color de marca es legible", () => {
    const r = ratio(paleta["--iv-marca-tinta"], paleta["--iv-marca"]);
    expect(r).toBeGreaterThanOrEqual(4.5);
  });

  test("el borde marcado se percibe (3:1 no textual)", () => {
    const r = ratio(paleta["--iv-linea-marcada"], paleta["--iv-superficie"]);
    expect(r).toBeGreaterThanOrEqual(3);
  });
});

test("ningún token existe en un solo tema", () => {
  // El fallo que esta capa viene a corregir es exactamente este: un color definido
  // solo en claro que en oscuro se queda sin valor y hereda algo que nadie eligió.
  const soloOscuro = Object.keys(tokensDe("\\.dark")).filter((t) => !(t in CLARO));
  expect(soloOscuro).toEqual([]);
});

test("los tokens son tripletes RGB, no hex", () => {
  // Si alguien escribe un hex, Tailwind pierde el poder componer opacidades
  // (`bg-sube/10`) y el fallo aparece lejos, en la pantalla que lo usaba.
  const hex = CSS.match(/--iv-[\w-]+\s*:\s*#[0-9a-fA-F]{3,8}\s*;/g);
  expect(hex).toBeNull();
});
