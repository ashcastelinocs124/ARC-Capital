import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useThemePosts } from "@/hooks/useThemes";
import { PostCard } from "@/components/DailyPostsFeed";
import { PageIntro } from "@/components/layout/PageIntro";

const DAY = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

// The next weekday 08:00 run, in New York time.
function nextRun(now = new Date()): string {
  const ny = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const wd = ny.getDay();
  if (wd >= 1 && wd <= 5 && ny.getHours() < 8) return "Today, 08:00 ET";
  return wd >= 1 && wd <= 4 ? "Tomorrow, 08:00 ET" : "Monday, 08:00 ET";
}

// /themes lists the Theme Charts posts on Substack; ?run= (an older X thread's link) opens that run's post.
export default function ThemesPage() {
  const run = useSearchParams()[0].get("run");
  const { data: posts = [], isLoading } = useThemePosts();
  const post = run ? posts.find((p) => p.run_id === run) : undefined;
  useEffect(() => {
    if (post) window.location.replace(post.url);
  }, [post]);
  if (run) {
    if (isLoading || post) return <div className="p-8 text-sm text-muted">Opening the Substack post…</div>;
    return (
      <div className="space-y-3 p-4 md:p-8">
        <Link to="/themes" className="text-xs font-medium text-accent hover:text-accent-hover">‹ All theme charts</Link>
        <div className="card p-6 text-sm text-muted">The theme charts for {run} aren't published on Substack.</div>
      </div>
    );
  }
  return (
    <div className="space-y-5 p-4 md:p-8">
      <PageIntro kicker="Theme Charts" title="The day's #1 macro theme, in charts"
        steps={["News & X", "Market moves", "Polymarket", "Pick the theme", "Draw the charts"]} highlight={3}
        when={{ label: "Next post", value: nextRun(), note: "Weekdays before the open" }}>
        Every weekday before the open an agent reads what the news and financial X are talking about, which markets
        moved most and where Polymarket odds swung, picks the single biggest macro theme and draws the charts that show
        it. Every number on a chart is market data. Each one is posted on Substack.
      </PageIntro>
      {isLoading && <div className="text-sm text-muted">Loading…</div>}
      {!isLoading && posts.length === 0 && (
        <div className="card p-6 text-sm text-muted">No theme charts on Substack yet. Next post: {nextRun()}.</div>
      )}
      <div className="space-y-4">
        {posts.map((p, i) => (
          <PostCard key={p.url} p={p} latest={i === 0} eyebrow={DAY.format(new Date(`${p.date}T00:00:00Z`))} />
        ))}
      </div>
    </div>
  );
}
