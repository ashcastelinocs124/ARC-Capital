import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";

// Sidebar order from before; tabs scroll sideways on a phone.
const TABS: [string, string][] = [
  ["/macro", "Macro & Signals"],
  ["/models", "Models"],
  ["/deep-research", "Deep Research"],
  ["/updates", "Daily Update"],
  ["/videos", "Videos"],
  ["/agents", "Agents"],
  ["/docs", "Docs"],
];

export function TopNav() {
  return (
    <nav className="shrink-0 bg-surface border-b border-border px-4 md:px-8 flex gap-7 overflow-x-auto">
      {TABS.map(([to, label]) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn(
              "py-3 text-sm whitespace-nowrap border-b-2 transition-colors",
              isActive
                ? "border-accent text-accent font-semibold"
                : "border-transparent text-text-2 font-medium hover:text-accent",
            )
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
