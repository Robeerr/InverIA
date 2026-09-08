import { saludoDeLaHora, nombreDe, desgloseDe } from "./portada";

/* La portada pasó de abrir con un titular que INFORMABA —«Dos acciones han llegado a tu
 * nivel»— a abrir con un saludo, que no informa de nada. Ese dato no se puede perder por
 * el camino: baja al subtítulo de la sección, junto a las tarjetas que describe. Estas
 * pruebas cubren la pieza que lo sostiene. */

describe("el saludo", () => {
  const a = (h) => new Date(2026, 7, 31, h, 0, 0);
  test("cambia con la hora del día", () => {
    expect(saludoDeLaHora(a(3))).toBe("Buenas noches");
    expect(saludoDeLaHora(a(9))).toBe("Buenos días");
    expect(saludoDeLaHora(a(17))).toBe("Buenas tardes");
    expect(saludoDeLaHora(a(23))).toBe("Buenas noches");
  });

  test("no lleva nombre", () => {
    // El frontend no conoce al usuario, y "admin" no es el nombre de nadie.
    for (const h of [0, 8, 15, 22]) expect(saludoDeLaHora(a(h))).not.toMatch(/,/);
  });
});

describe("el desglose de lo que hay hoy", () => {
  test("nombra cada tipo y concuerda en singular y plural", () => {
    expect(desgloseDe({ alerta: 2, nivel: 1 })).toEqual(["2 alertas saltadas", "1 nivel cerca"]);
    expect(desgloseDe({ alerta: 1 })).toEqual(["1 alerta saltada"]);
  });

  test("ordena de más a menos, que es como se lee", () => {
    expect(desgloseDe({ nivel: 1, alerta: 3 })).toEqual(["3 alertas saltadas", "1 nivel cerca"]);
  });

  test("no cuenta lo que está a cero ni lo que no sabe nombrar", () => {
    expect(desgloseDe({ alerta: 0, nivel: 2, inventado: 5 })).toEqual(["2 niveles cerca"]);
  });

  test("sin conteo devuelve una lista vacía, no revienta", () => {
    expect(desgloseDe(undefined)).toEqual([]);
    expect(desgloseDe({})).toEqual([]);
  });
});

describe("el nombre del saludo", () => {
  // El saludo iba SIN nombre porque el frontend solo conoce el usuario con el que
  // entras, y «admin» saludado como una persona queda peor que no saludar. Eso vale
  // para los identificadores genéricos, no para todos.

  test("un nombre normal se usa y se capitaliza", () => {
    expect(nombreDe("javier")).toBe("Javier");
    expect(nombreDe("ROBER")).toBe("Rober");
  });

  test("se queda con el nombre de pila", () => {
    expect(nombreDe("javier.moreno")).toBe("Javier");
    expect(nombreDe("rober_garcia")).toBe("Rober");
  });

  test("los identificadores genéricos NO son nombres", () => {
    for (const g of ["admin", "root", "user", "usuario", "demo", "test", "Admin"]) {
      expect(nombreDe(g)).toBeNull();
    }
  });

  test("ante la duda, no se saluda por el nombre", () => {
    // Equivocarse saludando es peor que no saludar: un correo, algo con cifras o una
    // cadena rarísima no son nombres de pila por mucho que lo parezcan.
    for (const raro of ["dev.rober07@gmail.com", "u123", "x", null, undefined, 42,
                        "", "   ", "unacadenaabsurdamentelargaquenoesunnombre"]) {
      expect(nombreDe(raro)).toBeNull();
    }
  });
});
