import React from "react";
import { ChartLineUp, MagnifyingGlass, House, Briefcase, CalendarBlank, ClockCounterClockwise, EnvelopeSimple, Lightning, Moon, Sun, TelegramLogo, Crosshair, List, X } from "@phosphor-icons/react";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Button } from "../components/ui/button";
import { Link, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { toast } from "sonner";

const DEFAULT_MODELS = [
  { value: "gpt-oss-120b", label: "GPT-OSS 120B (Gratis · Recomendado)", available: true },
  { value: "gpt-5.2", label: "GPT-5.2 (Premium)", available: true },
];

const NAV = [
  { to: "/", label: "Dashboard", icon: House, testId: "nav-dashboard" },
  { to: "/oportunidades", label: "Oportunidades", icon: Lightning, testId: "nav-opportunities" },
  { to: "/cartera", label: "Cartera", icon: Briefcase, testId: "nav-portfolio" },
  { to: "/calendario", label: "Calendario", icon: CalendarBlank, testId: "nav-calendar" },
  { to: "/signals", label: "Señales", icon: Crosshair, testId: "nav-signals" },
  { to: "/historial", label: "Historial", icon: ClockCounterClockwise, testId: "nav-history" },
];

export default function Header({ symbol, setSymbol, onSearch, model, setModel, showSearch = true, darkMode, setDarkMode }) {
  const [query, setQuery] = React.useState(symbol || "");
  const [models, setModels] = React.useState(DEFAULT_MODELS);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const location = useLocation();

  React.useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  React.useEffect(() => setQuery(symbol || ""), [symbol]);

  React.useEffect(() => {
    api.models().then((d) => {
      const available = (d.models || []).filter((m) => m.available);
      if (available.length > 0) setModels(available);
    }).catch(() => {});
  }, []);

  const submit = (e) => {
    e.preventDefault();
    const s = (query || "").trim().toUpperCase();
    if (s) {
      setSymbol(s);
      onSearch(s);
    }
  };

  const testEmail = async () => {
    try {
      await api.alerts.testEmail();
      toast.success("Email de prueba enviado");
    } catch (e) {
      const detail = e?.response?.data?.detail || "Error al enviar email";
      toast.error(detail, { duration: 12000 });
    }
  };

  const testTelegram = async () => {
    try {
      await api.alerts.testTelegram();
      toast.success("Mensaje de Telegram enviado");
    } catch (e) {
      const detail = e?.response?.data?.detail || "Error al enviar Telegram";
      toast.error(detail, { duration: 12000 });
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
            data-testid="test-email-btn"
            onClick={testEmail}
            variant="outline"
            size="icon"
            className="hidden sm:flex h-9 w-9 sm:h-10 sm:w-10 border-[#e5e0d8] hover:bg-[#e5e0d8]"
            title="Probar email"
          >
            <EnvelopeSimple size={15} />
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
          <Select value={model} onValueChange={setModel}>
            <SelectTrigger
              data-testid="model-selector"
              className="hidden md:flex w-[150px] xl:w-[170px] h-10 bg-white border-[#e5e0d8] text-[#0e1f1a]"
            >
              <SelectValue placeholder="Modelo" />
            </SelectTrigger>
            <SelectContent>
              {models.map((m) => (
                <SelectItem key={m.value} value={m.value} data-testid={`model-option-${m.value}`}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger className="flex-1 min-w-[160px] h-9 bg-white border-[#e5e0d8] text-[#0e1f1a] text-xs">
                <SelectValue placeholder="Modelo" />
              </SelectTrigger>
              <SelectContent>
                {models.map((m) => (
                  <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={testEmail} variant="outline" size="icon" className="h-9 w-9 border-[#e5e0d8]" title="Probar email">
              <EnvelopeSimple size={15} />
            </Button>
            <Button onClick={testTelegram} variant="outline" size="icon" className="h-9 w-9 border-[#e5e0d8]" title="Probar Telegram">
              <TelegramLogo size={15} />
            </Button>
          </div>
        </div>
      )}
    </header>
  );
}
