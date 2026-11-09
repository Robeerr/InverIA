/**
 * El Total de «Lo que tienes abierto» tiene que salir de las MISMAS cifras que sus filas.
 *
 * Lo que pasaba: con «Como en DEGIRO» puesto, cada fila enseñaba el invertido por media
 * ponderada, pero el Total ponía el invertido por FIFO (23.294,36 €) junto a la ganancia
 * ponderada (−5337,26 €). Las filas sumaban 23.845,27 €, y el Total no salía de restar
 * valor menos invertido. Este fichero fija que el Total es la suma de lo que se ve.
 */
import { cifrasResumen, datosPosicion, perdidasSegunMetodo, totalesAbiertas } from "./operaciones";

// Dos posiciones con las cifras de los dos métodos, como las manda /ventas/resumen.
const AAOI = {
  symbol: "AAOI", acciones: 12, precio_medio: 114.06, precio_medio_ponderado: 135.22,
  coste_eur: 1222.4, pnl_eur: -685.15, valor_eur: 537.25,
  ponderada: { coste_eur: 1380.43, pnl_eur: -843.18 },
};
const FN = {
  symbol: "FN", acciones: 12, precio_medio: 490.3, precio_medio_ponderado: 515.77,
  coste_eur: 5110.0, pnl_eur: -1604.08, valor_eur: 3505.92,
  ponderada: { coste_eur: 5376.8, pnl_eur: -1870.88 },
};

describe("totalesAbiertas", () => {
  test("como en DEGIRO: invertido y ganancia salen los dos de la media ponderada", () => {
    const t = totalesAbiertas([AAOI, FN], true);
    expect(t.invertido).toBeCloseTo(6757.23, 2);
    expect(t.ganancia).toBeCloseTo(-2714.06, 2);
  });

  test("con el método de gestión: los dos salen del método de gestión", () => {
    const t = totalesAbiertas([AAOI, FN], false);
    expect(t.invertido).toBeCloseTo(6332.4, 2);
    expect(t.ganancia).toBeCloseTo(-2289.23, 2);
  });

  test("valor menos invertido da la ganancia, con el interruptor puesto o quitado", () => {
    for (const comoBroker of [true, false]) {
      const t = totalesAbiertas([AAOI, FN], comoBroker);
      expect(t.valor - t.invertido).toBeCloseTo(t.ganancia, 2);
    }
  });

  test("el Total es la suma de las filas que se ven", () => {
    const filas = [AAOI, FN].map((p) => datosPosicion(p, true));
    const t = totalesAbiertas([AAOI, FN], true);
    expect(t.invertido).toBeCloseTo(filas.reduce((s, f) => s + f.invertido, 0), 2);
  });

  test("una posición sin valorar no entra a medias en el total", () => {
    const sinPrecio = { ...FN, symbol: "XYZ", valor_eur: null, pnl_eur: null,
      ponderada: { coste_eur: 1000, pnl_eur: null } };
    const t = totalesAbiertas([AAOI, sinPrecio], true);
    expect(t.invertido).toBeCloseTo(1380.43, 2);
    expect(t.sinValorar).toBe(1);
  });

  test("sin posiciones no hay porcentaje que inventar", () => {
    const t = totalesAbiertas([], true);
    expect(t.invertido).toBe(0);
    expect(t.pct).toBeNull();
  });
});

/* La cabecera de Cartera leía siempre el método de gestión (23.294,36 € invertidos,
   −4786,35 € latentes) mientras Hoy y Operaciones, con «Como en DEGIRO» puesto, enseñaban
   la media ponderada. Las tres pantallas tienen que seguir el mismo interruptor. */
const RESUMEN = {
  invertido_eur: 23294.36, latente_eur: -4786.35, realizado_eur: 6367.15,
  invertido_ponderada_eur: 23845.27, latente_ponderada_eur: -5337.26,
  realizado_ponderada_eur: 6918.07, metodo_gestion: "fifo",
};

describe("cifrasResumen", () => {
  test("como en DEGIRO: las tres cifras por media ponderada", () => {
    expect(cifrasResumen(RESUMEN, true)).toEqual({
      invertido: 23845.27, latente: -5337.26, realizado: 6918.07,
      metodo: "media ponderada · como DEGIRO" });
  });

  test("sin el interruptor: las tres por el método de gestión", () => {
    expect(cifrasResumen(RESUMEN, false)).toEqual({
      invertido: 23294.36, latente: -4786.35, realizado: 6367.15, metodo: "por FIFO" });
  });

  test("si falta alguna ponderada no mezcla métodos: usa las tres de gestión", () => {
    const c = cifrasResumen({ ...RESUMEN, realizado_ponderada_eur: null }, true);
    expect(c.invertido).toBe(23294.36);
    expect(c.metodo).toBe("por FIFO");
  });

  test("sin resumen todavía, todo vacío", () => {
    expect(cifrasResumen(undefined, true).invertido).toBeNull();
  });
});

describe("perdidasSegunMetodo", () => {
  const AT = [
    { symbol: "AAOI", pct: -56.05, pnl_eur: -661.86, ponderada: { pct: -61.08, pnl_eur: -843.18 } },
    { symbol: "X", pct: -5, pnl_eur: -50, ponderada: { pct: -9, pnl_eur: -90 } },
  ];

  test("como en DEGIRO: importe y % ponderados", () => {
    const f = perdidasSegunMetodo(AT, true);
    expect(f.map((p) => p.symbol)).toEqual(["AAOI", "X"]);
    expect(f[0].pnl_eur).toBe(-843.18);
    expect(f[0].pct).toBe(-61.08);
  });

  test("con el método de gestión solo quedan las que pierden por ese método", () => {
    const f = perdidasSegunMetodo(AT, false);
    expect(f.map((p) => p.symbol)).toEqual(["AAOI"]);
    expect(f[0].pnl_eur).toBe(-661.86);
  });

  test("como mucho cuatro, de peor a menos mala", () => {
    const muchas = [-10, -50, -20, -30, -40].map((v, i) => ({ symbol: `S${i}`, pct: v, pnl_eur: v }));
    expect(perdidasSegunMetodo(muchas, false).map((p) => p.pct)).toEqual([-50, -40, -30, -20]);
  });
});
