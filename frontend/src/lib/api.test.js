/**
 * El secreto de ingesta no puede volver a la URL.
 *
 * Iba como query param (`?token=…`), así que acababa en el historial del navegador,
 * en el log de cualquier proxy y en la cabecera Referer de lo que se cargara después.
 * INBOUND_SECRET no caduca ni se rota solo, así que ese rastro es permanente.
 *
 * Se comprueba sobre el código porque lo que se protege es la FORMA de la llamada, y
 * un test de red no distinguiría un secreto en la URL de uno en la cabecera.
 */
const fs = require("fs");
const path = require("path");

const FUENTE = fs.readFileSync(path.join(__dirname, "api.js"), "utf8");

// El bloque `telegram: { ... }` completo.
const BLOQUE_TELEGRAM = FUENTE.slice(
  FUENTE.indexOf("telegram: {"),
  FUENTE.indexOf("mantenimiento: {")
);

describe("secreto de ingesta", () => {
  test("las llamadas de Telegram lo mandan por cabecera", () => {
    const conCabecera = BLOQUE_TELEGRAM.match(/cabeceraIngesta\(token\)/g) || [];
    expect(conCabecera).toHaveLength(5);
  });

  test("ninguna llamada de Telegram lo manda por la URL", () => {
    expect(BLOQUE_TELEGRAM).not.toMatch(/params:\s*\{\s*token\s*\}/);
    expect(BLOQUE_TELEGRAM).not.toMatch(/token=/);
  });

  test("sin token no se manda una cabecera vacía", () => {
    // Mandar `X-Inbound-Token: undefined` haría que el servidor comparase contra la
    // cadena "undefined" en vez de responder 401 por credencial ausente.
    const helper = FUENTE.match(/const cabeceraIngesta = .*/)[0];
    expect(helper).toContain("token ?");
  });
});

describe("mantenimiento del Cerebro", () => {
  const BLOQUE = FUENTE.slice(FUENTE.indexOf("mantenimiento: {"));

  test("no llevan ningún secreto: van con la sesión normal", () => {
    expect(BLOQUE).not.toMatch(/token/i);
    expect(BLOQUE).not.toMatch(/X-Inbound-Token/);
  });

  test("están las siete acciones migradas", () => {
    for (const ruta of ["knowledge", "debug", "backfill-knowledge", "dedupe-knowledge",
                        "dedupe-knowledge-llm", "fix-encoding", "news/ingest"]) {
      expect(BLOQUE).toContain(ruta);
    }
  });
});
