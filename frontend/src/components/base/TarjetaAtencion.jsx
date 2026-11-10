import React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import Chip from "./Chip";
import { fmtEur, fmtPctPlano, fmtPrice, fmtHace, fmtEnDias } from "@/lib/format";

/* TarjetaAtencion · la unidad de «Lo que importa hoy»
   ─────────────────────────────────────────────────────────────────────────────
   El rediseño de la portada la convierte en una FILA DE TERMINAL: a la izquierda el
   relato (las tres preguntas que el Dashboard existe para contestar), a la derecha
   una LECTURA numérica —la cifra que el relato describía en prosa—. La queja del
   inventario era literal: «una lista de tarjetas de texto sin una sola cifra». Aquí
   cada tipo trae su propio panel de números, sacado de `datos`, sin inventar nada.

       qué pasa    → el titular, con el ticker y el dato
       por qué     → el respaldo: fuerza del nivel, métodos que coinciden, quién lo dice
       qué vigilar → lo accionable
       lectura     → las cifras de `datos`, en mono, alineadas a la derecha

   El backend manda el texto ya redactado y los datos crudos por separado. La frase
   la escribe el servidor porque cruza posición, niveles y menciones; las cifras las
   formatea el cliente con `lib/format`, que es el único sitio que sabe si un número
   es un precio en dólares o un importe en euros. */

const TIPOS = {
  ruptura: { tono: "baja", etiqueta: "Ruptura", halo: "iv-halo-baja" },
  alerta: { tono: "aviso", etiqueta: "Alerta", halo: "iv-halo-marca" },
  nivel: { tono: "marca", etiqueta: "Nivel cerca" },
  divergencia: { tono: "info", etiqueta: "Choque" },
  confluencia: { tono: "sube", etiqueta: "Coincidencia" },
  resultados: { tono: "neutro", etiqueta: "Resultados" },
};

/* URGENTE frente a INFORMATIVO. Una alerta que ha saltado o una ruptura de la media
   piden decidir hoy; un nivel cerca, un choque de fuentes o unos resultados piden
   mirar. Antes las cinco tarjetas pesaban igual y la urgencia solo la decía el
   orden; ahora la dice también la forma: las urgentes son tarjeta con halo, las
   informativas son filas compactas dentro de un mismo panel. */
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
 *  no cabían en media columna. */
function Lectura({ etiqueta, valor, tono, num, barra }) {
  const vacio = valor == null || valor === "—";
  const clave = tono === "auto" ? tonoDelNumero(num) : tono || "neutro";
  return (
    <div className="min-w-0">
      <p className="iv-etiqueta leading-none">{etiqueta}</p>
      {barra != null ? (
        <>
          <p className="iv-cifra text-apoyo font-semibold mt-1 leading-tight text-tinta-2">{valor}</p>
          <span className="block w-full max-w-[64px] h-1 mt-1.5 rounded-full bg-linea overflow-hidden"
                aria-hidden="true">
            <span className="block h-full bg-marca rounded-full" style={{ width: `${Math.min(100, barra)}%` }} />
          </span>
        </>
      ) : (
        <p className={cn("iv-cifra text-apoyo font-semibold mt-1 leading-tight break-words",
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

const ENLACE = "text-etiqueta text-marca underline-offset-4 decoration-marca/50 hover:underline " +
  "inline-flex items-center gap-1 py-1";

/** «INTC está a un 0.6% de tu Nivel 1» → «está a un 0.6% de tu Nivel 1». */
function sinPrefijoDelTicker(texto, symbol) {
  if (!texto || !symbol) return texto;
  return texto.startsWith(symbol + " ") ? texto.slice(symbol.length + 1) : texto;
}

export default function TarjetaAtencion({ tarjeta, orden }) {
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

  const ordinal = orden != null && (
    <span className={cn("iv-cifra text-etiqueta font-semibold tabular-nums shrink-0",
                        urgente ? "text-marca" : "text-tinta-3")}
>
      <span className="sr-only">Prioridad </span>{String(orden).padStart(2, "0")}
    </span>
  );

  const relatoComun = (
    <>
      {tarjeta.por_que && (
        <p className={cn("text-apoyo leading-relaxed mt-1 text-pretty",
                         urgente ? "text-tinta-2" : "text-tinta-3")}>
          {tarjeta.por_que}
        </p>
      )}

      {tarjeta.que_vigilar && (
        <p className="text-apoyo text-tinta mt-2 leading-snug text-pretty">
          <span className="iv-etiqueta mr-2 text-marca">Vigila</span>
          {tarjeta.que_vigilar}
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
    </>
  );

  /* ── Fila informativa ──────────────────────────────────────────────────
     Sin caja propia: vive dentro del panel que agrupa las informativas seguidas
     (lo monta HoyView), separada de la siguiente por un filete. La lectura va a la
     derecha en escritorio y en 2×2 debajo en móvil, sin rejilla de bordes. */
  if (!urgente) {
    return (
      <article
        className="px-4 py-4 sm:px-5 transition-colors duration-150 ease-out motion-reduce:transition-none
                   [@media(hover:hover)]:hover:bg-superficie-alt/60"
        data-testid={`tarjeta-hoy-${tarjeta.symbol}`}
      >
        <div className="flex flex-col md:flex-row md:gap-6">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 min-w-0">
              {ordinal}
              <Link to={tarjeta.ruta}
                    className="font-heading text-[17px] font-semibold leading-none text-tinta hover:text-marca
                               transition-colors duration-150 motion-reduce:transition-none shrink-0">
                {tarjeta.symbol}
              </Link>
              {tarjeta.nombre && tarjeta.nombre !== tarjeta.symbol && (
                <span className="text-apoyo text-tinta-3 truncate hidden sm:inline min-w-0">{tarjeta.nombre}</span>
              )}
              <span className="ml-auto flex items-center gap-3 shrink-0">
                {d.tiene_posicion && <span className="iv-etiqueta text-tinta-3">en cartera</span>}
                <TipoDiscreto meta={meta} />
              </span>
            </div>
            <p className="text-cuerpo text-tinta font-medium leading-snug mt-2 text-pretty">
              {sinPrefijoDelTicker(tarjeta.que_pasa, tarjeta.symbol)}
            </p>
            {relatoComun}
          </div>

          {lecturas.length > 0 && (
            <div className="mt-3 pt-3 border-t border-linea md:mt-0 md:pt-0 md:border-t-0 md:w-[224px] md:shrink-0
                            flex flex-col">
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                {lecturas.map((l) => <Lectura key={l.etiqueta} {...l} />)}
              </div>
              <Link to={tarjeta.ruta} className={cn(ENLACE, "mt-2 md:mt-auto self-start")}>
                Ver análisis <span aria-hidden="true">→</span>
              </Link>
            </div>
          )}
        </div>
      </article>
    );
  }

  /* ── Tarjeta urgente ───────────────────────────────────────────────────
     Halo del color de su tipo, chip sólido y el «qué pasa» a tamaño de titular: es
     lo primero que el ojo encuentra al abrir la portada. */
  return (
    <article
      className={cn("iv-panel overflow-hidden", meta.halo)}
      data-testid={`tarjeta-hoy-${tarjeta.symbol}`}
    >
      <div className="flex flex-col md:flex-row">
        <div className="flex-1 min-w-0 px-4 py-4 sm:px-5 sm:py-5">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 min-w-0">
            {ordinal}
            <Link to={tarjeta.ruta}
                  className="font-heading text-titulo font-semibold leading-none text-tinta hover:text-marca
                             transition-colors duration-150 motion-reduce:transition-none shrink-0">
              {tarjeta.symbol}
            </Link>
            {tarjeta.nombre && tarjeta.nombre !== tarjeta.symbol && (
              <span className="text-apoyo text-tinta-3 truncate hidden sm:inline min-w-0">{tarjeta.nombre}</span>
            )}
            <span className="ml-auto flex items-center gap-3 shrink-0">
              {d.tiene_posicion && <span className="iv-etiqueta text-tinta-3">en cartera</span>}
              <Chip tono={meta.tono} variante="solido">{meta.etiqueta}</Chip>
            </span>
          </div>

          {/* qué pasa · a tamaño de titular: es la frase que hay que leer hoy */}
          <p className="text-[17px] leading-snug text-tinta font-semibold mt-3 text-pretty">
            {sinPrefijoDelTicker(tarjeta.que_pasa, tarjeta.symbol)}
          </p>
          {relatoComun}
        </div>

        {/* ── Lectura numérica ───────────────────────────────────────
            La rejilla 2×2 de terminal, con filetes de un píxel. Las celdas son
            transparentes para que el tinte del halo llegue hasta el borde. */}
        {lecturas.length > 0 && (
          <div className="border-t md:border-t-0 md:border-l border-linea md:w-[248px] md:shrink-0 flex flex-col">
            <div className="grid grid-cols-2 flex-1">
              {lecturas.map((l, i) => (
                <div key={l.etiqueta}
                     className={cn("px-4 py-3 border-linea", i % 2 === 0 && "border-r",
                                   i < lecturas.length - 2 && "border-b")}>
                  <Lectura {...l} />
                </div>
              ))}
            </div>
            {/* El enlace vive con las cifras: es adonde se va DESPUÉS de mirarlas. */}
            <Link to={tarjeta.ruta} className={cn(ENLACE, "px-4 py-2.5 border-t border-linea")}>
              Ver análisis <span aria-hidden="true">→</span>
            </Link>
          </div>
        )}
      </div>
    </article>
  );
}
