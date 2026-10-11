import { ArrowUpRight } from "lucide-react";
import { NavLink } from "react-router-dom";
import { RefreshButton } from "@/components/layout/RefreshButton";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { STATIC } from "@/api/client";

export function TopBar() {
  return (
    <header className="h-14 shrink-0 bg-surface border-b border-border flex items-center justify-between px-4 md:px-8">
      <NavLink to="/" className="flex items-center gap-2.5">
        <img src="/arc-logo.png" alt="ARC" className="logo-img h-8 w-auto" />
        <span className="text-base font-bold tracking-tight text-text">ARC Research</span>
      </NavLink>
      <div className="flex items-center gap-3 md:gap-4 text-sm">
        {!STATIC && <RefreshButton />}
        <ThemeToggle />
        <a
          href="https://archresearch.substack.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-full bg-accent px-4 py-1.5 text-[13px] font-semibold text-on-accent hover:bg-accent-hover"
        >
          Newsletter <ArrowUpRight className="h-3.5 w-3.5" />
        </a>
      </div>
    </header>
  );
}
