import React, { useState, useEffect } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Header from "./components/Header";
import Dashboard from "./pages/Dashboard";
import HistoryView from "./pages/HistoryView";
import OpportunitiesView from "./pages/OpportunitiesView";
import PortfolioView from "./pages/PortfolioView";
import CalendarView from "./pages/CalendarView";
import SignalsView from "./pages/SignalsView";

function App() {
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

  return (
    <div className="App min-h-screen">
      <BrowserRouter>
        <Toaster position="bottom-right" theme={darkMode ? "dark" : "light"} />
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
          <Route
            path="/"
            element={<Dashboard symbol={symbol} setSymbol={setSymbol} model={model} />}
          />
          <Route path="/oportunidades" element={<div className="max-w-[1480px] mx-auto px-6 py-6"><OpportunitiesView setSymbol={setSymbol} /></div>} />
          <Route path="/cartera" element={<div className="max-w-[1480px] mx-auto px-6 py-6"><PortfolioView setSymbol={setSymbol} /></div>} />
          <Route path="/calendario" element={<div className="max-w-[1480px] mx-auto px-6 py-6"><CalendarView setSymbol={setSymbol} /></div>} />
          <Route path="/signals" element={<div className="max-w-[1480px] mx-auto px-6 py-6"><SignalsView setSymbol={setSymbol} /></div>} />
          <Route path="/historial" element={<div className="max-w-[1480px] mx-auto px-6 py-6"><HistoryView /></div>} />
        </Routes>

        <footer className="border-t border-[#e5e0d8] mt-12 py-6 text-center space-y-2">
          <p className="text-xs text-[#5c6b66]">
            InverIA · Datos en vivo de Yahoo Finance + Finnhub · IA con Groq, OpenAI, Anthropic & Google
          </p>
          <p className="text-[10px] text-[#5c6b66] max-w-2xl mx-auto px-6">
            ⚠️ Solo con fines educativos. Esta aplicación no constituye asesoramiento financiero, fiscal o legal.
            Los análisis son generados por IA y pueden contener errores. Invierte bajo tu propia responsabilidad
            y consulta a un profesional cualificado antes de tomar decisiones reales.
          </p>
        </footer>
      </BrowserRouter>
    </div>
  );
}

export default App;
