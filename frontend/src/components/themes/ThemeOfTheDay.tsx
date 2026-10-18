import { useState } from "react";
import type { ThemeRun, ThemeSignalKind } from "@/api/endpoints";
import { useThemeHistory, useThemePosts, useThemeRun } from "@/hooks/useThemes";
import { ThemeChartCard } from "@/components/themes/ThemeChart";
import { cn } from "@/lib/cn";

// Radar's "Today's theme" card (approved mockup radar-theme-mock.html, Option A, 2026-10-17): the latest
// Theme Charts run, one interactive exhibit at a time, with why the theme was picked beside it, and day
// chips to step back through the week's runs.

// Same path in dev (vite proxies /api) and on the static site (export_snapshot copies the PNGs).
const chartUrl = (rec: ThemeRun, file: string) =>
  `/api/themes/${rec.run_id}/charts/${file}?v=${encodeURIComponent(rec.generated_at)}`;
const DAY = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
const WEEKDAY = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: "UTC" });
const dayChip = (date: string) => `${WEEKDAY.format(new Date(`${date}T00:00:00Z`))} ${Number(date.slice(8))}`; // "Wed 14"
const stamp = (date: string, slot: "am" | "pm") =>
  `${DAY.format(new Date(`${date}T00:00:00Z`)).replace(",", "")} · ${slot === "am" ? "08:00" : "20:00"} ET`;
const SIGNAL: Record<ThemeSignalKind, string> = { coverage: "News & X", move: "Biggest move", odds: "Polymarket" };
const PREFIX: Record<ThemeSignalKind, string> = { coverage: "N", move: "M", odds: "P" }; // fact ids: N1, M7, P1
const SOURCE: Record<string, string> = { N: "News", M: "Market", P: "Polymarket" };
const ORD = ["", "", "2nd", "3rd"];
const streakLabel = (n: number) => (n <= 1 ? "New theme" : `Top theme for the ${ORD[n] ?? `${n}th`} run in a row`);
const SHOWN = 2; // facts listed before "Show all"

function Why({ rec }: { rec: ThemeRun }) {
  const [open, setOpen] = useState(false);
  const [lit, setLit] = useState<ThemeSignalKind | null>(null);
  const cited = rec.facts.filter((f) => rec.fact_ids.includes(f.id));
  const shown = open ? cited : cited.slice(0, SHOWN);
  return (
    <aside className="flex min-w-0 flex-col gap-3 border-t border-border pt-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
      <div className="text-[11px] font-bold uppercase tracking-[0.1em] text-muted">Why this theme</div>
      <p className="text-[13.5px] leading-[21px] text-text-2">{rec.why}</p>
      <div className="flex flex-col gap-2">
        {rec.signals.map((s) => (
          <button key={s.kind} type="button" onClick={() => { setLit(lit === s.kind ? null : s.kind); setOpen(true); }}
            className={cn("rounded-[10px] border px-3 py-2.5 text-left hover:shadow-card-hover",
              s.kind === rec.lead ? "border-accent bg-accent-soft" : "border-border bg-surface-2")}>
            <div className={cn("text-[10.5px] font-bold uppercase tracking-[0.08em]", s.kind === rec.lead ? "text-accent" : "text-muted")}>
              {SIGNAL[s.kind]}{s.kind === rec.lead && " · led the pick"}
            </div>
            <div className="mt-0.5 text-sm font-semibold text-text">{s.headline}</div>
            <div className="mt-0.5 text-xs text-muted">{s.note}</div>
          </button>
        ))}
      </div>
      {cited.length > 0 && (
        <>
          <div className="mt-1 text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
            Sources <span className="font-medium normal-case tracking-normal">· {cited.length} facts</span>
          </div>
          <ul className="flex flex-col gap-1.5">
            {shown.map((f) => (
              <li key={f.id} className={cn("rounded-lg border px-2 py-1.5 text-xs leading-[17px] text-text-2 transition-colors",
                lit && f.id.startsWith(PREFIX[lit]) ? "border-accent-soft-2 bg-accent-soft" : "border-transparent")}>
                <span className="mr-1 text-[9.5px] font-bold uppercase tracking-[0.06em] text-muted-2">{SOURCE[f.id[0]]}</span>
                {f.text.replace(/\*\*/g, "")}
                <a href={f.source_url} target="_blank" rel="noreferrer" className="mt-0.5 block text-[11px] text-muted hover:text-accent">{f.source_title} ↗</a>
              </li>
            ))}
          </ul>
          {cited.length > SHOWN && (
            <button type="button" onClick={() => setOpen(!open)} className="self-start text-[12.5px] font-semibold text-accent hover:text-accent-hover">
              {open ? "Show fewer ▴" : `Show all ${cited.length} ▾`}
            </button>
          )}
        </>
      )}
      <p className="text-[11px] leading-4 text-muted">Every number in the charts is market data.</p>
    </aside>
  );
}

export function ThemeOfTheDay() {
  const [run, setRun] = useState<string | null>(null); // null = the latest
  const [cur, setCur] = useState(0);
  const { data: rec } = useThemeRun(run);
  const { data: history = [] } = useThemeHistory();
  const { data: posts = [] } = useThemePosts();
  if (!rec || !rec.exhibits.length) return null;
  const ex = rec.exhibits[Math.min(cur, rec.exhibits.length - 1)];
  const post = posts.find((p) => p.run_id === rec.run_id);
  const days = [...history].reverse(); // oldest → newest; the server keeps one week (themes.prune)
  const latest = !run || run === history[0]?.run_id;
  return (
    <section id="theme" className="min-w-0 scroll-mt-4 rounded-xl border border-border bg-surface px-4 py-4 shadow-card md:px-6 md:py-5">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="pill">{latest ? "Today's theme" : "Earlier this week"}</span>
        <span className="text-[12.5px] text-muted">{stamp(rec.date, rec.slot)}</span>
        <span className="rounded-full border border-dashed border-border-strong px-2.5 py-0.5 text-[11.5px] text-text-2">{streakLabel(rec.streak)}</span>
        <div className="ml-auto flex flex-wrap items-center gap-3">
          {days.length > 1 && (
            <span className="inline-flex overflow-hidden rounded-lg border border-border-strong" role="group" aria-label="Pick a day">
              {days.map((d) => (
                <button key={d.run_id} type="button" title={d.theme} aria-pressed={d.run_id === rec.run_id}
                  onClick={() => { setRun(d.run_id); setCur(0); }}
                  className={cn("px-2.5 py-1 text-[11.5px] font-semibold",
                    d.run_id === rec.run_id ? "bg-accent-soft text-accent" : "text-muted hover:text-text")}>
                  {dayChip(d.date)}{d.slot === "pm" && " PM"}
                </button>
              ))}
            </span>
          )}
          {post && <a href={post.url} target="_blank" rel="noreferrer" className="text-[13px] font-semibold text-accent hover:text-accent-hover">Read it on Substack ↗</a>}
        </div>
      </div>
      <h2 className="mt-2.5 font-serif text-[21px] font-bold leading-tight text-text md:text-[23px]">{rec.theme}</h2>
      <div className="mt-3.5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-2.5">
          <div className="no-scrollbar flex gap-1.5 overflow-x-auto">
            {rec.exhibits.map((e, i) => (
              <button key={e.file} type="button" onClick={() => setCur(i)}
                className={cn("shrink-0 whitespace-nowrap rounded-full border px-3 py-1 text-xs",
                  e === ex ? "border-accent bg-accent-soft font-semibold text-accent" : "border-border-strong text-text-2 hover:text-text")}>
                <b className={cn("mr-1", e === ex ? "text-accent" : "text-muted")}>{e.n}</b>
                {e.title.replace(/^Exhibit \d+:\s*/, "").replace(/ · last.*$/, "")}
              </button>
            ))}
          </div>
          {ex.data ? (
            <ThemeChartCard key={`${rec.run_id}/${ex.file}`} ex={ex} png={chartUrl(rec, ex.file)} />
          ) : ( // runs before 2026-10-15 (and a chart whose data failed) have only the PNG
            <img src={chartUrl(rec, ex.file)} alt={`${ex.title}. ${ex.subtitle}`} className="w-full rounded-[10px] border border-border" />
          )}
        </div>
        <Why key={rec.run_id} rec={rec} />
      </div>
    </section>
  );
}
