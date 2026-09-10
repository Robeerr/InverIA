import React, { useEffect, useRef, useState } from "react";
import { X, ArrowSquareOut, FileText } from "@phosphor-icons/react";
import { api } from "../../lib/api";
import { nivelDe, tieneAnalisis, ETAPAS } from "../../lib/intelligence";
import { fmtHace, fmtDateTime } from "../../lib/format";

/**
 * El detalle de un evento. Un panel lateral, no un modal a pantalla completa: el radar se
 * sigue viendo detrás, que es el contexto de lo que estás leyendo.
 *
 * LA PARTE MÁS IMPORTANTE ES LA QUE DICE QUE NO SABE NADA
 *
 * En esta fase no hay análisis por IA. Así que este panel enseña el titular de la fuente,
 * el enlace al documento original y una frase diciendo exactamente eso: que no hay
 * interpretación, solo el hecho. La alternativa —dejar un hueco, o poner un «Analizando…»
 * que no analiza nada— convertiría una limitación conocida en un fallo aparente o, peor,
 * en una promesa falsa.
 *
 * EL ENLACE AL ORIGINAL NO ES UN EXTRA
 *
 * Es lo que hace comprobable todo lo demás. Un evento del que no puedes ir a leer la fuente
 * es una afirmación, y este sistema se construyó justamente para no tener que fiarse de
 * afirmaciones.
 */
/**
 * El documento tal como lo lee la IA, sin llamar a la IA.
 *
 * POR QUÉ ESTÁ AQUÍ Y NO EN EL PLAN
 *
 * Cuando una lectura dice «no permitía concluir nada» hay dos explicaciones que se ven
 * idénticas: el documento no decía nada, o le mandamos el documento equivocado. Muchos
 * 8-K son una carátula que remite a un anexo 99.1 y el contenido está allí.
 *
 * Solo se puede distinguir leyendo lo que leyó. Y hace más falta en los eventos YA
 * investigados —que no se pueden relanzar, porque la idempotencia lo impide— que en los
 * pendientes, así que vive donde se mira un evento concreto.
 */
function Documento({ evento }) {
  const [d, setD] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);

  const mirar = async () => {
    setCargando(true);
    setError(null);
    try {
      setD(await api.intelligence.documento(evento.id));
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "No se pudo leer");
    } finally {
      setCargando(false);
    }
  };

  const v = d?.verificacion;
  return (
    <div className="mt-6">
      <div className="iv-seccion"><span className="iv-etiqueta">El documento</span></div>
      <button onClick={mirar} disabled={cargando}
              className="inline-flex items-center gap-1.5 text-sm text-tinta-2
                         hover:text-tinta disabled:opacity-50"
              data-testid="ver-documento">
        <FileText size={14} />
        {cargando ? "Descargando…" : "Ver lo que lee la IA"}
      </button>
      <p className="mt-1 text-xs text-tinta-3">
        Una petición a la SEC. No llama a ningún modelo ni cambia nada.
      </p>

      {error && <p className="mt-2 text-xs text-baja" role="alert">{String(error)}</p>}

      {d && (
        <div className="mt-3">
          <p className="text-xs text-tinta-3">
            HTTP <span className="iv-cifra">{d.http ?? "—"}</span> ·{" "}
            <span className="iv-cifra">{d.bytes}</span> bytes ·{" "}
            <span className="iv-cifra">{d.caracteres}</span> caracteres de texto ·{" "}
            se enviarían <span className="iv-cifra">{d.caracteres_que_se_enviarian}</span>
          </p>
          {v && (
            <p className={`mt-1 text-xs ${v.ok ? "text-tinta-3" : "text-alerta"}`}>
              {v.ok ? "El texto menciona el filing." :
                "AVISO: no menciona ni el formulario ni el número de registro."}
            </p>
          )}
          {d.error && <p className="mt-1 text-xs text-baja">{d.error}</p>}
          {d.texto && (
            <pre className="mt-2 text-xs text-tinta-2 whitespace-pre-wrap break-words
                            max-h-96 overflow-y-auto border-l border-linea pl-3">
              {d.texto}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}


export default function IntelligenceDrawer({ evento, onCerrar }) {
  const cerrar = useRef(null);

  // Escape cierra, y el foco entra en el panel: sin esto, para alguien navegando con
  // teclado el panel se abre "en otro sitio" y hay que tabular por toda la página.
  useEffect(() => {
    if (!evento) return undefined;
    const alPulsar = (e) => { if (e.key === "Escape") onCerrar(); };
    document.addEventListener("keydown", alPulsar);
    cerrar.current?.focus();
    return () => document.removeEventListener("keydown", alPulsar);
  }, [evento, onCerrar]);

  if (!evento) return null;
  const n = nivelDe(evento);
  // `detalle` es la lista blanca de `crudo` que la API deja salir: escalares pequeños, sin
  // el documento entero de la fuente. Puede venir a null y entonces no se pinta ficha.
  const d = evento.detalle;

  return (
    <aside
      className="fixed inset-y-0 right-0 z-40 w-full sm:w-[420px] bg-superficie border-l
                 border-linea overflow-y-auto"
      role="dialog" aria-modal="true" aria-label={`Evento de ${evento.symbol || "una fuente"}`}
      data-testid="intelligence-drawer"
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <span className="iv-etiqueta">{evento.fuente}</span>
            <h2 className="font-heading text-2xl text-tinta mt-0.5">{evento.symbol || "—"}</h2>
          </div>
          <button ref={cerrar} onClick={onCerrar} aria-label="Cerrar"
                  className="text-tinta-3 hover:text-tinta p-1 -m-1">
            <X size={18} />
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className={`iv-etiqueta ${n.clase}`}>{n.etiqueta}</span>
          {evento.relevancia != null && (
            <span className="iv-cifra text-xs text-tinta-3">
              relevancia {evento.relevancia}/100
            </span>
          )}
          <span className="text-xs text-tinta-3">{fmtHace(evento.recibido_en)}</span>
        </div>

        <p className="mt-4 text-[15px] leading-relaxed text-tinta">{evento.titulo}</p>

        {/* La frase que impide creerse más de lo que hay. */}
        {!tieneAnalisis(evento) && (
          <p className="mt-3 text-xs text-tinta-3 border-l border-linea-fuerte pl-3">
            Esto es el titular tal cual lo publicó la fuente. InverIA no lo ha interpretado:
            todavía no hay análisis automático de eventos, así que la lectura la haces tú
            sobre el documento original.
          </p>
        )}
        {tieneAnalisis(evento) && (
          <p className="mt-3 text-sm text-tinta-2 leading-relaxed">{evento.resumen}</p>
        )}

        {/* El detalle propio de unos resultados. Solo se pinta lo que la fuente trajo:
            sin estimación no se enseña una comparación inventada. */}
        {d?.suceso && (
          <dl className="mt-4 text-sm space-y-1">
            {d.fecha_anterior && (
              <div className="flex justify-between gap-3">
                <dt className="text-tinta-3">Fecha anterior</dt>
                <dd className="iv-cifra text-tinta-2">{d.fecha_anterior}</dd>
              </div>
            )}
            {d.fecha && (
              <div className="flex justify-between gap-3">
                <dt className="text-tinta-3">
                  {d.suceso === "publicado" ? "Publicado el" : "Fecha prevista"}
                </dt>
                <dd className="iv-cifra text-tinta-2">{d.fecha}</dd>
              </div>
            )}
            {d.eps_estimado != null && (
              <div className="flex justify-between gap-3">
                <dt className="text-tinta-3">BPA esperado</dt>
                <dd className="iv-cifra text-tinta-2">{d.eps_estimado} $</dd>
              </div>
            )}
            {d.eps_real != null && (
              <div className="flex justify-between gap-3">
                <dt className="text-tinta-3">BPA real</dt>
                <dd className="iv-cifra text-tinta-2">{d.eps_real} $</dd>
              </div>
            )}
          </dl>
        )}

        {/* La fecha del calendario es del proveedor, no un anuncio de la empresa. Decirlo
            no es letra pequeña: es la diferencia entre un hecho y una previsión. */}
        {d?.suceso && d.suceso !== "publicado" && (
          <p className="mt-3 text-xs text-tinta-3 border-l border-linea-fuerte pl-3">
            Fecha del calendario de Finnhub. Puede ser una estimación suya y no un anuncio
            de la empresa, y por eso puede moverse — cuando se mueve, entra como un evento
            propio.
          </p>
        )}

        {evento.url && (
          <a href={evento.url} target="_blank" rel="noopener noreferrer"
             className="mt-4 inline-flex items-center gap-1.5 text-sm text-marca
                        hover:underline">
            Leer el documento original <ArrowSquareOut size={14} />
          </a>
        )}

        {/* Por qué te está llegando esto. Contestarlo es lo que separa una alerta de una
            notificación: si no puedes decir por qué te afecta, no deberías interrumpir. */}
        <div className="mt-6">
          <div className="iv-seccion"><span className="iv-etiqueta">Por qué te llega</span></div>
          <ul className="text-sm text-tinta-2 space-y-1">
            {evento.afecta_cartera && <li>Tienes {evento.symbol} en cartera.</li>}
            {evento.afecta_watchlist && !evento.afecta_cartera &&
              <li>Sigues {evento.symbol} sin tenerlo comprado.</li>}
            {evento.afecta_tesis && <li>Forma parte de una tesis tuya.</li>}
            <li className="text-tinta-3">
              Fuente de tier {evento.tier}
              {evento.tier === 1 ? " · hecho registrado, no una opinión" : ""}.
            </li>
          </ul>
        </div>

        {/* Solo para lo que tiene documento: un evento de resultados no tiene filing
            que inspeccionar. */}
        {evento.url && <Documento evento={evento} />}

        <div className="mt-6">
          <div className="iv-seccion"><span className="iv-etiqueta">Trazabilidad</span></div>
          <dl className="text-xs text-tinta-3 space-y-1">
            <div className="flex justify-between gap-3">
              <dt>Etapa</dt><dd className="text-tinta-2">{ETAPAS[evento.etapa] || evento.etapa}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt>Recibido</dt>
              <dd className="iv-cifra text-tinta-2">{fmtDateTime(evento.recibido_en)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt>Identificador</dt>
              <dd className="iv-cifra text-tinta-2 truncate max-w-[220px]">{evento.id}</dd>
            </div>
          </dl>
        </div>
      </div>
    </aside>
  );
}
