import React, { useCallback, useEffect, useState } from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import { api } from "../lib/api";
import InvestmentRadar from "../components/intelligence/InvestmentRadar";
import RadarFuente from "../components/intelligence/RadarFuente";
import IntelligenceDrawer from "../components/intelligence/IntelligenceDrawer";
import PruebaDeVida from "../components/intelligence/PruebaDeVida";
import { resumen as resumenDe, ordenados, nivelDe, MOTIVOS, ETAPAS } from "../lib/intelligence";
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
            {lista.map((ev) => {
              const n = nivelDe(ev);
              return (
                <li key={ev.id}>
                  <button onClick={() => setElegido(ev)}
                          className="w-full text-left py-3 group"
                          data-testid={`intelligence-evento-${ev.id}`}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="iv-cifra text-sm font-semibold text-tinta">
                        {ev.symbol || "—"}
                      </span>
                      <span className={`iv-etiqueta shrink-0 ${n.clase}`}>{n.etiqueta}</span>
                    </div>
                    <p className="mt-1 text-sm text-tinta-2 group-hover:text-tinta leading-snug">
                      {ev.titulo}
                    </p>
                    <p className="mt-1 text-xs text-tinta-3">
                      {ev.fuente} · {fmtHace(ev.recibido_en)}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>

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

              {/* El periodo de prueba: los cuatro números desde que la vigilancia arrancó.
                  El de guardados es el que cierra la cadena — «procesados 400» convive
                  perfectamente con una base de datos vacía. */}
              {diagnostico.acumulado?.ciclos > 0 && (
                <div className="mt-6">
                  <p className="iv-etiqueta mb-2">Desde que vigila</p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {[["Recibidos", diagnostico.acumulado.recibidos],
                      // «Pasan el filtro» se calcula, no se cuenta aparte: son los nuevos
                      // menos los descartados. Etiquetarlo con los significativos sería
                      // más bajo y se leería como si el filtro tirara más de lo que tira.
                      ["Pasan el filtro",
                       Math.max(0, diagnostico.acumulado.nuevos - diagnostico.acumulado.descartados)],
                      ["Descartados", diagnostico.acumulado.descartados],
                      ["Guardados", diagnostico.acumulado.guardados]].map(([t, n], i) => (
                      <div key={t} className={i === 3 ? "border-l border-marca pl-3" : ""}>
                        <p className="iv-cifra text-xl text-tinta">{n}</p>
                        <p className="iv-etiqueta">{t}</p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-tinta-3">
                    {diagnostico.acumulado.ciclos} vueltas
                    {diagnostico.acumulado.fallos > 0
                      ? `, ${diagnostico.acumulado.fallos} fallidas`
                      : " sin ningún fallo"}.{" "}
                    De los que pasan el filtro, {diagnostico.acumulado.significativos} han
                    llegado a significativo. «Guardados» incluye los descartados: el
                    descarte también es historia, y es lo que permite auditar el filtro.
                  </p>
                </div>
              )}

              <PruebaDeVida alTerminar={cargar} />

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
