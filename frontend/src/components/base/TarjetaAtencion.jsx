import React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import Chip from "./Chip";
import { fmtPrice } from "@/lib/format";

/* TarjetaAtencion · la unidad de «Lo que importa hoy»
   ─────────────────────────────────────────────────────────────────────────────
   La tarjeta tiene tres líneas y no son decorativas: son las tres preguntas que
   el Dashboard existe para contestar.

       qué pasa    → el titular, con el ticker y el dato
       por qué     → el respaldo: fuerza del nivel, métodos que coinciden, quién lo dice
       qué vigilar → lo accionable

   Si una tarjeta no puede rellenar las tres, el backend no la emite. Por eso aquí
   no hay ramas para «y si no hay porqué»: llegar sin porqué sería un fallo del
   servidor, no un caso a maquetar.

   El backend manda el texto ya redactado. Es deliberado: la frase depende de datos
   que solo el servidor tiene cruzados (posición, niveles, menciones), y partirla
   entre los dos lados garantizaría que un día digan cosas distintas. */

/* Un tono por tipo, y los seis distinguibles entre sí.
   La primera versión daba ámbar a la alerta, al nivel y al choque; en oscuro los
   tres bordes quedaban del mismo color y el código de color no distinguía nada,
   que es justo lo que tenía que hacer. Ahora:

     rojo   pierdes dinero        ámbar  te avisaste tú
     marca  precio en zona        azul   tus fuentes y el motor no coinciden
     verde  coinciden             gris   evento de agenda, no señal */
const TIPOS = {
  ruptura: { tono: "baja", etiqueta: "Ruptura" },
  alerta: { tono: "aviso", etiqueta: "Alerta" },
  nivel: { tono: "marca", etiqueta: "Nivel cerca" },
  divergencia: { tono: "info", etiqueta: "Choque" },
  confluencia: { tono: "sube", etiqueta: "Coincidencia" },
  resultados: { tono: "neutro", etiqueta: "Resultados" },
};

function BarraFuerza({ valor }) {
  if (!valor) return null;
  return (
    <span className="inline-flex items-center gap-1.5" title={`Fuerza ${valor} sobre 100`}>
      <span className="w-12 h-1 rounded-full bg-linea overflow-hidden inline-block">
        <span className="block h-full bg-marca" style={{ width: `${Math.min(100, valor)}%` }} />
      </span>
      <span className="iv-cifra text-etiqueta text-tinta-3">{valor}/100</span>
    </span>
  );
}

export default function TarjetaAtencion({ tarjeta, orden }) {
  const meta = TIPOS[tarjeta.tipo] || { tono: "neutro", etiqueta: tarjeta.tipo };
  const d = tarjeta.datos || {};

  return (
    <article
      className={cn(
        "iv-panel p-4 sm:p-5 relative",
        // El borde izquierdo es del color del tipo: deja leer la naturaleza del aviso
        // antes de leer el texto, que es lo que permite barrer cinco tarjetas de un vistazo.
        "border-l-[3px]",
        meta.tono === "baja" && "border-l-baja",
        meta.tono === "aviso" && "border-l-aviso",
        meta.tono === "marca" && "border-l-marca",
        meta.tono === "sube" && "border-l-sube",
        meta.tono === "info" && "border-l-info",
        meta.tono === "neutro" && "border-l-neutro"
      )}
      data-testid={`tarjeta-hoy-${tarjeta.symbol}`}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0 flex-wrap">
          {orden != null && (
            <span className="iv-cifra text-etiqueta text-tinta-3 tabular-nums">{orden}</span>
          )}
          <Link
            to={tarjeta.ruta}
            className="iv-cifra font-bold text-cuerpo text-tinta hover:text-marca transition-colors"
          >
            {tarjeta.symbol}
          </Link>
          <Chip tono={meta.tono}>{meta.etiqueta}</Chip>
          {d.tiene_posicion && <Chip tono="neutro" variante="contorno">en cartera</Chip>}
        </div>
        {d.fuerza != null && <BarraFuerza valor={d.fuerza} />}
      </div>

      {/* 1 · ¿Qué está pasando? */}
      <p className="text-cuerpo text-tinta font-medium leading-snug">{tarjeta.que_pasa}</p>

      {/* 2 · ¿Por qué? */}
      <p className="text-apoyo text-tinta-2 mt-1.5">{tarjeta.por_que}</p>

      {/* 3 · ¿Qué debería vigilar? */}
      <p className="text-apoyo text-tinta mt-2 pt-2 border-t border-linea">
        <span className="iv-etiqueta mr-2">Vigila</span>
        {tarjeta.que_vigilar}
      </p>

      {/* Los métodos que coinciden en el nivel. Es el «porqué» del porqué, y hoy solo
          se ve dentro de la ficha de la acción. */}
      {Array.isArray(d.razones) && d.razones.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {d.razones.map((r) => (
            <Chip key={r} tono="neutro" variante="contorno">{r}</Chip>
          ))}
        </div>
      )}

      {Array.isArray(d.fuentes) && d.fuentes.length > 0 && (
        <p className="text-etiqueta text-tinta-3 mt-2 truncate" title={d.fuentes.join(" · ")}>
          {d.fuentes.join(" · ")}
        </p>
      )}

      {(d.price != null || d.target != null) && (
        <div className="flex items-baseline gap-4 mt-2 iv-cifra text-apoyo">
          {d.price != null && (
            <span className="text-tinta-3">
              precio <span className="text-tinta font-semibold">{fmtPrice(d.price)}</span>
            </span>
          )}
          {d.target != null && (
            <span className="text-tinta-3">
              objetivo <span className="text-tinta font-semibold">{fmtPrice(d.target)}</span>
            </span>
          )}
        </div>
      )}

      {/* Lo que este ticker también dispara. No merece tarjeta propia, pero sí saberse. */}
      {Array.isArray(tarjeta.tambien) && tarjeta.tambien.length > 0 && (
        <p className="text-etiqueta text-tinta-3 mt-2">
          También: {tarjeta.tambien.map((t) => t.que_pasa).join(" · ")}
        </p>
      )}

      {/* El aviso del motor sobre la calidad del dato va PEGADO a lo que sostiene:
          una confianza recortada solo significa algo al lado de su afirmación. */}
      {tarjeta.aviso && (
        <p className="text-apoyo text-aviso mt-2 bg-aviso/10 border border-aviso/25 rounded-iv-sm px-2 py-1.5">
          {tarjeta.aviso}
        </p>
      )}
    </article>
  );
}
