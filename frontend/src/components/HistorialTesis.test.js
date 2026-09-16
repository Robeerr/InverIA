/**
 * El historial de tesis no puede presentarse como un juicio ni como un acierto.
 *
 * Son las dos garantías que esta pantalla tiene que dar, y las dos son fáciles de perder
 * al escribir el texto:
 *
 *   `diff_de_campos` es MECÁNICO. El backend lo declara: «decir si un cambio fue un
 *   matiz o un giro sería interpretar, y eso todavía no se puede hacer con criterio».
 *
 *   `veces_observada` cuenta redacciones consecutivas con la misma huella. Dice que la
 *   tesis NO ha cambiado, no que fuera correcta. Acertar se responde con el precio de
 *   después.
 *
 * Se comprueba sobre el código fuente: no hay `@testing-library/react` en el proyecto y
 * no se añade una dependencia por iniciativa propia.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const VISTA = leer("components/HistorialTesis.jsx");
const PANEL = leer("components/TesisPanel.jsx");
const DASHBOARD = leer("pages/Dashboard.jsx");
const API = leer("lib/api.js");
/** Sin comentarios: los bloques que EXPLICAN qué no se hace citan las palabras que se
 *  buscan, y sobre el fichero entero daban falsos positivos en los dos sentidos. */
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
     .replace(/(^|[^:])\/\/.*$/gm, "$1");
const CODIGO = sinComentarios(VISTA);

test("el historial NO se pide al cargar la acción", () => {
  // El precio y la tesis de hoy son la pantalla; el histórico es un extra. Pedirlo en
  // cada carga del dashboard cargaría a todo el mundo el coste de una minoría.
  expect(CODIGO).not.toContain("useEffect");
  expect(CODIGO).toContain("const alternar");
  // Y una vez cargado no se vuelve a pedir al plegar y desplegar.
  expect(CODIGO).toContain("if (datos || cargando) return");
});

test("los campos que entran y salen se dicen MECÁNICOS, no un juicio", () => {
  expect(VISTA).toContain("no dice si el cambio fue un matiz o un giro");
  // Y no puede aparecer vocabulario de valoración sobre el cambio.
  for (const prohibido of ["giro importante", "mejora", "empeora", "más sólida"]) {
    expect(CODIGO).not.toContain(prohibido);
  }
});

test("`veces_observada` NO se presenta como un acierto", () => {
  // `patrones_registro` ya usa «acierto» para «la predicción se cumplió». Cruzar los dos
  // vocabularios es exactamente lo que el backend evitó al renombrar este campo.
  expect(VISTA).toContain("no que acertara");
  for (const prohibido of ["acierto", "confirmada", "veces_confirmada", "validada"]) {
    expect(CODIGO).not.toContain(prohibido);
  }
});

test("una lista vacía se explica, en vez de parecer un fallo", () => {
  // Sin versiones no es que algo se haya roto: es que esa acción no se ha abierto desde
  // que existe el registro.
  expect(VISTA).toContain("Todavía no hay ninguna versión guardada");
  // Y una sola versión tampoco es un hueco: es que la tesis no ha cambiado.
  expect(VISTA).toContain("no ha cambiado desde que se registró");
});

test("la primera versión no pinta los campos que «entran»", () => {
  // En la v1 entran TODOS, porque antes no había ninguno. Nueve «+» ahí no informan y
  // compiten con los cambios reales de las versiones de arriba.
  expect(CODIGO).toContain("v.version > 1 && <Cambios");
  expect(VISTA).toContain("Primera versión registrada");
  // Y la condición mira el NÚMERO de versión, no la posición: la lista está topada y su
  // última fila no tiene por qué ser la primera versión.
  expect(CODIGO).not.toContain("i === versiones.length - 1");
});

test("el tope del backend se dice cuando se alcanza", () => {
  // Callarlo haría parecer completa una lista truncada.
  expect(CODIGO).toContain("versiones.length >= datos.techo");
  expect(VISTA).toContain("Hay más antiguas guardadas");
});

test("un fallo del historial no acusa a la tesis de arriba", () => {
  // El histórico cuelga de un endpoint aparte: que falle no dice nada de la tesis que ya
  // está en pantalla, y sugerirlo mandaría a desconfiar del dato bueno.
  expect(VISTA).toContain("La tesis de arriba no\n              depende de esto");
});

test("está enganchado a la tesis y recibe el símbolo", () => {
  expect(PANEL).toContain("import HistorialTesis");
  expect(PANEL).toContain("<HistorialTesis symbol={symbol || tesis.symbol} />");
  expect(DASHBOARD).toContain("symbol={sym}");
  expect(API).toContain("/tesis/${symbol}/versiones");
});

test("las dos llamadas del historial SOLO LEEN", () => {
  const bloque = API.slice(API.indexOf("  tesis: {"), API.indexOf("  laboratorio: {"));
  expect(bloque).toContain("client.get");
  for (const escritura of ["client.post", "client.put", "client.delete"]) {
    expect(bloque).not.toContain(escritura);
  }
});
