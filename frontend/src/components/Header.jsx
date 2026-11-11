import React from "react";
import { MagnifyingGlass, Moon, Sun, TelegramLogo, List, SignOut, User } from "@phosphor-icons/react";
import { RailCajon } from "./Rail";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";

// Botón de icono de la barra: sin caja propia hasta que pasas por encima. Antes cada
// acción llevaba borde y fondo, y la barra se leía como una fila de cuatro cajas que
// pesaban lo mismo que el buscador. 40px de lado: es zona táctil cómoda en móvil.
const ICONO =
  "h-10 w-10 shrink-0 text-tinta-2 hover:text-tinta hover:bg-superficie-alt " +
  "active:scale-[0.96] transition-[color,background-color,transform] duration-150 ease-out " +
  "motion-reduce:transition-none motion-reduce:active:scale-100";

// La navegación ya no vive aquí: la tiene `Rail.jsx`, que es su dueño único. Esta
// barra se queda con lo que de verdad es suyo —buscar, estado y cuenta— y con la
// hamburguesa que abre el cajón en móvil.
export default function Header({ symbol, setSymbol, onSearch, showSearch = true, darkMode, setDarkMode }) {
  const { user, logout } = useAuth();
  const [query, setQuery] = React.useState(symbol || "");
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [backendOk, setBackendOk] = React.useState(null); // null=checking, true=ok, false=down
  const [suggestions, setSuggestions] = React.useState([]);
  const [showSug, setShowSug] = React.useState(false);
  const searchRef = React.useRef(null);
  const location = useLocation();

  // #4 Autocompletado: busca por nombre o ticker (debounce 250ms) para no memorizar el ticker.
  React.useEffect(() => {
    const q = (query || "").trim();
    if (q.length < 1 || q === (symbol || "")) { setSuggestions([]); return; }
    let alive = true;
    const id = setTimeout(() => {
      api.search(q).then((r) => { if (alive) { setSuggestions(Array.isArray(r) ? r : []); setShowSug(true); } }).catch(() => {});
    }, 250);
    return () => { alive = false; clearTimeout(id); };
  }, [query, symbol]);

  // Cierra el desplegable al tocar fuera.
  React.useEffect(() => {
    const onDoc = (e) => { if (searchRef.current && !searchRef.current.contains(e.target)) setShowSug(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("touchstart", onDoc);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("touchstart", onDoc); };
  }, []);

  const pick = (sym) => {
    setSymbol(sym);
    onSearch(sym);
    setQuery(sym);
    setShowSug(false);
    setSuggestions([]);
  };

  // Status check cada 2 min (el indicador Online/Offline no necesita más frecuencia)
  React.useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch((process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "") + "/api/health", { signal: AbortSignal.timeout(8000) });
        setBackendOk(res.ok);
      } catch {
        setBackendOk(false);
      }
    };
    check();
    const id = setInterval(check, 120000);
    return () => clearInterval(id);
  }, []);

  React.useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  React.useEffect(() => setQuery(symbol || ""), [symbol]);

  const submit = (e) => {
    e.preventDefault();
    const s = (query || "").trim().toUpperCase();
    if (s) {
      setSymbol(s);
      onSearch(s);
    }
  };

  const testTelegram = async () => {
    for (const [grupo, label] of [["ideas_javi", "Cartera"]]) {
      try {
        await api.alerts.testTelegram(grupo);
        toast.success(`Telegram ${label}: enviado ✓`);
      } catch (e) {
        const detail = e?.response?.data?.detail || `Error al enviar Telegram (${label})`;
        toast.error(`${label}: ${detail}`, { duration: 12000 });
      }
    }
  };

  return (
    <header
      data-testid="app-header"
      className="sticky top-0 z-30 bg-fondo/95 backdrop-blur border-b border-linea"
    >
      {/* Barra superior. Ya no lleva navegación ni marca: las dos viven en el rail.
          Se queda con lo único que es suyo —buscar, estado y cuenta— y con la
          hamburguesa, que en móvil abre el cajón con las MISMAS etiquetas. */}
      <div className="mx-auto px-3 sm:px-5 py-2.5 flex items-center gap-2 sm:gap-3">
        <Button
          onClick={() => setMenuOpen(true)}
          variant="outline"
          size="icon"
          aria-label="Abrir menú"
          className={`lg:hidden ${ICONO} border-linea`}
        >
          <List size={16} />
        </Button>

        {/* Search + autocompletado.
            Sin techo, a propósito. Un `max-w` dejaba un hueco muerto entre el
            campo y las acciones en cuanto sobraba sitio, y ese hueco se ve peor
            que un buscador holgado. Ahora el campo se queda con lo que sobre, y
            lo que sobra es poco porque la nav ya no lo acapara.
            El suelo de 200px es lo que impide el fallo original, cuando `min-w-0`
            dejaba colapsar el campo hasta que solo se veía la lupa. Pero SOLO a
            partir de `lg`: en un móvil de 390px quedan ~358px útiles y el suelo,
            sumado al logo y a las acciones, pedía ~423. El sobrante no recorta el
            buscador —`min-width` no cede—, sino que desborda la barra y expulsa
            la hamburguesa fuera de la pantalla, que es justo el único acceso al
            menú que hay en móvil. Ahí el campo tiene que poder encogerse. */}
        {showSearch && (
          <div ref={searchRef} className="flex-1 relative min-w-0 lg:min-w-[200px]">
            <form onSubmit={submit} className="relative" role="search">
              <label htmlFor="busqueda-valor" className="sr-only">Buscar valor por ticker o nombre</label>
              <MagnifyingGlass size={16} aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-tinta-3" />
              <Input
                id="busqueda-valor"
                data-testid="stock-search-input"
                value={query}
                onChange={(e) => setQuery(e.target.value.toUpperCase())}
                onFocus={() => { if (suggestions.length) setShowSug(true); }}
                placeholder="Ticker o nombre (ej: AAPL o Apple)"
                className="pl-9 h-10 bg-superficie border-linea font-mono text-sm text-tinta
                           placeholder:text-tinta-3 hover:border-linea-fuerte transition-colors
                           focus-visible:border-linea-fuerte focus-visible:ring-marca"
                autoComplete="off"
              />
            </form>
            {/* Desplegable: filas compactas, ticker en tinta (el naranja es del rail y
                del activo, no de cada resultado) y nombre en segundo plano. El ticker
                ocupa lo que necesite —«BRK.B», «SAN.MC»— y el nombre se recorta. */}
            {showSug && suggestions.length > 0 && (
              <div className="absolute z-50 left-0 right-0 mt-1.5 bg-superficie border border-linea-fuerte
                              rounded-iv-sm shadow-[0_12px_32px_-12px_rgb(0_0_0/0.5)] overflow-hidden
                              max-h-72 overflow-y-auto overscroll-contain py-1">
                {suggestions.map((s) => (
                  <button
                    key={s.symbol}
                    type="button"
                    onClick={() => pick(s.symbol)}
                    className="w-full flex items-baseline gap-3 px-3 py-2 text-left
                               hover:bg-superficie-alt focus-visible:bg-superficie-alt transition-colors duration-100"
                  >
                    <span className="font-mono font-semibold text-sm text-tinta shrink-0 min-w-[4.5rem]">{s.symbol}</span>
                    <span className="text-apoyo text-tinta-2 truncate min-w-0">{s.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Acciones. Una sola fila sin cajas: el estado es un punto con su palabra, las
            acciones son iconos que solo toman fondo al pasar, y la cuenta se separa con
            un filete fino. Lo único que puede pedir atención aquí es «Offline», y por
            eso es lo único que se enseña en rojo y con palabra también en móvil. */}
        <div className="flex items-center gap-1 sm:gap-1.5 shrink-0 ml-auto">
          {/* Status indicator */}
          <div
            role="status"
            title={backendOk === null ? "Comprobando backend..." : backendOk ? "Backend activo ✓" : "Backend no responde"}
            className={`flex items-center gap-1.5 h-10 px-1.5 sm:px-2 font-mono text-etiqueta tracking-normal ${
              backendOk === false ? "text-baja" : "text-tinta-3"
            }`}
          >
            <span aria-hidden="true" className="relative flex w-2 h-2 shrink-0">
              {backendOk === false && (
                <span className="absolute inset-0 rounded-full bg-baja/60 motion-safe:animate-ping" />
              )}
              <span className={`relative w-2 h-2 rounded-full ${
                backendOk === null ? "bg-aviso motion-safe:animate-pulse" : backendOk ? "bg-sube" : "bg-baja"
              }`} />
            </span>
            <span className={backendOk === false ? "inline" : "sr-only lg:not-sr-only"}>
              {backendOk === null ? "..." : backendOk ? "Online" : "Offline"}
            </span>
          </div>

          <Button
            data-testid="dark-mode-toggle"
            onClick={() => setDarkMode(!darkMode)}
            variant="ghost"
            size="icon"
            className={ICONO}
            title={darkMode ? "Modo claro" : "Modo oscuro"}
            aria-label={darkMode ? "Modo claro" : "Modo oscuro"}
          >
            {darkMode ? <Sun size={16} /> : <Moon size={16} />}
          </Button>
          <Button
            data-testid="test-telegram-btn"
            onClick={testTelegram}
            variant="ghost"
            size="icon"
            className={`hidden sm:inline-flex ${ICONO}`}
            title="Probar Telegram"
            aria-label="Probar Telegram"
          >
            <TelegramLogo size={16} />
          </Button>

          {/* User + logout */}
          <div className="hidden sm:flex items-center gap-1 pl-2 ml-1 border-l border-linea">
            <span className="flex items-center gap-1.5 px-1.5 font-mono text-etiqueta tracking-normal text-tinta-3 min-w-0">
              <User size={14} aria-hidden="true" className="shrink-0" />
              <span className="hidden md:inline truncate max-w-[12ch]" title={user}>{user}</span>
            </span>
            <button
              onClick={logout}
              title="Cerrar sesión"
              aria-label="Cerrar sesión"
              className="inline-flex items-center justify-center h-9 w-9 rounded-iv-sm text-tinta-3
                         hover:text-baja hover:bg-baja/10 active:scale-[0.96]
                         transition-[color,background-color,transform] duration-150 ease-out
                         motion-reduce:transition-none motion-reduce:active:scale-100"
            >
              <SignOut size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* El menú móvil ya no se reimplementa aquí: es el MISMO rail, en cajón.
          Antes eran dos listas de navegación que había que mantener a la vez. */}
      <RailCajon abierto={menuOpen} cerrar={() => setMenuOpen(false)} />
    </header>
  );
}
