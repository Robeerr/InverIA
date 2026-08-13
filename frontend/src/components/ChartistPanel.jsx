import React, { useState, useEffect } from "react";
import { FolderSimplePlus, Calculator, Check } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";

const SENT_COLOR = {
  alcista: "text-sube bg-sube/10",
  bajista: "text-baja bg-baja/10",
  neutro: "text-tinta-3 bg-fondo",
};
const ACCION_COLOR = {
  COMPRAR: "bg-sube text-white",
  ESPERAR: "bg-aviso text-tinta",
  EVITAR: "bg-baja text-white",
};

// Chartista IA: veredicto técnico multi-timeframe con plan accionable y explicación
// pedagógica (para que el usuario aprenda cuándo entrar y por qué).
export default function ChartistPanel({ symbol, runSignal }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [calcOpen, setCalcOpen] = useState(false);
  const [capital, setCapital] = useState("");
  const [addedCartera, setAddedCartera] = useState(false);
  const [addingCartera, setAddingCartera] = useState(false);

  // #11 Añadir a Cartera: crea una entrada en tu Cartera con los niveles de compra del plan
  // del Chartista ya rellenados (nivel1..5), y el objetivo como nivel deseado de venta.
  async function addToCartera() {
    const plan = data?.plan;
    if (!symbol || !plan || addingCartera) return;
    // Guarda explícita, aunque el backend ya vacíe los niveles al servir un veredicto
    // vetado y rechace la escritura con un 409. Este botón no muestra: ESCRIBE en la
    // Cartera, y un efecto persistente no puede depender de que otra capa haya limpiado
    // bien los datos antes. Si algún día llega un plan vetado con niveles —una respuesta
    // cacheada en el navegador, un veredicto anterior a este cambio—, aquí se para.
    if (data?.vetado_por_tendencia) {
      toast.error("Esta acción no está en tendencia alcista: su plan de compra no se guarda");
      return;
    }
    const precios = (plan.niveles_entrada || [])
      .map((n) => Number(n.precio)).filter((v) => v > 0)
      .sort((a, b) => b - a).slice(0, 5);   // nivel1 = el más alto (primero que se toca)
    if (!precios.length) { toast.error("El plan no tiene niveles de compra concretos"); return; }
    setAddingCartera(true);
    const payload = { symbol, grupo: "ideas_javi", notes: "Añadido desde el Chartista IA" };
    precios.forEach((p, i) => { payload[`nivel${i + 1}`] = p; });
    if (Number(plan.objetivo) > 0) payload.deseado = Number(plan.objetivo);
    try {
      await api.signalsCreate(payload);
      setAddedCartera(true);
      toast.success(`${symbol} añadida a tu Cartera con ${precios.length} niveles`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      // Hay DOS 409 distintos en `POST /signals` y significan lo contrario:
      //
      //   · duplicado → la acción YA está en tu Cartera. Marcar el botón es correcto.
      //   · veto      → la acción NO se ha guardado, y no se va a guardar.
      //
      // Tratarlos igual pintaba el check verde de «En Cartera» sobre un rechazo: mentía
      // dos veces, porque ni estaba ni el motivo era ese. Se separan por un campo, no por
      // el texto: el mensaje del veto lo escribe `estado_accion` y puede cambiar.
      //
      // Esta rama es también la que cierra la CARRERA: el veredicto del Chartista se
      // cachea hasta 4 horas, así que el plan que tiene la pantalla puede venir de antes
      // de que la tendencia se girara. La guarda de arriba no salta —ese plan no está
      // marcado— y es aquí, con la respuesta del servidor, donde se descubre.
      if (detail?.error === "vetado_por_tendencia") {
        toast.error(detail.mensaje || "Esta acción no está en tendencia alcista");
        return;   // sin `setAddedCartera`: no se ha guardado nada
      }
      const msg = typeof detail === "string" ? detail : "";
      if (e?.response?.status === 409 || /ya/i.test(msg)) {
        setAddedCartera(true);
        toast(`${symbol} ya estaba en tu Cartera`);
      } else {
        toast.error(msg || "No se pudo añadir a la Cartera");
      }
    } finally {
      setAddingCartera(false);
    }
  }

  // Al cambiar de acción: limpiar el veredicto anterior y, si el pre-cálculo de la watchlist
  // ya dejó uno listo en caché, mostrarlo AL INSTANTE (sin pulsar ni gastar cuota). Si no hay
  // pre-cálculo, se queda el botón "Analizar" como siempre.
  useEffect(() => {
    setData(null);
    setErr(null);
    setLoading(false);
    setAddedCartera(false);
    if (!symbol) return;
    let ok = true;
    api.chartistCached(symbol)
      .then((d) => {
        if (ok && d && d.cached !== false && (d.sentido || d.veredicto || d.plan)) {
          setData(d);
        }
      })
      .catch(() => {});
    return () => { ok = false; };
  }, [symbol]);

  // Disparo externo desde el botón "Análisis completo" del Dashboard.
  // OJO CON EL COSTE: si ya hay veredicto (pre-calculado o cacheado) NO se pide nada. Antes
  // se llamaba con refresh=true, que salta la caché y puede acabar en la clave de PAGO.
  useEffect(() => {
    if (runSignal && !data && !loading) run(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runSignal]);

  async function run(refresh = false) {
    setLoading(true);
    setErr(null);
    try {
      const d = await api.chartist(symbol, refresh);
      setData(d);
    } catch (e) {
      setErr(e?.response?.data?.detail || "No se pudo generar el veredicto. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  const plan = data?.plan;

  return (
    <div className="iv-panel p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-semibold text-tinta">🎯 Chartista IA</span>
        {data?.sentido && (
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${SENT_COLOR[data.sentido] || SENT_COLOR.neutro}`}>
            {data.sentido.toUpperCase()}
          </span>
        )}
        {data?._ai_tier && <TierBadge tier={data._ai_tier} model={data._ai_model} />}
        {data?._precomputed && (
          <span title="Pre-calculado en segundo plano para tu watchlist" className="text-[9px] font-mono text-aviso">⚡ listo</span>
        )}
        <button
          onClick={() => run(!!data)}
          disabled={loading}
          className="ml-auto px-2.5 py-1 rounded text-[11px] font-mono font-semibold bg-marca text-white disabled:opacity-50"
        >
          {loading ? "Analizando…" : data ? "Recalcular" : "Analizar"}
        </button>
      </div>

      {!data && !loading && !err && (
        <p className="text-[11px] text-tinta-3">
          Lee los timeframes 15M → 1S, identifica el patrón y te da un veredicto con plan de
          entrada, invalidación y el porqué — para que aprendas a leerlo tú.
        </p>
      )}
      {loading && <p className="text-[11px] text-tinta-3">Leyendo velas de todos los timeframes y consultando al cerebro… (~20-40s)</p>}
      {err && <p className="text-[11px] text-baja">{err}</p>}

      {data && (
        <div className="space-y-3">
          {/* Patrón principal */}
          {data.patron_principal && (
            <div className="text-[12px] text-tinta">
              <b>Patrón que manda:</b> {data.patron_principal}
            </div>
          )}

          {/* Lectura por timeframe */}
          {Array.isArray(data.por_timeframe) && data.por_timeframe.length > 0 && (
            <div className="space-y-1">
              {data.por_timeframe.map((t, i) => (
                <div key={i} className="flex gap-2 text-[11px]">
                  <span className="font-mono font-semibold text-marca w-10 shrink-0">{t.tf}</span>
                  <span className="text-tinta-3">{t.lectura}</span>
                </div>
              ))}
            </div>
          )}

          {/* Veredicto */}
          {data.veredicto && (
            <div className="text-[12px] border border-linea rounded p-2 leading-snug">
              {data.veredicto}
            </div>
          )}

          {/* Por qué el plan no trae compra. Va ANTES del plan, no debajo: si el usuario
              lee «ESPERAR» sin explicación, lo atribuye al criterio del chartista y no a
              la estructura, que es justo el matiz que hace que aprenda algo. */}
          {data.vetado_por_tendencia && (
            <div data-testid="chartista-vetado"
                 className="border-l-[3px] border-baja bg-baja/5 rounded p-2 text-[11px] leading-snug">
              <span className="font-semibold text-baja">Compra vetada por la tendencia. </span>
              <span className="text-tinta-3">
                {data.veto_motivo || "La acción no está en tendencia alcista."}
              </span>
            </div>
          )}

          {/* Plan accionable */}
          {plan && (
            <div className="border border-linea rounded p-2.5 space-y-2">
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded text-[11px] font-mono font-bold ${ACCION_COLOR[plan.accion] || ACCION_COLOR.ESPERAR}`}>
                  {plan.accion || "ESPERAR"}
                </span>
                {plan.gatillo && <span className="text-[11px] text-tinta font-medium">{plan.gatillo}</span>}
                {Array.isArray(plan.niveles_entrada) && plan.niveles_entrada.some((n) => n.precio != null) && (
                  <button
                    onClick={addToCartera}
                    disabled={addingCartera || addedCartera}
                    title="Añadir esta acción a tu Cartera con estos niveles de compra"
                    className={`ml-auto shrink-0 flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono font-semibold transition-colors ${
                      addedCartera
                        ? "bg-sube/10 text-sube"
                        : "bg-marca text-white hover:bg-tinta disabled:opacity-50"
                    }`}
                  >
                    {addedCartera ? <><Check size={12} /> En Cartera</> : <><FolderSimplePlus size={12} /> Añadir a Cartera</>}
                  </button>
                )}
              </div>

              {/* Compra ESCALONADA por niveles (anclados a estructura real) */}
              {Array.isArray(plan.niveles_entrada) && plan.niveles_entrada.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[9px] uppercase tracking-wide text-tinta-3">Compra escalonada</div>
                  {plan.niveles_entrada.map((nv, i) => (
                    <div key={i} className="flex items-center gap-2 text-[11px]">
                      <span className="w-5 h-5 shrink-0 rounded-full bg-sube/10 text-sube font-mono font-bold text-[10px] flex items-center justify-center">{i + 1}</span>
                      <span className="font-mono font-bold text-sube">{nv.precio != null ? `$${Number(nv.precio).toFixed(2)}` : "—"}</span>
                      {nv.porcentaje != null && <span className="font-mono text-tinta font-semibold">· {Number(nv.porcentaje)}%</span>}
                      {nv.motivo && <span className="text-tinta-3 truncate">· {nv.motivo}</span>}
                    </div>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-2 gap-2 text-center">
                <Lvl label="Invalidación" val={plan.invalidacion} color="rgb(var(--iv-baja))" />
                <Lvl label="Objetivo" val={plan.objetivo} color="rgb(var(--iv-info))" />
              </div>

              {/* #12 Calculadora de posición: reparte tu capital por los niveles */}
              {Array.isArray(plan.niveles_entrada) && plan.niveles_entrada.some((n) => n.precio != null) && (
                <div>
                  <button
                    onClick={() => setCalcOpen((o) => !o)}
                    className="flex items-center gap-1.5 text-[10px] font-mono text-marca hover:underline"
                  >
                    <Calculator size={12} /> {calcOpen ? "Ocultar calculadora" : "Calcular posición"}
                  </button>
                  {calcOpen && (
                    <PositionCalc
                      niveles={plan.niveles_entrada}
                      invalidacion={plan.invalidacion}
                      objetivo={plan.objetivo}
                      capital={capital}
                      setCapital={setCapital}
                    />
                  )}
                </div>
              )}
              {plan.por_que && (
                <p className="text-[11px] text-tinta-3 leading-snug"><b className="text-tinta">Por qué:</b> {plan.por_que}</p>
              )}
            </div>
          )}

          {/* Enseñanza */}
          {data.para_aprender && (
            <div className="text-[11px] text-tinta-3 flex gap-1.5">
              <span>🎓</span>
              <span><b className="text-tinta">Para aprender:</b> {data.para_aprender}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Badge FREE / PAY: indica si el análisis lo sirvió la clave Gemini gratis o la de pago.
export function TierBadge({ tier, model }) {
  if (!tier) return null;
  const meta = {
    free: { label: "FREE", cls: "bg-sube/10 text-sube", title: "Servido por la clave Gemini GRATIS" },
    paid: { label: "PAY", cls: "bg-baja/10 text-baja", title: "Servido por la clave Gemini de PAGO (consume tu crédito)" },
    groq: { label: "ALT", cls: "bg-fondo text-tinta-3", title: "Gemini estaba saturado: servido por el modelo de respaldo (Groq, gratis)" },
  }[tier] || null;
  if (!meta) return null;
  return (
    <span className="inline-flex items-center gap-1">
      <span
        title={meta.title}
        className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase tracking-wide ${meta.cls}`}
      >
        {meta.label}
      </span>
      {model && <span className="text-[9px] font-mono text-tinta-3">{model}</span>}
    </span>
  );
}

// #12 Calculadora de posición: dado tu capital, reparte por los niveles del plan y calcula
// acciones por nivel, precio medio, riesgo hasta la invalidación y beneficio hasta el objetivo.
function PositionCalc({ niveles, invalidacion, objetivo, capital, setCapital }) {
  const C = Number(capital) || 0;
  const valid = niveles.filter((n) => Number(n.precio) > 0);
  // Reparto: usa los porcentajes del plan; si no suman, normaliza; si faltan, equireparte.
  const sumPct = valid.reduce((s, n) => s + (Number(n.porcentaje) || 0), 0);
  const rows = valid.map((n) => {
    const pct = sumPct > 0 ? (Number(n.porcentaje) || 0) / sumPct : 1 / valid.length;
    const euros = C * pct;
    const precio = Number(n.precio);
    return { precio, euros, acciones: precio > 0 ? euros / precio : 0 };
  });
  const totalAcc = rows.reduce((s, r) => s + r.acciones, 0);
  const invertido = rows.reduce((s, r) => s + r.euros, 0);
  const medio = totalAcc > 0 ? invertido / totalAcc : 0;
  const inv = Number(invalidacion) || 0;
  const obj = Number(objetivo) || 0;
  const riesgo = inv > 0 && totalAcc > 0 ? (medio - inv) * totalAcc : null;
  const riesgoPct = inv > 0 && medio > 0 ? ((medio - inv) / medio) * 100 : null;
  const benef = obj > 0 && totalAcc > 0 ? (obj - medio) * totalAcc : null;
  const benefPct = obj > 0 && medio > 0 ? ((obj - medio) / medio) * 100 : null;
  const fmt = (x) => x == null ? "—" : x.toLocaleString("es-ES", { maximumFractionDigits: 0 });

  return (
    <div className="mt-2 p-2 rounded bg-fondo border border-linea space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-tinta-3">Capital a invertir</span>
        <div className="flex items-center gap-1">
          <span className="text-[11px] text-tinta-3">$</span>
          <input
            type="number"
            inputMode="decimal"
            value={capital}
            onChange={(e) => setCapital(e.target.value)}
            placeholder="1000"
            className="w-24 bg-white border border-linea rounded px-2 py-1 font-mono text-[12px] focus:outline-none focus:border-marca"
          />
        </div>
      </div>
      {C > 0 && (
        <>
          <div className="space-y-0.5">
            {rows.map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-[10px] font-mono">
                <span className="w-4 h-4 shrink-0 rounded-full bg-sube/10 text-sube font-bold text-[9px] flex items-center justify-center">{i + 1}</span>
                <span className="text-tinta-3">${r.precio.toFixed(2)}</span>
                <span className="text-tinta">→ ${fmt(r.euros)}</span>
                <span className="ml-auto font-bold text-sube">{r.acciones.toFixed(r.acciones < 10 ? 2 : 1)} acc.</span>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 pt-1 border-t border-linea text-[10px] font-mono">
            <Row label="Acciones totales" val={`${totalAcc.toFixed(totalAcc < 10 ? 2 : 1)}`} />
            <Row label="Precio medio" val={`$${medio.toFixed(2)}`} />
            <Row label="Riesgo (a invalidación)" val={riesgo != null ? `-$${fmt(riesgo)}${riesgoPct != null ? ` · ${riesgoPct.toFixed(1)}%` : ""}` : "—"} color="rgb(var(--iv-baja))" />
            <Row label="Beneficio (a objetivo)" val={benef != null ? `+$${fmt(benef)}${benefPct != null ? ` · ${benefPct.toFixed(1)}%` : ""}` : "—"} color="rgb(var(--iv-sube))" />
          </div>
          {riesgo != null && benef != null && riesgo > 0 && (
            <p className="text-[10px] text-tinta-3">
              Ratio riesgo/beneficio: <b className="text-tinta">1:{(benef / riesgo).toFixed(1)}</b>
            </p>
          )}
        </>
      )}
    </div>
  );
}

function Row({ label, val, color }) {
  return (
    <div>
      <div className="text-tinta-3">{label}</div>
      <div className="font-bold" style={{ color: color || "rgb(var(--iv-tinta))" }}>{val}</div>
    </div>
  );
}

function Lvl({ label, val, color }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wide text-tinta-3">{label}</div>
      <div className="text-[13px] font-mono font-bold" style={{ color: val != null ? color : "rgb(var(--iv-tinta-3))" }}>
        {val != null ? `$${Number(val).toFixed(2)}` : "—"}
      </div>
    </div>
  );
}
