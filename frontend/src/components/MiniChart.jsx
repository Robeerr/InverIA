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
  const src =
    `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(symbol)}` +
    `&interval=W&hidesidetoolbar=1&hidetoptoolbar=1&symboledit=0&saveimage=0` +
    `&hideideas=1&hidevolume=1&theme=${isDark ? "dark" : "light"}&style=3&timezone=exchange` +
    `&withdateranges=0&studies=[]`;

  return (
    <div ref={ref} style={{ height }} className="w-full rounded-md overflow-hidden bg-[#f6f4ef] mt-2">
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
