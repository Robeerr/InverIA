import React, { useState } from "react";
import { ChartBar, CircleNotch, Eye, EyeSlash } from "@phosphor-icons/react";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";

/* Campo de texto de la entrada. Una sola definición para los dos campos, para que no
   se separen con el tiempo.
   · `text-base` en móvil: por debajo de 16 px iOS amplía la página al enfocar el campo
     y deja la tarjeta descolocada; desde `sm` vuelve a 14 px.
   · Placeholder en `tinta-3` entera: con /70 bajaba de 4,5:1.
   · Foco: borde naranja entero (≥3:1 sobre la superficie) más un anillo suave; el
     contorno global de :focus-visible se quita solo aquí porque este lo sustituye.
   · Solo se animan borde y sombra, nunca `all`. */
const CAMPO =
  "w-full h-12 px-4 rounded-xl border border-linea bg-superficie-alt font-mono text-base sm:text-sm " +
  "text-tinta caret-marca placeholder:text-tinta-3 hover:border-linea-fuerte " +
  "focus:outline-none focus-visible:outline-none focus:border-marca focus:ring-2 focus:ring-marca/30 " +
  "transition-[border-color,box-shadow] duration-150 ease-out";

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
  // `100dvh` y no `100vh`: en móvil la barra del navegador no empuja la tarjeta.
  return (
    <main className="min-h-screen min-h-[100dvh] flex items-center justify-center px-5 py-10 selection:bg-marca/30">
      {/* La única entrada animada de la pantalla: se ve una vez por sesión, así que se
          permite un fundido corto que sube 8 px. Con `prefers-reduced-motion` no hay
          desplazamiento (motion-safe) y el resto lo neutraliza App.css. */}
      <div className="w-full max-w-[380px] motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 motion-safe:duration-300 motion-safe:ease-out">
        <header className="flex flex-col items-center text-center mb-8">
          {/* El icono con su resplandor: el único elemento de la pantalla que brilla
              además del botón, y por eso es lo primero que se ve. */}
          <div className="relative mb-5" aria-hidden="true">
            <div className="absolute inset-1 rounded-[18px] bg-marca blur-2xl opacity-35" />
            <div className="relative w-14 h-14 rounded-[16px] iv-boton-brillo flex items-center justify-center">
              <ChartBar size={26} weight="bold" />
            </div>
          </div>
          <h1 className="iv-marca-palabra text-[40px] sm:text-[44px] leading-none pb-1">InverIA</h1>
          <p className="text-apoyo text-tinta-2 mt-2.5">Análisis bursátil en vivo</p>
        </header>

        <section className="iv-panel p-6 sm:p-8" aria-labelledby="login-titulo">
          {/* El título queda para lectores de pantalla: la tarjeta no lo necesita para
              entenderse, y sin él respira como en el diseño. */}
          <h2 id="login-titulo" className="sr-only">Iniciar sesión</h2>

          <form onSubmit={handleSubmit} className="flex flex-col gap-5" aria-busy={loading}>
            <div>
              <label htmlFor="login-usuario" className="iv-etiqueta block mb-2">
                Usuario
              </label>
              <input
                id="login-usuario"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="tu usuario"
                autoComplete="username"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                className={CAMPO}
              />
            </div>

            <div>
              <label htmlFor="login-clave" className="iv-etiqueta block mb-2">
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
                  className={`${CAMPO} pr-12`}
                />
                {/* Diana de 36 px (antes solo el icono de 17): se acierta con el pulgar. */}
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  aria-label={showPass ? "Ocultar contraseña" : "Mostrar contraseña"}
                  aria-pressed={showPass}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 h-9 w-9 grid place-items-center rounded-lg text-tinta-3 hover:text-tinta hover:bg-superficie transition-colors duration-150"
                >
                  {showPass ? <EyeSlash size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {/* Respuesta al pulsar: se hunde un 2 %. El brillo al pasar el ratón solo en
                dispositivos con puntero, para que en móvil no se quede encendido. */}
            <button
              type="submit"
              disabled={loading}
              className="mt-2 w-full h-12 inline-flex items-center justify-center gap-2 rounded-full iv-boton-brillo font-heading text-cuerpo font-semibold
                         transition-[filter,transform] duration-150 ease-out
                         [@media(hover:hover)]:hover:brightness-110 active:scale-[0.98] motion-reduce:active:scale-100
                         disabled:opacity-60 disabled:cursor-not-allowed disabled:active:scale-100"
            >
              {loading && (
                <CircleNotch size={18} weight="bold" className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
              )}
              {loading ? "Entrando…" : "Entrar a InverIA"}
            </button>
          </form>
        </section>

        {/* Nota de servicio, no un elemento: texto llano, sin la píldora con borde. */}
        <p className="mt-6 text-center text-etiqueta text-tinta-3 text-balance">
          Tus datos se sincronizan en todos tus dispositivos
        </p>
      </div>
    </main>
  );
}
