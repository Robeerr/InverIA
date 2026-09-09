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
export const NIVELES = {
  INFO: { etiqueta: "Contexto", clase: "text-tinta-3", peso: 0 },
  WATCH: { etiqueta: "Atención", clase: "text-info", peso: 1 },
  IMPORTANT: { etiqueta: "Importante", clase: "text-aviso", peso: 2 },
  CRITICAL: { etiqueta: "Crítico", clase: "text-alerta", peso: 3 },
};

export const nivelDe = (evento) =>
  NIVELES[evento?.nivel_alerta] || { etiqueta: "Sin evaluar", clase: "text-tinta-3", peso: -1 };

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
