import React, { useEffect, useMemo, useState } from "react";
import PageShell from "@/components/base/PageShell";
import Chip from "@/components/base/Chip";
import Boton from "@/components/base/Boton";
import Metrica from "@/components/base/Metrica";
import Estado, { Cargando, Vacio, Error as ErrorEstado } from "@/components/base/Estado";
import {
  fmtPrice, fmtPct, fmtNum, fmtEur, fmtDinero, fmtDate, fmtDateTime,
  fmtHace, fmtEnDias, fmtPctPlano, distanciaPct,
} from "@/lib/format";

/* Página de estilos viva · /sistema/estilos
   ─────────────────────────────────────────────────────────────────────────────
   Es la validación de la Fase 1. La idea es que el Design System se compruebe
   contra SÍ MISMO antes de tocar ninguna pantalla existente: migrar una pantalla
   vieja para validarlo mezclaría dos preguntas —"¿funciona el sistema?" y "¿he
   roto la pantalla?"— y solo la primera importa todavía.

   No es un muestrario: el contraste se MIDE en vivo leyendo los tokens ya
   resueltos por el navegador. Así, si alguien cambia un token y deja un texto por
   debajo del mínimo legible, se ve aquí en vez de descubrirse en producción. */

// ── Medición de contraste ────────────────────────────────────────────────────
function canalesDeToken(nombre) {
  const bruto = getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
  const partes = bruto.split(/[\s,]+/).map(Number).filter((n) => !isNaN(n));
  return partes.length >= 3 ? partes.slice(0, 3) : null;
}

function luminancia([r, g, b]) {
  const f = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function ratio(a, b) {
  if (!a || !b) return null;
  const la = luminancia(a), lb = luminancia(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const ROLES_TEXTO = [
  ["--iv-tinta", "tinta"], ["--iv-tinta-2", "tinta-2"], ["--iv-tinta-3", "tinta-3"],
  ["--iv-sube", "sube"], ["--iv-baja", "baja"], ["--iv-aviso", "aviso"],
  ["--iv-info", "info"], ["--iv-marca", "marca"],
];
const SUPERFICIES = [
  ["--iv-fondo", "fondo"], ["--iv-superficie", "superficie"], ["--iv-superficie-2", "superficie-2"],
];

// ── Piezas de la propia página ───────────────────────────────────────────────
function Bloque({ titulo, nota, children }) {
  return (
    <section className="mb-10">
      <h2 className="font-heading text-titulo font-bold text-tinta border-b border-linea pb-2 mb-1">
        {titulo}
      </h2>
      {nota && <p className="text-apoyo text-tinta-2 mb-4 max-w-[70ch]">{nota}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Muestra({ token, nombre }) {
  const canales = canalesDeToken(token);
  return (
    <div className="iv-panel overflow-hidden">
      <div className="h-12" style={{ background: `rgb(var(${token}))` }} />
      <div className="px-3 py-2">
        <p className="iv-cifra text-etiqueta text-tinta font-semibold">{nombre}</p>
        <p className="iv-cifra text-etiqueta text-tinta-3">{canales ? canales.join(" ") : "—"}</p>
      </div>
    </div>
  );
}

export default function EstilosView() {
  const [oscuro, setOscuro] = useState(() => document.documentElement.classList.contains("dark"));
  const [version, setVersion] = useState(0);

  // Al cambiar de tema hay que volver a leer los tokens: los valores resueltos
  // cambian, y una tabla de contraste calculada con los del otro tema mentiría.
  useEffect(() => {
    document.documentElement.classList.toggle("dark", oscuro);
    const t = setTimeout(() => setVersion((v) => v + 1), 30);
    return () => clearTimeout(t);
  }, [oscuro]);

  const medidas = useMemo(() => {
    void version;
    return SUPERFICIES.map(([tokenFondo, nombreFondo]) => ({
      fondo: nombreFondo,
      roles: ROLES_TEXTO.map(([tokenTexto, nombreTexto]) => ({
        rol: nombreTexto,
        r: ratio(canalesDeToken(tokenTexto), canalesDeToken(tokenFondo)),
      })),
    }));
  }, [version]);

  const peor = medidas
    .flatMap((m) => m.roles.map((x) => x.r))
    .filter(Boolean)
    .reduce((a, b) => Math.min(a, b), Infinity);

  return (
    <PageShell
      titulo="Design System"
      descripcion="La Fase 1, comprobándose a sí misma. Cambia de tema aquí arriba: todo lo de abajo sale de los mismos tokens, así que si algo se rompe en un tema se ve al instante."
      acciones={
        <Boton variante="secundario" onClick={() => setOscuro((v) => !v)}>
          Ver en {oscuro ? "claro" : "oscuro"}
        </Boton>
      }
    >
      <div className="mb-8 iv-destacada p-4">
        <p className="iv-etiqueta">Contraste mínimo de toda la paleta</p>
        <p className={`iv-cifra text-cifra font-bold ${peor >= 4.5 ? "text-sube" : "text-baja"}`}>
          {peor === Infinity ? "—" : `${peor.toFixed(2)}:1`}
        </p>
        <p className="text-apoyo text-tinta-2 mt-1">
          El mínimo legible es 4,5:1. Este número es el peor caso de los {ROLES_TEXTO.length} roles de
          texto sobre las {SUPERFICIES.length} superficies del tema actual, medido sobre los tokens ya
          resueltos por el navegador — no un valor escrito a mano que puede quedarse viejo.
        </p>
      </div>

      <Bloque
        titulo="Paleta"
        nota="El ámbar deja de ser un accidente. Hasta ahora era lo que salía cuando el parche !important convertía el verde de marca en naranja; ahora es --iv-marca, un color con nombre que se puede usar a propósito."
      >
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <Muestra token="--iv-fondo" nombre="fondo" />
          <Muestra token="--iv-superficie" nombre="superficie" />
          <Muestra token="--iv-superficie-2" nombre="superficie-2" />
          <Muestra token="--iv-linea" nombre="linea" />
          <Muestra token="--iv-linea-marcada" nombre="linea-marcada" />
          <Muestra token="--iv-marca" nombre="marca" />
          <Muestra token="--iv-sube" nombre="sube" />
          <Muestra token="--iv-baja" nombre="baja" />
          <Muestra token="--iv-aviso" nombre="aviso" />
          <Muestra token="--iv-info" nombre="info" />
        </div>
      </Bloque>

      <Bloque titulo="Contraste medido" nota="Cada rol de texto sobre cada superficie del tema actual.">
        <div className="overflow-x-auto iv-panel">
          <table className="w-full text-apoyo">
            <thead>
              <tr className="border-b border-linea">
                <th className="iv-etiqueta text-left px-3 py-2">Rol</th>
                {medidas.map((m) => (
                  <th key={m.fondo} className="iv-etiqueta text-right px-3 py-2">sobre {m.fondo}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROLES_TEXTO.map(([, nombre], i) => (
                <tr key={nombre} className="border-b border-linea last:border-0">
                  <td className="px-3 py-2 iv-cifra text-tinta">{nombre}</td>
                  {medidas.map((m) => {
                    const r = m.roles[i]?.r;
                    return (
                      <td key={m.fondo} className="px-3 py-2 text-right iv-cifra">
                        <span className={r >= 4.5 ? "text-sube" : "text-baja"}>
                          {r ? `${r.toFixed(2)}:1` : "—"}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Bloque>

      <Bloque
        titulo="Tipografía"
        nota="Cinco pasos y 11px como suelo absoluto. Hoy la app tiene text-[9px] en sitios de lectura: por debajo de 11px el texto no se lee, se adivina."
      >
        <div className="iv-panel p-4 space-y-3">
          <p className="text-cifra font-heading font-bold text-tinta">cifra · 26px — el dato protagonista</p>
          <p className="text-titulo font-heading font-bold text-tinta">titulo · 19px — título de sección</p>
          <p className="text-cuerpo text-tinta">cuerpo · 15px — el texto que se lee de verdad</p>
          <p className="text-apoyo text-tinta-2">apoyo · 13px — explicación secundaria</p>
          <p className="iv-etiqueta">etiqueta · 11px — el suelo, solo para etiquetas de dato</p>
          <p className="iv-cifra text-cuerpo text-tinta pt-2 border-t border-linea">
            1,234.56 · 1,111.11 · 9,999.99 <span className="text-tinta-3 text-apoyo font-sans">← cifras tabulares: las columnas no bailan al actualizarse en vivo</span>
          </p>
        </div>
      </Bloque>

      <Bloque
        titulo="Superficies"
        nota="Tres densidades, no cinco anatomías de tarjeta. El Brief lo pide literalmente: «no convertir todo en una card»."
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="iv-panel p-4">
            <p className="iv-etiqueta">iv-panel</p>
            <p className="text-apoyo text-tinta-2 mt-1">Contenedor de sección. Agrupa sin reclamar atención.</p>
          </div>
          <div className="iv-destacada p-4">
            <p className="iv-etiqueta">iv-destacada</p>
            <p className="text-apoyo text-tinta-2 mt-1">Decisión. Lo que hay que leer sí o sí.</p>
          </div>
          <div className="iv-panel p-0 overflow-hidden">
            <p className="iv-etiqueta px-4 pt-3">iv-fila</p>
            {["AAPL", "NVDA", "MRVL"].map((s) => (
              <div key={s} className="iv-fila px-4 py-2 flex justify-between items-center last:border-0">
                <span className="iv-cifra text-apoyo text-tinta">{s}</span>
                <span className="iv-cifra text-apoyo text-sube">+1.24%</span>
              </div>
            ))}
          </div>
        </div>
      </Bloque>

      <Bloque titulo="Chips" nota="~90 chips en la app resueltos hoy con 12 implementaciones distintas. Tres ejes: tono × variante × tamaño.">
        <div className="iv-panel p-4 space-y-3">
          {["suave", "solido", "contorno"].map((variante) => (
            <div key={variante} className="flex flex-wrap items-center gap-2">
              <span className="iv-etiqueta w-20 shrink-0">{variante}</span>
              {["neutro", "marca", "sube", "baja", "aviso", "info"].map((tono) => (
                <Chip key={tono} tono={tono} variante={variante}>{tono}</Chip>
              ))}
            </div>
          ))}
        </div>
      </Bloque>

      <Bloque titulo="Botones" nota="99 botones crudos en la app, ~25 combinaciones para lo mismo.">
        <div className="iv-panel p-4 flex flex-wrap gap-2 items-center">
          <Boton variante="primario">Primario</Boton>
          <Boton variante="secundario">Secundario</Boton>
          <Boton variante="contorno">Contorno</Boton>
          <Boton variante="fantasma">Fantasma</Boton>
          <Boton variante="peligro">Peligro</Boton>
          <Boton variante="enlace">Enlace</Boton>
          <Boton ocupado>Ocupado</Boton>
          <Boton disabled>Deshabilitado</Boton>
        </div>
      </Bloque>

      <Bloque
        titulo="Estados"
        nota="Hoy un fallo de red es indistinguible de «no hay nada»: en la Cartera, un error de carga se presenta como «Sin acciones todavía». Son tres estados distintos y tienen que verse distintos."
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="iv-panel p-4">
            <p className="iv-etiqueta mb-3">Cargando</p>
            <Cargando filas={4} />
          </div>
          <div className="iv-panel p-4">
            <p className="iv-etiqueta">Vacío con motivo</p>
            <Vacio
              titulo="Tus fuentes no han hablado de NVDA"
              motivo="En los últimos 30 días no hay ninguna mención en newsletters ni en Telegram."
              accion={{ texto: "Ampliar a 90 días", onClick: () => {} }}
            />
          </div>
          <div className="iv-panel p-4">
            <p className="iv-etiqueta mb-3">Error con causa</p>
            <ErrorEstado
              error={{ response: { status: 429 } }}
              onReintentar={() => {}}
            />
          </div>
        </div>
      </Bloque>

      <Bloque
        titulo="Métricas"
        nota="El color por signo solo vale cuando el número es un cambio y subir es bueno. Hoy hay sitios donde un EPS negativo sale en verde, porque el ternario se copió de donde sí tenía sentido."
      >
        <div className="iv-panel p-4 grid gap-4 grid-cols-2 sm:grid-cols-4">
          <Metrica etiqueta="Precio" valor={fmtPrice(182.34)} tamano="lg" />
          <Metrica etiqueta="Variación día" valor={fmtPct(2.4)} valorNumerico={2.4} tono="auto" tamano="lg" />
          <Metrica etiqueta="Variación día" valor={fmtPct(-1.1)} valorNumerico={-1.1} tono="auto" tamano="lg" />
          <Metrica
            etiqueta="EPS" valor={fmtPrice(-0.42)} tamano="lg"
            detalle="tono ninguno: es una magnitud, no una dirección"
          />
          <Metrica etiqueta="Deuda / EBITDA" valor="3.10" valorNumerico={3.1} tono="invertido" detalle="subir es malo" />
          <Metrica etiqueta="Sin dato" valor={null} detalle="nunca se tiñe" />
          <Metrica etiqueta="Volumen" valor={fmtNum(24_300_000)} />
          <Metrica etiqueta="P&L latente" valor={fmtEur(1234.5)} valorNumerico={1234.5} tono="auto" />
        </div>
      </Bloque>

      <Bloque titulo="Formato" nota="Nueve implementaciones de «formatear dinero» repartidas por las pantallas, y dos locales mezclados sin criterio.">
        <div className="overflow-x-auto iv-panel">
          <table className="w-full text-apoyo">
            <thead>
              <tr className="border-b border-linea">
                <th className="iv-etiqueta text-left px-3 py-2">Función</th>
                <th className="iv-etiqueta text-left px-3 py-2">Resultado</th>
                <th className="iv-etiqueta text-left px-3 py-2">Criterio</th>
              </tr>
            </thead>
            <tbody className="iv-cifra text-tinta">
              {[
                ["fmtPrice(1234.5)", fmtPrice(1234.5), "en-US: cuadra con el bróker de un vistazo"],
                ["fmtPct(2.4)", fmtPct(2.4), "signo siempre: el color no puede ser el único portador"],
                ["fmtPctPlano(1.8)", fmtPctPlano(1.8), "magnitudes sin dirección"],
                ["fmtNum(24300000)", fmtNum(24300000), "abreviado"],
                ["fmtEur(1234.5)", fmtEur(1234.5), "es-ES: el dinero propio"],
                ["fmtDinero(1234.5,'USD')", fmtDinero(1234.5, "USD"), "sin divisa fiable, no se inventa el símbolo"],
                ["fmtDate(hoy)", fmtDate(Date.now()), "es-ES siempre"],
                ["fmtDateTime(hoy)", fmtDateTime(Date.now()), ""],
                ["fmtHace(-30min)", fmtHace(Date.now() - 1800000), "saber si el dato está fresco es parte de fiarte de él"],
                ["fmtEnDias(+2d)", fmtEnDias(Date.now() + 172800000), "para el calendario"],
                ["distanciaPct(182,178)", `${distanciaPct(182, 178).toFixed(2)}%`, "la unidad de urgencia de la app"],
                ["fmtPrice(null)", fmtPrice(null), "un dato que falta es «—», nunca 0"],
              ].map(([fn, res, nota]) => (
                <tr key={fn} className="border-b border-linea last:border-0">
                  <td className="px-3 py-2 text-tinta-2">{fn}</td>
                  <td className="px-3 py-2 font-semibold">{res}</td>
                  <td className="px-3 py-2 font-sans text-tinta-3">{nota}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Bloque>

      <Bloque titulo="Foco visible" nota="Recorre esto con el tabulador. Global desde el principio: un foco que se añade al final acaba faltando en la mitad de los sitios.">
        <div className="iv-panel p-4 flex flex-wrap gap-2">
          <Boton variante="secundario">Primero</Boton>
          <Boton variante="secundario">Segundo</Boton>
          <input
            className="h-9 px-3 rounded-iv bg-superficie-alt border border-linea-fuerte text-apoyo text-tinta"
            placeholder="Un campo"
          />
          <a href="#foco" className="text-marca text-apoyo underline underline-offset-4 self-center">Un enlace</a>
        </div>
      </Bloque>

      <Estado vacio tituloVacio="Fin de la página de estilos" motivoVacio="Si algo de aquí arriba no te encaja, es más barato cambiarlo ahora que después de aplicarlo a ocho pantallas." />
    </PageShell>
  );
}
