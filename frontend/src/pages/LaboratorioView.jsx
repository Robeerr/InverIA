import React, { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, FlaskIcon } from "@phosphor-icons/react";
import { api } from "../lib/api";

/**
 * El laboratorio: qué ha leído InverIA, qué cree y qué ha medido.
 *
 * LA PANTALLA TIENE QUE DISTINGUIR TRES COSAS QUE NO SON LO MISMO
 *
 *   CONOCIMIENTO  alguien lo escribió y parece razonable. No es evidencia.
 *   HIPÓTESIS     creemos que mejoraría una decisión. Todavía no lo sabemos.
 *   EVIDENCIA     lo hemos medido sobre nuestros datos y sale esto.
 *
 * Enseñarlas juntas es exactamente el fallo que el laboratorio existe para impedir: un
 * umbral leído en un libro presentado al lado de uno medido se lee como si los dos
 * tuvieran el mismo respaldo, y no lo tienen.
 *
 * NO HAY NINGUNA PUNTUACIÓN GLOBAL, Y ES DELIBERADO
 *
 * Un «InverIA IQ» sumaría conceptos leídos, hipótesis abiertas y experimentos hechos,
 * que no son la misma magnitud. Es el mismo error que `separacion.py` documenta para el
 * score de oportunidades, donde un 60 puede significar «cara pero líder» o «barata pero
 * muerta». Aquí se enseñan las cuentas por separado, aunque queden menos vistosas.
 */

const ESTADOS = {
  VALIDATED: { etiqueta: "Validado", clase: "text-sube" },
  REJECTED: { etiqueta: "Rechazado", clase: "text-baja" },
  INSUFFICIENT_DATA: { etiqueta: "Sin muestra", clase: "text-tinta-3" },
  INCONCLUSIVE: { etiqueta: "No concluyente", clase: "text-aviso" },
  READY: { etiqueta: "Medible", clase: "text-marca" },
  IDEA: { etiqueta: "Bloqueada", clase: "text-tinta-3" },
};

const Estado = ({ valor }) => {
  const e = ESTADOS[valor] || { etiqueta: valor || "—", clase: "text-tinta-3" };
  return <span className={`iv-etiqueta shrink-0 ${e.clase}`}>{e.etiqueta}</span>;
};

/** Una cifra con su nombre. Sin totales: cada una responde a UNA pregunta. */
const Cifra = ({ n, etiqueta }) => (
  <div>
    <p className="iv-cifra text-xl text-tinta">{n ?? "—"}</p>
    <p className="iv-etiqueta">{etiqueta}</p>
  </div>
);

function Hipotesis({ h }) {
  const [abierta, setAbierta] = useState(false);
  return (
    <li data-testid={`lab-hipotesis-${h.id}`}>
      <button onClick={() => setAbierta((v) => !v)} aria-expanded={abierta}
              className="w-full text-left py-2 flex items-baseline gap-3 group">
        <span className="flex-1 min-w-0 text-sm text-tinta-2 group-hover:text-tinta truncate">
          {h.titulo}
        </span>
        <Estado valor={h.estado} />
      </button>
      {abierta && (
        <div className="pb-3 pl-1 space-y-2 border-l border-linea ml-1 pl-3">
          <p className="text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
            <b className="text-tinta-2">Qué mediría:</b> {h.mide || "—"}
          </p>
          {h.bloqueado_por && (
            <p className="text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
              <b className="text-tinta-2">Bloqueado por:</b> {h.bloqueado_por}
            </p>
          )}
          {h.relacion_con_produccion && (
            <p className="text-xs text-aviso max-w-[70ch] leading-relaxed">
              <b>Ya hay un número en producción:</b> {h.relacion_con_produccion}
            </p>
          )}
          <p className="text-xs text-tinta-3 max-w-[70ch] leading-relaxed">{h.por_que}</p>
        </div>
      )}
    </li>
  );
}

function Experimento({ e }) {
  const r = e.resultado || {};
  return (
    <li className="py-3" data-testid={`lab-experimento-${e.hipotesis_id}-${e.intento}`}>
      <div className="flex items-baseline gap-3">
        <span className="flex-1 min-w-0 text-sm text-tinta">{e.titulo}</span>
        <span className="iv-cifra text-xs text-tinta-3">intento {e.intento}</span>
        <Estado valor={e.estado} />
      </div>
      <p className="mt-1 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
        {r.conclusion}
      </p>
      {!!(r.tramos || []).length && (
        <div className="mt-2 overflow-x-auto">
          <table className="text-xs w-full">
            <thead className="text-tinta-3">
              <tr><th className="text-left font-normal py-1">Tramo</th>
                  <th className="text-right font-normal">Muestra</th>
                  <th className="text-right font-normal">Retorno medio</th>
                  {r.tramos.some((t) => t.mediana != null) && (
                    <>
                      <th className="text-right font-normal">Mediana</th>
                      {/* La amplitud responde «¿es solo que se mueve más?» y el peso del
                          10% mejor, «¿lo explica un puñado de aciertos?». Las dos se
                          medían desde el principio y no se enseñaban. */}
                      <th className="text-right font-normal">P25–P75</th>
                      <th className="text-right font-normal">Amplitud</th>
                      <th className="text-right font-normal">10% mejor</th>
                    </>
                  )}
                  <th className="text-right font-normal">Positivos</th></tr>
            </thead>
            <tbody className="iv-cifra">
              {r.tramos.map((t) => (
                <tr key={t.tramo} className="border-t border-linea">
                  <td className="py-1 text-tinta-2">{t.tramo}</td>
                  <td className="text-right text-tinta-3">{t.n}</td>
                  <td className="text-right text-tinta-2">
                    {(t.retorno_medio ?? t.media) == null
                      ? "—" : `${t.retorno_medio ?? t.media}%`}
                  </td>
                  {r.tramos.some((x) => x.mediana != null) && (
                    <>
                      <td className="text-right text-tinta">
                        {t.mediana == null ? "—" : `${t.mediana}%`}
                      </td>
                      <td className="text-right text-tinta-3 whitespace-nowrap">
                        {t.p25 == null ? "—" : `${t.p25} / ${t.p75}`}
                      </td>
                      <td className="text-right text-tinta-3">
                        {t.amplitud_intercuartil == null
                          ? "—" : `${t.amplitud_intercuartil} pp`}
                      </td>
                      <td className="text-right text-tinta-3">
                        {t.peso_del_10pct_mejor == null
                          ? "—" : `${t.peso_del_10pct_mejor}%`}
                      </td>
                    </>
                  )}
                  <td className="text-right text-tinta-3">
                    {t.positivos_pct == null ? "—" : `${t.positivos_pct}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!!(r.tramos || []).some((t) => t.por_año) && (
        <details className="mt-2">
          <summary className="text-xs text-marca cursor-pointer">Reparto por año</summary>
          <p className="mt-1 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
            Si un tramo se concentra en un año concreto, lo que mide es ese año.
          </p>
          <div className="mt-2 overflow-x-auto">
            <table className="text-xs w-full iv-cifra">
              <tbody>
                {r.tramos.map((t) => (
                  <tr key={t.tramo} className="border-t border-linea">
                    <td className="py-1 text-tinta-2">{t.tramo}</td>
                    {Object.entries(t.por_año || {}).map(([a, n]) => (
                      <td key={a} className="text-right text-tinta-3 px-2">
                        {a}: {n}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {/* `r.años` cuando el experimento ES el corte temporal; `r.por_periodo.años`
          cuando el corte viaja DENTRO de otro experimento, que es como llega desde que
          las lecciones vienen de serie. Se calculaba y quedaba enterrado un nivel más
          abajo, así que no se veía. */}
      {!!((r.años || r.por_periodo?.años) || []).length && (
        <div className="mt-2 overflow-x-auto">
          <table className="text-xs w-full">
            <thead className="text-tinta-3">
              <tr><th className="text-left font-normal py-1">Año</th>
                  <th className="text-right font-normal">Muestra</th>
                  <th className="text-right font-normal">¿Peor el tramo en máximos?</th>
                  <th className="text-right font-normal">Escalón</th></tr>
            </thead>
            <tbody className="iv-cifra">
              {(r.años || r.por_periodo?.años || []).map((a) => (
                <tr key={a.año} className="border-t border-linea">
                  <td className="py-1 text-tinta-2">{a.año}</td>
                  <td className="text-right text-tinta-3">{a.n}</td>
                  <td className={`text-right ${a.el_tramo_en_maximos_es_el_PEOR
                                    ? "text-tinta" : "text-tinta-3"}`}>
                    {a.el_tramo_en_maximos_es_el_PEOR ? "sí" : "no"}
                  </td>
                  <td className="text-right text-tinta-3">{a.escalon_pp} pp</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {/* El método viaja con el resultado. Un «+14%» sin saber sobre qué universo, con
          qué horizonte y con qué sesgos no se puede revisar dentro de seis meses. */}
      {e.controles && (
        <details className="mt-2">
          <summary className="text-xs text-marca cursor-pointer">Método y sesgos</summary>
          <dl className="mt-2 space-y-1">
            {Object.entries(e.controles).map(([k, v]) => (
              <div key={k} className="text-xs">
                <dt className="iv-etiqueta">{k}</dt>
                <dd className="text-tinta-3 max-w-[70ch] leading-relaxed">{v}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </li>
  );
}

export default function LaboratorioView() {
  const [datos, setDatos] = useState(null);
  const [experimentos, setExperimentos] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [corriendo, setCorriendo] = useState(false);
  const [error, setError] = useState(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const [p, e] = await Promise.all([
        api.laboratorio.panorama(),
        api.laboratorio.experimentos(),
      ]);
      setDatos(p);
      setExperimentos(e.experimentos || []);
      setError(null);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No se pudo cargar");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const ejecutar = async (cual) => {
    setCorriendo(true);
    try {
      await (api.laboratorio[cual] || api.laboratorio.distanciaAlMaximo)();
      await cargar();
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "El experimento falló");
    } finally {
      setCorriendo(false);
    }
  };

  const c = datos?.cobertura || {};
  const h = datos?.hipotesis || {};
  const ex = datos?.experimentos || {};

  return (
    <div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6">
      <div className="iv-veredicto">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <span className="iv-etiqueta">Laboratorio</span>
            <span className="iv-verbo text-tinta mt-1">
              {ex.total ? `${ex.total} ${ex.total === 1 ? "experimento" : "experimentos"}`
                        : "Sin medir todavía"}
            </span>
            <p className="mt-3 text-sm text-tinta-2 max-w-[52ch] leading-relaxed">
              Lo que InverIA ha leído no es lo que ha medido. Aquí se separan: lo que
              alguien escribió, lo que creemos que mejoraría una decisión, y lo que hemos
              comprobado sobre nuestros propios datos.
            </p>
          </div>
          <button onClick={cargar} disabled={cargando}
                  className="iv-etiqueta flex items-center gap-1.5 text-tinta-3
                             hover:text-tinta disabled:opacity-50 shrink-0"
                  data-testid="lab-refrescar">
            <ArrowClockwise size={14} /> Actualizar
          </button>
        </div>
      </div>

      {error && (
        <p className="mt-4 text-sm text-baja" role="alert">
          No se ha podido leer el laboratorio: {String(error)}.
        </p>
      )}

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div>
          <div className="iv-seccion iv-seccion-acento">
            <span className="iv-etiqueta">Lo que creemos y no hemos medido</span>
          </div>
          <p className="text-xs text-tinta-3 max-w-[70ch] leading-relaxed mb-3">
            Umbrales que el sistema necesitará y que hoy valen «sin medir» a propósito.
            Ninguno se copia de un libro: cada uno declara qué experimento haría falta.
          </p>
          <ul className="divide-y divide-linea">
            {(h.lista || []).map((x) => <Hipotesis key={x.id} h={x} />)}
          </ul>
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Cifra n={h.total} etiqueta="Hipótesis" />
            <Cifra n={h.medibles_hoy} etiqueta="Medibles hoy" />
            <Cifra n={h.bloqueadas} etiqueta="Bloqueadas" />
          </div>
        </div>

        <div>
          <div className="iv-seccion"><span className="iv-etiqueta">Lo que hemos medido</span></div>

          {!cargando && !experimentos.length && (
            <p className="text-sm text-tinta-3 max-w-[60ch] leading-relaxed">
              Todavía no se ha ejecutado ningún experimento. Eso no es un fallo: es el
              estado honesto de partida.
            </p>
          )}

          <ul className="divide-y divide-linea">
            {experimentos.map((e, i) => <Experimento key={`${e.hipotesis_id}-${i}`} e={e} />)}
          </ul>

          <div className="mt-4 flex flex-wrap gap-2">
            <button onClick={() => ejecutar("distanciaAlMaximo")} disabled={corriendo}
                    className="iv-etiqueta flex items-center gap-2 border border-linea
                               px-3 py-2 hover:text-tinta disabled:opacity-50"
                    data-testid="lab-ejecutar">
              <FlaskIcon size={14} />
              {corriendo ? "Midiendo…" : "Medir: distancia al máximo anual"}
            </button>
            <button onClick={() => ejecutar("pendiente")} disabled={corriendo}
                    className="iv-etiqueta flex items-center gap-2 border border-linea
                               px-3 py-2 hover:text-tinta disabled:opacity-50"
                    data-testid="lab-ejecutar-pendiente">
              <FlaskIcon size={14} />
              {corriendo ? "Midiendo…" : "Medir: persistencia de la tendencia"}
            </button>
            <button onClick={() => ejecutar("periodo")} disabled={corriendo}
                    className="iv-etiqueta flex items-center gap-2 border border-linea
                               px-3 py-2 hover:text-tinta disabled:opacity-50"
                    data-testid="lab-ejecutar-periodo">
              <FlaskIcon size={14} />
              {corriendo ? "Midiendo…" : "Corte temporal: ¿se repite cada año?"}
            </button>
            <button onClick={() => ejecutar("distribucion")} disabled={corriendo}
                    className="iv-etiqueta flex items-center gap-2 border border-linea
                               px-3 py-2 hover:text-tinta disabled:opacity-50"
                    data-testid="lab-ejecutar-distribucion">
              <FlaskIcon size={14} />
              {corriendo ? "Midiendo…" : "Diagnóstico: ¿centro o cola?"}
            </button>
          </div>
          <p className="mt-2 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
            Descarga el histórico semanal de tu universo y mide el retorno posterior
            según lo lejos que estuviera cada acción de su máximo anual. No llama a
            ningún modelo y no gasta cuota de IA, pero son decenas de peticiones — por
            eso lo disparas tú y no un bucle.
          </p>

          <div className="mt-10">
            <div className="iv-seccion"><span className="iv-etiqueta">Con qué datos contamos</span></div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Cifra n={c.dias} etiqueta="Días con foto" />
              <Cifra n={c.simbolos} etiqueta="Símbolos" />
              <Cifra n={c.fotos} etiqueta="Fotos" />
              <Cifra n={datos?.conocimiento?.conceptos} etiqueta="Conceptos leídos" />
            </div>
            <p className="mt-2 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
              {c.desde
                ? `Desde el ${c.desde} hasta el ${c.hasta}.`
                : "Todavía no se ha tomado ninguna foto diaria."}{" "}
              Los conceptos leídos se cuentan aparte del resto a propósito: haber leído
              algo no es haberlo comprobado, y sumarlos daría un número que mezcla las
              dos cosas.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
