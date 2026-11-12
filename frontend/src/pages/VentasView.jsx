import React from "react";
import { CaretDown, X } from "@phosphor-icons/react";
import {
  ArrowLeftRight, ChevronRight, CircleDollarSign, FileUp, Layers, Plus, Scale, Trash2,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { aNumero } from "../lib/format";
import RiesgoVenta from "../components/RiesgoVenta";
import ExtractoMargen from "../components/ExtractoMargen";
import { leerComoBroker, guardarComoBroker } from "../lib/preferencias";
import { datosPosicion, totalesAbiertas } from "../lib/operaciones";
import { useSignals } from "../hooks/useSignals";
import Boton from "../components/base/Boton";
import BaseChip from "../components/base/Chip";
import Monograma from "../components/base/Monograma";
import Segmentado from "../components/base/Segmentado";
import Cascada from "../components/base/Cascada";
import CabeceraBloque from "../components/base/CabeceraBloque";
import Pestanas, { propsPanel } from "../components/base/Pestanas";
import { Aviso, AvisosPanel } from "../components/base/Aviso";

// Símbolos que están en la Cartera pero todavía SIN ningún nivel definido.
//
// Comprar algo que no estaba en la Cartera crea ahora su fila sola (para que coja precio
// de mercado), pero deliberadamente sin niveles: el precio de compra y los niveles de
// estrategia son cosas distintas. Sin decirlo en la pantalla, esa posición se ve igual que
// una a la que se le olvidó asignar el nivel, y parece un fallo.
const NIVELES = ["nivel1", "nivel2", "nivel3", "nivel4", "nivel5"];
export function simbolosSinNiveles(entries) {
  const out = new Set();
  for (const e of entries || []) {
    if (!e?.symbol) continue;
    if (NIVELES.every((n) => e[n] == null)) out.add(e.symbol.toUpperCase());
  }
  return out;
}

// ── Formato ──────────────────────────────────────────────────────────────────
// Todo el dinero pasa por aquí para que no haya dos formatos distintos en la misma
// pantalla. `null` se pinta como "—" y NUNCA como 0: un 0 afirma que no ganaste nada,
// mientras que lo cierto es que falta el tipo de cambio para saberlo.
const eur = (v) => (v == null ? "—" : `${v >= 0 ? "" : "−"}${Math.abs(v).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`);
const usd = (v, d = "USD") => (v == null ? "—" : `${v >= 0 ? "" : "−"}${Math.abs(v).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${d === "USD" ? "$" : d}`);
const pct = (v) => (v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}%`);
const fecha = (f) => (f ? f.split("-").reverse().join("/") : "—");

const tono = (v) => (v == null ? "text-tinta-3" : v >= 0 ? "text-sube" : "text-baja");

// El botón de guardar de los formularios: mismo aspecto en los cuatro, con respuesta al
// pasar, al pulsar y desactivado (antes solo cambiaba la opacidad al desactivarse).
// Rediseño v2: el principal del sistema (índigo con filo de luz, radio de control de
// 10 px), a lo ancho del formulario y con 44 px de alto para el dedo.
const BOTON_PRINCIPAL = "iv-boton-brillo w-full sm:w-auto sm:min-w-[220px] h-11 rounded-[10px] px-4 text-[14px] font-medium "
  + "transition-[filter,transform] duration-150 ease-salida motion-reduce:transition-none "
  + "hover:brightness-[1.08] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed "
  + "disabled:hover:brightness-100 disabled:active:scale-100";

// Acción secundaria en texto: subrayado discreto que se afirma al pasar. Una sola clase
// para los enlaces-botón sueltos que había, cada uno con su propio estilo.
const ENLACE = "text-[13px] text-tinta-3 underline underline-offset-4 decoration-tinta/20 "
  + "hover:text-tinta hover:decoration-tinta/50 transition-colors duration-150 "
  + "motion-reduce:transition-none disabled:opacity-60 disabled:cursor-not-allowed";

// Rótulo de bloque pequeño: Geist en minúscula de frase. Sustituye a las versalitas
// monoespaciadas de 11 px de la versión anterior.
const ROTULO = "text-[12.5px] font-medium text-tinta-3";

// Botón de acción destructiva en línea (borrar una venta, un lote): rojo apagado que
// se afirma al pasar, con 36 px de alto para acertar con el dedo.
const BOTON_BORRAR = "inline-flex items-center gap-1.5 h-9 px-2.5 rounded-lg text-[12.5px] "
  + "text-baja/90 hover:text-baja hover:bg-baja/10 transition-colors duration-150 "
  + "motion-reduce:transition-none disabled:opacity-60";

// Campo de los formularios: capa de luz, radio 10, foco índigo.
const inputCls = "mt-1.5 w-full h-10 rounded-[10px] bg-tinta/[0.04] border border-suave px-3 iv-cifra "
  + "text-[14px] text-tinta placeholder:text-tinta-3/70 placeholder:font-sans transition-[border-color,box-shadow] duration-150 "
  + "focus:outline-none focus:border-marca/60 focus:ring-2 focus:ring-marca/20 motion-reduce:transition-none";
const inputMini = "h-9 rounded-lg bg-tinta/[0.04] border border-suave px-2.5 iv-cifra text-[13px] text-tinta "
  + "placeholder:text-tinta-3/70 placeholder:font-sans focus:outline-none focus:border-marca/60 focus:ring-2 focus:ring-marca/20 "
  + "disabled:opacity-40";

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
  "septiembre", "octubre", "noviembre", "diciembre"];
const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"];
// «2026-11-04» → «4 nov». Solo presentación: la fecha completa sigue en aria-label.
const fechaCorta = (f) => {
  const [, m, d] = (f || "").split("-");
  return m && d ? `${Number(d)} ${MESES_CORTOS[Number(m) - 1] || m}` : fecha(f);
};
const mesDe = (f) => {
  const [a, m] = (f || "").split("-");
  return m ? `${MESES[Number(m) - 1] || m} ${a}` : "Sin fecha";
};

// Cifra héroe: céntimos y «€» reducidos, como en Cartera.
function CifraHeroe({ valor }) {
  const t = eur(valor);
  const m = t.match(/^(.*?)(,\d+)?(\s€)$/);
  if (!m) return t;
  return (
    <>
      {m[1]}
      {m[2] && <span className="text-[0.5em] opacity-80 tracking-[-0.02em]">{m[2]}</span>}
      <span className="text-[0.42em] font-medium text-tinta-3 ml-[0.18em] tracking-normal align-[0.78em]">€</span>
    </>
  );
}

// Cabecera de un formulario: titular, nota y cierre.
function CabeceraForm({ titulo, nota, onCerrar, icono: Icono }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-start gap-3 min-w-0">
        {Icono && (
          <span aria-hidden="true" className="flex items-center justify-center w-9 h-9 rounded-[10px] bg-marca/10 text-marca shrink-0">
            <Icono className="w-[18px] h-[18px]" strokeWidth={1.75} />
          </span>
        )}
        <div className="min-w-0">
          <h3 className="text-[16px] font-semibold tracking-[-0.015em] text-tinta">{titulo}</h3>
          {nota && <p className="text-[13px] text-tinta-3 mt-0.5 leading-snug">{nota}</p>}
        </div>
      </div>
      <button type="button" onClick={onCerrar} aria-label="Cerrar"
              className="-m-1 w-9 h-9 inline-flex items-center justify-center rounded-lg text-tinta-3 hover:text-tinta hover:bg-tinta/[0.06] transition-colors duration-150 motion-reduce:transition-none">
        <X size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

/* Las cifras de una posición abierta, calculadas UNA vez.
   ─────────────────────────────────────────────────────────────────────────────
   «Lo que tienes abierto» se pinta de dos formas: tabla de seis columnas en
   escritorio y tarjetas apiladas en móvil, porque seis columnas no caben en 390px
   y obligaban a arrastrar la pantalla de lado para leer la ganancia — justo el
   dato por el que se abre esta sección.

   Las dos vistas enseñan los MISMOS números, así que la regla del interruptor de
   bróker vive aquí y no duplicada en cada una. Si un día cambia qué se considera
   precio medio o de dónde sale la ganancia, cambia en un solo sitio; con la regla
   copiada, la versión de móvil se quedaría atrás sin que nadie lo notara. */
/* La regla vive en lib/operaciones.js, con sus tests: el Total de abajo la usa también. */

/** Las etiquetas de nivel de una fila: en cuáles tienes posición AHORA.
 *
 *  Antes se pintaba `niveles_comprados`, que recorre el historial entero de compras. Una
 *  fila con tres lotes abiertos enseñaba cuatro etiquetas, y la cuarta era un nivel del
 *  que ya se había salido.
 *
 *  El primer intento fue apagarla y escribirle «vendido». Estaba mal por dos motivos.
 *  Uno: afirma POR QUÉ no hay posición, y eso no lo sabe esta fila — un nivel puede no
 *  tener lote abierto porque se vendió o porque nunca se compró, y el chip no distingue
 *  los dos casos. Dos: aquí nadie viene a mirar en qué niveles estuvo alguna vez, sino en
 *  cuáles está; lo otro está en el histórico de ventas, que es su sitio.
 *
 *  Así que se pintan los ABIERTOS y punto. Y sigue sirviendo de aviso: si apareciera un
 *  nivel que no reconoces, es que hay un lote VIVO etiquetado ahí — un dato que revisar,
 *  no una reliquia. */
function NivelesDeLaFila({ p }) {
  // Sin el campo nuevo —una respuesta cacheada de antes del despliegue— se usa la lista
  // vieja, que es lo que se pintaba hasta ahora. Enseñar nada haría parecer que la
  // posición no tiene niveles.
  const niveles = p.niveles_abiertos || p.niveles_comprados || [];
  if (!niveles.length) return null;
  // Compactas: «N1 N2 N3» en una sola pastilla en vez de cuatro chips «NIVEL 1…» que
  // partían la fila en dos o tres líneas. El nombre completo va en title y aria-label.
  const nombres = niveles.map((n) => NIVEL_ETIQUETA[n] || n);
  return (
    <span className="inline-flex items-center gap-1 h-[22px] rounded-md border border-info/15 bg-info/10 px-1.5 iv-cifra text-[11.5px] leading-none text-info whitespace-nowrap"
          title={`Niveles con posición abierta: ${nombres.join(", ")}`}
          aria-label={`Niveles con posición abierta: ${nombres.join(", ")}`}>
      {niveles.map((n) => (
        <span key={n}>{NIVEL_CORTO[n] || NIVEL_ETIQUETA[n] || n}</span>
      ))}
    </span>
  );
}

const NIVEL_CORTO = {
  deseado: "D", nivel1: "N1", nivel2: "N2", nivel3: "N3", nivel4: "N4", nivel5: "N5",
};

const NIVEL_ETIQUETA = {
  deseado: "Deseado", nivel1: "Nivel 1", nivel2: "Nivel 2",
  nivel3: "Nivel 3", nivel4: "Nivel 4", nivel5: "Nivel 5",
};

// El chip del sistema (Geist 12, radio 6). «nivel» es informativo: va en `info`.
function Chip({ children, tono: t = "neutro", title }) {
  return (
    <BaseChip tono={t === "nivel" ? "info" : t} title={title}>{children}</BaseChip>
  );
}

// ── Cifra grande de cabecera ─────────────────────────────────────────────────
// La ayuda NO puede vivir solo en `title=`: en el móvil no hay ratón que posar encima, así
// que el texto era sencillamente inalcanzable. Es un botón que despliega el texto bajo la
// cifra, y de paso funciona con teclado.
// Flecha de desplegar: un icono de verdad que gira, en vez de alternar «▲/▼». El giro
// dice qué ha pasado al pulsar; con movimiento reducido cambia sin animarse.
function Flecha({ abierta, className = "" }) {
  return (
    <CaretDown size={12} weight="bold" aria-hidden="true"
               className={`shrink-0 text-tinta-3 transition-transform duration-200 ease-out motion-reduce:transition-none ${abierta ? "rotate-180" : ""} ${className}`} />
  );
}

// Cuánto hace que se consultó una cifra. Un "1 € = 1,1563 USD" sin edad se lee como si
// fuera de ahora mismo, y puede tener hasta una hora.
function haceCuanto(segundos) {
  if (segundos == null) return null;
  if (segundos < 90) return "ahora mismo";
  const min = Math.round(segundos / 60);
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  return `hace ${h} h`;
}

// ── Detalle de una venta: de qué lotes salió ─────────────────────────────────
// Es la respuesta a "¿de qué compra eran estas acciones?", que es justo lo que un número
// suelto no puede contestar y por lo que existe el libro de lotes.
function DetalleLotes({ lotes, divisa }) {
  if (!lotes?.length) return null;
  return (
    <div className="min-w-0">
      {/* Tú compras y vendes POR NIVELES, pero el método de cálculo empareja por FECHA.
          Leer qué niveles se han consumido obligaba a recorrer la lista lote a lote; esto
          lo dice en una frase, en el idioma en el que operas. */}
      {(() => {
        const porNivel = {};
        for (const l of lotes) {
          const k = l.nivel || "sin";
          porNivel[k] = (porNivel[k] || 0) + (Number(l.acciones) || 0);
        }
        const partes = Object.entries(porNivel)
          .sort((a, b) => (a[0] === "sin" ? 1 : b[0] === "sin" ? -1 : a[0].localeCompare(b[0])))
          .map(([k, n]) => `${n} ${k === "sin" ? "sin nivel" : NIVEL_ETIQUETA[k] || k}`);
        return partes.length ? (
          <p className="text-[14px] text-tinta-2 mb-4 leading-snug">
            Has vendido <b className="font-semibold text-tinta">{partes.join(" y ")}</b>.
          </p>
        ) : null;
      })()}
      <p className={`${ROTULO} mb-2`}>Estas acciones salieron de</p>
      {/* Una línea de tiempo: cada compra es un punto en el carril, con su fecha, lo
          que se tomó de ella y su coste a la derecha. */}
      <ol className="relative ml-1 border-l border-medio">
        {lotes.map((l, i) => (
          <li key={i} className="relative pl-4 py-2">
            <span aria-hidden="true" className="absolute -left-[4.5px] top-[15px] w-2 h-2 rounded-full bg-superficie border border-tinta/40" />
            <div className="flex items-center gap-x-3 gap-y-1 flex-wrap text-[13px]">
              <span className="iv-cifra text-tinta-3 w-[78px] shrink-0">{fecha(l.fecha_compra)}</span>
              <span className="iv-cifra font-medium text-tinta">{l.acciones} × {usd(l.precio_compra, divisa)}</span>
              {l.nivel && <Chip tono="nivel">{NIVEL_ETIQUETA[l.nivel] || l.nivel}</Chip>}
              {l.comision_parte > 0 && (
                <span className="text-[12px] text-tinta-3">
                  +{usd(l.comision_parte, divisa)} comisión
                </span>
              )}
              <span className="ml-auto iv-cifra text-tinta-3 whitespace-nowrap">
                coste {usd(l.coste_divisa, divisa)}
              </span>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

// ── Una venta ────────────────────────────────────────────────────────────────
function FilaVenta({ v, metodo, comoBroker, onBorrar }) {
  const [abierto, setAbierto] = React.useState(false);
  // Con el interruptor puesto manda la ponderada, que es la del bróker. Antes solo cambiaba
  // la tabla de posiciones abiertas: el historial y el realizado seguían en FIFO/LIFO, así
  // que un botón que dice «ver como en DEGIRO» dejaba media pantalla en el otro método sin
  // decirlo. Si a esta venta le falta la ponderada se cae al método elegido, que es peor
  // que nada pero mejor que un hueco.
  const usaPmp = comoBroker && v.ponderada?.ganancia_divisa != null;
  const m = usaPmp ? v.ponderada : v[metodo];
  const otro = usaPmp ? v[metodo] : v[metodo === "fifo" ? "lifo" : "fifo"];
  const nombreOtro = usaPmp ? metodo.toUpperCase() : (metodo === "fifo" ? "LIFO" : "FIFO");
  const nombreMetodo = usaPmp ? "media ponderada" : metodo.toUpperCase();
  const difiere = Math.abs((m.ganancia_divisa ?? 0) - (otro?.ganancia_divisa ?? 0)) > 0.005;

  return (
    <div className="border-t border-suave first:border-t-0">
      <div className={`group px-4 sm:px-5 flex items-center gap-3 transition-colors duration-150 motion-reduce:transition-none hover:bg-tinta/[0.025] ${abierto ? "bg-tinta/[0.03]" : ""}`}>
        {/* aria-label descriptivo, no fijo: un lector de pantalla leía 146 botones
            idénticos. min-h para que el dedo acierte en el móvil. */}
        <button onClick={() => setAbierto((o) => !o)}
                aria-expanded={abierto}
                aria-label={`${abierto ? "Ocultar" : "Ver"} el detalle de la venta de ${v.acciones} ${v.symbol} del ${fecha(v.fecha)}`}
                className="flex items-center gap-3 flex-1 min-w-0 text-left min-h-[60px] py-2.5 rounded-lg">
          <Monograma symbol={v.symbol} tamano="sm" />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2 min-w-0">
              <span className="text-[14px] font-semibold text-tinta tracking-[-0.01em]">{v.symbol}</span>
              {v.sin_cubrir > 0 && (
                <Chip tono="aviso" title="Se han vendido más acciones de las que constan compradas. Añade la compra que falte.">
                  faltan {v.sin_cubrir}
                </Chip>
              )}
            </span>
            <span className="block iv-cifra text-[12px] text-tinta-3 mt-0.5 truncate">
              {fechaCorta(v.fecha)} · {v.acciones} × {usd(v.precio_venta, v.divisa)}
            </span>
          </span>
        </button>

        <div className="text-right shrink-0">
          <p className={`iv-cifra font-medium text-[14.5px] leading-tight whitespace-nowrap ${tono(m.ganancia_eur ?? m.ganancia_divisa)}`}>
            {m.ganancia_eur != null ? eur(m.ganancia_eur) : usd(m.ganancia_divisa, v.divisa)}
          </p>
          <p className="iv-cifra text-[12px] whitespace-nowrap mt-0.5">
            <span className={tono(m.pct_eur ?? m.pct)}>{pct(m.pct_eur ?? m.pct)}</span>
            {m.ganancia_eur != null && (
              <span className="text-tinta-3 hidden sm:inline"> · {usd(m.ganancia_divisa, v.divisa)}</span>
            )}
          </p>
        </div>

        <button onClick={() => setAbierto((o) => !o)}
                className="w-9 h-9 -mr-2 inline-flex items-center justify-center rounded-lg shrink-0 hover:bg-tinta/[0.06]"
                aria-label="Ver detalle" aria-expanded={abierto}>
          <Flecha abierta={abierto} />
        </button>
      </div>

      {abierto && (
        <div className="px-4 sm:px-5 pt-4 pb-5 bg-tinta/[0.03] border-t border-suave grid gap-x-10 gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] iv-entra">
          {m.lotes?.length ? <DetalleLotes lotes={m.lotes} divisa={v.divisa} /> : null}
          <div className={`min-w-0 text-[13px] space-y-1 ${m.lotes?.length ? "" : "lg:col-span-2"}`}>
            {/* Las DOS columnas, divisa y euros, en cada paso. Antes solo salían los
                dólares y luego aparecía la ganancia en euros: el salto de "259 $" a "209 €"
                había que creérselo. Con los dos lados y el tipo de cambio, la cuenta se
                rehace a mano en un minuto — que es la única forma de fiarse de una cifra. */}
            {/* QUÉ MÉTODO estás viendo. La cifra grande cambia con el interruptor de
                DEGIRO y nada lo decía: la MISMA venta salía a −56,39 € y a +282,04 € en dos
                pantallas por lo demás idénticas, sin forma de saber cuál era cuál. Un
                número que cambia sin decir por qué se lee como un fallo, y con razón. */}
            <p className={`${ROTULO} pb-2`}>
              Calculado por <b className="font-semibold text-tinta-2">{nombreMetodo}</b>
              {nombreMetodo === "media ponderada" && " · el método de DEGIRO"}
              {nombreMetodo === "FIFO" && " · el que va a tu declaración"}
              {nombreMetodo === "LIFO" && " · como vendes tú"}
            </p>
            <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-x-5 items-baseline [&>span]:py-1.5 [&>span:nth-child(n+4)]:border-t [&>span:nth-child(n+4)]:border-suave">
              <span className="text-[12px] text-tinta-3">Concepto</span>
              <span className="text-[12px] text-tinta-3 text-right">
                {v.divisa === "USD" ? "Dólares" : v.divisa}
              </span>
              <span className="text-[12px] text-tinta-3 text-right">Euros</span>

              <span className="text-tinta-2">Ingresado (menos comisión)</span>
              <span className="iv-cifra text-right">{usd(m.ingreso_divisa, v.divisa)}</span>
              <span className="iv-cifra text-right">{eur(m.ingreso_eur)}</span>

              <span className="text-tinta-2">Coste de esas acciones</span>
              <span className="iv-cifra text-right">{usd(m.coste_divisa, v.divisa)}</span>
              <span className="iv-cifra text-right">{eur(m.coste_eur)}</span>

              <span className="font-medium text-tinta">Ganancia</span>
              <span className={`iv-cifra text-right font-semibold ${tono(m.ganancia_divisa)}`}>
                {usd(m.ganancia_divisa, v.divisa)}
              </span>
              <span className={`iv-cifra text-right font-semibold ${tono(m.ganancia_eur)}`}>
                {eur(m.ganancia_eur)}
              </span>

              {/* Los DOS porcentajes, etiquetados. Antes se enseñaba solo el de euros junto
                  a las cifras en dólares, donde el porcentaje es otro: en esta misma venta,
                  +16,96% en euros y +18,41% en dólares. Parecía el de los dólares. */}
              <span className="text-tinta-2">Porcentaje</span>
              <span className={`iv-cifra text-right ${tono(m.pct)}`}>{pct(m.pct)}</span>
              <span className={`iv-cifra text-right ${tono(m.pct_eur)}`}>{pct(m.pct_eur)}</span>
            </div>

            {v.tasa_venta && (
              <p className="text-[12px] text-tinta-3 pt-2 leading-snug">
                Cambio del día de la venta: 1 € = {v.tasa_venta} {v.divisa}. El coste va al
                cambio del día de CADA compra, que es el que ves en cada línea de arriba.
              </p>
            )}

            {m.efecto_divisa_eur != null && (
              // Aparece sola en cuanto ves que ganaste en dólares y menos en euros.
              <div className="flex justify-between gap-4 pt-1">
                <span className="text-tinta-3" title="Parte del resultado que se debe al movimiento del euro frente a la divisa, y no a la acción. Si es negativo, el euro se comió parte de tu ganancia.">
                  De la ganancia en euros, por el movimiento del euro ⓘ
                </span>
                <span className={`iv-cifra ${tono(m.efecto_divisa_eur)}`}>{eur(m.efecto_divisa_eur)}</span>
              </div>
            )}
            {/* Cuando el SIGNO cambia entre las dos monedas, decirlo. Es el momento en que
                la pantalla más parece equivocada: arriba pone +22,10 $ y al lado −56,39 €,
                y sin una frase que lo nombre eso se lee como un fallo de cálculo. No es
                un dato nuevo —sale del efecto del euro que ya está tres líneas más
                arriba— es el mismo dato dicho cuando hace falta. */}
            {m.ganancia_eur != null && m.ganancia_divisa != null
              && (m.ganancia_divisa > 0) !== (m.ganancia_eur > 0)
              && Math.abs(m.ganancia_divisa) > 0.005 && Math.abs(m.ganancia_eur) > 0.005 && (
              <p className="text-[13px] text-tinta-2 mt-2 leading-snug rounded-iv bg-info/[0.07] px-3 py-2.5">
                <b className="font-semibold text-tinta">{m.ganancia_divisa > 0 ? "Ganaste" : "Perdiste"} en {v.divisa} y{" "}
                {m.ganancia_eur > 0 ? "ganaste" : "perdiste"} en euros.</b>{" "}
                No es un error: el euro se movió entre tus compras y esta venta, así que
                cada {v.divisa === "USD" ? "dólar" : v.divisa} que recuperaste vale{" "}
                {m.ganancia_eur < 0 ? "menos" : "más"} euros que los que pusiste. Lo que
                cuenta para ti —y para Hacienda— es la cifra en euros.
              </p>
            )}
            {!m.exacto && (
              <p className="text-[12px] text-aviso pt-1">
                Falta el tipo de cambio de alguna compra: la ganancia en euros de esta venta
                no se puede calcular y no entra en los totales.
              </p>
            )}
            {/* Los otros dos métodos, siempre. Es la misma venta contada de tres formas y
                cada una sirve para algo distinto; enseñar solo una invita a usarla para todo. */}
            <div className="pt-3 mt-2 border-t border-suave space-y-1.5">
              {difiere && (
                <div className="flex justify-between gap-4">
                  <span className="text-tinta-3">
                    Por <b className="font-medium text-tinta-2">{nombreOtro}</b>
                    {nombreOtro === "FIFO"
                      ? " (lo que va a tu declaración)"
                      : " (como vendes tú)"}
                  </span>
                  <span className="iv-cifra text-tinta-2 text-right whitespace-nowrap">
                    {otro.ganancia_eur != null ? eur(otro.ganancia_eur) : usd(otro.ganancia_divisa, v.divisa)}
                    {" · "}{pct(otro.pct_eur ?? otro.pct)}
                  </span>
                </div>
              )}
              {v.ponderada && !usaPmp && (
                <div className="flex justify-between gap-4">
                  <span className="text-tinta-3"
                        title="Media ponderada: el método que usa tu bróker para su pantalla. Todas tus acciones cuestan lo mismo (la media), así que no distingue niveles. Sirve para cuadrar con DEGIRO, no para la declaración.">
                    Por <b className="font-medium text-tinta-2">media ponderada</b> (como tu bróker) ⓘ
                  </span>
                  {/* En EUROS lo primero: es la cifra que enseña DEGIRO y con la que se
                      compara. En dólares al lado, para cuadrar con la línea de arriba. */}
                  <span className="iv-cifra text-tinta-3 text-right whitespace-nowrap">
                    {v.ponderada.ganancia_eur != null && (
                      <b className="font-medium text-tinta">{eur(v.ponderada.ganancia_eur)}</b>
                    )}
                    {v.ponderada.pct_eur != null && ` · ${pct(v.ponderada.pct_eur)}`}
                    <span className="block text-[12px]">
                      {usd(v.ponderada.ganancia_divisa, v.divisa)}
                      {v.ponderada.pct != null && ` · ${pct(v.ponderada.pct)}`}
                    </span>
                  </span>
                </div>
              )}
              {/* Por qué unas ventas cuadran con el bróker y otras no. Sin esto, la
                  diferencia se lee como un fallo de cálculo, y no lo es. */}
              {v.ponderada && (difiere || v.ponderada.ganancia_eur != null) && (
                <p className="text-[12px] text-tinta-3 pt-1 leading-relaxed">
                  {v.metodos_incoherentes
                    ? "Esta venta debería haber cerrado la posición, y entonces los tres "
                      + "métodos darían por fuerza el mismo número — pero no coinciden. Eso "
                      + "solo pasa si el libro tiene lotes de esta acción que no deberían "
                      + "estar, o le faltan: la cifra de arriba está calculada sobre un "
                      + "conjunto de compras que no es el real. Revisa sus compras antes de "
                      + "fiarte de este resultado."
                    : v.cierra_posicion && !v.ventas_antes
                    ? "Esta venta cerró la posición y es la única que has hecho de esta "
                      + "acción: se vendieron todos los lotes de una vez, así que los tres "
                      + "métodos dan por fuerza el mismo número."
                    : v.cierra_posicion
                    ? "Esta venta cerró la posición, pero antes vendiste parte, y ahí está "
                      + "la explicación de que los tres métodos difieran: cada uno dejó "
                      + "vivos lotes distintos —FIFO gastó los viejos, LIFO los nuevos— "
                      + "así que las acciones que quedaban no eran las mismas para uno que "
                      + "para otro. Lo que sí coincide en los tres es el TOTAL de todas tus "
                      + "ventas de esta acción; lo que cambia es cómo se reparte entre ellas."
                    : "Venta parcial" + (v.abiertas_despues
                        ? ` — quedaron ${v.abiertas_despues} acciones abiertas`
                        : "")
                      + ". Los tres métodos difieren porque el resultado depende de qué lote "
                      + "das por vendido, y eso no lo decide el cálculo. DEGIRO usa la media "
                      + "ponderada; a tu declaración va el FIFO."}
                </p>
              )}
            </div>
            <div className="pt-3">
              <button onClick={() => onBorrar(v)}
                      aria-label={`Borrar la venta de ${v.acciones} ${v.symbol} del ${fecha(v.fecha)}`}
                      className={`${BOTON_BORRAR} -ml-2.5`}>
                <Trash2 className="w-3.5 h-3.5" strokeWidth={1.9} aria-hidden="true" />
                Borrar esta venta
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Importar el CSV del bróker ───────────────────────────────────────────────
// Resuelve de una vez lo que se venía estimando: fecha exacta, comisión real y el tipo de
// cambio que te aplicaron de verdad. Va en dos pasos porque el fichero identifica cada
// acción por ISIN y nombre, no por ticker, y meter operaciones en la posición equivocada
// es peor que no importarlas.
function ImportarDegiro({ onCerrar }) {
  // Reparar las que ya estaban. Apagado por defecto: reescribe apuntes existentes y
  // eso solo debe pasar cuando se pide, no como efecto secundario de reimportar.
  const [actualizar, setActualizar] = React.useState(false);
  const [sustituir, setSustituir] = React.useState(false);
  const IGNORAR = "__IGNORAR__";
  const [archivo, setArchivo] = React.useState(null);
  const [previo, setPrevio] = React.useState(null);
  const [mapeo, setMapeo] = React.useState({});
  const qc = useQueryClient();

  const leer = useMutation({
    mutationFn: () => api.cartera.importarDegiro(archivo, null, false),
    onSuccess: (r) => {
      setPrevio(r);
      // Se rellena con lo YA decidido en importaciones anteriores —ticker o "ignorar"— y,
      // para lo que quede, con la sugerencia por el nombre. Así una segunda importación
      // solo pide lo nuevo en vez de volver a preguntarlo todo.
      const inicial = {};
      for (const p of r.productos || []) {
        if (p.ignorado) inicial[p.isin] = IGNORAR;
        else if (p.symbol || p.sugerencia) inicial[p.isin] = p.symbol || p.sugerencia;
      }
      setMapeo(inicial);
      const yaResueltos = (r.productos || []).filter((p) => p.symbol || p.ignorado).length;
      if (yaResueltos) {
        toast.info(`${yaResueltos} producto(s) ya emparejados de antes. `
          + `Solo tienes que rellenar los ${r.pendientes?.length || 0} que faltan.`,
          { duration: 8000 });
      }
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "No se pudo leer el fichero"),
  });

  const confirmar = useMutation({
    mutationFn: () =>
      api.cartera.importarDegiro(archivo, mapeo, true, actualizar, sustituir),
    onSuccess: (r) => {
      if (r.pendientes?.length) {
        toast.error("Faltan productos por emparejar");
        setPrevio(r);
        return;
      }
      if (r.tipo === "dividendos") {
        toast.success(r.importados
          ? `${r.importados} apunte(s) de dividendos importados`
          : `Ya estaban todos los dividendos (${r.saltados} apuntes).`, { duration: 8000 });
        qc.invalidateQueries({ queryKey: ["cartera", "historial"] });
      qc.invalidateQueries({ queryKey: ["cartera", "resumen"] });
      qc.invalidateQueries({ queryKey: ["cartera", "posicion"] });
      qc.invalidateQueries({ queryKey: ["cartera", "dividendos"] });
        onCerrar();
        return;
      }
      const reparadas = r.actualizadas
        ? ` · ${r.actualizadas} corregidas`
          + (r.comision_recuperada ? ` (${eur(r.comision_recuperada)} de comisión recuperada)` : "")
        : "";
      // Tres finales distintos, y antes los tres decían lo mismo. "Ya estaba todo
      // importado" tanto si no se pidió reparar como si se pidió y no había nada que
      // reparar deja al usuario sin saber si la casilla funcionó.
      const nadaQueCorregir = r.actualizar_pedido && !r.actualizadas;
      const sust = r.sustituidas
        ? ` · ${r.sustituidas} apunte(s) tuyos sustituidos por los del fichero`
        : "";
      toast.success(r.importadas
        ? `${r.importadas} operación(es) importadas`
          + (r.saltadas ? ` · ${r.saltadas} ya estaban` : "") + sust + reparadas
        : reparadas
          ? `No había nada nuevo, pero${reparadas.replace(" · ", " ")}.`
          : nadaQueCorregir
            ? `Nada que corregir: las ${r.saltadas} operaciones ya tienen la misma `
              + "comisión que el fichero."
            : r.tapadas_por_symbol?.length
              // NO es lo mismo "el fichero ya está entero" que "hay filas del fichero que
              // no pueden entrar porque un apunte tuyo las tapa". Lo segundo significa que
              // esas compras —con su fecha, su precio y su comisión reales— siguen fuera
              // del libro, y que seguirán fuera por mucho que reimportes.
              ? `${r.motivos_salto.la_tapa_un_apunte_manual} fila(s) del fichero NO han `
                + "entrado porque las tapa un apunte tuyo: "
                + r.tapadas_por_symbol.slice(0, 6)
                  .map((t) => `${t.symbol} (${t.acciones} acc.)`).join(", ")
                + ". Marca «Sustituir mis apuntes por los del fichero» y vuelve a importar."
              : `Ya estaba todo importado (${r.saltadas} operaciones). Si querías corregir `
              + "las comisiones, marca la casilla y vuelve a importar.",
        { duration: 10000 });
      // Una compra descartada es una venta futura SIN COSTE: su ganancia saldrá hinchada.
      // Pasó con OHLA y CRWV (filas a precio 0 de ampliaciones/splits) y desde el log del
      // servidor nadie se entera. Aquí se cuenta cuáles y por qué, para meterlas a mano.
      if (r.descartadas?.length) {
        toast.warning(
          `${r.descartadas.length} fila(s) NO han entrado y hay que meterlas a mano con `
          + "+ Compra: "
          + r.descartadas.slice(0, 6).map((d) =>
              `${d.symbol} ${d.fecha} (${d.tipo} ${d.acciones} × ${d.precio})`).join(" · ")
          + (r.descartadas.length > 6 ? ` · y ${r.descartadas.length - 6} más` : "")
          + `. Motivo: ${r.descartadas[0]?.motivo || ""}`,
          { duration: 20000 });
      }
      qc.invalidateQueries({ queryKey: ["cartera"] });
      onCerrar();
    },
    // Un corte por tiempo NO significa que haya fallado: el servidor sigue trabajando y
    // suele terminar. Decir "no se pudo importar" a secas hace pensar que no entró nada,
    // cuando lo normal es que entrara todo. Pasó de verdad.
    onError: (e) => {
      const porTiempo = e?.code === "ECONNABORTED" || /timeout/i.test(e?.message || "");
      toast.error(porTiempo
        ? "Se ha agotado la espera, pero el servidor puede haber terminado igualmente. "
          + "Vuelve a subir el mismo fichero: te dirá cuántas hay ya importadas."
        : (e?.response?.data?.detail || "No se pudo importar"),
        { duration: porTiempo ? 15000 : 5000 });
    },
  });

  const pendientes = (previo?.productos || []).filter((p) => !mapeo[p.isin]);
  const ignorados = (previo?.productos || []).filter((p) => mapeo[p.isin] === IGNORAR);

  return (
    <div className="iv-panel iv-entra p-5 sm:p-6 space-y-4">
      <CabeceraForm titulo="Importar el CSV de DEGIRO" icono={FileUp} onCerrar={onCerrar}
                    nota="Fecha, precio, comisión y tipo de cambio reales: dejan de hacer falta estimaciones." />

      <p className="text-[13px] text-tinta-2 leading-relaxed max-w-[90ch]">
        En DEGIRO: <b>Actividad → Transacciones</b> → elige el periodo → <b>Exportar → CSV</b>.
        Trae la fecha, el precio, la comisión y el tipo de cambio <b>reales</b>, así que deja
        de hacer falta estimarlos.
        <br />
        Sube también el <b>Account.csv</b> (Actividad → Cuenta): es el único sitio donde
        están los <b>dividendos</b>, que no aparecen en el de transacciones. Se reconoce solo
        cuál es cuál. Subir cualquiera dos veces no duplica nada.
      </p>

      <input type="file" accept=".csv,text/csv"
             onChange={(e) => { setArchivo(e.target.files?.[0] || null); setPrevio(null); }}
             className="block w-full text-[13px] text-tinta-2 rounded-iv border border-dashed border-medio bg-tinta/[0.02] p-3 file:mr-3 file:h-9 file:px-3.5 file:rounded-[10px] file:border file:border-suave file:bg-tinta/[0.06] file:text-tinta file:text-[13px] file:font-medium hover:file:bg-tinta/[0.1] file:cursor-pointer" />

      {archivo && !previo && (
        <button onClick={() => leer.mutate()} disabled={leer.isPending}
                className={BOTON_PRINCIPAL}>
          {leer.isPending ? "Leyendo…" : "Leer el fichero"}
        </button>
      )}

      {previo && (
        <div className="space-y-3">
          {/* QUÉ fichero es, antes que cuántas líneas trae. Los dos exports de DEGIRO se
              llaman parecido y el de Cuenta (dividendos) se reconoce solo, pero esta
              cabecera lo llamaba "operaciones" igual: salía "131 operaciones · compras ·
              ventas · — de comisiones reales", con tres huecos donde iban los números,
              porque el resumen de dividendos no tiene esos campos. Parecía un fichero de
              transacciones raro y era otro fichero. */}
          {previo.tipo === "dividendos" ? (
            <div className="text-[12.5px] text-tinta-3 border-t border-suave pt-2">
              Este es el fichero de <b>Cuenta</b> (Account.csv), el de los dividendos — no
              el de Transacciones. <b>{previo.resumen?.total}</b> apunte(s) de{" "}
              {fecha(previo.resumen?.desde)} a {fecha(previo.resumen?.hasta)}:{" "}
              {previo.resumen?.cobros} cobro(s) y {previo.resumen?.retenciones} retención(es).
              {" "}Si lo que querías era añadir compras y ventas, exporta{" "}
              <b>Actividad → Transacciones</b>.
            </div>
          ) : (
            <div className="text-[12.5px] text-tinta-3 border-t border-suave pt-2">
              <b>{previo.resumen?.total}</b> operaciones ·{" "}
              {previo.resumen?.compras} compras · {previo.resumen?.ventas} ventas ·{" "}
              de {fecha(previo.resumen?.desde)} a {fecha(previo.resumen?.hasta)} ·{" "}
              {usd(previo.resumen?.comisiones)} de comisiones reales
            </div>
          )}

          {!!previo.errores?.length && (
            <div className="text-[12.5px] text-aviso">
              {previo.errores.length} línea(s) no se han entendido y quedan fuera:
              <ul className="list-disc ml-4">
                {previo.errores.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </div>
          )}

          {/* El emparejamiento. Solo se pregunta una vez por producto: el ISIN se guarda en
              la Cartera y la próxima importación ya no lo pide. */}
          <div>
            <p className="text-[12.5px] font-medium text-tinta-3 mb-2">
              ¿A qué acción corresponde cada producto?
            </p>
            <div className="space-y-1.5">
              {(previo.productos || []).map((p) => (
                <div key={p.isin} className="flex items-center gap-2 flex-wrap text-[13px]">
                  <span className="flex-1 min-w-0 truncate" title={p.isin}>{p.producto}</span>
                  <span className="text-[12.5px] text-tinta-3 iv-cifra">{p.operaciones} ops</span>
                  {/* Campo LIBRE con la Cartera como sugerencias, no un desplegable cerrado.
                      Un CSV con años de historial trae posiciones ya cerradas y valores que
                      se dejaron de seguir, y sus ventas son parte de lo ganado: exigir que
                      estén en la Cartera dejaría fuera justo el historial a recuperar. */}
                  <input
                    list="tickers-cartera"
                    value={mapeo[p.isin] === IGNORAR ? "" : (mapeo[p.isin] || "")}
                    disabled={mapeo[p.isin] === IGNORAR}
                    onChange={(e) => setMapeo((m) => ({ ...m, [p.isin]: e.target.value.toUpperCase() }))}
                    placeholder="ticker"
                    className={`w-28 ${inputMini}`} />
                  <label className="flex items-center gap-1 text-[12.5px] text-tinta-3 cursor-pointer"
                         title="Deja este producto fuera de la importación. Útil para ETFs o valores que no quieres seguir.">
                    <input type="checkbox"
                           checked={mapeo[p.isin] === IGNORAR}
                           onChange={(e) => setMapeo((m) => ({
                             ...m, [p.isin]: e.target.checked ? IGNORAR : "" }))} />
                    ignorar
                  </label>
                  {(p.symbol || p.ignorado) && (
                    <Chip title="Decidido en una importación anterior. Puedes cambiarlo si quieres.">
                      recordado
                    </Chip>
                  )}
                </div>
              ))}
            </div>
            <datalist id="tickers-cartera">
              {(previo.simbolos_conocidos || []).map((sy) => <option key={sy} value={sy} />)}
            </datalist>
            <p className="text-[12.5px] text-tinta-3 mt-2">
              Escribe el ticker. Los de tu Cartera salen como sugerencia al empezar a
              teclear, pero puedes poner cualquiera: si es una posición que ya cerraste, su
              ganancia entra igual en el historial aunque no la sigas.
              {" "}Marca <b>ignorar</b> lo que no quieras (ETFs, valores que no llevas).
              <br />
              <b>Ignorar no es definitivo:</b> vuelve a subir este mismo fichero cuando
              quieras y ponles ticker entonces. Lo ya importado no se duplica y lo ignorado
              entrará. Si dudas de alguno, ignóralo y sigue.
            </p>
            {!!pendientes.length && (
              <p className="text-[12.5px] text-aviso mt-1">
                Faltan <b>{pendientes.length}</b> por decidir: ponles ticker o márcalos como
                ignorar.
              </p>
            )}
          </div>

          {/* Reparar lo que ya está. Apagado por defecto y con el efecto escrito: reescribe
              apuntes existentes, y eso solo debe pasar cuando se pide. Hace falta porque
              saltar las repetidas —correcto para no duplicar— dejaba intacto lo que se
              importó mal: cuando el lector no reconocía la columna de AutoFX, cientos de
              operaciones entraron con comisión cero y reimportar no las arreglaba. */}
          <label className="flex items-start gap-2 mb-3 cursor-pointer">
            <input type="checkbox" checked={actualizar}
                   onChange={(e) => setActualizar(e.target.checked)}
                   className="mt-0.5 w-4 h-4 accent-marca shrink-0" />
            <span className="text-apoyo text-tinta-2 leading-snug">
              <b>Corregir las comisiones de las operaciones que ya estaban.</b> Reescribe la
              comisión de los apuntes que ya tienes con la del fichero. No toca precios,
              fechas ni acciones. Márcalo si tu realizado está inflado porque se importaron
              sin comisión.
            </span>
          </label>

          {/* Sustituir lo tecleado por lo del fichero. Es la salida del punto muerto: una
              fila tapada por un apunte tuyo no entra NUNCA —y mientras no entre, el CSV
              "no cubre" esas acciones y tampoco se pueden quitar los lotes de la foto—.
              Son la misma operación: coinciden fecha, acciones y precio al cuarto decimal.
              Lo único que cambia es que la del fichero trae la comisión y el tipo de cambio
              que te aplicaron de verdad, en vez de estimados. */}
          <label className="flex items-start gap-2 mb-3 cursor-pointer">
            <input type="checkbox" checked={sustituir}
                   onChange={(e) => setSustituir(e.target.checked)}
                   className="mt-0.5 w-4 h-4 accent-marca shrink-0" />
            <span className="text-apoyo text-tinta-2 leading-snug">
              <b>Sustituir mis apuntes por los del fichero.</b> Si tecleaste una operación
              que también viene en el CSV —misma fecha, mismas acciones, mismo precio—, se
              queda la del fichero, que trae la comisión y el tipo de cambio reales. Tu
              posición no cambia: entra una y se va la otra. Lo que no esté en el fichero no
              se toca.
            </span>
          </label>

          <button onClick={() => confirmar.mutate()}
                  disabled={confirmar.isPending || !!pendientes.length}
                  className={BOTON_PRINCIPAL}>
            {confirmar.isPending ? "Importando…"
              : ignorados.length
                ? `Importar (ignorando ${ignorados.length} producto(s))`
                : previo.tipo === "dividendos"
                  ? "Este fichero es el de dividendos, no el de transacciones"
                  : `Importar ${previo.resumen?.total || ""} operaciones`}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Los lotes vivos de una acción ────────────────────────────────────────────
// Contesta a "¿cuántas me quedan y de qué compra son?" ANTES de vender. Sin esto los lotes
// solo se veían dentro de una venta ya hecha, así que no había forma de comprobar lo que
// habías metido hasta que ya era tarde.
function LotesAbiertos({ symbol, metodo }) {
  const qc = useQueryClient();
  const { data, isPending } = useQuery({
    queryKey: ["cartera", "posicion", symbol],
    queryFn: () => api.cartera.posicion(symbol),
    staleTime: 30_000,
  });

  const borrar = useMutation({
    mutationFn: ({ id, forzar }) => api.cartera.borrarCompra(id, forzar),
    onSuccess: () => {
      toast.success("Compra borrada");
      qc.invalidateQueries({ queryKey: ["cartera", "historial"] });
      qc.invalidateQueries({ queryKey: ["cartera", "resumen"] });
      qc.invalidateQueries({ queryKey: ["cartera", "posicion"] });
    },
    // Un 409 NO es un fallo: es el servidor avisando de que ese lote sostiene ventas y
    // borrarlo las dejaría sin coste (su ganancia saldría hinchada). Se pregunta en vez de
    // tragárselo, porque a veces borrar es justo lo que quieres.
    onError: (e, vars) => {
      const aviso = e?.response?.status === 409 && e?.response?.data?.detail;
      if (aviso && window.confirm(`${aviso}\n\n¿Borrarla de todos modos?`)) {
        borrar.mutate({ id: vars.id, forzar: true });
        return;
      }
      if (!aviso) toast.error("No se pudo borrar");
    },
  });

  // La detección automática solo asigna nivel si el precio está a menos del 1,5%; una
  // compra real puede desviarse más (2 AAOI a 120,89 $ sobre un nivel de 118,90: 1,67%,
  // lote "fuera de niveles" y campanita sin apagar). Aquí se corrige a mano.
  const asignar = useMutation({
    mutationFn: ({ id, nivel }) => api.cartera.cambiarNivelCompra(id, nivel),
    onSuccess: () => {
      toast.success("Nivel actualizado — campanitas y precio del nivel al día");
      qc.invalidateQueries({ queryKey: ["cartera", "historial"] });
      qc.invalidateQueries({ queryKey: ["cartera", "resumen"] });
      qc.invalidateQueries({ queryKey: ["cartera", "posicion"] });
    },
    onError: () => toast.error("No se pudo asignar el nivel"),
  });

  if (isPending) {
    return (
      <div role="status" aria-label={`Cargando las compras de ${symbol}`} className="px-4 sm:px-5 py-4 border-t border-suave space-y-2.5">
        {[0, 1].map((i) => <span key={i} className="block h-3 w-2/3 rounded iv-esqueleto" />)}
      </div>
    );
  }

  const est = data?.[metodo];
  const abiertos = est?.abiertos || [];
  const divisa = data?.divisa || "USD";
  const compradas = (data?.compras || []).reduce((s, c) => s + (c.acciones || 0), 0);
  const vendidas = compradas - (est?.acciones_abiertas || 0);

  return (
    <div className="bg-tinta/[0.03] px-4 sm:px-5 pt-4 pb-3 border-t border-suave iv-entra">
      <p className="text-[13px] font-medium text-tinta-2 mb-2">
        Lo que te queda, por compra · {metodo.toUpperCase()}
        {vendidas > 0.0001 && (
          <span className="normal-case tracking-normal ml-2">
            (compraste {compradas}, vendiste {Math.round(vendidas * 1e6) / 1e6})
          </span>
        )}
      </p>

      {/* Por qué el latente no coincide con el del bróker aunque el precio y las acciones
          sean idénticos: el coste en euros sale del cambio del día de CADA compra, y si
          alguna no lleva su fecha real, ese cambio no es el que te aplicaron. Se enseña el
          cambio medio para poder compararlo con el del bróker en vez de adivinar. */}
      {/* El precio con el que se ha valorado, y el cierre anterior al lado. Es la única
          cifra de la fila que no sale de tus apuntes, y cuando el bróker enseña otra
          ganancia suele ser esto: en NFLX eran 81,78 $ contra 80,01 $, o sea 121,80 € de
          diferencia con el mismo coste, el mismo cambio y el mismo método. Si el precio de
          aquí coincide con el cierre anterior, es que la sesión no ha abierto o el dato se
          quedó atrás; si el del bróker coincide con él, el que va con retraso es el suyo. */}
      {!!abiertos.length && data?.precio_actual != null && (
        <p className="text-[12.5px] text-tinta-3 mb-1 leading-snug">
          Valorado a <b className="iv-cifra">{usd(data.precio_actual, divisa)}</b>
          {data.cierre_anterior != null && (
            <> · cierre anterior <span className="iv-cifra">{usd(data.cierre_anterior, divisa)}</span></>
          )}
          {data.estado_mercado && <> · {data.estado_mercado.toLowerCase()}</>}
        </p>
      )}

      {!!abiertos.length && data?.cambio_medio_compras && divisa !== "EUR" && (
        <p className="text-[12.5px] text-tinta-3 mb-2 leading-snug">
          Tu coste se pasó a euros a <b className="iv-cifra">{data.cambio_medio_compras}</b>{" "}
          {divisa}/€ de media
          {data.cambio_hoy && <> (hoy: <span className="iv-cifra">{data.cambio_hoy}</span>)</>}.
          {!!data.acciones_sin_csv && (
            <> De las {data.acciones_abiertas_total} acciones abiertas,{" "}
              <b>{data.acciones_sin_csv} no vienen del CSV</b>: llevan la fecha en que se
              dieron de alta, no la de la compra, así que su cambio tampoco es el de ese
              día y el coste en euros puede salir desviado. El precio y las acciones sí
              son correctos.</>
          )}
        </p>
      )}

      {!abiertos.length ? (
        <p className="text-[13px] text-tinta-3">
          No queda nada abierto de {symbol}: se ha vendido la posición entera.
        </p>
      ) : (
        <div className="mt-1 divide-y divide-suave">
          {abiertos.map((l) => (
            <div key={l.id} className="flex items-center gap-x-3 gap-y-1.5 flex-wrap text-[13px] py-2">
              <span className="iv-cifra text-tinta-3 w-20 shrink-0">{fecha(l.fecha)}</span>
              {!!l.tasa && divisa !== "EUR" && (
                <span className="iv-cifra text-[12.5px] text-tinta-3"
                      title={`Cambio con el que el coste de esta compra se pasó a euros. Es el del día de la fecha que tiene el lote; si esa fecha no es la de tu compra real, esta cifra tampoco lo es.`}>
                  @{Math.round(l.tasa * 1e4) / 1e4}
                </span>
              )}
              <span className="iv-cifra font-medium text-tinta">
                {l.acciones_abiertas} × {usd(l.precio, divisa)}
              </span>
              {l.acciones_abiertas !== l.acciones && (
                <span className="text-[12.5px] text-tinta-3">(de {l.acciones})</span>
              )}
              {/* El selector está SIEMPRE, no solo en los lotes sin nivel: equivocarse al
                  asignar es un clic, y sin poder reasignar la única salida era borrar la
                  compra y volver a meterla. Pasó de verdad con un nivel 4 puesto como 3. */}
              <span className="inline-flex items-center gap-1.5">
                {l.nivel
                  ? <Chip tono="nivel">{NIVEL_ETIQUETA[l.nivel] || l.nivel}</Chip>
                  : <Chip title="Esta compra no cae a menos del 1,5% de ninguno de tus niveles con precio. Si en realidad ES la compra de un nivel, asígnaselo aquí: ese nivel pasará a valer tu precio de compra y su campanita se apagará.">fuera de niveles</Chip>}
                <select value={l.nivel || ""} disabled={asignar.isPending}
                        onChange={(e) => asignar.mutate({ id: l.id, nivel: e.target.value || null })}
                        title="Cambiar el nivel de esta compra. El precio del nivel en la Cartera se actualizará al precio real de la compra, y las campanitas se recalcularán."
                        className="h-8 rounded-lg bg-tinta/[0.04] border border-suave px-2 text-[12.5px] text-tinta-2">
                  <option value="">{l.nivel ? "sin nivel" : "asignar nivel…"}</option>
                  {/* Los cinco, con precio o sin él: en una acción sin niveles esta
                      lista salía vacía y "asignar nivel…" no ofrecía nada que asignar. */}
                  {[1, 2, 3, 4, 5].map((i) => {
                    const clave = `nivel${i}`;
                    const puesto = (data?.niveles || []).find((n) => n.nivel === clave);
                    return (
                      <option key={clave} value={clave}>
                        Nivel {i}
                        {puesto ? ` · ${puesto.precio} ${divisa === "EUR" ? "€" : "$"}` : " · sin precio"}
                      </option>
                    );
                  })}
                </select>
              </span>
              {l.comision_estimada && (
                <Chip title="La comisión de esta compra es una estimación con la tarifa pública de DEGIRO, no una cifra de tu extracto.">
                  comisión estimada
                </Chip>
              )}
              {!l.tasa && (
                <Chip tono="aviso" title="Sin el cambio de esa fecha no se puede saber lo que ganas en euros cuando vendas estas acciones.">
                  sin tipo de cambio
                </Chip>
              )}
              <span className="ml-auto iv-cifra text-tinta-3">
                {l.coste_eur != null ? eur(l.coste_eur) : usd(l.coste_divisa, divisa)}
              </span>
              <button
                onClick={() => window.confirm(`¿Borrar la compra de ${l.acciones} ${symbol} del ${fecha(l.fecha)}?`) && borrar.mutate({ id: l.id })}
                aria-label={`Borrar la compra de ${l.acciones} ${symbol} del ${fecha(l.fecha)}`}
                className={`${BOTON_BORRAR} shrink-0`}>
                <Trash2 className="w-3.5 h-3.5" strokeWidth={1.9} aria-hidden="true" />
                borrar
              </button>
            </div>
          ))}
        </div>
      )}

      {/* El orden de consumo es la respuesta a "de qué nivel será la próxima venta". */}
      {abiertos.length > 1 && (
        <p className="text-[12.5px] text-tinta-3 mt-2 pt-2 border-t border-suave">
          Si vendes ahora, {metodo === "fifo" ? "FIFO" : "LIFO"} consumirá primero la compra
          del <b>{fecha(abiertos[0].fecha)}</b>
          {abiertos[0].nivel && <> ({NIVEL_ETIQUETA[abiertos[0].nivel] || abiertos[0].nivel})</>}
          {" "}a {usd(abiertos[0].precio, divisa)}.
        </p>
      )}
    </div>
  );
}

// ── Alta de operaciones ──────────────────────────────────────────────────────
function Campo({ label, ayuda, children }) {
  return (
    <label className="block">
      <span className="text-[12.5px] font-medium text-tinta-2 flex items-center gap-1">
        {label}{ayuda && <span title={ayuda} className="cursor-help opacity-60">ⓘ</span>}
      </span>
      {children}
    </label>
  );
}


// Qué lotes se van a consumir ANTES de guardar la venta. El método decide de qué compra
// —y por tanto de qué nivel— sale lo que vendes, y eso no es evidente: con FIFO, vender
// consume la compra más antigua aunque fuera la más cara. Verlo antes evita registrar una
// venta pensando que salía de otro sitio.
// Retrasa el valor hasta que se deja de escribir. Sin esto, cada TECLA del ticker montaba
// una queryKey nueva: teclear "MRVL" pedía M, MR, MRV y MRVL, y el backend salía a Finnhub
// por cada prefijo inexistente gastando cuota.
function useTicker(valor, ms = 400) {
  const limpio = (valor || "").trim().toUpperCase();
  const [lento, setLento] = React.useState(limpio);
  React.useEffect(() => {
    const t = setTimeout(() => setLento(limpio), ms);
    return () => clearTimeout(t);
  }, [limpio, ms]);
  return lento;
}

function VistaPreviaVenta({ symbol, acciones }) {
  const sym = useTicker(symbol);
  const n = aNumero(acciones);
  const { data } = useQuery({
    queryKey: ["cartera", "posicion", sym],
    queryFn: () => api.cartera.posicion(sym),
    enabled: sym.length >= 2,
    staleTime: 30_000,
    retry: false,
  });
  if (!sym || !data) return null;

  const divisa = data.divisa || "USD";
  const disponibles = data.fifo?.acciones_abiertas ?? 0;
  if (!disponibles) {
    return (
      <p className="text-[12.5px] text-aviso">
        No consta ninguna compra abierta de {sym}. Puedes registrar la venta igualmente, pero
        saldrá marcada como descuadrada hasta que metas la compra que falta.
      </p>
    );
  }

  // Se calcula igual que el backend: se van tomando lotes en el orden del método hasta
  // cubrir las acciones. Es una previsión, no un cálculo aparte — el número bueno lo da el
  // servidor al guardar.
  const simular = (metodo) => {
    const abiertos = data[metodo]?.abiertos || [];
    let queda = n, out = [];
    for (const l of abiertos) {
      if (queda <= 1e-9) break;
      const toma = Math.min(l.acciones_abiertas, queda);
      queda -= toma;
      out.push({ ...l, toma });
    }
    return out;
  };

  return (
    <div className="rounded-iv bg-tinta/[0.035] border border-suave px-4 py-3 space-y-1.5">
      <p className="text-[13px] font-medium text-tinta-2">
        Tienes <span className="iv-cifra text-tinta">{disponibles}</span> acciones de {sym}
      </p>
      {n > 0 && (
        <>
          {n > disponibles + 1e-9 && (
            <p className="text-[12.5px] text-aviso">
              Estás vendiendo más de las que constan compradas ({disponibles}). Se registrará
              igual y quedará marcada, por si lo que falta es meter una compra antigua.
            </p>
          )}
          {[["fifo", "FIFO", "es el que vale para Hacienda"], ["lifo", "LIFO", "solo referencia"]].map(([k, label, nota]) => {
            const sim = simular(k);
            if (!sim.length) return null;
            return (
              <p key={k} className="text-[12.5px] text-tinta-3 leading-snug">
                <b>{label}</b> <span className="opacity-70">({nota})</span> venderá{" "}
                {sim.map((l, i) => (
                  <span key={i}>
                    {i > 0 && " + "}
                    {Math.round(l.toma * 1e6) / 1e6} de la compra del {fecha(l.fecha)} a{" "}
                    {usd(l.precio, divisa)}
                    {l.nivel && ` (${NIVEL_ETIQUETA[l.nivel] || l.nivel})`}
                  </span>
                ))}
              </p>
            );
          })}
        </>
      )}
    </div>
  );
}

// Alta de varias compras de golpe, una por nivel.
//
// Es el caso normal de esta Cartera: se entra por niveles, con un número parecido de
// acciones en cada uno. Meterlas de una en una son cinco formularios, cinco veces el mismo
// ticker y una oportunidad de equivocarse en cada uno.
//
// Además resuelve algo que a mano es fácil colar mal: los lotes se crean del nivel MÁS CARO
// al más barato, que es el orden en que se van tocando al caer y por tanto el orden real de
// las compras. FIFO desempata por ese orden cuando no hay fechas distintas, así que crearlos
// al revés haría que la primera venta consumiera el nivel equivocado.
function FormularioPorNiveles({ onCerrar }) {
  const hoy = new Date().toISOString().slice(0, 10);
  const [symbol, setSymbol] = React.useState("");
  const [porNivel, setPorNivel] = React.useState({});
  // Fecha POR NIVEL. Los niveles no se compran el mismo día: se entra en uno cuando el
  // precio llega y hay liquidez, y entre uno y otro pueden pasar días, semanas o meses.
  // Con una sola fecha para todos, los euros de cada compra saldrían al tipo de cambio de
  // un día que no fue el suyo — y ese es justo el dato que hace exacta la ganancia en euros.
  const [fechaPorNivel, setFechaPorNivel] = React.useState({});
  // `fechaBase`, no `fecha`: llamarlo `fecha` TAPABA al formateador fecha() del módulo y
  // el title del chip de "N veces" reventaba el render entero — la pantalla de Ventas se
  // caía al ErrorBoundary y se perdía todo lo tecleado.
  const [fechaBase, setFechaBase] = React.useState(hoy);
  const [iguales, setIguales] = React.useState("");
  const [guardando, setGuardando] = React.useState(false);
  const [estimadas, setEstimadas] = React.useState(null);   // {nivel: {toques, ...}}
  const qc = useQueryClient();

  // `sym` inmediato para guardar y estimar (lo que pulsa el usuario debe usar lo que ve);
  // `symLento` solo para la CONSULTA, que es lo que gastaba una petición por tecla.
  const sym = symbol.trim().toUpperCase();
  const symLento = useTicker(symbol);
  const { data } = useQuery({
    queryKey: ["cartera", "posicion", symLento],
    queryFn: () => api.cartera.posicion(symLento),
    enabled: symLento.length >= 2,
    staleTime: 30_000,
    retry: false,
  });
  const niveles = data?.niveles || [];

  const aplicarIguales = (v) => {
    setIguales(v);
    const n = aNumero(v);
    if (n > 0) setPorNivel(Object.fromEntries(niveles.map((x) => [x.nivel, v])));
  };

  const filas = niveles
    .map((n) => ({ ...n, acciones: aNumero(porNivel[n.nivel]) || 0,
                   fecha: fechaPorNivel[n.nivel] || fecha }))
    .filter((n) => n.acciones > 0);
  const totalAcciones = filas.reduce((s, f) => s + f.acciones, 0);
  const totalCoste = filas.reduce((s, f) => s + f.acciones * f.precio, 0);

  // Rellena las fechas con el día en que el precio pasó por cada nivel. Es una estimación,
  // pero muchísimo mejor que la de hoy: comprando por niveles se entra cuando el precio
  // llega, y la fecha determina el tipo de cambio de esa compra.
  const estimarFechas = useMutation({
    mutationFn: () => api.cartera.fechasNiveles(sym),
    onSuccess: (r) => {
      const nuevas = {}, info = {};
      for (const n of r.niveles || []) {
        if (n.fecha) nuevas[n.nivel] = n.fecha;
        info[n.nivel] = n;
      }
      setFechaPorNivel((p) => ({ ...p, ...nuevas }));
      setEstimadas(info);
      const sinFecha = (r.niveles || []).filter((n) => !n.fecha).length;
      toast.success(sinFecha
        ? `Fechas estimadas. ${sinFecha} nivel(es) no aparecen en los últimos 2 años: ponlos a mano.`
        : "Fechas estimadas por cuándo el precio pasó por cada nivel. Revísalas.");
    },
    onError: () => toast.error("No se pudieron estimar las fechas"),
  });

  const guardar = async () => {
    if (!sym) return toast.error("Falta el ticker");
    if (!filas.length) return toast.error("Pon cuántas acciones compraste en algún nivel");
    setGuardando(true);
    try {
      // En serie y de más caro a más barato: el orden de creación es el que desempata
      // FIFO/LIFO cuando dos compras comparten fecha.
      for (const f of filas) {
        await api.cartera.comprar({
          symbol: sym, acciones: f.acciones, precio: f.precio,
          fecha: f.fecha, nivel: f.nivel,   // comisión vacía: se estima con la tarifa
          notas: `Alta por niveles (${f.etiqueta})`,
        });
      }
      toast.success(`${filas.length} compras registradas para ${sym}`);
      qc.invalidateQueries({ queryKey: ["cartera"] });
      onCerrar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "No se pudieron guardar todas");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="iv-panel iv-entra p-5 sm:p-6 space-y-4">
      <CabeceraForm titulo="Dar de alta las compras por niveles" icono={Layers} onCerrar={onCerrar}
                    nota="Una compra por nivel, cada una con su fecha y su comisión." />

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Campo label="Ticker">
          <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                 placeholder="MRVL" className={inputCls} autoFocus />
        </Campo>
        <Campo label="Fecha (para todas)"
               ayuda="Punto de partida: cada nivel puede llevar la suya abajo. La fecha decide el tipo de cambio con el que se calculan tus euros, así que cuanto más ajustada, más exacta la ganancia.">
          <input type="date" value={fechaBase}
                 onChange={(e) => { setFechaBase(e.target.value); setFechaPorNivel({}); }}
                 className={inputCls} />
        </Campo>
        <Campo label="Mismas en cada nivel"
               ayuda="Atajo para el caso normal: si en cada nivel compraste lo mismo, escríbelo una vez.">
          <input value={iguales} onChange={(e) => aplicarIguales(e.target.value)}
                 inputMode="decimal" placeholder="5" className={inputCls} />
        </Campo>
      </div>

      {sym && !!niveles.length && (
        <div className="flex items-center gap-2 flex-wrap">
          <button type="button" onClick={() => estimarFechas.mutate()}
                  disabled={estimarFechas.isPending}
                  className="h-9 rounded-[10px] px-3.5 text-[13px] font-medium bg-tinta/[0.06] text-tinta border border-suave hover:bg-tinta/[0.1] transition-colors duration-150 motion-reduce:transition-none disabled:opacity-60">
            {estimarFechas.isPending ? "Buscando…" : "Estimar las fechas por el precio"}
          </button>
          <span className="text-[12.5px] text-tinta-3">
            Busca el día en que el precio pasó por cada nivel. Útil si no las recuerdas.
          </span>
        </div>
      )}

      {!sym ? (
        <p className="text-[12.5px] text-tinta-3">Escribe un ticker para ver sus niveles.</p>
      ) : !niveles.length ? (
        <p className="text-[12.5px] text-aviso">
          {sym} no tiene niveles puestos en la Cartera. Ponlos allí primero, o registra las
          compras una a una con su precio.
        </p>
      ) : (
        <div className="space-y-1.5">
          {niveles.map((n) => (
            <div key={n.nivel} className="flex items-center gap-3 text-[13px]">
              <Chip tono="nivel">{n.etiqueta}</Chip>
              <span className="iv-cifra text-tinta-3 w-24">{usd(n.precio, data?.divisa)}</span>
              {n.comprado && <span className="text-[12.5px] text-tinta-3">campanita apagada</span>}
              <input
                value={porNivel[n.nivel] ?? ""}
                onChange={(e) => setPorNivel((p) => ({ ...p, [n.nivel]: e.target.value }))}
                inputMode="decimal" placeholder="acciones"
                className={`ml-auto w-24 ${inputMini}`} />
              <input
                type="date"
                value={fechaPorNivel[n.nivel] || fechaBase}
                onChange={(e) => setFechaPorNivel((p) => ({ ...p, [n.nivel]: e.target.value }))}
                title="Cuándo compraste ESTE nivel. Determina el tipo de cambio de esa compra."
                className={inputMini} />
              {/* Con varios toques la estimación es ambigua. Decirlo es la diferencia entre
                  una sugerencia y un dato inventado. */}
              {estimadas?.[n.nivel] && (
                estimadas[n.nivel].toques === 0
                  ? <Chip tono="aviso" title="El precio no ha pasado por este nivel en los últimos 2 años. Pon la fecha a mano.">sin datos</Chip>
                  : estimadas[n.nivel].toques > 1
                    ? <Chip tono="aviso" title={`El precio pasó por aquí ${estimadas[n.nivel].toques} veces (la última, el ${fecha(estimadas[n.nivel].ultima)}). Se propone la primera: cámbiala si compraste en otra.`}>
                        {estimadas[n.nivel].toques} veces
                      </Chip>
                    : <Chip title="El precio pasó por este nivel una sola vez: la fecha es fiable.">1 vez</Chip>
              )}
            </div>
          ))}
        </div>
      )}

      {!!filas.length && (
        <p className="text-[12.5px] text-tinta-3 border-t border-suave pt-2">
          Se crearán <b>{filas.length}</b> compras · <b>{totalAcciones}</b> acciones ·
          coste <b>{usd(totalCoste, data?.divisa)}</b> · precio medio{" "}
          <b>{usd(totalCoste / totalAcciones, data?.divisa)}</b>.
          {" "}Compruébalo contra lo que tenías en la Cartera antes de vender.
          {/* La comisión es lo que separa este formulario del de compra suelta, y hasta
              ahora no lo decía ninguno de los dos. Aquí cada nivel es una ORDEN distinta
              —por eso tiene su propia fecha— así que lleva su propia comisión, que es lo
              correcto: DEGIRO cobra los 2 € fijos por operación. Si todo fue UNA orden, ese
              reparto cobraría de más, y hay otro sitio para eso. */}
          {filas.length > 1 && (
            <>
              {" "}Se contará <b>una comisión por nivel</b> ({filas.length} en total),
              porque cada uno es una orden distinta. Si lo compraste TODO de una vez en una
              sola orden, ciérralo y usa <b>«+ Compra suelta»</b> marcando ahí varios
              niveles: allí la comisión es una sola y se reparte.
            </>
          )}
          {filas.some((f) => f.fecha !== filas[0].fecha)
            ? " Cada nivel se guardará con su fecha, así que los euros saldrán al cambio de cada día."
            : " Todos con la misma fecha: si los compraste en días distintos, ajústalos arriba — la fecha decide el tipo de cambio."}
        </p>
      )}

      <button onClick={guardar} disabled={guardando || !filas.length}
              className={BOTON_PRINCIPAL}>
        {guardando ? "Guardando…" : `Guardar ${filas.length || ""} compra(s)`}
      </button>
    </div>
  );
}

// Enseña la comisión que se va a aplicar ANTES de guardar. Sin esto, "se estima sola" es
// una promesa a ciegas: no se sabe cuánto se ha metido hasta abrir la operación después.
// La cuenta es la misma que hace el servidor, pero el número bueno lo pone él al guardar.
const COMISION_FIJA_EUR = 2.0;
const FX_AUTO_PCT = 0.0025;

function AvisoComision({ comision, acciones, precio }) {
  const { data: tasas } = useQuery({
    queryKey: ["cartera", "resumen"],
    queryFn: api.cartera.resumen,
    staleTime: 60_000,
    retry: false,
  });
  if (comision !== "" && comision != null) {
    return aNumero(comision) === 0
      ? <p className="text-[12.5px] text-tinta-3">Sin comisión: se registrará tal cual.</p>
      : null;
  }
  const bruto = (aNumero(acciones) || 0) * (aNumero(precio) || 0);
  const tasa = tasas?.tasas?.USD;
  if (!bruto || !tasa) {
    return (
      <p className="text-[12.5px] text-tinta-3">
        La comisión se estimará con la tarifa de DEGIRO: 2 € por operación + 0,25% de
        conversión de divisa. Pon un 0 si esta operación no te costó nada.
      </p>
    );
  }
  const est = COMISION_FIJA_EUR * tasa + bruto * FX_AUTO_PCT;
  return (
    <p className="text-[12.5px] text-tinta-3">
      Se aplicará una comisión estimada de <b>{usd(est)}</b> ={" "}
      {usd(COMISION_FIJA_EUR * tasa)} (2 € de comisión y tramitación) +{" "}
      {usd(bruto * FX_AUTO_PCT)} (0,25% de conversión de divisa).
      {" "}Si tienes la real en tu extracto, escríbela y manda la tuya.
    </p>
  );
}

// Precio a mano para un valor sin cotización en vivo (un ETF, otro mercado). Sin él la
// posición queda fuera del latente y del total y el "⚠ sin precio" no se va nunca. Solo
// rellena huecos: si el valor cotiza en vivo, manda la cotización.
function CeldaValorHoy({ p }) {
  const qc = useQueryClient();
  const [precio, setPrecio] = React.useState("");
  const mut = useMutation({
    mutationFn: ({ symbol, valor }) => api.cartera.precioManual(symbol, valor),
    onSuccess: (r) => {
      toast.success(r.precio
        ? `Precio manual de ${r.symbol}: ${r.precio}`
        : `Precio manual de ${r.symbol} quitado`);
      qc.invalidateQueries({ queryKey: ["cartera", "resumen"] });
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "No se pudo guardar el precio"),
  });

  if (p.valor_eur == null) {
    return (
      <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        <input value={precio} onChange={(e) => setPrecio(e.target.value)} inputMode="decimal"
               placeholder={`precio en ${p.divisa === "EUR" ? "€" : "$"}`}
               className={`w-28 text-right ${inputMini}`} />
        <button disabled={mut.isPending || !(aNumero(precio) > 0)}
                onClick={() => mut.mutate({ symbol: p.symbol, valor: aNumero(precio) })}
                className="text-[12.5px] underline text-tinta-3 disabled:opacity-50">
          poner
        </button>
      </span>
    );
  }
  return (
    <>
      {eur(p.valor_eur)}
      {p.precio_manual && (
        <div className="text-[12.5px] text-aviso cursor-pointer"
             title="Este valor sale de un precio que pusiste tú a mano, no de una cotización en vivo. Pincha para cambiarlo o quitarlo."
             onClick={(e) => {
               e.stopPropagation();
               const nuevo = window.prompt(
                 `Precio manual de ${p.symbol} (ahora ${p.precio_actual}). `
                 + "Pon el nuevo, o déjalo vacío para quitarlo:", p.precio_actual);
               if (nuevo !== null) mut.mutate({ symbol: p.symbol, valor: aNumero(nuevo) || 0 });
             }}>
          precio manual · cambiar
        </div>
      )}
    </>
  );
}

function FormularioOperacion({ tipo, onHecho, onCerrar }) {
  const hoy = new Date().toISOString().slice(0, 10);
  // `niveles` es una LISTA, no un nivel: una sola orden puede cruzar dos o tres cuando la
  // acción cae mucho. `reparto` guarda cuántas acciones van en cada uno cuando hay varios.
  const [f, setF] = React.useState({ symbol: "", acciones: "", precio: "", comision: "",
                                     fecha: hoy, notas: "", niveles: [], reparto: {} });
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const qc = useQueryClient();

  // Los niveles del valor, para poder decir de cuál es la compra. Con nivel elegido, el
  // precio de ese nivel en la Cartera se actualiza al precio REAL de la compra — que es lo
  // que antes había que acordarse de hacer a mano y se olvidaba.
  const symLento = useTicker(f.symbol);
  const { data: pos } = useQuery({
    queryKey: ["cartera", "posicion", symLento],
    queryFn: () => api.cartera.posicion(symLento),
    enabled: tipo === "compra" && symLento.length >= 2,
    staleTime: 30_000,
    retry: false,
  });

  const mut = useMutation({
    mutationFn: ({ _multinivel, ...payload }) =>
      (_multinivel ? api.cartera.comprarMultinivel(payload)
        : tipo === "compra" ? api.cartera.comprar(payload) : api.cartera.vender(payload)),
    onSuccess: (r) => {
      toast.success(tipo === "compra" ? "Compra registrada" : "Venta registrada");
      // Un nivel vendido entero reactiva su campanita solo. Decirlo aquí ahorra ir a la
      // Cartera a comprobar que ha pasado — que era justo la duda ("¿y las campanas?").
      if (tipo === "venta" && r?.campanas?.reactivadas?.length) {
        toast.info(
          `${r.campanas.reactivadas.join(" y ")} de ${r.symbol} vendido(s) entero(s) — `
          + "campana reactivada: volverá a avisarte si el precio cae ahí.",
          { duration: 10000 });
      }
      qc.invalidateQueries({ queryKey: ["cartera", "historial"] });
      qc.invalidateQueries({ queryKey: ["cartera", "resumen"] });
      qc.invalidateQueries({ queryKey: ["cartera", "posicion"] });
      onHecho?.();
      onCerrar();
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "No se pudo guardar"),
  });

  // Reparto sugerido: a partes iguales, y el primero se lleva el resto cuando no divide
  // exacto (13 en dos niveles son 7 y 6, no 6,5 y 6,5 — no existen medias acciones aquí).
  const repartoSugerido = React.useMemo(() => {
    const niveles = f?.niveles || [];
    const total = aNumero(f?.acciones) || 0;
    if (niveles.length < 2 || total <= 0) return {};
    const base = Math.floor(total / niveles.length);
    const out = {};
    niveles.forEach((n, i) => { out[n] = i === 0 ? total - base * (niveles.length - 1) : base; });
    return out;
  }, [f?.niveles, f?.acciones]);

  const repartoFinal = React.useMemo(() => {
    const out = {};
    for (const n of f?.niveles || []) {
      out[n] = aNumero((f?.reparto || {})[n]) ?? repartoSugerido[n] ?? 0;
    }
    return out;
  }, [f?.niveles, f?.reparto, repartoSugerido]);

  const sumaReparto = (f?.niveles || []).length > 1
    ? Object.values(repartoFinal).reduce((s, x) => s + (x || 0), 0) : null;

  const enviar = (e) => {
    e.preventDefault();
    const sym = f.symbol.trim().toUpperCase();
    // aNumero: en el móvil se teclea con COMA. Con Number, "560,67" era NaN y la
    // pantalla contestaba "el precio debe ser mayor que cero", que no es lo que pasaba.
    const n = aNumero(f.acciones), p = aNumero(f.precio);
    if (!sym) return toast.error("Falta el ticker");
    if (!(n > 0)) return toast.error("El número de acciones debe ser mayor que cero");
    if (!(p > 0)) return toast.error("El precio debe ser mayor que cero");
    // VACÍO y CERO no son lo mismo, y aquí se colapsaban los dos a 0. El servidor trata el
    // cero como una afirmación —"esta operación no me costó nada"— y por eso NO la estima,
    // que es justo lo que hay que hacer cuando alguien lo pone a propósito. Pero el campo
    // en blanco significa "no lo sé", y el propio formulario promete debajo que se estimará
    // sola. Enviando 0, esa promesa no se cumplía nunca: cada venta tecleada entraba a
    // coste cero y acababa en el aviso de "ventas registradas sin comisión", inflando la
    // ganancia realizada. La previsualización de al lado ya distinguía los dos casos; lo
    // que se enviaba, no.
    const vacia = f.comision == null || String(f.comision).trim() === "";
    const niveles = tipo === "compra" ? (f.niveles || []) : [];
    if (niveles.length > 1) {
      // Una orden repartida: tiene su propia ruta porque la comisión se cobra UNA vez y se
      // prorratea. Mandar dos compras sueltas cobraría los 2 € fijos de DEGIRO dos veces.
      if (Math.abs((sumaReparto || 0) - n) > 1e-6) {
        return toast.error(`Los niveles suman ${sumaReparto} y la compra son ${n}`);
      }
      return mut.mutate({
        _multinivel: true,
        symbol: sym, precio: p,
        reparto: niveles.map((nv) => ({ nivel: nv, acciones: repartoFinal[nv] })),
        ...(vacia ? {} : { comision: aNumero(f.comision) || 0 }),
        fecha: f.fecha || hoy, notas: f.notas || "",
      });
    }
    mut.mutate({
      symbol: sym, acciones: n, precio: p,
      ...(vacia ? {} : { comision: aNumero(f.comision) || 0 }),
      fecha: f.fecha || hoy, notas: f.notas || "",
      ...(tipo === "compra" && niveles.length === 1 ? { nivel: niveles[0] } : {}),
    });
  };

  return (
    <form onSubmit={enviar} className="iv-panel iv-entra p-5 sm:p-6 space-y-4">
      <CabeceraForm titulo={tipo === "compra" ? "Registrar una compra" : "Registrar una venta"}
                    icono={tipo === "compra" ? Plus : CircleDollarSign} onCerrar={onCerrar}
                    nota={tipo === "compra"
                      ? "Deja la comisión vacía y se estima con la tarifa de DEGIRO."
                      : "Antes de guardar verás de qué compras sale y cuánto margen libera."} />

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Campo label="Ticker">
          <input value={f.symbol} onChange={set("symbol")} placeholder="FN" className={inputCls} autoFocus />
        </Campo>
        <Campo label="Nº acciones">
          <input value={f.acciones} onChange={set("acciones")} inputMode="decimal" placeholder="5" className={inputCls} />
        </Campo>
        <Campo label={tipo === "compra" ? "Precio de compra" : "Precio de venta"}>
          <input value={f.precio} onChange={set("precio")} inputMode="decimal" placeholder="130.50" className={inputCls} />
        </Campo>
        <Campo label="Comisión"
               ayuda="Déjala VACÍA y se estima con la tarifa pública de DEGIRO: 2 € por operación más el 0,25% de conversión de divisa. Si la tienes en tu extracto, ponla y manda la tuya. Un 0 se respeta como 'no me costó nada'.">
          <input value={f.comision} onChange={set("comision")} inputMode="decimal"
                 placeholder="se estima sola" className={inputCls} />
        </Campo>
        <Campo label="Fecha"
               ayuda="Determina el tipo de cambio que se usa. Ponla bien o los euros saldrán de otro día.">
          <input type="date" value={f.fecha} onChange={set("fecha")} className={inputCls} />
        </Campo>
        <Campo label="Notas">
          <input value={f.notas} onChange={set("notas")} placeholder="opcional" className={inputCls} />
        </Campo>
        {/* Los CINCO niveles, siempre, tengan precio o no.
            Antes esta lista salía de `pos.niveles`, que solo trae los que ya tienen un
            precio puesto. En una acción recién comprada están los cinco vacíos, así que
            la lista venía vacía y el desplegable NO se dibujaba: no había forma de decir
            "esta compra es mi Nivel 1", que es justo cuando más falta hace.
            Manda el precio al que compraste: al elegir nivel, ese nivel de la Cartera
            pasa a valer tu precio de compra —lo escribas o no estuviera antes—. */}
        {/* VARIOS niveles, no uno. Cuando una acción cae mucho, una sola orden puede
            cruzar dos o tres niveles: 12 acciones que son 6 del Nivel 1 y 6 del 2. Con un
            desplegable de una opción había que mentir —elegir uno— o partir la compra a
            mano en dos formularios, y entonces DEGIRO cobra una comisión pero la web
            apuntaba dos. Aquí se marcan los que sean y se reparten las acciones. */}
        {tipo === "compra" && (
          <Campo label="¿De qué nivel es?"
                 ayuda="Marca uno o varios. El precio de cada nivel marcado pasará a ser tu precio real de compra, con su campanita apagada. Si marcas más de uno, di cuántas acciones van en cada uno: se guardan como lotes separados, que es lo que son, y la comisión se reparte entre ellos en vez de cobrarse dos veces. Sin marcar nada, el nivel se detecta solo si el precio cae a menos del 1,5% de uno que ya tenga precio.">
            <div className="flex flex-wrap gap-1.5">
              {[1, 2, 3, 4, 5].map((i) => {
                const clave = `nivel${i}`;
                const puesto = (pos?.niveles || []).find((n) => n.nivel === clave);
                const moneda = pos?.divisa === "EUR" ? "€" : "$";
                const marcado = (f.niveles || []).includes(clave);
                return (
                  <button key={clave} type="button"
                          onClick={() => setF((p) => {
                            const ya = p.niveles || [];
                            return { ...p, niveles: ya.includes(clave)
                              ? ya.filter((x) => x !== clave) : [...ya, clave].sort() };
                          })}
                          title={puesto
                            ? `Ahora vale ${puesto.precio} ${moneda}${puesto.comprado ? " · ya comprado" : ""}`
                            : "Sin precio todavía: quedará fijado con tu compra"}
                          aria-pressed={marcado}
                          className={`iv-cifra h-10 min-w-[44px] text-[13px] rounded-lg px-2.5 border transition-colors duration-150 motion-reduce:transition-none ${marcado
                            ? "bg-marca/15 text-marca border-marca/50 font-semibold"
                            : "bg-tinta/[0.03] border-suave text-tinta-3 hover:text-tinta hover:bg-tinta/[0.06]"}`}>
                    N{i}
                  </button>
                );
              })}
              {(f.niveles || []).length > 0 && (
                <button type="button" onClick={() => setF((p) => ({ ...p, niveles: [] }))}
                        className="text-[12.5px] text-tinta-3 underline px-1">
                  quitar
                </button>
              )}
            </div>
          </Campo>
        )}
      </div>

      {/* El reparto, solo cuando hay más de un nivel. Se prerrellena a partes iguales
          porque es el caso normal, pero se puede corregir: entrar 8 en uno y 4 en otro es
          tan legítimo como 6 y 6, y adivinarlo mal sería peor que preguntarlo. */}
      {tipo === "compra" && (f.niveles || []).length > 1 && (
        <div className="rounded-iv bg-tinta/[0.035] border border-suave px-4 py-3 space-y-2">
          <p className="text-[12.5px] font-medium text-tinta-3">
            ¿Cuántas acciones en cada nivel?
          </p>
          <div className="flex flex-wrap gap-2">
            {f.niveles.map((clave) => (
              <label key={clave} className="flex items-center gap-1.5">
                <span className="text-[12.5px] text-tinta-2 iv-cifra">
                  {NIVEL_ETIQUETA[clave] || clave}
                </span>
                <input value={(f.reparto || {})[clave] ?? ""}
                       onChange={(e) => setF((p) => ({
                         ...p, reparto: { ...(p.reparto || {}), [clave]: e.target.value } }))}
                       inputMode="decimal" placeholder={repartoSugerido[clave] ?? ""}
                       className={`w-20 ${inputMini}`} />
              </label>
            ))}
          </div>
          {sumaReparto != null && aNumero(f.acciones) > 0
            && Math.abs(sumaReparto - aNumero(f.acciones)) > 1e-6 && (
            <p className="text-[12.5px] text-aviso">
              Los niveles suman {sumaReparto} y la compra son {aNumero(f.acciones)}.
              Tienen que cuadrar.
            </p>
          )}
        </div>
      )}

      {tipo === "compra" && (
        <p className="text-[12.5px] text-tinta-3">
          {(f.niveles || []).length > 1
            ? `Se guardarán ${f.niveles.length} lotes, uno por nivel, y cada uno de esos niveles pasará a valer tu precio real de compra${f.precio ? ` (${f.precio})` : ""}. Se cobra UNA sola comisión y se reparte entre ellos, porque es una sola orden. Si en realidad fueron compras de días distintos, usa «+ Compras por niveles»: allí cada una lleva su fecha y su comisión.`
            : (f.niveles || []).length === 1
            ? `El ${NIVEL_ETIQUETA[f.niveles[0]] || f.niveles[0]} de la Cartera pasará a valer tu precio real de compra${f.precio ? ` (${f.precio})` : ""}, y su campanita se apagará sola.`
            : "El nivel se detecta solo si el precio cae a menos del 1,5% de alguno de tus niveles; si compraste algo desviado, márcalo arriba y el precio del nivel en la Cartera se actualizará al tuyo."}
        </p>
      )}

      {tipo === "venta" && <VistaPreviaVenta symbol={f.symbol} acciones={f.acciones} />}
      {/* ANTES de confirmar, no después: la pregunta que resuelve —"¿esto me libera
          margen o no?"— solo sirve mientras la venta todavía se puede no hacer. */}
      {tipo === "venta" && f.symbol.trim() && (
        <RiesgoVenta symbol={f.symbol} acciones={aNumero(f.acciones) || undefined} />
      )}

      <AvisoComision comision={f.comision} acciones={f.acciones} precio={f.precio} />

      <button type="submit" disabled={mut.isPending}
              className={BOTON_PRINCIPAL}>
        {mut.isPending ? "Guardando…" : tipo === "compra" ? "Guardar compra" : "Guardar venta"}
      </button>
    </form>
  );
}

// ── Pantalla ─────────────────────────────────────────────────────────────────
export default function VentasView() {
  const qc = useQueryClient();
  // El método NO es solo una vista: gobierna qué lotes quedan vivos, tu precio medio y qué
  // campanitas se encienden. Por eso se guarda en el servidor y cambiarlo recalcula todo,
  // en vez de ser un estado local que solo afecta a lo que se pinta.
  //
  // Cuál reproduce lo que ves en tu bróker es una pregunta empírica: si al vender tu precio
  // medio BAJA, tu bróker quita las compras más antiguas (FIFO); si SUBE, las más recientes
  // (LIFO). De ahí que se pueda cambiar sin tocar código.
  const { data: ajustes } = useQuery({
    queryKey: ["cartera", "ajustes"],
    queryFn: api.cartera.ajustes,
    staleTime: 60_000,
  });
  const metodo = ajustes?.metodo_gestion || "lifo";
  // Para distinguir "esta compra no cae en ningún nivel" de "esta acción aún no tiene
  // niveles". Reutiliza el caché compartido de /signals, no pide nada nuevo.
  const { data: entradas } = useSignals();
  const sinNiveles = React.useMemo(() => simbolosSinNiveles(entradas), [entradas]);
  const cambiarMetodo = useMutation({
    mutationFn: (m) => api.cartera.guardarMetodo(m.toUpperCase()),
    onSuccess: (r) => {
      toast.success(`Método cambiado a ${r.metodo_gestion.toUpperCase()}. `
        + `${r.posiciones_recalculadas} posición(es) recalculadas.`);
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
    onError: () => toast.error("No se pudo cambiar el método"),
  });
  const setMetodo = (m) => cambiarMetodo.mutate(m);

  // Dos pasos: primero se pregunta qué tocaría, se enseña, y solo si dices que sí se
  // escribe. Reescribir apuntes del usuario sin que vea antes el alcance no es aceptable,
  // por muy claro que esté el fallo que los dejó así.
  // `incluirCsv` añade las que vinieron del fichero. Va por el mismo camino y con el
  // mismo aviso porque es la misma escritura; lo que cambia es que ahí el cero SÍ tiene
  // huella, y hay que decirlo en la pregunta para que se elija sabiéndolo.
  const repararComisiones = useMutation({
    mutationFn: async (incluirCsv = false) => {
      const previo = await api.cartera.estimarComisiones(false, incluirCsv);
      const n = previo.compras + previo.ventas;
      if (!n) {
        toast.success("No hay nada que estimar: todo tiene ya su comisión.");
        return null;
      }
      // EL DESGLOSE POR ORIGEN VA EN LA PREGUNTA, no solo el total. Con «8 apuntes, 16 €»
      // y nada más, alguien que venía a arreglar 2 ventas no puede saber qué está
      // aprobando — y los dos grupos ni siquiera merecen la misma confianza.
      const linea = (g, que) =>
        g.n ? `· ${g.n} ${que} (${g.compras} compra(s) y ${g.ventas} venta(s)), `
              + `unos ${g.eur} €\n`
            : "";
      const ok = window.confirm(
        `Se va a poner la comisión estimada (2 € + 0,25% de AutoFX) a ${n} apunte(s) `
        + `que están a cero, por unos ${previo.total_eur} € en total:\n\n`
        + linea(previo.a_mano, "tecleados a mano")
        + linea(previo.del_csv, "que vinieron del CSV")
        + "\nQuedarán marcados como ESTIMADOS.\n\n"
        + (previo.del_csv?.n
            ? "EN LAS DEL CSV EL CERO LLEGÓ CON EL FICHERO, así que solo tiene sentido "
              + "si aquel CSV se importó sin reconocer las columnas de comisión. Si "
              + "alguna de esas operaciones de verdad fue gratis, esto le pone un coste "
              + "que no tuvo. Las tecleadas a mano son otra cosa: ahí el cero es un "
              + "hueco que dejó el formulario, no algo que nadie afirmara."
            : "Lo que vino del CSV no se toca.")
        + "\n\n¿Continuar?");
      return ok ? api.cartera.estimarComisiones(true, incluirCsv) : null;
    },
    onSuccess: (r) => {
      if (!r) return;
      toast.success(`${r.compras} compra(s) y ${r.ventas} venta(s) actualizadas · `
        + `${r.total_eur} € de comisiones que faltaban`, { duration: 10000 });
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
    onError: () => toast.error("No se pudieron estimar las comisiones"),
  });

  // Borrar la copia manual de una compra duplicada. `forzar` porque la posición tiene
  // ventas registradas y el borrado normal se niega para no dejarlas sin coste; aquí es
  // justo lo contrario: son acciones que nunca existieron y estaban cubriendo ventas que
  // no les correspondían.
  const borrarDuplicada = useMutation({
    mutationFn: (id) => api.cartera.borrarCompra(id, true),
    onSuccess: () => {
      toast.success("Copia borrada. La del CSV se queda con su precio y su comisión reales.");
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
    onError: () => toast.error("No se pudo borrar la copia"),
  });
  const [form, setForm] = React.useState(null);   // "compra" | "venta" | null
  const [abierta, setAbierta] = React.useState(null);   // símbolo desplegado en la tabla
  const [verTodas, setVerTodas] = React.useState(false);   // historial completo o últimas 15
  // Valorar lo abierto como el bróker (media ponderada) o por tu método (FIFO/LIFO). No es
  // que una esté mal: lo que FIFO/LIFO se apuntan de más en el latente ya se lo apuntaron
  // en lo realizado. Se recuerda porque es una preferencia, no un vistazo puntual.
  // La preferencia la comparte la portada: ver `lib/preferencias`.
  const [comoBroker, setComoBroker] = React.useState(leerComoBroker);
  const alternarBroker = () => setComoBroker((v) => {
    guardarComoBroker(!v);
    return !v;
  });
  const [verExplicacion, setVerExplicacion] = React.useState(false);   // texto del método

  const { data: hist, isPending: cargandoHist, isError: errorHist, refetch: reintentarHist } = useQuery({
    queryKey: ["cartera", "historial"],
    queryFn: api.cartera.historial,
    staleTime: 60_000,
  });
  const { data: resumen } = useQuery({
    queryKey: ["cartera", "resumen"],
    queryFn: api.cartera.resumen,
    staleTime: 60_000,
  });
  const { data: divs } = useQuery({
    queryKey: ["cartera", "dividendos"],
    queryFn: api.cartera.dividendos,
    staleTime: 60_000,
    retry: false,
  });

  const borrar = useMutation({
    mutationFn: (v) => api.cartera.borrarVenta(v.id),
    onSuccess: () => {
      toast.success("Venta borrada");
      qc.invalidateQueries({ queryKey: ["cartera", "historial"] });
      qc.invalidateQueries({ queryKey: ["cartera", "resumen"] });
      qc.invalidateQueries({ queryKey: ["cartera", "posicion"] });
    },
    onError: () => toast.error("No se pudo borrar"),
  });

  const importar = useMutation({
    mutationFn: (reemplazar) => api.cartera.importar(!!reemplazar),
    onSuccess: (r) => {
      if (!r.creados) {
        toast.info("No había posiciones nuevas que importar");
      } else if (r.estimados?.length) {
        // Se avisa por separado de lo estimado: con tres o más niveles comprados hay
        // infinitos repartos que dan el mismo precio medio, y el reparto elegido cambia la
        // ganancia de cada venta futura. Callarlo lo convertiría en un dato inventado.
        toast.warning(
          `${r.creados} posición(es) importadas. Revisa el reparto de ${r.estimados.join(", ")}: ` +
          "tienen tres o más niveles comprados y el reparto entre ellos es una estimación.",
          { duration: 12000 });
      } else {
        toast.success(`${r.creados} posición(es) importadas, con sus lotes por nivel`);
      }
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
  });

  // La foto de la Cartera y el CSV de DEGIRO cuentan LAS MISMAS acciones; con ambos en el
  // libro cada posición sale al doble (24 RDDT en pantalla con 12 en el bróker). Esto quita
  // la foto donde el CSV ya cubre el símbolo y deja la versión con fechas y precios reales.
  const quitarDup = useMutation({
    mutationFn: api.cartera.quitarDuplicados,
    onSuccess: (r) => {
      // Un símbolo que el CSV solo cubre a medias NO se toca: borrar su foto dejaría la
      // posición corta. Se dice cuál y con qué cifras para poder subir el CSV completo.
      if (r.insuficientes?.length) {
        toast.warning(
          "No se ha tocado " + r.insuficientes.map((x) =>
            `${x.symbol} (el CSV trae ${x.en_el_csv} acciones y la foto ${x.en_la_foto})`).join(", ")
          + ". Vuelve a exportar el Transactions.csv con TODO el histórico y súbelo antes de "
          + "quitar duplicados ahí.", { duration: 20000 });
      }
      if (!r.borrados) {
        toast.info("No había lotes duplicados que quitar");
      } else {
        toast.success(
          `${r.borrados} lote(s) duplicados quitados de ${r.simbolos.join(", ")}. ` +
          "Compara ahora las acciones con tu bróker.", { duration: 12000 });
      }
      qc.invalidateQueries({ queryKey: ["cartera", "historial"] });
      qc.invalidateQueries({ queryKey: ["cartera", "resumen"] });
      qc.invalidateQueries({ queryKey: ["cartera", "posicion"] });
    },
    onError: () => toast.error("No se pudieron quitar los duplicados"),
  });

  // El realizado también obedece al interruptor: enseñar el total por LIFO debajo de un
  // botón que dice «como en DEGIRO» es mezclar dos métodos en la misma pantalla.
  const tot = (comoBroker && hist?.resumen?.ponderada?.ganancia_eur != null)
    ? hist.resumen.ponderada
    : hist?.resumen?.[metodo];
  const ventas = hist?.items || [];
  const realizado = tot?.ganancia_eur;
  const latenteBroker = resumen?.latente_ponderada_eur;
  // El latente TIENE que ir en la misma base que el realizado. Lo que un método se apunta
  // de más en lo realizado, el otro se lo guarda en el latente; sumar el realizado de uno
  // con el latente del otro da un Total que no es de nadie. Y esa es justo la propiedad
  // que hace útil el Total: como los dos lados van en la misma base, sale el MISMO número
  // con el interruptor puesto o quitado. Si algún día no saliera, es que hay un fallo.
  const usaPmp = comoBroker && latenteBroker != null
    && hist?.resumen?.ponderada?.ganancia_eur != null;
  const latente = usaPmp ? latenteBroker : resumen?.latente_eur;
  // El Total de «Lo que tienes abierto», sumado fila a fila con el mismo método que ellas.
  const totales = totalesAbiertas(resumen?.posiciones, comoBroker);
  // Los dividendos entran en el TOTAL —son dinero cobrado— pero se enseñan en su propia
  // cifra y nunca dentro de "Realizado". Fiscalmente son rendimientos del capital
  // mobiliario, no ganancias patrimoniales: van a casillas distintas de la declaración, y
  // mezclarlos daría un número que no sirve para rellenar ninguna de las dos.
  const dividendos = divs?.neto_eur ?? null;
  // Intereses del saldo en negativo y conectividad, del Account.csv. Llegan YA en negativo,
  // así que sumarlos resta. Van en el total porque el bróker también los descuenta del
  // suyo: sin ellos las dos cifras no pueden coincidir nunca.
  const costes = divs?.costes_eur ?? null;
  const total = (realizado != null || latente != null || dividendos != null)
    ? (realizado || 0) + (latente || 0) + (dividendos || 0) + (costes || 0) : null;

  // ── Rediseño v2 ────────────────────────────────────────────────────────────
  // Las tres listas (ventas, lo abierto, por acción) compiten por el mismo hueco: en
  // pestañas en vez de apiladas, porque con 190 ventas la tabla de posiciones quedaba a
  // varias pantallas. La pestaña elegida se recuerda, como antes cada plegable.
  const [pestana, setPestanaEstado] = React.useState(() => {
    try { return window.localStorage.getItem("ventas.pestana") || "ventas"; } catch { return "ventas"; }
  });
  const setPestana = (v) => {
    setPestanaEstado(v);
    try { window.localStorage.setItem("ventas.pestana", v); } catch { /* privado */ }
  };
  const [verAyudaTotal, setVerAyudaTotal] = React.useState(false);
  const [verAyudaEuro, setVerAyudaEuro] = React.useState(false);

  const hayAbierto = !!resumen?.posiciones?.length;
  const hayPorAccion = !!hist?.por_symbol?.length;
  const pestanas = [
    { valor: "ventas", cuenta: ventas.length,
      etiqueta: <><span className="sm:hidden">Ventas</span><span className="hidden sm:inline">Historial de ventas</span></> },
    hayAbierto && { valor: "abierto", cuenta: resumen.posiciones.length,
      etiqueta: <><span className="sm:hidden">Abierto</span><span className="hidden sm:inline">Lo que tienes abierto</span></> },
    hayPorAccion && { valor: "accion", cuenta: hist.por_symbol.length, etiqueta: "Por acción" },
  ].filter(Boolean);
  const vista = pestanas.some((p) => p.valor === pestana) ? pestana : "ventas";

  // Las ventas visibles, agrupadas por mes: el ojo encuentra «lo de octubre» sin leer
  // fechas. Solo agrupa; no suma nada nuevo.
  const visibles = verTodas ? ventas : ventas.slice(0, 15);
  const meses = [];
  for (const v of visibles) {
    const k = mesDe(v.fecha);
    if (!meses.length || meses[meses.length - 1].k !== k) meses.push({ k, items: [] });
    meses[meses.length - 1].items.push(v);
  }

  const sospechosas = (resumen?.posiciones || [])
    .filter((p) => p.acciones_sin_csv > 0)
    .sort((a, b) => (b.coste_eur || 0) - (a.coste_eur || 0));
  // Barra de «Por acción»: la escala es la mayor ganancia o pérdida en euros.
  const maxPorAccion = Math.max(1, ...(hist?.por_symbol || []).map((s) => Math.abs(s.ganancia_eur ?? 0)));

  const metodoRealizado = comoBroker && hist?.resumen?.ponderada?.ganancia_eur != null
    ? "media ponderada" : metodo.toUpperCase();

  return (
    // El mismo lienzo que el resto de pantallas (App.js no envuelve esta ruta).
    <div className="max-w-[1440px] mx-auto px-4 sm:px-8 py-5 sm:py-8 iv-entra space-y-6 sm:space-y-8">
      {/* ── Titular ─────────────────────────────────────────────────────────── */}
      <header className="flex flex-col xl:flex-row xl:items-end xl:justify-between gap-x-8 gap-y-5">
        <div className="min-w-0">
          <p className="text-[13px] text-tinta-3 flex items-center gap-1.5">
            Gestionar <ChevronRight className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" /> Operaciones
          </p>
          <h1 className="iv-verbo text-tinta mt-2">Ventas y ganancias</h1>
          <p className="text-[14.5px] text-tinta-2 mt-2.5 max-w-[58ch] leading-relaxed">
            Lo que llevas ganado de verdad, en euros, con el tipo de cambio de cada operación.
          </p>
        </div>
        {/* Solo UNA acción brilla: registrar una venta, la que mueve dinero y por la que
            se viene a esta pantalla. Las otras tres son secundarias; la que está abierta
            se marca. En el móvil, la principal ocupa la primera fila entera. */}
        <div className="grid grid-cols-2 sm:flex sm:flex-wrap gap-2 shrink-0" role="group" aria-label="Registrar operaciones">
          {[
            ["degiro", "Importar CSV", FileUp],
            ["niveles", "Compras por niveles", Layers],
            ["compra", "Compra suelta", Plus],
          ].map(([id, texto, Icono]) => (
            <Boton key={id} variante="secundario" onClick={() => setForm(id)} aria-pressed={form === id}
                   className={`h-10 sm:h-9 ${id === "degiro" ? "col-span-2 sm:col-span-1" : ""} ${form === id ? "bg-marca/10 border-marca/40 text-marca hover:bg-marca/15" : ""}`}>
              <Icono className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" />
              <span>{texto}{id === "degiro" && " de DEGIRO"}</span>
            </Boton>
          ))}
          <Boton onClick={() => setForm("venta")} aria-pressed={form === "venta"}
                 className="h-11 sm:h-9 col-span-2 order-first sm:order-none">
            <CircleDollarSign className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" />
            Registrar venta
          </Boton>
        </div>
      </header>

      {form === "degiro"
        ? <ImportarDegiro onCerrar={() => setForm(null)} />
        : form === "niveles"
          ? <FormularioPorNiveles onCerrar={() => setForm(null)} />
          : form && <FormularioOperacion tipo={form} onCerrar={() => setForm(null)} />}

      {/* ── Héroe · el resultado, y de dónde sale ─────────────────────────────
          Realizado y latente van SEPARADOS: uno está en tu cuenta y el otro puede
          evaporarse mañana. La cascada lo dice sin palabras: cada sumando es un tramo de
          barra que empieza donde acabó el anterior, y el último acaba en el Total.
          A la derecha, el método: es lo que reparte el resultado entre realizado y
          latente, así que vive junto a las cifras que mueve. */}
      <section className="iv-panel relative overflow-hidden" aria-labelledby="ops-resultado">
        <span aria-hidden="true"
              className="pointer-events-none absolute -top-36 -left-28 w-[560px] h-[320px] rounded-full bg-marca/[0.08] blur-3xl" />
        <div className="relative grid lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="p-5 sm:p-7 min-w-0">
            <CabeceraBloque icono={Scale} como="h2" id="ops-resultado"
                            derecha={
                              <button type="button" onClick={() => setVerAyudaTotal((a) => !a)}
                                      aria-expanded={verAyudaTotal} aria-label="Qué significa Total"
                                      className={`inline-flex items-center gap-1.5 h-8 px-2.5 -mr-2.5 rounded-lg text-[12.5px] transition-colors duration-150 motion-reduce:transition-none hover:bg-tinta/[0.06] ${verAyudaTotal ? "text-marca" : "text-tinta-3 hover:text-tinta"}`}>
                                <span className="hidden sm:inline">¿Qué incluye?</span>
                                <CaretDown size={12} weight="bold" aria-hidden="true"
                                           className={`transition-transform duration-200 ease-salida motion-reduce:transition-none ${verAyudaTotal ? "rotate-180" : ""}`} />
                              </button>
                            }>
              Total · tu resultado en esta cuenta
            </CabeceraBloque>
            {/* El tamaño se ajusta al ancho para que siete cifras quepan sin desbordar. */}
            <p className={`iv-cifra-hero text-[clamp(40px,11vw,64px)] lg:text-[clamp(44px,4.4vw,64px)] mt-4 break-words ${tono(total)}`}>
              <CifraHeroe valor={total} />
            </p>
            <p className="mt-3 text-[13px] text-tinta-3">
              Todo junto ·{" "}
              {[
                "realizado + latente",
                dividendos != null ? "+ dividendos" : null,
                costes != null ? "+ costes" : null,
              ].filter(Boolean).join(" ")}
            </p>
            {verAyudaTotal && (
              <p className="mt-3 text-[13px] text-tinta-2 leading-relaxed max-w-[80ch] rounded-iv bg-tinta/[0.035] px-3.5 py-3">
                Todo lo que llevas ganado o perdido en esta cuenta: lo realizado en ventas, lo
                latente de lo que sigue abierto, los dividendos cobrados y los costes. NO cambia
                con el método ni con el interruptor de DEGIRO: FIFO, LIFO y media ponderada
                reparten lo mismo de otra forma entre realizado y latente, pero suman igual. Si
                alguna vez cambia, es un fallo.
              </p>
            )}

            <Cascada className="mt-6" formato={eur} pasos={[
              {
                id: "realizado", etiqueta: "Realizado", significa: "Lo que ya cobraste al vender",
                valor: realizado, marca: true,
                // n_ventas cuelga del resumen, no del método: el número de ventas es el
                // mismo se mire con FIFO o con LIFO. Leerlo de dentro del método daba
                // siempre 0, o sea "no has vendido nada" con 148 ventas en la lista.
                // El descuadre va EN la fila: si hay acciones vendidas sin compra
                // registrada, salen con coste CERO y esta cifra está hinchada en hasta esos
                // euros. Sin el aviso, el número gordo se lee como bueno.
                sub: [
                  `${hist?.resumen?.n_ventas ?? 0} venta(s) · ${metodoRealizado}`,
                  hist?.resumen?.sin_cubrir_acciones
                    ? `${hist.resumen.sin_cubrir_acciones} acción(es) vendidas sin compra registrada`
                      + ` (${(hist.resumen.sin_cubrir_por_symbol || []).map((s) => s.symbol).join(", ")})`
                      + ` — hasta ${eur(hist.resumen.sin_cubrir_eur_aprox)} de esta cifra pueden sobrar`
                      + (hist.resumen.sin_cubrir_sin_tasa
                          ? `, y ${hist.resumen.sin_cubrir_sin_tasa} más sin tipo de cambio, sin contar`
                          : "")
                    : null,
                ].filter(Boolean).join(" · "),
                ayuda: "Ganancia de las ventas ya hechas, con el tipo de cambio del día de cada compra y de cada venta. Es dinero que ya está en tu cuenta. Cambia según el método: mira la etiqueta de debajo.",
                // El efecto del euro está DENTRO del realizado: no es un sumando más, así
                // que no lleva barra propia. Va colgando de su fila.
                extra: tot?.efecto_divisa_eur != null && Math.abs(tot.efecto_divisa_eur) >= 0.01 ? (
                  <div className="ml-3 pl-3 border-l border-medio">
                    <p className="flex items-center gap-2 flex-wrap text-[12.5px]">
                      <span className="text-tinta-2">Efecto del euro</span>
                      <span className={`iv-cifra font-medium ${tono(tot.efecto_divisa_eur)}`}>{eur(tot.efecto_divisa_eur)}</span>
                      <span className="text-tinta-3">· incluido en el realizado</span>
                      <button type="button" onClick={() => setVerAyudaEuro((a) => !a)} aria-expanded={verAyudaEuro}
                              aria-label="Qué significa Efecto del euro"
                              className={`${ENLACE} text-[12.5px]`}>
                        {verAyudaEuro ? "ocultar" : "qué es"}
                      </button>
                    </p>
                    {verAyudaEuro && (
                      <p className="text-[12.5px] text-tinta-2 mt-1.5 leading-relaxed max-w-[70ch]">
                        Cuánto de tu resultado es el euro y no la acción: cuánto de tu ganancia
                        realizada viene del movimiento del euro frente al dólar, y no de que la
                        acción subiera.
                      </p>
                    )}
                  </div>
                ) : null,
              },
              {
                // Va en la MISMA base que el realizado, y por eso obedece al interruptor:
                // lo que un método se apunta de más arriba, el otro se lo guarda aquí. La
                // cifra del otro método sigue debajo, que es lo que hace falta para
                // comparar pantallas.
                id: "latente", etiqueta: "Latente", significa: "Lo que aún está en juego", valor: latente,
                sub: [
                  resumen?.posiciones?.length
                    ? `${resumen.posiciones.length} posición(es) abiertas` : "sin posiciones",
                  // "sin precio" y "sin tipo de cambio" son averías DISTINTAS y se arreglan
                  // distinto.
                  resumen?.posiciones_sin_precio
                    ? `${resumen.posiciones_sin_precio} sin precio, fuera del total` : null,
                  resumen?.posiciones_sin_tipo_de_cambio
                    ? `${resumen.posiciones_sin_tipo_de_cambio} sin tipo de cambio, fuera del total` : null,
                  (usaPmp ? resumen?.latente_eur : latenteBroker) != null
                    && Math.abs((usaPmp ? resumen.latente_eur : latenteBroker) - (latente ?? 0)) > 0.5
                    ? (usaPmp
                        ? `por ${metodo.toUpperCase()} son ${eur(resumen.latente_eur)}`
                        : `en DEGIRO verás ${eur(latenteBroker)}`) : null,
                ].filter(Boolean).join(" · "),
                ayuda: "Lo que llevas ganado en lo que AÚN NO has vendido, al precio y al cambio de hoy. Puede cambiar mañana. Tu bróker enseña otra cifra porque valora TODAS las acciones al precio medio ponderado, mientras que FIFO/LIFO dejan vivos unos lotes concretos: lo que aquí falta, ya está contado en el Realizado. Sumados, los dos métodos dan el mismo total.",
              },
              {
                // SIEMPRE visible, aunque esté vacía: una función que no se ve no existe.
                // Vacía dice qué falta para llenarla.
                id: "dividendos", etiqueta: "Dividendos", significa: "Lo que te han pagado por tener las acciones",
                valor: dividendos,
                sub: dividendos == null
                  ? "sube tu Account.csv de DEGIRO"
                  : [
                      `${divs?.n_cobros ?? 0} cobros`,
                      divs?.retenido_eur ? `${eur(divs.retenido_eur)} retenidos` : null,
                      // Los que no se pudieron pasar a euros quedan FUERA del total.
                      divs?.sin_convertir ? `${divs.sin_convertir} sin convertir` : null,
                    ].filter(Boolean).join(" · "),
                ayuda: "Cobrado por dividendos, ya descontada la retención en origen. Los dividendos NO están en el Transactions.csv: hay que subir además el Account.csv (Actividad → Cuenta). Se cuentan aparte porque fiscalmente no son ganancias patrimoniales sino rendimientos del capital mobiliario, y van a otra casilla de la declaración. La retención de EE.UU. es recuperable en parte con el convenio de doble imposición.",
              },
              costes != null && {
                id: "costes", etiqueta: "Costes", significa: "Lo que te cobra DEGIRO por el saldo y los datos",
                valor: costes, sub: `${divs?.n_costes ?? 0} apunte(s) · intereses y conectividad`,
                ayuda: "Intereses por operar con el saldo en negativo y conectividad con mercados, sacados del Account.csv. No incluye las comisiones de compraventa, que ya están descontadas en cada operación. Es lo que separa tu total del Total P/L de DEGIRO.",
              },
            ].filter(Boolean)} />
          </div>

          {/* ── Método ────────────────────────────────────────────────────────
              Va acompañado SIEMPRE de la explicación fiscal: enseñar dos cifras
              distintas para la misma venta sin decir cuál vale para Hacienda sería peor
              que enseñar una sola. El interruptor del bróker vive AQUÍ, junto al método,
              porque manda en toda la pantalla. Va aparte de FIFO/LIFO y no como un
              tercer botón: esos dos deciden CÓMO SE EMPAREJAN tus ventas y se guardan en
              el servidor; este solo cambia lo que estás mirando, y vive en tu navegador. */}
          <aside className="relative p-5 sm:p-7 border-t lg:border-t-0 lg:border-l border-suave bg-tinta/[0.015] flex flex-col"
                 aria-labelledby="metodo-calculo">
            <CabeceraBloque icono={ArrowLeftRight} como="h2" id="metodo-calculo"
                            derecha={cambiarMetodo.isPending
                              ? <span className="text-[12.5px] text-tinta-3" role="status">Recalculando…</span>
                              : null}>
              Método de cálculo
            </CabeceraBloque>
            <Segmentado opciones={[{ valor: "fifo", etiqueta: "FIFO" }, { valor: "lifo", etiqueta: "LIFO" }]}
                        valor={metodo} onCambio={setMetodo} etiqueta="Método de cálculo" mono
                        className="mt-4 w-full [&>button]:flex-1" />
            {/* Texto explicativo en tinta normal: el verde se reserva para subidas. */}
            <p className="text-[13px] text-tinta-2 mt-3 leading-relaxed">
              {metodo === "lifo"
                ? "Vende lo más reciente · tu precio medio SUBE al vender"
                : "Vende lo más antiguo · tu precio medio BAJA al vender · es el de Hacienda"}
            </p>

            <button type="button" onClick={alternarBroker} aria-pressed={comoBroker}
                    title="Tu bróker valora TODAS las acciones al precio medio ponderado, que no baja al vender. FIFO/LIFO dejan vivos unos lotes concretos —los caros o los baratos— y por eso dan otro número. Ninguna está mal: lo que una se apunta de más aquí, la otra ya se lo apuntó en lo realizado. Cambia el historial, el realizado y la tabla de posiciones."
                    className={`group mt-5 w-full flex items-center justify-between gap-4 text-left rounded-iv border px-4 py-3 min-h-[56px] transition-colors duration-150 motion-reduce:transition-none ${comoBroker
                      ? "border-marca/40 bg-marca/[0.08]"
                      : "border-suave bg-tinta/[0.03] hover:bg-tinta/[0.06]"}`}>
              <span className="min-w-0">
                <span className={`block text-[14px] font-medium ${comoBroker ? "text-tinta" : "text-tinta-2 group-hover:text-tinta"}`}>
                  {comoBroker ? "Como en DEGIRO (media ponderada)" : "Ver como en DEGIRO"}
                </span>
                <span className="block text-[12.5px] text-tinta-3 mt-0.5">
                  Cambia el historial, el realizado y lo abierto
                </span>
              </span>
              {/* Interruptor: la pista se llena de índigo y el pomo se desliza. */}
              <span aria-hidden="true"
                    className={`relative w-10 h-6 rounded-full shrink-0 transition-colors duration-200 ease-salida motion-reduce:transition-none ${comoBroker ? "bg-marca" : "bg-tinta/15"}`}>
                <span className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow-[0_1px_2px_rgb(0_0_0/0.3)] transition-transform duration-200 ease-salida motion-reduce:transition-none ${comoBroker ? "translate-x-4" : ""}`} />
              </span>
            </button>

            <div className="mt-5 pt-4 border-t border-suave lg:mt-auto">
              <button onClick={() => setVerExplicacion((v) => !v)} aria-expanded={verExplicacion}
                      className={ENLACE}>
                {verExplicacion ? "ocultar" : "¿cómo funciona?"}
              </button>
              {verExplicacion && (
                <p className="text-[13px] text-tinta-2 mt-3 leading-relaxed">
                  Esto no cambia solo lo que ves: gobierna qué lotes te quedan vivos, tu precio medio
                  y qué campanitas se encienden. Cambiarlo recalcula todo, pero <b className="text-tinta">no altera ninguna
                  operación</b> — tus compras y ventas son las que son.
                  <br /><br />
                  <b className="text-tinta">Para saber cuál usar, mira tu bróker tras una venta parcial:</b> si tu precio
                  medio <b className="text-tinta">baja</b>, está quitando las compras más antiguas (FIFO); si <b className="text-tinta">sube</b>,
                  las más recientes (LIFO). Como entras por niveles según cae el precio, lo más
                  antiguo es lo más caro — por eso quitar lo antiguo hace bajar la media.
                  <br /><br />
                  FIFO es además el obligatorio en España para acciones cotizadas (art. 37.2 de la
                  Ley del IRPF): es la cifra de tu declaración, la mires con el método que la mires.
                  {tot && hist?.resumen?.fifo && hist?.resumen?.lifo
                    && hist.resumen.fifo.ganancia_divisa !== hist.resumen.lifo.ganancia_divisa && (
                    <> En tu caso la diferencia entre ambos es de{" "}
                      <b className="iv-cifra text-tinta">{usd(Math.abs(hist.resumen.fifo.ganancia_divisa - hist.resumen.lifo.ganancia_divisa))}</b>.</>
                  )}
                </p>
              )}
            </div>
          </aside>
        </div>
      </section>

      {/* ── Para cuadrar con DEGIRO ────────────────────────────────────────────
          Los avisos sobre tus datos, juntos y como filas de un solo panel en vez de
          cajas ámbar sueltas. Ninguno se ha quitado: cada uno conserva su texto y sus
          botones. */}
      <AvisosPanel titulo="Para cuadrar con DEGIRO" nota="Datos que hinchan o descuadran tus cifras">
        {/* Una venta sin comisión infla la ganancia entre 6 y 10 €, y esa cifra acaba en
            una declaración. Con cien ventas deja de ser calderilla, así que se dice cuánto
            falta en total en vez de dejarlo a que alguien sume. */}
        {!!hist?.ventas_sin_comision && (
          <Aviso titulo={<>{hist.ventas_sin_comision} venta(s) registradas sin comisión.</>}
                 acciones={(!!hist.ventas_sin_comision_manuales
                   || hist.ventas_sin_comision > hist.ventas_sin_comision_manuales) && (
                   <>
                     {/* El botón para repararlas. Los apuntes tecleados se quedaron a cero
                         por un fallo del formulario: son huecos. Se rellenan con la tarifa
                         publicada y quedan marcados como estimados. */}
                     {!!hist.ventas_sin_comision_manuales && (
                       <Boton variante="secundario" tamano="sm" onClick={() => repararComisiones.mutate(false)}
                              ocupado={repararComisiones.isPending}>
                         {repararComisiones.isPending
                           ? "Calculando…"
                           : "Poner la comisión estimada a las que tecleaste a mano"}
                       </Boton>
                     )}
                     {/* Las del CSV no tenían salida si ya no conservas aquel fichero. Va
                         aparte y con su propia advertencia porque ahí el cero SÍ llegó con
                         huella, y estimarlo puede estar inventando un coste que no existió. */}
                     {hist.ventas_sin_comision > hist.ventas_sin_comision_manuales && (
                       <Boton variante="fantasma" tamano="sm" onClick={() => repararComisiones.mutate(true)}
                              disabled={repararComisiones.isPending} className="whitespace-normal text-left h-auto min-h-8 py-1.5">
                         Estimar también las{" "}
                         {hist.ventas_sin_comision - hist.ventas_sin_comision_manuales} que vinieron
                         del CSV
                       </Boton>
                     )}
                   </>
                 )}>
            DEGIRO cobra 2 € por operación más el 0,25% de AutoFX, así que tu ganancia realizada
            está inflada en unos{" "}
            <b className="iv-cifra font-medium text-aviso">{eur(hist.comision_no_contada_eur)}</b>.
            {hist.ventas_sin_comision_manuales === hist.ventas_sin_comision
              ? " Todas están tecleadas a mano, así que reimportar el CSV no las toca:"
                + " no tienen huella que emparejar, y encima tapan la fila del fichero,"
                + " que sí trae la comisión buena. Se arreglan borrándolas aquí abajo y"
                + " volviendo a importar el CSV."
              : " Las que vinieron del CSV se corrigen reimportándolo con la casilla de"
                + " corregir comisiones marcada, que es lo mejor porque trae la cifra"
                + " real; si ya no conservas aquel fichero, aquí abajo puedes estimarlas."
                + " Las tecleadas a mano hay que borrarlas y reimportar, porque no tienen"
                + " huella que emparejar."}
            {/* CUÁLES. Sin el símbolo y la fecha delante, «10 ventas» es un dato que no se
                puede accionar. */}
            {!!hist.ventas_sin_comision_detalle?.length && (
              <ul className="mt-2.5 flex flex-wrap gap-1.5">
                {hist.ventas_sin_comision_detalle.map((v) => (
                  <li key={v.id} className="iv-cifra text-[12px] text-tinta-2 rounded-md bg-tinta/[0.05] px-2 py-1">
                    {v.symbol} · {v.fecha} · {v.acciones} acc.
                    {v.manual ? " · a mano" : " · del CSV"}
                  </li>
                ))}
              </ul>
            )}
          </Aviso>
        )}

        {/* Ventas de la contabilidad VIEJA (el diálogo Vender de la Cartera antes de que
            escribiera en el libro). Ni sus acciones ni su ganancia están en ninguna cifra
            de esta pantalla. */}
        {!!hist?.ventas_antiguas && (
          <Aviso titulo={<>{hist.ventas_antiguas} venta(s) del sistema antiguo, fuera de estas cifras</>}>
            Se registraron con el botón «Vender» de la Cartera cuando ese botón llevaba su
            propia contabilidad aparte. No cuentan en el Realizado ni descuentan acciones del
            libro. Vuelve a meterlas aquí con <b className="text-tinta">Registrar venta</b> (o impórtalas con el CSV de
            DEGIRO, que las trae) y quedarán contadas de verdad.
          </Aviso>
        )}

        {/* La misma venta metida a mano Y venida del CSV solo se detecta como duplicada si
            coincide al céntimo. En una posición ya cerrada no se nota en las acciones —
            solo en que el Realizado se dispara. */}
        {!!hist?.posibles_duplicadas?.length && (
          <Aviso titulo={<>{hist.posibles_duplicadas.length} venta(s) posiblemente contadas dos veces</>}>
            Estas ventas están una vez metidas a mano y otra vez traídas del CSV de DEGIRO
            (misma acción, misma fecha, mismas acciones). Cada pareja suma su ganancia dos
            veces. Busca la copia manual en la lista de abajo (la que NO pone «DEGIRO» en
            las notas) y bórrala con su botón.
            <ul className="mt-2.5 flex flex-wrap gap-1.5">
              {hist.posibles_duplicadas.map((d, i) => (
                <li key={i} className="iv-cifra text-[12px] text-tinta-2 rounded-md bg-tinta/[0.05] px-2 py-1">
                  {d.symbol} · {d.fecha} · {d.acciones} acciones
                </li>
              ))}
            </ul>
          </Aviso>
        )}

        {/* Compras duplicadas. Una compra repetida no descuadra nada contable, así que
            nadie la busca: solo infla la posición y con ella el latente. En NFLX eran 30
            acciones tecleadas a 76,00 $ y la misma compra del CSV a 76,01. */}
        {!!hist?.posibles_compras_duplicadas?.length && (
          <Aviso titulo={<>{hist.posibles_compras_duplicadas.length} compra(s) posiblemente contadas dos veces</>}>
            Cada una está metida a mano y además traída del CSV de DEGIRO: misma acción,
            misma fecha y mismas acciones, con los precios a un céntimo. Eso infla tu
            posición y tu ganancia latente sin descuadrar ningún total, así que no salta
            ningún otro aviso. Borra la copia manual — la del precio redondeado.
            <div className="mt-2.5 divide-y divide-suave rounded-iv border border-suave">
              {hist.posibles_compras_duplicadas.map((d, i) => (
                <div key={i} className="flex items-center gap-x-3 gap-y-1 flex-wrap text-[13px] iv-cifra px-3 py-2">
                  <span className="font-semibold text-tinta">{d.symbol}</span>
                  <span className="text-tinta-3">{fecha(d.fecha)}</span>
                  <span>{d.acciones} acciones</span>
                  <span className="text-tinta-3">
                    a {d.precios.map((x) => x.toFixed(2)).join(" y ")}
                  </span>
                  <span className="text-aviso">+{d.acciones_de_mas} de más</span>
                  <button onClick={() => window.confirm(
                            `Se borra la copia MANUAL de ${d.acciones} ${d.symbol} del `
                            + `${fecha(d.fecha)}. La que vino del CSV se queda, con su precio y `
                            + "su comisión reales.\n\n¿Continuar?")
                            && d.ids_manuales.forEach((id) => borrarDuplicada.mutate(id))}
                          disabled={borrarDuplicada.isPending}
                          className={`${BOTON_BORRAR} ml-auto font-sans`}>
                    <Trash2 className="w-3.5 h-3.5" strokeWidth={1.9} aria-hidden="true" />
                    borrar la copia manual
                  </button>
                </div>
              ))}
            </div>
          </Aviso>
        )}

        {hist?.resumen?.aviso && (
          <Aviso>{hist.resumen.aviso}</Aviso>
        )}

        {/* Qué posiciones arrastran lotes que no vinieron del CSV. Son las que pueden no
            cuadrar con el bróker: su fecha es la del alta, no la de la compra, así que el
            coste se pasó a euros al cambio de un día que no es el tuyo. Se ordenan por
            dinero afectado, que es el orden en que compensa arreglarlas. */}
        {!!sospechosas.length && (
          <Aviso titulo={<>{sospechosas.length} posición(es) con lotes que no vienen del CSV.</>}>
            Esos lotes llevan la fecha en que se dieron de alta, no la de tu compra, así
            que su coste se pasó a euros al cambio de ese día. Por eso el latente puede
            no cuadrar con DEGIRO teniendo el mismo precio y las mismas acciones. Se
            arreglan borrando esos lotes y volviendo a importar el CSV.
            <div className="mt-2.5 overflow-x-auto rounded-iv border border-suave">
              <table className="w-full text-[12.5px] iv-cifra whitespace-nowrap">
                <thead className="text-tinta-3 font-sans">
                  <tr className="text-left [&>th]:font-medium [&>th]:px-3 [&>th]:py-2">
                    <th>Acción</th>
                    <th className="text-right">Sin CSV</th>
                    <th className="text-right">De</th>
                    <th className="text-right">Invertido</th>
                    <th className="text-right">Cambio usado</th>
                    <th className="text-right">Hoy</th>
                  </tr>
                </thead>
                <tbody>
                  {sospechosas.map((p) => (
                    <tr key={p.symbol} className="border-t border-suave [&>td]:px-3 [&>td]:py-1.5">
                      <td className="font-semibold text-tinta">{p.symbol}</td>
                      <td className="text-right">{p.acciones_sin_csv}</td>
                      <td className="text-right text-tinta-3">{p.acciones_abiertas_total}</td>
                      <td className="text-right">{eur(p.coste_eur)}</td>
                      <td className="text-right">{p.cambio_medio_compras ?? "—"}</td>
                      <td className="text-right text-tinta-3">{p.cambio_hoy ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[12.5px] text-tinta-3 mt-2 leading-snug">
              Un «cambio usado» pegado al de hoy en una compra antigua es la señal: ese
              lote se convirtió al cambio de hoy y no al del día en que compraste.
            </p>
          </Aviso>
        )}
      </AvisosPanel>

      {/* ── Las tres listas ─────────────────────────────────────────────────── */}
      <section aria-label="Ventas y posiciones" className="space-y-4">
        <Pestanas id="ops" etiqueta="Ventas y posiciones" pestanas={pestanas} valor={vista} onCambio={setPestana} />

        {vista === "ventas" && (
          <div {...propsPanel("ops", "ventas")} className="iv-panel overflow-clip">
            <div className="px-4 sm:px-5 py-3 flex items-center justify-between gap-3 flex-wrap border-b border-suave">
              <p className="text-[13px] text-tinta-3">Toca una para ver de qué compra salió</p>
              <p className="text-[12.5px] text-tinta-3">Cifras por <span className="text-tinta-2">{metodoRealizado}</span></p>
            </div>
            {cargandoHist ? (
              // Esqueleto con la forma de las filas de verdad, para que la lista no salte
              // al llegar. El barrido se apaga si el sistema pide menos movimiento.
              <div role="status" aria-label="Cargando el historial de ventas" className="divide-y divide-suave">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div key={i} className="px-4 sm:px-5 py-4 flex items-center gap-3">
                    <span className="w-8 h-8 rounded-[9px] iv-esqueleto" />
                    <span className="space-y-1.5">
                      <span className="block h-3 w-16 rounded iv-esqueleto" />
                      <span className="block h-2.5 w-28 rounded iv-esqueleto" />
                    </span>
                    <span className="h-3 w-20 rounded iv-esqueleto ml-auto" />
                  </div>
                ))}
              </div>
            ) : errorHist ? (
              <div role="alert" className="px-5 py-8 flex items-center gap-3 flex-wrap">
                <span aria-hidden="true" className="flex items-center justify-center w-8 h-8 rounded-[9px] bg-baja/10 text-baja">!</span>
                <p className="text-[14px] text-tinta-2">No se ha podido cargar el historial de ventas.</p>
                <Boton variante="secundario" tamano="sm" className="ml-auto" onClick={() => reintentarHist()}>Reintentar</Boton>
              </div>
            ) : !ventas.length ? (
              <div className="px-5 py-12 text-center">
                <span aria-hidden="true" className="mx-auto flex items-center justify-center w-11 h-11 rounded-[12px] bg-marca/10 text-marca">
                  <CircleDollarSign className="w-5 h-5" strokeWidth={1.75} />
                </span>
                <p className="text-[16px] font-semibold text-tinta mt-4">Aún no has registrado ninguna venta.</p>
                <p className="text-[13px] text-tinta-3 max-w-[60ch] mx-auto leading-relaxed mt-2">
                  Si ya tenías posiciones en la Cartera, impórtalas para no empezar de cero. Se
                  reconstruye <b className="text-tinta-2">un lote por cada nivel que tengas con la campanita apagada</b>,
                  que es como marcas los niveles ya comprados. Con uno o dos niveles el reparto
                  de acciones sale exacto a partir de tu precio medio; con tres o más es una
                  estimación y te lo aviso para que la corrijas.
                </p>
                <Boton variante="secundario" className="mt-5" onClick={() => importar.mutate(false)} ocupado={importar.isPending}>
                  {importar.isPending ? "Importando…" : "Importar mis posiciones actuales"}
                </Boton>
              </div>
            ) : (
              <>
                {/* Las últimas 15 a la vista; el resto bajo demanda. */}
                {meses.map((g) => (
                  <div key={g.k}>
                    <p className="sticky top-14 z-[2] px-4 sm:px-5 h-9 flex items-center gap-2 text-[12.5px] font-medium text-tinta-2 bg-superficie/90 backdrop-blur-md border-b border-suave">
                      {g.k.charAt(0).toUpperCase() + g.k.slice(1)}
                      <span className="iv-cifra text-tinta-3 font-normal">· {g.items.length}</span>
                    </p>
                    {g.items.map((v) => (
                      <FilaVenta key={v.id} v={v} metodo={metodo} comoBroker={comoBroker}
                                 onBorrar={(x) => window.confirm(`¿Borrar la venta de ${x.acciones} ${x.symbol} del ${fecha(x.fecha)}?`) && borrar.mutate(x)} />
                    ))}
                  </div>
                ))}
                {ventas.length > 15 && (
                  <button onClick={() => setVerTodas((v) => !v)}
                          aria-expanded={verTodas}
                          className="w-full min-h-[48px] py-3 text-[13px] font-medium text-tinta-2 border-t border-suave inline-flex items-center justify-center gap-2 transition-colors duration-150 motion-reduce:transition-none hover:bg-tinta/[0.025] hover:text-tinta">
                    {verTodas ? "Enseñar solo las últimas 15" : `Enseñar las ${ventas.length - 15} restantes`}
                    <Flecha abierta={verTodas} />
                  </button>
                )}
              </>
            )}
          </div>
        )}

        {vista === "accion" && hayPorAccion && (
          <div {...propsPanel("ops", "accion")} className="iv-panel overflow-hidden">
            <div className="px-4 sm:px-5 py-3 border-b border-suave">
              <p className="text-[13px] text-tinta-3">Lo ganado o perdido en las ventas de cada acción · cifras por {metodoRealizado}</p>
            </div>
            {/* Dos columnas en escritorio: 97 filas en una sola eran una tira interminable. */}
            <ul className="grid md:grid-cols-2 md:divide-x divide-suave">
              {[0, 1].map((col) => (
                <li key={col} className="divide-y divide-suave">
                  {hist.por_symbol
                    .filter((_, i) => (i < Math.ceil(hist.por_symbol.length / 2)) === (col === 0))
                    .map((s) => {
                      const g = s.ganancia_eur;
                      return (
                        <div key={s.symbol} className="px-4 sm:px-5 py-2.5 flex items-center gap-3 transition-colors duration-150 motion-reduce:transition-none hover:bg-tinta/[0.025]">
                          <Monograma symbol={s.symbol} tamano="sm" />
                          <div className="min-w-0 w-24 shrink-0">
                            <p className="text-[14px] font-semibold text-tinta tracking-[-0.01em]">{s.symbol}</p>
                            <p className="text-[12px] text-tinta-3">{s.n_ventas} venta(s)</p>
                          </div>
                          <div className="flex-1 min-w-0 h-1.5 rounded-full bg-tinta/[0.045]" aria-hidden="true">
                            {g != null && (
                              <div className={`h-full rounded-full min-w-[2px] ${g >= 0 ? "bg-sube/60" : "bg-baja/60"}`}
                                   style={{ width: `${(Math.abs(g) / maxPorAccion) * 100}%` }} />
                            )}
                          </div>
                          <span className={`iv-cifra font-medium text-[14px] whitespace-nowrap text-right min-w-[96px] ${tono(s.ganancia_eur ?? s.ganancia_divisa)}`}>
                            {s.ganancia_eur != null ? eur(s.ganancia_eur) : usd(s.ganancia_divisa, s.divisa)}
                          </span>
                        </div>
                      );
                    })}
                </li>
              ))}
            </ul>
          </div>
        )}

        {vista === "abierto" && hayAbierto && (
          <div {...propsPanel("ops", "abierto")} className="iv-panel overflow-hidden">
            <div className="px-4 sm:px-5 py-3 flex items-center gap-x-5 gap-y-2 flex-wrap border-b border-suave">
              {resumen.tasas && (
                <span className="text-[12.5px] text-tinta-3 iv-cifra mr-auto"
                      title="El tipo de cambio se consulta como mucho una vez por hora, y esta pantalla no se refresca sola: para ver el más reciente, recarga.">
                  {Object.entries(resumen.tasas).filter(([d]) => d !== "EUR")
                    .map(([d, t]) => {
                      const edad = haceCuanto(resumen.tasas_edad_s?.[d]);
                      return `1 € = ${t} ${d}${edad ? ` (${edad})` : ""}`;
                    }).join(" · ")}
                </span>
              )}
              {/* Rehacer la importación: si la primera salió con los lotes mal repartidos,
                  borrarlos uno a uno serían decenas de clics. No toca las acciones que ya
                  tengan ventas registradas — ahí borrar compras falsearía la ganancia. */}
              <button onClick={() => window.confirm(
                        "Se rehacen los lotes de las posiciones importadas, a partir de tus "
                        + "niveles y tu precio medio actuales.\n\nLas acciones que ya tengan "
                        + "ventas registradas NO se tocan.\n\n¿Continuar?")
                        && importar.mutate(true)}
                      disabled={importar.isPending}
                      className={ENLACE}>
                {importar.isPending ? "Rehaciendo…" : "Rehacer la importación"}
              </button>
              <button onClick={() => window.confirm(
                        "Si importaste tus posiciones Y ADEMÁS el CSV de DEGIRO, cada "
                        + "posición está contada dos veces (verás el doble de acciones que "
                        + "en tu bróker).\n\nEsto quita los lotes de \"Importar mis "
                        + "posiciones\" en los símbolos que ya cubre el CSV, y deja la "
                        + "versión del CSV, que trae las fechas y precios reales.\n\n¿Continuar?")
                        && quitarDup.mutate()}
                      disabled={quitarDup.isPending}
                      className={ENLACE}>
                {quitarDup.isPending ? "Quitando…" : "Quitar duplicados del CSV"}
              </button>
            </div>

            {/* ── Móvil: una ficha por posición ─────────────────────────────────
                Seis columnas no caben en 390px. Apilado en vez de tabla estrecha: cada
                dato lleva su rótulo al lado. Es la MISMA fila, con otra disposición. */}
            <ul className="md:hidden divide-y divide-suave">
              {resumen.posiciones.map((p) => {
                const { g, precioMedio, invertido, hayOtroMedio, sinPmp } = datosPosicion(p, comoBroker);
                const abiertaEsta = abierta === p.symbol;
                return (
                  <li key={p.symbol}>
                    {/* La ficha entera es pulsable, pero el botón de verdad es el del
                        símbolo. La ficha NO puede ser un <button> envolvente: «Valor hoy»
                        trae un campo y un botón cuando falta cotización. */}
                    <div onClick={() => setAbierta(abiertaEsta ? null : p.symbol)}
                         className={`px-4 py-3.5 cursor-pointer transition-colors duration-150 motion-reduce:transition-none active:bg-tinta/[0.04] ${abiertaEsta ? "bg-tinta/[0.03]" : ""}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-3 min-w-0">
                          <Monograma symbol={p.symbol} tamano="md" />
                          <div className="min-w-0">
                            <button type="button"
                                    onClick={(e) => { e.stopPropagation();
                                                      setAbierta(abiertaEsta ? null : p.symbol); }}
                                    aria-expanded={abiertaEsta}
                                    aria-label={`${abiertaEsta ? "Ocultar" : "Ver"} las compras de ${p.symbol}`}
                                    className="inline-flex items-center gap-1.5 min-h-[28px] rounded">
                              <span className="text-[15px] font-semibold text-tinta tracking-[-0.01em]">{p.symbol}</span>
                              <Flecha abierta={abiertaEsta} />
                            </button>
                            <div className="flex items-center gap-1.5 flex-wrap mt-1">
                              {!!p.divisas_mezcladas && (
                                <Chip tono="aviso"
                                      title={`Esta posición tiene lotes en ${p.divisas_mezcladas.join(" y ")}. El precio medio y el invertido EN DIVISA suman monedas distintas y no significan nada; las cifras en euros sí son correctas, porque cada lote se convierte con su propia tasa. Revisa la divisa de cada compra.`}>
                                  {p.divisas_mezcladas.join("+")}
                                </Chip>
                              )}
                              {p.divisa_incoherente && (
                                <Chip tono="aviso"
                                      title={`Tus operaciones de ${p.symbol} están en ${p.divisa}, pero cotiza en ${p.divisa_cotizacion}. Las cifras en euros son correctas; revisa la divisa de la ficha o la de las compras.`}>
                                  {p.divisa}≠{p.divisa_cotizacion}
                                </Chip>
                              )}
                              {sinPmp && (
                                <Chip tono="aviso"
                                      title="Esta fila NO está en media ponderada aunque el interruptor lo esté: falta el tipo de cambio de alguna compra de su historial y sin él no hay coste en euros que ponderar. Se enseña por tu método (FIFO/LIFO), que da otro número. No la compares con DEGIRO.">
                                  sin ponderada
                                </Chip>
                              )}
                              <NivelesDeLaFila p={p} />
                              {sinNiveles.has(p.symbol) && (
                                <Chip title="Esta acción está en la Cartera pero todavía no tiene niveles. Se creó sola al registrar la compra, para que coja precio de mercado; el precio al que compraste NO es un nivel. Ponle los niveles en la Cartera cuando los tengas.">
                                  niveles pendientes
                                </Chip>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          <div className={`iv-cifra font-medium text-[15px] whitespace-nowrap ${tono(g.pnl_eur)}`}>{eur(g.pnl_eur)}</div>
                          <div className={`iv-cifra text-[12px] whitespace-nowrap ${tono(g.pct_eur)}`}>{pct(g.pct_eur)}</div>
                        </div>
                      </div>

                      {/* Los cuatro datos restantes, cada uno con su rótulo, en una franja
                          de luz de dos columnas. */}
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 mt-3 rounded-iv bg-tinta/[0.03] px-3 py-2.5 text-[12.5px]">
                        <div className="min-w-0">
                          <dt className="text-tinta-3">Acciones</dt>
                          <dd className="iv-cifra text-tinta mt-0.5">{p.acciones}</dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-tinta-3">Invertido <span className="opacity-70">(€)</span></dt>
                          <dd className="iv-cifra whitespace-nowrap mt-0.5 text-tinta">{eur(invertido)}</dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-tinta-3">Precio medio <span className="opacity-70">({p.divisa === "EUR" ? "€" : p.divisa})</span></dt>
                          <dd className="iv-cifra whitespace-nowrap mt-0.5 text-tinta">
                            {usd(precioMedio, p.divisa)}
                            {hayOtroMedio && (
                              <div className="text-[11.5px] text-tinta-3">
                                {comoBroker
                                  ? `${metodo.toUpperCase()} = ${usd(p.precio_medio, p.divisa)}`
                                  : `bróker ≈ ${usd(p.precio_medio_degiro ?? p.precio_medio_ponderado, p.divisa)}`}
                              </div>
                            )}
                          </dd>
                        </div>
                        <div className="min-w-0">
                          <dt className="text-tinta-3">Valor hoy <span className="opacity-70">(€)</span></dt>
                          {/* Frena la propagación: con un campo dentro, escribir no pliega la ficha. */}
                          <dd className="iv-cifra whitespace-nowrap mt-0.5 text-tinta" onClick={(e) => e.stopPropagation()}>
                            <CeldaValorHoy p={p} />
                          </dd>
                        </div>
                      </dl>
                    </div>
                    {abiertaEsta && <LotesAbiertos symbol={p.symbol} metodo={metodo} />}
                  </li>
                );
              })}
              {/* El total, con la misma forma de ficha para que se lea como una más. */}
              <li className="px-4 py-4 border-t border-medio bg-tinta/[0.03]">
                <div className="flex items-start justify-between gap-3">
                  <span className="text-[14px] font-semibold text-tinta pt-0.5">Total</span>
                  <div className="text-right shrink-0">
                    <div className={`iv-cifra font-semibold text-[16px] whitespace-nowrap ${tono(totales.ganancia)}`}>{eur(totales.ganancia)}</div>
                    {totales.pct != null ? (
                      <div className={`iv-cifra text-[12px] whitespace-nowrap ${tono(totales.ganancia)}`}>{pct(totales.pct)}</div>
                    ) : null}
                    {totales.sinValorar > 0 && (
                      <div className="text-[12px] text-tinta-3">{totales.sinValorar} sin valorar, fuera del total</div>
                    )}
                  </div>
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 mt-3 text-[12.5px]">
                  <div className="min-w-0">
                    <dt className="text-tinta-3">Posiciones</dt>
                    <dd className="iv-cifra mt-0.5">{resumen.posiciones.length}</dd>
                  </div>
                  <div className="min-w-0">
                    <dt className="text-tinta-3">Invertido <span className="opacity-70">(€)</span></dt>
                    <dd className="iv-cifra whitespace-nowrap mt-0.5">{eur(totales.invertido)}</dd>
                  </div>
                  <div className="min-w-0">
                    <dt className="text-tinta-3">Valor hoy <span className="opacity-70">(€)</span></dt>
                    <dd className="iv-cifra whitespace-nowrap mt-0.5">{eur(totales.valor)}</dd>
                  </div>
                </dl>
              </li>
            </ul>

            {/* ── Escritorio: tabla ─────────────────────────────────────────────
                Aquí las seis columnas caben y comparar posiciones en vertical es más
                rápido que en fichas. Cifras tabulares y sin partir. */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-[13px] [&_td]:align-middle">
                <thead>
                  {/* Las unidades EN LA CABECERA: el precio medio va en la divisa del
                      valor y el resto en euros. */}
                  <tr className="text-left border-b border-suave [&>th]:text-[12px] [&>th]:font-medium [&>th]:text-tinta-3 [&>th]:whitespace-nowrap [&>th]:py-3">
                    <th scope="col" className="px-5">Acción</th>
                    <th scope="col" className="px-3 text-right">Acciones</th>
                    <th scope="col" className="px-3 text-right">
                      Precio medio <span className="opacity-70">(divisa)</span>
                    </th>
                    <th scope="col" className="px-3 text-right">
                      Invertido <span className="opacity-70">(€)</span>
                    </th>
                    <th scope="col" className="px-3 text-right">
                      Valor hoy <span className="opacity-70">(€)</span>
                    </th>
                    <th scope="col" className="px-5 text-right">
                      Ganancia <span className="opacity-70">(€)</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {resumen.posiciones.map((p) => {
                    const { g, precioMedio, invertido, hayOtroMedio, sinPmp } = datosPosicion(p, comoBroker);
                    return (
                    <React.Fragment key={p.symbol}>
                    <tr className={`border-b border-suave cursor-pointer transition-colors duration-150 motion-reduce:transition-none hover:bg-tinta/[0.025] [&>td]:py-3 ${abierta === p.symbol ? "bg-tinta/[0.03]" : ""}`}
                        onClick={() => setAbierta(abierta === p.symbol ? null : p.symbol)}>
                      <td className="px-5">
                        <div className="flex items-center gap-3">
                          <Monograma symbol={p.symbol} tamano="sm" />
                          <div className="flex items-center gap-x-2 gap-y-1 flex-wrap min-w-0">
                          {/* Un botón de verdad, no un <tr onClick>: así se despliega también
                              con teclado y un lector de pantalla dice qué hace. */}
                          <button type="button"
                                  onClick={(e) => { e.stopPropagation();
                                                    setAbierta(abierta === p.symbol ? null : p.symbol); }}
                                  aria-expanded={abierta === p.symbol}
                                  aria-label={`${abierta === p.symbol ? "Ocultar" : "Ver"} las compras de ${p.symbol}`}
                                  className="inline-flex items-center gap-1.5 min-h-[32px] pr-1 rounded">
                            <span className="text-[14px] font-semibold text-tinta tracking-[-0.01em]">{p.symbol}</span>
                            <Flecha abierta={abierta === p.symbol} />
                          </button>
                          {!!p.divisas_mezcladas && (
                            <Chip tono="aviso"
                                  title={`Esta posición tiene lotes en ${p.divisas_mezcladas.join(" y ")}. El precio medio y el invertido EN DIVISA suman monedas distintas y no significan nada; las cifras en euros sí son correctas, porque cada lote se convierte con su propia tasa. Revisa la divisa de cada compra.`}>
                              {p.divisas_mezcladas.join("+")}
                            </Chip>
                          )}
                          {/* La operación dice una moneda y el mercado otra: una de las dos es
                              una errata. Las cifras en euros ya salen bien. */}
                          {p.divisa_incoherente && (
                            <Chip tono="aviso"
                                  title={`Tus operaciones de ${p.symbol} están en ${p.divisa}, pero cotiza en ${p.divisa_cotizacion}. Las cifras en euros son correctas; revisa la divisa de la ficha o la de las compras.`}>
                              {p.divisa}≠{p.divisa_cotizacion}
                            </Chip>
                          )}
                          {sinPmp && (
                            <Chip tono="aviso"
                                  title="Esta fila NO está en media ponderada aunque el interruptor lo esté: falta el tipo de cambio de alguna compra de su historial y sin él no hay coste en euros que ponderar. Se enseña por tu método (FIFO/LIFO), que da otro número. No la compares con DEGIRO.">
                              sin ponderada
                            </Chip>
                          )}
                          <NivelesDeLaFila p={p} />
                          {sinNiveles.has(p.symbol) && (
                            <Chip title="Esta acción está en la Cartera pero todavía no tiene niveles. Se creó sola al registrar la compra, para que coja precio de mercado; el precio al que compraste NO es un nivel. Ponle los niveles en la Cartera cuando los tengas.">
                              niveles pendientes
                            </Chip>
                          )}
                          </div>
                        </div>
                      </td>
                      <td className="px-3 text-right iv-cifra">{p.acciones}</td>
                      <td className="px-3 text-right iv-cifra whitespace-nowrap">
                        {/* Con el interruptor puesto manda la ponderada, que es la del
                            bróker; la otra baja debajo etiquetada. Las dos son correctas. */}
                        {usd(precioMedio, p.divisa)}
                        {hayOtroMedio && (
                          <div className="text-[11.5px] text-tinta-3"
                               title={comoBroker
                                 ? `Arriba, la media ponderada (la de tu bróker). Debajo, el coste real de las ${p.acciones} acciones que te quedan por ${metodo.toUpperCase()}.`
                                 : "Precio medio ponderado: el que suele enseñar tu bróker. No cambia al vender, porque promedia TODO lo que has comprado. El de arriba es el coste de las acciones que te quedan de verdad."}>
                            {comoBroker
                              ? `${metodo.toUpperCase()} = ${usd(p.precio_medio, p.divisa)}`
                              : `bróker ≈ ${usd(p.precio_medio_degiro ?? p.precio_medio_ponderado, p.divisa)}`}
                          </div>
                        )}
                      </td>
                      <td className="px-3 text-right iv-cifra whitespace-nowrap">{eur(invertido)}</td>
                      <td className="px-3 text-right iv-cifra whitespace-nowrap"><CeldaValorHoy p={p} /></td>
                      {/* Importe y % apilados en la misma columna derecha. */}
                      <td className="px-5 text-right whitespace-nowrap">
                        <div className={`iv-cifra font-medium text-[14px] ${tono(g.pnl_eur)}`}>{eur(g.pnl_eur)}</div>
                        <div className={`iv-cifra text-[12px] ${tono(g.pct_eur)}`}>{pct(g.pct_eur)}</div>
                      </td>
                    </tr>
                    {abierta === p.symbol && (
                      <tr>
                        <td colSpan={6} className="p-0">
                          <LotesAbiertos symbol={p.symbol} metodo={metodo} />
                        </td>
                      </tr>
                    )}
                    </React.Fragment>
                    );
                  })}
                </tbody>
                {/* Totales: el % agregado es sobre lo invertido. El Total suma las MISMAS
                    cifras que enseñan las filas: valor − invertido = ganancia. */}
                <tfoot>
                  <tr className="border-t border-medio bg-tinta/[0.03] [&>td]:py-3.5">
                    <td className="px-5 text-[14px] font-semibold text-tinta">Total</td>
                    <td className="px-3 text-right iv-cifra text-tinta-3 whitespace-nowrap">
                      {resumen.posiciones.length} pos.
                    </td>
                    <td />
                    <td className="px-3 text-right iv-cifra font-medium whitespace-nowrap">{eur(totales.invertido)}</td>
                    <td className="px-3 text-right iv-cifra font-medium whitespace-nowrap">{eur(totales.valor)}</td>
                    <td className="px-5 text-right whitespace-nowrap">
                      <div className={`iv-cifra font-semibold text-[15px] ${tono(totales.ganancia)}`}>{eur(totales.ganancia)}</div>
                      {totales.pct != null ? (
                        <div className={`iv-cifra text-[12px] ${tono(totales.ganancia)}`}>
                          {pct(totales.pct)}
                        </div>
                      ) : null}
                      {totales.sinValorar > 0 && (
                        <div className="text-[12px] text-tinta-3">{totales.sinValorar} sin valorar, fuera del total</div>
                      )}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
            {/* La explicación se lee una vez y luego estorba: plegada por defecto. */}
            <details className="group border-t border-suave">
              <summary className="px-4 sm:px-5 min-h-[44px] text-[13px] text-tinta-3 cursor-pointer list-none [&::-webkit-details-marker]:hidden flex items-center gap-2 hover:text-tinta transition-colors duration-150 motion-reduce:transition-none">
                <CaretDown size={11} weight="bold" aria-hidden="true"
                           className="-rotate-90 group-open:rotate-0 transition-transform duration-200 ease-salida motion-reduce:transition-none" />
                Cómo leer esta tabla
              </summary>
              <p className="px-4 sm:px-5 pb-4 text-[13px] text-tinta-2 leading-relaxed max-w-[90ch]">
                El precio medio es el de las acciones que te QUEDAN, por <b className="text-tinta">{metodo.toUpperCase()}</b>.
                Tras vender parte, FIFO y LIFO dejan lotes distintos abiertos y el medio no
                coincide: si no cuadra con tu bróker, prueba el otro método arriba.
                <br />
                Las campanitas de la Cartera se mueven solas: se apagan al comprar en un nivel y
                vuelven a encenderse en cuanto vendes la última acción de ese nivel. Los niveles
                que no tengan compras registradas no se tocan.
                <br />
                <b className="text-tinta">bróker ≈</b> es el precio medio de DEGIRO, y no se calcula como el de arriba:
                al vender, DEGIRO resta del coste de la posición <b className="text-tinta">el dinero que ingresas</b>, no
                lo que costaron las acciones vendidas. Por eso su medio SE MUEVE cuando vendes —
                sube si vendes por debajo de tu media y baja si vendes por encima—. El de arriba
                es el coste real de las acciones que te quedan. Los dos son correctos y miden
                cosas distintas: el suyo sirve para cuadrar pantallas, no para saber lo que
                ganaste en cada nivel.
              </p>
            </details>
          </div>
        )}
      </section>

      {/* Al final, no en medio. Es lo que autoriza a estimar el margen de una venta, pero
          se teclea una vez al mes. Su sitio no cambia lo que hace. */}
      <ExtractoMargen />
    </div>
  );
}
