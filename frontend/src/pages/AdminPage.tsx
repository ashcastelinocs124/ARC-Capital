import { useEffect, useRef, useState, type ComponentType } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import {
  Activity, ArrowUpRight, AtSign, BookOpen, Bot, CircleDollarSign, FileText, FlaskConical, House, LineChart, Lock,
  Menu, PanelLeftClose, PanelLeftOpen, Scale, Search, Users, type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { STATIC } from "@/api/client";
import AgentsPage from "@/pages/AgentsPage";
import DailyDesk from "@/components/admin/DailyDesk";
import XPosts from "@/components/admin/XPosts";
import TradeLab from "@/components/admin/trade/TradeLab";
import Research from "@/components/admin/research/Research";
import Consultants from "@/components/admin/consultants/Consultants";
import Costs from "@/components/admin/Costs";
import ChartDesk from "@/components/admin/ChartDesk";
import Overview, { useOverview } from "@/components/admin/Overview";
import CommandPalette from "@/components/admin/CommandPalette";
import { ActionsSlot } from "@/components/admin/shell";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Article, DOCS_LIST, type DocDetail } from "@/pages/DocsPage";

// PRIVATE area, with its own shell (no public top bar or footer). The data (/api/admin/*) and the detailed docs
// module (/admin/chunks/*) are password-gated by frontend/middleware.ts on the public site; locally the backend
// serves them without a login. This page's own code holds no private data, so it can ship in the public bundle.
// Design: docs/design/2026-10-24-admin-console-brief.md (local only).

export type Group = "" | "Publish" | "Studio" | "System";
export type Section = { id: string; label: string; group: Group; icon: LucideIcon; blurb: string; el: () => React.ReactNode };

export const SECTIONS: Section[] = [
  { id: "overview", label: "Overview", group: "", icon: House, blurb: "What needs you, what's running and what went out today.", el: () => <Overview /> },
  { id: "daily-desk", label: "Daily desk", group: "Publish", icon: FileText, blurb: "Read each analyst's findings, edit the note with the Editor or by hand, and send its Substack draft.", el: () => <DailyDesk /> },
  { id: "x-posts", label: "X posts", group: "Publish", icon: AtSign, blurb: "Draft and post the X thread for each published note and deep dive.", el: () => <XPosts /> },
  { id: "research", label: "Research", group: "Studio", icon: FlaskConical, blurb: "Deep research on any topic, with an editor desk to question and rewrite each point.", el: () => <Research /> },
  { id: "trade-lab", label: "Trade Lab", group: "Studio", icon: Scale, blurb: "Take one trade idea through a debate, your view and research to a Substack draft.", el: () => <TradeLab /> },
  { id: "consultants", label: "Consultants", group: "Studio", icon: Users, blurb: "Topic agents that build a cited file every day, keep a view and advise the Daily Update.", el: () => <Consultants /> },
  { id: "charts", label: "Charts", group: "Studio", icon: LineChart, blurb: "Ask the chart agent for any chart, or run one prompt on several models and vote.", el: () => <ChartDesk /> },
  { id: "agents", label: "Agents", group: "System", icon: Bot, blurb: "Every agent's prompt, model, tools, memory and API keys, with the system diagrams.", el: () => <AgentsPage /> },
  { id: "models", label: "Models", group: "System", icon: Activity, blurb: "The nowcasters and indices: what each predicts, its inputs and how it has done.", el: () => <AdminModels /> },
  { id: "costs", label: "Costs", group: "System", icon: CircleDollarSign, blurb: "Model, X and server spend from the call logs, against this month's budget. An estimate, not your invoice.", el: () => <Costs /> },
  { id: "docs", label: "Docs", group: "", icon: BookOpen, blurb: "Every model in full: target, inputs, method, testing and limits.", el: () => <AdminDocs /> },
];
const GROUPS: Group[] = ["Publish", "Studio", "System"];
export const href = (id: string) => (id === "overview" ? "/admin" : `/admin/${id}`);

const LoadFailed = ({ what }: { what: string }) => (
  <div className="rounded-lg border border-danger/40 bg-danger-soft px-5 py-3 text-sm">
    Couldn't load the private {what}. If you are on the public site, reload and sign in with the admin password.
  </div>
);

// The models are admin-only (since 2026-10-15): the page is a private chunk (/admin/chunks/*) and its
// data comes from /api/admin/*, so neither ships to visitors.
function AdminModels() {
  const [Page, setPage] = useState<ComponentType | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    import("@/admin/private/ModelsPage").then((m) => setPage(() => m.default), () => setFailed(true));
  }, []);
  if (failed) return <div className="p-5 md:p-8"><LoadFailed what="models" /></div>;
  return Page ? <Page /> : <p className="p-5 text-sm text-muted md:p-8">Loading…</p>;
}

function AdminDocs() {
  const [detail, setDetail] = useState<Record<string, DocDetail> | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    import("@/admin/private/docsDetail").then((m) => setDetail(m.DETAIL), () => setFailed(true));
  }, []);
  return (
    <div className="space-y-5 p-5 md:p-8">
      {failed && <LoadFailed what="write-ups" />}
      {DOCS_LIST.map((d) => <Article key={d.id} d={d} detail={detail?.[d.id]} />)}
    </div>
  );
}

// The private chip: on the public site, the session's end time (from the middleware) and Sign out.
function PrivateChip({ compact }: { compact: boolean }) {
  const [until, setUntil] = useState<string | null>(null);
  useEffect(() => {
    if (!STATIC) return;
    fetch("/api/admin/session")
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j?.expires && setUntil(new Date(j.expires * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })))
      .catch(() => {});
  }, []);
  const text = STATIC ? (until ? `Private · signed in until ${until}` : "Private · signed in") : "Private · local, no sign-in";
  const signOut = () => fetch("/api/admin/logout", { method: "POST" }).finally(() => { location.href = "/admin/login"; });
  return (
    <div className={cn("flex items-center gap-2 px-2 text-xs text-muted", compact && "justify-center px-0")} title={compact ? text : undefined}>
      <Lock className="h-3.5 w-3.5 flex-none" aria-hidden="true" />
      {compact ? <span className="sr-only">{text}</span> : <span className="min-w-0 flex-1 truncate">{text}</span>}
      {STATIC && !compact && <button onClick={signOut} className="rounded px-1 font-medium text-text-2 underline-offset-2 hover:underline">Sign out</button>}
    </div>
  );
}

function Count({ waiting, running, compact }: { waiting: number; running: number; compact: boolean }) {
  if (!waiting && !running) return null;
  const label = [running && `${running} running`, waiting && `${waiting} waiting for you`].filter(Boolean).join(", ");
  if (compact) {
    return <span className={cn("absolute right-1.5 top-1.5 h-[7px] w-[7px] rounded-full border-2 border-rail", waiting ? "bg-warning" : "bg-accent")} aria-label={label} />;
  }
  return (
    <span className="ml-auto flex gap-1" aria-label={label}>
      {waiting > 0 && <span className="rounded-full bg-warning-soft px-1.5 font-mono text-[11px] leading-[18px] text-warning">{waiting}</span>}
      {running > 0 && <span className="rounded-full bg-accent-soft px-1.5 font-mono text-[11px] leading-[18px] text-accent">{running}</span>}
    </span>
  );
}

function Sidebar({ current, compact, onToggle, onNavigate, id }: {
  current: Section; compact: boolean; onToggle?: () => void; onNavigate?: () => void; id: string;
}) {
  const { data } = useOverview();
  const counts = data?.counts ?? {};
  const item = (s: Section) => (
    <li key={s.id}>
      <Link to={href(s.id)} onClick={onNavigate} aria-current={s.id === current.id ? "page" : undefined}
        title={compact ? s.label : undefined}
        className={cn("relative flex h-8 items-center gap-2.5 rounded-lg px-2 text-sm",
          compact && "justify-center px-0",
          s.id === current.id ? "bg-surface-3 font-medium text-text" : "text-muted hover:bg-surface hover:text-text-2")}>
        <s.icon className="h-4 w-4 flex-none" aria-hidden="true" />
        {compact ? <span className="sr-only">{s.label}</span> : <span className="truncate">{s.label}</span>}
        <Count waiting={counts[s.id]?.waiting ?? 0} running={counts[s.id]?.running ?? 0} compact={compact} />
      </Link>
    </li>
  );
  const running = data?.running.length ?? 0;
  const waiting = data?.needs_you.length ?? 0;
  return (
    <nav id={id} aria-label="Admin sections" className={cn("flex h-full flex-col bg-rail px-2.5 py-3", compact ? "w-[52px] px-2" : "w-56")}>
      <div className={cn("mb-2 flex items-center gap-2.5 px-1.5 pb-2", compact && "flex-col px-0")}>
        <img src="/arc-logo.png" alt="" className="h-7 w-7 flex-none rounded-md bg-white object-contain p-0.5" />
        {!compact && <span className="text-sm font-semibold">ARC <span className="font-normal text-muted">Admin</span></span>}
        {onToggle && (
          <button onClick={onToggle} aria-expanded={!compact} aria-controls={id}
            aria-label={compact ? "Expand sidebar" : "Collapse sidebar"} title={compact ? "Expand sidebar" : "Collapse sidebar"}
            className={cn("grid h-6 w-6 place-items-center rounded-md text-muted hover:bg-surface hover:text-text", !compact && "ml-auto")}>
            {compact ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        )}
      </div>
      <ul className="space-y-0.5">{item(SECTIONS[0])}</ul>
      {GROUPS.map((g) => (
        <div key={g}>
          {compact ? <hr className="mx-2 my-2.5 border-border-soft" /> : <div className="px-2 pb-1 pt-4 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{g}</div>}
          <ul className="space-y-0.5">{SECTIONS.filter((s) => s.group === g).map(item)}</ul>
        </div>
      ))}
      <div className="mt-auto space-y-1.5 border-t border-border-soft pt-2.5">
        <ul>{item(SECTIONS.find((s) => s.id === "docs")!)}</ul>
        <Link to="/admin" onClick={onNavigate} title={compact ? `${running} running · ${waiting} waiting for you` : undefined}
          className={cn("flex items-center gap-2 rounded-lg px-2 py-1 text-xs text-text-2 hover:bg-surface", compact && "justify-center px-0")}>
          <i className={cn("block h-[7px] w-[7px] flex-none rounded-full", running ? "bg-accent motion-safe:animate-[pulse-ring_1.6s_ease-in-out_infinite]" : "border-[1.5px] border-muted")} aria-hidden="true" />
          {compact ? <span className="sr-only">{running} running, {waiting} waiting for you</span> : <span>{running} running · {waiting} waiting for you</span>}
        </Link>
        <PrivateChip compact={compact} />
        <div className={cn("flex items-center gap-2 px-1 pt-1", compact && "flex-col px-0")}>
          <ThemeToggle />
          <Link to="/" className={cn("inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-muted hover:text-text", compact && "px-0")}
            title="View site" aria-label={compact ? "View site" : undefined}>
            {!compact && "View site"}<ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </nav>
  );
}

const SIDEBAR_KEY = "arc.admin.sidebar"; // "collapsed" | "expanded"

export default function AdminPage() {
  const { pathname, search } = useLocation();
  const [compact, setCompact] = useState(() => {
    try { return localStorage.getItem(SIDEBAR_KEY) === "collapsed"; } catch { return false; }
  });
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const main = useRef<HTMLElement>(null);
  const id = pathname.replace(/^\/admin\/?/, "").split("/")[0] || "overview";
  const section = SECTIONS.find((s) => s.id === id);

  useEffect(() => {
    main.current?.scrollTo(0, 0); // braces: scrollTo can return a Promise, and an effect may only return a cleanup
    setDrawer(false);
    if (section) document.title = `${section.label} · ARC Admin`;
  }, [section]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); }
      if (e.key === "Escape") setDrawer(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const toggle = () => setCompact((c) => {
    try { localStorage.setItem(SIDEBAR_KEY, c ? "expanded" : "collapsed"); } catch { /* not remembered */ }
    return !c;
  });

  if (!section) return <Navigate to="/admin" replace />;
  return (
    <div className="flex h-dvh bg-background text-text">
      <div className="hidden flex-none border-r border-border-soft lg:block">
        <Sidebar id="admin-nav" current={section} compact={compact} onToggle={toggle} />
      </div>
      {drawer && (
        <div className="fixed inset-0 z-40 flex lg:hidden" role="dialog" aria-modal="true" aria-label="Admin sections">
          <div className="border-r border-border-soft shadow-xl"><Sidebar id="admin-drawer" current={section} compact={false} onNavigate={() => setDrawer(false)} /></div>
          <button className="flex-1 bg-black/40" onClick={() => setDrawer(false)} aria-label="Close menu" />
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 flex-none items-center gap-3 border-b border-border-soft px-4 md:px-6">
          <button onClick={() => setDrawer(true)} className="grid h-8 w-8 place-items-center rounded-lg text-text-2 hover:bg-surface-3 lg:hidden"
            aria-label="Open menu" aria-expanded={drawer}>
            <Menu className="h-4 w-4" />
          </button>
          <span className="truncate text-[13px] text-muted">
            {section.group && <>{section.group} / </>}<b className="font-medium text-text-2">{section.label}</b>
          </span>
          <button onClick={() => setPalette(true)}
            className="ml-auto inline-flex h-8 items-center gap-2 rounded-lg border border-border bg-surface px-2.5 text-[13px] text-muted hover:border-border-strong hover:text-text-2">
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Search sections and agents</span><span className="sm:hidden">Search</span>
            <kbd className="rounded border border-border px-1 font-mono text-[11px] text-text-2">⌘K</kbd>
          </button>
        </div>
        <main ref={main} className="min-h-0 flex-1 overflow-auto">
          <header className="border-b border-border-soft px-5 pb-4 pt-5 md:px-8">
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
              <div className="min-w-0 flex-1 basis-80">
                <h1 className="text-[22px] font-semibold leading-7 tracking-[-0.01em]">{section.label}</h1>
                <p className="mt-1 max-w-3xl text-[13px] leading-5 text-muted">{section.blurb}</p>
              </div>
              <div ref={setSlot} className="flex flex-wrap items-center gap-2 empty:hidden" />
            </div>
          </header>
          <ActionsSlot.Provider value={slot}>
            {/* agents re-mounts on ?agent= so ⌘K can open one; every other section keeps its state */}
            <div key={section.id === "agents" ? `agents${search}` : section.id}>{section.el()}</div>
          </ActionsSlot.Provider>
        </main>
      </div>
      {palette && <CommandPalette sections={SECTIONS} href={href} onClose={() => setPalette(false)} />}
    </div>
  );
}
