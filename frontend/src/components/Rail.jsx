import React from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import {
  House, Telescope, ListFilter, Wallet, ArrowLeftRight, CalendarDays,
  ChartLine, BrainCircuit, Radar, FlaskConical, Stethoscope, Send, Palette, X,
  PanelLeftClose, PanelLeftOpen,
} from "lucide-react";

/**
 * Navegación lateral persistente.
 *
 * LOS TRES GRUPOS SON LA JERARQUÍA
 *   Decidir    → a lo que abres la aplicación.
 *   Gestionar  → lo que ya tienes y hay que mantener.
 *   Entender   → lo que se consulta, no lo que se opera.
 * Las herramientas —diagnóstico, Telegram, la guía de estilos— bajan al pie.
 *
 * EL ÍNDIGO SEÑALA DÓNDE ESTÁS
 * El ítem activo es el único con color: icono índigo, fondo de luz y una pestaña
 * índigo en el borde. Nada más en el rail lleva índigo salvo el sello de la marca.
 *
 * VERSIÓN COMPACTA
 * Solo iconos (68 px). Se recuerda en localStorage y se publica como
 * `data-rail="compacto"` en <html>, que cambia `--rail-w`: así el lienzo de App se
 * aparta lo justo sin que ninguna pantalla tenga que saberlo.
 */

const GRUPOS = [
  {
    titulo: "Decidir",
    items: [
      { to: "/", label: "Hoy", icon: House, testId: "nav-hoy" },
      { to: "/oportunidades", label: "Oportunidades", icon: Telescope, testId: "nav-opportunities" },
      { to: "/oportunidades?modo=screener", label: "Screener", icon: ListFilter, testId: "nav-screener" },
    ],
  },
  {
    titulo: "Gestionar",
    items: [
      { to: "/cartera", label: "Cartera", icon: Wallet, testId: "nav-signals" },
      { to: "/operaciones", label: "Operaciones", icon: ArrowLeftRight, testId: "nav-ventas" },
      { to: "/calendario", label: "Calendario", icon: CalendarDays, testId: "nav-calendar" },
    ],
  },
  {
    titulo: "Entender",
    items: [
      { to: "/track-record", label: "Track record", icon: ChartLine, testId: "nav-track-record" },
      { to: "/cerebro", label: "Cerebro", icon: BrainCircuit, testId: "nav-brain" },
      { to: "/intelligence", label: "Inteligencia", icon: Radar, testId: "nav-intelligence" },
      { to: "/laboratorio", label: "Laboratorio", icon: FlaskConical, testId: "nav-laboratorio" },
    ],
  },
];

const HERRAMIENTAS = [
  { to: "/diagnostico", label: "Diagnóstico", icon: Stethoscope, testId: "nav-diagnostico" },
  { to: "/telegram", label: "Telegram", icon: Send, testId: "nav-telegram" },
  { to: "/sistema/estilos", label: "Estilos", icon: Palette, testId: "nav-estilos" },
];

/** El sello de InverIA: una línea que sube y se posa en un punto. */
export function Sello({ className = "w-8 h-8 rounded-[10px]", trazo = 2 }) {
  return (
    <span aria-hidden="true" className={`iv-sello inline-flex items-center justify-center shrink-0 ${className}`}>
      <svg viewBox="0 0 24 24" className="w-[62%] h-[62%]" fill="none">
        <path d="M3.5 16.5 L9 11 L12.5 14 L19 7.5" stroke="currentColor" strokeWidth={trazo}
              strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="19" cy="7.5" r="2.1" fill="currentColor" />
      </svg>
    </span>
  );
}

function Item({ n, activo, onNavigate, compacto }) {
  const Icon = n.icon;
  return (
    <Link
      to={n.to}
      data-testid={n.testId}
      onClick={onNavigate}
      aria-current={activo ? "page" : undefined}
      title={compacto ? n.label : undefined}
      aria-label={compacto ? n.label : undefined}
      /* 44 px en el cajón táctil, 34 px en el rail de escritorio. */
      className={`group relative flex items-center gap-3 h-11 lg:h-[34px] rounded-[9px]
                  text-[13.5px] font-medium tracking-[-0.005em]
                  transition-[background-color,color] duration-150 ease-salida motion-reduce:transition-none
                  ${compacto ? "justify-center px-0 mx-1" : "px-2.5"}
                  ${activo
                    ? "bg-tinta/[0.07] text-tinta"
                    : "text-tinta-2 hover:bg-tinta/[0.045] hover:text-tinta active:bg-tinta/[0.07]"}`}
    >
      {/* La pestaña índigo en el borde: el «estás aquí» que no se confunde. */}
      <span
        aria-hidden="true"
        className={`absolute -left-3 top-1/2 -translate-y-1/2 w-[3px] rounded-r-full bg-marca
                    shadow-[0_0_12px_rgb(var(--iv-intencion)/0.7)]
                    transition-[height,opacity] duration-200 ease-salida
                    ${activo ? "h-5 opacity-100" : "h-2 opacity-0"}`}
      />
      <Icon
        size={17}
        strokeWidth={activo ? 2.1 : 1.75}
        aria-hidden="true"
        className={`shrink-0 transition-colors duration-150 ${
          activo ? "text-marca" : "text-tinta-3 group-hover:text-tinta-2"
        }`}
      />
      {!compacto && <span className="truncate">{n.label}</span>}
    </Link>
  );
}

/** El contenido del rail. Se reutiliza tal cual en el cajón móvil: una sola fuente. */
export function RailContenido({ onNavigate, compacto = false, onCompactar }) {
  const { pathname, search } = useLocation();
  const actual = pathname + search;
  const uid = React.useId();
  const esActivo = (to) =>
    to.includes("?") ? actual === to : pathname === to && !search.includes("modo=screener");

  return (
    <>
      <div className={`flex items-center shrink-0 h-14 ${compacto ? "justify-center" : "px-2 gap-2.5"}`}>
        <Link to="/" onClick={onNavigate} aria-label="InverIA · Hoy"
              className="flex items-center gap-2.5 min-w-0 rounded-[10px]">
          <Sello />
          {!compacto && (
            <span className="min-w-0 leading-none">
              <span className="iv-marca-palabra block text-[17px]">InverIA</span>
              <span className="block mt-1 text-[11.5px] text-tinta-3 font-medium truncate">Análisis privado</span>
            </span>
          )}
        </Link>
      </div>

      <nav aria-label="Principal"
           className={`flex-1 min-h-0 overflow-y-auto overscroll-contain no-scrollbar pb-2 pt-2 ${compacto ? "-mx-2 px-2" : "-mx-3 px-3"}`}>
        {GRUPOS.map((g, i) => (
          <div key={g.titulo} className={i ? "mt-5" : ""}>
            {compacto ? (
              i ? <div aria-hidden="true" className="mx-4 mb-3 h-px bg-[var(--borde-suave)]" /> : null
            ) : (
              <p id={`${uid}-${g.titulo}`} className="px-2.5 pb-1.5 text-[11.5px] font-medium text-tinta-3">
                {g.titulo}
              </p>
            )}
            <div role="group" aria-labelledby={compacto ? undefined : `${uid}-${g.titulo}`}
                 aria-label={compacto ? g.titulo : undefined} className="space-y-0.5">
              {g.items.map((n) => (
                <Item key={n.to} n={n} activo={esActivo(n.to)} onNavigate={onNavigate} compacto={compacto} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div role="group" aria-label="Herramientas"
           className="pt-2 mt-1 shrink-0 space-y-0.5 border-t border-suave">
        {HERRAMIENTAS.map((n) => (
          <Item key={n.to} n={n} activo={esActivo(n.to)} onNavigate={onNavigate} compacto={compacto} />
        ))}
        {onCompactar && (
          <button
            type="button"
            onClick={onCompactar}
            aria-label={compacto ? "Expandir menú lateral" : "Compactar menú lateral"}
            title={compacto ? "Expandir menú" : "Compactar menú"}
            className={`flex items-center gap-3 w-full h-[34px] rounded-[9px] text-[13px] text-tinta-3
                        hover:text-tinta hover:bg-tinta/[0.045] ${compacto ? "justify-center" : "px-2.5"}`}
          >
            {compacto ? <PanelLeftOpen size={17} strokeWidth={1.75} aria-hidden="true" />
                      : <PanelLeftClose size={17} strokeWidth={1.75} aria-hidden="true" />}
            {!compacto && <span>Compactar</span>}
          </button>
        )}
      </div>
    </>
  );
}

const CLAVE_COMPACTO = "inveria-rail";

/** Rail fijo de escritorio. */
export default function Rail() {
  const [compacto, setCompacto] = React.useState(
    () => typeof window !== "undefined" && localStorage.getItem(CLAVE_COMPACTO) === "compacto"
  );

  React.useLayoutEffect(() => {
    const raiz = document.documentElement;
    if (compacto) raiz.dataset.rail = "compacto";
    else delete raiz.dataset.rail;
    localStorage.setItem(CLAVE_COMPACTO, compacto ? "compacto" : "normal");
  }, [compacto]);

  return (
    <aside
      data-testid="app-rail"
      className={`hidden lg:flex fixed left-0 top-0 bottom-0 w-[var(--rail-w)] flex-col
                  bg-fondo/80 border-r border-suave py-2 z-40
                  transition-[width] duration-200 ease-salida motion-reduce:transition-none
                  ${compacto ? "px-2" : "px-3"}`}
    >
      <RailContenido compacto={compacto} onCompactar={() => setCompacto((c) => !c)} />
    </aside>
  );
}

/** Cajón móvil. MISMAS etiquetas: aquí nunca se cae a iconos sueltos.
 *
 * Va en un portal: la cabecera lleva `backdrop-blur`, que crea bloque contenedor
 * para los `fixed` y atraparía el cajón a la altura de la cabecera.
 */
export function RailCajon({ abierto, cerrar }) {
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
      <button
        aria-label="Cerrar menú"
        tabIndex={-1}
        onClick={cerrar}
        className="absolute inset-0 bg-black/55 backdrop-blur-[2px] animate-in fade-in-0 duration-200"
      />
      <div className="absolute left-0 top-0 bottom-0 w-[288px] max-w-[86vw] bg-superficie border-r border-suave
                      px-3 pt-[max(0.5rem,env(safe-area-inset-top))] pb-[max(0.75rem,env(safe-area-inset-bottom))]
                      flex flex-col shadow-flotante
                      motion-safe:animate-in motion-safe:slide-in-from-left motion-safe:duration-300
                      motion-safe:ease-[cubic-bezier(0.32,0.72,0,1)]">
        <button
          onClick={cerrar}
          aria-label="Cerrar menú"
          className="absolute right-2.5 top-[max(0.5rem,env(safe-area-inset-top))] mt-1.5 z-10 inline-flex items-center
                     justify-center h-11 w-11 rounded-[10px] text-tinta-3 hover:text-tinta hover:bg-tinta/[0.06]"
        >
          <X size={18} strokeWidth={1.75} />
        </button>
        <RailContenido onNavigate={cerrar} />
      </div>
    </div>,
    document.body,
  );
}
