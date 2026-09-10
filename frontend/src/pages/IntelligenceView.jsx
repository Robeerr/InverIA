import React, { useCallback, useEffect, useState } from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import { api } from "../lib/api";
import InvestmentRadar from "../components/intelligence/InvestmentRadar";
import RadarFuente from "../components/intelligence/RadarFuente";
import IntelligenceDrawer from "../components/intelligence/IntelligenceDrawer";
import PruebaDeVida from "../components/intelligence/PruebaDeVida";
import SondeoSec from "../components/intelligence/SondeoSec";
import DiagnosticoTickers from "../components/intelligence/DiagnosticoTickers";
import PlanInvestigacion from "../components/intelligence/PlanInvestigacion";
import { resumen as resumenDe, ordenados, plegarRepetidos, recortar, tituloCorto,
         nivelDe, MOTIVOS, ETAPAS } from "../lib/intelligence";
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
 */
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
    <button onClick={() => onElegir(evento)}
            className={`w-full text-left py-2 flex items-baseline gap-3 group
                        ${dentroDeGrupo ? "pl-4" : ""}`}
            data-testid={`intelligence-evento-${evento.id}`}>
      <span className="iv-cifra text-sm font-semibold text-tinta w-16 shrink-0 truncate">
        {evento.symbol || "—"}
      </span>
      <span className="flex-1 min-w-0 text-sm text-tinta-2 group-hover:text-tinta truncate">
        {tituloCorto(evento)}
      </span>
      {/* La procedencia se esconde en pantalla estrecha: es contexto, no lo que se
          busca. El nivel y el símbolo no se esconden nunca. */}
      <span className="hidden md:inline text-xs text-tinta-3 shrink-0 whitespace-nowrap">
        {dentroDeGrupo && d.accession
          ? <span className="iv-cifra">n.º {d.accession.slice(-6)}</span>
          : fmtHace(evento.recibido_en)}
      </span>
      {!dentroDeGrupo && (
        <span className={`iv-etiqueta shrink-0 ${n.clase}`}>{n.etiqueta}</span>
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
      <button onClick={() => setAbierto((v) => !v)}
              className="w-full text-left py-2 flex items-baseline gap-3 group"
              aria-expanded={abierto}>
        <span className="iv-cifra text-sm font-semibold text-tinta w-16 shrink-0 truncate">
          {fila.symbol}
        </span>
        <span className="flex-1 min-w-0 text-sm text-tinta-2 group-hover:text-tinta truncate">
          {fila.titulo}
          <span className="text-tinta-3"> · {abierto ? "ocultar" : "ver una a una"}</span>
        </span>
        <span className="hidden md:inline text-xs text-tinta-3 shrink-0 whitespace-nowrap">
          {fmtHace(fila.items[0].recibido_en)}
        </span>
        <span className={`iv-etiqueta shrink-0 ${n.clase}`}>{n.etiqueta}</span>
      </button>
      {abierto && (
        <ul className="border-l border-linea ml-1 divide-y divide-linea">
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

  return (
    <div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6">
      <div className="iv-veredicto">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <span className="iv-etiqueta">Inteligencia</span>
            <span className="iv-verbo text-tinta mt-1">{r.titulo}</span>
            <p className="mt-3 text-sm text-tinta-2 max-w-[52ch] leading-relaxed">
              {cargando ? "Leyendo el estado de las fuentes…" : r.detalle}
            </p>
          </div>
          <button onClick={cargar} disabled={cargando}
                  className="iv-etiqueta flex items-center gap-1.5 text-tinta-3
                             hover:text-tinta disabled:opacity-50 shrink-0"
                  data-testid="intelligence-refrescar">
            <ArrowClockwise size={14} /> Actualizar
          </button>
        </div>
      </div>

      {error && (
        <p className="mt-4 text-sm text-baja" role="alert">
          No se ha podido leer el estado: {String(error)}. Lo que ves abajo puede estar
          desactualizado.
        </p>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <div>
          <InvestmentRadar estado={estado} eventos={lista}
                           onElegir={setElegido} seleccionado={elegido} />

          <div className="mt-8">
            <div className="iv-seccion"><span className="iv-etiqueta">Fuentes</span></div>
            {(estado?.fuentes || []).map((f) => <RadarFuente key={f.fuente} fuente={f} />)}
            {!cargando && !(estado?.fuentes || []).length && (
              <p className="text-sm text-tinta-3">No hay ninguna fuente implementada.</p>
            )}
          </div>
        </div>

        <div>
          <div className="iv-seccion iv-seccion-acento">
            <span className="iv-etiqueta">Lo que te afecta</span>
          </div>

          {!cargando && !lista.length && (
            <p className="text-sm text-tinta-3 max-w-[60ch] leading-relaxed">
              {r.vigila
                ? "No ha entrado nada relevante para tus valores. Silencio de mercado, no de sistema: abajo puedes ver cuántos eventos se han leído y descartado."
                : "No está entrando nada porque no hay ninguna fuente escuchando. Lo que ves no es un mercado tranquilo: es un radar apagado."}
            </p>
          )}

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
            <button onClick={() => setVerTodo(true)}
                    className="mt-3 text-xs text-marca hover:underline"
                    data-testid="intelligence-ver-todo">
              Ver {ocultas} {ocultas === 1 ? "fila más" : "filas más"}
            </button>
          )}

          {/* El diagnóstico. Es lo que impide confundir un filtro roto con un mercado
              tranquilo, y por eso está aquí y no escondido. */}
          {diagnostico && (
            <div className="mt-10">
              <div className="iv-seccion"><span className="iv-etiqueta">Por dónde se va lo demás</span></div>
              <div className="grid gap-6 sm:grid-cols-2">
                <div>
                  <p className="iv-etiqueta mb-2">Etapas</p>
                  <ul className="text-sm space-y-1">
                    {Object.entries(diagnostico.por_etapa || {}).map(([etapa, n]) => (
                      <li key={etapa} className="flex justify-between gap-3">
                        <span className="text-tinta-2">{ETAPAS[etapa] || etapa}</span>
                        <span className="iv-cifra text-tinta-3">{n}</span>
                      </li>
                    ))}
                    {!Object.keys(diagnostico.por_etapa || {}).length && (
                      <li className="text-sm text-tinta-3">Todavía no ha entrado nada.</li>
                    )}
                  </ul>
                </div>
                <div>
                  <p className="iv-etiqueta mb-2">Motivos del descarte</p>
                  <ul className="text-sm space-y-1">
                    {Object.entries(diagnostico.descartes_por_motivo || {}).map(([m, n]) => (
                      <li key={m} className="flex justify-between gap-3">
                        <span className="text-tinta-2">{MOTIVOS[m] || m}</span>
                        <span className="iv-cifra text-tinta-3">{n}</span>
                      </li>
                    ))}
                    {!Object.keys(diagnostico.descartes_por_motivo || {}).length && (
                      <li className="text-sm text-tinta-3">Nada descartado.</li>
                    )}
                  </ul>
                </div>
              </div>

              {/* El periodo de prueba, UNA FILA POR FUENTE. Sumarlas escondería lo que
                  hace falta ver: con SEC leyendo cada cinco minutos y resultados cada
                  seis horas, el total lo dominaría la primera y una caída de la segunda
                  pasaría desapercibida. */}
              {Object.entries(diagnostico.acumulado_por_fuente || {})
                .filter(([, a]) => a.ciclos > 0)
                .map(([fuente, a]) => (
                  <div key={fuente} className="mt-6">
                    <p className="iv-etiqueta mb-2">{a.nombre} · desde que vigila</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                      {[["Recibidos", a.recibidos],
                        // Ya conocidos: se van en la deduplicación, ANTES del filtro. Van
                        // aquí, entre recibidos y nuevos, porque es donde ocurren.
                        ["Ya conocidos", a.repetidos],
                        ["Nuevos", a.nuevos],
                        ["Descartados por filtro", a.descartados],
                        ["Te afectan", a.significativos],
                        ["Guardados únicos", a.guardados_unicos]].map(([t, n], i) => (
                        <div key={t} className={i === 5 ? "border-l border-marca pl-3" : ""}>
                          <p className="iv-cifra text-xl text-tinta">{n ?? 0}</p>
                          <p className="iv-etiqueta">{t}</p>
                        </div>
                      ))}
                    </div>
                    <p className="mt-2 text-xs text-tinta-3">
                      {a.ciclos} vueltas
                      {a.fallos > 0 ? `, ${a.fallos} fallidas` : " sin ningún fallo"}.
                    </p>
                  </div>
                ))}

              <p className="mt-4 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
                «Ya conocidos» son documentos que ya teníamos: no es que se hayan tirado,
                es que no eran nuevos. «Guardados únicos» cuenta documentos en la base de
                datos e incluye los descartados — el descarte también es historia, y es lo
                que permite auditar el filtro después.
              </p>

              <PruebaDeVida alTerminar={cargar} />

              <SondeoSec />

              <PlanInvestigacion />

              <DiagnosticoTickers />

              {/* Lo que falta, dicho en la pantalla. Una etapa declarada y no implementada
                  que solo se cuenta en el código acaba pareciendo que funciona. */}
              <p className="mt-6 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
                Un evento pasa por estas etapas antes de llegarte. Las de{" "}
                <b className="text-tinta-2">
                  {(diagnostico.sin_implementar || []).map((e) => ETAPAS[e] || e).join(" y ")}
                </b>{" "}
                están declaradas pero todavía no se ejecutan: no hay análisis por IA ni
                agrupación de eventos relacionados. Tampoco hay fuentes sociales. Lo que ves
                sale entero de documentos registrados.
              </p>
            </div>
          )}
        </div>
      </div>

      <IntelligenceDrawer evento={elegido} onCerrar={() => setElegido(null)} />
    </div>
  );
}
