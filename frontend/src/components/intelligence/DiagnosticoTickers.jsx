import React, { useState } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { api } from "../../lib/api";

/**
 * La tabla que traduce tus símbolos a empresas de la SEC, auditada.
 *
 * EL FALLO QUE BUSCA
 *
 * El fichero de la SEC trae una fila POR TICKER, y una empresa puede tener varias clases
 * de acción: Alphabet aparece como GOOGL y como GOOG con el mismo CIK. El mapa que se
 * construye hoy va de CIK a ticker, así que la segunda fila PISA a la primera y el ticker
 * perdedor deja de existir para el sistema.
 *
 * La consecuencia no es teórica: un 8-K de esa empresa se etiqueta con el ticker que ganó,
 * y si el tuyo es el otro, el pipeline lo descarta como «no es un valor tuyo». Un registro
 * de una empresa de tu cartera, tirado en silencio.
 *
 * YA ESTÁ ARREGLADO, Y ESTE PANEL TIENE QUE DECIRLO
 *
 * El mapa vigente es `{TICKER: cik}` y no pierde nada. Este panel se escribió cuando el
 * mapa sí perdía, y evaluaba contra él: si se hubiera dejado así, seguiría diciendo que
 * los registros de GOOGL «se están descartando ahora mismo» mientras entran por decenas.
 *
 * Ahora informa de DOS cosas separadas:
 *
 *   AHORA  · se resuelve, o no está en la SEC. No hay tercer estado.
 *   ANTES  · qué perdía el mapa colapsado — la medida de lo que arregló la migración.
 */
export default function DiagnosticoTickers() {
  const [r, setR] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);
  const [verTodos, setVerTodos] = useState(false);

  const mirar = async () => {
    setCargando(true);
    setError(null);
    try {
      setR(await api.intelligence.tickersSec());
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "No se pudo leer la tabla");
    } finally {
      setCargando(false);
    }
  };

  const u = r?.universo;
  const casos = r?.casos_multiples || [];
  const visibles = verTodos ? casos : casos.slice(0, 12);

  return (
    <div className="mt-8" data-testid="diagnostico-tickers">
      <div className="iv-seccion"><span className="iv-etiqueta">Tabla ticker ↔ CIK</span></div>
      <p className="text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
        Una petición al fichero de tickers de la SEC para auditar cómo traducimos tus
        símbolos a empresas. Las filas se resumen y se tiran; no se guarda nada.
      </p>

      <button onClick={mirar} disabled={cargando}
              className="mt-3 inline-flex items-center gap-2 border border-linea-fuerte
                         px-3 py-1.5 text-sm text-tinta hover:border-marca
                         disabled:opacity-50">
        <MagnifyingGlass size={15} />
        {cargando ? "Leyendo…" : "Auditar la tabla"}
      </button>

      {error && <p className="mt-3 text-sm text-baja" role="alert">{String(error)}</p>}

      {r && (
        <div className="mt-4" data-testid="tickers-resultado">
          <p className={`text-sm ${r.veredicto === "A" ? "text-sube" : "text-alerta"}`}>
            {r.veredicto} · {r.titulo}
          </p>
          <p className="mt-1 text-xs text-tinta-3 max-w-[70ch]">{r.detalle}</p>

          <div className="mt-4 grid grid-cols-2 sm:grid-cols-5 gap-3">
            {[["Filas", r.total_filas], ["CIK distintos", r.ciks_distintos],
              ["Tickers", r.tickers_distintos],
              ["CIK con varias clases", r.ciks_con_varios_tickers],
              ["Perdía el mapa viejo", r.tickers_que_perdia_el_mapa_viejo]].map(([t, v], i) => (
              <div key={t} className={i === 4 ? "border-l border-linea-fuerte pl-3" : ""}>
                <p className="iv-cifra text-xl text-tinta">{v}</p>
                <p className="iv-etiqueta">{t}</p>
              </div>
            ))}
          </div>

          {/* Tu universo, con el mapa VIGENTE. Dos estados, no tres. */}
          {u && (
            <div className="mt-6">
              <p className="iv-etiqueta mb-2">Tus {u.revisados} valores, ahora</p>
              <ul className="text-sm space-y-1">
                <li className="flex justify-between gap-3">
                  <span className="text-sube">Se resuelven a un CIK</span>
                  <span className="iv-cifra text-tinta-2">{u.resueltos.length}</span>
                </li>
                <li className="flex justify-between gap-3">
                  <span className="text-tinta-3">Sin CIK en la SEC</span>
                  <span className="iv-cifra text-tinta-2">{u.sin_cik_en_la_sec.length}</span>
                </li>
              </ul>
              {u.los_recuperaba_la_migracion?.length > 0 && (
                <p className="mt-2 text-xs text-sube max-w-[70ch] leading-relaxed">
                  {u.los_recuperaba_la_migracion.join(", ")} — los perdía el mapa anterior
                  y ahora entran. Es lo que arregló la migración, medido.
                </p>
              )}
              {u.sin_cik_en_la_sec.length > 0 && (
                <p className="mt-2 text-xs text-tinta-3 max-w-[70ch] leading-relaxed">
                  {u.sin_cik_en_la_sec.join(", ")} — no están en el fichero de la SEC. No
                  lo arregla ningún mapa; simplemente no registran en EDGAR.
                </p>
              )}
            </div>
          )}

          {/* Las consultas concretas, con el recorrido entero de cada ticker. */}
          {(r.consultas || []).length > 0 && (
            <div className="mt-6 overflow-x-auto">
              <p className="iv-etiqueta mb-2">Recorrido, ticker a ticker</p>
              <table className="w-full text-xs iv-cifra">
                <thead className="text-tinta-3">
                  <tr className="text-left">
                    {["Ticker", "¿En la SEC?", "CIK", "Tickers de ese CIK",
                      "El mapa viejo guardaba", "¿Se alcanza ahora?"].map((h) => (
                      <th key={h} className="font-normal pb-2 pr-4">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="text-tinta-2">
                  {r.consultas.map((f) => (
                    <tr key={f.ticker} className="border-t border-linea">
                      <td className="py-2 pr-4 text-tinta font-semibold">{f.ticker}</td>
                      <td className="py-2 pr-4">{f.existe_en_la_fuente ? "sí" : "no"}</td>
                      <td className="py-2 pr-4">{f.cik ?? "—"}</td>
                      <td className="py-2 pr-4">{f.tickers_de_ese_cik.join(", ") || "—"}</td>
                      <td className="py-2 pr-4">{f.el_mapa_viejo_guardaba ?? "—"}</td>
                      <td className={`py-2 pr-4 ${f.alcanzable_ahora ? "text-sube" : "text-tinta-3"}`}>
                        {f.alcanzable_ahora ? "sí" : "no está en la SEC"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Todos los CIK con varias clases. Se recorta por defecto porque pueden ser
              cientos, pero el listado completo está a un clic: es la evidencia. */}
          {casos.length > 0 && (
            <div className="mt-6">
              <p className="iv-etiqueta mb-2">
                CIK con varias clases de acción ({casos.length}) · lo que guardaba el
                mapa viejo
              </p>
              <ul className="text-xs iv-cifra text-tinta-2 space-y-0.5 max-h-72 overflow-y-auto">
                {visibles.map((c) => (
                  <li key={c.cik}>
                    {c.cik} · {c.tickers.join(", ")}{" "}
                    <span className="text-tinta-3">→ el mapa guarda {c.gana_hoy}</span>
                  </li>
                ))}
              </ul>
              {casos.length > visibles.length && (
                <button onClick={() => setVerTodos(true)}
                        className="mt-2 text-xs text-marca hover:underline">
                  Ver los {casos.length}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
