// Configuración de ESLint (formato plano, ESLint 9).
//
// Por qué existe: el build de CRA compila con Babel, que NO comprueba si una variable
// existe. Se verificó midiendo: metiendo `variableQueNoExiste` a propósito en un fichero,
// `craco build` responde "Compiled successfully" y la pantalla revienta en el navegador con
// "X is not defined". Eso ya pasó una vez —un hook llamado en el componente equivocado— y
// llegó a producción con el build en verde.
//
// El objetivo es acotado a propósito: cazar los errores que ROMPEN la aplicación, no
// imponer un estilo. Una configuración estricta sobre un código que ya existe da cientos
// de avisos, se ignora, y entonces no caza nada.

const js = require("@eslint/js");
const reactHooks = require("eslint-plugin-react-hooks");
const react = require("eslint-plugin-react");

// Globales del navegador que usa la aplicación. Se listan a mano en vez de depender del
// paquete `globals` para no añadir una dependencia solo por esto.
const GLOBALES_NAVEGADOR = {
  window: "readonly", document: "readonly", navigator: "readonly",
  localStorage: "readonly", sessionStorage: "readonly",
  fetch: "readonly", Request: "readonly", Response: "readonly", Headers: "readonly",
  URL: "readonly", URLSearchParams: "readonly", Blob: "readonly", FormData: "readonly",
  FileReader: "readonly", File: "readonly",
  AbortController: "readonly", AbortSignal: "readonly",
  WebSocket: "readonly", EventSource: "readonly",
  setTimeout: "readonly", clearTimeout: "readonly",
  setInterval: "readonly", clearInterval: "readonly",
  requestAnimationFrame: "readonly", cancelAnimationFrame: "readonly",
  MutationObserver: "readonly", IntersectionObserver: "readonly", ResizeObserver: "readonly",
  console: "readonly", alert: "readonly", confirm: "readonly", prompt: "readonly",
  Image: "readonly", Audio: "readonly", CustomEvent: "readonly", Event: "readonly",
  getComputedStyle: "readonly", matchMedia: "readonly",
  process: "readonly", module: "writable", require: "readonly", __dirname: "readonly",
  structuredClone: "readonly", queueMicrotask: "readonly", performance: "readonly",
};

// Globales que inyecta Jest en los ficheros de test. Sin esto, `no-undef` marcaba
// `describe`, `test` y `expect` como identificadores inexistentes: 199 errores falsos que
// enterraban los de verdad y dejaban `npx eslint src` inservible como red de seguridad —
// que es justo lo que compensa no tener tests de render en este proyecto.
const GLOBALES_JEST = {
  describe: "readonly", test: "readonly", it: "readonly", expect: "readonly",
  beforeAll: "readonly", afterAll: "readonly", beforeEach: "readonly", afterEach: "readonly",
  jest: "readonly",
};

module.exports = [
  {
    ignores: ["build/**", "node_modules/**", "public/**", "*.config.js"],
  },
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: GLOBALES_NAVEGADOR,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { "react-hooks": reactHooks, react },
    rules: {
      ...js.configs.recommended.rules,

      // LA REGLA QUE MOTIVA ESTE FICHERO. Un identificador que no existe es siempre un
      // error en tiempo de ejecución, nunca una preferencia de estilo.
      "no-undef": "error",

      // Los hooks tienen reglas que, al saltárselas, producen fallos intermitentes muy
      // difíciles de reproducir. Como error, igual que no-undef.
      "react-hooks/rules-of-hooks": "error",
      // Las dependencias faltantes SÍ son a menudo intencionadas en este código (y están
      // comentadas donde lo son), así que aviso y no error.
      "react-hooks/exhaustive-deps": "warn",

      // Ruido sobre código que ya funciona: se avisa, no se bloquea.
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-empty": ["warn", { allowEmptyCatch: true }],
      // Sin esto, no-unused-vars marca como "sin usar" TODO componente que solo aparece
      // dentro de JSX — o sea casi todos —, y 250 avisos falsos entierran los 2 de verdad.
      "react/jsx-uses-vars": "error",
      "react/jsx-uses-react": "error",
    },
  },
  {
    // Solo se anaden los globales; las reglas de arriba siguen aplicandose igual.
    files: ["src/**/*.test.{js,jsx}"],
    languageOptions: { globals: GLOBALES_JEST },
  },
];
