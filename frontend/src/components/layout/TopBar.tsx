import { useLocation } from "react-router-dom";
import { ChevronLeft, ChevronRight, Activity, Menu, Mail } from "lucide-react";
import { usePortfolioMetrics } from "@/hooks/usePortfolio";
import { RefreshButton } from "@/components/layout/RefreshButton";
import { STATIC } from "@/api/client";
import { pageEnabled } from "@/pages/visibility";

const TITLES: Record<string, { section: string; page: string }> = {
  "/portfolio": { section: "Trading", page: "Portfolio" },
  "/models": { section: "Trading", page: "Models" },
  "/macro": { section: "Trading", page: "Macro & Signals" },
  "/research": { section: "Trading", page: "Research" },
  "/deep-research": { section: "Trading", page: "Deep Research" },
  "/updates": { section: "Trading", page: "Daily Update" },
  "/risk": { section: "Trading", page: "Risk & Attribution" },
  "/agents": { section: "Trading", page: "Agents" },
  "/approvals": { section: "Trading", page: "Approval Center" },
};

export function TopBar({ onMenu }: { onMenu: () => void }) {
  const location = useLocation();
  const { data: metrics } = usePortfolioMetrics();
  const crumb = TITLES[location.pathname] || { section: "ARC", page: "Dashboard" };

  const nav = pageEnabled("/portfolio") ? metrics?.find((m) => m.label === "NAV") : undefined;
  const navDelta = nav?.delta || "";
  const navIsUp = navDelta.startsWith("+");
  const navIsDown = navDelta.startsWith("-");

  return (
    <header className="h-14 shrink-0 bg-surface-2 flex items-center justify-between px-4 md:px-8">
      {/* Left: nav arrows + breadcrumb */}
      <div className="flex items-center gap-3">
        <button onClick={onMenu} aria-label="Open menu"
          className="md:hidden h-8 w-8 -ml-1 inline-flex items-center justify-center rounded-md text-text-2 hover:bg-surface-3">
          <Menu className="h-5 w-5" />
        </button>
        <div className="hidden md:flex items-center gap-1">
          <button className="h-7 w-7 inline-flex items-center justify-center rounded-md text-muted hover:bg-surface-3 hover:text-text-2">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button className="h-7 w-7 inline-flex items-center justify-center rounded-md text-muted hover:bg-surface-3 hover:text-text-2">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        <nav className="flex items-center gap-2 text-sm">
          <span className="hidden sm:inline text-muted">{crumb.section}</span>
          <span className="hidden sm:inline text-muted-2">/</span>
          <span className="text-text font-medium">{crumb.page}</span>
        </nav>
      </div>

      {/* Right: live metrics */}
      <div className="flex items-center gap-3 md:gap-5 text-sm">
        {nav && (
          <div className="hidden sm:flex items-baseline gap-2">
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
        <a href="https://archresearch.substack.com/" target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 font-medium text-text-2 hover:bg-surface-3 hover:text-text">
          <Mail className="h-4 w-4" />
          Newsletter
        </a>
        {!STATIC && <RefreshButton />}
        <div className="flex items-center gap-1.5 text-muted">
          <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse-slow" />
          <Activity className="h-3.5 w-3.5" />
          <span className="text-xs">Live</span>
        </div>
      </div>
    </header>
  );
}
