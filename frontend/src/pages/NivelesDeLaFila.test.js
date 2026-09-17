/**
 * Las etiquetas de nivel de una fila dicen en cuáles tienes posición AHORA.
 *
 * Se pintaba `niveles_comprados`, que recorre el historial entero de compras: una fila
 * con tres lotes abiertos enseñaba cuatro etiquetas, y la cuarta era un nivel del que ya
 * se había salido.
 *
 * El primer intento fue apagarla y escribirle «vendido». Estaba mal: afirma POR QUÉ no
 * hay posición, y eso esta fila no lo sabe — un nivel puede no tener lote abierto porque
 * se vendió o porque nunca se compró, y el chip no distingue los dos casos.
 *
 * Se comprueba sobre el código fuente: no hay `@testing-library/react` en el proyecto y
 * no se añade una dependencia por iniciativa propia.
 */
const fs = require("fs");
const path = require("path");

const VISTA = fs.readFileSync(path.join(__dirname, "VentasView.jsx"), "utf8");
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
     .replace(/(^|[^:])\/\/.*$/gm, "$1");
const CODIGO = sinComentarios(VISTA);

test("los chips salen de los niveles ABIERTOS, no del historial de compras", () => {
  expect(CODIGO).toContain("p.niveles_abiertos");
  expect(CODIGO).toContain("niveles.map((n) =>");
});

test("la fila NO afirma por qué un nivel no tiene posición", () => {
  // Un nivel sin lote abierto puede ser uno vendido o uno que nunca se compró, y desde
  // aquí no se distinguen. Decir «vendido» es afirmar lo que no se sabe.
  expect(CODIGO).not.toContain("· vendido");
  expect(CODIGO).not.toContain("nivelCerrado");
});

test("una respuesta sin el campo nuevo sigue enseñando algo", () => {
  // Una respuesta cacheada de antes del despliegue no trae `niveles_abiertos`. Dejar la
  // fila sin etiquetas haría parecer que la posición no tiene niveles.
  expect(CODIGO).toContain("p.niveles_abiertos || p.niveles_comprados");
});

test("los dos sitios que pintaban los chips usan el mismo componente", () => {
  // Estaban duplicados y uno de los dos se habría quedado sin el arreglo.
  expect(CODIGO.match(/<NivelesDeLaFila p=\{p\} \/>/g) || []).toHaveLength(2);
  expect(CODIGO).not.toContain("p.niveles_comprados.map((n) => (");
});
