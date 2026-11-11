import React from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ArrowClockwise, CaretDown } from "@phosphor-icons/react";
import { api } from "../lib/api";
import { useSignals } from "../hooks/useSignals";
import { etiquetaCalendario } from "../lib/cartera";
import { fmtEnDias } from "../lib/format";
import { cn } from "../lib/utils";
import Boton from "../components/base/Boton";
import { Cargando, Error as ErrorEstado } from "../components/base/Estado";

/* Calendario de resultados · rediseño de presentación
   ─────────────────────────────────────────────────────────────────────────────
   Mismo lenguaje que la portada «Hoy»: cabecera a sangre sin caja, UN solo panel
   con filetes en vez de una caja por día, filas compactas y la cifra (EPS est.)
   en una columna derecha de dígitos tabulares. El color se reserva para lo que
   dice algo: la fecha más cercana (hoy/mañana) y las acciones que tienes. */

function fechaValida(dateStr) {
  return !!dateStr && !Number.isNaN(new Date(dateStr).getTime());
}

function dayLabel(dateStr) {
  if (!dateStr) return "—";
  if (!fechaValida(dateStr)) return dateStr; // «Sin fecha»: se enseña tal cual, no «Invalid Date»
  const d = new Date(dateStr);
  return d.toLocaleDateString("es-ES", { weekday: "short", day: "2-digit", month: "short" });
}

function hourLabel(h) {
  if (!h) return "—";
  const map = { bmo: "Antes apertura", amc: "Tras cierre", dmh: "Durante sesión" };
  return map[h] || h;
}

/** Tono de la etiqueta de origen: lo que tienes destaca; lo que vigilas, no. */
function tonoGrupo(etiqueta) {
  return etiqueta === "En cartera" ? "text-marca" : "text-tinta-3";
}

export default function CalendarView({ setSymbol }) {
  const [days, setDays] = React.useState(14);
  const [refreshN, setRefreshN] = React.useState(0);

  // Señales desde el caché compartido (no se re-piden al cambiar "días").
  const { data: signals } = useSignals();
  const syms = React.useMemo(() => {
    const entries = Array.isArray(signals) ? signals : (signals?.items || signals?.entries || []);
    return [...new Set(entries.map((e) => e.symbol).filter(Boolean))];
  }, [signals]);

  // Qué tienes de verdad: la misma consulta (y la misma caché) que la cabecera de Cartera.
  const { data: resumen } = useQuery({
    queryKey: ["cartera-resumen"],
    queryFn: () => api.cartera.resumen(),
    staleTime: 60_000,
    retry: false,
  });
  const enCartera = React.useMemo(() => {
    if (!resumen?.posiciones) return null;
    return new Set(resumen.posiciones
      .filter((p) => (p.acciones || 0) > 0)
      .map((p) => (p.symbol || "").toUpperCase()));
  }, [resumen]);

  // Mapa símbolo → de dónde sale cada earnings: «En cartera» solo si tienes acciones;
  // si no, es una acción que vigilas. Antes todo lo de la tabla salía como «Cartera».
  const symGroup = React.useMemo(() => {
    const entries = Array.isArray(signals) ? signals : (signals?.items || signals?.entries || []);
    const m = {};
    entries.forEach((e) => {
      const etiqueta = e.symbol && etiquetaCalendario(e, enCartera);
      if (etiqueta) m[e.symbol.toUpperCase()] = etiqueta;
    });
    return m;
  }, [signals, enCartera]);

  // Earnings de esos símbolos: el backend los trae en paralelo por símbolo.
  const earningsQuery = useQuery({
    queryKey: ["earnings", days, syms, refreshN],
    queryFn: () =>
      syms.length ? api.calendar.earnings(days, syms.join(","), refreshN > 0) : Promise.resolve({ items: [] }),
    enabled: signals !== undefined,
    staleTime: 5 * 60_000,
  });
  const data = earningsQuery.data;
  const loading = signals === undefined || earningsQuery.isFetching;

  const grouped = React.useMemo(() => {
    if (!data?.items) return [];
    const m = {};
    data.items.forEach((it) => {
      const k = it.date || "Sin fecha";
      (m[k] = m[k] || []).push(it);
    });
    return Object.entries(m).map(([date, items]) => ({ date, items }));
  }, [data]);

  const total = data?.items?.length || 0;

  return (
    <div data-testid="calendar-view">
      {/* ── Cabecera a sangre, sin caja (como «Hoy»). Controles a la derecha; en móvil
          bajan debajo del título y quedan a mano del pulgar. */}
      <header className="iv-veredicto mb-6 sm:mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h1 className="iv-verbo text-tinta text-balance">Calendario de resultados</h1>
          <p className="text-cuerpo text-tinta-2 mt-2.5 max-w-[58ch]">
            Próximos earnings de las acciones que tienes y de las que vigilas.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="relative">
            <label htmlFor="calendario-periodo" className="sr-only">Periodo</label>
            <select
              id="calendario-periodo"
              data-testid="days-select"
              value={days}
              onChange={(e) => setDays(parseInt(e.target.value))}
              className="appearance-none h-8 pl-3 pr-8 rounded-full bg-superficie-alt border border-linea-fuerte
                         text-apoyo text-tinta font-mono cursor-pointer
                         hover:border-tinta-3 transition-colors duration-150 motion-reduce:transition-none"
            >
              <option value={7}>Próximos 7 días</option>
              <option value={14}>Próximos 14 días</option>
              <option value={30}>Próximos 30 días</option>
              <option value={60}>Próximos 60 días</option>
            </select>
            <CaretDown size={12} weight="bold" aria-hidden="true"
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-tinta-3" />
          </div>
          <Boton
            variante="fantasma"
            tamano="sm"
            onClick={() => setRefreshN((n) => n + 1)}
            title="Recargar (datos frescos)"
            aria-busy={loading || undefined}
          >
            <ArrowClockwise size={14} weight="bold" aria-hidden="true"
              className={cn("text-marca", loading && "animate-spin motion-reduce:animate-none")} />
            Actualizar
          </Boton>
        </div>
      </header>

      {/* ── Cabecera de sección con filete de acento + recuento en una línea de apoyo. */}
      <div className="iv-seccion iv-seccion-acento !mb-1.5">
        <h2 className="font-heading text-titulo font-semibold text-tinta leading-tight min-w-0">
          Próximos resultados
        </h2>
      </div>
      <p className="iv-cifra text-etiqueta text-tinta-3 mb-4 min-h-[1rem]" aria-live="polite">
        {!loading && !earningsQuery.error && data && total > 0 &&
          `${total} ${total === 1 ? "resultado" : "resultados"} · ${grouped.length} ${grouped.length === 1 ? "fecha" : "fechas"}`}
      </p>

      {loading ? (
        <div className="iv-panel p-5">
          <Cargando filas={4} etiqueta="Cargando calendario..." />
        </div>
      ) : earningsQuery.error ? (
        <ErrorEstado
          error={earningsQuery.error}
          onReintentar={() => earningsQuery.refetch()}
          titulo="No se ha podido cargar el calendario"
        />
      ) : data && grouped.length === 0 ? (
        <div className="iv-panel px-6 py-10 text-center">
          <p className="text-cuerpo text-tinta font-medium">
            Ninguna de tus señales tiene earnings en este período.
          </p>
          <p className="text-apoyo text-tinta-3 mt-1">
            Periodo consultado: próximos {days} días.
          </p>
        </div>
      ) : grouped.length > 0 ? (
        // Un único panel; cada fecha es un bloque con filete, no una caja propia.
        <div className="iv-panel overflow-hidden divide-y divide-linea">
          {grouped.map(({ date, items }) => {
            const relativa = fechaValida(date) ? fmtEnDias(date) : null;
            const inminente = relativa === "hoy" || relativa === "mañana";
            return (
              <section key={date} aria-label={dayLabel(date)}>
                <header className="flex items-baseline justify-between gap-3 px-4 sm:px-5 pt-4 pb-1.5">
                  <h3 className="font-heading font-semibold text-cuerpo text-tinta capitalize">
                    {dayLabel(date)}
                  </h3>
                  {relativa && (
                    <span className={cn("iv-cifra text-etiqueta shrink-0",
                      inminente ? "text-marca font-semibold" : "text-tinta-3")}>
                      {relativa}
                    </span>
                  )}
                </header>
                <ul className="pb-2">
                  {items.map((it, i) => {
                    const grupo = symGroup[it.symbol?.toUpperCase()];
                    return (
                      <li key={`${it.symbol}-${i}`}>
                        <button
                          type="button"
                          data-testid={`earnings-${it.symbol}`}
                          className="group w-full text-left flex items-center gap-3 px-4 sm:px-5 py-2.5
                                     hover:bg-superficie-alt focus-visible:-outline-offset-2
                                     transition-colors duration-150 motion-reduce:transition-none"
                          /* setSymbol ya navega a /accion/:symbol. El navigate("/") que había
                             aquí ahora llevaría a la portada, que es lo contrario de lo que
                             espera quien pulsa una fila del calendario. */
                          onClick={() => setSymbol(it.symbol)}
                        >
                          <div className="flex-1 min-w-0">
                            <p className="flex items-baseline gap-2 min-w-0">
                              <span className="iv-cifra font-semibold text-apoyo text-tinta truncate
                                               group-hover:text-marca transition-colors duration-150
                                               motion-reduce:transition-none">
                                {it.symbol}
                              </span>
                              {grupo && (
                                <span className={cn("text-etiqueta font-medium shrink-0", tonoGrupo(grupo))}>
                                  {grupo}
                                </span>
                              )}
                            </p>
                            <p className="iv-cifra text-etiqueta text-tinta-3 truncate mt-0.5">
                              Q{it.quarter} {it.year} · {hourLabel(it.hour)}
                            </p>
                          </div>
                          <div className="text-right shrink-0 min-w-[5.5rem]">
                            <p className="iv-etiqueta">EPS est.</p>
                            <p className="iv-cifra text-apoyo font-semibold text-tinta whitespace-nowrap">
                              {it.eps_estimate ?? "—"}
                            </p>
                          </div>
                          <ArrowRight size={14} aria-hidden="true"
                            className="text-tinta-3 shrink-0 transition-transform duration-150 ease-out
                                       group-hover:translate-x-0.5 group-hover:text-tinta-2
                                       motion-reduce:transition-none motion-reduce:group-hover:translate-x-0" />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
