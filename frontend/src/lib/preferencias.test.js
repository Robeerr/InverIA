/**
 * La portada y Operaciones tienen que enseñar las cifras en el MISMO método.
 *
 * Con «Como en DEGIRO» puesto, Operaciones enseñaba media ponderada y la portada LIFO:
 * realizado 7.264 € en una y 7.766 € en la otra, y parecía que no cuadraban. Las dos
 * sumaban lo mismo; solo repartían distinto.
 */
const fs = require("fs");
const path = require("path");
const { leerComoBroker, guardarComoBroker, CLAVE_COMO_BROKER } = require("./preferencias");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");

afterEach(() => window.localStorage.clear());

test("lo que guarda una vista lo lee la otra", () => {
  guardarComoBroker(true);
  expect(leerComoBroker()).toBe(true);
  guardarComoBroker(false);
  expect(leerComoBroker()).toBe(false);
});

test("sin preferencia guardada, el método de gestión", () => {
  expect(leerComoBroker()).toBe(false);
});

test("la clave es la que ya usaba Operaciones, para no perder la preferencia guardada", () => {
  expect(CLAVE_COMO_BROKER).toBe("ventas.comoBroker");
});

test("las dos pantallas leen la preferencia del MISMO sitio", () => {
  // Si cada una escribiera su propia clave, una errata bastaría para volver a enseñar
  // métodos distintos sin decirlo.
  for (const f of ["pages/VentasView.jsx", "components/hoy/PanelCartera.jsx"]) {
    const src = leer(f);
    expect(src).toContain("leerComoBroker");
    expect(src).not.toContain('"ventas.comoBroker"');
  }
});

test("la portada dice en qué método están las cifras", () => {
  const panel = leer("components/hoy/PanelCartera.jsx");
  expect(panel).toContain("media ponderada · como DEGIRO");
  expect(panel).toContain("Cifras {c.metodo}");
});

test("sin cifras ponderadas en la respuesta, la portada sigue con las de siempre", () => {
  // Una portada cacheada de antes del despliegue no trae `ponderada`: apagar las cifras
  // sería peor que enseñar las del método de gestión, que es lo que se veía hasta ahora.
  const panel = leer("components/hoy/PanelCartera.jsx");
  expect(panel).toContain("comoBroker && pond.latente_eur != null && pond.realizado_eur != null");
});
