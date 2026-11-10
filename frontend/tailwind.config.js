/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        forest: {
          darkest: "#0B231D",
          DEFAULT: "#102F28",
          hover: "#16382C",
          primary: "#1F5244",
          light: "#2A6857",
        },
        cream: {
          canvas: "#F6F7F4",
          soft: "#FBFBF9",
          DEFAULT: "#F6F7F4",
        },
        sage: {
          badge: "#EDF4ED",
          border: "#E5EBE4",
          text: "#38724C",
          muted: "#6D7C73",
          accent: "#8BC7AE",
        },
        terracotta: {
          badge: "#FCF1E8",
          border: "#F0DCD2",
          text: "#9B5540",
          alert: "#854B35",
        },
        ink: {
          DEFAULT: "#1D2B27",
          secondary: "#4A5550",
          muted: "#89938E",
          border: "#E8EBE6",
        },
        finance: {
          bg: "#F6F7F4",        // Warm porcelain / cream canvas
          card: "#FFFFFF",      // Clean white card surface
          border: "#E8EBE6",    // Warm refined border
          text: "#1D2B27",      // Deep dark forest charcoal ink
          muted: "#6D7C73",     // Soft sage gray
          navy: "#102F28",      // Forest green primary
          navyDark: "#0B231D",  // Deepest pine
          emerald: "#38724C",   // Forest green credit
          emeraldLight: "#EDF4ED",
          rose: "#9B5540",      // Terracotta red debit
          roseLight: "#FCF1E8",
          amber: "#B45309",
          amberLight: "#FEF3C7",
        }
      },
      fontFamily: {
        serif: [
          '"Playfair Display"',
          'Georgia',
          'Cambria',
          'serif',
        ],
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'sans-serif',
        ],
        mono: [
          '"JetBrains Mono"',
          'Consolas',
          'monospace',
        ],
      }
    },
  },
  plugins: [],
}
