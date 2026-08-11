import React from "react";
import { fmtPrice } from "../lib/format";
import InfoDot from "./InfoDot";

/**
 * Estado técnico: el bloque 03 de la arquitectura.
 *
 * Reúne los cinco campos que el backend calcula en cada carga, mete en el prompt de
 * la IA y pasa al motor de niveles… y que no tenían UNA SOLA lectura en el frontend:
 * `regime`, `regime.adx`, `atr_pct`, `obv_trend` y `vwap_anchored`. Más la media de
 * 10 semanas, que solo asomaba como un chip en la barra inferior.
 *
 * No cuesta nada: todo esto ya viajaba en la respuesta del dashboard.
 *
 * CÓMO SE PRESENTAN. Ninguno se pinta como cifra cruda: el ADX es el adjetivo del
 * régimen, el ATR es «se mueve un ±X% al día» y el OBV son dos palabras sobre si
 * entra o sale dinero. Un indicador en bruto obliga al lector a interpretar, y ese
 * trabajo es el que InverIA promete hacer.
 *
 * El régimen de MERCADO entra aquí como una cláusula al final, y no como la barra
 * propia que ocupaba la parte alta de la página: es el único de los cuatro bloques
 * de contexto que cambia cómo se lee ESTA acción, porque el motor de niveles ajusta
 * sus pesos con él.
 */

const REGIMEN = {
  tendencia_alcista: "Tendencia alcista",
  tendencia_bajista: "Tendencia bajista",
  rango: "En lateral: aquí mandan los niveles",
  transicion: "En transición: ni tendencia clara ni rango",
};

const ADX_CON_FUERZA = 25;   // el mismo umbral que usa indicators.market_regime

function Dato({ etiqueta, children, tono, testId, info }) {
  return (
    <div className="flex flex-col gap-0.5 min-w-0" data-testid={testId}>
      <span className="text-[9.5px] uppercase tracking-[0.14em] text-[#5c6b66] font-mono flex items-center gap-1">
        {etiqueta}
        {info && <InfoDot term={info} />}
      </span>
      <span className={`text-[13px] font-medium leading-tight ${tono || "text-[#0e1f1a]"}`}>
        {children}
      </span>
    </div>
  );
}

export default function EstadoTecnico({ indicators, quote, marketRegime }) {
  if (!indicators) return null;

  const regimen = indicators.regime?.regime;
  const adx = indicators.regime?.adx;
  const atrPct = indicators.atr_pct;
  const obv = indicators.obv_trend;
  const vwap = indicators.vwap_anchored;
  const salida = indicators.salida_10w;
  // quote.price es el ÚNICO precio: `indicators.price` es el cierre de la última vela
  // diaria y durante la sesión difiere siempre, así que comparar contra él daría un
  // «por encima del VWAP» que no cuadra con el precio de la cabecera.
  const precio = quote?.price;

  const etiquetaRegimen = REGIMEN[regimen];
  const conFuerza =
    adx != null && (regimen === "tendencia_alcista" || regimen === "tendencia_bajista")
      ? adx >= ADX_CON_FUERZA ? " con fuerza" : " sin mucha fuerza"
      : "";
  const adxTexto = adx != null ? ` (ADX ${Math.round(adx)})` : "";

  const sobreVwap = precio != null && vwap != null ? precio > vwap : null;
  const hayAlgo = etiquetaRegimen || atrPct != null || obv || vwap != null || salida;
  if (!hayAlgo) return null;

  return (
    <section className="card-flat px-4 py-3" data-testid="estado-tecnico">
      <div className="flex flex-wrap gap-x-6 gap-y-3">
        {etiquetaRegimen && (
          <Dato etiqueta="Régimen" testId="et-regimen" info={adx != null ? "ADX" : undefined}>
            {etiquetaRegimen}{conFuerza}{adxTexto}
          </Dato>
        )}

        {atrPct != null && (
          <Dato etiqueta="Ruido diario" testId="et-atr" info="ATR">
            ±{fmtPrice(atrPct, 1)}%
          </Dato>
        )}

        {obv && (
          <Dato
            etiqueta="Volumen"
            testId="et-obv"
            info="OBV"
            tono={String(obv).toLowerCase() === "subiendo" ? "text-[#4a7c59]" : "text-[#d85c41]"}
          >
            {String(obv).toLowerCase() === "subiendo" ? "Entra dinero" : "Sale dinero"}
          </Dato>
        )}

        {vwap != null && (
          <Dato
            etiqueta="VWAP anclado"
            testId="et-vwap"
            tono={sobreVwap ? "text-[#4a7c59]" : sobreVwap === false ? "text-[#d85c41]" : undefined}
          >
            {sobreVwap == null ? `$${fmtPrice(vwap)}` : `${sobreVwap ? "Por encima" : "Por debajo"} · $${fmtPrice(vwap)}`}
          </Dato>
        )}

        {salida && salida.por_encima != null && (
          <Dato
            etiqueta="Media 10 semanas"
            testId="et-salida10w"
            tono={salida.por_encima ? "text-[#4a7c59]" : "text-[#d85c41]"}
          >
            {salida.por_encima ? "Por encima" : "Por debajo"}
            {salida.sma != null ? ` · $${fmtPrice(salida.sma)}` : ""}
          </Dato>
        )}

        {marketRegime?.label && marketRegime.light !== "desconocido" && (
          <Dato etiqueta="Mercado" testId="et-mercado">
            <span className="inline-flex items-center gap-1.5">
              <span
                className="w-2 h-2 rounded-full inline-block shrink-0"
                style={{
                  background:
                    marketRegime.light === "rojo" ? "#d85c41"
                    : marketRegime.light === "amarillo" ? "#c9a14a" : "#4a7c59",
                }}
              />
              {marketRegime.label}
            </span>
          </Dato>
        )}
      </div>

      {/* La señal de salida del método. Va aparte y no como un dato más: es lo único
          de esta franja que pide una decisión hoy, y hasta ahora no existía en pantalla. */}
      {salida?.recien_perdida && (
        <p
          className="mt-3 pt-3 border-t border-[#e5e0d8] text-[12.5px] text-[#d85c41] font-medium flex gap-1.5"
          data-testid="et-recien-perdida"
        >
          <span aria-hidden="true">⚠️</span>
          <span>Acaba de perder la media de 10 semanas — es la señal de salida del método.</span>
        </p>
      )}
    </section>
  );
}
