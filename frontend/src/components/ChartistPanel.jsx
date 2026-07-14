import React, { useState, useEffect } from "react";
import { api } from "../lib/api";

const SENT_COLOR = {
  alcista: "text-[#1e7a3a] bg-[#e6f4ea]",
  bajista: "text-[#c0392b] bg-[#fbe9e6]",
  neutro: "text-[#5c6b66] bg-[#f0ece3]",
};
const ACCION_COLOR = {
  COMPRAR: "bg-[#1e7a3a] text-white",
  ESPERAR: "bg-[#d9a441] text-[#0e1f1a]",
  EVITAR: "bg-[#c0392b] text-white",
};

// Chartista IA: veredicto técnico multi-timeframe con plan accionable y explicación
// pedagógica (para que el usuario aprenda cuándo entrar y por qué).
export default function ChartistPanel({ symbol }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  // Al cambiar de acción, limpiar el veredicto anterior: vuelve a "Analizar" en vez de
  // dejar el análisis de la acción previa.
  useEffect(() => {
    setData(null);
    setErr(null);
    setLoading(false);
  }, [symbol]);

  async function run(refresh = false) {
    setLoading(true);
    setErr(null);
    try {
      const d = await api.chartist(symbol, refresh);
      setData(d);
    } catch (e) {
      setErr(e?.response?.data?.detail || "No se pudo generar el veredicto. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  const plan = data?.plan;

  return (
    <div className="card-flat p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-semibold text-[#0e1f1a]">🎯 Chartista IA</span>
        {data?.sentido && (
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${SENT_COLOR[data.sentido] || SENT_COLOR.neutro}`}>
            {data.sentido.toUpperCase()}
          </span>
        )}
        <button
          onClick={() => run(!!data)}
          disabled={loading}
          className="ml-auto px-2.5 py-1 rounded text-[11px] font-mono font-semibold bg-[#1a3a32] text-white disabled:opacity-50"
        >
          {loading ? "Analizando…" : data ? "Recalcular" : "Analizar"}
        </button>
      </div>

      {!data && !loading && !err && (
        <p className="text-[11px] text-[#5c6b66]">
          Lee los timeframes 15M → 1S, identifica el patrón y te da un veredicto con plan de
          entrada, invalidación y el porqué — para que aprendas a leerlo tú.
        </p>
      )}
      {loading && <p className="text-[11px] text-[#5c6b66]">Leyendo velas de todos los timeframes y consultando al cerebro… (~20-40s)</p>}
      {err && <p className="text-[11px] text-[#c0392b]">{err}</p>}

      {data && (
        <div className="space-y-3">
          {/* Patrón principal */}
          {data.patron_principal && (
            <div className="text-[12px] text-[#0e1f1a]">
              <b>Patrón que manda:</b> {data.patron_principal}
            </div>
          )}

          {/* Lectura por timeframe */}
          {Array.isArray(data.por_timeframe) && data.por_timeframe.length > 0 && (
            <div className="space-y-1">
              {data.por_timeframe.map((t, i) => (
                <div key={i} className="flex gap-2 text-[11px]">
                  <span className="font-mono font-semibold text-[#1a3a32] w-10 shrink-0">{t.tf}</span>
                  <span className="text-[#5c6b66]">{t.lectura}</span>
                </div>
              ))}
            </div>
          )}

          {/* Veredicto */}
          {data.veredicto && (
            <div className="text-[12px] border border-[#e5e0d8] rounded p-2 leading-snug">
              {data.veredicto}
            </div>
          )}

          {/* Plan accionable */}
          {plan && (
            <div className="border border-[#e5e0d8] rounded p-2.5 space-y-2">
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold ${ACCION_COLOR[plan.accion] || ACCION_COLOR.ESPERAR}`}>
                  {plan.accion || "ESPERAR"}
                </span>
                {plan.gatillo && <span className="text-[11px] text-[#0e1f1a] font-medium">{plan.gatillo}</span>}
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <Lvl label="Entrada" val={plan.entrada} color="#1e7a3a" />
                <Lvl label="Invalidación" val={plan.invalidacion} color="#c0392b" />
                <Lvl label="Objetivo" val={plan.objetivo} color="#2563eb" />
              </div>
              {plan.por_que && (
                <p className="text-[11px] text-[#5c6b66] leading-snug"><b className="text-[#0e1f1a]">Por qué:</b> {plan.por_que}</p>
              )}
            </div>
          )}

          {/* Enseñanza */}
          {data.para_aprender && (
            <div className="text-[11px] text-[#5c6b66] flex gap-1.5">
              <span>🎓</span>
              <span><b className="text-[#0e1f1a]">Para aprender:</b> {data.para_aprender}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Lvl({ label, val, color }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wide text-[#8a958f]">{label}</div>
      <div className="text-[13px] font-mono font-bold" style={{ color: val != null ? color : "#b8b8b8" }}>
        {val != null ? `$${Number(val).toFixed(2)}` : "—"}
      </div>
    </div>
  );
}
