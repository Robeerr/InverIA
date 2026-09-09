import { useEffect, useRef, useState } from "react";

/**
 * El barrido del radar. Dos condiciones, y las dos son obligatorias.
 *
 * 1. QUE HAYA ALGO QUE VIGILAR. Si ninguna fuente está escuchando, el radar NO gira. Un
 *    barrido girando sobre un sistema apagado es la mentira visual más fácil de colar y la
 *    más difícil de detectar: parece que trabaja, y nadie mira los estados.
 *
 * 2. QUE EL USUARIO NO HAYA PEDIDO QUIETUD. `prefers-reduced-motion` no es una sugerencia:
 *    hay gente a la que el movimiento continuo le provoca mareo. Con esa preferencia puesta
 *    el radar se dibuja igual, con todo su contenido, simplemente sin girar.
 *
 * Y una tercera que no es una condición sino una obligación de buen vecino: cuando la
 * pestaña está en segundo plano no se anima. `requestAnimationFrame` ya se detiene solo,
 * pero el ángulo se recalcula desde el reloj para que al volver no dé un salto de vuelta
 * entera.
 */
export default function useRadarAnimacion(activo, { periodoMs = 8000 } = {}) {
  const [angulo, setAngulo] = useState(0);
  const [quieto, setQuieto] = useState(false);
  const frame = useRef(null);

  // La preferencia se ESCUCHA, no se lee una vez: se puede cambiar con la web abierta.
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const aplicar = () => setQuieto(mq.matches);
    aplicar();
    // `addEventListener` en un MediaQueryList no existe en navegadores viejos.
    if (mq.addEventListener) {
      mq.addEventListener("change", aplicar);
      return () => mq.removeEventListener("change", aplicar);
    }
    mq.addListener(aplicar);
    return () => mq.removeListener(aplicar);
  }, []);

  const girando = Boolean(activo) && !quieto;

  useEffect(() => {
    if (!girando) {
      setAngulo(0);
      return undefined;
    }
    const paso = () => {
      // Desde el reloj y no acumulando: si la pestaña se queda en segundo plano un rato,
      // al volver el barrido está donde debería, sin dar un salto.
      setAngulo(((Date.now() % periodoMs) / periodoMs) * 360);
      frame.current = requestAnimationFrame(paso);
    };
    frame.current = requestAnimationFrame(paso);
    return () => frame.current && cancelAnimationFrame(frame.current);
  }, [girando, periodoMs]);

  return { angulo, girando, quieto };
}
