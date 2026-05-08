import { useLocation } from "react-router-dom";
import { ChevronLeft, ChevronRight, Activity } from "lucide-react";
import { usePortfolioMetrics } from "@/hooks/usePortfolio";

const TITLES: Record<string, { section: string; page: string }> = {
  "/portfolio": { section: "Trading", page: "Portfolio" },
  "/macro": { section: "Trading", page: "Macro & Signals" },
  "/research": { section: "Trading", page: "Research" },
  "/risk": { section: "Trading", page: "Risk & Attribution" },
  "/agents": { section: "Trading", page: "Agent Decisions" },
  "/approvals": { section: "Trading", page: "Approval Center" },
};

export function TopBar() {
  const location = useLocation();
  const { data: metrics } = usePortfolioMetrics();
  const crumb = TITLES[location.pathname] || { section: "CKM", page: "Dashboard" };

  const nav = metrics?.find((m) => m.label === "NAV");
  const navDelta = nav?.delta || "";
  const navIsUp = navDelta.startsWith("+");
  const navIsDown = navDelta.startsWith("-");

  return (
    <header className="h-14 bg-surface-2 flex items-center justify-between px-8">
      {/* Left: nav arrows + breadcrumb */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <button className="h-7 w-7 inline-flex items-center justify-center rounded-md text-muted hover:bg-surface-3 hover:text-text-2">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button className="h-7 w-7 inline-flex items-center justify-center rounded-md text-muted hover:bg-surface-3 hover:text-text-2">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        <nav className="flex items-center gap-2 text-sm">
          <span className="text-muted">{crumb.section}</span>
          <span className="text-muted-2">/</span>
          <span className="text-text font-medium">{crumb.page}</span>
        </nav>
      </div>

      {/* Right: live metrics */}
      <div className="flex items-center gap-5 text-sm">
        {nav && (
          <div className="flex items-baseline gap-2">
            <span className="text-xs text-muted">NAV</span>
            <span className="font-mono font-semibold num">{nav.value}</span>
            {navDelta && (
              <span
                className={
                  navIsUp ? "text-success text-xs font-medium"
                  : navIsDown ? "text-danger text-xs font-medium"
                  : "text-muted text-xs"
                }
              >
                {navDelta}
              </span>
            )}
          </div>
        )}
        <div className="flex items-center gap-1.5 text-muted">
          <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse-slow" />
          <Activity className="h-3.5 w-3.5" />
          <span className="text-xs">Live</span>
        </div>
      </div>
    </header>
  );
}
