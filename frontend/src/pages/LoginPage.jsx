import React, { useState } from "react";
import { ChartLineUp, Eye, EyeSlash, LockKey } from "@phosphor-icons/react";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) { toast.error("Introduce usuario y contraseña"); return; }
    setLoading(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      toast.error(err.message || "Error al iniciar sesión");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f5f3ef] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-[#1a3a32] flex items-center justify-center mb-4 shadow-lg">
            <ChartLineUp size={32} weight="bold" className="text-[#f5f3ef]" />
          </div>
          <h1 className="font-heading font-bold text-3xl text-[#0e1f1a] tracking-tight">InverIA</h1>
          <p className="text-sm text-[#5c6b66] mt-1 font-mono">Análisis bursátil en vivo</p>
        </div>

        {/* Card */}
        <div className="bg-white border border-[#e5e0d8] rounded-xl shadow-sm p-8">
          <div className="flex items-center gap-2 mb-6">
            <LockKey size={18} className="text-[#1a3a32]" weight="bold" />
            <h2 className="font-heading font-semibold text-lg text-[#0e1f1a]">Iniciar sesión</h2>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-mono text-[#5c6b66] mb-1.5 uppercase tracking-wider">
                Usuario
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="tu usuario"
                autoComplete="username"
                className="w-full h-11 px-3 rounded-md border border-[#e5e0d8] bg-[#f9f7f3] font-mono text-sm text-[#0e1f1a] placeholder:text-[#c5bfb4] focus:outline-none focus:ring-2 focus:ring-[#1a3a32] focus:border-transparent transition"
              />
            </div>

            <div>
              <label className="block text-xs font-mono text-[#5c6b66] mb-1.5 uppercase tracking-wider">
                Contraseña
              </label>
              <div className="relative">
                <input
                  type={showPass ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className="w-full h-11 px-3 pr-10 rounded-md border border-[#e5e0d8] bg-[#f9f7f3] font-mono text-sm text-[#0e1f1a] placeholder:text-[#c5bfb4] focus:outline-none focus:ring-2 focus:ring-[#1a3a32] focus:border-transparent transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#5c6b66] hover:text-[#0e1f1a]"
                >
                  {showPass ? <EyeSlash size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-[#1a3a32] hover:bg-[#0e1f1a] text-[#f5f3ef] font-mono font-semibold text-sm rounded-md transition-colors disabled:opacity-60 disabled:cursor-not-allowed mt-2"
            >
              {loading ? "Entrando..." : "Entrar"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-[#5c6b66] mt-6 font-mono">
          Tus datos se sincronizan en todos tus dispositivos
        </p>
      </div>
    </div>
  );
}
