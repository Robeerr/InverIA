import React, { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, CaretRight, FlaskIcon } from "@phosphor-icons/react";
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

/** El veredicto: un punto del color del estado y su nombre. Sin caja ni chip: en una
 *  lista de catorce, catorce chips son ruido; el punto basta para leerlos en vertical. */
const Estado = ({ valor }) => {
  const e = ESTADOS[valor] || { etiqueta: valor || "—", clase: "text-tinta-3" };
  return (
    <span className={`iv-etiqueta shrink-0 inline-flex items-center gap-1.5 whitespace-nowrap ${e.clase}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
      {e.etiqueta}
    </span>
  );
};

/** Una cifra con su nombre. Sin totales: cada una responde a UNA pregunta. El número va
 *  en tabulares y con `break-all` de red: una cuenta de siete cifras no desborda la celda. */
const Cifra = ({ n, etiqueta }) => (
  // El rótulo va primero en el DOM (lo exige <dl>) y debajo en pantalla: se mira la cifra.
  <div className="min-w-0 py-2 flex flex-col-reverse">
    <dt className="iv-etiqueta mt-1.5">{etiqueta}</dt>
    <dd className="iv-cifra text-titulo font-semibold text-tinta leading-none [overflow-wrap:anywhere]">
      {n ?? "—"}
    </dd>
  </div>
);

/* ── Piezas comunes de las tablas ───────────────────────────────────────────
   Todas las tablas del laboratorio comparten rejilla: rótulos pequeños y apagados con
   un filete más fuerte debajo, cifras tabulares alineadas a la derecha, y la primera
   columna pegada al borde izquierdo para que la lista se lea como una sola columna. */
const TABLA = "text-xs w-full border-collapse";
const CABECERA = "text-tinta-3 border-b border-linea-fuerte";
const TH_IZQ = "text-left font-normal align-bottom py-1.5 pr-3";
const TH = "text-right font-normal align-bottom py-1.5 px-2 last:pr-0";
const FILA = "border-t border-linea first:border-t-0";
const TD_IZQ = "py-1.5 pr-3 text-tinta-2 whitespace-nowrap";
const TD = "text-right py-1.5 px-2 last:pr-0 whitespace-nowrap";
const NOTA = "mt-2 text-xs text-tinta-3 max-w-[70ch] leading-relaxed";
const DESPLAZABLE = "mt-3 overflow-x-auto";

/** El rótulo de un desplegable: un triángulo que gira al abrir, en el naranja de los
 *  enlaces. El giro es la única animación de la pantalla y dice algo —abierto o
 *  cerrado—, así que se queda; con movimiento reducido, cambia sin girar. */
function Rotulo({ children }) {
  return (
    <summary className="inline-flex items-center gap-1.5 text-xs text-marca cursor-pointer list-none
                        [&::-webkit-details-marker]:hidden select-none py-1.5
                        underline-offset-4 decoration-marca/50 hover:underline
                        rounded-iv-sm focus-visible:outline focus-visible:outline-2
                        focus-visible:outline-offset-2 focus-visible:[outline-color:rgb(var(--iv-foco))]">
      <CaretRight size={11} weight="bold" aria-hidden="true"
                  className="shrink-0 transition-transform duration-150 ease-out
                             group-open:rotate-90 motion-reduce:transition-none" />
      {children}
    </summary>
  );
}

function Hipotesis({ h }) {
  const [abierta, setAbierta] = useState(false);
  return (
    <li data-testid={`lab-hipotesis-${h.id}`}>
      {/* El título ya no se trunca: cortado a media frase, «Distancia máxima al…» no
          dice qué umbral es, y en móvil se cortaban casi todos. */}
      <button onClick={() => setAbierta((v) => !v)} aria-expanded={abierta}
              className="w-full text-left py-2.5 flex items-start gap-2.5 group">
        <CaretRight size={11} weight="bold" aria-hidden="true"
                    className={`shrink-0 mt-[5px] text-tinta-3 group-hover:text-tinta-2
                                transition-transform duration-150 ease-out motion-reduce:transition-none
                                ${abierta ? "rotate-90" : ""}`} />
        <span className="flex-1 min-w-0 text-apoyo text-tinta-2 group-hover:text-tinta
                         transition-colors duration-150 motion-reduce:transition-none">
          {h.titulo}
        </span>
        <span className="mt-[2px]"><Estado valor={h.estado} /></span>
      </button>
      {abierta && (
        <div className="pb-3 ml-[5px] pl-[15px] space-y-2 border-l border-linea">
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

/** El corte por año llega en `resultado.años` cuando el experimento ES el corte, y en
 *  `resultado.por_periodo` cuando viaja dentro de otro. Buscarlo en un solo sitio ya
 *  dejó la tabla invisible una vez. */
const añosDe = (r) => (r.años || r.por_periodo?.años || []);
const descartadosDe = (r) =>
  (r.años_descartados || r.por_periodo?.años_descartados || []);

function Experimento({ e }) {
  const r = e.resultado || {};
  return (
    <li className="py-5 first:pt-1" data-testid={`lab-experimento-${e.hipotesis_id}-${e.intento}`}>
      {/* El veredicto arriba y antes que el título en móvil: es lo que se busca al
          recorrer la lista. En escritorio va a la derecha, alineado en columna. */}
      <div className="flex flex-col-reverse gap-1.5 sm:flex-row sm:items-baseline sm:gap-4">
        <h3 className="flex-1 min-w-0 font-heading text-cuerpo font-semibold text-tinta leading-snug
                       [text-wrap:balance]">
          {e.titulo}
        </h3>
        <div className="flex items-baseline gap-3 shrink-0">
          <Estado valor={e.estado} />
          <span className="iv-cifra text-etiqueta text-tinta-3 whitespace-nowrap">intento {e.intento}</span>
        </div>
      </div>
      {/* De qué experimento nace éste. Una réplica sin su motivo delante se lee como
          otra tirada más, y lo que la hace valer es exactamente lo contrario: que
          responde a una duda concreta del experimento anterior. El backend lo venía
          calculando desde el aguante limpio y la pantalla nunca lo enseñó. */}
      {/* El rótulo «Réplica de:» conserva el ámbar; el motivo va en tinta normal. Todo
          en ámbar y negrita gritaba más que el propio veredicto. */}
      {e.deriva_de && (
        <p className="mt-2 text-xs text-tinta-2 max-w-[70ch] leading-relaxed">
          <b className="text-aviso font-semibold">Réplica de:</b> {e.deriva_de}
        </p>
      )}
      {/* La conclusión es lo que se viene a leer: un paso de tamaño y de tinta por
          encima de las notas al pie de las tablas. */}
      <p className="mt-2 text-apoyo text-tinta-2 max-w-[70ch] leading-relaxed">
        {r.conclusion}
      </p>
      {!!(r.multiplos || []).length && (
        <div className={DESPLAZABLE}>
          <table className={TABLA}>
            <thead className={CABECERA}>
              <tr><th className={TH_IZQ}>Stop</th>
                  <th className={TH}>Salta</th>
                  <th className={TH}>Saltos</th>
                  <th className={TH}>En falso</th>
                  <th className={TH}>Ahorro (ATR)</th></tr>
            </thead>
            <tbody className="iv-cifra">
              {r.multiplos.map((m) => (
                <tr key={m.multiplo} className={FILA}>
                  <td className={TD_IZQ}>{m.multiplo}×ATR</td>
                  {/* «Salta» va apagado a propósito: está determinado por aritmética
                      —si no bajó 1,0 ATR tampoco bajó 2,4— y no es evidencia de nada. */}
                  <td className={`${TD} text-tinta-3`}>
                    {m.salta_pct == null ? "—" : `${m.salta_pct}%`}
                  </td>
                  <td className={`${TD} text-tinta-3`}>{m.n_saltan}</td>
                  <td className={`${TD} text-tinta font-semibold`}>
                    {m.falsos_pct == null ? "—" : `${m.falsos_pct}%`}
                  </td>
                  <td className={`${TD} text-tinta-3`}>
                    {m.ahorro_atr_mediana == null ? "—" : m.ahorro_atr_mediana}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {r.banda && (
            <p className={NOTA}>
              Diferencia observada {r.banda.observada_pp} pp · banda de{" "}
              {r.banda.banda_baja_pp} a {r.banda.banda_alta_pp} pp, por remuestreo de{" "}
              {r.banda.bloques} días.{" "}
              {/* Antes decía «Si incluye el cero, no se distinguen» pasara lo que
                  pasara. Es la regla, no el resultado — y puesta debajo de una banda
                  que NO incluye el cero se lee como si dijera que no se distinguen,
                  justo lo contrario de lo medido. Dice lo que ha salido. */}
              {r.banda.banda_baja_pp <= 0 && r.banda.banda_alta_pp >= 0
                ? "Incluye el cero: no se distinguen."
                : "No incluye el cero: se distinguen."}
            </p>
          )}
        </div>
      )}
      {!!(r.cubos || []).length && (
        <div className={DESPLAZABLE}>
          <table className={TABLA}>
            <thead className={CABECERA}>
              {/* La cabecera la pone el experimento: esta misma tabla sirve para los
                  cubos de fuerza y para los tramos de profundidad, y poner «Fuerza» en
                  los dos diría que se midió algo que no se midió. */}
              <tr><th className={TH_IZQ}>{r.etiqueta_cubo || "Fuerza"}</th>
                  <th className={TH}>Toques resueltos</th>
                  {/* El rótulo lo pone el experimento: con la métrica exigente, la
                      tasa que llega a esta columna es la del aguante LIMPIO, y dejar
                      «Aguantó» pondría el número estricto donde se espera el laxo. */}
                  <th className={TH}>{r.etiqueta_metrica || "Aguantó"}</th>
                  <th className={TH}>Aguantó limpio</th></tr>
            </thead>
            <tbody className="iv-cifra">
              {r.cubos.map((c) => (
                <tr key={c.cubo} className={FILA}>
                  <td className={TD_IZQ}>{c.cubo}</td>
                  <td className={`${TD} text-tinta-3`}>{c.n}</td>
                  <td className={`${TD} text-tinta font-semibold`}>
                    {c.aguante_pct == null ? "—" : `${c.aguante_pct}%`}
                  </td>
                  <td className={`${TD} text-tinta-3`}>
                    {c.aguante_limpio_pct == null ? "—" : `${c.aguante_limpio_pct}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {r.ruido && (
            <p className={NOTA}>
              Separación observada {r.ruido.observado_pp} pp · suelo de ruido{" "}
              {r.ruido.azar_p95_pp} pp, medido barajando los cubos dentro de cada fecha.
            </p>
          )}
        </div>
      )}
      {!!(r.tramos || []).length && (
        <div className={DESPLAZABLE}>
          <table className={TABLA}>
            <thead className={CABECERA}>
              <tr><th className={TH_IZQ}>Tramo</th>
                  <th className={TH}>Muestra</th>
                  <th className={TH}>Retorno medio</th>
                  {r.tramos.some((t) => t.mediana != null) && (
                    <>
                      <th className={TH}>Mediana</th>
                      {/* La amplitud responde «¿es solo que se mueve más?» y el peso del
                          10% mejor, «¿lo explica un puñado de aciertos?». Las dos se
                          medían desde el principio y no se enseñaban. */}
                      <th className={TH}>P25–P75</th>
                      <th className={TH}>Amplitud</th>
                      <th className={TH}>10% mejor</th>
                    </>
                  )}
                  <th className={TH}>Positivos</th></tr>
            </thead>
            <tbody className="iv-cifra">
              {r.tramos.map((t) => (
                <tr key={t.tramo} className={FILA}>
                  <td className={TD_IZQ}>{t.tramo}</td>
                  <td className={`${TD} text-tinta-3`}>{t.n}</td>
                  <td className={`${TD} text-tinta-2`}>
                    {(t.retorno_medio ?? t.media) == null
                      ? "—" : `${t.retorno_medio ?? t.media}%`}
                  </td>
                  {r.tramos.some((x) => x.mediana != null) && (
                    <>
                      <td className={`${TD} text-tinta font-semibold`}>
                        {t.mediana == null ? "—" : `${t.mediana}%`}
                      </td>
                      <td className={`${TD} text-tinta-3`}>
                        {t.p25 == null ? "—" : `${t.p25} / ${t.p75}`}
                      </td>
                      <td className={`${TD} text-tinta-3`}>
                        {t.amplitud_intercuartil == null
                          ? "—" : `${t.amplitud_intercuartil} pp`}
                      </td>
                      <td className={`${TD} text-tinta-3`}>
                        {t.peso_del_10pct_mejor == null
                          ? "—" : `${t.peso_del_10pct_mejor}%`}
                      </td>
                    </>
                  )}
                  <td className={`${TD} text-tinta-3`}>
                    {t.positivos_pct == null ? "—" : `${t.positivos_pct}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!!(r.tramos || []).some((t) => t.por_año) && (
        <details className="group mt-2">
          <Rotulo>Reparto por año</Rotulo>
          <p className="mt-1 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
            Si un tramo se concentra en un año concreto, lo que mide es ese año.
          </p>
          <div className={DESPLAZABLE}>
            <table className={`${TABLA} iv-cifra`}>
              <tbody>
                {r.tramos.map((t) => (
                  <tr key={t.tramo} className={FILA}>
                    <td className={TD_IZQ}>{t.tramo}</td>
                    {Object.entries(t.por_año || {}).map(([a, n]) => (
                      <td key={a} className={`${TD} text-tinta-3`}>
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
      {!!añosDe(r).length && (
        <div className={DESPLAZABLE}>
          <table className={TABLA}>
            <thead className={CABECERA}>
              {/* Etiqueta GENÉRICA. Decía «¿Peor el tramo en máximos?» y acabó
                  preguntando por máximos en una hipótesis sobre la persistencia de la
                  tendencia. La columna de dirección solo sale si la hipótesis declaró una. */}
              <tr><th className={TH_IZQ}>Año</th>
                  <th className={TH}>Muestra</th>
                  {añosDe(r).some((a) => a.direccion_se_cumple != null) && (
                    <th className={TH}>¿Se cumple la dirección?</th>
                  )}
                  <th className={TH}>¿El primer tramo es el peor?</th>
                  <th className={TH}>Escalón</th></tr>
            </thead>
            <tbody className="iv-cifra">
              {añosDe(r).map((a) => (
                <tr key={a.año} className={FILA}>
                  <td className={TD_IZQ}>{a.año}</td>
                  <td className={`${TD} text-tinta-3`}>{a.n}</td>
                  {añosDe(r).some((x) => x.direccion_se_cumple != null) && (
                    <td className={`${TD} ${a.direccion_se_cumple
                                      ? "text-sube" : "text-tinta-3"}`}>
                      {a.direccion_se_cumple == null
                        ? "—" : a.direccion_se_cumple ? "sí" : "no"}
                    </td>
                  )}
                  <td className={`${TD} ${a.el_primer_tramo_es_el_PEOR
                                    ? "text-tinta" : "text-tinta-3"}`}>
                    {a.el_primer_tramo_es_el_PEOR ? "sí" : "no"}
                  </td>
                  <td className={`${TD} text-tinta-3`}>{a.escalon_pp} pp</td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* Los años SIN muestra suficiente desaparecían de la tabla en silencio, y un
              año que falta se lee como un año que no existió. */}
          {!!descartadosDe(r).length && (
            <p className={NOTA}>
              Sin muestra suficiente en todos los tramos, así que no se evalúan:{" "}
              {descartadosDe(r).map((x) => x.año).join(", ")}.
            </p>
          )}
        </div>
      )}
      {/* El desglose por metodología. `backtest` ya lo calculaba y nadie lo guardaba;
          ahora viaja con el experimento. Va como DESCRIPTIVO y con el aviso delante:
          buscar aquí «la fuente buena» después de ver la tabla sería elegir el ganador
          mirando el marcador, que es justo lo que el laboratorio existe para no hacer. */}
      {!!Object.keys(e.por_fuente || {}).length && (
        <details className="group mt-2">
          <Rotulo>Por metodología · descriptivo, NO probado</Rotulo>
          <p className="mt-1 text-xs text-aviso max-w-[70ch] leading-relaxed">
            Estas cifras no se han contrastado contra ruido ni tenían dirección fijada de
            antemano. Sirven para saber dónde mirar después; elegir una de aquí porque
            sale bien en la tabla sería escoger al ganador mirando el marcador.
          </p>
          <div className={DESPLAZABLE}>
            <table className={TABLA}>
              <thead className={CABECERA}>
                <tr><th className={TH_IZQ}>Metodología</th>
                    <th className={TH}>Toques</th>
                    <th className={TH}>Aguantó</th>
                    <th className={TH}>Limpio</th></tr>
              </thead>
              <tbody className="iv-cifra">
                {Object.entries(e.por_fuente).map(([fuente, v]) => (
                  <tr key={fuente} className={FILA}>
                    <td className={TD_IZQ}>{fuente}</td>
                    <td className={`${TD} text-tinta-3`}>{v.n}</td>
                    <td className={`${TD} text-tinta-3`}>
                      {v.hold_rate == null ? "—" : `${v.hold_rate}%`}
                    </td>
                    <td className={`${TD} text-tinta font-semibold`}>
                      {v.clean_hold_rate == null ? "—" : `${v.clean_hold_rate}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {/* El método viaja con el resultado. Un «+14%» sin saber sobre qué universo, con
          qué horizonte y con qué sesgos no se puede revisar dentro de seis meses. */}
      {e.controles && (
        <details className="group mt-2">
          <Rotulo>Método y sesgos</Rotulo>
          <dl className="mt-2 ml-[5px] pl-[15px] border-l border-linea space-y-2.5">
            {Object.entries(e.controles).map(([k, v]) => (
              <div key={k} className="text-xs">
                <dt className="iv-etiqueta [overflow-wrap:anywhere]">{k}</dt>
                <dd className="mt-0.5 text-tinta-3 max-w-[70ch] leading-relaxed">{v}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </li>
  );
}

/** Un botón de experimento. Solo el que corre cambia de texto.
 *
 *  Antes eran once cajas con borde, en mayúsculas de 11 px, que se partían en líneas de
 *  anchos distintos. Ahora es una lista de filas en caja baja, legible de corrido; el
 *  naranja pasa del borde al matraz (las réplicas y auditorías siguen marcadas), y el
 *  que corre conserva el borde naranja y un latido en el icono para encontrarlo. */
function Boton({ cual, activo, on, testid, acento, verbo = "Midiendo…", children }) {
  const yo = activo === cual;
  return (
    <button onClick={() => on(cual)} disabled={!!activo} data-testid={testid}
            aria-busy={yo || undefined}
            className={`w-full text-left flex items-start gap-2.5 rounded-iv-sm border px-3 py-2.5
                        text-apoyo leading-snug transition-[color,background-color,border-color,transform]
                        duration-150 ease-out motion-reduce:transition-none
                        enabled:hover:bg-superficie-alt enabled:hover:text-tinta enabled:hover:border-linea-fuerte
                        enabled:active:scale-[0.98] motion-reduce:enabled:active:scale-100
                        disabled:cursor-not-allowed
                        ${yo ? "border-marca text-tinta bg-superficie-alt"
                             : "border-linea text-tinta-2 disabled:opacity-50"}`}>
      <FlaskIcon size={14} aria-hidden="true"
                 className={`shrink-0 mt-[2px] ${acento || yo ? "text-marca" : "text-tinta-3"}
                             ${yo ? "animate-pulse" : ""}`} />
      <span className="min-w-0">{yo ? verbo : children}</span>
    </button>
  );
}

export default function LaboratorioView() {
  const [datos, setDatos] = useState(null);
  const [experimentos, setExperimentos] = useState([]);
  const [cargando, setCargando] = useState(true);
  // Cuál se está ejecutando, no «si hay alguno»: con un booleano los nueve botones
  // decían «Midiendo…» a la vez y ninguno decía cuál. Un experimento tarda minutos.
  const [corriendo, setCorriendo] = useState(null);
  const [error, setError] = useState(null);
  // El fallo de EJECUTAR es otro que el de LEER. Compartían estado y compartían
  // cartel, así que un experimento caído se anunciaba como «no se ha podido leer el
  // laboratorio» y encima arriba del todo, lejos del botón que acababas de pulsar.
  const [fallo, setFallo] = useState(null);

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
    setCorriendo(cual);
    setFallo(null);
    try {
      const r = await (api.laboratorio[cual] || api.laboratorio.distanciaAlMaximo)();
      // El backend dice si LLEGÓ A GUARDARSE, y hasta ahora se tiraba. Un experimento
      // que corre entero, devuelve 200 y falla al insertar era indistinguible de un
      // botón muerto: sin error, sin línea nueva, sin nada que mirar.
      if (r?.guardado && r.guardado.ok === false) {
        setFallo(`el experimento se ha ejecutado pero NO se ha podido guardar `
                 + `(${r.guardado.motivo || "sin motivo"}`
                 + `${r.guardado.error ? `: ${r.guardado.error}` : ""}). `
                 + `Salió «${r.estado || "sin estado"}»`);
      } else if (r?.estado && r.guardado === undefined) {
        // Salida temprana del endpoint: ni se midió ni se guardó, pero devuelve 200.
        setFallo(`el experimento no ha llegado a medirse: `
                 + `${r.conclusion || r.estado}`);
      }
      await cargar();
    } catch (err) {
      setFallo(`la petición ha fallado: `
               + (err?.response?.data?.detail || err.message || "sin detalle"));
    } finally {
      setCorriendo(null);
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
            {/* Mientras llega la primera lectura no se dice «Sin medir todavía»: eso es un
                resultado, y todavía no lo hay. Va una barra en su sitio. */}
            {cargando && !datos ? (
              <span className="block mt-2 h-[clamp(30px,4.2vw,52px)] w-[min(18ch,70%)] rounded-iv-sm
                               bg-superficie-alt animate-pulse" aria-hidden="true" />
            ) : (
              <span className="iv-verbo text-tinta mt-1">
                {ex.total ? `${ex.total} ${ex.total === 1 ? "experimento" : "experimentos"}`
                          : "Sin medir todavía"}
              </span>
            )}
            <p className="mt-3 text-apoyo sm:text-cuerpo text-tinta-2 max-w-[58ch] leading-relaxed">
              Lo que InverIA ha leído no es lo que ha medido. Aquí se separan: lo que
              alguien escribió, lo que creemos que mejoraría una decisión, y lo que hemos
              comprobado sobre nuestros propios datos.
            </p>
          </div>
          {/* El icono gira mientras se lee: sin eso, pulsar «Actualizar» con la red lenta
              no daba ninguna señal. Con movimiento reducido el giro se apaga solo (App.css). */}
          <button onClick={cargar} disabled={cargando} aria-busy={cargando || undefined}
                  className="iv-etiqueta flex items-center gap-1.5 text-tinta-3 shrink-0 py-1.5 -my-1.5
                             hover:text-tinta transition-colors duration-150 motion-reduce:transition-none
                             disabled:opacity-50 disabled:cursor-wait"
                  data-testid="lab-refrescar">
            <ArrowClockwise size={14} aria-hidden="true" className={cargando ? "animate-spin" : ""} />
            Actualizar
          </button>
        </div>
      </div>

      {error && (
        <p className="mt-5 text-apoyo text-baja max-w-[70ch]" role="alert">
          No se ha podido leer el laboratorio: {String(error)}.
        </p>
      )}

      {/* Dos columnas de peso distinto: a la izquierda lo que se cree y con qué datos se
          cuenta, que es contexto corto; a la derecha lo medido, que es largo y es lo que
          se viene a leer. Antes iban a medias y la izquierda acababa en un hueco. */}
      <div className="mt-8 sm:mt-10 grid grid-cols-1 gap-10 lg:gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.55fr)]">
        <div className="min-w-0">
          <section aria-labelledby="lab-creemos">
            <div className="iv-seccion iv-seccion-acento">
              <h2 id="lab-creemos" className="iv-etiqueta">Lo que creemos y no hemos medido</h2>
            </div>
            <p className="text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
              Umbrales que el sistema necesitará y que hoy valen «sin medir» a propósito.
              Ninguno se copia de un libro: cada uno declara qué experimento haría falta.
            </p>
            {/* Las cuentas encima de la lista, no al pie: resumen primero, detalle después. */}
            <dl className="mt-4 grid grid-cols-3 gap-4 border-y border-linea">
              <Cifra n={h.total} etiqueta="Hipótesis" />
              <Cifra n={h.medibles_hoy} etiqueta="Medibles hoy" />
              <Cifra n={h.bloqueadas} etiqueta="Bloqueadas" />
            </dl>
            <ul className="mt-1 divide-y divide-linea">
              {(h.lista || []).map((x) => <Hipotesis key={x.id} h={x} />)}
            </ul>
          </section>

          <section className="mt-10" aria-labelledby="lab-datos">
            <div className="iv-seccion">
              <h2 id="lab-datos" className="iv-etiqueta">Con qué datos contamos</h2>
            </div>
            <dl className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4 gap-x-4 border-y border-linea">
              <Cifra n={c.dias} etiqueta="Días con foto" />
              <Cifra n={c.simbolos} etiqueta="Símbolos" />
              <Cifra n={c.fotos} etiqueta="Fotos" />
              <Cifra n={datos?.conocimiento?.conceptos} etiqueta="Conceptos leídos" />
            </dl>
            <p className={NOTA}>
              {c.desde
                ? `Desde el ${c.desde} hasta el ${c.hasta}.`
                : "Todavía no se ha tomado ninguna foto diaria."}{" "}
              Los conceptos leídos se cuentan aparte del resto a propósito: haber leído
              algo no es haberlo comprobado, y sumarlos daría un número que mezcla las
              dos cosas.
            </p>
          </section>
        </div>

        <section className="min-w-0" aria-labelledby="lab-medido">
          <div className="iv-seccion">
            <h2 id="lab-medido" className="iv-etiqueta">Lo que hemos medido</h2>
          </div>

          {!cargando && !experimentos.length && (
            <p className="py-6 text-apoyo text-tinta-3 max-w-[60ch] leading-relaxed border-y border-linea">
              Todavía no se ha ejecutado ningún experimento. Eso no es un fallo: es el
              estado honesto de partida.
            </p>
          )}

          {/* Primera carga: la silueta de tres experimentos en vez de una columna vacía. */}
          {cargando && !experimentos.length && (
            <div role="status" className="space-y-6 py-2">
              <span className="sr-only">Cargando experimentos…</span>
              {[0, 1, 2].map((i) => (
                <div key={i} aria-hidden="true" className="space-y-2.5">
                  <div className="h-4 w-3/4 rounded-iv-sm bg-superficie-alt animate-pulse" />
                  <div className="h-3 w-full rounded-iv-sm bg-superficie-alt animate-pulse" />
                  <div className="h-3 w-5/6 rounded-iv-sm bg-superficie-alt animate-pulse" />
                </div>
              ))}
            </div>
          )}

          <ul className="divide-y divide-linea">
            {experimentos.map((e, i) => <Experimento key={`${e.hipotesis_id}-${i}`} e={e} />)}
          </ul>

          {/* Los disparadores, en su propio panel al final de lo medido: «Lo que ves
              arriba» del aviso de fallo sigue apuntando a la lista. */}
          <div className="iv-panel mt-8 p-4 sm:p-5">
            <h3 className="iv-etiqueta mb-3">Lanzar un experimento</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <Boton cual="distanciaAlMaximo" activo={corriendo} on={ejecutar}
                   testid="lab-ejecutar">Medir: distancia al máximo anual</Boton>
            <Boton cual="aguante" activo={corriendo} on={ejecutar} acento
                   testid="lab-ejecutar-aguante">Medir: ¿aguantan las zonas fuertes?</Boton>
            <Boton cual="stops" activo={corriendo} on={ejecutar} acento
                   testid="lab-ejecutar-stops">Medir: ¿dónde poner el stop?</Boton>
            <Boton cual="profundidad" activo={corriendo} on={ejecutar} acento
                   testid="lab-ejecutar-profundidad">
              Medir: ¿aguantan menos las zonas más hondas?
            </Boton>
            <Boton cual="profundidadLimpia" activo={corriendo} on={ejecutar} acento
                   testid="lab-ejecutar-profundidad-limpia">
              Réplica fuera de muestra: zonas hondas, aguante limpio
            </Boton>
            <Boton cual="stopsFuera" activo={corriendo} on={ejecutar} acento
                   testid="lab-ejecutar-stops-fuera">
              Réplica fuera de muestra: ¿dónde poner el stop?
            </Boton>
            <Boton cual="aguanteLimpio" activo={corriendo} on={ejecutar} acento
                   testid="lab-ejecutar-aguante-limpio">
              Réplica fuera de muestra: aguante limpio
            </Boton>
            <Boton cual="azar" activo={corriendo} on={ejecutar} acento verbo="Barajando…"
                   testid="lab-ejecutar-azar">Auditar el método: ¿qué produce el azar?</Boton>
            <Boton cual="pendiente" activo={corriendo} on={ejecutar}
                   testid="lab-ejecutar-pendiente">Medir: persistencia de la tendencia</Boton>
            <Boton cual="periodo" activo={corriendo} on={ejecutar}
                   testid="lab-ejecutar-periodo">Corte temporal: ¿se repite cada año?</Boton>
            <Boton cual="distribucion" activo={corriendo} on={ejecutar}
                   testid="lab-ejecutar-distribucion">Diagnóstico: ¿centro o cola?</Boton>
          </div>

          {corriendo && (
            <p className="mt-3 text-xs text-tinta-2 leading-relaxed" role="status">
              Descargando histórico y midiendo. Tarda minutos y la pestaña tiene que
              seguir abierta: si la cierras, el experimento no se guarda.
            </p>
          )}
          {fallo && (
            <p className="mt-3 text-apoyo text-baja leading-relaxed" role="alert" data-testid="lab-fallo">
              No hay línea nueva porque {String(fallo)}. Lo que ves arriba sigue siendo
              la tirada anterior.
            </p>
          )}
          <p className={NOTA}>
            Descarga el histórico semanal de tu universo y mide el retorno posterior
            según lo lejos que estuviera cada acción de su máximo anual. No llama a
            ningún modelo y no gasta cuota de IA, pero son decenas de peticiones — por
            eso lo disparas tú y no un bucle.
          </p>
          </div>
        </section>
      </div>
    </div>
  );
}
