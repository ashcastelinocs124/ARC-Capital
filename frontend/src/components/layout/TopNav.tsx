import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

// The logo is the way home, so Overview has no tab. Groups open as dropdowns: on desktop a pill
// group centred in the top bar (hover or click), on phones a sideways row whose group, when
// tapped, lists its pages underneath. A `to` with a #hash jumps to a card on that page
// (AppShell scrolls to it), and doesn't mark its group active.
type Item = { to: string; label: string; desc: string };
type Entry = { label: string; to: string } | { label: string; items: Item[] };

const NAV: Entry[] = [
  { label: "Models", to: "/models" },
  { label: "Markets", items: [
    { to: "/macro", label: "Radar", desc: "The week ahead: releases, earnings, AI launches" },
    { to: "/updates", label: "Memo", desc: "The daily note, every weekday" },
    { to: "/deep-research", label: "Deep Research", desc: "The Sunday deep dive" },
  ] },
  { label: "AI", items: [
    { to: "/ai", label: "AI Update", desc: "Models, chips and the AI stack" },
  ] },
  { label: "Special Topics", items: [
    { to: "/special-topics", label: "Special Topics", desc: "Deeper dives and presentations" },
    { to: "/videos", label: "Videos", desc: "AI updates and special topics, on camera" },
  ] },
  { label: "How it works", items: [
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
  useEffect(() => {
    setOpen(null); // close after navigating
  }, [pathname, hash]);
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
      <nav ref={nav} className="hidden items-center gap-1 rounded-full border border-border bg-surface-2 p-1 lg:flex" onMouseLeave={() => setOpen(null)}>
        {NAV.map((e) => {
          const tab = (active: boolean) =>
            cn("flex items-center whitespace-nowrap rounded-full px-4 py-2 text-[15px] font-medium transition-colors",
              active ? "bg-surface text-text shadow-card ring-1 ring-border" : "text-text-2 hover:text-text");
          if ("to" in e) return <NavLink key={e.label} to={e.to} className={({ isActive }) => tab(isActive)}>{e.label}</NavLink>;
          const isOpen = open === e.label;
          return (
            <div key={e.label} className="relative" onMouseEnter={() => setOpen(e.label)}>
              <button type="button" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : e.label)} className={tab(holds(e.items, pathname))}>
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

  const group = NAV.find((e) => e.label === open && "items" in e) as { items: Item[] } | undefined;
  return (
    <nav ref={nav} className="shrink-0 border-b border-border bg-surface lg:hidden">
      <div className="no-scrollbar flex gap-7 overflow-x-auto px-4">
        {NAV.map((e) => {
          const line = (active: boolean) =>
            cn("flex items-center whitespace-nowrap border-b-2 py-3 text-[15px] transition-colors",
              active ? "border-text font-semibold text-text" : "border-transparent font-medium text-text-2 hover:text-text");
          if ("to" in e) return <NavLink key={e.label} to={e.to} className={({ isActive }) => line(isActive)}>{e.label}</NavLink>;
          return (
            <button key={e.label} type="button" aria-expanded={open === e.label} onClick={() => setOpen(open === e.label ? null : e.label)}
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
