/**
 * Lo que la pantalla de Inteligencia dice sobre sí misma.
 *
 * LA REGLA QUE MANDA AQUÍ
 *
 * La frase que se enseña arriba tiene que ser VERDAD. Está prohibido que la aplicación
 * diga que «está analizando Internet en tiempo real» si no hay ni una fuente conectada, y
 * está prohibido que un radar gire porque gira bonito. Eso convierte el texto de cabecera
 * en lógica, no en copy, y por eso vive aquí y tiene tests.
 *
 * TRES SILENCIOS DISTINTOS QUE NO SE PUEDEN PINTAR IGUAL
 *
 *   1. No hay ninguna fuente conectada     → «Sin fuentes conectadas»
 *   2. Hay fuentes y no vigilan nada       → «Vigilando 0 valores»
 *   3. Hay fuentes, vigilan, y no ha pasado nada → «Sin novedades»
 *
 * Los tres se ven idénticos en un radar vacío, y significan cosas completamente distintas:
 * el primero es una configuración que falta, el segundo una cartera vacía y el tercero un
 * mercado tranquilo. Confundirlos es la forma más rápida de creerte que el sistema está
 * trabajando cuando está apagado.
 */

// Los estados que sirve el backend. `escuchando` es lo único que autoriza a decir que
// una fuente está trabajando: DEGRADADA responde a veces y RATE_LIMITED está esperando,
// pero ninguna de las dos justifica un radar en marcha.
export const ESTADOS = {
  ONLINE: { etiqueta: "Escuchando", clase: "text-sube", escuchando: true },
  DEGRADADA: { etiqueta: "Intermitente", clase: "text-aviso", escuchando: false },
  RATE_LIMITED: { etiqueta: "Esperando turno", clase: "text-aviso", escuchando: false },
  NO_CONFIGURADA: { etiqueta: "Sin conectar", clase: "text-tinta-3", escuchando: false },
  ERROR: { etiqueta: "Con error", clase: "text-baja", escuchando: false },
  OFFLINE: { etiqueta: "Caída", clase: "text-baja", escuchando: false },
};

const DESCONOCIDO = { etiqueta: "Desconocido", clase: "text-tinta-3", escuchando: false };

export const estadoDe = (fuente) => ESTADOS[fuente?.estado] || DESCONOCIDO;

/** Cuántas fuentes están de verdad escuchando. Es lo que autoriza a animar el radar. */
export const escuchando = (fuentes) =>
  (fuentes || []).filter((f) => estadoDe(f).escuchando).length;

/**
 * La frase de cabecera. Se calcula, no se escribe.
 *
 * El orden de las comprobaciones es el orden de honestidad: primero lo que está apagado,
 * y solo al final —cuando de verdad hay fuentes escuchando y valores vigilados— se puede
 * hablar de vigilancia.
 */
export function resumen(estado) {
  const fuentes = estado?.fuentes || [];
  const activas = escuchando(fuentes);
  const universo = estado?.universo || 0;
  const significativos = estado?.eventos?.significativos || 0;

  if (!fuentes.length) {
    return { titulo: "Inteligencia sin fuentes",
             detalle: "No hay ninguna fuente implementada todavía.", vigila: false };
  }
  if (!activas) {
    return { titulo: "Sin fuentes conectadas",
             detalle: "Ninguna fuente está escuchando ahora mismo, así que no está " +
                      "entrando nada. El radar está apagado, no en silencio.",
             vigila: false };
  }
  if (!universo) {
    return { titulo: "Nada que vigilar",
             detalle: `${activas === 1 ? "Una fuente" : `${activas} fuentes`} escuchando, ` +
                      "pero no tienes valores en cartera ni en seguimiento: no hay con qué " +
                      "cruzar lo que llega.",
             vigila: false };
  }
  return {
    titulo: significativos
      ? `${significativos} ${significativos === 1 ? "novedad" : "novedades"}`
      : "Sin novedades",
    detalle: `${activas === 1 ? "Una fuente" : `${activas} fuentes`} vigilando ` +
             `${universo} ${universo === 1 ? "valor" : "valores"}.` +
             (significativos ? "" : " Nada relevante ha entrado todavía."),
    vigila: true,
  };
}

// Los niveles del backend, de menos a más. El nivel decide el color; el orden decide
// quién va arriba en la lista.
// `interrumpe` es el mismo umbral que el backend (INTERRUMPEN = IMPORTANT, CRITICAL) y va
// declarado en vez de deducirse del peso: si mañana cambia, se cambia aquí y no en cada
// sitio que compare números.
export const NIVELES = {
  INFO: { etiqueta: "Contexto", clase: "text-tinta-3", peso: 0, interrumpe: false },
  WATCH: { etiqueta: "Atención", clase: "text-info", peso: 1, interrumpe: false },
  IMPORTANT: { etiqueta: "Importante", clase: "text-aviso", peso: 2, interrumpe: true },
  CRITICAL: { etiqueta: "Crítico", clase: "text-alerta", peso: 3, interrumpe: true },
};

export const nivelDe = (evento) =>
  NIVELES[evento?.nivel_alerta] ||
  { etiqueta: "Sin evaluar", clase: "text-tinta-3", peso: -1, interrumpe: false };

/** Los eventos ordenados como se leen: lo más grave primero y, a igual gravedad, lo más nuevo. */
export function ordenados(eventos) {
  return [...(eventos || [])].sort((a, b) => {
    const d = nivelDe(b).peso - nivelDe(a).peso;
    if (d) return d;
    return String(b.recibido_en || "").localeCompare(String(a.recibido_en || ""));
  });
}

/** Agrupa por valor, conservando el orden de gravedad dentro de cada grupo. */
export function porValor(eventos) {
  const grupos = new Map();
  for (const e of ordenados(eventos)) {
    const s = e.symbol || "—";
    if (!grupos.has(s)) grupos.set(s, []);
    grupos.get(s).push(e);
  }
  return [...grupos.entries()].map(([symbol, items]) => ({ symbol, items }));
}

/**
 * Qué tiene y qué no tiene un evento, dicho explícitamente.
 *
 * En esta fase NO hay resumen por IA: `resumen` viaja siempre a null. La pantalla tiene
 * que enseñar el titular de la fuente y decir que eso es todo lo que hay, en vez de dejar
 * un hueco que parezca un fallo de carga — o peor, rellenarlo con prosa inventada.
 */
export const tieneAnalisis = (evento) => Boolean((evento?.resumen || "").trim());

/** El nombre corto de la etapa, para el diagnóstico. */
export const ETAPAS = {
  recibido: "Recibido",
  normalizado: "Normalizado",
  deduplicado: "Sin duplicar",
  filtrado: "Filtrado",
  investigado: "Investigado",
  agrupado: "Agrupado",
  significativo: "Significativo",
  alertado: "Alertado",
  descartado: "Descartado",
};

// Los motivos por los que el FILTRO tira un evento. «Ya conocido» no está aquí y no es
// un olvido: un documento que ya teníamos no lo descarta el filtro, lo resuelve la
// deduplicación un paso antes. Se conserva la traducción de `duplicado` porque puede
// quedar en datos antiguos, pero el pipeline ya no lo emite como motivo.
export const MOTIVOS = {
  sin_symbol: "Sin valor identificable",
  fuera_de_universo: "No es un valor tuyo",
  sin_relevancia: "No te afecta lo suficiente",
  duplicado: "Ya lo teníamos (dato antiguo)",
  sin_motivo: "Sin motivo anotado",
};

/**
 * Dónde va un evento en la esfera del radar: su antigüedad, en el sentido del reloj.
 *
 * Arriba es «ahora» y se va hacia atrás, como un reloj. Así la distancia entre dos marcas
 * es tiempo de verdad y no un reparto estético — que es lo que haría un `index * 30`.
 *
 * Devuelve `null` si el evento no trae una hora fiable, y ESE es el punto: sin hora no se
 * coloca. Inventarle un ángulo lo pondría en un sitio que el usuario leería como una hora
 * concreta, y sería un dato falso disfrazado de posición.
 */
export const VENTANA_RADAR_H = 24;

export function anguloPorHora(iso, ahora = Date.now()) {
  const t = Date.parse(iso || "");
  if (Number.isNaN(t)) return null;
  const horas = (ahora - t) / 3600000;
  if (horas < 0) return 0;                       // relojes desalineados: se trata como ahora
  return Math.min(horas / VENTANA_RADAR_H, 1) * 360;
}


/**
 * Plegar lo repetido: catorce Form 4 de MSFT son una fila, no catorce.
 *
 * EL PROBLEMA, MEDIDO EN PRODUCCIÓN
 *
 * Cuando una empresa consolida acciones, media directiva registra un Form 4 el mismo día.
 * En una vuelta real entraron 14 de MSFT y 10 de NFLX, todos con el mismo título —
 * `4 · Operación de un directivo — MSFT`— porque el nombre del directivo está dentro del
 * documento y no lo descargamos. Catorce líneas idénticas no informan de nada.
 *
 * NO son duplicados: son registros distintos, con su propio número y su enlace. La
 * deduplicación funciona. Lo que fallaba era la lectura.
 *
 * ESTO NO ES LA ETAPA `agrupado` DEL PIPELINE
 *
 * Y la distinción importa, porque esa etapa sigue declarada como no implementada. Son
 * cosas distintas:
 *
 *   `agrupado`  · el backend decide que varios eventos cuentan LA MISMA historia y los
 *                 funde en uno. Cambia lo que se guarda y lo que se puntúa. No existe.
 *   plegar      · la pantalla junta filas que dicen lo mismo para poder leerlas. No
 *                 cambia ningún evento, ninguna nota y ninguna etapa; se despliega y
 *                 están todos, con su enlace.
 *
 * LO QUE INTERRUMPE NUNCA SE PLIEGA
 *
 * Un evento que el backend consideró digno de sacarte de lo que estás haciendo no puede
 * acabar escondido dentro de un montón. Es la regla que impide que plegar se convierta en
 * ocultar.
 */
const PLURAL = {
  "4": ["operación de un directivo", "operaciones de directivos"],
  "8-K": ["hecho relevante", "hechos relevantes"],
  programado: ["resultados programados", "resultados programados"],
  cambio_fecha: ["cambio de fecha", "cambios de fecha"],
  publicado: ["resultados publicados", "resultados publicados"],
};

export const tituloDeGrupo = (suceso, n) => {
  const par = PLURAL[suceso];
  if (!par) return `${n} eventos`;
  return `${n} ${n === 1 ? par[0] : par[1]}`;
};

/** Qué filas cuentan como «lo mismo»: mismo valor, mismo suceso y mismo día. */
export const claveDePliegue = (e) =>
  [e?.symbol || "—", e?.fuente || "", e?.detalle?.suceso || "",
   (e?.detalle?.fecha_registro || e?.recibido_en || "").slice(0, 10)].join("|");

export function plegarRepetidos(eventos, minimo = 2) {
  const lista = ordenados(eventos);
  const orden = [];
  const porClave = new Map();

  for (const e of lista) {
    // Lo que interrumpe va suelto, en su sitio y con su gravedad a la vista.
    if (nivelDe(e).interrumpe) {
      orden.push({ suelto: e });
      continue;
    }
    const k = claveDePliegue(e);
    if (!porClave.has(k)) {
      porClave.set(k, []);
      orden.push({ clave: k });
    }
    porClave.get(k).push(e);
  }

  return orden.map((x) => {
    if (x.suelto) return { tipo: "evento", id: x.suelto.id, evento: x.suelto };
    const items = porClave.get(x.clave);
    // Un «grupo» de uno es un evento: pintarlo plegado obligaría a desplegar para leer
    // una sola línea.
    if (items.length < minimo) {
      return { tipo: "evento", id: items[0].id, evento: items[0] };
    }
    return {
      tipo: "grupo", id: x.clave, items, n: items.length,
      symbol: items[0].symbol, fuente: items[0].fuente,
      // `ordenados` ya dejó el más grave delante, así que el grupo hereda su nivel.
      nivel: items[0].nivel_alerta,
      titulo: tituloDeGrupo(items[0]?.detalle?.suceso, items.length),
    };
  });
}


/**
 * Marcas del radar que caen en el mismo sitio.
 *
 * EL PROBLEMA, VISTO EN PRODUCCIÓN
 *
 * El radar coloca cada evento por su tier (radio) y su hora (ángulo). En una vuelta real
 * entraron 42 registros en el mismo minuto y casi todos Tier 1: mismas coordenadas, y en
 * pantalla se veían cuatro marcas de cuarenta y dos.
 *
 * No era un fallo de dibujo: era el radar diciendo «hay cuatro cosas» cuando había
 * cuarenta y dos. Exactamente el tipo de mentira silenciosa que este radar existe para
 * no contar.
 *
 * POR QUÉ SE AGRUPA EN VEZ DE SEPARARLAS
 *
 * Separarlas obligaría a moverlas, y las dos coordenadas SIGNIFICAN algo: el radio es el
 * tier y el ángulo es la hora. Empujar una marca un grado la mueve seis minutos en el
 * tiempo — un dato falso para arreglar un problema de dibujo.
 *
 * Así que se agrupan y se dice cuántas hay. Una marca que lleva un «14» al lado es más
 * verdad que catorce marcas que se ven como una.
 */
export function agruparCoincidentes(marcas, tolerancia = 7) {
  const celdas = new Map();
  const orden = [];
  for (const m of marcas || []) {
    // La rejilla es del tamaño de lo que el ojo no distingue. Dos marcas más separadas
    // que eso se pintan aparte, porque ahí sí se ven las dos.
    const celda = `${Math.round(m.x / tolerancia)}|${Math.round(m.y / tolerancia)}`;
    if (!celdas.has(celda)) {
      celdas.set(celda, []);
      orden.push(celda);
    }
    celdas.get(celda).push(m);
  }
  return orden.map((celda) => {
    const items = celdas.get(celda);
    // La posición es la de la PRIMERA, no un centroide: las marcas vienen ordenadas por
    // gravedad, así que el grupo se queda donde estaba la más grave. Un centroide
    // desplazaría el conjunto a un punto donde no ocurrió nada.
    return { x: items[0].x, y: items[0].y, items, n: items.length };
  });
}
