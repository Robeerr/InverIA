/** El título de la pestaña según la pantalla.
 *
 * Antes salía del ticker seleccionado, que empieza en AAPL: la portada, Cartera o el
 * Track record se llamaban todas «AAPL · InverIA» en la pestaña y en el historial.
 */
const NOMBRES = {
  "/": "Hoy",
  "/oportunidades": "Oportunidades",
  "/calendario": "Calendario",
  "/cartera": "Cartera",
  "/operaciones": "Operaciones",
  "/track-record": "Track record",
  "/telegram": "Telegram",
  "/intelligence": "Inteligencia",
  "/laboratorio": "Laboratorio",
  "/cerebro": "Cerebro",
  "/diagnostico": "Diagnóstico",
  "/sistema/estilos": "Estilos",
};

export function tituloDePagina(pathname) {
  const ruta = (pathname || "/").replace(/\/+$/, "") || "/";
  const accion = ruta.match(/^\/accion\/([^/]+)$/);
  if (accion) {
    // Un enlace mal escrito (`/accion/%`) haría lanzar a decodeURIComponent, y esto corre
    // por encima del ErrorBoundary: dejaría la app en blanco. Se usa el texto tal cual.
    let sym = accion[1];
    try { sym = decodeURIComponent(sym); } catch { /* se queda sin decodificar */ }
    return `${sym.toUpperCase()} · InverIA`;
  }
  const nombre = NOMBRES[ruta];
  return nombre ? `${nombre} · InverIA` : "InverIA";
}
