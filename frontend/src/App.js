import React, { useState, useEffect } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Header from "./components/Header";
import Dashboard from "./pages/Dashboard";
import OpportunitiesView from "./pages/OpportunitiesView";
import PortfolioView from "./pages/PortfolioView";
import CalendarView from "./pages/CalendarView";
import SignalsView from "./pages/SignalsView";
import AlertHistoryView from "./pages/AlertHistoryView";
import LoginPage from "./pages/LoginPage";

function AppInner() {
  const { isAuth, loading } = useAuth();
  const [symbol, setSymbol] = useState("AAPL");
  const [model, setModel] = useState("gpt-oss-120b");
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
    <div className="App min-h-screen">
      <Header
        symbol={symbol}
        setSymbol={setSymbol}
        onSearch={setSymbol}
        model={model}
        setModel={setModel}
        darkMode={darkMode}
        setDarkMode={setDarkMode}
      />
      <Routes>
        <Route path="/" element={<Dashboard symbol={symbol} setSymbol={setSymbol} model={model} />} />
        <Route path="/oportunidades" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><OpportunitiesView setSymbol={setSymbol} /></div>} />
        <Route path="/cartera" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><PortfolioView setSymbol={setSymbol} /></div>} />
        <Route path="/calendario" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><CalendarView setSymbol={setSymbol} /></div>} />
        <Route path="/signals" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><SignalsView setSymbol={setSymbol} /></div>} />
        <Route path="/alertas" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><AlertHistoryView /></div>} />
        <Route path="*" element={<div className="max-w-[1480px] mx-auto px-4 sm:px-6 py-4 sm:py-6"><Dashboard symbol={symbol} setSymbol={setSymbol} model={model} /></div>} />
      </Routes>

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
