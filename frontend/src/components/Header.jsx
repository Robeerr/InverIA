import React from "react";
import { ChartLineUp, MagnifyingGlass, House, CalendarBlank, Lightning, Moon, Sun, TelegramLogo, Crosshair, List, X, Bell, SignOut, User } from "@phosphor-icons/react";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Link, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";

const NAV = [
  { to: "/", label: "Dashboard", icon: House, testId: "nav-dashboard" },
  { to: "/oportunidades", label: "Oportunidades", icon: Lightning, testId: "nav-opportunities" },
  { to: "/calendario", label: "Calendario", icon: CalendarBlank, testId: "nav-calendar" },
  { to: "/signals", label: "Alertas", icon: Bell, testId: "nav-signals" },
];

export default function Header({ symbol, setSymbol, onSearch, showSearch = true, darkMode, setDarkMode }) {
  const { user, logout } = useAuth();
  const [query, setQuery] = React.useState(symbol || "");
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [backendOk, setBackendOk] = React.useState(null); // null=checking, true=ok, false=down
  const location = useLocation();

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
    for (const [grupo, label] of [["ideas_javi", "Cartera"], ["cimientos", "Cimientos"]]) {
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
      className="sticky top-0 z-50 bg-[#f5f3ef]/95 backdrop-blur border-b border-[#e5e0d8]"
    >
      {/* Main bar */}
      <div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-3 flex items-center gap-3 sm:gap-6">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 shrink-0">
          <div className="w-9 h-9 rounded-md bg-[#1a3a32] flex items-center justify-center text-[#f5f3ef]">
            <ChartLineUp size={20} weight="bold" />
          </div>
          <div className="hidden sm:block">
            <h1 className="font-heading font-bold text-lg leading-none tracking-tight text-[#0e1f1a]">InverIA</h1>
            <p className="text-[10px] uppercase tracking-[0.2em] text-[#5c6b66] mt-0.5">Análisis bursátil en vivo</p>
          </div>
          <span className="sm:hidden font-heading font-bold text-lg text-[#0e1f1a]">InverIA</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden lg:flex items-center gap-1 bg-white border border-[#e5e0d8] rounded-md p-1">
          {NAV.map((n) => {
            const Icon = n.icon;
            const active = location.pathname === n.to;
            return (
              <Link
                key={n.to}
                to={n.to}
                data-testid={n.testId}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-mono transition-colors ${
                  active ? "bg-[#1a3a32] text-[#f5f3ef]" : "text-[#5c6b66] hover:text-[#0e1f1a]"
                }`}
              >
                <Icon size={14} weight="bold" />
                {n.label}
              </Link>
            );
          })}
        </nav>

        {/* Search */}
        {showSearch && (
          <form onSubmit={submit} className="flex-1 relative min-w-0">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#5c6b66]" />
            <Input
              data-testid="stock-search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value.toUpperCase())}
              placeholder="Ticker (ej: AAPL)"
              className="pl-9 h-10 bg-white border-[#e5e0d8] font-mono text-sm placeholder:text-[#5c6b66] focus-visible:ring-[#1a3a32]"
            />
          </form>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Status indicator */}
          <div
            title={backendOk === null ? "Comprobando backend..." : backendOk ? "Backend activo ✓" : "Backend no responde"}
            className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-md border border-[#e5e0d8] bg-white text-xs font-mono"
          >
            <span className={`w-2 h-2 rounded-full ${backendOk === null ? "bg-yellow-400 animate-pulse" : backendOk ? "bg-green-500" : "bg-red-500 animate-pulse"}`} />
            <span className="text-[#5c6b66] hidden lg:inline">{backendOk === null ? "..." : backendOk ? "Online" : "Offline"}</span>
          </div>
          <Button
            data-testid="dark-mode-toggle"
            onClick={() => setDarkMode(!darkMode)}
            variant="outline"
            size="icon"
            className="h-9 w-9 sm:h-10 sm:w-10 border-[#e5e0d8] hover:bg-[#e5e0d8]"
            title={darkMode ? "Modo claro" : "Modo oscuro"}
          >
            {darkMode ? <Sun size={15} /> : <Moon size={15} />}
          </Button>
          <Button
            data-testid="test-telegram-btn"
            onClick={testTelegram}
            variant="outline"
            size="icon"
            className="hidden sm:flex h-9 w-9 sm:h-10 sm:w-10 border-[#e5e0d8] hover:bg-[#e5e0d8]"
            title="Probar Telegram"
          >
            <TelegramLogo size={15} />
          </Button>
          {/* User + logout */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-[#e5e0d8] bg-white text-xs font-mono text-[#5c6b66]">
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
            className="lg:hidden h-9 w-9 border-[#e5e0d8] hover:bg-[#e5e0d8]"
          >
            {menuOpen ? <X size={16} /> : <List size={16} />}
          </Button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="lg:hidden border-t border-[#e5e0d8] bg-[#f5f3ef] px-4 py-3 space-y-1">
          {NAV.map((n) => {
            const Icon = n.icon;
            const active = location.pathname === n.to;
            return (
              <Link
                key={n.to}
                to={n.to}
                data-testid={n.testId}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-mono transition-colors ${
                  active ? "bg-[#1a3a32] text-[#f5f3ef]" : "text-[#5c6b66] hover:bg-white hover:text-[#0e1f1a]"
                }`}
              >
                <Icon size={16} weight="bold" />
                {n.label}
              </Link>
            );
          })}
          <div className="pt-2 border-t border-[#e5e0d8] flex items-center gap-2 flex-wrap">
            <Button onClick={testTelegram} variant="outline" size="icon" className="h-9 w-9 border-[#e5e0d8]" title="Probar Telegram">
              <TelegramLogo size={15} />
            </Button>
            {/* Status mobile */}
            <div className="flex items-center gap-1.5 px-2 h-9 rounded-md border border-[#e5e0d8] bg-white text-xs font-mono">
              <span className={`w-2 h-2 rounded-full ${backendOk === null ? "bg-yellow-400 animate-pulse" : backendOk ? "bg-green-500" : "bg-red-500 animate-pulse"}`} />
              <span className="text-[#5c6b66]">{backendOk === null ? "Comprobando..." : backendOk ? "Backend online" : "Backend offline"}</span>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
