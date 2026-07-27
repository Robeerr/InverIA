import React, { useState, useEffect } from "react";
import { Lightning, Sparkle, Newspaper } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { fmtPct } from "../lib/format";

const VERDICT = {
  SUBE: { text: "text-[#4a7c59]", bg: "bg-[#4a7c59]/10", label: "Sube hoy" },
  BAJA: { text: "text-[#d85c41]", bg: "bg-[#d85c41]/10", label: "Baja hoy" },
  PLANO: { text: "text-[#5c6b66]", bg: "bg-[#5c6b66]/10", label: "Plano hoy" },
};

const RELIABILITY = {
  ALTA: { text: "text-[#4a7c59]", label: "Fiabilidad alta" },
  MEDIA: { text: "text-[#c9a14a]", label: "Fiabilidad media" },
  BAJA: { text: "text-[#d85c41]", label: "Fiabilidad baja" },
};

const MOVE_TYPE = {
  ESPECÍFICO_EMPRESA: "Noticia propia de la empresa",
  SECTOR_MERCADO: "Arrastre del sector / mercado",
  MIXTO: "Empresa + mercado",
  SIN_CATALIZADOR_CLARO: "Sin catalizador claro (movimiento técnico)",
};

export default function WhyMovingCard({ symbol, model, runSignal }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);

  // Al cambiar de acción, limpiar: si no, seguías leyendo la explicación de la acción
  // ANTERIOR bajo el ticker nuevo. (No usamos key={symbol} a propósito: remontar dispararía
  // el efecto de runSignal y gastaría una llamada de IA sin que la pidas.)
  useEffect(() => {
    setData(null);
    setLoading(false);
  }, [symbol]);

  // Disparo externo desde el botón "Análisis completo" del Dashboard.
  useEffect(() => {
    if (runSignal && !loading) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runSignal]);

  const run = async () => {
    if (!symbol) return;
    setLoading(true);
    try {
      const res = await api.whyMoving(symbol, model);
      setData(res);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "No se pudo explicar el movimiento");
    } finally {
      setLoading(false);
    }
  };

  const exp = data?.explanation;
  const verdict = exp ? VERDICT[(exp.veredicto || "PLANO").toUpperCase()] || VERDICT.PLANO : null;
  const rel = exp ? RELIABILITY[(exp.fiabilidad || "MEDIA").toUpperCase()] || RELIABILITY.MEDIA : null;
  const pct = data?.change_percent;

  return (
    <section data-testid="why-moving" className="card-flat p-6 animate-fade-up">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Lightning size={18} weight="bold" className="text-[#1a3a32]" />
          <h3 className="font-heading font-semibold text-lg text-[#0e1f1a]">¿Por qué se mueve hoy?</h3>
        </div>
        <button
          data-testid="why-moving-btn"
          onClick={run}
          disabled={loading || !symbol}
          className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-md bg-[#1a3a32] text-[#f5f3ef] hover:bg-[#24514695] disabled:opacity-50 transition-colors"
        >
          <Sparkle size={14} weight="bold" />
          {loading ? "Analizando…" : data ? "Actualizar" : "Explicar movimiento"}
        </button>
      </div>

      {!data && !loading && (
        <p className="text-sm text-[#5c6b66] mt-3">
          La IA conecta el movimiento de hoy de <span className="font-mono font-semibold text-[#0e1f1a]">{symbol}</span> con las
          noticias recientes y te dice, en segundos, qué hay detrás de la subida o caída.
        </p>
      )}

      {loading && (
        <p className="text-sm text-[#5c6b66] mt-4 animate-pulse">Leyendo noticias y conectando con el precio…</p>
      )}

      {data && exp && (
        <div className="mt-4 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${verdict.bg} ${verdict.text}`}>
              {verdict.label}
            </span>
            {pct != null && (
              <span className={`font-mono text-sm font-semibold ${pct >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]"}`}>
                {pct >= 0 ? "+" : ""}{fmtPct(pct)}
              </span>
            )}
            {rel && <span className={`text-[11px] font-medium ${rel.text}`}>· {rel.label}</span>}
          </div>

          {exp.titular && (
            <p className="font-heading font-semibold text-base text-[#0e1f1a] leading-snug">{exp.titular}</p>
          )}

          {exp.resumen && (
            <p className="text-sm text-[#3a4a44] leading-relaxed border-l-2 border-[#1a3a32] pl-3">{exp.resumen}</p>
          )}

          {Array.isArray(exp.factores) && exp.factores.length > 0 && (
            <ul className="space-y-1.5">
              {exp.factores.filter(Boolean).map((f, i) => (
                <li key={i} className="text-sm text-[#3a4a44] flex gap-2">
                  <span className="text-[#1a3a32] font-bold shrink-0">·</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
            {exp.tipo_movimiento && (
              <span className="text-[11px] text-[#5c6b66]">
                {MOVE_TYPE[(exp.tipo_movimiento || "").toUpperCase()] || exp.tipo_movimiento}
              </span>
            )}
            {data.model && (
              <span className="text-[10px] uppercase tracking-wider text-[#9aa39f] font-mono">
                {data.model}{data.fellback ? " (fallback)" : ""}
              </span>
            )}
          </div>

          {Array.isArray(data.news) && data.news.length > 0 && (
            <div className="pt-2 border-t border-[#e5e0d8]">
              <p className="label-small flex items-center gap-1 mb-2">
                <Newspaper size={12} /> Noticias usadas
              </p>
              <ul className="space-y-1">
                {data.news.slice(0, 3).map((n, i) => (
                  <li key={i} className="text-xs text-[#5c6b66] truncate">
                    {n.url ? (
                      <a href={n.url} target="_blank" rel="noopener noreferrer" className="hover:text-[#1a3a32] hover:underline">
                        {n.title}
                      </a>
                    ) : (
                      n.title
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
