/**
 * Un nivel que ya vendiste no puede pintarse igual que uno que tienes.
 *
 * `niveles_comprados` recorre el historial entero de compras; `niveles_abiertos`, solo
 * los lotes vivos. La fila enseñaba únicamente la primera lista, y en el sitio donde el
 * ojo busca «qué tengo»: una posición con tres lotes abiertos enseñaba cuatro etiquetas
 * y no había forma de saber cuál sobraba.
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

test("las dos listas se usan, no solo la de compras", () => {
  expect(CODIGO).toContain("p.niveles_abiertos");
  expect(CODIGO).toContain("abiertos.has(n)");
});

test("el nivel vendido se APAGA, no se esconde", () => {
  // Que entraras ahí y ya no estés es información: quitarlo obligaría a irse al
  // histórico de ventas para saberlo.
  expect(CODIGO).toContain('tono="nivelCerrado"');
  expect(CODIGO).toContain("const comprados = p.niveles_comprados");
  // Se recorre la lista COMPLETA de comprados: si se recorriera la de abiertos, el
  // nivel vendido desaparecería en vez de apagarse.
  expect(CODIGO).toContain("comprados.map((n) =>");
});

test("«vendido» se lee sin pasar el ratón por encima", () => {
  // En el móvil no hay ratón, y este mismo fichero ya documenta que ahí un texto que
  // solo vive en `title=` es sencillamente inalcanzable.
  expect(CODIGO).toContain("· vendido");
});

test("una respuesta sin el campo nuevo NO apaga nada", () => {
  // Una respuesta cacheada de antes del despliegue no trae `niveles_abiertos`. Apagar
  // por defecto diría que has vendido cosas que no has vendido.
  expect(CODIGO).toContain("new Set(p.niveles_abiertos || comprados)");
});

test("los dos sitios que pintaban los chips usan el mismo componente", () => {
  // Estaban duplicados y uno de los dos se habría quedado sin el arreglo.
  expect(CODIGO.match(/<NivelesDeLaFila p=\{p\} \/>/g) || []).toHaveLength(2);
  expect(CODIGO).not.toContain('p.niveles_comprados.map((n) => (');
});
