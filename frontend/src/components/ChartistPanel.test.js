/**
 * El Chartista en pantalla no puede ejecutar una compra que la estructura ha vetado.
 *
 * MOSTRAR Y EJECUTAR NO SON LO MISMO
 *
 * Casi todo este panel muestra: lecturas por timeframe, patrón, veredicto en prosa. Eso
 * sobrevive al veto, porque una acción en tendencia bajista se puede estudiar.
 *
 * «Añadir a Cartera» es la excepción: ESCRIBE. Crea una entrada con `nivel1..5` y un
 * precio deseado de venta, y eso persiste después de que el usuario cierre la pestaña. Un
 * efecto persistente no puede depender de que otra capa haya limpiado bien los datos
 * antes de llegar aquí — el backend ya vacía los niveles al servir y rechaza la escritura
 * con un 409, pero una respuesta cacheada en el navegador no pasa por ninguno de los dos.
 *
 * POR QUÉ SE PRUEBA SOBRE EL CÓDIGO
 *
 * El proyecto no tiene `@testing-library`, así que no se monta el componente. Lo que hay
 * que proteger es que la guarda EXISTA y esté ANTES de la escritura, y eso se ve en la
 * fuente. La lógica de degradación ya está probada aparte, en `test_veto_compra.py`.
 */
const fs = require("fs");
const path = require("path");

const leer = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const sinComentarios = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const PANEL = leer("components/ChartistPanel.jsx");
const CODIGO = sinComentarios(PANEL);

describe("añadir a Cartera respeta el veto", () => {
  const cuerpo = CODIGO.slice(CODIGO.indexOf("async function addToCartera"));
  const hastaLaEscritura = cuerpo.slice(0, cuerpo.indexOf("api.signalsCreate"));

  test("hay una guarda por veto antes de escribir nada", () => {
    expect(hastaLaEscritura).toContain("data?.vetado_por_tendencia");
  });

  test("la guarda sale de la función, no solo avisa", () => {
    const trozo = hastaLaEscritura.slice(hastaLaEscritura.indexOf("vetado_por_tendencia"));
    expect(trozo).toMatch(/return;/);
  });

  test("la guarda va antes de construir el payload de niveles", () => {
    expect(hastaLaEscritura.indexOf("vetado_por_tendencia"))
      .toBeLessThan(hastaLaEscritura.indexOf("niveles_entrada"));
  });

  test("un 409 por veto NO marca la acción como añadida", () => {
    // Es el fallo que este bloque existe para impedir: cualquier 409 se leía como
    // duplicado, así que un rechazo terminaba con el check verde de «En Cartera».
    // Mentía dos veces — ni estaba guardada, ni el motivo era ese.
    const captura = cuerpo.slice(cuerpo.indexOf("catch"));
    const rama = captura.slice(captura.indexOf('detail?.error === "vetado_por_tendencia"'));
    const hastaElCierre = rama.slice(0, rama.indexOf("}"));
    expect(hastaElCierre).not.toContain("setAddedCartera");
    expect(hastaElCierre).toMatch(/return;/);
  });

  test("los dos 409 se separan por un campo, no por el texto", () => {
    // El mensaje del veto lo redacta `estado_accion` y puede cambiar; el campo no.
    const captura = cuerpo.slice(cuerpo.indexOf("catch"));
    expect(captura).toContain('detail?.error === "vetado_por_tendencia"');
    expect(captura.indexOf('vetado_por_tendencia'))
      .toBeLessThan(captura.indexOf("status === 409"));
  });

  test("cierra la carrera: el veto se descubre en la respuesta, no solo en el plan", () => {
    // El veredicto del Chartista se cachea hasta 4 horas, así que el plan que tiene la
    // pantalla puede ser anterior al giro de tendencia: llega SIN marcar, la guarda de
    // entrada no salta y la petición sale. El 409 del servidor es entonces el único
    // punto donde se descubre, y por eso la rama vive en el `catch` y no depende de
    // `data.vetado_por_tendencia`.
    const captura = cuerpo.slice(cuerpo.indexOf("catch"));
    const rama = captura.slice(captura.indexOf('detail?.error === "vetado_por_tendencia"'));
    const hastaElCierre = rama.slice(0, rama.indexOf("}"));
    expect(hastaElCierre).not.toContain("data?.vetado_por_tendencia");
    expect(hastaElCierre).not.toContain("data.vetado_por_tendencia");
  });

  test("el toast del veto usa el mensaje del backend", () => {
    const captura = cuerpo.slice(cuerpo.indexOf("catch"));
    expect(captura).toContain("detail.mensaje");
  });

  test("el detalle del duplicado se sigue leyendo como cadena", () => {
    // El contrato del duplicado no cambia: `detail` sigue siendo un string. Sin el
    // `typeof`, un detalle-objeto acabaría en `/ya/i.test("[object Object]")`.
    const captura = cuerpo.slice(cuerpo.indexOf("catch"));
    expect(captura).toContain('typeof detail === "string"');
  });

  test("nunca envía `forzar` al servidor", () => {
    // El servidor bloquea por defecto la escritura de niveles sobre una acción vetada, y
    // `forzar: true` es el escape. Tiene que ser una decisión EXPLÍCITA del usuario: un
    // escape que un automatismo puede activar solo no es un escape, es un agujero.
    expect(CODIGO).not.toContain("forzar");
  });
});

describe("el veto se explica, no solo se aplica", () => {
  test("el panel pinta el aviso cuando el backend lo marca", () => {
    expect(CODIGO).toContain("data.vetado_por_tendencia");
    expect(CODIGO).toContain('data-testid="chartista-vetado"');
  });

  test("y usa el motivo que manda el backend, sin redactar el suyo", () => {
    // El texto vive en `estado_accion._MOTIVOS`, que es el dueño de la explicación.
    // Escribir aquí una segunda versión sería tener dos verdades sobre lo mismo.
    expect(CODIGO).toContain("data.veto_motivo");
  });

  test("el aviso va antes del plan", () => {
    // Si el usuario lee «ESPERAR» sin explicación lo atribuye al criterio del chartista y
    // no a la estructura, que es justo el matiz del que aprende algo.
    expect(CODIGO.indexOf("chartista-vetado")).toBeLessThan(CODIGO.indexOf("Compra escalonada"));
  });
});

describe("la pantalla no decide", () => {
  test("no clasifica la tendencia por su cuenta", () => {
    for (const propio of ["NO_COMPRAR", "sma200", "sma50", "ALCISTA", "BAJISTA"]) {
      expect(CODIGO).not.toContain(propio);
    }
  });

  test("no reescribe la acción del plan", () => {
    // Degradar COMPRAR → ESPERAR es del backend. Hacerlo también aquí daría dos reglas
    // para lo mismo, y la de la pantalla ganaría sin que nadie se enterase.
    expect(CODIGO).not.toMatch(/accion\s*=\s*["']ESPERAR["']/);
  });

  test("los tres colores de acción siguen declarados", () => {
    for (const accion of ["COMPRAR", "ESPERAR", "EVITAR"]) {
      expect(CODIGO).toContain(accion);
    }
  });
});
