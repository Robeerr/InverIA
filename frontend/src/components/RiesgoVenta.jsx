import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

/**
 * Qué le pasa al RIESGO de tu cartera si vendes esto. Antes de confirmar la venta.
 *
 * QUÉ PREGUNTA CONTESTA Y QUÉ NO
 *
 * Con perfil Trader, el "Margen libre" de DEGIRO no es un contador de caja: es garantía
 * menos el RIESGO que su modelo asigna a la cartera. Vender mueve dinero de cartera a
 * efectivo dentro de la misma ecuación, así que lo único que mueve el margen es cuánto
 * baja el riesgo. Por eso vender 1.000 € de una acción dispara el margen y vender 1.000 €
 * de otra no lo mueve.
 *
 * Esto estima ESO: el riesgo retirado. NO el margen que DEGIRO devolverá. Faltan la
 * categoría A-D del instrumento, la taxonomía sectorial del bróker y el efectivo de la
 * cuenta, y sin las tres una cifra en euros de margen sería una afirmación que no se puede
 * sostener. De ahí que aquí no haya ni una: solo una clase y el desglose que la produce.
 *
 * El aviso no es letra pequeña de descargo: es la diferencia entre una estimación y una
 * promesa, y va donde se lee.
 */

const TONO = {
  ALTO: "text-sube",
  MEDIO: "text-tinta",
  BAJO: "text-tinta-3",
};

const EUR = (v) =>
  v == null ? "—" : `${Math.round(v).toLocaleString("es-ES")} €`;

const ORDEN = ["evento", "neto_categoria", "sector", "bruto"];
const ETIQUETA = {
  evento: "Mayor posición",
  neto_categoria: "Peso total",
  sector: "Sector mayor",
  bruto: "Bruto",
};

function Desglose({ datos }) {
  const antes = datos.componentes_antes || {};
  const despues = datos.componentes_despues || {};
  return (
    <div className="mt-2 pt-2 border-t border-linea">
      <p className="iv-etiqueta mb-1.5">Riesgo de cartera, por componente</p>
      <table className="w-full text-apoyo">
        <thead>
          <tr className="text-tinta-3">
            <th className="text-left font-normal py-1">Componente</th>
            <th className="text-right font-normal">Ahora</th>
            <th className="text-right font-normal">Tras vender</th>
          </tr>
        </thead>
        <tbody className="iv-cifra">
          {ORDEN.filter((k) => k in antes).map((k) => {
            const mandaAntes = datos.dominante_antes === k;
            const mandaDespues = datos.dominante_despues === k;
            return (
              <tr key={k} className="border-t border-linea/60">
                <td className="py-1 font-sans">
                  {ETIQUETA[k]}
                  {mandaAntes && <span className="text-tinta-3"> · manda ahora</span>}
                </td>
                <td className={`text-right ${mandaAntes ? "font-semibold" : "text-tinta-3"}`}>
                  {EUR(antes[k])}
                </td>
                <td className={`text-right ${mandaDespues ? "font-semibold" : "text-tinta-3"}`}>
                  {EUR(despues[k])}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {/* El máximo, y no la suma, es la pieza que explica todo lo raro: si vendes algo que
          no marcaba el máximo, el máximo lo sigue fijando otra cosa y no baja nada. */}
      <p className="text-etiqueta text-tinta-3 mt-2 leading-snug">
        El riesgo de la cartera es el <b>mayor</b> de estos cuatro, no su suma. Ahora mismo
        manda {datos.dominante_antes_texto}
        {datos.dominante_despues_texto
          ? <>, y tras la venta mandaría {datos.dominante_despues_texto}</>
          : null}.
      </p>
      <p className="text-etiqueta text-tinta-3 mt-1 leading-snug">
        Retira <span className="iv-cifra">{EUR(datos.riesgo_retirado_eur)}</span> de riesgo,
        que es <span className="iv-cifra">{datos.indice?.toFixed(2)}</span> veces lo que
        retiraría una venta cualquiera del mismo importe. Por debajo de{" "}
        {datos.umbrales?.medio} es BAJO; a partir de {datos.umbrales?.alto}, ALTO.
      </p>
      <p className="text-etiqueta text-tinta-3 mt-1 leading-snug">
        No se conoce la categoría de riesgo (A-D) que DEGIRO asigna a cada acción, así que
        todas cuentan igual en «mayor posición». Una acción de categoría peor retiraría más
        riesgo del que aquí se ve.
      </p>
    </div>
  );
}

export default function RiesgoVenta({ symbol }) {
  const [abierto, setAbierto] = React.useState(false);
  const sym = (symbol || "").trim().toUpperCase();

  const { data, isPending, isError } = useQuery({
    queryKey: ["cartera", "riesgo-venta", sym],
    queryFn: () => api.cartera.riesgoVenta(sym),
    enabled: sym.length >= 1,
    staleTime: 60_000,
    retry: false,
  });

  if (!sym) return null;

  return (
    <div className="iv-panel p-3 bg-superficie-alt">
      <p className="text-apoyo text-tinta-2 leading-snug">
        Si vendo esto, ¿qué impacto tendrá probablemente sobre mi margen libre?
      </p>

      {isPending && <p className="text-apoyo text-tinta-3 mt-1.5">Calculando…</p>}

      {isError && (
        <p className="text-apoyo text-tinta-3 mt-1.5">
          No se ha podido estimar ahora mismo.
        </p>
      )}

      {data && data.clase === "SIN_ESTIMACION" && (
        <p className="text-apoyo text-aviso mt-1.5 leading-snug">{data.motivo}</p>
      )}

      {data && data.clase !== "SIN_ESTIMACION" && (
        <>
          <p className="mt-1.5">
            <span className="iv-etiqueta">Riesgo eliminado estimado</span>{" "}
            <span className={`font-mono font-bold text-titulo ${TONO[data.clase] || ""}`}>
              {data.clase}
            </span>
          </p>
          <p className="text-apoyo text-tinta-2 mt-1 leading-snug">{data.motivo}</p>
          <button
            type="button"
            onClick={() => setAbierto((a) => !a)}
            aria-expanded={abierto}
            className="text-apoyo text-tinta-3 underline mt-1.5"
          >
            {abierto ? "Ocultar el cálculo" : "Ver el cálculo"}
          </button>
          {abierto && <Desglose datos={data} />}
        </>
      )}

      {/* Va SIEMPRE, también cuando no se puede estimar: quien lee esto tiene que saber
          qué está leyendo, y no solo cuando el número le gusta. */}
      <p className="text-etiqueta text-tinta-3 mt-2 leading-snug">
        Estimación de InverIA. No representa el margen libre que DEGIRO liberará
        exactamente.
      </p>
    </div>
  );
}
