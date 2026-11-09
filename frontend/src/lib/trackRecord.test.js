/**
 * Lo que el Track record le dice al usuario sobre el índice.
 *
 * El caso que protege este fichero es el de la pantalla real: motor −0,7 %, índice −2,5 %.
 * Se presentaba como «aporta valor sobre comprar SPY y esperar» porque solo se miraba la
 * diferencia con el índice. Perder menos que el mercado sigue siendo perder dinero.
 */
import { lecturaBenchmark, notaCostes } from "./trackRecord";

const base = { baten_spy_pct: 57.7, muestra: 208 };

describe("lecturaBenchmark", () => {
  test("perder menos que el índice no se presenta como aportar valor", () => {
    const l = lecturaBenchmark({ ...base, sistema_medio: -0.7, spy_medio: -2.5, alpha: 1.8,
      veredicto: "pierde_menos_que_indice" });
    expect(l.texto).toMatch(/pierde un 0.7%/);
    expect(l.texto).toMatch(/no es ganar dinero/);
    expect(l.texto).not.toMatch(/aporta valor/);
    expect(l.tono).toBe("aviso");
  });

  test("solo es verde si gana dinero Y bate al índice", () => {
    const l = lecturaBenchmark({ ...base, sistema_medio: 3, spy_medio: 1, alpha: 2,
      veredicto: "gana_y_bate" });
    expect(l.tono).toBe("sube");
    expect(l.texto).toMatch(/gana un \+3%/);
  });

  test("ganar menos que el índice se dice", () => {
    const l = lecturaBenchmark({ ...base, sistema_medio: 1, spy_medio: 3, alpha: -2,
      veredicto: "gana_sin_batir" });
    expect(l.texto).toMatch(/2 puntos menos/);
    expect(l.tono).toBe("aviso");
  });

  test("perder y además quedar por debajo del índice es rojo", () => {
    const l = lecturaBenchmark({ ...base, sistema_medio: -3, spy_medio: -1, alpha: -2,
      veredicto: "pierde_y_no_bate" });
    expect(l.tono).toBe("baja");
  });

  test("explica que la comparación es en la misma ventana y con costes", () => {
    const l = lecturaBenchmark({ ...base, sistema_medio: 3, spy_medio: 1, alpha: 2,
      veredicto: "gana_y_bate" });
    expect(l.metodo).toMatch(/misma ventana/);
    expect(l.metodo).toMatch(/208 señales/);
  });

  test("una respuesta antigua del servidor, sin veredicto, no rompe la página", () => {
    const l = lecturaBenchmark({ ...base, sistema_medio: -0.7, spy_medio: -2.5, alpha: 1.8 });
    expect(l.texto).toMatch(/no es ganar dinero/);
  });
});

describe("notaCostes", () => {
  test("dice qué se ha descontado y con qué supuesto", () => {
    const t = notaCostes({ pct_ida_vuelta: 0.9, importe_referencia_eur: 1000 }, 0);
    expect(t).toMatch(/0.9%/);
    expect(t).toMatch(/1000 €/);
    expect(t).not.toMatch(/duplicad/);
  });

  test("avisa de las señales duplicadas descartadas", () => {
    expect(notaCostes({ pct_ida_vuelta: 0.9, importe_referencia_eur: 1000 }, 3)).toMatch(/3 señales duplicadas/);
  });

  test("sin datos de costes no inventa nada", () => {
    expect(notaCostes(null, 0)).toBeNull();
  });
});
