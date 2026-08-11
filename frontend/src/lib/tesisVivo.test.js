/**
 * Un solo precio vivo en pantalla.
 *
 * EL BUG QUE CONGELA ESTE FICHERO (AMD, producción)
 *
 *   cabecera: $468.96   (parche del WebSocket, tick a tick)
 *   tesis:    «AMD cotiza a 468.34 (-0.26% hoy)»   (dashboard cacheado)
 *
 * Dos precios de la misma acción a diez píxeles de distancia. La causa no era el
 * WebSocket: era que el precio venía COCIDO dentro de una frase que se cachea 15 min y
 * se sirve caducada hasta 30, mientras la cotización se refresca por su cuenta.
 */
import { titularVivo } from "./tesisVivo";

// Lo que manda el backend para AMD. `titular` es la frase ya escrita; `titular_plantilla`
// es la misma con los dos huecos de los valores que cambian tick a tick.
const AMD = {
  titular: "AMD cotiza a 468.34 (-0.26% hoy), por encima de su media de 200 sesiones.",
  titular_plantilla: "AMD cotiza a {p0} ({p1} hoy), por encima de su media de 200 sesiones.",
  titular_huecos: {
    p0: { campo_origen: "quote.price", formato: "precio", valor: 468.34 },
    p1: { campo_origen: "quote.change_percent", formato: "pct_signo", valor: -0.26 },
  },
};

const NVDA = {
  titular: "NVDA cotiza a 182.10 (+1.40% hoy), por encima de su media de 200 sesiones.",
  titular_plantilla: "NVDA cotiza a {p0} ({p1} hoy), por encima de su media de 200 sesiones.",
  titular_huecos: {
    p0: { campo_origen: "quote.price", formato: "precio", valor: 182.10 },
    p1: { campo_origen: "quote.change_percent", formato: "pct_signo", valor: 1.4 },
  },
};

describe("el tick vivo llega a la tesis", () => {
  test("dashboard a 468.34 + WebSocket a 468.96 → la tesis dice 468.96", () => {
    const t = titularVivo(AMD, { price: 468.96, change_percent: -0.13 });
    expect(t).toContain("468.96");
    expect(t).not.toContain("468.34");
  });

  test("la variación del día también se actualiza con el mismo quote", () => {
    const t = titularVivo(AMD, { price: 468.96, change_percent: -0.13 });
    expect(t).toContain("(-0.13% hoy)");
    expect(t).not.toContain("-0.26%");
  });

  test("un cambio de signo se escribe bien, no solo la cifra", () => {
    // El fallo que tendría una sustitución textual ingenua: cambiar «0.26» por «0.13»
    // dejaría «(-0.13% hoy)» aunque el día se hubiera puesto en positivo.
    const t = titularVivo(AMD, { price: 470.0, change_percent: 0.35 });
    expect(t).toContain("(+0.35% hoy)");
    expect(t).not.toContain("(-");
  });

  test("los miles se formatean igual que en el servidor", () => {
    const t = titularVivo(AMD, { price: 1234.5, change_percent: -0.26 });
    expect(t).toContain("1,234.50");
  });
});

describe("sin tick vivo se usa lo que trajo el servidor", () => {
  test("sin WebSocket → la tesis sigue diciendo 468.34", () => {
    expect(titularVivo(AMD, null)).toBe(AMD.titular);
    expect(titularVivo(AMD, {})).toBe(AMD.titular);
  });

  test("con un quote a medias, cada hueco cae por su cuenta", () => {
    // Llega precio pero no variación: se actualiza el precio y la variación se queda con
    // la del servidor. Nunca se inventa un valor ni se deja el hueco a la vista.
    const t = titularVivo(AMD, { price: 468.96 });
    expect(t).toContain("468.96");
    expect(t).toContain("(-0.26% hoy)");
    expect(t).not.toContain("{p1}");
  });

  test("una respuesta antigua sin plantilla se pinta tal cual", () => {
    const viejo = { titular: "AMD cotiza a 468.34." };
    expect(titularVivo(viejo, { price: 999 })).toBe("AMD cotiza a 468.34.");
  });

  test("sin tesis no revienta", () => {
    expect(titularVivo(null, { price: 1 })).toBe("");
    expect(titularVivo(undefined, null)).toBe("");
  });
});

describe("cambiar de ticker no arrastra el precio anterior", () => {
  test("la tesis de NVDA con el quote de NVDA no menciona nada de AMD", () => {
    const t = titularVivo(NVDA, { price: 183.55, change_percent: 2.1 });
    expect(t).toContain("NVDA");
    expect(t).toContain("183.55");
    expect(t).not.toContain("468.96");
    expect(t).not.toContain("468.34");
  });

  test("mientras carga el nuevo ticker no se pinta el precio del anterior", () => {
    // Al cambiar de acción el parche se vacía y `datos` aún no ha llegado: no hay tesis
    // que pintar. Lo que NUNCA puede pasar es que salga el titular de AMD con el precio
    // vivo de otra, y eso lo garantiza que ambos salen del mismo objeto por símbolo.
    expect(titularVivo(null, { price: 183.55 })).toBe("");
  });

  test("la función es pura: no guarda nada entre llamadas", () => {
    titularVivo(AMD, { price: 468.96, change_percent: -0.13 });
    expect(titularVivo(NVDA, null)).toBe(NVDA.titular);
  });
});

describe("el tick NO toca ningún otro dato de la tesis", () => {
  test("el juicio sobre la media de 200 sesiones se queda como lo calculó el servidor", () => {
    // Es un juicio derivado del precio, no el precio. Recalcularlo aquí sería mover
    // lógica de negocio al navegador.
    const t = titularVivo(AMD, { price: 1.0, change_percent: -99 });
    expect(t).toContain("por encima de su media de 200 sesiones");
  });

  test("solo se sustituyen los huecos declarados, y son dos", () => {
    expect(Object.keys(AMD.titular_huecos)).toHaveLength(2);
    const campos = Object.values(AMD.titular_huecos).map((h) => h.campo_origen);
    expect(campos.sort()).toEqual(["quote.change_percent", "quote.price"]);
  });

  test("un hueco de un campo que no es del quote vivo usa su valor del servidor", () => {
    const conAjeno = {
      titular: "X cotiza a 10.00 y su ATR es 2.00.",
      titular_plantilla: "X cotiza a {p0} y su ATR es {p9}.",
      titular_huecos: {
        p0: { campo_origen: "quote.price", formato: "precio", valor: 10 },
        p9: { campo_origen: "indicators.atr", formato: "precio", valor: 2 },
      },
    };
    const t = titularVivo(conAjeno, { price: 11, atr: 99 });
    expect(t).toBe("X cotiza a 11.00 y su ATR es 2.00.");
  });

  test("el resto de la frase se respeta carácter a carácter", () => {
    const t = titularVivo(AMD, { price: 468.34, change_percent: -0.26 });
    expect(t).toBe(AMD.titular);
  });
});
