import React, { useState } from "react";
import { Loader2, Eye, EyeOff } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import { Sello } from "../components/Rail";

/* Campo de texto de la entrada. Una sola definición para los dos campos, para que no
   se separen con el tiempo.
   · `text-base` en móvil: por debajo de 16 px iOS amplía la página al enfocar el campo
     y deja la tarjeta descolocada; desde `sm` vuelve a 14 px.
   · Placeholder en `tinta-3` entera: con /70 bajaba de 4,5:1.
   · Foco: borde naranja entero (≥3:1 sobre la superficie) más un anillo suave; el
     contorno global de :focus-visible se quita solo aquí porque este lo sustituye.
   · Solo se animan borde y sombra, nunca `all`. */
const CAMPO =
  "w-full h-12 px-4 rounded-[12px] border border-medio bg-superficie-alt text-base sm:text-[14.5px] " +
  "text-tinta caret-marca placeholder:text-tinta-3 hover:border-linea-fuerte " +
  "focus:outline-none focus-visible:outline-none focus:border-marca focus:ring-[3px] focus:ring-marca/25 " +
  "transition-[border-color,box-shadow] duration-150 ease-salida";

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

  // Sin `bg-fondo` en la raíz: el fondo lo pone `body` (grafito con la luz índigo).
  // `100dvh` y no `100vh`: en móvil la barra del navegador no empuja la tarjeta.
  return (
    <main className="relative min-h-screen min-h-[100dvh] flex items-center justify-center px-5 py-10 overflow-hidden">
      {/* La sala: una retícula muy tenue que se apaga hacia los bordes y una luz
          índigo detrás del formulario. Decorado puro, fuera del árbol accesible. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0
           [background-image:linear-gradient(rgb(var(--iv-tinta)/0.035)_1px,transparent_1px),linear-gradient(90deg,rgb(var(--iv-tinta)/0.035)_1px,transparent_1px)]
           [background-size:56px_56px]
           [mask-image:radial-gradient(ellipse_60%_55%_at_50%_45%,black,transparent)]" />
      <div aria-hidden="true" className="pointer-events-none absolute left-1/2 top-[38%] -translate-x-1/2 -translate-y-1/2
           w-[560px] h-[360px] rounded-full bg-marca/[0.14] blur-[90px]" />

      {/* La única entrada animada: fundido corto que sube 6 px (240 ms). */}
      <div className="relative w-full max-w-[380px] motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300 motion-safe:ease-salida">
        <header className="flex flex-col items-start mb-7">
          <Sello className="w-11 h-11 rounded-[13px]" trazo={2.2} />
          <h1 className="mt-6 text-[30px] leading-[1.1] font-semibold tracking-[-0.04em] text-tinta">
            Entra en InverIA
          </h1>
          <p className="text-cuerpo text-tinta-2 mt-2">Tu cartera y tus señales, en vivo.</p>
        </header>

        <section className="iv-panel p-6 sm:p-7 shadow-flotante" aria-labelledby="login-titulo">
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
                  {showPass ? <EyeOff size={17} strokeWidth={1.75} /> : <Eye size={17} strokeWidth={1.75} />}
                </button>
              </div>
            </div>

            {/* Respuesta al pulsar: se hunde un 2 %. El brillo al pasar el ratón solo en
                dispositivos con puntero, para que en móvil no se quede encendido. */}
            <button
              type="submit"
              disabled={loading}
              className="mt-1 w-full h-12 inline-flex items-center justify-center gap-2 rounded-[12px] iv-boton-brillo text-[15px] font-medium tracking-[-0.01em]
                         transition-[filter,transform] duration-150 ease-salida
                         [@media(hover:hover)]:hover:brightness-[1.08] active:scale-[0.98] motion-reduce:active:scale-100
                         disabled:opacity-60 disabled:cursor-not-allowed disabled:active:scale-100"
            >
              {loading && (
                <Loader2 size={18} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
              )}
              {loading ? "Entrando…" : "Entrar a InverIA"}
            </button>
          </form>
        </section>

        <p className="mt-5 text-apoyo text-tinta-3 text-balance">
          Tus datos se sincronizan en todos tus dispositivos
        </p>
      </div>
    </main>
  );
}
