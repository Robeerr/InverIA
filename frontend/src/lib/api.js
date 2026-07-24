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
  chartist: (symbol, refresh = false) =>
    client.get(`/chartist/${symbol}`, { params: { refresh }, timeout: 90000 }).then((r) => r.data),
  // Solo devuelve el veredicto si ya está pre-calculado (no gasta IA ni espera).
  chartistCached: (symbol) =>
    client.get(`/chartist/${symbol}`, { params: { cached_only: true }, timeout: 15000 }).then((r) => r.data),
  watchlist: {
    symbols: () => client.get(`/watchlist/symbols`).then((r) => r.data),
    add: (symbol) => client.post(`/watchlist`, { symbol }).then((r) => r.data),
    remove: (symbol) => client.delete(`/watchlist/${symbol}`).then((r) => r.data),
  },
  indicators: (symbol) => client.get(`/indicators/${symbol}`).then((r) => r.data),
  news: (symbol) => client.get(`/news/${symbol}`).then((r) => r.data),
  analyze: (symbol, model) =>
    client.post(`/analyze`, { symbol, model }, { timeout: 120000 }).then((r) => r.data),
  whyMoving: (symbol, model) =>
    client.get(`/why-moving/${symbol}`, { params: model ? { model } : {}, timeout: 60000 }).then((r) => r.data),
  popular: () => client.get(`/market/popular`).then((r) => r.data),
  analyst: (symbol) => client.get(`/analyst/${symbol}`).then((r) => r.data),
  sentiment: (symbol) => client.get(`/sentiment/${symbol}`).then((r) => r.data),
  compare: (symbols) => client.post(`/compare`, { symbols }).then((r) => r.data),
  history: (symbol) =>
    client.get(symbol ? `/history/${symbol}` : `/history`).then((r) => r.data),
  opportunities: (refresh = false) =>
    client.get(`/opportunities/daily`, { params: refresh ? { refresh: true } : {} }).then((r) => r.data),
  opportunitiesScreener: (refresh = false) =>
    client.get(`/opportunities/screener`, { params: refresh ? { refresh: true } : {} }).then((r) => r.data),
  marketMovers: () => client.get(`/market/movers`).then((r) => r.data),
  backtest: (symbol, window = 60) =>
    client.get(`/backtest/${symbol}`, { params: { window }, timeout: 120000 }).then((r) => r.data),
  backtestUniverse: (window = 60, limit = 30) =>
    client.get(`/backtest`, { params: { window, limit }, timeout: 300000 }).then((r) => r.data),
  marketFutures: () => client.get(`/market/futures`).then((r) => r.data),
  marketSentiment: () => client.get(`/market/sentiment`).then((r) => r.data),
  marketHeatmap: () => client.get(`/market/heatmap`).then((r) => r.data),
  search: (q) => client.get(`/search`, { params: { q }, timeout: 8000 }).then((r) => r.data),
  radar: (days = 14) => client.get(`/radar`, { params: { days } }).then((r) => r.data),
  brain: () => client.get(`/brain`).then((r) => r.data),
  fuentes: (symbol) => client.get(`/fuentes/${symbol}`).then((r) => r.data),
  alternativa: (symbol) => client.get(`/alternativa/${symbol}`).then((r) => r.data),
  youtubeIngest: (url) => client.post(`/youtube/ingest`, { url }, { timeout: 300000 }).then((r) => r.data),
  ingestText: (text, fuente) => client.post(`/ingest/text`, { text, fuente }, { timeout: 120000 }).then((r) => r.data),
  trackRecord: (days = 180, refresh = false) =>
    client.get(`/track-record`, { params: { days, refresh: refresh || undefined }, timeout: 120000 }).then((r) => r.data),
  telegram: {
    status: (token) => client.get(`/telegram/status`, { params: { token } }).then((r) => r.data),
    loginStart: (token, phone) => client.post(`/telegram/login/start`, { phone }, { params: { token }, timeout: 60000 }).then((r) => r.data),
    loginCode: (token, code, password) => client.post(`/telegram/login/code`, { code, password }, { params: { token }, timeout: 60000 }).then((r) => r.data),
    dialogs: (token) => client.get(`/telegram/dialogs`, { params: { token }, timeout: 60000 }).then((r) => r.data),
    setCapture: (token, chat_ids) => client.post(`/telegram/capture`, { chat_ids }, { params: { token } }).then((r) => r.data),
  },
  signals: () => client.get(`/signals`).then((r) => r.data),
  signalsCreate: (payload) => client.post(`/signals`, payload).then((r) => r.data),
  portfolioCorrelation: () => client.get(`/portfolio/correlation`, { timeout: 60000 }).then((r) => r.data),
  calendar: {
    earnings: (days = 14, symbols = null, refresh = false) =>
      client.get(`/calendar/earnings`, { params: { days, symbols: symbols || undefined, refresh: refresh || undefined } }).then((r) => r.data),
  },
  alerts: {
    create: (payload) => client.post(`/alerts`, payload).then((r) => r.data),
    list: () => client.get(`/alerts`).then((r) => r.data),
    delete: (id) => client.delete(`/alerts/${id}`).then((r) => r.data),
    testTelegram: (grupo) => client.post(`/alerts/test-telegram`, null, { params: grupo ? { grupo } : {} }).then((r) => r.data),
  },
};
