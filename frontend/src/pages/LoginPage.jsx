import React, { useState } from "react";
import { ChartBar, Eye, EyeSlash } from "@phosphor-icons/react";
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

  // Sin `bg-fondo` en la raíz: el fondo lo pone `body`, que en oscuro lleva los dos
  // brillos suaves de toda la app. Taparlo aquí dejaría la entrada en negro plano.
  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-[380px]">
        <div className="flex flex-col items-center mb-9">
          {/* El icono con su resplandor: el único elemento de la pantalla que brilla
              además del botón, y por eso es lo primero que se ve. */}
          <div className="relative mb-5">
            <div className="absolute inset-0 rounded-[18px] bg-marca blur-2xl opacity-40" aria-hidden="true" />
            <div className="relative w-[60px] h-[60px] rounded-[18px] iv-boton-brillo flex items-center justify-center">
              <ChartBar size={28} weight="bold" />
            </div>
          </div>
          <h1 className="iv-marca-palabra text-[44px] leading-none pb-1">InverIA</h1>
          <p className="text-apoyo text-tinta-3 mt-2">Análisis bursátil en vivo</p>
        </div>

        <div className="iv-panel rounded-[22px] p-7 sm:p-8">
          {/* El título queda para lectores de pantalla: la tarjeta no lo necesita para
              entenderse, y sin él respira como en el diseño. */}
          <h2 className="sr-only">Iniciar sesión</h2>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="login-usuario" className="iv-etiqueta block mb-2 tracking-[0.14em]">
                Usuario
              </label>
              <input
                id="login-usuario"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="tu usuario"
                autoComplete="username"
                className="w-full h-12 px-4 rounded-xl border border-linea bg-superficie-alt font-mono text-sm text-tinta placeholder:text-tinta-3/70 focus:outline-none focus:ring-2 focus:ring-marca/70 focus:border-transparent transition"
              />
            </div>

            <div>
              <label htmlFor="login-clave" className="iv-etiqueta block mb-2 tracking-[0.14em]">
                Contraseña
              </label>
              <div className="relative">
                <input
                  id="login-clave"
                  type={showPass ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className="w-full h-12 px-4 pr-11 rounded-xl border border-linea bg-superficie-alt font-mono text-sm text-tinta placeholder:text-tinta-3/70 focus:outline-none focus:ring-2 focus:ring-marca/70 focus:border-transparent transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  aria-label={showPass ? "Ocultar contraseña" : "Mostrar contraseña"}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-tinta-3 hover:text-tinta"
                >
                  {showPass ? <EyeSlash size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full h-12 rounded-full iv-boton-brillo font-heading text-cuerpo hover:brightness-110 transition disabled:opacity-60 disabled:cursor-not-allowed !mt-7"
            >
              {loading ? "Entrando…" : "Entrar a InverIA"}
            </button>
          </form>
        </div>

        <p className="flex justify-center mt-6">
          <span className="iv-etiqueta normal-case tracking-normal border border-linea rounded-full px-3 py-1">
            Tus datos se sincronizan en todos tus dispositivos
          </span>
        </p>
      </div>
    </div>
  );
}
