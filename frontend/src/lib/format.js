/* ─────────────────────────────────────────────────────────────────────────────
   Formato de datos · un solo sitio
   ─────────────────────────────────────────────────────────────────────────────

   Este fichero ya existía y estaba bien planteado, pero casi nadie lo usaba: la
   auditoría encontró 9 implementaciones distintas de "formatear dinero" repartidas
   por las pantallas, y dos locales mezclados (en-US para precios, es-ES para
   fechas) sin criterio.

   El criterio, escrito para no volver a discutirlo:

     · Los PRECIOS de acciones van en formato en-US (1,234.56) porque así los da el
       mercado y así los lee el usuario en el bróker. Cambiarlos a formato español
       haría que no cuadren de un vistazo con la pantalla de DEGIRO.
     · Los IMPORTES en euros van en es-ES (1.234,56 €), que es como se lee el
       dinero propio.
     · Las FECHAS van siempre en es-ES.
     · Un dato que falta se escribe "—", nunca "0", "N/A" ni cadena vacía. Un cero
       es una afirmación: dice que el valor es cero. Una raya dice que no se sabe,
       que es distinto y a veces más importante.
   ───────────────────────────────────────────────────────────────────────────── */

export const SIN_DATO = "—";

const esNulo = (v) => v === null || v === undefined || v === "" || (typeof v === "number" && isNaN(v));

/** Precio de mercado: 1,234.56 — formato en-US, como el bróker. */
export const fmtPrice = (v, decimales = 2) => {
  if (esNulo(v)) return SIN_DATO;
  return Number(v).toLocaleString("en-US", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
};

/** Porcentaje con signo explícito: +2.40% / -1.10%.
 *  El signo va siempre, también en positivo: sin él hay que fijarse en el color
 *  para saber el sentido, y el color solo no puede ser el portador de un dato. */
export const fmtPct = (v, decimales = 2) => {
  if (esNulo(v)) return SIN_DATO;
  const n = Number(v);
  return `${n >= 0 ? "+" : ""}${n.toFixed(decimales)}%`;
};

/** Porcentaje sin signo, para magnitudes que no tienen dirección (una distancia,
 *  una probabilidad): "1.8%". Usar fmtPct cuando el sentido importe. */
export const fmtPctPlano = (v, decimales = 1) => {
  if (esNulo(v)) return SIN_DATO;
  return `${Number(v).toFixed(decimales)}%`;
};

/** Número grande abreviado: 1.20T / 3.40B / 25.10M / 4.50K */
export const fmtNum = (v) => {
  if (esNulo(v)) return SIN_DATO;
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  return n.toLocaleString("en-US");
};

/** Dinero propio en euros: 1.234,56 € */
export const fmtEur = (v, decimales = 2) => {
  if (esNulo(v)) return SIN_DATO;
  return Number(v).toLocaleString("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
};

/** Dinero en la divisa que sea.
 *
 *  Nunca se inventa el símbolo: etiquetar dólares como euros no es un fallo de
 *  estilo, es un error de dato. Un código ISO válido pero que el navegador no
 *  conoce se escribe tal cual ("1234,50 XYZ"), que es honesto; solo cuando el
 *  código está malformado —e Intl lanza— se cae a número plano sin divisa. */
export const fmtDinero = (v, divisa = "EUR", decimales = 2) => {
  if (esNulo(v)) return SIN_DATO;
  const n = Number(v);
  try {
    return n.toLocaleString(divisa === "USD" ? "en-US" : "es-ES", {
      style: "currency",
      currency: divisa || "EUR",
      minimumFractionDigits: decimales,
      maximumFractionDigits: decimales,
    });
  } catch {
    return fmtPrice(n, decimales);
  }
};

/** Fecha corta: 10 ago 2026 */
export const fmtDate = (d) => {
  if (esNulo(d)) return SIN_DATO;
  const fecha = new Date(d);
  if (isNaN(fecha.getTime())) return SIN_DATO;
  return fecha.toLocaleDateString("es-ES", { day: "2-digit", month: "short", year: "numeric" });
};

/** Fecha y hora: 10 ago, 15:42 */
export const fmtDateTime = (d) => {
  if (esNulo(d)) return SIN_DATO;
  const fecha = new Date(d);
  if (isNaN(fecha.getTime())) return SIN_DATO;
  return fecha.toLocaleString("es-ES", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
};

/** Antigüedad en lenguaje normal: "hace 30 min", "hace 2 días".
 *
 *  Hace falta en más sitios de los que parece: un análisis puede ser de hace media
 *  hora y hoy la pantalla lo enseña como si acabara de calcularse. Saber si un dato
 *  está fresco es parte de poder fiarte de él. */
export const fmtHace = (d, ahora = Date.now()) => {
  if (esNulo(d)) return SIN_DATO;
  const t = new Date(d).getTime();
  if (isNaN(t)) return SIN_DATO;
  const seg = Math.floor((ahora - t) / 1000);
  if (seg < 0) return "en el futuro";
  if (seg < 60) return "hace un momento";
  const min = Math.floor(seg / 60);
  if (min < 60) return `hace ${min} min`;
  const horas = Math.floor(min / 60);
  if (horas < 24) return `hace ${horas} ${horas === 1 ? "hora" : "horas"}`;
  const dias = Math.floor(horas / 24);
  if (dias < 31) return `hace ${dias} ${dias === 1 ? "día" : "días"}`;
  const meses = Math.floor(dias / 30);
  if (meses < 12) return `hace ${meses} ${meses === 1 ? "mes" : "meses"}`;
  const anios = Math.floor(dias / 365);
  return `hace ${anios} ${anios === 1 ? "año" : "años"}`;
};

/** Días que faltan: "hoy", "mañana", "en 2 días". Para el calendario.
 *
 *  Cuenta días de CALENDARIO, no tramos de 24 horas. Con la resta cruda, unos
 *  resultados dentro de dos horas salían como "mañana" —porque cualquier resto
 *  positivo redondeaba a 1— y unos de mañana a primera hora salían como "hoy".
 *  Para "¿cuándo presenta resultados?" lo que importa es el día del calendario. */
export const fmtEnDias = (d, ahora = Date.now()) => {
  if (esNulo(d)) return SIN_DATO;
  const t = new Date(d);
  if (isNaN(t.getTime())) return SIN_DATO;
  const aMedianoche = (x) => {
    const y = new Date(x);
    y.setHours(0, 0, 0, 0);
    return y.getTime();
  };
  const dias = Math.round((aMedianoche(t) - aMedianoche(new Date(ahora))) / 86400000);
  if (dias < 0) return fmtDate(d);
  if (dias === 0) return "hoy";
  if (dias === 1) return "mañana";
  return `en ${dias} días`;
};

/** Distancia de un precio a una referencia, en %.
 *
 *  Es la unidad de urgencia de toda la app ("estás a un 1,8% de tu Nivel 3"), así
 *  que conviene que la calcule un solo sitio. Devuelve null si no se puede. */
export const distanciaPct = (precio, referencia) => {
  if (esNulo(precio) || esNulo(referencia)) return null;
  const p = Number(precio);
  const r = Number(referencia);
  if (!r) return null;
  return ((p - r) / r) * 100;
};

/** El signo de un número, para elegir color/tono sin repetir el ternario.
 *  Devuelve "sube" | "baja" | "neutro" — los mismos nombres que los tokens. */
export const tono = (v) => {
  if (esNulo(v)) return "neutro";
  const n = Number(v);
  if (n > 0) return "sube";
  if (n < 0) return "baja";
  return "neutro";
};

/** Un número escrito A MANO, con la coma decimal española.
 *
 *  En el móvil el teclado numérico de un teléfono en español ofrece COMA, no punto. Y
 *  `<input type="number">` no acepta la coma: el navegador descarta la tecla y el valor
 *  llega vacío. Con `Number("560,67")` sale NaN, así que registrar una compra a 560,67 $
 *  contestaba "el precio debe ser mayor que cero" sin más explicación. Escribir un precio
 *  es lo más básico que hace esta aplicación y desde el móvil era imposible.
 *
 *  Cuando aparecen los dos separadores, el ÚLTIMO manda: es el decimal, y el otro son los
 *  miles. Así "1.234,56" y "1,234.56" dan lo mismo, que es lo que se espera al pegar una
 *  cifra copiada del bróker.
 *
 *  Una coma sola SIEMPRE es decimal. "1,000" se lee como 1 y no como mil: aquí se teclean
 *  precios, no cantidades con separador de miles, y la lectura contraria convertiría
 *  "0,5 acciones" en un número absurdo. El punto solo ya se comportaba así.
 *
 *  Devuelve null —nunca NaN— cuando no hay número: quien llama distingue "vacío" de "cero"
 *  sin tener que acordarse de comprobar isNaN. */
export const aNumero = (v) => {
  if (esNulo(v) || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  let s = String(v).trim().replace(/\s/g, "");
  if (!s) return null;
  const coma = s.lastIndexOf(",");
  const punto = s.lastIndexOf(".");
  if (coma !== -1 && punto !== -1) {
    const miles = coma > punto ? "." : ",";
    s = s.split(miles).join("");
  }
  s = s.replace(",", ".");
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};
