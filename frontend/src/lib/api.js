import axios from "axios";

const RAW_BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const BACKEND_URL = RAW_BACKEND_URL.replace(/\/+$/, ""); // strip trailing slashes
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API, timeout: 60000 });

// Attach JWT token to every request automatically
client.interceptors.request.use((config) => {
  const token = localStorage.getItem("inveria_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// If 401 → clear token so app redirects to login
client.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem("inveria_token");
      localStorage.removeItem("inveria_user");
      window.location.href = "/";
    }
    return Promise.reject(err);
  }
);

export const api = {
  dashboard: (symbol, timeframe = "1Y") =>
    client.get(`/dashboard/${symbol}`, { params: { timeframe } }).then((r) => r.data),
  quote: (symbol) => client.get(`/quote/${symbol}`).then((r) => r.data),
  chart: (symbol, timeframe = "1Y") =>
    client.get(`/chart/${symbol}`, { params: { timeframe } }).then((r) => r.data),
  indicators: (symbol) => client.get(`/indicators/${symbol}`).then((r) => r.data),
  news: (symbol) => client.get(`/news/${symbol}`).then((r) => r.data),
  analyze: (symbol, model) =>
    client.post(`/analyze`, { symbol, model }, { timeout: 120000 }).then((r) => r.data),
  whyMoving: (symbol, model) =>
    client.get(`/why-moving/${symbol}`, { params: model ? { model } : {}, timeout: 60000 }).then((r) => r.data),
  popular: () => client.get(`/market/popular`).then((r) => r.data),
  analyst: (symbol) => client.get(`/analyst/${symbol}`).then((r) => r.data),
  sentiment: (symbol) => client.get(`/sentiment/${symbol}`).then((r) => r.data),
  backtest: (payload) => client.post(`/backtest`, payload).then((r) => r.data),
  compare: (symbols) => client.post(`/compare`, { symbols }).then((r) => r.data),
  history: (symbol) =>
    client.get(symbol ? `/history/${symbol}` : `/history`).then((r) => r.data),
  opportunities: (refresh = false) =>
    client.get(`/opportunities/daily`, { params: refresh ? { refresh: true } : {} }).then((r) => r.data),
  opportunitiesScreener: (refresh = false) =>
    client.get(`/opportunities/screener`, { params: refresh ? { refresh: true } : {} }).then((r) => r.data),
  marketMovers: () => client.get(`/market/movers`).then((r) => r.data),
  marketFutures: () => client.get(`/market/futures`).then((r) => r.data),
  signals: () => client.get(`/signals`).then((r) => r.data),
  calendar: {
    earnings: (days = 14, symbols = null) =>
      client.get(`/calendar/earnings`, { params: { days, symbols: symbols || undefined } }).then((r) => r.data),
  },
  alerts: {
    create: (payload) => client.post(`/alerts`, payload).then((r) => r.data),
    list: () => client.get(`/alerts`).then((r) => r.data),
    delete: (id) => client.delete(`/alerts/${id}`).then((r) => r.data),
    testTelegram: (grupo) => client.post(`/alerts/test-telegram`, null, { params: grupo ? { grupo } : {} }).then((r) => r.data),
  },
};
