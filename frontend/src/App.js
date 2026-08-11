import React, { useState, useEffect, useCallback, Suspense } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useParams } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Header from "./components/Header";
import ErrorBoundary from "./components/ErrorBoundary";
import LoginPage from "./pages/LoginPage";

const Dashboard        = React.lazy(() => import("./pages/Dashboard"));
const OpportunitiesView = React.lazy(() => import("./pages/OpportunitiesView"));
const CalendarView     = React.lazy(() => import("./pages/CalendarView"));
const SignalsView      = React.lazy(() => import("./pages/SignalsView"));
const TrackRecordView  = React.lazy(() => import("./pages/TrackRecordView"));
const VentasView       = React.lazy(() => import("./pages/VentasView"));
const TelegramConnectView = React.lazy(() => import("./pages/TelegramConnectView"));
const BrainView        = React.lazy(() => import("./pages/BrainView"));
const DiagnosticoView  = React.lazy(() => import("./pages/DiagnosticoView"));
// Página de estilos viva: la validación de la Fase 1. Va bajo /sistema/ porque es
// una herramienta de desarrollo, no una sección del producto.
const EstilosView      = React.lazy(() => import("./pages/EstilosView"));
const HoyView          = React.lazy(() => import("./pages/HoyView"));

const PageLoader = () => (
  <div className="min-h-[60vh] flex items-center justify-center">
    <div className="w-8 h-8 rounded-lg bg-[#1a3a32] animate-pulse flex items-center justify-center">
      <span className="text-[#f5f3ef] font-bold text-sm">I</span>
    </div>
  </div>
);

/* La acción vive en la URL, no solo en el estado.
   ─────────────────────────────────────────────────────────────────────────────
   Antes el ticker solo existía en un useState, con dos consecuencias: no se podía
   guardar ni compartir el enlace de una acción concreta, y pulsar un ticker en la
   Cartera o en el Radar cambiaba el estado sin llevarte a ninguna parte —parecía
   un enlace roto porque, a efectos prácticos, lo era.

   Este componente sincroniza el parámetro de la URL con el estado de la app, para
   que ambos sentidos funcionen: escribir /accion/NVDA a mano y pulsar un ticker. */
function PaginaAccion({ symbol, setSymbol, sincronizar, model, setModel }) {
  const { symbol: symbolUrl } = useParams();

  // Sincroniza el ESTADO desde la URL, y para eso usa el setter puro — no `setSymbol`,
  // que aquí es `irAAccion` y además NAVEGA.
  //
  // El bug que esto arregla: al pulsar un ticker había un render en el que el estado ya
  // era el nuevo y `symbolUrl` seguía siendo el viejo. Este efecto veía la discrepancia y
  // «sincronizaba» llamando a algo que navega, así que empujaba la URL DE VUELTA a la
  // acción anterior. Cada clic producía dos pushState —el tuyo y el rebote— y la ruta se
  // quedaba donde estaba. Rompía la watchlist y la alternativa sectorial por igual.
  //
  // Un efecto de sincronización no puede navegar. Guardar y navegar son cosas distintas y
  // aquí se habían quedado detrás del mismo nombre.
  useEffect(() => {
    const sym = (symbolUrl || "").toUpperCase();
    if (sym && sym !== symbol) sincronizar(sym);
  }, [symbolUrl, symbol, sincronizar]);

  // Se pinta con el de la URL para que el primer render ya sea el correcto: usar el
  // del estado enseñaría la acción anterior durante un fotograma al navegar.
  return (
    <Dashboard
      symbol={(symbolUrl || symbol || "").toUpperCase()}
      setSymbol={setSymbol}
      model={model}
      setModel={setModel}
    />
  );
}

function AppInner() {
  const { isAuth, loading } = useAuth();
  const navigate = useNavigate();
  const [symbol, setSymbol] = useState("AAPL");
  const [model, setModel] = useState(() => localStorage.getItem("inveria-model-v3") || "gemini-2.5-flash");

  useEffect(() => {
    localStorage.setItem("inveria-model-v3", model);
  }, [model]);
  // Oscuro por defecto: es la identidad de InverIA, no una preferencia. Solo se
  // arranca en claro si TÚ lo elegiste alguna vez — de ahí distinguir "no hay nada
  // guardado" de "guardado como 0", que con el `=== "1"` anterior era lo mismo.
  const [darkMode, setDarkMode] = useState(() => {
    const guardado = localStorage.getItem("inveria-dark");
    return guardado === null ? true : guardado === "1";
  });

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("inveria-dark", "1");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("inveria-dark", "0");
    }
  }, [darkMode]);

  useEffect(() => {
    document.title = symbol ? `${symbol} · InverIA` : "InverIA · Análisis Bursátil";
  }, [symbol]);

  /* Elegir un ticker en cualquier pantalla lleva a su ficha.
     Se pasa con el nombre `setSymbol` a propósito: las ocho pantallas que ya lo
     reciben siguen funcionando sin tocarlas, y de paso quedan arregladas las que
     hasta ahora cambiaban el estado sin navegar. */
  const irAAccion = useCallback((s) => {
    const sym = (s || "").toString().toUpperCase().trim();
    if (!sym) return;
    setSymbol(sym);
    navigate(`/accion/${sym}`);
  }, [navigate]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f5f3ef] flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 rounded-xl bg-[#1a3a32] flex items-center justify-center mx-auto mb-3 animate-pulse">
            <span className="text-[#f5f3ef] font-bold text-lg">I</span>
          </div>
          <p className="text-[#5c6b66] font-mono text-sm">Cargando InverIA...</p>
        </div>
      </div>
    );
  }

  if (!isAuth) return <LoginPage />;

  return (
    <div className="App min-h-screen overflow-x-hidden">
      <Header
        symbol={symbol}
        setSymbol={irAAccion}
        onSearch={irAAccion}
        darkMode={darkMode}
        setDarkMode={setDarkMode}
      />
      <ErrorBoundary>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* La portada. Hasta ahora "/" montaba la ficha de UNA acción, así que
              entrar exigía saber ya qué ticker mirar. */}
          <Route path="/" element={<HoyView />} />

          <Route path="/accion/:symbol" element={
            <PaginaAccion symbol={symbol} setSymbol={irAAccion} sincronizar={setSymbol}
              model={model} setModel={setModel} />
          } />

          <Route path="/oportunidades" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><OpportunitiesView setSymbol={irAAccion} /></div>} />
          <Route path="/calendario" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><CalendarView setSymbol={irAAccion} /></div>} />
          <Route path="/cartera" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><SignalsView setSymbol={irAAccion} /></div>} />
          <Route path="/operaciones" element={<VentasView />} />
          <Route path="/track-record" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><TrackRecordView /></div>} />
          <Route path="/telegram" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><TelegramConnectView /></div>} />
          <Route path="/cerebro" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><BrainView /></div>} />
          <Route path="/diagnostico" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><DiagnosticoView /></div>} />
          {/* Sin wrapper: EstilosView trae su propio PageShell, que es justamente
              el componente que sustituye a este div copiado ocho veces. */}
          <Route path="/sistema/estilos" element={<EstilosView />} />

          {/* Rutas viejas: redirección, no ruptura. Están en tu historial y en tus
              marcadores, y algunas llevan meses ahí. */}
          <Route path="/signals" element={<Navigate to="/cartera" replace />} />
          <Route path="/ventas" element={<Navigate to="/operaciones" replace />} />
          <Route path="/radar" element={<Navigate to="/oportunidades" replace />} />

          {/* Una ruta desconocida ya no cae en la ficha de una acción cualquiera:
              cae en la portada, que es la que sabe qué enseñarte sin contexto. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
      </ErrorBoundary>

      <footer className="border-t border-[#e5e0d8] mt-12 py-6 text-center space-y-2">
        <p className="text-xs text-[#5c6b66]">
          InverIA · Datos en vivo de Yahoo Finance + Finnhub · IA con Groq, OpenAI, Anthropic & Google
        </p>
        <p className="text-[10px] text-[#5c6b66] max-w-2xl mx-auto px-6">
          ⚠️ Solo con fines educativos. Esta aplicación no constituye asesoramiento financiero, fiscal o legal.
        </p>
      </footer>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Toaster position="bottom-right" />
      <AuthProvider>
        <AppInner />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
