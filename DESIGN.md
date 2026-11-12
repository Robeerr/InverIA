# InverIA · Sistema de diseño «Grafito e índigo» (v2)

Guía viva: `/sistema/estilos` (mide el contraste en tiempo real). Fuente de verdad del código:
`frontend/src/styles/tokens.css`, `frontend/src/index.css`, `frontend/tailwind.config.js`.

## Idea
Una sala de lectura de noche. Grafito frío, superficies que suben de luz por capas, **un único color de intención (índigo)** y el verde/rojo reservados a lo único que significan: subir y bajar. Sustituye a la «terminal» naranja con etiquetas monoespaciadas en versalitas.

## Reglas
1. **Índigo = intención.** Acción principal, lugar actual (rail), foco, enlaces. Nunca un dato.
2. **Verde/rojo = dirección** de una cifra. Nunca botones ni decoración.
3. **Elevación por luz**, no por cajas: fondo → superficie → superficie-2. Una pieza dentro de otra pierde borde y sombra (`.iv-panel .iv-panel`).
4. **Tres niveles de texto** como mucho por bloque (tinta, tinta-2, tinta-3).
5. **Etiquetas en Geist, minúscula de frase.** Geist Mono solo para cifras tabulares. Las versalitas mono espaciadas antiguas se neutralizan globalmente en `index.css`.

## Color (tripletes RGB → `bg-marca/10` funciona)
| Token | Oscuro (referencia) | Claro | Uso |
|---|---|---|---|
| `fondo` | `#0e0f14` | `#f6f6f8` | lienzo |
| `superficie` | `#16171e` | `#ffffff` | piezas |
| `superficie-2` | `#1e2029` | `#f1f1f4` | capa interior, campos |
| `tinta` / `-2` / `-3` | `#ecedf3` / `#b0b3c2` / `#8a8da0` | `#111114` / `#3f3f48` / `#5c5c68` | texto |
| `intencion` (utilidad `marca`) | `#8d8eff` | `#4f46e5` | intención |
| `--iv-marca` (heredado) | `#8d8eff` | `#ac4e08` | solo lo leen a mano 3 sitios sin migrar; ver nota |
| `acento-2` | `#b28cff` | `#7c3aed` | segundo tono del sello |
| `sube` / `baja` | `#4fc28c` / `#f0707e` | `#047857` / `#be123c` | dirección |
| `aviso` / `alerta` / `info` | `#e5bd5c` / `#f09668` / `#64beeb` | `#925c06` / `#c2410c` / `#1d4ed8` | estados |

Bordes de pieza: `--borde-suave` (blanco 6,5 %) y `--borde-medio` (11 %) → utilidades `border-suave`, `border-medio`.
Botón principal: relleno `--boton-fondo` (índigo más profundo, texto blanco ≥ 5:1).
Contraste: todos los roles de texto ≥ 4,5:1 sobre las tres superficies (lo verifica `styles/tokens.test.js`; peor caso oscuro ≈ 4,95:1).
`lib/tokens.js` repite los valores claros como respaldo para el gráfico; un test vigila que coincidan.
**Nota `--iv-marca`:** la utilidad de Tailwind `marca` lee `--iv-intencion`. `--iv-marca` queda como token heredado porque `lib/tokens.js` (fuera de esta fase) fija su respaldo claro en `172 78 8`; lo usan a mano `CarteraCabecera`, `OpportunitiesView` y la línea «taza» del gráfico, que en tema claro aún salen en ámbar. Al migrar esos sitios a `--iv-intencion`, actualizar el respaldo y retirar el token.

## Tipografía
- **Geist** (UI, titulares, cifra héroe con `tnum`), **Geist Mono** (columnas de cifras). Cargadas por `<link>` en `public/index.html`.
- Escala (`tailwind.config.js`): `etiqueta` 12 · `apoyo` 13 · `cuerpo` 14,5 · `titulo` 18 · `cifra` 28 · `heroe` 44. Titulares con tracking negativo (−0,02 a −0,045 em).
- Clases: `.iv-cifra-hero` (Geist 600 tabular, tinta plena), `.iv-cifra` (Geist Mono tabular), `.iv-etiqueta` (Geist 12/500, tinta-3), `.iv-verbo` (titular de pantalla, clamp 28–42 px).
- **Ojo con `cn()`**: usa tailwind-merge sin configurar y toma `text-cifra`/`text-apoyo` por colores. En componentes que pasan por `cn`, usar tamaños explícitos (`text-[13px]`).

## Forma
- Radios: 8 (`rounded`, `rounded-iv-sm`) · 12 (`rounded-iv`, campos) · 16 (`rounded-iv-lg`, piezas). Botones 10 px (no píldora).
- Sombras: `shadow-panel` (corta y suave), `shadow-flotante` (menús, cajón, avisos).
- Superficies: `.iv-panel`, `.iv-destacada` (filo índigo + luz en esquina), `.iv-halo-{sube,baja,marca,info}` (tinte, sin resplandor), `.iv-fila`.
- Sección: `.iv-seccion` sin filete; `.iv-seccion-acento` añade un punto índigo.

## Armazón
- **Rail** (`components/Rail.jsx`): 240 px, compacto 68 px (solo iconos, recordado en `localStorage` `inveria-rail` y publicado como `html[data-rail="compacto"]` → `--rail-w`). Grupos Decidir / Gestionar / Entender, herramientas al pie. Activo: fondo de luz, icono índigo y pestaña índigo en el borde. Iconos lucide a 17 px, trazo 1,75. Sello de marca: `<Sello />`.
- **Cabecera** (`components/Header.jsx`): 56 px, vidrio (`--vidrio` + blur), nombre de la pantalla a la izquierda, buscador centrado (máx. 460 px), estado en píldora, avatar con inicial.
- **Lienzo** (`App.js`): `max-w-[1440px]`, `px-4 sm:px-8`, `py-5 sm:py-8`; entrada `.iv-entra`. `PageShell` usa el mismo armazón con h1 de 26/32 px.
- **Pie**: aviso legal íntegro a la izquierda, fuentes a la derecha.

## Movimiento (Emil Kowalski)
- Curva de salida `cubic-bezier(0.23,1,0.32,1)` (`ease-salida`), 150 ms en hover/foco/pulsar, 220 ms en entradas.
- Pulsar: `scale(0.98)` en todo `<button>` (global, especificidad cero).
- Entrada de pantalla: opacidad + 6 px. Cajón móvil: 300 ms curva de cajón iOS.
- Esqueletos con barrido (`.iv-esqueleto`) en lugar de parpadeo.
- `prefers-reduced-motion`: sin desplazamientos ni barridos (App.css + tokens.css).

## Datos
- Tablas: cabecera tenue en minúscula, hover de fila (`tbody tr:hover`), separadores `border-suave`, cifras `iv-cifra` alineadas a la derecha. En móvil, lista (patrón en la guía).
- Chips (`base/Chip`): Geist 12/500, radio 6, fondo 11 % del tono. Solo cuando aportan.
- Métricas (`base/Metrica`): `sm`/`md` en mono, `lg`/`xl` como cifra héroe. Teñir por signo hay que pedirlo (`tono="auto"`).
- Estados (`base/Estado`): cargando con forma, vacío con motivo, error con causa y reintento.
- Monograma (`base/Monograma`): cuadrado de 32/40 px con las letras del ticker en Geist Mono; ancla las filas de lista (no hay logotipos y no se inventan). Se tiñe solo si la fila lo pide (`tono`).
- Cabecera de bloque (`base/CabeceraBloque`): icono lucide 16 px en tinta-3 + rótulo Geist 13/500 + nota o enlace a la derecha. Nivel por debajo del titular de sección.
- Listas de decisión (`base/TarjetaAtencion`): filas en un único panel, partidas en tramos rotulados («Piden decisión» / «Para vigilar»); urgentes con filo de color de 3 px a la izquierda y chip sólido; lectura numérica en columna fija de 264 px (escritorio) o franja de luz 2–4 columnas (móvil).

## Pantalla «Hoy» (fase 2)
Dos columnas: principal (cartera como métrica héroe de 40–60 px con «€» reducido, luego la lista de decisiones) y contexto de 336–364 px (mercado: régimen + futuros + miedo/codicia en un panel con filetes; calendario + cerebro; sectores como barras divergentes de ±3 %). En móvil, el contexto baja entero detrás de las decisiones.

## Pendiente (fases siguientes)
Cada pantalla hereda el sistema pero conserva maquetación propia: tablas anchas de Cartera (niveles) y su desplazamiento horizontal, fichas con cajas anidadas, cifras de tabla en mono negrita que conviene aligerar, y la barra de señal inferior de la ficha.
