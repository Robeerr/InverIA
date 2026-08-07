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

// Mide la carga de la PROPIA web usando la API de rendimiento del navegador. Es la medida
// que importa: la hace tu navegador, en tu conexión, con tu caché. Compilar el proyecto en
// otro sitio solo diría cuánto PESA, no cuánto TARDAS tú.
function VelocidadWeb() {
  const [d, setD] = React.useState(null);

  const medir = () => {
    const recursos = performance.getEntriesByType("resource");
    const nav = performance.getEntriesByType("navigation")[0];
    const porTipo = {};
    let total = 0, sinComprimir = 0;
    for (const r of recursos) {
      // transferSize = lo que viajó por la red (0 si vino de caché).
      const tipo = r.name.match(/\.js(\?|$)/) ? "JavaScript"
        : r.name.match(/\.css(\?|$)/) ? "CSS"
        : r.name.match(/fonts?\.|\.woff/) ? "Tipografías"
        : r.initiatorType === "fetch" || r.initiatorType === "xmlhttprequest" ? "Datos (API)"
        : "Otros";
      porTipo[tipo] = porTipo[tipo] || { n: 0, kb: 0, ms: 0 };
      porTipo[tipo].n++;
      porTipo[tipo].kb += (r.transferSize || 0) / 1024;
      porTipo[tipo].ms = Math.max(porTipo[tipo].ms, Math.round(r.duration));
      total += (r.transferSize || 0);
      sinComprimir += (r.decodedBodySize || 0);
    }
    setD({
      recursos: recursos.length,
      totalKb: Math.round(total / 1024),
      sinComprimirKb: Math.round(sinComprimir / 1024),
      porTipo: Object.entries(porTipo).sort((a, b) => b[1].kb - a[1].kb),
      cargaMs: nav ? Math.round(nav.duration) : null,
      hastaInteractivo: nav ? Math.round(nav.domInteractive) : null,
    });
  };

  return (
    <section className="card-flat p-5">
      <h2 className="font-heading font-semibold text-lg text-[#0e1f1a]">Velocidad de la web</h2>
      <p className="text-xs text-[#5c6b66] mt-1 mb-3">
        Lo mide tu navegador, en tu conexión. <b>Mide lo que se haya cargado en ESTA visita</b>,
        así que para ver el peso del Dashboard: entra en el Dashboard, abre una acción, y
        luego ven aquí <b>sin recargar</b> (por el menú) y pulsa Medir. Si recargas estando
        en esta página solo medirás esta página, que es de las ligeras.
      </p>
      <button onClick={medir}
              className="bg-[#1a3a32] text-[#f5f3ef] rounded px-4 py-1.5 text-sm font-semibold">
        Medir esta página
      </button>
      {d && (
        <div className="mt-3">
          <p className="text-sm mb-2">
            Descargado: <b className="font-mono">{d.totalKb} KB</b> en {d.recursos} ficheros
            {d.cargaMs != null && <> · carga total <b className="font-mono">{d.cargaMs} ms</b></>}
          </p>
          <table className="w-full text-xs">
            <thead><tr className="text-left text-[#5c6b66] border-b border-[#e5e0d8]">
              <th className="py-1">Tipo</th><th className="text-right">Ficheros</th>
              <th className="text-right">KB</th><th className="text-right">El más lento (ms)</th>
            </tr></thead>
            <tbody>
              {d.porTipo.map(([t, v]) => (
                <tr key={t} className="border-b border-[#f0ebe1]">
                  <td className="py-1">{t}</td>
                  <td className="text-right font-mono">{v.n}</td>
                  <td className="text-right font-mono font-semibold">{Math.round(v.kb)}</td>
                  <td className="text-right font-mono">{v.ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[11px] text-[#5c6b66] mt-2 leading-snug">
            Referencia: por debajo de 1.000 KB de JavaScript es sano; por encima de 2.000 KB
            la culpa de la lentitud es del tamaño. Si sale 0 KB, vino todo de caché: recarga
            con Ctrl+Shift+R y vuelve a medir.
          </p>
        </div>
      )}
    </section>
  );
}

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

      <VelocidadWeb />

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
            {/* La cifra que contesta a "¿va rápido?". Va la primera y destacada porque el
                "Total" de abajo mide otra cosa —el coste de las fuentes SIN caché— y
                leerlo como si fuera el tiempo de carga lleva a la conclusión contraria:
                todo lo que consiste en dejar de repetir trabajo es invisible ahí. */}
            {carga.experiencia_real && (
              <div className="mb-3 p-3 rounded-md border border-[#e5e0d8] bg-[#faf8f4]">
                <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-1">
                  Lo que tardas tú al elegir esta acción
                </p>
                <p className="text-sm">
                  <b className="font-mono text-2xl">{carga.experiencia_real.ms} ms</b>{" "}
                  <span className={`font-semibold ${tono(
                    carga.experiencia_real.ms < 300 ? "rápido"
                      : carga.experiencia_real.ms < 1500 ? "aceptable" : "LENTO")}`}>
                    · {carga.experiencia_real.ms < 300 ? "instantáneo"
                        : carga.experiencia_real.ms < 1500 ? "rápido" : "lento"}
                  </span>
                </p>
                <p className="text-[11px] text-[#5c6b66] mt-1">{carga.experiencia_real.nota}</p>
              </div>
            )}
            <p className="text-sm mb-2">
              Coste de las fuentes sin caché: <b className="font-mono">{carga.total_ms} ms</b>{" "}
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
            {carga.desglose_cotizacion && (
              <div className="mt-4">
                <p className="text-xs font-semibold text-[#0e1f1a] mb-1">
                  Dentro de la cotización (la lenta)
                  <span className="font-normal text-[#5c6b66]"> · {carga.desglose_cotizacion.rama}</span>
                </p>
                <table className="w-full text-xs">
                  <tbody>
                    {carga.desglose_cotizacion.fases.map((f) => (
                      <tr key={f.fase} className="border-b border-[#f0ebe1]">
                        <td className="py-1">{f.fase}</td>
                        <td className="text-right font-mono font-semibold w-16">{f.ms}</td>
                        <td className="pl-3 text-[#5c6b66]">{f.estado}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {carga.paneles_al_cambiar_de_accion && (
              <div className="mt-4">
                <p className="text-xs font-semibold text-[#0e1f1a] mb-1">
                  Paneles que se cargan solos al cambiar de acción
                  <span className="font-normal text-[#5c6b66]"> · suman {carga.total_paneles_ms} ms</span>
                </p>
                <table className="w-full text-xs">
                  <tbody>
                    {carga.paneles_al_cambiar_de_accion.map((f) => (
                      <tr key={f.fuente} className="border-b border-[#f0ebe1]">
                        <td className="py-1">{f.fuente}</td>
                        <td className="text-right font-mono font-semibold w-16">{f.ms}</td>
                        <td className="pl-3 text-[#5c6b66]">{f.estado}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
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
