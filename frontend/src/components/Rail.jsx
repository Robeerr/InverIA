import React from "react";
import { Link, useLocation } from "react-router-dom";
import {
  House, Lightning, MagnifyingGlass, Bell, Coins, CalendarBlank,
  ChartLineUp, Brain, ChartLineUp as Marca, Stethoscope, TelegramLogo, Palette, X,
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
 * LEY 1 · EL ÁMBAR NO DECORA
 *
 * Aparece exactamente una vez en todo el rail: el ítem activo. Ni el logo, ni los
 * grupos, ni el hover. Si el ámbar señalara varias cosas dejaría de señalar ninguna.
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
      className={`flex items-center gap-2.5 px-2.5 py-1.5 rounded-iv-sm text-apoyo transition-colors ${
        activo
          ? "bg-marca/10 text-tinta font-semibold shadow-[inset_2px_0_0_rgb(var(--iv-marca))]"
          : "text-tinta-2 hover:bg-superficie-alt hover:text-tinta"
      }`}
    >
      <Icon size={15} weight={activo ? "bold" : "regular"} className="shrink-0" />
      <span className="truncate">{n.label}</span>
    </Link>
  );
}

/** El contenido del rail. Se reutiliza tal cual en el cajón móvil: una sola fuente. */
export function RailContenido({ onNavigate }) {
  const { pathname, search } = useLocation();
  const actual = pathname + search;
  const esActivo = (to) =>
    to.includes("?") ? actual === to : pathname === to && !search.includes("modo=screener");

  return (
    <>
      <Link
        to="/"
        onClick={onNavigate}
        className="flex items-center gap-2.5 px-2.5 pt-1 pb-4 shrink-0"
      >
        <span className="w-[18px] h-[18px] rounded-iv-sm bg-marca flex items-center justify-center text-marca-tinta shrink-0">
          <Marca size={12} weight="bold" />
        </span>
        <span className="font-heading font-bold text-cuerpo tracking-tight text-tinta">InverIA</span>
      </Link>

      <nav className="flex-1 min-h-0 overflow-y-auto">
        {GRUPOS.map((g) => (
          <div key={g.titulo}>
            <p className="iv-etiqueta px-2.5 pt-3.5 pb-1.5 tracking-[0.14em] text-linea-marcada">
              {g.titulo}
            </p>
            <div className="space-y-0.5">
              {g.items.map((n) => (
                <Item key={n.to} n={n} activo={esActivo(n.to)} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Herramientas: se llega, pero no compiten. Antes no se llegaba de ninguna forma. */}
      <div className="border-t border-linea pt-2 mt-2 space-y-0.5 shrink-0">
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

/** Cajón móvil. MISMAS etiquetas: aquí nunca se cae a iconos sueltos. */
export function RailCajon({ abierto, cerrar }) {
  if (!abierto) return null;
  return (
    <div className="lg:hidden fixed inset-0 z-50" role="dialog" aria-modal="true">
      <button
        aria-label="Cerrar menú"
        onClick={cerrar}
        className="absolute inset-0 bg-fondo/80 backdrop-blur-sm"
      />
      <div className="absolute left-0 top-0 bottom-0 w-[236px] bg-superficie border-r border-linea
                      px-2.5 py-3.5 flex flex-col shadow-2xl">
        <button
          onClick={cerrar}
          aria-label="Cerrar menú"
          className="absolute right-2.5 top-3.5 text-tinta-3 hover:text-tinta p-1"
        >
          <X size={16} />
        </button>
        <RailContenido onNavigate={cerrar} />
      </div>
    </div>
  );
}
