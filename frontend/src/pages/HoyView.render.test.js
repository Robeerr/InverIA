import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockHoyData = {
  generado_en: new Date().toISOString(),
  saludo: { piezas: ["1 alerta saltada", "2 niveles cerca"] },
  importa_hoy: [
    { tipo: "ruptura", symbol: "MSFT", nombre: "Microsoft", ruta: "/accion/MSFT",
      que_pasa: "MSFT acaba de perder su media de 10 semanas", por_que: "Cotiza por debajo.",
      que_vigilar: "Decide si la regla de salida aplica.",
      datos: { sma_10w: 412.5, distancia_pct: -3.2, acciones: 20, pnl_eur: -540.25, tiene_posicion: true } },
    { tipo: "alerta", symbol: "INTC", nombre: "Intel", ruta: "/accion/INTC",
      que_pasa: "INTC: se ha disparado tu alerta de compra en 30.00", por_que: "El precio la ha tocado.",
      que_vigilar: "Toca decidir si actúas.",
      datos: { target: 30, price: 29.9, accion: "COMPRA", nivel: "nivel2", fired_at: new Date().toISOString() } },
    { tipo: "nivel", symbol: "NVDA", nombre: "NVIDIA", ruta: "/accion/NVDA",
      que_pasa: "NVDA está a un 1.8% de tu Nivel 3", por_que: "Motor de niveles: zona de fuerza 78/100 · SMA200 + Fib.",
      que_vigilar: "Precio 120.00 contra 118.00",
      datos: { price: 120, target: 118, distancia_pct: 1.8, nivel: "nivel3", accion: "COMPRA",
        fuerza: 78, razones: ["SMA200", "Fib 38.2%"], tiene_posicion: false, motor_niveles: "confirma" } },
    { tipo: "divergencia", symbol: "TSLA", nombre: "Tesla", ruta: "/accion/TSLA",
      que_pasa: "Tus fuentes empujan TSLA y no está en tendencia alcista", por_que: "5 menciones, 4 en positivo.",
      que_vigilar: "Desconfía del entusiasmo.",
      datos: { menciones: 5, positivos: 4, negativos: 1, fuentes: ["A", "B", "C"], estado: "CHOQUE", tiene_posicion: false } },
    { tipo: "resultados", symbol: "AAPL", nombre: "Apple", ruta: "/accion/AAPL",
      que_pasa: "AAPL presenta resultados en 2 días", por_que: "Tienes 10 acciones.",
      que_vigilar: "Decide antes de la publicación.",
      datos: { fecha: new Date(Date.now() + 2 * 86400000).toISOString(), dias: 2, acciones: 10, pnl_eur: 320,
        sorpresas: { supera: 7, total: 8 } } },
  ],
  cartera: { valor_eur: 45230.55, latente_eur: -820.4, realizado_eur: 1250, invertido_eur: 44000,
    posiciones_sin_valorar: 1,
    atencion: [{ symbol: "MSFT", motivo: "en pérdidas", pct: -12.3, pnl_eur: -540.25 }] },
  mercado: { light: "verde", label: "Mercado sano — señales de compra fiables",
    advice: "Régimen alcista: opera con normalidad.", spy_price: 512.34, sma200: 490.1, sma50: 505.2,
    dist_sma200_pct: 4.5, return_1m_pct: 2.1, above_sma200: true },
  cerebro: { menciones_nuevas: 3, tickers_nuevos: ["AMD", "SMCI"] },
  proximos_7_dias: [
    { symbol: "AAPL", date: new Date(Date.now() + 2 * 86400000).toISOString(), dias: 2, hour: "amc", quarter: 3, year: 2026, eps_estimate: 1.42 },
  ],
};

jest.mock("@/lib/api", () => ({
  api: {
    hoy: jest.fn(() => Promise.resolve(mockHoyData)),
    marketFutures: jest.fn(() => Promise.resolve({ items: [{ symbol: "ES", label: "S&P", change_percent: 0.4 }] })),
    marketSentiment: jest.fn(() => Promise.resolve({ score: 62, label: "Codicia", vix: 14.2, advice: "Cuidado con perseguir precios." })),
    marketHeatmap: jest.fn(() => Promise.resolve({ sectors: [{ symbol: "XLK", sector: "Tecnología", change_percent: 1.2 }] })),
  },
}));

import HoyView from "./HoyView";

function renderHoy() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><HoyView /></MemoryRouter>
    </QueryClientProvider>
  );
}

test("la portada renderiza con cifras reales en todos los tipos de tarjeta", async () => {
  renderHoy();
  // Titular
  await waitFor(() => expect(screen.getByText(/han cruzado tus alertas|ha cruzado tu alerta/)).toBeInTheDocument());
  // Cinta de mercado (régimen + SPY)
  expect(screen.getByText(/Mercado sano/)).toBeInTheDocument();
  expect(screen.getByText("$512.34")).toBeInTheDocument();
  // Tarjetas con lecturas numéricas
  expect(screen.getByTestId("tarjeta-hoy-MSFT")).toBeInTheDocument();
  expect(screen.getByTestId("tarjeta-hoy-NVDA")).toBeInTheDocument();
  expect(screen.getByText("78/100")).toBeInTheDocument(); // fuerza del nivel
  expect(screen.getByText("7/8")).toBeInTheDocument();     // sorpresas de resultados
  // Cartera: valor grande + pérdidas
  expect(screen.getByText(/45\.230,55/)).toBeInTheDocument();
  expect(screen.getByText("-12.30%")).toBeInTheDocument();
  // Agenda + cerebro
  expect(screen.getByText(/BPA \$1\.42/)).toBeInTheDocument();
  expect(screen.getByText("AMD")).toBeInTheDocument();
});
