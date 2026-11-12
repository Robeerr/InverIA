import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle, ChartPie, ChevronRight, GitCompareArrows, HeartPulse, Minus, Plus, Search,
  TrendingDown, TrendingUp, Upload, Wallet,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { fmtEur, fmtPct } from "../lib/format";
import { leerComoBroker } from "../lib/preferencias";
import { cifrasResumen, datosPosicion } from "../lib/operaciones";
import { estadoPosicion } from "../lib/cartera";
import { cn } from "@/lib/utils";
import Boton from "./base/Boton";
import Monograma from "./base/Monograma";
import CabeceraBloque from "./base/CabeceraBloque";
import Segmentado from "./base/Segmentado";

/* Cabecera de Cartera · la lectura antes del detalle
   ─────────────────────────────────────────────────────────────────────────────
   La tabla de abajo es para EDITAR: quince columnas, niveles, campanas, celdas que
   se escriben. Esto es para LEER, y son dos trabajos distintos. Antes solo existía
   el segundo, así que para saber cuánto tienes invertido había que sumar mentalmente
   una tabla pensada para otra cosa.

   COMPOSICIÓN (v2)

     1. Titular de pantalla y acciones.
     2. Una sola pieza héroe a lo ancho: el patrimonio invertido como cifra grande,
        su evolución debajo y, a la derecha, el desglose en columna tabular.
     3. Una fila de RIESGO: salud, distribución (con el aviso de concentración
        dentro, junto al dato que lo provoca) y la correlación que pasa la página.
     4. Las posiciones para leer, ancladas por su monograma.

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

/* Paleta CATEGÓRICA de sectores. Un sector no tiene papel —no sube, no baja, no
   avisa—, solo hay que distinguirlo del de al lado. Por eso son valores fijos y, con
   el sistema «grafito e índigo», tonos medios fríos que NO se confunden con los tres
   colores que sí significan algo: ni verde, ni rojo, ni el índigo de la intención. */
const COLORES = ["#6ea8fe", "#c9a26b", "#b48cf2", "#4fc3cf", "#e389b9", "#9fa8c9", "#7c8296"];

const num = (v) => (typeof v === "number" && isFinite(v) ? v : null);

const RIESGO_TONO = { BAJO: "text-sube", MEDIO: "text-aviso", ALTO: "text-baja" };
const RIESGO_TXT = { BAJO: "Bajo", MEDIO: "Medio", ALTO: "Alto" };

const TRANS = "transition-colors duration-150 ease-salida motion-reduce:transition-none";

/** Tono de la nota de salud, el mismo umbral que las barras de componentes. */
const tonoNota = (n) => (n >= 70 ? "text-sube" : n >= 40 ? "text-aviso" : "text-baja");
const FONDO_NOTA = { "text-sube": "bg-sube/10", "text-aviso": "bg-aviso/10", "text-baja": "bg-baja/10" };
const colorNota =(n) => (n >= 70 ? "rgb(var(--iv-sube))" : n >= 40 ? "rgb(var(--iv-aviso))" : "rgb(var(--iv-baja))");

/** Barra de peso: la misma pieza para la tabla y para la distribución.
 *
 * La PISTA va visible (luz baja) y no del color del panel: una nota de 0 —concentración
 * alta, por ejemplo— salía como un hueco y se leía como un fallo de dibujo en vez de
 * como un cero. Con la pista visible, vacío significa vacío.
 */
function Barra({ pct, color, ancho = "w-16", alto = "h-1" }) {
  return (
    <span className={`inline-block ${ancho} ${alto} rounded-full bg-tinta/[0.08] align-middle overflow-hidden`}>
      <span className="block h-full rounded-full" style={{ width: `${Math.min(100, Math.max(0, pct))}%`,
                                              background: color || "rgb(var(--iv-intencion) / 0.75)" }} />
    </span>
  );
}

/** «22.210,91 €» → «22.210» grande, «,91» y «€» reducidos. Mismo texto de `fmtEur`,
 *  partido solo para pintarlo: los céntimos y el símbolo a tamaño héroe pesaban como
 *  tres dígitos más y no cambian ninguna decisión. */
function CifraHeroe({ valor }) {
  if (valor === null) return "—";
  const t = fmtEur(valor).replace("+", "");
  const m = t.match(/^(.*?)(,\d+)?(\s?€)$/);
  if (!m) return t;
  return (
    <>
      {m[1]}
      {m[2] && <span className="text-[0.5em] text-tinta-2 tracking-[-0.02em]">{m[2]}</span>}
      <span className="text-[0.42em] font-medium text-tinta-3 ml-[0.18em] tracking-normal align-[0.78em]">€</span>
    </>
  );
}

/** Fila del desglose: rótulo a la izquierda, cifra en columna derecha tabular. */
function Fila({ etiqueta, children, tono = "text-tinta", ayuda }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 py-2.5">
      <dt className="text-[13px] text-tinta-2" title={ayuda}>{etiqueta}</dt>
      <dd className={cn("iv-cifra text-[14px] font-medium ml-auto text-right", tono)}>{children}</dd>
    </div>
  );
}

/** Estado de la posición: punto + texto en su tono. El punto hace de ancla en la
 *  columna; el texto no cambia. */
function EstadoTxt({ estado }) {
  return (
    <span className={cn("inline-flex items-center gap-2", estado.tono)} title={estado.ayuda || undefined}>
      <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" aria-hidden="true" />
      <span className="truncate">{estado.txt}</span>
    </span>
  );
}

export default function CarteraCabecera({ entries = [], onAnalizarCorrelacion, onAnadir, onImportar, correlacion = null }) {
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
  const navegar = useNavigate();
  const [abierta, setAbierta] = React.useState(false);
  const [guardando, setGuardando] = React.useState(false);
  const [busca, setBusca] = React.useState("");
  const [riesgoFiltro, setRiesgoFiltro] = React.useState("Todas");
  const [rango, setRango] = React.useState("Todo");

  /* Guardar la foto a mano. El servidor ya la escribe solo al arrancar y cada media
     hora, asi que esto es para cuando NO quieres esperar: acabas de comprar y quieres
     que el punto de hoy recoja ya la posicion nueva.

     No es una via paralela: llama al MISMO endpoint que el bucle y escribe el mismo
     registro del mismo dia, asi que sobrescribe en vez de duplicar. */
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
  /* Rango del gráfico. Los días son de MERCADO, no naturales: la serie solo guarda
     días de bolsa, así que «1M» son 22 puntos y no 30. Contar naturales dejaría un
     mes corto de cinco sesiones. */
  const DIAS = { "1M": 22, "3M": 66, "1A": 252, Todo: Infinity };
  const serieCompleta = hist?.serie || [];
  const serieHist = React.useMemo(() => {
    const n = DIAS[rango] ?? Infinity;
    return n === Infinity ? serieCompleta : serieCompleta.slice(-n);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serieCompleta, rango]);

  // Las tres cifras en el método del interruptor «Como en DEGIRO», como Hoy y Operaciones.
  // Antes esta cabecera leía siempre el método de gestión y no cuadraba con las otras dos.
  const [comoBroker] = React.useState(leerComoBroker);
  // Tendencia por símbolo: la calcula el servidor con la salud de la cartera (la misma
  // lectura que paga el veto). Sin ella la columna Estado salía «Sin datos» en todo.
  const tendencias = saludResp?.tendencias;
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
          // P&L de la fila en el método del interruptor. Antes se leía `latente_eur`,
          // un campo que las posiciones no traen, y la columna salía «—» entera.
          pnl: num(datosPosicion(p, comoBroker).g?.pnl_eur),
          estado: estadoPosicion(e, precio, tendencias?.[(p.symbol || "").toUpperCase()]),
        };
      })
      .filter((p) => num(p.valor_eur) !== null)
      .sort((a, b) => (b.valor_eur || 0) - (a.valor_eur || 0));
  }, [resumen, entries, tendencias, comoBroker]);

  const totalValor = posiciones.reduce((s, p) => s + (p.valor_eur || 0), 0);
  const cifras = cifrasResumen(resumen, comoBroker);
  const invertido = num(cifras.invertido);
  const latente = num(cifras.latente);
  const latentePct = invertido && latente !== null ? (latente / invertido) * 100 : null;
  const signo = latente > 0 ? "sube" : latente < 0 ? "baja" : "neutro";
  const Flecha = signo === "sube" ? TrendingUp : signo === "baja" ? TrendingDown : Minus;

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

  /* Lo que se pinta en la tabla tras buscador y filtro. Los totales de arriba
     —patrimonio, distribución, concentración— siguen saliendo de TODAS las
     posiciones: filtrar la vista no cambia lo que tienes. */
  const visibles = React.useMemo(() => {
    const q = busca.trim().toLowerCase();
    return posiciones.filter((p) => {
      if (riesgoFiltro !== "Todas" && p.riesgo !== riesgoFiltro) return false;
      if (!q) return true;
      return `${p.symbol} ${p.nombre}`.toLowerCase().includes(q);
    });
  }, [posiciones, busca, riesgoFiltro]);

  // Barras del gráfico: las mismas 40 últimas de siempre, con su escala.
  const barras = serieHist.slice(-40);
  const vs = barras.map((x) => x.valor_eur);
  const lo = Math.min(...vs), hi = Math.max(...vs);

  return (
    <>
      {/* ── Titular ─────────────────────────────────────────────────────────── */}
      <header className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-x-8 gap-y-5">
        <div className="min-w-0">
          <p className="text-[13px] text-tinta-3 flex items-center gap-1.5">
            Gestionar <ChevronRight className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" /> Capital y riesgo
          </p>
          <h1 className="iv-verbo text-tinta mt-2">Cartera</h1>
          <p className="text-[14.5px] text-tinta-2 mt-2.5 max-w-[58ch] leading-relaxed">
            Una lectura limpia de tu capital, tus concentraciones y las decisiones pendientes.
          </p>
          <p className="mt-3 flex items-center gap-2 text-[12.5px] text-tinta-3 flex-wrap">
            <span className="relative flex w-2 h-2 shrink-0" aria-hidden="true">
              <span className="absolute inset-0 rounded-full bg-sube/40 animate-ping motion-reduce:animate-none" />
              <span className="relative w-2 h-2 rounded-full bg-sube" />
            </span>
            Cartera personal
            {resumen?.precio_actualizado && (
              <span>· Actualizada <span className="iv-cifra">{resumen.precio_actualizado}</span></span>
            )}
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {/* En el teléfono el atajo queda en icono: los tres rótulos no caben en una fila. */}
          <Boton variante="fantasma" onClick={onAnalizarCorrelacion} aria-label="Analizar correlación"
                 title="Analizar correlación" className="px-2.5 sm:px-3.5">
            <GitCompareArrows className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" />
            <span className="hidden sm:inline">Analizar correlación</span>
          </Boton>
          <Boton variante="secundario" onClick={onImportar}>
            <Upload className="w-4 h-4" strokeWidth={1.75} aria-hidden="true" /> Importar
          </Boton>
          <Boton onClick={onAnadir}>
            <Plus className="w-4 h-4" strokeWidth={2} aria-hidden="true" /> Añadir posición
          </Boton>
        </div>
      </header>

      {/* ── Héroe · patrimonio ──────────────────────────────────────────────── */}
      <section className="iv-panel relative overflow-hidden" aria-labelledby="cartera-patrimonio">
        {/* Luz de esquina, muy baja: profundidad para la pieza principal sin teñirla. */}
        <span aria-hidden="true"
              className="pointer-events-none absolute -top-32 -left-24 w-[520px] h-[300px] rounded-full bg-marca/[0.09] blur-3xl" />
        <div className="relative grid lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="p-5 sm:p-7 min-w-0">
            <CabeceraBloque icono={Wallet} como="h2" id="cartera-patrimonio">Patrimonio invertido</CabeceraBloque>
            {/* El tamaño se ajusta al ancho para que siete cifras quepan sin desbordar. */}
            <p className="iv-cifra-hero text-[clamp(40px,11vw,64px)] lg:text-[clamp(44px,4.4vw,64px)] mt-4 break-words">
              <CifraHeroe valor={invertido} />
            </p>
            <p className="mt-4 flex flex-wrap items-center gap-2">
              <span className={cn("iv-cifra inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[13px] font-medium",
                                  signo === "sube" ? "bg-sube/10 text-sube"
                                    : signo === "baja" ? "bg-baja/10 text-baja" : "bg-tinta/5 text-tinta-3")}>
                <Flecha className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" />
                {latente !== null ? <>{fmtEur(latente)} · {fmtPct(latentePct)}</> : "—"}
              </span>
              <span className="text-[13px] text-tinta-3">latente</span>
            </p>

            {/* Evolución. Barras y no una línea: la serie es DIARIA y con pocos puntos
                una línea insinúa una continuidad entre días que no se ha medido. */}
            <div className="mt-7">
              <div className="flex items-center justify-between gap-3 mb-3">
                <p className="text-[12.5px] font-medium text-tinta-3">Evolución del valor</p>
                {serieHist.length >= 2 && (
                  <Segmentado opciones={["1M", "3M", "1A", "Todo"]} valor={rango} onCambio={setRango}
                              etiqueta="Rango del gráfico" mono tamano="sm"
                              disabled={serieCompleta.length < 2} />
                )}
              </div>
              {serieHist.length >= 2 ? (
                <div className="relative flex items-end gap-[3px] h-24 sm:h-28" aria-hidden="true">
                  {/* Guías horizontales muy tenues: dan escala sin competir con las barras. */}
                  <span className="absolute inset-x-0 top-0 border-t border-dashed border-suave" />
                  <span className="absolute inset-x-0 top-1/2 border-t border-dashed border-suave" />
                  {barras.map((d, i, arr) => {
                    const alto = hi > lo ? 15 + ((d.valor_eur - lo) / (hi - lo)) * 85 : 60;
                    const ultimo = i === arr.length - 1;
                    return (
                      <span key={d.dia} title={`${d.dia}: ${fmtEur(d.valor_eur).replace("+", "")}`}
                            className={cn("relative flex-1 min-w-[3px] rounded-t-[3px] transition-[background-color] duration-150",
                                          ultimo ? "bg-marca" : "bg-marca/30 hover:bg-marca/60")}
                            style={{ height: `${alto}%` }} />
                    );
                  })}
                </div>
              ) : (
                <div className="rounded-iv border border-dashed border-medio px-4 py-5">
                  <p className="text-[13px] text-tinta-3 leading-relaxed max-w-[60ch]">
                    {serieHist.length === 1
                      ? "Ya hay una foto guardada. El gráfico aparece con la segunda: con un solo punto no hay nada que unir."
                      : "La evolución empieza hoy. El servidor guarda una foto por día de mercado; aún no hay ninguna."}
                  </p>
                  <Boton variante="secundario" tamano="sm" className="mt-3" onClick={guardarFoto} ocupado={guardando}>
                    {guardando ? "Guardando…" : "Guardar la foto de hoy"}
                  </Boton>
                </div>
              )}
            </div>
          </div>

          {/* Desglose */}
          <div className="relative p-5 sm:p-7 border-t lg:border-t-0 lg:border-l border-suave bg-tinta/[0.015] flex flex-col">
            <p className="text-[12.5px] font-medium text-tinta-3">Desglose</p>
            <dl className="mt-2 [&>div+div]:border-t [&>div+div]:border-suave">
              <Fila etiqueta="Valor de mercado">{totalValor ? fmtEur(totalValor).replace("+", "") : "—"}</Fila>
              <Fila etiqueta="Latente" tono={signo === "sube" ? "text-sube" : signo === "baja" ? "text-baja" : "text-tinta"}>
                {latente !== null ? fmtEur(latente) : "—"}
              </Fila>
              <Fila etiqueta="Ya cobrado al vender" tono={cifras.realizado > 0 ? "text-sube" : "text-tinta"}>
                {num(cifras.realizado) !== null ? fmtEur(cifras.realizado) : "—"}
              </Fila>
              <Fila etiqueta="Posiciones abiertas">{posiciones.length}</Fila>
            </dl>
            {cifras.metodo && (
              <p className="text-[12px] text-tinta-3 mt-auto pt-3" title="Cambia con el interruptor «Como en DEGIRO» de Operaciones">
                Cifras {cifras.metodo}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ── Riesgo · salud, distribución, correlación ───────────────────────── */}
      <div className={cn("grid gap-4 sm:gap-5 items-start", correlacion ? "lg:grid-cols-3" : "lg:grid-cols-2")}>
        {/* Índice de salud · SIEMPRE con sus componentes detrás */}
        <section className="iv-panel p-5 sm:p-6 min-w-0" aria-labelledby="cartera-salud">
          <CabeceraBloque icono={HeartPulse} como="h2" id="cartera-salud"
                          derecha={salud?.etiqueta && (
                            <span className={cn("text-[12px] font-medium px-2 h-[22px] inline-flex items-center rounded-md",
                                                salud?.puntuacion != null
                                                  ? `${tonoNota(salud.puntuacion)} ${FONDO_NOTA[tonoNota(salud.puntuacion)]}`
                                                  : "text-tinta-2 bg-tinta/[0.06]")}>
                              {salud.etiqueta}
                            </span>
                          )}>
            Salud de cartera
          </CabeceraBloque>
          {salud?.puntuacion == null ? (
            <p className="text-[13px] text-tinta-3 mt-4">
              Todavía no hay nada que medir: hacen falta posiciones valoradas.
            </p>
          ) : (
            <>
              <div className="flex items-baseline gap-2 mt-4">
                <span className={cn("iv-cifra-hero text-[44px]", tonoNota(salud.puntuacion))}>
                  {salud.puntuacion}
                </span>
                <span className="iv-cifra text-[13px] text-tinta-3">/ 100</span>
              </div>
              {/* Medidor en 20 marcas: la nota se lee como «cuánto falta» de un vistazo. */}
              <div className="flex gap-[3px] mt-3" aria-hidden="true">
                {Array.from({ length: 20 }, (_, i) => (
                  <span key={i} className="flex-1 h-1.5 rounded-[2px]"
                        style={{ background: (i + 0.5) * 5 <= salud.puntuacion
                          ? colorNota(salud.puntuacion) : "rgb(var(--iv-tinta) / 0.08)" }} />
                ))}
              </div>
              {/* Los componentes se ven SIEMPRE: un índice cuyo desglose hay que
                  desplegar sigue siendo un número opaco de un vistazo. Lo que se
                  pliega es la EXPLICACIÓN de cada uno, que es lo que ocupa. */}
              <div className="mt-5 pt-4 border-t border-suave space-y-3.5">
                {(salud.componentes || []).map((c) => (
                  <div key={c.clave}>
                    <div className="flex justify-between items-baseline text-[13px] gap-2 mb-1.5">
                      <span className={c.medible ? "text-tinta-2" : "text-tinta-3"}>
                        {c.nombre}
                        <span className="iv-cifra text-[11.5px] ml-1.5 text-tinta-3" title="Peso aplicado en el índice">{c.peso_efectivo || 0} %</span>
                      </span>
                      <span className={cn("iv-cifra shrink-0", c.medible ? "text-tinta" : "text-tinta-3")}>
                        {c.medible ? `${Math.round(c.valor)} ${c.unidad}` : "sin medir"}
                      </span>
                    </div>
                    {c.medible && <Barra pct={c.nota} ancho="w-full" color={colorNota(c.nota)} />}
                    {abierta && (
                      <p className="text-[12px] text-tinta-3 mt-1.5 leading-snug">{c.explica}</p>
                    )}
                  </div>
                ))}
                {abierta && salud.medidos < salud.de && (
                  <p className="text-[12px] text-tinta-3 border-t border-suave pt-3 leading-snug">
                    Se han podido medir {salud.medidos} de {salud.de}. Lo que no se mide no
                    puntúa cero: sale del reparto, y los pesos de arriba son los aplicados.
                  </p>
                )}
              </div>
              {/* El número SIEMPRE se puede abrir. Un compuesto que no se desglosa es
                  una métrica inventada con otro nombre. */}
              <button onClick={() => setAbierta((v) => !v)} aria-expanded={abierta}
                      className={cn("mt-4 min-h-[32px] text-[13px] font-medium text-marca hover:text-tinta flex items-center gap-1", TRANS)}>
                {abierta ? "Ocultar el porqué" : "Qué significa cada uno"}
                <ChevronRight className={cn("w-3.5 h-3.5 transition-transform duration-200 ease-salida motion-reduce:transition-none",
                                            abierta && "rotate-90")} strokeWidth={2} aria-hidden="true" />
              </button>
            </>
          )}
        </section>

        {/* Distribución por VALOR, con el aviso de concentración junto a su causa */}
        <section className="iv-panel p-5 sm:p-6 min-w-0" aria-labelledby="cartera-distribucion">
          <CabeceraBloque icono={ChartPie} como="h2" id="cartera-distribucion"
                          derecha={sectores[0] && (
                            <span className="iv-cifra text-[12px] text-tinta-3">{sectores.length} sectores</span>
                          )}>
            Distribución por valor
          </CabeceraBloque>
          {sectores[0] && (
            <div className="mt-4">
              <p className="text-[12.5px] text-tinta-3">Mayor peso</p>
              <p className="flex items-baseline gap-2 mt-1 min-w-0">
                <span className="iv-cifra-hero text-[44px] shrink-0">{concentracion.toFixed(0)}<span className="text-[0.5em] text-tinta-3 ml-0.5">%</span></span>
                <span className="text-[14px] text-tinta-2 truncate" title={sectores[0].nombre}>{sectores[0].nombre}</span>
              </p>
            </div>
          )}
          <div className="flex h-2.5 rounded-full overflow-hidden mt-4 gap-[2px]" aria-hidden="true">
            {sectores.map((s) => (
              <span key={s.nombre} className="first:rounded-l-full last:rounded-r-full"
                    style={{ width: `${s.pct}%`, background: s.color }}
                    title={`${s.nombre} ${s.pct.toFixed(0)} %`} />
            ))}
          </div>
          {/* Una sola columna en lista: los nombres de sector (Communication Services…)
              no caben en media columna sin cortarse, y así los % quedan en vertical. */}
          <ul className="mt-4 pt-1 border-t border-suave">
            {sectores.map((s) => (
              <li key={s.nombre} className="flex items-center justify-between gap-3 py-2 text-[13px] min-w-0 border-b border-suave last:border-b-0">
                <span className="flex items-center gap-2.5 min-w-0">
                  <span className="w-2 h-2 rounded-[3px] shrink-0" style={{ background: s.color }} aria-hidden="true" />
                  <span className="truncate text-tinta-2" title={s.nombre}>{s.nombre}</span>
                </span>
                <span className="flex items-baseline gap-3 shrink-0">
                  <span className="iv-cifra text-[12px] text-tinta-3 hidden sm:inline">{fmtEur(s.valor, 0)}</span>
                  <span className="iv-cifra font-medium text-tinta w-11 text-right">{s.pct.toFixed(0)} %</span>
                </span>
              </li>
            ))}
          </ul>

          {/* ── Lo que merece atención: junto al dato que lo provoca ── */}
          {concentracion > 35 && (
            <div role="note" className="mt-4 rounded-iv bg-aviso/[0.07] border border-aviso/25 px-3.5 py-3 text-[13px]">
              <p className="flex items-start gap-2.5 leading-relaxed">
                <AlertTriangle className="w-4 h-4 text-aviso shrink-0 mt-0.5" strokeWidth={2} aria-hidden="true" />
                <span>
                  <b className="text-tinta font-semibold">Una concentración merece tu atención.</b>{" "}
                  <span className="text-tinta-2">
                    {sectores[0].nombre} representa el {concentracion.toFixed(0)} % de tu cartera por valor.
                    Una sola caída sectorial te alcanzaría a esa parte entera.
                  </span>
                </span>
              </p>
              <button onClick={onAnalizarCorrelacion}
                      className={cn("ml-[26px] mt-1 min-h-[28px] text-[13px] font-medium text-marca hover:text-tinta inline-flex items-center gap-1", TRANS)}>
                Ver análisis <ChevronRight className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" />
              </button>
            </div>
          )}
        </section>

        {correlacion}
      </div>

      {/* ── Posiciones, para LEER ───────────────────────────────────────────── */}
      <section aria-labelledby="cartera-posiciones">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-4">
          <div className="min-w-0">
            <h2 id="cartera-posiciones" className="text-[18px] font-semibold tracking-[-0.02em] text-tinta flex items-center gap-2.5">
              Posiciones
              <span className="iv-cifra text-[12px] font-medium text-tinta-2 h-[22px] px-2 inline-flex items-center rounded-md bg-tinta/[0.06]">
                {posiciones.length} {posiciones.length === 1 ? "activa" : "activas"}
              </span>
            </h2>
            <p className="text-[13px] text-tinta-3 mt-1">Revisa peso, riesgo y estado antes de decidir</p>
          </div>
          {/* Buscador y filtro por riesgo. Con once posiciones la tabla ya no se
              abarca de un vistazo, y el riesgo es el corte que de verdad se usa:
              «enséñame solo lo que tengo marcado como ALTO». */}
          {posiciones.length > 3 && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <label className="relative w-full sm:w-auto">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-tinta-3 pointer-events-none" strokeWidth={1.75} aria-hidden="true" />
                <input
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                  placeholder="Buscar activo"
                  aria-label="Buscar activo en tus posiciones"
                  className={cn("h-9 pl-9 pr-3 rounded-[10px] bg-tinta/[0.04] border border-suave text-[13px] text-tinta w-full sm:w-56",
                                "placeholder:text-tinta-3 hover:border-medio focus:border-marca/60 focus:bg-superficie outline-none", TRANS)}
                />
              </label>
              <Segmentado
                opciones={["Todas", "BAJO", "MEDIO", "ALTO"].map((r) => ({ valor: r, etiqueta: r === "Todas" ? "Todas" : RIESGO_TXT[r] }))}
                valor={riesgoFiltro} onCambio={setRiesgoFiltro} etiqueta="Filtrar por riesgo" className="self-start sm:self-auto" />
            </div>
          )}
        </div>

        {visibles.length === 0 ? (
          <div className="rounded-iv-lg border border-dashed border-medio p-10 text-center">
            {posiciones.length === 0 ? (
              <>
                <p className="text-[14.5px] text-tinta font-medium">Todavía no hay posiciones valoradas.</p>
                <p className="text-[13px] text-tinta-3 mt-1.5 max-w-[46ch] mx-auto">
                  En cuanto una acción tenga precio de compra y cotización, aparecerá aquí
                  con su peso y su resultado.
                </p>
              </>
            ) : (
              <>
                <p className="text-[14.5px] text-tinta font-medium">Ninguna posición encaja con ese filtro.</p>
                <Boton variante="secundario" tamano="sm" className="mt-3"
                       onClick={() => { setBusca(""); setRiesgoFiltro("Todas"); }}>
                  Ver todas
                </Boton>
              </>
            )}
          </div>
        ) : (
          <>
          {/* MÓVIL · lista. Monograma a la izquierda para que el ojo baje por la
              columna; lo que decide (P&L) arriba a la derecha y el resto debajo. */}
          <ul className="md:hidden iv-panel overflow-hidden">
            {visibles.map((p) => {
              const peso = totalValor ? (p.valor_eur / totalValor) * 100 : 0;
              return (
                <li key={p.symbol} className="border-b border-suave last:border-b-0">
                  <Link to={`/accion/${p.symbol}`}
                        className={cn("flex gap-3 px-4 py-3.5 active:bg-tinta/[0.04]", TRANS)}>
                    <Monograma symbol={p.symbol} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-[14.5px] font-semibold text-tinta">{p.symbol}</span>
                        <span className={cn("iv-cifra text-[14px] font-medium shrink-0",
                                            p.pnl > 0 ? "text-sube" : p.pnl < 0 ? "text-baja" : "text-tinta-3")}>
                          {p.pnl !== null ? fmtEur(p.pnl) : "—"}
                        </span>
                      </div>
                      <div className="flex items-baseline justify-between gap-3 mt-0.5">
                        <span className="text-[12.5px] text-tinta-3 truncate">
                          {[p.nombre, p.mercado].filter(Boolean).join(" · ")}
                        </span>
                        <span className="iv-cifra text-[12.5px] shrink-0">
                          <span className="text-tinta-2">{num(p.precio_actual) !== null ? p.precio_actual.toFixed(2) : "—"}</span>{" "}
                          <span className={p.hoyPct > 0 ? "text-sube" : p.hoyPct < 0 ? "text-baja" : "text-tinta-3"}>
                            {p.hoyPct !== null ? fmtPct(p.hoyPct) : "—"}
                          </span>
                        </span>
                      </div>
                      <div className="mt-2.5 flex items-center gap-3 text-[12px]">
                        <span className="flex items-center gap-1.5">
                          <Barra pct={peso} ancho="w-12" />
                          <span className="iv-cifra text-tinta-3">{peso.toFixed(0)} %</span>
                        </span>
                        <span className={cn("font-medium", RIESGO_TONO[p.riesgo] || "text-tinta-3")}>{RIESGO_TXT[p.riesgo] || p.riesgo || "—"}</span>
                        <span className="ml-auto min-w-0"><EstadoTxt estado={p.estado} /></span>
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>

          {/* ESCRITORIO · tabla */}
          <div className="hidden md:block iv-panel overflow-x-auto">
            <table className="w-full text-[13px]" style={{ minWidth: 820 }}>
              <thead>
                <tr className="text-left">
                  {["Activo", "Precio", "Hoy", "P&L", "Peso", "Riesgo", "Estado"].map((h, i) => (
                    <th key={h} scope="col" className={cn("px-4 first:pl-5 h-11 text-[12px] font-medium text-tinta-3 border-b border-suave whitespace-nowrap",
                                                         i >= 1 && i <= 3 ? "text-right" : "text-left")}>{h}</th>
                  ))}
                  <th className="border-b border-suave w-10"><span className="sr-only">Abrir</span></th>
                </tr>
              </thead>
              <tbody>
                {visibles.map((p) => {
                  const peso = totalValor ? (p.valor_eur / totalValor) * 100 : 0;
                  return (
                    <tr key={p.symbol}
                        onClick={() => navegar(`/accion/${p.symbol}`)}
                        className={cn("group border-b border-suave last:border-b-0 hover:bg-tinta/[0.025] cursor-pointer", TRANS)}>
                      <td className="pl-5 pr-4 py-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <Monograma symbol={p.symbol} tamano="sm" />
                          <div className="min-w-0">
                            {/* El símbolo es un enlace real: la fila entera se pulsa con el
                                ratón, y con el teclado se llega aquí con Tab. */}
                            <Link to={`/accion/${p.symbol}`} onClick={(ev) => ev.stopPropagation()}
                                  className={cn("text-[13.5px] font-semibold text-tinta group-hover:text-marca leading-tight", TRANS)}>
                              {p.symbol}
                            </Link>
                            <div className="text-[12px] text-tinta-3 truncate max-w-[220px]">
                              {[p.nombre, p.mercado].filter(Boolean).join(" · ")}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right iv-cifra text-tinta-2 whitespace-nowrap">
                        {num(p.precio_actual) !== null ? p.precio_actual.toFixed(2) : "—"}
                      </td>
                      <td className={cn("px-4 py-3 text-right iv-cifra whitespace-nowrap",
                                        p.hoyPct > 0 ? "text-sube" : p.hoyPct < 0 ? "text-baja" : "text-tinta-3")}>
                        {p.hoyPct !== null ? fmtPct(p.hoyPct) : "—"}
                      </td>
                      <td className={cn("px-4 py-3 text-right iv-cifra font-medium whitespace-nowrap",
                                        p.pnl > 0 ? "text-sube" : p.pnl < 0 ? "text-baja" : "text-tinta-3")}>
                        {p.pnl !== null ? fmtEur(p.pnl) : "—"}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Barra pct={peso} />
                        <span className="iv-cifra text-tinta-2 ml-2.5 inline-block w-9 text-right">{peso.toFixed(0)} %</span>
                      </td>
                      <td className={cn("px-4 py-3 font-medium", RIESGO_TONO[p.riesgo] || "text-tinta-3")}>
                        {RIESGO_TXT[p.riesgo] || p.riesgo || "—"}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <EstadoTxt estado={p.estado} />
                      </td>
                      <td className="pr-4 py-3 text-right">
                        <ChevronRight aria-hidden="true" strokeWidth={1.75}
                                      className="w-4 h-4 inline text-tinta-3 group-hover:text-marca group-hover:translate-x-0.5 transition-[color,transform] duration-150 ease-salida motion-reduce:transition-none" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          </>
        )}
      </section>
    </>
  );
}
