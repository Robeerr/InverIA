# InverIA - Plataforma de Análisis Bursátil con IA

## Problema original (verbatim)
"Creame una aplicacion web para inversiones, donde yo escriba una accion y me des informacion de ella, con un dashboard profesional y sobre todo quiero saber puntos de venta y compra, sobre todo por niveles en venta y compra, nose si podras hacer eso, tendrias quey analizar los graficos, y darme recomendacion de compra o no investigando y haciendo analisis EN VIVO, es decir, con precios actuales y etc..."

## User Choices (Feb 2026)
- Mercado: Acciones de EE.UU. (NASDAQ/NYSE)
- Datos: Yahoo Finance (yfinance) — sin API key
- IA: GPT-5.2, Claude Sonnet 4.5, Gemini 3 Flash — selector en UI, vía Emergent LLM Key universal
- Indicadores: avanzados + patrones gráficos
- Features extra: watchlist + alertas

## Arquitectura
- **Backend**: FastAPI + MongoDB (motor). Modulos: market_data (yfinance), indicators (pandas/numpy: RSI, MACD, Bollinger, SMA, EMA, Fibonacci, soporte/resistencia, patrones), ai_analysis (emergentintegrations LlmChat). Todos los endpoints bajo `/api`.
- **Frontend**: React 19 + Tailwind + Shadcn UI + Recharts + @phosphor-icons/react. Tipografía Manrope (headings) + IBM Plex Sans/Mono. Paleta "Organic & Earthy" (verde bosque #1A3A32, sand #F5F3EF, moss #4A7C59, terracotta #D85C41).

## Personas de usuario
- Trader retail / inversor activo que busca recomendaciones accionables con niveles operativos.
- Aprendiz que quiere ver indicadores técnicos explicados con IA.

## Requisitos centrales (estáticos)
- Búsqueda por ticker con datos en vivo.
- Gráfico interactivo con niveles SL/TP/entry/soportes/resistencias superpuestos.
- Recomendación IA con confianza, R/R, horizonte, riesgos, catalizadores.
- 13 indicadores técnicos + patrones detectados.
- Watchlist + alertas de precio + populares.

## Implementado (2026-02-04 / 2026-02-05 / 2026-06-05)
- ✅ Endpoints: `/api/quote`, `/api/chart`, `/api/indicators`, `/api/news`, `/api/analyze`, `/api/watchlist` CRUD, `/api/alerts` CRUD, `/api/market/popular`
- ✅ Análisis IA con los 3 modelos (GPT-5.2, Claude Sonnet 4.5, Gemini 3 Flash) devolviendo JSON estructurado
- ✅ Dashboard completo en español
- ✅ Auto-refresh de quote cada 30s
- ✅ **Iteración 2 (2026-02-05)**: Sección prominente "Niveles de Compra y Venta", consenso analistas Finnhub, sentimiento Alpha Vantage, backtest de niveles, comparador multi-acción, historial de análisis IA, alertas por email vía Resend con worker en background
- ✅ Testing: 30/30 backend tests pasados, frontend completo verificado
- ✅ **Iteración 3 (2026-06-05) — Resiliencia en Render cloud**:
  - Migración de Yahoo Finance → **Finnhub como fuente PRIMARIA** para quotes (no IP-blocked en cloud providers)
  - **Yahoo direct chart API + Stooq** como fallbacks en cascada para histórico OHLC
  - **Rate limiter global Finnhub** (50/min thread-safe) compartido entre `market_data` y `external_data` para no superar el límite free (60/min)
  - **Caché en memoria (TTL 15min)** del histórico por símbolo+timeframe — reduce drásticamente llamadas externas
  - Escáner de oportunidades: **lock async** evita scans concurrentes, devuelve cache previo (o `status: "warming"` la primera vez) en lugar de bloquear ⇒ evita 502/timeouts del proxy
  - **Pre-warm en startup** del escáner en background — cache caliente antes del primer request del usuario
  - Concurrencia oportunidades 8→3 para respetar rate limit
  - Frontend `OpportunitiesView`: auto-retry cada 8s si el backend reporta `status: warming`

- ✅ **Iteración 5 (2026-06-05) — Parser DEGIRO nativo (sin IA)**:
  - Causa raíz: Groq free tier tiene cuotas TPD (tokens/día) que se agotan rápido con PDFs de DEGIRO grandes (93 páginas) → "0 ops + 0 movimientos"
  - Nuevo módulo `degiro_parser.py` con **regex puro** que extrae directamente del formato tabular DEGIRO
  - **Auto-detección DEGIRO**: `is_degiro_transactions()` / `is_degiro_account()` usan el contenido del PDF
  - **ISIN → ticker via Finnhub `/search`** con caché y rate-limiter compartido (US11135F1012 → AVGO, US0231351067 → AMZN, etc.)
  - AI Groq queda como **fallback solo para brokers desconocidos** (Trade Republic, IBKR, etc.)
  - **Resultados con PDFs reales del usuario**:
    - Transactions.pdf (19 pág) → **217 transacciones** en 3-65s (43 tickers únicos resueltos)
    - Account.pdf (93 pág) → **482 cash events** en 13-30s (FEE, DIVIDEND, INTEREST, CONNECTIVITY, WITHDRAWAL, DEPOSIT clasificados)
  - **No consume cuota Groq**, soluciona el bloqueo crítico de hoy

- ✅ **Iteración 6 (2026-06-16) — Optimización de velocidad (backend + frontend)**:
  - **Raíz del problema**: `get_quote()` arrastraba `yfinance.info` (1-3s) en CADA llamada aunque casi siempre solo se necesita el precio; y el worker de señales recorría ~500 símbolos en serie cada 30s, saturando la única CPU del free tier de Render.
  - **Backend**:
    - Nuevo `market_data.get_quote_fast()`: precio SOLO de Finnhub, sin `.info`. Usado en worker, websocket y validación de símbolos (watchlist/alerts).
    - Caché de `.info` (fundamentales) 1h en `market_data` — `.info` ya no se re-descarga intradía.
    - Sesión HTTP global con keep-alive (`requests.Session` + pooling) compartida por `market_data`/`external_data`/`polygon_data`/`fmp_data` — elimina el handshake TLS por llamada.
    - Worker de señales reescrito en 2 fases: Fase 1 trae precios en PARALELO (semáforo 6, Finnhub-only); Fase 2 mantiene la misma lógica de cruce/alertas pero sin red.
    - `/analyze`: `get_quote` + `get_full_indicator_history` movidos al `gather` (antes bloqueaban el event loop ~3-5s); `get_news` también paralelizado.
    - Vectorizados `indicators.support_resistance` (rolling centrado, sin loop) y `market_data.df_to_candles` (sin `iterrows`).
    - **Fix de paso**: el websocket enviaba claves (`current`/`high`/`low`) que no coincidían con las del frontend (`price`/`day_high`/`day_low`) → el precio en vivo no se actualizaba. Corregido.
  - **Frontend**:
    - `React.memo(PriceChart)` + `useMemo` del dominio Y → el gráfico Recharts deja de redibujarse en cada tick del WebSocket.
    - Hook compartido `useSignals()` (react-query) → Dashboard y Calendario comparten caché de `/signals` (antes 3 fetches duplicados). Futuros también vía react-query.
    - Desinstaladas 5 deps sin uso (swr, framer-motion, dayjs, lodash, date-fns) + react-day-picker + `ui/calendar.jsx` muerto.
    - Fuentes: quitada la precarga de Inter (no se usaba) y el `@import` bloqueante; Manrope/IBM Plex ahora vía `<link>` en `index.html`.
    - `useMemo` en `visible`/counts de SignalsView; health-check de Header 60s→120s.

## Backlog (P0/P1/P2)
- **P1**: Cache de sentiment de Alpha Vantage (25/día limit) por ~6h
- **P1**: Validación de niveles en backtest (entry_min < entry_max, etc.)
- **P1**: Verificar parsing de Cash Events DEGIRO (fees, dividendos, FX) en producción Render
- **P2**: Lifespan handlers FastAPI (en vez de @app.on_event deprecated)
- **P2**: Modo dark (ya implementado parcialmente — refinar)
- **P2**: Internacionalización (ES/EN)
- **P2**: Integración Stripe (suscripción Pro con análisis premium ilimitados)
- **P2**: Verificar dominio propio en Resend para enviar emails a cualquier destinatario
- **P2**: Refactor `opportunities.py` con caché persistente en Mongo (sobrevive reinicios)

## Próximos pasos
- Usuario hace **Save to GitHub** → trigger redeploy en Render + Vercel
- Validar logs de Render: deben desaparecer los `HTTP 401 Invalid Crumb` de Yahoo
- Recibir feedback del usuario sobre la primera versión
- Priorizar features según uso real
