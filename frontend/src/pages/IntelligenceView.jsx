import React, { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, CaretDown } from "@phosphor-icons/react";
import { api } from "../lib/api";
import PageShell from "../components/base/PageShell";
import Boton from "../components/base/Boton";
import { Cargando } from "../components/base/Estado";
import InvestmentRadar from "../components/intelligence/InvestmentRadar";
import RadarFuente from "../components/intelligence/RadarFuente";
import IntelligenceDrawer from "../components/intelligence/IntelligenceDrawer";
import PruebaDeVida from "../components/intelligence/PruebaDeVida";
import SondeoSec from "../components/intelligence/SondeoSec";
import DiagnosticoTickers from "../components/intelligence/DiagnosticoTickers";
import PlanInvestigacion from "../components/intelligence/PlanInvestigacion";
import { resumen as resumenDe, ordenados, plegarRepetidos, recortar, tituloCorto,
         nivelDe, estadoDeLectura, LEIDO, MOTIVOS, ETAPAS } from "../lib/intelligence";
import { fmtHace } from "../lib/format";

/**
 * Inteligencia: qué está entrando, de dónde, y qué se ha quedado por el camino.
 *
 * LA PANTALLA TIENE QUE PODER DECIR QUE NO SABE NADA
 *
 * El titular no está escrito: lo calcula `lib/intelligence.js` a partir del estado real, y
 * distingue tres silencios que en un radar vacío se ven idénticos —sin fuentes conectadas,
 * sin nada que vigilar y sin novedades—. Esa distinción es toda la pantalla: si los tres
 * dijeran «todo en orden», un sistema apagado sería indistinguible de uno tranquilo.
 *
 * POR QUÉ EL DIAGNÓSTICO ESTÁ EN LA MISMA PÁGINA
 *
 * Porque el filtro es lo que puede fallar en silencio. Un filtro demasiado agresivo se ve
 * exactamente igual que un mercado tranquilo, y la única forma de notarlo es ver cuántos
 * eventos se han descartado y por qué motivo. Esconderlo en otra pantalla equivale a no
 * mirarlo nunca.
 *
 * QUÉ NO HAY TODAVÍA
 *
 * No hay resumen por IA, ni agrupación de eventos relacionados, ni contraste de
 * afirmaciones, ni fuentes sociales. Se dice al pie, en la propia pantalla, y no solo en un
 * comentario del código: una limitación que el usuario no ve es una limitación que se le
 * acaba olvidando al sistema.
 *
 * MAQUETACIÓN (mismo lenguaje que Hoy)
 *
 * Lo que te afecta es la sección principal: en escritorio ocupa la columna ancha y en móvil
 * sube ARRIBA del todo, antes que el radar, que es contexto. Radar y fuentes van juntos en
 * un solo panel lateral; el diagnóstico, en paneles con filetes internos en vez de bloques
 * sueltos; las cuatro comprobaciones manuales, como filas de un mismo panel.
 */

/** Fila pulsable: hover y foco por dentro del panel, sin mover nada. Solo color: es una
 *  lista que se recorre decenas de veces, y ahí el movimiento sobra. */
const FILA_PULSABLE =
  // py-3 en móvil: la fila llega a ~44 px, el mínimo cómodo para el dedo.
  "w-full text-left px-4 sm:px-5 py-3 sm:py-2.5 flex items-baseline gap-3 group " +
  "transition-colors duration-150 ease-out motion-reduce:transition-none " +
  "hover:bg-superficie-alt/70 focus-visible:bg-superficie-alt/70 " +
  "focus-visible:!outline-offset-[-2px] focus-visible:!rounded-none";

/** Cabecera de sección: el mismo gesto que en Hoy, con el título como h2. */
function Seccion({ id, titulo, acento = false, children }) {
  return (
    <div className={`iv-seccion ${acento ? "iv-seccion-acento" : ""} !mb-3`}>
      <h2 id={id} className="font-heading text-titulo font-semibold text-tinta leading-tight">
        {titulo}
      </h2>
      {children}
    </div>
  );
}

/**
 * Una fila de evento, en UNA línea.
 *
 * Antes ocupaba tres —símbolo, título y procedencia— y con cuarenta eventos eso son mil
 * quinientos píxeles de scroll para leer una columna de texto casi idéntico. En una línea
 * la lista se abarca de un vistazo, que es lo que se hace con ella: buscar si hay algo
 * tuyo, no leerla entera.
 *
 * El símbolo va en su columna, así que el título se queda sin el «— NVDA» del final: ahí
 * repetía lo que ya se lee al lado.
 */
function Fila({ evento, onElegir, dentroDeGrupo = false }) {
  const n = nivelDe(evento);
  const d = evento.detalle || {};
  return (
    <button type="button" onClick={() => onElegir(evento)}
            className={`${FILA_PULSABLE} ${dentroDeGrupo ? "pl-8 sm:pl-9" : ""}`}
            data-testid={`intelligence-evento-${evento.id}`}>
      <span className="iv-cifra text-apoyo font-semibold text-tinta w-14 sm:w-16 shrink-0 truncate">
        {evento.symbol || "—"}
      </span>
      <span className="flex-1 min-w-0 text-apoyo text-tinta-2 group-hover:text-tinta
                       transition-colors duration-150 motion-reduce:transition-none truncate">
        {/* Un punto delante de lo que la IA ya ha leído. Champán si sacó algo, apagado
            si el documento no decía nada: en una lista las dos cosas se ven igual, y
            significan lo contrario sobre si merece la pena abrirlo. */}
        {estadoDeLectura(evento) !== LEIDO.NO && (
          <span className={estadoDeLectura(evento) === LEIDO.CON_INFO
                            ? "text-marca" : "text-tinta-3"}
                title={estadoDeLectura(evento) === LEIDO.CON_INFO
                        ? "La IA lo ha leído y ha sacado algo"
                        : "La IA lo ha leído y no decía nada"}>● </span>
        )}
        {tituloCorto(evento)}
      </span>
      {/* La procedencia se esconde en pantalla estrecha: es contexto, no lo que se
          busca. El nivel y el símbolo no se esconden nunca. Columna de ancho fijo y
          alineada a la derecha para que las fechas se lean en vertical. */}
      <span className="hidden md:inline iv-cifra text-etiqueta text-tinta-3 shrink-0 whitespace-nowrap
                       w-24 text-right">
        {dentroDeGrupo && d.accession
          ? <>n.º {d.accession.slice(-6)}</>
          : fmtHace(evento.recibido_en)}
      </span>
      {!dentroDeGrupo && (
        <span className={`iv-etiqueta shrink-0 w-[84px] text-right ${n.clase}`}>{n.etiqueta}</span>
      )}
    </button>
  );
}


/**
 * Varias filas que dicen lo mismo, plegadas en una.
 *
 * Se despliega y están TODAS, cada una con su número de registro y su enlace al
 * documento. Plegar es una decisión de lectura, no un filtro: no desaparece nada.
 */
function Grupo({ fila, onElegir }) {
  const [abierto, setAbierto] = React.useState(false);
  const n = nivelDe({ nivel_alerta: fila.nivel });
  return (
    <li data-testid={`intelligence-grupo-${fila.id}`}>
      <button type="button" onClick={() => setAbierto((v) => !v)}
              className={FILA_PULSABLE}
              aria-expanded={abierto}>
        <span className="iv-cifra text-apoyo font-semibold text-tinta w-14 sm:w-16 shrink-0 truncate">
          {fila.symbol}
        </span>
        <span className="flex-1 min-w-0 text-apoyo text-tinta-2 group-hover:text-tinta
                         transition-colors duration-150 motion-reduce:transition-none truncate">
          {fila.titulo}
          <span className="text-tinta-3"> · {abierto ? "ocultar" : "ver una a una"}</span>
        </span>
        <CaretDown size={12} aria-hidden="true"
                   className={`self-center shrink-0 text-tinta-3 transition-transform duration-200 ease-out
                               motion-reduce:transition-none ${abierto ? "rotate-180" : ""}`} />
        <span className="hidden md:inline iv-cifra text-etiqueta text-tinta-3 shrink-0 whitespace-nowrap
                         w-24 text-right">
          {fmtHace(fila.items[0].recibido_en)}
        </span>
        <span className={`iv-etiqueta shrink-0 w-[84px] text-right ${n.clase}`}>{n.etiqueta}</span>
      </button>
      {abierto && (
        <ul className="relative bg-superficie-alt/40 divide-y divide-linea border-t border-linea
                       before:absolute before:left-5 sm:before:left-6 before:inset-y-2 before:w-px before:bg-linea-fuerte">
          {fila.items.map((e) => (
            <li key={e.id}>
              <Fila evento={e} onElegir={onElegir} dentroDeGrupo />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}


/** Una lista «rótulo … cifra», con la cifra en su columna derecha y tabular. */
function ListaCifras({ titulo, filas, vacio }) {
  return (
    <div className="min-w-0">
      <h3 className="iv-etiqueta mb-1.5">{titulo}</h3>
      <dl className="divide-y divide-linea">
        {filas.map(([k, rotulo, n]) => (
          <div key={k} className="flex items-baseline justify-between gap-3 py-1.5">
            <dt className="text-apoyo text-tinta-2 min-w-0">{rotulo}</dt>
            <dd className="iv-cifra text-apoyo font-semibold text-tinta text-right">{n}</dd>
          </div>
        ))}
      </dl>
      {!filas.length && <p className="text-apoyo text-tinta-3 py-1.5">{vacio}</p>}
    </div>
  );
}


export default function IntelligenceView() {
  const [estado, setEstado] = useState(null);
  const [eventos, setEventos] = useState([]);
  const [diagnostico, setDiagnostico] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [elegido, setElegido] = useState(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const [e, ev, d] = await Promise.all([
        api.intelligence.estado(),
        api.intelligence.eventos(),
        api.intelligence.diagnostico(),
      ]);
      setEstado(e);
      setEventos(ev.eventos || []);
      setDiagnostico(d);
      setError(null);
    } catch (err) {
      // El error se enseña. Una pantalla vacía tras un fallo de red se lee como «no hay
      // nada», que es justo la confusión que esta pantalla existe para evitar.
      setError(err?.response?.data?.detail || err.message || "No se pudo cargar");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const r = resumenDe(estado);
  const lista = ordenados(eventos);
  // El radar sigue recibiendo los eventos UNO A UNO: plegar es cosa de la lista, y una
  // marca por registro es lo que hace que el radar represente lo que de verdad entró.
  const filas = plegarRepetidos(eventos);
  const [verTodo, setVerTodo] = useState(false);
  const { visibles, ocultas } = recortar(filas);
  const aPintar = verTodo ? filas : visibles;
  const fuentes = estado?.fuentes || [];
  // Primera carga: todavía no hay nada que enseñar. En las recargas se deja lo que había
  // a la vista; el botón de actualizar ya dice que está leyendo.
  const primeraCarga = cargando && !estado && !eventos.length;

  return (
    <PageShell>
      <header className="iv-veredicto mb-6 sm:mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <span className="iv-etiqueta">Inteligencia</span>
          <h1 className="iv-verbo text-tinta mt-1 text-balance">{r.titulo}</h1>
          <p className="mt-2.5 text-cuerpo text-tinta-2 max-w-[58ch]" aria-live="polite">
            {cargando ? "Leyendo el estado de las fuentes…" : r.detalle}
          </p>
        </div>
        <Boton variante="fantasma" tamano="sm" onClick={cargar} ocupado={cargando}
               className="shrink-0" data-testid="intelligence-refrescar">
          <ArrowClockwise size={14} aria-hidden="true"
                          className={cargando ? "animate-spin motion-reduce:animate-none" : ""} />
          Actualizar
        </Boton>
      </header>

      {error && (
        <div role="alert"
             className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-iv
                        border border-baja/30 bg-baja/5 px-4 py-3">
          <p className="text-apoyo text-tinta-2 min-w-0 max-w-[75ch]">
            <span className="text-baja font-semibold">No se ha podido leer el estado:</span>{" "}
            <span className="break-words">{String(error)}</span>. Lo que ves abajo puede estar
            desactualizado.
          </p>
          <Boton variante="contorno" tamano="sm" onClick={cargar} ocupado={cargando}>
            Reintentar
          </Boton>
        </div>
      )}

      {/* `grid-cols-1` NO es redundante. Sin él, en móvil no hay ninguna columna
          declarada y la única que se crea es implícita: se dimensiona a `max-content`,
          o sea al ancho del párrafo más largo que haya dentro. Medido en un navegador a
          390 px, la columna salía de 693 px y la pantalla se veía cortada a la mitad
          —sin poder arrastrar, porque `.App` lleva `overflow-x-hidden`—. `grid-cols-1`
          declara la columna como `minmax(0,1fr)`, que es lo que la obliga a encoger. */}
      <div className="grid grid-cols-1 gap-6 lg:gap-8 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        {/* La columna principal va PRIMERO en el código: en móvil se lee (y se tabula)
            antes que el radar, que es contexto. En escritorio se coloca a la derecha. */}
        <div className="min-w-0 lg:col-start-2 lg:row-start-1">
          <section aria-labelledby="iv-afecta">
            <Seccion id="iv-afecta" titulo="Lo que te afecta" acento />

            {primeraCarga ? (
              <div className="iv-panel p-5"><Cargando filas={5} etiqueta="Cargando eventos…" /></div>
            ) : !lista.length ? (
              <div className={`iv-panel px-5 py-6 ${r.vigila ? "" : "border-aviso/40"}`}>
                <p className="text-cuerpo text-tinta-2 max-w-[60ch] leading-relaxed">
                  {r.vigila
                    ? "No ha entrado nada relevante para tus valores. Silencio de mercado, no de sistema: abajo puedes ver cuántos eventos se han leído y descartado."
                    : "No está entrando nada porque no hay ninguna fuente escuchando. Lo que ves no es un mercado tranquilo: es un radar apagado."}
                </p>
              </div>
            ) : (
              <div className="iv-panel overflow-hidden">
                <ul className="divide-y divide-linea">
                  {aPintar.map((fila) => (
                    fila.tipo === "grupo"
                      ? <Grupo key={fila.id} fila={fila} onElegir={setElegido} />
                      : <li key={fila.id}>
                          <Fila evento={fila.evento} onElegir={setElegido} />
                        </li>
                  ))}
                </ul>

                {ocultas > 0 && !verTodo && (
                  <button type="button" onClick={() => setVerTodo(true)}
                          className="w-full flex items-center justify-center gap-1.5 border-t border-linea
                                     px-4 py-2.5 text-apoyo font-medium text-marca
                                     transition-colors duration-150 ease-out motion-reduce:transition-none
                                     hover:bg-superficie-alt/70 focus-visible:!outline-offset-[-2px]
                                     focus-visible:!rounded-none"
                          data-testid="intelligence-ver-todo">
                    Ver {ocultas} {ocultas === 1 ? "fila más" : "filas más"}
                    <CaretDown size={12} aria-hidden="true" />
                  </button>
                )}
              </div>
            )}
          </section>

          {/* El diagnóstico. Es lo que impide confundir un filtro roto con un mercado
              tranquilo, y por eso está aquí y no escondido. */}
          {diagnostico && (
            <section className="mt-10" aria-labelledby="iv-diagnostico">
              <Seccion id="iv-diagnostico" titulo="Por dónde se va lo demás" />

              <div className="iv-panel overflow-hidden divide-y divide-linea">
                <div className="grid grid-cols-1 gap-x-8 gap-y-5 p-4 sm:p-5 sm:grid-cols-2">
                  <ListaCifras titulo="Etapas" vacio="Todavía no ha entrado nada."
                               filas={Object.entries(diagnostico.por_etapa || {})
                                 .map(([etapa, n]) => [etapa, ETAPAS[etapa] || etapa, n])} />
                  <ListaCifras titulo="Motivos del descarte" vacio="Nada descartado."
                               filas={Object.entries(diagnostico.descartes_por_motivo || {})
                                 .map(([m, n]) => [m, MOTIVOS[m] || m, n])} />
                </div>

                {/* El periodo de prueba, UNA FILA POR FUENTE. Sumarlas escondería lo que
                    hace falta ver: con SEC leyendo cada cinco minutos y resultados cada
                    seis horas, el total lo dominaría la primera y una caída de la segunda
                    pasaría desapercibida. */}
                {Object.entries(diagnostico.acumulado_por_fuente || {})
                  .filter(([, a]) => a.ciclos > 0)
                  .map(([fuente, a]) => (
                    <div key={fuente} className="p-4 sm:p-5">
                      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 mb-3">
                        <h3 className="iv-etiqueta">{a.nombre} · desde que vigila</h3>
                        <p className="iv-cifra text-etiqueta text-tinta-3">
                          {a.ciclos} vueltas
                          {a.fallos > 0
                            ? <>, <span className="text-baja">{a.fallos} fallidas</span></>
                            : " sin ningún fallo"}.
                        </p>
                      </div>
                      <dl className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-x-4 gap-y-3">
                        {[["Recibidos", a.recibidos],
                          // Ya conocidos: se van en la deduplicación, ANTES del filtro. Van
                          // aquí, entre recibidos y nuevos, porque es donde ocurren.
                          ["Ya conocidos", a.repetidos],
                          ["Nuevos", a.nuevos],
                          ["Descartados por filtro", a.descartados],
                          ["Te afectan", a.significativos],
                          ["Guardados únicos", a.guardados_unicos]].map(([t, n], i) => (
                          <div key={t} className={`min-w-0 flex flex-col-reverse
                                                   ${i === 5 ? "border-l border-marca pl-3" : ""}`}>
                            <dt className="iv-etiqueta leading-snug">{t}</dt>
                            <dd className={`iv-cifra text-lg font-semibold break-all
                                            ${i === 4 && n ? "text-marca" : "text-tinta"}`}>
                              {n ?? 0}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  ))}
              </div>

              <p className="mt-3 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
                «Ya conocidos» son documentos que ya teníamos: no es que se hayan tirado,
                es que no eran nuevos. «Guardados únicos» cuenta documentos en la base de
                datos e incluye los descartados — el descarte también es historia, y es lo
                que permite auditar el filtro después.
              </p>

              {/* Las comprobaciones manuales, como filas de un mismo panel: son
                  herramientas que se usan de vez en cuando, no lecturas del día. */}
              <div className="mt-8 iv-panel overflow-hidden divide-y divide-linea">
                <PruebaDeVida alTerminar={cargar} />

                <SondeoSec />

                <PlanInvestigacion />

                <DiagnosticoTickers />
              </div>

              {/* Lo que falta, dicho en la pantalla. Una etapa declarada y no implementada
                  que solo se cuenta en el código acaba pareciendo que funciona. */}
              <p className="mt-4 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
                Un evento pasa por estas etapas antes de llegarte. Las de{" "}
                <b className="text-tinta-2">
                  {(diagnostico.sin_implementar || []).map((e) => ETAPAS[e] || e).join(" y ")}
                </b>{" "}
                están declaradas pero todavía no se ejecutan: no hay análisis por IA ni
                agrupación de eventos relacionados. Tampoco hay fuentes sociales. Lo que ves
                sale entero de documentos registrados.
              </p>
            </section>
          )}
        </div>

        {/* Columna lateral: radar + fuentes en un solo panel. En escritorio, a la
            izquierda y fija al hacer scroll; en móvil, debajo de lo que te afecta. */}
        <aside className="min-w-0 lg:col-start-1 lg:row-start-1 lg:sticky lg:top-4 lg:self-start"
               aria-label="Radar y fuentes">
          <div className="iv-panel overflow-hidden">
            <div className="px-4 pt-5 pb-4">
              <InvestmentRadar estado={estado} eventos={lista}
                               onElegir={setElegido} seleccionado={elegido} />
            </div>

            <section className="border-t border-linea px-4 sm:px-5 pt-4 pb-1"
                     aria-labelledby="iv-fuentes">
              <h2 id="iv-fuentes" className="iv-etiqueta">Fuentes</h2>
              {primeraCarga && <Cargando filas={3} className="py-3" etiqueta="Cargando fuentes…" />}
              {fuentes.map((f) => <RadarFuente key={f.fuente} fuente={f} />)}
              {!cargando && !fuentes.length && (
                <p className="text-apoyo text-tinta-3 py-3">No hay ninguna fuente implementada.</p>
              )}
            </section>
          </div>
        </aside>
      </div>

      <IntelligenceDrawer evento={elegido} onCerrar={() => setElegido(null)} />
    </PageShell>
  );
}
