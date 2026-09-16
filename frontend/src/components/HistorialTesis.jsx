import React, { useState } from "react";
import { ClockCounterClockwise } from "@phosphor-icons/react";
import { fmtHace } from "../lib/format";
import { api } from "../lib/api";

/**
 * Cómo ha ido cambiando la tesis de una acción.
 *
 * QUÉ PROBLEMA RESUELVE, QUE NO ES «TENER HISTÓRICO»
 *
 * La tesis se redacta de nuevo en cada carga del dashboard. Sin registro, la pantalla
 * solo sabe decir qué piensa HOY, y después de una operación mala no hay forma de saber
 * si eso era lo que decía cuando entraste — ni siquiera para uno mismo. Se reescribe el
 * pasado sin querer, que es el fallo más caro que puede tener una herramienta así.
 *
 * `tesis_registro` lleva semanas guardando una versión cada vez que la huella cambia. El
 * dato estaba, los endpoints estaban, y no había ninguna pantalla que lo leyera.
 *
 * SE PIDE AL ABRIRLO, NO AL CARGAR LA ACCIÓN
 *
 * El histórico es un extra: el precio y la tesis de hoy son la pantalla. Añadir una
 * petición a cada carga del dashboard por algo que casi nunca se mira es cargarle a todo
 * el mundo el coste de una minoría.
 *
 * LO QUE ESTA PANTALLA NO HACE, Y ES DELIBERADO
 *
 * No dice si un cambio fue un matiz o un giro. `diff_de_campos` es mecánico —qué campos
 * entran y salen— y el propio backend lo declara: «decir si un cambio fue un matiz o un
 * giro sería interpretar, y eso todavía no se puede hacer con criterio». Enseñarlo como
 * un juicio sería inventarse una capa de análisis que no existe.
 *
 * Y no dice si una tesis ACERTÓ. `veces_observada` cuenta redacciones consecutivas con la
 * misma huella: dice que no ha cambiado, no que fuera correcta. Acertar se responde con
 * el precio de después y no se responde aquí.
 */

/** Qué campos entran y salen entre una versión y la anterior. Mecánico, no un juicio. */
function Cambios({ cambios }) {
  const entran = cambios?.entran || [];
  const salen = cambios?.salen || [];
  if (!entran.length && !salen.length) return null;
  return (
    <p className="text-[11px] font-mono text-tinta-3 mt-1 leading-relaxed">
      {entran.map((c) => (
        <span key={`e${c}`} className="mr-2 whitespace-nowrap">
          <span className="text-sube" aria-hidden="true">+</span>{c}
        </span>
      ))}
      {salen.map((c) => (
        <span key={`s${c}`} className="mr-2 whitespace-nowrap">
          <span className="text-baja" aria-hidden="true">−</span>{c}
        </span>
      ))}
    </p>
  );
}

function Version({ v, esUltima }) {
  return (
    <li className="py-2.5 border-t border-linea" data-testid={`tesis-version-${v.version}`}>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="text-[11px] font-mono text-tinta-3 shrink-0">v{v.version}</span>
        {esUltima && (
          <span className="text-[10px] uppercase tracking-[0.15em] font-mono text-marca shrink-0">
            vigente
          </span>
        )}
        <span className="text-[11px] font-mono text-tinta-3 ml-auto shrink-0">
          {fmtHace(v.creada_en)}
        </span>
      </div>
      <p className="text-[13px] text-tinta leading-snug mt-1">{v.titular || "—"}</p>
      <Cambios cambios={v.cambios} />
      {/* Cuántas redacciones seguidas dieron esta misma huella. NO es un acierto, y la
          frase lo dice entera para que no se lea como tal aunque nadie pase el ratón. */}
      {v.veces_observada > 1 && (
        <p className="text-[11px] text-tinta-3 mt-1">
          Se ha vuelto a redactar igual {v.veces_observada} veces. Dice que no ha
          cambiado, no que acertara.
        </p>
      )}
    </li>
  );
}

export default function HistorialTesis({ symbol }) {
  const [abierto, setAbierto] = useState(false);
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);

  const alternar = async () => {
    if (abierto) { setAbierto(false); return; }
    setAbierto(true);
    if (datos || cargando) return;      // ya cargado: no se vuelve a pedir
    setCargando(true);
    setError(null);
    try {
      setDatos(await api.tesis.versiones(symbol));
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "No se pudo leer");
    } finally {
      setCargando(false);
    }
  };

  if (!symbol) return null;
  const versiones = datos?.versiones || [];

  return (
    <div className="mt-3 pt-3 border-t border-linea">
      <button onClick={alternar} aria-expanded={abierto}
              data-testid="btn-historial-tesis"
              className="text-[12px] font-mono text-tinta-3 hover:text-tinta
                         flex items-center gap-1.5">
        <ClockCounterClockwise size={13} aria-hidden="true" />
        {abierto ? "Ocultar el historial" : "Cómo ha cambiado esta tesis"}
      </button>

      {abierto && (
        <div className="mt-2" data-testid="historial-tesis">
          {cargando && <p className="text-[12px] text-tinta-3">Leyendo el historial…</p>}

          {error && (
            <p className="text-[12px] text-baja" role="alert">
              No se ha podido leer el historial: {String(error)}. La tesis de arriba no
              depende de esto.
            </p>
          )}

          {/* Sin versiones NO es un fallo: es que esta acción todavía no se ha abierto
              desde que existe el registro. Una lista vacía sin explicación se lee como
              que algo se ha roto. */}
          {!cargando && !error && !versiones.length && (
            <p className="text-[12px] text-tinta-3 leading-relaxed max-w-[60ch]">
              Todavía no hay ninguna versión guardada de {symbol}. Se guarda una la
              primera vez que se redacta su tesis, y otra cada vez que cambia de verdad.
            </p>
          )}

          {versiones.length === 1 && (
            <p className="text-[12px] text-tinta-3 leading-relaxed max-w-[60ch] mb-1">
              Una sola versión: la tesis de {symbol} no ha cambiado desde que se registró.
            </p>
          )}

          {!!versiones.length && (
            <>
              <ul>
                {versiones.map((v, i) => (
                  <Version key={v.version} v={v} esUltima={i === 0} />
                ))}
              </ul>
              {/* El tope existe en el backend y callarlo haría parecer completa una
                  lista truncada. */}
              {datos?.techo && versiones.length >= datos.techo && (
                <p className="text-[11px] text-tinta-3 mt-2">
                  Se enseñan las {datos.techo} más recientes. Hay más antiguas guardadas.
                </p>
              )}
              <p className="text-[11px] text-tinta-3 mt-2 leading-relaxed max-w-[70ch]">
                Los signos son qué campos entraron y salieron entre una versión y la
                anterior. Es mecánico: no dice si el cambio fue un matiz o un giro.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
