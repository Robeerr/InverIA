/**
 * Lecturas de la Cartera que no son cifras: el estado de una posición y de dónde sale
 * cada acción. Se sacan aquí para poder probarlas sin montar la pantalla.
 */

const num = (v) => {
  const n = Number(v);
  return v != null && v !== "" && Number.isFinite(n) && n > 0 ? n : null;
};

/* Más de un 3 % por debajo del nivel más bajo ya no es «cerca»: el precio ha
   atravesado todo tu plan de compra. Entre −3 % y −0,5 % no se afirma ninguna de las
   dos cosas y manda la tendencia. */
const MARGEN_AGOTADO = 0.03;

/** El estado de una posición en una frase.
 *
 * No hay un campo «estado» en la base de datos: sale de cruzar la tendencia con la
 * distancia a tus niveles de compra. `tendencia` la calcula el servidor (la misma que
 * usa la salud de la cartera); si no llega, se mira la de la entrada. Antes solo se
 * miraba la de la entrada, que la tabla nunca trae, y las once posiciones salían
 * «Sin datos».
 *
 * El orden importa: un veto manda sobre cualquier proximidad a un nivel, que es la
 * misma regla que aplica la ficha de la acción. Y un precio por debajo de TODOS tus
 * niveles no es una oportunidad: es un plan escrito para otros precios.
 */
export function estadoPosicion(entrada, precio, tendencia) {
  const t = (tendencia || entrada?.tendencia || "").toUpperCase();
  if (t === "BAJISTA") return { txt: "Compra vetada", tono: "text-baja" };

  const p = num(precio);
  const niveles = [1, 2, 3, 4, 5]
    .map((n) => ({ n, p: num(entrada?.[`nivel${n}`]), comprado: entrada?.[`alert_nivel${n}`] === false }))
    .filter((x) => x.p);

  if (p && niveles.length) {
    // El nivel más cercano de los que todavía no has comprado.
    const cerca = niveles
      .filter((x) => !x.comprado)
      .map((x) => ({ ...x, d: (p - x.p) / x.p }))
      .filter((x) => x.d >= -0.005 && x.d <= 0.03)
      .sort((a, b) => Math.abs(a.d) - Math.abs(b.d))[0];
    if (cerca) return { txt: `Nivel ${cerca.n} cerca`, tono: "text-marca" };

    const masBajo = Math.min(...niveles.map((x) => x.p));
    if (p < masBajo * (1 - MARGEN_AGOTADO)) {
      return {
        txt: "Bajo todos tus niveles",
        tono: "text-aviso",
        ayuda: "El precio está por debajo de todos tus niveles de compra: el plan se escribió "
          + "para otros precios. Recalcula los niveles antes de añadir.",
      };
    }
  }

  if (t === "ALCISTA") return { txt: "Tendencia intacta", tono: "text-sube" };
  if (t === "INDEFINIDA") return { txt: "Esperar", tono: "text-tinta-2" };
  return { txt: "Sin datos", tono: "text-tinta-3" };
}

/** La etiqueta de una acción en el Calendario.
 *
 * Antes toda acción de la tabla de niveles salía como «Cartera», tuvieras acciones o
 * no, y el Calendario contradecía a Hoy («ninguna de tus posiciones presenta
 * resultados»). Ahora «En cartera» solo si tienes acciones; si no, la vigilas.
 * `enCartera` es el conjunto de símbolos con acciones, o null mientras no se sabe:
 * entonces no se afirma nada.
 */
export function etiquetaCalendario(entrada, enCartera) {
  if ((entrada?.grupo || "") === "cimientos") return "Cimientos";
  if (!enCartera) return null;
  return enCartera.has((entrada?.symbol || "").toUpperCase()) ? "En cartera" : "Vigilando";
}
