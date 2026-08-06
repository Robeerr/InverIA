import React from "react";
import { API } from "../lib/api";

// El API de lib/api.js YA incluye el sufijo /api, así que las rutas van sin él.
const authHeaders = () => {
  const token = localStorage.getItem("inveria_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// Página de diagnóstico. Existe para no tener que pedirle a nadie que pegue código en la
// consola del navegador: Chrome avisa (con razón) de que eso es un vector de estafa, y no
// conviene acostumbrar a saltarse ese aviso.
export default function DiagnosticoView() {
  const [ticker, setTicker] = React.useState("AAPL");
  const [carga, setCarga] = React.useState(null);
  const [estudio, setEstudio] = React.useState(null);
  const [cargando, setCargando] = React.useState(null);
  const [error, setError] = React.useState(null);

  const pedir = async (ruta, set, etiqueta) => {
    setCargando(etiqueta); setError(null);
    try {
      const r = await fetch(`${API}${ruta}`, { headers: authHeaders() });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `Error ${r.status}`);
      set(d);
    } catch (e) { setError(e.message); }
    finally { setCargando(null); }
  };

  const tono = (v) => v === "rápido" ? "text-[#4a7c59]" : v === "LENTO" ? "text-[#d85c41]" : "text-[#c9a14a]";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading font-bold text-2xl text-[#0e1f1a]">Diagnóstico</h1>
        <p className="text-sm text-[#5c6b66] mt-1">
          Mide de dónde viene la lentitud y contrasta la idea del RSI con datos reales.
        </p>
      </div>

      {/* ── Velocidad de carga ── */}
      <section className="card-flat p-5">
        <h2 className="font-heading font-semibold text-lg text-[#0e1f1a]">Velocidad de carga</h2>
        <p className="text-xs text-[#5c6b66] mt-1 mb-3">
          Cronometra cada fuente por separado, sin caché: es el peor caso, el de abrir un
          ticker por primera vez.
        </p>
        <div className="flex gap-2 mb-3">
          <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())}
                 className="border border-[#e5e0d8] rounded px-2 py-1.5 font-mono text-sm w-28" />
          <button onClick={() => pedir(`/diagnostico/carga/${ticker}`, setCarga, "carga")}
                  disabled={cargando === "carga"}
                  className="bg-[#1a3a32] text-[#f5f3ef] rounded px-4 py-1.5 text-sm font-semibold disabled:opacity-60">
            {cargando === "carga" ? "Midiendo…" : "Medir"}
          </button>
        </div>
        {carga && (
          <div>
            <p className="text-sm mb-2">
              Total: <b className="font-mono">{carga.total_ms} ms</b>{" "}
              <span className={`font-semibold ${tono(carga.veredicto)}`}>· {carga.veredicto}</span>
            </p>
            <table className="w-full text-xs">
              <thead><tr className="text-left text-[#5c6b66] border-b border-[#e5e0d8]">
                <th className="py-1">Fuente</th><th className="text-right">ms</th><th className="pl-3">Estado</th>
              </tr></thead>
              <tbody>
                {carga.por_fuente.map((f) => (
                  <tr key={f.fuente} className="border-b border-[#f0ebe1]">
                    <td className="py-1">{f.fuente}</td>
                    <td className="text-right font-mono font-semibold">{f.ms}</td>
                    <td className="pl-3 text-[#5c6b66]">{f.estado}{f.detalle ? ` · ${f.detalle}` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {carga.cuota_finnhub && (
              <p className={`text-xs mt-2 ${carga.cuota_finnhub.saturado ? "text-[#d85c41] font-semibold" : "text-[#5c6b66]"}`}>
                Cuota de datos: {carga.cuota_finnhub.usadas_ultimo_minuto} de{" "}
                {carga.cuota_finnhub.tope_total} en el último minuto ·{" "}
                <b>{carga.cuota_finnhub.libres_para_ti} libres</b> para navegar
                {carga.cuota_finnhub.saturado
                  ? " · SATURADA: esto SÍ te ralentiza"
                  : carga.cuota_finnhub.fondo_frenado
                    ? " · las tareas de fondo van más lentas para dejarte sitio (normal)"
                    : ""}
              </p>
            )}
          </div>
        )}
      </section>

      {/* ── Estudio del RSI ── */}
      <section className="card-flat p-5">
        <h2 className="font-heading font-semibold text-lg text-[#0e1f1a]">
          ¿Sube siempre el S&amp;P tras un RSI por debajo de 30?
        </h2>
        <p className="text-xs text-[#5c6b66] mt-1 mb-3">
          Con datos hasta hoy. Compara con comprar un día cualquiera: si el índice sube el
          70% de las veces igualmente, un 70% tras la señal no demuestra nada.
        </p>
        <button onClick={() => pedir("/estudio/rsi-sobreventa", setEstudio, "estudio")}
                disabled={cargando === "estudio"}
                className="bg-[#1a3a32] text-[#f5f3ef] rounded px-4 py-1.5 text-sm font-semibold disabled:opacity-60">
          {cargando === "estudio" ? "Calculando… (tarda unos segundos)" : "Calcular"}
        </button>
        {estudio && !estudio.error && (
          <div className="mt-3">
            <p className="text-xs text-[#5c6b66] mb-2">
              {estudio.desde} → {estudio.hasta} · {estudio.episodios} episodios
            </p>
            <table className="w-full text-xs">
              <thead><tr className="text-left text-[#5c6b66] border-b border-[#e5e0d8]">
                <th className="py-1">Horizonte</th><th className="text-right">Tras RSI&lt;30</th>
                <th className="text-right">Día cualquiera</th><th className="text-right">Sobre SMA200</th>
                <th className="text-right">Peor caso</th>
              </tr></thead>
              <tbody>
                {Object.keys(estudio.tras_sobreventa).map((h) => (
                  <tr key={h} className="border-b border-[#f0ebe1]">
                    <td className="py-1">{h}</td>
                    <td className="text-right font-mono font-semibold">{estudio.tras_sobreventa[h].subio_pct}%</td>
                    <td className="text-right font-mono text-[#5c6b66]">{estudio.dia_cualquiera[h]?.subio_pct}%</td>
                    <td className="text-right font-mono text-[#4a7c59]">{estudio.sobre_sma200[h]?.subio_pct ?? "—"}%</td>
                    <td className="text-right font-mono text-[#d85c41]">{estudio.tras_sobreventa[h].peor}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {estudio.aviso_independencia && (
              <p className="text-[11px] text-[#5c6b66] mt-2 leading-snug">{estudio.aviso_independencia}</p>
            )}
          </div>
        )}
        {estudio?.error && <p className="text-xs text-[#d85c41] mt-2">{estudio.error}</p>}
      </section>

      {error && <p className="text-sm text-[#d85c41]">{error}</p>}
    </div>
  );
}
