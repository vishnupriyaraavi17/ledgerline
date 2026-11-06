/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        finance: {
          bg: "#f8fafc",        // Neutral slate-50 background
          card: "#ffffff",      // Clean white card background
          border: "#e2e8f0",    // Subtle slate-200 border
          text: "#0f172a",      // Dark navy / charcoal text (slate-900)
          muted: "#64748b",     // Muted slate-500
          navy: "#1e293b",      // Deep navy (slate-800)
          navyDark: "#090d16",  // Ultra dark navy header
          emerald: "#059669",   // Vibrant green for success / balanced books
          emeraldLight: "#ecfdf5",
          rose: "#dc2626",      // Crimson red for errors / alerts
          roseLight: "#fef2f2",
          amber: "#d97706",     // Amber for warnings
          amberLight: "#fffbeb",
        }
      },
      fontFamily: {
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
