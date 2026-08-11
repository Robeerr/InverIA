/**
 * «Tu posición» solo existe si hay dinero dentro.
 *
 * La distinción que protege este fichero: tener una acción en la tabla de seguimiento
 * con unos niveles apuntados NO es tener una posición. Si el bloque se pintara en ese
 * caso, diría que estás dentro cuando solo estás mirando — y sobre eso se toman
 * decisiones distintas.
 */
import { posicionDe, entradaDe } from "./posicion";

const CARTERA = [
  { symbol: "AAPL", acciones: 10, compra: 200, nivel1: 190, nivel2: 180, divisa: "USD", notes: "  " },
  { symbol: "NVDA", nivel1: 100, nivel2: 90 },                 // vigilada, sin comprar
  { symbol: "MSFT", acciones: 0, compra: 300 },                // vendida entera
  { symbol: "TSLA", acciones: 5, compra: null },               // sin precio de compra
  { symbol: "AMD",  acciones: 4, compra: 100, last_price: 120 },
];

describe("cuándo NO hay posición", () => {
  test("el ticker no está en la cartera", () => {
    expect(posicionDe(CARTERA, "GOOG", 100)).toBeNull();
  });

  test("está en la tabla pero sin acciones compradas", () => {
    // El caso que importa: NVDA tiene niveles apuntados y sigue sin ser una posición.
    expect(posicionDe(CARTERA, "NVDA", 100)).toBeNull();
  });

  test("tuvo posición y la vendió entera", () => {
    expect(posicionDe(CARTERA, "MSFT", 300)).toBeNull();
  });

  test("hay acciones pero no precio de compra: no se puede calcular nada", () => {
    expect(posicionDe(CARTERA, "TSLA", 250)).toBeNull();
  });

  test.each([[null], [undefined], [[]], ["no es una lista"]])(
    "cartera no utilizable (%p) no revienta", (cartera) => {
      expect(posicionDe(cartera, "AAPL", 100)).toBeNull();
    });

  test("sin símbolo tampoco", () => {
    expect(posicionDe(CARTERA, "", 100)).toBeNull();
    expect(posicionDe(CARTERA, null, 100)).toBeNull();
  });
});

describe("cuándo sí la hay", () => {
  test("calcula invertido, valor y latente con el precio vivo", () => {
    const p = posicionDe(CARTERA, "AAPL", 220);
    expect(p).not.toBeNull();
    expect(p.acciones).toBe(10);
    expect(p.compra).toBe(200);
    expect(p.invertido).toBe(2000);
    expect(p.valor).toBe(2200);
    expect(p.plAbs).toBe(200);
    expect(p.plPct).toBeCloseTo(10, 6);
  });

  test("una pérdida sale en negativo, no en valor absoluto", () => {
    const p = posicionDe(CARTERA, "AAPL", 180);
    expect(p.plAbs).toBe(-200);
    expect(p.plPct).toBeCloseTo(-10, 6);
  });

  test("el símbolo se compara en mayúsculas", () => {
    expect(posicionDe(CARTERA, "aapl", 220)).not.toBeNull();
  });

  test("sin precio vivo cae a last_price, que escribe el worker", () => {
    const p = posicionDe(CARTERA, "AMD", null);
    expect(p.precio).toBe(120);
    expect(p.plAbs).toBe(80);
  });

  test("sin precio de ninguna fuente no se inventa uno: valor y latente quedan a null", () => {
    const p = posicionDe([{ symbol: "X", acciones: 2, compra: 50 }], "X", null);
    expect(p.invertido).toBe(100);
    expect(p.precio).toBeNull();
    expect(p.valor).toBeNull();
    expect(p.plAbs).toBeNull();
    expect(p.plPct).toBeNull();
  });

  test("recoge los niveles apuntados y descarta los vacíos", () => {
    const p = posicionDe(CARTERA, "AAPL", 220);
    expect(p.niveles.map((n) => n.precio)).toEqual([190, 180]);
  });

  test("una nota en blanco no cuenta como nota", () => {
    expect(posicionDe(CARTERA, "AAPL", 220).notas).toBeNull();
  });
});

describe("entradaDe", () => {
  test("encuentra la fila aunque el símbolo venga en minúsculas", () => {
    expect(entradaDe(CARTERA, "nvda").symbol).toBe("NVDA");
  });
  test("devuelve null si no está", () => {
    expect(entradaDe(CARTERA, "ZZZZ")).toBeNull();
  });
});
