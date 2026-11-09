/* Arranque de InverIA: corre ANTES de React, en el <head>.
 *
 * Vive en un archivo y no dentro de index.html porque la política de seguridad (CSP)
 * solo deja ejecutar scripts que vengan de nuestro dominio. Un script en línea exigiría
 * permitirlos todos, que es justo lo que la CSP existe para impedir.
 */

/* Un aviso del navegador al copiar datos de rendimiento (PerformanceServerTiming) salía
   como error sin serlo. Se descarta solo ese caso. */
window.addEventListener("error", function (e) {
  if (e.error instanceof DOMException && e.error.name === "DataCloneError" && e.message
      && e.message.includes("PerformanceServerTiming")) {
    e.stopImmediatePropagation();
    e.preventDefault();
  }
}, true);

/* Tema ANTES del primer pintado. React monta unos cientos de milisegundos después de que
   el navegador pinte, así que decidirlo solo en React deja un destello blanco a pantalla
   completa al abrir la app. Mismo criterio que App.js: solo se arranca en claro si el
   usuario lo eligió alguna vez. */
(function () {
  try {
    var g = localStorage.getItem("inveria-dark");
    if (g === null || g === "1") document.documentElement.classList.add("dark");
  } catch (e) {
    document.documentElement.classList.add("dark");
  }
})();
