/**
 * La auditoría de la Inteligencia vive entre las herramientas, no en la investigación.
 *
 * La pantalla de investigación está congelada: la exportación y el banco de pruebas se
 * manejan desde Diagnóstico. Las dos acciones que escriben o gastan —congelar el banco y
 * ejecutarlo— piden confirmación con su efecto escrito.
 *
 * Se comprueba sobre el código fuente, como el resto de pruebas de pantallas del
 * proyecto: no hay `@testing-library/react` y no se añade por iniciativa propia.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, rel), "utf8");
const DIAGNOSTICO = leer("DiagnosticoView.jsx");
const API = leer("../lib/api.js");
const INVESTIGACION = ["../components/intelligence/PlanInvestigacion.jsx",
                       "../components/intelligence/IntelligenceDrawer.jsx",
                       "../components/intelligence/DocumentosEnviados.jsx"].map(leer);

const bloque = DIAGNOSTICO.slice(DIAGNOSTICO.indexOf("function AuditoriaInteligencia"),
                                 DIAGNOSTICO.indexOf("export default function DiagnosticoView"));

test("el bloque está en Diagnóstico y se pinta", () => {
  expect(bloque).toContain('data-testid="auditoria-inteligencia"');
  expect(DIAGNOSTICO).toContain("<AuditoriaInteligencia />");
});

test("la pantalla de investigación no se toca", () => {
  for (const fuente of INVESTIGACION) {
    expect(fuente).not.toContain("exportarInvestigaciones");
    expect(fuente).not.toContain("congelarBanco");
    expect(fuente).not.toContain("traza");
  }
});

test("congelar y ejecutar el banco piden confirmación con su efecto escrito", () => {
  const congelar = bloque.slice(bloque.indexOf('id: "congelar"'), bloque.indexOf('id: "exportar-banco"'));
  const ejecutar = bloque.slice(bloque.indexOf('id: "ejecutar"'), bloque.indexOf('id: "ejecuciones"'));
  expect(congelar).toContain("confirmar:");
  expect(congelar).toContain("No toca las investigaciones");
  expect(ejecutar).toContain("confirmar:");
  expect(ejecutar).toContain("20 llamadas al modelo");
});

test("exportar y ver no piden confirmación: no escriben nada", () => {
  for (const id of ['id: "exportar"', 'id: "fallos"', 'id: "banco"', 'id: "ejecuciones"']) {
    const desde = bloque.indexOf(id);
    const tramo = bloque.slice(desde, bloque.indexOf("},", desde));
    expect(tramo).not.toContain("confirmar:");
  }
});

test("las llamadas van a los endpoints de auditoría", () => {
  for (const ruta of ["/intelligence/investigaciones/exportar", "/intelligence/intentos",
                      "/intelligence/banco", "/intelligence/banco/congelar",
                      "/intelligence/banco/exportar", "/intelligence/banco/ejecutar",
                      "/intelligence/banco/ejecuciones"]) {
    expect(API).toContain(ruta);
  }
});
