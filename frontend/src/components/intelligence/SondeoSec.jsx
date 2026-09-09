import React, { useState } from "react";
import { Ruler } from "@phosphor-icons/react";
import { api } from "../../lib/api";

/**
 * Sondeo de EDGAR: la medición que decide si vigilamos por CIK.
 *
 * QUÉ SE ESTÁ MIDIENDO
 *
 * Vigilar por CIK significa pedir el historial de cada empresa en cada vuelta. Si esas
 * peticiones devuelven el JSON entero, son ~2,9 GB al día; si devuelven `304 Not
 * Modified`, son 3 MB. Tres órdenes de magnitud, y toda la arquitectura depende de cuál
 * de las dos sea cierta.
 *
 * POR QUÉ ESTÁ EN LA PANTALLA Y NO EN UN LOG
 *
 * Porque la decisión es del usuario, no del código. Enseñar los bytes, las cabeceras y
 * el código HTTP de cada petición permite discutir el diseño mirando lo que pasó, en vez
 * de fiarse de un resumen. Es la misma razón por la que el diagnóstico está a la vista.
 *
 * ESTO NO CAMBIA NADA
 *
 * Seis peticiones de lectura. No escribe en la base de datos, no toca el connector y no
 * altera la vigilancia que está corriendo.
 */
const kb = (b) => (b == null ? "—" : `${(b / 1024).toFixed(1)} kB`);

const VEREDICTOS = {
  APOYA: ["text-sube", "La caché condicional funciona: la vigilancia por CIK es viable."],
  PARCIAL: ["text-aviso", "Funciona solo en parte, y eso no basta."],
  NO_APOYA: ["text-baja", "No hay caché condicional que aprovechar."],
  SIN_DATOS: ["text-tinta-3",
              "Sin cabeceras de caché: es el resultado esperado, no un fallo."],
};

export default function SondeoSec() {
  const [r, setR] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);

  const sondear = async () => {
    setCargando(true);
    setError(null);
    try {
      setR(await api.intelligence.sondeoSec());
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "No se pudo sondear");
    } finally {
      setCargando(false);
    }
  };

  const [clase, frase] = VEREDICTOS[r?.veredicto] || VEREDICTOS.SIN_DATOS;
  const p = r?.proyeccion;

  return (
    <div className="mt-8" data-testid="sondeo-sec">
      <div className="iv-seccion"><span className="iv-etiqueta">Sondeo de EDGAR</span></div>
      <p className="text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
        Seis peticiones a tres empresas de tu cartera. Midió si la SEC responde{" "}
        <span className="iv-cifra">304</span> a una petición condicional:{" "}
        <b className="text-tinta-2">no lo hace</b>, y por eso la vigilancia por CIK no
        implementa caché condicional. Lo que sí midió —22 kB comprimidos por empresa— es
        lo que la hizo viable. Se conserva para poder repetir la medición si algún día
        cambia. No escribe nada.
      </p>

      <button onClick={sondear} disabled={cargando}
              className="mt-3 inline-flex items-center gap-2 border border-linea-fuerte
                         px-3 py-1.5 text-sm text-tinta hover:border-marca
                         disabled:opacity-50">
        <Ruler size={15} />
        {cargando ? "Midiendo…" : "Sondear EDGAR"}
      </button>

      {error && <p className="mt-3 text-sm text-baja" role="alert">{String(error)}</p>}

      {r && (
        <div className="mt-4" data-testid="sondeo-resultado">
          <p className={`text-sm ${clase}`}>
            {r.veredicto} · {frase}
          </p>
          <p className="mt-1 text-xs text-tinta-3">{r.detalle}</p>

          {/* Petición a petición. El resumen se puede discutir; los códigos y los bytes,
              no — y son lo que decide. */}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-xs iv-cifra">
              <thead className="text-tinta-3">
                <tr className="text-left">
                  {["Valor", "1ª", "Recibido", "ETag", "Last-Modified", "2ª", "Recibido", "ms"]
                    .map((h) => <th key={h} className="font-normal pb-2 pr-4">{h}</th>)}
                </tr>
              </thead>
              <tbody className="text-tinta-2">
                {(r.resultados || []).map((f) => (
                  <tr key={f.cik} className="border-t border-linea">
                    <td className="py-2 pr-4 text-tinta font-semibold">{f.symbol}</td>
                    <td className="py-2 pr-4">{f.primera?.http ?? "—"}</td>
                    <td className="py-2 pr-4">{kb(f.primera?.bytes_transferidos)}</td>
                    <td className="py-2 pr-4">{f.primera?.cache?.etag ? "sí" : "no"}</td>
                    <td className="py-2 pr-4">{f.primera?.cache?.last_modified ? "sí" : "no"}</td>
                    <td className={`py-2 pr-4 ${f.segunda?.http === 304 ? "text-sube" : "text-baja"}`}>
                      {f.segunda?.http ?? "—"}
                    </td>
                    <td className="py-2 pr-4">{kb(f.segunda?.bytes_transferidos)}</td>
                    <td className="py-2 pr-4">
                      {f.primera?.ms ?? "—"} / {f.segunda?.ms ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {(r.resultados || []).filter((f) => f.error).map((f) => (
            <p key={f.cik} className="mt-2 text-xs text-baja">{f.symbol}: {f.error}</p>
          ))}

          {/* Los dos escenarios, con los bytes medidos. El de «sin condicional» se enseña
              siempre: es el que hay que mirar si la medición sale mal. */}
          {p && (
            <div className="mt-5">
              <p className="iv-etiqueta mb-2">
                Tráfico proyectado · {p.supuestos.en_cartera} en cartera cada{" "}
                {p.supuestos.cada_cartera_min} min, {p.supuestos.en_watchlist} en
                seguimiento cada {p.supuestos.cada_watchlist_min} min
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[["Peticiones/día", p.peticiones_por_dia],
                  ["% del límite SEC", `${p.porcentaje_del_limite_sec} %`],
                  ["MB/día con 304", p.mb_dia_con_condicional ?? "—"],
                  ["MB/día sin 304", p.mb_dia_sin_condicional ?? "—"]].map(([t, v], i) => (
                  <div key={t} className={i === 3 ? "border-l border-linea-fuerte pl-3" : ""}>
                    <p className="iv-cifra text-xl text-tinta">{v}</p>
                    <p className="iv-etiqueta">{t}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {r.sin_cik_en_cartera?.length > 0 && (
            <p className="mt-4 text-xs text-aviso max-w-[70ch] leading-relaxed">
              El mapa actual no resuelve a CIK: {r.sin_cik_en_cartera.join(", ")}. OJO:
              esto NO significa que no estén en la SEC. La auditoría de la tabla, más
              abajo, distingue las dos cosas — y en la medición real resultó que sí
              estaban, y que los perdía nuestro propio mapa.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
