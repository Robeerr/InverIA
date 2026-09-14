/**
 * El cajón no puede atribuir un dato a la fuente equivocada.
 *
 * QUÉ PASÓ
 *
 * El aviso «Fecha del calendario de Finnhub. Puede ser una estimación suya y no un
 * anuncio de la empresa» se enseñaba cuando `suceso !== "publicado"`. Un 8-K tiene
 * `suceso: "8-K"`, así que la condición se cumplía y el aviso salía en TODOS los filings
 * de la SEC desde que existe Earnings.
 *
 * Le decía al usuario que la fecha de un documento registrado ante la SEC era una
 * estimación de un proveedor de datos. Es lo contrario de lo que es, y sobre la fuente
 * más fiable que tiene el sistema — la que se eligió precisamente por ser un hecho
 * registrado y no una opinión.
 *
 * Un aviso que existe para separar un hecho de una previsión, convirtiendo un hecho en
 * una previsión.
 *
 * ESTOS TESTS LEEN EL CÓDIGO FUENTE
 *
 * No hay `@testing-library/react` en el proyecto y no se añade una dependencia por
 * iniciativa propia. Lo que se protege es una CONDICIÓN, y se ve en el texto.
 */
const fs = require("fs");
const path = require("path");

const CAJON = fs.readFileSync(
  path.join(__dirname, "IntelligenceDrawer.jsx"), "utf8");

test("el aviso de Finnhub se condiciona a la FUENTE, no al suceso", () => {
  const i = CAJON.indexOf("Fecha del calendario de Finnhub");
  expect(i).toBeGreaterThan(-1);
  // La condición que gobierna el bloque va justo antes del texto.
  const antes = CAJON.slice(Math.max(0, i - 400), i);
  expect(antes).toContain('evento.fuente === "earnings"');
});

test("mirar solo el suceso NO basta, y queda dicho por qué", () => {
  // `suceso !== "publicado"` se cumple para un 8-K y para un Form 4.
  expect(CAJON).toContain("un 8-K tiene `suceso: \"8-K\"`");
});

test("el cajón sigue enseñando de qué fuente viene cada evento", () => {
  expect(CAJON).toContain("{evento.fuente}");
});

test("el enlace al documento original sigue ahí", () => {
  // Es lo que hace comprobable todo lo demás: un evento del que no puedes ir a leer la
  // fuente es un evento en el que hay que creer.
  expect(CAJON).toContain("evento.url");
  expect(CAJON).toContain('target="_blank"');
});
