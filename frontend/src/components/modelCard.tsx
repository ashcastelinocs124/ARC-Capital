import { useEffect, useRef, useState, type ReactNode } from "react";
import { Maximize2 } from "lucide-react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";

// Building blocks that mirror the forecaster cards on the Models page (pages/ModelsPage.tsx),
// so indicator cards (Sector Sentiment, AI Adoption) read the same way.

export function ago(iso: string) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 60) return `${mins}m ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}

export function StatusBadge({ status, text }: { status: "fresh" | "stale" | "missing"; text: string }) {
  const cls = {
    fresh: "bg-success-soft text-success",
    stale: "bg-warning-soft text-warning",
    missing: "bg-info-soft text-muted",
  }[status];
  return <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full whitespace-nowrap", cls)}>{text}</span>;
}

export function CardHead({
  name,
  kind,
  badge,
  expanded,
  onCollapse,
}: {
  name: string;
  kind: string;
  badge: ReactNode;
  expanded?: boolean;
  onCollapse?: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3" data-card-head>
      <div>
        <div className="text-base font-semibold text-text">{name}</div>
        <div className="text-xs text-muted">{kind}</div>
      </div>
      <div className="flex items-center gap-2">
        {badge}
        {onCollapse &&
          (expanded ? (
            <button
              onClick={onCollapse}
              className="text-xs font-semibold text-accent border border-accent rounded-md px-2 whitespace-nowrap"
            >
              Collapse ✕
            </button>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs text-muted border border-border rounded-md px-1.5 whitespace-nowrap group-hover:text-accent group-hover:border-accent">
              <Maximize2 className="h-3 w-3" aria-hidden /> Expand
            </span>
          ))}
      </div>
    </div>
  );
}

// Click a collapsed card to expand it across the grid; collapse via the header, the button or Esc.
// Clicks on controls inside the card (buttons, selects, links, rows marked data-stop) never toggle it.
export function ExpandableCard({
  expanded,
  onToggle,
  collapsed,
  full,
}: {
  expanded: boolean;
  onToggle: () => void;
  collapsed: ReactNode;
  full: { left: ReactNode; right: ReactNode };
}) {
  const ref = useRef<HTMLDivElement>(null);
  const toggleRef = useRef(onToggle);
  toggleRef.current = onToggle;
  // keyed on `expanded` only, so periodic data refetches don't re-scroll the page
  useEffect(() => {
    if (!expanded) return;
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const onKey = (ev: KeyboardEvent) => ev.key === "Escape" && toggleRef.current();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const onClick = (e: React.MouseEvent) => {
    const t = e.target as HTMLElement;
    if (t.closest("button, a, select, input, [data-stop]")) return;
    if (!expanded || t.closest("[data-card-head]")) onToggle();
  };

  return (
    <div
      ref={ref}
      onClick={onClick}
      className={cn(
        "card p-5 group scroll-mt-20",
        expanded ? "col-span-full ring-2 ring-accent-soft" : "cursor-pointer transition-shadow hover:shadow-card-hover",
      )}
    >
      {expanded ? (
        <div className="grid lg:grid-cols-3 gap-7">
          <div className="min-w-0">{full.left}</div>
          <div className="lg:col-span-2 min-w-0 space-y-3.5">{full.right}</div>
        </div>
      ) : (
        collapsed
      )}
    </div>
  );
}

export function HowItWorks({
  short,
  steps,
  expanded,
  docsId,
}: {
  short: string;
  steps: ReactNode[];
  expanded: boolean;
  docsId?: string; // anchor on /docs
}) {
  return (
    <div className="mt-3.5 rounded-r-lg border-l-[3px] border-accent bg-accent-soft px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-accent">How it works</div>
        {docsId && (
          <Link to={`/docs#${docsId}`} onClick={(e) => e.stopPropagation()}
            className="text-[11px] font-medium text-accent hover:underline whitespace-nowrap">
            Full documentation →
          </Link>
        )}
      </div>
      {expanded ? (
        <ol className="mt-1 list-decimal pl-4 space-y-1 text-[13px] leading-snug text-text-2">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      ) : (
        <p className="mt-0.5 text-[13px] leading-snug text-text-2 line-clamp-3">{short}</p>
      )}
    </div>
  );
}

// Bordered panel used in the expanded view.
export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-border px-3.5 py-3">
      <div className="text-xs font-semibold text-text mb-1.5">{title}</div>
      {children}
    </div>
  );
}

export function Headline({
  value,
  label,
  tone,
  fill,
}: {
  value: string;
  label: string;
  tone: "success" | "danger";
  fill: number; // 0-100, width of the bar under the number
}) {
  return (
    <>
      <div className="mt-4 flex items-baseline gap-2.5">
        <span className={cn("font-mono text-2xl font-bold", tone === "success" ? "text-success" : "text-danger")}>{value}</span>
        <span className="text-sm text-muted">{label}</span>
      </div>
      <div className="h-1.5 bg-surface-3 rounded mt-1.5 mb-4 overflow-hidden">
        <div
          className={cn("h-full", tone === "success" ? "bg-success" : "bg-danger")}
          style={{ width: `${Math.max(0, Math.min(100, fill))}%` }}
        />
      </div>
    </>
  );
}

export function StatGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 border-t border-border pt-3.5">{children}</div>;
}

export function StatCell({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="text-xs text-muted">
      {label}
      <div className={cn("font-mono font-semibold text-sm num", warn ? "text-warning" : "text-text")}>{value}</div>
    </div>
  );
}

export function Measures({ question, output }: { question: string; output: string }) {
  return (
    <div className="mt-3.5 rounded-lg bg-surface-2 border border-border px-3 py-2.5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Measures</div>
      <div className="text-sm text-text mt-0.5">{question}</div>
      <div className="text-xs text-muted mt-0.5">Output: {output}</div>
    </div>
  );
}

// "Show X ▾" footer toggles; one pane open at a time, same styling as Parameters / Sources.
export function Toggles({ tabs }: { tabs: { key: string; label: string; render: () => ReactNode }[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const current = tabs.find((t) => t.key === open);
  return (
    <>
      <div className="mt-3.5 border-t border-border pt-3 flex flex-wrap gap-x-4 gap-y-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setOpen(open === t.key ? null : t.key)}
            className={cn("text-xs font-medium", open === t.key ? "text-accent" : "text-muted hover:text-accent")}
          >
            {open === t.key ? "Hide" : "Show"} {t.label} {open === t.key ? "▴" : "▾"}
          </button>
        ))}
      </div>
      {current && <div className="mt-2.5">{current.render()}</div>}
    </>
  );
}
