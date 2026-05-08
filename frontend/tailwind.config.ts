import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Monochrome base with functional color accents (P&L green/red kept for semantics)
        background: "#ffffff",
        surface: "#ffffff",
        "surface-2": "#f7f7f8",      // page bg / hover
        "surface-3": "#ececef",      // stronger gray
        border: "#e5e5e7",
        "border-strong": "#d4d4d7",
        text: "#0a0a0a",             // near-black
        "text-2": "#27272a",
        muted: "#71717a",            // mid gray
        "muted-2": "#a1a1aa",        // light gray

        // Primary accent: monochrome (near-black)
        accent: "#0a0a0a",
        "accent-hover": "#27272a",
        "accent-soft": "#f4f4f5",    // active sidebar bg (subtle gray)
        "accent-soft-2": "#e4e4e7",

        // Functional colors — kept for trading data semantics
        success: "#16a34a",
        "success-soft": "#dcfce7",
        danger: "#dc2626",
        "danger-soft": "#fee2e2",
        warning: "#d97706",
        "warning-soft": "#fef3c7",
        info: "#52525b",             // info → muted slate, not blue
        "info-soft": "#f4f4f5",
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      fontSize: {
        xs: ["11px", "16px"],
        sm: ["13px", "20px"],
        base: ["14px", "22px"],
        lg: ["16px", "24px"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.04)",
        "card-hover": "0 4px 12px -2px rgb(0 0 0 / 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;
