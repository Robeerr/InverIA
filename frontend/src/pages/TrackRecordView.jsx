import React, { useEffect, useState, useCallback } from "react";
import { ArrowClockwise, CheckCircle, XCircle, Clock } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { lecturaBenchmark, notaCostes } from "../lib/trackRecord";
import { cn } from "@/lib/utils";
import Boton from "@/components/base/Boton";
import { Cargando, Error as ErrorEstado } from "@/components/base/Estado";

// Auto-examen honesto del sistema: ¿funcionaron las señales de COMPRA del motor?
// Lee /track-record (evalúa qué hizo el precio tras cada análisis) y lo muestra sin
// adornos: aciertos, fallos, abiertas, % de acierto y retorno medio.
//
// Presentación (rediseño): antes eran once cajas del mismo peso más una caja por
// señal. Ahora las cifras van en tiras con filetes dentro de un único panel por
// bloque, la lista de señales es una tabla compacta con el resultado alineado a la
// derecha en dígitos tabulares, y el color solo marca subidas, bajadas y avisos.

const RES = {
  tp1: { c: "rgb(var(--iv-sube))", label: "Acierto", Icon: CheckCircle },
  stop: { c: "rgb(var(--iv-baja))", label: "Fallo", Icon: XCircle },
  abierta: { c: "rgb(var(--iv-aviso))", label: "Abierta", Icon: Clock },
};

const PERIODOS = [90, 180, 365];

/** Una celda de la tira de cifras: rótulo arriba, cifra tabular, nota debajo.
 *  `grande` para las métricas principales; el resto, un escalón por debajo. */
function Stat({ label, value, sub, color, grande = false }) {
  return (
    <div className="bg-superficie px-3 sm:px-4 py-3.5 min-w-0">
      <p className="iv-etiqueta break-words">{label}</p>
      <p
        className={cn("iv-cifra font-semibold mt-1.5 leading-none break-words",
          grande ? "text-[clamp(20px,5.5vw,26px)]" : "text-titulo")}
        style={{ color: color || "rgb(var(--iv-tinta))" }}
      >
        {value}
      </p>
      {sub && <p className="text-etiqueta text-tinta-3 mt-1.5">{sub}</p>}
    </div>
  );
}

/** Rejilla de celdas separadas por filetes de 1px (el hueco deja ver la línea). */
function Tira({ children, cols = "grid-cols-2 sm:grid-cols-4", className }) {
  return <div className={cn("grid gap-px bg-linea", cols, className)}>{children}</div>;
}

/** Cabecera de bloque dentro de un panel. */
function Cabecera({ id, children, extra }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-4 pt-4 pb-3">
      <h2 id={id} className="font-heading text-cuerpo font-semibold text-tinta text-balance">{children}</h2>
      {extra}
    </div>
  );
}

export default function TrackRecordView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(180);

  const load = useCallback(async (d, refresh = false) => {
    setLoading(true);
    try { setData(await api.trackRecord(d, refresh)); }
    catch (e) { toast.error("No se pudo cargar el track record"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(days); }, [load, days]);

  const s = data || {};
  // Qué se ha descontado y qué se ha quitado: un supuesto escondido se lee como un dato.
  const nota = notaCostes(s.costes, s.duplicadas_descartadas);
  const señales = s["señales"] || s.senales || [];

  return (
    <div className="space-y-5">
      <header className="iv-veredicto flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h1 className="iv-verbo text-tinta">Track record</h1>
          <p className="text-cuerpo text-tinta-2 mt-3 max-w-[58ch]">
            ¿Funcionan las señales de COMPRA del motor? Sin autoengaño.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Selector de periodo: control segmentado, un solo contenedor en vez de tres píldoras sueltas */}
          <div role="group" aria-label="Periodo evaluado"
               className="inline-flex items-center gap-0.5 p-0.5 rounded-full border border-linea bg-superficie">
            {PERIODOS.map((d) => (
              <button key={d} type="button" onClick={() => setDays(d)} aria-pressed={days === d}
                className={cn(
                  "h-8 px-3.5 rounded-full text-apoyo font-semibold iv-cifra",
                  "transition-[color,background-color,transform] duration-150 ease-out active:scale-[0.97]",
                  "motion-reduce:transition-none motion-reduce:active:scale-100",
                  days === d ? "bg-marca text-marca-tinta" : "text-tinta-3 hover:text-tinta"
                )}>
                {d === 365 ? "1 año" : `${d} días`}
              </button>
            ))}
          </div>
          <Boton variante="fantasma" tamano="sm" onClick={() => load(days, true)} disabled={loading}
                 title="Recargar (datos frescos)" aria-busy={loading || undefined}>
            <ArrowClockwise size={15} weight="bold" aria-hidden="true"
              className={cn("text-marca", loading && "animate-spin motion-reduce:animate-none")} />
            Recargar
          </Boton>
        </div>
      </header>

      {loading ? (
        <div className="space-y-5" aria-label="Evaluando señales…">
          <div className="iv-panel p-5"><Cargando filas={3} etiqueta="Evaluando señales…" /></div>
          <div className="iv-panel p-5"><Cargando filas={5} etiqueta="Evaluando señales…" /></div>
        </div>
      ) : !data ? (
        <ErrorEstado
          error={{ message: "El servidor no ha devuelto la evaluación de las señales." }}
          onReintentar={() => load(days)}
          titulo="No se pudo cargar el track record"
        />
      ) : s.total === 0 ? (
        <div className="iv-panel px-6 py-10 text-center">
          <p className="text-cuerpo text-tinta font-semibold">Aún no hay señales que evaluar</p>
          <p className="text-apoyo text-tinta-3 mt-1 max-w-[52ch] mx-auto">Cuando el motor genere análisis de COMPRA y pase algún tiempo, aparecerán aquí con su resultado real.</p>
        </div>
      ) : (
        <>
          {/* Resumen principal: acierto + esperanza (el que dice si gana dinero), y debajo
              el desglose ganancia/pérdida y cerradas vs abiertas. Un solo panel. */}
          <section className="iv-panel overflow-hidden" aria-labelledby="tr-resumen">
            <h2 id="tr-resumen" className="sr-only">Resumen de las señales</h2>
            <Tira>
              <Stat grande label="% Acierto" value={s.win_rate != null ? `${s.win_rate}%` : "—"}
                sub={`${s.aciertos}✓ / ${s.fallos}✗`}
                color={s.win_rate == null ? "rgb(var(--iv-tinta-3))" : s.win_rate >= 55 ? "rgb(var(--iv-sube))" : s.win_rate >= 45 ? "rgb(var(--iv-aviso))" : "rgb(var(--iv-baja))"} />
              <Stat grande label="Esperanza / op." value={s.esperanza != null ? `${s.esperanza > 0 ? "+" : ""}${s.esperanza}%` : "—"}
                sub="por señal cerrada"
                color={s.esperanza == null ? "rgb(var(--iv-tinta-3))" : s.esperanza > 0 ? "rgb(var(--iv-sube))" : "rgb(var(--iv-baja))"} />
              <Stat grande label="Ratio R/R" value={s.ratio_rr != null ? `${s.ratio_rr}:1` : "—"}
                sub="ganancia / pérdida"
                color={s.ratio_rr == null ? "rgb(var(--iv-tinta-3))" : s.ratio_rr >= 1.5 ? "rgb(var(--iv-sube))" : s.ratio_rr >= 1 ? "rgb(var(--iv-aviso))" : "rgb(var(--iv-baja))"} />
              <Stat grande label="Señales" value={s.total} sub={`${s.abiertas} abiertas`} />
            </Tira>
            <Tira className="border-t border-linea">
              <Stat label="Ganancia media" value={s.ganancia_media != null ? `+${s.ganancia_media}%` : "—"} sub="cuando acierta" color="rgb(var(--iv-sube))" />
              <Stat label="Pérdida media" value={s.perdida_media != null ? `${s.perdida_media}%` : "—"} sub="cuando falla" color="rgb(var(--iv-baja))" />
              <Stat label="Retorno cerradas" value={s.retorno_medio_cerradas != null ? `${s.retorno_medio_cerradas > 0 ? "+" : ""}${s.retorno_medio_cerradas}%` : "—"} sub="resultado real"
                color={(s.retorno_medio_cerradas || 0) > 0 ? "rgb(var(--iv-sube))" : (s.retorno_medio_cerradas || 0) < 0 ? "rgb(var(--iv-baja))" : "rgb(var(--iv-tinta-3))"} />
              <Stat label="P&L abiertas" value={s.pl_abiertas != null ? `${s.pl_abiertas > 0 ? "+" : ""}${s.pl_abiertas}%` : "—"} sub="en curso"
                color={(s.pl_abiertas || 0) > 0 ? "rgb(var(--iv-sube))" : (s.pl_abiertas || 0) < 0 ? "rgb(var(--iv-baja))" : "rgb(var(--iv-tinta-3))"} />
            </Tira>
          </section>

          {/* Benchmark: ¿bate el motor a comprar y mantener el índice? */}
          {s.benchmark && (() => {
            // Verde solo si gana dinero Y bate al índice: perder menos que el mercado no
            // es «aportar valor».
            const l = lecturaBenchmark(s.benchmark);
            const color = `rgb(var(--iv-${l.tono}))`;
            const signo = (x) => `${x > 0 ? "+" : ""}${x}%`;
            return (
              <section className="iv-panel overflow-hidden" aria-labelledby="tr-benchmark">
                <Cabecera id="tr-benchmark">¿Gana dinero y bate al índice? (vs comprar S&P 500)</Cabecera>
                {/* El veredicto, en palabras y con su tono: es la conclusión del bloque. */}
                <p className="flex gap-2.5 px-4 pb-4 text-apoyo text-tinta font-medium leading-relaxed max-w-[75ch]">
                  <span aria-hidden="true" className="mt-[7px] h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
                  <span>{l.texto}</span>
                </p>
                <Tira cols="grid-cols-3" className="border-t border-linea">
                  <Stat label="Tu motor" value={signo(s.benchmark.sistema_medio)}
                    sub="retorno medio, neto" color={s.benchmark.sistema_medio > 0 ? "rgb(var(--iv-sube))" : "rgb(var(--iv-baja))"} />
                  <Stat label="S&P 500" value={signo(s.benchmark.spy_medio)}
                    sub="misma ventana" color={s.benchmark.spy_medio > 0 ? "rgb(var(--iv-sube))" : "rgb(var(--iv-baja))"} />
                  <Stat label="Diferencia" value={signo(s.benchmark.alpha)}
                    sub={s.benchmark.alpha >= 0 ? "a favor del motor" : "a favor del índice"}
                    color={s.benchmark.alpha >= 0 ? "rgb(var(--iv-tinta-2))" : "rgb(var(--iv-baja))"} />
                </Tira>
                <p className="border-t border-linea px-4 py-3 text-etiqueta text-tinta-3 leading-relaxed">{l.metodo}</p>
              </section>
            );
          })()}

          {nota && (
            <p className="text-etiqueta text-tinta-3 leading-relaxed px-1 max-w-[95ch]">{nota}</p>
          )}

          {/* Escenario TP2: qué pasa si aguantas hasta el objetivo mayor */}
          {s.tp2 && (
            <section className="iv-panel overflow-hidden" aria-labelledby="tr-tp2">
              <Cabecera id="tr-tp2">Si aguantas hasta TP2 (objetivo mayor)</Cabecera>
              <Tira className="border-t border-linea">
                <Stat label="% Acierto" value={s.tp2.win_rate != null ? `${s.tp2.win_rate}%` : "—"}
                  sub={`${s.tp2.aciertos}✓ / ${s.tp2.fallos}✗`}
                  color={s.tp2.win_rate == null ? "rgb(var(--iv-tinta-3))" : s.tp2.win_rate >= 50 ? "rgb(var(--iv-sube))" : s.tp2.win_rate >= 40 ? "rgb(var(--iv-aviso))" : "rgb(var(--iv-baja))"} />
                <Stat label="Esperanza / op." value={s.tp2.esperanza != null ? `${s.tp2.esperanza > 0 ? "+" : ""}${s.tp2.esperanza}%` : "—"}
                  sub="por señal cerrada"
                  color={s.tp2.esperanza == null ? "rgb(var(--iv-tinta-3))" : s.tp2.esperanza > 0 ? "rgb(var(--iv-sube))" : "rgb(var(--iv-baja))"} />
                <Stat label="Ratio R/R" value={s.tp2.ratio_rr != null ? `${s.tp2.ratio_rr}:1` : "—"}
                  sub="ganancia / pérdida"
                  color={s.tp2.ratio_rr == null ? "rgb(var(--iv-tinta-3))" : s.tp2.ratio_rr >= 1.5 ? "rgb(var(--iv-sube))" : s.tp2.ratio_rr >= 1 ? "rgb(var(--iv-aviso))" : "rgb(var(--iv-baja))"} />
                <Stat label="Ganancia media" value={s.tp2.ganancia_media != null ? `+${s.tp2.ganancia_media}%` : "—"} sub="cuando acierta" color="rgb(var(--iv-sube))" />
              </Tira>
              <p className="border-t border-linea px-4 py-3 text-etiqueta text-tinta-3 leading-relaxed">
                Mismo motor, pero cerrando en el <b className="text-tinta-2 font-semibold">segundo objetivo</b> en vez del primero. Aciertas
                menos veces (cuesta más llegar) pero ganas más por acierto — compara la esperanza y el R/R
                con los de arriba (TP1) para ver qué salida te renta más.
              </p>
            </section>
          )}

          {/* Nota honesta */}
          <p className="text-etiqueta text-tinta-3 leading-relaxed px-1 max-w-[95ch]">
            La <b className="text-tinta-2 font-semibold">esperanza por operación</b> es lo que importa: cuánto ganas de media por señal cerrada
            (pondera aciertos y fallos). Si es positiva, el motor gana dinero aunque falle a veces.
            El <b className="text-tinta-2 font-semibold">ratio R/R</b> ideal es ≥1.5:1. Acierto = tocó <b className="text-tinta-2 font-semibold">take-profit</b> antes que el stop; el stop se
            cuenta primero (conservador). Las <b className="text-tinta-2 font-semibold">abiertas</b> aún no han tocado ninguno.
          </p>

          {/* Detalle: una tabla compacta, no una caja por señal */}
          {señales.length > 0 && (
            <section className="iv-panel overflow-hidden" aria-labelledby="tr-detalle">
              <Cabecera id="tr-detalle">Señal a señal</Cabecera>
              {/* Rótulos de columna (solo escritorio: en móvil la fila ya se explica sola) */}
              <div aria-hidden="true"
                   className="hidden sm:flex items-center gap-3 px-4 py-2 border-t border-linea iv-etiqueta">
                <span className="flex-1 pl-[30px]">Acción · fecha · entrada</span>
                <span className="w-20">Resultado</span>
                <span className="w-20 text-right">Retorno</span>
              </div>
              <ul className="divide-y divide-linea border-t border-linea">
                {señales.map((r, i) => {
                  const meta = RES[r.resultado] || RES.abierta;
                  return (
                    <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                      <meta.Icon size={18} weight="fill" style={{ color: meta.c }} className="shrink-0" aria-hidden="true" />
                      <div className="min-w-0 flex-1">
                        <p className="iv-cifra font-semibold text-apoyo text-tinta">{r.symbol}</p>
                        <p className="iv-cifra text-etiqueta text-tinta-3 break-words">{r.fecha} · entrada ${r.entrada}</p>
                      </div>
                      <div className="shrink-0 flex flex-col items-end sm:flex-row sm:items-center sm:gap-3">
                        <span className="text-etiqueta font-semibold sm:w-20" style={{ color: meta.c }}>{meta.label}</span>
                        <span className="iv-cifra text-apoyo font-semibold sm:w-20 text-right"
                          style={{ color: r.retorno == null ? undefined : r.retorno > 0 ? "rgb(var(--iv-sube))" : r.retorno < 0 ? "rgb(var(--iv-baja))" : "rgb(var(--iv-tinta-3))" }}>
                          {r.retorno != null ? <>{r.retorno > 0 ? "+" : ""}{r.retorno}%</> : null}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
