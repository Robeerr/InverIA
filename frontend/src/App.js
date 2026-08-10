import React, { useState, useEffect, Suspense } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
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

const PageLoader = () => (
  <div className="min-h-[60vh] flex items-center justify-center">
    <div className="w-8 h-8 rounded-lg bg-[#1a3a32] animate-pulse flex items-center justify-center">
      <span className="text-[#f5f3ef] font-bold text-sm">I</span>
    </div>
  </div>
);

function AppInner() {
  const { isAuth, loading } = useAuth();
  const [symbol, setSymbol] = useState("AAPL");
  const [model, setModel] = useState(() => localStorage.getItem("inveria-model-v3") || "gemini-2.5-flash");

  useEffect(() => {
    localStorage.setItem("inveria-model-v3", model);
  }, [model]);
  const [darkMode, setDarkMode] = useState(() => {
    return localStorage.getItem("inveria-dark") === "1";
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
        setSymbol={setSymbol}
        onSearch={setSymbol}
        darkMode={darkMode}
        setDarkMode={setDarkMode}
      />
      <ErrorBoundary>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Dashboard symbol={symbol} setSymbol={setSymbol} model={model} setModel={setModel} />} />
          <Route path="/oportunidades" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><OpportunitiesView setSymbol={setSymbol} /></div>} />
          <Route path="/calendario" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><CalendarView setSymbol={setSymbol} /></div>} />
          <Route path="/signals" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><SignalsView setSymbol={setSymbol} /></div>} />
          <Route path="/radar" element={<Navigate to="/oportunidades" replace />} />
          <Route path="/ventas" element={<VentasView />} />
          <Route path="/track-record" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><TrackRecordView /></div>} />
          <Route path="/telegram" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><TelegramConnectView /></div>} />
          <Route path="/cerebro" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><BrainView /></div>} />
          <Route path="/diagnostico" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><DiagnosticoView /></div>} />
          {/* Sin wrapper: EstilosView trae su propio PageShell, que es justamente
              el componente que sustituye a este div copiado ocho veces. */}
          <Route path="/sistema/estilos" element={<EstilosView />} />
          <Route path="*" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><Dashboard symbol={symbol} setSymbol={setSymbol} model={model} setModel={setModel} /></div>} />
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
