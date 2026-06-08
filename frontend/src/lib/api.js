import axios from "axios";

const RAW_BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const BACKEND_URL = RAW_BACKEND_URL.replace(/\/+$/, ""); // strip trailing slashes
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API, timeout: 60000 });

export const api = {
  models: () => client.get(`/models`).then((r) => r.data),
  quote: (symbol) => client.get(`/quote/${symbol}`).then((r) => r.data),
  chart: (symbol, timeframe = "1Y") =>
    client.get(`/chart/${symbol}`, { params: { timeframe } }).then((r) => r.data),
  indicators: (symbol) => client.get(`/indicators/${symbol}`).then((r) => r.data),
  news: (symbol) => client.get(`/news/${symbol}`).then((r) => r.data),
  analyze: (symbol, model) =>
    client.post(`/analyze`, { symbol, model }).then((r) => r.data),
  popular: () => client.get(`/market/popular`).then((r) => r.data),
  analyst: (symbol) => client.get(`/analyst/${symbol}`).then((r) => r.data),
  sentiment: (symbol) => client.get(`/sentiment/${symbol}`).then((r) => r.data),
  backtest: (payload) => client.post(`/backtest`, payload).then((r) => r.data),
  compare: (symbols) => client.post(`/compare`, { symbols }).then((r) => r.data),
  history: (symbol) =>
    client.get(symbol ? `/history/${symbol}` : `/history`).then((r) => r.data),
  opportunities: (refresh = false) =>
    client.get(`/opportunities/daily`, { params: refresh ? { refresh: true } : {} }).then((r) => r.data),
  portfolio: {
    get: () => client.get(`/portfolio`).then((r) => r.data),
    listTransactions: () => client.get(`/portfolio/transactions`).then((r) => r.data),
    addTransactions: (transactions) =>
      client.post(`/portfolio/transactions`, { transactions }).then((r) => r.data),
    removeTransaction: (id) => client.delete(`/portfolio/transactions/${id}`).then((r) => r.data),
    clearAll: () => client.delete(`/portfolio/transactions`).then((r) => r.data),
    uploadPdf: (file) => {
      const fd = new FormData();
      fd.append("file", file);
      return client.post(`/portfolio/upload-pdf`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 120000,
      }).then((r) => r.data);
    },
    addCashEvents: (events) => client.post(`/portfolio/cash-events`, { events }).then((r) => r.data),
    cashEvents: () => client.get(`/portfolio/cash-events`).then((r) => r.data),
  },
  calendar: {
    earnings: (days = 14, symbols = null) =>
      client.get(`/calendar/earnings`, { params: { days, symbols: symbols || undefined } }).then((r) => r.data),
  },
  watchlist: {
    list: () => client.get(`/watchlist`).then((r) => r.data),
    add: (symbol) => client.post(`/watchlist`, { symbol }).then((r) => r.data),
    remove: (symbol) => client.delete(`/watchlist/${symbol}`).then((r) => r.data),
  },
  alerts: {
    list: () => client.get(`/alerts`).then((r) => r.data),
    add: (payload) => client.post(`/alerts`, payload).then((r) => r.data),
    remove: (id) => client.delete(`/alerts/${id}`).then((r) => r.data),
    testEmail: () => client.post(`/alerts/test-email`).then((r) => r.data),
    testTelegram: () => client.post(`/alerts/test-telegram`).then((r) => r.data),
  },
};
