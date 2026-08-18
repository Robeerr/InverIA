/**
 * El formato tiene reglas de producto, no solo de presentación, y por eso conviene
 * fijarlas en tests: hasta ahora había nueve implementaciones distintas de
 * "formatear dinero" y cada una decidía por su cuenta qué hacer con un nulo.
 *
 * Lo que se protege aquí:
 *   · Un dato que falta se escribe "—", nunca "0". Un cero afirma que el valor es
 *     cero; una raya dice que no se sabe, que es distinto y a veces más importante.
 *   · El porcentaje lleva el signo SIEMPRE, también en positivo: si el sentido solo
 *     lo diera el color, quien no distingue rojo de verde se queda sin el dato.
 *   · Los precios van en formato en-US y el dinero propio en es-ES, a propósito.
 */
import {
  fmtPrice, fmtPct, fmtPctPlano, fmtNum, fmtEur, fmtDinero,
  fmtDate, fmtHace, fmtEnDias, distanciaPct, tono, aNumero, SIN_DATO,
} from "./format";

describe("datos ausentes", () => {
  const funciones = { fmtPrice, fmtPct, fmtPctPlano, fmtNum, fmtEur, fmtDate, fmtHace, fmtEnDias };
  test.each(Object.keys(funciones))("%s devuelve la raya y no un cero", (nombre) => {
    for (const vacio of [null, undefined, "", NaN]) {
      expect(funciones[nombre](vacio)).toBe(SIN_DATO);
    }
  });

  test("el cero de verdad sí se escribe como cero", () => {
    // El caso que se rompe si se comprueba con `if (!valor)`: 0 es un dato válido.
    expect(fmtPrice(0)).toBe("0.00");
    expect(fmtPct(0)).toBe("+0.00%");
    expect(fmtNum(0)).toBe("0");
  });
});

describe("porcentajes", () => {
  test("el signo va siempre, también en positivo", () => {
    expect(fmtPct(2.4)).toBe("+2.40%");
    expect(fmtPct(-1.1)).toBe("-1.10%");
  });

  test("fmtPctPlano no pone signo: es una magnitud sin dirección", () => {
    expect(fmtPctPlano(1.84)).toBe("1.8%");
  });
});

describe("dinero", () => {
  test("los precios van en formato de mercado (en-US)", () => {
    expect(fmtPrice(1234.5)).toBe("1,234.50");
  });

  test("los euros van en formato español", () => {
    // El espacio antes del € es un NBSP en es-ES, así que se compara sin espacios.
    // Ojo: en español las cifras de cuatro dígitos NO llevan separador de millares,
    // y a partir de cinco sí. Se fijan los dos casos para que quede documentado.
    expect(fmtEur(1234.5).replace(/\s/g, "")).toBe("1234,50€");
    expect(fmtEur(12345.5).replace(/\s/g, "")).toBe("12.345,50€");
  });

  test("una divisa desconocida no se disfraza de euros", () => {
    // Etiquetar dólares como euros no es un fallo de estilo: es un error de dato.
    // Un código ISO válido que el navegador no conoce se escribe tal cual.
    // Normalizado: Intl separa con espacio duro (U+00A0), no con un espacio normal.
    expect(fmtDinero(1234.5, "XYZ").replace(/\s/g, " ")).toBe("1234,50 XYZ");
  });

  test("un código de divisa malformado cae a número plano, no revienta", () => {
    expect(fmtDinero(1234.5, "NO-ES-UN-CODIGO")).toBe("1,234.50");
  });
});

describe("números grandes", () => {
  test.each([
    [24_300_000, "24.30M"],
    [1_200_000_000, "1.20B"],
    [3_400_000_000_000, "3.40T"],
    [4500, "4.50K"],
    [-2_500_000, "-2.50M"],
  ])("%s → %s", (valor, esperado) => {
    expect(fmtNum(valor)).toBe(esperado);
  });
});

describe("tiempo", () => {
  const ahora = new Date("2026-08-10T15:00:00Z").getTime();

  test.each([
    [30_000, "hace un momento"],
    [30 * 60_000, "hace 30 min"],
    [3 * 3600_000, "hace 3 horas"],
    [2 * 86400_000, "hace 2 días"],
  ])("hace %sms → %s", (delta, esperado) => {
    expect(fmtHace(ahora - delta, ahora)).toBe(esperado);
  });

  test("el singular no se escribe en plural", () => {
    expect(fmtHace(ahora - 3600_000, ahora)).toBe("hace 1 hora");
    expect(fmtHace(ahora - 86400_000, ahora)).toBe("hace 1 día");
  });

  test("los días que faltan se dicen en lenguaje normal", () => {
    expect(fmtEnDias(ahora + 1000, ahora)).toBe("hoy");
    expect(fmtEnDias(ahora + 86400_000, ahora)).toBe("mañana");
    expect(fmtEnDias(ahora + 2 * 86400_000, ahora)).toBe("en 2 días");
  });

  test("una fecha inválida no se cuela como 'Invalid Date'", () => {
    expect(fmtDate("no es una fecha")).toBe(SIN_DATO);
  });
});

describe("distancia a un nivel", () => {
  test("es la unidad de urgencia de la app", () => {
    expect(distanciaPct(182, 178)).toBeCloseTo(2.247, 2);
    expect(distanciaPct(178, 182)).toBeCloseTo(-2.198, 2);
  });

  test("sin referencia utilizable devuelve null, no cero", () => {
    // Devolver 0 diría "estás justo en el nivel", que es lo contrario de "no se sabe".
    expect(distanciaPct(182, 0)).toBeNull();
    expect(distanciaPct(182, null)).toBeNull();
    expect(distanciaPct(null, 178)).toBeNull();
  });
});

describe("tono por signo", () => {
  test.each([[2.4, "sube"], [-1.1, "baja"], [0, "neutro"], [null, "neutro"]])(
    "%s → %s", (valor, esperado) => expect(tono(valor)).toBe(esperado)
  );
});

// El bug: en el móvil, el teclado numérico de un teléfono en español ofrece COMA. Con
// `<input type="number">` el navegador la descartaba y el valor llegaba vacío; con
// `Number("560,67")` salía NaN y la pantalla contestaba "el precio debe ser mayor que
// cero". Registrar una compra a 560,67 $ desde el móvil era imposible.
describe("números escritos a mano", () => {
  test("la coma decimal española", () => {
    expect(aNumero("560,67")).toBe(560.67);
    expect(aNumero("0,5")).toBe(0.5);
  });

  test("el punto decimal sigue funcionando", () => {
    expect(aNumero("560.67")).toBe(560.67);
    expect(aNumero("1234")).toBe(1234);
    expect(aNumero(560.67)).toBe(560.67);
  });

  test("con los dos separadores manda el ÚLTIMO", () => {
    // Es lo que se espera al pegar una cifra copiada del bróker, en cualquiera de los
    // dos formatos.
    expect(aNumero("1.234,56")).toBe(1234.56);
    expect(aNumero("1,234.56")).toBe(1234.56);
    expect(aNumero("1.234.567,89")).toBe(1234567.89);
  });

  test("los negativos y los espacios sobrantes", () => {
    expect(aNumero("-3,5")).toBe(-3.5);
    expect(aNumero("  12,25  ")).toBe(12.25);
  });

  test("sin número devuelve null y NUNCA NaN", () => {
    // Quien llama distingue "vacío" de "cero" sin acordarse de comprobar isNaN.
    for (const vacio of ["", "   ", null, undefined, "abc", NaN]) {
      expect(aNumero(vacio)).toBeNull();
    }
  });

  test("el cero es un valor, no un hueco", () => {
    expect(aNumero("0")).toBe(0);
    expect(aNumero("0,00")).toBe(0);
  });
});
