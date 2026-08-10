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
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
        // Escala de InverIA: tres radios, no los cuatro sueltos que hay hoy a mano.
        iv: 'var(--iv-radio)',
        'iv-sm': 'var(--iv-radio-sm)',
        'iv-lg': 'var(--iv-radio-lg)',
      },
      // Escala tipográfica cerrada de cinco pasos, con 11px como SUELO ABSOLUTO.
      // Hoy hay `text-[9px]` en sitios de lectura: por debajo de 11px el texto no
      // se lee, se adivina. Cinco pasos bastan para toda la app y evitan que cada
      // pantalla invente su propio tamaño.
      fontSize: {
        etiqueta: ['11px', { lineHeight: '1.35', letterSpacing: '0.08em' }],
        apoyo: ['13px', { lineHeight: '1.45' }],
        cuerpo: ['15px', { lineHeight: '1.55' }],
        titulo: ['19px', { lineHeight: '1.3', letterSpacing: '-0.01em' }],
        cifra: ['26px', { lineHeight: '1.15', letterSpacing: '-0.02em' }],
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
          DEFAULT: 'rgb(var(--iv-marca) / <alpha-value>)',
          tinta: 'rgb(var(--iv-marca-tinta) / <alpha-value>)',
        },
        sube: 'rgb(var(--iv-sube) / <alpha-value>)',
        baja: 'rgb(var(--iv-baja) / <alpha-value>)',
        aviso: 'rgb(var(--iv-aviso) / <alpha-value>)',
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