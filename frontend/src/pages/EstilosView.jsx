import React, { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, ArrowDownRight, Search } from "lucide-react";
import PageShell from "@/components/base/PageShell";
import Chip from "@/components/base/Chip";
import Boton from "@/components/base/Boton";
import Metrica from "@/components/base/Metrica";
import Estado, { Cargando, Vacio, Error as ErrorEstado } from "@/components/base/Estado";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Sello } from "@/components/Rail";
import {
  fmtPrice, fmtPct, fmtNum, fmtEur, fmtDinero, fmtDate, fmtDateTime,
  fmtHace, fmtEnDias, fmtPctPlano, distanciaPct,
} from "@/lib/format";

/* Guía viva del sistema «Grafito e índigo» · /sistema/estilos
   ─────────────────────────────────────────────────────────────────────────────
   Todo lo que se ve aquí sale de los mismos tokens que el resto de la app, y el
   contraste se MIDE en vivo leyendo los valores ya resueltos por el navegador: si
   alguien cambia un token y deja un texto por debajo de 4,5:1, se ve aquí. La
   referencia escrita está en DESIGN.md, en la raíz del repo. */

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
  ["--iv-intencion", "intencion"], ["--iv-sube", "sube"], ["--iv-baja", "baja"],
  ["--iv-aviso", "aviso"], ["--iv-alerta", "alerta"], ["--iv-info", "info"],
];
const SUPERFICIES = [
  ["--iv-fondo", "fondo"], ["--iv-superficie", "superficie"], ["--iv-superficie-2", "superficie-2"],
];

const GRUPOS_PALETA = [
  {
    titulo: "Capas",
    nota: "La elevación es luz: cada capa sube un escalón.",
    tokens: [["--iv-fondo", "fondo"], ["--iv-superficie", "superficie"], ["--iv-superficie-2", "superficie-2"], ["--iv-linea-marcada", "linea-marcada"]],
  },
  {
    titulo: "Tinta",
    nota: "Tres niveles de texto, como mucho, en un mismo bloque.",
    tokens: [["--iv-tinta", "tinta"], ["--iv-tinta-2", "tinta-2"], ["--iv-tinta-3", "tinta-3"]],
  },
  {
    titulo: "Intención",
    nota: "Índigo: acción principal, dónde estás y foco. Nunca un dato.",
    tokens: [["--iv-intencion", "intencion (bg-marca)"], ["--iv-acento-2", "acento-2"]],
  },
  {
    titulo: "Dirección y aviso",
    nota: "Verde y rojo solo dicen si una cifra sube o baja.",
    tokens: [["--iv-sube", "sube"], ["--iv-baja", "baja"], ["--iv-aviso", "aviso"], ["--iv-alerta", "alerta"], ["--iv-info", "info"]],
  },
];

// ── Piezas de la propia página ───────────────────────────────────────────────
function Bloque({ id, titulo, nota, children }) {
  return (
    <section id={id} className="scroll-mt-20 grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-10 py-10 border-t border-suave first:border-t-0 first:pt-0">
      <div className="lg:sticky lg:top-20 self-start">
        <h2 className="text-titulo font-semibold text-tinta">{titulo}</h2>
        {nota && <p className="text-apoyo text-tinta-3 mt-1.5 max-w-[46ch]">{nota}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function Muestra({ token, nombre }) {
  const canales = canalesDeToken(token);
  return (
    <div className="min-w-0">
      <div className="h-16 rounded-[12px] border border-suave" style={{ background: `rgb(var(${token}))` }} />
      <p className="mt-2 text-apoyo font-medium text-tinta">{nombre}</p>
      <p className="iv-cifra text-[11.5px] text-tinta-3 truncate">{canales ? canales.join(" ") : "—"}</p>
    </div>
  );
}

const FILAS_MODELO = [
  { s: "NVDA", n: "NVIDIA Corp.", p: 182.34, c: 2.41, v: 12450.8 },
  { s: "ORCL", n: "Oracle Corp.", p: 128.38, c: -1.12, v: 5905.48 },
  { s: "ASML", n: "ASML Holding", p: 712.9, c: 0.36, v: 1425800.12 },
];

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
      titulo="Grafito e índigo"
      descripcion="El sistema visual de InverIA. Todo lo de abajo sale de los mismos tokens que la app: si algo se rompe en un tema, se ve aquí antes que en ninguna pantalla."
      acciones={
        <Boton variante="secundario" onClick={() => setOscuro((v) => !v)}>
          Ver en {oscuro ? "claro" : "oscuro"}
        </Boton>
      }
    >
      {/* Portada del sistema: la marca, los principios y el contraste medido. */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] mb-12">
        <div className="iv-destacada p-6 sm:p-8 flex flex-col justify-between gap-8 min-h-[220px]">
          <div className="flex items-center gap-3">
            <Sello className="w-10 h-10 rounded-[12px]" />
            <span className="iv-marca-palabra text-[22px]">InverIA</span>
          </div>
          <ul className="grid gap-3 sm:grid-cols-3 text-apoyo text-tinta-2">
            <li><span className="block text-tinta font-medium mb-0.5">Una intención</span>El índigo marca acción, lugar y foco.</li>
            <li><span className="block text-tinta font-medium mb-0.5">Dos direcciones</span>Verde sube, rojo baja. Nada más.</li>
            <li><span className="block text-tinta font-medium mb-0.5">Capas de luz</span>Elevación por luminosidad, no por cajas.</li>
          </ul>
        </div>
        <div className="iv-panel p-6 sm:p-8 flex flex-col justify-between gap-6">
          <p className="iv-etiqueta">Contraste mínimo del tema actual</p>
          <p className={`iv-cifra-hero text-heroe ${peor >= 4.5 ? "text-sube" : "text-baja"}`}>
            {peor === Infinity ? "—" : `${peor.toFixed(2)}:1`}
          </p>
          <p className="text-apoyo text-tinta-3">
            Peor caso de {ROLES_TEXTO.length} roles de texto sobre {SUPERFICIES.length} superficies, medido
            sobre los tokens resueltos. El mínimo es 4,5:1.
          </p>
        </div>
      </div>

      <Bloque id="paleta" titulo="Paleta" nota="Grafito frío con un único color de intención. Tripletes RGB: admiten opacidad (bg-marca/10).">
        <div className="space-y-8">
          {GRUPOS_PALETA.map((g) => (
            <div key={g.titulo}>
              <div className="flex flex-wrap items-baseline gap-x-3 mb-3">
                <p className="text-cuerpo font-medium text-tinta">{g.titulo}</p>
                <p className="text-apoyo text-tinta-3">{g.nota}</p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-4">
                {g.tokens.map(([t, n]) => <Muestra key={t} token={t} nombre={n} />)}
              </div>
            </div>
          ))}
        </div>
      </Bloque>

      <Bloque id="tipografia" titulo="Tipografía" nota="Geist para todo lo que se lee; Geist Mono solo en columnas de cifras. Seis pasos, tres como mucho por bloque.">
        <div className="iv-panel divide-y divide-[var(--borde-suave)]">
          {[
            ["heroe · 44", <p className="iv-cifra-hero text-heroe text-tinta">19.632,03 €</p>],
            ["cifra · 28", <p className="iv-cifra-hero text-cifra text-tinta">$128.38</p>],
            ["titulo · 18", <p className="text-titulo font-semibold text-tinta">Decisiones que requieren tu atención</p>],
            ["cuerpo · 14,5", <p className="text-cuerpo text-tinta">El texto que se lee de verdad, con una medida de unos 70 caracteres.</p>],
            ["apoyo · 13", <p className="text-apoyo text-tinta-2">Explicación secundaria o el contexto de una cifra.</p>],
            ["etiqueta · 12", <p className="iv-etiqueta">Precio medio</p>],
            ["mono · cifras", <p className="iv-cifra text-cuerpo text-tinta">1,234.56 · 1,111.11 · 9,999.99</p>],
          ].map(([n, ej]) => (
            <div key={n} className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-6 px-5 py-4">
              <span className="text-apoyo text-tinta-3 sm:w-28 shrink-0">{n}</span>
              <div className="min-w-0">{ej}</div>
            </div>
          ))}
        </div>
      </Bloque>

      <Bloque id="superficies" titulo="Superficies" nota="Radios 8 · 12 · 16. Bordes de 1 px translúcidos. Una pieza dentro de otra pierde su caja y pasa a ser una zona de luz.">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="iv-panel p-5">
            <p className="text-cuerpo font-medium text-tinta">iv-panel</p>
            <p className="text-apoyo text-tinta-3 mt-1">La pieza base. Agrupa sin reclamar atención.</p>
            <div className="iv-panel p-3 mt-4">
              <p className="text-apoyo text-tinta-2">Anidada: sin borde ni sombra.</p>
            </div>
          </div>
          <div className="iv-destacada p-5">
            <p className="text-cuerpo font-medium text-tinta">iv-destacada</p>
            <p className="text-apoyo text-tinta-3 mt-1">Lo que hay que leer sí o sí. Filo índigo y luz en la esquina.</p>
          </div>
          <div className="iv-panel iv-halo-baja p-5">
            <p className="text-cuerpo font-medium text-tinta">iv-halo-*</p>
            <p className="text-apoyo text-tinta-3 mt-1">Tinte de dirección (sube, baja, info). Con moderación.</p>
          </div>
        </div>
      </Bloque>

      <Bloque id="tabla" titulo="Tabla" nota="Cabecera fija y tenue, cifras tabulares a la derecha, hover de fila, separadores apenas visibles. En móvil, la tabla se convierte en lista.">
        <div className="iv-panel overflow-hidden">
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-apoyo">
              <thead className="sticky top-0">
                <tr className="border-b border-suave">
                  <th className="iv-etiqueta text-left font-medium px-5 py-3">Acción</th>
                  <th className="iv-etiqueta text-right font-medium px-5 py-3">Precio</th>
                  <th className="iv-etiqueta text-right font-medium px-5 py-3">Hoy</th>
                  <th className="iv-etiqueta text-right font-medium px-5 py-3">Valor</th>
                </tr>
              </thead>
              <tbody>
                {FILAS_MODELO.map((f) => (
                  <tr key={f.s} className="border-b border-suave last:border-0">
                    <td className="px-5 py-3">
                      <span className="font-medium text-tinta">{f.s}</span>
                      <span className="text-tinta-3 ml-2">{f.n}</span>
                    </td>
                    <td className="px-5 py-3 text-right iv-cifra text-tinta">${fmtPrice(f.p)}</td>
                    <td className={`px-5 py-3 text-right iv-cifra ${f.c >= 0 ? "text-sube" : "text-baja"}`}>
                      <span className="inline-flex items-center gap-0.5">
                        {f.c >= 0 ? <ArrowUpRight size={13} aria-hidden="true" /> : <ArrowDownRight size={13} aria-hidden="true" />}
                        {fmtPct(f.c)}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right iv-cifra text-tinta">{fmtEur(f.v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="sm:hidden divide-y divide-[var(--borde-suave)]">
            {FILAS_MODELO.map((f) => (
              <li key={f.s} className="flex items-center justify-between gap-3 px-4 min-h-[56px] py-2.5">
                <div className="min-w-0">
                  <p className="font-medium text-tinta">{f.s}</p>
                  <p className="text-apoyo text-tinta-3 truncate">{f.n}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="iv-cifra text-tinta">{fmtEur(f.v)}</p>
                  <p className={`iv-cifra text-apoyo ${f.c >= 0 ? "text-sube" : "text-baja"}`}>{fmtPct(f.c)}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </Bloque>

      <Bloque id="controles" titulo="Controles" nota="Radio de control 10 px. Al pulsar se hunden un 2 % en 150 ms. El principal es el único índigo sólido de una vista.">
        <div className="space-y-6">
          <div className="flex flex-wrap gap-2 items-center">
            <Boton variante="primario">Añadir posición</Boton>
            <Boton variante="secundario">Importar</Boton>
            <Boton variante="contorno">Contorno</Boton>
            <Boton variante="fantasma">Fantasma</Boton>
            <Boton variante="peligro">Eliminar</Boton>
            <Boton variante="enlace">Ver análisis</Boton>
            <Boton ocupado>Ocupado</Boton>
            <Boton disabled>Deshabilitado</Boton>
          </div>
          <div className="flex flex-wrap gap-4 items-center">
            <Tabs defaultValue="todas">
              <TabsList>
                <TabsTrigger value="todas">Todas</TabsTrigger>
                <TabsTrigger value="bajo">Bajo</TabsTrigger>
                <TabsTrigger value="medio">Medio</TabsTrigger>
                <TabsTrigger value="alto">Alto</TabsTrigger>
              </TabsList>
              <TabsContent value="todas" className="sr-only">Todas</TabsContent>
            </Tabs>
            <div className="relative w-full max-w-[280px]">
              <Search size={15} aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 text-tinta-3 pointer-events-none" />
              <label htmlFor="estilos-campo" className="sr-only">Campo de ejemplo</label>
              <Input id="estilos-campo" placeholder="Buscar ticker o empresa" className="pl-9" />
            </div>
          </div>
          <div className="space-y-3">
            {["suave", "solido", "contorno"].map((variante) => (
              <div key={variante} className="flex flex-wrap items-center gap-2">
                <span className="text-apoyo text-tinta-3 w-20 shrink-0">{variante}</span>
                {["neutro", "marca", "sube", "baja", "aviso", "info"].map((tono) => (
                  <Chip key={tono} tono={tono} variante={variante}>{tono}</Chip>
                ))}
              </div>
            ))}
          </div>
        </div>
      </Bloque>

      <Bloque id="metricas" titulo="Métricas" nota="El color por signo solo cuando el número es un cambio y subir es bueno. Teñir hay que pedirlo.">
        <div className="iv-panel p-5 sm:p-6 grid gap-6 grid-cols-2 sm:grid-cols-4">
          <Metrica etiqueta="Precio" valor={fmtPrice(182.34)} tamano="lg" />
          <Metrica etiqueta="Variación día" valor={fmtPct(2.4)} valorNumerico={2.4} tono="auto" tamano="lg" />
          <Metrica etiqueta="Variación día" valor={fmtPct(-1.1)} valorNumerico={-1.1} tono="auto" tamano="lg" />
          <Metrica
            etiqueta="EPS" valor={fmtPrice(-0.42)} tamano="lg"
            detalle="Magnitud, no dirección"
          />
          <Metrica etiqueta="Deuda / EBITDA" valor="3.10" valorNumerico={3.1} tono="invertido" detalle="Subir es malo" />
          <Metrica etiqueta="Sin dato" valor={null} detalle="Nunca se tiñe" />
          <Metrica etiqueta="Volumen" valor={fmtNum(24_300_000)} />
          <Metrica etiqueta="P&L latente" valor={fmtEur(1234.5)} valorNumerico={1234.5} tono="auto" />
        </div>
      </Bloque>

      <Bloque id="estados" titulo="Estados" nota="Cargando, vacío y error son tres cosas distintas y se ven distintas. La carga tiene la forma de lo que viene.">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="iv-panel p-5">
            <p className="iv-etiqueta mb-4">Cargando</p>
            <Cargando filas={4} />
          </div>
          <div className="iv-panel p-5">
            <p className="iv-etiqueta">Vacío con motivo</p>
            <Vacio
              titulo="Tus fuentes no han hablado de NVDA"
              motivo="En los últimos 30 días no hay ninguna mención en newsletters ni en Telegram."
              accion={{ texto: "Ampliar a 90 días", onClick: () => {} }}
            />
          </div>
          <div className="iv-panel p-5">
            <p className="iv-etiqueta mb-4">Error con causa</p>
            <ErrorEstado error={{ response: { status: 429 } }} onReintentar={() => {}} />
          </div>
        </div>
      </Bloque>

      <Bloque id="movimiento" titulo="Movimiento" nota="Responde a lo que haces, no decora. Con movimiento reducido, todo aparece sin desplazarse.">
        <div className="iv-panel divide-y divide-[var(--borde-suave)]">
          {[
            ["Pulsar", "scale 0.98 · 150 ms · curva de salida"],
            ["Hover y foco", "color y fondo · 150 ms"],
            ["Entrada de pantalla", "opacidad + 6 px · 220 ms"],
            ["Cajón móvil", "deslizar · 300 ms · curva de cajón"],
            ["Esqueleto", "barrido de luz · 1,6 s · se detiene con movimiento reducido"],
          ].map(([a, b]) => (
            <div key={a} className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-6 px-5 py-3.5">
              <span className="text-apoyo text-tinta font-medium sm:w-44 shrink-0">{a}</span>
              <span className="iv-cifra text-apoyo text-tinta-2">{b}</span>
            </div>
          ))}
        </div>
      </Bloque>

      <Bloque id="contraste" titulo="Contraste medido" nota="Cada rol de texto sobre cada superficie del tema actual. AA es 4,5:1.">
        <div className="overflow-x-auto iv-panel">
          <table className="w-full text-apoyo">
            <thead>
              <tr className="border-b border-suave">
                <th className="iv-etiqueta text-left font-medium px-5 py-3">Rol</th>
                {medidas.map((m) => (
                  <th key={m.fondo} className="iv-etiqueta text-right font-medium px-5 py-3">Sobre {m.fondo}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROLES_TEXTO.map(([token, nombre], i) => (
                <tr key={nombre} className="border-b border-suave last:border-0">
                  <td className="px-5 py-2.5">
                    <span className="inline-flex items-center gap-2 text-tinta">
                      <span aria-hidden="true" className="w-2.5 h-2.5 rounded-full" style={{ background: `rgb(var(${token}))` }} />
                      {nombre}
                    </span>
                  </td>
                  {medidas.map((m) => {
                    const r = m.roles[i]?.r;
                    return (
                      <td key={m.fondo} className="px-5 py-2.5 text-right iv-cifra">
                        <span className={r >= 4.5 ? "text-tinta-2" : "text-baja font-semibold"}>
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

      <Bloque id="formato" titulo="Formato" nota="Un solo sitio sabe si un número es un precio en dólares o un importe en euros: lib/format.">
        <div className="overflow-x-auto iv-panel">
          <table className="w-full text-apoyo">
            <thead>
              <tr className="border-b border-suave">
                <th className="iv-etiqueta text-left font-medium px-5 py-3">Función</th>
                <th className="iv-etiqueta text-right font-medium px-5 py-3">Resultado</th>
                <th className="iv-etiqueta text-left font-medium px-5 py-3">Criterio</th>
              </tr>
            </thead>
            <tbody>
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
                <tr key={fn} className="border-b border-suave last:border-0">
                  <td className="px-5 py-2.5 iv-cifra text-tinta-2 whitespace-nowrap">{fn}</td>
                  <td className="px-5 py-2.5 iv-cifra text-tinta text-right whitespace-nowrap">{res}</td>
                  <td className="px-5 py-2.5 text-tinta-3 min-w-[16rem]">{nota}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Bloque>

      <Bloque id="foco" titulo="Foco visible" nota="Recorre esto con el tabulador: anillo índigo de 2 px separado del control.">
        <div className="iv-panel p-5 flex flex-wrap gap-2 items-center">
          <Boton variante="secundario">Primero</Boton>
          <Boton variante="secundario">Segundo</Boton>
          <label htmlFor="estilos-foco" className="sr-only">Un campo</label>
          <Input id="estilos-foco" className="w-48" placeholder="Un campo" />
          <a href="#foco" className="text-marca text-apoyo underline underline-offset-4">Un enlace</a>
        </div>
      </Bloque>

      <Estado vacio tituloVacio="Fin de la guía" motivoVacio="La referencia escrita del sistema está en DESIGN.md, en la raíz del repositorio." />
    </PageShell>
  );
}
