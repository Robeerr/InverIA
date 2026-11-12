import React from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import Chip from "./Chip";
import Monograma from "./Monograma";
import { fmtEur, fmtPctPlano, fmtPrice, fmtHace, fmtEnDias } from "@/lib/format";

/* TarjetaAtencion · la unidad de «Lo que importa hoy»
   ─────────────────────────────────────────────────────────────────────────────
   Una FILA de lista de producto, no una tarjeta suelta: monograma del ticker a la
   izquierda (el ancla que el ojo recorre en vertical), el relato en el centro y la
   LECTURA numérica a la derecha —la cifra que el relato describía en prosa—. Todas
   las filas viven en un mismo panel (lo monta HoyView), así que las columnas de
   cifras quedan alineadas de una fila a otra como en una tabla.

       qué pasa    → el titular, con el ticker y el dato
       por qué     → el respaldo: fuerza del nivel, métodos que coinciden, quién lo dice
       qué vigilar → lo accionable
       lectura     → las cifras de `datos`, en mono, en rejilla fija

   El backend manda el texto ya redactado y los datos crudos por separado. La frase
   la escribe el servidor porque cruza posición, niveles y menciones; las cifras las
   formatea el cliente con `lib/format`, que es el único sitio que sabe si un número
   es un precio en dólares o un importe en euros. */

const TIPOS = {
  ruptura: { tono: "baja", etiqueta: "Ruptura" },
  alerta: { tono: "aviso", etiqueta: "Alerta" },
  nivel: { tono: "marca", etiqueta: "Nivel cerca" },
  divergencia: { tono: "info", etiqueta: "Choque" },
  confluencia: { tono: "sube", etiqueta: "Coincidencia" },
  resultados: { tono: "neutro", etiqueta: "Resultados" },
};

/* URGENTE frente a INFORMATIVO. Una alerta que ha saltado o una ruptura de la media
   piden decidir hoy; un nivel cerca, un choque de fuentes o unos resultados piden
   mirar. La urgencia la dice el orden, el grupo en el que cae (HoyView los rotula) y
   la forma: las urgentes llevan filo de color, monograma teñido y chip sólido. */
const URGENTES = new Set(["ruptura", "alerta"]);
export function esUrgente(tarjeta) {
  return URGENTES.has(tarjeta?.tipo);
}

const PUNTO_TONO = {
  sube: "bg-sube",
  baja: "bg-baja",
  aviso: "bg-aviso",
  info: "bg-info",
  marca: "bg-marca",
  neutro: "bg-linea-marcada",
};

/* La LECTURA por tipo. Cada entrada: etiqueta corta + valor ya formateado + tono.
   `tono` decide el color de la cifra: "auto" lo saca del signo (P&L, variación),
   un token fijo cuando lo manda la semántica, y sin tono cuando es una magnitud
   que no tiene dirección (un precio, un recuento). Es la misma disciplina que
   `Metrica`: teñir hay que pedirlo, porque un número en rojo afirma algo. */
function lecturasDe(tarjeta) {
  const d = tarjeta.datos || {};
  switch (tarjeta.tipo) {
    case "ruptura":
      return [
        { etiqueta: "P&L", valor: fmtEur(d.pnl_eur), num: d.pnl_eur, tono: "auto" },
        { etiqueta: "Distancia", valor: d.distancia_pct != null ? `${fmtPctPlano(Math.abs(d.distancia_pct))} debajo` : "—", tono: "baja" },
        { etiqueta: "Media 10s", valor: d.sma_10w != null ? `$${fmtPrice(d.sma_10w)}` : "—" },
        { etiqueta: "Acciones", valor: d.acciones != null ? String(d.acciones) : "—" },
      ];
    case "alerta":
      return [
        { etiqueta: "Precio", valor: d.price != null ? `$${fmtPrice(d.price)}` : "—" },
        { etiqueta: "Objetivo", valor: d.target != null ? `$${fmtPrice(d.target)}` : "—", tono: "marca" },
        { etiqueta: "Acción", valor: d.accion || "—", tono: d.accion === "COMPRA" ? "sube" : d.accion === "VENTA" ? "baja" : "neutro" },
        { etiqueta: "Disparada", valor: d.fired_at ? fmtHace(d.fired_at) : "—" },
      ];
    case "nivel":
      return [
        { etiqueta: "Distancia", valor: d.distancia_pct != null ? fmtPctPlano(Math.abs(d.distancia_pct)) : "—", tono: "marca" },
        { etiqueta: "Precio", valor: d.price != null ? `$${fmtPrice(d.price)}` : "—" },
        { etiqueta: "Nivel", valor: d.target != null ? `$${fmtPrice(d.target)}` : "—" },
        { etiqueta: "Fuerza", valor: d.fuerza != null ? `${d.fuerza}/100` : null, barra: d.fuerza },
      ];
    case "divergencia":
    case "confluencia":
      return [
        { etiqueta: "Menciones", valor: d.menciones != null ? String(d.menciones) : "—" },
        { etiqueta: "A favor", valor: d.positivos != null ? String(d.positivos) : "—", tono: "sube" },
        { etiqueta: "En contra", valor: d.negativos != null ? String(d.negativos) : "—", tono: "baja" },
        { etiqueta: "Fuentes", valor: Array.isArray(d.fuentes) ? String(d.fuentes.length) : "—" },
      ];
    case "resultados":
      return [
        { etiqueta: "Cuándo", valor: d.fecha ? fmtEnDias(d.fecha) : (d.dias != null ? `en ${d.dias} días` : "—"), tono: "aviso" },
        { etiqueta: "P&L", valor: fmtEur(d.pnl_eur), num: d.pnl_eur, tono: "auto" },
        { etiqueta: "Acciones", valor: d.acciones != null ? String(d.acciones) : "—" },
        d.sorpresas?.supera != null && d.sorpresas?.total
          ? { etiqueta: "Bate", valor: `${d.sorpresas.supera}/${d.sorpresas.total}` }
          : null,
      ].filter(Boolean);
    default:
      return [];
  }
}

const CLASES_TONO = {
  sube: "text-sube",
  baja: "text-baja",
  aviso: "text-aviso",
  info: "text-info",
  marca: "text-marca",
  neutro: "text-tinta",
};

function tonoDelNumero(n) {
  if (n == null || isNaN(Number(n))) return "neutro";
  return Number(n) > 0 ? "sube" : Number(n) < 0 ? "baja" : "neutro";
}

/** Una celda de la lectura: etiqueta arriba, cifra mono debajo. La barra de fuerza va
 *  DEBAJO de la cifra y no a su lado: en móvil, «100/100» y la barra en la misma línea
 *  no cabían en media columna. Cifra en peso medio, no negrita: en columna, el peso lo
 *  da la alineación, y la negrita mono de antes pesaba más que el titular. */
function Lectura({ etiqueta, valor, tono, num, barra }) {
  const vacio = valor == null || valor === "—";
  const clave = tono === "auto" ? tonoDelNumero(num) : tono || "neutro";
  return (
    <div className="min-w-0">
      <p className="iv-etiqueta leading-none">{etiqueta}</p>
      {barra != null ? (
        <>
          <p className="iv-cifra text-[13.5px] font-medium mt-1.5 leading-tight text-tinta-2">{valor}</p>
          <span className="block w-full max-w-[72px] h-1 mt-1.5 rounded-full bg-tinta/10 overflow-hidden"
                aria-hidden="true">
            <span className="block h-full bg-marca rounded-full" style={{ width: `${Math.min(100, barra)}%` }} />
          </span>
        </>
      ) : (
        <p className={cn("iv-cifra text-[13.5px] font-medium mt-1.5 leading-tight break-words",
          vacio ? "text-tinta-3" : CLASES_TONO[clave] || CLASES_TONO.neutro)}>
          {valor ?? "—"}
        </p>
      )}
    </div>
  );
}

/** Texto del estado del motor, o null si confirma. Va como nota en línea, no como
 *  chip: es contexto del «por qué», no una etiqueta que clasifique la tarjeta. */
function estadoMotor(estado) {
  if (!estado || estado === "confirma" || estado === "ok") return null;
  return estado === "sin_datos"
    ? { texto: "Motor de niveles: sin datos todavía",
        ayuda: "Aún no se ha calculado para este símbolo. No es un rechazo ni una confirmación." }
    : { texto: "Motor de niveles: sin zona en este precio",
        ayuda: "Ha calculado zonas para este símbolo, pero ninguna cae en este precio." };
}

/** La etiqueta de tipo de una fila informativa: punto de color + texto, sin caja. El
 *  chip relleno se reserva para las urgentes, que es lo que tiene que verse de lejos. */
function TipoDiscreto({ meta }) {
  return (
    <span className="inline-flex items-center gap-1.5 iv-etiqueta text-tinta-2 whitespace-nowrap">
      <span className={cn("w-1.5 h-1.5 rounded-full", PUNTO_TONO[meta.tono] || PUNTO_TONO.neutro)}
            aria-hidden="true" />
      {meta.etiqueta}
    </span>
  );
}

const FILO = {
  baja: "bg-baja",
  aviso: "bg-aviso",
};

/** «INTC está a un 0.6% de tu Nivel 1» → «Está a un 0.6% de tu Nivel 1».
 *  «MU: se ha disparado…» → «Se ha disparado…». El ticker ya está escrito encima, en
 *  grande; repetirlo era la primera palabra de cada titular. Solo se quita si el texto
 *  EMPIEZA por el ticker: nada del contenido cambia. */
function sinPrefijoDelTicker(texto, symbol) {
  if (!texto || !symbol) return texto;
  let t = texto;
  if (t.startsWith(symbol + ": ")) t = t.slice(symbol.length + 2);
  else if (t.startsWith(symbol + " ")) t = t.slice(symbol.length + 1);
  else return texto;
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export default function TarjetaAtencion({ tarjeta, orden, indice = 0 }) {
  const meta = TIPOS[tarjeta.tipo] || { tono: "neutro", etiqueta: tarjeta.tipo };
  const d = tarjeta.datos || {};
  const lecturas = lecturasDe(tarjeta);
  const razonesYFuentes = [
    ...(Array.isArray(d.razones) ? d.razones : []),
    ...(Array.isArray(d.fuentes) ? d.fuentes : []),
  ];
  // Las razones del motor ya vienen escritas en el «por qué» («Soporte histórico (swing
  // low) + Fibonacci 50%…»): pintarlas además como chips era decir lo mismo dos veces
  // con el doble de peso. Solo se enseñan las que el texto no menciona —típicamente,
  // las fuentes de un choque o una coincidencia—.
  const extras = razonesYFuentes.filter((r) => !(tarjeta.por_que || "").includes(r));
  const motor = estadoMotor(d.motor_niveles);
  const tambien = Array.isArray(tarjeta.tambien) && tarjeta.tambien.length > 0 ? tarjeta.tambien : null;
  const urgente = esUrgente(tarjeta);

  return (
    <article
      className="group relative px-4 py-5 sm:px-6 iv-entra
                 transition-colors duration-150 ease-salida motion-reduce:transition-none
                 [@media(hover:hover)]:hover:bg-tinta/[0.025]"
      style={{ animationDelay: `${Math.min(indice, 8) * 40}ms` }}
      data-testid={`tarjeta-hoy-${tarjeta.symbol}`}
    >
      {/* El filo de color de las urgentes: dice «esto pide decidir» antes de leer nada,
          sin teñir la fila entera (eso volvería a ser una caja dentro de la caja). */}
      {urgente && (
        <span className={cn("absolute left-0 top-5 bottom-5 w-[3px] rounded-r-full",
                            FILO[meta.tono] || "bg-marca")}
              aria-hidden="true" />
      )}

      {/* En móvil el monograma sube a la línea del ticker (a 32 px): como columna propia
          se comía 56 px de un texto que ya va justo de ancho. */}
      <div className="grid grid-cols-1 sm:grid-cols-[40px_minmax(0,1fr)] sm:gap-x-4
                      lg:grid-cols-[40px_minmax(0,1fr)_264px] lg:gap-x-6">
        <Monograma symbol={tarjeta.symbol} tono={urgente ? meta.tono : "neutro"} className="mt-0.5 hidden sm:inline-flex" />

        {/* ── El relato ── */}
        <div className="min-w-0">
          <div className="flex items-center gap-x-2 gap-y-1 min-w-0">
            <Monograma symbol={tarjeta.symbol} tono={urgente ? meta.tono : "neutro"} tamano="sm"
                       className="sm:hidden mr-1" />
            <Link to={tarjeta.ruta}
                  className="text-[15px] font-semibold tracking-[-0.015em] leading-none text-tinta
                             hover:text-marca transition-colors duration-150 motion-reduce:transition-none shrink-0">
              {tarjeta.symbol}
            </Link>
            {tarjeta.nombre && tarjeta.nombre !== tarjeta.symbol && (
              <span className="text-[13px] text-tinta-3 truncate min-w-0 leading-none">{tarjeta.nombre}</span>
            )}
            <span className="ml-auto flex items-center gap-2.5 shrink-0 pl-2">
              {d.tiene_posicion && <span className="iv-etiqueta whitespace-nowrap">En cartera</span>}
              {urgente
                ? <Chip tono={meta.tono} variante="solido">{meta.etiqueta}</Chip>
                : <TipoDiscreto meta={meta} />}
            </span>
          </div>

          {/* qué pasa · la frase que hay que leer hoy */}
          <p className={cn("leading-snug text-tinta mt-2 text-pretty tracking-[-0.01em]",
                           urgente ? "text-[16px] font-semibold" : "text-[15px] font-medium")}>
            {orden != null && (
              <span className="sr-only">Prioridad {String(orden).padStart(2, "0")}. </span>
            )}
            {sinPrefijoDelTicker(tarjeta.que_pasa, tarjeta.symbol)}
          </p>

          {tarjeta.por_que && (
            <p className="text-[13.5px] leading-relaxed mt-1.5 text-pretty text-tinta-2 max-w-[68ch]">
              {tarjeta.por_que}
            </p>
          )}

          {tarjeta.que_vigilar && (
            <p className="text-[13.5px] text-tinta mt-2.5 leading-snug text-pretty flex gap-2 max-w-[68ch]">
              <span className="text-[12px] font-medium text-marca shrink-0 leading-[1.45]">Vigila</span>
              <span>{tarjeta.que_vigilar}</span>
            </p>
          )}

          {(motor || extras.length > 0 || tambien) && (
            <p className="text-etiqueta text-tinta-3 mt-2 leading-relaxed">
              {[
                motor && <span key="motor" title={motor.ayuda}>{motor.texto}</span>,
                extras.length > 0 && <span key="extras">{extras.join(" · ")}</span>,
                tambien && <span key="tambien">también: {tambien.map((t) => t.que_pasa).join(" · ")}</span>,
              ].filter(Boolean).reduce((acc, el, i) => (i ? [...acc, " · ", el] : [el]), [])}
            </p>
          )}

          {tarjeta.aviso && (
            <p className="text-apoyo text-aviso mt-2.5 bg-aviso/10 border border-aviso/25 rounded-iv-sm px-2.5 py-1.5">
              {tarjeta.aviso}
            </p>
          )}
        </div>

        {/* ── La lectura ──
            En escritorio, columna fija a la derecha: el mismo ancho en todas las filas,
            así las cifras se leen en vertical como una tabla. En móvil, debajo del
            relato y a todo el ancho, en cuatro columnas cuando caben. */}
        {lecturas.length > 0 && (
          <div className="col-span-full mt-4 lg:col-span-1 lg:mt-0 flex flex-col
                          lg:border-l lg:border-suave lg:pl-6">
            <div className="grid grid-cols-2 min-[460px]:grid-cols-4 lg:grid-cols-2 gap-x-4 gap-y-3.5
                            rounded-iv bg-tinta/[0.03] px-3.5 py-3 lg:bg-transparent lg:p-0">
              {lecturas.map((l) => <Lectura key={l.etiqueta} {...l} />)}
            </div>
            <Link to={tarjeta.ruta}
                  className="mt-3 lg:mt-auto lg:pt-3 self-start inline-flex items-center gap-1 min-h-[32px]
                             text-[13px] font-medium text-tinta-2 hover:text-marca
                             transition-colors duration-150 motion-reduce:transition-none">
              Ver análisis
              <ChevronRight className="w-3.5 h-3.5 transition-transform duration-150 ease-salida
                                       group-hover:translate-x-0.5 motion-reduce:transition-none"
                            strokeWidth={2} aria-hidden="true" />
            </Link>
          </div>
        )}
      </div>
    </article>
  );
}
