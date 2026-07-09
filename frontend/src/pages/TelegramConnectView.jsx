import React, { useEffect, useState, useCallback } from "react";
import { TelegramLogo, CheckCircle, ArrowClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Pantalla para conectar tu cuenta de Telegram (userbot, solo lectura) y elegir qué
// canales de tu grupo de pago capturar para alimentar el cerebro. Todo desde el móvil.

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
      } else toast.error(r.error || "No se pudieron listar los canales");
    } catch (e) { toast.error("Error listando canales"); }
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

  const Field = ({ label, ...p }) => (
    <label className="block mb-3">
      <span className="text-[11px] uppercase tracking-wider text-[#5c6b66] font-mono">{label}</span>
      <input {...p} className="w-full mt-1 px-3 py-2 rounded-md border border-[#e5e0d8] bg-white text-[#0e1f1a] text-sm" />
    </label>
  );

  return (
    <div className="max-w-lg mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <TelegramLogo size={24} weight="fill" className="text-[#229ED9]" />
        <div>
          <h1 className="font-heading font-bold text-lg text-[#0e1f1a] leading-tight">Conectar Telegram</h1>
          <p className="text-[11px] text-[#5c6b66]">Lee los canales de tu grupo de pago para alimentar el cerebro (solo lectura).</p>
        </div>
      </div>

      {step === "token" && (
        <div className="card-flat p-5">
          <Field label="Token de acceso" type="password" value={token} placeholder="tu INBOUND_SECRET"
            onChange={(e) => setToken(e.target.value)} />
          <button onClick={submitToken} disabled={busy} className="w-full py-2 rounded-md bg-[#1a3a32] text-white text-sm font-semibold disabled:opacity-50">
            Continuar
          </button>
        </div>
      )}

      {step === "phone" && (
        <div className="card-flat p-5">
          <p className="text-xs text-[#5c6b66] mb-3">Introduce tu número de Telegram. Te llegará un código dentro de la propia app de Telegram.</p>
          <Field label="Teléfono (con prefijo)" type="tel" value={phone} placeholder="+34600000000"
            onChange={(e) => setPhone(e.target.value)} />
          <button onClick={sendCode} disabled={busy} className="w-full py-2 rounded-md bg-[#1a3a32] text-white text-sm font-semibold disabled:opacity-50">
            {busy ? "Enviando…" : "Enviar código"}
          </button>
        </div>
      )}

      {step === "code" && (
        <div className="card-flat p-5">
          <p className="text-xs text-[#5c6b66] mb-3">Mira el código que te ha llegado <b>en Telegram</b> (mensaje de "Telegram") y ponlo aquí. Si tienes verificación en 2 pasos, añade tu contraseña.</p>
          <Field label="Código" type="text" inputMode="numeric" value={code} placeholder="12345"
            onChange={(e) => setCode(e.target.value)} />
          <Field label="Contraseña 2FA (si tienes)" type="password" value={password} placeholder="opcional"
            onChange={(e) => setPassword(e.target.value)} />
          <button onClick={submitCode} disabled={busy} className="w-full py-2 rounded-md bg-[#1a3a32] text-white text-sm font-semibold disabled:opacity-50">
            {busy ? "Verificando…" : "Conectar"}
          </button>
        </div>
      )}

      {step === "channels" && (
        <div className="card-flat p-5">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-semibold text-[#0e1f1a]">Elige qué capturar</p>
            <button onClick={() => loadDialogs(token)} className="p-1.5 rounded-md border border-[#e5e0d8]" title="Recargar">
              <ArrowClockwise size={14} weight="bold" className={busy ? "animate-spin" : ""} />
            </button>
          </div>
          <p className="text-[11px] text-[#5c6b66] mb-3">Marca los canales de los <b>dueños</b> (señal). Deja sin marcar los chats de miembros (ruido).</p>
          <div className="space-y-1.5 max-h-[50vh] overflow-y-auto mb-4">
            {dialogs.length === 0 && !busy && <p className="text-xs text-[#5c6b66]">No hay canales o aún cargando…</p>}
            {dialogs.map((c) => (
              <button key={c.id} onClick={() => toggle(c.id)}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md border text-left"
                style={{ borderColor: selected.has(c.id) ? "#4a7c59" : "#e5e0d8", background: selected.has(c.id) ? "#4a7c5910" : "white" }}>
                <div className="min-w-0">
                  <p className="text-sm text-[#0e1f1a] truncate">{c.nombre}</p>
                  <p className="text-[10px] text-[#5c6b66]">{c.tipo} · {c.id}</p>
                </div>
                {selected.has(c.id) && <CheckCircle size={18} weight="fill" className="text-[#4a7c59] shrink-0" />}
              </button>
            ))}
          </div>
          <button onClick={saveCapture} disabled={busy} className="w-full py-2 rounded-md bg-[#1a3a32] text-white text-sm font-semibold disabled:opacity-50">
            Guardar y empezar a capturar ({selected.size})
          </button>
        </div>
      )}

      {status && (
        <p className="text-[10px] text-[#5c6b66] text-center">
          Sesión: {status.sesion_guardada ? "✅ conectada" : "—"} · Capturando: {status.canales_capturando?.length || 0} canal(es)
        </p>
      )}
    </div>
  );
}
