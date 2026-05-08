import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Globe,
  Microscope,
  ShieldAlert,
  Bot,
  CheckSquare,
  Settings,
  Bell,
  PanelLeftClose,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useApprovalMetrics } from "@/hooks/useApprovals";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const items: NavItem[] = [
  { to: "/portfolio", label: "Portfolio", icon: LayoutDashboard },
  { to: "/macro", label: "Macro & Signals", icon: Globe },
  { to: "/research", label: "Research", icon: Microscope },
  { to: "/risk", label: "Risk", icon: ShieldAlert },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/approvals", label: "Approvals", icon: CheckSquare },
];

export function Sidebar() {
  const { data: metrics } = useApprovalMetrics();
  const pendingCount = parseInt(metrics?.[0]?.value || "0", 10);

  return (
    <aside className="w-60 h-screen bg-surface border-r border-border flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-text flex items-center justify-center text-white font-bold text-sm">
            C
          </div>
          <div className="text-base font-bold tracking-tight text-text">CKM Capital</div>
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
                  ? "bg-surface-3 text-text"
                  : "text-text-2 hover:bg-surface-2",
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={cn("h-4 w-4 shrink-0", isActive ? "text-text" : "text-muted")} />
                <span className="flex-1">{label}</span>
                {to === "/approvals" && pendingCount > 0 && (
                  <span className="text-xs font-semibold px-1.5 py-0.5 rounded-md bg-danger text-white animate-pulse-slow">
                    {pendingCount}
                  </span>
                )}
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
