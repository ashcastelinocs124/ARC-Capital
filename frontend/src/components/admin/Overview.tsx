import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { call } from "@/components/admin/DailyDesk";
import { BUDGET } from "@/components/admin/Costs";
import { Status, btn, type Tone } from "@/components/admin/shell";

// /admin → Overview, and the sidebar's live counts: one read of GET /admin/desk/overview
// (src/castelino/dashboard/endpoints/admin_overview.py), shared through the query cache and refreshed every 30 s.
export type Item = {
  section: string; title: string; detail: string; at: string | null; cost_usd: number | null;
  action: string | null; href: string; url: string | null; tone: Tone;
};
export type OverviewData = {
  day: string;
  needs_you: Item[]; // oldest first
  running: Item[];
  went_out: Item[]; // newest first
  spend: { today_usd: number; calls: number; tokens: number; month_usd: number } | null;
  counts: Record<string, { waiting: number; running: number }>;
  errors: string[];
};

export const useOverview = () =>
  useQuery({
    queryKey: ["admin_overview"],
    queryFn: () => call<OverviewData>("/overview"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

const usd = (v: number) => `$${v.toFixed(2)}`;
const tokens = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${n}`);
const hhmm = (at: string | null) => (at && at.length >= 16 ? at.slice(11, 16) : "");
const MONTH = new Intl.DateTimeFormat("en-US", { month: "long", timeZone: "UTC" });
const TOTAL_BUDGET = Object.values(BUDGET).reduce((a, b) => a + b, 0);

function Stat({ label, value, note, bar }: { label: string; value: React.ReactNode; note?: React.ReactNode; bar?: number }) {
  return (
    <div className="rounded-xl border border-border-soft bg-surface px-4 py-3.5">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 text-[22px] font-semibold leading-[30px] tabular-nums">{value}</div>
      {note && <div className="text-xs text-muted">{note}</div>}
      {bar !== undefined && (
        <div className="mt-2 h-1 overflow-hidden rounded bg-surface-3" role="presentation">
          <i className={cn("block h-full", bar > 1 ? "bg-danger" : "bg-accent")} style={{ width: `${Math.min(bar, 1) * 100}%` }} />
        </div>
      )}
    </div>
  );
}

function Row({ it, right }: { it: Item; right?: React.ReactNode }) {
  const title = it.url && !it.action
    ? <a href={it.url} target="_blank" rel="noreferrer" className="hover:underline">{it.title}</a>
    : <Link to={it.href} className="hover:underline">{it.title}</Link>;
  return (
    <li className="flex items-center gap-3 border-b border-border-soft px-4 py-3 last:border-b-0">
      <Status tone={it.tone} className="flex-none" /> {/* the detail line says the state in words */}
      <div className="min-w-0 flex-1">
        <b className="block truncate text-[13px] font-medium text-text">{title}</b>
        <span className="block truncate text-xs text-muted">{it.detail}</span>
      </div>
      {right}
    </li>
  );
}

function Panel({ title, count, tone, empty, children, className }: {
  title: string; count?: number; tone?: "wait" | "run"; empty: string; children: React.ReactNode[]; className?: string;
}) {
  return (
    <section className={cn("rounded-xl border border-border-soft bg-surface", className)} aria-label={title}>
      <h2 className="flex items-center gap-2 border-b border-border-soft px-4 py-3 text-sm font-medium">
        {title}
        {!!count && (
          <span className={cn("rounded-full px-1.5 font-mono text-[11px] leading-[18px]",
            tone === "wait" ? "bg-warning-soft text-warning" : "bg-accent-soft text-accent")}>{count}</span>
        )}
      </h2>
      {children.length ? <ul>{children}</ul> : <p className="px-4 py-6 text-center text-[13px] text-muted">{empty}</p>}
    </section>
  );
}

export default function Overview() {
  const { data, error, isLoading } = useOverview();
  if (isLoading) return <p className="p-5 text-sm text-muted md:p-8">Loading…</p>;
  if (error || !data) {
    return (
      <div className="p-5 md:p-8">
        <div className="rounded-lg border border-danger/40 bg-danger-soft px-4 py-3 text-sm">
          Couldn&apos;t load the overview: {error instanceof Error ? error.message : "no data"}. Check that the backend is up, then reload.
        </div>
      </div>
    );
  }
  const s = data.spend;
  const month = MONTH.format(new Date(`${data.day}T12:00:00Z`));
  return (
    <div className="space-y-4 p-5 md:p-8">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat label="Spend today" value={s ? usd(s.today_usd) : "—"}
          note={s && <span className="font-mono">{s.calls} calls · {tokens(s.tokens)} tokens</span>} />
        <Stat label={`${month} so far`} value={s ? <>{usd(s.month_usd)} <span className="text-sm font-normal text-muted">of ${TOTAL_BUDGET}</span></> : "—"}
          bar={s ? s.month_usd / TOTAL_BUDGET : undefined} />
        <Stat label="Waiting for you" value={data.needs_you.length} note={data.needs_you.length ? "oldest first below" : "nothing to do"} />
        <Stat label="Went out today" value={data.went_out.length} note="X and Substack" />
      </div>
      {data.errors.length > 0 && (
        <p className="rounded-lg border border-warning/40 bg-warning-soft px-4 py-2 text-[13px]" role="status">
          Some sections couldn&apos;t be read, so they are missing below: {data.errors.join("; ")}
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Needs you" count={data.needs_you.length} tone="wait" empty="Nothing is waiting for you.">
          {data.needs_you.map((it, i) => (
            <Row key={i} it={it} right={it.action && (it.url
              ? <a href={it.url} target="_blank" rel="noreferrer" className={btn.secondary}>{it.action}<ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" /></a>
              : <Link to={it.href} className={btn.secondary}>{it.action}</Link>)} />
          ))}
        </Panel>
        <Panel title="Running now" count={data.running.length} tone="run" empty="Nothing is running.">
          {data.running.map((it, i) => (
            <Row key={i} it={it} right={
              <span className="flex-none text-right font-mono text-xs text-muted">
                {hhmm(it.at) && <>since {hhmm(it.at)}</>}{it.cost_usd != null && <> · {usd(it.cost_usd)}</>}
              </span>} />
          ))}
        </Panel>
      </div>
      <Panel title="Went out today" empty="Nothing has gone out yet today.">
        {data.went_out.map((it, i) => (
          <Row key={i} it={it} right={<span className="flex-none font-mono text-xs text-muted">{hhmm(it.at)}</span>} />
        ))}
      </Panel>
    </div>
  );
}
