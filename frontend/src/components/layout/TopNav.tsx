import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";

// Overview first (it is the home page); tabs scroll sideways on a phone.
const TABS: [string, string][] = [
  ["/", "Overview"],
  ["/models", "Models"],
  ["/macro", "Macro & Signals"],
  ["/updates", "Memo"],
  ["/deep-research", "Deep Research"],
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
          end={to === "/"}
          className={({ isActive }) =>
            cn(
              "py-3 text-sm whitespace-nowrap border-b-2 transition-colors",
              isActive
                ? "border-text text-text font-semibold"
                : "border-transparent text-text-2 font-medium hover:text-text",
            )
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
