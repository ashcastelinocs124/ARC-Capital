import { NavLink } from "react-router-dom";
import {
  Cpu,
  Globe,
  Telescope,
  Newspaper,
  Bot,
  BookOpen,
  Settings,
  Bell,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/cn";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const items: NavItem[] = [
  { to: "/macro", label: "Macro & Signals", icon: Globe },
  { to: "/models", label: "Models", icon: Cpu },
  { to: "/deep-research", label: "Deep Research", icon: Telescope },
  { to: "/updates", label: "Daily Update", icon: Newspaper },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/docs", label: "Documentation", icon: BookOpen },
];

const COLLAPSED_KEY = "arc.sidebar.collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false; // storage blocked (private mode, previews)
  }
}

// `collapsible` is off in the phone drawer, which is always full width.
export function Sidebar({ collapsible = true }: { collapsible?: boolean }) {
  const [collapsed, setCollapsed] = useState(() => collapsible && readCollapsed());
  const toggle = () => {
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, c ? "0" : "1");
      } catch {
        /* not remembered, still toggles */
      }
      return !c;
    });
  };

  return (
    <aside
      className={cn(
        "h-full bg-surface border-r border-border flex flex-col transition-[width] duration-200",
        collapsed ? "w-16" : "w-60",
      )}
    >
      {/* Logo */}
      <div className={cn("py-5", collapsed ? "px-3" : "px-5")}>
        <div className="flex items-center gap-2.5">
          <img src="/arc-logo.png" alt="ARC" className={cn("w-auto", collapsed ? "h-7" : "h-9")} />
          {!collapsed && <div className="text-base font-bold tracking-tight text-text">ARC Research</div>}
        </div>
      </div>

      {/* Nav */}
      <nav className={cn("flex-1 py-2 space-y-0.5", collapsed ? "px-2" : "px-3")}>
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? label : undefined}
            aria-label={label}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 py-2 rounded-lg text-sm font-medium transition-colors",
                collapsed ? "justify-center px-0" : "px-3",
                isActive
                  ? "bg-accent-soft text-accent"
                  : "text-text-2 hover:bg-surface-2",
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={cn("h-4 w-4 shrink-0", isActive ? "text-accent" : "text-muted")} />
                {!collapsed && <span className="flex-1">{label}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User block at bottom */}
      <div className={cn("border-t border-border py-3", collapsed ? "px-2" : "px-4")}>
        <div className={cn("flex items-center gap-2.5 mb-3", collapsed && "justify-center")}>
          <div
            title={collapsed ? "Ashleyn Castelino" : undefined}
            className="w-9 h-9 shrink-0 rounded-full bg-text flex items-center justify-center text-white text-sm font-semibold"
          >
            AC
          </div>
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-text truncate">Ashleyn Castelino</div>
              <div className="text-xs text-muted truncate">ashleyncastelino@gmail.com</div>
            </div>
          )}
        </div>
        <div className={cn("flex items-center gap-1", collapsed && "justify-center")}>
          {!collapsed && <IconButton><Settings className="h-3.5 w-3.5" /></IconButton>}
          {!collapsed && <IconButton><Bell className="h-3.5 w-3.5" /></IconButton>}
          {collapsible && (
            <IconButton
              className={collapsed ? undefined : "ml-auto"}
              onClick={toggle}
              label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? <PanelLeftOpen className="h-3.5 w-3.5" /> : <PanelLeftClose className="h-3.5 w-3.5" />}
            </IconButton>
          )}
        </div>
      </div>
    </aside>
  );
}

function IconButton({
  children,
  className,
  onClick,
  label,
}: {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  label?: string;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        "h-7 w-7 inline-flex items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-text-2 transition-colors",
        className,
      )}
    >
      {children}
    </button>
  );
}
