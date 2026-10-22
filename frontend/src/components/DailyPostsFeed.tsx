import { isNote, type DailyPost } from "@/api/endpoints";

const DAY = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const day = (d: string) => new Date(`${d}T00:00:00Z`);

// One published Substack post: cover left, title and takeaways right (also the Deep Research weekly feed).
export function PostCard({ p, latest, eyebrow }: {
  p: Pick<DailyPost, "title" | "takeaways" | "image" | "url">;
  latest: boolean;
  eyebrow: string;
}) {
  return (
    <a
      href={p.url}
      target="_blank"
      rel="noopener noreferrer"
      className="card group flex flex-col gap-5 p-5 transition-shadow hover:shadow-card-hover md:flex-row md:gap-7 md:p-6"
    >
      <div className="aspect-[1536/936] w-full shrink-0 overflow-hidden rounded-2xl bg-gradient-to-br from-[#0b3d24] via-accent to-[#9ad7b6] md:w-[44%]">
        {p.image && <img src={p.image} alt="" loading="lazy" className="h-full w-full object-cover" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2.5">
          <span className="eyebrow">{eyebrow}</span>
          <span className="pill">{latest ? "LATEST · SUBSTACK" : "SUBSTACK"}</span>
        </div>
        <h3 className="mt-3 text-xl font-semibold leading-snug tracking-tight text-text md:text-2xl">{p.title}</h3>
        {p.takeaways.length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-relaxed text-text-2">
            {p.takeaways.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        )}
        <div className="mt-4 text-[13px] font-semibold text-accent">Read on Substack ↗</div>
      </div>
    </a>
  );
}

// Only Substack posts: the site links to each published note, never hosts its own copy.
export function DailyPostsFeed({ posts, loading }: { posts: DailyPost[]; loading: boolean }) {
  return (
    <div className="space-y-5 p-4 md:p-8">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-text">Memo</h2>
        <p className="mt-0.5 text-xs text-muted">Daily Updates and Theme Charts from the ARC Research Substack. Each one opens the post.</p>
      </div>
      {loading && <div className="text-sm text-muted">Loading…</div>}
      {!loading && posts.length === 0 && (
        <div className="card p-6 text-sm text-muted">No published posts yet. They appear here once a note or Theme Charts post is published on Substack.</div>
      )}
      <div className="space-y-4">
        {posts.map((p, i) => (
          <PostCard key={p.url} p={p} latest={i === 0} eyebrow={`${isNote(p) ? "" : "Theme Charts · "}${DAY.format(day(p.date))}`} />
        ))}
      </div>
    </div>
  );
}
