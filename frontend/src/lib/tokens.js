/**
 * Leer un token de color desde JavaScript.
 *
 * POR QUÉ HACE FALTA
 *
 * Casi toda la app pinta con clases de Tailwind, que resuelven los tokens solas. El
 * gráfico no: `lightweight-charts` dibuja sobre un lienzo y su API recibe cadenas de
 * color, no clases. Por eso sus colores estaban escritos a mano en dos versiones
 * (`dark ? "#0e1f1a" : "#ffffff"`), que es la duplicación que la capa de tokens existe
 * para eliminar.
 *
 * FORMATO
 *
 * Los tokens se declaran como tripletes sin función —`--iv-sube: 47 107 69`— para que
 * Tailwind pueda componer opacidades. Aquí hay que envolverlos en `rgb()`, y se usa la
 * forma con comas: `rgb(47, 107, 69)`. La separada por espacios es CSS Color 4 y los
 * navegadores modernos la entienden, pero el lienzo la ha soportado más tarde y no hay
 * ninguna ventaja en arriesgarse.
 *
 * RESPALDOS
 *
 * `getComputedStyle` puede devolver vacío si se llama antes de que la hoja de estilos
 * esté aplicada. Un color vacío no es un color feo: es un color inválido, y el gráfico
 * se queda sin dibujar esa serie. Por eso cada token tiene respaldo.
 *
 * Los respaldos son los valores del tema CLARO, que es el que declara `:root`. Están
 * repetidos de `tokens.css` a propósito y un test los compara con el fichero, igual que
 * se hace con `.iv-oscuro`: la duplicación se vigila, no se esconde.
 */

export const RESPALDOS = {
  "--iv-fondo": "245 243 239",
  "--iv-superficie": "255 255 255",
  "--iv-superficie-2": "250 248 244",
  "--iv-linea": "229 224 216",
  "--iv-linea-fuerte": "176 166 146",
  "--iv-tinta": "14 31 26",
  "--iv-tinta-2": "70 86 79",
  "--iv-tinta-3": "92 107 102",
  "--iv-marca": "26 58 50",
  "--iv-sube": "47 107 69",
  "--iv-baja": "192 68 42",
  "--iv-aviso": "138 101 8",
  "--iv-info": "26 106 148",
};

/**
 * Devuelve el token `nombre` como `rgb(r, g, b)`.
 *
 * Se lee del elemento raíz, que es donde viven `:root` y `.dark`, así que el valor que
 * sale es el del tema activo en ese momento. Quien necesite reaccionar a un cambio de
 * tema tiene que volver a llamar: esta función no observa nada.
 */
export function leerToken(nombre, respaldo) {
  let valor = "";
  try {
    valor = getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
  } catch {
    valor = "";
  }
  if (!valor) valor = respaldo || RESPALDOS[nombre] || "0 0 0";
  const canales = valor.split(/[\s,]+/).filter(Boolean).slice(0, 3);
  // Un token a medias tampoco sirve: mejor el respaldo que un `rgb(47, 107)` inválido.
  if (canales.length < 3) return `rgb(${(RESPALDOS[nombre] || "0 0 0").split(/\s+/).join(", ")})`;
  return `rgb(${canales.join(", ")})`;
}
