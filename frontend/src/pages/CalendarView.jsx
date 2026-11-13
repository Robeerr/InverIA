import React from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, RotateCw, Sunrise, Moon, Clock, CalendarDays } from "lucide-react";
import { api } from "../lib/api";
import { useSignals } from "../hooks/useSignals";
import { etiquetaCalendario } from "../lib/cartera";
import { fmtEnDias } from "../lib/format";
import { cn } from "../lib/utils";
import Boton from "../components/base/Boton";
import Segmentado from "../components/base/Segmentado";
import Monograma from "../components/base/Monograma";
import FranjaDias from "../components/base/FranjaDias";
import { Cargando, Vacio, Error as ErrorEstado } from "../components/base/Estado";

/* Calendario de resultados · fase 2 («otra app»)
   ─────────────────────────────────────────────────────────────────────────────
   1. Titular con miga y el periodo como `Segmentado` (7 · 14 · 30 · 60 días).
   2. Pieza héroe: el PRÓXIMO resultado como cifra grande (cuántos días faltan) con
      su monograma, y debajo la `FranjaDias` con el periodo entero de un vistazo.
      A la derecha, el reparto: cuántos tienes en cartera y cuántos vigilas.
   3. Agenda: UN panel; cada fecha es una fila con una baldosa de día a la izquierda
      (día de la semana, número grande, mes) y sus resultados a la derecha en una
      rejilla de columnas (valor · trimestre · momento · EPS est.). En móvil la fila
      de resultado baja a dos líneas y la baldosa se queda a la izquierda.
   El índigo solo marca lo que tienes en cartera y lo inminente (hoy/mañana). */

function fechaValida(dateStr) {
  return !!dateStr && !Number.isNaN(new Date(dateStr).getTime());
}

function dayLabel(dateStr) {
  if (!dateStr) return "—";
  if (!fechaValida(dateStr)) return dateStr; // «Sin fecha»: se enseña tal cual, no «Invalid Date»
  const d = new Date(dateStr);
  return d.toLocaleDateString("es-ES", { weekday: "short", day: "2-digit", month: "short" });
}

/** Partes de la baldosa de fecha: «jue» · «12» · «nov». */
function partesFecha(dateStr) {
  const d = new Date(dateStr);
  const limpio = (s) => s.replace(".", "");
  return {
    semana: limpio(d.toLocaleDateString("es-ES", { weekday: "short" })),
    dia: d.getDate(),
    mes: limpio(d.toLocaleDateString("es-ES", { month: "short" })),
  };
}

/** Días naturales de hoy a la fecha (mismo criterio que `fmtEnDias`). Solo para colocar. */
function diasHasta(dateStr) {
  const a = new Date(dateStr); a.setHours(0, 0, 0, 0);
  const b = new Date(); b.setHours(0, 0, 0, 0);
  return Math.round((a.getTime() - b.getTime()) / 86400000);
}

function hourLabel(h) {
  if (!h) return "—";
  const map = { bmo: "Antes apertura", amc: "Tras cierre", dmh: "Durante sesión" };
  return map[h] || h;
}

const ICONO_HORA = { bmo: Sunrise, amc: Moon, dmh: Clock };

/** Tono del grupo: lo que tienes destaca; lo que vigilas, no. */
const TONO_GRUPO = {
  "En cartera": { punto: "bg-marca", texto: "text-marca", mono: "marca" },
  Vigilando: { punto: "bg-tinta-3", texto: "text-tinta-3", mono: "neutro" },
  Cimientos: { punto: "bg-info", texto: "text-info", mono: "neutro" },
};
const tonoGrupo = (g) => TONO_GRUPO[g] || TONO_GRUPO.Vigilando;

const PERIODOS = [7, 14, 30, 60].map((d) => ({ valor: d, etiqueta: `${d} días` }));

/** Entrada escalonada sutil para las primeras fechas. */
const escalon = (i) => (i < 8 ? { animationDelay: `${i * 40}ms` } : undefined);

/* ═════════════════════════════════ piezas ═════════════════════════════════ */

function Grupo({ grupo }) {
  if (!grupo) return null;
  const t = tonoGrupo(grupo);
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[12px] font-medium whitespace-nowrap", t.texto)}>
      <span aria-hidden="true" className={cn("w-1.5 h-1.5 rounded-full", t.punto)} />
      {grupo}
    </span>
  );
}

function Momento({ hour, className }) {
  const Icono = ICONO_HORA[hour];
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", className)}>
      {Icono && <Icono className="w-3.5 h-3.5 text-tinta-3" strokeWidth={1.75} aria-hidden="true" />}
      {hourLabel(hour)}
    </span>
  );
}

/** Héroe: el próximo resultado y el periodo entero en una franja. */
function Heroe({ proximo, grupoProximo, total, fechas, reparto, days, eventos }) {
  const relativa = proximo && fechaValida(proximo.date) ? fmtEnDias(proximo.date) : null;
  const faltan = proximo && fechaValida(proximo.date) ? diasHasta(proximo.date) : null;
  const cifra = faltan === 0 ? "Hoy" : faltan === 1 ? "Mañana" : faltan > 1 ? String(faltan) : relativa;
  const unidad = faltan > 1 ? "días" : null;
  const maxReparto = Math.max(1, ...reparto.map((r) => r.n));

  return (
    <section aria-label="Próximo resultado"
             className="iv-panel overflow-hidden grid lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="p-5 sm:p-7 min-w-0">
        <p className="iv-etiqueta">Próximo resultado</p>
        {proximo ? (
          <>
            <div className="flex items-end gap-4 sm:gap-5 mt-4 min-w-0">
              <p className="flex items-baseline gap-2.5 min-w-0">
                <span className="iv-cifra-hero text-[44px] sm:text-[60px] leading-[0.9]">{cifra}</span>
                {unidad && (
                  <span className="text-[15px] sm:text-[17px] text-tinta-2 font-medium tracking-[-0.01em]">{unidad}</span>
                )}
              </p>
            </div>
            <div className="flex items-center gap-3 mt-5 min-w-0">
              <Monograma symbol={proximo.symbol} tono={tonoGrupo(grupoProximo).mono} />
              <div className="min-w-0">
                <p className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                  <span className="iv-cifra text-[15px] font-semibold text-tinta">{proximo.symbol}</span>
                  <Grupo grupo={grupoProximo} />
                </p>
                <p className="text-[13px] text-tinta-2 mt-0.5">
                  <span className="capitalize">{dayLabel(proximo.date)}</span>
                  <span className="text-tinta-3"> · </span>
                  <span className="iv-cifra">Q{proximo.quarter} {proximo.year}</span>
                  <span className="text-tinta-3"> · </span>
                  {hourLabel(proximo.hour)}
                </p>
              </div>
            </div>
          </>
        ) : (
          <p className="iv-cifra-hero text-[44px] sm:text-[60px] leading-[0.9] mt-4">—</p>
        )}

        <FranjaDias dias={days} eventos={eventos} className="mt-7 sm:mt-8" />
      </div>

      {/* Reparto del periodo */}
      <div className="p-5 sm:p-7 border-t lg:border-t-0 lg:border-l border-suave bg-tinta/[0.02] min-w-0">
        <p className="iv-etiqueta">En los próximos {days} días</p>
        <p className="flex items-baseline gap-2.5 mt-4">
          <span className="iv-cifra-hero text-[40px] leading-none">{total}</span>
          <span className="text-[14.5px] text-tinta-2 font-medium">
            {total === 1 ? "resultado" : "resultados"}
          </span>
        </p>
        <p className="text-[13px] text-tinta-3 mt-1.5">
          en <span className="iv-cifra text-tinta-2">{fechas}</span> {fechas === 1 ? "fecha" : "fechas"}
        </p>
        {reparto.length > 0 && (
          <ul className="mt-6 space-y-3.5">
            {reparto.map((r) => {
              const t = tonoGrupo(r.grupo);
              return (
                <li key={r.grupo}>
                  <div className="flex items-baseline justify-between gap-3">
                    <Grupo grupo={r.grupo} />
                    <span className="iv-cifra text-[13px] text-tinta font-semibold">{r.n}</span>
                  </div>
                  <div className="mt-1.5 h-1 rounded-full bg-tinta/[0.06] overflow-hidden">
                    <div className={cn("h-full rounded-full", t.punto)} style={{ width: `${(r.n / maxReparto) * 100}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

/** Una fecha de la agenda: baldosa a la izquierda, resultados a la derecha. */
function Fecha({ date, items, symGroup, setSymbol, indice }) {
  const valida = fechaValida(date);
  const relativa = valida ? fmtEnDias(date) : null;
  const faltan = valida ? diasHasta(date) : null;
  const inminente = faltan === 0 || faltan === 1;
  const pasada = faltan !== null && faltan < 0;
  const p = valida ? partesFecha(date) : null;

  return (
    <section aria-label={dayLabel(date)} style={escalon(indice)}
             className="iv-entra grid grid-cols-[64px_minmax(0,1fr)] sm:grid-cols-[132px_minmax(0,1fr)]">
      {/* Baldosa de día */}
      <header className="px-3 sm:px-6 py-3.5 sm:py-4 border-r border-suave">
        {p ? (
          <div className={cn("flex flex-col sm:flex-row sm:items-center gap-x-2.5 gap-y-1", pasada && "opacity-60")}>
            <h3 className={cn("iv-cifra-hero text-[24px] sm:text-[28px] leading-none",
                              inminente && "!text-marca")}>{p.dia}</h3>
            <p className="text-[11.5px] sm:text-[12px] leading-tight text-tinta-3 capitalize">
              <span className={cn("block font-medium", inminente ? "text-marca" : "text-tinta-2")}>{p.semana}</span>
              <span className="block">{p.mes}</span>
            </p>
          </div>
        ) : (
          <h3 className="text-[13px] font-medium text-tinta-2">{dayLabel(date)}</h3>
        )}
        {relativa && (
          <p className={cn("hidden sm:block mt-2 text-[12px]",
            inminente ? "text-marca font-semibold" : "text-tinta-3")}>
            {relativa}
          </p>
        )}
      </header>

      <ul className="min-w-0 py-1.5 sm:py-2">
        {relativa && (
          <li className={cn("sm:hidden px-3.5 pt-2.5 text-[12px]",
            inminente ? "text-marca font-semibold" : "text-tinta-3")}>
            {relativa}
          </li>
        )}
        {items.map((it, i) => {
          const grupo = symGroup[it.symbol?.toUpperCase()];
          return (
            <li key={`${it.symbol}-${i}`}>
              <button
                type="button"
                data-testid={`earnings-${it.symbol}`}
                /* setSymbol ya navega a /accion/:symbol (no a la portada). */
                onClick={() => setSymbol(it.symbol)}
                className="group w-full text-left min-h-[56px] px-3.5 sm:px-5 py-2.5 rounded-[12px]
                           grid items-center gap-x-3 sm:gap-x-4
                           grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[auto_minmax(0,1fr)_auto]
                           lg:grid-cols-[auto_minmax(0,1fr)_7rem_9.5rem_7rem_1rem]
                           hover:bg-tinta/[0.04] focus-visible:-outline-offset-2
                           transition-colors duration-150 ease-salida motion-reduce:transition-none"
              >
                {/* En móvil la baldosa de fecha ya ancla la fila: el monograma cedería sitio al momento. */}
                <Monograma symbol={it.symbol} tamano="sm" tono={tonoGrupo(grupo).mono} className="hidden sm:inline-flex" />

                <div className="min-w-0">
                  <p className="flex items-baseline gap-2.5 min-w-0">
                    <span className="iv-cifra text-[14px] font-semibold text-tinta truncate
                                     group-hover:text-marca transition-colors duration-150 motion-reduce:transition-none">
                      {it.symbol}
                    </span>
                    <Grupo grupo={grupo} />
                  </p>
                  {/* Móvil y tablet: trimestre y momento en la segunda línea */}
                  <p className="lg:hidden text-[12.5px] text-tinta-3 mt-0.5 flex items-center gap-x-2 min-w-0">
                    <span className="iv-cifra shrink-0">Q{it.quarter} {it.year}</span>
                    <span aria-hidden="true">·</span>
                    <Momento hour={it.hour} className="truncate" />
                  </p>
                </div>

                <span className="hidden lg:block iv-cifra text-[13px] text-tinta-2">Q{it.quarter} {it.year}</span>
                <Momento hour={it.hour} className="hidden lg:inline-flex text-[13px] text-tinta-2" />

                <div className="text-right">
                  <p className="text-[11.5px] text-tinta-3 lg:sr-only">EPS est.</p>
                  <p className="iv-cifra text-[14px] font-medium text-tinta whitespace-nowrap">
                    {it.eps_estimate ?? "—"}
                  </p>
                </div>

                <ChevronRight
                  className="hidden lg:block w-4 h-4 text-tinta-3 transition-transform duration-150 ease-salida
                             group-hover:translate-x-0.5 group-hover:text-tinta-2
                             motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
                  strokeWidth={1.75} aria-hidden="true" />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* ═════════════════════════════════ pantalla ═════════════════════════════════ */

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

  // ── Solo presentación: qué enseñar en el héroe y en la franja.
  const proximo = React.useMemo(() => {
    const items = data?.items || [];
    return items.find((it) => fechaValida(it.date) && diasHasta(it.date) >= 0) || items[0] || null;
  }, [data]);
  const reparto = React.useMemo(() => {
    const cuenta = {};
    (data?.items || []).forEach((it) => {
      const g = symGroup[it.symbol?.toUpperCase()];
      if (g) cuenta[g] = (cuenta[g] || 0) + 1;
    });
    return ["En cartera", "Vigilando", "Cimientos"].filter((g) => cuenta[g]).map((g) => ({ grupo: g, n: cuenta[g] }));
  }, [data, symGroup]);
  const eventos = React.useMemo(() => grouped
    .filter(({ date }) => fechaValida(date))
    .map(({ date, items }) => ({
      offset: diasHasta(date),
      etiquetas: items.map((it) => it.symbol),
      tono: diasHasta(date) < 0 ? "pasado"
        : items.some((it) => symGroup[it.symbol?.toUpperCase()] === "En cartera") ? "marca" : "neutro",
    })), [grouped, symGroup]);

  return (
    <div data-testid="calendar-view" className="space-y-6 sm:space-y-8">
      {/* ── Titular de página ─────────────────────────────────────────────── */}
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-5">
        <div className="min-w-0">
          <p className="text-[13px] text-tinta-3 flex items-center gap-1.5">
            Gestionar <ChevronRight className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" /> Calendario
          </p>
          <h1 className="iv-verbo text-tinta mt-2 text-balance">Calendario de resultados</h1>
          <p className="text-[14.5px] text-tinta-2 mt-2.5 max-w-[58ch] leading-relaxed">
            Próximos earnings de las acciones que tienes y de las que vigilas.
          </p>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div data-testid="days-select" className="flex-1 sm:flex-none min-w-0 overflow-x-auto">
            <Segmentado
              etiqueta="Periodo"
              opciones={PERIODOS}
              valor={days}
              onCambio={setDays}
              className="w-full sm:w-auto [&>button]:flex-1 sm:[&>button]:flex-none"
            />
          </div>
          <Boton
            variante="secundario"
            tamano="md"
            onClick={() => setRefreshN((n) => n + 1)}
            title="Recargar (datos frescos)"
            aria-label="Actualizar"
            aria-busy={loading || undefined}
            className="shrink-0 h-[40px] sm:h-9 w-[40px] sm:w-auto px-0 sm:px-3.5"
          >
            <RotateCw className={cn("w-4 h-4", loading && "animate-spin motion-reduce:animate-none")}
                      strokeWidth={1.75} aria-hidden="true" />
            <span className="hidden sm:inline">Actualizar</span>
          </Boton>
        </div>
      </header>

      {loading ? (
        <div className="space-y-6" aria-busy="true">
          <div className="iv-panel p-5 sm:p-7 grid lg:grid-cols-[minmax(0,1fr)_300px] gap-8">
            <div>
              <div className="h-3 w-32 rounded iv-esqueleto" />
              <div className="h-12 w-40 rounded-md iv-esqueleto mt-5" />
              <div className="h-16 w-full rounded-md iv-esqueleto mt-8" />
            </div>
            <Cargando filas={4} etiqueta="Cargando calendario..." />
          </div>
          <div className="iv-panel p-5">
            <Cargando filas={4} alto="h-10" etiqueta="Cargando agenda..." />
          </div>
        </div>
      ) : earningsQuery.error ? (
        <ErrorEstado
          error={earningsQuery.error}
          onReintentar={() => earningsQuery.refetch()}
          titulo="No se ha podido cargar el calendario"
        />
      ) : data && grouped.length === 0 ? (
        <div className="iv-panel">
          <Vacio
            icono={<CalendarDays className="w-5 h-5" strokeWidth={1.75} />}
            titulo="Ninguna de tus señales tiene earnings en este período."
            motivo={`Periodo consultado: próximos ${days} días.`}
            className="py-14"
          />
        </div>
      ) : grouped.length > 0 ? (
        <>
          <Heroe proximo={proximo} grupoProximo={proximo && symGroup[proximo.symbol?.toUpperCase()]}
                 total={total} fechas={grouped.length} reparto={reparto} days={days} eventos={eventos} />

          <section aria-labelledby="cal-agenda">
            <div className="flex items-baseline justify-between gap-4 mb-3.5">
              <h2 id="cal-agenda" className="font-heading text-[18px] font-semibold tracking-[-0.015em] text-tinta">
                Agenda
              </h2>
              <p className="iv-cifra text-[12.5px] text-tinta-3" aria-live="polite">
                {`${total} ${total === 1 ? "resultado" : "resultados"} · ${grouped.length} ${grouped.length === 1 ? "fecha" : "fechas"}`}
              </p>
            </div>

            <div className="iv-panel overflow-hidden">
              {/* Cabecera de columnas (escritorio) */}
              <div aria-hidden="true"
                   className="hidden lg:grid grid-cols-[132px_minmax(0,1fr)] border-b border-suave text-[12px] text-tinta-3">
                <span className="px-6 py-2.5">Fecha</span>
                <div className="grid grid-cols-[2rem_minmax(0,1fr)_7rem_9.5rem_7rem_1rem] gap-x-4 px-5 py-2.5">
                  <span />
                  <span>Valor</span>
                  <span>Trimestre</span>
                  <span>Momento</span>
                  <span className="text-right">EPS est.</span>
                  <span />
                </div>
              </div>
              <div className="divide-y divide-suave">
                {grouped.map(({ date, items }, i) => (
                  <Fecha key={date} date={date} items={items} symGroup={symGroup}
                         setSymbol={setSymbol} indice={i} />
                ))}
              </div>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
