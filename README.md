# 📈 InverIA — Plataforma de Análisis Bursátil con IA

Dashboard profesional de análisis bursátil con datos en vivo y planes operativos (zonas de compra/venta por niveles) generados por IA. Enfoque de inversión por **acumulación a medio/largo plazo**, con Volume Profile real, confluencias técnicas y tesis de inversión.

![Status](https://img.shields.io/badge/status-production-success)
![Stack](https://img.shields.io/badge/stack-React%20%2B%20FastAPI%20%2B%20MongoDB-blue)
![IA](https://img.shields.io/badge/IA-gratis%20(Groq%20%2B%20Gemini)-brightgreen)
![License](https://img.shields.io/badge/uso-educativo-orange)

## ✨ Características

### 🤖 Análisis con IA (botón "Generar análisis")
- **3 modelos gratis** seleccionables: **GPT-OSS 120B** (por defecto), **Llama 3.3 70B** (ambos vía Groq) y **Gemini 2.5 Flash** (Google AI Studio). Modelos premium opcionales (GPT-5.2 / Claude / Gemini Pro) vía Emergent.
- **Fallback automático**: si el modelo elegido falla o agota su límite, reintenta solo con GPT-OSS — nunca te quedas sin análisis.
- **Niveles de acumulación escalonados**: 3 zonas de entrada (óptima / segunda / agresiva profunda hacia el VAL), 3 stop-losses y 3 take-profits. Garantizados y saneados en el servidor (sin NaN, sin objetivos irreales).
- **Volume Profile real** (Polygon.io): POC, Value Area High/Low y High-Volume Nodes de las últimas 250 sesiones.
- **Confluencias automáticas**: los niveles de la IA que coinciden con zonas de alto volumen se marcan como "alta probabilidad".
- **Tesis de inversión**: posición competitiva, rival principal y potencial del sector (3-5 años).
- **Señales de mercado**: insider trading de directivos y historial de earnings (beat rate) vía Finnhub.
- **Riesgos y catalizadores**, análisis técnico detallado, Fibonacci y patrones.

### 📊 Datos y herramientas
- **Datos en vivo** de acciones de EE.UU. (Yahoo Finance, sin API key) con respaldo de Finnhub.
- **Indicadores técnicos**: RSI, MACD, Bollinger, SMA/EMA, Fibonacci, soportes/resistencias por pivotes, patrones gráficos.
- **Fundamentales**: P/E, EPS, Beta, dividend yield, crecimiento de ventas/EPS YoY, rango 52 semanas (con respaldo Finnhub si Yahoo falla).
- **Consenso de analistas** de Wall Street (Finnhub).
- **Gráfico interactivo** con timeframes y niveles de la IA superpuestos.

### 💡 Oportunidades (2 modos)
- **Señales del día**: escaneo con scoring multi-señal (sobreventa, dips, momentum, breakouts) sobre acciones populares.
- **Screener de Crecimiento**: 6 filtros (market cap > $2B, precio > $9, sin dividendo, volumen > 200K, a <20% de máximos 52s, ventas YoY > 20%) sobre un universo curado de ~105 growth stocks, con escaneo en dos fases para ser eficiente.

### 🔔 Alertas (tabla de cartera)
Dos sub-pestañas sobre la misma colección de señales (campo `grupo`):
- **Cartera**: tabla editable con **niveles 1-5 + nivel deseado/venta**, riesgo y posibles ganancias. **Importación desde Excel** (pega tus celdas) y edición en línea.
- **Cimientos**: núcleo de cartera con **niveles de compra escalonados (25→100%)**, divisa, BZ, **caída necesaria** y **distancia a objetivo** calculadas en vivo, nivel de venta/protección y objetivo a 5 años.
- Notificación por **Telegram + email** cuando el precio alcanza un nivel activado, **solo en horario de mercado** (9:30-16:00 ET) y **una vez al día por nivel**.

### 📅 Otros
- **Calendario de earnings** próximos.
- **Login con contraseña** (JWT).
- Endpoints de **comparador**, **backtest** e **historial** de análisis.

## 📦 Stack

- **Frontend**: React 19 + Tailwind CSS + Shadcn UI + Recharts + Phosphor Icons (desplegado en Vercel)
- **Backend**: FastAPI + Motor (MongoDB async) + yfinance + pandas/numpy (desplegado en Render)
- **IA**: Groq (GPT-OSS 120B, Llama 3.3 70B) + Google Gemini 2.5 Flash + emergentintegrations (premium opcional)
- **Datos de mercado**: Yahoo Finance + Finnhub + Polygon.io (Volume Profile) + Alpha Vantage
- **Notificaciones**: Telegram Bot API + Resend (email)
- **Base de datos**: MongoDB Atlas

## 🔑 Variables de entorno

### Backend (`/backend/.env`)
```env
# MongoDB
MONGO_URL=mongodb://localhost:27017      # O tu connection string de MongoDB Atlas
DB_NAME=inveria

# CORS
CORS_ORIGINS=*                           # En producción, la URL de tu frontend

# Login
APP_PASSWORD_HASH=...                    # Hash bcrypt de la contraseña de acceso

# IA — gratis (recomendado)
GROQ_API_KEY=gsk_...                     # https://console.groq.com  (GPT-OSS 120B, Llama 3.3)
GEMINI_API_KEY=...                       # https://aistudio.google.com/apikey  (Gemini 2.5 Flash)

# IA — premium (opcional)
EMERGENT_LLM_KEY=sk-emergent-...         # Universal key de Emergent (GPT-5.2 / Claude / Gemini Pro)

# Datos de mercado
FINNHUB_API_KEY=...                      # https://finnhub.io  (60/min gratis) — analistas, insider, earnings, fundamentales
POLYGON_API_KEY=...                      # https://polygon.io  (gratis) — Volume Profile
ALPHA_VANTAGE_API_KEY=...                # https://www.alphavantage.co  (opcional)

# Notificaciones
TELEGRAM_BOT_TOKEN=...                   # Token del bot de Telegram (@BotFather)
TELEGRAM_CHAT_ID=...                     # Tu chat id de Telegram
RESEND_API_KEY=re_...                    # https://resend.com  (email, opcional)
ALERT_FROM_EMAIL=onboarding@resend.dev   # Remitente (o un dominio verificado en Resend)
ALERT_RECIPIENT_EMAIL=tu@email.com       # Email destino de las alertas
```

> Las claves de IA y de notificaciones son opcionales: la app funciona con cualquier
> subconjunto. Como mínimo necesitas `GROQ_API_KEY` para el análisis y `FINNHUB_API_KEY`
> para analistas/insider/earnings. `GEMINI_API_KEY` y `POLYGON_API_KEY` activan Gemini y
> el Volume Profile respectivamente.

### Frontend (`/frontend/.env`)
```env
REACT_APP_BACKEND_URL=https://tu-backend.onrender.com   # URL del backend desplegado
```

## 🏃 Ejecutar localmente

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Frontend (en otra terminal)
cd frontend
yarn install
yarn start
```

App disponible en `http://localhost:3000`.

## 🌐 Despliegue gratuito 24/7

| Componente | Servicio | Plan gratis |
|---|---|---|
| Frontend | **Vercel** | ♾️ ilimitado |
| Backend | **Render** | 750h/mes |
| Base de datos | **MongoDB Atlas** | 512MB |

### 1️⃣ MongoDB Atlas
1. Crea cuenta en https://www.mongodb.com/cloud/atlas/register
2. Crea un cluster **M0 Free** (512MB) y un usuario con contraseña
3. En **Network Access**, añade `0.0.0.0/0`
4. **Database → Connect → Drivers** → copia el connection string

### 2️⃣ Backend en Render
1. **New + → Web Service** → conecta el repo `InverIA`
2. Configuración:
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
3. Añade las **Environment Variables** del backend
4. Deploy → copia la URL pública (`https://inveria-backend.onrender.com`)

### 3️⃣ Frontend en Vercel
1. **Add New → Project** → importa el repo `InverIA`
2. Configuración:
   - **Framework Preset**: Create React App
   - **Root Directory**: `frontend`
   - **Build Command**: `yarn build`  ·  **Output Directory**: `build`
3. **Environment Variables**: `REACT_APP_BACKEND_URL` = URL del backend
4. Deploy

### 4️⃣ CORS
En Render, pon `CORS_ORIGINS` con tu URL de Vercel y reinicia el backend.

### 5️⃣ Mantenerlo despierto (evitar cold-starts)
El repo incluye un GitHub Action (`.github/workflows/keep-warm.yml`) que hace ping a
`/api/health` cada 5 minutos. También puedes usar [UptimeRobot](https://uptimerobot.com)
apuntando a la misma URL. Esto mantiene vivo el worker de alertas y elimina los arranques en frío.

## 🔧 API endpoints principales

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/api/dashboard/{symbol}` | Quote + chart + indicadores + noticias + analistas (combinado) |
| GET | `/api/quote/{symbol}` | Cotización en vivo |
| GET | `/api/chart/{symbol}?timeframe=1Y` | Histórico OHLC |
| GET | `/api/indicators/{symbol}` | Indicadores técnicos |
| POST | `/api/analyze` | Análisis IA completo (niveles, tesis, Volume Profile, insider, earnings) |
| GET | `/api/analyst/{symbol}` | Consenso Wall Street |
| GET | `/api/opportunities/daily` | Señales del día |
| GET | `/api/opportunities/screener` | Screener de crecimiento |
| GET | `/api/calendar/earnings` | Calendario de earnings |
| GET/POST/PATCH/DELETE | `/api/signals` | Tabla de cartera y alertas por niveles |
| POST | `/api/backtest` | Backtest de niveles |
| POST | `/api/compare` | Comparar varias acciones |
| GET | `/api/history` | Historial de análisis IA |

## ⚠️ Disclaimer

Esta aplicación es **solo con fines educativos**. No constituye asesoramiento financiero, fiscal o legal. Los análisis son generados por IA y pueden contener errores. Invierte bajo tu propia responsabilidad y consulta a un profesional cualificado antes de tomar decisiones reales.

## 📄 Licencia

Uso personal / educativo. No redistribuir comercialmente sin permiso.

---

Hecho con ☕ y 📈
