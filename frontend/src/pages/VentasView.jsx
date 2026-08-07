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
            <div className="flex justify-between">
              <span className="text-[#5c6b66]">Ingresado (menos comisión)</span>
              <span className="font-mono">{usd(m.coste_divisa + m.ganancia_divisa, v.divisa)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#5c6b66]">Coste de esas acciones</span>
              <span className="font-mono">{usd(m.coste_divisa, v.divisa)}</span>
            </div>
            {m.efecto_divisa_eur != null && (
              // Aparece sola en cuanto ves que ganaste en dólares y menos en euros.
              <div className="flex justify-between">
                <span className="text-[#5c6b66]" title="Parte del resultado que se debe al movimiento del euro frente a la divisa, y no a la acción.">
                  De eso, por el movimiento del euro ⓘ
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
            {difiere && (
              <div className="flex justify-between pt-1 border-t border-[#e5e0d8] dark:border-[#1a3a32] mt-1">
                <span className="text-[#5c6b66]">
                  Por {metodo === "fifo" ? "LIFO" : "FIFO"} habría sido
                </span>
                <span className="font-mono text-[#5c6b66]">
                  {otro.ganancia_eur != null ? eur(otro.ganancia_eur) : usd(otro.ganancia_divisa, v.divisa)}
                  {" · "}{pct(otro.pct_eur ?? otro.pct)}
                </span>
              </div>
            )}
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
                : <Chip title="Esta compra no cae cerca de ninguno de los niveles que tienes en la Cartera.">fuera de niveles</Chip>}
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
  const [fecha, setFecha] = React.useState(hoy);
  const [iguales, setIguales] = React.useState("");
  const [guardando, setGuardando] = React.useState(false);
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
    .map((n) => ({ ...n, acciones: Number(porNivel[n.nivel]) || 0 }))
    .filter((n) => n.acciones > 0);
  const totalAcciones = filas.reduce((s, f) => s + f.acciones, 0);
  const totalCoste = filas.reduce((s, f) => s + f.acciones * f.precio, 0);

  const guardar = async () => {
    if (!sym) return toast.error("Falta el ticker");
    if (!filas.length) return toast.error("Pon cuántas acciones compraste en algún nivel");
    setGuardando(true);
    try {
      // En serie y de más caro a más barato: el orden de creación es el que desempata
      // FIFO cuando las fechas coinciden.
      for (const f of filas) {
        await api.cartera.comprar({
          symbol: sym, acciones: f.acciones, precio: f.precio,
          fecha, nivel: f.nivel, comision: 0,
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
        <Campo label="Fecha"
               ayuda="La misma para todas. Si las compraste en fechas distintas y las recuerdas, dalas de alta una a una para que los euros salgan con el cambio correcto de cada día.">
          <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} className={inputCls} />
        </Campo>
        <Campo label="Mismas en cada nivel"
               ayuda="Atajo para el caso normal: si en cada nivel compraste lo mismo, escríbelo una vez.">
          <input value={iguales} onChange={(e) => aplicarIguales(e.target.value)}
                 inputMode="decimal" placeholder="5" className={inputCls} />
        </Campo>
      </div>

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
        </p>
      )}

      <button onClick={guardar} disabled={guardando || !filas.length}
              className="w-full bg-[#1a3a32] text-[#f5f3ef] rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
        {guardando ? "Guardando…" : `Guardar ${filas.length || ""} compra(s)`}
      </button>
    </div>
  );
}

function FormularioOperacion({ tipo, onHecho, onCerrar }) {
  const hoy = new Date().toISOString().slice(0, 10);
  const [f, setF] = React.useState({ symbol: "", acciones: "", precio: "", comision: "", fecha: hoy, notas: "" });
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const qc = useQueryClient();

  const mut = useMutation({
    mutationFn: (payload) => (tipo === "compra" ? api.cartera.comprar(payload) : api.cartera.vender(payload)),
    onSuccess: () => {
      toast.success(tipo === "compra" ? "Compra registrada" : "Venta registrada");
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
               ayuda="Lo que te cobró el bróker por ESTA operación. En DeGiro no es fija: depende del mercado y del producto. Súmala tal cual aparece en tu extracto; si la dejas vacía se calcula sin ella y la ganancia saldrá algo optimista.">
          <input value={f.comision} onChange={set("comision")} inputMode="decimal" placeholder="1.00" className={inputCls} />
        </Campo>
        <Campo label="Fecha"
               ayuda="Determina el tipo de cambio que se usa. Ponla bien o los euros saldrán de otro día.">
          <input type="date" value={f.fecha} onChange={set("fecha")} className={inputCls} />
        </Campo>
        <Campo label="Notas">
          <input value={f.notas} onChange={set("notas")} placeholder="opcional" className={inputCls} />
        </Campo>
      </div>

      {tipo === "compra" && (
        <p className="text-[11px] text-[#5c6b66]">
          El nivel se detecta solo: si el precio cae cerca de alguno de los niveles que tienes
          puestos en la Cartera, la compra queda marcada con ese nivel.
        </p>
      )}

      {tipo === "venta" && <VistaPreviaVenta symbol={f.symbol} acciones={f.acciones} />}

      <button type="submit" disabled={mut.isPending}
              className="w-full bg-[#1a3a32] text-[#f5f3ef] rounded px-4 py-2 text-sm font-semibold disabled:opacity-60">
        {mut.isPending ? "Guardando…" : tipo === "compra" ? "Guardar compra" : "Guardar venta"}
      </button>
    </form>
  );
}

// ── Pantalla ─────────────────────────────────────────────────────────────────
export default function VentasView() {
  // FIFO por defecto: es el método obligatorio en España y el único que vale para la
  // declaración. LIFO está a un clic, pero etiquetado, para que nadie confunda las cifras.
  const [metodo, setMetodo] = React.useState("fifo");
  const [form, setForm] = React.useState(null);   // "compra" | "venta" | null
  const [abierta, setAbierta] = React.useState(null);   // símbolo desplegado en la tabla
  const qc = useQueryClient();

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

  const borrar = useMutation({
    mutationFn: (v) => api.cartera.borrarVenta(v.id),
    onSuccess: () => {
      toast.success("Venta borrada");
      qc.invalidateQueries({ queryKey: ["cartera"] });
    },
    onError: () => toast.error("No se pudo borrar"),
  });

  const importar = useMutation({
    mutationFn: api.cartera.importar,
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

  const tot = hist?.resumen?.[metodo];
  const ventas = hist?.items || [];
  const realizado = tot?.ganancia_eur;
  const latente = resumen?.latente_eur;
  const total = (realizado != null || latente != null)
    ? (realizado || 0) + (latente || 0) : null;

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

      {form === "niveles"
        ? <FormularioPorNiveles onCerrar={() => setForm(null)} />
        : form && <FormularioOperacion tipo={form} onCerrar={() => setForm(null)} />}

      {/* Cifras de cabecera. Realizado y latente van SEPARADOS: uno está en tu cuenta y el
          otro puede evaporarse mañana. Sumarlos sin distinguirlos da una sensación de
          riqueza que el mercado no ha confirmado. */}
      <div className="flex gap-3 flex-wrap">
        <Kpi etiqueta="Realizado" valor={realizado} acento
             sub={`${tot?.n_ventas ?? 0} venta(s) · ${metodo.toUpperCase()}`}
             ayuda="Ganancia de las ventas ya hechas, con el tipo de cambio del día de cada compra y de cada venta. Es dinero que ya está en tu cuenta." />
        <Kpi etiqueta="Latente" valor={latente}
             sub={resumen?.posiciones?.length ? `${resumen.posiciones.length} posición(es) abiertas` : "sin posiciones"}
             ayuda="Lo que llevas ganado en lo que AÚN NO has vendido, al precio y al cambio de hoy. Puede cambiar mañana." />
        <Kpi etiqueta="Total" valor={total}
             sub="realizado + latente" />
        {tot?.efecto_divisa_eur != null && Math.abs(tot.efecto_divisa_eur) >= 0.01 && (
          <Kpi etiqueta="Efecto del euro" valor={tot.efecto_divisa_eur}
               sub="incluido en el realizado"
               ayuda="Cuánto de tu ganancia realizada viene del movimiento del euro frente al dólar, y no de que la acción subiera." />
        )}
      </div>

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
          {metodo === "fifo" ? (
            <span className="text-[11px] text-[#4a7c59] font-semibold">✓ Es el que va a tu declaración</span>
          ) : (
            <span className="text-[11px] text-[#8a6508] font-semibold">⚠ Solo como referencia — no vale para Hacienda</span>
          )}
        </div>
        <p className="text-[11px] text-[#5c6b66] mt-2 leading-relaxed">
          <b>FIFO</b> vende primero lo que compraste primero. Es obligatorio en España para
          acciones cotizadas (art. 37.2 de la Ley del IRPF) y es la cifra que Hacienda
          considera tu ganancia. <b>LIFO</b> vende lo último que compraste — suele ser como
          uno lo piensa al promediar a la baja, pero no es válido fiscalmente.
          {tot && hist?.resumen?.fifo && hist?.resumen?.lifo
            && hist.resumen.fifo.ganancia_divisa !== hist.resumen.lifo.ganancia_divisa && (
            <> En tu caso la diferencia entre ambos es de{" "}
              <b>{usd(Math.abs(hist.resumen.fifo.ganancia_divisa - hist.resumen.lifo.ganancia_divisa))}</b>.</>
          )}
        </p>
      </div>

      {tot?.aviso && (
        <div className="card-flat px-4 py-2.5 border border-[#c9a14a]/40 bg-[#c9a14a]/[0.06] flex items-start gap-2">
          <span>⚠️</span>
          <span className="text-[11px] text-[#8a6508] leading-snug">{tot.aviso}</span>
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
            <button onClick={() => importar.mutate()} disabled={importar.isPending}
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
            <h2 className="font-heading font-bold text-sm">Lo que tienes abierto</h2>
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
                    <td className="py-2 text-right font-mono">{usd(p.precio_medio, p.divisa)}</td>
                    <td className="py-2 text-right font-mono">{eur(p.coste_eur)}</td>
                    <td className="py-2 text-right font-mono">{eur(p.valor_eur)}</td>
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
            El precio medio es el de las acciones que te QUEDAN, por FIFO. Tras vender parte,
            FIFO y LIFO dejan lotes distintos abiertos y el medio no coincide.
            <br />
            Las campanitas de la Cartera se mueven solas: se apagan al comprar en un nivel y
            vuelven a encenderse en cuanto vendes la última acción de ese nivel. Los niveles
            que no tengan compras registradas no se tocan.
          </p>
        </div>
      )}
    </div>
  );
}
