import React, { useState } from "react";
import { Eye } from "@phosphor-icons/react";
import { api } from "../../lib/api";
import { nivelDe } from "../../lib/intelligence";
import { fmtHace } from "../../lib/format";

/**
 * Qué se investigaría si se encendiera la fase de IA. Sin encenderla.
 *
 * POR QUÉ ESTA PANTALLA EXISTE ANTES QUE LA FASE
 *
 * La investigación cuesta dinero y llamadas a un modelo. Un presupuesto que solo se puede
 * comprobar gastándolo no es un presupuesto — así que primero se enseña, sobre los datos
 * REALES de producción, cuántos eventos entrarían, cuáles y en qué orden.
 *
 * NO descarga documentos, NO llama a ningún modelo, NO consume cuota y NO cambia la etapa
 * de nada. Es una lectura de la colección y unas cuentas.
 *
 * LOS CINCO ESTADOS NO SON DECORATIVOS
 *
 * Son cinco porque la etapa sola no distingue lo que hay que distinguir: «investigado»
 * cubre tanto «se leyó y no decía nada» como «se leyó y esto es lo que dice», y
 * «significativo» cubre «pendiente» y «no investigable». Sin separarlos, un radar en
 * silencio no se puede leer.
 */
const ESTADOS = {
  descartado_por_filtro: ["Descartado por el filtro", "text-tinta-3",
                          "No es un valor tuyo. Se guarda para poder auditar el filtro."],
  no_investigable: ["No investigable", "text-tinta-3",
                    "Es tuyo, pero no pasa la puerta: no interrumpe, o no tiene enlace al documento."],
  pendiente_de_investigacion: ["Pendiente de investigación", "text-aviso",
                               "Merece que se gasten recursos en entenderlo y todavía no se ha leído."],
  investigado_sin_informacion: ["Investigado · sin información", "text-info",
                                "La IA leyó el documento y no permitía concluir nada. Sigue sin resumen, a propósito."],
  investigado_con_informacion: ["Investigado · con información", "text-sube",
                                "La IA leyó el documento y produjo una lectura válida."],
};

const ORDEN_NIVELES = ["CRITICAL", "IMPORTANT", "WATCH", "INFO"];

function Lista({ titulo, eventos, nota }) {
  if (!eventos?.length) return null;
  return (
    <div className="mt-5">
      <p className="iv-etiqueta mb-1">{titulo}</p>
      {nota && <p className="text-xs text-tinta-3 mb-2 max-w-[70ch]">{nota}</p>}
      <ol className="divide-y divide-linea">
        {eventos.map((e, i) => {
          const n = nivelDe(e);
          return (
            <li key={e.id} className="py-2 flex items-baseline gap-3">
              <span className="iv-cifra text-xs text-tinta-3 w-6 shrink-0">{i + 1}</span>
              <span className="iv-cifra text-sm font-semibold text-tinta w-16 shrink-0 truncate">
                {e.symbol || "—"}
              </span>
              <span className="flex-1 min-w-0 text-sm text-tinta-2 truncate">{e.titulo}</span>
              <span className="hidden md:inline iv-cifra text-xs text-tinta-3 shrink-0">
                {e.relevancia}/100
              </span>
              <span className="hidden lg:inline text-xs text-tinta-3 shrink-0">
                {e.afecta_cartera ? "cartera" : "seguimiento"}
              </span>
              <span className="hidden md:inline text-xs text-tinta-3 shrink-0 whitespace-nowrap">
                {fmtHace(e.recibido_en)}
              </span>
              <span className={`iv-etiqueta shrink-0 ${n.clase}`}>{n.etiqueta}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function PlanInvestigacion() {
  const [r, setR] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);

  const mirar = async () => {
    setCargando(true);
    setError(null);
    try {
      setR(await api.intelligence.planInvestigacion());
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "No se pudo calcular el plan");
    } finally {
      setCargando(false);
    }
  };

  const p = r?.presupuesto;

  return (
    <div className="mt-8" data-testid="plan-investigacion">
      <div className="iv-seccion"><span className="iv-etiqueta">Plan de investigación</span></div>
      <p className="text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
        Qué se investigaría con los eventos que hay ahora mismo en la base de datos.{" "}
        <b className="text-tinta-2">No descarga ningún documento, no llama a ningún modelo
        y no cambia el estado de nada.</b> La fase de IA todavía no está encendida.
      </p>

      <button onClick={mirar} disabled={cargando}
              className="mt-3 inline-flex items-center gap-2 border border-linea-fuerte
                         px-3 py-1.5 text-sm text-tinta hover:border-marca
                         disabled:opacity-50">
        <Eye size={15} />
        {cargando ? "Calculando…" : "Ver el plan"}
      </button>

      {error && <p className="mt-3 text-sm text-baja" role="alert">{String(error)}</p>}

      {r && (
        <div className="mt-4" data-testid="plan-resultado">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[["Eventos", r.total_eventos],
              ["Pendientes", r.por_estado.pendiente_de_investigacion],
              ["Entrarían hoy", r.entrarian_en_el_presupuesto],
              ["Quedarían fuera", r.quedarian_pendientes]].map(([t, v], i) => (
              <div key={t} className={i === 2 ? "border-l border-marca pl-3" : ""}>
                <p className="iv-cifra text-xl text-tinta">{v}</p>
                <p className="iv-etiqueta">{t}</p>
              </div>
            ))}
          </div>

          {/* Los cinco estados, cada uno con lo que significa. Un recuento sin la frase
              obliga a recordar qué distingue «no investigable» de «pendiente». */}
          <div className="mt-6">
            <p className="iv-etiqueta mb-2">Los cinco estados</p>
            <ul className="space-y-2">
              {Object.entries(ESTADOS).map(([clave, [nombre, color, explicacion]]) => (
                <li key={clave} className="flex items-baseline justify-between gap-3">
                  <div className="min-w-0">
                    <span className={`text-sm ${color}`}>{nombre}</span>
                    <p className="text-xs text-tinta-3 max-w-[62ch]">{explicacion}</p>
                  </div>
                  <span className="iv-cifra text-sm text-tinta shrink-0">
                    {r.por_estado[clave] ?? 0}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* El reparto por nivel de lo que sigue sin investigar, junto al de lo que pasa
              la puerta. Las dos columnas a la vez son las que enseñan DÓNDE se corta. */}
          <div className="mt-6 overflow-x-auto">
            <p className="iv-etiqueta mb-2">Sin investigar, por nivel</p>
            <table className="w-full text-xs iv-cifra max-w-md">
              <thead className="text-tinta-3">
                <tr className="text-left">
                  <th className="font-normal pb-2 pr-4">Nivel</th>
                  <th className="font-normal pb-2 pr-4">Hay</th>
                  <th className="font-normal pb-2">Pasan la puerta</th>
                </tr>
              </thead>
              <tbody className="text-tinta-2">
                {ORDEN_NIVELES.map((nivel) => {
                  const pasa = (r.niveles_que_pasan_la_puerta || []).includes(nivel);
                  return (
                    <tr key={nivel} className="border-t border-linea">
                      <td className={`py-1.5 pr-4 ${nivelDe({ nivel_alerta: nivel }).clase}`}>
                        {nivelDe({ nivel_alerta: nivel }).etiqueta}
                      </td>
                      <td className="py-1.5 pr-4">{r.sin_investigar_por_nivel?.[nivel] ?? 0}</td>
                      <td className={`py-1.5 ${pasa ? "" : "text-tinta-3"}`}>
                        {pasa ? (r.pendientes_por_nivel?.[nivel] ?? 0) : "no, por diseño"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <Lista titulo="Se investigarían, en este orden"
                 nota="Prioridad: nivel, después score, después cartera antes que seguimiento, y por último lo más reciente."
                 eventos={r.elegidos} />

          <Lista titulo="Quedarían pendientes por presupuesto"
                 nota="No se descartan ni se pierden: siguen en «significativo» y la vuelta siguiente los recoge."
                 eventos={r.pendientes} />

          <p className="mt-5 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
            Calculado con un tope de <span className="iv-cifra">{p?.tope_diario}</span> al
            día y <span className="iv-cifra">{p?.gastadas_hoy}</span> gastadas hoy.{" "}
            {r.contador_diario_implementado === false && (
              <>El contador diario <b className="text-tinta-2">todavía no existe</b>, así
              que «gastadas hoy» es cero por construcción — hoy es correcto, porque no se
              ha investigado nada nunca, pero no es un dato medido.</>
            )}
          </p>
        </div>
      )}
    </div>
  );
}
