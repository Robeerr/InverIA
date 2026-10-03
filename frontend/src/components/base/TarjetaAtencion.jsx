import React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import Chip from "./Chip";
import { fmtEur, fmtPct, fmtPctPlano, fmtPrice, fmtHace, fmtEnDias } from "@/lib/format";

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
  ruptura: { tono: "baja", etiqueta: "Ruptura", filo: "border-l-baja" },
  alerta: { tono: "aviso", etiqueta: "Alerta", filo: "border-l-aviso" },
  nivel: { tono: "marca", etiqueta: "Nivel cerca", filo: "border-l-marca" },
  divergencia: { tono: "info", etiqueta: "Choque", filo: "border-l-info" },
  confluencia: { tono: "sube", etiqueta: "Coincidencia", filo: "border-l-sube" },
  resultados: { tono: "neutro", etiqueta: "Resultados", filo: "border-l-linea-fuerte" },
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

/** Una celda de la lectura: etiqueta arriba, cifra mono debajo. */
function Lectura({ etiqueta, valor, tono, num, barra }) {
  const vacio = valor == null || valor === "—";
  const clave = tono === "auto" ? tonoDelNumero(num) : tono || "neutro";
  return (
    <div className="min-w-0">
      <p className="iv-etiqueta leading-none">{etiqueta}</p>
      {barra != null ? (
        <span className="inline-flex items-center gap-1.5 mt-1">
          <span className="w-10 h-1 rounded-full bg-linea overflow-hidden inline-block">
            <span className="block h-full bg-marca" style={{ width: `${Math.min(100, barra)}%` }} />
          </span>
          <span className="iv-cifra text-apoyo font-semibold text-tinta-2">{valor}</span>
        </span>
      ) : (
        <p className={cn("iv-cifra text-apoyo font-semibold mt-0.5 leading-tight break-words",
          vacio ? "text-tinta-3" : CLASES_TONO[clave] || CLASES_TONO.neutro)}>
          {valor ?? "—"}
        </p>
      )}
    </div>
  );
}

function EstadoMotorNiveles({ estado }) {
  if (!estado || estado === "confirma" || estado === "ok") return null;
  const texto = estado === "sin_datos"
    ? "Motor de niveles: sin datos todavía"
    : "Motor de niveles: sin zona en este precio";
  return (
    <Chip
      tono="neutro"
      variante="contorno"
      title={estado === "sin_datos"
        ? "Aún no se ha calculado para este símbolo. No es un rechazo ni una confirmación."
        : "Ha calculado zonas para este símbolo, pero ninguna cae en este precio."}
    >
      {texto}
    </Chip>
  );
}

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
  const destacada = orden === 1;

  return (
    <article
      className={cn(
        // Tarjeta, no fila. La etapa anterior las encadenaba como una tabla rayada; el
        // rediseño las separa en piezas con cuerpo, y la urgencia la siguen diciendo el
        // ordinal y el orden. El TIPO lo dice el chip de color. La #1 lleva el halo
        // naranja: es la única que brilla, y por eso se ve primero.
        "iv-panel overflow-hidden transition-colors",
        destacada ? "iv-halo-marca" : "hover:border-linea-fuerte"
      )}
      data-testid={`tarjeta-hoy-${tarjeta.symbol}`}
    >
      <div className="flex flex-col md:flex-row">
        {/* El ordinal, en su propia columna. Fuera del texto se lee como índice —01, 02,
            03— y no compite con el ticker, que es lo que se busca al barrer la lista. */}
        {/* ── Relato ─────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 px-5 py-4">
          <div className="flex items-center gap-2.5 min-w-0">
            {/* El ordinal en su cajita, como índice de la lista: la lista va por urgencia
                y el número lo dice. En naranja solo el primero. */}
            {orden != null && (
              <span className={cn(
                "iv-cifra text-etiqueta font-semibold leading-none tabular-nums shrink-0",
                "rounded-iv-sm border px-1.5 py-1",
                destacada ? "text-marca border-marca/40 bg-marca/10" : "text-tinta-3 border-linea"
              )}>
                {String(orden).padStart(2, "0")}
              </span>
            )}
            <Link
              to={tarjeta.ruta}
              className={cn("font-heading text-titulo leading-none transition-colors shrink-0",
                destacada ? "text-marca hover:brightness-110" : "text-tinta hover:text-marca")}
            >
              {tarjeta.symbol}
            </Link>
            {tarjeta.nombre && tarjeta.nombre !== tarjeta.symbol && (
              <span className="text-apoyo text-tinta-3 truncate hidden sm:inline">{tarjeta.nombre}</span>
            )}
            <span className="ml-auto flex items-center gap-1.5 shrink-0">
              <Chip tono={meta.tono}>{meta.etiqueta}</Chip>
              {d.tiene_posicion && <Chip tono="neutro" variante="contorno">cartera</Chip>}
            </span>
          </div>

          {/* qué pasa */}
          <p className="text-cuerpo text-tinta font-medium leading-snug mt-1.5 text-pretty">
            {sinPrefijoDelTicker(tarjeta.que_pasa, tarjeta.symbol)}
          </p>

          {/* por qué */}
          <p className="text-apoyo text-tinta-2 mt-1 leading-relaxed">{tarjeta.por_que}</p>

          {/* qué vigilar */}
          <p className="text-apoyo text-tinta mt-1.5">
            <span className="iv-etiqueta mr-2 text-marca">Vigila</span>
            {tarjeta.que_vigilar}
          </p>

          {(razonesYFuentes.length > 0 || tarjeta.tambien?.length > 0
            || (d.motor_niveles && d.motor_niveles !== "confirma" && d.motor_niveles !== "ok")) && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-2">
              <EstadoMotorNiveles estado={d.motor_niveles} />
              {razonesYFuentes.map((r) => (
                <Chip key={r} tono="neutro" variante="contorno">{r}</Chip>
              ))}
              {Array.isArray(tarjeta.tambien) && tarjeta.tambien.length > 0 && (
                <span className="text-etiqueta text-tinta-3">
                  también: {tarjeta.tambien.map((t) => t.que_pasa).join(" · ")}
                </span>
              )}
            </div>
          )}

          {tarjeta.aviso && (
            <p className="text-apoyo text-aviso mt-2 bg-aviso/10 border border-aviso/25 rounded-iv-sm px-2 py-1.5">
              {tarjeta.aviso}
            </p>
          )}
        </div>

        {/* ── Lectura numérica ───────────────────────────────────────
            El panel de cifras. En escritorio va a la derecha con un filo que lo
            separa del relato; en móvil baja debajo con un filo superior. Es lo
            que convierte la tarjeta de prosa en una fila de terminal. */}
        {lecturas.length > 0 && (
          <div className="border-t md:border-t-0 md:border-l border-linea md:w-[264px] md:shrink-0 flex flex-col">
            {/* Rejilla de 2×2 con filetes de un píxel: el fondo de la rejilla es la línea
                y cada celda tapa su hueco, así las separaciones salen siempre iguales. */}
            <div className="grid grid-cols-2 gap-px bg-linea flex-1">
              {lecturas.map((l) => (
                <div key={l.etiqueta} className="bg-superficie px-4 py-3">
                  <Lectura {...l} />
                </div>
              ))}
            </div>
            {/* El enlace vive con las cifras y no con el relato: es adonde se va DESPUÉS
                de mirarlas, cuando el resumen no basta. */}
            <Link to={tarjeta.ruta}
                  className="text-etiqueta text-marca hover:underline px-4 py-2 border-t border-linea">
              Ver análisis →
            </Link>
          </div>
        )}
      </div>
    </article>
  );
}
