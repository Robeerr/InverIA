import React, { useState } from "react";
import { Pulse } from "@phosphor-icons/react";
import { api } from "../../lib/api";
import { MOTIVOS } from "../../lib/intelligence";
import { fmtDateTime } from "../../lib/format";

/**
 * «Comprobar ahora»: la prueba de vida de la cadena SEC → evento → Mongo.
 *
 * POR QUÉ HACE FALTA UN BOTÓN HABIENDO UN BUCLE
 *
 * Porque «espera cinco minutos y mira si ha cambiado algo» no es una verificación. Si al
 * volver el radar sigue vacío, no sabes cuál de estas tres cosas ha pasado:
 *
 *   · la fuente no ha contestado,
 *   · el filtro se lo ha comido todo,
 *   · no había novedades.
 *
 * Las tres se ven exactamente igual. Esto ejecuta una vuelta AHORA y enseña los seis
 * pasos con sus números, que es lo único que las distingue.
 *
 * «YA CONOCIDO» NO ES «DESCARTADO»
 *
 * Van en casillas separadas a propósito. Un documento que ya teníamos no es un evento
 * irrelevante: simplemente no es nuevo. Y como el feed de la SEC devuelve los mismos
 * registros cada pocos minutos, en régimen normal casi todo lo que se lee ya lo teníamos
 * — sumarlo a los descartes daría una tasa de descarte altísima y parecería un filtro
 * fuera de control, justo cuando lo que demuestra es que la deduplicación funciona.
 *
 * EL ÚLTIMO NÚMERO ES EL QUE CIERRA LA CADENA
 *
 * «Guardados únicos» no lo dice el ciclo: se cuenta en la colección. Que el proceso afirme
 * haber escrito tres eventos y que la colección tenga tres documentos son dos afirmaciones
 * distintas, y solo la segunda demuestra que la cadena llega al final.
 */
export default function PruebaDeVida({ alTerminar }) {
  const [r, setR] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);

  const comprobar = async () => {
    setCargando(true);
    setError(null);
    try {
      const res = await api.intelligence.comprobar();
      setR(res);
      if (alTerminar) alTerminar();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "No se pudo comprobar");
    } finally {
      setCargando(false);
    }
  };

  const c = r?.cadena;
  // Los seis pasos, en el orden en que ocurren. «Ya conocidos» va inmediatamente después
  // de los recibidos porque es ahí donde se van: la deduplicación es lo PRIMERO que pasa,
  // antes que el filtro. Ponerlo junto a los descartados sugeriría que los tira el filtro.
  const pasos = c ? [
    ["Recibidos", c.leidos_de_la_fuente],
    ["Ya conocidos", c.ya_conocidos],
    ["Nuevos", c.nuevos_tras_deduplicar],
    ["Descartados por filtro", c.descartados_al_filtrar],
    ["Te afectan", c.significativos],
    ["Guardados únicos", r?.guardados_unicos],
  ] : [];

  return (
    <div className="mt-6" data-testid="prueba-de-vida">
      <button onClick={comprobar} disabled={cargando}
              className="inline-flex items-center gap-2 border border-linea-fuerte px-3 py-1.5
                         text-sm text-tinta hover:border-marca disabled:opacity-50">
        <Pulse size={15} />
        {cargando ? "Preguntando a la SEC…" : "Comprobar ahora"}
      </button>
      <p className="mt-2 text-xs text-tinta-3 max-w-[62ch] leading-relaxed">
        Fuerza una vuelta y enseña por dónde va cada evento. Es el mismo ciclo que corre
        solo cada cinco minutos, no una versión de prueba.
      </p>

      {error && <p className="mt-3 text-sm text-baja" role="alert">{String(error)}</p>}

      {r && (
        <div className="mt-4" data-testid="prueba-resultado">
          {r.estado === "ONLINE" ? (
            <p className="text-sm text-sube">La SEC ha contestado.</p>
          ) : (
            <p className="text-sm text-baja">
              {r.estado === "NO_CONFIGURADA"
                ? "SEC_USER_AGENT no está configurada, así que no se ha hecho ninguna petición."
                : `La SEC no ha contestado bien: ${r.error || r.estado}`}
            </p>
          )}

          {/* Leerlos de izquierda a derecha es leer la cadena entera. */}
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {pasos.map(([etiqueta, n], i) => (
              <div key={etiqueta}
                   className={i === pasos.length - 1 ? "border-l border-marca pl-3" : ""}>
                <p className="iv-cifra text-xl text-tinta">{n}</p>
                <p className="iv-etiqueta">{etiqueta}</p>
              </div>
            ))}
          </div>

          <p className="mt-3 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
            <b className="text-tinta-2">Ya conocidos</b> no son descartes: son documentos
            que ya teníamos. El feed devuelve los mismos registros cada pocos minutos, así
            que este número alto significa que la deduplicación funciona.{" "}
            <b className="text-tinta-2">Guardados únicos</b> son documentos que existen en
            la base de datos, contados en la colección — no operaciones de escritura.
          </p>

          {Object.keys(r.por_motivo || {}).length > 0 && (
            <ul className="mt-3 text-xs text-tinta-3 space-y-0.5">
              {Object.entries(r.por_motivo).map(([m, n]) => (
                <li key={m}>{MOTIVOS[m] || m}: <span className="iv-cifra">{n}</span></li>
              ))}
            </ul>
          )}

          {/* El acumulado del periodo de prueba. Es lo que convierte una comprobación
              puntual en evidencia de que lleva días funcionando. */}
          {r.acumulado?.ciclos > 0 && (
            <p className="mt-4 text-xs text-tinta-3 leading-relaxed max-w-[70ch]">
              Desde {fmtDateTime(r.acumulado.desde)}:{" "}
              <span className="iv-cifra text-tinta-2">{r.acumulado.ciclos}</span> vueltas
              {r.acumulado.fallos > 0 && <> (<span className="iv-cifra text-baja">{r.acumulado.fallos}</span> fallidas)</>},{" "}
              <span className="iv-cifra text-tinta-2">{r.acumulado.recibidos}</span> leídos,{" "}
              <span className="iv-cifra text-tinta-2">{r.acumulado.repetidos}</span> ya conocidos,{" "}
              <span className="iv-cifra text-tinta-2">{r.acumulado.descartados}</span> descartados
              por el filtro.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
