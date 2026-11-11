import React, { useEffect, useState, useCallback } from "react";
import { TelegramLogo, CheckCircle, Circle, ArrowClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Pantalla para conectar tu cuenta de Telegram (userbot, solo lectura) y elegir qué
// canales de tu grupo de pago capturar para alimentar el cerebro. Todo desde el móvil.

/* ── Piezas de presentación ──────────────────────────────────────────────────
   Fuera del componente a propósito: definido dentro, React lo trataba como un
   componente nuevo en cada render y el input perdía el foco con cada tecla. */

// Botón principal: respuesta al pulsar (escala 0,98, 150 ms ease-out) y brillo
// solo en dispositivos con ratón, para que en el móvil no se quede «pegado».
const BOTON =
  "w-full h-10 rounded-iv bg-marca text-marca-tinta text-sm font-semibold " +
  "transition-[transform,filter] duration-150 ease-out active:scale-[0.98] " +
  "[@media(hover:hover)]:hover:brightness-110 " +
  "disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 " +
  "motion-reduce:transition-none motion-reduce:active:scale-100";

// 16 px en móvil para que iOS no haga zoom al enfocar; 14 px desde sm.
const INPUT =
  "w-full h-10 mt-1.5 px-3 rounded-iv border border-linea bg-fondo/40 text-tinta " +
  "text-[16px] sm:text-sm placeholder:text-tinta-3 " +
  "transition-colors duration-150 ease-out focus:border-marca/70 " +
  "[@media(hover:hover)]:hover:border-linea-fuerte";

function Campo({ label, mono = false, ...p }) {
  return (
    <label className="block">
      <span className="text-etiqueta uppercase tracking-wider text-tinta-3 font-mono">{label}</span>
      <input {...p} className={`${INPUT} ${mono ? "font-mono tracking-wide" : ""}`} />
    </label>
  );
}

const PASOS = [
  { id: "token", nombre: "Acceso" },
  { id: "phone", nombre: "Teléfono" },
  { id: "code", nombre: "Código" },
  { id: "channels", nombre: "Canales" },
];

// Dónde estás en el alta. Informativo: no se puede saltar de paso desde aquí.
function Pasos({ step }) {
  const actual = PASOS.findIndex((p) => p.id === step);
  return (
    <ol className="grid grid-cols-4 gap-2" aria-label="Pasos para conectar Telegram">
      {PASOS.map((p, i) => {
        const hecho = i < actual;
        const ahora = i === actual;
        return (
          <li key={p.id} aria-current={ahora ? "step" : undefined} className="min-w-0">
            <span
              aria-hidden="true"
              className={`block h-0.5 rounded-full transition-colors duration-200 ${
                ahora ? "bg-marca" : hecho ? "bg-tinta-3" : "bg-linea"
              }`}
            />
            <span
              className={`mt-1.5 block truncate text-etiqueta ${
                ahora ? "text-tinta font-semibold" : hecho ? "text-tinta-2" : "text-tinta-3"
              }`}
            >
              {p.nombre}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

const AYUDA = "text-apoyo text-tinta-2 [&_b]:font-semibold [&_b]:text-tinta";

export default function TelegramConnectView() {
  const [token, setToken] = useState("");
  const [status, setStatus] = useState(null);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState("token"); // token | phone | code | channels
  const [dialogs, setDialogs] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [busy, setBusy] = useState(false);

  const loadStatus = useCallback(async (t) => {
    try {
      const s = await api.telegram.status(t);
      setStatus(s);
      if (s.sesion_guardada) setStep("channels");
      else setStep("phone");
      return s;
    } catch (e) {
      toast.error("Token inválido o error de conexión");
      return null;
    }
  }, []);

  const loadDialogs = useCallback(async (t) => {
    setBusy(true);
    try {
      const r = await api.telegram.dialogs(t);
      if (r.ok) {
        setDialogs(r.canales || []);
        setSelected(new Set((r.canales || []).filter((c) => c.capturando).map((c) => c.id)));
      } else {
        // Sesión inválida (o caducada) → volver al login de teléfono.
        toast.error(r.error || "Sesión no válida, vuelve a hacer login");
        setStep("phone");
      }
    } catch (e) { toast.error("Error listando canales"); setStep("phone"); }
    finally { setBusy(false); }
  }, []);

  useEffect(() => { if (step === "channels" && token) loadDialogs(token); }, [step, token, loadDialogs]);

  const submitToken = async () => {
    if (!token.trim()) return;
    setBusy(true);
    await loadStatus(token.trim());
    setBusy(false);
  };

  const sendCode = async () => {
    if (!phone.trim()) return toast.error("Pon tu teléfono con prefijo (ej. +34...)");
    setBusy(true);
    try {
      const r = await api.telegram.loginStart(token, phone.trim());
      if (r.ok) { toast.success("Código enviado a Telegram"); setStep("code"); }
      else toast.error(r.error || "No se pudo enviar el código");
    } catch (e) { toast.error("Error enviando el código"); }
    finally { setBusy(false); }
  };

  const submitCode = async () => {
    if (!code.trim()) return;
    setBusy(true);
    try {
      const r = await api.telegram.loginCode(token, code.trim(), password.trim());
      if (r.ok) { toast.success(`Conectado como ${r.cuenta || "tu cuenta"}`); setStep("channels"); }
      else toast.error(r.error || "El código no funcionó");
    } catch (e) { toast.error("Error verificando el código"); }
    finally { setBusy(false); }
  };

  const toggle = (id) => setSelected((s) => {
    const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  const saveCapture = async () => {
    setBusy(true);
    try {
      const r = await api.telegram.setCapture(token, [...selected]);
      if (r.ok) toast.success(`Capturando ${r.capturando.length} canal(es). El cerebro ya escucha.`);
      else toast.error("No se pudo guardar");
    } catch (e) { toast.error("Error guardando"); }
    finally { setBusy(false); }
  };

  const cargandoLista = busy && dialogs.length === 0;

  return (
    <div className="max-w-lg mx-auto space-y-5">
      <header className="flex items-start gap-3">
        {/* EXCEPCIÓN DE MARCA · #229ED9 es el azul de Telegram, no un color de
            InverIA. Se queda fijo en los dos temas porque un logo que cambia de
            color con el tema deja de ser el logo. Es, con el rojo de YouTube en
            BrainView, uno de los DOS únicos hex que sobreviven fuera de la paleta
            de sectores — y los dos por el mismo motivo: identifican un servicio
            ajeno, no un papel dentro de InverIA.

            Contraste como elemento gráfico (umbral 3:1): 3,02:1 sobre el blanco de
            claro y 5,90:1 sobre la superficie oscura. La cifra de oscuro subió al
            bajar el fondo a verde-negro; la de claro no se mueve y sigue siendo la
            justa, así que el logo no debe encogerse por debajo de 24 px. */}
        <TelegramLogo size={24} weight="fill" className="text-[#229ED9] shrink-0 mt-0.5" aria-hidden="true" />
        <div className="min-w-0">
          <h1 className="font-heading font-bold text-titulo text-tinta">Conectar Telegram</h1>
          <p className="mt-0.5 text-apoyo text-tinta-2">Lee los canales de tu grupo de pago para alimentar el cerebro (solo lectura).</p>
        </div>
      </header>

      <Pasos step={step} />

      {step === "token" && (
        <section className="iv-panel p-4 sm:p-5 space-y-4" aria-label="Acceso">
          <Campo label="Token de acceso" type="password" mono value={token} placeholder="tu INBOUND_SECRET"
            autoComplete="off" onChange={(e) => setToken(e.target.value)} />
          <button onClick={submitToken} disabled={busy} aria-busy={busy} className={BOTON}>
            Continuar
          </button>
        </section>
      )}

      {step === "phone" && (
        <section className="iv-panel p-4 sm:p-5 space-y-4" aria-label="Teléfono">
          <p className={AYUDA}>Introduce tu número de Telegram. Te llegará un código dentro de la propia app de Telegram.</p>
          <Campo label="Teléfono (con prefijo)" type="tel" mono value={phone} placeholder="+34600000000"
            autoComplete="tel" onChange={(e) => setPhone(e.target.value)} />
          <button onClick={sendCode} disabled={busy} aria-busy={busy} className={BOTON}>
            {busy ? "Enviando…" : "Enviar código"}
          </button>
        </section>
      )}

      {step === "code" && (
        <section className="iv-panel p-4 sm:p-5 space-y-4" aria-label="Código">
          <p className={AYUDA}>Mira el código que te ha llegado <b>en Telegram</b> (mensaje de "Telegram") y ponlo aquí. Si tienes verificación en 2 pasos, añade tu contraseña.</p>
          <Campo label="Código" type="text" inputMode="numeric" mono value={code} placeholder="12345"
            autoComplete="one-time-code" onChange={(e) => setCode(e.target.value)} />
          <Campo label="Contraseña 2FA (si tienes)" type="password" value={password} placeholder="opcional"
            onChange={(e) => setPassword(e.target.value)} />
          <button onClick={submitCode} disabled={busy} aria-busy={busy} className={BOTON}>
            {busy ? "Verificando…" : "Conectar"}
          </button>
        </section>
      )}

      {step === "channels" && (
        <section className="iv-panel p-4 sm:p-5" aria-labelledby="tg-canales">
          <div className="flex items-center justify-between gap-3">
            <h2 id="tg-canales" className="font-heading text-cuerpo font-semibold text-tinta">Elige qué capturar</h2>
            <button
              onClick={() => loadDialogs(token)}
              title="Recargar"
              aria-label="Recargar canales"
              className="grid place-items-center size-8 shrink-0 rounded-iv border border-linea text-tinta-2
                transition-[color,border-color,transform] duration-150 ease-out active:scale-[0.94]
                [@media(hover:hover)]:hover:text-tinta [@media(hover:hover)]:hover:border-linea-fuerte
                motion-reduce:active:scale-100"
            >
              <ArrowClockwise size={14} weight="bold" className={busy ? "animate-spin" : ""} />
            </button>
          </div>
          <p className={`${AYUDA} mt-1 mb-3`}>Marca los canales de los <b>dueños</b> (señal). Deja sin marcar los chats de miembros (ruido).</p>

          {/* Una sola caja con filas separadas por línea fina, como las listas de Hoy:
              la selección se marca con el acento (fondo tenue + check), no con verde,
              que en InverIA queda reservado a las subidas. */}
          <div
            className="max-h-[50vh] overflow-y-auto overscroll-contain rounded-iv border border-linea divide-y divide-linea mb-4"
            aria-busy={busy}
          >
            {cargandoLista && (
              <div role="status" aria-label="Cargando canales">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-3 px-3 py-3 animate-pulse" aria-hidden="true">
                    <span className="size-[18px] rounded-full bg-linea" />
                    <span className="flex-1 space-y-1.5">
                      <span className="block h-3 w-2/3 rounded bg-linea" />
                      <span className="block h-2.5 w-1/3 rounded bg-linea/70" />
                    </span>
                  </div>
                ))}
              </div>
            )}
            {dialogs.length === 0 && !busy && (
              <p className="px-3 py-6 text-center text-apoyo text-tinta-3">No hay canales o aún cargando…</p>
            )}
            {dialogs.map((c) => {
              const on = selected.has(c.id);
              return (
                <button
                  key={c.id}
                  onClick={() => toggle(c.id)}
                  aria-pressed={on}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors duration-150 ease-out
                    ${on ? "bg-marca/[0.07]" : "[@media(hover:hover)]:hover:bg-superficie-alt"}`}
                >
                  {on
                    ? <CheckCircle size={18} weight="fill" className="text-marca shrink-0" aria-hidden="true" />
                    : <Circle size={18} className="text-tinta-3 shrink-0" aria-hidden="true" />}
                  <span className="min-w-0 flex-1">
                    <span className={`block text-sm truncate ${on ? "text-tinta font-medium" : "text-tinta-2"}`}>{c.nombre}</span>
                    <span className="block text-etiqueta text-tinta-3 truncate">
                      {c.tipo} · <span className="iv-cifra">{c.id}</span>
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          <button onClick={saveCapture} disabled={busy} aria-busy={busy} className={BOTON}>
            Guardar y empezar a capturar (<span className="iv-cifra">{selected.size}</span>)
          </button>
          <button
            onClick={() => setStep("phone")}
            className="w-full mt-1 py-2.5 text-tinta-3 text-xs underline underline-offset-4 decoration-tinta-3/50
              transition-colors duration-150 [@media(hover:hover)]:hover:text-tinta-2"
          >
            ¿Problemas? Rehacer login (teléfono + código)
          </button>
        </section>
      )}

      {status && (
        <p className="text-etiqueta text-tinta-3 text-center">
          Sesión: <span className={status.sesion_guardada ? "text-tinta-2" : ""}>{status.sesion_guardada ? "conectada" : "—"}</span>
          {" · "}Capturando: <span className="iv-cifra text-tinta-2">{status.canales_capturando?.length || 0}</span> canal(es)
        </p>
      )}
    </div>
  );
}
