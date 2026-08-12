/**
 * La confluencia en pantalla: mismo estado, misma pinta, en los dos sitios.
 *
 * Lo que se protege aquí no es el aspecto sino la relación con el backend: que la
 * pantalla no invente estados, no derive ninguno de los números sueltos y no recalcule
 * un umbral. Toda la clasificación vive en `confluencia.py`; si algún día alguien
 * añadiera aquí un `score > 65`, tendríamos dos verdades y la de la pantalla ganaría
 * sin que nadie se enterase.
 */
const fs = require("fs");
const path = require("path");

const { ESTILO } = require("./Confluencia");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const COMPONENTE = leer("components/Confluencia.jsx");
const BACKEND_ESTADOS = ["ACUERDO", "CHOQUE", "MIXTO", "NEUTRAL", "INSUFICIENTE", "SIN_FUENTES"];

describe("los seis estados del backend están contemplados", () => {
  test.each(BACKEND_ESTADOS)("%s tiene una entrada declarada", (estado) => {
    expect(estado in ESTILO).toBe(true);
  });

  test("y no hay ninguno de más inventado en la pantalla", () => {
    expect(Object.keys(ESTILO).sort()).toEqual([...BACKEND_ESTADOS].sort());
  });

  test("los cuatro con algo que contar tienen etiqueta y tono", () => {
    for (const estado of ["ACUERDO", "CHOQUE", "MIXTO", "INSUFICIENTE"]) {
      expect(ESTILO[estado].etiqueta).toBeTruthy();
      expect(ESTILO[estado].texto).toMatch(/^text-/);
    }
  });
});

describe("neutral y sin_fuentes no se pintan", () => {
  // El backend ya devuelve `texto: null` para los dos: significan «no se ha cruzado
  // nada» y «nadie ha hablado». Un chip gris repetido en cada tarjeta sería ruido, y el
  // ruido es lo que hace que se deje de mirar la señal cuando sí aparece.
  test.each(["NEUTRAL", "SIN_FUENTES"])("%s no tiene estilo", (estado) => {
    expect(ESTILO[estado]).toBeNull();
  });

  test("el componente sale antes de pintar nada", () => {
    expect(COMPONENTE).toContain("if (!estilo) return null;");
  });
});

describe("la pantalla no clasifica", () => {
  const codigo = sinComentarios(COMPONENTE);

  test("no hay ningún umbral escrito en el componente", () => {
    // Un `score >= 65` aquí sería una segunda clasificación, y ganaría la de la pantalla.
    expect(codigo).not.toMatch(/[><]=?\s*\d+/);
  });

  test("no lee los números sueltos para deducir el estado", () => {
    // `score_motor` ya no existe; se deja para que no pueda volver.
    for (const campo of ["score_motor", "positivos", "negativos", "n_fuentes"]) {
      expect(codigo).not.toContain(campo);
    }
    // El campo que lo sustituye se comprueba por ACCESO, no por palabra: «tendencia»
    // aparece legítimamente como texto visible («Sin tendencia», «tendencia ↔ fuentes»).
    // Prohibir la palabra sería leer la prosa en vez del código.
    expect(codigo).not.toContain("confluencia.tendencia");
  });

  test("el estado y la frase salen tal cual del backend", () => {
    expect(codigo).toContain("confluencia.estado");
    expect(codigo).toContain("confluencia.texto");
  });

  test("sin objeto de confluencia no revienta", () => {
    // Una respuesta anterior a este cambio, servida desde caché, no trae el campo.
    expect(codigo).toContain("confluencia ? ESTILO[confluencia.estado] : null");
  });
});

describe("el mismo estado se pinta igual en los dos sitios", () => {
  const FUENTES = leer("components/SourcesPanel.jsx");
  const RADAR = leer("pages/RadarView.jsx");

  test("los dos usan el mismo componente", () => {
    for (const src of [FUENTES, RADAR]) {
      expect(src).toContain("Confluencia");
      expect(src).toMatch(/import Confluencia from/);
    }
  });

  test("el panel de fuentes pinta la frase completa", () => {
    expect(FUENTES).toContain("<Confluencia confluencia={data.confluencia}");
    expect(FUENTES).not.toContain("compacto");
  });

  test("las tarjetas del radar pintan la etiqueta compacta", () => {
    expect(RADAR).toContain("compacto");
  });

  test("ninguno de los dos reimplementa el estado por su cuenta", () => {
    for (const src of [sinComentarios(FUENTES), sinComentarios(RADAR)]) {
      expect(src).not.toContain("ACUERDO");
      expect(src).not.toContain("CHOQUE");
    }
  });
});

describe("los campos que ya había siguen ahí", () => {
  const FUENTES = leer("components/SourcesPanel.jsx");
  const RADAR = leer("pages/RadarView.jsx");

  test("el panel de fuentes conserva menciones, positivos y negativos", () => {
    for (const campo of ["data.n", "data.positivos", "data.negativos", "data.menciones"]) {
      expect(FUENTES).toContain(campo);
    }
  });

  test("las tarjetas del radar conservan los datos de las fuentes", () => {
    for (const campo of ["row.n_fuentes", "row.fuentes", "row.angulos"]) {
      expect(RADAR).toContain(campo);
    }
  });

  test("el veredicto del motor ya NO tiene chip", () => {
    // Estos dos tests decían lo contrario, y se invierten a propósito.
    //
    // Cuando se añadió la confluencia, protegían que no se llevara por delante el chip
    // que ya estaba: la confluencia era la conclusión y las dos partes seguían visibles.
    //
    // Ya no. El veredicto era un score que mezclaba crecimiento, valoración, punto de
    // entrada, consenso y momentum, bucketeado en 65/45. Con el motor aportando solo
    // elegibilidad estructural, ese chip contaría una lógica distinta de la del chip de
    // confluencia que tiene al lado — dos historias incompatibles en la misma tarjeta.
    expect(RADAR).not.toContain("verdictStyle");
    expect(RADAR).not.toContain("inveria");
  });

  test("el panel de fuentes tampoco menciona el motor", () => {
    expect(FUENTES).not.toContain("inveria");
  });
});
