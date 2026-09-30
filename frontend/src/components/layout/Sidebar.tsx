import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Cpu,
  Globe,
  Microscope,
  Telescope,
  Newspaper,
  ShieldAlert,
  Bot,
  Settings,
  Bell,
  PanelLeftClose,
} from "lucide-react";
import { cn } from "@/lib/cn";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const items: NavItem[] = [
  { to: "/portfolio", label: "Portfolio", icon: LayoutDashboard },
  { to: "/models", label: "Models", icon: Cpu },
  { to: "/macro", label: "Macro & Signals", icon: Globe },
  { to: "/research", label: "Research", icon: Microscope },
  { to: "/deep-research", label: "Deep Research", icon: Telescope },
  { to: "/updates", label: "Daily Update", icon: Newspaper },
  { to: "/risk", label: "Risk", icon: ShieldAlert },
  { to: "/agents", label: "Agents", icon: Bot },
];

export function Sidebar() {

  return (
    <aside className="w-60 h-screen bg-surface border-r border-border flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5">
        <div className="flex items-center gap-2.5">
          <img src="/arc-logo.png" alt="ARC" className="h-9 w-auto" />
          <div className="text-base font-bold tracking-tight text-text">ARC Research</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-2 space-y-0.5">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                isActive
                  ? "bg-accent-soft text-accent"
                  : "text-text-2 hover:bg-surface-2",
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={cn("h-4 w-4 shrink-0", isActive ? "text-accent" : "text-muted")} />
                <span className="flex-1">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User block at bottom */}
      <div className="border-t border-border px-4 py-3">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-9 h-9 rounded-full bg-text flex items-center justify-center text-white text-sm font-semibold">
            AC
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-text truncate">Ashleyn Castelino</div>
            <div className="text-xs text-muted truncate">ashleyn4@illinois.edu</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <IconButton><Settings className="h-3.5 w-3.5" /></IconButton>
          <IconButton><Bell className="h-3.5 w-3.5" /></IconButton>
          <IconButton className="ml-auto"><PanelLeftClose className="h-3.5 w-3.5" /></IconButton>
        </div>
      </div>
    </aside>
  );
}

function IconButton({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <button
      className={cn(
        "h-7 w-7 inline-flex items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-text-2 transition-colors",
        className,
      )}
    >
      {children}
    </button>
  );
}
