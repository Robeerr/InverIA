/**
 * La pantalla dice qué documentos leyó el modelo, y lo dice también cuando fue solo uno.
 *
 * Con la lectura de anexos, una investigación puede haber visto el 8-K solo o el 8-K más
 * sus EX-99. Si la pantalla no lo distingue, una incertidumbre del modelo no se puede
 * atribuir: ¿faltaba en el documento o no se descargó el anexo?
 *
 * Se comprueba sobre el código fuente: no hay `@testing-library/react` en el proyecto y
 * no se añade una dependencia por iniciativa propia.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, rel), "utf8");
const COMPONENTE = leer("DocumentosEnviados.jsx");
const PLAN = leer("PlanInvestigacion.jsx");
const CAJON = leer("IntelligenceDrawer.jsx");

test("las dos pantallas usan la MISMA pieza", () => {
  // Dos formas de pintar lo mismo acaban diciendo cosas distintas.
  expect(PLAN).toContain("<DocumentosEnviados documentos={a.documentos_enviados}");
  expect(CAJON).toContain("<DocumentosEnviados documentos={evento.documentos_enviados}");
});

test("cada documento enseña su tipo, su enlace, sus caracteres y si se recortó", () => {
  for (const campo of ["d.tipo", "d.url", "d.documento", "d.caracteres_enviados",
                       "d.recortado", "d.caracteres_extraidos"]) {
    expect(COMPONENTE).toContain(campo);
  }
});

test("las investigaciones ANTERIORES dicen que leyeron solo el principal", () => {
  // Sin el campo, la ausencia es el dato: separa los casos 1–8 de los siguientes.
  expect(COMPONENTE).toContain("el modelo leyó solo el documento");
  expect(CAJON).toContain("anterior />");
  // En el resultado recién ejecutado NO: ahí el campo siempre viene.
  expect(PLAN).not.toContain("anterior");
});

test("«no había EX-99» y «no se pudo leer» se distinguen", () => {
  expect(COMPONENTE).toContain("anexos.motivo");
  expect(COMPONENTE).toContain("anexos.fallos");
});
