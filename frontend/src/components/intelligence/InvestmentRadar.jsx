import React from "react";
import useRadarAnimacion from "../../hooks/useRadarAnimacion";
import { escuchando, estadoDe, nivelDe, anguloPorHora, agruparCoincidentes,
         VENTANA_RADAR_H } from "../../lib/intelligence";

/**
 * El radar. Cada cosa que se dibuja significa algo, y nada se dibuja por dibujar.
 *
 * CÓMO SE LEE
 *
 *   · Los ANILLOS son los tiers de fiabilidad. El de dentro es Tier 1 —hechos registrados,
 *     como un filing de la SEC— y hacia fuera se va perdiendo autoridad. Cuanto más al
 *     centro, más te lo puedes creer sin comprobarlo.
 *   · Cada FUENTE es un punto sobre su anillo. Late solo si está escuchando de verdad.
 *   · Cada EVENTO es una marca, colocada en su anillo por fiabilidad y en su ángulo por
 *     hora: arriba es ahora y se va hacia atrás en el sentido del reloj, como una esfera.
 *     Así la distancia entre dos marcas es tiempo real, no reparto estético.
 *   · Cuando varias caen en el mismo sitio se agrupan y se dice CUÁNTAS. En producción
 *     entraron 42 registros en el mismo minuto y el mismo tier, y se veían cuatro marcas.
 *     Separarlas habría exigido moverlas, y mover una marca un grado la mueve seis
 *     minutos en el tiempo: un dato falso para arreglar un problema de dibujo.
 *   · El BARRIDO gira únicamente si hay una fuente escuchando.
 *
 * LO QUE ESTE COMPONENTE NO HACE, A PROPÓSITO
 *
 * No inventa puntos. Si no hay eventos, el radar sale vacío y el texto lo dice. Un radar con
 * marcas de ejemplo sería un adorno que además miente, y es exactamente lo que se prohibió
 * por escrito.
 */

// Radio de cada anillo, por tier. Tier 1 en el centro: es el más fiable.
const RADIO_TIER = { 1: 42, 2: 72, 3: 102, 4: 128 };
const CENTRO = 160;

const punto = (radio, gradosDesdeArriba) => {
  const rad = ((gradosDesdeArriba - 90) * Math.PI) / 180;
  return { x: CENTRO + radio * Math.cos(rad), y: CENTRO + radio * Math.sin(rad) };
};

export default function InvestmentRadar({ estado, eventos, onElegir, seleccionado }) {
  const fuentes = estado?.fuentes || [];
  const activas = escuchando(fuentes);
  const { angulo, girando } = useRadarAnimacion(activas > 0);
  const ahora = Date.now();

  // Solo se colocan los eventos con hora y con tier conocido. Los demás existen —salen en
  // la lista de abajo— pero no se les asigna una posición inventada en el radar.
  const marcas = [];
  for (const ev of eventos || []) {
    const radio = RADIO_TIER[ev.tier];
    const grados = anguloPorHora(ev.recibido_en, ahora);
    if (!radio || grados === null) continue;
    marcas.push({ ev, ...punto(radio, grados) });
  }

  const tiersConFuente = new Set(fuentes.map((f) => f.tier));

  return (
    <div className="relative">
      <svg viewBox="0 0 320 320" className="w-full max-w-[380px] mx-auto block"
           role="img" data-testid="investment-radar"
           aria-label={activas
             ? `Radar de inteligencia: ${activas} fuentes escuchando, ${marcas.length} eventos en las últimas ${VENTANA_RADAR_H} horas`
             : "Radar de inteligencia apagado: ninguna fuente está escuchando"}>
        {/* Los anillos. Los tiers sin ninguna fuente implementada se dibujan más apagados:
            el hueco es información —«aquí todavía no escuchamos nada»— y taparlo daría a
            entender una cobertura que no existe. */}
        <g className="text-linea">
          {Object.entries(RADIO_TIER).map(([tier, radio]) => (
            <circle key={tier} cx={CENTRO} cy={CENTRO} r={radio} fill="none"
                    stroke="currentColor"
                    strokeWidth={1}
                    strokeDasharray={tiersConFuente.has(Number(tier)) ? undefined : "2 5"} />
          ))}
        </g>

        {/* Las marcas de las horas: cada 6 h, para que el ojo pueda medir. */}
        <g className="text-linea">
          {[0, 90, 180, 270].map((g) => {
            const a = punto(RADIO_TIER[1] - 8, g);
            const b = punto(RADIO_TIER[4] + 6, g);
            return <line key={g} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                         stroke="currentColor" strokeWidth={1} />;
          })}
        </g>

        {/* El barrido. Solo existe en el DOM si de verdad gira: un barrido parado, tenue,
            seguiría sugiriendo un mecanismo en marcha. */}
        {girando && (
          <g style={{ transform: `rotate(${angulo}deg)`, transformOrigin: `${CENTRO}px ${CENTRO}px` }}>
            <line x1={CENTRO} y1={CENTRO}
                  x2={punto(RADIO_TIER[4] + 6, 0).x} y2={punto(RADIO_TIER[4] + 6, 0).y}
                  className="text-marca" stroke="currentColor" strokeWidth={1.5}
                  opacity={0.55} />
          </g>
        )}

        {/* Los eventos. El tamaño lo da la gravedad, no el azar; y si varias marcas
            coinciden, el número dice cuántas hay ahí. */}
        {agruparCoincidentes(marcas).map((g) => {
          const ev = g.items[0].ev;
          const n = nivelDe(ev);
          const elegido = g.items.some((m) => seleccionado?.id === m.ev.id);
          return (
            <g key={ev.id} className={n.clase}>
              {elegido && (
                <circle cx={g.x} cy={g.y} r={9} fill="none" stroke="currentColor"
                        strokeWidth={1} opacity={0.7} />
              )}
              <circle
                cx={g.x} cy={g.y} r={Math.max(2.5, 2.5 + n.peso)}
                fill="currentColor"
                className="cursor-pointer"
                data-testid={`radar-evento-${ev.id}`}
                onClick={() => onElegir && onElegir(ev)}
              >
                <title>
                  {g.n > 1
                    ? `${g.n} eventos aquí · ${ev.symbol || "—"} y otros`
                    : `${ev.symbol || "—"} · ${ev.titulo || ""}`}
                </title>
              </circle>
              {/* El recuento solo cuando hay más de uno: un «1» junto a cada marca sería
                  ruido en el 90 % de los casos. */}
              {g.n > 1 && (
                <text x={g.x + 7} y={g.y + 3} className="iv-cifra" fontSize="9"
                      fill="currentColor" opacity={0.85}>{g.n}</text>
              )}
            </g>
          );
        })}

        {/* Las fuentes, repartidas por el arco superior de su anillo para que no caigan
            encima de las marcas de eventos recientes. */}
        {fuentes.map((f, i) => {
          const radio = RADIO_TIER[f.tier] || RADIO_TIER[4];
          const { x, y } = punto(radio, -35 - i * 26);
          const e = estadoDe(f);
          return (
            <g key={f.fuente} className={e.clase}>
              <circle cx={x} cy={y} r={4.5} fill="currentColor"
                      data-testid={`radar-nodo-${f.fuente}`}>
                <title>{`${f.nombre}: ${e.etiqueta}`}</title>
              </circle>
              {/* El latido marca «esta fuente está escuchando AHORA». Por eso solo lo
                  llevan las que lo están, y la animación se apaga con
                  prefers-reduced-motion (ver tokens.css). */}
              {e.escuchando && (
                <circle cx={x} cy={y} r={4.5} fill="none" stroke="currentColor"
                        strokeWidth={1} className="iv-radar-latido" />
              )}
            </g>
          );
        })}

        {/* El centro: tú. Todo lo que se dibuja está colocado respecto a tu cartera, y no
            respecto al mercado. */}
        <circle cx={CENTRO} cy={CENTRO} r={2.5} className="text-marca" fill="currentColor" />
      </svg>

      {/* La leyenda de los anillos. Sin ella los círculos son decoración. */}
      <div className="mt-3 flex flex-wrap justify-center gap-x-5 gap-y-1 iv-etiqueta">
        <span>Centro · tu cartera</span>
        <span>Anillos · fiabilidad de la fuente</span>
        <span>Giro · últimas {VENTANA_RADAR_H} h</span>
        <span>Número · cuántos eventos coinciden ahí</span>
      </div>
    </div>
  );
}
