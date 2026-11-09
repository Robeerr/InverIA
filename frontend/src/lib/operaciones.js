/**
 * Cifras de la cartera en UN solo método, el que el usuario tiene elegido.
 *
 * InverIA calcula las posiciones con dos métodos: el de gestión (FIFO/LIFO, el de
 * Hacienda) y la media ponderada (la que enseña DEGIRO). Las dos son correctas, pero
 * miden cosas distintas, y mezclarlas en una misma pantalla da números que no cuadran
 * con nada. El interruptor «Como en DEGIRO» elige cuál se ve; estas funciones son las
 * que lo aplican, y Hoy, Cartera y Operaciones las usan todas.
 */

/** Las cifras de una fila de «Lo que tienes abierto».
 *
 *  La media ponderada se enseña ENTERA o no se enseña: si falta una pieza —basta con que
 *  una compra no tenga tipo de cambio— la fila usa el método de gestión entero y lo dice
 *  (`sinPmp`), en vez de mezclar el precio del bróker con el coste de FIFO. */
export function datosPosicion(p, comoBroker) {
  const pmpCompleta = p.ponderada?.pnl_eur != null && p.ponderada?.coste_eur != null
    && p.precio_medio_ponderado != null;
  const usaPmp = comoBroker && pmpCompleta;
  return {
    g: usaPmp ? p.ponderada : p,
    // Con el interruptor puesto se enseña el precio medio del bróker, que es un precio
    // (sin comisiones) y se mueve al vender, como en la pantalla de DEGIRO.
    precioMedio: usaPmp
      ? (p.precio_medio_degiro ?? p.precio_medio_ponderado)
      : p.precio_medio,
    invertido: usaPmp ? p.ponderada.coste_eur : p.coste_eur,
    sinPmp: comoBroker && !pmpCompleta,
    // Solo se enseña el otro precio medio cuando difiere de verdad.
    hayOtroMedio: p.precio_medio_ponderado != null
      && Math.abs(p.precio_medio_ponderado - (p.precio_medio ?? 0)) > 0.01,
  };
}

/** El Total de «Lo que tienes abierto»: la suma de las MISMAS cifras que enseñan las filas.
 *
 *  Antes el invertido del Total salía del método de gestión aunque las filas y la
 *  ganancia fueran por media ponderada, y valor − invertido no daba la ganancia. Las
 *  posiciones sin valor de hoy se cuentan aparte: sumar su coste sin su valor haría
 *  parecer que han perdido el 100 %. */
export function totalesAbiertas(posiciones, comoBroker) {
  let invertido = 0, valor = 0, ganancia = 0, sinValorar = 0;
  for (const p of posiciones || []) {
    const { g, invertido: inv } = datosPosicion(p, comoBroker);
    if (p.valor_eur == null || g.pnl_eur == null || inv == null) {
      sinValorar += 1;
      continue;
    }
    invertido += inv;
    valor += p.valor_eur;
    ganancia += g.pnl_eur;
  }
  const r2 = (x) => Math.round(x * 100) / 100;
  return {
    invertido: r2(invertido), valor: r2(valor), ganancia: r2(ganancia), sinValorar,
    pct: invertido ? (ganancia / invertido) * 100 : null,
  };
}

/** Invertido, latente y realizado de `GET /cartera/resumen` en el método elegido.
 *
 *  Si falta cualquiera de las tres ponderadas se usan las tres de gestión: medio
 *  conjunto de cada método no es de ninguno. */
export function cifrasResumen(resumen, comoBroker) {
  const r = resumen || {};
  const pondCompleta = r.invertido_ponderada_eur != null && r.latente_ponderada_eur != null
    && r.realizado_ponderada_eur != null;
  if (comoBroker && pondCompleta) {
    return { invertido: r.invertido_ponderada_eur, latente: r.latente_ponderada_eur,
      realizado: r.realizado_ponderada_eur, metodo: "media ponderada · como DEGIRO" };
  }
  return {
    invertido: r.invertido_eur ?? null, latente: r.latente_eur ?? null,
    realizado: r.realizado_eur ?? null,
    metodo: r.metodo_gestion ? `por ${r.metodo_gestion.toUpperCase()}` : null,
  };
}

/** Umbral, en %, desde el que una posición sale en «En pérdidas». Igual que el servidor. */
export const UMBRAL_PERDIDAS_PCT = -8;

/** Las posiciones en pérdidas de la portada, con las cifras del método elegido.
 *
 *  El servidor manda las que pierden en CUALQUIERA de los dos métodos, cada una con los
 *  dos juegos de cifras; aquí se queda con el elegido, se vuelve a filtrar y se enseñan
 *  las cuatro peores. */
export function perdidasSegunMetodo(atencion, comoBroker, maximo = 4) {
  return (atencion || [])
    .map((p) => {
      const pond = comoBroker && p.ponderada?.pct != null ? p.ponderada : null;
      return { ...p, pct: pond ? pond.pct : p.pct, pnl_eur: pond ? pond.pnl_eur : p.pnl_eur };
    })
    .filter((p) => p.pct != null && p.pct <= UMBRAL_PERDIDAS_PCT)
    .sort((a, b) => a.pct - b.pct)
    .slice(0, maximo);
}
