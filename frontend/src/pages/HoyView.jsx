import React, { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import PageShell from "@/components/base/PageShell";
import TarjetaAtencion from "@/components/base/TarjetaAtencion";
import Metrica from "@/components/base/Metrica";
import Chip from "@/components/base/Chip";
import Boton from "@/components/base/Boton";
import { Cargando, Error as ErrorEstado } from "@/components/base/Estado";
import { fmtEur, fmtHace, fmtPct, fmtEnDias } from "@/lib/format";

/* Dashboard «Hoy» · la portada
   ─────────────────────────────────────────────────────────────────────────────
   Contesta tres preguntas en el orden en que se hacen al abrir la app:

       ¿Qué merece mi atención hoy?  → el bloque grande, máximo cinco
       ¿Por qué?                     → dentro de cada tarjeta
       ¿Qué debería revisar?         → dentro de cada tarjeta

   Lo que NO hay aquí, a propósito: ningún widget que no sostenga una decisión. No
   hay gráfico de índices, ni mapa de calor sectorial, ni lista de "más negociadas".
   Todos ellos son ciertos y ninguno cambia lo que vas a hacer hoy.

   Los bloques de abajo (cartera, cerebro, próximos días) son contexto, y por eso
   son pequeños y van después. Si alguno empieza a necesitar más sitio, la respuesta
   correcta casi siempre es que ese contenido pertenece a su propia sección. */

const CLAVE_ULTIMA_VISITA = "inveria-ultima-visita-hoy";

function leerUltimaVisita() {
  try {
    return localStorage.getItem(CLAVE_ULTIMA_VISITA) || undefined;
  } catch {
    return undefined;
  }
}

function Seccion({ titulo, children, accion }) {
  return (
    <section className="mt-8">
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className="font-heading text-titulo font-bold text-tinta">{titulo}</h2>
        {accion}
      </div>
      {children}
    </section>
  );
}

export default function HoyView() {
  // Se lee UNA vez al montar y se congela: si se leyera en cada render, al guardar
  // la visita nueva el bloque "desde tu última visita" se vaciaría solo delante del
  // usuario, que es justo lo que venía a leer.
  const desde = useMemo(() => leerUltimaVisita(), []);

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["hoy", desde],
    queryFn: () => api.hoy(desde),
    staleTime: 120_000,
    refetchOnWindowFocus: true,
  });

  // La visita se marca solo cuando ha llegado algo: si se marcara al entrar y la
  // petición fallara, se perdería el "qué ha cambiado" sin haberlo enseñado nunca.
  useEffect(() => {
    if (!data) return;
    try {
      localStorage.setItem(CLAVE_ULTIMA_VISITA, new Date().toISOString());
    } catch {
      /* modo incógnito: no poder recordar la visita no debe romper la página */
    }
  }, [data]);

  const importa = data?.importa_hoy || [];
  const cartera = data?.cartera || {};
  const cerebro = data?.cerebro || {};
  const mercado = data?.mercado;

  return (
    <PageShell
      titulo="Hoy"
      descripcion={
        data?.generado_en
          ? `Calculado ${fmtHace(data.generado_en)}. Se actualiza al volver a la pestaña.`
          : undefined
      }
      acciones={
        <Boton variante="fantasma" tamano="sm" onClick={() => refetch()} ocupado={isFetching}>
          Actualizar
        </Boton>
      }
    >
      {/* ── Franja de saludo: el índice de todo lo que hay debajo ── */}
      {data?.saludo?.piezas?.length > 0 && (
        <p className="text-cuerpo text-tinta-2 mb-5 -mt-1">
          Hoy:{" "}
          {data.saludo.piezas.map((p, i) => (
            <React.Fragment key={p}>
              {i > 0 && <span className="text-tinta-3"> · </span>}
              <span className="text-tinta font-medium">{p}</span>
            </React.Fragment>
          ))}
        </p>
      )}

      {/* ── Lo que importa hoy ── */}
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
        /* El día vacío es una respuesta legítima y se escribe con la misma calidad
           que una tarjeta. Rellenar con lo sexto más urgente entrena a desconfiar. */
        <div className="iv-destacada p-6 text-center">
          <p className="text-cuerpo text-tinta font-medium">
            Hoy no hay nada que requiera tu atención.
          </p>
          <p className="text-apoyo text-tinta-2 mt-1 max-w-[60ch] mx-auto">
            Ningún nivel cerca, ninguna alerta saltada y nada nuevo en tus fuentes sobre lo
            que sigues. Es una respuesta, no un hueco.
          </p>
          <div className="flex gap-2 justify-center mt-4">
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

      {/* ── Contexto: pequeño, y después ── */}
      <div className="grid gap-4 sm:grid-cols-2 mt-8">
        <div className="iv-panel p-4">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="iv-etiqueta">Tu cartera</h2>
            <Link to="/cartera" className="text-etiqueta text-marca hover:underline">ver todo</Link>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Metrica etiqueta="Valor" valor={fmtEur(cartera.valor_eur)} />
            <Metrica
              etiqueta="Latente"
              valor={fmtEur(cartera.latente_eur)}
              valorNumerico={cartera.latente_eur}
              tono="auto"
            />
            <Metrica
              etiqueta="Realizado"
              valor={fmtEur(cartera.realizado_eur)}
              valorNumerico={cartera.realizado_eur}
              tono="auto"
            />
            <Metrica etiqueta="Invertido" valor={fmtEur(cartera.invertido_eur)} />
          </div>
          {cartera.posiciones_sin_valorar > 0 && (
            <p className="text-etiqueta text-tinta-3 mt-2">
              {cartera.posiciones_sin_valorar} sin valorar (falta precio o tipo de cambio)
            </p>
          )}
          {cartera.atencion?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-linea space-y-1.5">
              {cartera.atencion.map((p) => (
                <div key={p.symbol} className="flex items-center justify-between gap-2">
                  <Link to={`/accion/${p.symbol}`} className="iv-cifra text-apoyo text-tinta hover:text-marca">
                    {p.symbol}
                  </Link>
                  <span
                    className="iv-cifra text-apoyo text-baja"
                    title="Rendimiento de la acción en su divisa: lo que dice si la tesis va mal, sin el ruido del tipo de cambio"
                  >
                    {fmtPct(p.pct)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="iv-panel p-4">
          <h2 className="iv-etiqueta mb-3">Mercado</h2>
          {mercado ? (
            <>
              <p className="text-cuerpo text-tinta font-medium">
                {mercado.emoji ? `${mercado.emoji} ` : ""}
                {mercado.estado || mercado.regime || "—"}
              </p>
              {mercado.detalle && (
                <p className="text-apoyo text-tinta-2 mt-1">{mercado.detalle}</p>
              )}
            </>
          ) : (
            <p className="text-apoyo text-tinta-3">Sin datos de régimen ahora mismo.</p>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 mt-4">
        <div className="iv-panel p-4">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="iv-etiqueta">Desde tu última visita</h2>
            <Link to="/cerebro" className="text-etiqueta text-marca hover:underline">el Cerebro</Link>
          </div>
          {cerebro.menciones_nuevas > 0 || cerebro.tickers_nuevos?.length > 0 ? (
            <>
              <p className="text-apoyo text-tinta-2">
                {cerebro.menciones_nuevas} menciones nuevas en tus fuentes.
              </p>
              {cerebro.tickers_nuevos?.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {cerebro.tickers_nuevos.slice(0, 8).map((t) => (
                    <Link key={t} to={`/accion/${t}`}>
                      <Chip tono="marca">{t}</Chip>
                    </Link>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-apoyo text-tinta-3">
              Tus fuentes no han publicado nada nuevo desde la última vez que entraste.
            </p>
          )}
        </div>

        <div className="iv-panel p-4">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="iv-etiqueta">Próximos 7 días</h2>
            <Link to="/calendario" className="text-etiqueta text-marca hover:underline">calendario</Link>
          </div>
          {data?.proximos_7_dias?.length > 0 ? (
            <div className="space-y-1.5">
              {data.proximos_7_dias.map((e) => (
                <div key={e.symbol} className="flex items-center justify-between gap-2">
                  <Link to={`/accion/${e.symbol}`} className="iv-cifra text-apoyo text-tinta hover:text-marca">
                    {e.symbol}
                  </Link>
                  <span className="text-apoyo text-tinta-3">{fmtEnDias(e.date)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-apoyo text-tinta-3">
              Ninguna de tus posiciones presenta resultados esta semana.
            </p>
          )}
        </div>
      </div>
    </PageShell>
  );
}
