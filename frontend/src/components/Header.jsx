import React from "react";
import { MagnifyingGlass, Moon, Sun, TelegramLogo, List, SignOut, User } from "@phosphor-icons/react";
import { RailCajon } from "./Rail";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";

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
      <div className="mx-auto px-4 sm:px-5 py-2.5 flex items-center gap-3">
        <Button
          onClick={() => setMenuOpen(true)}
          variant="outline"
          size="icon"
          aria-label="Abrir menú"
          className="lg:hidden h-9 w-9 border-linea hover:bg-superficie-alt shrink-0"
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
            <form onSubmit={submit} className="relative">
              <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-tinta-3" />
              <Input
                data-testid="stock-search-input"
                value={query}
                onChange={(e) => setQuery(e.target.value.toUpperCase())}
                onFocus={() => { if (suggestions.length) setShowSug(true); }}
                placeholder="Ticker o nombre (ej: AAPL o Apple)"
                className="pl-9 h-10 bg-superficie border-linea font-mono text-sm placeholder:text-tinta-3 focus-visible:ring-marca"
                autoComplete="off"
              />
            </form>
            {showSug && suggestions.length > 0 && (
              <div className="absolute z-50 left-0 right-0 mt-1 bg-superficie border border-linea rounded-md shadow-lg overflow-hidden max-h-72 overflow-y-auto">
                {suggestions.map((s) => (
                  <button
                    key={s.symbol}
                    type="button"
                    onClick={() => pick(s.symbol)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-fondo transition-colors"
                  >
                    <span className="font-mono font-bold text-sm text-marca shrink-0 w-16">{s.symbol}</span>
                    <span className="text-xs text-tinta-3 truncate">{s.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0 ml-auto">
          {/* Status indicator */}
          <div
            title={backendOk === null ? "Comprobando backend..." : backendOk ? "Backend activo ✓" : "Backend no responde"}
            className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-md border border-linea bg-superficie text-xs font-mono"
          >
            <span className={`w-2 h-2 rounded-full ${backendOk === null ? "bg-yellow-400 animate-pulse" : backendOk ? "bg-green-500" : "bg-red-500 animate-pulse"}`} />
            <span className="text-tinta-3 hidden lg:inline">{backendOk === null ? "..." : backendOk ? "Online" : "Offline"}</span>
          </div>
          <Button
            data-testid="dark-mode-toggle"
            onClick={() => setDarkMode(!darkMode)}
            variant="outline"
            size="icon"
            className="h-9 w-9 sm:h-10 sm:w-10 border-linea hover:bg-linea"
            title={darkMode ? "Modo claro" : "Modo oscuro"}
          >
            {darkMode ? <Sun size={15} /> : <Moon size={15} />}
          </Button>
          <Button
            data-testid="test-telegram-btn"
            onClick={testTelegram}
            variant="outline"
            size="icon"
            className="hidden sm:flex h-9 w-9 sm:h-10 sm:w-10 border-linea hover:bg-linea"
            title="Probar Telegram"
          >
            <TelegramLogo size={15} />
          </Button>
          {/* User + logout */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-linea bg-superficie text-xs font-mono text-tinta-3">
            <User size={13} />
            <span className="hidden md:inline">{user}</span>
            <button onClick={logout} title="Cerrar sesión" className="ml-1 hover:text-red-500 transition-colors">
              <SignOut size={13} />
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
