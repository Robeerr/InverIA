import React from "react";
import { ChartLineUp, MagnifyingGlass, House, CalendarBlank, Lightning, Moon, Sun, TelegramLogo, List, X, Bell, SignOut, User, Brain, Coins } from "@phosphor-icons/react";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Link, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";

// Cada entrada se llama como lo que hay dentro. "Dashboard" montaba la ficha de una
// acción, "Cartera" vivía en /signals y "Ventas" era en realidad el libro de
// operaciones completo, con compras incluidas.
const NAV = [
  { to: "/", label: "Hoy", icon: House, testId: "nav-hoy" },
  { to: "/oportunidades", label: "Oportunidades", icon: Lightning, testId: "nav-opportunities" },
  { to: "/calendario", label: "Calendario", icon: CalendarBlank, testId: "nav-calendar" },
  { to: "/cartera", label: "Cartera", icon: Bell, testId: "nav-signals" },
  { to: "/operaciones", label: "Operaciones", icon: Coins, testId: "nav-ventas" },
  { to: "/track-record", label: "Track record", icon: ChartLineUp, testId: "nav-track-record" },
  { to: "/cerebro", label: "Cerebro", icon: Brain, testId: "nav-brain" },
  // Telegram: setup puntual (conectar / cambiar temas). Fuera del menú para no
  // saturar; sigue accesible por URL directa /telegram cuando haga falta.
];

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
      className="sticky top-0 z-50 bg-fondo/95 backdrop-blur border-b border-linea"
    >
      {/* Main bar */}
      <div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-3 flex items-center gap-3 sm:gap-6">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 shrink-0">
          <div className="w-9 h-9 rounded-md bg-marca flex items-center justify-center text-marca-tinta">
            <ChartLineUp size={20} weight="bold" />
          </div>
          <div className="hidden sm:block">
            <h1 className="font-heading font-bold text-lg leading-none tracking-tight text-tinta">InverIA</h1>
            {/* La coletilla mide ~155px por el `tracking` ancho y es lo que menos
                aporta de toda la barra. Se reserva para 2xl, donde sobra sitio. */}
            <p className="hidden 2xl:block text-[10px] uppercase tracking-[0.2em] text-tinta-3 mt-0.5">Análisis bursátil en vivo</p>
          </div>
          <span className="sm:hidden font-heading font-bold text-lg text-tinta">InverIA</span>
        </Link>

        {/* Desktop nav ─────────────────────────────────────────────────────────
            Solo iconos. Con las siete etiquetas la nav mide ~790px y, sumada al
            logo y a las acciones, no deja sitio al buscador ni siquiera en el
            ancho máximo del contenedor (`max-w-[1480px]`): el campo se quedaba
            en ~110px y se cortaba el placeholder. No hay ningún tamaño de
            pantalla en el que ambas cosas quepan, así que las etiquetas se
            mantienen donde sí caben —el menú móvil— y aquí manda el icono.
            `shrink-0` impide además que la nav se comprima y parta un icono.

            El `title` no es decoración: cuando solo se ve el icono, es la única
            forma de saber a dónde lleva. `aria-label` mantiene el nombre para
            lectores de pantalla en los dos tamaños. */}
        <nav className="hidden lg:flex shrink-0 items-center gap-1 bg-superficie border border-linea rounded-md p-1">
          {NAV.map((n) => {
            const Icon = n.icon;
            const active = location.pathname === n.to;
            return (
              <Link
                key={n.to}
                to={n.to}
                data-testid={n.testId}
                title={n.label}
                aria-label={n.label}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono transition-colors ${
                  active ? "bg-marca text-marca-tinta" : "text-tinta-3 hover:text-tinta"
                }`}
              >
                <Icon size={14} weight="bold" />
              </Link>
            );
          })}
        </nav>

        {/* Search + autocompletado.
            `min-w-[240px]` es el suelo: por debajo, el placeholder se corta y el
            campo deja de decir qué se busca. Antes era `min-w-0`, que permite
            colapsar hasta cero y hacía del buscador el primero en ceder ancho. */}
        {showSearch && (
          <div ref={searchRef} className="flex-1 relative min-w-[240px] xl:min-w-[300px]">
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
        <div className="flex items-center gap-2 shrink-0">
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
          {/* Hamburger */}
          <Button
            onClick={() => setMenuOpen(!menuOpen)}
            variant="outline"
            size="icon"
            className="lg:hidden h-9 w-9 border-linea hover:bg-linea"
          >
            {menuOpen ? <X size={16} /> : <List size={16} />}
          </Button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="lg:hidden border-t border-linea bg-fondo px-4 py-3 space-y-1">
          {NAV.map((n) => {
            const Icon = n.icon;
            const active = location.pathname === n.to;
            return (
              <Link
                key={n.to}
                to={n.to}
                data-testid={n.testId}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-mono transition-colors ${
                  active ? "bg-marca text-marca-tinta" : "text-tinta-3 hover:bg-superficie hover:text-tinta"
                }`}
              >
                <Icon size={16} weight="bold" />
                {n.label}
              </Link>
            );
          })}
          <div className="pt-2 border-t border-linea flex items-center gap-2 flex-wrap">
            <Button onClick={testTelegram} variant="outline" size="icon" className="h-9 w-9 border-linea" title="Probar Telegram">
              <TelegramLogo size={15} />
            </Button>
            {/* Status mobile */}
            <div className="flex items-center gap-1.5 px-2 h-9 rounded-md border border-linea bg-superficie text-xs font-mono">
              <span className={`w-2 h-2 rounded-full ${backendOk === null ? "bg-yellow-400 animate-pulse" : backendOk ? "bg-green-500" : "bg-red-500 animate-pulse"}`} />
              <span className="text-tinta-3">{backendOk === null ? "Comprobando..." : backendOk ? "Backend online" : "Backend offline"}</span>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
