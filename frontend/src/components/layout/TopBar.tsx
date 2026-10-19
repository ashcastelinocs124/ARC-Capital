import { ArrowUpRight, Lock } from "lucide-react";
import { NavLink } from "react-router-dom";
import { RefreshButton } from "@/components/layout/RefreshButton";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { TopNav } from "@/components/layout/TopNav";
import { STATIC } from "@/api/client";

export function TopBar() {
  return (
    <header className="h-16 shrink-0 bg-surface border-b border-border grid grid-cols-[1fr_auto] xl:grid-cols-[1fr_auto_1fr] items-center gap-4 px-4 md:h-[76px] md:px-8">
      <NavLink to="/" className="flex items-center" aria-label="ARC Research home">
        <img src="/arc-logo.png" alt="ARC Research" className="logo-img h-11 w-auto md:h-14" />
      </NavLink>
      <TopNav pill />
      <div className="flex items-center justify-end gap-3 md:gap-4 text-sm">
        {!STATIC && <RefreshButton />}
        {/* a full page load, not a router Link: only a real request to /admin reaches the password middleware */}
        <a href="/admin" className="inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] text-muted hover:text-accent" aria-label="Admin login">
          <Lock className="h-3.5 w-3.5" />
          <span className="hidden 2xl:inline">Admin login</span>
        </a>
        <ThemeToggle />
        <a
          href="https://archresearch.substack.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-full bg-text px-4 py-1.5 text-[13px] font-semibold text-surface hover:bg-text-2"
        >
          Newsletter <ArrowUpRight className="h-3.5 w-3.5" />
        </a>
      </div>
    </header>
  );
}
