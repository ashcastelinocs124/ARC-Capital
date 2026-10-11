import { Activity, ArrowUpRight } from "lucide-react";
import { NavLink } from "react-router-dom";
import { RefreshButton } from "@/components/layout/RefreshButton";
import { STATIC } from "@/api/client";

export function TopBar() {
  return (
    <header className="h-14 shrink-0 bg-surface border-b border-border flex items-center justify-between px-4 md:px-8">
      <NavLink to="/" className="flex items-center gap-2.5">
        <img src="/arc-logo.png" alt="ARC" className="h-8 w-auto" />
        <span className="text-base font-bold tracking-tight text-text">ARC Research</span>
      </NavLink>
      <div className="flex items-center gap-3 md:gap-4 text-sm">
        <div className="hidden sm:flex items-center gap-1.5 text-muted">
          <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse-slow" />
          <Activity className="h-3.5 w-3.5" />
          <span className="text-xs">Live</span>
        </div>
        {!STATIC && <RefreshButton />}
        <a
          href="https://archresearch.substack.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-full bg-accent px-4 py-1.5 text-[13px] font-semibold text-white hover:bg-accent-hover"
        >
          Newsletter <ArrowUpRight className="h-3.5 w-3.5" />
        </a>
      </div>
    </header>
  );
}
