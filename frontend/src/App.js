import React, { useState, useEffect, useCallback, Suspense } from "react";
import "./App.css";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useParams,
         useLocation, useNavigationType } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Header from "./components/Header";
import Rail, { Sello } from "./components/Rail";
import ErrorBoundary from "./components/ErrorBoundary";
import LoginPage from "./pages/LoginPage";
import { tituloDePagina } from "./lib/titulo";

const Dashboard        = React.lazy(() => import("./pages/Dashboard"));
const OpportunitiesView = React.lazy(() => import("./pages/OpportunitiesView"));
const CalendarView     = React.lazy(() => import("./pages/CalendarView"));
const SignalsView      = React.lazy(() => import("./pages/SignalsView"));
const TrackRecordView  = React.lazy(() => import("./pages/TrackRecordView"));
const VentasView       = React.lazy(() => import("./pages/VentasView"));
const TelegramConnectView = React.lazy(() => import("./pages/TelegramConnectView"));
const BrainView        = React.lazy(() => import("./pages/BrainView"));
const IntelligenceView = React.lazy(() => import("./pages/IntelligenceView"));
const LaboratorioView = React.lazy(() => import("./pages/LaboratorioView"));
const DiagnosticoView  = React.lazy(() => import("./pages/DiagnosticoView"));
// Página de estilos viva: la validación de la Fase 1. Va bajo /sistema/ porque es
// una herramienta de desarrollo, no una sección del producto.
const EstilosView      = React.lazy(() => import("./pages/EstilosView"));
const HoyView          = React.lazy(() => import("./pages/HoyView"));

/* El lienzo de cada pantalla: ancho de lectura cómodo, más aire a los lados en
   escritorio y una entrada corta (6 px, 220 ms) al cambiar de ruta. */
const LIENZO = "max-w-[1440px] mx-auto px-4 sm:px-8 py-5 sm:py-8 iv-entra";

/* Mientras llega el código de una pantalla: su forma, no un spinner. */
const PageLoader = () => (
  <div className="max-w-[1440px] mx-auto px-4 sm:px-8 py-5 sm:py-8" role="status" aria-live="polite">
    <span className="sr-only">Cargando vista</span>
    <div className="iv-esqueleto h-8 w-56 rounded-[10px]" aria-hidden="true" />
    <div className="iv-esqueleto h-4 w-80 max-w-full rounded-md mt-3" aria-hidden="true" />
    <div className="grid gap-4 sm:grid-cols-3 mt-8" aria-hidden="true">
      {[0, 1, 2].map((i) => <div key={i} className="iv-esqueleto h-28 rounded-[16px]" />)}
    </div>
    <div className="iv-esqueleto h-64 rounded-[16px] mt-4" aria-hidden="true" />
  </div>
);

/* La acción vive en la URL, no solo en el estado.
   ─────────────────────────────────────────────────────────────────────────────
   Antes el ticker solo existía en un useState, con dos consecuencias: no se podía
   guardar ni compartir el enlace de una acción concreta, y pulsar un ticker en la
   Cartera o en el Radar cambiaba el estado sin llevarte a ninguna parte —parecía
   un enlace roto porque, a efectos prácticos, lo era.

   Este componente sincroniza el parámetro de la URL con el estado de la app, para
   que ambos sentidos funcionen: escribir /accion/NVDA a mano y pulsar un ticker. */
/* Al cambiar de pantalla, la vista vuelve al principio.
   React Router NO lo hace solo: cambia la ruta y deja el scroll donde estaba. En una
   ficha de acción, que es larga, eso significaba pulsar una alternativa desde el fondo
   de la página y quedarte mirando el fondo de la página siguiente — la cabecera con el
   ticker nuevo estaba dos pantallas más arriba y parecía que no hubiera pasado nada.

   NO se aplica al ir ATRÁS. Ahí el navegador restaura la posición que tenías, y saltar
   al principio destruiría justo lo que esperas: volver donde estabas. Por eso se mira el
   tipo de navegación y se ignora `POP`.

   Salto instantáneo y no suave: un desplazamiento animado de dos pantallas mientras la
   siguiente se monta se ve como un tirón, y encima retrasa la lectura. */
function IrAlPrincipio() {
  const { pathname } = useLocation();
  const tipo = useNavigationType();

  useEffect(() => {
    if (tipo === "POP") return;
    window.scrollTo(0, 0);
  }, [pathname, tipo]);

  return null;
}


function PaginaAccion({ symbol, setSymbol, sincronizar, model, setModel }) {
  const { symbol: symbolUrl } = useParams();

  // Sincroniza el ESTADO desde la URL, y para eso usa el setter puro — no `setSymbol`,
  // que aquí es `irAAccion` y además NAVEGA.
  //
  // El bug que esto arregla: al pulsar un ticker había un render en el que el estado ya
  // era el nuevo y `symbolUrl` seguía siendo el viejo. Este efecto veía la discrepancia y
  // «sincronizaba» llamando a algo que navega, así que empujaba la URL DE VUELTA a la
  // acción anterior. Cada clic producía dos pushState —el tuyo y el rebote— y la ruta se
  // quedaba donde estaba. Rompía la watchlist y la alternativa sectorial por igual.
  //
  // Un efecto de sincronización no puede navegar. Guardar y navegar son cosas distintas y
  // aquí se habían quedado detrás del mismo nombre.
  useEffect(() => {
    const sym = (symbolUrl || "").toUpperCase();
    if (sym && sym !== symbol) sincronizar(sym);
  }, [symbolUrl, symbol, sincronizar]);

  // Se pinta con el de la URL para que el primer render ya sea el correcto: usar el
  // del estado enseñaría la acción anterior durante un fotograma al navegar.
  return (
    <Dashboard
      symbol={(symbolUrl || symbol || "").toUpperCase()}
      setSymbol={setSymbol}
      model={model}
      setModel={setModel}
    />
  );
}

function AppInner() {
  const { isAuth, loading } = useAuth();
  const navigate = useNavigate();
  const [symbol, setSymbol] = useState("AAPL");
  const [model, setModel] = useState(() => localStorage.getItem("inveria-model-v3") || "gemini-2.5-flash");

  useEffect(() => {
    localStorage.setItem("inveria-model-v3", model);
  }, [model]);
  // Oscuro por defecto: es la identidad de InverIA, no una preferencia. Solo se
  // arranca en claro si TÚ lo elegiste alguna vez — de ahí distinguir "no hay nada
  // guardado" de "guardado como 0", que con el `=== "1"` anterior era lo mismo.
  const [darkMode, setDarkMode] = useState(() => {
    const guardado = localStorage.getItem("inveria-dark");
    return guardado === null ? true : guardado === "1";
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

  // El título sale de la PANTALLA, no del ticker seleccionado: con el ticker, que
  // empieza en AAPL, la portada y el resto se llamaban «AAPL · InverIA».
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = tituloDePagina(pathname);
  }, [pathname]);

  /* Elegir un ticker en cualquier pantalla lleva a su ficha.
     Se pasa con el nombre `setSymbol` a propósito: las ocho pantallas que ya lo
     reciben siguen funcionando sin tocarlas, y de paso quedan arregladas las que
     hasta ahora cambiaban el estado sin navegar. */
  const irAAccion = useCallback((s) => {
    const sym = (s || "").toString().toUpperCase().trim();
    if (!sym) return;
    setSymbol(sym);
    navigate(`/accion/${sym}`);
  }, [navigate]);

  if (loading) {
    return (
      <div className="min-h-screen min-h-[100dvh] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 text-tinta-3" role="status" aria-live="polite">
          <Sello className="w-10 h-10 rounded-[12px] motion-safe:animate-pulse" />
          <span className="text-apoyo">Cargando InverIA</span>
        </div>
      </div>
    );
  }

  if (!isAuth) return <LoginPage />;

  return (
    <div className="App min-h-screen overflow-x-hidden">
      {/* Navegación persistente. El lienzo se aparta lo que mida el rail
          (`--rail-w`, que cambia con la versión compacta) en vez de usar un grid:
          así ninguna de las rutas tiene que cambiar su contenedor. */}
      <Rail />
      <div className="lg:pl-[var(--rail-w)] transition-[padding] duration-200 ease-salida motion-reduce:transition-none">
      <Header
        symbol={symbol}
        setSymbol={irAAccion}
        onSearch={irAAccion}
        darkMode={darkMode}
        setDarkMode={setDarkMode}
      />
      <IrAlPrincipio />
      <ErrorBoundary>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* La portada. Hasta ahora "/" montaba la ficha de UNA acción, así que
              entrar exigía saber ya qué ticker mirar. */}
          <Route path="/" element={<HoyView />} />

          <Route path="/accion/:symbol" element={
            <PaginaAccion symbol={symbol} setSymbol={irAAccion} sincronizar={setSymbol}
              model={model} setModel={setModel} />
          } />

          <Route path="/oportunidades" element={<div className={LIENZO}><OpportunitiesView setSymbol={irAAccion} /></div>} />
          <Route path="/calendario" element={<div className={LIENZO}><CalendarView setSymbol={irAAccion} /></div>} />
          <Route path="/cartera" element={<div className={LIENZO}><SignalsView setSymbol={irAAccion} /></div>} />
          <Route path="/operaciones" element={<VentasView />} />
          <Route path="/track-record" element={<div className={LIENZO}><TrackRecordView /></div>} />
          <Route path="/telegram" element={<div className={LIENZO}><TelegramConnectView /></div>} />
          <Route path="/intelligence" element={<IntelligenceView />} />
          <Route path="/laboratorio" element={<LaboratorioView />} />
          <Route path="/cerebro" element={<div className={LIENZO}><BrainView /></div>} />
          <Route path="/diagnostico" element={<div className={LIENZO}><DiagnosticoView /></div>} />
          {/* Sin wrapper: EstilosView trae su propio PageShell, que es justamente
              el componente que sustituye a este div copiado ocho veces. */}
          <Route path="/sistema/estilos" element={<EstilosView />} />

          {/* Rutas viejas: redirección, no ruptura. Están en tu historial y en tus
              marcadores, y algunas llevan meses ahí. */}
          <Route path="/signals" element={<Navigate to="/cartera" replace />} />
          <Route path="/ventas" element={<Navigate to="/operaciones" replace />} />
          <Route path="/radar" element={<Navigate to="/oportunidades" replace />} />

          {/* Una ruta desconocida ya no cae en la ficha de una acción cualquiera:
              cae en la portada, que es la que sabe qué enseñarte sin contexto. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
      </ErrorBoundary>

      {/* Pie: una línea discreta, alineada con el contenido. El aviso legal se
          mantiene íntegro y legible (tinta-3, nunca rebajado con opacidad). */}
      <footer className="max-w-[1440px] mx-auto px-4 sm:px-8 mt-10 pb-8">
        <div className="border-t border-suave pt-5 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 sm:gap-8">
          <p className="text-[12.5px] text-tinta-3 leading-relaxed">
            Solo con fines educativos. Esta aplicación no constituye asesoramiento financiero, fiscal o legal.
          </p>
          <p className="text-[12.5px] text-tinta-3 leading-relaxed sm:text-right shrink-0">
            InverIA · Datos en vivo de Yahoo Finance + Finnhub · IA con Groq, OpenAI, Anthropic &amp; Google
          </p>
        </div>
      </footer>
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      {/* Los avisos salían con el blanco por defecto de sonner: una tarjeta clara
          sobre una app verde-negra, y encima es lo ÚLTIMO que aparece en pantalla,
          así que la incoherencia se veía siempre. Se pintan con los mismos tokens
          que todo lo demás, de modo que siguen al tema sin saber cuál está activo. */}
      <Toaster
        position="bottom-right"
        toastOptions={{
          className: "iv-aviso-flotante",
          style: {
            background: "rgb(var(--iv-superficie))",
            border: "1px solid var(--borde-medio)",
            borderRadius: "var(--iv-radio)",
            boxShadow: "var(--sombra-flotante)",
            color: "rgb(var(--iv-tinta))",
            fontFamily: "'Geist', ui-sans-serif, system-ui, sans-serif",
            fontSize: "13px",
          },
        }}
      />
      <AuthProvider>
        <AppInner />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
