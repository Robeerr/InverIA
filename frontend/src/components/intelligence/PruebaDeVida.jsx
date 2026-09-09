import React, { useState } from "react";
import { Pulse } from "@phosphor-icons/react";
import { api } from "../../lib/api";
import { MOTIVOS } from "../../lib/intelligence";
import { fmtDateTime } from "../../lib/format";

/**
 * «Comprobar ahora»: la prueba de vida de la cadena fuente → evento → Mongo.
 *
 * POR QUÉ HACE FALTA UN BOTÓN HABIENDO UN BUCLE
 *
 * Porque «espera y mira si ha cambiado algo» no es una verificación. Si al
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
 * UNA FILA POR FUENTE, SIN SUMAR
 *
 * Con SEC leyendo cada cinco minutos y resultados cada seis horas, un total conjunto
 * estaría dominado por la primera y una caída de la segunda pasaría desapercibida.
 *
 * EL ÚLTIMO NÚMERO ES EL QUE CIERRA LA CADENA
 *
 * «Guardados únicos» no lo dice el ciclo: se cuenta en la colección. Que el proceso afirme
 * haber escrito tres eventos y que la colección tenga tres documentos son dos afirmaciones
 * distintas, y solo la segunda demuestra que la cadena llega al final.
 */
/** Los seis pasos de UNA fuente, en el orden en que ocurren. */
function Fuente({ f }) {
  const c = f.cadena || {};
  // «Ya conocidos» va inmediatamente después de los recibidos porque es ahí donde se van:
  // la deduplicación es lo PRIMERO que pasa, antes que el filtro. Ponerlo junto a los
  // descartados sugeriría que los tira el filtro.
  const pasos = [
    ["Recibidos", c.leidos_de_la_fuente],
    ["Ya conocidos", c.ya_conocidos],
    ["Nuevos", c.nuevos_tras_deduplicar],
    ["Descartados por filtro", c.descartados_al_filtrar],
    ["Te afectan", c.significativos],
    ["Guardados únicos", f.guardados_unicos],
  ];
  const a = f.acumulado || {};

  return (
    <div className="mt-5 pt-4 border-t border-linea first:border-t-0"
         data-testid={`prueba-resultado-${f.fuente}`}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold text-tinta">{f.nombre || f.fuente}</span>
        {f.estado === "ONLINE" ? (
          <span className="iv-etiqueta text-sube">Ha contestado</span>
        ) : (
          <span className="iv-etiqueta text-baja">
            {f.estado === "NO_CONFIGURADA" ? "Sin conectar" : "No ha contestado"}
          </span>
        )}
      </div>

      {f.estado !== "ONLINE" && (
        <p className="mt-1 text-sm text-baja">
          {f.estado === "NO_CONFIGURADA"
            ? "Le falta su variable de entorno, así que no se ha hecho ninguna petición."
            : `${f.error || f.estado}`}
        </p>
      )}

      {/* Leerlos de izquierda a derecha es leer la cadena entera. */}
      <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {pasos.map(([etiqueta, n], i) => (
          <div key={etiqueta}
               className={i === pasos.length - 1 ? "border-l border-marca pl-3" : ""}>
            <p className="iv-cifra text-xl text-tinta">{n ?? 0}</p>
            <p className="iv-etiqueta">{etiqueta}</p>
          </div>
        ))}
      </div>

      {Object.keys(f.por_motivo || {}).length > 0 && (
        <ul className="mt-3 text-xs text-tinta-3 space-y-0.5">
          {Object.entries(f.por_motivo).map(([m, n]) => (
            <li key={m}>{MOTIVOS[m] || m}: <span className="iv-cifra">{n}</span></li>
          ))}
        </ul>
      )}

      {/* El acumulado del periodo de prueba. Es lo que convierte una comprobación
          puntual en evidencia de que lleva días funcionando. */}
      {a.ciclos > 0 && (
        <p className="mt-3 text-xs text-tinta-3 leading-relaxed max-w-[70ch]">
          Desde {fmtDateTime(a.desde)}:{" "}
          <span className="iv-cifra text-tinta-2">{a.ciclos}</span> vueltas
          {a.fallos > 0 && <> (<span className="iv-cifra text-baja">{a.fallos}</span> fallidas)</>},{" "}
          <span className="iv-cifra text-tinta-2">{a.recibidos}</span> leídos,{" "}
          <span className="iv-cifra text-tinta-2">{a.repetidos}</span> ya conocidos,{" "}
          <span className="iv-cifra text-tinta-2">{a.descartados}</span> descartados por
          el filtro.
        </p>
      )}
    </div>
  );
}


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

  const fuentes = r?.fuentes || [];

  return (
    <div className="mt-6" data-testid="prueba-de-vida">
      <button onClick={comprobar} disabled={cargando}
              className="inline-flex items-center gap-2 border border-linea-fuerte px-3 py-1.5
                         text-sm text-tinta hover:border-marca disabled:opacity-50">
        <Pulse size={15} />
        {cargando ? "Preguntando a las fuentes…" : "Comprobar ahora"}
      </button>
      <p className="mt-2 text-xs text-tinta-3 max-w-[62ch] leading-relaxed">
        Fuerza una vuelta de cada fuente y enseña por dónde va cada evento. Es el mismo
        ciclo que corre solo, no una versión de prueba.
      </p>
      {fuentes.length > 0 && (
        <p className="mt-3 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
          <b className="text-tinta-2">Ya conocidos</b> no son descartes: son documentos que
          ya teníamos, y un número alto significa que la deduplicación funciona.{" "}
          <b className="text-tinta-2">Guardados únicos</b> son documentos que existen en la
          base de datos, contados en la colección — no operaciones de escritura.
        </p>
      )}

      {error && <p className="mt-3 text-sm text-baja" role="alert">{String(error)}</p>}

      {fuentes.map((f) => <Fuente key={f.fuente} f={f} />)}
    </div>
  );
}
