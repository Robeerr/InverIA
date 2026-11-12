import React, { useState, useEffect } from "react";
import { Lightning, Sparkle, Newspaper } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { fmtPct } from "../lib/format";
import { botonVariants } from "./base/Boton";

const VERDICT = {
  SUBE: { text: "text-sube", bg: "bg-sube/10", label: "Sube hoy" },
  BAJA: { text: "text-baja", bg: "bg-baja/10", label: "Baja hoy" },
  PLANO: { text: "text-tinta-3", bg: "bg-tinta-3/10", label: "Plano hoy" },
};

const RELIABILITY = {
  ALTA: { text: "text-sube", label: "Fiabilidad alta" },
  MEDIA: { text: "text-aviso", label: "Fiabilidad media" },
  BAJA: { text: "text-baja", label: "Fiabilidad baja" },
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
    <section data-testid="why-moving" className="iv-panel p-5" aria-busy={loading}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h3 className="text-[15px] font-semibold tracking-[-0.015em] text-tinta flex items-center gap-2.5">
          <span className="w-8 h-8 rounded-[9px] bg-marca/10 text-marca inline-flex items-center justify-center shrink-0">
            <Lightning size={16} weight="bold" aria-hidden="true" />
          </span>
          ¿Por qué se mueve hoy?
        </h3>
        {/* Botón secundario de contorno, igual que el del Chartista: en esta sección el
            único botón relleno es «Generar análisis». Tres naranjas sólidos seguidos no
            dejaban saber cuál era el principal. */}
        <button
          data-testid="why-moving-btn"
          onClick={run}
          disabled={loading || !symbol}
          className={botonVariants({ variante: "secundario", tamano: "sm" })}
        >
          <Sparkle size={14} weight="bold" className="text-marca" aria-hidden="true" />
          {loading ? "Analizando…" : data ? "Actualizar" : "Explicar movimiento"}
        </button>
      </div>

      {!data && !loading && (
        <p className="text-[13.5px] text-tinta-3 mt-3 max-w-[68ch] leading-relaxed">
          La IA conecta el movimiento de hoy de <span className="font-semibold text-tinta">{symbol}</span> con las
          noticias recientes y te dice, en segundos, qué hay detrás de la subida o caída.
        </p>
      )}

      {loading && (
        <p className="text-apoyo text-tinta-3 mt-3 animate-pulse motion-reduce:animate-none" role="status">Leyendo noticias y conectando con el precio…</p>
      )}

      {data && exp && (
        <div className="mt-4 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${verdict.bg} ${verdict.text}`}>
              {verdict.label}
            </span>
            {pct != null && (
              <span className={`iv-cifra text-apoyo font-semibold ${pct >= 0 ? "text-sube" : "text-baja"}`}>
                {pct >= 0 ? "+" : ""}{fmtPct(pct)}
              </span>
            )}
            {rel && <span className={`text-[11px] font-medium ${rel.text}`}>· {rel.label}</span>}
          </div>

          {exp.titular && (
            <p className="font-semibold text-[17px] tracking-[-0.015em] text-tinta leading-snug">{exp.titular}</p>
          )}

          {exp.resumen && (
            <p className="text-apoyo text-tinta-2 leading-relaxed max-w-[70ch]">{exp.resumen}</p>
          )}

          {Array.isArray(exp.factores) && exp.factores.length > 0 && (
            <ul className="space-y-1.5">
              {exp.factores.filter(Boolean).map((f, i) => (
                <li key={i} className="text-apoyo text-tinta-2 flex gap-2 max-w-[70ch]">
                  <span className="text-tinta-3 font-bold shrink-0" aria-hidden="true">·</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
            {exp.tipo_movimiento && (
              <span className="text-etiqueta text-tinta-3">
                {MOVE_TYPE[(exp.tipo_movimiento || "").toUpperCase()] || exp.tipo_movimiento}
              </span>
            )}
            {data.model && (
              <span className="iv-etiqueta">
                {data.model}{data.fellback ? " (fallback)" : ""}
              </span>
            )}
          </div>

          {Array.isArray(data.news) && data.news.length > 0 && (
            <div className="pt-2 border-t border-linea">
              <p className="iv-etiqueta flex items-center gap-1 mb-2">
                <Newspaper size={12} aria-hidden="true" /> Noticias usadas
              </p>
              <ul className="space-y-1">
                {data.news.slice(0, 3).map((n, i) => (
                  <li key={i} className="text-etiqueta text-tinta-3 truncate">
                    {n.url ? (
                      <a href={n.url} target="_blank" rel="noopener noreferrer" className="hover:text-marca hover:underline">
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
