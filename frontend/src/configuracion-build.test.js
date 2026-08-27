/* Lo que Vercel ejecuta de verdad.
 * ─────────────────────────────────────────────────────────────────────────────
 * Estas comprobaciones no miran código de la aplicación: miran que el despliegue
 * sea REPRODUCIBLE. Un build que resuelve las dependencias de cero cada vez puede
 * romperse solo, sin que nadie haya tocado nada, y el fallo aparece en producción
 * y no aquí — que es el peor sitio donde puede aparecer.
 */
const fs = require("fs");
const path = require("path");

const raiz = path.join(__dirname, "..");
const leer = (n) => JSON.parse(fs.readFileSync(path.join(raiz, n), "utf8"));

describe("el despliegue es reproducible", () => {
  test("Vercel instala con npm ci, que es el gestor del lock que hay en el repo", () => {
    const v = leer("vercel.json");
    // Con `yarn install` y sin yarn.lock, Vercel avisaba "No lockfile found" y resolvía
    // todo de cero, ignorando el package-lock.json del repo.
    expect(v.installCommand).toBe("npm ci");
    expect(v.installCommand).not.toMatch(/yarn/);
    expect(v.buildCommand).not.toMatch(/yarn/);
  });

  test("el lock de npm existe y es el único", () => {
    expect(fs.existsSync(path.join(raiz, "package-lock.json"))).toBe(true);
    // Dos locks de gestores distintos se desincronizan, y entonces lo que instala Vercel
    // deja de ser lo que instalas tú.
    expect(fs.existsSync(path.join(raiz, "yarn.lock"))).toBe(false);
  });

  test("package.json y package-lock.json dicen lo mismo", () => {
    // `npm ci` FALLA si no concuerdan, y falla en Vercel, no aquí. Editar una dependencia
    // sin regenerar el lock rompería el despliegue sin avisar en local.
    const pkg = leer("package.json");
    const lock = leer("package-lock.json");
    const raizLock = lock.packages[""];
    for (const campo of ["dependencies", "devDependencies", "optionalDependencies"]) {
      expect(raizLock[campo] || {}).toEqual(pkg[campo] || {});
    }
  });
});
