import React from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { API, api } from "../lib/api";
import { cn } from "@/lib/utils";
import Boton from "@/components/base/Boton";

// El API de lib/api.js YA incluye el sufijo /api, así que las rutas van sin él.
const authHeaders = () => {
  const token = localStorage.getItem("inveria_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// Página de diagnóstico. Existe para no tener que pedirle a nadie que pegue código en la
// consola del navegador: Chrome avisa (con razón) de que eso es un vector de estafa, y no
// conviene acostumbrar a saltarse ese aviso.

/* ── Piezas de presentación ──────────────────────────────────────────────────
   Diagnóstico, rediseñado con el lenguaje de Hoy: cabecera a sangre, bloques con
   filete corrido (`iv-seccion`) en vez de cinco cajas del mismo peso, tablas de
   terminal (cifras tabulares a la derecha, rótulos en versalitas) y las acciones de
   mantenimiento como filas de una lista en vez de dieciséis chips naranjas iguales.

   Dos grupos con jerarquía: arriba lo que MIDE (solo lee), abajo lo que MANTIENE
   (algunas acciones escriben y piden confirmación; se ve en la propia fila). */

/** Cabecera de un panel: título + texto de ayuda a la izquierda, acción a la derecha. */
function CabeceraPanel({ id, titulo, children, accion }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
      <div className="min-w-0">
        <h3 id={id} className="font-heading text-cuerpo font-semibold text-tinta text-balance">
          {titulo}
        </h3>
        {children && (
          <div className="text-apoyo text-tinta-3 mt-1 max-w-[68ch] [&_b]:font-semibold [&_b]:text-tinta-2">
            {children}
          </div>
        )}
      </div>
      {accion && <div className="flex items-center gap-2 shrink-0">{accion}</div>}
    </div>
  );
}

/* Tablas de terminal: rótulos en versalitas monoespaciadas, filas con filete fino y
   cifras tabulares alineadas a la derecha. `overflow-x-auto` en el envoltorio: en
   móvil una tabla de cinco columnas se desplaza dentro de su panel, no lo rompe. */
const TABLA = "w-full text-apoyo border-collapse";
const TH = "iv-etiqueta font-normal text-left py-2 pr-3 border-b border-linea-fuerte whitespace-nowrap";
const TH_NUM = "iv-etiqueta font-normal text-right py-2 pl-3 border-b border-linea-fuerte whitespace-nowrap";
const TR = "border-b border-linea last:border-b-0";
const TD = "py-1.5 pr-3 text-tinta-2";
const TD_NUM = "iv-cifra text-right py-1.5 pl-3 whitespace-nowrap";

/** Bloque de resultado que aparece tras pulsar: entra con un fundido corto (nada si se
 *  ha pedido reducir el movimiento) para que se note que algo ha llegado. */
const APARECE = "motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-top-1 " +
  "motion-safe:duration-200";

function AvisoError({ children, className }) {
  return (
    <p role="alert"
       className={cn("rounded-iv-sm border border-baja/30 bg-baja/5 px-3 py-2 text-apoyo text-baja",
         "break-words", className)}>
      {children}
    </p>
  );
}

/** Lista de acciones de mantenimiento. Cada acción es una fila pulsable a todo el ancho:
 *  más fácil de acertar en el móvil que un chip, y con sitio para decir a la derecha si
 *  la acción pide confirmación (las que escriben o gastan llamadas al modelo). */
function ListaAcciones({ acciones, ocupada, onLanzar }) {
  return (
    <ul className="mt-4 grid sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2 sm:gap-x-6 border-t border-linea">
      {acciones.map((a) => {
        const enCurso = ocupada === a.id;
        return (
          <li key={a.id} className="border-b border-linea min-w-0">
            <button
              type="button"
              onClick={() => onLanzar(a)}
              disabled={ocupada !== null}
              aria-busy={enCurso || undefined}
              className={cn(
                "group w-[calc(100%+1rem)] min-h-[44px] flex items-center justify-between gap-3 -mx-2 px-2 py-2",
                "rounded-iv-sm text-left text-apoyo text-tinta",
                // Color al pasar por encima y un leve hundimiento al pulsar: la fila confirma
                // que ha oído el clic antes de que llegue el «Ejecutando…».
                "transition-[color,background-color,transform] duration-150 ease-out active:scale-[0.99]",
                "motion-reduce:transition-none motion-reduce:active:scale-100",
                "hover:bg-superficie-alt hover:text-marca",
                "disabled:cursor-not-allowed disabled:active:scale-100",
                "disabled:hover:bg-transparent disabled:hover:text-tinta",
                ocupada !== null && !enCurso && "opacity-50",
              )}
            >
              <span className="min-w-0 break-words">
                {enCurso ? <span className="text-marca">Ejecutando…</span> : a.texto}
              </span>
              <span className="flex items-center gap-2 shrink-0 text-tinta-3">
                {a.confirmar && !enCurso && (
                  <span className="text-etiqueta text-tinta-3">pide confirmación</span>
                )}
                {enCurso ? (
                  <Loader2 className="w-3.5 h-3.5 text-marca animate-spin motion-reduce:animate-none"
                           aria-hidden="true" />
                ) : (
                  <ChevronRight
                    className="w-3.5 h-3.5 transition-transform duration-150 ease-out
                               group-hover:translate-x-0.5 group-hover:text-marca
                               group-disabled:translate-x-0 motion-reduce:transition-none"
                    aria-hidden="true" />
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Lo que devuelve una acción de mantenimiento: la respuesta tal cual, en JSON. */
function ResultadoAccion({ resultado }) {
  return (
    <div className={cn("mt-4", APARECE)} role="status">
      <p className="text-etiqueta text-tinta-3 mb-1.5">
        Resultado · <span className="text-tinta-2">{resultado.accion}</span>
      </p>
      <pre className="iv-cifra text-etiqueta leading-relaxed text-tinta-2 bg-fondo border border-linea
                      rounded-iv-sm p-3 overflow-auto max-h-64">
        {JSON.stringify(resultado.datos, null, 2)}
      </pre>
    </div>
  );
}

// Mide la carga de la PROPIA web usando la API de rendimiento del navegador. Es la medida
// que importa: la hace tu navegador, en tu conexión, con tu caché. Compilar el proyecto en
// otro sitio solo diría cuánto PESA, no cuánto TARDAS tú.
function VelocidadWeb() {
  const [d, setD] = React.useState(null);

  const medir = () => {
    const recursos = performance.getEntriesByType("resource");
    const nav = performance.getEntriesByType("navigation")[0];
    const porTipo = {};
    let total = 0, sinComprimir = 0;
    for (const r of recursos) {
      // transferSize = lo que viajó por la red (0 si vino de caché).
      const tipo = r.name.match(/\.js(\?|$)/) ? "JavaScript"
        : r.name.match(/\.css(\?|$)/) ? "CSS"
        : r.name.match(/fonts?\.|\.woff/) ? "Tipografías"
        : r.initiatorType === "fetch" || r.initiatorType === "xmlhttprequest" ? "Datos (API)"
        : "Otros";
      porTipo[tipo] = porTipo[tipo] || { n: 0, kb: 0, ms: 0 };
      porTipo[tipo].n++;
      porTipo[tipo].kb += (r.transferSize || 0) / 1024;
      porTipo[tipo].ms = Math.max(porTipo[tipo].ms, Math.round(r.duration));
      total += (r.transferSize || 0);
      sinComprimir += (r.decodedBodySize || 0);
    }
    setD({
      recursos: recursos.length,
      totalKb: Math.round(total / 1024),
      sinComprimirKb: Math.round(sinComprimir / 1024),
      porTipo: Object.entries(porTipo).sort((a, b) => b[1].kb - a[1].kb),
      cargaMs: nav ? Math.round(nav.duration) : null,
      hastaInteractivo: nav ? Math.round(nav.domInteractive) : null,
    });
  };

  return (
    <section className="iv-panel p-4 sm:p-5 min-w-0" aria-labelledby="diag-web">
      <CabeceraPanel
        id="diag-web"
        titulo="Velocidad de la web"
        accion={
          <Boton tamano="sm" onClick={medir}>
            Medir esta página
          </Boton>
        }
      >
        <p>
          Lo mide tu navegador, en tu conexión. <b>Mide lo que se haya cargado en ESTA visita</b>,
          así que para ver el peso del Dashboard: entra en el Dashboard, abre una acción, y
          luego ven aquí <b>sin recargar</b> (por el menú) y pulsa Medir. Si recargas estando
          en esta página solo medirás esta página, que es de las ligeras.
        </p>
      </CabeceraPanel>

      {d && (
        <div className={cn("mt-5 pt-4 border-t border-linea", APARECE)}>
          {/* Las dos cifras de la medida, en grande y lado a lado: es lo que se viene a ver. */}
          <dl className="flex flex-wrap gap-x-8 gap-y-3 mb-4">
            <div className="min-w-0">
              <dt className="iv-etiqueta">Descargado</dt>
              <dd className="iv-cifra text-titulo font-semibold text-tinta mt-1 whitespace-nowrap">
                {d.totalKb} KB{" "}
                <span className="text-apoyo font-normal text-tinta-3">en {d.recursos} ficheros</span>
              </dd>
            </div>
            {d.cargaMs != null && (
              <div className="min-w-0">
                <dt className="iv-etiqueta">Carga total</dt>
                <dd className="iv-cifra text-titulo font-semibold text-tinta mt-1 whitespace-nowrap">
                  {d.cargaMs} ms
                </dd>
              </div>
            )}
          </dl>
          <div className="overflow-x-auto">
            <table className={TABLA}>
              <thead><tr>
                <th scope="col" className={TH}>Tipo</th>
                <th scope="col" className={TH_NUM}>Ficheros</th>
                <th scope="col" className={TH_NUM}>KB</th>
                <th scope="col" className={TH_NUM}>El más lento (ms)</th>
              </tr></thead>
              <tbody>
                {d.porTipo.map(([t, v]) => (
                  <tr key={t} className={TR}>
                    <td className={TD}>{t}</td>
                    <td className={cn(TD_NUM, "text-tinta-2")}>{v.n}</td>
                    <td className={cn(TD_NUM, "font-semibold text-tinta")}>{Math.round(v.kb)}</td>
                    <td className={cn(TD_NUM, "text-tinta-2")}>{v.ms}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-etiqueta text-tinta-3 mt-3 leading-snug max-w-[72ch]">
            Referencia: por debajo de 1.000 KB de JavaScript es sano; por encima de 2.000 KB
            la culpa de la lentitud es del tamaño. Si sale 0 KB, vino todo de caché: recarga
            con Ctrl+Shift+R y vuelve a medir.
          </p>
        </div>
      )}
    </section>
  );
}


/* Mantenimiento del Cerebro.
   ─────────────────────────────────────────────────────────────────────────────
   Estas operaciones se lanzaban tocando un enlace con el secreto INBOUND_SECRET
   dentro de la URL. Cómodo desde el móvil, pero el secreto acababa en el historial
   del navegador, en el log de cualquier proxy y en la cabecera Referer — y ese
   secreto no caduca ni se rota solo.

   Ahora van con la sesión normal, como el resto de la app: en el móvil ya estás
   dentro, así que se pierde comodidad cero y el secreto desaparece de la URL. */
function MantenimientoCerebro() {
  const [ocupada, setOcupada] = React.useState(null);
  const [resultado, setResultado] = React.useState(null);
  const [fallo, setFallo] = React.useState(null);

  const ACCIONES = [
    { id: "estado", texto: "Ver estado del Cerebro", fn: api.mantenimiento.estado },
    { id: "diagnostico", texto: "Diagnóstico de ingesta", fn: api.mantenimiento.diagnostico },
    { id: "noticias", texto: "Ingerir noticias ahora", fn: api.mantenimiento.ingerirNoticias },
    // Sin confirmación: solo lee el catálogo de Google. No cambia el modelo — cambiarlo
    // es poner GEMINI_MODEL en el entorno, a mano y a propósito.
    { id: "modelo", texto: "¿Hay un Gemini más nuevo?", fn: api.mantenimiento.comprobarModelo },
    // Sin confirmación: solo RELLENA huecos, nunca pisa lo que ya está escrito.
    { id: "fichas", texto: "Completar fichas de la Cartera", fn: api.mantenimiento.completarFichas },
    { id: "reprocesar", texto: "Reprocesar correos guardados", fn: () => api.mantenimiento.reprocesar(200),
      confirmar: "Reprocesará los últimos 200 correos con una llamada al modelo por cada uno. Tarda minutos y consume cuota. ¿Seguir?" },
    { id: "acentos", texto: "Reparar acentos", fn: api.mantenimiento.repararAcentos,
      confirmar: "Reescribirá los principios con acentos corruptos. ¿Seguir?" },
    // Las dos de fusión MODIFICAN principios de forma irreversible: piden confirmación
    // con el efecto escrito, no un "¿estás seguro?" que nadie lee.
    { id: "fusionar", texto: "Fusionar principios casi idénticos", fn: api.mantenimiento.fusionarPrincipios,
      confirmar: "Fusionará principios casi idénticos del Cerebro. NO se puede deshacer. ¿Seguir?" },
    { id: "fusionar-ia", texto: "Fusionar con IA (entiende paráfrasis)", fn: api.mantenimiento.fusionarPrincipiosIA,
      confirmar: "Fusión semántica con el modelo: entiende paráfrasis, tarda varios minutos y NO se puede deshacer. ¿Seguir?" },
  ];

  const lanzar = async (accion) => {
    if (accion.confirmar && !window.confirm(accion.confirmar)) return;
    setOcupada(accion.id); setFallo(null); setResultado(null);
    try {
      setResultado({ accion: accion.texto, datos: await accion.fn() });
    } catch (e) {
      setFallo(e?.response?.data?.detail || e?.message || "Error desconocido");
    } finally {
      setOcupada(null);
    }
  };

  return (
    <section className="iv-panel p-4 sm:p-5 min-w-0" aria-labelledby="diag-cerebro">
      <CabeceraPanel id="diag-cerebro" titulo="Mantenimiento del Cerebro">
        <p>Antes se lanzaban desde un enlace con el secreto en la URL. Ahora usan tu sesión.</p>
      </CabeceraPanel>
      <ListaAcciones acciones={ACCIONES} ocupada={ocupada} onLanzar={lanzar} />
      {fallo && <AvisoError className="mt-4">{fallo}</AvisoError>}
      {resultado && <ResultadoAccion resultado={resultado} />}
    </section>
  );
}

/** Guarda `datos` como un fichero JSON en el ordenador. */
function descargarJSON(datos, nombre) {
  const blob = new Blob([JSON.stringify(datos, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* Auditoría de la Inteligencia. Está AQUÍ, entre las herramientas, y no en la pantalla de
   investigación, que no cambia. Exportar y ver no escriben nada. Congelar el banco guarda
   los 20 casos en su propia colección una sola vez; ejecutarlo gasta llamadas al modelo.
   Ninguna de las dos toca las investigaciones ni el presupuesto diario. */
function AuditoriaInteligencia() {
  const [ocupada, setOcupada] = React.useState(null);
  const [resultado, setResultado] = React.useState(null);
  const [fallo, setFallo] = React.useState(null);
  const hoy = () => new Date().toISOString().slice(0, 10);

  const ACCIONES = [
    { id: "exportar", texto: "Exportar investigaciones (JSON)",
      fn: async () => {
        const d = await api.intelligence.exportarInvestigaciones();
        descargarJSON(d, `inveria-investigaciones-${hoy()}.json`);
        return { descargado: true, total: d.total, con_traza: d.con_traza };
      } },
    { id: "fallos", texto: "Ver intentos fallidos", fn: () => api.intelligence.intentos(true) },
    { id: "banco", texto: "Ver el banco de pruebas", fn: api.intelligence.banco },
    { id: "congelar", texto: "Congelar el banco (20 casos)", fn: api.intelligence.congelarBanco,
      confirmar: "Re-descargará de la SEC los documentos de los 20 casos y los guardará aparte. "
        + "No toca las investigaciones y solo se hace una vez. ¿Seguir?" },
    { id: "exportar-banco", texto: "Exportar el banco (JSON)",
      fn: async () => {
        const d = await api.intelligence.exportarBanco();
        descargarJSON(d, `inveria-banco-${hoy()}.json`);
        return { descargado: true, casos: d.casos?.length };
      } },
    { id: "ejecutar", texto: "Ejecutar el banco con la versión de producción",
      fn: () => api.intelligence.ejecutarBanco("produccion"),
      confirmar: "Hará hasta 20 llamadas al modelo con los 20 casos. No toca las "
        + "investigaciones ni el presupuesto diario. El resultado sale en «Ver ejecuciones». ¿Seguir?" },
    { id: "ejecuciones", texto: "Ver ejecuciones del banco", fn: api.intelligence.ejecucionesBanco },
  ];

  const lanzar = async (accion) => {
    if (accion.confirmar && !window.confirm(accion.confirmar)) return;
    setOcupada(accion.id); setFallo(null); setResultado(null);
    try {
      setResultado({ accion: accion.texto, datos: await accion.fn() });
    } catch (e) {
      setFallo(e?.response?.data?.detail || e?.message || "Error desconocido");
    } finally {
      setOcupada(null);
    }
  };

  return (
    <section className="iv-panel p-4 sm:p-5 min-w-0" data-testid="auditoria-inteligencia"
             aria-labelledby="diag-auditoria">
      <CabeceraPanel id="diag-auditoria" titulo="Auditoría de la Inteligencia">
        <p>
          Exporta las investigaciones con su traza y gestiona el banco de pruebas de 20 casos.
          Nada de esto cambia cómo se investiga.
        </p>
      </CabeceraPanel>
      <ListaAcciones acciones={ACCIONES} ocupada={ocupada} onLanzar={lanzar} />
      {fallo && <AvisoError className="mt-4">{String(fallo)}</AvisoError>}
      {resultado && <ResultadoAccion resultado={resultado} />}
    </section>
  );
}

/** Subtabla de «Velocidad de carga»: fase o panel · ms · estado. */
function SubtablaMs({ titulo, nota, filas, clave }) {
  return (
    <div className="mt-5 min-w-0">
      <p className="text-apoyo font-semibold text-tinta mb-1">
        {titulo}
        <span className="font-normal text-tinta-3"> · {nota}</span>
      </p>
      <div className="overflow-x-auto">
        <table className={TABLA}>
          <tbody>
            {filas.map((f) => (
              <tr key={f[clave]} className={TR}>
                <td className={TD}>{f[clave]}</td>
                <td className={cn(TD_NUM, "font-semibold text-tinta w-20")}>{f.ms}</td>
                <td className="py-1.5 pl-4 text-tinta-3">{f.estado}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function DiagnosticoView() {
  const [ticker, setTicker] = React.useState("AAPL");
  const [carga, setCarga] = React.useState(null);
  const [estudio, setEstudio] = React.useState(null);
  const [cargando, setCargando] = React.useState(null);
  const [error, setError] = React.useState(null);

  const pedir = async (ruta, set, etiqueta) => {
    setCargando(etiqueta); setError(null);
    try {
      const r = await fetch(`${API}${ruta}`, { headers: authHeaders() });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `Error ${r.status}`);
      set(d);
    } catch (e) { setError(e.message); }
    finally { setCargando(null); }
  };

  const tono = (v) => v === "rápido" ? "text-sube" : v === "LENTO" ? "text-baja" : "text-aviso";

  return (
    <div className="space-y-8">
      <header className="iv-veredicto">
        <h1 className="iv-verbo text-tinta">Diagnóstico</h1>
        <p className="text-cuerpo text-tinta-2 mt-3 max-w-[58ch]">
          Mide de dónde viene la lentitud y contrasta la idea del RSI con datos reales.
        </p>
      </header>

      {/* ── Medir: solo lee. Las dos velocidades lado a lado en escritorio. ── */}
      <section aria-labelledby="diag-medir">
        <div className="iv-seccion iv-seccion-acento">
          <h2 id="diag-medir" className="iv-etiqueta">Velocidad</h2>
        </div>
        <div className="grid gap-4 lg:grid-cols-2 items-start">
          <VelocidadWeb />

          {/* ── Velocidad de carga ── */}
          <section className="iv-panel p-4 sm:p-5 min-w-0" aria-labelledby="diag-carga">
            <CabeceraPanel id="diag-carga" titulo="Velocidad de carga">
              <p>
                Cronometra cada fuente por separado, sin caché: es el peor caso, el de abrir un
                ticker por primera vez.
              </p>
            </CabeceraPanel>
            <div className="flex flex-wrap items-center gap-2 mt-4">
              <label htmlFor="diag-ticker" className="sr-only">Ticker a medir</label>
              <input id="diag-ticker" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())}
                     autoComplete="off" spellCheck={false}
                     className="iv-cifra h-8 w-28 rounded-full border border-linea-fuerte bg-fondo px-3.5
                                text-apoyo font-semibold text-tinta placeholder:text-tinta-3
                                transition-colors duration-150 hover:border-tinta-3
                                motion-reduce:transition-none" />
              <Boton tamano="sm" onClick={() => pedir(`/diagnostico/carga/${ticker}`, setCarga, "carga")}
                     ocupado={cargando === "carga"}>
                {cargando === "carga" && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                )}
                {cargando === "carga" ? "Midiendo…" : "Medir"}
              </Boton>
            </div>
            {carga && (
              <div className={cn("mt-5 pt-4 border-t border-linea", APARECE)}>
                {/* La cifra que contesta a "¿va rápido?". Va la primera y destacada porque el
                    "Total" de abajo mide otra cosa —el coste de las fuentes SIN caché— y
                    leerlo como si fuera el tiempo de carga lleva a la conclusión contraria:
                    todo lo que consiste en dejar de repetir trabajo es invisible ahí. */}
                {carga.experiencia_real && (
                  <div className="mb-4">
                    <p className="iv-etiqueta">Lo que tardas tú al elegir esta acción</p>
                    <p className="mt-1.5 flex flex-wrap items-baseline gap-x-2">
                      <span className="iv-cifra text-cifra font-bold text-tinta whitespace-nowrap">
                        {carga.experiencia_real.ms} ms
                      </span>
                      <span className={`text-apoyo font-semibold ${tono(
                        carga.experiencia_real.ms < 300 ? "rápido"
                          : carga.experiencia_real.ms < 1500 ? "aceptable" : "LENTO")}`}>
                        · {carga.experiencia_real.ms < 300 ? "instantáneo"
                            : carga.experiencia_real.ms < 1500 ? "rápido" : "lento"}
                      </span>
                    </p>
                    <p className="text-etiqueta text-tinta-3 mt-1 max-w-[72ch]">{carga.experiencia_real.nota}</p>
                  </div>
                )}
                <p className="text-apoyo text-tinta-2 mb-2">
                  Coste de las fuentes sin caché:{" "}
                  <b className="iv-cifra font-semibold text-tinta whitespace-nowrap">{carga.total_ms} ms</b>{" "}
                  <span className={`font-semibold ${tono(carga.veredicto)}`}>· {carga.veredicto}</span>
                </p>
                <div className="overflow-x-auto">
                  <table className={TABLA}>
                    <thead><tr>
                      <th scope="col" className={TH}>Fuente</th>
                      <th scope="col" className={TH_NUM}>ms</th>
                      <th scope="col" className={cn(TH, "pl-4 pr-0")}>Estado</th>
                    </tr></thead>
                    <tbody>
                      {carga.por_fuente.map((f) => (
                        <tr key={f.fuente} className={TR}>
                          <td className={TD}>{f.fuente}</td>
                          <td className={cn(TD_NUM, "font-semibold text-tinta w-20")}>{f.ms}</td>
                          <td className="py-1.5 pl-4 text-tinta-3">{f.estado}{f.detalle ? ` · ${f.detalle}` : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {carga.desglose_cotizacion && (
                  <SubtablaMs titulo="Dentro de la cotización (la lenta)"
                              nota={carga.desglose_cotizacion.rama}
                              filas={carga.desglose_cotizacion.fases} clave="fase" />
                )}
                {carga.paneles_al_cambiar_de_accion && (
                  <SubtablaMs titulo="Paneles que se cargan solos al cambiar de acción"
                              nota={`suman ${carga.total_paneles_ms} ms`}
                              filas={carga.paneles_al_cambiar_de_accion} clave="fuente" />
                )}
                {carga.cuota_finnhub && (
                  <p className={cn("text-apoyo mt-4 pt-3 border-t border-linea",
                    carga.cuota_finnhub.saturado ? "text-baja font-semibold" : "text-tinta-3")}>
                    Cuota de datos:{" "}
                    <span className="iv-cifra">{carga.cuota_finnhub.usadas_ultimo_minuto}</span> de{" "}
                    <span className="iv-cifra">{carga.cuota_finnhub.tope_total}</span> en el último minuto ·{" "}
                    <b className={carga.cuota_finnhub.saturado ? "" : "text-tinta-2"}>
                      <span className="iv-cifra">{carga.cuota_finnhub.libres_para_ti}</span> libres
                    </b> para navegar
                    {carga.cuota_finnhub.saturado
                      ? " · SATURADA: esto SÍ te ralentiza"
                      : carga.cuota_finnhub.fondo_frenado
                        ? " · las tareas de fondo van más lentas para dejarte sitio (normal)"
                        : ""}
                  </p>
                )}
              </div>
            )}
          </section>
        </div>
      </section>

      {/* ── Estudio del RSI ── */}
      <section aria-labelledby="diag-estudio">
        <div className="iv-seccion">
          <h2 id="diag-estudio" className="iv-etiqueta">Estudio</h2>
        </div>
        <section className="iv-panel p-4 sm:p-5 min-w-0" aria-labelledby="diag-rsi">
          <CabeceraPanel
            id="diag-rsi"
            titulo="¿Sube siempre el S&P tras un RSI por debajo de 30?"
            accion={
              <Boton tamano="sm" onClick={() => pedir("/estudio/rsi-sobreventa", setEstudio, "estudio")}
                     ocupado={cargando === "estudio"}>
                {cargando === "estudio" && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                )}
                {cargando === "estudio" ? "Calculando… (tarda unos segundos)" : "Calcular"}
              </Boton>
            }
          >
            <p>
              Con datos hasta hoy. Compara con comprar un día cualquiera: si el índice sube el
              70% de las veces igualmente, un 70% tras la señal no demuestra nada.
            </p>
          </CabeceraPanel>
          {estudio && !estudio.error && (
            <div className={cn("mt-5 pt-4 border-t border-linea", APARECE)}>
              <p className="iv-cifra text-etiqueta text-tinta-3 mb-2">
                {estudio.desde} → {estudio.hasta} · {estudio.episodios} episodios
              </p>
              <div className="overflow-x-auto">
                <table className={TABLA}>
                  <thead><tr>
                    <th scope="col" className={TH}>Horizonte</th>
                    <th scope="col" className={TH_NUM}>Tras RSI&lt;30</th>
                    <th scope="col" className={TH_NUM}>Día cualquiera</th>
                    <th scope="col" className={TH_NUM}>Sobre SMA200</th>
                    <th scope="col" className={TH_NUM}>Peor caso</th>
                  </tr></thead>
                  <tbody>
                    {Object.keys(estudio.tras_sobreventa).map((h) => (
                      <tr key={h} className={TR}>
                        <td className={cn(TD, "iv-cifra whitespace-nowrap")}>{h}</td>
                        <td className={cn(TD_NUM, "font-semibold text-tinta")}>{estudio.tras_sobreventa[h].subio_pct}%</td>
                        <td className={cn(TD_NUM, "text-tinta-3")}>{estudio.dia_cualquiera[h]?.subio_pct}%</td>
                        <td className={cn(TD_NUM, "text-sube")}>{estudio.sobre_sma200[h]?.subio_pct ?? "—"}%</td>
                        <td className={cn(TD_NUM, "text-baja")}>{estudio.tras_sobreventa[h].peor}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {estudio.aviso_independencia && (
                <p className="text-etiqueta text-tinta-3 mt-3 leading-snug max-w-[72ch]">{estudio.aviso_independencia}</p>
              )}
            </div>
          )}
          {estudio?.error && <AvisoError className="mt-4">{estudio.error}</AvisoError>}
        </section>

        {/* El fallo de «Medir» o «Calcular»: justo debajo de los dos bloques que lo
            pueden provocar, no al pie de la página, donde no se veía. */}
        {error && <AvisoError className="mt-4">{error}</AvisoError>}
      </section>

      {/* ── Mantener: algunas acciones escriben; las que lo hacen piden confirmación. ── */}
      <section aria-labelledby="diag-mantener">
        <div className="iv-seccion">
          <h2 id="diag-mantener" className="iv-etiqueta">Mantenimiento</h2>
        </div>
        <div className="grid gap-4 lg:grid-cols-2 items-start">
          <MantenimientoCerebro />

          <AuditoriaInteligencia />
        </div>
      </section>
    </div>
  );
}
