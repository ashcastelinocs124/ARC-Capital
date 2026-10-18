import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useWeeklyPosts } from "@/hooks/useWeekly";
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

export default function DeepResearchPage() {
  const [params] = useSearchParams();
  const week = params.get("week");
  const { data: posts = [], isLoading } = useWeeklyPosts();
  // ?week= opens that week's Substack post; the site never shows its own copy of a report.
  const post = week ? posts.find((p) => p.week === week) : undefined;
  useEffect(() => {
    if (post) window.location.replace(post.url);
  }, [post]);
  if (week) {
    if (isLoading || post) return <div className="p-8 text-sm text-muted">Opening the Substack post…</div>;
    return (
      <div className="space-y-3 p-4 md:p-8">
        <Link to="/deep-research" className="text-xs font-medium text-accent hover:text-accent-hover">‹ All deep dives</Link>
        <div className="card p-6 text-sm text-muted">The deep dive for {week} isn't published on Substack.</div>
      </div>
    );
  }
  return (
    <div className="space-y-5 p-4 md:p-8">
      <PageIntro kicker="Deep Research" title="A deep dive into what happened in the markets this week"
        when={{ label: "Next report", value: nextSunday(), note: "Covers Monday–Friday" }}>
        Every Sunday morning, ARC's research desk reads the week's Morning Notes, picks the 10 to 12 stories that
        mattered, and splits them across five specialist agents that pull the data behind each one. An editor then challenges every
        finding before writing it up. Every number in the report traces back to a cited data series.
      </PageIntro>
      {isLoading && <div className="text-sm text-muted">Loading…</div>}
      {!isLoading && posts.length === 0 && (
        <div className="card p-6 text-sm text-muted">No deep dives yet. The first one arrives Sunday morning.</div>
      )}
      <div className="space-y-4">
        {posts.map((p, i) => (
          // ponytail: the first five trends; the post has all of them
          <PostCard key={p.url} p={{ ...p, takeaways: p.takeaways.slice(0, 5) }} latest={i === 0}
            eyebrow={p.topic ? `${p.topic} · ${MD.format(new Date(`${p.start}T00:00:00Z`))}` : `Week ${weekNo(p.week)} · ${fmtRange(p.start, p.end)}`} />
        ))}
      </div>
    </div>
  );
}
