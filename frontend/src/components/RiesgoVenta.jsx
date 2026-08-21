import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

/**
 * Cuánto margen libre devuelve esta venta. Antes de confirmarla.
 *
 * POR QUÉ NO BASTA CON LO QUE DICE DEGIRO
 *
 * DEGIRO enseña un "Margin impact" en su pantalla de la orden. Está mal. Medido contra una
 * venta real de 15 MRVL el 21-08-2026: su ticket predijo 5,36 €, este modelo predijo
 * 1.199 €, y ocurrieron 1.202,12 €. Un error del 99,6% frente a uno del 0,3%.
 *
 * La causa es que el riesgo de cartera es el MÁXIMO de cuatro componentes, no la suma: si
 * vendes algo que no marcaba el máximo, el máximo se queda donde estaba y el margen no se
 * mueve; si vendes justo lo que lo marcaba, se desploma. De ahí que la misma cantidad de
 * dinero libere 1.200 € o 5 € según qué vendas.
 *
 * CUÁNDO SE CALLA
 *
 * Las categorías A-D y la taxonomía sectorial del bróker no se pueden consultar por API, y
 * DEGIRO las revisa cada mes. Así que la cifra solo sale si el modelo ha demostrado antes
 * que reproduce el riesgo del último extracto de margen. Si no cuadra, aquí no aparece un
 * número: aparece el motivo. La diferencia entre una estimación y una promesa es
 * exactamente esa, y va donde se lee.
 */

const EUR = (v) =>
  v == null ? "—" : `${Math.round(v).toLocaleString("es-ES")} €`;

const ORDEN = ["evento", "neto", "sector", "bruto"];
const ETIQUETA = {
  evento: "Mayor posición",
  neto: "Peso total",
  sector: "Sector mayor",
  bruto: "Bruto",
};

function Desglose({ datos }) {
  const antes = datos.componentes_antes || {};
  const despues = datos.componentes_despues || {};
  return (
    <div className="mt-2 pt-2 border-t border-linea">
      <table className="w-full text-etiqueta">
        <thead>
          <tr className="text-tinta-3">
            <th className="text-left font-normal py-0.5">Componente</th>
            <th className="text-right font-normal">Ahora</th>
            <th className="text-right font-normal">Después</th>
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {ORDEN.map((k) => {
            const manda = datos.dominante_antes === k;
            return (
              <tr key={k} className={manda ? "text-tinta font-semibold" : "text-tinta-3"}>
                <td className="py-0.5">
                  {ETIQUETA[k]}
                  {manda && <span className="ml-1 text-marca">← manda</span>}
                </td>
                <td className="text-right">{EUR(antes[k])}</td>
                <td className="text-right">{EUR(despues[k])}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-etiqueta text-tinta-3 mt-2 leading-snug">
        Tu riesgo es el <b>mayor</b> de los cuatro, no su suma. Por eso vender algo que no
        marca el máximo no mueve el margen, por mucho dinero que sea.
      </p>
      {datos.calibracion?.error != null && (
        <p className="text-etiqueta text-tinta-3 mt-1.5 leading-snug">
          Calibrado con tu extracto de DEGIRO
          {datos.calibracion.fecha ? ` del ${datos.calibracion.fecha}` : ""}: el modelo
          reproduce tu riesgo real con un{" "}
          <b className="font-mono">{(datos.calibracion.error * 100).toFixed(1)}%</b> de
          desviación.
        </p>
      )}
    </div>
  );
}

export default function RiesgoVenta({ symbol, acciones }) {
  const [abierto, setAbierto] = React.useState(false);
  const sym = (symbol || "").trim().toUpperCase();
  const { data, isPending } = useQuery({
    queryKey: ["cartera", "riesgo-venta", sym, acciones || null],
    queryFn: () => api.cartera.riesgoVenta(sym, acciones),
    enabled: sym.length >= 1,
    staleTime: 30_000,
    retry: false,
  });

  if (!sym) return null;
  if (isPending) {
    return (
      <div className="iv-panel p-3">
        <p className="text-apoyo text-tinta-3">Calculando el impacto en tu margen…</p>
      </div>
    );
  }
  if (!data) return null;

  // Sin cifra: se dice por qué. Nunca un número a medias.
  if (data.estado !== "OK") {
    return (
      <div className="iv-panel p-3 border-l-[3px] border-l-linea-fuerte">
        <p className="iv-etiqueta mb-1">Impacto en tu margen libre</p>
        <p className="text-apoyo text-tinta-2 leading-snug">{data.motivo}</p>
      </div>
    );
  }

  const pct = (data.pct_del_importe || 0) * 100;
  return (
    <div className="iv-panel p-3 border-l-[3px] border-l-marca">
      <p className="iv-etiqueta mb-1">Si vendes esto, tu margen libre</p>
      <p className="iv-cifra text-cifra text-sube leading-none">
        +{EUR(data.margen_eur)}
      </p>
      <p className="text-apoyo text-tinta-3 mt-1">
        sobre <span className="iv-cifra">{EUR(data.importe_eur)}</span> vendidos ·{" "}
        <span className="iv-cifra">{pct.toFixed(0)}%</span> del importe
      </p>
      <p className="text-apoyo text-tinta-2 mt-2 leading-snug">{data.motivo}</p>

      {/* El aviso no es letra pequeña de descargo: DEGIRO enseña su propio número en la
          pantalla de la orden y a veces discrepa muchísimo. Que no sorprenda. */}
      <p className="text-etiqueta text-tinta-3 mt-2 leading-snug">
        Estimación de InverIA con el modelo de riesgo de DEGIRO. El «Margin impact» que
        muestra el bróker en su pantalla de la orden puede decir algo muy distinto: el
        21-08-2026 dijo 5 € en una venta que devolvió 1.202 €.
      </p>

      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="text-etiqueta text-tinta-3 underline mt-1.5"
      >
        {abierto ? "Ocultar el cálculo" : "Ver el cálculo"}
      </button>
      {abierto && <Desglose datos={data} />}
    </div>
  );
}
