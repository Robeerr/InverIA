import React, { useState, useRef, useEffect } from "react";
import { Question } from "@phosphor-icons/react";

// Glosario pedagógico en cristiano. Clave -> explicación breve para el usuario que aprende.
export const GLOSARIO = {
  RSI: "Mide si una acción está 'cara' o 'barata' a corto plazo (0-100). Por encima de 70 = sobrecomprada (puede corregir); por debajo de 30 = sobrevendida (puede rebotar). No es señal por sí sola.",
  MACD: "Compara dos medias móviles para ver el impulso de la tendencia. Por encima de 0 = impulso alcista; por debajo = bajista. La compra fiable es cuando cruza al alza estando ya por encima de 0.",
  Signal: "La media del propio MACD. Cuando el MACD cruza por encima de su Signal, es señal de impulso alcista; por debajo, bajista.",
  Histograma: "La distancia entre el MACD y su Signal. Si crece, el impulso se acelera; si se encoge, se está agotando.",
  SMA: "Media del precio de los últimos N días (simple). La de 200 marca la tendencia de fondo: por encima = alcista, por debajo = bajista. Suelen actuar como soporte/resistencia.",
  EMA: "Como la media simple pero da más peso a los días recientes, así que reacciona antes a los cambios de precio.",
  Bollinger: "Una banda alrededor del precio que se ensancha con la volatilidad. Tocar la banda inferior sugiere sobreventa; la superior, sobrecompra. El estrechamiento suele preceder a un movimiento fuerte.",
  Soporte: "Un precio por debajo del actual donde históricamente ha habido compradores y el precio ha frenado su caída. Es donde te planteas comprar.",
  Resistencia: "Un precio por encima del actual donde históricamente ha habido vendedores y el precio se ha frenado al subir. Es donde te planteas vender/tomar beneficios.",
  Fibonacci: "Niveles matemáticos (38,2%, 50%, 61,8%...) donde el precio suele rebotar dentro de una tendencia. Se usan para anticipar hasta dónde puede corregir antes de seguir.",
  ADX: "Mide la FUERZA de la tendencia (no la dirección). Por encima de 25 = tendencia fuerte y fiable; por debajo de 20 = mercado sin rumbo (rango), donde las señales de tendencia fallan más.",
  OBV: "Suma el volumen según el precio suba o baje. Si el OBV sube aunque el precio no, sugiere que el dinero fuerte está acumulando (comprando) por debajo.",
  ATR: "La volatilidad real diaria de la acción. Se usa para poner el stop a una distancia sensata (ej. 1,5×ATR): ni tan cerca que te salte el ruido, ni tan lejos que arriesgues de más.",
};

// Punto de interrogación que muestra una explicación al TOCARLO (funciona en móvil, sin hover).
export default function InfoDot({ term, text }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const body = text || GLOSARIO[term];
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("touchstart", onDoc);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("touchstart", onDoc); };
  }, [open]);
  if (!body) return null;
  return (
    <span ref={ref} className="relative inline-flex">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        aria-label={`Qué es ${term || "esto"}`}
        className="inline-flex items-center justify-center w-4 h-4 rounded-full border border-[#d9d3c7] text-[#8a958f] hover:border-[#1a3a32] hover:text-[#1a3a32] transition-colors"
      >
        <Question size={10} weight="bold" />
      </button>
      {open && (
        <span className="absolute z-30 left-0 top-5 w-60 p-2.5 rounded-lg bg-[#0e1f1a] text-[#f5f3ef] text-[11px] leading-snug shadow-lg">
          {term && <b className="block mb-0.5 text-[#e6c98a]">{term}</b>}
          {body}
        </span>
      )}
    </span>
  );
}
