import React from "react";
import { cn } from "@/lib/utils";
import { fmtPrice, fmtPct } from "@/lib/format";

/* BandaRegimen · el semáforo del mercado, en cabecera de terminal
   ─────────────────────────────────────────────────────────────────────────────
   El régimen decide si las señales de compra son fiables hoy, así que abre la
   pantalla: un punto de color, la etiqueta, el consejo en prosa, y a la derecha la
   LECTURA de SPY —precio, sus medias de 50 y 200 sesiones, la distancia a la de 200
   y el retorno a un mes—. Todos los números vienen de `market_regime`; ninguno se
   inventa. Si no se ha podido calcular, se dice, y no se pinta un semáforo apagado
   como si fuera neutro (LEY 4 del producto: no saber no es una señal). */

const COLOR = {
  verde: "bg-sube",
  amarillo: "bg-aviso",
  rojo: "bg-baja",
};

function Stat({ etiqueta, valor, tono, num }) {
  const clave = tono === "auto"
    ? (num > 0 ? "text-sube" : num < 0 ? "text-baja" : "text-tinta")
    : tono || "text-tinta";
  return (
    <div className="min-w-0">
      <p className="iv-etiqueta leading-none">{etiqueta}</p>
      <p className={cn("iv-cifra text-apoyo font-semibold mt-0.5", clave)}>{valor}</p>
    </div>
  );
}

export default function BandaRegimen({ mercado }) {
  const m = mercado;
  const desconocido = !m?.label || m.light === "desconocido";

  if (desconocido) {
    return (
      <section className="iv-panel px-4 py-3" aria-label="Régimen de mercado">
        <div className="flex items-center gap-2.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-linea-marcada shrink-0" />
          <p className="text-apoyo text-tinta-2">
            No se ha podido evaluar el régimen de mercado ahora mismo. Suele ser que el
            histórico de SPY no está disponible; se reintenta solo en la próxima carga.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section
      className="iv-panel px-4 py-3 flex flex-col lg:flex-row lg:items-center gap-x-6 gap-y-3"
      aria-label="Régimen de mercado"
    >
      {/* Semáforo + prosa */}
      <div className="flex items-start gap-3 min-w-0 lg:flex-1">
        <span className={cn("inline-block w-2.5 h-2.5 rounded-full shrink-0 mt-1", COLOR[m.light] || "bg-linea-marcada")}
              aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-cuerpo text-tinta font-semibold leading-snug text-pretty">{m.label}</p>
          {m.advice && <p className="text-apoyo text-tinta-3 mt-0.5 leading-relaxed">{m.advice}</p>}
        </div>
      </div>

      {/* Lectura de SPY */}
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-x-5 gap-y-2 shrink-0
                      lg:border-l lg:border-linea lg:pl-6">
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
