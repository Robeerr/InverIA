import React from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import {
  ChartBar,
  House, Lightning, MagnifyingGlass, Bell, Coins, CalendarBlank,
  ChartLineUp, Brain, Broadcast, Stethoscope, TelegramLogo, Palette, X, Flask,
} from "@phosphor-icons/react";

/**
 * Navegación lateral persistente. Sustituye a la fila de siete iconos de la barra.
 *
 * POR QUÉ UN RAIL Y NO UNA BARRA
 *
 * La barra tenía siete entradas planas y, por debajo de 1400px, se quedaba en siete
 * iconos SIN etiqueta. Eso no es navegación: es un examen de memoria. Y siete destinos
 * con el mismo peso no dicen nada sobre a qué vienes.
 *
 * LOS TRES GRUPOS SON LA JERARQUÍA
 *
 *   Decidir    → a lo que abres la aplicación.
 *   Gestionar  → lo que ya tienes y hay que mantener.
 *   Entender   → lo que se consulta, no lo que se opera.
 *
 * Y las herramientas —diagnóstico, Telegram, la guía de estilos— bajan al pie, que es
 * donde deben estar: antes solo se llegaba a ellas escribiendo la URL a mano.
 *
 * LEY 1 · EL NARANJA NO DECORA
 *
 * En el rail aparece en dos sitios y nada más: el icono del logotipo y el ítem activo.
 * Ni los grupos ni el hover. Si el naranja señalara muchas cosas dejaría de señalar
 * ninguna.
 */

const GRUPOS = [
  {
    titulo: "Decidir",
    items: [
      { to: "/", label: "Hoy", icon: House, testId: "nav-hoy" },
      { to: "/oportunidades", label: "Oportunidades", icon: Lightning, testId: "nav-opportunities" },
      { to: "/oportunidades?modo=screener", label: "Screener", icon: MagnifyingGlass, testId: "nav-screener" },
    ],
  },
  {
    titulo: "Gestionar",
    items: [
      { to: "/cartera", label: "Cartera", icon: Bell, testId: "nav-signals" },
      { to: "/operaciones", label: "Operaciones", icon: Coins, testId: "nav-ventas" },
      { to: "/calendario", label: "Calendario", icon: CalendarBlank, testId: "nav-calendar" },
    ],
  },
  {
    titulo: "Entender",
    items: [
      { to: "/track-record", label: "Track record", icon: ChartLineUp, testId: "nav-track-record" },
      { to: "/cerebro", label: "Cerebro", icon: Brain, testId: "nav-brain" },
      { to: "/intelligence", label: "Inteligencia", icon: Broadcast, testId: "nav-intelligence" },
      { to: "/laboratorio", label: "Laboratorio", icon: Flask, testId: "nav-laboratorio" },
    ],
  },
];

const HERRAMIENTAS = [
  { to: "/diagnostico", label: "Diagnóstico", icon: Stethoscope, testId: "nav-diagnostico" },
  { to: "/telegram", label: "Telegram", icon: TelegramLogo, testId: "nav-telegram" },
  { to: "/sistema/estilos", label: "Estilos", icon: Palette, testId: "nav-estilos" },
];

function Item({ n, activo, onNavigate }) {
  const Icon = n.icon;
  return (
    <Link
      to={n.to}
      data-testid={n.testId}
      onClick={onNavigate}
      aria-current={activo ? "page" : undefined}
      /* El activo es un fondo tintado de naranja con el icono en naranja: una sola
         señal. El anillo que llevaba encima era una segunda caja que no decía nada
         nuevo. Las demás no tienen caja hasta que pasas por encima.
         Más alto en el cajón móvil (py-2.5 ≈ 40px de zona táctil) que en el rail fijo,
         donde se apunta con ratón y la lista tiene que caber entera. */
      className={`group flex items-center gap-2.5 mx-1.5 px-2.5 py-2.5 lg:py-1.5 text-apoyo rounded-iv-sm
                  transition-colors duration-150 ease-out motion-reduce:transition-none ${
        activo
          ? "bg-marca/10 text-tinta font-medium"
          : "text-tinta-2 hover:bg-superficie-alt hover:text-tinta active:bg-superficie-alt"
      }`}
    >
      <Icon size={16} weight={activo ? "fill" : "regular"} aria-hidden="true"
            className={`shrink-0 transition-colors duration-150 ${
              activo ? "text-marca" : "text-tinta-3 group-hover:text-tinta-2"
            }`} />
      <span className="truncate">{n.label}</span>
    </Link>
  );
}

/** El contenido del rail. Se reutiliza tal cual en el cajón móvil: una sola fuente. */
export function RailContenido({ onNavigate }) {
  const { pathname, search } = useLocation();
  const actual = pathname + search;
  // El rail fijo y el cajón pintan este mismo contenido: los id tienen que ser propios
  // de cada instancia o se repetirían en la página.
  const uid = React.useId();
  const esActivo = (to) =>
    to.includes("?") ? actual === to : pathname === to && !search.includes("modo=screener");

  return (
    <>
      {/* El logotipo: el icono naranja con brillo y la palabra en degradado, el mismo
          gesto que la pantalla de entrada. Así la marca se reconoce igual dentro y fuera. */}
      <Link
        to="/"
        onClick={onNavigate}
        className="flex items-center gap-2.5 px-1.5 pt-1 pb-4 shrink-0 border-b border-linea mb-1 rounded-iv-sm"
      >
        <span aria-hidden="true" className="w-8 h-8 rounded-[10px] iv-boton-brillo flex items-center justify-center shrink-0">
          <ChartBar size={16} weight="bold" />
        </span>
        <span className="min-w-0">
          <span className="iv-marca-palabra block text-[21px] leading-none pb-0.5">InverIA</span>
          {/* 11px, el suelo de la casa (antes 9px, que no se lee). Con menos tracking
              para que quepa en los 196px del rail sin partirse. */}
          <span className="iv-etiqueta block mt-1 tracking-[0.06em] truncate">
            Terminal privada
          </span>
        </span>
      </Link>

      <nav aria-label="Principal" className="flex-1 min-h-0 overflow-y-auto overscroll-contain -mx-2.5 pb-1">
        {GRUPOS.map((g) => (
          <div key={g.titulo}>
            {/* pl-3 = los 12px a los que empieza el texto de un ítem (2px de filete
                + 10px de sangría). Sin esto las etiquetas de grupo quedaban 2px a la
                izquierda de los enlaces que encabezan. */}
            <p id={`${uid}-${g.titulo}`} className="iv-etiqueta pl-3 pr-2.5 pt-4 pb-1.5 tracking-[0.14em] text-tinta-3">
              {g.titulo}
            </p>
            <div role="group" aria-labelledby={`${uid}-${g.titulo}`} className="space-y-px">
              {g.items.map((n) => (
                <Item key={n.to} n={n} activo={esActivo(n.to)} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Herramientas: se llega, pero no compiten. Antes no se llegaba de ninguna forma. */}
      <div role="group" aria-label="Herramientas" className="border-t border-linea pt-2 mt-2 shrink-0 -mx-2.5 space-y-px">
        {HERRAMIENTAS.map((n) => (
          <Item key={n.to} n={n} activo={esActivo(n.to)} onNavigate={onNavigate} />
        ))}
      </div>
    </>
  );
}

/** Rail fijo de escritorio. */
export default function Rail() {
  return (
    <aside
      data-testid="app-rail"
      className="hidden lg:flex fixed left-0 top-0 bottom-0 w-[196px] flex-col
                 bg-superficie border-r border-linea px-2.5 py-3.5 z-40"
    >
      <RailContenido />
    </aside>
  );
}

/** Cajón móvil. MISMAS etiquetas: aquí nunca se cae a iconos sueltos.
 *
 * VA EN UN PORTAL, Y NO ES UN DETALLE DE IMPLEMENTACIÓN
 *
 * Se pinta desde dentro de la cabecera, que lleva `backdrop-blur`. Un backdrop-filter
 * crea BLOQUE CONTENEDOR para los descendientes `fixed`: el cajón dejaba de medirse
 * contra la pantalla y pasaba a medirse contra la cabecera. `inset-0` le daba la altura
 * de la cabecera —unos 60px—, así que el fondo sólido llegaba hasta el logo y el resto de
 * los enlaces se desbordaba SIN fondo, escrito encima del contenido de la página. En el
 * móvil el menú era ilegible.
 *
 * Sacándolo a `document.body` no hay ancestro que pueda atraparlo: ni éste ni ningún
 * `transform`, `filter` o `contain` que aparezca mañana en la cabecera.
 */
export function RailCajon({ abierto, cerrar }) {
  // Con el cajón abierto, el fondo no debe poder desplazarse: en el móvil, arrastrar
  // sobre el velo movía la página de detrás y al cerrar habías perdido el sitio.
  // `cerrar` llega como función nueva en cada render de la cabecera. En las dependencias
  // haría que el efecto se deshiciera y se rehiciera continuamente mientras el cajón está
  // abierto; en una ref, el efecto depende solo de si está abierto.
  const cerrarRef = React.useRef(cerrar);
  cerrarRef.current = cerrar;
  React.useEffect(() => {
    if (!abierto) return undefined;
    const previo = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const alPulsar = (e) => { if (e.key === "Escape") cerrarRef.current(); };
    document.addEventListener("keydown", alPulsar);
    return () => {
      document.body.style.overflow = previo;
      document.removeEventListener("keydown", alPulsar);
    };
  }, [abierto]);

  if (!abierto) return null;
  return createPortal(
    <div className="lg:hidden fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Menú">
      {/* El velo: fundido corto. Fuera del orden de tabulación —el botón de cierre
          visible ya lo cubre— para que el teclado no pase dos veces por «Cerrar». */}
      <button
        aria-label="Cerrar menú"
        tabIndex={-1}
        onClick={cerrar}
        className="absolute inset-0 bg-fondo/80 backdrop-blur-sm animate-in fade-in-0 duration-200"
      />
      {/* El cajón entra desde el borde del que sale el gesto, con la curva de cajón de
          iOS: arranca rápido y frena suave. Con movimiento reducido solo aparece. */}
      <div className="absolute left-0 top-0 bottom-0 w-[260px] max-w-[85vw] bg-superficie border-r border-linea
                      px-2.5 py-3.5 pb-[max(0.875rem,env(safe-area-inset-bottom))] flex flex-col
                      shadow-[12px_0_40px_-12px_rgb(0_0_0/0.6)]
                      motion-safe:animate-in motion-safe:slide-in-from-left motion-safe:duration-300
                      motion-safe:ease-[cubic-bezier(0.32,0.72,0,1)]">
        <button
          onClick={cerrar}
          aria-label="Cerrar menú"
          className="absolute right-2 top-2.5 z-10 inline-flex items-center justify-center h-9 w-9 rounded-iv-sm
                     text-tinta-3 hover:text-tinta hover:bg-superficie-alt active:scale-[0.96]
                     transition-[color,background-color,transform] duration-150 ease-out
                     motion-reduce:transition-none motion-reduce:active:scale-100"
        >
          <X size={16} />
        </button>
        <RailContenido onNavigate={cerrar} />
      </div>
    </div>,
    document.body,
  );
}
