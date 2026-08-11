/**
 * Tu posición en una acción concreta, a partir de la cartera que ya está en memoria.
 *
 * `/signals` se pide una vez por sesión (useSignals) y se comparte entre páginas. La
 * página de acción lo tenía cargado, calculaba la entrada del símbolo abierto en un
 * `useState`… y no la leía nadie. Esto es esa función, extraída aparte para poder
 * probarla: es la que decide si el bloque «Tu posición» existe o no.
 *
 * LA REGLA: sin acciones compradas NO hay posición. Tener la acción en la tabla de
 * seguimiento con unos niveles apuntados no es tener dinero dentro, y enseñar un
 * bloque de posición vacío haría creer lo contrario.
 */

const NIVELES = ["nivel1", "nivel2", "nivel3", "nivel4", "nivel5"];

/**
 * Número utilizable, o null.
 *
 * `Number(null)` es 0 y `Number("")` también, y los dos pasan `isFinite`. Sin este
 * filtro, «no hay precio» se convertía en «el precio es 0» y la posición salía con
 * una pérdida del 100%. Ausente y cero son cosas distintas.
 */
function num(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** La fila de la cartera para este símbolo, o null. Comparación en mayúsculas. */
export function entradaDe(signals, symbol) {
  if (!Array.isArray(signals) || !symbol) return null;
  const sym = String(symbol).toUpperCase();
  return signals.find((e) => String(e?.symbol || "").toUpperCase() === sym) || null;
}

/**
 * Posición real, o `null` si no la hay.
 *
 * Devolver null y no un objeto con ceros es deliberado: quien pinta el bloque hace
 * `if (!posicion) return null` y no tiene que distinguir «no tengo» de «tengo cero».
 */
export function posicionDe(signals, symbol, precioActual) {
  const entrada = entradaDe(signals, symbol);
  if (!entrada) return null;

  const acciones = num(entrada.acciones);
  const compra = num(entrada.compra);
  if (acciones === null || acciones <= 0) return null;
  if (compra === null || compra <= 0) return null;

  const invertido = acciones * compra;

  // El precio vivo manda; `last_price` (que escribe el worker cada 60 s) es el respaldo
  // para cuando la cotización aún no ha llegado. Nunca se inventa un precio.
  const precio = num(precioActual) ?? num(entrada.last_price);

  const valor = precio != null ? acciones * precio : null;
  const plAbs = valor != null ? valor - invertido : null;
  const plPct = valor != null && invertido > 0 ? (plAbs / invertido) * 100 : null;

  // Los peldaños apuntados, con cuáles quedan por debajo del precio actual. No se
  // marca ninguno como «comprado»: la tabla guarda el precio medio, no qué nivel se
  // ejecutó, y deducirlo sería inventar.
  const niveles = NIVELES
    .map((clave, i) => ({ etiqueta: `Nivel ${i + 1}`, precio: num(entrada[clave]) }))
    .filter((n) => n.precio !== null && n.precio > 0);

  return {
    symbol: String(entrada.symbol || symbol).toUpperCase(),
    acciones,
    compra,
    invertido,
    precio,
    valor,
    plAbs,
    plPct,
    divisa: (entrada.divisa || "").toUpperCase() || null,
    niveles,
    notas: (entrada.notes || "").trim() || null,
  };
}
