/**
 * La pantalla de Inteligencia tiene que caber en un móvil.
 *
 * POR QUÉ ESTE TEST EXISTE
 *
 * Medido en un navegador a 390 px: la columna de contenido salía de 693 px y media
 * pantalla quedaba cortada —los contadores, las fechas de los eventos, los párrafos a
 * mitad de frase—. Y no se podía arrastrar para verlo, porque `.App` lleva
 * `overflow-x-hidden`: lo que desborda no se esconde detrás de un scroll, desaparece.
 *
 * La causa es sutil y muy fácil de reintroducir. `grid` + `lg:grid-cols-[...]` deja el
 * móvil SIN ninguna columna declarada, así que se crea una implícita, y una columna
 * implícita se dimensiona a `max-content` — al ancho del párrafo más largo que haya
 * dentro. `grid-cols-1` la declara como `minmax(0,1fr)`, que es lo que la obliga a
 * encoger. Se lee como redundante y no lo es: por eso hay un test.
 *
 * ESTE TEST LEE EL CÓDIGO FUENTE
 *
 * Igual que los del radar, y por el mismo motivo: no hay `@testing-library/react` en el
 * proyecto y no se añade una dependencia por iniciativa propia.
 */
const fs = require("fs");
const path = require("path");

const VISTA = fs.readFileSync(path.join(__dirname, "IntelligenceView.jsx"), "utf8");

// La rejilla de dos columnas: radar a la izquierda, eventos a la derecha.
const REJILLA = (VISTA.match(/className="[^"]*lg:grid-cols-\[[^"]*"/) || [""])[0];

test("la rejilla principal declara su columna de móvil", () => {
  expect(REJILLA).toContain("lg:grid-cols-[");        // la de escritorio sigue ahí
  expect(REJILLA).toContain("grid-cols-1");           // y la de móvil, declarada
});

test("las dos columnas de escritorio pueden encoger", () => {
  // `minmax(0,…)` en ambas: sin el 0, el contenido largo vuelve a estirar la columna,
  // que es exactamente el mismo fallo una pantalla más ancha.
  expect(REJILLA).toContain("lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]");
});

test("ninguna rejilla de la pantalla fija columnas sin punto de ruptura", () => {
  // `grid-cols-4` a secas son cuatro columnas también en un móvil de 390 px. Las que
  // haya tienen que empezar en 1 o 2 y crecer con `sm:`/`lg:`.
  const fijas = [...VISTA.matchAll(/(?<![a-z:-])grid-cols-(\d+)/g)]
    .map((m) => Number(m[1]))
    .filter((n) => n > 2);
  expect(fijas).toEqual([]);
});
