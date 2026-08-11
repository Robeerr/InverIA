/**
 * El desglose del score en pantalla: bajo demanda y sin calcular nada.
 *
 * Lo que se protege aquí es lo que el componente NO hace. Que pinte bien unas barras se
 * ve mirando; que no pida el desglose hasta que alguien lo abre, y que no reconstruya el
 * score por su cuenta, no se ve nunca — y son las dos cosas que sostienen el diseño.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const SCORE = leer("components/Score.jsx");
const SCORE_COD = sinComentarios(SCORE);
const VISTA = leer("pages/OpportunitiesView.jsx");
const API = leer("lib/api.js");

describe("la petición ocurre solo al abrir, y una sola vez", () => {
  test("no hay ningún efecto que pida al montar", () => {
    // Con un `useEffect` que pidiera al montar, abrir Oportunidades dispararía una
    // petición por tarjeta: cientos, para un detalle que se abre dos o tres veces.
    expect(SCORE_COD).not.toContain("useEffect");
  });

  test("la llamada vive dentro del manejador del clic", () => {
    const manejador = SCORE_COD.slice(SCORE_COD.indexOf("const alternar"),
                                      SCORE_COD.indexOf("const d = datos"));
    expect(manejador).toContain("api.desgloseScore(symbol)");
  });

  test("no se repite si ya se tienen los datos", () => {
    expect(SCORE_COD).toContain('if (datos || estado === "cargando") return;');
  });

  test("cerrar no vuelve a pedir", () => {
    expect(SCORE_COD).toContain("if (abierto) { setAbierto(false); return; }");
  });
});

describe("no se calcula nada en el cliente", () => {
  test("no hay umbrales escritos en el componente", () => {
    // Un `puntos >= 65` aquí sería una segunda clasificación, y ganaría esta.
    const sinPorcentaje = SCORE_COD.replace(/Math\.(max|min)\(0, Math\.min\(100[^)]*\)\)/g, "");
    expect(sinPorcentaje).not.toMatch(/(puntos|score|bruto)\s*[><]=?\s*\d+/);
  });

  test("no reconstruye el score sumando componentes", () => {
    expect(SCORE_COD).not.toContain("reduce");
    expect(SCORE_COD).not.toContain("multiplicador *");
    expect(SCORE_COD).not.toMatch(/\*\s*d\.multiplicador/);
  });

  test("los puntos, máximos y motivos salen tal cual del backend", () => {
    for (const campo of ["c.puntos", "c.maximo", "c.etiqueta", "c.detalle",
                         "d.bruto", "d.multiplicador", "d.motivo_multiplicador",
                         "d.recortado"]) {
      expect(SCORE_COD).toContain(campo);
    }
  });

  test("la barra es proporción visual, no una regla de negocio", () => {
    // Lo único que se calcula: puntos/máximo para el ancho. No decide nada.
    expect(SCORE_COD).toContain("(puntos / maximo) * 100");
  });
});

describe("el guardián se enseña como multiplicador", () => {
  test("va aparte de los componentes", () => {
    expect(SCORE_COD).toContain("d.multiplicador !== 1");
    expect(SCORE).toContain("Guardián de tendencia");
  });

  test("con su motivo al lado", () => {
    expect(SCORE_COD).toContain("d.motivo_multiplicador");
  });

  test("y no se pinta cuando no ha actuado", () => {
    expect(SCORE_COD).toMatch(/d\.multiplicador != null && d\.multiplicador !== 1/);
  });
});

describe("los tres estados de carga están cubiertos", () => {
  test.each(["cargando", "vacio", "error"])("%s tiene su mensaje", (estado) => {
    expect(SCORE_COD).toContain(`estado === "${estado}"`);
  });

  test("un 404 no se trata como error", () => {
    // No es un fallo: el escaneo del screener aún no ha pasado por ese símbolo.
    expect(SCORE_COD).toContain('err?.response?.status === 404 ? "vacio" : "error"');
  });
});

describe("cerrado se ve exactamente como antes", () => {
  test("el chip original sigue en la vista, con su color y su texto", () => {
    expect(VISTA).toContain("{ps} pts");
    expect(VISTA).toContain("background: `${psColor}18`");
  });

  test("el componente solo lo envuelve", () => {
    expect(VISTA).toContain("<Score symbol={row.symbol}>");
    expect(SCORE_COD).toContain("{children}");
  });

  test("no se pierde ningún campo de la tarjeta", () => {
    for (const campo of ["row.potential_score", "row.valuation", "row.momentum",
                         "row.dist_52w_high", "row.pe_ratio"]) {
      expect(VISTA).toContain(campo);
    }
  });

  test("el clic no navega a la acción al abrir el desglose", () => {
    // La tarjeta entera navega al pulsarla: sin esto, abrir el detalle cambiaría de acción.
    expect(SCORE_COD).toContain("e.stopPropagation()");
  });
});

describe("se ve que se puede pulsar", () => {
  // El chip parecia una etiqueta mas: nada decia que hubiera algo debajo. Un desglose
  // que nadie descubre es lo mismo que no tenerlo.
  test("hay un rótulo que lo dice", () => {
    expect(SCORE).toContain("ver desglose");
  });

  test("y cambia cuando está abierto, para saber que se puede cerrar", () => {
    expect(SCORE_COD).toContain('abierto ? "ocultar');
  });

  test("el rótulo vive en el componente, que es quien sabe si está abierto", () => {
    expect(VISTA).not.toContain("ver desglose");
  });

  test("el cursor y el hover acompañan", () => {
    expect(SCORE_COD).toContain("cursor-pointer");
    expect(SCORE_COD).toContain("group-hover:text-marca");
  });

  test("el lector de pantalla también se entera", () => {
    expect(SCORE_COD).toContain("aria-expanded={abierto}");
    expect(SCORE_COD).toContain("aria-label");
  });
});

describe("la llamada a la API", () => {
  test("apunta al endpoint acordado", () => {
    expect(API).toContain("desgloseScore");
    expect(API).toContain("/opportunities/score/${symbol}");
  });

  test("y no se usa en ningún otro sitio todavía", () => {
    const usos = [leer("pages/OpportunitiesView.jsx"), leer("components/Score.jsx")]
      .filter((s) => s.includes("desgloseScore"));
    expect(usos).toHaveLength(1);
  });
});
