import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      // Every color is a CSS variable (src/index.css: :root = light, .dark = dark) so the theme toggle swaps them all.
      colors: Object.fromEntries(
        [
        "background",
        "surface",
        "surface-2",
        "surface-3",
        "border",
        "border-soft",
        "border-strong",
        "rail",
        "text",
        "text-2",
        "muted",
        "muted-2",
        "accent",
        "accent-hover",
        "accent-soft",
        "accent-soft-2",
        "on-accent",
        "success",
        "success-soft",
        "danger",
        "danger-soft",
        "warning",
        "warning-soft",
        "info",
        "info-soft",
        ].map((n) => [n, `rgb(var(--c-${n}) / <alpha-value>)`]),
      ),
      // ponytail: info/success/... keep their names; hover:bg-emerald-600 / red-600 in ui/button.tsx stay raw Tailwind.
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
        serif: ['"Source Serif 4"', 'Georgia', 'serif'],
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
        "card-hover": "0 0 0 1px rgb(var(--c-text))", // Damnang-style ink outline instead of a lift
      },
    },
  },
  plugins: [],
} satisfies Config;
