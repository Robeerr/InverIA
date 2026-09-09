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
  anguloPorHora,
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
