import { useState } from "react";
import { Moon, Sun } from "lucide-react";

const KEY = "arc.theme"; // "dark" | "light"; index.html applies it before the first paint

export function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const flip = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(KEY, next ? "dark" : "light");
    } catch {
      /* storage blocked: the theme still switches, just isn't remembered */
    }
    setDark(next);
  };
  return (
    <button
      onClick={flip}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      title={dark ? "Light theme" : "Dark theme"}
      className="grid h-9 w-9 place-items-center rounded-full border border-border bg-surface text-text-2 hover:text-accent"
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}
