/* La política de seguridad de contenido (CSP)
 * ─────────────────────────────────────────────────────────────────────────────
 * Le dice al navegador de dónde puede cargar código la web. Su valor está en que un
 * script inyectado (por ejemplo, un texto de una fuente externa que acabe pintado como
 * HTML) no se ejecute: con `script-src 'self'` solo corre lo que sale de nuestro dominio.
 *
 * Eso exige que index.html no lleve scripts en línea: o se permiten todos los scripts en
 * línea (y la CSP deja de servir para lo que importa) o no se permite ninguno.
 */
const fs = require("fs");
const path = require("path");

const raiz = path.join(__dirname, "..");
const vercel = JSON.parse(fs.readFileSync(path.join(raiz, "vercel.json"), "utf8"));
const indexHtml = fs.readFileSync(path.join(raiz, "public", "index.html"), "utf8");

function csp() {
  const cabeceras = (vercel.headers || []).flatMap((h) => h.headers || []);
  const c = cabeceras.find((h) =>
    /^Content-Security-Policy(-Report-Only)?$/.test(h.key));
  return c ? c.value : "";
}

function directiva(nombre) {
  const d = csp().split(";").map((s) => s.trim()).find((s) => s.startsWith(`${nombre} `));
  return d ? d.slice(nombre.length + 1).split(/\s+/) : null;
}

describe("CSP", () => {
  test("index.html no lleva scripts en línea", () => {
    const enLinea = indexHtml.match(/<script(?![^>]*\bsrc=)[^>]*>/g) || [];
    expect(enLinea).toEqual([]);
  });

  test("hay una política, y solo deja ejecutar scripts propios", () => {
    expect(csp()).not.toBe("");
    const script = directiva("script-src");
    expect(script).toContain("'self'");
    expect(script).not.toContain("'unsafe-inline'");
    expect(script).not.toContain("'unsafe-eval'");
  });

  test("nadie puede meter la web en un marco ni cargar plugins", () => {
    expect(directiva("frame-ancestors")).toEqual(["'none'"]);
    expect(directiva("object-src")).toEqual(["'none'"]);
  });

  test("deja hablar con el backend, también por WebSocket", () => {
    const connect = directiva("connect-src");
    expect(connect).toContain("https://inveria-backend.onrender.com");
    expect(connect).toContain("wss://inveria-backend.onrender.com");
  });
});
