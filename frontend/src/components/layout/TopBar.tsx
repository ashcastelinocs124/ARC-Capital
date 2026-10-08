import { useLocation } from "react-router-dom";
import { ChevronLeft, ChevronRight, Activity, Menu, Mail } from "lucide-react";
import { RefreshButton } from "@/components/layout/RefreshButton";
import { STATIC } from "@/api/client";

const TITLES: Record<string, { section: string; page: string }> = {
  "/models": { section: "Research", page: "Models" },
  "/macro": { section: "Research", page: "Macro & Signals" },
  "/deep-research": { section: "Research", page: "Deep Research" },
  "/updates": { section: "Research", page: "Daily Update" },
  "/agents": { section: "Research", page: "Agents" },
  "/docs": { section: "Research", page: "Documentation" },
};

export function TopBar({ onMenu }: { onMenu: () => void }) {
  const location = useLocation();
  const crumb = TITLES[location.pathname] || { section: "ARC", page: "Dashboard" };


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
