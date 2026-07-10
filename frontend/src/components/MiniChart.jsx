import React, { useEffect, useRef, useState } from "react";

// Mini-gráfico de TradingView por tarjeta (como el del vídeo). Se monta SOLO cuando la
// tarjeta entra en pantalla (IntersectionObserver) para no cargar 77 iframes de golpe
// en el móvil. Sin coste de datos: TradingView lo sirve gratis.

export default function MiniChart({ symbol, height = 140 }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || visible) return;
    const io = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) { setVisible(true); io.disconnect(); }
    }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [visible]);

  const isDark = typeof document !== "undefined" && document.documentElement.classList.contains("dark");
  // Widget "Mini Symbol Overview": línea limpia SIN barras de herramientas (como el vídeo).
  // La config va en el hash de la URL como JSON.
  const config = {
    symbol,
    width: "100%",
    height: String(height),
    locale: "es",
    dateRange: "12M",
    colorTheme: isDark ? "dark" : "light",
    isTransparent: true,
    autosize: true,
    chartOnly: false,
    noTimeScale: false,
  };
  const src = `https://s.tradingview.com/embed-widget/mini-symbol-overview/?locale=es#${encodeURIComponent(JSON.stringify(config))}`;

  return (
    <div ref={ref} style={{ height }} className="w-full rounded-md overflow-hidden mt-2">
      {visible && (
        <iframe
          title={`chart-${symbol}`}
          src={src}
          style={{ width: "100%", height: "100%", border: 0 }}
          loading="lazy"
          scrolling="no"
        />
      )}
    </div>
  );
}
