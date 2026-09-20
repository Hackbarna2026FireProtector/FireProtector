/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B1220",
        panel: "#111A2E",
        raised: "#16213A",
        border: "#23304D",
        text: {
          primary: "#E6EDF7",
          secondary: "#9AA8C2",
          muted: "#6B7A99",
        },
        fire: {
          amber: "#F59E0B",
          orange: "#F97316",
          red: "#EF4444",
        },
        tier: {
          critical: "#EF4444",
          high: "#F97316",
          medium: "#F59E0B",
          low: "#EAB308",
          safe: "#64748B",
        },
        accent: "#38BDF8",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
