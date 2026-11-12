/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
    extend: {
      borderRadius: {
        // `rounded` a secas → radio pequeño de la casa (8 px). Escala: 8 · 12 · 16.
        DEFAULT: 'var(--iv-radio-sm)',
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
        // Escala de InverIA: tres radios, no los cuatro sueltos que hay hoy a mano.
        iv: 'var(--iv-radio)',
        'iv-sm': 'var(--iv-radio-sm)',
        'iv-lg': 'var(--iv-radio-lg)',
      },
      // Escala tipográfica cerrada (Geist), con 12px como suelo de lectura y 11px
      // solo para micro-etiquetas. Seis pasos: etiqueta → héroe. Un bloque usa
      // como mucho tres.
      fontSize: {
        etiqueta: ['12px', { lineHeight: '1.35', letterSpacing: '0' }],
        apoyo: ['13px', { lineHeight: '1.5', letterSpacing: '-0.003em' }],
        cuerpo: ['14.5px', { lineHeight: '1.55', letterSpacing: '-0.006em' }],
        titulo: ['18px', { lineHeight: '1.3', letterSpacing: '-0.02em' }],
        cifra: ['28px', { lineHeight: '1.1', letterSpacing: '-0.035em' }],
        heroe: ['44px', { lineHeight: '1', letterSpacing: '-0.045em' }],
      },
      fontFamily: {
        sans: ['Geist', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        heading: ['Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Geist Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        panel: 'var(--sombra-panel)',
        flotante: 'var(--sombra-flotante)',
      },
      transitionTimingFunction: {
        salida: 'cubic-bezier(0.23, 1, 0.32, 1)',
        mover: 'cubic-bezier(0.77, 0, 0.175, 1)',
      },
      borderColor: {
        suave: 'var(--borde-suave)',
        medio: 'var(--borde-medio)',
      },
      colors: {
        // ── Tokens semánticos de InverIA ─────────────────────────────────────
        // Definidos en src/styles/tokens.css como tripletes RGB para que estas
        // utilidades admitan opacidad (`bg-sube/10`, `border-baja/30`), que es un
        // patrón muy usado en este código y que se pierde si el token es un hex.
        //
        // Conviven con los tokens de shadcn de más abajo (background, card,
        // primary…), que consumen `ui/button` y compañía y NO se tocan.
        fondo: 'rgb(var(--iv-fondo) / <alpha-value>)',
        superficie: {
          DEFAULT: 'rgb(var(--iv-superficie) / <alpha-value>)',
          alt: 'rgb(var(--iv-superficie-2) / <alpha-value>)',
        },
        linea: {
          DEFAULT: 'rgb(var(--iv-linea) / <alpha-value>)',
          fuerte: 'rgb(var(--iv-linea-fuerte) / <alpha-value>)',
          marcada: 'rgb(var(--iv-linea-marcada) / <alpha-value>)',
        },
        tinta: {
          DEFAULT: 'rgb(var(--iv-tinta) / <alpha-value>)',
          2: 'rgb(var(--iv-tinta-2) / <alpha-value>)',
          3: 'rgb(var(--iv-tinta-3) / <alpha-value>)',
        },
        marca: {
          // La utilidad `marca` es la INTENCIÓN (índigo). `--iv-marca` es un token
          // heredado que ya no pinta el sistema (ver styles/tokens.css).
          DEFAULT: 'rgb(var(--iv-intencion) / <alpha-value>)',
          tinta: 'rgb(var(--iv-marca-tinta) / <alpha-value>)',
        },
        sube: 'rgb(var(--iv-sube) / <alpha-value>)',
        baja: 'rgb(var(--iv-baja) / <alpha-value>)',
        aviso: 'rgb(var(--iv-aviso) / <alpha-value>)',
        alerta: 'rgb(var(--iv-alerta) / <alpha-value>)',
        info: 'rgb(var(--iv-info) / <alpha-value>)',
        neutro: 'rgb(var(--iv-neutro) / <alpha-value>)',

        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))'
        }
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0'
          },
          to: {
            height: 'var(--radix-accordion-content-height)'
          }
        },
        'accordion-up': {
          from: {
            height: 'var(--radix-accordion-content-height)'
          },
          to: {
            height: '0'
          }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out'
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
};