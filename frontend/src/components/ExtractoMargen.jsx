import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { aNumero } from "../lib/format";

/**
 * El «Margin statement» de DEGIRO, copiado a mano. Es lo que autoriza a dar cifras.
 *
 * POR QUÉ HAY QUE TECLEARLO
 *
 * El modelo de riesgo necesita dos cosas que no se pueden consultar: la categoría A-D que
 * DEGIRO asigna a cada instrumento —no hay API, y la revisa cada mes— y su taxonomía
 * sectorial, que no coincide con la de ningún proveedor de datos.
 *
 * Se podrían pedir esas letras una a una, pero caducarían en silencio. Esto es mejor: con
 * el riesgo total que publica el propio bróker, InverIA COMPRUEBA si su cálculo lo
 * reproduce. Si lo reproduce, las estimaciones valen y se puede decir con cuánto error. Si
 * deja de reproducirlo, se callan solas. Un número que se puede auditar contra la pantalla
 * del bróker vale más que quince que hay que mantener a mano.
 */
export default function ExtractoMargen() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["cartera", "margen"],
    queryFn: api.cartera.margen,
    staleTime: 60_000,
    retry: false,
  });
  const [f, setF] = React.useState(null);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));

  const guardar = useMutation({
    mutationFn: (datos) => api.cartera.guardarMargen(datos),
    onSuccess: () => {
      toast.success("Extracto guardado — las estimaciones se recalibran solas");
      qc.invalidateQueries({ queryKey: ["cartera"] });
      setF(null);
    },
    onError: (e) =>
      toast.error(e?.response?.data?.detail || "No se pudo guardar el extracto"),
  });

  const enviar = (e) => {
    e.preventDefault();
    const riesgo = aNumero(f?.riesgo_eur);
    if (!(riesgo > 0)) return toast.error("Falta el «Portfolio Risk» del extracto");
    guardar.mutate({
      riesgo_eur: riesgo,
      valor_cartera_eur: aNumero(f?.valor_cartera_eur),
      saldo_eur: aNumero(f?.saldo_eur),
      margen_eur: aNumero(f?.margen_eur),
      fecha: f?.fecha || undefined,
    });
  };

  const campos = [
    ["riesgo_eur", "Portfolio Risk *", "11645,14"],
    ["valor_cartera_eur", "Value of portfolio", "30440,28"],
    ["saldo_eur", "Cash balance", "-18616,99"],
    ["margen_eur", "Margin (surplus)", "196,37"],
  ];
  const cls =
    "w-full bg-fondo border border-linea rounded px-2 py-1.5 font-mono text-apoyo";

  return (
    <section className="iv-panel p-4">
      <h3 className="font-heading font-semibold text-titulo text-tinta">
        Extracto de margen de DEGIRO
      </h3>
      <p className="text-apoyo text-tinta-3 mt-1 leading-snug">
        Cópialo de «Available to trade → Margin statement». Sin él, InverIA no estima
        cuánto margen libera una venta: prefiere callarse a dar un número que no puede
        comprobar.
      </p>

      {data?.riesgo_eur && !f && (
        <div className="mt-3 flex items-baseline gap-3 flex-wrap">
          <span className="iv-etiqueta">Guardado</span>
          <span className="iv-cifra text-cuerpo text-tinta">
            {Math.round(data.riesgo_eur).toLocaleString("es-ES")} € de riesgo
          </span>
          {data.fecha && (
            <span className="text-apoyo text-tinta-3">del {data.fecha}</span>
          )}
          <button
            type="button"
            onClick={() => setF({})}
            className="text-apoyo text-tinta-3 underline ml-auto"
          >
            Actualizar
          </button>
        </div>
      )}

      {(!data?.riesgo_eur || f) && (
        <form onSubmit={enviar} className="mt-3 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            {campos.map(([k, etiqueta, ejemplo]) => (
              <label key={k} className="block">
                <span className="iv-etiqueta block mb-0.5">{etiqueta}</span>
                <input
                  value={f?.[k] || ""}
                  onChange={set(k)}
                  inputMode="decimal"
                  placeholder={ejemplo}
                  className={cls}
                />
              </label>
            ))}
          </div>
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={guardar.isPending}
              className="bg-marca text-marca-tinta rounded px-4 py-1.5 text-apoyo font-semibold disabled:opacity-60"
            >
              {guardar.isPending ? "Guardando…" : "Guardar"}
            </button>
            {data?.riesgo_eur && (
              <button
                type="button"
                onClick={() => setF(null)}
                className="text-apoyo text-tinta-3 underline"
              >
                Cancelar
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
