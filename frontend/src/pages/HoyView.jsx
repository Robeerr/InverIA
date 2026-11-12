import React, { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
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

/** «Martes, 8 de septiembre». Sitúa la pantalla en el día sin que haya que mirar el
 *  reloj del sistema, que es justo lo que se hace al abrir un panel por la mañana. */
function fechaLarga(d = new Date()) {
  const t = d.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Parte la lista en tramos para pintarla: cada urgente va sola; las informativas
 *  consecutivas van juntas. No reordena nada — el orden es el del servidor. */
function segmentosDe(lista) {
  const tramos = [];
  lista.forEach((t, i) => {
    const item = { t, orden: i + 1 };
    const urgente = esUrgente(t);
    const ultimo = tramos[tramos.length - 1];
    if (!urgente && ultimo && !ultimo.urgente) ultimo.items.push(item);
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

  return (
    <PageShell>
      {/* ── 0 · CABECERA. El régimen sube AQUÍ, a la derecha del saludo, en vez de ocupar
          una banda propia debajo: es la condición bajo la que se leen las decisiones
          que vienen después, no una decisión más. Su lectura completa —SPY, medias,
          distancia— sigue estando entera en el panel de abajo. */}
      <header className="iv-veredicto mb-6 sm:mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h1 className="iv-verbo text-tinta">
            {saludoDeLaHora()}{nombreUsuario ? `, ${nombreUsuario}` : ""}
          </h1>
          {/* La fecha y la frescura, DEBAJO del saludo y no como antetítulo: el saludo se
              lee primero, y «calculado hace…» es la nota que dice si fiarse de lo demás. */}
          <p className="iv-cifra text-etiqueta text-tinta-3 mt-2.5 flex flex-wrap gap-x-2">
            <span>{fechaLarga()}</span>
            {data?.generado_en && (
              <>
                <span aria-hidden="true" className="text-linea-marcada">·</span>
                <span>Calculado {fmtHace(data.generado_en)}</span>
              </>
            )}
          </p>
          <p className="hidden sm:block text-cuerpo text-tinta-2 mt-2 max-w-[58ch]">
            No necesitas mirar todo. Solo saber qué importa ahora.
          </p>
        </div>

        {/* El régimen ya no se repite aquí en una pastilla: se lee entero en el panel de
            mercado justo debajo, con sus cifras. */}
        <div className="flex items-center gap-2 shrink-0 flex-wrap">
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
      {/* Un solo panel con filetes internos: régimen arriba; futuros y miedo/codicia
          debajo, lado a lado en escritorio. Antes eran tres cajas apiladas. */}
      {!isLoading && !error && (
        <div className="iv-panel overflow-hidden mb-8 divide-y divide-linea">
          <BandaRegimen mercado={mercado} />
          {(futures?.items?.length > 0 || sentiment?.score != null) && (
            <div className="flex flex-col lg:flex-row divide-y lg:divide-y-0 lg:divide-x divide-linea
                            lg:[&>*]:flex-1 [&>*]:min-w-0">
              <MarketFuturesBar futures={futures} />
              <FearGreedBar data={sentiment} />
            </div>
          )}
        </div>
      )}

      {/* ── Terminal: lo que importa (ancho) + contexto (lateral) ──────────── */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_340px]">
        {/* Columna principal */}
        <div className="min-w-0">
          {/* La cabecera de sección con filete corrido, en su variante de acento: esta
              es la sección PRINCIPAL de la portada y la única que lo lleva. */}
          {/* El titular de la sección ES la cabecera con filete de acento: antes llevaba
              además un antetítulo («Lo que importa hoy») que decía lo mismo. */}
          <div className="iv-seccion iv-seccion-acento !mb-1.5">
            <h2 className="font-heading text-titulo font-semibold text-tinta leading-tight min-w-0 text-balance">
              {/* Mientras carga o si falla NO se sabe si hay decisiones: decir «no hay»
                  antes de tener los datos es afirmar algo falso. */}
              {isLoading ? "Revisando qué importa hoy…"
                : error ? "Lo que importa hoy"
                : titular ? "Decisiones que requieren tu atención" : "Hoy no hay decisiones pendientes"}
            </h2>
          </div>
          {/* El desglose por tipo y el recuento, en una sola línea de apoyo, sin caja. */}
          <p className="text-apoyo text-tinta-3 mb-4 flex flex-wrap gap-x-2">
            {(desglose.length > 0 || data?.saludo?.piezas?.length > 0) && (
              <span>{(desglose.length ? desglose : data.saludo.piezas).join(" · ")}</span>
            )}
            {!isLoading && !error && importa.length > 0 && (
              <span className="iv-cifra text-etiqueta self-center">
                {(desglose.length > 0 || data?.saludo?.piezas?.length > 0) && (
                  <span aria-hidden="true" className="text-linea-marcada mr-2">—</span>
                )}
                {importa.length} de {data?.saludo?.total ?? importa.length} · por urgencia
              </span>
            )}
          </p>

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
              {/* Urgentes como tarjeta con halo; informativas seguidas, juntas en un único
                  panel con filetes. Se respeta el orden de urgencia que manda el servidor:
                  solo se agrupan las informativas CONSECUTIVAS. */}
              <div className="space-y-3">
                {segmentosDe(importa).map((seg) => (
                  seg.urgente ? (
                    <TarjetaAtencion key={seg.clave} tarjeta={seg.items[0].t} orden={seg.items[0].orden} />
                  ) : (
                    <div key={seg.clave} className="iv-panel overflow-hidden divide-y divide-linea">
                      {seg.items.map(({ t, orden }) => (
                        <TarjetaAtencion key={`${t.symbol}-${t.tipo}`} tarjeta={t} orden={orden} />
                      ))}
                    </div>
                  )
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
              <div className="iv-panel overflow-hidden divide-y divide-linea">
                <PanelAgenda eventos={data?.proximos_7_dias} />
                <PanelCerebro cerebro={cerebro} />
              </div>
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
