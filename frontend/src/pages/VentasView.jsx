import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "../lib/api";

// ── Formato ──────────────────────────────────────────────────────────────────
// Todo el dinero pasa por aquí para que no haya dos formatos distintos en la misma
// pantalla. `null` se pinta como "—" y NUNCA como 0: un 0 afirma que no ganaste nada,
// mientras que lo cierto es que falta el tipo de cambio para saberlo.
const eur = (v) => (v == null ? "—" : `${v >= 0 ? "" : "−"}${Math.abs(v).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`);
const usd = (v, d = "USD") => (v == null ? "—" : `${v >= 0 ? "" : "−"}${Math.abs(v).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${d === "USD" ? "$" : d}`);
const pct = (v) => (v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}%`);
const fecha = (f) => (f ? f.split("-").reverse().join("/") : "—");

const tono = (v) => (v == null ? "text-[#5c6b66]" : v >= 0 ? "text-[#4a7c59]" : "text-[#d85c41]");

const NIVEL_ETIQUETA = {
  deseado: "Deseado", nivel1: "Nivel 1", nivel2: "Nivel 2",
  nivel3: "Nivel 3", nivel4: "Nivel 4", nivel5: "Nivel 5",
};

function Chip({ children, tono: t = "neutro", title }) {
  const estilos = {
    neutro: "bg-[#f0ece3] text-[#5c6b66] dark:bg-[#1a3a32] dark:text-[#8fa39b]",
    nivel: "bg-[#2563eb]/12 text-[#2563eb]",
    aviso: "bg-[#c9a14a]/15 text-[#8a6508]",
  }[t];
  return (
    <span title={title} className={`font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${estilos}`}>
      {children}
    </span>
  );
}

// ── Cifra grande de cabecera ─────────────────────────────────────────────────
function Kpi({ etiqueta, valor, sub, acento = false, ayuda }) {
  return (
    <div className="card-flat px-4 py-3 flex-1 min-w-[150px]">
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono flex items-center gap-1">
        {etiqueta}
        {ayuda && <span title={ayuda} className="cursor-help opacity-60">ⓘ</span>}
      </p>
      <p className={`font-mono font-bold mt-1 ${acento ? "text-2xl" : "text-xl"} ${tono(valor)}`}>
        {eur(valor)}
      </p>
      {sub && <p className="text-[11px] text-[#5c6b66] mt-0.5">{sub}</p>}
    </div>
  );
}

// ── Detalle de una venta: de qué lotes salió ─────────────────────────────────
// Es la respuesta a "¿de qué compra eran estas acciones?", que es justo lo que un número
// suelto no puede contestar y por lo que existe el libro de lotes.
function DetalleLotes({ lotes, divisa }) {
  if (!lotes?.length) return null;
  return (
    <div className="bg-[#faf8f4] dark:bg-[#0e1f1a] px-4 py-3 border-t border-[#e5e0d8] dark:border-[#1a3a32]">
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-2">
        Estas acciones salieron de
      </p>
      <div className="space-y-1.5">
        {lotes.map((l, i) => (
          <div key={i} className="flex items-center gap-3 flex-wrap text-xs">
            <span className="font-mono text-[#5c6b66] w-20">{fecha(l.fecha_compra)}</span>
            <span className="font-mono font-semibold">{l.acciones} × {usd(l.precio_compra, divisa)}</span>
            {l.nivel && <Chip tono="nivel">{NIVEL_ETIQUETA[l.nivel] || l.nivel}</Chip>}
            {l.comision_parte > 0 && (
              <span className="text-[11px] text-[#5c6b66]">
                +{usd(l.comision_parte, divisa)} comisión
              </span>
            )}
            <span className="ml-auto font-mono text-[#5c6b66]">
              coste {usd(l.coste_divisa, divisa)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Una venta ────────────────────────────────────────────────────────────────
function FilaVenta({ v, metodo, onBorrar }) {
  const [abierto, setAbierto] = React.useState(false);
  const m = v[metodo];
  const otro = v[metodo === "fifo" ? "lifo" : "fifo"];
  const difiere = Math.abs((m.ganancia_divisa ?? 0) - (otro.ganancia_divisa ?? 0)) > 0.005;

  return (
    <div className="border-b border-[#e5e0d8] dark:border-[#1a3a32] last:border-0">
      <div className="px-4 py-3 flex items-center gap-3 flex-wrap hover:bg-[#faf8f4] dark:hover:bg-[#0e1f1a] transition-colors">
        <button onClick={() => setAbierto((o) => !o)} className="flex items-center gap-3 flex-1 min-w-0 text-left">
          <span className="font-mono text-[11px] text-[#5c6b66] w-16 shrink-0">{fecha(v.fecha)}</span>
          <span className="font-mono font-bold text-sm w-16 shrink-0">{v.symbol}</span>
          <span className="font-mono text-xs text-[#5c6b66] shrink-0">
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
              <span className="text-[#5c6b66]"> · {usd(m.ganancia_divisa, v.divisa)}</span>
            )}
          </p>
        </div>

        <button onClick={() => setAbierto((o) => !o)}
                className="text-[#5c6b66] text-xs w-5 shrink-0" aria-label="Ver detalle">
          {abierto ? "▲" : "▼"}
        </button>
      </div>

      {abierto && (
        <div>
          <DetalleLotes lotes={m.lotes} divisa={v.divisa} />
          <div className="px-4 py-3 bg-[#faf8f4] dark:bg-[#0e1f1a] border-t border-[#e5e0d8] dark:border-[#1a3a32] text-xs space-y-1">
            {/* Las DOS columnas, divisa y euros, en cada paso. Antes solo salían los
                dólares y luego aparecía la ganancia en euros: el salto de "259 $" a "209 €"
                había que creérselo. Con los dos lados y el tipo de cambio, la cuenta se
                rehace a mano en un minuto — que es la única forma de fiarse de una cifra. */}
            <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 gap-y-1 items-baseline">
              <span className="text-[10px] uppercase tracking-wider text-[#5c6b66] font-mono">Concepto</span>
              <span className="text-[10px] uppercase tracking-wider text-[#5c6b66] font-mono text-right">
                {v.divisa === "USD" ? "Dólares" : v.divisa}
              </span>
              <span className="text-[10px] uppercase tracking-wider text-[#5c6b66] font-mono text-right">Euros</span>

              <span className="text-[#5c6b66]">Ingresado (menos comisión)</span>
              <span className="font-mono text-right">{usd(m.ingreso_divisa, v.divisa)}</span>
              <span className="font-mono text-right">{eur(m.ingreso_eur)}</span>

              <span className="text-[#5c6b66]">Coste de esas acciones</span>
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
              <span className="text-[#5c6b66]">Porcentaje</span>
              <span className={`font-mono text-right ${tono(m.pct)}`}>{pct(m.pct)}</span>
              <span className={`font-mono text-right ${tono(m.pct_eur)}`}>{pct(m.pct_eur)}</span>
            </div>

            {v.tasa_venta && (
              <p className="text-[10px] text-[#5c6b66] pt-1">
                Cambio del día de la venta: 1 € = {v.tasa_venta} {v.divisa}. El coste va al
                cambio del día de CADA compra, que es el que ves en cada línea de arriba.
              </p>
            )}

            {m.efecto_divisa_eur != null && (
              // Aparece sola en cuanto ves que ganaste en dólares y menos en euros.
              <div className="flex justify-between pt-1">
                <span className="text-[#5c6b66]" title="Parte del resultado que se debe al movimiento del euro frente a la divisa, y no a la acción. Si es negativo, el euro se comió parte de tu ganancia.">
                  De la ganancia en euros, por el movimiento del euro ⓘ
                </span>
                <span className={`font-mono ${tono(m.efecto_divisa_eur)}`}>{eur(m.efecto_divisa_eur)}</span>
              </div>
            )}
            {!m.exacto && (
              <p className="text-[11px] text-[#8a6508] pt-1">
                Falta el tipo de cambio de alguna compra: la ganancia en euros de esta venta
                no se puede calcular y no entra en los totales.
              </p>
            )}
            {/* Los otros dos métodos, siempre. Es la misma venta contada de tres formas y
                cada una sirve para algo distinto; enseñar solo una invita a usarla para todo. */}
            <div className="pt-2 border-t border-[#e5e0d8] dark:border-[#1a3a32] mt-1 space-y-0.5">
              {difiere && (
                <div className="flex justify-between">
                  <span className="text-[#5c6b66]">
                    Por <b>{metodo === "fifo" ? "LIFO" : "FIFO"}</b>
                    {metodo === "fifo"
                      ? " (como vendes tú)"
                      : " (lo que va a tu declaración)"}
                  </span>
                  <span className="font-mono text-[#5c6b66]">
                    {otro.ganancia_eur != null ? eur(otro.ganancia_eur) : usd(otro.ganancia_divisa, v.divisa)}
                    {" · "}{pct(otro.pct_eur ?? otro.pct)}
                  </span>
                </div>
              )}
              {v.ponderada && (
                <div className="flex justify-between">
                  <span className="text-[#5c6b66]"
                        title="Media ponderada: el método que usa tu bróker para su pantalla. Todas tus acciones cuestan lo mismo (la media), así que no distingue niveles. Sirve para cuadrar con DEGIRO, no para la declaración.">
                    Por <b>media ponderada</b> (como tu bróker) ⓘ
                  </span>
                  <span className="font-mono text-[#5c6b66]">
                    {usd(v.ponderada.ganancia_divisa, v.divisa)}
                    {v.ponderada.pct != null && ` · ${pct(v.ponderada.pct)}`}
                  </span>
                </div>
              )}
            </div>
            <div className="pt-2">
              <button onClick={() => onBorrar(v)} className="text-[11px] text-[#d85c41] hover:underline">
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
    mutationFn: () => api.cartera.importarDegiro(archivo, mapeo, true),
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
        qc.invalidateQueries({ queryKey: ["cartera"] });
        onCerrar();
        return;
      }
      toast.success(r.importadas
        ? `${r.importadas} operación(es) importadas`
          + (r.saltadas ? ` · ${r.saltadas} ya estaban` : "")
        : `Ya estaba todo importado (${r.saltadas} operaciones). No hacía falta nada.`,
        { duration: 8000 });
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
    <div className="card-flat p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-heading font-bold text-sm">Importar el CSV de DEGIRO</h3>
        <button type="button" onClick={onCerrar} className="text-[#5c6b66] text-sm">✕</button>
      </div>

      <p className="text-[11px] text-[#5c6b66] leading-relaxed">
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
                className="w-full bg-[#1a3a32] text-[#f5f3ef] rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
          {leer.isPending ? "Leyendo…" : "Leer el fichero"}
        </button>
      )}

      {previo && (
        <div className="space-y-3">
          <div className="text-[11px] text-[#5c6b66] border-t border-[#e5e0d8] dark:border-[#1a3a32] pt-2">
            <b>{previo.resumen?.total}</b> operaciones ·{" "}
            {previo.resumen?.compras} compras · {previo.resumen?.ventas} ventas ·{" "}
            de {fecha(previo.resumen?.desde)} a {fecha(previo.resumen?.hasta)} ·{" "}
            {usd(previo.resumen?.comisiones)} de comisiones reales
          </div>

          {!!previo.errores?.length && (
            <div className="text-[11px] text-[#8a6508]">
              {previo.errores.length} línea(s) no se han entendido y quedan fuera:
              <ul className="list-disc ml-4">
                {previo.errores.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </div>
          )}

          {/* El emparejamiento. Solo se pregunta una vez por producto: el ISIN se guarda en
              la Cartera y la próxima importación ya no lo pide. */}
          <div>
            <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-2">
              ¿A qué acción corresponde cada producto?
            </p>
            <div className="space-y-1.5">
              {(previo.productos || []).map((p) => (
                <div key={p.isin} className="flex items-center gap-2 flex-wrap text-xs">
                  <span className="flex-1 min-w-0 truncate" title={p.isin}>{p.producto}</span>
                  <span className="text-[10px] text-[#5c6b66] font-mono">{p.operaciones} ops</span>
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
                    className="border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-2 py-1 font-mono text-xs w-28 bg-transparent disabled:opacity-40" />
                  <label className="flex items-center gap-1 text-[10px] text-[#5c6b66] cursor-pointer"
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
            <p className="text-[11px] text-[#5c6b66] mt-2">
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
              <p className="text-[11px] text-[#8a6508] mt-1">
                Faltan <b>{pendientes.length}</b> por decidir: ponles ticker o márcalos como
                ignorar.
              </p>
            )}
          </div>

          <button onClick={() => confirmar.mutate()}
                  disabled={confirmar.isPending || !!pendientes.length}
                  className="w-full bg-[#1a3a32] text-[#f5f3ef] rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
            {confirmar.isPending ? "Importando…"
              : ignorados.length
                ? `Importar (ignorando ${ignorados.length} producto(s))`
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
    mutationFn: (id) => api.cartera.borrarCompra(id),
    onSuccess: () => {
      toast.success("Compra borrada");
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
    onError: () => toast.error("No se pudo borrar"),
  });

  // La detección automática solo asigna nivel si el precio está a menos del 1,5%; una
  // compra real puede desviarse más (2 AAOI a 120,89 $ sobre un nivel de 118,90: 1,67%,
  // lote "fuera de niveles" y campanita sin apagar). Aquí se corrige a mano.
  const asignar = useMutation({
    mutationFn: ({ id, nivel }) => api.cartera.cambiarNivelCompra(id, nivel),
    onSuccess: () => {
      toast.success("Nivel asignado — campanitas actualizadas");
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
    onError: () => toast.error("No se pudo asignar el nivel"),
  });

  if (isPending) return <p className="px-4 py-3 text-xs text-[#5c6b66]">Cargando…</p>;

  const est = data?.[metodo];
  const abiertos = est?.abiertos || [];
  const divisa = data?.divisa || "USD";
  const compradas = (data?.compras || []).reduce((s, c) => s + (c.acciones || 0), 0);
  const vendidas = compradas - (est?.acciones_abiertas || 0);

  return (
    <div className="bg-[#faf8f4] dark:bg-[#0e1f1a] px-4 py-3 border-t border-[#e5e0d8] dark:border-[#1a3a32]">
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono mb-2">
        Lo que te queda, por compra · {metodo.toUpperCase()}
        {vendidas > 0.0001 && (
          <span className="normal-case tracking-normal ml-2">
            (compraste {compradas}, vendiste {Math.round(vendidas * 1e6) / 1e6})
          </span>
        )}
      </p>

      {!abiertos.length ? (
        <p className="text-xs text-[#5c6b66]">
          No queda nada abierto de {symbol}: se ha vendido la posición entera.
        </p>
      ) : (
        <div className="space-y-1.5">
          {abiertos.map((l) => (
            <div key={l.id} className="flex items-center gap-3 flex-wrap text-xs">
              <span className="font-mono text-[#5c6b66] w-20 shrink-0">{fecha(l.fecha)}</span>
              <span className="font-mono font-semibold">
                {l.acciones_abiertas} × {usd(l.precio, divisa)}
              </span>
              {l.acciones_abiertas !== l.acciones && (
                <span className="text-[10px] text-[#5c6b66]">(de {l.acciones})</span>
              )}
              {l.nivel
                ? <Chip tono="nivel">{NIVEL_ETIQUETA[l.nivel] || l.nivel}</Chip>
                : (
                  <span className="inline-flex items-center gap-1.5">
                    <Chip title="Esta compra no cae a menos del 1,5% de ninguno de tus niveles. Si en realidad ES la compra de un nivel, asígnaselo aquí y su campanita se apagará.">fuera de niveles</Chip>
                    <select value="" disabled={asignar.isPending}
                            onChange={(e) => e.target.value && asignar.mutate({ id: l.id, nivel: e.target.value })}
                            className="text-[10px] bg-transparent border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-1 py-0.5 text-[#5c6b66]">
                      <option value="">asignar nivel…</option>
                      {(data?.niveles || []).map((n) => (
                        <option key={n.nivel} value={n.nivel}>
                          {n.etiqueta} · {n.precio} {divisa === "EUR" ? "€" : "$"}
                        </option>
                      ))}
                    </select>
                  </span>
                )}
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
              <span className="ml-auto font-mono text-[#5c6b66]">
                {l.coste_eur != null ? eur(l.coste_eur) : usd(l.coste_divisa, divisa)}
              </span>
              <button
                onClick={() => window.confirm(`¿Borrar la compra de ${l.acciones} ${symbol} del ${fecha(l.fecha)}?`) && borrar.mutate(l.id)}
                className="text-[11px] text-[#d85c41] hover:underline shrink-0">
                borrar
              </button>
            </div>
          ))}
        </div>
      )}

      {/* El orden de consumo es la respuesta a "de qué nivel será la próxima venta". */}
      {abiertos.length > 1 && (
        <p className="text-[11px] text-[#5c6b66] mt-2 pt-2 border-t border-[#e5e0d8] dark:border-[#1a3a32]">
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
      <span className="text-[10px] uppercase tracking-wider text-[#5c6b66] font-mono flex items-center gap-1">
        {label}{ayuda && <span title={ayuda} className="cursor-help opacity-60">ⓘ</span>}
      </span>
      {children}
    </label>
  );
}

const inputCls = "mt-1 w-full border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-2 py-1.5 font-mono text-sm bg-transparent";

// Qué lotes se van a consumir ANTES de guardar la venta. El método decide de qué compra
// —y por tanto de qué nivel— sale lo que vendes, y eso no es evidente: con FIFO, vender
// consume la compra más antigua aunque fuera la más cara. Verlo antes evita registrar una
// venta pensando que salía de otro sitio.
function VistaPreviaVenta({ symbol, acciones }) {
  const sym = (symbol || "").trim().toUpperCase();
  const n = Number(acciones);
  const { data } = useQuery({
    queryKey: ["cartera", "posicion", sym],
    queryFn: () => api.cartera.posicion(sym),
    enabled: sym.length >= 1,
    staleTime: 30_000,
    retry: false,
  });
  if (!sym || !data) return null;

  const divisa = data.divisa || "USD";
  const disponibles = data.fifo?.acciones_abiertas ?? 0;
  if (!disponibles) {
    return (
      <p className="text-[11px] text-[#8a6508]">
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
    <div className="rounded border border-[#e5e0d8] dark:border-[#1a3a32] px-3 py-2 space-y-1.5">
      <p className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono">
        Tienes {disponibles} acciones de {sym}
      </p>
      {n > 0 && (
        <>
          {n > disponibles + 1e-9 && (
            <p className="text-[11px] text-[#8a6508]">
              Estás vendiendo más de las que constan compradas ({disponibles}). Se registrará
              igual y quedará marcada, por si lo que falta es meter una compra antigua.
            </p>
          )}
          {[["fifo", "FIFO", "es el que vale para Hacienda"], ["lifo", "LIFO", "solo referencia"]].map(([k, label, nota]) => {
            const sim = simular(k);
            if (!sim.length) return null;
            return (
              <p key={k} className="text-[11px] text-[#5c6b66] leading-snug">
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
  const [fecha, setFecha] = React.useState(hoy);
  const [iguales, setIguales] = React.useState("");
  const [guardando, setGuardando] = React.useState(false);
  const [estimadas, setEstimadas] = React.useState(null);   // {nivel: {toques, ...}}
  const qc = useQueryClient();

  const sym = symbol.trim().toUpperCase();
  const { data } = useQuery({
    queryKey: ["cartera", "posicion", sym],
    queryFn: () => api.cartera.posicion(sym),
    enabled: sym.length >= 1,
    staleTime: 30_000,
    retry: false,
  });
  const niveles = data?.niveles || [];

  const aplicarIguales = (v) => {
    setIguales(v);
    const n = Number(v);
    if (n > 0) setPorNivel(Object.fromEntries(niveles.map((x) => [x.nivel, v])));
  };

  const filas = niveles
    .map((n) => ({ ...n, acciones: Number(porNivel[n.nivel]) || 0,
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
    <div className="card-flat p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-heading font-bold text-sm">Dar de alta las compras por niveles</h3>
        <button type="button" onClick={onCerrar} className="text-[#5c6b66] text-sm">✕</button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Campo label="Ticker">
          <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                 placeholder="MRVL" className={inputCls} autoFocus />
        </Campo>
        <Campo label="Fecha (para todas)"
               ayuda="Punto de partida: cada nivel puede llevar la suya abajo. La fecha decide el tipo de cambio con el que se calculan tus euros, así que cuanto más ajustada, más exacta la ganancia.">
          <input type="date" value={fecha}
                 onChange={(e) => { setFecha(e.target.value); setFechaPorNivel({}); }}
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
                  className="border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-3 py-1 text-[11px] font-semibold disabled:opacity-60">
            {estimarFechas.isPending ? "Buscando…" : "Estimar las fechas por el precio"}
          </button>
          <span className="text-[11px] text-[#5c6b66]">
            Busca el día en que el precio pasó por cada nivel. Útil si no las recuerdas.
          </span>
        </div>
      )}

      {!sym ? (
        <p className="text-[11px] text-[#5c6b66]">Escribe un ticker para ver sus niveles.</p>
      ) : !niveles.length ? (
        <p className="text-[11px] text-[#8a6508]">
          {sym} no tiene niveles puestos en la Cartera. Ponlos allí primero, o registra las
          compras una a una con su precio.
        </p>
      ) : (
        <div className="space-y-1.5">
          {niveles.map((n) => (
            <div key={n.nivel} className="flex items-center gap-3 text-xs">
              <Chip tono="nivel">{n.etiqueta}</Chip>
              <span className="font-mono text-[#5c6b66] w-24">{usd(n.precio, data?.divisa)}</span>
              {n.comprado && <span className="text-[10px] text-[#5c6b66]">campanita apagada</span>}
              <input
                value={porNivel[n.nivel] ?? ""}
                onChange={(e) => setPorNivel((p) => ({ ...p, [n.nivel]: e.target.value }))}
                inputMode="decimal" placeholder="acciones"
                className="ml-auto border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-2 py-1 font-mono text-xs w-24 bg-transparent" />
              <input
                type="date"
                value={fechaPorNivel[n.nivel] || fecha}
                onChange={(e) => setFechaPorNivel((p) => ({ ...p, [n.nivel]: e.target.value }))}
                title="Cuándo compraste ESTE nivel. Determina el tipo de cambio de esa compra."
                className="border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-2 py-1 font-mono text-xs bg-transparent" />
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
        <p className="text-[11px] text-[#5c6b66] border-t border-[#e5e0d8] dark:border-[#1a3a32] pt-2">
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
              className="w-full bg-[#1a3a32] text-[#f5f3ef] rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
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
    return Number(comision) === 0
      ? <p className="text-[11px] text-[#5c6b66]">Sin comisión: se registrará tal cual.</p>
      : null;
  }
  const bruto = (Number(acciones) || 0) * (Number(precio) || 0);
  const tasa = tasas?.tasas?.USD;
  if (!bruto || !tasa) {
    return (
      <p className="text-[11px] text-[#5c6b66]">
        La comisión se estimará con la tarifa de DEGIRO: 2 € por operación + 0,25% de
        conversión de divisa. Pon un 0 si esta operación no te costó nada.
      </p>
    );
  }
  const est = COMISION_FIJA_EUR * tasa + bruto * FX_AUTO_PCT;
  return (
    <p className="text-[11px] text-[#5c6b66]">
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
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "No se pudo guardar el precio"),
  });

  if (p.valor_eur == null) {
    return (
      <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        <input value={precio} onChange={(e) => setPrecio(e.target.value)} inputMode="decimal"
               placeholder={`precio en ${p.divisa === "EUR" ? "€" : "$"}`}
               className="w-24 text-[11px] bg-transparent border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-1.5 py-0.5 text-right font-mono" />
        <button disabled={mut.isPending || !(Number(precio) > 0)}
                onClick={() => mut.mutate({ symbol: p.symbol, valor: Number(precio) })}
                className="text-[11px] underline text-[#5c6b66] disabled:opacity-50">
          poner
        </button>
      </span>
    );
  }
  return (
    <>
      {eur(p.valor_eur)}
      {p.precio_manual && (
        <div className="text-[10px] text-[#8a6508] cursor-pointer"
             title="Este valor sale de un precio que pusiste tú a mano, no de una cotización en vivo. Pincha para cambiarlo o quitarlo."
             onClick={(e) => {
               e.stopPropagation();
               const nuevo = window.prompt(
                 `Precio manual de ${p.symbol} (ahora ${p.precio_actual}). `
                 + "Pon el nuevo, o déjalo vacío para quitarlo:", p.precio_actual);
               if (nuevo !== null) mut.mutate({ symbol: p.symbol, valor: Number(nuevo) || 0 });
             }}>
          precio manual · cambiar
        </div>
      )}
    </>
  );
}

function FormularioOperacion({ tipo, onHecho, onCerrar }) {
  const hoy = new Date().toISOString().slice(0, 10);
  const [f, setF] = React.useState({ symbol: "", acciones: "", precio: "", comision: "", fecha: hoy, notas: "", nivel: "" });
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const qc = useQueryClient();

  // Los niveles del valor, para poder decir de cuál es la compra. Con nivel elegido, el
  // precio de ese nivel en la Cartera se actualiza al precio REAL de la compra — que es lo
  // que antes había que acordarse de hacer a mano y se olvidaba.
  const sym = f.symbol.trim().toUpperCase();
  const { data: pos } = useQuery({
    queryKey: ["cartera", "posicion", sym],
    queryFn: () => api.cartera.posicion(sym),
    enabled: tipo === "compra" && sym.length >= 1,
    staleTime: 30_000,
    retry: false,
  });

  const mut = useMutation({
    mutationFn: (payload) => (tipo === "compra" ? api.cartera.comprar(payload) : api.cartera.vender(payload)),
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
      qc.invalidateQueries({ queryKey: ["cartera"] });
      onHecho?.();
      onCerrar();
    },
    onError: (e) => toast.error(e?.response?.data?.detail || "No se pudo guardar"),
  });

  const enviar = (e) => {
    e.preventDefault();
    const sym = f.symbol.trim().toUpperCase();
    const n = Number(f.acciones), p = Number(f.precio);
    if (!sym) return toast.error("Falta el ticker");
    if (!(n > 0)) return toast.error("El número de acciones debe ser mayor que cero");
    if (!(p > 0)) return toast.error("El precio debe ser mayor que cero");
    mut.mutate({
      symbol: sym, acciones: n, precio: p,
      comision: Number(f.comision) || 0,
      fecha: f.fecha || hoy, notas: f.notas || "",
      ...(tipo === "compra" && f.nivel ? { nivel: f.nivel } : {}),
    });
  };

  return (
    <form onSubmit={enviar} className="card-flat p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-heading font-bold text-sm">
          {tipo === "compra" ? "Registrar una compra" : "Registrar una venta"}
        </h3>
        <button type="button" onClick={onCerrar} className="text-[#5c6b66] text-sm">✕</button>
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
        {tipo === "compra" && !!pos?.niveles?.length && (
          <Campo label="¿De qué nivel es?"
                 ayuda="Elige el nivel y el precio de ese nivel en la Cartera se actualizará al precio real de esta compra, con su campanita apagada. En automático solo se detecta si el precio cae a menos del 1,5% del nivel.">
            <select value={f.nivel} onChange={set("nivel")} className={inputCls}>
              <option value="">detectar solo (±1,5%)</option>
              {pos.niveles.map((n) => (
                <option key={n.nivel} value={n.nivel}>
                  {n.etiqueta} · ahora {n.precio} {pos.divisa === "EUR" ? "€" : "$"}{n.comprado ? " · ya comprado" : ""}
                </option>
              ))}
            </select>
          </Campo>
        )}
      </div>

      {tipo === "compra" && (
        <p className="text-[11px] text-[#5c6b66]">
          {f.nivel
            ? `El precio del ${NIVEL_ETIQUETA[f.nivel] || f.nivel} en la Cartera se actualizará a tu precio real de compra y su campanita se apagará sola.`
            : "El nivel se detecta solo si el precio cae a menos del 1,5% de alguno de tus niveles; si compraste algo desviado, elígelo arriba y el precio del nivel en la Cartera se actualizará al tuyo."}
        </p>
      )}

      {tipo === "venta" && <VistaPreviaVenta symbol={f.symbol} acciones={f.acciones} />}

      <AvisoComision comision={f.comision} acciones={f.acciones} precio={f.precio} />

      <button type="submit" disabled={mut.isPending}
              className="w-full bg-[#1a3a32] text-[#f5f3ef] rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
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
  const [form, setForm] = React.useState(null);   // "compra" | "venta" | null
  const [abierta, setAbierta] = React.useState(null);   // símbolo desplegado en la tabla

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
      qc.invalidateQueries({ queryKey: ["cartera"] });
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
      if (!r.borrados) {
        toast.info("No había lotes duplicados que quitar");
      } else {
        toast.success(
          `${r.borrados} lote(s) duplicados quitados de ${r.simbolos.join(", ")}. ` +
          "Compara ahora las acciones con tu bróker.", { duration: 12000 });
      }
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
    onError: () => toast.error("No se pudieron quitar los duplicados"),
  });

  const tot = hist?.resumen?.[metodo];
  const ventas = hist?.items || [];
  const realizado = tot?.ganancia_eur;
  const latente = resumen?.latente_eur;
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
          <p className="text-sm text-[#5c6b66] mt-0.5">
            Lo que llevas ganado de verdad, en euros, con el tipo de cambio de cada operación.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setForm("degiro")}
                  className="bg-[#1a3a32] text-[#f5f3ef] rounded px-3 py-1.5 text-sm font-semibold">
            Importar CSV de DEGIRO
          </button>
          <button onClick={() => setForm("niveles")}
                  className="border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-3 py-1.5 text-sm font-semibold">
            + Compras por niveles
          </button>
          <button onClick={() => setForm("compra")}
                  className="border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-3 py-1.5 text-sm font-semibold">
            + Compra suelta
          </button>
          <button onClick={() => setForm("venta")}
                  className="bg-[#1a3a32] text-[#f5f3ef] rounded px-3 py-1.5 text-sm font-semibold">
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
        <Kpi etiqueta="Realizado" valor={realizado} acento
             // n_ventas cuelga del resumen, no del método: el número de ventas es el
             // mismo se mire con FIFO o con LIFO. Leerlo de dentro del método daba
             // siempre 0, o sea "no has vendido nada" con 148 ventas en la lista.
             // El descuadre va EN el KPI y no en una fila perdida: si hay acciones vendidas
             // sin compra registrada, salen con coste CERO y esta cifra está hinchada en
             // hasta esos euros. Sin el aviso, el número gordo se lee como bueno.
             sub={[
               `${hist?.resumen?.n_ventas ?? 0} venta(s) · ${metodo.toUpperCase()}`,
               hist?.resumen?.sin_cubrir_acciones
                 ? `⚠ ${hist.resumen.sin_cubrir_acciones} acción(es) vendidas sin compra registrada`
                   + ` (${(hist.resumen.sin_cubrir_por_symbol || []).map((s) => s.symbol).join(", ")})`
                   + ` — hasta ${eur(hist.resumen.sin_cubrir_eur_aprox)} de esta cifra pueden sobrar`
                 : null,
             ].filter(Boolean).join(" · ")}
             ayuda="Ganancia de las ventas ya hechas, con el tipo de cambio del día de cada compra y de cada venta. Es dinero que ya está en tu cuenta. Cambia según el método: mira la etiqueta de debajo." />
        <Kpi etiqueta="Latente" valor={latente}
             // Una posición sin cotización NO entra en el latente, y hasta ahora eso no se
             // decía: el número parecía completo cuando le faltaba una posición entera. Es
             // lo primero que hay que mirar cuando el total no cuadra con el bróker.
             sub={[
               resumen?.posiciones?.length
                 ? `${resumen.posiciones.length} posición(es) abiertas` : "sin posiciones",
               resumen?.posiciones_sin_valorar
                 ? `⚠ ${resumen.posiciones_sin_valorar} sin precio, fuera del total` : null,
             ].filter(Boolean).join(" · ")}
             ayuda="Lo que llevas ganado en lo que AÚN NO has vendido, al precio y al cambio de hoy. Puede cambiar mañana." />
        {/* SIEMPRE visible, aunque esté vacía. Escondiéndola hasta que hubiera dividendos,
            la única forma de enterarse de que existe era leer el texto del importador — y
            una función que no se ve no existe. Vacía dice qué falta para llenarla. */}
        <Kpi etiqueta="Dividendos" valor={dividendos}
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
          <Kpi etiqueta="Costes" valor={costes}
               sub={`${divs?.n_costes ?? 0} apunte(s) · intereses y conectividad`}
               ayuda="Intereses por operar con el saldo en negativo y conectividad con mercados, sacados del Account.csv. No incluye las comisiones de compraventa, que ya están descontadas en cada operación. Es lo que separa tu total del Total P/L de DEGIRO." />
        )}
        <Kpi etiqueta="Total" valor={total}
             sub={[
               "realizado + latente",
               dividendos != null ? "+ dividendos" : null,
               costes != null ? "+ costes" : null,
             ].filter(Boolean).join(" ")} />
        {tot?.efecto_divisa_eur != null && Math.abs(tot.efecto_divisa_eur) >= 0.01 && (
          <Kpi etiqueta="Efecto del euro" valor={tot.efecto_divisa_eur}
               sub="incluido en el realizado"
               ayuda="Cuánto de tu ganancia realizada viene del movimiento del euro frente al dólar, y no de que la acción subiera." />
        )}
      </div>

      {/* La misma venta metida a mano Y venida del CSV solo se detecta como duplicada si
          coincide al céntimo; tecleada de memoria, rara vez lo hace. En una posición ya
          cerrada no se nota en las acciones — solo en que el Realizado se dispara. */}
      {!!hist?.posibles_duplicadas?.length && (
        <div className="card-flat px-4 py-3 border-l-4 border-l-amber-500">
          <p className="text-sm font-semibold mb-1">
            ⚠ {hist.posibles_duplicadas.length} venta(s) posiblemente contadas dos veces
          </p>
          <p className="text-xs text-[#5c6b66] mb-2">
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

      {/* Selector de método. Va acompañado SIEMPRE de la explicación fiscal: enseñar dos
          cifras distintas para la misma venta sin decir cuál vale para Hacienda sería peor
          que enseñar una sola. */}
      <div className="card-flat px-4 py-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-[10px] uppercase tracking-[0.15em] text-[#5c6b66] font-mono">Método de cálculo</span>
          <div className="flex rounded overflow-hidden border border-[#e5e0d8] dark:border-[#1a3a32]">
            {[["fifo", "FIFO"], ["lifo", "LIFO"]].map(([k, label]) => (
              <button key={k} onClick={() => setMetodo(k)}
                      className={`px-3 py-1 text-xs font-mono font-semibold ${metodo === k ? "bg-[#1a3a32] text-[#f5f3ef]" : "text-[#5c6b66]"}`}>
                {label}
              </button>
            ))}
          </div>
          {cambiarMetodo.isPending && (
            <span className="text-[11px] text-[#5c6b66]">Recalculando…</span>
          )}
          {metodo === "lifo" ? (
            <span className="text-[11px] text-[#4a7c59] font-semibold">Vende lo más reciente · tu precio medio SUBE al vender</span>
          ) : (
            <span className="text-[11px] text-[#4a7c59] font-semibold">Vende lo más antiguo · tu precio medio BAJA al vender · es el de Hacienda</span>
          )}
        </div>
        <p className="text-[11px] text-[#5c6b66] mt-2 leading-relaxed">
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
      </div>

      {hist?.resumen?.aviso && (
        <div className="card-flat px-4 py-2.5 border border-[#c9a14a]/40 bg-[#c9a14a]/[0.06] flex items-start gap-2">
          <span>⚠️</span>
          <span className="text-[11px] text-[#8a6508] leading-snug">{hist.resumen.aviso}</span>
        </div>
      )}

      {/* Historial */}
      <div className="card-flat overflow-hidden">
        <div className="px-4 py-3 border-b border-[#e5e0d8] dark:border-[#1a3a32] flex items-center justify-between">
          <h2 className="font-heading font-bold text-sm">Historial de ventas</h2>
          <span className="text-[11px] text-[#5c6b66]">Toca una para ver de qué compra salió</span>
        </div>
        {cargandoHist ? (
          <p className="px-4 py-8 text-center text-sm text-[#5c6b66]">Cargando…</p>
        ) : !ventas.length ? (
          <div className="px-4 py-8 text-center space-y-3">
            <p className="text-sm text-[#5c6b66]">Aún no has registrado ninguna venta.</p>
            <p className="text-[11px] text-[#5c6b66] max-w-md mx-auto">
              Si ya tenías posiciones en la Cartera, impórtalas para no empezar de cero. Se
              reconstruye <b>un lote por cada nivel que tengas con la campanita apagada</b>,
              que es como marcas los niveles ya comprados. Con uno o dos niveles el reparto
              de acciones sale exacto a partir de tu precio medio; con tres o más es una
              estimación y te lo aviso para que la corrijas.
            </p>
            <button onClick={() => importar.mutate(false)} disabled={importar.isPending}
                    className="border border-[#e5e0d8] dark:border-[#1a3a32] rounded px-3 py-1.5 text-xs font-semibold disabled:opacity-60">
              {importar.isPending ? "Importando…" : "Importar mis posiciones actuales"}
            </button>
          </div>
        ) : (
          ventas.map((v) => (
            <FilaVenta key={v.id} v={v} metodo={metodo}
                       onBorrar={(x) => window.confirm(`¿Borrar la venta de ${x.acciones} ${x.symbol} del ${fecha(x.fecha)}?`) && borrar.mutate(x)} />
          ))
        )}
      </div>

      {/* Por acción */}
      {!!hist?.por_symbol?.length && (
        <div className="card-flat overflow-hidden">
          <div className="px-4 py-3 border-b border-[#e5e0d8] dark:border-[#1a3a32]">
            <h2 className="font-heading font-bold text-sm">Por acción</h2>
          </div>
          {hist.por_symbol.map((s) => (
            <div key={s.symbol} className="px-4 py-2.5 flex items-center gap-3 border-b border-[#e5e0d8] dark:border-[#1a3a32] last:border-0">
              <span className="font-mono font-bold text-sm w-16">{s.symbol}</span>
              <span className="text-[11px] text-[#5c6b66]">{s.n_ventas} venta(s)</span>
              <span className={`ml-auto font-mono font-semibold text-sm ${tono(s.ganancia_eur ?? s.ganancia_divisa)}`}>
                {s.ganancia_eur != null ? eur(s.ganancia_eur) : usd(s.ganancia_divisa, s.divisa)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Posiciones abiertas, en euros */}
      {!!resumen?.posiciones?.length && (
        <div className="card-flat overflow-hidden">
          <div className="px-4 py-3 border-b border-[#e5e0d8] dark:border-[#1a3a32] flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-3 flex-wrap">
              <h2 className="font-heading font-bold text-sm">Lo que tienes abierto</h2>
              {/* Rehacer la importación: si la primera salió con los lotes mal repartidos,
                  borrarlos uno a uno serían decenas de clics. No toca las acciones que ya
                  tengan ventas registradas — ahí borrar compras falsearía la ganancia. */}
              <button onClick={() => window.confirm(
                        "Se rehacen los lotes de las posiciones importadas, a partir de tus "
                        + "niveles y tu precio medio actuales.\n\nLas acciones que ya tengan "
                        + "ventas registradas NO se tocan.\n\n¿Continuar?")
                        && importar.mutate(true)}
                      disabled={importar.isPending}
                      className="text-[11px] text-[#5c6b66] underline disabled:opacity-60">
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
                      className="text-[11px] text-[#5c6b66] underline disabled:opacity-60">
                {quitarDup.isPending ? "Quitando…" : "Quitar duplicados del CSV"}
              </button>
            </div>
            {resumen.tasas && (
              <span className="text-[11px] text-[#5c6b66] font-mono">
                {Object.entries(resumen.tasas).filter(([d]) => d !== "EUR")
                  .map(([d, t]) => `1 € = ${t} ${d}`).join(" · ")}
              </span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[#5c6b66] border-b border-[#e5e0d8] dark:border-[#1a3a32]">
                  <th className="px-4 py-2 font-normal">Acción</th>
                  <th className="py-2 font-normal text-right">Acciones</th>
                  <th className="py-2 font-normal text-right">Precio medio</th>
                  <th className="py-2 font-normal text-right">Invertido</th>
                  <th className="py-2 font-normal text-right">Valor hoy</th>
                  <th className="px-4 py-2 font-normal text-right">Ganancia</th>
                </tr>
              </thead>
              <tbody>
                {resumen.posiciones.map((p) => (
                  <React.Fragment key={p.symbol}>
                  <tr className="border-b border-[#e5e0d8] dark:border-[#1a3a32] cursor-pointer hover:bg-[#faf8f4] dark:hover:bg-[#0e1f1a]"
                      onClick={() => setAbierta(abierta === p.symbol ? null : p.symbol)}>
                    <td className="px-4 py-2">
                      <span className="text-[#5c6b66] mr-1 text-[10px]">{abierta === p.symbol ? "▲" : "▼"}</span>
                      <span className="font-mono font-bold">{p.symbol}</span>
                      {!!p.niveles_comprados?.length && (
                        <span className="ml-2 inline-flex gap-1">
                          {p.niveles_comprados.map((n) => (
                            <Chip key={n} tono="nivel">{NIVEL_ETIQUETA[n] || n}</Chip>
                          ))}
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-right font-mono">{p.acciones}</td>
                    <td className="py-2 text-right font-mono">
                      {usd(p.precio_medio, p.divisa)}
                      {/* La media ponderada es OTRA medida, no una correccion de la de
                          arriba: el broker la usa y no se mueve al vender. Se enseña debajo
                          y etiquetada para poder cuadrar las dos pantallas sin pensar que
                          una de las dos esta mal. Solo cuando difieren, o seria ruido. */}
                      {p.precio_medio_ponderado != null
                        && Math.abs(p.precio_medio_ponderado - (p.precio_medio ?? 0)) > 0.01 && (
                        <div className="text-[10px] text-[#5c6b66]"
                             title="Precio medio ponderado: el que suele enseñar tu bróker. No cambia al vender, porque promedia TODO lo que has comprado. El de arriba es el coste de las acciones que te quedan de verdad.">
                          bróker ≈ {usd(p.precio_medio_ponderado, p.divisa)}
                        </div>
                      )}
                    </td>
                    <td className="py-2 text-right font-mono">{eur(p.coste_eur)}</td>
                    <td className="py-2 text-right font-mono"><CeldaValorHoy p={p} /></td>
                    <td className="px-4 py-2 text-right">
                      <span className={`font-mono font-semibold ${tono(p.pnl_eur)}`}>{eur(p.pnl_eur)}</span>
                      <span className={`font-mono text-[10px] ml-1 ${tono(p.pct_eur)}`}>{pct(p.pct_eur)}</span>
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
                ))}
              </tbody>
            </table>
          </div>
          <p className="px-4 py-2 text-[11px] text-[#5c6b66] border-t border-[#e5e0d8] dark:border-[#1a3a32]">
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
        </div>
      )}
    </div>
  );
}
