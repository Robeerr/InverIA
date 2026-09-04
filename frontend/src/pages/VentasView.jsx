import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";
import { aNumero } from "../lib/format";
import RiesgoVenta from "../components/RiesgoVenta";
import ExtractoMargen from "../components/ExtractoMargen";
import { useSignals } from "../hooks/useSignals";

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
function datosPosicion(p, comoBroker) {
  // La media ponderada se enseña ENTERA o no se enseña. Antes cada cifra caía por su
  // cuenta: bastaba con que faltara el coste en euros —lo que ocurre en cuanto UNA compra
  // de la historia no tiene tipo de cambio— para que la fila mezclara el precio medio del
  // bróker con el coste y la ganancia de FIFO/LIFO, debajo de un botón que dice "✓ Como en
  // DEGIRO". Esa fila no cuadra con ninguna de las dos pantallas, y lo peor es que no lo
  // dice: parece la cifra del bróker y es otra cosa.
  const pmpCompleta = p.ponderada?.pnl_eur != null && p.ponderada?.coste_eur != null
    && p.precio_medio_ponderado != null;
  const usaPmp = comoBroker && pmpCompleta;
  return {
    g: usaPmp ? p.ponderada : p,
    precioMedio: usaPmp ? p.precio_medio_ponderado : p.precio_medio,
    invertido: usaPmp ? p.ponderada.coste_eur : p.coste_eur,
    // Para poder decirlo en la fila en vez de dejar que el número mienta en silencio.
    sinPmp: comoBroker && !pmpCompleta,
    // Solo se enseña el otro precio medio cuando difiere de verdad; por debajo de un
    // céntimo, dos cifras iguales una encima de otra parecen un fallo de la pantalla.
    hayOtroMedio: p.precio_medio_ponderado != null
      && Math.abs(p.precio_medio_ponderado - (p.precio_medio ?? 0)) > 0.01,
  };
}

const NIVEL_ETIQUETA = {
  deseado: "Deseado", nivel1: "Nivel 1", nivel2: "Nivel 2",
  nivel3: "Nivel 3", nivel4: "Nivel 4", nivel5: "Nivel 5",
};

function Chip({ children, tono: t = "neutro", title }) {
  const estilos = {
    neutro: "bg-superficie-alt text-tinta-3",
    nivel: "bg-info/12 text-info",
    aviso: "bg-aviso/15 text-aviso",
  }[t];
  return (
    <span title={title} className={`font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${estilos}`}>
      {children}
    </span>
  );
}

// ── Cifra grande de cabecera ─────────────────────────────────────────────────
// La ayuda NO puede vivir solo en `title=`: en el móvil no hay ratón que posar encima, así
// que el texto era sencillamente inalcanzable. Es un botón que despliega el texto bajo la
// cifra, y de paso funciona con teclado.
function Kpi({ etiqueta, significa, valor, sub, acento = false, ayuda }) {
  const [abierta, setAbierta] = React.useState(false);
  return (
    <div className="iv-panel px-4 py-3 flex-1 min-w-[150px]">
      <p className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono flex items-center gap-1">
        {etiqueta}
        {ayuda && (
          <button type="button" onClick={() => setAbierta((a) => !a)}
                  aria-expanded={abierta}
                  aria-label={`Qué significa ${etiqueta}`}
                  className="opacity-60 hover:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded">
            ⓘ
          </button>
        )}
      </p>
      {/* Qué es, en cristiano, entre el nombre y la cifra. La etiqueta de arriba es el
          nombre técnico —REALIZADO, LATENTE— y no dice nada a quien no lo sepa ya; el pie
          de debajo es el detalle (cuántas ventas, qué método). Faltaba lo del medio: la
          frase que contesta "¿esto qué es?" sin tener que abrir la ayuda. */}
      {significa && (
        <p className="text-[11px] text-tinta-2 mt-0.5 leading-snug">{significa}</p>
      )}
      <p className={`font-mono font-bold mt-1 ${acento ? "text-2xl" : "text-xl"} ${tono(valor)}`}>
        {eur(valor)}
      </p>
      {sub && <p className="text-[11px] text-tinta-3 mt-0.5">{sub}</p>}
      {abierta && ayuda && (
        <p className="text-[11px] text-tinta-3 mt-2 pt-2 border-t border-linea leading-relaxed">
          {ayuda}
        </p>
      )}
    </div>
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
    <div className="bg-superficie-alt px-4 py-3 border-t border-linea">
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
          <p className="text-apoyo text-tinta-2 mb-2">
            Has vendido <b className="text-tinta">{partes.join(" y ")}</b>.
          </p>
        ) : null;
      })()}
      <p className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono mb-2">
        Estas acciones salieron de
      </p>
      <div className="space-y-1.5">
        {lotes.map((l, i) => (
          <div key={i} className="flex items-center gap-3 flex-wrap text-xs">
            <span className="font-mono text-tinta-3 w-20">{fecha(l.fecha_compra)}</span>
            <span className="font-mono font-semibold">{l.acciones} × {usd(l.precio_compra, divisa)}</span>
            {l.nivel && <Chip tono="nivel">{NIVEL_ETIQUETA[l.nivel] || l.nivel}</Chip>}
            {l.comision_parte > 0 && (
              <span className="text-[11px] text-tinta-3">
                +{usd(l.comision_parte, divisa)} comisión
              </span>
            )}
            <span className="ml-auto font-mono text-tinta-3">
              coste {usd(l.coste_divisa, divisa)}
            </span>
          </div>
        ))}
      </div>
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
    <div className="border-b border-linea last:border-0">
      <div className="px-4 py-3 flex items-center gap-3 flex-wrap hover:bg-superficie-alt transition-colors">
        {/* aria-label descriptivo, no fijo: un lector de pantalla leía 146 botones
            idénticos. min-h para que el dedo acierte en el móvil. */}
        <button onClick={() => setAbierto((o) => !o)}
                aria-expanded={abierto}
                aria-label={`${abierto ? "Ocultar" : "Ver"} el detalle de la venta de ${v.acciones} ${v.symbol} del ${fecha(v.fecha)}`}
                className="flex items-center gap-3 flex-1 min-w-0 text-left min-h-[44px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded">
          <span className="font-mono text-[11px] text-tinta-3 w-16 shrink-0">{fecha(v.fecha)}</span>
          <span className="font-mono font-bold text-sm w-16 shrink-0">{v.symbol}</span>
          <span className="font-mono text-xs text-tinta-3 shrink-0">
            {v.acciones} × {usd(v.precio_venta, v.divisa)}
          </span>
          {v.sin_cubrir > 0 && (
            <Chip tono="aviso" title="Se han vendido más acciones de las que constan compradas. Añade la compra que falte.">
              faltan {v.sin_cubrir}
            </Chip>
          )}
        </button>

        <div className="text-right shrink-0">
          <p className={`font-mono font-bold text-sm ${tono(m.ganancia_eur ?? m.ganancia_divisa)}`}>
            {m.ganancia_eur != null ? eur(m.ganancia_eur) : usd(m.ganancia_divisa, v.divisa)}
          </p>
          <p className={`font-mono text-[11px] ${tono(m.pct_eur ?? m.pct)}`}>
            {pct(m.pct_eur ?? m.pct)}
            {m.ganancia_eur != null && (
              <span className="text-tinta-3"> · {usd(m.ganancia_divisa, v.divisa)}</span>
            )}
          </p>
        </div>

        <button onClick={() => setAbierto((o) => !o)}
                className="text-tinta-3 text-xs w-5 shrink-0" aria-label="Ver detalle">
          {abierto ? "▲" : "▼"}
        </button>
      </div>

      {abierto && (
        <div>
          <DetalleLotes lotes={m.lotes} divisa={v.divisa} />
          <div className="px-4 py-3 bg-superficie-alt border-t border-linea text-xs space-y-1">
            {/* Las DOS columnas, divisa y euros, en cada paso. Antes solo salían los
                dólares y luego aparecía la ganancia en euros: el salto de "259 $" a "209 €"
                había que creérselo. Con los dos lados y el tipo de cambio, la cuenta se
                rehace a mano en un minuto — que es la única forma de fiarse de una cifra. */}
            {/* QUÉ MÉTODO estás viendo. La cifra grande cambia con el interruptor de
                DEGIRO y nada lo decía: la MISMA venta salía a −56,39 € y a +282,04 € en dos
                pantallas por lo demás idénticas, sin forma de saber cuál era cuál. Un
                número que cambia sin decir por qué se lee como un fallo, y con razón. */}
            <p className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono pb-1">
              Calculado por <b className="text-tinta-2">{nombreMetodo}</b>
              {nombreMetodo === "media ponderada" && " · el método de DEGIRO"}
              {nombreMetodo === "FIFO" && " · el que va a tu declaración"}
              {nombreMetodo === "LIFO" && " · como vendes tú"}
            </p>
            <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 gap-y-1 items-baseline">
              <span className="text-[10px] uppercase tracking-wider text-tinta-3 font-mono">Concepto</span>
              <span className="text-[10px] uppercase tracking-wider text-tinta-3 font-mono text-right">
                {v.divisa === "USD" ? "Dólares" : v.divisa}
              </span>
              <span className="text-[10px] uppercase tracking-wider text-tinta-3 font-mono text-right">Euros</span>

              <span className="text-tinta-3">Ingresado (menos comisión)</span>
              <span className="font-mono text-right">{usd(m.ingreso_divisa, v.divisa)}</span>
              <span className="font-mono text-right">{eur(m.ingreso_eur)}</span>

              <span className="text-tinta-3">Coste de esas acciones</span>
              <span className="font-mono text-right">{usd(m.coste_divisa, v.divisa)}</span>
              <span className="font-mono text-right">{eur(m.coste_eur)}</span>

              <span className="font-semibold">Ganancia</span>
              <span className={`font-mono text-right font-semibold ${tono(m.ganancia_divisa)}`}>
                {usd(m.ganancia_divisa, v.divisa)}
              </span>
              <span className={`font-mono text-right font-semibold ${tono(m.ganancia_eur)}`}>
                {eur(m.ganancia_eur)}
              </span>

              {/* Los DOS porcentajes, etiquetados. Antes se enseñaba solo el de euros junto
                  a las cifras en dólares, donde el porcentaje es otro: en esta misma venta,
                  +16,96% en euros y +18,41% en dólares. Parecía el de los dólares. */}
              <span className="text-tinta-3">Porcentaje</span>
              <span className={`font-mono text-right ${tono(m.pct)}`}>{pct(m.pct)}</span>
              <span className={`font-mono text-right ${tono(m.pct_eur)}`}>{pct(m.pct_eur)}</span>
            </div>

            {v.tasa_venta && (
              <p className="text-[10px] text-tinta-3 pt-1">
                Cambio del día de la venta: 1 € = {v.tasa_venta} {v.divisa}. El coste va al
                cambio del día de CADA compra, que es el que ves en cada línea de arriba.
              </p>
            )}

            {m.efecto_divisa_eur != null && (
              // Aparece sola en cuanto ves que ganaste en dólares y menos en euros.
              <div className="flex justify-between pt-1">
                <span className="text-tinta-3" title="Parte del resultado que se debe al movimiento del euro frente a la divisa, y no a la acción. Si es negativo, el euro se comió parte de tu ganancia.">
                  De la ganancia en euros, por el movimiento del euro ⓘ
                </span>
                <span className={`font-mono ${tono(m.efecto_divisa_eur)}`}>{eur(m.efecto_divisa_eur)}</span>
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
              <p className="text-apoyo text-tinta-2 mt-1.5 leading-snug">
                <b>{m.ganancia_divisa > 0 ? "Ganaste" : "Perdiste"} en {v.divisa} y{" "}
                {m.ganancia_eur > 0 ? "ganaste" : "perdiste"} en euros.</b>{" "}
                No es un error: el euro se movió entre tus compras y esta venta, así que
                cada {v.divisa === "USD" ? "dólar" : v.divisa} que recuperaste vale{" "}
                {m.ganancia_eur < 0 ? "menos" : "más"} euros que los que pusiste. Lo que
                cuenta para ti —y para Hacienda— es la cifra en euros.
              </p>
            )}
            {!m.exacto && (
              <p className="text-[11px] text-aviso pt-1">
                Falta el tipo de cambio de alguna compra: la ganancia en euros de esta venta
                no se puede calcular y no entra en los totales.
              </p>
            )}
            {/* Los otros dos métodos, siempre. Es la misma venta contada de tres formas y
                cada una sirve para algo distinto; enseñar solo una invita a usarla para todo. */}
            <div className="pt-2 border-t border-linea mt-1 space-y-0.5">
              {difiere && (
                <div className="flex justify-between">
                  <span className="text-tinta-3">
                    Por <b>{nombreOtro}</b>
                    {nombreOtro === "FIFO"
                      ? " (lo que va a tu declaración)"
                      : " (como vendes tú)"}
                  </span>
                  <span className="font-mono text-tinta-3">
                    {otro.ganancia_eur != null ? eur(otro.ganancia_eur) : usd(otro.ganancia_divisa, v.divisa)}
                    {" · "}{pct(otro.pct_eur ?? otro.pct)}
                  </span>
                </div>
              )}
              {v.ponderada && !usaPmp && (
                <div className="flex justify-between">
                  <span className="text-tinta-3"
                        title="Media ponderada: el método que usa tu bróker para su pantalla. Todas tus acciones cuestan lo mismo (la media), así que no distingue niveles. Sirve para cuadrar con DEGIRO, no para la declaración.">
                    Por <b>media ponderada</b> (como tu bróker) ⓘ
                  </span>
                  {/* En EUROS lo primero: es la cifra que enseña DEGIRO y con la que se
                      compara. En dólares al lado, para cuadrar con la línea de arriba. */}
                  <span className="font-mono text-tinta-3 text-right">
                    {v.ponderada.ganancia_eur != null && (
                      <b className="text-tinta">{eur(v.ponderada.ganancia_eur)}</b>
                    )}
                    {v.ponderada.pct_eur != null && ` · ${pct(v.ponderada.pct_eur)}`}
                    <span className="block text-[10px]">
                      {usd(v.ponderada.ganancia_divisa, v.divisa)}
                      {v.ponderada.pct != null && ` · ${pct(v.ponderada.pct)}`}
                    </span>
                  </span>
                </div>
              )}
              {/* Por qué unas ventas cuadran con el bróker y otras no. Sin esto, la
                  diferencia se lee como un fallo de cálculo, y no lo es. */}
              {v.ponderada && (difiere || v.ponderada.ganancia_eur != null) && (
                <p className="text-[11px] text-tinta-3 pt-1 leading-snug">
                  {v.metodos_incoherentes
                    ? "⚠ Esta venta debería haber cerrado la posición, y entonces los tres "
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
            <div className="pt-2">
              <button onClick={() => onBorrar(v)}
                      aria-label={`Borrar la venta de ${v.acciones} ${v.symbol} del ${fecha(v.fecha)}`}
                      className="text-[11px] text-baja hover:underline min-h-[44px] px-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded">
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
    <div className="iv-panel p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-heading font-bold text-sm">Importar el CSV de DEGIRO</h3>
        <button type="button" onClick={onCerrar} className="text-tinta-3 text-sm">✕</button>
      </div>

      <p className="text-[11px] text-tinta-3 leading-relaxed">
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
             className="text-xs w-full" />

      {archivo && !previo && (
        <button onClick={() => leer.mutate()} disabled={leer.isPending}
                className="w-full bg-marca text-marca-tinta rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
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
            <div className="text-[11px] text-tinta-3 border-t border-linea pt-2">
              Este es el fichero de <b>Cuenta</b> (Account.csv), el de los dividendos — no
              el de Transacciones. <b>{previo.resumen?.total}</b> apunte(s) de{" "}
              {fecha(previo.resumen?.desde)} a {fecha(previo.resumen?.hasta)}:{" "}
              {previo.resumen?.cobros} cobro(s) y {previo.resumen?.retenciones} retención(es).
              {" "}Si lo que querías era añadir compras y ventas, exporta{" "}
              <b>Actividad → Transacciones</b>.
            </div>
          ) : (
            <div className="text-[11px] text-tinta-3 border-t border-linea pt-2">
              <b>{previo.resumen?.total}</b> operaciones ·{" "}
              {previo.resumen?.compras} compras · {previo.resumen?.ventas} ventas ·{" "}
              de {fecha(previo.resumen?.desde)} a {fecha(previo.resumen?.hasta)} ·{" "}
              {usd(previo.resumen?.comisiones)} de comisiones reales
            </div>
          )}

          {!!previo.errores?.length && (
            <div className="text-[11px] text-aviso">
              {previo.errores.length} línea(s) no se han entendido y quedan fuera:
              <ul className="list-disc ml-4">
                {previo.errores.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </div>
          )}

          {/* El emparejamiento. Solo se pregunta una vez por producto: el ISIN se guarda en
              la Cartera y la próxima importación ya no lo pide. */}
          <div>
            <p className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono mb-2">
              ¿A qué acción corresponde cada producto?
            </p>
            <div className="space-y-1.5">
              {(previo.productos || []).map((p) => (
                <div key={p.isin} className="flex items-center gap-2 flex-wrap text-xs">
                  <span className="flex-1 min-w-0 truncate" title={p.isin}>{p.producto}</span>
                  <span className="text-[10px] text-tinta-3 font-mono">{p.operaciones} ops</span>
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
                    className="border border-linea rounded px-2 py-1 font-mono text-xs w-28 bg-transparent disabled:opacity-40" />
                  <label className="flex items-center gap-1 text-[10px] text-tinta-3 cursor-pointer"
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
            <p className="text-[11px] text-tinta-3 mt-2">
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
              <p className="text-[11px] text-aviso mt-1">
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
                  className="w-full bg-marca text-marca-tinta rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
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

  if (isPending) return <p className="px-4 py-3 text-xs text-tinta-3">Cargando…</p>;

  const est = data?.[metodo];
  const abiertos = est?.abiertos || [];
  const divisa = data?.divisa || "USD";
  const compradas = (data?.compras || []).reduce((s, c) => s + (c.acciones || 0), 0);
  const vendidas = compradas - (est?.acciones_abiertas || 0);

  return (
    <div className="bg-superficie-alt px-4 py-3 border-t border-linea">
      <p className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono mb-2">
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
        <p className="text-[11px] text-tinta-3 mb-1 leading-snug">
          Valorado a <b className="font-mono">{usd(data.precio_actual, divisa)}</b>
          {data.cierre_anterior != null && (
            <> · cierre anterior <span className="font-mono">{usd(data.cierre_anterior, divisa)}</span></>
          )}
          {data.estado_mercado && <> · {data.estado_mercado.toLowerCase()}</>}
        </p>
      )}

      {!!abiertos.length && data?.cambio_medio_compras && divisa !== "EUR" && (
        <p className="text-[11px] text-tinta-3 mb-2 leading-snug">
          Tu coste se pasó a euros a <b className="font-mono">{data.cambio_medio_compras}</b>{" "}
          {divisa}/€ de media
          {data.cambio_hoy && <> (hoy: <span className="font-mono">{data.cambio_hoy}</span>)</>}.
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
        <p className="text-xs text-tinta-3">
          No queda nada abierto de {symbol}: se ha vendido la posición entera.
        </p>
      ) : (
        <div className="space-y-1.5">
          {abiertos.map((l) => (
            <div key={l.id} className="flex items-center gap-3 flex-wrap text-xs">
              <span className="font-mono text-tinta-3 w-20 shrink-0">{fecha(l.fecha)}</span>
              {!!l.tasa && divisa !== "EUR" && (
                <span className="font-mono text-[10px] text-tinta-3"
                      title={`Cambio con el que el coste de esta compra se pasó a euros. Es el del día de la fecha que tiene el lote; si esa fecha no es la de tu compra real, esta cifra tampoco lo es.`}>
                  @{Math.round(l.tasa * 1e4) / 1e4}
                </span>
              )}
              <span className="font-mono font-semibold">
                {l.acciones_abiertas} × {usd(l.precio, divisa)}
              </span>
              {l.acciones_abiertas !== l.acciones && (
                <span className="text-[10px] text-tinta-3">(de {l.acciones})</span>
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
                        className="text-[10px] bg-transparent border border-linea rounded px-1 py-0.5 text-tinta-3">
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
              <span className="ml-auto font-mono text-tinta-3">
                {l.coste_eur != null ? eur(l.coste_eur) : usd(l.coste_divisa, divisa)}
              </span>
              <button
                onClick={() => window.confirm(`¿Borrar la compra de ${l.acciones} ${symbol} del ${fecha(l.fecha)}?`) && borrar.mutate({ id: l.id })}
                className="text-[11px] text-baja hover:underline shrink-0 min-h-[44px] px-2 -my-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded">
                borrar
              </button>
            </div>
          ))}
        </div>
      )}

      {/* El orden de consumo es la respuesta a "de qué nivel será la próxima venta". */}
      {abiertos.length > 1 && (
        <p className="text-[11px] text-tinta-3 mt-2 pt-2 border-t border-linea">
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
      <span className="text-[10px] uppercase tracking-wider text-tinta-3 font-mono flex items-center gap-1">
        {label}{ayuda && <span title={ayuda} className="cursor-help opacity-60">ⓘ</span>}
      </span>
      {children}
    </label>
  );
}

const inputCls = "mt-1 w-full border border-linea rounded px-2 py-1.5 font-mono text-sm bg-transparent";

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
      <p className="text-[11px] text-aviso">
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
    <div className="rounded border border-linea px-3 py-2 space-y-1.5">
      <p className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono">
        Tienes {disponibles} acciones de {sym}
      </p>
      {n > 0 && (
        <>
          {n > disponibles + 1e-9 && (
            <p className="text-[11px] text-aviso">
              Estás vendiendo más de las que constan compradas ({disponibles}). Se registrará
              igual y quedará marcada, por si lo que falta es meter una compra antigua.
            </p>
          )}
          {[["fifo", "FIFO", "es el que vale para Hacienda"], ["lifo", "LIFO", "solo referencia"]].map(([k, label, nota]) => {
            const sim = simular(k);
            if (!sim.length) return null;
            return (
              <p key={k} className="text-[11px] text-tinta-3 leading-snug">
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
    <div className="iv-panel p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-heading font-bold text-sm">Dar de alta las compras por niveles</h3>
        <button type="button" onClick={onCerrar} className="text-tinta-3 text-sm">✕</button>
      </div>

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
                  className="border border-linea rounded px-3 py-1 text-[11px] font-semibold disabled:opacity-60">
            {estimarFechas.isPending ? "Buscando…" : "Estimar las fechas por el precio"}
          </button>
          <span className="text-[11px] text-tinta-3">
            Busca el día en que el precio pasó por cada nivel. Útil si no las recuerdas.
          </span>
        </div>
      )}

      {!sym ? (
        <p className="text-[11px] text-tinta-3">Escribe un ticker para ver sus niveles.</p>
      ) : !niveles.length ? (
        <p className="text-[11px] text-aviso">
          {sym} no tiene niveles puestos en la Cartera. Ponlos allí primero, o registra las
          compras una a una con su precio.
        </p>
      ) : (
        <div className="space-y-1.5">
          {niveles.map((n) => (
            <div key={n.nivel} className="flex items-center gap-3 text-xs">
              <Chip tono="nivel">{n.etiqueta}</Chip>
              <span className="font-mono text-tinta-3 w-24">{usd(n.precio, data?.divisa)}</span>
              {n.comprado && <span className="text-[10px] text-tinta-3">campanita apagada</span>}
              <input
                value={porNivel[n.nivel] ?? ""}
                onChange={(e) => setPorNivel((p) => ({ ...p, [n.nivel]: e.target.value }))}
                inputMode="decimal" placeholder="acciones"
                className="ml-auto border border-linea rounded px-2 py-1 font-mono text-xs w-24 bg-transparent" />
              <input
                type="date"
                value={fechaPorNivel[n.nivel] || fechaBase}
                onChange={(e) => setFechaPorNivel((p) => ({ ...p, [n.nivel]: e.target.value }))}
                title="Cuándo compraste ESTE nivel. Determina el tipo de cambio de esa compra."
                className="border border-linea rounded px-2 py-1 font-mono text-xs bg-transparent" />
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
        <p className="text-[11px] text-tinta-3 border-t border-linea pt-2">
          Se crearán <b>{filas.length}</b> compras · <b>{totalAcciones}</b> acciones ·
          coste <b>{usd(totalCoste, data?.divisa)}</b> · precio medio{" "}
          <b>{usd(totalCoste / totalAcciones, data?.divisa)}</b>.
          {" "}Compruébalo contra lo que tenías en la Cartera antes de vender.
          {filas.some((f) => f.fecha !== filas[0].fecha)
            ? " Cada nivel se guardará con su fecha, así que los euros saldrán al cambio de cada día."
            : " Todos con la misma fecha: si los compraste en días distintos, ajústalos arriba — la fecha decide el tipo de cambio."}
        </p>
      )}

      <button onClick={guardar} disabled={guardando || !filas.length}
              className="w-full bg-marca text-marca-tinta rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
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
      ? <p className="text-[11px] text-tinta-3">Sin comisión: se registrará tal cual.</p>
      : null;
  }
  const bruto = (aNumero(acciones) || 0) * (aNumero(precio) || 0);
  const tasa = tasas?.tasas?.USD;
  if (!bruto || !tasa) {
    return (
      <p className="text-[11px] text-tinta-3">
        La comisión se estimará con la tarifa de DEGIRO: 2 € por operación + 0,25% de
        conversión de divisa. Pon un 0 si esta operación no te costó nada.
      </p>
    );
  }
  const est = COMISION_FIJA_EUR * tasa + bruto * FX_AUTO_PCT;
  return (
    <p className="text-[11px] text-tinta-3">
      Se aplicará una comisión estimada de <b>{usd(est)}</b> ={" "}
      {usd(COMISION_FIJA_EUR * tasa)} (2 € de comisión y tramitación) +{" "}
      {usd(bruto * FX_AUTO_PCT)} (0,25% de conversión de divisa).
      {" "}Si tienes la real en tu extracto, escríbela y manda la tuya.
    </p>
  );
}

// Sección plegable con memoria: con 146 ventas la página era un scroll interminable para
// llegar a "Lo que tienes abierto". El estado se guarda por sección en localStorage para
// que cada uno deje abierto lo que mira a diario y cerrado lo que no.
function Plegable({ id, titulo, cabeceraExtra, abierta: porDefecto = true, children }) {
  const clave = `ventas.seccion.${id}`;
  const [abierta, setAbierta] = React.useState(() => {
    try {
      const v = window.localStorage.getItem(clave);
      return v === null ? porDefecto : v === "1";
    } catch { return porDefecto; }
  });
  const alternar = () => {
    setAbierta((a) => {
      try { window.localStorage.setItem(clave, a ? "0" : "1"); } catch { /* privado */ }
      return !a;
    });
  };
  return (
    <div className="iv-panel overflow-hidden">
      <div className="px-4 py-3 border-b border-linea flex items-center justify-between flex-wrap gap-2">
        <button onClick={alternar} className="flex items-center gap-2 text-left">
          <span className="text-tinta-3 text-[10px]">{abierta ? "▲" : "▼"}</span>
          <h2 className="font-heading font-bold text-sm">{titulo}</h2>
        </button>
        {cabeceraExtra}
      </div>
      {abierta && children}
    </div>
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
               className="w-24 text-[11px] bg-transparent border border-linea rounded px-1.5 py-0.5 text-right font-mono" />
        <button disabled={mut.isPending || !(aNumero(precio) > 0)}
                onClick={() => mut.mutate({ symbol: p.symbol, valor: aNumero(precio) })}
                className="text-[11px] underline text-tinta-3 disabled:opacity-50">
          poner
        </button>
      </span>
    );
  }
  return (
    <>
      {eur(p.valor_eur)}
      {p.precio_manual && (
        <div className="text-[10px] text-aviso cursor-pointer"
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
          `🔔 ${r.campanas.reactivadas.join(" y ")} de ${r.symbol} vendido(s) entero(s) — `
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
    <form onSubmit={enviar} className="iv-panel p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-heading font-bold text-sm">
          {tipo === "compra" ? "Registrar una compra" : "Registrar una venta"}
        </h3>
        <button type="button" onClick={onCerrar} className="text-tinta-3 text-sm">✕</button>
      </div>

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
                          className={`text-[11px] rounded px-2 py-1 border transition-colors ${marcado
                            ? "bg-marca text-marca-tinta border-marca font-semibold"
                            : "border-linea text-tinta-3 hover:text-tinta"}`}>
                    N{i}
                  </button>
                );
              })}
              {(f.niveles || []).length > 0 && (
                <button type="button" onClick={() => setF((p) => ({ ...p, niveles: [] }))}
                        className="text-[11px] text-tinta-3 underline px-1">
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
        <div className="rounded border border-linea px-3 py-2 space-y-1.5">
          <p className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono">
            ¿Cuántas acciones en cada nivel?
          </p>
          <div className="flex flex-wrap gap-2">
            {f.niveles.map((clave) => (
              <label key={clave} className="flex items-center gap-1.5">
                <span className="text-[11px] text-tinta-2 font-mono">
                  {NIVEL_ETIQUETA[clave] || clave}
                </span>
                <input value={(f.reparto || {})[clave] ?? ""}
                       onChange={(e) => setF((p) => ({
                         ...p, reparto: { ...(p.reparto || {}), [clave]: e.target.value } }))}
                       inputMode="decimal" placeholder={repartoSugerido[clave] ?? ""}
                       className="w-16 bg-fondo border border-linea rounded px-2 py-1 font-mono text-[11px]" />
              </label>
            ))}
          </div>
          {sumaReparto != null && aNumero(f.acciones) > 0
            && Math.abs(sumaReparto - aNumero(f.acciones)) > 1e-6 && (
            <p className="text-[11px] text-aviso">
              Los niveles suman {sumaReparto} y la compra son {aNumero(f.acciones)}.
              Tienen que cuadrar.
            </p>
          )}
        </div>
      )}

      {tipo === "compra" && (
        <p className="text-[11px] text-tinta-3">
          {(f.niveles || []).length > 1
            ? `Se guardarán ${f.niveles.length} lotes, uno por nivel, y cada uno de esos niveles pasará a valer tu precio real de compra${f.precio ? ` (${f.precio})` : ""}. La comisión se reparte entre ellos: es una sola orden.`
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
              className="w-full bg-marca text-marca-tinta rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
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
  const repararComisiones = useMutation({
    mutationFn: async () => {
      const previo = await api.cartera.estimarComisiones(false);
      const n = previo.compras + previo.ventas;
      if (!n) {
        toast.success("No hay nada que estimar: todo lo tecleado ya tiene comisión.");
        return null;
      }
      const ok = window.confirm(
        `Se va a poner la comisión estimada (2 € + 0,25% de AutoFX) a ${n} apunte(s) `
        + `tecleados a mano que están a cero: ${previo.compras} compra(s) y `
        + `${previo.ventas} venta(s).\n\nSuman unos ${previo.total_eur} €. Quedarán `
        + "marcados como ESTIMADOS.\n\nLo que vino del CSV no se toca.\n\n¿Continuar?");
      return ok ? api.cartera.estimarComisiones(true) : null;
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
  const [comoBroker, setComoBroker] = React.useState(() => {
    try { return window.localStorage.getItem("ventas.comoBroker") === "1"; } catch { return false; }
  });
  const alternarBroker = () => setComoBroker((v) => {
    try { window.localStorage.setItem("ventas.comoBroker", v ? "0" : "1"); } catch { /* privado */ }
    return !v;
  });
  const [verExplicacion, setVerExplicacion] = React.useState(false);   // texto del método

  const { data: hist, isPending: cargandoHist } = useQuery({
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

  return (
    <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-4 sm:py-6 space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-heading font-bold text-2xl">Ventas y ganancias</h1>
          <p className="text-sm text-tinta-3 mt-0.5">
            Lo que llevas ganado de verdad, en euros, con el tipo de cambio de cada operación.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setForm("degiro")}
                  className="bg-marca text-marca-tinta rounded px-3 py-1.5 text-sm font-semibold">
            Importar CSV de DEGIRO
          </button>
          <button onClick={() => setForm("niveles")}
                  className="border border-linea rounded px-3 py-1.5 text-sm font-semibold">
            + Compras por niveles
          </button>
          <button onClick={() => setForm("compra")}
                  className="border border-linea rounded px-3 py-1.5 text-sm font-semibold">
            + Compra suelta
          </button>
          <button onClick={() => setForm("venta")}
                  className="bg-marca text-marca-tinta rounded px-3 py-1.5 text-sm font-semibold">
            + Venta
          </button>
        </div>
      </div>

      {form === "degiro"
        ? <ImportarDegiro onCerrar={() => setForm(null)} />
        : form === "niveles"
          ? <FormularioPorNiveles onCerrar={() => setForm(null)} />
          : form && <FormularioOperacion tipo={form} onCerrar={() => setForm(null)} />}

      {/* Cifras de cabecera. Realizado y latente van SEPARADOS: uno está en tu cuenta y el
          otro puede evaporarse mañana. Sumarlos sin distinguirlos da una sensación de
          riqueza que el mercado no ha confirmado. */}
      <div className="flex gap-3 flex-wrap">
        <Kpi etiqueta="Realizado" significa="Lo que ya cobraste al vender" valor={realizado} acento
             // n_ventas cuelga del resumen, no del método: el número de ventas es el
             // mismo se mire con FIFO o con LIFO. Leerlo de dentro del método daba
             // siempre 0, o sea "no has vendido nada" con 148 ventas en la lista.
             // El descuadre va EN el KPI y no en una fila perdida: si hay acciones vendidas
             // sin compra registrada, salen con coste CERO y esta cifra está hinchada en
             // hasta esos euros. Sin el aviso, el número gordo se lee como bueno.
             sub={[
               `${hist?.resumen?.n_ventas ?? 0} venta(s) · ${
                 comoBroker && hist?.resumen?.ponderada?.ganancia_eur != null
                   ? "media ponderada" : metodo.toUpperCase()}`,
               hist?.resumen?.sin_cubrir_acciones
                 ? `⚠ ${hist.resumen.sin_cubrir_acciones} acción(es) vendidas sin compra registrada`
                   + ` (${(hist.resumen.sin_cubrir_por_symbol || []).map((s) => s.symbol).join(", ")})`
                   + ` — hasta ${eur(hist.resumen.sin_cubrir_eur_aprox)} de esta cifra pueden sobrar`
                   + (hist.resumen.sin_cubrir_sin_tasa
                       ? `, y ${hist.resumen.sin_cubrir_sin_tasa} más sin tipo de cambio, sin contar`
                       : "")
                 : null,
             ].filter(Boolean).join(" · ")}
             ayuda="Ganancia de las ventas ya hechas, con el tipo de cambio del día de cada compra y de cada venta. Es dinero que ya está en tu cuenta. Cambia según el método: mira la etiqueta de debajo." />
        {/* Va en la MISMA base que el realizado, y por eso obedece al interruptor: lo que
            un método se apunta de más arriba, el otro se lo guarda aquí. La cifra del otro
            método sigue debajo, que es lo que hace falta para comparar pantallas. */}
        <Kpi etiqueta="Latente" significa="Lo que aún está en juego" valor={latente}
             // Una posición sin cotización NO entra en el latente, y hasta ahora eso no se
             // decía: el número parecía completo cuando le faltaba una posición entera. Es
             // lo primero que hay que mirar cuando el total no cuadra con el bróker.
             sub={[
               resumen?.posiciones?.length
                 ? `${resumen.posiciones.length} posición(es) abiertas` : "sin posiciones",
               // "sin precio" y "sin tipo de cambio" son averías DISTINTAS y se arreglan
               // distinto: decir siempre "sin precio" mandaba a buscar el problema donde
               // no estaba (el precio estaba; lo que faltaba era el cambio).
               resumen?.posiciones_sin_precio
                 ? `⚠ ${resumen.posiciones_sin_precio} sin precio, fuera del total` : null,
               resumen?.posiciones_sin_tipo_de_cambio
                 ? `⚠ ${resumen.posiciones_sin_tipo_de_cambio} sin tipo de cambio, fuera del total` : null,
               // Con el interruptor puesto, el de al lado ya ES el del bróker: lo que
               // hace falta enseñar entonces es el otro, no repetir el mismo.
               (usaPmp ? resumen?.latente_eur : latenteBroker) != null
                 && Math.abs((usaPmp ? resumen.latente_eur : latenteBroker) - (latente ?? 0)) > 0.5
                 ? (usaPmp
                     ? `por ${metodo.toUpperCase()} son ${eur(resumen.latente_eur)}`
                     : `en DEGIRO verás ${eur(latenteBroker)}`) : null,
             ].filter(Boolean).join(" · ")}
             ayuda="Lo que llevas ganado en lo que AÚN NO has vendido, al precio y al cambio de hoy. Puede cambiar mañana. Tu bróker enseña otra cifra porque valora TODAS las acciones al precio medio ponderado, mientras que FIFO/LIFO dejan vivos unos lotes concretos: lo que aquí falta, ya está contado en el Realizado. Sumados, los dos métodos dan el mismo total." />
        {/* SIEMPRE visible, aunque esté vacía. Escondiéndola hasta que hubiera dividendos,
            la única forma de enterarse de que existe era leer el texto del importador — y
            una función que no se ve no existe. Vacía dice qué falta para llenarla. */}
        <Kpi etiqueta="Dividendos" significa="Lo que te han pagado por tener las acciones" valor={dividendos}
             sub={dividendos == null
               ? "sube tu Account.csv de DEGIRO"
               : [
                   `${divs?.n_cobros ?? 0} cobros`,
                   divs?.retenido_eur ? `${eur(divs.retenido_eur)} retenidos` : null,
                   // Los que no se pudieron pasar a euros quedan FUERA del total. Callarlo
                   // haria que el numero pareciera completo cuando no lo es.
                   divs?.sin_convertir ? `⚠ ${divs.sin_convertir} sin convertir` : null,
                 ].filter(Boolean).join(" · ")}
             ayuda="Cobrado por dividendos, ya descontada la retención en origen. Los dividendos NO están en el Transactions.csv: hay que subir además el Account.csv (Actividad → Cuenta). Se cuentan aparte porque fiscalmente no son ganancias patrimoniales sino rendimientos del capital mobiliario, y van a otra casilla de la declaración. La retención de EE.UU. es recuperable en parte con el convenio de doble imposición." />
        {costes != null && (
          <Kpi etiqueta="Costes" significa="Lo que te cobra DEGIRO por el saldo y los datos" valor={costes}
               sub={`${divs?.n_costes ?? 0} apunte(s) · intereses y conectividad`}
               ayuda="Intereses por operar con el saldo en negativo y conectividad con mercados, sacados del Account.csv. No incluye las comisiones de compraventa, que ya están descontadas en cada operación. Es lo que separa tu total del Total P/L de DEGIRO." />
        )}
        {/* La cifra que contesta "¿cuánto llevo ganado en DEGIRO en total?". Y la única de
            la pantalla que NO depende del método: como el realizado y el latente van en la
            misma base, lo que un método se apunta de más en uno se lo guarda en el otro y
            la suma sale igual. Por eso no hay que activar nada para leerla. */}
        <Kpi etiqueta="Total" significa="Todo junto: tu resultado en esta cuenta" valor={total}
             ayuda="Todo lo que llevas ganado o perdido en esta cuenta: lo realizado en ventas, lo latente de lo que sigue abierto, los dividendos cobrados y los costes. NO cambia con el método ni con el interruptor de DEGIRO: FIFO, LIFO y media ponderada reparten lo mismo de otra forma entre realizado y latente, pero suman igual. Si alguna vez cambia, es un fallo."
             sub={[
               "realizado + latente",
               dividendos != null ? "+ dividendos" : null,
               costes != null ? "+ costes" : null,
             ].filter(Boolean).join(" ")} />
        {tot?.efecto_divisa_eur != null && Math.abs(tot.efecto_divisa_eur) >= 0.01 && (
          <Kpi etiqueta="Efecto del euro" significa="Cuánto de tu resultado es el euro y no la acción" valor={tot.efecto_divisa_eur}
               sub="incluido en el realizado"
               ayuda="Cuánto de tu ganancia realizada viene del movimiento del euro frente al dólar, y no de que la acción subiera." />
        )}
      </div>

      {/* Ventas de la contabilidad VIEJA (el diálogo Vender de la Cartera antes de que
          escribiera en el libro). Si quedan, ni sus acciones ni su ganancia están en
          ninguna cifra de esta pantalla, y hay que meterlas como ventas normales. */}
      {/* Una venta sin comisión infla la ganancia entre 6 y 10 €, y esa cifra acaba en
          una declaración. Con cien ventas deja de ser calderilla, así que se dice cuánto
          falta en total en vez de dejarlo a que alguien sume. */}
      {!!hist?.ventas_sin_comision && (
        <div className="iv-panel px-4 py-2.5 border border-aviso/40 bg-aviso/[0.06]">
          <p className="text-apoyo text-aviso leading-snug">
            ⚠ <b>{hist.ventas_sin_comision} venta(s) registradas sin comisión.</b> DEGIRO
            cobra 2 € por operación más el 0,25% de AutoFX, así que tu ganancia realizada
            está inflada en unos{" "}
            <b className="font-mono">{eur(hist.comision_no_contada_eur)}</b>.
            {hist.ventas_sin_comision_manuales === hist.ventas_sin_comision
              ? " Todas están tecleadas a mano, así que reimportar el CSV no las toca:"
                + " no tienen huella que emparejar, y encima tapan la fila del fichero,"
                + " que sí trae la comisión buena. Se arreglan borrándolas aquí abajo y"
                + " volviendo a importar el CSV."
              : " Las que vinieron del CSV se corrigen reimportándolo con la casilla de"
                + " corregir comisiones marcada; las tecleadas a mano hay que borrarlas y"
                + " reimportar, porque no tienen huella que emparejar."}
          </p>
          {/* CUÁLES. Sin el símbolo y la fecha delante, «10 ventas» es un dato que no se
              puede accionar: hay que rebuscarlas una a una entre cientos de filas. */}
          {!!hist.ventas_sin_comision_detalle?.length && (
            <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-etiqueta text-tinta-3">
              {hist.ventas_sin_comision_detalle.map((v) => (
                <li key={v.id} className="font-mono">
                  {v.symbol} · {v.fecha} · {v.acciones} acc.
                  {v.manual ? " · a mano" : " · del CSV"}
                </li>
              ))}
            </ul>
          )}
          {/* El botón para repararlas. Los apuntes tecleados se quedaron a cero por un
              fallo del formulario —enviaba 0 donde debía enviar "vacío"—, así que no son
              ceros que nadie afirmara: son huecos. Se rellenan con la tarifa publicada y
              quedan marcados como estimados, para poder distinguirlos luego de una cifra
              sacada del extracto. Lo que vino del CSV no se toca: ahí un cero es un dato. */}
          {!!hist.ventas_sin_comision_manuales && (
            <button onClick={() => repararComisiones.mutate()}
                    disabled={repararComisiones.isPending}
                    className="mt-2 text-[11px] underline text-aviso disabled:opacity-60">
              {repararComisiones.isPending
                ? "Calculando…"
                : "Poner la comisión estimada a las que tecleaste a mano"}
            </button>
          )}
        </div>
      )}

      {!!hist?.ventas_antiguas && (
        <div className="iv-panel px-4 py-3 border-l-4 border-l-amber-500">
          <p className="text-sm font-semibold mb-1">
            ⚠ {hist.ventas_antiguas} venta(s) del sistema antiguo, fuera de estas cifras
          </p>
          <p className="text-xs text-tinta-3">
            Se registraron con el botón «Vender» de la Cartera cuando ese botón llevaba su
            propia contabilidad aparte. No cuentan en el Realizado ni descuentan acciones del
            libro. Vuelve a meterlas aquí con <b>+ Venta</b> (o impórtalas con el CSV de
            DEGIRO, que las trae) y quedarán contadas de verdad.
          </p>
        </div>
      )}

      {/* La misma venta metida a mano Y venida del CSV solo se detecta como duplicada si
          coincide al céntimo; tecleada de memoria, rara vez lo hace. En una posición ya
          cerrada no se nota en las acciones — solo en que el Realizado se dispara. */}
      {!!hist?.posibles_duplicadas?.length && (
        <div className="iv-panel px-4 py-3 border-l-4 border-l-amber-500">
          <p className="text-sm font-semibold mb-1">
            ⚠ {hist.posibles_duplicadas.length} venta(s) posiblemente contadas dos veces
          </p>
          <p className="text-xs text-tinta-3 mb-2">
            Estas ventas están una vez metidas a mano y otra vez traídas del CSV de DEGIRO
            (misma acción, misma fecha, mismas acciones). Cada pareja suma su ganancia dos
            veces. Busca la copia manual en la lista de abajo (la que NO pone «DEGIRO» en
            las notas) y bórrala con su botón.
          </p>
          {hist.posibles_duplicadas.map((d, i) => (
            <p key={i} className="text-xs font-mono">
              {d.symbol} · {d.fecha} · {d.acciones} acciones
            </p>
          ))}
        </div>
      )}

      {/* Compras duplicadas. Al contrario que una venta repetida, una compra repetida no
          descuadra nada contable —no deja ventas sin cubrir, no rompe ningún total— así que
          nadie la busca: solo infla la posición y con ella el latente. En NFLX eran 30
          acciones tecleadas a 76,00 $ y la misma compra del CSV a 76,01: 80 acciones en
          pantalla donde el broker tenía 50, y unos +140 € de ganancia inexistente. Las otras
          quince posiciones cuadraban al detalle, que es lo que hace que no se sospeche. */}
      {!!hist?.posibles_compras_duplicadas?.length && (
        <div className="iv-panel px-4 py-3 border-l-4 border-l-amber-500">
          <p className="text-sm font-semibold mb-1">
            ⚠ {hist.posibles_compras_duplicadas.length} compra(s) posiblemente contadas dos veces
          </p>
          <p className="text-xs text-tinta-3 mb-2">
            Cada una está metida a mano y además traída del CSV de DEGIRO: misma acción,
            misma fecha y mismas acciones, con los precios a un céntimo. Eso infla tu
            posición y tu ganancia latente sin descuadrar ningún total, así que no salta
            ningún otro aviso. Borra la copia manual — la del precio redondeado.
          </p>
          {hist.posibles_compras_duplicadas.map((d, i) => (
            <div key={i} className="flex items-center gap-3 flex-wrap text-xs font-mono py-0.5">
              <span className="font-semibold">{d.symbol}</span>
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
                      className="text-baja underline disabled:opacity-60">
                borrar la copia manual
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Selector de método. Va acompañado SIEMPRE de la explicación fiscal: enseñar dos
          cifras distintas para la misma venta sin decir cuál vale para Hacienda sería peor
          que enseñar una sola. */}
      <div className="iv-panel px-4 py-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-[10px] uppercase tracking-[0.15em] text-tinta-3 font-mono">Método de cálculo</span>
          {/* El interruptor del bróker vive AQUÍ, junto al método, porque manda en toda la
              pantalla: el historial, el realizado y la tabla de posiciones. Estaba metido
              en la cabecera de esa tabla y desde ahí parecía cambiar solo esa tabla —que
              es lo que hacía antes—, así que el resto de la pantalla se quedaba en el otro
              método sin decirlo.
              Va aparte de FIFO/LIFO y no como un tercer botón porque no es lo mismo: esos
              dos deciden CÓMO SE EMPAREJAN tus ventas y se guardan en el servidor; este
              solo cambia lo que estás mirando ahora, y vive en tu navegador. */}
          <div className="flex rounded overflow-hidden border border-linea">
            {[["fifo", "FIFO"], ["lifo", "LIFO"]].map(([k, label]) => (
              <button key={k} onClick={() => setMetodo(k)}
                      className={`px-3 py-1 text-xs font-mono font-semibold ${metodo === k ? "bg-marca text-marca-tinta" : "text-tinta-3"}`}>
                {label}
              </button>
            ))}
          </div>
          <button onClick={alternarBroker}
                  title="Tu bróker valora TODAS las acciones al precio medio ponderado, que no baja al vender. FIFO/LIFO dejan vivos unos lotes concretos —los caros o los baratos— y por eso dan otro número. Ninguna está mal: lo que una se apunta de más aquí, la otra ya se lo apuntó en lo realizado. Cambia el historial, el realizado y la tabla de posiciones."
                  className={`text-[11px] rounded px-2 py-1 border ${comoBroker
                    ? "bg-marca text-marca-tinta border-marca font-semibold"
                    : "border-linea text-tinta-3"}`}>
            {comoBroker ? "✓ Como en DEGIRO (media ponderada)" : "Ver como en DEGIRO"}
          </button>
          {cambiarMetodo.isPending && (
            <span className="text-[11px] text-tinta-3">Recalculando…</span>
          )}
          {metodo === "lifo" ? (
            <span className="text-[11px] text-sube font-semibold">Vende lo más reciente · tu precio medio SUBE al vender</span>
          ) : (
            <span className="text-[11px] text-sube font-semibold">Vende lo más antiguo · tu precio medio BAJA al vender · es el de Hacienda</span>
          )}
          <button onClick={() => setVerExplicacion((v) => !v)}
                  className="text-[11px] text-tinta-3 underline ml-auto">
            {verExplicacion ? "ocultar" : "¿cómo funciona?"}
          </button>
        </div>
        {verExplicacion && (
        <p className="text-[11px] text-tinta-3 mt-2 leading-relaxed">
          Esto no cambia solo lo que ves: gobierna qué lotes te quedan vivos, tu precio medio
          y qué campanitas se encienden. Cambiarlo recalcula todo, pero <b>no altera ninguna
          operación</b> — tus compras y ventas son las que son.
          <br />
          <b>Para saber cuál usar, mira tu bróker tras una venta parcial:</b> si tu precio
          medio <b>baja</b>, está quitando las compras más antiguas (FIFO); si <b>sube</b>,
          las más recientes (LIFO). Como entras por niveles según cae el precio, lo más
          antiguo es lo más caro — por eso quitar lo antiguo hace bajar la media.
          <br />
          FIFO es además el obligatorio en España para acciones cotizadas (art. 37.2 de la
          Ley del IRPF): es la cifra de tu declaración, la mires con el método que la mires.
          {tot && hist?.resumen?.fifo && hist?.resumen?.lifo
            && hist.resumen.fifo.ganancia_divisa !== hist.resumen.lifo.ganancia_divisa && (
            <> En tu caso la diferencia entre ambos es de{" "}
              <b>{usd(Math.abs(hist.resumen.fifo.ganancia_divisa - hist.resumen.lifo.ganancia_divisa))}</b>.</>
          )}
        </p>
        )}
      </div>

      {hist?.resumen?.aviso && (
        <div className="iv-panel px-4 py-2.5 border border-aviso/40 bg-aviso/[0.06] flex items-start gap-2">
          <span>⚠️</span>
          <span className="text-[11px] text-aviso leading-snug">{hist.resumen.aviso}</span>
        </div>
      )}

      {/* Historial */}
      <Plegable id="historial" titulo={`Historial de ventas (${ventas.length})`}
                cabeceraExtra={<span className="text-[11px] text-tinta-3">Toca una para ver de qué compra salió</span>}>
        {cargandoHist ? (
          <p className="px-4 py-8 text-center text-sm text-tinta-3">Cargando…</p>
        ) : !ventas.length ? (
          <div className="px-4 py-8 text-center space-y-3">
            <p className="text-sm text-tinta-3">Aún no has registrado ninguna venta.</p>
            <p className="text-[11px] text-tinta-3 max-w-md mx-auto">
              Si ya tenías posiciones en la Cartera, impórtalas para no empezar de cero. Se
              reconstruye <b>un lote por cada nivel que tengas con la campanita apagada</b>,
              que es como marcas los niveles ya comprados. Con uno o dos niveles el reparto
              de acciones sale exacto a partir de tu precio medio; con tres o más es una
              estimación y te lo aviso para que la corrijas.
            </p>
            <button onClick={() => importar.mutate(false)} disabled={importar.isPending}
                    className="border border-linea rounded px-3 py-1.5 text-xs font-semibold disabled:opacity-60">
              {importar.isPending ? "Importando…" : "Importar mis posiciones actuales"}
            </button>
          </div>
        ) : (
          <>
            {/* Las últimas 15 a la vista; el resto bajo demanda. Con 146 ventas la lista
                entera convertía llegar al final de la página en una expedición. */}
            {(verTodas ? ventas : ventas.slice(0, 15)).map((v) => (
              <FilaVenta key={v.id} v={v} metodo={metodo} comoBroker={comoBroker}
                         onBorrar={(x) => window.confirm(`¿Borrar la venta de ${x.acciones} ${x.symbol} del ${fecha(x.fecha)}?`) && borrar.mutate(x)} />
            ))}
            {ventas.length > 15 && (
              <button onClick={() => setVerTodas((v) => !v)}
                      className="w-full py-2.5 text-xs text-tinta-3 underline hover:bg-superficie-alt">
                {verTodas ? "Enseñar solo las últimas 15" : `Enseñar las ${ventas.length - 15} restantes`}
              </button>
            )}
          </>
        )}
      </Plegable>

      {/* Por acción */}
      {!!hist?.por_symbol?.length && (
        <Plegable id="por-accion" titulo={`Por acción (${hist.por_symbol.length})`} abierta={false}>
          {hist.por_symbol.map((s) => (
            <div key={s.symbol} className="px-4 py-2.5 flex items-center gap-3 border-b border-linea last:border-0">
              <span className="font-mono font-bold text-sm w-16">{s.symbol}</span>
              <span className="text-[11px] text-tinta-3">{s.n_ventas} venta(s)</span>
              <span className={`ml-auto font-mono font-semibold text-sm ${tono(s.ganancia_eur ?? s.ganancia_divisa)}`}>
                {s.ganancia_eur != null ? eur(s.ganancia_eur) : usd(s.ganancia_divisa, s.divisa)}
              </span>
            </div>
          ))}
        </Plegable>
      )}

      {/* Qué posiciones arrastran lotes que no vinieron del CSV. Son las que pueden no
          cuadrar con el bróker: su fecha es la del alta, no la de la compra, así que el
          coste se pasó a euros al cambio de un día que no es el tuyo. El precio y las
          acciones sí están bien; lo que baila es la conversión. Se ordenan por dinero
          afectado, que es el orden en que compensa arreglarlas. */}
      {(() => {
        const sospechosas = (resumen?.posiciones || [])
          .filter((p) => p.acciones_sin_csv > 0)
          .sort((a, b) => (b.coste_eur || 0) - (a.coste_eur || 0));
        if (!sospechosas.length) return null;
        return (
          <div className="iv-panel px-4 py-3 border border-aviso/40 bg-aviso/[0.06] mb-3">
            <p className="text-apoyo text-aviso leading-snug mb-2">
            ⚠ <b>{sospechosas.length} posición(es) con lotes que no vienen del CSV.</b>{" "}
            Esos lotes llevan la fecha en que se dieron de alta, no la de tu compra, así
            que su coste se pasó a euros al cambio de ese día. Por eso el latente puede
            no cuadrar con DEGIRO teniendo el mismo precio y las mismas acciones. Se
            arreglan borrando esos lotes y volviendo a importar el CSV.
            </p>
            <div className="overflow-x-auto">
            <table className="w-full text-etiqueta font-mono">
              <thead className="text-tinta-3">
                <tr className="text-left">
                  <th className="pr-3 font-normal">Acción</th>
                  <th className="pr-3 font-normal text-right">Sin CSV</th>
                  <th className="pr-3 font-normal text-right">De</th>
                  <th className="pr-3 font-normal text-right">Invertido</th>
                  <th className="pr-3 font-normal text-right">Cambio usado</th>
                  <th className="font-normal text-right">Hoy</th>
                </tr>
              </thead>
              <tbody>
                {sospechosas.map((p) => (
                  <tr key={p.symbol} className="border-t border-linea/60">
                  <td className="pr-3 py-1 font-bold">{p.symbol}</td>
                  <td className="pr-3 text-right">{p.acciones_sin_csv}</td>
                  <td className="pr-3 text-right text-tinta-3">
                    {p.acciones_abiertas_total}
                  </td>
                  <td className="pr-3 text-right">{eur(p.coste_eur)}</td>
                  <td className="pr-3 text-right">{p.cambio_medio_compras ?? "—"}</td>
                  <td className="text-right text-tinta-3">{p.cambio_hoy ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <p className="text-[11px] text-tinta-3 mt-2 leading-snug">
            Un «cambio usado» pegado al de hoy en una compra antigua es la señal: ese
            lote se convirtió al cambio de hoy y no al del día en que compraste.
            </p>
          </div>
        );
      })()}


      {/* Posiciones abiertas, en euros */}
      {!!resumen?.posiciones?.length && (
        <Plegable id="abierto" titulo={`Lo que tienes abierto (${resumen.posiciones.length})`}
                  cabeceraExtra={
            <div className="flex items-center gap-3 flex-wrap ml-auto">
              {/* El interruptor que hace que esta tabla se pueda comparar fila a fila con la
                  pantalla del bróker. Sin él, las posiciones donde se vendió parte enseñaban
                  otro precio medio y otra ganancia, y parecía un error de cálculo. */}
              {/* Rehacer la importación: si la primera salió con los lotes mal repartidos,
                  borrarlos uno a uno serían decenas de clics. No toca las acciones que ya
                  tengan ventas registradas — ahí borrar compras falsearía la ganancia. */}
              <button onClick={() => window.confirm(
                        "Se rehacen los lotes de las posiciones importadas, a partir de tus "
                        + "niveles y tu precio medio actuales.\n\nLas acciones que ya tengan "
                        + "ventas registradas NO se tocan.\n\n¿Continuar?")
                        && importar.mutate(true)}
                      disabled={importar.isPending}
                      className="text-[11px] text-tinta-3 underline disabled:opacity-60">
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
                      className="text-[11px] text-tinta-3 underline disabled:opacity-60">
                {quitarDup.isPending ? "Quitando…" : "Quitar duplicados del CSV"}
              </button>
              {resumen.tasas && (
                <span className="text-[11px] text-tinta-3 font-mono"
                      title="El tipo de cambio se consulta como mucho una vez por hora, y esta pantalla no se refresca sola: para ver el más reciente, recarga.">
                  {Object.entries(resumen.tasas).filter(([d]) => d !== "EUR")
                    .map(([d, t]) => {
                      const edad = haceCuanto(resumen.tasas_edad_s?.[d]);
                      return `1 € = ${t} ${d}${edad ? ` (${edad})` : ""}`;
                    }).join(" · ")}
                </span>
              )}
            </div>
                  }>
          {/* ── Móvil: una tarjeta por posición ──────────────────────────────────
              Seis columnas no caben en 390px. Con la tabla había que arrastrar la
              pantalla de lado para llegar a la ganancia, que es el dato por el que
              se abre esta sección: quedaba justo en la columna más escondida.

              Apilado en vez de tabla estrecha: encoger las columnas solo cambia el
              arrastre por cifras cortadas. Cada dato lleva su rótulo al lado, que
              es lo que en la tabla hace la cabecera y aquí no existe.

              El interruptor de bróker, el método y el resto del comportamiento son
              los mismos: esto es la MISMA fila, con otra disposición. */}
          <ul className="md:hidden divide-y divide-linea">
            {resumen.posiciones.map((p) => {
              const { g, precioMedio, invertido, hayOtroMedio, sinPmp } = datosPosicion(p, comoBroker);
              const abiertaEsta = abierta === p.symbol;
              return (
                <li key={p.symbol}>
                  {/* La tarjeta entera es pulsable, como la fila de la tabla, pero el
                      botón de verdad es el del símbolo: así se despliega también con
                      teclado y un lector de pantalla dice qué hace y si está abierto.
                      La tarjeta NO puede ser un <button> envolvente: «Valor hoy» trae
                      un campo y un botón cuando falta cotización, y un control dentro
                      de otro control es HTML inválido y deja de responder. */}
                  <div onClick={() => setAbierta(abiertaEsta ? null : p.symbol)}
                       className="px-4 py-3 cursor-pointer">
                    {/* Primera línea: quién es y cuánto gana. Las dos cosas que se
                        miran de un vistazo van juntas y arriba. */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                        <button type="button"
                                onClick={(e) => { e.stopPropagation();
                                                  setAbierta(abiertaEsta ? null : p.symbol); }}
                                aria-expanded={abiertaEsta}
                                aria-label={`${abiertaEsta ? "Ocultar" : "Ver"} las compras de ${p.symbol}`}
                                className="inline-flex items-center gap-1.5 min-h-[44px] -my-2 pr-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded">
                          <span className="text-tinta-3 text-[10px]">{abiertaEsta ? "▲" : "▼"}</span>
                          <span className="font-mono font-bold text-sm">{p.symbol}</span>
                        </button>
                        {!!p.divisas_mezcladas && (
                          <Chip tono="aviso"
                                title={`Esta posición tiene lotes en ${p.divisas_mezcladas.join(" y ")}. El precio medio y el invertido EN DIVISA suman monedas distintas y no significan nada; las cifras en euros sí son correctas, porque cada lote se convierte con su propia tasa. Revisa la divisa de cada compra.`}>
                            {p.divisas_mezcladas.join("+")}
                          </Chip>
                        )}
                        {/* La operación dice una moneda y el mercado otra: una de las dos es una
                            errata. Las cifras en euros ya salen bien —el valor se convierte con el
                            cambio del mercado donde cotiza— pero el precio medio "en divisa" mezcla
                            monedas mientras la ficha siga mal. */}
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
                        {p.niveles_comprados?.map((n) => (
                          <Chip key={n} tono="nivel">{NIVEL_ETIQUETA[n] || n}</Chip>
                        ))}
                        {sinNiveles.has(p.symbol) && (
                          <Chip title="Esta acción está en la Cartera pero todavía no tiene niveles. Se creó sola al registrar la compra, para que coja precio de mercado; el precio al que compraste NO es un nivel. Ponle los niveles en la Cartera cuando los tengas.">
                            niveles pendientes
                          </Chip>
                        )}
                      </div>
                      <div className="text-right shrink-0">
                        <div className={`font-mono font-semibold text-sm ${tono(g.pnl_eur)}`}>{eur(g.pnl_eur)}</div>
                        <div className={`font-mono text-[10px] ${tono(g.pct_eur)}`}>{pct(g.pct_eur)}</div>
                      </div>
                    </div>

                    {/* Los cuatro datos restantes, cada uno con su rótulo. Dos columnas
                        y no una lista larga: así la tarjeta sigue cabiendo de un vistazo. */}
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 mt-2.5 text-[11px]">
                      <div className="flex items-baseline justify-between gap-2">
                        <dt className="text-tinta-3">Acciones</dt>
                        <dd className="font-mono">{p.acciones}</dd>
                      </div>
                      <div className="flex items-baseline justify-between gap-2">
                        <dt className="text-tinta-3">Invertido <span className="opacity-60">(€)</span></dt>
                        <dd className="font-mono">{eur(invertido)}</dd>
                      </div>
                      <div className="flex items-baseline justify-between gap-2">
                        <dt className="text-tinta-3">Precio medio <span className="opacity-60">({p.divisa === "EUR" ? "€" : p.divisa})</span></dt>
                        <dd className="font-mono text-right">
                          {usd(precioMedio, p.divisa)}
                          {hayOtroMedio && (
                            <div className="text-[10px] text-tinta-3">
                              {comoBroker
                                ? `${metodo.toUpperCase()} = ${usd(p.precio_medio, p.divisa)}`
                                : `bróker ≈ ${usd(p.precio_medio_ponderado, p.divisa)}`}
                            </div>
                          )}
                        </dd>
                      </div>
                      <div className="flex items-baseline justify-between gap-2">
                        <dt className="text-tinta-3">Valor hoy <span className="opacity-60">(€)</span></dt>
                        {/* El div frena la propagación por dentro: cuando falta cotización
                            esta celda trae un campo y un botón, y al escribir en él no se
                            puede plegar la tarjeta que lo contiene. */}
                        <dd className="font-mono" onClick={(e) => e.stopPropagation()}>
                          <CeldaValorHoy p={p} />
                        </dd>
                      </div>
                    </dl>
                  </div>
                  {abiertaEsta && <LotesAbiertos symbol={p.symbol} metodo={metodo} />}
                </li>
              );
            })}
            {/* El total, con la misma forma de tarjeta para que se lea como una más. */}
            <li className="px-4 py-3 border-t-2 border-linea">
              <div className="flex items-start justify-between gap-3">
                <span className="font-semibold text-sm">Total</span>
                {(() => {
                  const lat = comoBroker && latenteBroker != null ? latenteBroker : latente;
                  const base = resumen.invertido_eur;
                  return (
                    <div className="text-right shrink-0">
                      <div className={`font-mono font-semibold text-sm ${tono(lat)}`}>{eur(lat)}</div>
                      {base ? (
                        <div className={`font-mono text-[10px] ${tono(lat)}`}>{pct((lat / base) * 100)}</div>
                      ) : null}
                    </div>
                  );
                })()}
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 mt-2.5 text-[11px]">
                <div className="flex items-baseline justify-between gap-2">
                  <dt className="text-tinta-3">Posiciones</dt>
                  <dd className="font-mono">{resumen.posiciones.length}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-2">
                  <dt className="text-tinta-3">Invertido <span className="opacity-60">(€)</span></dt>
                  <dd className="font-mono">{eur(resumen.invertido_eur)}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-2 col-span-2">
                  <dt className="text-tinta-3">Valor hoy <span className="opacity-60">(€)</span></dt>
                  <dd className="font-mono">{eur(resumen.valor_eur)}</dd>
                </div>
              </dl>
            </li>
          </ul>

          {/* Escritorio: la tabla de siempre, intacta. Aquí las seis columnas caben
              y comparar posiciones en vertical es más rápido que en tarjetas. */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-tinta-3 border-b border-linea">
                  {/* Las unidades EN LA CABECERA: el precio medio va en la divisa del
                      valor y el resto en euros, y sin decirlo la tabla parecía mezclar. */}
                  <th scope="col" className="px-4 py-2 font-normal">Acción</th>
                  <th scope="col" className="py-2 font-normal text-right">Acciones</th>
                  <th scope="col" className="py-2 font-normal text-right">
                    Precio medio <span className="opacity-60">(divisa)</span>
                  </th>
                  <th scope="col" className="py-2 font-normal text-right">
                    Invertido <span className="opacity-60">(€)</span>
                  </th>
                  <th scope="col" className="py-2 font-normal text-right">
                    Valor hoy <span className="opacity-60">(€)</span>
                  </th>
                  <th scope="col" className="px-4 py-2 font-normal text-right">
                    Ganancia <span className="opacity-60">(€)</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {resumen.posiciones.map((p) => {
                  const { g, precioMedio, invertido, hayOtroMedio, sinPmp } = datosPosicion(p, comoBroker);
                  return (
                  <React.Fragment key={p.symbol}>
                  <tr className="border-b border-linea cursor-pointer hover:bg-superficie-alt"
                      onClick={() => setAbierta(abierta === p.symbol ? null : p.symbol)}>
                    <td className="px-4 py-2">
                      {/* Un botón de verdad, no un <tr onClick>: así se despliega también
                          con teclado y un lector de pantalla dice qué hace y si está
                          abierto. min-h/min-w para que el dedo acierte en el móvil. */}
                      <button type="button"
                              onClick={(e) => { e.stopPropagation();
                                                setAbierta(abierta === p.symbol ? null : p.symbol); }}
                              aria-expanded={abierta === p.symbol}
                              aria-label={`${abierta === p.symbol ? "Ocultar" : "Ver"} las compras de ${p.symbol}`}
                              className="inline-flex items-center gap-1 min-h-[44px] -my-2 pr-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded">
                        <span className="text-tinta-3 text-[10px]">{abierta === p.symbol ? "▲" : "▼"}</span>
                        <span className="font-mono font-bold">{p.symbol}</span>
                      </button>
                      {!!p.divisas_mezcladas && (
                        <Chip tono="aviso"
                              title={`Esta posición tiene lotes en ${p.divisas_mezcladas.join(" y ")}. El precio medio y el invertido EN DIVISA suman monedas distintas y no significan nada; las cifras en euros sí son correctas, porque cada lote se convierte con su propia tasa. Revisa la divisa de cada compra.`}>
                          {p.divisas_mezcladas.join("+")}
                        </Chip>
                      )}
                      {/* La operación dice una moneda y el mercado otra: una de las dos es una
                          errata. Las cifras en euros ya salen bien —el valor se convierte con el
                          cambio del mercado donde cotiza— pero el precio medio "en divisa" mezcla
                          monedas mientras la ficha siga mal. */}
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
                      {!!p.niveles_comprados?.length && (
                        <span className="ml-2 inline-flex gap-1">
                          {p.niveles_comprados.map((n) => (
                            <Chip key={n} tono="nivel">{NIVEL_ETIQUETA[n] || n}</Chip>
                          ))}
                        </span>
                      )}
                      {sinNiveles.has(p.symbol) && (
                        <Chip title="Esta acción está en la Cartera pero todavía no tiene niveles. Se creó sola al registrar la compra, para que coja precio de mercado; el precio al que compraste NO es un nivel. Ponle los niveles en la Cartera cuando los tengas.">
                          niveles pendientes
                        </Chip>
                      )}
                    </td>
                    <td className="py-2 text-right font-mono">{p.acciones}</td>
                    <td className="py-2 text-right font-mono">
                      {/* Con el interruptor puesto manda la ponderada, que es la del bróker;
                          la otra baja debajo etiquetada. Ninguna es una corrección de la
                          otra: miden cosas distintas y las dos son correctas. */}
                      {usd(precioMedio, p.divisa)}
                      {hayOtroMedio && (
                        <div className="text-[10px] text-tinta-3"
                             title={comoBroker
                               ? `Arriba, la media ponderada (la de tu bróker). Debajo, el coste real de las ${p.acciones} acciones que te quedan por ${metodo.toUpperCase()}.`
                               : "Precio medio ponderado: el que suele enseñar tu bróker. No cambia al vender, porque promedia TODO lo que has comprado. El de arriba es el coste de las acciones que te quedan de verdad."}>
                          {comoBroker
                            ? `${metodo.toUpperCase()} = ${usd(p.precio_medio, p.divisa)}`
                            : `bróker ≈ ${usd(p.precio_medio_ponderado, p.divisa)}`}
                        </div>
                      )}
                    </td>
                    <td className="py-2 text-right font-mono">{eur(invertido)}</td>
                    <td className="py-2 text-right font-mono"><CeldaValorHoy p={p} /></td>
                    <td className="px-4 py-2 text-right">
                      <span className={`font-mono font-semibold ${tono(g.pnl_eur)}`}>{eur(g.pnl_eur)}</span>
                      <span className={`font-mono text-[10px] ml-1 ${tono(g.pct_eur)}`}>{pct(g.pct_eur)}</span>
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
              {/* Totales: hasta ahora había que sumar las filas a mano para saber cuánto
                  llevas metido y cuánto vale hoy. El % agregado es sobre lo invertido. */}
              <tfoot>
                <tr className="border-t-2 border-linea font-semibold">
                  <td className="px-4 py-2">Total</td>
                  <td className="py-2 text-right font-mono text-tinta-3">
                    {resumen.posiciones.length} pos.
                  </td>
                  <td />
                  <td className="py-2 text-right font-mono">{eur(resumen.invertido_eur)}</td>
                  <td className="py-2 text-right font-mono">{eur(resumen.valor_eur)}</td>
                  <td className="px-4 py-2 text-right">
                    {(() => {
                      const lat = comoBroker && latenteBroker != null ? latenteBroker : latente;
                      const base = resumen.invertido_eur;
                      return (
                        <>
                          <span className={`font-mono ${tono(lat)}`}>{eur(lat)}</span>
                          {base ? (
                            <span className={`font-mono text-[10px] ml-1 ${tono(lat)}`}>
                              {pct((lat / base) * 100)}
                            </span>
                          ) : null}
                        </>
                      );
                    })()}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
          {/* La explicación se lee una vez y luego estorba: plegada por defecto. */}
          <details className="border-t border-linea">
            <summary className="px-4 py-2 text-[11px] text-tinta-3 cursor-pointer">
              Cómo leer esta tabla
            </summary>
          <p className="px-4 pb-2 text-[11px] text-tinta-3">
            El precio medio es el de las acciones que te QUEDAN, por <b>{metodo.toUpperCase()}</b>.
            Tras vender parte, FIFO y LIFO dejan lotes distintos abiertos y el medio no
            coincide: si no cuadra con tu bróker, prueba el otro método arriba.
            <br />
            Las campanitas de la Cartera se mueven solas: se apagan al comprar en un nivel y
            vuelven a encenderse en cuanto vendes la última acción de ese nivel. Los niveles
            que no tengan compras registradas no se tocan.
            <br />
            <b>bróker ≈</b> es el precio medio ponderado, el que suele enseñar tu bróker: promedia
            TODO lo que has comprado y no cambia al vender. El de arriba es el coste real de
            las acciones que te quedan. Los dos son correctos y miden cosas distintas — el
            ponderado sirve para cuadrar pantallas, no para saber lo que ganaste en cada nivel.
          </p>
          </details>
        </Plegable>
      )}

      {/* Al final, no en medio. Es lo que autoriza a estimar el margen de una venta, pero
          se teclea una vez al mes: partía la página en dos entre el historial y la tabla
          de posiciones, que es lo que se viene a mirar. Su sitio no cambia lo que hace. */}
      <ExtractoMargen />
    </div>
  );
}
