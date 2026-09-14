/**
 * Las ventas a cero del CSV tenían que tener una salida.
 *
 * El aviso decía «reimpórtalo con la casilla de corregir comisiones marcada», y eso solo
 * funciona si conservas aquel fichero. Si no lo tienes, la venta se queda a cero para
 * siempre y el aviso no se va nunca — que es justo lo que pasaba con las dos que
 * quedaban.
 *
 * Se comprueba sobre el código fuente: no hay `@testing-library/react` en el proyecto y
 * no se añade una dependencia por iniciativa propia.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const VISTA = leer("pages/VentasView.jsx");
const API = leer("lib/api.js");

test("hay un botón para estimar las que vinieron del CSV", () => {
  expect(VISTA).toContain("repararComisiones.mutate(true)");
  expect(VISTA).toContain("que vinieron");
  expect(API).toContain("incluir_csv");
});

test("el botón del CSV solo sale si QUEDA alguna del CSV", () => {
  // Con todas tecleadas a mano, ofrecerlo sería un botón que no hace nada.
  expect(VISTA).toContain("hist.ventas_sin_comision > hist.ventas_sin_comision_manuales");
});

test("la pregunta avisa de que ahí el cero SÍ vino con el fichero", () => {
  // Es la diferencia entera entre los dos grupos: en el tecleado el cero es un hueco del
  // formulario; en el del CSV puede ser una operación que de verdad fue gratis.
  expect(VISTA).toContain("EN LAS DEL CSV EL CERO LLEGÓ CON EL FICHERO");
  expect(VISTA).toContain("esto le pone un coste");
});

test("la pregunta desglosa por ORIGEN, no solo el total", () => {
  // Salió «8 apuntes, 16 €» a quien venía a arreglar 2 ventas de 4,42 €. Sin saber
  // cuántos vienen del fichero y cuántos están tecleados, eso es aprobar a ciegas ocho
  // escrituras sobre apuntes propios.
  expect(VISTA).toContain("previo.a_mano");
  expect(VISTA).toContain("previo.del_csv");
  expect(VISTA).toContain("tecleados a mano");
  expect(VISTA).toContain("que vinieron del CSV");
});

test("reimportar sigue siendo lo primero que se ofrece", () => {
  // El fichero trae la cifra REAL; la estimación es el plan B de quien ya no lo tiene.
  // Invertir ese orden cambiaría un dato bueno por uno inventado sin necesidad.
  const i = VISTA.indexOf("se corrigen reimportándolo");
  expect(i).toBeGreaterThan(-1);
  expect(VISTA.slice(i, i + 400)).toContain("es lo mejor porque trae la cifra");
});
