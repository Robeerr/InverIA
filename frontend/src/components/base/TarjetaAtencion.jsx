import React from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import Chip from "./Chip";

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

/* Estado del MOTOR DE NIVELES, explícito y separado del de oportunidades.
   Son dos cosas distintas que se llamaban igual:
     · niveles       → buy_levels con fuerza y métodos. Vive en la caché del proceso,
                       así que puede no estar. Que falte NO es un rechazo.
     · oportunidades → el score que cruza con tus fuentes. Persistido en Mongo.
   Sin esta distinción, «el motor no tiene zona» se leía como «el motor lo descarta». */
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

/** «INTC está a un 0.6% de tu Nivel 1» → «está a un 0.6% de tu Nivel 1».
 *
 *  El titular lo redacta el servidor empezando por el ticker, porque fuera de esta
 *  tarjeta (una notificación, un correo) tiene que sostenerse solo. Aquí el ticker
 *  ya está al lado, así que repetirlo obligaba a poner el titular en otra fila. */
function sinPrefijoDelTicker(texto, symbol) {
  if (!texto || !symbol) return texto;
  return texto.startsWith(symbol + " ")
    ? texto.slice(symbol.length + 1)
    : texto;
}

export default function TarjetaAtencion({ tarjeta, orden }) {
  const meta = TIPOS[tarjeta.tipo] || { tono: "neutro", etiqueta: tarjeta.tipo };
  const d = tarjeta.datos || {};
  const razonesYFuentes = [
    ...(Array.isArray(d.razones) ? d.razones : []),
    ...(Array.isArray(d.fuentes) ? d.fuentes : []),
  ];

  return (
    <article
      className={cn(
        "iv-panel px-4 py-3 relative",
        // LEY 4 · el filo ámbar marca LA decisión, y solo hay una por pantalla. Antes
        // cada tipo traía su color y las cinco tarjetas competían entre sí: seis colores
        // de filo convertían la lista en un semáforo, y cuando todo destaca no destaca
        // nada. El tipo lo sigue diciendo el chip, que es su sitio.
        // antes de leer el texto, que es lo que permite barrer cinco tarjetas de un vistazo.
        "border-l-[3px]",
        orden === 1 ? "border-l-marca" : "border-l-linea-fuerte"
      )}
      data-testid={`tarjeta-hoy-${tarjeta.symbol}`}
    >
      {/* Cabecera y titular en la MISMA línea siempre que quepan: el titular ya
          empieza por el ticker, así que repetirlo arriba en su propia fila gastaba
          una línea entera por tarjeta sin añadir nada. */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2 min-w-0">
          {orden != null && (
            <span className="iv-cifra text-etiqueta text-tinta-3 tabular-nums shrink-0">{orden}</span>
          )}
          <Link
            to={tarjeta.ruta}
            className="iv-cifra font-bold text-cuerpo text-tinta hover:text-marca transition-colors shrink-0"
          >
            {tarjeta.symbol}
          </Link>
          {/* 1 · ¿Qué está pasando? Sin el prefijo del ticker, que ya está al lado. */}
          <p className="text-cuerpo text-tinta font-medium leading-snug truncate">
            {sinPrefijoDelTicker(tarjeta.que_pasa, tarjeta.symbol)}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {d.fuerza != null && <BarraFuerza valor={d.fuerza} />}
          <Chip tono={meta.tono}>{meta.etiqueta}</Chip>
          {d.tiene_posicion && <Chip tono="neutro" variante="contorno">cartera</Chip>}
        </div>
      </div>

      {/* 2 · ¿Por qué? */}
      <p className="text-apoyo text-tinta-2 mt-1">{tarjeta.por_que}</p>

      {/* 3 · ¿Qué debería vigilar? Sin separador ni relleno: la etiqueta ya marca
          dónde empieza, y una línea de 1px por tarjeta son cinco líneas de nada. */}
      <p className="text-apoyo text-tinta mt-1">
        <span className="iv-etiqueta mr-2">Vigila</span>
        {tarjeta.que_vigilar}
      </p>

      {/* Razones, fuentes y «también» comparten fila cuando caben. La fila de
          «precio X · objetivo Y» se ha quitado: repetía literalmente lo que ya dice
          la línea de Vigila («Precio 98.38 contra 97.80»). */}
      {(razonesYFuentes.length > 0 || tarjeta.tambien?.length > 0
        || (d.motor_niveles && d.motor_niveles !== "confirma" && d.motor_niveles !== "ok")) && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1.5">
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
