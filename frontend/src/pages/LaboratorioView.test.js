/**
 * El laboratorio no puede presentar lo leído como si fuera medido.
 *
 * Es la única garantía que esta pantalla tiene que dar, y es fácil de perder sin darse
 * cuenta: basta con juntar en una tabla los umbrales de un libro y los que hemos medido,
 * y a partir de ahí los dos se leen con el mismo respaldo.
 *
 * ESTOS TESTS LEEN EL CÓDIGO FUENTE
 *
 * Mismo motivo que los del radar: no hay `@testing-library/react` en el proyecto y no se
 * añade una dependencia por iniciativa propia.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const VISTA = leer("pages/LaboratorioView.jsx");
/** Sin comentarios: el bloque que EXPLICA por qué no hay puntuación global contiene el
 *  término, y buscarlo sobre el fichero entero daba un falso positivo. */
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
     .replace(/(^|[^:])\/\/.*$/gm, "$1");
const CODIGO = sinComentarios(VISTA);
const API = leer("lib/api.js");
const RAIL = leer("components/Rail.jsx");
const APP = leer("App.js");

test("la pantalla separa lo leído, lo que se cree y lo medido", () => {
  expect(VISTA).toContain("Lo que creemos y no hemos medido");
  expect(VISTA).toContain("Lo que hemos medido");
  expect(VISTA).toContain("Conceptos leídos");
});

test("los cuatro finales de un experimento tienen su etiqueta", () => {
  for (const estado of ["VALIDATED", "REJECTED", "INSUFFICIENT_DATA", "INCONCLUSIVE"]) {
    expect(VISTA).toContain(estado);
  }
});

test("NO existe ninguna puntuación global del laboratorio", () => {
  // Un «InverIA IQ» sumaría conceptos leídos, hipótesis abiertas y experimentos hechos,
  // que no son la misma magnitud. Es el error que `separacion.py` documenta.
  for (const prohibido of ["InverIA IQ", "inveriaIq", "puntuacionGlobal", "scoreTotal"]) {
    expect(CODIGO).not.toContain(prohibido);
  }
  // Y la explicación SÍ tiene que seguir en el fichero, para que nadie lo añada creyendo
  // que simplemente se olvidó.
  expect(VISTA).toContain("InverIA IQ");
});

test("el experimento enseña su método y sus sesgos, no solo el resultado", () => {
  expect(VISTA).toContain("Método y sesgos");
  expect(VISTA).toContain("e.controles");
});

test("cuando no hay experimentos se dice, en vez de enseñar una tabla vacía", () => {
  expect(VISTA).toContain("Todavía no se ha ejecutado ningún experimento");
});

test("solo el experimento ESCRIBE; el resto de la pantalla lee", () => {
  const lab = API.slice(API.indexOf("laboratorio: {"), API.indexOf("intelligence: {"));
  expect((lab.match(/client\.post/g) || []).length).toBe(1);
  expect((lab.match(/client\.get/g) || []).length).toBe(2);
  expect(lab).toContain("distanciaAlMaximo");
});

test("la rejilla declara su columna de móvil", () => {
  // Mismo fallo que ya cortó la pantalla de Inteligencia por la mitad: sin `grid-cols-1`
  // la columna implícita se dimensiona a `max-content` y no encoge.
  const rejilla = (VISTA.match(/className="[^"]*lg:grid-cols-\[[^"]*"/) || [""])[0];
  expect(rejilla).toContain("grid-cols-1");
  expect(rejilla).toContain("minmax(0,1fr)");
});

test("la pantalla está enganchada a la navegación y a una ruta", () => {
  expect(RAIL).toContain('to: "/laboratorio"');
  expect(APP).toContain('path="/laboratorio"');
  expect(APP).toContain("LaboratorioView");
});
