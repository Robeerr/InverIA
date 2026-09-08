import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, CaretRight, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { fmtEur, fmtPct } from "../lib/format";

/* Cabecera de Cartera · la lectura antes del detalle
   ─────────────────────────────────────────────────────────────────────────────
   La tabla de abajo es para EDITAR: quince columnas, niveles, campanas, celdas que
   se escriben. Esto es para LEER, y son dos trabajos distintos. Antes solo existía
   el segundo, así que para saber cuánto tienes invertido había que sumar mentalmente
   una tabla pensada para otra cosa.

   LA EVOLUCIÓN Y LA SALUD YA EXISTEN, PERO NO COMO SE PIDIERON

   Las dos hacían falta y ninguna se podía dibujar: no había serie que graficar ni
   índice que componer. Ahora `cartera_historico` guarda una foto diaria y calcula el
   índice, así que las dos son reales — con dos diferencias respecto del diseño:

     · La evolución EMPIEZA HOY. Nadie guardó nunca el valor de la cartera, así que
       la serie arranca vacía y se llena a un punto por día. Dibujar doce meses habría
       exigido inventárselos.
     · El índice se puede ABRIR. Un «78/100» que no se desglosa es una métrica
       inventada con otro nombre: nadie sabría si baja por concentración o por
       estructura. Cada componente enseña su nota, su peso APLICADO y su porqué.

   Y falta una que sigue sin poderse medir: la LIQUIDEZ. Necesita el saldo en
   efectivo, y hoy eso solo entra pegado a mano en el extracto de margen — no es un
   dato que el sistema tenga, es uno que el usuario escribe a veces.

   Lo demás del diseño está entero y sale de datos reales. */

const N_SECTOR = 6;   // sectores con nombre propio; el resto cae en «Otros»

/* Paleta categórica: la MISMA de la tabla de sectores de abajo, para que un sector
   no cambie de color entre dos bloques de la misma pantalla. */
const COLORES = ["#c9b37e", "#5bb77c", "#7fb2d9", "#e07a5f", "#6e9e9e", "#a9946b", "#8fa89e"];

const num = (v) => (typeof v === "number" && isFinite(v) ? v : null);

/** El estado de una posición en una frase, derivado de lo que ya sabemos.
 *
 * No hay ningún campo «estado» en la base de datos: sale de cruzar la tendencia que
 * calcula el backend con la distancia a tus niveles de compra. Por eso el orden de
 * las ramas importa — un veto manda sobre cualquier proximidad a un nivel, que es la
 * misma regla que aplica la ficha de la acción. */
function estadoDe(entrada, precio) {
  const t = (entrada?.tendencia || "").toUpperCase();
  if (t === "BAJISTA") return { txt: "Compra vetada", tono: "text-baja" };
  const niveles = [1, 2, 3, 4, 5]
    .map((n) => ({ n, p: num(Number(entrada?.[`nivel${n}`])) }))
    .filter((x) => x.p && x.p > 0);
  if (precio && niveles.length) {
    // El nivel más cercano POR ENCIMA del cual todavía no has comprado.
    const cerca = niveles
      .map((x) => ({ ...x, d: (precio - x.p) / x.p }))
      .filter((x) => x.d >= -0.005 && x.d <= 0.03)
      .sort((a, b) => Math.abs(a.d) - Math.abs(b.d))[0];
    if (cerca) return { txt: `Nivel ${cerca.n} cerca`, tono: "text-marca" };
  }
  if (t === "ALCISTA") return { txt: "Tendencia intacta", tono: "text-sube" };
  if (t === "INDEFINIDA") return { txt: "Esperar", tono: "text-tinta-2" };
  return { txt: "Sin datos", tono: "text-tinta-3" };
}

const RIESGO_TONO = { BAJO: "text-sube", MEDIO: "text-aviso", ALTO: "text-baja" };

/** Barra de peso: la misma pieza para la tabla y para la distribución. */
function Barra({ pct, color, ancho = "w-16" }) {
  return (
    <span className={`inline-block ${ancho} h-1 bg-superficie-alt align-middle overflow-hidden`}>
      <span className="block h-full" style={{ width: `${Math.min(100, Math.max(0, pct))}%`,
                                              background: color || "rgb(var(--iv-marca))" }} />
    </span>
  );
}

export default function CarteraCabecera({ entries = [], onAnalizarCorrelacion, onAnadir, onImportar }) {
  const { data: resumen } = useQuery({
    queryKey: ["cartera-resumen"],
    queryFn: () => api.cartera.resumen(),
    staleTime: 60_000,
    retry: false,
  });
  const { data: hist } = useQuery({
    queryKey: ["cartera-historico"],
    queryFn: () => api.cartera.historico(),
    staleTime: 300_000,
    retry: false,
  });
  // La salud cuesta una lectura de histórico por posición (la misma que paga el veto),
  // así que se pide una vez y se guarda diez minutos. No se recalcula al repintar.
  const { data: saludResp } = useQuery({
    queryKey: ["cartera-salud"],
    queryFn: () => api.cartera.salud(),
    staleTime: 600_000,
    retry: false,
  });
  const qc = useQueryClient();
  const [abierta, setAbierta] = React.useState(false);
  const [guardando, setGuardando] = React.useState(false);

  /* Guardar la foto a mano. El bucle del servidor la escribe tras el cierre de Nueva
     York (22:00 UTC), asi que el primer dia habria que esperar a la noche para ver un
     solo punto. Esto NO es una via paralela: llama al MISMO endpoint que el bucle y
     escribe el mismo registro del mismo dia, asi que pulsarlo dos veces no duplica
     nada — sobrescribe. */
  async function guardarFoto() {
    if (guardando) return;
    setGuardando(true);
    try {
      const snap = await api.cartera.guardarFotoHoy();
      qc.invalidateQueries({ queryKey: ["cartera-historico"] });
      qc.invalidateQueries({ queryKey: ["cartera-salud"] });
      toast.success(`Foto de ${snap.dia} guardada: ${fmtEur(snap.valor_eur).replace("+", "")}`);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "No se pudo guardar la foto de hoy");
    } finally {
      setGuardando(false);
    }
  }
  const salud = saludResp?.salud;
  const serieHist = hist?.serie || [];

  const posiciones = React.useMemo(() => {
    const porSymbol = new Map(
      (entries || []).filter((e) => e?.symbol).map((e) => [e.symbol.toUpperCase(), e]));
    return ((resumen?.posiciones) || [])
      .map((p) => {
        const e = porSymbol.get((p.symbol || "").toUpperCase()) || {};
        const precio = num(p.precio_actual);
        const previo = num(p.cierre_anterior);
        return {
          ...p,
          nombre: e.name || "",
          mercado: e.mercado || p.mercado || "",
          sector: e.sector || "Otros",
          riesgo: (e.riesgo || "").toUpperCase(),
          hoyPct: precio && previo ? ((precio - previo) / previo) * 100 : null,
          estado: estadoDe(e, precio),
        };
      })
      .filter((p) => num(p.valor_eur) !== null)
      .sort((a, b) => (b.valor_eur || 0) - (a.valor_eur || 0));
  }, [resumen, entries]);

  const totalValor = posiciones.reduce((s, p) => s + (p.valor_eur || 0), 0);
  const invertido = num(resumen?.invertido_eur);
  const latente = num(resumen?.latente_eur);
  const latentePct = invertido && latente !== null ? (latente / invertido) * 100 : null;

  /* Distribución POR VALOR, no por número de acciones: cien acciones de 2 € pesan
     menos que dos de 500 €, y la tabla de abajo lo contaba por unidades. */
  const sectores = React.useMemo(() => {
    const acum = new Map();
    posiciones.forEach((p) => acum.set(p.sector, (acum.get(p.sector) || 0) + (p.valor_eur || 0)));
    const orden = [...acum.entries()].sort((a, b) => b[1] - a[1]);
    const top = orden.slice(0, N_SECTOR);
    const resto = orden.slice(N_SECTOR).reduce((s, [, v]) => s + v, 0);
    if (resto > 0) top.push(["Otros", resto]);
    return top.map(([n, v], i) => ({
      nombre: n, valor: v,
      pct: totalValor ? (v / totalValor) * 100 : 0,
      color: COLORES[i % COLORES.length],
    }));
  }, [posiciones, totalValor]);

  const concentracion = sectores[0]?.pct ?? 0;

  return (
    <>
      {/* ── Cabecera editorial ──────────────────────────────────────────────── */}
      <div className="iv-veredicto">
        <p className="iv-etiqueta tracking-[0.16em] text-tinta-3 mb-1">
          Gestionar <span className="text-linea-fuerte mx-1">/</span> Capital y riesgo
        </p>
        <div className="flex items-end justify-between gap-6 flex-wrap">
          <div className="min-w-0">
            <h1 className="iv-verbo text-tinta">Cartera</h1>
            <p className="text-cuerpo text-tinta-2 mt-3 max-w-[58ch]">
              Una lectura limpia de tu capital, tus concentraciones y las decisiones pendientes.
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button onClick={onImportar}
                    className="flex items-center gap-1.5 px-3 py-2 border border-linea-fuerte text-apoyo hover:border-marca hover:text-marca transition-colors">
              <ArrowUpRight size={13} /> Importar
            </button>
            <button onClick={onAnadir}
                    className="px-3 py-2 bg-marca text-marca-tinta text-apoyo font-semibold hover:opacity-90 transition-opacity">
              + Añadir posición
            </button>
          </div>
        </div>
      </div>

      {/* ── Estado y acciones de lectura ────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 flex-wrap border-b border-linea pb-3">
        <span className="flex items-center gap-2 iv-etiqueta">
          <span className="w-1.5 h-1.5 rounded-full bg-sube inline-block" />
          Cartera personal
          {resumen?.precio_actualizado && (
            <span className="text-linea-fuerte">· Actualizada {resumen.precio_actualizado}</span>
          )}
        </span>
        <button onClick={onAnalizarCorrelacion}
                className="px-3 py-1.5 border border-linea text-etiqueta hover:border-marca hover:text-marca transition-colors">
          Analizar correlación
        </button>
      </div>

      {/* ── Tres lecturas ───────────────────────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1.2fr)]">
        {/* Patrimonio */}
        <div className="iv-panel p-4">
          <p className="iv-etiqueta mb-3">Patrimonio invertido</p>
          <p className="iv-cifra text-tinta" style={{ fontSize: 30, lineHeight: 1 }}>
            {invertido !== null ? fmtEur(invertido).replace("+", "") : "—"}
          </p>
          <p className={`text-apoyo mt-2 ${latente > 0 ? "text-sube" : latente < 0 ? "text-baja" : "text-tinta-3"}`}>
            {latente !== null ? `${fmtEur(latente)} · ${fmtPct(latentePct)} latente` : "—"}
          </p>
          {/* Evolución. Barras y no una línea: la serie es DIARIA y con pocos puntos
              una línea insinúa una continuidad entre días que no se ha medido. */}
          {serieHist.length >= 2 ? (
            <div className="mt-3 flex items-end gap-[2px] h-10" aria-hidden="true">
              {serieHist.slice(-40).map((d, i, arr) => {
                const vs = arr.map((x) => x.valor_eur);
                const lo = Math.min(...vs), hi = Math.max(...vs);
                const alto = hi > lo ? 15 + ((d.valor_eur - lo) / (hi - lo)) * 85 : 60;
                return (
                  <span key={d.dia} title={`${d.dia}: ${fmtEur(d.valor_eur).replace("+", "")}`}
                        className="flex-1 min-w-[3px]"
                        style={{ height: `${alto}%`,
                                 background: i === arr.length - 1
                                   ? "rgb(var(--iv-sube))" : "rgb(var(--iv-marca) / 0.55)" }} />
                );
              })}
            </div>
          ) : (
            <div className="mt-3">
              <p className="text-etiqueta text-tinta-3 leading-relaxed">
                La evolución empieza a dibujarse hoy: se guarda una foto por día tras el
                cierre. {serieHist.length === 1 ? "Ya hay 1 día." : "Todavía no hay ninguna."}
              </p>
              <button onClick={guardarFoto} disabled={guardando}
                      className="mt-2 px-2.5 py-1 border border-linea-fuerte text-etiqueta hover:border-marca hover:text-marca transition-colors disabled:opacity-50">
                {guardando ? "Guardando…" : "Guardar la foto de hoy"}
              </button>
            </div>
          )}

          <div className="mt-3 pt-3 border-t border-linea space-y-1.5">
            <div className="flex justify-between text-apoyo">
              <span className="text-tinta-3">Valor de mercado</span>
              <span className="iv-cifra">{totalValor ? fmtEur(totalValor).replace("+", "") : "—"}</span>
            </div>
            <div className="flex justify-between text-apoyo">
              <span className="text-tinta-3">Ya cobrado al vender</span>
              <span className={`iv-cifra ${resumen?.realizado_eur > 0 ? "text-sube" : ""}`}>
                {num(resumen?.realizado_eur) !== null ? fmtEur(resumen.realizado_eur) : "—"}
              </span>
            </div>
          </div>
        </div>

        {/* Índice de salud · SIEMPRE con sus componentes detrás */}
        <div className="iv-panel p-4">
          <div className="flex items-center justify-between gap-2 mb-3">
            <p className="iv-etiqueta">Salud de cartera</p>
            {salud?.etiqueta && (
              <span className="iv-etiqueta border border-linea-fuerte px-2 py-0.5">{salud.etiqueta}</span>
            )}
          </div>
          {salud?.puntuacion == null ? (
            <p className="text-apoyo text-tinta-3">
              Todavía no hay nada que medir: hacen falta posiciones valoradas.
            </p>
          ) : (
            <>
              <div className="flex items-baseline gap-2">
                <span className="font-heading text-tinta" style={{ fontSize: 38, lineHeight: 1 }}>
                  {salud.puntuacion}
                </span>
                <span className="iv-etiqueta text-tinta-3">/ 100</span>
              </div>
              {/* El número SIEMPRE se puede abrir. Un compuesto que no se desglosa es
                  una métrica inventada con otro nombre: nadie sabría si baja por
                  concentración o por estructura. */}
              <button onClick={() => setAbierta((v) => !v)}
                      aria-expanded={abierta}
                      className="mt-2 text-etiqueta text-marca hover:underline flex items-center gap-1">
                {abierta ? "Ocultar" : "De dónde sale"}
                <CaretRight size={10} className={abierta ? "rotate-90 transition-transform" : "transition-transform"} />
              </button>
              <div className={`mt-3 space-y-2.5 ${abierta ? "" : "hidden"}`}>
                {(salud.componentes || []).map((c) => (
                  <div key={c.clave}>
                    <div className="flex justify-between items-baseline text-apoyo gap-2">
                      <span className={c.medible ? "text-tinta-2" : "text-tinta-3"}>
                        {c.nombre}
                        <span className="iv-etiqueta ml-1.5 text-linea-fuerte">{c.peso_efectivo || 0} %</span>
                      </span>
                      <span className={`iv-cifra shrink-0 ${!c.medible ? "text-tinta-3" : ""}`}>
                        {c.medible ? `${Math.round(c.valor)} ${c.unidad}` : "sin medir"}
                      </span>
                    </div>
                    {c.medible && (
                      <Barra pct={c.nota} ancho="w-full"
                             color={c.nota >= 70 ? "rgb(var(--iv-sube))"
                               : c.nota >= 40 ? "rgb(var(--iv-aviso))" : "rgb(var(--iv-baja))"} />
                    )}
                    <p className="text-etiqueta text-tinta-3 mt-1 leading-snug">{c.explica}</p>
                  </div>
                ))}
                {salud.medidos < salud.de && (
                  <p className="text-etiqueta text-tinta-3 border-t border-linea pt-2">
                    Se han podido medir {salud.medidos} de {salud.de}. Lo que no se mide no
                    puntúa cero: sale del reparto, y los pesos de arriba son los aplicados.
                  </p>
                )}
              </div>
            </>
          )}
        </div>

        {/* Distribución por VALOR */}
        <div className="iv-panel p-4">
          <p className="iv-etiqueta mb-3">Distribución por valor</p>
          <div className="flex h-2 overflow-hidden mb-3">
            {sectores.map((s) => (
              <span key={s.nombre} style={{ width: `${s.pct}%`, background: s.color }}
                    title={`${s.nombre} ${s.pct.toFixed(0)} %`} />
            ))}
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            {sectores.map((s) => (
              <div key={s.nombre} className="flex items-center justify-between gap-2 text-apoyo min-w-0">
                <span className="flex items-center gap-1.5 min-w-0">
                  <span className="w-2 h-2 shrink-0" style={{ background: s.color }} />
                  <span className="truncate text-tinta-2">{s.nombre}</span>
                </span>
                <span className="iv-cifra shrink-0">{s.pct.toFixed(0)} %</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Lo que merece atención ──────────────────────────────────────────── */}
      {concentracion > 35 && (
        <div className="aviso flex items-start gap-3">
          <Warning size={15} weight="fill" className="text-aviso shrink-0 mt-0.5" />
          <div className="min-w-0">
            <b>Una concentración merece tu atención.</b>{" "}
            <span className="text-tinta-2">
              {sectores[0].nombre} representa el {concentracion.toFixed(0)} % de tu cartera por valor.
              Una sola caída sectorial te alcanzaría a esa parte entera.
            </span>
          </div>
          <button onClick={onAnalizarCorrelacion}
                  className="ml-auto shrink-0 text-etiqueta text-marca hover:underline flex items-center gap-1">
            Ver análisis <CaretRight size={11} />
          </button>
        </div>
      )}

      {/* ── Posiciones, para LEER ───────────────────────────────────────────── */}
      <div>
        <div className="iv-seccion iv-seccion-acento">
          <span className="iv-etiqueta tracking-[0.18em] text-tinta-2">
            Posiciones · {posiciones.length} {posiciones.length === 1 ? "activa" : "activas"}
          </span>
          <span className="text-etiqueta text-tinta-3 whitespace-nowrap hidden sm:inline">
            Revisa peso, riesgo y estado antes de decidir
          </span>
        </div>
        {posiciones.length === 0 ? (
          <div className="border border-dashed border-linea-fuerte p-8 text-center">
            <p className="text-cuerpo text-tinta">Todavía no hay posiciones valoradas.</p>
            <p className="text-apoyo text-tinta-3 mt-1 max-w-[46ch] mx-auto">
              En cuanto una acción tenga precio de compra y cotización, aparecerá aquí con su
              peso y su resultado.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto border border-linea">
            <table className="w-full text-apoyo" style={{ minWidth: 780 }}>
              <thead>
                <tr>
                  {["Activo", "Precio", "Hoy", "P&L", "Peso", "Riesgo", "Estado"].map((h, i) => (
                    <th key={h} className={`px-3 py-2.5 iv-etiqueta bg-superficie-alt border-b border-linea whitespace-nowrap ${
                      i >= 1 && i <= 3 ? "text-right" : "text-left"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {posiciones.map((p) => {
                  const peso = totalValor ? (p.valor_eur / totalValor) * 100 : 0;
                  return (
                    <tr key={p.symbol} className="border-b border-linea last:border-b-0 hover:bg-superficie-alt transition-colors">
                      <td className="px-3 py-3">
                        <span className="font-mono font-semibold text-tinta">{p.symbol}</span>
                        <div className="text-etiqueta text-tinta-3 truncate max-w-[190px]">
                          {[p.nombre, p.mercado].filter(Boolean).join(" · ")}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right iv-cifra whitespace-nowrap">
                        {num(p.precio_actual) !== null ? p.precio_actual.toFixed(2) : "—"}
                      </td>
                      <td className={`px-3 py-3 text-right iv-cifra whitespace-nowrap ${
                        p.hoyPct > 0 ? "text-sube" : p.hoyPct < 0 ? "text-baja" : "text-tinta-3"}`}>
                        {p.hoyPct !== null ? fmtPct(p.hoyPct) : "—"}
                      </td>
                      <td className={`px-3 py-3 text-right iv-cifra whitespace-nowrap ${
                        p.latente_eur > 0 ? "text-sube" : p.latente_eur < 0 ? "text-baja" : "text-tinta-3"}`}>
                        {num(p.latente_eur) !== null ? fmtEur(p.latente_eur) : "—"}
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <Barra pct={peso} />
                        <span className="iv-cifra text-tinta-3 ml-2">{peso.toFixed(0)} %</span>
                      </td>
                      <td className={`px-3 py-3 iv-etiqueta ${RIESGO_TONO[p.riesgo] || "text-tinta-3"}`}>
                        {p.riesgo || "—"}
                      </td>
                      <td className={`px-3 py-3 whitespace-nowrap ${p.estado.tono}`}>
                        {p.estado.txt}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
