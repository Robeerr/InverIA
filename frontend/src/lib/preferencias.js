/**
 * Preferencias de pantalla que comparten varias vistas.
 *
 * «Como en DEGIRO» decide si las cifras de la cartera se enseñan por media ponderada —el
 * método del bróker— o por el método de gestión (FIFO/LIFO). Lo leen Operaciones y la
 * portada. Antes solo lo leía Operaciones, y la portada enseñaba LIFO al lado: parecía
 * que los números no cuadraban cuando solo estaban repartidos de otra forma.
 *
 * Un solo nombre de clave para las dos: si cada vista escribiera la suya, una errata
 * bastaría para que volvieran a enseñar métodos distintos sin decirlo.
 */
export const CLAVE_COMO_BROKER = "ventas.comoBroker";

export function leerComoBroker() {
  try {
    return window.localStorage.getItem(CLAVE_COMO_BROKER) === "1";
  } catch {
    return false;   // modo privado: sin preferencia guardada, el método de gestión
  }
}

export function guardarComoBroker(valor) {
  try {
    window.localStorage.setItem(CLAVE_COMO_BROKER, valor ? "1" : "0");
  } catch {
    /* modo privado: la preferencia vive solo mientras dura la pestaña */
  }
}
