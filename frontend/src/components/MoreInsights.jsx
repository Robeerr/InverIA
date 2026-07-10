import React, { useEffect, useState } from "react";
import { Bank, ArrowFatRight } from "@phosphor-icons/react";
import { api } from "../lib/api";

// Congreso de EE.UU. (smart money) + alternativa sectorial. Solo se muestran si hay datos.

export function CongressPanel({ symbol }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    let a = true;
    if (!symbol) return;
    api.congress(symbol).then((x) => { if (a) setD(x); }).catch(() => {});
    return () => { a = false; };
  }, [symbol]);
  if (!d || !d.n) return null;
  return (
    <section className="card-flat p-5 animate-fade-up">
      <div className="flex items-center gap-2 mb-3">
        <Bank size={18} weight="fill" className="text-[#1a3a32]" />
        <h3 className="font-heading font-semibold text-base text-[#0e1f1a]">Congreso EE.UU. · {d.symbol}</h3>
      </div>
      <div className="flex items-center gap-3 mb-3 text-[11px] font-semibold">
        <span className="text-[#5c6b66]">{d.n} operaciones (12m)</span>
        {d.compras > 0 && <span className="text-[#4a7c59]">🟢 {d.compras} compras</span>}
        {d.ventas > 0 && <span className="text-[#d85c41]">🔴 {d.ventas} ventas</span>}
      </div>
      <div className="space-y-1.5">
        {d.operaciones.slice(0, 6).map((t, i) => {
          const buy = (t.tipo || "").toLowerCase().includes("purchase") || (t.tipo || "").toLowerCase().includes("buy");
          return (
            <div key={i} className="flex items-center justify-between gap-2 text-[11px]">
              <span className="text-[#0e1f1a] truncate">{t.nombre}</span>
              <span className="shrink-0 font-semibold" style={{ color: buy ? "#4a7c59" : "#d85c41" }}>
                {buy ? "Compra" : "Venta"}{t.importe ? ` · $${Number(t.importe).toLocaleString()}` : ""}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-[#8a958f] mt-3">Operaciones declaradas de congresistas de EE.UU. (indicador secundario "smart money").</p>
    </section>
  );
}

export function AlternativePanel({ symbol, onPick }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    let a = true;
    if (!symbol) return;
    api.alternativa(symbol).then((x) => { if (a) setD(x); }).catch(() => {});
    return () => { a = false; };
  }, [symbol]);
  if (!d || !(d.alternativas || []).length) return null;
  return (
    <section className="card-flat p-5 animate-fade-up">
      <div className="flex items-center gap-2 mb-1">
        <ArrowFatRight size={18} weight="fill" className="text-[#b8860b]" />
        <h3 className="font-heading font-semibold text-base text-[#0e1f1a]">Alternativa en {d.sector}</h3>
      </div>
      <p className="text-[11px] text-[#5c6b66] mb-3">Otras del mismo sector con mejor potencial que {d.symbol}:</p>
      <div className="space-y-2">
        {d.alternativas.map((a) => (
          <button key={a.symbol} onClick={() => onPick?.(a.symbol)}
            className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md border border-[#e5e0d8] hover:border-[#b8860b] text-left transition-colors">
            <div className="min-w-0">
              <p className="font-mono font-bold text-sm text-[#0e1f1a]">{a.symbol}</p>
              <p className="text-[10px] text-[#5c6b66] truncate max-w-[160px]">{a.name}</p>
            </div>
            <div className="text-right shrink-0">
              <span className="text-sm font-mono font-bold text-[#4a7c59]">{a.potential_score} pts</span>
              {typeof a.revenue_growth === "number" && <p className="text-[10px] text-[#5c6b66]">ventas +{Math.round(a.revenue_growth)}%</p>}
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
