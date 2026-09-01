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

  // Agrupar como DEGIRO. El bróker no publica su taxonomía, pero sí cuánto suma su mayor
  // sector; con el valor de cada posición eso deja de ser una pregunta sobre clasificación
  // y pasa a ser una suma con solución. Va en dos pasos: escribe en fichas del usuario, así
  // que primero enseña qué tocaría y solo escribe si se acepta.
  const agrupar = useMutation({
    mutationFn: async () => {
      const plan = await api.cartera.agruparSector(false);
      if (plan.estado === "YA_CUADRA") {
        toast.success("El sector ya cuadra con tu extracto: no hay nada que agrupar.");
        return null;
      }
      if (!plan.propuesta?.length) {
        const porque = {
          NOS_PASAMOS: "aquí se agrupa MÁS que en DEGIRO, y qué sacar no se deduce de una "
            + "suma: cualquier combinación que sobre serviría.",
          AMBIGUO: `hay varias combinaciones que cuadran igual (${(plan.candidatas || [])
            .map((c) => c.join("+")).join(", ")}), y acertar por suerte no vale.`,
          SIN_SOLUCION: "ninguna combinación de tus posiciones llega al objetivo"
            + ((plan.cerca || []).length
              // Lo más cerca que se llega dice MÁS que el "no": si el objetivo se queda
              // entre dos posiciones, es que DEGIRO no agrupa como ningún subconjunto del
              // nuestro y hay que mirar otra cosa.
              ? `. Lo más cerca: ${plan.cerca.map((c) => `${c.symbols.join("+")} = `
                  + `${Math.round(c.suma_eur)} €`).join(", ")}.`
              : "."),
          DEMASIADAS: "hay demasiadas posiciones fuera del grupo para probarlas todas.",
        }[plan.estado] || "no se ha podido calcular.";
        toast.error(`Faltan ${Math.round(plan.faltan_eur)} € pero ${porque}`,
          { duration: 12000 });
        return null;
      }
      const cuales = plan.propuesta
        .map((p) => `${p.symbol} (${Math.round(p.valor_eur)} €, ahora ${p.sector})`)
        .join("\n");
      const ok = window.confirm(
        `Tu extracto dice que DEGIRO agrupa ${Math.round(plan.objetivo_eur)} € en su mayor `
        + `sector, y aquí «${plan.grupo}» agrupa ${Math.round(plan.actual_eur)} €.\n\n`
        + `Pasando esto al mismo grupo se llega a ${Math.round(plan.resultado_eur)} €:\n\n`
        + `${cuales}\n\nSolo cambia el campo «Sector DEGIRO»; tu columna Sector no se `
        + "toca.\n\n¿Aplicar?");
      return ok ? api.cartera.agruparSector(true) : null;
    },
    onSuccess: (r) => {
      if (!r) return;
      toast.success(`${r.propuesta.length} posición(es) agrupadas en «${r.grupo}». `
        + `El sector pasa a ${Math.round(r.resultado_eur)} €.`, { duration: 10000 });
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "No se pudo calcular la agrupación"),
  });

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
    const cartera = aNumero(f?.valor_cartera_eur);
    if (!(riesgo > 0)) return toast.error("Falta el «Portfolio Risk» del extracto");
    // Sin el valor de cartera solo se pueden comparar euros contra euros, y entonces el
    // extracto caduca con cualquier día verde: la cartera sube, el riesgo sube con ella y
    // el modelo cree que ha dejado de acertar. Con los dos se compara la PROPORCIÓN, que
    // no se inmuta ante una subida general, y el extracto vale semanas.
    if (!(cartera > 0)) return toast.error("Falta el «Value of portfolio»: sin él el extracto caduca en un día");
    guardar.mutate({
      riesgo_eur: riesgo,
      valor_cartera_eur: aNumero(f?.valor_cartera_eur),
      saldo_eur: aNumero(f?.saldo_eur),
      margen_eur: aNumero(f?.margen_eur),
      riesgo_neto_eur: aNumero(f?.riesgo_neto_eur),
      riesgo_bruto_eur: aNumero(f?.riesgo_bruto_eur),
      riesgo_sector_eur: aNumero(f?.riesgo_sector_eur),
      fecha: f?.fecha || undefined,
    });
  };

  // Las tres últimas salen de DESPLEGAR «Portfolio Risk» en el extracto. Son opcionales,
  // pero valen mucho: con Net y Gross, InverIA despeja cuántos euros de tu cartera están
  // en categoría D —su resta es el 15% de lo que NO lo está— y con la línea sectorial
  // despeja cuánto agrupa DEGIRO en su mayor sector. Sin ellas solo puede decir «no
  // cuadro»; con ellas dice cuántos euros faltan por marcar y dónde.
  const campos = [
    ["riesgo_eur", "Portfolio Risk *", "11645,14"],
    ["valor_cartera_eur", "Value of portfolio *", "30440,28"],
    ["saldo_eur", "Cash balance", "-18616,99"],
    ["margen_eur", "Margin (surplus)", "196,37"],
    ["riesgo_neto_eur", "Net investment…", "13468,28"],
    ["riesgo_bruto_eur", "Gross investment…", "10218,56"],
    ["riesgo_sector_eur", "Largest sector risk", "13951,13"],
  ];
  const cls =
    "w-full bg-fondo border border-linea rounded px-2 py-1.5 font-mono text-apoyo";

  // Con el extracto ya guardado esto es un dato de mantenimiento: se teclea una vez al mes
  // y el resto del tiempo solo estorba. Entonces se encoge a una línea y la explicación se
  // pliega. Cuando NO hay extracto es al revés —hay que decir qué es y de dónde se saca, o
  // el hueco no se rellena nunca—, así que ahí el texto se queda a la vista.
  const guardado = data?.riesgo_eur && !f;

  const explicacion = (
    <>
      Cópialo de «Available to trade → Margin statement». Sin él, InverIA no estima
      cuánto margen libera una venta: prefiere callarse a dar un número que no puede
      comprobar. <b>Vale un mes</b> — se compara la proporción riesgo/cartera, que no se
      mueve con el vaivén diario de los precios, y DEGIRO recategoriza los instrumentos
      mensualmente. Cuando caduque te avisa por Telegram.
    </>
  );

  return (
    <section className="iv-panel p-4">
      {guardado ? (
        <div className="flex items-baseline gap-3 flex-wrap">
          <h3 className="font-heading font-semibold text-cuerpo text-tinta-2">
            Extracto de margen
          </h3>
          <span className="iv-cifra text-cuerpo text-tinta">
            {Math.round(data.riesgo_eur).toLocaleString("es-ES")} € de riesgo
          </span>
          {data.fecha && (
            <span className="text-apoyo text-tinta-3">del {data.fecha}</span>
          )}
          <button
            type="button"
            onClick={() => agrupar.mutate()}
            disabled={agrupar.isPending}
            title="Calcula qué posiciones hay que meter en el mismo sector para reproducir el agrupamiento de DEGIRO, usando la cifra de su propio extracto. No toca tu columna Sector."
            className="text-apoyo text-tinta-3 underline ml-auto disabled:opacity-60"
          >
            {agrupar.isPending ? "Calculando…" : "Agrupar como DEGIRO"}
          </button>
          <button
            type="button"
            onClick={() => setF({})}
            className="text-apoyo text-tinta-3 underline"
          >
            Actualizar
          </button>
        </div>
      ) : (
        <>
          <h3 className="font-heading font-semibold text-titulo text-tinta">
            Extracto de margen de DEGIRO
          </h3>
          <p className="text-apoyo text-tinta-3 mt-1 leading-snug">{explicacion}</p>
        </>
      )}

      {guardado && (
        <details className="mt-1">
          <summary className="text-etiqueta text-tinta-3 cursor-pointer">
            Para qué sirve
          </summary>
          <p className="text-apoyo text-tinta-3 mt-1 leading-snug">{explicacion}</p>
        </details>
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
          {/* Dónde salen las tres últimas, que es lo que nadie adivina: hay que TOCAR la
              flecha de «Portfolio Risk» para que se abra el desglose. */}
          <p className="text-etiqueta text-tinta-3 leading-snug">
            Las tres últimas salen de desplegar <b>Portfolio Risk</b> en el extracto (la
            flechita a su derecha). Son opcionales, pero con ellas InverIA puede decirte
            cuántos euros de tu cartera están en categoría D y cuánto agrupa DEGIRO en su
            mayor sector — que es lo que hace falta para que el modelo cuadre.
          </p>
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
