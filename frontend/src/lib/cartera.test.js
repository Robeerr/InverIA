import { estadoPosicion, etiquetaCalendario } from "./cartera";

// ORCL tal y como estaba: 119,27 $ con los cinco niveles de compra entre 132 y 180 $.
const orcl = { nivel1: 180.06, nivel2: 180, nivel3: 158.37, nivel4: 149, nivel5: 132.32 };

describe("estadoPosicion · la columna Estado de Cartera", () => {
  it("una tendencia bajista manda sobre todo lo demás", () => {
    expect(estadoPosicion(orcl, 119.27, "BAJISTA").txt).toBe("Compra vetada");
  });

  it("con el precio por debajo de TODOS los niveles de compra, el plan está agotado", () => {
    const e = estadoPosicion(orcl, 119.27, "INDEFINIDA");
    expect(e.txt).toBe("Bajo todos tus niveles");
    expect(e.ayuda).toMatch(/recalcula/i);
  });

  it("ya no dice «Sin datos» cuando la tendencia llega del servidor", () => {
    expect(estadoPosicion({ nivel1: 100 }, 130, "ALCISTA").txt).toBe("Tendencia intacta");
    expect(estadoPosicion({ nivel1: 100 }, 130, "INDEFINIDA").txt).toBe("Esperar");
  });

  it("sin tendencia conocida sigue diciendo «Sin datos»", () => {
    expect(estadoPosicion({ nivel1: 100 }, 130, null).txt).toBe("Sin datos");
  });

  it("avisa de un nivel cercano que aún no has comprado", () => {
    expect(estadoPosicion({ nivel1: 150, nivel3: 96.55 }, 97.11, "ALCISTA").txt).toBe("Nivel 3 cerca");
  });

  it("un nivel ya comprado (campanita apagada) no cuenta como «cerca»", () => {
    const e = estadoPosicion({ nivel3: 96.55, alert_nivel3: false }, 97.11, "ALCISTA");
    expect(e.txt).toBe("Tendencia intacta");
  });

  it("un precio justo debajo del nivel más bajo todavía es «cerca», no «agotado»", () => {
    expect(estadoPosicion({ nivel1: 100 }, 99.8, "ALCISTA").txt).toBe("Nivel 1 cerca");
  });

  it("entre −3 % y −0,5 % del nivel más bajo no afirma ni «cerca» ni «agotado»", () => {
    expect(estadoPosicion({ nivel1: 100 }, 98, "ALCISTA").txt).toBe("Tendencia intacta");
  });

  it("los niveles ya comprados también cuentan para saber si el plan está agotado", () => {
    expect(estadoPosicion({ nivel1: 150, nivel2: 130, alert_nivel2: false }, 110, "INDEFINIDA").txt)
      .toBe("Bajo todos tus niveles");
  });

  it("si la tabla no trae tendencia, usa la de la propia entrada", () => {
    expect(estadoPosicion({ nivel1: 100, tendencia: "bajista" }, 130).txt).toBe("Compra vetada");
  });

  it("sin niveles ni precio no inventa un estado", () => {
    expect(estadoPosicion({}, null, null).txt).toBe("Sin datos");
  });
});

describe("etiquetaCalendario · de dónde sale cada earnings", () => {
  const enCartera = new Set(["ORCL"]);

  it("solo dice «En cartera» si de verdad tienes acciones", () => {
    expect(etiquetaCalendario({ symbol: "ORCL" }, enCartera)).toBe("En cartera");
  });

  it("una acción de tu tabla sin acciones es una que vigilas, no tu cartera", () => {
    expect(etiquetaCalendario({ symbol: "NBIS", grupo: "ideas_javi" }, enCartera)).toBe("Vigilando");
  });

  it("respeta el grupo Cimientos", () => {
    expect(etiquetaCalendario({ symbol: "KO", grupo: "cimientos" }, enCartera)).toBe("Cimientos");
  });

  it("mientras no se sabe qué tienes, no afirma nada", () => {
    expect(etiquetaCalendario({ symbol: "NBIS" }, null)).toBeNull();
  });
});
