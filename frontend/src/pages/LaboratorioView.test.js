/**
 * El laboratorio no puede presentar lo leído como si fuera medido.
 *
 * Es la única garantía que esta pantalla tiene que dar, y es fácil de perder sin darse
 * cuenta: basta con juntar en una tabla los umbrales de un libro y los que hemos medido,
 * y a partir de ahí los dos se leen con el mismo respaldo.
 *
 * ESTOS TESTS LEEN EL CÓDIGO FUENTE
 *
 * Mismo motivo que los del radar: no hay `@testing-library/react` en el proyecto y no se
 * añade una dependencia por iniciativa propia.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const VISTA = leer("pages/LaboratorioView.jsx");
/** Sin comentarios: el bloque que EXPLICA por qué no hay puntuación global contiene el
 *  término, y buscarlo sobre el fichero entero daba un falso positivo. */
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
     .replace(/(^|[^:])\/\/.*$/gm, "$1");
const CODIGO = sinComentarios(VISTA);
const API = leer("lib/api.js");
const RAIL = leer("components/Rail.jsx");
const APP = leer("App.js");

test("la pantalla separa lo leído, lo que se cree y lo medido", () => {
  expect(VISTA).toContain("Lo que creemos y no hemos medido");
  expect(VISTA).toContain("Lo que hemos medido");
  expect(VISTA).toContain("Conceptos leídos");
});

test("los cuatro finales de un experimento tienen su etiqueta", () => {
  for (const estado of ["VALIDATED", "REJECTED", "INSUFFICIENT_DATA", "INCONCLUSIVE"]) {
    expect(VISTA).toContain(estado);
  }
});

test("NO existe ninguna puntuación global del laboratorio", () => {
  // Un «InverIA IQ» sumaría conceptos leídos, hipótesis abiertas y experimentos hechos,
  // que no son la misma magnitud. Es el error que `separacion.py` documenta.
  for (const prohibido of ["InverIA IQ", "inveriaIq", "puntuacionGlobal", "scoreTotal"]) {
    expect(CODIGO).not.toContain(prohibido);
  }
  // Y la explicación SÍ tiene que seguir en el fichero, para que nadie lo añada creyendo
  // que simplemente se olvidó.
  expect(VISTA).toContain("InverIA IQ");
});

test("el experimento enseña su método y sus sesgos, no solo el resultado", () => {
  expect(VISTA).toContain("Método y sesgos");
  expect(VISTA).toContain("e.controles");
});

test("cuando no hay experimentos se dice, en vez de enseñar una tabla vacía", () => {
  expect(VISTA).toContain("Todavía no se ha ejecutado ningún experimento");
});

test("solo los experimentos ESCRIBEN; el resto de la pantalla lee", () => {
  const lab = API.slice(API.indexOf("laboratorio: {"), API.indexOf("intelligence: {"));
  // Dos POST —el experimento y su diagnóstico— y dos GET de consulta. El invariante no
  // es cuántos hay, sino que consultar el laboratorio nunca escriba.
  expect((lab.match(/client\.get/g) || []).length).toBe(2);
  expect(lab).toContain("distanciaAlMaximo");
  expect(lab).toContain("distribucion");
});

test("el diagnóstico enseña la MEDIANA, que es lo que lo distingue del primero", () => {
  // El experimento 1 solo daba medias, y una media la mueve un solo acierto enorme.
  expect(VISTA).toContain("Mediana");
  expect(VISTA).toContain("t.mediana");
});

test("se enseña TODO lo que el diagnóstico mide, no solo la mediana", () => {
  // La amplitud y el peso del 10% mejor se medían desde el principio y no se veían.
  // Un confundido que se calcula y no se pinta es un confundido que nadie mira.
  expect(VISTA).toContain("amplitud_intercuartil");
  expect(VISTA).toContain("peso_del_10pct_mejor");
  expect(VISTA).toContain("por_año");
});

test("el aguante de las zonas tiene su propia tabla, no la de tramos", () => {
  // Son magnitudes distintas: una tasa de aguante no es un retorno medio, y meterlas en
  // la misma tabla habría obligado a que una de las dos se leyera mal.
  expect(VISTA).toContain("r.cubos");
  expect(VISTA).toContain("Toques resueltos");
  expect(VISTA).toContain("aguante_limpio_pct");
});

test("el aguante enseña su suelo de ruido junto al resultado", () => {
  // Una separación sin el suelo al lado no se puede leer: 7,91 pp parecían mucho hasta
  // saber que el azar llega a 8,26.
  expect(VISTA).toContain("suelo de ruido");
  expect(VISTA).toContain("azar_p95_pp");
});

test("el desglose por metodología va marcado como DESCRIPTIVO", () => {
  // `backtest` lo calculaba y nadie lo guardaba. Enseñarlo sin el aviso invitaría a
  // elegir «la fuente buena» mirando la tabla, que es escoger al ganador viendo el
  // marcador.
  expect(VISTA).toContain("descriptivo, NO probado");
  expect(VISTA).toContain("mirando el marcador");
  expect(VISTA).toContain("e.por_fuente");
});

test("el corte temporal enseña si el patrón se repite AÑO A AÑO", () => {
  expect(VISTA).toContain("el_primer_tramo_es_el_PEOR");
  expect(VISTA).toContain("escalon_pp");
  expect(VISTA).toContain("direccion_se_cumple");
});

test("la tabla por año NO pregunta por «máximos» en hipótesis que no hablan de máximos", () => {
  // La etiqueta era «¿Peor el tramo en máximos?» y se reutilizó para la persistencia de
  // la tendencia. Mismo error que el veredicto reutilizado, una capa más abajo.
  expect(CODIGO).not.toContain("tramo en máximos");
  expect(VISTA).toContain("¿El primer tramo es el peor?");
});

test("el corte por año se busca en los DOS sitios donde puede venir", () => {
  // `resultado.años` cuando el experimento ES el corte; `resultado.por_periodo` cuando
  // viaja dentro de otro. Buscarlo en uno solo ya dejó la tabla invisible una vez.
  expect(VISTA).toContain("r.por_periodo?.años");
  expect(VISTA).toContain("añosDe");
});

test("los años SIN muestra se dicen, no desaparecen", () => {
  // Un año que falta de la tabla se lee como un año que no existió.
  expect(VISTA).toContain("años_descartados");
  expect(VISTA).toContain("Sin muestra suficiente");
});

test("la rejilla declara su columna de móvil", () => {
  // Mismo fallo que ya cortó la pantalla de Inteligencia por la mitad: sin `grid-cols-1`
  // la columna implícita se dimensiona a `max-content` y no encoge.
  const rejilla = (VISTA.match(/className="[^"]*lg:grid-cols-\[[^"]*"/) || [""])[0];
  expect(rejilla).toContain("grid-cols-1");
  expect(rejilla).toContain("minmax(0,1fr)");
});

test("la pantalla está enganchada a la navegación y a una ruta", () => {
  expect(RAIL).toContain('to: "/laboratorio"');
  expect(APP).toContain('path="/laboratorio"');
  expect(APP).toContain("LaboratorioView");
});

test("un experimento caído NO se anuncia como un fallo de lectura", () => {
  // Compartían `error` y compartían cartel: si la ejecución fallaba, la pantalla decía
  // «no se ha podido leer el laboratorio» arriba del todo, lejos del botón pulsado, y
  // la lectura sí había funcionado. Son dos estados distintos.
  expect(CODIGO).toContain("setFallo(");
  expect(CODIGO).toContain('data-testid="lab-fallo"');
  // El catch de `ejecutar` no puede volver a escribir en el estado de lectura.
  const ejecutar = CODIGO.slice(CODIGO.indexOf("const ejecutar"),
                                CODIGO.indexOf("const c = datos"));
  expect(ejecutar).not.toContain("setError(");
});

test("se dice CUÁL experimento está corriendo, no solo que hay uno", () => {
  // Con un booleano los ocho botones ponían «Midiendo…» a la vez. Un experimento tarda
  // minutos: no saber cuál corre es indistinguible de que el botón no hiciera nada.
  expect(CODIGO).toContain("const yo = activo === cual");
  expect(CODIGO).toContain("useState(null)");
  expect(CODIGO).not.toContain("setCorriendo(true)");
});
