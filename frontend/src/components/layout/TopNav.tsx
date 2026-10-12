import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";

// Overview first (it is the home page). Desktop: a pill group centred in the top bar
// (after semianalysis.com). Phone: its own underline row that scrolls sideways.
const TABS: [string, string][] = [
  ["/", "Overview"],
  ["/macro", "Radar"],
  ["/models", "Models"],
  ["/updates", "Memo"],
  ["/deep-research", "Deep Research"],
  ["/videos", "Videos"],
  ["/agents", "Agents"],
  ["/docs", "Docs"],
];

export function TopNav({ pill = false }: { pill?: boolean }) {
  return (
    <nav
      className={
        pill
          ? "hidden items-center gap-1 rounded-full border border-border bg-surface-2 p-1 lg:flex"
          : "flex shrink-0 gap-7 overflow-x-auto border-b border-border bg-surface px-4 lg:hidden"
      }
    >
      {TABS.map(([to, label]) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          className={({ isActive }) =>
            pill
              ? cn(
                  "whitespace-nowrap rounded-full px-4 py-2 text-[15px] font-medium transition-colors",
                  isActive ? "bg-surface text-text shadow-card ring-1 ring-border" : "text-text-2 hover:text-text",
                )
              : cn(
                  "whitespace-nowrap border-b-2 py-3 text-[15px] transition-colors",
                  isActive ? "border-text font-semibold text-text" : "border-transparent font-medium text-text-2 hover:text-text",
                )
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
