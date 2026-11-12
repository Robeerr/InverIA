import React, { useEffect, useState, useCallback, useId } from "react";
import { ArrowClockwise, TelegramLogo, Envelope, CaretDown, YoutubeLogo } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";
import Boton from "@/components/base/Boton";
import Chip from "@/components/base/Chip";
import { Cargando, Vacio } from "@/components/base/Estado";

/* Cerebro · lo que InverIA aprende de tus fuentes
   ─────────────────────────────────────────────────────────────────────────────
   Antes: tres tarjetas-métrica con un color distinto cada una, un rótulo de sección
   que repetía la pestaña activa y una caja por mensaje (sesenta cajas iguales en la
   captura). Ahora, como en Hoy:

     · Las tres cifras van en una sola tira con filetes, junto al titular.
     · Las pestañas son una barra con subrayado: dicen dónde estás sin un rótulo extra.
     · Cada lista es UN panel con filas separadas por filetes. Las capturas que
       sumaron principios se leen más fuertes que el ruido, que queda atenuado.
     · Cifras en monoespaciada tabular y alineadas a la derecha. */

// Campos de texto: mismo borde que el resto y foco en naranja, no el azul del sistema.
const CAMPO =
  "w-full px-3 py-2 rounded-iv border border-linea bg-superficie text-tinta text-sm " +
  "placeholder:text-tinta-3 transition-colors hover:border-linea-fuerte " +
  "focus:border-marca focus:outline-none focus-visible:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-marca/30 motion-reduce:transition-none";

// Las URLs largas (hojas de cálculo, enlaces de noticias) no tienen espacios donde
// partir: sin esto, empujan la fila más allá del borde en móvil.
const PARTIR = "[overflow-wrap:anywhere]";

function YouTubeBox({ onDone }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [manual, setManual] = useState(false);
  const [texto, setTexto] = useState("");
  const [fuente, setFuente] = useState("");
  const idManual = useId();

  const go = async () => {
    if (!url.trim()) return;
    setBusy(true); setRes(null);
    try {
      const r = await api.youtubeIngest(url.trim());
      setRes(r);
      if (r.ok) { toast.success("Vídeo procesado"); onDone?.(); }
      else toast.error(r.error || "No se pudo procesar");
    } catch (e) { toast.error("Error procesando el vídeo"); }
    finally { setBusy(false); }
  };

  const goText = async () => {
    if (texto.trim().length < 60) return toast.error("Pega un texto más largo");
    setBusy(true); setRes(null);
    try {
      const r = await api.ingestText(texto.trim(), fuente.trim() || "Texto pegado");
      setRes(r);
      if (r.ok) { toast.success("Texto procesado"); setTexto(""); onDone?.(); }
    } catch (e) { toast.error("Error procesando el texto"); }
    finally { setBusy(false); }
  };

  return (
    <div className="iv-panel overflow-hidden divide-y divide-linea">
      <div className="p-4 sm:p-5">
        <div className="flex items-center gap-2 mb-3">
          <YoutubeLogo size={18} weight="fill" className="text-[#FF0000] shrink-0" aria-hidden="true" />
          <h2 className="text-cuerpo font-semibold text-tinta">Añadir vídeo de YouTube</h2>
        </div>
        <div className="flex gap-2">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://youtu.be/..."
            aria-label="Enlace del vídeo de YouTube" inputMode="url"
            onKeyDown={(e) => { if (e.key === "Enter" && !busy) go(); }}
            className={`${CAMPO} flex-1 min-w-0`} />
          <Boton onClick={go} disabled={busy} className="shrink-0">
            {busy ? "Procesando…" : "Procesar"}
          </Boton>
        </div>
        {busy && (
          <p className="text-etiqueta text-tinta-3 mt-2" role="status" aria-live="polite">
            Procesando y extrayendo ideas…
          </p>
        )}

        <button type="button" onClick={() => setManual((v) => !v)}
          aria-expanded={manual} aria-controls={idManual}
          className="text-etiqueta text-tinta-3 underline underline-offset-4 decoration-linea-fuerte
                     hover:text-tinta hover:decoration-marca transition-colors mt-3 py-1
                     motion-reduce:transition-none">
          {manual ? "Ocultar" : "¿Falla? Pega la transcripción / texto a mano"}
        </button>
        {manual && (
          <div id={idManual} className="mt-2 space-y-2">
            <input value={fuente} onChange={(e) => setFuente(e.target.value)} placeholder="Fuente (ej. Vídeo JaviZone) — opcional"
              aria-label="Fuente del texto (opcional)" className={CAMPO} />
            <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={5} placeholder="Pega aquí la transcripción del vídeo, o cualquier texto (artículo, análisis)…"
              aria-label="Transcripción o texto" className={`${CAMPO} resize-y leading-relaxed`} />
            <Boton variante="secundario" onClick={goText} disabled={busy} className="w-full">
              {busy ? "Procesando…" : "Procesar texto"}
            </Boton>
          </div>
        )}
      </div>

      {res?.ok && (
        <div className="p-4 sm:p-5 bg-sube/[0.04]" role="status" aria-live="polite">
          <p className="text-etiqueta font-semibold text-sube">Conseguido del vídeo (vía {res.via}):</p>
          {res.resumen && <p className={`text-apoyo text-tinta leading-relaxed mt-1.5 max-w-[70ch] ${PARTIR}`}>{res.resumen}</p>}
          <div className="flex flex-wrap gap-1.5 mt-3">
            <Chip tono="sube"><span className="iv-cifra">{res.aprendidos}</span> aprendizajes</Chip>
            <Chip tono="info"><span className="iv-cifra">{res.acciones}</span> picks</Chip>
            {(res.tickers || []).map((t) => (
              <Chip key={t} tono="neutro" variante="contorno">{t}</Chip>
            ))}
          </div>
          {res.acciones === 0 && res.aprendidos === 0 && (
            <p className="text-etiqueta text-tinta-3 mt-2">Leyó el vídeo ({res.chars} caracteres) pero no encontró picks ni método reutilizable.</p>
          )}
        </div>
      )}
      {res && !res.ok && (
        <p className="px-4 sm:px-5 py-3 text-apoyo text-baja bg-baja/5" role="alert">{res.error}</p>
      )}
    </div>
  );
}

// Apartado "Cerebro": ventana a lo que sabe y a lo que va capturando en tiempo real
// (Telegram + newsletters). Feed de actividad + conocimiento acumulado por categoría.

function fmtFecha(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("es-ES", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { return iso.slice(0, 16).replace("T", " "); }
}

// Miles con punto, como en el resto de la app. Lo que no es número pasa tal cual («—»).
const fmtNum = (n) => (typeof n === "number" ? n.toLocaleString("es-ES") : n);

/* Una cifra de la tira de cabecera. Sin color propio por defecto: el color solo
   se gasta en la que manda (Principios). */
function Stat({ label, value, acento = false }) {
  return (
    <div className="px-4 py-3 min-w-0">
      <dt className="iv-etiqueta truncate">{label}</dt>
      <dd className={`iv-cifra text-xl sm:text-2xl font-semibold leading-none mt-1.5 truncate ${acento ? "text-marca" : "text-tinta"}`}>
        {value}
      </dd>
    </div>
  );
}

// El caret gira con una ease-out firme y corta: confirma el clic sin hacerse esperar.
const CARET =
  "text-tinta-3 transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] " +
  "motion-reduce:transition-none";
// El fondo al pasar solo con ratón: en móvil el «hover» se queda pegado tras el toque.
const FILA_INTERACTIVA =
  "[@media(hover:hover)]:hover:bg-superficie-alt/50 transition-colors duration-150 " +
  "motion-reduce:transition-none focus-visible:bg-superficie-alt/50 focus-visible:-outline-offset-2";

function ActivityItem({ a }) {
  const [open, setOpen] = useState(false);
  const idDetalle = useId();
  const principios = a.principios || [];
  const canOpen = principios.length > 0;
  // Lo que sumó principios es lo que se viene a leer; el resto es ruido que pasa.
  const aporta = a.aprendidos > 0;

  const contenido = (
    <>
      {a.tipo === "telegram"
        ? <TelegramLogo size={15} weight="fill" className="text-tinta-3 shrink-0 mt-0.5" aria-label="Telegram" />
        : <Envelope size={15} weight="fill" className="text-tinta-3 shrink-0 mt-0.5" aria-label="Correo" />}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className={`text-apoyo font-semibold truncate ${aporta ? "text-tinta" : "text-tinta-2"}`}>{a.fuente}</p>
          <time dateTime={a.at || undefined} className="iv-cifra text-etiqueta text-tinta-3 shrink-0 tabular-nums">
            {fmtFecha(a.at)}
          </time>
        </div>
        <p className={`text-apoyo leading-snug mt-0.5 ${PARTIR} ${aporta ? "text-tinta-2" : "text-tinta-3"} ${open ? "" : "line-clamp-2"}`}>
          {a.snippet || "(sin texto)"}
        </p>
      </div>
      <div className="flex items-center gap-1.5 shrink-0 w-12 justify-end self-start mt-0.5">
        {aporta && (
          <span className="iv-cifra text-etiqueta font-bold text-sube" title={`${a.aprendidos} principios sumados`}>
            +{a.aprendidos}
          </span>
        )}
        {canOpen && <CaretDown size={12} aria-hidden="true" className={`${CARET} ${open ? "rotate-180" : ""}`} />}
      </div>
    </>
  );

  return (
    <li>
      {canOpen ? (
        <button type="button" onClick={() => setOpen((v) => !v)}
          aria-expanded={open} aria-controls={idDetalle}
          className={`w-full flex items-start gap-3 text-left px-4 py-3 cursor-pointer ${FILA_INTERACTIVA}`}>
          {contenido}
        </button>
      ) : (
        <div className="w-full flex items-start gap-3 px-4 py-3">{contenido}</div>
      )}
      {open && (
        <div id={idDetalle} className="pl-[2.6875rem] pr-4 pb-3 -mt-1">
          <p className="iv-etiqueta mb-1.5">Aprendió:</p>
          <ul className="space-y-1.5">
            {principios.map((p, i) => (
              <li key={i} className={`text-apoyo text-tinta leading-snug flex gap-2 ${PARTIR}`}>
                <span aria-hidden="true" className="mt-[0.45em] h-1 w-1 rounded-full bg-sube shrink-0" />
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

function Principio({ p }) {
  const [open, setOpen] = useState(false);
  const idDetalle = useId();
  return (
    <li>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-controls={idDetalle}
        className={`w-full flex items-start justify-between gap-3 text-left px-4 py-3 ${FILA_INTERACTIVA}`}>
        <div className="min-w-0">
          <span className="iv-etiqueta text-marca">{p.categoria}</span>
          <p className={`text-sm text-tinta leading-snug mt-1 ${PARTIR}`}>{p.principio}</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
          {p.refuerzos > 1 && (
            <span className="iv-cifra text-etiqueta font-bold text-sube" title={`Reforzado ${p.refuerzos} veces`}>×{p.refuerzos}</span>
          )}
          {p.detalle && <CaretDown size={12} aria-hidden="true" className={`${CARET} ${open ? "rotate-180" : ""}`} />}
        </div>
      </button>
      <div id={idDetalle}>
        {open && p.detalle && (
          <p className={`text-apoyo text-tinta-2 leading-relaxed px-4 -mt-1 pb-3 max-w-[75ch] ${PARTIR}`}>{p.detalle}</p>
        )}
        {open && p.fuentes?.length > 0 && (
          <p className={`text-etiqueta text-tinta-3 px-4 pb-3 ${p.detalle ? "-mt-1.5" : "-mt-1"} ${PARTIR}`}>
            Fuentes: {p.fuentes.join(" · ")}
          </p>
        )}
      </div>
    </li>
  );
}

const PESTANAS = [["actividad", "Actividad"], ["conocimiento", "Conocimiento"],
  ["fuentes", "Fuentes"], ["anadir", "Añadir"]];

export default function BrainView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("actividad");
  const [cat, setCat] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await api.brain()); }
    catch (e) { toast.error("No se pudo cargar el cerebro"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const d = data || {};
  const actividad = d.actividad || [];
  const top = d.top || [];
  const fuentes = d.fuentes || [];
  const cats = d.por_categoria || {};
  const totalCapturas = fuentes.reduce((a, f) => a + (f.capturas || 0), 0);
  const filtered = cat ? top.filter((p) => p.categoria === cat) : top;
  // Sin respuesta del servidor no se sabe cuántas hay: «—», no un 0 que parece un dato.
  const sinDatos = !loading && !data;

  return (
    <div className="space-y-6">
      {/* ── Cabecera: titular a la izquierda, las tres cifras a la derecha en una tira.
          En móvil la tira baja debajo del texto y ocupa el ancho. */}
      <header className="iv-veredicto flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
        <div className="min-w-0 flex-1 basis-[20rem]">
          <div className="flex items-center gap-3">
            <h1 className="iv-verbo text-tinta">Cerebro</h1>
            <Boton variante="fantasma" tamano="icono" onClick={load} title="Recargar" aria-label="Recargar"
              className="text-tinta-3 mt-1">
              <ArrowClockwise size={16} className={loading ? "motion-safe:animate-spin" : ""} aria-hidden="true" />
            </Boton>
          </div>
          <p className="text-cuerpo text-tinta-2 mt-2.5 max-w-[58ch]">
            Lo que InverIA aprende de tus fuentes. Lo que aporta método suma principios;
            el ruido pasa sin añadir nada.
          </p>
        </div>

        <dl className="iv-panel grid grid-cols-3 divide-x divide-linea w-full sm:w-auto sm:min-w-[22rem] shrink-0"
          aria-busy={loading || undefined}>
          <Stat label="Principios" value={sinDatos ? "—" : fmtNum(d.principios ?? "—")} acento />
          <Stat label="Capturas" value={sinDatos ? "—" : fmtNum(totalCapturas)} />
          <Stat label="Fuentes" value={sinDatos ? "—" : fmtNum(fuentes.length)} />
        </dl>
      </header>

      {/* Cuatro pestañas. «Añadir» era antes un bloque fijo sobre el contenido: una
          caja de formulario que se veía en cada visita para una acción que se hace de
          vez en cuando, y que empujaba hacia abajo lo que sí se viene a leer.
          La barra de pestañas con su filete hace de cabecera de sección: el rótulo
          que repetía el nombre de la pestaña activa sobraba. */}
      <div>
        <div role="tablist" aria-label="Secciones del cerebro"
          className="flex gap-1 border-b border-linea overflow-x-auto [scrollbar-width:none]">
          {PESTANAS.map(([k, l]) => {
            const activa = tab === k;
            return (
              <button key={k} type="button" role="tab" id={`cerebro-tab-${k}`}
                aria-selected={activa} aria-controls="cerebro-panel"
                onClick={() => setTab(k)}
                className={`relative shrink-0 px-3 sm:px-4 py-2.5 text-apoyo font-medium whitespace-nowrap
                            transition-colors duration-150 motion-reduce:transition-none
                            focus-visible:-outline-offset-2
                            after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full
                            after:transition-colors after:duration-150
                            ${activa ? "text-tinta after:bg-marca"
                                     : "text-tinta-3 hover:text-tinta after:bg-transparent hover:after:bg-linea-fuerte"}`}>
                {l}
              </button>
            );
          })}
        </div>

        <div id="cerebro-panel" role="tabpanel" aria-labelledby={`cerebro-tab-${tab}`} className="pt-4">
          {tab === "anadir" ? (
            /* «Añadir» no depende de la carga: así el resultado del vídeo recién
               procesado no desaparece mientras se refrescan las cifras. */
            <div className="space-y-3 max-w-[46rem]">
              <p className="text-apoyo text-tinta-2 max-w-[62ch]">
                Pega un vídeo de YouTube o un texto y el cerebro extrae los principios que
                contenga. Lo que no aporta método no suma nada: no es un archivo, es un filtro.
              </p>
              <YouTubeBox onDone={load} />
            </div>
          ) : loading ? (
            <div className="iv-panel divide-y divide-linea overflow-hidden">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="px-4 py-4">
                  <Cargando filas={2} alto="h-3" etiqueta={i === 0 ? "Cargando…" : ""} />
                </div>
              ))}
            </div>
          ) : sinDatos ? (
            <div className="iv-panel px-4 py-8 text-center border-baja/30" role="alert">
              <p className="text-cuerpo text-tinta font-medium">No se pudo cargar el cerebro</p>
              <Boton variante="contorno" tamano="sm" className="mt-3" onClick={load}>Reintentar</Boton>
            </div>
          ) : tab === "actividad" ? (
            <div className="space-y-3">
              <p className="text-apoyo text-tinta-3 max-w-[75ch]">Cada mensaje/audio/foto que capta, en orden. Lo que aporta método suma principios; el ruido pasa sin añadir nada.</p>
              {actividad.length === 0 ? (
                <div className="iv-panel">
                  <Vacio titulo="Aún no ha capturado nada." motivo="Cuando llegue algo a tus fuentes, aparecerá aquí." />
                </div>
              ) : (
                <ul className="iv-panel overflow-hidden divide-y divide-linea">
                  {actividad.map((a, i) => <ActivityItem key={i} a={a} />)}
                </ul>
              )}
            </div>
          ) : tab === "conocimiento" ? (
            <div className="space-y-3">
              <div className="flex gap-1.5 flex-wrap" role="group" aria-label="Filtrar por categoría">
                {[[null, "Todo", null], ...Object.entries(cats).map(([c, n]) => [c, c, n])].map(([c, l, n]) => {
                  const activa = cat === c;
                  return (
                    <button key={c ?? "__todo"} type="button" onClick={() => setCat(c)} aria-pressed={activa}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-etiqueta border
                                  transition-[color,background-color,border-color,transform] duration-150 ease-out
                                  active:scale-[0.97] motion-reduce:transition-none motion-reduce:active:scale-100
                                  ${activa ? "bg-marca text-marca-tinta border-marca font-semibold"
                                           : "border-linea text-tinta-2 hover:border-linea-fuerte hover:text-tinta"}`}>
                      {n == null ? l : <>{l} <span className={`iv-cifra ${activa ? "" : "text-tinta-3"}`}>· {n}</span></>}
                    </button>
                  );
                })}
              </div>
              {filtered.length === 0 ? (
                <div className="iv-panel">
                  <Vacio titulo="Sin principios todavía." />
                </div>
              ) : (
                <ul className="iv-panel overflow-hidden divide-y divide-linea">
                  {filtered.map((p, i) => <Principio key={i} p={p} />)}
                </ul>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-apoyo text-tinta-3">De dónde viene el conocimiento y cuánto aporta cada fuente.</p>
              {fuentes.length === 0 ? (
                <div className="iv-panel">
                  <Vacio titulo="Sin fuentes activas todavía." />
                </div>
              ) : (
                <ul className="iv-panel overflow-hidden divide-y divide-linea">
                  {fuentes.map((f, i) => (
                    <li key={i} className="px-4 py-3 flex items-center justify-between gap-4">
                      <div className="min-w-0">
                        <p className="text-sm text-tinta truncate" title={f.fuente}>{f.fuente}</p>
                        <p className="text-etiqueta text-tinta-3 mt-0.5">
                          Última: <span className="iv-cifra">{fmtFecha(f.ultima)}</span>
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="iv-cifra text-sm font-semibold text-sube">+{fmtNum(f.aprendidos)}</p>
                        <p className="text-etiqueta text-tinta-3 mt-0.5">
                          <span className="iv-cifra">{fmtNum(f.capturas)}</span> capturas
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
