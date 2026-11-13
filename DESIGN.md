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
**Nota `--iv-marca`:** la utilidad de Tailwind `marca` lee `--iv-intencion`. `--iv-marca` queda como token heredado porque `lib/tokens.js` (fuera de esta fase) fija su respaldo claro en `172 78 8`; lo usaban a mano `CarteraCabecera`, `OpportunitiesView` (ambas ya migradas) y la línea «taza» del gráfico, que en tema claro aún salen en ámbar. Al migrar esos sitios a `--iv-intencion`, actualizar el respaldo y retirar el token.

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

- Segmentado (`base/Segmentado`): carril de luz baja con la opción elegida levantada (superficie + filo), sin índigo: elegir un filtro no es una acción principal. `mono` para opciones-código (1M, 3M), `tamano` sm/md.

## Pantalla «Cartera» (fase 2)
1. Titular + acciones (correlación en icono en móvil, Importar, Añadir posición).
2. **Una pieza héroe** a lo ancho: patrimonio invertido 44–64 px (céntimos y «€» reducidos), chip de latente con flecha, evolución en barras índigo (la última plena) con `Segmentado`; desglose tabular a la derecha (320 px) o debajo en móvil.
3. **Fila de riesgo** en 3 columnas: salud (nota héroe + medidor de 20 marcas + componentes), distribución (mayor peso como héroe, barra apilada, lista con € y %, aviso de concentración DENTRO del panel) y correlación.
4. Posiciones (lectura): filas ancladas con `Monograma`, estado con punto de color; en móvil lista de dos líneas.
5. Niveles y alertas (edición): tabla con cabecera fija y alto propio (`max-h: 100vh-140px`), dos columnas fijas opacas, sin columnas teñidas: niveles en tinta neutra (un nivel de compra no es una subida), deseado en `info`, el próximo nivel en ámbar con ◀. Posición = «N acc. / a precio» en una celda. En móvil, fichas con los niveles plegados en `<details>` cuyo resumen ya dice el siguiente nivel y su distancia.
- Paleta categórica de sectores renovada en tonos medios fríos (sin verde, rojo ni índigo); `CarteraCabecera` y `SignalsView` la comparten. `CarteraCabecera` ya no lee `--iv-marca`.

## Pantalla «Hoy» (fase 2)
Dos columnas: principal (cartera como métrica héroe de 40–60 px con «€» reducido, luego la lista de decisiones) y contexto de 336–364 px (mercado: régimen + futuros + miedo/codicia en un panel con filetes; calendario + cerebro; sectores como barras divergentes de ±3 %). En móvil, el contexto baja entero detrás de las decisiones.

## Pantalla «Ficha de acción» (fase 2)
1. **Watchlist en cinta** (`WatchlistStrip`): una línea con desplazamiento lateral (flechas en escritorio, máscara de fundido en los bordes), la acción abierta levantada y centrada. Sustituye a la columna lateral de 60 tarjetas.
2. **Cabecera héroe** (`QuoteHeader`): `Monograma lg` (48 px, nuevo tamaño) + ticker + nombre; corazón y alerta como botones de 36/44 px; precio a 44–64 px con «$» y céntimos reducidos y variación en píldora tintada; a la derecha, `base/Rango` (nuevo: pista con tramo recorrido y punto) para el día y las 52 semanas; franja inferior con apertura, anterior, volumen y capitalización. La alerta se abre como franja dentro de la pieza (con `Segmentado`).
3. **Dos columnas** (`1fr` + 352–368 px): gráfico justo bajo el precio y, a la derecha, «tu dinero»: lectura rápida (régimen, señal IA, 10 semanas, entrada/stop/TP1), tu posición (latente como cifra héroe de 32 px, desglose en filas, niveles en celdas de luz) y el simulador de margen (`Segmentado` + campo con la unidad dentro). En móvil esa columna cae entre el veredicto y el plan de entrada.
4. **Secciones** con titular Geist 18/600 y nota en tinta-3; 40–48 px entre secciones. La tesis es la pieza `iv-destacada` (titular 22 px, a favor/en contra con marcas cuadradas, pie con «Ampliar con IA»). El estado técnico es una ficha de celdas con filetes de 1 px.
5. El veto «No comprar» es `iv-halo-baja` con sello de 44 px y titular de 24 px; el aviso «Avísame» es botón principal.
6. `BottomSignalBar` tiene dos formas: `como="panel"` (escritorio, columna derecha) y la barra fija con vidrio (solo `< lg`).
7. IA, analistas, fuentes, noticias y detalle: cabeceras de bloque Geist 13–15, iconos en cuadrado de luz, botones `Boton` secundarios (adiós al contorno mono índigo); fuentes con recuento héroe y barra partida a favor/en contra; consenso y fuerza relativa en dos columnas.

## Piezas nuevas (fase 2 · Operaciones)
- **Cascada** (`base/Cascada`): una suma que se lee como suma. Cada sumando es una fila (rótulo + significado · barra · importe) y su barra empieza donde acabó la anterior; línea de cero si hay negativos. Verde/rojo por el signo de cada paso. Ayuda por fila como botón que despliega (no `title`), `extra` para lo que cuelga de una fila (p. ej. «de ello, efecto del euro»). No calcula nada de negocio: solo acumula lo que recibe; `null` se escribe «—» y no mueve la barra.
- **Pestanas** (`base/Pestanas` + `propsPanel`): vistas alternativas de un mismo hueco. Geist 14/500 con recuento en mono; activa en tinta con filo índigo de 2 px debajo; flechas ←/→ (patrón ARIA tablist).
- **Aviso / AvisosPanel** (`base/Aviso`): los avisos de datos como filas de UN panel con rótulo y recuento, icono en cuadrado ámbar de 32 px, titular de una frase y detalle en tinta-2; botones al pie. Sustituye a las cajas ámbar sueltas.

## Pantalla «Operaciones» (fase 2)
1. Titular con miga «Gestionar › Operaciones»; acciones a la derecha con `Boton` (una sola principal, «Registrar venta»; la abierta se marca en índigo suave). En móvil la principal ocupa la primera fila.
2. **Héroe** a lo ancho: Total como cifra héroe 44–64 px teñida por signo (céntimos y «€» reducidos) y debajo la `Cascada` realizado → latente → dividendos → costes. Columna derecha de 340 px con el método (`Segmentado` FIFO/LIFO), el interruptor «Ver como en DEGIRO» como conmutador y «¿cómo funciona?».
3. Avisos agrupados en `AvisosPanel` «Para cuadrar con DEGIRO» (solo si hay alguno).
4. `Pestanas`: Historial de ventas · Lo que tienes abierto · Por acción (se recuerda en `localStorage` `ventas.pestana`). Ventas agrupadas por mes con cabecera fija bajo la barra superior, filas ancladas con `Monograma` y detalle desplegado en dos columnas (línea de tiempo de lotes · la cuenta en divisa y euros). Lo abierto: tabla con monogramas en escritorio, fichas con franja de datos en móvil. Por acción: dos columnas con barra proporcional a la ganancia en euros.
5. Formularios como panel con `CabeceraForm` (icono en cuadrado índigo), campos de 40 px con foco índigo; `RiesgoVenta` como caja de luz baja (no panel dentro de panel) con la cifra en héroe 32 px. `ExtractoMargen` en una línea con icono, cifra y botones.

## Pantalla «Oportunidades» (fase 2)
- **Medidor** (`base/Medidor`, nuevo): hermano compacto de `Rango` para filas de tabla. Pista de 4 px, zonas opcionales teñidas bajo (`zonas: [{desde, hasta, tono}]`), marca vertical de 3 px donde cae el valor, `relleno` para puntuaciones. Neutro por defecto; si el valor no es número, no se pinta.
1. Titular de página fijo (miga «Decidir › Oportunidades») y las cuatro vistas como `Pestanas` con recuento (el modo sigue en `?modo=`).
2. **Héroe por vista**: cifra grande (44–60 px) de lo encontrado + metadatos (hora, «actualizando» como chip ámbar). En Señales, columna derecha de 400 px «Por tipo de señal»: cada categoría es una fila pulsable con barra proporcional — el reparto ES el filtro (activa: luz + filo índigo de 2 px). En Screener, la columna lleva el semáforo de mercado y los criterios del filtro.
3. **Señales como tabla** (≥ 1280 px): valor + lectura (monograma, categoría con punto, motivo, señales en línea) y columnas Score · RSI (zonas 30/70 en info/ámbar) · Soporte–Resistencia (medidor con el precio dentro) · Analistas (consenso en frase + nº) · Precio con variación en píldora. Cabecera fija bajo la barra superior. Por debajo, la misma fila es ficha con banda de luz de 2–4 celdas (`xl:contents`).
4. Categorías con paleta categórica fría (info, alerta, aviso, acento-2, intención, tinta-3): ya no hay verde/rojo para tipos de señal. `OpportunitiesView` ya no lee `--iv-marca`.
5. Screener: Top selección en `iv-destacada` con ranking y medidor; tarjetas con monograma, precio de 30 px con «$» reducido, filas etiqueta/valor, banda de crecimiento y aviso de resultados en caja roja suave.
6. Movers: tres paneles con ranking, monograma y barra de magnitud de la variación; en móvil un `Segmentado` (Subidas · Bajadas · Negociadas) muestra una lista a la vez.

## Pantalla «Calendario» (fase 2)
- **FranjaDias** (`base/FranjaDias`, nuevo): horizonte de «Hoy» a «+N d» en una pista con marca por día (por semana si N > 31), tramo índigo bajo hasta el último evento y un punto por fecha con los tickers encima (en móvil, solo el punto y el recuento). Tonos `marca` (hay algo en cartera), `neutro`, `pasado` (apagado, pegado a «Hoy»). Es `aria-hidden`: la información está en la lista.
1. Titular con miga «Gestionar › Calendario»; el periodo es `Segmentado` (7 · 14 · 30 · 60 días) y «Actualizar» un `Boton` secundario (solo icono de 40 px en móvil).
2. **Héroe**: los días que faltan para el próximo resultado como cifra 44–60 px («Hoy»/«Mañana» en palabra), monograma + ticker + grupo + fecha/trimestre/momento, y la `FranjaDias` debajo. Columna de 340 px con el recuento (resultados y fechas) y el reparto En cartera / Vigilando / Cimientos con barra.
3. **Agenda**: un panel; cada fecha es una fila con baldosa de día (número 28 px + día/mes, relativa debajo; índigo si es hoy/mañana, atenuada si ya pasó) y sus resultados en rejilla Valor · Trimestre · Momento (icono amanecer/luna/reloj) · EPS est. con cabecera de columnas. En móvil la fila baja a dos líneas sin monograma y la relativa encabeza la fecha.

## Pendiente (fases siguientes)
Cada pantalla hereda el sistema pero conserva maquetación propia: la tabla de niveles de Cartera aún necesita desplazamiento horizontal por debajo de ~1400 px de lienzo, fichas con cajas anidadas y cifras de tabla en mono negrita que conviene aligerar. En la ficha, `LightweightChart` (fuera de esta fase) mantiene sus botones de escala con relleno índigo y su leyenda; y el interior de `TradingLevels`/`ChartistPanel` (zonas, stops, plan) solo se ha aligerado, no recompuesto.
