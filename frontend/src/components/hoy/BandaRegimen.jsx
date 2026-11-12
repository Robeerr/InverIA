import React from "react";
import { cn } from "@/lib/utils";
import { Gauge } from "lucide-react";
import CabeceraBloque from "@/components/base/CabeceraBloque";
import { fmtPrice, fmtPct } from "@/lib/format";

/* BandaRegimen · el semáforo del mercado
   ─────────────────────────────────────────────────────────────────────────────
   El régimen decide si las señales de compra son fiables hoy, así que abre la
   columna de mercado, junto a la cartera: un punto de color, la etiqueta, el consejo
   en prosa, y debajo la LECTURA de SPY —precio, sus medias de 50 y 200 sesiones, la distancia a la de 200
   y el retorno a un mes—. Todos los números vienen de `market_regime`; ninguno se
   inventa. Si no se ha podido calcular, se dice, y no se pinta un semáforo apagado
   como si fuera neutro (LEY 4 del producto: no saber no es una señal). */

const COLOR = {
  verde: "bg-sube",
  amarillo: "bg-aviso",
  rojo: "bg-baja",
};

/* Halo del punto: el color del semáforo con un anillo del mismo tono, bajo. */
const ANILLO = {
  verde: "shadow-[0_0_0_4px_rgb(var(--iv-sube)/0.16)]",
  amarillo: "shadow-[0_0_0_4px_rgb(var(--iv-aviso)/0.16)]",
  rojo: "shadow-[0_0_0_4px_rgb(var(--iv-baja)/0.16)]",
};

function Stat({ etiqueta, valor, tono, num }) {
  const clave = tono === "auto"
    ? (num > 0 ? "text-sube" : num < 0 ? "text-baja" : "text-tinta")
    : tono || "text-tinta";
  return (
    <div className="min-w-0">
      <p className="iv-etiqueta leading-none">{etiqueta}</p>
      <p className={cn("iv-cifra text-[13.5px] font-medium mt-1.5 leading-none", clave)}>{valor}</p>
    </div>
  );
}

export default function BandaRegimen({ mercado }) {
  const m = mercado;
  const desconocido = !m?.label || m.light === "desconocido";

  if (desconocido) {
    return (
      <section className="p-5 sm:p-6" aria-label="Régimen de mercado">
        <CabeceraBloque icono={Gauge}>Régimen de mercado</CabeceraBloque>
        <div className="flex items-start gap-2.5 mt-3">
          <span className="inline-block w-2 h-2 mt-1.5 rounded-full bg-linea-marcada shrink-0" />
          <p className="text-[13.5px] text-tinta-2 leading-relaxed">
            No se ha podido evaluar el régimen de mercado ahora mismo. Suele ser que el
            histórico de SPY no está disponible; se reintenta solo en la próxima carga.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="p-5 sm:p-6" aria-labelledby="hoy-lectura">
      <CabeceraBloque icono={Gauge}>Régimen de mercado</CabeceraBloque>

      {/* La LECTURA, en prosa y a tamaño de titular. El régimen no es un dato más: es
          la condición bajo la que se leen todas las decisiones de la portada — y el
          consejo debajo, que es lo que de verdad se puede accionar. */}
      <h2 id="hoy-lectura"
          className="mt-4 text-[19px] sm:text-[20px] font-semibold tracking-[-0.025em] text-tinta leading-[1.2]
                     text-pretty flex items-baseline gap-3">
        <span className={cn("inline-block w-2 h-2 rounded-full shrink-0 -translate-y-[0.2em]",
                            COLOR[m.light] || "bg-linea-marcada", ANILLO[m.light])} aria-hidden="true" />
        <span>{m.label}</span>
      </h2>
      {m.advice && (
        <p className="text-[13.5px] text-tinta-2 mt-2 leading-relaxed text-pretty">{m.advice}</p>
      )}

      {/* La lectura de SPY. Las cinco cifras que sostienen la frase de arriba: sin
          ellas el veredicto es una opinión, y con ellas se puede comprobar. */}
      <div className="grid grid-cols-3 gap-x-4 gap-y-4 mt-5 pt-5 border-t border-suave">
        <Stat etiqueta="SPY" valor={m.spy_price != null ? `$${fmtPrice(m.spy_price)}` : "—"} />
        <Stat etiqueta="vs SMA200" valor={m.dist_sma200_pct != null ? fmtPct(m.dist_sma200_pct) : "—"}
              tono="auto" num={m.dist_sma200_pct} />
        <Stat etiqueta="1 mes" valor={m.return_1m_pct != null ? fmtPct(m.return_1m_pct) : "—"}
              tono="auto" num={m.return_1m_pct} />
        <Stat etiqueta="SMA 50" valor={m.sma50 != null ? `$${fmtPrice(m.sma50)}` : "—"} />
        <Stat etiqueta="SMA 200" valor={m.sma200 != null ? `$${fmtPrice(m.sma200)}` : "—"} />
      </div>
    </section>
  );
}
