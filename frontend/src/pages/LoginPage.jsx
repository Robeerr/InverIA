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
    <div className="min-h-screen bg-fondo flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-marca flex items-center justify-center mb-4 shadow-lg">
            <ChartLineUp size={32} weight="bold" className="text-marca-tinta" />
          </div>
          <h1 className="font-heading font-bold text-3xl text-tinta tracking-tight">InverIA</h1>
          <p className="text-sm text-tinta-3 mt-1 font-mono">Análisis bursátil en vivo</p>
        </div>

        {/* Card */}
        <div className="bg-superficie border border-linea rounded-xl shadow-sm p-8">
          <div className="flex items-center gap-2 mb-6">
            <LockKey size={18} className="text-marca" weight="bold" />
            <h2 className="font-heading font-semibold text-lg text-tinta">Iniciar sesión</h2>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-mono text-tinta-3 mb-1.5 uppercase tracking-wider">
                Usuario
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="tu usuario"
                autoComplete="username"
                className="w-full h-11 px-3 rounded-md border border-linea bg-superficie-alt font-mono text-sm text-tinta placeholder:text-tinta-3/70 focus:outline-none focus:ring-2 focus:ring-marca focus:border-transparent transition"
              />
            </div>

            <div>
              <label className="block text-xs font-mono text-tinta-3 mb-1.5 uppercase tracking-wider">
                Contraseña
              </label>
              <div className="relative">
                <input
                  type={showPass ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className="w-full h-11 px-3 pr-10 rounded-md border border-linea bg-superficie-alt font-mono text-sm text-tinta placeholder:text-tinta-3/70 focus:outline-none focus:ring-2 focus:ring-marca focus:border-transparent transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-tinta-3 hover:text-tinta"
                >
                  {showPass ? <EyeSlash size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-marca hover:bg-marca/90 text-marca-tinta font-mono font-semibold text-sm rounded-md transition-colors disabled:opacity-60 disabled:cursor-not-allowed mt-2"
            >
              {loading ? "Entrando..." : "Entrar"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-tinta-3 mt-6 font-mono">
          Tus datos se sincronizan en todos tus dispositivos
        </p>
      </div>
    </div>
  );
}
