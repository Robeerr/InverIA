/* Portada · la lógica que no es pintura
   ─────────────────────────────────────────────────────────────────────────────
   Vive fuera de HoyView porque es lo único de esa pantalla que se puede comprobar
   con un test de verdad: el componente importa react-router, que jest no resuelve
   en este proyecto, así que todo lo que se quede dentro solo se puede examinar
   leyendo la fuente. Aquí se ejecuta.

   Y porque son dos preguntas distintas: qué se dice, y cómo se pinta. */

const NOMBRES = {
  nivel: ["ha llegado a tu nivel", "han llegado a tu nivel"],
  ruptura: ["ha roto su nivel", "han roto su nivel"],
  alerta: ["ha cruzado tu alerta", "han cruzado tus alertas"],
  divergencia: ["choca con tus fuentes", "chocan con tus fuentes"],
  confluencia: ["coincide con tus fuentes", "coinciden con tus fuentes"],
  resultados: ["presenta resultados", "presentan resultados"],
};
const CANTIDAD = ["Ninguna", "Una", "Dos", "Tres", "Cuatro", "Cinco"];

/** El saludo va sin nombre a propósito: el frontend no conoce al usuario, y «admin»
 *  no es el nombre de nadie. */
function saludoDeLaHora(d = new Date()) {
  const h = d.getHours();
  if (h < 6) return "Buenas noches";
  if (h < 14) return "Buenos días";
  if (h < 21) return "Buenas tardes";
  return "Buenas noches";
}

/** «2 alertas saltadas · 2 niveles cerca», del conteo por tipo que ya manda el servidor.
 *  Es el mismo dato que antes iba en el titular grande: al pasar la portada a un saludo,
 *  esta frase es la que impide que se pierda. */
const NOMBRE_TIPO = {
  ruptura: ["ruptura", "rupturas"],
  alerta: ["alerta saltada", "alertas saltadas"],
  nivel: ["nivel cerca", "niveles cerca"],
  divergencia: ["choque con tus fuentes", "choques con tus fuentes"],
  confluencia: ["coincidencia con tus fuentes", "coincidencias con tus fuentes"],
  resultados: ["resultados", "resultados"],
};

function desgloseDe(conteo) {
  if (!conteo) return [];
  return Object.entries(conteo)
    .filter(([tipo, n]) => n > 0 && NOMBRE_TIPO[tipo])
    .sort((a, b) => b[1] - a[1])
    .map(([tipo, n]) => `${n} ${NOMBRE_TIPO[tipo][n === 1 ? 0 : 1]}`);
}

function titularDe(tarjetas) {
  if (!tarjetas?.length) return null;
  const porTipo = [];
  for (const t of tarjetas) {
    const fila = porTipo.find((x) => x.tipo === t.tipo);
    if (fila) fila.n += 1;
    else porTipo.push({ tipo: t.tipo, n: 1 });
  }
  const principal = porTipo[0];
  const nombre = NOMBRES[principal.tipo];
  if (!nombre) return null;
  const cuantas = CANTIDAD[principal.n] || String(principal.n);
  const sujeto = principal.n === 1 ? "acción" : "acciones";
  return {
    frase: `${cuantas} ${sujeto} ${nombre[principal.n === 1 ? 0 : 1]}`,
    resto: tarjetas.length - principal.n,
  };
}

export { saludoDeLaHora, desgloseDe, titularDe, NOMBRE_TIPO };
