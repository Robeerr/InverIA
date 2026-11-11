import React from "react";
import { Eye, Prohibit, BellSimple, Check } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";

/**
 * Por qué esta acción no tiene zonas de compra en pantalla.
 *
 * Sustituye al panel de niveles cuando la acción no está en tendencia alcista. No es un
 * hueco ni un mensaje de error: es la respuesta a una pregunta que el usuario se va a
 * hacer en cuanto eche en falta la lista.
 *
 * QUÉ SE OCULTA Y QUÉ NO
 *
 * El motor sigue calculando los soportes y siguen viajando en la respuesta como
 * `key_levels.support`. Lo que desaparece es su presentación COMO ZONAS DE COMPRA. Un
 * soporte dice dónde sería interesante comprar; nunca dice que haya que comprar, y bajo
 * una acción en tendencia bajista lo que marca es la siguiente parada de la caída.
 *
 * DOS ESTADOS, DOS COLORES DISTINTOS
 *
 * NO_COMPRAR y EN_SEGUIMIENTO no son lo mismo y no pueden verse igual: el primero es una
 * puerta cerrada y el segundo, una acción que hay que mirar. Pintarlos del mismo color
 * convertiría «vigila esto» en «olvídate de esto».
 *
 * LO QUE ESTE PANEL NO DICE
 *
 * No dice que la acción sea comprable cuando la tendencia es alcista. En ese caso ni
 * siquiera aparece: se muestran los niveles de siempre. Que una acción pase el filtro de
 * tendencia no significa que tenga un punto de entrada — eso es otra decisión y todavía
 * no está construida.
 *
 * LA SALIDA DEL CALLEJÓN
 *
 * El aviso de «avísame cuando se pueda comprar» estaba SOLO en el panel del Chartista, y
 * ese panel no existe hasta que se pulsa «Ampliar con IA». Así que en el caso normal
 * —abres una acción vetada y no gastas una llamada de IA— el veto se leía sin ninguna
 * salida, que es exactamente lo que la vigilancia venía a resolver.
 *
 * Aquí es donde tiene que estar: pegado a la frase que dice que no se puede comprar.
 */
export default function EstadoTendencia({ estado, motivo, soportes, symbol }) {
  const [vigilada, setVigilada] = React.useState(false);
  const [vigilando, setVigilando] = React.useState(false);

  // Si ya armaste el aviso, el botón sale marcado. Sin esto, volver a la acción invitaba
  // a armarlo otra vez y el intento moría en un 409: un error por hacer algo bien hecho.
  React.useEffect(() => {
    if (!symbol) return undefined;
    let vivo = true;
    setVigilada(false);
    api.vigilanciaVeto.lista()
      .then((r) => {
        if (!vivo) return;
        const syms = (r?.vigiladas || []).map((v) => v.symbol);
        if (syms.includes(symbol.toUpperCase())) setVigilada(true);
      })
      .catch(() => {});
    return () => { vivo = false; };
  }, [symbol]);

  async function vigilar() {
    if (!symbol || vigilando || vigilada) return;
    setVigilando(true);
    try {
      await api.vigilanciaVeto.armar(symbol);
      setVigilada(true);
      toast.success(`Te avisaré cuando ${symbol} vuelva a tendencia alcista`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      // «Ya no hay veto» es una BUENA noticia: la acción se giró a favor. Pintarla de
      // rojo diría lo contrario de lo que ha pasado.
      if (detail?.error === "sin_veto_que_levantar") {
        toast(detail.mensaje || `${symbol} ya está en tendencia alcista`);
        return;
      }
      const msg = typeof detail === "string" ? detail : "";
      if (e?.response?.status === 409 && /ya estás vigilando/i.test(msg)) {
        setVigilada(true);
        toast(`Ya estabas vigilando ${symbol}`);
      } else {
        toast.error(msg || "No se pudo armar el aviso");
      }
    } finally {
      setVigilando(false);
    }
  }

  if (!estado || estado === "SIN_EVALUAR") return null;

  const bloqueada = estado === "NO_COMPRAR";
  const Icono = bloqueada ? Prohibit : Eye;
  // Clases COMPLETAS y literales, no `border-${tono}`. Tailwind genera el CSS leyendo el
  // código fuente: una clase construida por concatenación no existe en ningún fichero, no
  // se emite, y el elemento sale sin color sin que falle nada. Ya nos pasó con otro
  // arbitrario y no se ve hasta que se mira la pantalla.
  const borde = bloqueada ? "border-baja" : "border-aviso";
  const texto = bloqueada ? "text-baja" : "text-aviso";

  return (
    <section
      data-testid="estado-tendencia"
      className={`iv-panel p-5 sm:p-6 border-l-[3px] ${borde}`}
    >
      <div className="flex items-start gap-3">
        <Icono size={22} weight="bold" className={`${texto} shrink-0 mt-0.5`} aria-hidden="true" />
        <div className="min-w-0">
          <h3 className="font-heading text-titulo text-tinta">
            {bloqueada ? "No comprar" : "En seguimiento"}
          </h3>
          <p className="text-cuerpo text-tinta mt-1.5 leading-relaxed max-w-[68ch]">{motivo}</p>
          <p className="text-apoyo text-tinta-3 mt-3 leading-relaxed max-w-[68ch]">
            No se muestran zonas de compra porque un soporte, por sí solo, no es una
            oportunidad: indica dónde podría pararse el precio, no que convenga comprar
            ahí.
          </p>

          {symbol && (
            <button
              data-testid="vigilar-veto-estado"
              onClick={vigilar}
              disabled={vigilando || vigilada}
              title="Recibirás un aviso en Telegram cuando esta acción vuelva a tendencia alcista"
              aria-live="polite"
              className={`mt-4 flex items-center gap-1.5 px-3 py-2 rounded-iv text-apoyo font-medium
                          transition-[color,border-color,background-color,transform] duration-150 motion-reduce:transition-none ${
                vigilada
                  ? "border border-sube/40 text-sube bg-sube/10"
                  : "border border-linea-fuerte text-tinta hover:border-marca/60 hover:text-marca active:scale-[0.97] disabled:opacity-50"
              }`}
            >
              {vigilada
                ? <><Check size={14} aria-hidden="true" /> Te avisaré cuando se pueda comprar</>
                : <><BellSimple size={14} aria-hidden="true" /> Avísame cuando se pueda comprar</>}
            </button>
          )}

          {/* Los soportes siguen siendo información técnica válida. Se enseñan como lo
              que son —estructura— y sin etiqueta de compra, precio ni plan. */}
          {Array.isArray(soportes) && soportes.length > 0 && (
            <div className="mt-5 pt-4 border-t border-linea">
              <p className="iv-etiqueta mb-1.5">Soportes técnicos</p>
              <ul className="flex flex-wrap gap-x-5 gap-y-1">
                {soportes.slice(0, 4).map((s) => (
                  <li key={s} className="iv-cifra text-apoyo text-tinta-2">
                    ${typeof s === "number" ? s.toFixed(2) : s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
