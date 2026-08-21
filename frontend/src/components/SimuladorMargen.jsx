import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { aNumero } from "../lib/format";

/**
 * Qué le pasa a tu margen libre si compras o vendes esta acción. ANTES de decidir.
 *
 * POR QUÉ EXISTE, HABIENDO YA UN AVISO EN LOS FORMULARIOS DE VENTA
 *
 * Aquel vive dentro de la venta, y ahí ya has decidido. Y solo cubre la venta: COMPRAR
 * también mueve el margen, en la dirección peligrosa cuando la cuenta está apalancada.
 * Con 1.551 € de margen, comprar 1.551 € de una acción de categoría D lo deja en cero.
 *
 * LA LETRA A-D DECIDE CASI TODO
 *
 * Mil euros de una categoría A cuestan ~314 € de margen; de una categoría D, los mil.
 * Cuando no se sabe, esto enseña el RANGO entre las cuatro en vez de elegir una: un rango
 * honesto sirve para decidir, una letra inventada no. Con el selector se fija y la cifra
 * pasa a ser exacta.
 */

const EUR = (v) =>
  v == null ? "—" : `${Math.round(Math.abs(v)).toLocaleString("es-ES")} €`;

const CATS = ["A", "B", "C", "D"];

function Resultado({ d }) {
  const gana = (d.margen_eur || 0) > 0;
  const pct = Math.abs((d.pct_del_importe || 0) * 100);
  return (
    <div className="mt-3">
      <p className="iv-etiqueta mb-1">
        {gana ? "Tu margen libre subiría" : "Tu margen libre bajaría"}
      </p>
      {d.distinguible === false ? (
        <p className="text-cuerpo text-tinta">Apenas se movería.</p>
      ) : (
        <p className={`iv-cifra text-cifra leading-none ${gana ? "text-sube" : "text-baja"}`}>
          {gana ? "+" : "−"}
          {EUR(d.margen_eur)}
          {d.incertidumbre_eur ? (
            <span className="text-cuerpo text-tinta-3"> ± {EUR(d.incertidumbre_eur)}</span>
          ) : null}
        </p>
      )}
      {d.distinguible !== false && (
        <p className="text-apoyo text-tinta-3 mt-1">
          sobre <span className="iv-cifra">{EUR(d.importe_eur)}</span> ·{" "}
          <span className="iv-cifra">{pct.toFixed(0)}%</span> del importe
        </p>
      )}
      <p className="text-apoyo text-tinta-2 mt-2 leading-snug">{d.motivo}</p>
    </div>
  );
}

function Rango({ d }) {
  return (
    <div className="mt-3">
      <p className="iv-etiqueta mb-1">Tu margen libre bajaría</p>
      <p className="iv-cifra text-cifra text-baja leading-none">
        −{EUR(d.rango_min_eur)}
        <span className="text-cuerpo text-tinta-3"> a </span>
        −{EUR(d.rango_max_eur)}
      </p>
      <p className="text-apoyo text-tinta-3 mt-1">
        según sea categoría {d.rango_min_cat} o {d.rango_max_cat}
      </p>
      <p className="text-apoyo text-tinta-2 mt-2 leading-snug">{d.motivo}</p>
    </div>
  );
}

export default function SimuladorMargen({ symbol }) {
  const sym = (symbol || "").trim().toUpperCase();
  const [accion, setAccion] = React.useState("comprar");
  const [importe, setImporte] = React.useState("");
  const [cat, setCat] = React.useState("");

  const eur = aNumero(importe);
  const { data, isFetching } = useQuery({
    queryKey: ["cartera", "simular", sym, accion, eur, cat],
    queryFn: () => api.cartera.simularMargen(sym, accion, eur, cat || undefined),
    enabled: !!sym && eur > 0,
    staleTime: 30_000,
    retry: false,
  });

  if (!sym) return null;
  const btn = (id, texto) => (
    <button
      key={id}
      type="button"
      onClick={() => setAccion(id)}
      className={`px-3 py-1 rounded-iv-sm text-apoyo font-semibold ${
        accion === id ? "bg-marca text-marca-tinta" : "text-tinta-3 border border-linea"
      }`}
    >
      {texto}
    </button>
  );

  return (
    <div className="iv-panel p-4" data-testid="simulador-margen">
      <h3 className="font-heading font-semibold text-titulo text-tinta">
        Impacto en tu margen
      </h3>
      <p className="text-apoyo text-tinta-3 mt-0.5 leading-snug">
        Cuánto margen libre ganas o pierdes con esta operación, según el modelo de riesgo
        de DEGIRO.
      </p>

      <div className="flex items-center gap-2 mt-3 flex-wrap">
        {btn("comprar", "Voy a comprar")}
        {btn("vender", "Voy a vender")}
        <input
          value={importe}
          onChange={(e) => setImporte(e.target.value)}
          inputMode="decimal"
          placeholder="importe en €"
          aria-label="Importe en euros"
          className="flex-1 min-w-[120px] bg-fondo border border-linea rounded px-2 py-1.5 font-mono text-apoyo"
        />
      </div>

      {/* El selector solo aparece cuando hace falta: si la acción ya está en tu cartera,
          su categoría se sabe y preguntarla otra vez sería ruido. */}
      {accion === "comprar" && data?.estado === "FALTA_CATEGORIA" && (
        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
          <span className="iv-etiqueta">Categoría en DEGIRO:</span>
          {CATS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCat(c)}
              className={`w-8 py-1 rounded-iv-sm text-apoyo font-mono font-bold ${
                cat === c ? "bg-marca text-marca-tinta" : "text-tinta-3 border border-linea"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      {isFetching && eur > 0 && (
        <p className="text-apoyo text-tinta-3 mt-3">Calculando…</p>
      )}
      {!isFetching && data && data.estado === "OK" && <Resultado d={data} />}
      {!isFetching && data && data.estado === "FALTA_CATEGORIA" && <Rango d={data} />}
      {!isFetching && data && !["OK", "FALTA_CATEGORIA"].includes(data.estado) && (
        <p className="text-apoyo text-tinta-2 mt-3 leading-snug">{data.motivo}</p>
      )}

      {data?.calibracion?.error != null && (
        <p className="text-etiqueta text-tinta-3 mt-2 leading-snug">
          Calibrado con tu extracto de DEGIRO
          {data.calibracion.fecha ? ` del ${data.calibracion.fecha}` : ""}: reproduce tu
          riesgo real con un{" "}
          <b className="font-mono">{(data.calibracion.error * 100).toFixed(1)}%</b> de
          desviación. Medido contra dos ventas reales, falló por 3 € y por 41 €.
        </p>
      )}
    </div>
  );
}
