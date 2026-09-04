import React, { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import PageShell from "@/components/base/PageShell";
import TarjetaAtencion from "@/components/base/TarjetaAtencion";
import Boton from "@/components/base/Boton";
import { Cargando, Error as ErrorEstado } from "@/components/base/Estado";
import { fmtHace } from "@/lib/format";
import { saludoDeLaHora, desgloseDe, titularDe } from "@/lib/portada";
import { MarketFuturesBar, FearGreedBar, SectorHeatmap } from "@/components/ContextoMercado";
import BandaRegimen from "@/components/hoy/BandaRegimen";
import PanelCartera from "@/components/hoy/PanelCartera";
import PanelAgenda from "@/components/hoy/PanelAgenda";
import PanelCerebro from "@/components/hoy/PanelCerebro";

/* Dashboard «Hoy» · la portada, rediseñada como terminal financiero
   ─────────────────────────────────────────────────────────────────────────────
   Contesta «¿qué merece mi atención hoy?» en el orden en que se hace la pregunta:

     1. La CINTA DE MERCADO abre arriba —régimen + SPY + futuros + miedo/codicia—:
        el estado del terreno de juego, en cifras, antes de decidir nada.
     2. El TITULAR responde la pregunta en una línea, en el mayor tamaño de la escala.
     3. LO QUE IMPORTA HOY, la columna ancha: hasta cinco tarjetas-fila con su lectura
        numérica. Es el bloque grande porque es la razón de existir de la pantalla.
     4. La BARRA LATERAL agrupa el contexto —cartera, agenda, cerebro— con jerarquía
        propia y compacta, en vez de las cuatro cajas del mismo peso de antes.
     5. El MAPA DE SECTORES cierra a pie de página: se consulta, no se opera.

   No se pierde ni un dato del inventario 1.1, y no se inventa ninguna métrica: cada
   cifra sale de `GET /hoy` o de las tres consultas de contexto de mercado. */

const CLAVE_ULTIMA_VISITA = "inveria-ultima-visita-hoy";

function leerUltimaVisita() {
  try {
    return localStorage.getItem(CLAVE_ULTIMA_VISITA) || undefined;
  } catch {
    return undefined;
  }
}

export default function HoyView() {
  const desde = useMemo(() => leerUltimaVisita(), []);

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

  return (
    <PageShell>
      {/* ── 0 · CABECERA ────────────────────────────────────────────────────
          Cintillo, saludo y las dos acciones. El saludo no informa de nada —para eso
          está el desglose de más abajo— pero sitúa: dice de quién es esta pantalla y
          en qué momento del día se abre. */}
      <header className="mb-6 flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2.5 mb-1.5">
            <span className="inline-block w-6 h-px bg-marca shrink-0" aria-hidden="true" />
            <span className="iv-etiqueta tracking-[0.16em] text-tinta-3">Panel de control</span>
            {!isLoading && !error && (
              <span className="iv-etiqueta tracking-[0.12em] text-sube border border-sube/40 rounded-iv-sm px-1.5 py-px">
                live
              </span>
            )}
          </p>
          <h1 className="font-heading text-cifra font-bold text-tinta leading-[1.15]">
            {saludoDeLaHora()}
          </h1>
          <p className="text-apoyo text-tinta-2 mt-1">
            El contexto que necesitas para decidir mejor hoy.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {data?.generado_en && (
            <span className="text-etiqueta text-tinta-3 hidden sm:inline mr-1">
              Calculado {fmtHace(data.generado_en)}
            </span>
          )}
          <Boton variante="fantasma" tamano="sm" onClick={() => refetch()} ocupado={isFetching}>
            Actualizar
          </Boton>
          {/* `?nueva=1` abre el formulario directamente: mandar a la Cartera y que ahí
              haya que buscar el botón otra vez convierte un atajo en un desvío. */}
          <Boton tamano="sm" asChild>
            <Link to="/cartera?nueva=1">+ Nueva acción</Link>
          </Boton>
        </div>
      </header>
      {/* ── 1 · CINTA DE MERCADO ────────────────────────────────────────────
          El estado del terreno de juego, arriba y en cifras. El régimen decide si
          fiarse de las señales; los futuros y el termómetro de miedo lo enmarcan. */}
      {!isLoading && !error && (
        <div className="space-y-2 mb-6">
          <BandaRegimen mercado={mercado} />
          <MarketFuturesBar futures={futures} />
          <FearGreedBar data={sentiment} />
        </div>
      )}

      {/* ── Terminal: lo que importa (ancho) + contexto (lateral) ──────────── */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_340px]">
        {/* Columna principal */}
        <div className="min-w-0">
          <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1 mb-3">
            <div className="min-w-0">
              <p className="iv-etiqueta tracking-[0.16em] text-tinta-3 mb-1">Lo que importa hoy</p>
              <h2 className="font-heading text-titulo font-bold text-tinta leading-tight">
                {titular ? "Decisiones que requieren tu atención" : "Hoy no hay decisiones pendientes"}
              </h2>
              {/* El desglose por tipo: es el dato que antes iba en el titular grande. */}
              {(desglose.length > 0 || data?.saludo?.piezas?.length > 0) && (
                <p className="text-apoyo text-tinta-3 mt-1">
                  {(desglose.length ? desglose : data.saludo.piezas).join(" · ")}
                </p>
              )}
            </div>
            {!isLoading && !error && importa.length > 0 && (
              <span className="iv-cifra text-etiqueta text-tinta-3 border border-linea rounded-iv-sm px-2 py-1 shrink-0">
                {importa.length} de {data?.saludo?.total ?? importa.length} · por urgencia
              </span>
            )}
          </div>

          {isLoading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="iv-panel p-5">
                  <Cargando filas={3} />
                </div>
              ))}
            </div>
          ) : error ? (
            <ErrorEstado
              error={error}
              onReintentar={refetch}
              titulo="No se ha podido preparar tu portada"
            />
          ) : importa.length === 0 ? (
            <div className="iv-destacada p-6">
              <p className="text-cuerpo text-tinta font-medium">
                Hoy no hay nada que requiera tu atención.
              </p>
              <p className="text-apoyo text-tinta-2 mt-1 max-w-[60ch]">
                Ningún nivel cerca, ninguna alerta saltada y nada nuevo en tus fuentes sobre lo
                que sigues. Es una respuesta, no un hueco.
              </p>
              <div className="flex gap-2 mt-4">
                <Boton variante="contorno" tamano="sm" asChild>
                  <Link to="/cartera">Ver la cartera</Link>
                </Boton>
                <Boton variante="fantasma" tamano="sm" asChild>
                  <Link to="/oportunidades">Buscar oportunidades</Link>
                </Boton>
              </div>
            </div>
          ) : (
            <>
              <div className="space-y-3">
                {importa.map((t, i) => (
                  <TarjetaAtencion key={`${t.symbol}-${t.tipo}`} tarjeta={t} orden={i + 1} />
                ))}
              </div>
              {importa.length < 3 && (
                <p className="text-apoyo text-tinta-3 mt-3">
                  {importa.length === 1
                    ? "Solo hay una cosa que mirar hoy."
                    : "Solo hay dos cosas que mirar hoy."}{" "}
                  La lista no se rellena para parecer más larga.
                </p>
              )}
            </>
          )}
        </div>

        {/* Barra lateral: contexto con jerarquía, no cuatro cajas iguales */}
        <aside className="min-w-0 lg:sticky lg:top-4 lg:self-start space-y-4">
          {isLoading ? (
            <div className="iv-panel p-4"><Cargando filas={4} /></div>
          ) : (
            <>
              <PanelCartera cartera={cartera} />
              <PanelAgenda eventos={data?.proximos_7_dias} />
              <PanelCerebro cerebro={cerebro} />
            </>
          )}
        </aside>
      </div>

      {/* ── 5 · MAPA DE SECTORES ────────────────────────────────────────────
          Cierra a pie de página: es lectura del mercado, no una decisión de hoy. */}
      <div className="mt-6">
        <SectorHeatmap data={heatmap} />
      </div>
    </PageShell>
  );
}
