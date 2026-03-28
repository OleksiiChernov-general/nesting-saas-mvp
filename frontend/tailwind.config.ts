import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#f9fafb",
        steel: "#9ca3af",
        accent: "#10b981",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "Consolas", "monospace"],
      },
      boxShadow: {
        panel: "0 18px 40px rgba(0, 0, 0, 0.34)",
      },
    },
  },
  plugins: [],
} satisfies Config;
