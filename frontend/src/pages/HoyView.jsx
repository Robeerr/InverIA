import React, { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { Plus, RefreshCw, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import PageShell from "@/components/base/PageShell";
import TarjetaAtencion, { esUrgente } from "@/components/base/TarjetaAtencion";
import Boton from "@/components/base/Boton";
import { Cargando, Error as ErrorEstado } from "@/components/base/Estado";
import { fmtHace } from "@/lib/format";
import { saludoDeLaHora, nombreDe, desgloseDe, titularDe } from "@/lib/portada";
import { MarketFuturesBar, FearGreedBar, SectorHeatmap } from "@/components/ContextoMercado";
import BandaRegimen from "@/components/hoy/BandaRegimen";
import PanelCartera from "@/components/hoy/PanelCartera";
import PanelAgenda from "@/components/hoy/PanelAgenda";
import PanelCerebro from "@/components/hoy/PanelCerebro";

/* «Hoy» · la portada
   ─────────────────────────────────────────────────────────────────────────────
   Contesta «¿qué merece mi atención hoy?» en dos columnas con papeles distintos:

     COLUMNA PRINCIPAL — lo tuyo, en el orden en que se mira:
       1. La CARTERA como métrica héroe: el valor es la cifra que se abre a ver.
       2. LO QUE IMPORTA HOY: una única lista, agrupada en «piden decisión» y «para
          vigilar», con las cifras de cada fila en una columna fija que se lee como
          una tabla. Es el bloque grande porque es la razón de existir de la pantalla.

     COLUMNA DE CONTEXTO — el terreno de juego, que se consulta y no se opera:
       3. MERCADO: régimen (la condición bajo la que se leen las decisiones), futuros
          y miedo/codicia, en un solo panel con filetes.
       4. Calendario de resultados y novedades del Cerebro.
       5. Sectores, como barras divergentes.

   En móvil la columna de contexto baja entera detrás de las decisiones: primero lo
   que pide actuar, luego el marco.

   No se pierde ni un dato del inventario 1.1, y no se inventa ninguna métrica: cada
   cifra sale de `GET /hoy` o de las tres consultas de contexto de mercado. */

const CLAVE_ULTIMA_VISITA = "inveria-ultima-visita-hoy";

/** «Martes, 8 de septiembre». Sitúa la pantalla en el día sin que haya que mirar el
 *  reloj del sistema, que es justo lo que se hace al abrir un panel por la mañana. */
function fechaLarga(d = new Date()) {
  const t = d.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Parte la lista en tramos para pintarla: las urgentes consecutivas van juntas bajo
 *  «Piden decisión»; las informativas consecutivas, bajo «Para vigilar». No reordena
 *  nada — el orden es el del servidor, y si una informativa cae entre dos urgentes,
 *  abre su propio tramo. */
function segmentosDe(lista) {
  const tramos = [];
  lista.forEach((t, i) => {
    const item = { t, orden: i + 1, indice: i };
    const urgente = esUrgente(t);
    const ultimo = tramos[tramos.length - 1];
    if (ultimo && ultimo.urgente === urgente) ultimo.items.push(item);
    else tramos.push({ urgente, clave: `${t.symbol}-${t.tipo}`, items: [item] });
  });
  return tramos;
}

function leerUltimaVisita() {
  try {
    return localStorage.getItem(CLAVE_ULTIMA_VISITA) || undefined;
  } catch {
    return undefined;
  }
}

/** Esqueleto con la FORMA de lo que viene: monograma, dos líneas y la columna de
 *  cifras. Un spinner diría «espera»; esto dice además «esto es lo que vas a ver». */
function FilaEsqueleto() {
  return (
    <div className="px-4 py-5 sm:px-6 grid grid-cols-[40px_minmax(0,1fr)] lg:grid-cols-[40px_minmax(0,1fr)_264px] gap-x-4 lg:gap-x-6">
      <span className="w-10 h-10 rounded-[11px] iv-esqueleto" />
      <div className="space-y-2.5 pt-1">
        <span className="block h-3.5 w-28 rounded iv-esqueleto" />
        <span className="block h-4 w-4/5 rounded iv-esqueleto" />
        <span className="block h-3.5 w-3/5 rounded iv-esqueleto" />
      </div>
      <div className="hidden lg:grid grid-cols-2 gap-3 pl-6">
        {[0, 1, 2, 3].map((i) => <span key={i} className="block h-8 rounded iv-esqueleto" />)}
      </div>
    </div>
  );
}

export default function HoyView() {
  const desde = useMemo(() => leerUltimaVisita(), []);
  // `nombreDe` devuelve null para los identificadores genéricos («admin», «user»…),
  // y entonces se saluda sin nombre. Equivocarse saludando es peor que no saludar.
  const { user } = useAuth();
  const nombreUsuario = nombreDe(user);

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["hoy", desde],
    queryFn: () => api.hoy(desde),
    staleTime: 120_000,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    if (!data) return;
    try {
      localStorage.setItem(CLAVE_ULTIMA_VISITA, new Date().toISOString());
    } catch {
      /* modo incógnito: no poder recordar la visita no debe romper la página */
    }
  }, [data]);

  const importa = data?.importa_hoy || [];
  const titular = titularDe(importa);
  const cartera = data?.cartera || {};
  const cerebro = data?.cerebro || {};
  const mercado = data?.mercado;

  // Contexto de mercado, misma cadencia que tenía en la ficha de acción.
  const { data: futures } = useQuery({
    queryKey: ["market-futures"],
    queryFn: api.marketFutures,
    refetchInterval: 60_000,
    staleTime: 60_000,
  });
  const { data: sentiment } = useQuery({
    queryKey: ["market-sentiment"],
    queryFn: api.marketSentiment,
    refetchInterval: 15 * 60_000,
    staleTime: 15 * 60_000,
  });
  const { data: heatmap } = useQuery({
    queryKey: ["market-heatmap"],
    queryFn: api.marketHeatmap,
    refetchInterval: 5 * 60_000,
    staleTime: 5 * 60_000,
  });

  const desglose = desgloseDe(data?.saludo?.conteo);
  const resumen = desglose.length > 0 ? desglose : (data?.saludo?.piezas || []);

  return (
    <PageShell>
      {/* ── CABECERA ──────────────────────────────────────────────────────────
          La fecha y la frescura van ENCIMA del saludo, en pequeño, como antetítulo de
          producto: el saludo se lee primero por tamaño, y «calculado hace…» es la nota
          que dice si fiarse de lo demás. */}
      <header className="iv-veredicto mb-6 sm:mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <p className="text-[13px] text-tinta-3 flex flex-wrap items-center gap-x-2">
            <span>{fechaLarga()}</span>
            {data?.generado_en && (
              <>
                <span aria-hidden="true" className="w-[3px] h-[3px] rounded-full bg-tinta-3/60" />
                <span>Calculado {fmtHace(data.generado_en)}</span>
              </>
            )}
          </p>
          <h1 className="iv-verbo text-tinta mt-2">
            {saludoDeLaHora()}{nombreUsuario ? `, ${nombreUsuario}` : ""}
          </h1>
          <p className="hidden sm:block text-[14.5px] text-tinta-2 mt-2.5 max-w-[58ch]">
            No necesitas mirar todo. Solo saber qué importa ahora.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Boton variante="secundario" tamano="md" onClick={() => refetch()} ocupado={isFetching}>
            <RefreshCw className={cn("w-3.5 h-3.5", isFetching && "animate-spin motion-reduce:animate-none")}
                       strokeWidth={2} aria-hidden="true" />
            Actualizar
          </Boton>
          {/* `?nueva=1` abre el formulario directamente: mandar a la Cartera y que ahí
              haya que buscar el botón otra vez convierte un atajo en un desvío. */}
          <Boton tamano="md" asChild>
            <Link to="/cartera?nueva=1">
              <Plus className="w-4 h-4" strokeWidth={2.25} aria-hidden="true" />
              Nueva acción
            </Link>
          </Boton>
        </div>
      </header>

      <div className="grid gap-5 lg:gap-6 lg:grid-cols-[minmax(0,1fr)_336px] xl:grid-cols-[minmax(0,1fr)_364px] items-start">
        {/* ── COLUMNA PRINCIPAL ─────────────────────────────────────────────── */}
        <div className="min-w-0 space-y-8 sm:space-y-10">
          {isLoading ? (
            <div className="iv-panel p-5 sm:p-7 space-y-4">
              <span className="block h-3.5 w-24 rounded iv-esqueleto" />
              <span className="block h-12 w-64 max-w-full rounded-lg iv-esqueleto" />
              <span className="block h-6 w-40 rounded iv-esqueleto" />
            </div>
          ) : !error && (
            <PanelCartera cartera={cartera} />
          )}

          <section aria-labelledby="hoy-decisiones">
            <div className="mb-4">
              <h2 id="hoy-decisiones"
                  className="text-[20px] sm:text-[22px] font-semibold tracking-[-0.03em] text-tinta leading-tight text-balance">
                {/* Mientras carga o si falla NO se sabe si hay decisiones: decir «no hay»
                    antes de tener los datos es afirmar algo falso. */}
                {isLoading ? "Revisando qué importa hoy…"
                  : error ? "Lo que importa hoy"
                  : titular ? "Decisiones que requieren tu atención" : "Hoy no hay decisiones pendientes"}
              </h2>
              {/* El desglose por tipo y el recuento, en una sola línea de apoyo, sin caja. */}
              {(resumen.length > 0 || (!isLoading && !error && importa.length > 0)) && (
                <p className="text-[13px] text-tinta-3 mt-1.5 flex flex-wrap items-center gap-x-2">
                  {resumen.length > 0 && <span>{resumen.join(" · ")}</span>}
                  {!isLoading && !error && importa.length > 0 && (
                    <>
                      {resumen.length > 0 && (
                        <span aria-hidden="true" className="w-[3px] h-[3px] rounded-full bg-tinta-3/60" />
                      )}
                      <span>
                        <span className="iv-cifra">{importa.length}</span> de{" "}
                        <span className="iv-cifra">{data?.saludo?.total ?? importa.length}</span> · por urgencia
                      </span>
                    </>
                  )}
                </p>
              )}
            </div>

            {isLoading ? (
              <div className="iv-panel overflow-hidden [&>*+*]:border-t [&>*+*]:border-suave">
                <span className="sr-only" role="status">Cargando…</span>
                {[0, 1, 2].map((i) => <FilaEsqueleto key={i} />)}
              </div>
            ) : error ? (
              <ErrorEstado
                error={error}
                onReintentar={refetch}
                titulo="No se ha podido preparar tu portada"
              />
            ) : importa.length === 0 ? (
              <div className="iv-destacada p-6 sm:p-7 flex gap-4">
                <CheckCircle2 className="w-5 h-5 text-marca shrink-0 mt-0.5" strokeWidth={1.75} aria-hidden="true" />
                <div className="min-w-0">
                  <p className="text-[15px] text-tinta font-medium">
                    Hoy no hay nada que requiera tu atención.
                  </p>
                  <p className="text-[13.5px] text-tinta-2 mt-1 max-w-[60ch] leading-relaxed">
                    Ningún nivel cerca, ninguna alerta saltada y nada nuevo en tus fuentes sobre lo
                    que sigues. Es una respuesta, no un hueco.
                  </p>
                  <div className="flex flex-wrap gap-2 mt-4">
                    <Boton variante="secundario" tamano="sm" asChild>
                      <Link to="/cartera">Ver la cartera</Link>
                    </Boton>
                    <Boton variante="fantasma" tamano="sm" asChild>
                      <Link to="/oportunidades">Buscar oportunidades</Link>
                    </Boton>
                  </div>
                </div>
              </div>
            ) : (
              <>
                {/* Una sola lista en un solo panel, partida en tramos rotulados. Se
                    respeta el orden de urgencia que manda el servidor: solo se agrupan
                    las filas CONSECUTIVAS del mismo tipo. */}
                <div className="iv-panel overflow-hidden">
                  {segmentosDe(importa).map((seg, n) => (
                    <div key={seg.clave} className={cn(n > 0 && "border-t border-suave")}>
                      <div className="flex items-center justify-between gap-3 px-4 sm:px-6 h-10
                                      bg-tinta/[0.025] border-b border-suave">
                        <p className="flex items-center gap-2 text-[12px] font-medium text-tinta-2">
                          <span className={cn("w-1.5 h-1.5 rounded-full", seg.urgente ? "bg-aviso" : "bg-marca")}
                                aria-hidden="true" />
                          {seg.urgente ? "Piden decisión" : "Para vigilar"}
                        </p>
                        <span className="iv-cifra text-[12px] text-tinta-3">{seg.items.length}</span>
                      </div>
                      <div className="[&>*+*]:border-t [&>*+*]:border-suave">
                        {seg.items.map(({ t, orden, indice }) => (
                          <TarjetaAtencion key={`${t.symbol}-${t.tipo}`} tarjeta={t} orden={orden} indice={indice} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                {importa.length < 3 && (
                  <p className="text-[13px] text-tinta-3 mt-3">
                    {importa.length === 1
                      ? "Solo hay una cosa que mirar hoy."
                      : "Solo hay dos cosas que mirar hoy."}{" "}
                    La lista no se rellena para parecer más larga.
                  </p>
                )}
              </>
            )}
          </section>
        </div>

        {/* ── COLUMNA DE CONTEXTO ───────────────────────────────────────────── */}
        <aside className="min-w-0 space-y-5 lg:space-y-6" aria-label="Contexto de mercado">
          {isLoading ? (
            <div className="iv-panel p-5 sm:p-6"><Cargando filas={5} /></div>
          ) : !error && (
            // Un solo panel con filetes internos: régimen arriba, futuros y miedo/codicia
            // debajo. Son tres lecturas del mismo terreno de juego.
            <div className="iv-panel overflow-hidden [&>*+*]:border-t [&>*+*]:border-suave">
              <BandaRegimen mercado={mercado} />
              <MarketFuturesBar futures={futures} />
              <FearGreedBar data={sentiment} />
            </div>
          )}

          {!isLoading && !error && (
            <div className="iv-panel overflow-hidden [&>*+*]:border-t [&>*+*]:border-suave">
              <PanelAgenda eventos={data?.proximos_7_dias} />
              <PanelCerebro cerebro={cerebro} />
            </div>
          )}

          {/* Sectores: lectura del mercado, no una decisión de hoy. Cierra la columna. */}
          <SectorHeatmap data={heatmap} />
        </aside>
      </div>
    </PageShell>
  );
}
