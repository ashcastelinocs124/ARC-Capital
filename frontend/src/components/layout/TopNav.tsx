import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

// The logo is the way home, so Overview has no tab. Groups open as dropdowns: on desktop a pill
// group centred in the top bar (hover or click), on phones a sideways row whose group, when
// tapped, lists its pages underneath. A `to` with a #hash jumps to a card on that page
// (AppShell scrolls to it), and doesn't mark its group active. A `latest` group's tab opens its first
// (newest) page as well as the menu.
type Item = { to: string; label: string; desc: string };
type Group = { label: string; items: Item[]; latest?: boolean };
type Entry = { label: string; to: string } | Group;

const NAV: Entry[] = [
  { label: "Radar", to: "/macro" },
  { label: "Markets", items: [
    { to: "/updates", label: "Memo", desc: "The daily note, every weekday" },
    { to: "/deep-research", label: "Deep Research", desc: "The Sunday deep dive" },
  ] },
  { label: "AI", items: [
    { to: "/ai/models", label: "Models", desc: "Frontier and open-weight models, labs and releases" },
    { to: "/ai/chips", label: "Semis & Chips", desc: "GPUs, foundries and the compute supply chain" },
  ] },
  // newest first: the tab opens the top one (keep App.tsx's /dashboards redirect on it too)
  { label: "Dashboards", latest: true, items: [
    { to: "/dashboards/partisan-gap", label: "Partisan Policy Gap", desc: "Does the gap between the parties move markets? 1921–2024" },
    { to: "/dashboards/ai-capex", label: "AI Demand & Capex", desc: "Hyperscaler and neocloud spending, funding, demand and compute" },
  ] },
  { label: "Special Topics", to: "/special-topics" },
  { label: "Resources", items: [
    { to: "/resources", label: "Resources", desc: "Talks, slides and the Global Macro Cookbook" },
    { to: "/agents", label: "Agents", desc: "How ARC's own agents are built" },
    { to: "/docs", label: "Docs", desc: "What each model predicts and how to read it" },
  ] },
  { label: "About", to: "/about" },
];

const holds = (items: Item[], path: string) => items.some((i) => !i.to.includes("#") && i.to === path);

export function TopNav({ pill = false }: { pill?: boolean }) {
  const { pathname, hash } = useLocation();
  const [open, setOpen] = useState<string | null>(null);
  const nav = useRef<HTMLElement>(null);
  const navigate = useNavigate();
  const keep = useRef<string | null>(null); // a menu to leave open across the navigation its own tab started
  useEffect(() => {
    setOpen(keep.current); // close after navigating
    keep.current = null;
  }, [pathname, hash]);
  // a tab opens its menu; a `latest` group's tab also goes to its newest page, leaving the menu open
  // (on phones the list under the bar is the only way to the older pages)
  const tap = (g: Group) => {
    if (g.latest && g.items[0].to !== pathname) {
      keep.current = g.label;
      return navigate(g.items[0].to); // even when hover already opened the menu
    }
    setOpen(open === g.label ? null : g.label);
  };
  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (!nav.current?.contains(e.target as Node)) setOpen(null);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);
  const isCur = (to: string) => to === pathname + hash || (!to.includes("#") && to === pathname && !hash);

  if (pill) {
    return (
      // xl, not lg: seven tabs plus the right-hand buttons overlap below 1280px (measured 2026-10-18)
      <nav ref={nav} className="hidden items-center gap-1 rounded-full border border-border bg-surface-2 p-1 xl:flex" onMouseLeave={() => setOpen(null)}>
        {NAV.map((e) => {
          const tab = (active: boolean) =>
            cn("flex items-center whitespace-nowrap rounded-full px-3 py-2 text-[15px] font-medium transition-colors 2xl:px-4",
              active ? "bg-surface text-text shadow-card ring-1 ring-border" : "text-text-2 hover:text-text");
          if ("to" in e) return <NavLink key={e.label} to={e.to} className={({ isActive }) => tab(isActive)}>{e.label}</NavLink>;
          const isOpen = open === e.label;
          return (
            <div key={e.label} className="relative" onMouseEnter={() => setOpen(e.label)}>
              <button type="button" aria-expanded={isOpen} onClick={() => tap(e)} className={tab(holds(e.items, pathname))}>
                {e.label}
                <ChevronDown className={cn("ml-1 h-3.5 w-3.5 opacity-70 transition-transform", isOpen && "rotate-180")} />
              </button>
              {isOpen && (
                // pt-2 bridges the gap so the menu doesn't close while the pointer moves down to it
                <div className="absolute left-1/2 top-full z-30 -translate-x-1/2 pt-2">
                  <div className="w-72 rounded-2xl border border-border bg-surface p-2 shadow-card-hover">
                    {e.items.map((i) => (
                      <Link key={i.to} to={i.to} className="block rounded-xl px-3 py-2.5 hover:bg-surface-3">
                        <div className={cn("text-sm font-semibold", isCur(i.to) ? "text-accent" : "text-text")}>{i.label}</div>
                        <div className="mt-0.5 text-[12.5px] text-muted">{i.desc}</div>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </nav>
    );
  }

  const group = NAV.find((e) => e.label === open && "items" in e) as Group | undefined;
  return (
    <nav ref={nav} className="shrink-0 border-b border-border bg-surface xl:hidden">
      <div className="no-scrollbar flex gap-7 overflow-x-auto px-4">
        {NAV.map((e) => {
          const line = (active: boolean) =>
            cn("flex items-center whitespace-nowrap border-b-2 py-3 text-[15px] transition-colors",
              active ? "border-text font-semibold text-text" : "border-transparent font-medium text-text-2 hover:text-text");
          if ("to" in e) return <NavLink key={e.label} to={e.to} className={({ isActive }) => line(isActive)}>{e.label}</NavLink>;
          return (
            <button key={e.label} type="button" aria-expanded={open === e.label} onClick={() => tap(e)}
              className={line(open === e.label || (!open && holds(e.items, pathname)))}>
              {e.label}
              <ChevronDown className={cn("ml-1 h-3.5 w-3.5 opacity-70 transition-transform", open === e.label && "rotate-180")} />
            </button>
          );
        })}
      </div>
      {group && (
        <div className="border-t border-border px-2 py-1.5">
          {group.items.map((i) => (
            <Link key={i.to} to={i.to} className={cn("block rounded-xl px-3 py-2.5 text-[15px] font-semibold hover:bg-surface-3", isCur(i.to) ? "text-accent" : "text-text")}>
              {i.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  );
}
