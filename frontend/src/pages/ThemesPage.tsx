import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { isThemeRun, type ThemeRun } from "@/api/endpoints";
import { useThemeHistory, useThemeRun } from "@/hooks/useThemes";
import { ExhibitViewer } from "@/components/MorningNote";
import { PageIntro } from "@/components/layout/PageIntro";
import { cn } from "@/lib/cn";

// Same path in dev (vite proxies /api) and on the static site (export_snapshot copies the PNGs).
const chartUrl = (rec: ThemeRun, file: string) =>
  `/api/themes/${rec.run_id}/charts/${file}?v=${encodeURIComponent(rec.generated_at)}`;
const DAY = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
const stamp = (date: string, slot: "am" | "pm") =>
  `${DAY.format(new Date(`${date}T00:00:00Z`)).replace(",", "")} · ${slot === "am" ? "08:00" : "20:00"} ET`;
const SIGNAL = { coverage: "News & X", move: "Biggest move", odds: "Polymarket" } as const;
const ORD = ["", "", "2nd", "3rd"];
const streakLabel = (n: number) =>
  n <= 1 ? "New theme" : `Top theme for the ${ORD[n] ?? `${n}th`} run in a row`;

// The next 08:00 or 20:00 run, in New York time.
function nextRun(now = new Date()): string {
  const h = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" })).getHours();
  return h < 8 ? "Today, 08:00 ET" : h < 20 ? "Tonight, 20:00 ET" : "Tomorrow, 08:00 ET";
}

function Run({ rec, latest }: { rec: ThemeRun; latest: boolean }) {
  const [open, setOpen] = useState<ThemeRun["exhibits"][number] | null>(null);
  const cited = new Set(rec.fact_ids);
  const sources = [...new Map(rec.facts.filter((f) => cited.has(f.id)).map((f) => [f.source_title, f])).values()];
  return (
    <section className="card px-5 py-5 md:px-6">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className={cn("pill", rec.slot === "pm" && "bg-surface-3 text-text-2")}>{rec.slot === "am" ? "Day run" : "Night run"}</span>
        <span className="text-[12.5px] text-muted">{stamp(rec.date, rec.slot)}</span>
        <span className="rounded-full border border-dashed border-border-strong px-2.5 py-0.5 text-[11.5px] text-text-2">{streakLabel(rec.streak)}</span>
        {!latest && <Link to="/themes" className="ml-auto text-[13px] font-semibold text-accent hover:text-accent-hover">‹ Back to latest</Link>}
      </div>
      <h2 className="mt-2.5 mb-2 font-serif text-[21px] font-bold leading-tight text-text md:text-[23px]">{rec.theme}</h2>
      <p className="max-w-4xl text-[14px] leading-[22px] text-text-2">{rec.why}</p>
      {sources.length > 0 && (
        <div className="mt-1.5 text-[11.5px] text-muted">
          Sources:{" "}
          {sources.map((f, i) => (
            <span key={f.id}>
              {i > 0 && " · "}
              <a href={f.source_url} target="_blank" rel="noreferrer" className="hover:text-accent">{f.source_title}</a>
            </span>
          ))}
        </div>
      )}
      <div className="my-4 grid gap-2.5 md:grid-cols-3">
        {rec.signals.map((s) => (
          <div key={s.kind} className={cn("rounded-[10px] border px-3 py-2.5", s.kind === rec.lead ? "border-accent bg-accent-soft" : "border-border bg-surface-2")}>
            <div className={cn("text-[10.5px] font-bold uppercase tracking-[0.08em]", s.kind === rec.lead ? "text-accent" : "text-muted")}>
              {SIGNAL[s.kind]}{s.kind === rec.lead && " · led the pick"}
            </div>
            <div className="mt-0.5 text-sm font-semibold text-text">{s.headline}</div>
            <div className="mt-0.5 text-xs text-muted">{s.note}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-3.5 md:grid-cols-2">
        {rec.exhibits.map((ex) => (
          <button key={ex.file} type="button" onClick={() => setOpen(ex)} title="Open full size"
            className="block overflow-hidden rounded-[10px] border border-border cursor-zoom-in hover:shadow-card-hover">
            <img src={chartUrl(rec, ex.file)} alt={`${ex.title}. ${ex.subtitle}`} className="w-full" loading="lazy" />
          </button>
        ))}
      </div>
      {open && <ExhibitViewer src={chartUrl(rec, open.file)} ex={open} onClose={() => setOpen(null)} />}
    </section>
  );
}

export default function ThemesPage() {
  const [params] = useSearchParams();
  const run = params.get("run");
  const { data, isLoading } = useThemeRun(run);
  const { data: histRaw } = useThemeHistory();
  const rec = isThemeRun(data) ? data : undefined;
  const runs = histRaw && !Array.isArray(histRaw) && Array.isArray(histRaw.items) ? histRaw.items : [];
  const latest = !run || run === runs[0]?.run_id;
  return (
    <div className="space-y-5 p-4 md:p-8">
      <PageIntro kicker="Theme Charts" title="The day's #1 macro theme, in charts"
        steps={["News & X", "Market moves", "Polymarket", "Pick the theme", "Draw the charts"]} highlight={3}
        when={{ label: "Next run", value: nextRun(), note: "Runs at 08:00 and 20:00 ET" }}>
        Twice a day an agent reads what the news and financial X are talking about, which markets moved most and where
        Polymarket odds swung, picks the single biggest macro theme and draws the charts that show it. Every number on a
        chart is market data.
      </PageIntro>
      {isLoading && <div className="text-sm text-muted">Loading…</div>}
      {!isLoading && !rec && (
        <div className="card p-6 text-sm text-muted">
          {run ? <>No theme charts for {run}.</> : <><b className="text-text">No theme charts yet.</b> The first run publishes {nextRun().toLowerCase()}.</>}
        </div>
      )}
      {rec && <Run rec={rec} latest={latest} />}
      {runs.length > 1 && (
        <div>
          <h3 className="py-1 text-[15px] font-semibold text-text">Earlier runs <span className="text-xs font-normal text-muted">· newest first</span></h3>
          <div className="card mt-2 overflow-hidden">
            {runs.map((r) => {
              const cur = r.run_id === rec?.run_id;
              return (
                <Link key={r.run_id} to={`/themes?run=${r.run_id}`}
                  className={cn("grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 border-t border-border px-5 py-3 first:border-0 md:grid-cols-[170px_1fr_auto]",
                    cur ? "bg-accent-soft" : "hover:bg-surface-2")}>
                  <span className="eyebrow col-span-2 md:col-span-1">{stamp(r.date, r.slot)}</span>
                  <span className="text-sm text-text-2">{r.theme}</span>
                  <span className="text-[13px] font-semibold text-accent">{cur ? "Showing" : "View ›"}</span>
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
