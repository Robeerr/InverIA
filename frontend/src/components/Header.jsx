import React from "react";
import { Search, Moon, Sun, Send, Menu, LogOut } from "lucide-react";
import { RailCajon } from "./Rail";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { tituloDePagina } from "../lib/titulo";

// Botón de icono de la barra: sin caja hasta que pasas por encima. 44 px en móvil
// (diana táctil), 36 px con puntero fino.
const ICONO =
  "h-11 w-11 sm:h-9 sm:w-9 shrink-0 rounded-[9px] text-tinta-2 hover:text-tinta hover:bg-tinta/[0.06] " +
  "active:scale-[0.96] transition-[color,background-color,transform] duration-150 ease-salida " +
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

  // El nombre de la pantalla, del mismo sitio que el título de la pestaña.
  const pantalla = tituloDePagina(location.pathname).replace(/\s*·\s*InverIA$/, "");
  const inicial = (user || "?").toString().trim().charAt(0).toUpperCase() || "?";

  return (
    <header
      data-testid="app-header"
      className="sticky top-0 z-30 bg-[var(--vidrio)] backdrop-blur-xl backdrop-saturate-150 border-b border-suave"
    >
      {/* Barra superior de vidrio. A la izquierda dónde estás, en el centro buscar, a
          la derecha estado y cuenta. La navegación vive en el rail (o en su cajón). */}
      <div className="mx-auto px-3 sm:px-6 h-14 flex items-center gap-2 sm:gap-4">
        <Button
          onClick={() => setMenuOpen(true)}
          variant="ghost"
          size="icon"
          aria-label="Abrir menú"
          className={`lg:hidden ${ICONO} -ml-1`}
        >
          <Menu size={19} strokeWidth={1.75} />
        </Button>

        <p className="hidden lg:block shrink-0 text-[14px] font-semibold tracking-[-0.015em] text-tinta min-w-0 truncate max-w-[22ch]">
          {pantalla}
        </p>

        {/* Buscador. Con suelo de 200px solo desde `lg`: en un móvil de 390px el
            suelo expulsaría la hamburguesa fuera de la pantalla. */}
        {showSearch && (
          <div ref={searchRef} className="flex-1 relative min-w-0 lg:min-w-[200px] lg:max-w-[460px] lg:mx-auto">
            <form onSubmit={submit} className="relative" role="search">
              <label htmlFor="busqueda-valor" className="sr-only">Buscar valor por ticker o nombre</label>
              <Search size={16} strokeWidth={1.75} aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-tinta-3" />
              <Input
                id="busqueda-valor"
                data-testid="stock-search-input"
                value={query}
                onChange={(e) => setQuery(e.target.value.toUpperCase())}
                onFocus={() => { if (suggestions.length) setShowSug(true); }}
                placeholder="Buscar ticker o empresa"
                className="pl-9 h-10 sm:h-9 rounded-[10px] bg-tinta/[0.04] border-suave text-[14px] sm:text-[13.5px] text-tinta
                           placeholder:text-tinta-3 hover:border-medio"
                autoComplete="off"
              />
            </form>
            {/* Desplegable: filas compactas, ticker en mono, nombre en segundo plano. */}
            {showSug && suggestions.length > 0 && (
              <div className="absolute z-50 left-0 right-0 mt-2 bg-superficie border border-medio
                              rounded-[12px] shadow-flotante overflow-hidden
                              max-h-80 overflow-y-auto overscroll-contain p-1
                              motion-safe:animate-in motion-safe:fade-in-0 motion-safe:zoom-in-[0.98] motion-safe:duration-150">
                {suggestions.map((s) => (
                  <button
                    key={s.symbol}
                    type="button"
                    onClick={() => pick(s.symbol)}
                    className="w-full flex items-baseline gap-3 px-2.5 h-10 items-center text-left rounded-[8px]
                               hover:bg-tinta/[0.06] focus-visible:bg-tinta/[0.06]"
                  >
                    <span className="font-mono font-medium text-[13px] text-tinta shrink-0 min-w-[4.5rem]">{s.symbol}</span>
                    <span className="text-apoyo text-tinta-2 truncate min-w-0">{s.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Acciones. Lo único que puede pedir atención aquí es «Offline», y por eso es
            lo único que se enseña en rojo y con palabra también en móvil. */}
        <div className="flex items-center gap-0.5 sm:gap-1 shrink-0 ml-auto lg:ml-0">
          {/* Status indicator */}
          <div
            role="status"
            title={backendOk === null ? "Comprobando backend..." : backendOk ? "Backend activo ✓" : "Backend no responde"}
            className={`flex items-center gap-2 h-8 px-2 sm:px-2.5 rounded-full text-[12px] font-medium ${
              backendOk === false ? "text-baja bg-baja/10" : "text-tinta-3 lg:bg-tinta/[0.04]"
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
            {darkMode ? <Sun size={17} strokeWidth={1.75} /> : <Moon size={17} strokeWidth={1.75} />}
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
            <Send size={16} strokeWidth={1.75} />
          </Button>

          {/* Cuenta: avatar con la inicial y salir. */}
          <div className="hidden sm:flex items-center gap-1 pl-2 ml-1.5 border-l border-suave">
            <span className="flex items-center gap-2 pl-1 pr-1 min-w-0" title={user}>
              <span aria-hidden="true"
                    className="grid place-items-center h-7 w-7 rounded-full bg-marca/15 text-marca text-[12px] font-semibold
                               ring-1 ring-inset ring-marca/25">
                {inicial}
              </span>
              <span className="hidden md:inline truncate max-w-[12ch] text-[13px] font-medium text-tinta-2">{user}</span>
            </span>
            <button
              onClick={logout}
              title="Cerrar sesión"
              aria-label="Cerrar sesión"
              className="inline-flex items-center justify-center h-9 w-9 rounded-[9px] text-tinta-3
                         hover:text-baja hover:bg-baja/10"
            >
              <LogOut size={16} strokeWidth={1.75} />
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
