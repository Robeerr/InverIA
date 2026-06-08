# 📈 InverIA - Plataforma de Análisis Bursátil con IA

Dashboard profesional de análisis bursátil con datos en vivo de Yahoo Finance y recomendaciones de compra/venta generadas por IA (Groq gratis o modelos premium).

![Status](https://img.shields.io/badge/status-production-success)
![Stack](https://img.shields.io/badge/stack-React%20%2B%20FastAPI%20%2B%20MongoDB-blue)
![License](https://img.shields.io/badge/uso-educativo-orange)

## ✨ Características

- 📊 **Datos en vivo** de acciones de EE.UU. (Yahoo Finance, sin API key)
- 🤖 **5 modelos de IA** seleccionables — 2 gratis (Groq) + 3 premium (GPT-5.2 / Claude / Gemini)
- 🎯 **Niveles operativos detallados**: 3 zonas de entrada (conservadora/moderada/agresiva), 3 stop losses, 3 take profits
- 📉 **13 indicadores técnicos**: RSI, MACD, Bollinger, SMA/EMA, Fibonacci, soportes/resistencias por pivotes, patrones gráficos
- 👥 **Consenso de analistas** Wall Street (Finnhub)
- 💡 **Oportunidades del Día**: escaneo automático de 53 acciones con scoring multi-señal
- ⚖️ **Comparador multi-acción** lado a lado
- 🧪 **Backtest** de los niveles sugeridos sobre datos históricos
- 📚 **Historial** de análisis IA guardados
- 📧 **Alertas por email** via Resend con worker en background
- 🌟 **Watchlist** personalizada

## 🚀 Despliegue gratuito (recomendado)

Para tener la app online 24/7 gratis para siempre:

| Componente | Servicio | Plan gratis |
|---|---|---|
| Frontend | **Vercel** | ♾️ ilimitado |
| Backend | **Render** o **Railway** | 750h/mes |
| Base de datos | **MongoDB Atlas** | 512MB |

Pasos resumidos: ver sección [Despliegue paso a paso](#-despliegue-paso-a-paso).

## 📦 Stack

- **Frontend**: React 19 + Tailwind CSS + Shadcn UI + Recharts + Phosphor Icons
- **Backend**: FastAPI + Motor (MongoDB async) + yfinance + pandas/numpy
- **IA**: Groq (Llama 3.3 70B, GPT-OSS 120B) + emergentintegrations (GPT-5.2, Claude, Gemini)
- **Email**: Resend
- **Datos**: Yahoo Finance + Finnhub + Alpha Vantage

## 🔑 Variables de entorno requeridas

### Backend (`/backend/.env`)
```env
# MongoDB
MONGO_URL=mongodb://localhost:27017      # O tu connection string de MongoDB Atlas
DB_NAME=inveria

# CORS
CORS_ORIGINS=*

# AI - Groq (gratis, recomendado)
GROQ_API_KEY=gsk_...                     # https://console.groq.com

# AI - Modelos premium (opcional)
EMERGENT_LLM_KEY=sk-emergent-...          # Universal key de Emergent (opcional)

# Datos de mercado
ALPHA_VANTAGE_API_KEY=...                 # https://www.alphavantage.co (25/día gratis)
FINNHUB_API_KEY=...                       # https://finnhub.io (60/min gratis)

# Email (alertas)
RESEND_API_KEY=re_...                     # https://resend.com
SENDER_EMAIL=onboarding@resend.dev        # O un email de un dominio verificado
ALERT_RECIPIENT_EMAIL=tu@email.com        # Email destino de las alertas
```

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

## 🌐 Despliegue paso a paso

### 1️⃣ MongoDB Atlas (base de datos gratis)
1. Crea cuenta en https://www.mongodb.com/cloud/atlas/register
2. Crea un cluster **M0 Free** (512MB)
3. Crea un usuario con contraseña
4. En **Network Access**, añade `0.0.0.0/0` (acceso desde cualquier IP)
5. En **Database** → **Connect** → **Drivers** → copia el connection string:
   ```
   mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```

### 2️⃣ Backend en Render (gratis 750h/mes)
1. Crea cuenta en https://render.com (puedes usar GitHub login)
2. **New +** → **Web Service** → conecta el repo `InverIA`
3. Configuración:
   - **Name**: `inveria-backend`
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. **Environment Variables** → añade todas las del backend (.env)
   - `MONGO_URL`: el connection string de Atlas
   - `DB_NAME`: `inveria`
   - El resto de keys (Groq, Finnhub, Alpha Vantage, Resend)
5. **Deploy**
6. Cuando termine, copia la URL pública (tipo `https://inveria-backend.onrender.com`)

### 3️⃣ Frontend en Vercel (gratis ilimitado)
1. Crea cuenta en https://vercel.com (con GitHub login)
2. **Add New** → **Project** → importa repo `InverIA`
3. Configuración:
   - **Framework Preset**: Create React App
   - **Root Directory**: `frontend`
   - **Build Command**: `yarn build`
   - **Output Directory**: `build`
4. **Environment Variables**:
   - `REACT_APP_BACKEND_URL`: URL del backend de Render (paso 2)
5. **Deploy**
6. Tu app estará en `https://inveria-tuusuario.vercel.app`

### 4️⃣ Conectar Frontend con Backend (CORS)
En Render, edita `CORS_ORIGINS` y pon tu URL de Vercel:
```
CORS_ORIGINS=https://inveria-tuusuario.vercel.app
```
Reinicia el backend.

### ✅ ¡Listo!
Comparte la URL de Vercel con tus amigos. 100% gratis para siempre.

## 🔧 API endpoints principales

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/api/quote/{symbol}` | Cotización en vivo |
| GET | `/api/chart/{symbol}?timeframe=1Y` | Histórico OHLC |
| GET | `/api/indicators/{symbol}` | Indicadores técnicos |
| POST | `/api/analyze` | Análisis IA completo |
| GET | `/api/analyst/{symbol}` | Consenso Wall Street |
| GET | `/api/opportunities/daily` | Oportunidades del día |
| POST | `/api/backtest` | Backtest de niveles |
| POST | `/api/compare` | Comparar varias acciones |
| GET | `/api/history` | Historial de análisis |
| GET/POST/DELETE | `/api/watchlist` | Gestión de watchlist |
| GET/POST/DELETE | `/api/alerts` | Gestión de alertas |

## ⚠️ Disclaimer

Esta aplicación es **solo con fines educativos**. No constituye asesoramiento financiero, fiscal o legal. Los análisis son generados por IA y pueden contener errores. Invierte bajo tu propia responsabilidad y consulta a un profesional cualificado antes de tomar decisiones reales.

## 📄 Licencia

Uso personal / educativo. No redistribuir comercialmente sin permiso.

---

Hecho con ☕ y 📈 sobre [Emergent](https://emergent.sh).
