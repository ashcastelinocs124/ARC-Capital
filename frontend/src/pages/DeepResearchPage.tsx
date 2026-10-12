import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Download, Link2 } from "lucide-react";
import { isWeekly } from "@/api/endpoints";
import { useWeekly, useWeeklyHistory, useWeeklyPosts } from "@/hooks/useWeekly";
import { WeeklyReport } from "@/components/WeeklyReport";
import { PostCard } from "@/components/DailyPostsFeed";
import { PageIntro } from "@/components/layout/PageIntro";

const MD = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const fmtRange = (start: string, end: string) => {
  if (!start || !end) return "";
  const [a, b] = [new Date(`${start}T00:00:00Z`), new Date(`${end}T00:00:00Z`)];
  return a.getUTCMonth() === b.getUTCMonth() ? `${MD.format(a)}–${b.getUTCDate()}` : `${MD.format(a)}–${MD.format(b)}`;
};
const weekNo = (w: string) => Number(w.split("-W")[1]);
// The next Sunday 08:00 ET release (today, if it's Sunday before 08:00 in New York).
function nextSunday(now = new Date()): string {
  const ny = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const add = ny.getDay() === 0 && ny.getHours() < 8 ? 0 : (7 - ny.getDay()) % 7 || 7;
  ny.setDate(ny.getDate() + add);
  return `${ny.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })}, 08:00 ET`;
}

// ?week= opens the on-site paged report (the weeks from before the Substack posts, or a shared link).
function WeekReport({ week }: { week: string }) {
  const { data, isLoading } = useWeekly(week);
  const rec = isWeekly(data) ? data : undefined;
  const [copied, setCopied] = useState(false);
  const copyLink = async () => {
    const url = `${window.location.origin}/deep-research?week=${week}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      window.prompt("Copy this link", url); // clipboard blocked (e.g. not https)
    }
  };
  // ponytail: the browser's own Save as PDF (print styles in index.css show only #report).
  const downloadPdf = () => {
    const title = document.title;
    document.title = `ARC Weekly Deep Dive ${week}`; // the default PDF file name
    window.print();
    document.title = title;
  };
  return (
    <div className="space-y-4 p-4 md:p-8">
      <div className="flex items-baseline justify-between gap-3 no-print">
        <Link to="/deep-research" className="text-[13px] font-semibold text-accent hover:text-accent-hover">‹ All deep dives</Link>
        {rec && (
          <div className="flex shrink-0 items-center gap-4">
            <button onClick={downloadPdf} className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:text-accent-hover">
              <Download className="h-3.5 w-3.5" />Download PDF
            </button>
            <button onClick={copyLink} className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:text-accent-hover">
              <Link2 className="h-3.5 w-3.5" />{copied ? "Link copied" : "Copy link"}
            </button>
          </div>
        )}
      </div>
      {isLoading && <div className="text-sm text-muted">Loading…</div>}
      {!isLoading && !rec && <div className="card p-6 text-sm text-muted">No deep dive for {week}.</div>}
      {rec && <div id="report"><WeeklyReport rec={rec} /></div>}
    </div>
  );
}

export default function DeepResearchPage() {
  const [params] = useSearchParams();
  const week = params.get("week");
  const { data: posts = [], isLoading } = useWeeklyPosts();
  const { data: histRaw } = useWeeklyHistory();
  if (week) return <WeekReport week={week} />;

  const weeks = histRaw && !Array.isArray(histRaw) && Array.isArray(histRaw.items) ? histRaw.items : [];
  const onSubstack = new Set(posts.map((p) => p.week));
  const earlier = weeks.filter((w) => !onSubstack.has(w.week));
  return (
    <div className="space-y-5 p-4 md:p-8">
      <PageIntro kicker="Deep Research" title="A deep dive into what happened in the markets this week"
        when={{ label: "Next report", value: nextSunday(), note: "Covers Monday–Friday" }}>
        Every Sunday morning, ARC's research desk reads the week's Morning Notes, picks the 10 to 12 stories that
        mattered, and splits them across five specialist agents that pull the data behind each one. An editor then challenges every
        finding before writing it up. Every number in the report traces back to a cited data series.
      </PageIntro>
      {isLoading && <div className="text-sm text-muted">Loading…</div>}
      {!isLoading && posts.length === 0 && earlier.length === 0 && (
        <div className="card p-6 text-sm text-muted">No deep dives yet. The first one arrives Sunday morning.</div>
      )}
      <div className="space-y-4">
        {posts.map((p, i) => (
          // ponytail: the first five trends; the post has all of them
          <PostCard key={p.url} p={{ ...p, takeaways: p.takeaways.slice(0, 5) }} latest={i === 0}
            eyebrow={`Week ${weekNo(p.week)} · ${fmtRange(p.start, p.end)}`} />
        ))}
      </div>
      {earlier.length > 0 && (
        <div>
          <h3 className="py-1 text-[15px] font-semibold text-text">
            Earlier deep dives <span className="text-xs font-normal text-muted">· on-site, before Substack · {earlier.length}</span>
          </h3>
          <div className="card mt-2 overflow-hidden">
            {earlier.map((w) => (
              <Link key={w.week} to={`/deep-research?week=${w.week}`}
                className="grid grid-cols-[110px_1fr_auto] gap-3 border-t border-border px-5 py-3 first:border-0 hover:bg-surface-2">
                <span className="eyebrow">Wk {weekNo(w.week)} · {fmtRange(w.start, w.end)}</span>
                <span className="text-sm text-text-2">{w.title}</span>
                <span className="text-[13px] font-semibold text-accent">Read ›</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
