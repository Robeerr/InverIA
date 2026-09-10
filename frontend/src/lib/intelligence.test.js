/**
 * La pantalla de Inteligencia no puede mentir sobre sí misma.
 *
 * Estos tests existen porque la frase de cabecera es la que se cree el usuario. Si dice
 * «vigilando» cuando no hay nada conectado, el sistema entero pasa a ser decorativo sin
 * que se note — y no se notaría precisamente porque la pantalla dice que va bien.
 *
 * El bloque central separa los tres silencios: nada conectado, nada que vigilar y nada que
 * contar. En un radar vacío se ven idénticos, y significan cosas opuestas.
 */
import {
  ESTADOS, escuchando, estadoDe, resumen, nivelDe, ordenados, porValor, tieneAnalisis,
  anguloPorHora, plegarRepetidos, NIVELES, agruparCoincidentes, recortar, tituloCorto,
  estadoDeLectura, LEIDO,
} from "./intelligence";

const online = { fuente: "sec", estado: "ONLINE" };
const apagada = { fuente: "sec", estado: "NO_CONFIGURADA" };

describe("qué cuenta como escuchar", () => {
  test("solo ONLINE está escuchando de verdad", () => {
    const escuchan = Object.entries(ESTADOS)
      .filter(([, v]) => v.escuchando)
      .map(([k]) => k);
    expect(escuchan).toEqual(["ONLINE"]);
  });

  test("intermitente y esperando turno NO autorizan a decir que se escucha", () => {
    // Las dos responden a veces, y eso no es lo mismo que estar trabajando. Si contaran,
    // el radar se animaría durante una caída parcial.
    expect(escuchando([{ estado: "DEGRADADA" }, { estado: "RATE_LIMITED" }])).toBe(0);
  });

  test("un estado que no conocemos no se pinta como bueno", () => {
    // Si el backend añade un estado, el fallback tiene que ser conservador: mejor
    // «desconocido» que un verde que no le corresponde.
    expect(estadoDe({ estado: "ALGO_NUEVO" }).escuchando).toBe(false);
  });
});

describe("los tres silencios", () => {
  test("sin fuentes conectadas se dice que está APAGADO, no en silencio", () => {
    const r = resumen({ fuentes: [apagada], universo: 12, eventos: { significativos: 0 } });
    expect(r.vigila).toBe(false);
    expect(r.titulo).toMatch(/Sin fuentes conectadas/);
  });

  test("con fuentes pero sin cartera se dice que no hay nada que vigilar", () => {
    const r = resumen({ fuentes: [online], universo: 0 });
    expect(r.vigila).toBe(false);
    expect(r.titulo).toMatch(/Nada que vigilar/);
  });

  test("con todo en marcha y sin novedades se dice SIN NOVEDADES, y sí vigila", () => {
    const r = resumen({ fuentes: [online], universo: 12, eventos: { significativos: 0 } });
    expect(r.vigila).toBe(true);
    expect(r.titulo).toBe("Sin novedades");
    expect(r.detalle).toMatch(/12 valores/);
  });

  test("los tres silencios dicen cosas DISTINTAS", () => {
    const titulos = [
      resumen({ fuentes: [apagada], universo: 12 }).titulo,
      resumen({ fuentes: [online], universo: 0 }).titulo,
      resumen({ fuentes: [online], universo: 12, eventos: { significativos: 0 } }).titulo,
    ];
    expect(new Set(titulos).size).toBe(3);
  });

  test("NUNCA se dice que vigila si no hay una fuente escuchando", () => {
    // La prohibición escrita: no afirmar que está analizando si alguna parte no lo está.
    for (const estado of Object.keys(ESTADOS)) {
      const r = resumen({ fuentes: [{ estado }], universo: 40,
                          eventos: { significativos: 9 } });
      expect(r.vigila).toBe(estado === "ONLINE");
    }
  });

  test("sin fuentes implementadas no se inventa ninguna", () => {
    expect(resumen({ fuentes: [] }).vigila).toBe(false);
    expect(resumen({}).vigila).toBe(false);
  });
});

describe("el recuento de novedades", () => {
  test("se enseña el número real y en singular cuando es una", () => {
    expect(resumen({ fuentes: [online], universo: 5, eventos: { significativos: 1 } }).titulo)
      .toBe("1 novedad");
    expect(resumen({ fuentes: [online], universo: 5, eventos: { significativos: 3 } }).titulo)
      .toBe("3 novedades");
  });
});

describe("orden de lectura", () => {
  const e = (id, nivel, cuando) => ({ id, nivel_alerta: nivel, recibido_en: cuando });

  test("lo más grave va primero", () => {
    const lista = ordenados([e("a", "WATCH", "2026-09-09"), e("b", "CRITICAL", "2026-09-01")]);
    expect(lista.map((x) => x.id)).toEqual(["b", "a"]);
  });

  test("a igual gravedad, lo más nuevo primero", () => {
    const lista = ordenados([e("viejo", "WATCH", "2026-09-01"), e("nuevo", "WATCH", "2026-09-09")]);
    expect(lista.map((x) => x.id)).toEqual(["nuevo", "viejo"]);
  });

  test("ordenar no muta la lista original", () => {
    const original = [e("a", "WATCH", "2026-09-01"), e("b", "CRITICAL", "2026-09-02")];
    ordenados(original);
    expect(original.map((x) => x.id)).toEqual(["a", "b"]);
  });

  test("un evento sin evaluar no se cuela por delante de uno evaluado", () => {
    // `nivel_alerta` a null significa «no se ha mirado». Tratarlo como INFO lo colaría en
    // la lista como si alguien lo hubiera revisado.
    expect(nivelDe({ nivel_alerta: null }).peso).toBeLessThan(nivelDe({ nivel_alerta: "INFO" }).peso);
  });

  test("agrupar por valor conserva la gravedad dentro del grupo", () => {
    const grupos = porValor([
      { symbol: "NVDA", nivel_alerta: "WATCH", recibido_en: "2026-09-09" },
      { symbol: "NVDA", nivel_alerta: "CRITICAL", recibido_en: "2026-09-01" },
      { symbol: "AMD", nivel_alerta: "INFO", recibido_en: "2026-09-09" },
    ]);
    expect(grupos.map((g) => g.symbol)).toEqual(["NVDA", "AMD"]);
    expect(grupos[0].items.map((i) => i.nivel_alerta)).toEqual(["CRITICAL", "WATCH"]);
  });
});

describe("lo que todavía no existe", () => {
  test("sin resumen de IA se dice que no hay análisis, no se finge uno", () => {
    // En esta fase `resumen` viaja siempre a null. La pantalla tiene que poder distinguir
    // «no hay análisis» de «el análisis está cargando».
    expect(tieneAnalisis({ resumen: null })).toBe(false);
    expect(tieneAnalisis({ resumen: "  " })).toBe(false);   // en blanco tampoco es análisis
    expect(tieneAnalisis({ resumen: "Un directivo ha vendido." })).toBe(true);
    expect(tieneAnalisis(undefined)).toBe(false);
  });
});

describe("dónde va cada marca en la esfera", () => {
  const AHORA = Date.parse("2026-09-09T12:00:00Z");

  test("lo de ahora mismo va arriba del todo", () => {
    expect(anguloPorHora("2026-09-09T12:00:00Z", AHORA)).toBe(0);
  });

  test("la esfera es un reloj: media ventana es media vuelta", () => {
    // 12 h de antigüedad sobre una ventana de 24 h. Si esto dejara de cumplirse, la
    // distancia entre dos marcas ya no sería tiempo.
    expect(anguloPorHora("2026-09-09T00:00:00Z", AHORA)).toBe(180);
    expect(anguloPorHora("2026-09-09T06:00:00Z", AHORA)).toBe(90);   // 6 h → un cuarto
  });

  test("lo más viejo que la ventana se queda en el borde, no da otra vuelta", () => {
    // Sin el tope, un evento de hace tres días aparecería como si fuera de hace unas
    // horas: exactamente la lectura contraria a la verdadera.
    expect(anguloPorHora("2026-09-01T12:00:00Z", AHORA)).toBe(360);
  });

  test("SIN HORA NO SE COLOCA", () => {
    // La regla que impide inventar. Un ángulo por defecto se leería como una hora
    // concreta, y sería un dato falso disfrazado de posición.
    expect(anguloPorHora(null, AHORA)).toBeNull();
    expect(anguloPorHora("", AHORA)).toBeNull();
    expect(anguloPorHora("no es una fecha", AHORA)).toBeNull();
  });

  test("un evento con fecha futura se trata como ahora, no se sale de la esfera", () => {
    // Pasa de verdad: los relojes de las fuentes y el nuestro no están sincronizados.
    expect(anguloPorHora("2026-09-09T13:00:00Z", AHORA)).toBe(0);
  });
});


describe("plegar lo repetido", () => {
  const f4 = (id, symbol = "MSFT", extra = {}) => ({
    id, symbol, fuente: "sec", nivel_alerta: "WATCH", recibido_en: "2026-09-09T10:00:00Z",
    detalle: { suceso: "4", fecha_registro: "2026-09-08", accession: id }, ...extra,
  });

  test("catorce Form 4 del mismo dia son UNA fila", () => {
    // El caso real: cuando una empresa consolida acciones, media directiva registra el
    // mismo día. Catorce líneas con el mismo título no informan de nada.
    const filas = plegarRepetidos(Array.from({ length: 14 }, (_, i) => f4(`a${i}`)));
    expect(filas).toHaveLength(1);
    expect(filas[0].tipo).toBe("grupo");
    expect(filas[0].n).toBe(14);
    expect(filas[0].titulo).toBe("14 operaciones de directivos");
  });

  test("NO se pierde ninguno: están todos dentro, con su enlace", () => {
    // Plegar no es descartar. Si un evento desapareciera aquí, la pantalla estaría
    // ocultando un registro real y no habría forma de notarlo.
    const originales = Array.from({ length: 14 }, (_, i) => f4(`a${i}`));
    const dentro = plegarRepetidos(originales).flatMap((x) => x.items || [x.evento]);
    expect(dentro.map((e) => e.id).sort()).toEqual(originales.map((e) => e.id).sort());
  });

  test("lo que INTERRUMPE nunca se pliega", () => {
    // La regla que impide que plegar se convierta en ocultar: algo que el backend
    // consideró digno de sacarte de lo que haces no puede acabar dentro de un montón.
    const filas = plegarRepetidos([
      f4("a", "MSFT"), f4("b", "MSFT"),
      f4("importante", "MSFT", { nivel_alerta: "IMPORTANT" }),
    ]);
    const sueltos = filas.filter((x) => x.tipo === "evento");
    expect(sueltos).toHaveLength(1);
    expect(sueltos[0].evento.id).toBe("importante");
  });

  test("valores distintos no se mezclan", () => {
    const filas = plegarRepetidos([f4("a", "MSFT"), f4("b", "MSFT"),
                                   f4("c", "NFLX"), f4("d", "NFLX")]);
    expect(filas.map((x) => x.symbol)).toEqual(["MSFT", "NFLX"]);
  });

  test("sucesos distintos no se mezclan", () => {
    // Un 8-K y un Form 4 de la misma empresa el mismo día no cuentan lo mismo.
    const ocho = { ...f4("x"), detalle: { suceso: "8-K", fecha_registro: "2026-09-08" } };
    const filas = plegarRepetidos([f4("a"), f4("b"), ocho, { ...ocho, id: "y" }]);
    expect(filas).toHaveLength(2);
    expect(filas.map((x) => x.titulo)).toContain("2 hechos relevantes");
  });

  test("DIAS distintos no se mezclan", () => {
    const ayer = { ...f4("v"), detalle: { suceso: "4", fecha_registro: "2026-09-07" } };
    expect(plegarRepetidos([f4("a"), f4("b"), ayer, { ...ayer, id: "w" }])).toHaveLength(2);
  });

  test("uno solo NO se pliega", () => {
    // Un «grupo» de uno obligaría a desplegar para leer una línea.
    const filas = plegarRepetidos([f4("a"), f4("otro", "NFLX")]);
    expect(filas.every((x) => x.tipo === "evento")).toBe(true);
  });

  test("el grupo hereda la gravedad de su miembro más grave", () => {
    const filas = plegarRepetidos([f4("a"), f4("b", "MSFT", { nivel_alerta: "INFO" })]);
    expect(filas[0].nivel).toBe("WATCH");
  });

  test("el orden de lectura se conserva: lo más grave arriba", () => {
    const filas = plegarRepetidos([
      f4("info", "AMD", { nivel_alerta: "INFO" }), f4("info2", "AMD", { nivel_alerta: "INFO" }),
      f4("grave", "MSFT", { nivel_alerta: "IMPORTANT" }),
      f4("a"), f4("b"),
    ]);
    expect(filas[0].tipo).toBe("evento");        // el IMPORTANT, suelto y primero
    expect(filas[0].evento.id).toBe("grave");
  });

  test("sin eventos no se inventa ninguna fila", () => {
    expect(plegarRepetidos([])).toEqual([]);
    expect(plegarRepetidos(null)).toEqual([]);
  });

  test("un suceso desconocido se pliega con un titulo neutro", () => {
    const raro = { ...f4("a"), detalle: { suceso: "vete_a_saber", fecha_registro: "2026-09-08" } };
    const filas = plegarRepetidos([raro, { ...raro, id: "b" }]);
    expect(filas[0].titulo).toBe("2 eventos");
  });

  test("los niveles declaran si INTERRUMPEN, igual que el backend", () => {
    const interrumpen = Object.entries(NIVELES)
      .filter(([, v]) => v.interrumpe).map(([k]) => k);
    expect(interrumpen.sort()).toEqual(["CRITICAL", "IMPORTANT"]);
  });
});


describe("marcas del radar que coinciden", () => {
  const m = (id, x, y, symbol = "MSFT") => ({ x, y, ev: { id, symbol, nivel_alerta: "WATCH" } });

  test("42 marcas en el mismo punto son UNA con su recuento", () => {
    // El caso real: 42 registros en el mismo minuto y el mismo tier. En pantalla se veían
    // cuatro marcas de cuarenta y dos — el radar decía que había cuatro cosas.
    const g = agruparCoincidentes(Array.from({ length: 42 }, (_, i) => m(`a${i}`, 160, 120)));
    expect(g).toHaveLength(1);
    expect(g[0].n).toBe(42);
  });

  test("marcas que el ojo SÍ distingue se pintan aparte", () => {
    expect(agruparCoincidentes([m("a", 100, 100), m("b", 160, 200)])).toHaveLength(2);
  });

  test("no se pierde ninguna marca", () => {
    const marcas = [m("a", 100, 100), m("b", 100, 100), m("c", 200, 200)];
    const dentro = agruparCoincidentes(marcas).flatMap((g) => g.items);
    expect(dentro).toHaveLength(3);
  });

  test("el grupo se queda donde estaba la marca MÁS GRAVE, no en un centroide", () => {
    // Un centroide desplazaría el conjunto a un punto donde no ocurrió nada, y las dos
    // coordenadas significan algo: el radio es el tier y el ángulo es la hora.
    const g = agruparCoincidentes([m("grave", 100, 100), m("otro", 103, 104)]);
    expect([g[0].x, g[0].y]).toEqual([100, 100]);
  });

  test("las coordenadas NO se tocan para separar marcas", () => {
    // Mover una marca un grado la mueve seis minutos en el tiempo. Se agrupa justamente
    // para no tener que inventar posiciones.
    const original = [m("a", 77, 133)];
    expect(agruparCoincidentes(original)[0]).toMatchObject({ x: 77, y: 133, n: 1 });
  });

  test("sin marcas no se inventa ningún grupo", () => {
    expect(agruparCoincidentes([])).toEqual([]);
    expect(agruparCoincidentes(null)).toEqual([]);
  });
});


describe("recortar la lista sin esconder nada", () => {
  const fila = (id, nivel = "WATCH") => ({
    tipo: "evento", id, evento: { id, nivel_alerta: nivel, symbol: "X" },
  });

  test("por debajo del tope no se recorta", () => {
    const filas = [...Array(5)].map((_, i) => fila(`a${i}`));
    expect(recortar(filas, 12)).toEqual({ visibles: filas, ocultas: 0 });
  });

  test("por encima se recorta y se DICE cuántas quedan", () => {
    // Recortar sin decir cuánto queda sería ocultar.
    const r = recortar([...Array(40)].map((_, i) => fila(`a${i}`)), 12);
    expect(r.visibles).toHaveLength(12);
    expect(r.ocultas).toBe(28);
  });

  test("lo que INTERRUMPE se ve SIEMPRE, aunque no quepa", () => {
    // Con veinte eventos importantes, el tope no puede decidir cuáles miras.
    const filas = [...Array(30)].map((_, i) => fila(`a${i}`));
    filas.push(fila("urgente", "CRITICAL"));
    const r = recortar(filas, 5);
    expect(r.visibles.map((f) => f.id)).toContain("urgente");
  });

  test("con más importantes que el tope, salen todos", () => {
    const filas = [...Array(20)].map((_, i) => fila(`i${i}`, "IMPORTANT"));
    const r = recortar(filas, 5);
    expect(r.visibles).toHaveLength(20) && expect(r.ocultas).toBe(0);
  });

  test("el recorte NO reordena lo que deja", () => {
    // `ordenados` ya puso lo grave delante; reordenar aquí rompería esa lectura.
    const filas = [fila("a"), fila("b"), fila("urgente", "IMPORTANT"), fila("c")];
    expect(recortar(filas, 3).visibles.map((f) => f.id)).toEqual(["a", "b", "urgente"]);
  });

  test("un GRUPO también puede ser urgente y verse siempre", () => {
    const grupo = { tipo: "grupo", id: "g", nivel: "IMPORTANT", items: [] };
    const filas = [...[...Array(30)].map((_, i) => fila(`a${i}`)), grupo];
    expect(recortar(filas, 4).visibles.map((f) => f.id)).toContain("g");
  });

  test("sin filas no revienta", () => {
    expect(recortar([], 12)).toEqual({ visibles: [], ocultas: 0 });
    expect(recortar(null, 12)).toEqual({ visibles: [], ocultas: 0 });
  });
});

describe("el título no repite el símbolo", () => {
  test("se quita el sufijo que duplica la columna de al lado", () => {
    expect(tituloCorto({ symbol: "NVDA", titulo: "4 · Operación de un directivo — NVDA" }))
      .toBe("4 · Operación de un directivo");
  });

  test("si el título no acaba en el símbolo, no se toca", () => {
    const t = "NVDA 2027Q1 · Resultados el 2026-10-28";
    expect(tituloCorto({ symbol: "NVDA", titulo: t })).toBe(t);
  });

  test("aguanta un evento sin título o sin símbolo", () => {
    expect(tituloCorto({})).toBe("");
    expect(tituloCorto({ titulo: "algo" })).toBe("algo");
  });
});


describe("marcar lo que la IA ya ha leído", () => {
  test("tres estados, no dos", () => {
    // «Se leyó y no decía nada» y «se leyó y esto dice» se ven igual en una lista si no
    // se marcan, y significan lo contrario sobre si merece la pena abrirlo.
    expect(estadoDeLectura({})).toBe(LEIDO.NO);
    expect(estadoDeLectura({ investigacion: { hay_informacion: false } })).toBe(LEIDO.SIN_INFO);
    expect(estadoDeLectura({ investigacion: { hay_informacion: true } })).toBe(LEIDO.CON_INFO);
  });

  test("un evento sin investigar no se marca como leído", () => {
    expect(estadoDeLectura({ resumen: null, investigacion: null })).toBe(LEIDO.NO);
    expect(estadoDeLectura(null)).toBe(LEIDO.NO);
  });
});
