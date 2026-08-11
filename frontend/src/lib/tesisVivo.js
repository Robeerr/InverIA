import { fmtPrice, fmtPct } from "./format";

/**
 * El titular de la tesis, con el precio del momento.
 *
 * EL PROBLEMA QUE RESUELVE
 *
 * La cabecera se actualiza tick a tick por WebSocket y la tesis venía del dashboard, que
 * se cachea 15 min y se sirve caducado hasta 30. En AMD eso se veía así: cabecera
 * $468.96, y justo debajo «AMD cotiza a 468.34». Dos precios de la misma acción en la
 * misma pantalla, que es exactamente lo que la regla de fuente única prohíbe.
 *
 * QUÉ HACE Y QUÉ NO
 *
 * El backend manda la frase ya escrita (`titular`) y, además, la misma frase con dos
 * huecos (`titular_plantilla`) y qué va en cada uno (`titular_huecos`). Aquí SOLO se
 * rellenan esos huecos con la cotización viva. No se redacta, no se reordena, no se
 * decide qué entra en la frase y no se recalcula ningún indicador: todo eso sigue en
 * `tesis.py`.
 *
 * Lo que deliberadamente NO se toca son los juicios derivados del precio —«por encima de
 * su media de 200 sesiones», «a 1,2% de su máximo anual»—. Recalcularlos con cada tick
 * sería mover lógica de negocio al navegador. Se quedan como los calculó el servidor, y
 * el sello de antigüedad del bloque dice de cuándo son.
 *
 * LA FUENTE DE VERDAD es el `quote` compuesto de `Dashboard.jsx`
 * (`{...datos.quote, ...parche.quote}`), el MISMO objeto que recibe `QuoteHeader`. Si se
 * le pasara otro, volveríamos a tener dos precios.
 */

/** Qué campo del quote vivo alimenta cada hueco. */
const CAMPOS_VIVOS = {
  "quote.price": (q) => q?.price,
  "quote.change_percent": (q) => q?.change_percent,
};

function formatear(valor, formato) {
  if (valor == null) return null;
  if (formato === "precio") return fmtPrice(valor);
  if (formato === "pct_signo") return fmtPct(valor);
  return String(valor);
}

export function titularVivo(tesis, quote) {
  if (!tesis) return "";
  const plantilla = tesis.titular_plantilla;
  const huecos = tesis.titular_huecos;

  // Sin plantilla —una respuesta anterior a este cambio, servida desde caché— se usa la
  // frase tal cual vino. Nunca se intenta reconstruirla a mano.
  if (!plantilla || !huecos) return tesis.titular || "";

  return plantilla.replace(/\{(\w+)\}/g, (completo, clave) => {
    const hueco = huecos[clave];
    if (!hueco) return completo;

    // El valor vivo manda; si no hay tick, el que trajo el servidor. Nunca se inventa uno
    // ni se deja el hueco a la vista.
    const leer = CAMPOS_VIVOS[hueco.campo_origen];
    const vivo = leer ? leer(quote) : null;
    const valor = vivo == null ? hueco.valor : vivo;
    return formatear(valor, hueco.formato) ?? completo;
  });
}
