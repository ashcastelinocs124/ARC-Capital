import { useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, MinusCircle, RefreshCw, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { useRefresh } from "@/hooks/useRefresh";
import type { RefreshJob } from "@/api/refresh";

function ago(iso: string) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}

function JobIcon({ s }: { s: RefreshJob["status"] }) {
  if (s === "running") return <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />;
  if (s === "done") return <Check className="h-3.5 w-3.5 text-success" />;
  if (s === "failed") return <AlertTriangle className="h-3.5 w-3.5 text-danger" />;
  if (s === "skipped") return <MinusCircle className="h-3.5 w-3.5 text-muted" />;
  return <span className="h-3.5 w-3.5 rounded-full border border-border-strong" />;
}

// Runs the Update Agent briefing, Sector Sentiment and AI Adoption refreshes on demand
// (POST /refresh); the backend no longer runs them at start-up.
export function RefreshButton() {
  const { status, running, start, starting } = useRefresh();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (running) setOpen(true);
  }, [running]);

  const jobs = status?.jobs ?? [];
  const finished = jobs.filter((j) => j.status !== "running" && j.status !== "idle").length;
  const failed = jobs.some((j) => j.status === "failed");
  const last = jobs.map((j) => j.finished_at).filter(Boolean).sort().pop();
  const busy = running || starting;

  return (
    <div className="relative">
      <button
        onClick={() => (busy ? setOpen((o) => !o) : start())}
        title={last ? `Last refreshed ${ago(last)}` : "Refresh dashboard data"}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium",
          busy ? "border-accent text-accent bg-accent-soft" : "border-border-strong text-text-2 bg-surface hover:border-accent hover:text-accent",
        )}
      >
        <RefreshCw className={cn("h-3.5 w-3.5", busy && "animate-spin")} />
        {busy ? `Refreshing ${finished}/${jobs.length || 3}` : "Refresh"}
        {!busy && failed && <AlertTriangle className="h-3.5 w-3.5 text-danger" aria-label="last refresh had a failure" />}
      </button>
      {open && jobs.length > 0 && (
        <div className="absolute right-0 top-9 z-40 w-80 rounded-lg border border-border bg-surface p-3 shadow-card-hover">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-text">{busy ? "Refreshing data…" : "Last refresh"}</span>
            <button onClick={() => setOpen(false)} aria-label="Close" className="text-muted hover:text-text">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <ul className="space-y-2">
            {jobs.map((j) => (
              <li key={j.key} className="flex gap-2 text-xs">
                <span className="mt-0.5"><JobIcon s={j.status} /></span>
                <div className="min-w-0">
                  <div className="font-medium text-text">{j.label}</div>
                  <div className={cn("text-muted", j.status === "failed" && "text-danger")}>
                    {j.status === "running" ? "running…" : j.message ?? j.status}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {!busy && last && <div className="mt-2 text-[11px] text-muted">Finished {ago(last)}. Pages reloaded with the new data.</div>}
        </div>
      )}
    </div>
  );
}
